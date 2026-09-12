#!/usr/bin/env python3
from __future__ import annotations

import argparse
import html
import json
import sys
from collections import Counter
from fractions import Fraction
from pathlib import Path

RANK_ORDER = "AKQJT98765432"
RANK_VALUE = {r: 14-i for i, r in enumerate(RANK_ORDER)}
FR = {"A":"As","K":"Roi","Q":"Dame","J":"Valet","T":"10","9":"9","8":"8","7":"7","6":"6","5":"5","4":"4","3":"3","2":"2","-":"chicane"}
HONORS = set("AKQJT")

CASES = [
    {"id":"BS_A","north":"KJ98765","south":"2","display":["RV98765","2"],"target":5},
    {"id":"BS_B","north":"AT987","south":"Q432","display":["AX987","D432"],"target":4},
    {"id":"BS_C","north":"K432","south":"QT5","display":["R432","DX5"],"target":3},
    {"id":"BS_D","north":"AQT32","south":"654","display":["ADX32","654"],"target":4},
    {"id":"BS_E","north":"AJ32","south":"K954","display":["AV32","R954"],"target":4},
    {"id":"SUITPLAY_ENC","north":"AT42","south":"953","display":["AX42","953"],"target":2},
    {"id":"ROUD_2","north":"K62","south":"AJ853","display":["R62","AV853"],"target":5},
    {"id":"BH_1","north":"AQ9","south":"65","display":["AD9","65"],"target":2},
    {"id":"BH_2","north":"AT9","south":"Q65","display":["AX9","D65"],"target":3},
    {"id":"X98_ARD7","north":"T98","south":"AKQ7","display":["X98","ARD7"],"target":4},
]


def pct(f: Fraction) -> str:
    return f"{float(f)*100:.2f}".replace(".", ",") + " %"


def fr_article(rank: str) -> str:
    return {"A":"l’As","K":"le Roi","Q":"la Dame","J":"le Valet","T":"le 10"}.get(rank, "le "+FR.get(rank,rank))


def relation_for_defender(lead_seat: str, defender: str) -> str:
    if lead_seat == "N":
        return "en deuxième" if defender == "E" else "en quatrième"
    return "en deuxième" if defender == "W" else "en quatrième"


def holding_cards(eng, mask: int) -> set[str]:
    return {eng.I2R[r] for r in eng.ranks(mask)}


def root_action_masks(eng, e, root):
    rows=[]
    for seat,hand in (("N",root.north),("S",root.south)):
        for r in eng.ranks(hand):
            lead=eng.PublicState(root.north,root.south,root.west_seen,root.east_seen,
                                 root.west_void,root.east_void,seat,0,tuple(),root.won)
            ns=e.decl_play(lead,seat,r)
            fr=e.frontier(ns)
            if not fr:
                continue
            best=max(fr,key=lambda m:(e.model.weight(m),m))
            rows.append({"seat":seat,"rank":eng.I2R[r],"mask":best,"prob":e.model.weight(best),"state":ns})
    rows.sort(key=lambda x:(-x["prob"],x["seat"],RANK_ORDER.index(x["rank"])))
    return rows


def select_decl(eng, e, s, mask):
    seat=e.order(s.leader)[s.pos]
    hand=s.north if seat=="N" else s.south
    acts=eng.ranks(hand) if hand else (eng.VOID,)
    cands=[]
    for r in acts:
        ns=e.close(e.decl_play(s,seat,r))
        for cm in e.frontier(ns):
            if (mask|cm)==cm:
                cands.append((r,ns,cm))
    if not cands:
        return None
    cands.sort(key=lambda x:(x[0],-float(e.model.weight(x[2])),-x[2]))
    r,ns,cm=cands[0]
    return seat,("-" if not r else eng.I2R[r]),ns,cm


def select_def_child(e,s,mask,seat,r,legal):
    ns=e.close(e.def_play(s,seat,r))
    need=mask & legal
    feasible=[cm for cm in e.frontier(ns) if (need|cm)==cm]
    if not feasible:
        return None
    cm=max(feasible,key=lambda x:(e.model.weight(x),x))
    return ns,cm


def first_defender_map(eng,e,lead_row):
    s=lead_row["state"]
    mask=lead_row["mask"]
    dseat=e.order(s.leader)[s.pos]
    rows=[]
    for r,legal in e.defender_actions(s,dseat):
        need=mask & legal
        if not need:
            continue
        child=select_def_child(e,s,mask,dseat,r,legal)
        if child is None:
            continue
        ns,cm=child
        term=e.terminal(ns)
        dec=None if term is not None else select_decl(eng,e,ns,cm)
        rows.append({
            "defender":dseat,
            "def_card":"-" if not r else eng.I2R[r],
            "mass":e.model.weight(need),
            "next":None if dec is None else (dec[0],dec[1]),
        })
    return rows


def root_phrase(lead, branches):
    seat=lead["seat"]; rank=lead["rank"]
    mass_by={}
    for b in branches:
        if b["next"] is not None:
            mass_by[b["next"]]=mass_by.get(b["next"],Fraction(0))+b["mass"]
    target=max(mass_by,key=mass_by.get) if mass_by else None
    if target and target[0] != seat:
        tr=target[1]
        if rank in "765432":
            return f"Commencer par petit vers {fr_article(tr)}.", target
        if rank in "98T":
            return f"Commencer par {fr_article(rank)} vers {fr_article(tr)}.", target
    if rank == "A":
        return "Tirer l’As.", target
    if rank == "K":
        return "Tirer le Roi.", target
    if rank == "Q":
        return "Présenter la Dame.", target
    if rank == "J":
        return "Présenter le Valet.", target
    return f"Commencer par {fr_article(rank)}.", target


def cover_clause(branches, default_target):
    if default_target is None:
        return ""
    default_rank=default_target[1]
    clauses=[]
    for b in branches:
        if b["next"] is None:
            continue
        nr=b["next"][1]
        dc=b["def_card"]
        if dc in HONORS and nr != default_rank and nr in HONORS and RANK_VALUE[nr] > RANK_VALUE[dc]:
            clauses.append((dc,nr,b["mass"]))
    if not clauses:
        return ""
    dc,nr,_=max(clauses,key=lambda x:x[2])
    return f" Si l’adversaire intercale {fr_article(dc)}, couvrir avec {fr_article(nr)}."


def mask_worlds(eng,e,mask):
    for i in range(e.model.n):
        if (mask>>i)&1:
            yield i,e.model.world_w[i],e.model.world_e[i],e.model.weights[i]


def position_features(eng,e,mask,lead_seat):
    if not mask:
        return []
    worlds=list(mask_worlds(eng,e,mask))
    visible=holding_cards(eng,e.initial().north)|holding_cards(eng,e.initial().south)
    missing=[r for r in RANK_ORDER if r not in visible]
    missing_h=[r for r in missing if r in HONORS]
    out=[]
    splits=[]
    for _,w,east,_ in worlds:
        splits.append(tuple(sorted((w.bit_count(),east.bit_count()),reverse=True)))
    if len(set(splits))==1:
        a,b=splits[0]
        out.append(f"le partage {a}–{b}")
    for h in missing_h:
        vals=[]
        bit=1<<eng.R2I[h]
        for _,w,east,_ in worlds:
            if w&bit:
                vals.append(("W",w.bit_count()))
            elif east&bit:
                vals.append(("E",east.bit_count()))
        if vals and len(set(vals))==1:
            seat,n=vals[0]
            adj={1:"sec",2:"second",3:"troisième",4:"quatrième",5:"cinquième",6:"sixième"}.get(n,f"{n}e")
            out.append(f"{fr_article(h)} {adj} {relation_for_defender(lead_seat,seat)}")
        elif vals and len({x[0] for x in vals})==1:
            seat=vals[0][0]; lens=sorted({x[1] for x in vals})
            if lens==[1,2]:
                out.append(f"{fr_article(h)} sec ou second {relation_for_defender(lead_seat,seat)}")
    for i,a in enumerate(missing_h):
        for b in missing_h[i+1:]:
            bit_a=1<<eng.R2I[a]; bit_b=1<<eng.R2I[b]
            vals=[]
            for _,w,east,_ in worlds:
                if (w&bit_a) and (w&bit_b): vals.append(("W",w.bit_count()))
                elif (east&bit_a) and (east&bit_b): vals.append(("E",east.bit_count()))
                else: vals.append(None)
            if vals and None not in vals and len(set(vals))==1:
                seat,n=vals[0]
                adj={1:"secs",2:"seconds",3:"troisièmes",4:"quatrièmes"}.get(n,f"{n}es")
                out.append(f"{FR[a]}-{FR[b]} groupés {adj} {relation_for_defender(lead_seat,seat)}")
    ded=[]
    for x in out:
        if x not in ded:
            ded.append(x)
    return ded[:4]


def auto_why(eng,e,best,alt):
    if alt is None:
        return "Plusieurs premiers coups atteignent exactement la même probabilité ; aucun ne doit être présenté comme supérieur sans autre raison de bridge.", {}
    gain=best["mask"] & ~alt["mask"]
    loss=alt["mask"] & ~best["mask"]
    gf=position_features(eng,e,gain,best["seat"])
    lf=position_features(eng,e,loss,best["seat"])
    gp=e.model.weight(gain); lp=e.model.weight(loss)
    alt_name=f"{fr_article(alt['rank'])} depuis l’autre main" if alt["seat"]!=best["seat"] else fr_article(alt["rank"])
    if gf:
        text="On cherche notamment à profiter de " + ", ".join(gf) + "."
        if gp:
            text += f" Ces positions représentent {pct(gp)} du modèle exact."
        if lf:
            text += " L’alternative " + alt_name + " gagne en échange " + ", ".join(lf) + "."
        if lp:
            text += f" Son gain propre ne pèse que {pct(lp)}."
        return text,{"gain":str(gp),"loss":str(lp),"gain_features":gf,"loss_features":lf}
    text=f"Le premier coup choisi gagne exactement {pct(gp)} de positions que l’alternative {alt_name} perd."
    if lp:
        text+=f" L’alternative gagne de son côté {pct(lp)} d’autres positions."
    text+=" Les positions différentielles restent trop variées pour être résumées proprement par une seule formule de bridge : le texte doit rester en revue."
    return text,{"gain":str(gp),"loss":str(lp),"gain_features":gf,"loss_features":lf}


def trace_principal(eng,e,lead,max_steps=24):
    s=lead["state"]; mask=lead["mask"]; out=[]
    for _ in range(max_steps):
        term=e.terminal(s)
        if term is not None:
            break
        seat=e.order(s.leader)[s.pos]
        if seat in eng.DECL:
            z=select_decl(eng,e,s,mask)
            if z is None: break
            seat,rank,s,mask=z
            out.append(f"{seat}:{rank}")
        else:
            choices=[]
            for r,legal in e.defender_actions(s,seat):
                need=mask&legal
                if not need: continue
                child=select_def_child(e,s,mask,seat,r,legal)
                if child is None: continue
                ns,cm=child
                choices.append((e.model.weight(need),r,ns,cm))
            if not choices: break
            _,r,s,mask=max(choices,key=lambda x:(x[0],x[1]))
            out.append(f"{seat}:{'-' if not r else eng.I2R[r]}")
    return out


def make_html(rows, out_path):
    cards=[]
    for r in rows:
        auto=html.escape(r["auto_maniement"])
        why=html.escape(r["auto_why"])
        gold=html.escape(r.get("reference_maniement") or "—")
        goldwhy=html.escape(r.get("reference_why") or "—")
        status=html.escape(r["status"])
        h1,h2=map(html.escape,r["display"])
        expert=html.escape(json.dumps(r["expert"],ensure_ascii=False,indent=2))
        cards.append(f'''<article class="card">
<div class="head"><div class="holding"><span>{h1}</span><span>{h2}</span></div><div><b>{r['target']} levées</b><div class="prob">{html.escape(r['probability_percent'])}</div><div class="frac">{html.escape(r['probability_fraction'])}</div></div><span class="badge">{status}</span></div>
<div class="grid"><section><h3>Généré automatiquement</h3><p class="line">{auto}</p><h4>Pourquoi ? / position recherchée</h4><p>{why}</p></section><section class="gold"><h3>Référence de revue</h3><p class="line">{gold}</p><h4>Pourquoi ?</h4><p>{goldwhy}</p></section></div>
<details><summary>Détail exact / diagnostic</summary><pre>{expert}</pre></details></article>''')
    doc=f'''<!doctype html><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1"><title>MANIEMENTS V5 — V4.4 batch auto-human</title>
<style>body{{margin:0;background:#0b0f14;color:#edf3f9;font:15px/1.5 system-ui}}main{{max-width:1180px;margin:30px auto;padding:0 16px 60px}}h1{{font-size:30px;margin-bottom:4px}}.intro{{color:#aab9c9;margin-bottom:20px}}.card{{background:#141b24;border:1px solid #2b3745;border-radius:16px;padding:18px;margin:14px 0}}.head{{display:grid;grid-template-columns:160px 1fr auto;gap:18px;align-items:center}}.holding{{display:grid;justify-items:center;width:max-content;font:800 24px/1.05 ui-monospace,monospace}}.prob{{font-size:23px;color:#6fdaa0;font-weight:800}}.frac{{color:#92a5ba}}.badge{{border:1px solid #6b5821;color:#ffdc76;border-radius:999px;padding:4px 9px;font-size:12px}}.grid{{display:grid;grid-template-columns:1fr 1fr;gap:18px;margin-top:16px}}section{{background:#0f151d;border-radius:12px;padding:14px}}section.gold{{border:1px dashed #3c4d60}}h3{{margin:0 0 10px}}h4{{margin:14px 0 5px;color:#c6d5e5}}.line{{border-left:4px solid #dfb64f;padding-left:10px}}details{{margin-top:12px}}pre{{white-space:pre-wrap;color:#aebfd0;background:#0d1218;padding:10px;border-radius:8px;overflow:auto}}@media(max-width:760px){{.head{{grid-template-columns:1fr}}.grid{{grid-template-columns:1fr}}}}</style><main><h1>V4.4 — batch automatique, 10 cas</h1><p class="intro">La colonne de gauche est produite sans recopier le texte de référence. La colonne de droite sert de contrôle humain. Aucun candidat n’est promu en production par ce rapport seul.</p>{''.join(cards)}</main>'''
    out_path.write_text(doc,encoding="utf-8")


def main():
    ap=argparse.ArgumentParser()
    ap.add_argument("--runtime-root",required=True)
    ap.add_argument("--reference",required=True)
    ap.add_argument("--x98-reference",required=True)
    ap.add_argument("--out-dir",required=True)
    a=ap.parse_args()

    sys.path.insert(0,str(Path(a.runtime_root)/"runtime"))
    import integrated_engine as eng

    refs=json.loads(Path(a.reference).read_text(encoding="utf-8"))
    ref_by={x["id"]:x for x in refs["cases"]}
    x98=json.loads(Path(a.x98_reference).read_text(encoding="utf-8"))
    out=[]

    for c in CASES:
        e=eng.Engine2(c["north"],c["south"],c["target"])
        solved=e.solve(include_policy=False)
        optimum=Fraction(solved["probability_fraction"])
        root=e.initial()
        roots=root_action_masks(eng,e,root)
        if not roots:
            raise RuntimeError(f"no root actions for {c['id']}")
        best=roots[0]
        if best["prob"] != optimum:
            raise AssertionError((c["id"],best["prob"],optimum))
        alt=next((x for x in roots[1:] if x["prob"] < best["prob"]),None)
        branches=first_defender_map(eng,e,best)
        opening,target=root_phrase(best,branches)
        auto_line=opening + cover_clause(branches,target)
        why,delta=auto_why(eng,e,best,alt)
        status="AUTO_REVIEW"
        if c["id"]=="X98_ARD7":
            status="CALIBRATION_HUMAN_TREE_EXACT"
        ref=ref_by.get(c["id"])
        if c["id"]=="X98_ARD7":
            ref_line=x98["human_line_fr"]; ref_why=x98["why_fr"]
        else:
            ref_line=ref.get("maniement_fr") if ref else None
            ref_why=ref.get("why_fr") if ref else None
        out.append({
            "id":c["id"],"north":c["north"],"south":c["south"],"display":c["display"],"target":c["target"],
            "probability_fraction":str(optimum),"probability_percent":pct(optimum),"status":status,
            "auto_maniement":auto_line,"auto_why":why,
            "reference_maniement":ref_line,"reference_why":ref_why,
            "expert":{
                "best_root":f"{best['seat']}:{best['rank']}",
                "best_root_probability":str(best["prob"]),
                "alternative_root":None if alt is None else f"{alt['seat']}:{alt['rank']}",
                "alternative_probability":None if alt is None else str(alt["prob"]),
                "differential":delta,
                "first_defender_map":[{"card":b["def_card"],"next":b["next"],"mass":str(b["mass"])} for b in branches],
                "principal_exact_trace":trace_principal(eng,e,best),
            }
        })

    od=Path(a.out_dir); od.mkdir(parents=True,exist_ok=True)
    (od/"HUMAN_V44_BATCH.json").write_text(json.dumps({"schema":"MANIEMENTS_V5_HUMAN_V44_BATCH_V1","status":"AUTO_REVIEW","cases":out},ensure_ascii=False,indent=2)+"\n",encoding="utf-8")
    make_html(out,od/"MANIEMENTS_V5_HUMAN_V44_BATCH_REVIEW.html")
    print(json.dumps({"cases":len(out),"out_dir":str(od)},ensure_ascii=False))


if __name__=="__main__":
    main()

#!/usr/bin/env python3
from __future__ import annotations

import argparse
import html
import json
import sys
import time
from fractions import Fraction
from pathlib import Path

HERE = Path(__file__).resolve().parent
FR_IN = {"R":"K","D":"Q","V":"J","X":"T"}
FR_OUT = {"K":"R","Q":"D","J":"V","T":"X"}
RVAL = {"2":2,"3":3,"4":4,"5":5,"6":6,"7":7,"8":8,"9":9,"T":10,"J":11,"Q":12,"K":13,"A":14}
RUNTIME_SHA = "a0b580531f3c9e8bb00710b9c3e1c183b27cbfe9231c9d584e29a374ba88835d"


def normalize(text: str) -> str:
    s = str(text or "").replace("10", "T")
    for ch in " -_,./":
        s = s.replace(ch, "")
    vals=[];seen=set()
    for raw in s:
        if raw == "x":
            raise ValueError("V6.0 prototype: cartes exactes uniquement; x générique viendra après validation.")
        c=FR_IN.get(raw.upper(),raw.upper())
        if c not in RVAL: raise ValueError(f"rang invalide: {raw}")
        if c in seen: raise ValueError(f"carte répétée: {raw}")
        seen.add(c);vals.append(c)
    if not vals: raise ValueError("main vide")
    return "".join(sorted(vals,key=lambda c:RVAL[c],reverse=True))


def frhand(s: str) -> str:
    return "".join(FR_OUT.get(c,c) for c in s)


def frac_pct(f: Fraction) -> float:
    return round(float(f)*100.0,8)


def frozen(v):
    if isinstance(v, tuple): return [frozen(x) for x in v]
    if isinstance(v, list): return [frozen(x) for x in v]
    if isinstance(v, dict): return {str(k):frozen(x) for k,x in v.items()}
    return v


def load_modules(runtime_root: Path, tools_root: Path):
    for p in (runtime_root, runtime_root/"runtime"):
        if (p/"integrated_engine.py").exists():
            sys.path.insert(0,str(p));break
    sys.path.insert(0,str(tools_root))
    import integrated_engine as eng
    import human_motif_search_v57 as v57
    # Importing V5.72 applies the reviewed V5.71 continuation fix to the shared
    # V57 module: once a finesse sequence is exhausted, finish by cashing the
    # highest remaining partnership card instead of terminating the maneuver.
    import human_motif_search_v572 as _v572_patch
    import human_motif_search_v59 as v59
    import human_sequence_search_v512 as v512
    import human_conditional_motifs_v513 as v513
    import human_progressive_shortage_v514 as v514
    import human_layout_reason_v581 as v581
    import prototype_v3_inspect as inspect
    import human_oracle_v61 as v61
    import human_adaptive_prefix_v62 as v62
    import human_semantic_v62 as sem62
    return eng,v57,v59,v512,v513,v514,v581,inspect,v61,v62,sem62


def motif_label(source, spec, kind=None):
    if source == "V57":
        cash, feeder, target, seq = spec
        if not seq:
            return "JEU_EN_TETE"
        if cash:
            return "COUP_DE_SONDE_PUIS_IMPASSE" if len(cash)==1 else "TIRAGE_EN_TETE_PUIS_IMPASSE"
        return "IMPASSE_REPETEE" if len(seq)>1 else "IMPASSE_SIMPLE"
    if source == "V512":
        if spec.get("probe"):
            return "HONNEUR_SONDE_PUIS_MANOEUVRE"
        seq=tuple(spec.get("seq") or ())
        cash=tuple(spec.get("cash") or ())
        mode=spec.get("mode")
        if cash and seq:
            return "COUP_DE_SONDE_PUIS_IMPASSE" if len(cash)==1 else "TIRAGE_EN_TETE_PUIS_IMPASSE"
        if seq:
            # An ordered sequence beginning by a top honor reached from the
            # opposite hand is functionally a probe/cash before the later
            # finesse rounds, even when V512 encodes it inside seq rather than
            # in the separate cash field.
            if len(seq)>1 and seq[0] in ("A","K"):
                return "COUP_DE_SONDE_PUIS_IMPASSE"
            base="IMPASSE_REPETEE" if len(seq)>1 else "IMPASSE_SIMPLE"
            return base+"_LAISSER_COURIR" if mode=="duck" else base
        return "AUTRE_SEQUENCE"
    if source == "V513":
        return kind or "CONDITIONNEL"
    if source == "V514":
        return "EPUISEMENT_PROGRESSIF"
    return source


def complexity(source, spec, lines):
    raw=json.dumps(frozen(spec),ensure_ascii=False,separators=(",",":"))
    return (len(lines),len(raw),source)


def candidate_id(source, label, spec):
    return source+":"+label+":"+json.dumps(frozen(spec),sort_keys=True,ensure_ascii=True,separators=(",",":"))


def add_candidate(rows, *, source, label, spec, lines, prob, mask, oracle, target_hand=None):
    p=Fraction(prob)
    if p <= 0:
        return
    rows.append({
        "id":candidate_id(source,label,spec),
        "source":source,
        "label":label,
        "spec":frozen(spec),
        "lines_provisional":list(lines or []),
        "fraction":str(p),
        "percent":frac_pct(p),
        "mask":str(mask),
        "optimal":p==oracle,
        "gap_points":round(float(oracle-p)*100.0,8),
        "target_hand":target_hand,
        "complexity":list(complexity(source,spec,lines or [])),
    })


def collect_candidates(mods, north, south, target, oracle):
    eng,v57,v59,v512,v513,v514,v581,inspect,v61,v62,sem62=mods
    display=[frhand(north),frhand(south)]
    rows=[];stats={}

    t0=time.monotonic();tested=0
    for spec in v57.candidate_specs(north,south):
        try:
            prob,mask=v57.evaluate(eng,north,south,target,*spec);tested+=1
        except Exception:
            continue
        cash,feeder,tgt,seq=spec
        add_candidate(rows,source="V57",label=motif_label("V57",spec),spec={"cash":cash,"feeder":feeder,"target":tgt,"seq":seq},
                      lines=v57.procedure(cash,feeder,tgt,seq,display),prob=prob,mask=mask,oracle=oracle,target_hand=tgt)
    stats["V57"]={"tested":tested,"seconds":round(time.monotonic()-t0,3)}

    t0=time.monotonic();tested=0
    # V512 is the broadest ordered-sequence family. It evaluates using V59's exact replay.
    for spec in v512.specs(north,south):
        try:
            prob,mask=v59.evaluate(eng,north,south,target,spec);tested+=1
        except Exception:
            continue
        label=motif_label("V512",spec)
        add_candidate(rows,source="V512",label=label,spec=spec,lines=v59.lines(spec,display),
                      prob=prob,mask=mask,oracle=oracle,target_hand=spec.get("target"))
    stats["V512"]={"tested":tested,"seconds":round(time.monotonic()-t0,3)}

    t0=time.monotonic();tested=0
    for kind,stream in (("DROP_SWITCH",v513.drop_specs(north,south)),("SAFETY_FORCE",v513.safety_specs(north,south))):
        for spec in stream:
            try:
                prob,mask=v513.evaluate(eng,north,south,target,spec,kind);tested+=1
            except Exception:
                continue
            add_candidate(rows,source="V513",label=kind,spec=spec,lines=v513.describe(kind,spec,display),
                          prob=prob,mask=mask,oracle=oracle,target_hand=spec.get("target"))
    stats["V513"]={"tested":tested,"seconds":round(time.monotonic()-t0,3)}

    t0=time.monotonic();tested=0
    for spec in v514.spec_candidates(north,south):
        try:
            prob,mask=v514.evaluate(eng,north,south,target,spec);tested+=1
        except Exception:
            continue
        add_candidate(rows,source="V514",label="EPUISEMENT_PROGRESSIF",spec=spec,lines=v514.describe(spec,display),
                      prob=prob,mask=mask,oracle=oracle,target_hand=spec.get("target"))
    stats["V514"]={"tested":tested,"seconds":round(time.monotonic()-t0,3)}

    # First try to humanize the exact oracle with a certified V6.1 recognizer.
    human_oracle_matched=any(Fraction(r["fraction"])==oracle for r in rows)
    if not human_oracle_matched:
        h=v61.recognize(eng,inspect,north,south,target)
        if h and h.get("certified") and Fraction(h["probability_fraction"])==oracle:
            add_candidate(
                rows,
                source="V61",
                label=h["kind"],
                spec={"certification":h["certification"],"failure_fraction":h["failure_fraction"]},
                lines=h["lines_fr"],
                prob=oracle,
                mask=int(h["success_mask"]),
                oracle=oracle,
                target_hand=h.get("target_hand"),
            )
            rows[-1]["certified_humanization"]=h
            human_oracle_matched=True

    # V6.2 fallback: compact multi-round adaptive program. This is attempted
    # only after the cheaper named maneuver families and V6.1 recognizer fail.
    if not human_oracle_matched:
        h2=v62.find_candidate(eng,north,south,target,display,oracle)
        if h2.get("found") and h2.get("certified") and Fraction(h2["probability_fraction"])==oracle:
            add_candidate(
                rows,
                source="V62",
                label=h2["kind"],
                spec={
                    "source_family":h2["source_family"],
                    "prefix_rounds":h2["prefix_rounds"],
                    "program":h2["spec"],
                    "certification":h2["certification"],
                },
                lines=h2["lines_fr"],
                prob=oracle,
                mask=int(h2["success_mask"]),
                oracle=oracle,
                target_hand=h2["spec"].get("target"),
            )
            rows[-1]["certified_adaptive_humanization"]=h2
            human_oracle_matched=True

    # V6.2 semantic fallback: compile the exact public policy into executable
    # bridge-semantic actions and certify the resulting program by exhaustive replay.
    if not human_oracle_matched:
        hs=sem62.certified_humanize(eng,north,south,target,display,oracle)
        if hs.get("found") and hs.get("certified") and Fraction(hs["probability_fraction"])==oracle:
            add_candidate(
                rows,
                source="V62S",
                label=hs["kind"],
                spec={
                    "program":hs["program"],
                    "repairs":hs.get("repairs") or [],
                    "certification":hs["certification"],
                    "human_compact":hs["human_compact"],
                    "visible_lines":hs["visible_lines"],
                },
                lines=hs["lines_fr"],
                prob=oracle,
                mask=int(hs["success_mask"]),
                oracle=oracle,
                target_hand=None,
            )
            rows[-1]["certified_semantic_humanization"]=hs
            rows[-1]["human_compact"]=bool(hs["human_compact"])
            human_oracle_matched=True

    # Only if V6.2 semantic compilation still cannot explain the optimum,
    # retain the exact public oracle policy as a technical candidate.
    if not human_oracle_matched:
        e_oracle=eng.Engine2(north,south,target)
        solved=e_oracle.solve(include_policy=True)
        root=e_oracle.initial()
        frontier=e_oracle.frontier(root)
        best_mask=max(frontier,key=lambda m:(e_oracle.model.weight(m),m))
        root_key=repr(e_oracle.public_key(root))
        lead=(solved.get("policy") or {}).get(root_key) or "—"
        add_candidate(
            rows,
            source="ORACLE",
            label="POLITIQUE_ADAPTATIVE_EXACTE_A_HUMANISER",
            spec={"lead":lead,"policy_states":solved.get("policy_states",0)},
            lines=[
                "Stratégie adaptative exacte calculée par l’oracle.",
                "Elle atteint l’optimum mais son motif bridge compact n’est pas encore reconnu."
            ],
            prob=oracle,
            mask=best_mask,
            oracle=oracle,
            target_hand=None,
        )

    # Deduplicate by exact success mask. Same mask = same set of layouts covered.
    bymask={}
    for r in rows:
        m=r["mask"]
        if m not in bymask:
            bymask[m]=r; r["equivalent_variants"]=[]
        else:
            cur=bymask[m]
            if tuple(r["complexity"]) < tuple(cur["complexity"]):
                r["equivalent_variants"]=cur.get("equivalent_variants",[])+[{
                    "source":cur["source"],"label":cur["label"],"spec":cur["spec"]
                }]
                bymask[m]=r
            else:
                cur.setdefault("equivalent_variants",[]).append({
                    "source":r["source"],"label":r["label"],"spec":r["spec"]
                })

    unique=list(bymask.values())
    unique.sort(key=lambda r:(-Fraction(r["fraction"]),tuple(r["complexity"]),r["label"]))

    # Conservative exact layout explanation from the existing certified reasoner.
    e=eng.Engine2(north,south,target)
    for r in unique[:30]:
        if r.get("certified_semantic_humanization"):
            h=r["certified_semantic_humanization"]
            r["layout_reason"]={
                "certified":True,
                "mode":"CERTIFIED_V62_SEMANTIC_PROGRAM",
                "reason":"Programme adaptatif sémantique certifié par replay exhaustif contre toutes les défenses.",
                "visible_lines":h["visible_lines"],
                "human_compact":h["human_compact"],
            }
            continue
        if r.get("certified_adaptive_humanization"):
            h=r["certified_adaptive_humanization"]
            r["layout_reason"]={
                "certified":True,
                "mode":"CERTIFIED_V62_ADAPTIVE_PROGRAM",
                "reason":"Programme adaptatif multi-tours certifié par préfixe exact et continuation publique exacte.",
                "visible_lines":h["certification"]["visible_lines"],
            }
            continue
        if r.get("certified_humanization"):
            h=r["certified_humanization"]
            rr=v61.explain_qj_mask(eng,north,south,target,int(r["mask"]),r.get("target_hand"))
            r["layout_reason"]=rr or {
                "certified":True,
                "reason":h["success_condition_fr"],
                "mode":"CERTIFIED_V61",
                "failure_fraction":h["failure_fraction"],
                "failure_percent":h["failure_percent"],
            }
            continue
        rr=v61.explain_qj_mask(eng,north,south,target,int(r["mask"]),r.get("target_hand"))
        if rr:
            r["layout_reason"]=rr
            continue
        try:
            rr=v581.reason_for_mask(eng,e,int(r["mask"]),r.get("target_hand"))
            r["layout_reason"]=rr
        except Exception as exc:
            r["layout_reason"]={"certified":False,"reason":"","error":f"{type(exc).__name__}: {exc}"}

    return unique,stats


def compare(runtime_root: Path, tools_root: Path, north: str, south: str):
    north=normalize(north);south=normalize(south)
    dup=set(north)&set(south)
    if dup: raise ValueError("même carte dans les deux mains: "+"".join(sorted(dup,key=lambda c:RVAL[c],reverse=True)))
    mods=load_modules(runtime_root,tools_root)
    eng=mods[0]
    curve=[]
    max_target=max(len(north),len(south))
    for t in range(1,max_target+1):
        p=Fraction(eng.Engine2(north,south,t).solve(include_policy=False)["probability_fraction"])
        curve.append({"target":t,"fraction":str(p),"percent":frac_pct(p)})
    guaranteed=max([x["target"] for x in curve if Fraction(x["fraction"])==1],default=0)
    possible=max([x["target"] for x in curve if Fraction(x["fraction"])>0],default=0)

    objectives=[]
    for t in range(possible,guaranteed,-1):
        oracle=Fraction(next(x["fraction"] for x in curve if x["target"]==t))
        t0=time.monotonic()
        candidates,stats=collect_candidates(mods,north,south,t,oracle)
        optimal=[r for r in candidates if r["optimal"]]
        human_optimal=[r for r in optimal if r["source"]!="ORACLE"]
        objectives.append({
            "target":t,
            "oracle_fraction":str(oracle),
            "oracle_percent":frac_pct(oracle),
            "candidate_count":len(candidates),
            "optimal_candidate_count":len(optimal),
            "oracle_matched":bool(optimal),
            "human_oracle_matched":bool(human_optimal),
            "needs_humanization":not bool(human_optimal),
            "families":stats,
            "candidates":candidates,
            "elapsed_seconds":round(time.monotonic()-t0,3),
        })

    return {
        "schema":"MANIEMENTS_V6_COMPARATOR_V60",
        "runtime_frozen_sha256":RUNTIME_SHA,
        "north":north,"south":south,
        "north_fr":frhand(north),"south_fr":frhand(south),
        "curve":curve,
        "guaranteed_target":guaranteed,
        "possible_target":possible,
        "objectives":objectives,
        "rule":"all candidate maneuver probabilities are retained; optimal iff exact candidate fraction equals oracle fraction",
    }


def render_html(report):
    def pct(x): return f"{x:.4f}".replace(".",",")+" %"
    out=["<!doctype html><meta charset='utf-8'><title>MANIEMENTS V6.0</title>",
         "<style>body{font-family:system-ui;max-width:980px;margin:30px auto;padding:0 18px;background:#0b0f14;color:#eef4fa}section,article{background:#151b23;border:1px solid #2b3542;border-radius:14px;padding:16px;margin:14px 0}.best{border-color:#3f8b63}.muted{color:#9aa7b5}.p{float:right;color:#77e3aa;font-weight:800}ol{padding-left:22px}code{color:#fff}details{margin-top:9px}</style>",
         f"<h1>Comparateur de maniements V6.0</h1><p><b>{html.escape(report['north_fr'])}</b> face à <b>{html.escape(report['south_fr'])}</b></p>"]
    for o in report["objectives"]:
        out.append(f"<section><h2>Objectif : {o['target']} levées <span class='p'>{pct(o['oracle_percent'])}</span></h2>")
        out.append(f"<p class='muted'>Optimum oracle · {o['candidate_count']} comportements distincts · calcul exact couvert : <b>{'oui' if o['oracle_matched'] else 'NON'}</b> · motif humain optimal reconnu : <b>{'oui' if o.get('human_oracle_matched') else 'non, à humaniser'}</b></p>")
        for i,c in enumerate(o["candidates"][:8]):
            cls="best" if c["optimal"] else ""
            out.append(f"<article class='{cls}'><h3>{html.escape(c['label'])} <span class='p'>{pct(c['percent'])}</span></h3>")
            if c["optimal"]: out.append("<p><b>Optimal pour cet objectif</b></p>")
            elif c["gap_points"]>0: out.append(f"<p class='muted'>Écart : −{pct(c['gap_points'])} points</p>")
            if c.get("lines_provisional"):
                out.append("<ol>"+"".join("<li>"+html.escape(x)+"</li>" for x in c["lines_provisional"])+"</ol>")
            rr=c.get("layout_reason") or {}
            if rr.get("certified") and rr.get("reason"):
                out.append("<p><b>Cas exacts :</b> "+html.escape(rr["reason"])+"</p>")
                if rr.get("cases"):
                    out.append("<ul>"+ "".join(
                        "<li>"+html.escape(x["name"])+" : <b>"+pct(x["percent"])+"</b></li>"
                        for x in rr["cases"]
                    ) +"</ul>")
            else:
                out.append("<p class='muted'>Description compacte exacte des cas gagnants : pas encore disponible.</p>")
            out.append("<details><summary>Diagnostic</summary><pre>"+html.escape(json.dumps({"source":c["source"],"spec":c["spec"],"fraction":c["fraction"],"mask":c["mask"]},ensure_ascii=False,indent=2))+"</pre></details></article>")
        out.append("</section>")
    if report["guaranteed_target"]:
        out.append(f"<section><b>{report['guaranteed_target']} levée{'s' if report['guaranteed_target']>1 else ''} sont assurées.</b> Les objectifs inférieurs ne sont pas détaillés.</section>")
    return "\n".join(out)


def main():
    ap=argparse.ArgumentParser()
    ap.add_argument("--runtime-root",required=True)
    ap.add_argument("--tools-root",required=True)
    ap.add_argument("--north",required=True)
    ap.add_argument("--south",required=True)
    ap.add_argument("--output",required=True)
    ap.add_argument("--html")
    a=ap.parse_args()
    report=compare(Path(a.runtime_root),Path(a.tools_root),a.north,a.south)
    Path(a.output).write_text(json.dumps(report,ensure_ascii=False,indent=2)+"\n",encoding="utf-8")
    if a.html: Path(a.html).write_text(render_html(report),encoding="utf-8")
    summary={
        "hands":report["north_fr"]+"/"+report["south_fr"],
        "guaranteed":report["guaranteed_target"],
        "objectives":[{
            "target":o["target"],"oracle":o["oracle_fraction"],"candidates":o["candidate_count"],
            "oracle_matched":o["oracle_matched"],
            "human_oracle_matched":o["human_oracle_matched"],
            "top":[(x["label"],x["fraction"]) for x in o["candidates"][:5]]
        } for o in report["objectives"]]
    }
    print(json.dumps(summary,ensure_ascii=False,indent=2))


if __name__=="__main__":
    main()

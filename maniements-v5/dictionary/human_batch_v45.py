#!/usr/bin/env python3
from __future__ import annotations
import argparse, html, json, sys
from dataclasses import dataclass
from fractions import Fraction
from pathlib import Path

HERE=Path(__file__).resolve().parent
sys.path.insert(0,str(HERE))
import human_batch_v44 as b

CASES=[x for x in b.CASES if x['id']!='BH_2']+[
    {'id':'BS_2','north':'AKQT9','south':'2','display':['ARDX9','2'],'target':5},
]

@dataclass
class Node:
    kind:str
    state:object=None
    mask:int=0
    action:tuple|None=None
    branches:list|None=None
    terminal:str|None=None


def state_id(s):
    return (s.north,s.south,s.west_seen,s.east_seen,s.west_void,s.east_void,s.leader,s.pos,tuple(s.trick),s.won)


def action_success(eng,e,s,seat,r):
    if s.pos==0:
        lead=eng.PublicState(s.north,s.south,s.west_seen,s.east_seen,s.west_void,s.east_void,seat,0,tuple(),s.won)
        ns=e.close(e.decl_play(lead,seat,r))
    else:
        ns=e.close(e.decl_play(s,seat,r))
    fr=e.frontier(ns)
    best=max(fr,key=lambda m:(e.model.weight(m),m)) if fr else 0
    return ns,best


def feasible_actions(eng,e,s,need):
    acts=[]
    if s.pos==0:
        pools=tuple((seat,hand) for seat,hand in (('N',s.north),('S',s.south)) if hand)
    else:
        seat=e.order(s.leader)[s.pos]
        if seat not in eng.DECL:return []
        pools=((seat,s.north if seat=='N' else s.south),)
    for seat,hand in pools:
        ranks=eng.ranks(hand) if hand else ((eng.VOID,) if s.pos else tuple())
        for r in ranks:
            ns,support=action_success(eng,e,s,seat,r)
            if need==0 or (need|support)==support:
                acts.append((seat,r,ns,support))
    return acts


def previous_def_card(eng,e,s):
    if not s.trick:return None
    seat=e.order(s.leader)[s.pos]
    order=e.order(s.leader)
    ix=order.index(seat)
    if ix==0:return None
    prev=order[ix-1]
    if prev in eng.DECL:return None
    return next((r for q,r in s.trick if q==prev),None)


def choose_human_action(eng,e,s,need,cands):
    if not cands:raise RuntimeError('no feasible declarer action')
    bestw=max(e.model.weight(x[3]) for x in cands)
    top=[x for x in cands if e.model.weight(x[3])==bestw]
    if s.pos==0:
        spots=[x for x in top if eng.I2R[x[1]] not in 'AKQJ']
        pool=spots or top
        def key(x):
            seat,r,_,_=x
            hand=s.north if seat=='N' else s.south
            rank=eng.I2R[r]
            if pool is spots:
                return (hand.bit_count(), b.RANK_VALUE[rank], 0 if seat=='N' else 1)
            return (0,-b.RANK_VALUE[rank],0 if seat=='N' else 1)
        return min(pool,key=key)

    prev=previous_def_card(eng,e,s)
    rows=[(x,eng.I2R[x[1]] if x[1] else '-') for x in top]
    if prev:
        p='-' if not prev else eng.I2R[prev]
        if p!='-' and b.RANK_VALUE[p]>=10:
            beat=[z for z in rows if z[1]!='-' and b.RANK_VALUE[z[1]]>b.RANK_VALUE[p]]
            if beat:
                return min(beat,key=lambda z:b.RANK_VALUE[z[1]])[0]
            return min(rows,key=lambda z:b.RANK_VALUE.get(z[1],0))[0]
    strategic=[z for z in rows if z[1]!='-' and b.RANK_VALUE[z[1]]>=8]
    if strategic:
        return min(strategic,key=lambda z:b.RANK_VALUE[z[1]])[0]
    return min(rows,key=lambda z:b.RANK_VALUE.get(z[1],0))[0]


def explore(eng,e,s,need,decisions,rows,memo):
    term=e.terminal(s)
    if term is not None:
        return Node('T',state=s,mask=need,terminal='SUCCESS' if need else 'DEAD')
    k=(state_id(s),need)
    if k in memo:return memo[k]
    seat=e.order(s.leader)[s.pos]
    if s.pos==0 or seat in eng.DECL:
        cands=feasible_actions(eng,e,s,need)
        chosen=choose_human_action(eng,e,s,need,cands)
        cseat,r,ns,support=chosen
        action=(cseat,'-' if not r else eng.I2R[r])
        alts=[]
        for z in cands:
            if z[0]==cseat and z[1]==r:continue
            alts.append(z)
        alt=max(alts,key=lambda z:e.model.weight(z[3])) if alts else None
        if alt is not None:
            gain=support & ~alt[3]; loss=alt[3] & ~support
            lead_seat=cseat if s.pos==0 else s.leader
            decisions.append({
                'state':s,'need':need,'chosen':action,
                'alternative':(alt[0],'-' if not alt[1] else eng.I2R[alt[1]]),
                'chosen_support':support,'alt_support':alt[3],
                'gain':gain,'loss':loss,'gain_weight':e.model.weight(gain),'loss_weight':e.model.weight(loss),
                'gain_features':b.position_features(eng,e,gain,lead_seat),
                'loss_features':b.position_features(eng,e,loss,lead_seat),
            })
        rows.append((s,action))
        node=Node('D',state=s,mask=need,action=action)
        memo[k]=node
        node.branches=[explore(eng,e,ns,need,decisions,rows,memo)]
        return node

    branches=[]
    for r,legal in e.defender_actions(s,seat):
        branch_need=need & legal
        if not branch_need:
            continue
        ns=e.close(e.def_play(s,seat,r))
        child=explore(eng,e,ns,branch_need,decisions,rows,memo)
        branches.append(( '-' if not r else eng.I2R[r], child))
    node=Node('F',state=s,mask=need,branches=branches)
    memo[k]=node
    return node


def sig(n):
    if n.kind=='T':return ('T',n.terminal)
    if n.kind=='D':return ('D',n.action,sig(n.branches[0]))
    groups=[]
    for card,ch in n.branches or []:groups.append((card,sig(ch)))
    return ('F',tuple(groups))


def collapse(n):
    if n.kind=='T':return n
    if n.kind=='D':
        n.branches=[collapse(n.branches[0])]; return n
    bs=[(c,collapse(ch)) for c,ch in n.branches]
    grouped={}
    for c,ch in bs:grouped.setdefault(sig(ch),[ch,[]])[1].append(c)
    if len(grouped)==1:
        return next(iter(grouped.values()))[0]
    n.branches=[(tuple(v[1]),v[0]) for v in grouped.values()]
    return n


def card_condition(cards):
    cards=list(cards)
    if cards==['-']:return "si l’adversaire défausse"
    names=[b.fr_article(c) for c in cards]
    if len(names)==1:return f"si l’adversaire fournit {names[0]}"
    return "si l’adversaire fournit " + ", ".join(names[:-1]) + " ou " + names[-1]


def first_decl_action(n):
    if n.kind=='D':return n.action
    if n.kind=='T':return None
    vals=[]
    for _,ch in n.branches or []:
        a=first_decl_action(ch)
        if a:vals.append(a)
    return vals[0] if vals and len(set(vals))==1 else None


def action_phrase(n,first=False):
    seat,rank=n.action
    s=n.state
    if s.pos==0:
        nxt=first_decl_action(n.branches[0]) if n.branches else None
        if nxt and nxt[0]!=seat:
            if rank in '765432': return f"{'Commencer' if first else 'Jouer'} par petit vers {b.fr_article(nxt[1])}."
            if rank in '98T': return f"{'Commencer' if first else 'Jouer'} par {b.fr_article(rank)} vers {b.fr_article(nxt[1])}."
        if rank=='A':return "Tirer l’As."
        if rank=='K':return "Tirer le Roi."
        return f"Jouer {b.fr_article(rank)}."
    prev=previous_def_card_cached(s)
    if prev and prev!='-' and b.RANK_VALUE.get(rank,0)>b.RANK_VALUE.get(prev,99):
        return f"Couvrir avec {b.fr_article(rank)}."
    if rank in '765432':return "Fournir petit."
    return f"Passer {b.fr_article(rank)}."

_ENG=None; _E=None
def previous_def_card_cached(s):
    r=previous_def_card(_ENG,_E,s)
    return None if r is None else ('-' if not r else _ENG.I2R[r])


def render_tree(n,depth=0,first=True,max_depth=8):
    if depth>max_depth:return ["…"]
    if n.kind=='T':return []
    if n.kind=='D':
        lines=[action_phrase(n,first=first)]
        lines+=render_tree(n.branches[0],depth+1,False,max_depth)
        return lines
    out=[]
    for cards,ch in n.branches:
        sub=render_tree(ch,depth+1,False,max_depth)
        if not sub:continue
        out.append(card_condition(cards).capitalize()+" : "+sub[0])
        out.extend("  "+x for x in sub[1:])
    return out


def why_from_decisions(eng,e,decisions):
    useful=[d for d in decisions if d['gain_weight'] or d['loss_weight']]
    if not useful:
        return "Les choix visibles de cette ligne sont tous équivalents sur l’ensemble exact de réussite.",None
    useful.sort(key=lambda d:(d['gain_weight']-d['loss_weight'],d['gain_weight']),reverse=True)
    d=useful[0]
    gf=d['gain_features']; lf=d['loss_features']
    ch=d['chosen'][1]; al=d['alternative'][1]
    if gf:
        txt="Le choix de "+b.fr_article(ch)+" permet notamment de profiter de "+", ".join(gf)+"."
        if lf:txt+=" L’alternative avec "+b.fr_article(al)+" gagne plutôt "+", ".join(lf)+"."
        if d['gain_weight'] or d['loss_weight']:
            txt+=f" Différentiel exact : +{b.pct(d['gain_weight'])} / -{b.pct(d['loss_weight'])}."
        return txt,d
    return "La ligne exacte est certifiée, mais la différence avec l’alternative reste répartie sur trop de positions pour produire encore un « pourquoi » propre automatiquement.",d


def html_report(cases,path):
    cards=[]
    for r in cases:
        steps=''.join('<li>'+html.escape(x)+'</li>' for x in r['steps'])
        cards.append(f'''<article><header><div class="holding"><span>{html.escape(r['display'][0])}</span><span>{html.escape(r['display'][1])}</span></div><div><b>{r['target']} levées</b><div class="p">{r['percent']}</div><small>{r['fraction']}</small></div><strong>{r['status']}</strong></header><div class="grid"><section><h3>Arbre humain exact généré</h3><ol>{steps}</ol><h4>Pourquoi ?</h4><p>{html.escape(r['why'])}</p></section><section><h3>Référence revue</h3><p>{html.escape(r['ref_line'] or '—')}</p><h4>Pourquoi ?</h4><p>{html.escape(r['ref_why'] or '—')}</p></section></div><details><summary>Diagnostic</summary><pre>{html.escape(json.dumps(r['expert'],ensure_ascii=False,indent=2))}</pre></details></article>''')
    path.write_text(f'''<!doctype html><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1"><title>Human V4.5 exact tree</title><style>body{{background:#0b0f14;color:#eef4fa;font:15px/1.5 system-ui;margin:0}}main{{max-width:1160px;margin:28px auto;padding:0 16px 60px}}article{{background:#141b24;border:1px solid #2b3745;border-radius:16px;padding:18px;margin:14px 0}}header{{display:grid;grid-template-columns:150px 1fr auto;gap:16px;align-items:center}}.holding{{display:grid;justify-items:center;width:max-content;font:800 24px/1.05 ui-monospace,monospace}}.p{{font-size:23px;color:#70daa0;font-weight:800}}strong{{font-size:12px;color:#ffdc76}}.grid{{display:grid;grid-template-columns:1fr 1fr;gap:16px;margin-top:14px}}section{{background:#0f151d;padding:14px;border-radius:10px}}ol{{padding-left:22px}}h3{{margin-top:0}}h4{{margin-bottom:4px}}pre{{white-space:pre-wrap;color:#aec0d2}}@media(max-width:760px){{header,.grid{{grid-template-columns:1fr}}}}</style><main><h1>V4.5 — compression en arbre humain exact</h1><p>Chaque arbre de gauche est construit uniquement avec des actions qui préservent l’ensemble exact optimal, puis comparé à la référence revue.</p>{''.join(cards)}</main>''',encoding='utf-8')


def main():
    ap=argparse.ArgumentParser();ap.add_argument('--runtime-root',required=True);ap.add_argument('--reference',required=True);ap.add_argument('--x98-reference',required=True);ap.add_argument('--out-dir',required=True);a=ap.parse_args()
    sys.path.insert(0,str(Path(a.runtime_root)/'runtime'))
    import integrated_engine as eng
    global _ENG,_E;_ENG=eng
    refs=json.loads(Path(a.reference).read_text(encoding='utf-8'));ref_by={x['id']:x for x in refs['cases']}
    x98=json.loads(Path(a.x98_reference).read_text(encoding='utf-8'))
    outs=[]
    for c in CASES:
        e=eng.Engine2(c['north'],c['south'],c['target']);_E=e
        solved=e.solve(include_policy=False);opt=Fraction(solved['probability_fraction'])
        root=e.initial();fr=e.frontier(root);best=max(fr,key=lambda m:(e.model.weight(m),m));assert e.model.weight(best)==opt
        decisions=[];rows=[];tree=explore(eng,e,root,best,decisions,rows,{})
        ct=collapse(tree);steps=render_tree(ct)
        why,top=why_from_decisions(eng,e,decisions)
        ref=ref_by.get(c['id'])
        if c['id']=='X98_ARD7':rl=x98['human_line_fr'];rw=x98['why_fr']
        else:rl=ref.get('maniement_fr') if ref else None;rw=ref.get('why_fr') if ref else None
        outs.append({'id':c['id'],'display':c['display'],'target':c['target'],'fraction':str(opt),'percent':b.pct(opt),'status':'HUMAN_TREE_EXACT_CANDIDATE','steps':steps,'why':why,'ref_line':rl,'ref_why':rw,'expert':{'decision_count':len(decisions),'row_count':len(rows),'top_why':None if top is None else {'chosen':top['chosen'],'alternative':top['alternative'],'gain':str(top['gain_weight']),'loss':str(top['loss_weight']),'gain_features':top['gain_features'],'loss_features':top['loss_features']}}})
    od=Path(a.out_dir);od.mkdir(parents=True,exist_ok=True)
    (od/'HUMAN_V45_BATCH.json').write_text(json.dumps({'schema':'MANIEMENTS_V5_HUMAN_V45_EXACT_TREE_V1','cases':outs},ensure_ascii=False,indent=2)+'\n',encoding='utf-8')
    html_report(outs,od/'MANIEMENTS_V5_HUMAN_V45_EXACT_TREE_REVIEW.html')
    print(json.dumps({'cases':len(outs)},ensure_ascii=False))
if __name__=='__main__':main()

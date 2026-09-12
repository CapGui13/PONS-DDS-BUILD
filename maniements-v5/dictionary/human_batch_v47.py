#!/usr/bin/env python3
from __future__ import annotations

import argparse, html, json, sys
from collections import deque, defaultdict
from fractions import Fraction
from pathlib import Path

HERE=Path(__file__).resolve().parent
sys.path.insert(0,str(HERE))
import human_batch_v44 as b
import human_batch_v46_runner as v46  # patches v45 with exact-preserving semantic choices
v45=v46.v45

REFERENCE_OVERRIDES={
    'BS_C':{
        'why_fr':"Le deuxième passage vers D-10 gagne notamment lorsque A-V sont seconds dans la main placée devant D-10. Commencer par le Roi ne permet pas de profiter de cette position de cartes."
    },
    'BS_D':{
        'why_fr':"Cet ordre permet de faire 4 levées dans le cas du Valet sec mal placé. Commencer par l’impasse au Valet avec le 10 perd cette possibilité."
    },
    'SUITPLAY_ENC':{
        'why_fr':"Si le 9 est pris, tirer ensuite l’As vise à écraser l’autre honneur adverse lorsqu’il est devenu sec ou second. Si un honneur est joué en deuxième avant le 9, conserver le 9 puis le jouer en forçante garde ensuite la possibilité de jouer petit vers le 10."
    },
}


def pct(f):
    return f"{float(f)*100:.2f}".replace('.',',')+' %'


def sem_card(c):
    if isinstance(c,(tuple,list)):
        return tuple(sem_card(x) for x in c)
    if c in ('A','K','Q','J','T','9','8','-'):
        return c
    return 'x'


def flatten(x):
    if isinstance(x,(tuple,list)):
        out=[]
        for z in x:out.extend(flatten(z))
        return out
    return [x]


def fr_card(c):
    if c=='x':return 'une petite carte'
    if c=='-':return 'une chicane'
    return b.fr_article(c)


def first_decl_actions(n,depth=0,max_depth=4):
    if depth>max_depth or n.kind=='T':return set()
    if n.kind=='D':
        seat,rank=n.action
        return {(seat,sem_card(rank))}
    out=set()
    for _,ch in n.branches or []:
        out |= first_decl_actions(ch,depth+1,max_depth)
    return out


def branch_groups(n):
    groups=defaultdict(list)
    for cards,ch in n.branches or []:
        acts=first_decl_actions(ch)
        if len(acts)!=1:
            continue
        act=next(iter(acts))
        for c in flatten(cards):
            sc=sem_card(c)
            if sc not in groups[act]:groups[act].append(sc)
    return groups


def action_fr(action,cards):
    _,rank=action
    cards=[c for c in cards if c not in ('x','-')]
    if rank=='x':return 'jouer petit'
    if rank=='-':return 'ne plus fournir dans la couleur'
    # If the defender has just played a lower honour, say cover rather than merely play.
    if cards:
        vals=[b.RANK_VALUE.get(c,0) for c in cards]
        if vals and all(b.RANK_VALUE.get(rank,0)>v for v in vals):
            return 'couvrir avec '+b.fr_article(rank)
    if rank=='A':return 'jouer l’As'
    if rank=='K':return 'jouer le Roi'
    if rank=='Q':return 'jouer la Dame'
    if rank=='J':return 'jouer le Valet'
    return 'jouer '+b.fr_article(rank)


def condition_fr(cards):
    cats=[]
    for c in cards:
        sc=sem_card(c)
        if sc not in cats:cats.append(sc)
    if cats==['-']:return "si l’adversaire défausse"
    names=[fr_card(c) for c in cats]
    if len(names)==1:return "si l’adversaire fournit "+names[0]
    return "si l’adversaire fournit "+', '.join(names[:-1])+' ou '+names[-1]


def node_depth(initial,n):
    s=n.state
    start=initial.north.bit_count()+initial.south.bit_count()
    now=s.north.bit_count()+s.south.bit_count()
    return max(0,start-now)


def critical_nodes(root,initial,limit=3):
    q=deque([root]); seen=set(); out=[]; defender_nodes=0
    while q:
        n=q.popleft()
        if id(n) in seen:continue
        seen.add(id(n))
        if n.kind=='D':
            q.extend(n.branches or [])
            continue
        if n.kind=='F':
            defender_nodes+=1
            groups=branch_groups(n)
            if len(groups)>=2:
                rules=[]
                for act,cards in groups.items():
                    rules.append(condition_fr(cards)+' → '+action_fr(act,cards))
                score=sum(2 if any(c in ('A','K','Q','J','T','-') for c in cards) else 1 for cards in groups.values())
                out.append({'depth':node_depth(initial,n),'score':score,'rules':rules})
            for _,ch in n.branches or []:q.append(ch)
    out.sort(key=lambda x:(x['depth'],-x['score'],len(x['rules'])))
    return out[:limit],defender_nodes


def choose_root(eng,e,best_mask):
    root=e.initial()
    cands=v46.feasible_actions(eng,e,root,best_mask)
    chosen=v46.choose_human_action(eng,e,root,best_mask,cands)
    seat,r,ns,support=chosen
    row={'seat':seat,'rank':eng.I2R[r],'mask':support,'prob':e.model.weight(support),'state':ns}
    branches=b.first_defender_map(eng,e,row)
    phrase,_=b.root_phrase(row,branches)
    return row,phrase


def corrected_ref(ref):
    if not ref:return None
    z=dict(ref)
    z.update(REFERENCE_OVERRIDES.get(ref['id'],{}))
    return z


def html_report(rows,path):
    cards=[]
    for r in rows:
        crit=''.join('<li>'+html.escape(x)+'</li>' for x in r['critical']) or '<li>Aucune branche critique précoce à afficher.</li>'
        cards.append(f'''<article><header><div class="holding"><span>{html.escape(r['display'][0])}</span><span>{html.escape(r['display'][1])}</span></div><div><b>{r['target']} levée{'s' if r['target']>1 else ''}</b><div class="p">{r['percent']}</div><small>{html.escape(r['fraction'])}</small></div><strong>{html.escape(r['status'])}</strong></header><section class="main"><h3>Maniement</h3><p class="line">{html.escape(r['line'])}</p><h3>Pourquoi ?</h3><p>{html.escape(r['why'])}</p></section><details><summary>Contrôle automatique exact — décisions critiques seulement</summary><div class="diag"><p><b>Départ exact retenu :</b> {html.escape(r['auto_opening'])}</p><ul>{crit}</ul><p class="muted">{r['hidden']} nœuds de défense parcourus ; seuls {len(r['critical'])} points de décision distinctifs sont affichés. L’arbre exact complet reste masqué.</p></div></details></article>''')
    path.write_text(f'''<!doctype html><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1"><title>MANIEMENTS V5 — V4.7</title><style>body{{margin:0;background:#0b1016;color:#eef3f8;font:15px/1.5 system-ui}}main{{max-width:980px;margin:28px auto;padding:0 16px 60px}}h1{{margin-bottom:4px}}.intro{{color:#aebcca;margin-top:0}}article{{background:#141c25;border:1px solid #2c3947;border-radius:16px;padding:18px;margin:16px 0}}header{{display:grid;grid-template-columns:160px 1fr auto;gap:18px;align-items:center}}.holding{{display:grid;justify-items:center;width:max-content;min-width:120px;font:800 26px/1.08 ui-monospace,monospace}}.p{{font-size:24px;color:#71daa0;font-weight:800}}strong{{font-size:12px;color:#ffdb78}}.main{{background:#0f161e;border-radius:11px;padding:14px 16px;margin-top:14px}}.main h3{{margin:6px 0 3px}}.line{{font-weight:650;font-size:16px}}details{{margin-top:12px}}summary{{cursor:pointer;color:#b7cbe0}}.diag{{padding:8px 4px}}.muted{{color:#95a6b7;font-size:13px}}@media(max-width:700px){{header{{grid-template-columns:1fr}}}}</style><main><h1>V4.7 — fiche humaine + contrôle exact compact</h1><p class="intro">La fiche normale ne montre plus le parcours exact. Le contrôle automatique conserve seulement le départ optimal et les premiers embranchements où l’observation de la défense change réellement l’action.</p>{''.join(cards)}</main>''',encoding='utf-8')


def main():
    ap=argparse.ArgumentParser();ap.add_argument('--runtime-root',required=True);ap.add_argument('--reference',required=True);ap.add_argument('--x98-reference',required=True);ap.add_argument('--out-dir',required=True);a=ap.parse_args()
    sys.path.insert(0,str(Path(a.runtime_root)/'runtime'))
    import integrated_engine as eng
    refs=json.loads(Path(a.reference).read_text(encoding='utf-8')); ref_by={x['id']:corrected_ref(x) for x in refs['cases']}
    x98=json.loads(Path(a.x98_reference).read_text(encoding='utf-8'))
    out=[]
    for c in v45.CASES:
        e=eng.Engine2(c['north'],c['south'],c['target']); v45._ENG=eng; v45._E=e
        solved=e.solve(include_policy=False); opt=Fraction(solved['probability_fraction'])
        root=e.initial(); fr=e.frontier(root); best=max(fr,key=lambda m:(e.model.weight(m),m)); assert e.model.weight(best)==opt
        row,opening=choose_root(eng,e,best)
        decisions=[]; raw=[]; tree=v45.explore(eng,e,root,best,decisions,raw,{})
        tree=v46.collapse(tree)
        crit,total_def=critical_nodes(tree,root,limit=3)
        crit_lines=[]
        for i,z in enumerate(crit,1):
            prefix=f"Décision {i}"
            if z['depth']:
                prefix+=f" après {z['depth']} carte{'s' if z['depth']>1 else ''} jouée{'s' if z['depth']>1 else ''}"
            crit_lines.append(prefix+' : '+' ; '.join(z['rules'])+'.')
        if c['id']=='X98_ARD7':
            line=x98['human_line_fr']; why=x98['why_fr']; status='HUMAN_TREE_EXACT'
        else:
            ref=ref_by.get(c['id'])
            line=(ref or {}).get('maniement_fr') or opening
            why=(ref or {}).get('why_fr') or 'Calcul exact disponible — explication en cours de certification.'
            status='REFERENCE_VERIFIED' if ref else 'RAW_EXACT_ONLY'
        out.append({'id':c['id'],'display':c['display'],'target':c['target'],'fraction':str(opt),'percent':pct(opt),'line':line,'why':why,'status':status,'auto_opening':opening,'critical':crit_lines,'hidden':total_def})
    od=Path(a.out_dir);od.mkdir(parents=True,exist_ok=True)
    (od/'HUMAN_V47_CRITICAL.json').write_text(json.dumps({'schema':'MANIEMENTS_V5_HUMAN_V47_CRITICAL_V1','cases':out},ensure_ascii=False,indent=2)+'\n',encoding='utf-8')
    html_report(out,od/'MANIEMENTS_V5_HUMAN_V47_CRITICAL_REVIEW.html')
    print(json.dumps({'cases':len(out),'status':'OK'},ensure_ascii=False))

if __name__=='__main__':main()

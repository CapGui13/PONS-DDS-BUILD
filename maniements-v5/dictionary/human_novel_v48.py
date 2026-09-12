#!/usr/bin/env python3
from __future__ import annotations

import argparse, html, json, sys
from fractions import Fraction
from pathlib import Path

HERE=Path(__file__).resolve().parent
sys.path.insert(0,str(HERE))
import human_batch_v471_runner as v471

v47=v471.v47
v46=v471.v46
v45=v46.v45
b=v47.b

POOL=[
 ('N01','AJT4','832',3),('N02','AQ94','732',3),('N03','KJT4','A82',3),('N04','KQ94','J82',3),
 ('N05','A984','K32',3),('N06','QJ94','A82',3),('N07','AT84','Q32',3),('N08','K984','J32',3),
 ('N09','AJ84','Q32',3),('N10','AQ84','J32',3),('N11','KQ84','A32',3),('N12','AQT84','632',4),
 ('N13','AJ984','Q32',4),('N14','KJT84','A32',4),('N15','KQ984','J32',4),('N16','AQJ84','632',4),
 ('N17','AK984','Q32',4),('N18','AQT9','543',3),('N19','KJT9','A43',3),('N20','AQJ9','543',3),
 ('N21','A9854','K32',4),('N22','K9854','A32',4),('N23','QJ854','A32',4),('N24','AJ854','K32',4),
 ('N25','AQ854','T32',4),('N26','KQ854','J32',4),('N27','AKT84','632',4),('N28','AJT84','632',4),
 ('N29','KQT84','A32',4),('N30','AQ984','T32',4),('N31','KJ984','A32',4),('N32','QJT84','A32',4),
]

TR={'K':'R','Q':'D','J':'V','T':'X'}
def disp(h): return ''.join(TR.get(c,c) for c in h)
def pct(f): return f"{float(f)*100:.2f}".replace('.',',')+' %'

def known_set(path):
    refs=json.loads(Path(path).read_text(encoding='utf-8'))
    out=set()
    for r in refs['cases']:
        a=(r['north_fr'],r['south_fr'],int(r['target']))
        out.add(a); out.add((a[1],a[0],a[2]))
    return out

def alt_root(eng,e,root,row):
    alts=[]
    for x in b.root_action_masks(eng,e,root):
        if x['seat']==row['seat'] and x['rank']==row['rank']: continue
        if x['mask']==row['mask']: continue
        alts.append(x)
    return max(alts,key=lambda x:(x['prob'],x['mask'])) if alts else None

def why_auto(eng,e,row,alt):
    if alt is None:
        return "Plusieurs départs atteignent exactement la même probabilité. Le départ affiché est retenu pour sa lisibilité, pas parce qu’il serait mathématiquement supérieur.", {'gain':'0','loss':'0'}
    gain=row['mask'] & ~alt['mask']; loss=alt['mask'] & ~row['mask']
    gp=e.model.weight(gain); lp=e.model.weight(loss)
    gf=b.position_features(eng,e,gain,row['seat']); lf=b.position_features(eng,e,loss,row['seat'])
    if gf:
        txt='Ce départ permet notamment de profiter de '+', '.join(gf)+'.'
        if lf:
            txt+=' L’autre départ gagne en échange '+', '.join(lf)+'.'
        if gp or lp:
            txt+=f" Différentiel exact : +{pct(gp)} / -{pct(lp)}."
    else:
        txt=f"Ce départ gagne {pct(gp)} de positions que la meilleure alternative perd"
        if lp: txt+=f", tandis que l’alternative gagne {pct(lp)} d’autres positions"
        txt+='. Les positions différentielles sont trop variées pour être résumées proprement par une seule formule ; cette explication reste donc à relire.'
    return txt,{'gain':str(gp),'loss':str(lp),'gain_features':gf,'loss_features':lf,'alternative':[alt['seat'],alt['rank']]}

def critical_lines(crit):
    out=[]
    for z in crit[:2]:
        label='Après observation de la défense'
        if z['depth']:
            label+=f" (après {z['depth']} carte{'s' if z['depth']>1 else ''} jouée{'s' if z['depth']>1 else ''})"
        out.append(label+' : '+' ; '.join(z['rules'])+'.')
    return out

def complexity_score(e,row,alt,crit,decisions,total_def):
    diff=Fraction(0)
    if alt is not None: diff=e.model.weight(row['mask'] ^ alt['mask'])
    p=float(e.model.weight(row['mask']))
    middle=1.0-abs(p-0.65)
    return 18*len(crit)+0.18*min(len(decisions),80)+8*float(diff)+2*middle+0.01*min(total_def,200)

def html_report(rows,path):
    cards=[]
    for r in rows:
        cond=''.join('<li>'+html.escape(x)+'</li>' for x in r['critical']) or '<li>Aucune adaptation précoce distincte détectée.</li>'
        cards.append(f'''<article><header><div class="holding"><span>{html.escape(r['display'][0])}</span><span>{html.escape(r['display'][1])}</span></div><div><b>{r['target']} levée{'s' if r['target']>1 else ''}</b><div class="p">{r['percent']}</div><small>{html.escape(r['fraction'])}</small></div><strong>NOUVEAU — AUTO, NON RELU</strong></header><section class="main"><h3>Maniement généré</h3><p class="line">{html.escape(r['opening'])}</p><ul>{cond}</ul><h3>Pourquoi ?</h3><p>{html.escape(r['why'])}</p></section><details><summary>Contrôle exact</summary><p>Score de complexité : {r['score']:.2f} — {r['decision_count']} décisions déclarant analysées — {r['def_nodes']} nœuds défense.</p><pre>{html.escape(json.dumps(r['diag'],ensure_ascii=False,indent=2))}</pre></details></article>''')
    path.write_text(f'''<!doctype html><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1"><title>MANIEMENTS V5 — 10 cas nouveaux V4.8</title><style>body{{margin:0;background:#0b1016;color:#eef3f8;font:15px/1.5 system-ui}}main{{max-width:980px;margin:28px auto;padding:0 16px 60px}}h1{{margin-bottom:4px}}.intro{{color:#aebcca;margin-top:0}}article{{background:#141c25;border:1px solid #2c3947;border-radius:16px;padding:18px;margin:16px 0}}header{{display:grid;grid-template-columns:160px 1fr auto;gap:18px;align-items:center}}.holding{{display:grid;justify-items:center;width:max-content;min-width:120px;font:800 26px/1.08 ui-monospace,monospace}}.p{{font-size:24px;color:#71daa0;font-weight:800}}strong{{font-size:11px;color:#ffdb78}}.main{{background:#0f161e;border-radius:11px;padding:14px 16px;margin-top:14px}}.main h3{{margin:6px 0 3px}}.line{{font-weight:700;font-size:16px}}details{{margin-top:12px}}summary{{cursor:pointer;color:#b7cbe0}}pre{{white-space:pre-wrap;color:#aebcca}}@media(max-width:700px){{header{{grid-template-columns:1fr}}}}</style><main><h1>V4.8 — 10 maniements réellement nouveaux</h1><p class="intro">Aucune réponse humaine de référence n’est fournie à ces 10 cas. Le système choisit les cas parmi un pool inédit, calcule l’optimum exact, produit le départ, les adaptations observables et le « pourquoi ». C’est précisément le test de généralisation à relire.</p>{''.join(cards)}</main>''',encoding='utf-8')

def main():
    ap=argparse.ArgumentParser(); ap.add_argument('--runtime-root',required=True); ap.add_argument('--reference',required=True); ap.add_argument('--out-dir',required=True); a=ap.parse_args()
    sys.path.insert(0,str(Path(a.runtime_root)/'runtime'))
    import integrated_engine as eng
    known=known_set(a.reference)
    results=[]
    for cid,north,south,target in POOL:
        display=[disp(north),disp(south)]
        if (display[0],display[1],target) in known: continue
        e=eng.Engine2(north,south,target); v45._ENG=eng; v45._E=e
        solved=e.solve(include_policy=False); opt=Fraction(solved['probability_fraction'])
        if opt<=0 or opt>=1: continue
        root=e.initial(); fr=e.frontier(root); best=max(fr,key=lambda m:(e.model.weight(m),m)); assert e.model.weight(best)==opt
        row,opening=v47.choose_root(eng,e,best)
        alt=alt_root(eng,e,root,row)
        decisions=[]; raw=[]; tree=v45.explore(eng,e,root,best,decisions,raw,{})
        tree=v46.collapse(tree)
        crit,total_def=v47.critical_nodes(tree,root,limit=3)
        why,diag=why_auto(eng,e,row,alt)
        score=complexity_score(e,row,alt,crit,decisions,total_def)
        results.append({'id':cid,'display':display,'target':target,'fraction':str(opt),'percent':pct(opt),'opening':opening,'critical':critical_lines(crit),'why':why,'score':score,'decision_count':len(decisions),'def_nodes':total_def,'diag':diag})
        print(json.dumps({'case':cid,'p':str(opt),'score':round(score,3),'crit':len(crit),'decisions':len(decisions)},ensure_ascii=False),flush=True)
    results.sort(key=lambda x:(-x['score'],x['id']))
    selected=results[:10]
    assert len(selected)==10
    # hard gate: selected cases must not already exist in canonical reviewed corpus
    for r in selected:
        assert (r['display'][0],r['display'][1],r['target']) not in known
        assert (r['display'][1],r['display'][0],r['target']) not in known
    od=Path(a.out_dir); od.mkdir(parents=True,exist_ok=True)
    payload={'schema':'MANIEMENTS_V5_HUMAN_V48_NOVEL_AUTO_V1','selection':'top 10 by exact branching/decision complexity from unseen pool','human_reference_answers_used':False,'cases':selected}
    (od/'HUMAN_V48_NOVEL_AUTO.json').write_text(json.dumps(payload,ensure_ascii=False,indent=2)+'\n',encoding='utf-8')
    html_report(selected,od/'MANIEMENTS_V5_HUMAN_V48_10_NOUVEAUX.html')
    print(json.dumps({'selected':[x['id'] for x in selected],'status':'OK'},ensure_ascii=False),flush=True)

if __name__=='__main__': main()

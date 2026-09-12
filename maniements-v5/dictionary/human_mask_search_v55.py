#!/usr/bin/env python3
from __future__ import annotations

import argparse, json, sys, time
from collections import Counter
from fractions import Fraction
from pathlib import Path

HERE=Path(__file__).resolve().parent
sys.path.insert(0,str(HERE))
import human_semantic_v52 as v52
import human_motif_v54 as v54


def mask_candidate(eng,e,mask,display):
    v52.v45._ENG=eng;v52.v45._E=e
    row,opening=v52.v47.choose_root(eng,e,mask)
    decisions=[];raw=[]
    tree=v52.v45.explore(eng,e,e.initial(),mask,decisions,raw,{})
    audit=v52.v50.audit_exact_tree(eng,e,tree,mask)
    if not audit.get('ok'):
        return {'valid':False,'reason':'exact_replay_failed','audit':audit}
    comp=v52.compress_policy(eng,e,tree,display[0],display[1])
    raw_lines=comp.get('lines') or []
    lines=v54.naturalize(raw_lines,display) if raw_lines else []
    generic=bool(comp.get('ok')) and not comp.get('spot_fallback_used',False)
    exact_compact=generic and v54.exact_quality(lines)
    ready=exact_compact and v54.bridge_ready(lines)
    score=(int(ready),int(exact_compact),int(generic),-v54.spot_count(lines),-v54.condition_count(lines),-len(lines),-max((len(x) for x in lines),default=0),-int(comp.get('normalized_states',10**9)))
    return {'valid':True,'mask':str(mask),'opening':opening,'row':row,'audit':audit,'semantic':{k:v for k,v in comp.items() if k!='lines'},'raw_lines':raw_lines,'lines':lines,'generic':generic,'exact_compact':exact_compact,'bridge_ready':ready,'score':list(score),'conditions':v54.condition_count(lines),'spot_conditions':v54.spot_count(lines)}


def analyze_profile(eng,c,p,max_masks):
    target=int(p['target']);e=eng.Engine2(c['north'],c['south'],target);root=e.initial();front=e.frontier(root)
    opt=max(e.model.weight(m) for m in front)
    masks=[m for m in front if e.model.weight(m)==opt]
    default=max(masks,key=lambda m:m)
    # Search every co-optimal success mask unless an explicit safety cap is reached.
    # When capped, keep the deterministic default plus masks spread over integer order.
    searched=masks
    capped=False
    if max_masks and len(masks)>max_masks:
        capped=True;ordered=sorted(masks);idxs={0,len(ordered)-1}
        if max_masks>2:
            for k in range(1,max_masks-1):idxs.add(round(k*(len(ordered)-1)/(max_masks-1)))
        searched=[ordered[i] for i in sorted(idxs)][:max_masks]
        if default not in searched:searched[-1]=default
    rows=[];started=time.monotonic()
    for m in searched:
        try:rows.append(mask_candidate(eng,e,m,c['display']))
        except Exception as ex:rows.append({'valid':False,'mask':str(m),'reason':'exception','error':repr(ex)})
    good=[r for r in rows if r.get('valid')]
    if not good:return {'target':target,'fraction':str(opt),'optimal_masks':len(masks),'searched_masks':len(searched),'capped':capped,'error':'no_valid_candidate','candidates':rows}
    best=max(good,key=lambda r:tuple(r['score']))
    base=next((r for r in good if int(r['mask'])==default),None)
    if base is None:
        base=mask_candidate(eng,e,default,c['display'])
    chosen=int(best['mask']);changed=chosen!=default
    why=p.get('qualification',{}).get('candidate_why') or p.get('why') or ''
    if changed:
        try:
            row=best['row'];alt=v52.v48.alt_root(eng,e,root,row);why=v52.v51.witness_reason(eng,e,row,alt) or why
        except Exception:pass
    why=v54.clean(why,c['display'])
    if best['bridge_ready']:
        why=v54.exact_reason(eng,c['north'],c['south'],target,why)
    return {'target':target,'fraction':str(opt),'optimal_masks':len(masks),'searched_masks':len(searched),'capped':capped,'default_mask':str(default),'chosen_mask':str(chosen),'mask_changed':changed,'baseline':{k:base.get(k) for k in ('generic','exact_compact','bridge_ready','lines','conditions','spot_conditions','score')},'chosen':{k:best.get(k) for k in ('generic','exact_compact','bridge_ready','opening','lines','conditions','spot_conditions','score','semantic')},'why':why,'elapsed_seconds':round(time.monotonic()-started,3)}


def main():
    ap=argparse.ArgumentParser();ap.add_argument('--input',required=True);ap.add_argument('--runtime-root',required=True);ap.add_argument('--out-dir',required=True);ap.add_argument('--max-masks',type=int,default=0);a=ap.parse_args()
    eng=v54.load_engine(a.runtime_root);src=json.load(open(a.input,encoding='utf-8'));results=[];counts=Counter();started=time.monotonic()
    for c in src['cases']:
        cr={'id':c['id'],'north':c['north'],'south':c['south'],'display':c['display'],'profiles':[]}
        for p in c['profiles']:
            if not p.get('qualification',{}).get('counted'):continue
            r=analyze_profile(eng,c,p,a.max_masks);cr['profiles'].append(r)
            b=r.get('baseline') or {};z=r.get('chosen') or {}
            counts['profiles']+=1;counts['multi_mask']+=int(r.get('optimal_masks',0)>1);counts['mask_changed']+=int(r.get('mask_changed',False));counts['baseline_generic']+=int(bool(b.get('generic')));counts['chosen_generic']+=int(bool(z.get('generic')));counts['baseline_exact_compact']+=int(bool(b.get('exact_compact')));counts['chosen_exact_compact']+=int(bool(z.get('exact_compact')));counts['baseline_bridge_ready']+=int(bool(b.get('bridge_ready')));counts['chosen_bridge_ready']+=int(bool(z.get('bridge_ready')));counts['capped']+=int(r.get('capped',False))
            print(json.dumps({'case':c['id'],'target':p['target'],'masks':r.get('optimal_masks'),'changed':r.get('mask_changed'),'base_generic':b.get('generic'),'chosen_generic':z.get('generic'),'base_ready':b.get('bridge_ready'),'chosen_ready':z.get('bridge_ready'),'sec':r.get('elapsed_seconds')},ensure_ascii=False),flush=True)
        results.append(cr)
    summary={'schema':'MANIEMENTS_V5_HUMAN_V55_MASK_SEARCH_V1',**dict(counts),'generic_gain':counts['chosen_generic']-counts['baseline_generic'],'exact_compact_gain':counts['chosen_exact_compact']-counts['baseline_exact_compact'],'bridge_ready_gain':counts['chosen_bridge_ready']-counts['baseline_bridge_ready'],'elapsed_seconds':round(time.monotonic()-started,3),'max_masks':a.max_masks or 'ALL','runtime_frozen_sha256':'a0b580531f3c9e8bb00710b9c3e1c183b27cbfe9231c9d584e29a374ba88835d'}
    od=Path(a.out_dir);od.mkdir(parents=True,exist_ok=True);(od/'HUMAN_V55_MASK_SEARCH.json').write_text(json.dumps({'summary':summary,'cases':results},ensure_ascii=False,indent=2)+'\n',encoding='utf-8');(od/'SUMMARY.txt').write_text('\n'.join(f'{k}={json.dumps(v,ensure_ascii=False) if isinstance(v,(dict,list)) else v}' for k,v in summary.items())+'\n',encoding='utf-8');print(json.dumps(summary,ensure_ascii=False),flush=True)

if __name__=='__main__':main()

#!/usr/bin/env python3
from __future__ import annotations

import argparse,json,re,sys,time
from collections import Counter,defaultdict
from fractions import Fraction
from pathlib import Path

HERE=Path(__file__).resolve().parent
sys.path.insert(0,str(HERE))
import human_batch_v44 as v44
import human_motif_v54 as v54
import human_semantic_v52 as v52
import human_prefix_exact_v511 as v511
import human_sequence_search_v512 as v512

m=v511.x591.m


def all_specs(north,south):
    out=[];seen=set()
    for source,s in v511.candidate_specs(north,south):
        k=repr(s)
        if k not in seen:seen.add(k);out.append((source,s))
    for s in v512.specs(north,south):
        k=repr(s)
        if k not in seen:seen.add(k);out.append(('V512',s))
    return out


def residual_states(eng,e,spec,prefix_rounds):
    out={};seen=set()
    def walk(s,rnd):
        key=(s,rnd)
        if key in seen:return
        seen.add(key)
        term=e.terminal(s)
        if term is not None:return
        if s.pos==0 and rnd>prefix_rounds:
            out[s]=1;return
        if s.pos==0:
            a=m.action(eng,e,s,spec)
            if a is None:return
            seat,c=a;r=eng.R2I[c]
            lead=eng.PublicState(s.north,s.south,s.west_seen,s.east_seen,s.west_void,s.east_void,seat,0,tuple(),s.won)
            walk(e.close(e.decl_play(lead,seat,r)),rnd);return
        seat=e.order(s.leader)[s.pos]
        if seat in eng.DECL:
            a=m.action(eng,e,s,spec)
            if a is None or a[0]!=seat:return
            c=a[1];r=eng.VOID if c=='-' else eng.R2I[c]
            ns=e.close(e.decl_play(s,seat,r));walk(ns,rnd+1 if ns.pos==0 else rnd);return
        for r,legal in e.defender_actions(s,seat):
            if not (e.belief(s)&legal):continue
            ns=e.close(e.def_play(s,seat,r));walk(ns,rnd+1 if ns.pos==0 else rnd)
    walk(e.initial(),1)
    return list(out)


def compress_forest(eng,e,states,top,bottom):
    rows=[];trees=0;decisions=0
    v52.v45._ENG=eng;v52.v45._E=e
    for s in states:
        fr=e.frontier(s)
        if not fr:continue
        best=max(fr,key=lambda z:(e.model.weight(z),z))
        ds=[];raw=[]
        tree=v52.v45.explore(eng,e,s,best,ds,raw,{})
        rows.extend(v52.collect_states(eng,e,tree));trees+=1;decisions+=len(ds)
    if not rows:
        return {'ok':True,'lines':[],'visible_lines':0,'spot_fallback_used':False,'human_safe':True,'trees':trees,'decisions':decisions}
    norm,refined,conflicts,irrelevant=v52.normalize_states(rows)
    if conflicts:return {'ok':False,'reason':'true_observable_conflict','conflicts':conflicts[:5],'trees':trees,'decisions':decisions}
    grouped=defaultdict(list)
    for r in norm:
        f=r['features'];key=(f['round'],f['phase'],f.get('leader'),f.get('seat'))
        grouped[key].append({'features':f,'label':v52.public_action(r['action'],f['phase']),'tier':r['tier']})
    lines=[];spot=False
    for key,ss in sorted(grouped.items(),key=lambda kv:str(kv[0])):
        c,sp=v52.compress_group(ss,top,bottom)
        if c is None:return {'ok':False,'reason':'rules_not_separable','group':key,'trees':trees,'decisions':decisions}
        spot|=sp or any(x['tier']=='spots' for x in ss)
        rnd,phase,leader,seat=key;prefix=f"Au {rnd}{'er' if rnd==1 else 'e'} tour après le motif"
        for rr in c['rules']:
            cond=' et '.join(v52.human_atom(k,v,top,bottom) for k,v in rr['if'])
            prev=next((v for k,v in rr['if'] if k=='prev_card'),None)
            lines.append(f"{prefix}, si {cond} : {v52.action_text(rr['label'],phase,top,bottom,prev)}.")
        if not (phase=='response' and c['default']=='-'):
            leadin='sinon : ' if c['rules'] else ''
            lines.append(f"{prefix}, {leadin}{v52.action_text(c['default'],phase,top,bottom)}.")
    ded=[]
    for x in lines:
        if x not in ded:ded.append(x)
    return {'ok':True,'lines':ded,'visible_lines':len(ded),'spot_fallback_used':spot,'human_safe':(not spot and len(ded)<=8),'normalized_states':len(norm),'irrelevant_pruned':irrelevant,'refined_states':refined,'trees':trees,'decisions':decisions}


def prefix_lines(spec,display,prefix):
    raw=m.lines(spec,display)
    # Lines generated from a motif are already bridge-oriented; limit the display
    # to the amount of strategy constrained before the exact residual begins.
    # Keep at least the lead/response instruction pair.
    n=min(len(raw),max(1,prefix+1))
    return raw[:n]


def clean_residual(lines):
    out=[]
    for x in lines:
        x=re.sub(r'^Au 1er tour après le motif,\s*','Ensuite, ',x)
        x=re.sub(r'^Au (\d+)e tour après le motif,\s*',r'Puis, au \1e tour suivant, ',x)
        out.append(x)
    return out


def analyze(eng,c,max_specs=0):
    e=eng.Engine2(c['north'],c['south'],c['target']);opt=Fraction(e.solve(include_policy=False)['probability_fraction']);rows=[];tested=0;t0=time.monotonic();specs=all_specs(c['north'],c['south'])
    if max_specs:specs=specs[:max_specs]
    for source,spec in specs:
        for pr in (1,2,3):
            try:p,_=v511.evaluate_prefix(eng,c['north'],c['south'],c['target'],spec,pr);tested+=1
            except Exception:continue
            if p!=opt:continue
            states=residual_states(eng,e,spec,pr);comp=compress_forest(eng,e,states,c['display'][0],c['display'][1]);res=clean_residual(comp.get('lines') or [])
            pref=prefix_lines(spec,c['display'],pr);total=pref+res
            # Exactness is guaranteed by: prefix equality to oracle optimum + exact
            # continuation tree chosen independently at every reachable residual state.
            score=(int(not comp.get('ok')),int(comp.get('spot_fallback_used',False)),len(total),len(res),comp.get('normalized_states',9999),pr)
            rows.append({'source':source,'prefix_rounds':pr,'prefix_lines':pref,'residual':comp,'residual_lines':res,'full_lines':total,'score':list(score),'spec':{k:(list(v) if isinstance(v,tuple) else v) for k,v in spec.items()},'residual_states':len(states)})
    rows.sort(key=lambda r:tuple(r['score']));best=rows[0] if rows else None
    ready=bool(best and best['residual'].get('ok') and not best['residual'].get('spot_fallback_used') and len(best['full_lines'])<=7)
    return {'id':c['id'],'display':c['display'],'north':c['north'],'south':c['south'],'target':c['target'],'fraction':str(opt),'found_prefix':bool(rows),'bridge_compact_exact':ready,'best':best,'candidates':len(rows),'tested':tested,'elapsed_seconds':round(time.monotonic()-t0,3)}


def main():
    ap=argparse.ArgumentParser();ap.add_argument('--runtime-root',required=True);ap.add_argument('--out-dir',required=True);ap.add_argument('--max-specs',type=int,default=0);a=ap.parse_args();eng=v54.load_engine(a.runtime_root);rows=[];cnt=Counter();t0=time.monotonic()
    for c in v44.CASES:
        r=analyze(eng,c,a.max_specs);rows.append(r);cnt['cases']+=1;cnt['prefix']+=int(r['found_prefix']);cnt['compact']+=int(r['bridge_compact_exact']);print(json.dumps({'case':c['id'],'prefix':r['found_prefix'],'compact':r['bridge_compact_exact'],'lines':len((r.get('best') or {}).get('full_lines') or []),'residual':len((r.get('best') or {}).get('residual_lines') or []),'sec':r['elapsed_seconds']},ensure_ascii=False),flush=True)
    summary={'schema':'MANIEMENTS_V5_HUMAN_V515_PREFIX_RESIDUAL_REVIEWED_V1',**dict(cnt),'prefix_rate_percent':f"{100*cnt['prefix']/cnt['cases']:.2f}",'compact_rate_percent':f"{100*cnt['compact']/cnt['cases']:.2f}",'elapsed_seconds':round(time.monotonic()-t0,3),'runtime_frozen_sha256':'a0b580531f3c9e8bb00710b9c3e1c183b27cbfe9231c9d584e29a374ba88835d','proof':'human prefix preserves exact optimum; every reachable residual state is completed by an exact public policy and compressed jointly'}
    od=Path(a.out_dir);od.mkdir(parents=True,exist_ok=True);(od/'HUMAN_V515_PREFIX_RESIDUAL_REVIEWED.json').write_text(json.dumps({'summary':summary,'cases':rows},ensure_ascii=False,indent=2)+'\n');(od/'SUMMARY.txt').write_text('\n'.join(f'{k}={v}' for k,v in summary.items())+'\n');print(json.dumps(summary,ensure_ascii=False),flush=True)
if __name__=='__main__':main()

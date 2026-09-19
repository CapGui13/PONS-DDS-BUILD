#!/usr/bin/env python3
from __future__ import annotations
import argparse,json,sys,time
from functools import lru_cache
from fractions import Fraction
from pathlib import Path
ap=argparse.ArgumentParser()
ap.add_argument('--runtime-root',required=True);ap.add_argument('--tools-root',required=True);ap.add_argument('--output',required=True)
a=ap.parse_args()
sys.path.insert(0,str(Path(a.runtime_root)/'runtime'));sys.path.insert(0,a.tools_root)
import integrated_engine as eng
import human_observed_drop_switch_v623 as obs
import human_prefix_exact_v511 as v511
import human_prefix_residual_v515 as v515

n,s,t='K62','AJ853',5
display=['R62','AV853']
e=eng.Engine2(n,s,t);oracle=Fraction(e.solve(include_policy=False)['probability_fraction'])

def eval_prefix(z,rounds=2):
    @lru_cache(maxsize=None)
    def F(st,rnd):
        term=e.terminal(st)
        if term is not None:return term[0]
        if rnd>rounds and st.pos==0:
            return v511.best_frontier(e,st)
        if st.pos==0:
            a=obs.action(eng,e,st,z)
            if a is None:return 0
            seat,c=a;r=eng.R2I[c]
            lead=eng.PublicState(st.north,st.south,st.west_seen,st.east_seen,st.west_void,st.east_void,seat,0,tuple(),st.won)
            return F(e.close(e.decl_play(lead,seat,r)),rnd)
        seat=e.order(st.leader)[st.pos]
        if seat in eng.DECL:
            a=obs.action(eng,e,st,z)
            if a is None or a[0]!=seat:return 0
            c=a[1];r=eng.VOID if c=='-' else eng.R2I[c]
            ns=e.close(e.decl_play(st,seat,r));return F(ns,rnd+1 if ns.pos==0 else rnd)
        belief=e.belief(st);ok=belief
        for r,legal in e.defender_actions(st,seat):
            ns=e.close(e.def_play(st,seat,r));nr=rnd+1 if ns.pos==0 else rnd
            ok &= ((belief&~legal)|F(ns,nr))
        return ok
    m=F(e.initial(),1);return e.model.weight(m),m

def residual_states(z,rounds=2):
    out={};seen=set()
    def walk(st,rnd):
        k=(st,rnd)
        if k in seen:return
        seen.add(k)
        if e.terminal(st) is not None:return
        if st.pos==0 and rnd>rounds:
            out[st]=1;return
        if st.pos==0:
            a=obs.action(eng,e,st,z)
            if a is None:return
            seat,c=a;r=eng.R2I[c]
            lead=eng.PublicState(st.north,st.south,st.west_seen,st.east_seen,st.west_void,st.east_void,seat,0,tuple(),st.won)
            walk(e.close(e.decl_play(lead,seat,r)),rnd);return
        seat=e.order(st.leader)[st.pos]
        if seat in eng.DECL:
            a=obs.action(eng,e,st,z)
            if a is None or a[0]!=seat:return
            c=a[1];r=eng.VOID if c=='-' else eng.R2I[c]
            ns=e.close(e.decl_play(st,seat,r));walk(ns,rnd+1 if ns.pos==0 else rnd);return
        for r,legal in e.defender_actions(st,seat):
            if not (e.belief(st)&legal):continue
            ns=e.close(e.def_play(st,seat,r));walk(ns,rnd+1 if ns.pos==0 else rnd)
    walk(e.initial(),1)
    return list(out)

rows=[];tested=0;t0=time.monotonic()
for z in obs.specs(n,s):
    p,m=eval_prefix(z,2);tested+=1
    if p!=oracle:continue
    states=residual_states(z,2)
    comp=v515.compress_forest(eng,e,states,display[0],display[1])
    prefix=obs.describe(z,display)[:4]
    residual=v515.clean_residual(comp.get('lines') or [])
    rows.append({
      'spec':{k:(list(v) if isinstance(v,tuple) else v) for k,v in z.items()},
      'fraction':str(p),'prefix_lines':prefix,'residual_lines':residual,
      'full_lines':prefix+residual,'residual_states':len(states),
      'residual_ok':comp.get('ok'),'spot_fallback':comp.get('spot_fallback_used'),
      'score':[int(not comp.get('ok')),int(comp.get('spot_fallback_used',False)),len(prefix)+len(residual),len(residual)]
    })
rows.sort(key=lambda r:tuple(r['score']))
out={'oracle':str(oracle),'tested':tested,'found_prefixes':len(rows),'best':rows[0] if rows else None,'elapsed':round(time.monotonic()-t0,3)}
Path(a.output).write_text(json.dumps(out,ensure_ascii=False,indent=2)+'\n',encoding='utf-8')
print(json.dumps(out,ensure_ascii=False,indent=2))

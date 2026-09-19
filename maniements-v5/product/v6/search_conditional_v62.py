#!/usr/bin/env python3
import argparse,json,sys,time
from fractions import Fraction
from pathlib import Path
ap=argparse.ArgumentParser()
ap.add_argument('--runtime-root',required=True)
ap.add_argument('--tools-root',required=True)
ap.add_argument('--output',required=True)
a=ap.parse_args()
sys.path.insert(0,str(Path(a.runtime_root)/'runtime'))
sys.path.insert(0,a.tools_root)
import integrated_engine as eng
import human_conditional_followup_v62 as v62
north,south,target='K62','AJ853',5
oracle=Fraction(eng.Engine2(north,south,target).solve(include_policy=False)['probability_fraction'])
rows=[]; t0=time.monotonic(); tested=0
for s in v62.specs(north,south):
    p,m=v62.evaluate(eng,north,south,target,s); tested+=1
    if p==oracle:
        rows.append({'spec':{k:(list(v) if isinstance(v,tuple) else v) for k,v in s.items()},
                     'fraction':str(p),'mask':str(m),'lines':v62.lines(s,['R62','AV853'])})
rows.sort(key=lambda r:(len(r['spec']['trigger']),r['spec']['cash'],r['spec']['if_seen'],r['spec']['if_not']))
out={'oracle':str(oracle),'tested':tested,'found':len(rows),'best':rows[0] if rows else None,
     'elapsed_seconds':round(time.monotonic()-t0,3)}
Path(a.output).write_text(json.dumps(out,ensure_ascii=False,indent=2)+'\n',encoding='utf-8')
print(json.dumps(out,ensure_ascii=False,indent=2))
if not rows: raise SystemExit(2)

#!/usr/bin/env python3
import argparse,json,sys
from fractions import Fraction
from pathlib import Path
ap=argparse.ArgumentParser()
ap.add_argument('--runtime-root',required=True);ap.add_argument('--tools-root',required=True);ap.add_argument('--output',required=True)
a=ap.parse_args()
sys.path.insert(0,str(Path(a.runtime_root)/'runtime'));sys.path.insert(0,a.tools_root)
import integrated_engine as eng
import human_observed_drop_switch_v623 as m
n,s,t='K62','AJ853',5
display=['R62','AV853']
e=eng.Engine2(n,s,t);oracle=Fraction(e.solve(include_policy=False)['probability_fraction'])
root=e.initial();best=max(e.frontier(root),key=lambda x:(e.model.weight(x),x))
rows=[];tested=0
for z in m.specs(n,s):
    p,mask=m.evaluate(eng,n,s,t,z);tested+=1
    if p==oracle:
        rows.append({'spec':{k:(list(v) if isinstance(v,tuple) else v) for k,v in z.items()},
                     'fraction':str(p),'mask':str(mask),'mask_matches_oracle':int(mask)==int(best),
                     'lines':m.describe(z,display)})
rows.sort(key=lambda r:(len(r['spec']['switch']),r['spec']['watch'],r['spec']['if_target'],r['spec']['else_target']))
out={'oracle':str(oracle),'tested':tested,'found':len(rows),'best':rows[0] if rows else None}
Path(a.output).write_text(json.dumps(out,ensure_ascii=False,indent=2)+'\n',encoding='utf-8')
print(json.dumps(out,ensure_ascii=False,indent=2))

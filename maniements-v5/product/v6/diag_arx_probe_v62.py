#!/usr/bin/env python3
import argparse,sys,json
from fractions import Fraction
from pathlib import Path
ap=argparse.ArgumentParser()
ap.add_argument('--runtime-root',required=True);ap.add_argument('--tools-root',required=True)
a=ap.parse_args()
sys.path.insert(0,'maniements-v5/product/v6')
import comparator_v60 as comp
mods=comp.load_modules(Path(a.runtime_root),Path(a.tools_root))
eng=mods[0]
n,s,t='AKT92','765',5
oracle=Fraction(eng.Engine2(n,s,t).solve(include_policy=False)['probability_fraction'])
rows,stats=comp.collect_candidates(mods,n,s,t,oracle)
for r in rows:
    if r['fraction']=='52/575' or 'SONDE' in r['label'] or 'SONDE' in json.dumps(r.get('spec',{}),ensure_ascii=False):
        print(json.dumps({k:r.get(k) for k in ('source','label','fraction','percent','optimal','spec','lines_provisional')},ensure_ascii=False))
print('ALL',json.dumps([(r['source'],r['label'],r['fraction']) for r in rows],ensure_ascii=False))

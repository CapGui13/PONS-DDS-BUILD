#!/usr/bin/env python3
from __future__ import annotations
import argparse,json,sys,time
from fractions import Fraction
from pathlib import Path

ap=argparse.ArgumentParser()
ap.add_argument('--runtime-root',required=True)
ap.add_argument('--tools-root',required=True)
ap.add_argument('--output',required=True)
a=ap.parse_args()

HERE=Path(__file__).resolve().parent
sys.path.insert(0,str(HERE))
sys.path.insert(0,a.tools_root)

import comparator_v60 as comp
import human_batch_v44 as batch

mods=comp.load_modules(Path(a.runtime_root),Path(a.tools_root))
eng=mods[0]
rows=[]
started=time.monotonic()
for c in batch.CASES:
    t0=time.monotonic()
    oracle=Fraction(eng.Engine2(c['north'],c['south'],c['target']).solve(include_policy=False)['probability_fraction'])
    candidates,stats=comp.collect_candidates(mods,c['north'],c['south'],c['target'],oracle)
    optimal=[x for x in candidates if Fraction(x['fraction'])==oracle]
    human=[x for x in optimal if x['source']!='ORACLE']
    top=optimal[0] if optimal else None
    row={
      'id':c['id'],'north':c['north'],'south':c['south'],'display':c['display'],'target':c['target'],
      'oracle_fraction':str(oracle),'oracle_percent':float(oracle)*100,
      'candidate_count':len(candidates),
      'exact_covered':bool(optimal),
      'human_covered':bool(human),
      'optimal_human_sources':sorted(set(x['source'] for x in human)),
      'optimal_human_labels':sorted(set(x['label'] for x in human)),
      'top_source':None if top is None else top['source'],
      'top_label':None if top is None else top['label'],
      'seconds':round(time.monotonic()-t0,3),
      'family_stats':stats,
    }
    rows.append(row)
    print(json.dumps({k:row[k] for k in ('id','target','oracle_fraction','candidate_count','human_covered','optimal_human_sources','optimal_human_labels','seconds')},ensure_ascii=False),flush=True)

human_n=sum(x['human_covered'] for x in rows)
summary={
  'schema':'MANIEMENTS_V61_HUMAN_COVERAGE_BENCH_V1',
  'cases':len(rows),
  'human_covered':human_n,
  'human_coverage_percent':round(100*human_n/len(rows),2) if rows else 0,
  'uncovered':[x['id'] for x in rows if not x['human_covered']],
  'elapsed_seconds':round(time.monotonic()-started,3),
  'runtime_frozen_sha256':'a0b580531f3c9e8bb00710b9c3e1c183b27cbfe9231c9d584e29a374ba88835d'
}
Path(a.output).write_text(json.dumps({'summary':summary,'cases':rows},ensure_ascii=False,indent=2)+'\n',encoding='utf-8')
print(json.dumps(summary,ensure_ascii=False,indent=2))

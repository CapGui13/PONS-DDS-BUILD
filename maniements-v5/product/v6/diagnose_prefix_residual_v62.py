#!/usr/bin/env python3
from __future__ import annotations
import argparse,json,sys,time
from pathlib import Path

CASES=[
 {'id':'BS_B','north':'AT987','south':'Q432','display':['AX987','D432'],'target':4},
 {'id':'BS_E','north':'AJ32','south':'K954','display':['AV32','R954'],'target':4},
 {'id':'SUITPLAY_ENC','north':'AT42','south':'953','display':['AX42','953'],'target':2},
 {'id':'ROUD_2','north':'K62','south':'AJ853','display':['R62','AV853'],'target':5},
]

ap=argparse.ArgumentParser()
ap.add_argument('--runtime-root',required=True)
ap.add_argument('--tools-root',required=True)
ap.add_argument('--output',required=True)
a=ap.parse_args()
sys.path.insert(0,str(Path(a.runtime_root)/'runtime'))
sys.path.insert(0,a.tools_root)

import integrated_engine as eng
import human_prefix_residual_v515 as v515

rows=[];t0=time.monotonic()
for c in CASES:
    r=v515.analyze(eng,c)
    rows.append(r)
    b=r.get('best') or {}
    print(json.dumps({
      'id':c['id'],
      'fraction':r['fraction'],
      'found_prefix':r['found_prefix'],
      'bridge_compact_exact':r['bridge_compact_exact'],
      'prefix_rounds':b.get('prefix_rounds'),
      'source':b.get('source'),
      'lines':b.get('full_lines'),
      'score':b.get('score'),
      'residual_states':b.get('residual_states'),
      'seconds':r['elapsed_seconds'],
    },ensure_ascii=False),flush=True)

out={
 'schema':'MANIEMENTS_V62_ADAPTIVE_PREFIX_RESIDUAL_DIAG_V1',
 'cases':rows,
 'compact_exact_count':sum(bool(x['bridge_compact_exact']) for x in rows),
 'elapsed_seconds':round(time.monotonic()-t0,3),
}
Path(a.output).write_text(json.dumps(out,ensure_ascii=False,indent=2)+'\n',encoding='utf-8')
print(json.dumps({'compact_exact_count':out['compact_exact_count'],'elapsed_seconds':out['elapsed_seconds']},ensure_ascii=False))

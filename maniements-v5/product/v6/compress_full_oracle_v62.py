#!/usr/bin/env python3
from __future__ import annotations
import argparse,json,sys,time
from pathlib import Path

CASES=[
 {'id':'BS_B','north':'AT987','south':'Q432','display':['AX987','D432'],'target':4},
 {'id':'SUITPLAY_ENC','north':'AT42','south':'953','display':['AX42','953'],'target':2},
 {'id':'ROUD_2','north':'K62','south':'AJ853','display':['R62','AV853'],'target':5},
]

ap=argparse.ArgumentParser()
ap.add_argument('--runtime-root',required=True)
ap.add_argument('--tools-root',required=True)
ap.add_argument('--case-id',required=True)
ap.add_argument('--output',required=True)
a=ap.parse_args()
sys.path.insert(0,str(Path(a.runtime_root)/'runtime'))
sys.path.insert(0,a.tools_root)
import integrated_engine as eng
import human_prefix_residual_v515 as v515

c=next(x for x in CASES if x['id']==a.case_id)
e=eng.Engine2(c['north'],c['south'],c['target'])
t0=time.monotonic()
comp=v515.compress_forest(eng,e,[e.initial()],c['display'][0],c['display'][1])
out={
 'id':c['id'],'fraction':e.solve(include_policy=False)['probability_fraction'],
 'ok':comp.get('ok'),'visible_lines':comp.get('visible_lines'),
 'spot_fallback_used':comp.get('spot_fallback_used'),
 'human_safe':comp.get('human_safe'),
 'normalized_states':comp.get('normalized_states'),
 'trees':comp.get('trees'),'decisions':comp.get('decisions'),
 'lines':comp.get('lines'),'reason':comp.get('reason'),
 'seconds':round(time.monotonic()-t0,3)
}
Path(a.output).write_text(json.dumps(out,ensure_ascii=False,indent=2)+'\n',encoding='utf-8')
print(json.dumps(out,ensure_ascii=False,indent=2))

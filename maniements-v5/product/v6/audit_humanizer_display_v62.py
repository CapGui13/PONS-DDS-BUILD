#!/usr/bin/env python3
import argparse,json,sys
from fractions import Fraction
from pathlib import Path
CASES={
 'SUITPLAY_ENC':('AT42','953',2,['AX42','953']),
 'ROUD_2':('K62','AJ853',5,['R62','AV853']),
}
ap=argparse.ArgumentParser()
ap.add_argument('--runtime-root',required=True);ap.add_argument('--tools-root',required=True)
ap.add_argument('--case-id',required=True);ap.add_argument('--output',required=True)
a=ap.parse_args()
sys.path.insert(0,str(Path(a.runtime_root)/'runtime'));sys.path.insert(0,a.tools_root)
import integrated_engine as eng
import human_semantic_v62 as sem
n,s,t,display=CASES[a.case_id]
oracle=Fraction(eng.Engine2(n,s,t).solve(include_policy=False)['probability_fraction'])
h=sem.certified_humanize(eng,n,s,t,display,oracle)
Path(a.output).write_text(json.dumps(h,ensure_ascii=False,indent=2)+'\n',encoding='utf-8')
print(json.dumps({
 'id':a.case_id,'found':h.get('found'),'kind':h.get('kind'),
 'fraction':h.get('probability_fraction'),'visible_lines':h.get('visible_lines'),
 'compact':h.get('human_compact'),'repairs':h.get('repairs'),
 'lines':h.get('lines_fr')
},ensure_ascii=False,indent=2))

#!/usr/bin/env python3
import argparse,json,sys
from pathlib import Path
ap=argparse.ArgumentParser()
ap.add_argument('--runtime-root',required=True);ap.add_argument('--tools-root',required=True);ap.add_argument('--output',required=True)
a=ap.parse_args()
sys.path.insert(0,str(Path(a.runtime_root)/'runtime'));sys.path.insert(0,a.tools_root)
import integrated_engine as eng
import human_semantic_v62 as sem
import human_semantic_v52 as v52

north,south,target='AT42','953',2
e=eng.Engine2(north,south,target)
root=e.initial();best=max(e.frontier(root),key=lambda m:(e.model.weight(m),m))
v52.v45._ENG=eng;v52.v45._E=e
tree=v52.v45.explore(eng,e,root,best,[],[],{})
comp=sem.compress(eng,e,tree,'AX42','953')
before,mb=sem.evaluate_program(eng,north,south,target,comp['program'])

patched=0
for item in comp['program']:
    k=item['key']
    # Generic strategic condition in this holding: on the second round, while
    # still needing both tricks, two of the three honors above T have already
    # been forced out. Preserve T by ducking another small card.
    if k[0]==2 and k[1]=='response' and k[4]==0 and k[5]=='TA' and k[6]=='':
        item['rules'].insert(0,{'if':[['seen_KQJ',2],['west_KQJ',1],['east_KQJ',1],['prev_class','LOW']],'action':'LOW'})
        patched+=1

after,ma=sem.evaluate_program(eng,north,south,target,comp['program'])
out={
 'oracle':str(e.model.weight(best)),
 'before':str(before),'after':str(after),'patched_groups':patched,
 'mask_matches_oracle':int(ma)==int(best),
 'visible_lines_before':comp['visible_lines'],
}
Path(a.output).write_text(json.dumps(out,ensure_ascii=False,indent=2)+'\n')
print(json.dumps(out,ensure_ascii=False,indent=2))

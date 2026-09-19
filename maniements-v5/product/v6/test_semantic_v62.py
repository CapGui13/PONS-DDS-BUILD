#!/usr/bin/env python3
import argparse,json,sys,time
from pathlib import Path
CASES={
 'SUITPLAY_ENC':('AT42','953',2,'AX42','953'),
 'ROUD_2':('K62','AJ853',5,'R62','AV853'),
 'BS_B':('AT987','Q432',4,'AX987','D432'),
}
ap=argparse.ArgumentParser()
ap.add_argument('--runtime-root',required=True);ap.add_argument('--tools-root',required=True)
ap.add_argument('--case-id',required=True);ap.add_argument('--output',required=True)
a=ap.parse_args()
sys.path.insert(0,str(Path(a.runtime_root)/'runtime'));sys.path.insert(0,a.tools_root)
import integrated_engine as eng
import human_semantic_v62 as sem
import human_semantic_v52 as v52
n,s,t,top,bottom=CASES[a.case_id]
e=eng.Engine2(n,s,t)
root=e.initial();best=max(e.frontier(root),key=lambda m:(e.model.weight(m),m))
dec=[];raw=[];v52.v45._ENG=eng;v52.v45._E=e
tree=v52.v45.explore(eng,e,root,best,dec,raw,{})
t0=time.monotonic();r=sem.compress(eng,e,tree,top,bottom)
if r.get('ok'):
    rp,rm=sem.evaluate_program(eng,n,s,t,r['program'])
    r['replay_fraction']=str(rp)
    r['replay_percent']=float(rp)*100.0
    r['replay_matches_oracle']=(rp==e.model.weight(best))
    r['replay_mask_matches_oracle']=(int(rm)==int(best))
r.update({'id':a.case_id,'fraction':str(e.model.weight(best)),'seconds':round(time.monotonic()-t0,3)})
Path(a.output).write_text(json.dumps(r,ensure_ascii=False,indent=2)+'\n',encoding='utf-8')
print(json.dumps(r,ensure_ascii=False,indent=2))

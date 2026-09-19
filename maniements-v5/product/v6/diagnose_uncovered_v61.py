#!/usr/bin/env python3
from __future__ import annotations
import argparse,json,sys
from pathlib import Path

CASES=[
 ("BS_B","AT987","Q432",4),
 ("BS_C","K432","QT5",3),
 ("BS_D","AQT32","654",4),
 ("BS_E","AJ32","K954",4),
 ("SUITPLAY_ENC","AT42","953",2),
 ("ROUD_2","K62","AJ853",5),
]

ap=argparse.ArgumentParser()
ap.add_argument('--runtime-root',required=True)
ap.add_argument('--tools-root',required=True)
ap.add_argument('--output',required=True)
a=ap.parse_args()
sys.path.insert(0,str(Path(a.runtime_root)/'runtime'))
sys.path.insert(0,a.tools_root)
import integrated_engine as eng
import prototype_v3_inspect as ins

out=[]
for cid,north,south,target in CASES:
    e=eng.Engine2(north,south,target)
    base=e.solve(include_policy=False)
    root=e.initial(); fr=e.frontier(root); best=max(fr,key=lambda m:(e.model.weight(m),m))
    seat,rank,after,leadmask=ins.select_root(eng,e,root,best)
    first=[]
    dseat=e.order(after.leader)[after.pos]
    for r,legal in e.defender_actions(after,dseat):
        need=leadmask&legal
        if not need: continue
        ch=ins.select_def_child(e,after,leadmask,dseat,r,legal)
        if not ch: continue
        ns,cm=ch
        dec=None if ins.terminal_code(e,ns) else ins.select_decl(eng,e,ns,cm)
        row={
          'defender':dseat,'card':'-' if not r else eng.I2R[r],
          'mass':str(e.model.weight(need)),
          'next':None if not dec else f'{dec[0]}:{dec[1]}',
        }
        if dec:
            row['continuation']=ins.trace_one(eng,e,dec[2],dec[3],max_actions=16)
        first.append(row)
    row={
      'id':cid,'north':north,'south':south,'target':target,
      'oracle':base['probability_fraction'],
      'root_lead':f'{seat}:{rank}',
      'root_actions':ins.root_action_probabilities(eng,e,root)[:8],
      'support':ins.support_features(eng,e,best),
      'first_branches':first,
    }
    out.append(row)
    print(json.dumps({'id':cid,'oracle':row['oracle'],'root':row['root_lead'],
                      'roots':[(x['action'],x['probability_fraction']) for x in row['root_actions']],
                      'branches':[(x['card'],x['next']) for x in first]},ensure_ascii=False),flush=True)
Path(a.output).write_text(json.dumps({'cases':out},ensure_ascii=False,indent=2)+'\n',encoding='utf-8')

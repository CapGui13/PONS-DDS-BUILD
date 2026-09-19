#!/usr/bin/env python3
from __future__ import annotations
import argparse,json,sys
from pathlib import Path

CASES=[
 ("BS_B","AT987","Q432",4),
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

def seen_cards(e,s,seat):
    m=s.west_seen if seat=='W' else s.east_seen
    return ''.join(e.I2R[r] for r in sorted(e.ranks(m),reverse=True)) or '-'

out=[]
for cid,north,south,target in CASES:
    e=eng.Engine2(north,south,target)
    solved=e.solve(include_policy=False)
    root=e.initial(); fr=e.frontier(root); best=max(fr,key=lambda m:(e.model.weight(m),m))
    seat,rank,s0,m0=ins.select_root(eng,e,root,best)
    branches=[]

    def walk(s,mask,trace):
        if s.pos==0:
            nxt=ins.select_root(eng,e,s,mask)
            branches.append({
              'trace':trace,
              'won':s.won,
              'west_seen':seen_cards(e,s,'W'),
              'east_seen':seen_cards(e,s,'E'),
              'north_remaining':ins.hand_text(eng,s.north),
              'south_remaining':ins.hand_text(eng,s.south),
              'next':None if nxt is None else f'{nxt[0]}:{nxt[1]}',
              'mass':str(e.model.weight(mask)),
            })
            return
        who=e.order(s.leader)[s.pos]
        if who in eng.DECL:
            dec=ins.select_decl(eng,e,s,mask)
            if dec is None:return
            walk(dec[2],dec[3],trace+[f'{dec[0]}:{dec[1]}'])
            return
        for r,legal in e.defender_actions(s,who):
            need=mask&legal
            if not need:continue
            child=ins.select_def_child(e,s,mask,who,r,legal)
            if child is None:continue
            ns,cm=child
            card='-' if not r else eng.I2R[r]
            walk(ns,cm,trace+[f'{who}:{card}'])

    walk(s0,m0,[f'{seat}:{rank}'])
    # Deduplicate identical public end states.
    uniq={}
    for b in branches:
        key=(b['west_seen'],b['east_seen'],b['north_remaining'],b['south_remaining'],b['won'],b['next'])
        if key not in uniq or len(b['trace'])<len(uniq[key]['trace']):
            uniq[key]=b
    rows=sorted(uniq.values(),key=lambda z:(z['next'] or '',z['west_seen'],z['east_seen']))
    item={'id':cid,'north':north,'south':south,'target':target,'oracle':solved['probability_fraction'],
          'root':f'{seat}:{rank}','after_first_trick':rows}
    out.append(item)
    print('\n'+cid,north,south,'target',target,'oracle',item['oracle'],'root',item['root'])
    for b in rows:
        print(json.dumps(b,ensure_ascii=False))
Path(a.output).write_text(json.dumps({'cases':out},ensure_ascii=False,indent=2)+'\n',encoding='utf-8')

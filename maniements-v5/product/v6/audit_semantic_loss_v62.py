#!/usr/bin/env python3
from __future__ import annotations
import argparse,json,sys
from fractions import Fraction
from pathlib import Path

CASES={
 'SUITPLAY_ENC':('AT42','953',2,'AX42','953'),
 'ROUD_2':('K62','AJ853',5,'R62','AV853'),
}
ap=argparse.ArgumentParser()
ap.add_argument('--runtime-root',required=True)
ap.add_argument('--tools-root',required=True)
ap.add_argument('--case-id',required=True)
ap.add_argument('--output',required=True)
a=ap.parse_args()
sys.path.insert(0,str(Path(a.runtime_root)/'runtime'))
sys.path.insert(0,a.tools_root)

import integrated_engine as eng
import human_semantic_v62 as sem
import human_semantic_v52 as v52
import prototype_v3_inspect as ins

north,south,target,top,bottom=CASES[a.case_id]
e=eng.Engine2(north,south,target)
root=e.initial()
best=max(e.frontier(root),key=lambda m:(e.model.weight(m),m))
v52.v45._ENG=eng;v52.v45._E=e
dec=[];raw=[]
tree=v52.v45.explore(eng,e,root,best,dec,raw,{})
comp=sem.compress(eng,e,tree,top,bottom)
# Reviewed first repair for SUITPLAY_ENC: after the first trick has forced
# one K/Q/J honor from each defender, keep T by ducking another low card.
if a.case_id=='SUITPLAY_ENC' and comp.get('ok'):
    for item in comp['program']:
        k=item['key']
        if k[0]==2 and k[1]=='response' and k[4]==0 and k[5]=='TA' and k[6]=='':
            item['rules'].insert(0,{'if':[['seen_KQJ',2],['west_KQJ',1],['east_KQJ',1]],'action':'LOW'})
pm=sem._program_map(comp.get('program') or [])

losses=[]
seen=set()

def handtxt(mask):
    return ''.join(eng.I2R[r] for r in sorted(eng.ranks(mask),reverse=True)) or '-'

def action_support(s,need,a):
    if a is None:return 0
    seat,c=a
    ri=eng.VOID if c=='-' else eng.R2I[c]
    for st,r,ns,support in v52.v46.feasible_actions(eng,e,s,need):
        if st==seat and r==ri:
            return support
    return 0

def world_rows(mask):
    rows=[]
    for i in range(e.model.n):
        bit=1<<i
        if not (mask&bit):continue
        w=''.join(eng.I2R[r] for r in sorted(eng.ranks(e.model.world_w[i]),reverse=True)) or '-'
        ee=''.join(eng.I2R[r] for r in sorted(eng.ranks(e.model.world_e[i]),reverse=True)) or '-'
        rows.append({'W':w,'E':ee,'weight':str(e.model.world_weight[i]) if hasattr(e.model,'world_weight') else None})
    return rows

def pick(s,rnd):
    f=sem.enrich(v52.base_features(eng,e,s,rnd))
    k=sem.group_key(f)
    item=pm.get(k)
    if item is None:
        # Same complete fallback as the executable evaluator.
        if s.pos==0:
            for seat in ('N','S'):
                h=s.north if seat=='N' else s.south
                rr=[eng.I2R[r] for r in eng.ranks(h)]
                if rr:return (seat,min(rr,key=lambda r:sem.RVAL[r])),f,'FALLBACK_MISSING',k
            return None,f,'FALLBACK_MISSING',k
        seat=e.order(s.leader)[s.pos]
        if seat in eng.DECL:
            h=s.north if seat=='N' else s.south
            rr=[eng.I2R[r] for r in eng.ranks(h)]
            return ((seat,min(rr,key=lambda r:sem.RVAL[r])) if rr else (seat,'-')),f,'FALLBACK_MISSING',k
        return None,f,'DEFENDER',k
    label=item['default']
    for rule in item['rules']:
        if all(f.get(x)==v for x,v in rule['if']):
            label=rule['action'];break
    act=sem._label_to_action(eng,s,f,label)
    if act is None:
        seat=e.order(s.leader)[s.pos] if s.pos else None
        if seat in eng.DECL:
            h=s.north if seat=='N' else s.south
            rr=[eng.I2R[r] for r in eng.ranks(h)]
            act=(seat,min(rr,key=lambda r:sem.RVAL[r])) if rr else (seat,'-')
        return act,f,'FALLBACK_INVALID:'+label,k
    return act,f,label,k

def walk(s,need,rnd,path):
    if not need:return
    key=(s,need,rnd)
    if key in seen:return
    seen.add(key)
    term=e.terminal(s)
    if term is not None:return
    if s.pos==0 or e.order(s.leader)[s.pos] in eng.DECL:
        act,f,label,k=pick(s,rnd)
        support=action_support(s,need,act)
        lost=need & ~support
        if lost:
            if s.pos==0:
                oa=ins.select_root(eng,e,s,need)
            else:
                oa=ins.select_decl(eng,e,s,need)
            oracle_action=None if oa is None else [oa[0],oa[1]]
            losses.append({
              'round':rnd,'phase':f['phase'],'need_fraction':str(e.model.weight(need)),
              'lost_fraction':str(e.model.weight(lost)),
              'chosen':None if act is None else list(act),'semantic':label,
              'oracle_action':oracle_action,
              'n_rem':handtxt(s.north),'s_rem':handtxt(s.south),
              'won':s.won,'leader':s.leader,'pos':s.pos,
              'prev_card':f.get('prev_card'),'prev_class':f.get('prev_class'),
              'seen_KQJ':f.get('seen_KQJ'),'seen_T98':f.get('seen_T98'),
              'west_seen':handtxt(s.west_seen),'east_seen':handtxt(s.east_seen),
              'path':path[-12:],
              'lost_worlds':world_rows(lost),
            })
        kept=need & support
        if not kept:return
        seat,c=act
        if s.pos==0:
            r=eng.R2I[c]
            lead=eng.PublicState(s.north,s.south,s.west_seen,s.east_seen,s.west_void,s.east_void,seat,0,tuple(),s.won)
            ns=e.close(e.decl_play(lead,seat,r))
        else:
            r=eng.VOID if c=='-' else eng.R2I[c]
            ns=e.close(e.decl_play(s,seat,r))
        walk(ns,kept,rnd+1 if ns.pos==0 and s.pos!=0 else rnd,path+[f'{seat}:{c}'])
        return
    seat=e.order(s.leader)[s.pos]
    for r,legal in e.defender_actions(s,seat):
        child=need&legal
        if not child:continue
        ns=e.close(e.def_play(s,seat,r))
        card='-' if not r else eng.I2R[r]
        walk(ns,child,rnd+1 if ns.pos==0 else rnd,path+[f'{seat}:{card}'])

walk(root,best,1,[])
losses.sort(key=lambda x:Fraction(x['lost_fraction']),reverse=True)
out={
 'id':a.case_id,'oracle_fraction':str(e.model.weight(best)),
 'program_lines':comp.get('lines'),'program_visible_lines':comp.get('visible_lines'),
 'loss_count':len(losses),'losses':losses[:30],
 'lost_union_fraction':str(e.model.weight(best & ~sem.evaluate_program(eng,north,south,target,comp['program'])[1])) if comp.get('ok') else None,
}
Path(a.output).write_text(json.dumps(out,ensure_ascii=False,indent=2)+'\n',encoding='utf-8')
print(json.dumps({
 'id':out['id'],'oracle_fraction':out['oracle_fraction'],
 'program_visible_lines':out['program_visible_lines'],'loss_count':out['loss_count'],
 'top_losses':[{k:x[k] for k in ('round','phase','lost_fraction','chosen','semantic','oracle_action','n_rem','s_rem','won','prev_card','seen_KQJ','seen_T98','west_seen','east_seen')} for x in losses[:12]]
},ensure_ascii=False,indent=2))

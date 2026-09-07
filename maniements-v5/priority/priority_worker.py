#!/usr/bin/env python3
from __future__ import annotations
import argparse, datetime, hashlib, json, signal, sys, time
from pathlib import Path

PLAN_ID = 'MANIEMENTS_V5_PRIORITY_P1_COMMON_SPLITS_PLUS_BOUNDARY_V1'
STATE_SCHEMA = 'MANIEMENTS_V5_PRIORITY_WORKER_STATE_V1'
WORKER_HASH_PREFIX = 'MANIEMENTS_V5_PRIORITY_P1_WORKER_V1:'
COMMON_SPLITS = {(2,3),(2,4),(3,3),(3,4)}
PLAN_TOTAL_ORBITS = 146641
PLAN_RANDOM_DEAL_MASS = 0.4611817577950189

class TargetTimeout(Exception):
    pass

def alarm_handler(signum, frame):
    raise TargetTimeout()

def utcnow():
    return datetime.datetime.now(datetime.timezone.utc).replace(microsecond=0).isoformat()

def profile(sid:int):
    code=sid; nmask=smask=0; nc=sc=0
    for r in range(2,15):
        d=code%3; code//=3
        if d==1:
            nmask |= 1<<r; nc += 1
        elif d==2:
            smask |= 1<<r; sc += 1
    canonical = (nmask,smask) < (smask,nmask)
    return nmask,smask,nc,sc,canonical

def eligible_counts(nc:int, sc:int)->bool:
    a,b=sorted((nc,sc)); v=a+b
    boundary = (v==1) or (a==1 and b==1) or (v>=12)
    return boundary or ((a,b) in COMMON_SPLITS)

def worker_for(sid:int,count:int)->int:
    h=hashlib.sha256(f'{WORKER_HASH_PREFIX}{sid}'.encode('ascii')).digest()
    return int.from_bytes(h[:8],'big')%count

def split_key(nc:int,sc:int)->str:
    a,b=sorted((nc,sc)); return f'{a}-{b}'

def blank_state(worker:int,count:int,target_cap:float):
    return {
        'schema':STATE_SCHEMA,'plan_id':PLAN_ID,'plan_total_orbits':PLAN_TOTAL_ORBITS,
        'plan_random_deal_probability_mass':PLAN_RANDOM_DEAL_MASS,
        'worker_id':worker,'worker_count':count,'target_cap_seconds':target_cap,
        'next_scan_state_id':1,'active_orbit':None,'sequence':0,'done':False,
        'completed_orbits':0,'completed_ordered_rows':0,'completed_targets':0,
        'deferred_orbits':0,'completed_by_split':{},'deferred_by_split':{},
        'updated_at_utc':utcnow(),
    }

def load_state(root:Path,worker:int,count:int,target_cap:float):
    p=root/'priority'/'state.json'
    if not p.exists(): return blank_state(worker,count,target_cap)
    s=json.loads(p.read_text(encoding='utf-8'))
    exp={'schema':STATE_SCHEMA,'plan_id':PLAN_ID,'worker_id':worker,'worker_count':count}
    for k,v in exp.items():
        if s.get(k)!=v: raise RuntimeError(f'priority state mismatch: {k}')
    if abs(float(s.get('target_cap_seconds'))-target_cap)>1e-9:
        raise RuntimeError('priority target cap changed; use a new plan/stage instead of mutating P1')
    return s

def next_candidate(state,worker,count,universe):
    sid=int(state['next_scan_state_id'])
    while sid<=universe:
        _,_,nc,sc,canon=profile(sid)
        nxt=sid+1
        if canon and eligible_counts(nc,sc) and worker_for(sid,count)==worker:
            state['next_scan_state_id']=nxt
            return sid,nc,sc
        sid=nxt
    state['next_scan_state_id']=universe+1
    return None,None,None

def bump(d:dict,k:str,n:int=1):
    d[k]=int(d.get(k,0))+n

def main():
    ap=argparse.ArgumentParser()
    ap.add_argument('--runtime-root',required=True)
    ap.add_argument('--state-root',required=True)
    ap.add_argument('--worker-id',type=int,required=True)
    ap.add_argument('--worker-count',type=int,default=20)
    ap.add_argument('--budget-seconds',type=float,default=1320)
    ap.add_argument('--close-reserve-seconds',type=float,default=120)
    ap.add_argument('--target-cap-seconds',type=float,default=180)
    a=ap.parse_args()
    if not (0<=a.worker_id<a.worker_count<=64): raise SystemExit('invalid worker id/count')
    if a.target_cap_seconds<=0: raise SystemExit('invalid target cap')
    if a.budget_seconds<=a.close_reserve_seconds+a.target_cap_seconds+5: raise SystemExit('budget too small')

    sys.path.insert(0,str(Path(a.runtime_root)/'runtime'))
    import integrated_engine as eng
    import generator_v5 as core
    import orbit_pass_v5 as op

    root=Path(a.state_root)
    (root/'priority'/'chunks').mkdir(parents=True,exist_ok=True)
    (root/'priority'/'deferred').mkdir(parents=True,exist_ok=True)
    state=load_state(root,a.worker_id,a.worker_count,a.target_cap_seconds)
    if state.get('done'):
        print(json.dumps({'status':'DONE','worker_id':a.worker_id,'completed_orbits':state['completed_orbits'],'deferred_orbits':state['deferred_orbits']},sort_keys=True))
        return

    started=time.monotonic(); deadline=started+a.budget_seconds-a.close_reserve_seconds
    rows=[]; deferred=[]; pass_complete=pass_deferred=pass_targets=0
    old_handler=signal.signal(signal.SIGALRM,alarm_handler)
    try:
        while True:
            remaining=deadline-time.monotonic()
            if remaining < a.target_cap_seconds+5:
                break

            if state['active_orbit'] is None:
                sid,nc,sc=next_candidate(state,a.worker_id,a.worker_count,eng.UNIVERSE_SIZE)
                if sid is None:
                    state['done']=True; break
                st=op.state_static(sid)
                state['active_orbit']={
                    'rep_state_id':sid,'north':st['north'],'south':st['south'],
                    'north_count':nc,'south_count':sc,'split':split_key(nc,sc),
                    'max_target':st['max_target'],'targets':[],
                }

            active=state['active_orbit']; sid=int(active['rep_state_id'])
            st=op.state_static(sid); t=len(active['targets'])
            if t>st['max_target']:
                arow,brow=op.reconstruct_rows(st,active['targets'])
                rows.extend((arow,brow)); pass_complete+=1
                state['completed_orbits']+=1; state['completed_ordered_rows']+=2
                bump(state['completed_by_split'],active['split'])
                state['active_orbit']=None
                continue

            try:
                signal.setitimer(signal.ITIMER_REAL,a.target_cap_seconds)
                result=op.compute_target(st,t)
                signal.setitimer(signal.ITIMER_REAL,0)
            except TargetTimeout:
                signal.setitimer(signal.ITIMER_REAL,0)
                rec={
                    'schema':'MANIEMENTS_V5_PRIORITY_DEFERRED_ORBIT_V1','plan_id':PLAN_ID,
                    'worker_id':a.worker_id,'rep_state_id':sid,'swap_state_id':st['swap_state_id'],
                    'north':st['north'],'south':st['south'],'split':active['split'],
                    'blocked_target':t,'target_cap_seconds':a.target_cap_seconds,
                    'completed_prefix_targets':active['targets'],'deferred_at_utc':utcnow(),
                }
                deferred.append(rec); pass_deferred+=1
                state['deferred_orbits']+=1; bump(state['deferred_by_split'],active['split'])
                state['active_orbit']=None
                continue
            active['targets'].append(result)
            state['completed_targets']+=1; pass_targets+=1

        active=state.get('active_orbit')
        if active is not None:
            st=op.state_static(int(active['rep_state_id']))
            if len(active['targets'])==st['max_target']+1:
                arow,brow=op.reconstruct_rows(st,active['targets'])
                rows.extend((arow,brow)); pass_complete+=1
                state['completed_orbits']+=1; state['completed_ordered_rows']+=2
                bump(state['completed_by_split'],active['split']); state['active_orbit']=None
    finally:
        signal.setitimer(signal.ITIMER_REAL,0)
        signal.signal(signal.SIGALRM,old_handler)

    seq=int(state.get('sequence',0))
    if rows:
        p=root/'priority'/'chunks'/f'chunk_{seq:06d}.jsonl'
        with p.open('wb') as f:
            for row in rows: f.write(core.canonical_json_bytes(row))
    if deferred:
        p=root/'priority'/'deferred'/f'deferred_{seq:06d}.jsonl'
        with p.open('wb') as f:
            for rec in deferred: f.write(core.canonical_json_bytes(rec))

    state['sequence']=seq+1
    state['updated_at_utc']=utcnow()
    state['last_pass']={
        'sequence':seq,'completed_orbits':pass_complete,'deferred_orbits':pass_deferred,
        'completed_targets':pass_targets,'elapsed_seconds':round(time.monotonic()-started,6),
    }
    (root/'priority'/'state.json').write_text(json.dumps(state,sort_keys=True,indent=2)+'\n',encoding='utf-8')
    print(json.dumps({
        'status':'DONE' if state.get('done') else 'BUDGET_STOP','worker_id':a.worker_id,
        'sequence':seq,'pass_completed_orbits':pass_complete,'pass_deferred_orbits':pass_deferred,
        'pass_completed_targets':pass_targets,'cumulative_completed_orbits':state['completed_orbits'],
        'cumulative_deferred_orbits':state['deferred_orbits'],'next_scan_state_id':state['next_scan_state_id'],
        'active_rep_state_id':None if state['active_orbit'] is None else state['active_orbit']['rep_state_id'],
    },sort_keys=True))

if __name__=='__main__': main()

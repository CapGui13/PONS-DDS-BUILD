#!/usr/bin/env python3
from __future__ import annotations

import argparse, datetime, json, signal, sys, time
from collections import defaultdict
from fractions import Fraction
from pathlib import Path

# Importing v31 installs the exact semantic supported_plan into materialize_worker_v3.
import materialize_worker_v31  # noqa: F401
import materialize_worker_v3 as base

PRIORITY_MODE='HONOR_FIRST_X_FAMILY_V1'
LOW='234567'
MAJOR='AKQJ'
INTERMEDIATE='T98'


class TargetTimeout(Exception):
    pass


def alarm_handler(signum, frame):
    raise TargetTimeout()


def utcnow():
    return datetime.datetime.now(datetime.timezone.utc).replace(microsecond=0).isoformat()


def skeleton_hand(hand:str) -> str:
    return ''.join('x' if c in LOW else c for c in hand)


def skeleton(row):
    return skeleton_hand(row['north'])+'/'+skeleton_hand(row['south'])


def family_priority(row):
    n=row['north']; s=row['south']
    mn=sum(c in MAJOR for c in n); ms=sum(c in MAJOR for c in s); m=mn+ms
    one_hand_two=int(max(mn,ms)>=2)
    split=int(mn>0 and ms>0)
    # The most useful classical maneuver families usually own 2–3 of A/K/Q/J.
    if m in (2,3): tier=6
    elif m==1: tier=5
    elif m==4: tier=4
    elif any(c=='T' for c in n+s): tier=3
    elif any(c in '98' for c in n+s): tier=2
    else: tier=1
    inter=sum(c in INTERMEDIATE for c in n+s)
    xcount=sum(c in LOW for c in n+s)
    total=len(n)+len(s)
    # Descending tuple: honor-rich first, then families with a real two-honor holding,
    # then split honors and explicit intermediates. Prefer ordinary 6–8 card holdings.
    ordinary=int(5<=total<=8)
    return (tier,one_hand_two,split,m,inter,ordinary,xcount,-abs(len(n)-len(s)))


def iter_all_source_rows(source:Path):
    for p in sorted((source/'priority'/'chunks').glob('chunk_*.jsonl')):
        with p.open(encoding='utf-8') as f:
            for line in f:
                if not line.strip():
                    continue
                row=json.loads(line)
                if row.get('policy_swap_to_input'):
                    continue
                yield row


def load_keys(root:Path, subdir:str, prefix:str):
    out=set()
    for p in sorted((root/'dictionary'/subdir).glob(prefix+'*.jsonl')):
        with p.open(encoding='utf-8') as f:
            for line in f:
                if line.strip():
                    r=json.loads(line); out.add((int(r['state_id']),int(r['target'])))
    return out


def positive_targets(row):
    curve=row['curve']
    for t in range(1,len(curve)):
        if Fraction(curve[t])>0:
            yield t


def pending_families(source:Path,root:Path):
    done=load_keys(root,'chunks','chunk_')
    deferred=load_keys(root,'deferred','deferred_')
    fam=defaultdict(list)
    fam_row={}
    total_fresh=0
    for row in iter_all_source_rows(source):
        sid=int(row['state_id']); sk=skeleton(row); fam_row.setdefault(sk,row)
        for t in positive_targets(row):
            k=(sid,t)
            if k in done or k in deferred:
                continue
            fam[sk].append((row,t)); total_fresh+=1
    ordered=sorted(fam.items(),key=lambda kv:(family_priority(fam_row[kv[0]]),kv[0]),reverse=True)
    return ordered,done,deferred,total_fresh


def main():
    ap=argparse.ArgumentParser()
    ap.add_argument('--runtime-root',required=True)
    ap.add_argument('--source-root',required=True)
    ap.add_argument('--state-root',required=True)
    ap.add_argument('--worker-id',type=int,required=True)
    ap.add_argument('--budget-seconds',type=float,default=1320)
    ap.add_argument('--close-reserve-seconds',type=float,default=120)
    ap.add_argument('--target-cap-seconds',type=float,default=210)
    a=ap.parse_args()

    sys.path.insert(0,str(Path(a.runtime_root)/'runtime'))
    import integrated_engine as eng
    here=Path(__file__).resolve().parent; sys.path.insert(0,str(here))
    import prototype_v3_builtin_policy as bp
    import prototype_v3_policy_compress as pc
    import prototype_v3_compile as cc

    source=Path(a.source_root); root=Path(a.state_root)
    (root/'dictionary'/'chunks').mkdir(parents=True,exist_ok=True)
    (root/'dictionary'/'deferred').mkdir(parents=True,exist_ok=True)
    state=base.load_state(root,a.worker_id,a.target_cap_seconds)
    state['caught_up']=False; state['priority_mode']=PRIORITY_MODE

    families,done,deferred,total_fresh=pending_families(source,root)
    started=time.monotonic(); deadline=started+a.budget_seconds-a.close_reserve_seconds
    entries=[]; new_deferred=[]; pass_ok=pass_def=0; families_touched=[]
    old_handler=signal.signal(signal.SIGALRM,alarm_handler)
    stop=False
    try:
        for sk,items in families:
            if stop: break
            touched=False
            # Stable order inside a generalized x-family.
            items.sort(key=lambda rt:(int(rt[0]['state_id']),int(rt[1])))
            for row,t in items:
                if time.monotonic()>=deadline-a.target_cap_seconds-5:
                    stop=True; break
                sid=int(row['state_id'])
                try:
                    signal.setitimer(signal.ITIMER_REAL,a.target_cap_seconds)
                    comp,states=base.solve_one(eng,bp,pc,cc,row['north'],row['south'],t,row['curve'][t],row['policy_sha256'][t])
                    signal.setitimer(signal.ITIMER_REAL,0)
                    entries.append({'schema':base.ENTRY_SCHEMA,'plan_id':base.PLAN_ID,'worker_id':a.worker_id,
                                    'state_id':sid,'north':row['north'],'south':row['south'],'target':t,
                                    'probability_fraction':row['curve'][t],'policy_sha256':row['policy_sha256'][t],
                                    'policy_states':states,'extractor':base.EXTRACTOR,'compact':comp,
                                    'materialized_at_utc':utcnow(),'priority_mode':PRIORITY_MODE,'x_family':sk})
                    done.add((sid,t)); pass_ok+=1; touched=True
                except (base.TargetTimeout,TargetTimeout):
                    signal.setitimer(signal.ITIMER_REAL,0)
                    new_deferred.append({'schema':base.DEFER_SCHEMA,'plan_id':base.PLAN_ID,'worker_id':a.worker_id,
                                         'state_id':sid,'north':row['north'],'south':row['south'],'target':t,
                                         'probability_fraction':row['curve'][t],'policy_sha256':row['policy_sha256'][t],
                                         'target_cap_seconds':a.target_cap_seconds,'reason':'TARGET_TIMEOUT',
                                         'extractor':base.EXTRACTOR,'deferred_at_utc':utcnow(),
                                         'priority_mode':PRIORITY_MODE,'x_family':sk})
                    deferred.add((sid,t)); pass_def+=1; touched=True
            if touched: families_touched.append(sk)
    finally:
        signal.setitimer(signal.ITIMER_REAL,0); signal.signal(signal.SIGALRM,old_handler)

    seq=int(state.get('sequence',0))
    if entries:
        p=root/'dictionary'/'chunks'/f'chunk_{seq:06d}.jsonl'
        with p.open('w',encoding='utf-8') as f:
            for x in entries: f.write(json.dumps(x,sort_keys=True,separators=(',',':'),ensure_ascii=False)+'\n')
    if new_deferred:
        p=root/'dictionary'/'deferred'/f'deferred_{seq:06d}.jsonl'
        with p.open('w',encoding='utf-8') as f:
            for x in new_deferred: f.write(json.dumps(x,sort_keys=True,separators=(',',':'),ensure_ascii=False)+'\n')

    # Re-scan only logically: fresh backlog before this pass minus attempted targets.
    remaining=max(0,total_fresh-pass_ok-pass_def)
    state['sequence']=seq+1
    state['materialized_targets']=len(done)
    state['deferred_targets']=len(deferred)
    state['updated_at_utc']=utcnow()
    state['extractor']=base.EXTRACTOR
    state['active_state_id']=None
    state['next_target']=1
    state['next_source_state_id']=1
    state['caught_up']=(remaining==0)
    try:
        state['source_done']=bool(json.loads((source/'priority'/'state.json').read_text(encoding='utf-8')).get('done'))
    except Exception:
        pass
    state['last_pass']={'sequence':seq,'materialized_targets':pass_ok,'deferred_targets':pass_def,
                        'elapsed_seconds':round(time.monotonic()-started,6),'extractor':base.EXTRACTOR,
                        'priority_mode':PRIORITY_MODE,'families_touched':len(families_touched),
                        'first_families':families_touched[:12],'fresh_targets_remaining':remaining}
    (root/'dictionary'/'state.json').write_text(json.dumps(state,sort_keys=True,indent=2,ensure_ascii=False)+'\n',encoding='utf-8')
    print(json.dumps({'status':'CAUGHT_UP' if state['caught_up'] else 'BUDGET_STOP','worker_id':a.worker_id,
                      'extractor':base.EXTRACTOR,'priority_mode':PRIORITY_MODE,
                      'pass_materialized_targets':pass_ok,'pass_deferred_targets':pass_def,
                      'families_touched':len(families_touched),'first_families':families_touched[:12],
                      'fresh_targets_remaining':remaining,'cumulative_materialized_targets':state['materialized_targets'],
                      'cumulative_deferred_targets':state['deferred_targets']},sort_keys=True,ensure_ascii=False))


if __name__=='__main__':
    main()

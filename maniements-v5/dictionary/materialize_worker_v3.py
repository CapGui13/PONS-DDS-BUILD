#!/usr/bin/env python3
from __future__ import annotations
import argparse, datetime, json, signal, sys, time
from collections import Counter
from fractions import Fraction
from pathlib import Path

SCHEMA='MANIEMENTS_V5_DICTIONARY_WORKER_STATE_V2'
ENTRY_SCHEMA='MANIEMENTS_V5_DICTIONARY_ENTRY_V2'
DEFER_SCHEMA='MANIEMENTS_V5_DICTIONARY_DEFERRED_TARGET_V2'
PLAN_ID='MANIEMENTS_V5_PRIORITY_P1_COMMON_SPLITS_PLUS_BOUNDARY_V1'
EXTRACTOR='NATIVE_PUBLIC_POLICY_COMPRESSED_V3'
SEAT_FR={'N':'Nord','S':'Sud','E':'Est','W':'Ouest'}

class TargetTimeout(Exception): pass
def alarm_handler(signum,frame): raise TargetTimeout()
def utcnow(): return datetime.datetime.now(datetime.timezone.utc).replace(microsecond=0).isoformat()
def frac_positive(fr): return Fraction(fr)>0

def blank_state(worker,cap):
    return {'schema':SCHEMA,'plan_id':PLAN_ID,'worker_id':worker,'target_cap_seconds':cap,'extractor':EXTRACTOR,
            'next_source_state_id':1,'active_state_id':None,'next_target':1,'sequence':0,'materialized_targets':0,
            'deferred_targets':0,'caught_up':False,'source_done':False,'updated_at_utc':utcnow()}
def load_state(root,worker,cap):
    p=root/'dictionary'/'state.json'
    if not p.exists(): return blank_state(worker,cap)
    s=json.loads(p.read_text(encoding='utf-8'))
    for k,v in {'schema':SCHEMA,'plan_id':PLAN_ID,'worker_id':worker}.items():
        if s.get(k)!=v: raise RuntimeError(f'state mismatch {k}: {s.get(k)!r} != {v!r}')
    if abs(float(s.get('target_cap_seconds'))-cap)>1e-9: raise RuntimeError('target cap mismatch')
    s['extractor']=EXTRACTOR; return s

def iter_source_rows(source:Path,min_sid:int):
    for p in sorted((source/'priority'/'chunks').glob('chunk_*.jsonl')):
        with p.open(encoding='utf-8') as f:
            for line in f:
                if not line.strip(): continue
                row=json.loads(line)
                if row.get('policy_swap_to_input'): continue
                sid=int(row['state_id'])
                if sid>=min_sid: yield row

def parse_action(a): return a.split(':',1)
def fr_card(r): return {'A':"l'As",'K':'le Roi','Q':'la Dame','J':'le Valet','T':'le 10'}.get(r,'le '+r)
def action_fr(a):
    seat,rank=parse_action(a); return f'jouer {fr_card(rank)} de {SEAT_FR[seat]}'

def boundary_plan(eng,north,south,target,probability):
    n=eng.parse(north); s=eng.parse(south); cn,cs,sw=eng.canonical_frame(n,s)
    root=eng._boundary_root_action_map(cn,cs,target)
    if sw: root=dict((eng.swap_action(k),v) for k,v in root.items())
    p=Fraction(probability); best=sorted(a for a,fr in root.items() if Fraction(fr)==p)
    lead=best[0] if best else (sorted(root)[0] if root else None)
    summary=(action_fr(lead).capitalize()+'.') if lead else 'Jouer les cartes maîtresses disponibles.'
    return {'kind':'boundary_closed_form_v3','extractor':EXTRACTOR,'lead':lead,'summary_fr':summary,
            'probability_fraction':probability,'target':target,'confidence':'HIGH','coverage':'BOUNDARY_CLOSED_FORM',
            'pattern':'BOUNDARY_CLOSED_FORM'}

def native_policy_dict(bp,north,south,target,solved,source):
    solved=dict(solved); policy=solved.pop('policy')
    rows=[]; by_depth=Counter(); by_action=Counter(); fresh=Counter()
    for key_text,action in policy.items():
        st=bp.normalize_state(key_text); depth=bp.state_depth(st,north,south)
        row={'depth':depth,'action':action,**st}; rows.append(row); by_depth[depth]+=1; by_action[action]+=1
        if st['pos']==0: fresh[action]+=1
    rows.sort(key=lambda r:(r['depth'],r['won'],r['leader'],r['pos'],r['west_seen'],r['east_seen'],r['north_remaining'],r['south_remaining'],r['action']))
    return {'schema':'MANIEMENTS_V5_DICTIONARY_V3_NATIVE_POLICY_V2','case':{'north':north,'south':south,'target':target},
            'policy_source':source,'solve':solved,'policy_state_count':len(rows),'policy_states':rows,
            'summary':{'states_by_depth':dict(sorted(by_depth.items())),'actions':dict(sorted(by_action.items())),
                       'fresh_trick_actions':dict(sorted(fresh.items()))}}

def supported_plan(eng,bp,pc,cc,north,south,target,expected_prob):
    e=eng.Engine2(north,south,target)
    base=e.solve(include_policy=False); prob=base['probability_fraction']
    if Fraction(prob)!=Fraction(expected_prob): raise RuntimeError(f'probability mismatch {prob} != {expected_prob}')
    root=e.initial(); fr=e.frontier(root); best=max(fr,key=lambda m:(e.model.weight(m),m))
    if e.model.weight(best)!=Fraction(expected_prob): raise RuntimeError('optimal-mask probability mismatch')
    source={'mode':'FULL_SOLVE'}
    try:
        solved=e.solve(include_policy=True)
    except (AssertionError,RuntimeError,ValueError):
        e2=eng.Engine2(north,south,target); e2.model.all=best
        solved=e2.solve(include_policy=True)
        if solved['success_worlds']!=best.bit_count(): raise RuntimeError('optimal-mask replay lost winning worlds')
        source={'mode':'OPTIMAL_MASK_REPLAY','winning_worlds':best.bit_count(),'winning_mask':str(best)}
    if Fraction(solved['probability_fraction'])!=Fraction(expected_prob): raise RuntimeError('policy probability mismatch')
    native=native_policy_dict(bp,north,south,target,solved,source)
    program=pc.compress_policy_dict(native)
    if program['program_stats']['unseparable_contexts']!=0: raise RuntimeError('unseparable V3 policy contexts')
    compiled=cc.compile_policy_program(program); compact=pc.compact_policy_program(program)
    return ({'kind':'native_public_policy_v3','extractor':EXTRACTOR,'lead':compiled['root_lead'],
             'summary_fr':compiled['summary_fr'],'probability_fraction':prob,'target':target,
             'confidence':'HIGH','coverage':'EXACT_POLICY_PROGRAM','pattern':'NATIVE_POLICY_PROGRAM_EXACT',
             'policy_source':source,'program_stats':program['program_stats'],'policy_program':compact},
            native['policy_state_count'])

def solve_one(eng,bp,pc,cc,north,south,target,expected_prob,expected_hash):
    n=eng.parse(north); s=eng.parse(south); cn,cs,sw=eng.canonical_frame(n,s)
    if sw: raise RuntimeError('source row is not canonical')
    ph=eng.policy_recipe(north,south,target)['policy_sha256']
    if ph!=expected_hash: raise RuntimeError('policy recipe hash mismatch')
    if eng.is_w3_supported_masks(cn,cs): return supported_plan(eng,bp,pc,cc,north,south,target,expected_prob)
    res=eng.solve_target_integrated(north,south,target,False)
    if Fraction(res['probability_fraction'])!=Fraction(expected_prob) or res['policy_sha256']!=expected_hash:
        raise RuntimeError('boundary verification mismatch')
    return boundary_plan(eng,north,south,target,expected_prob),'programmatic_total'

def main():
    ap=argparse.ArgumentParser(); ap.add_argument('--runtime-root',required=True); ap.add_argument('--source-root',required=True)
    ap.add_argument('--state-root',required=True); ap.add_argument('--worker-id',type=int,required=True)
    ap.add_argument('--budget-seconds',type=float,default=1320); ap.add_argument('--close-reserve-seconds',type=float,default=120)
    ap.add_argument('--target-cap-seconds',type=float,default=210); a=ap.parse_args()
    sys.path.insert(0,str(Path(a.runtime_root)/'runtime')); import integrated_engine as eng
    here=Path(__file__).resolve().parent; sys.path.insert(0,str(here))
    import prototype_v3_builtin_policy as bp
    import prototype_v3_policy_compress as pc
    import prototype_v3_compile as cc

    source=Path(a.source_root); root=Path(a.state_root); (root/'dictionary'/'chunks').mkdir(parents=True,exist_ok=True); (root/'dictionary'/'deferred').mkdir(parents=True,exist_ok=True)
    state=load_state(root,a.worker_id,a.target_cap_seconds); state['caught_up']=False
    started=time.monotonic(); deadline=started+a.budget_seconds-a.close_reserve_seconds; entries=[]; deferred=[]; pass_ok=pass_def=0
    old_handler=signal.signal(signal.SIGALRM,alarm_handler)
    try:
        start_sid=int(state['active_state_id']) if state['active_state_id'] is not None else int(state['next_source_state_id'])
        rows=list(iter_source_rows(source,start_sid)); rowmap={int(r['state_id']):r for r in rows}
        while time.monotonic()<deadline-a.target_cap_seconds-5:
            if state['active_state_id'] is None:
                candidates=[sid for sid in rowmap if sid>=int(state['next_source_state_id'])]
                if not candidates:
                    state['caught_up']=True
                    try: state['source_done']=bool(json.loads((source/'priority'/'state.json').read_text(encoding='utf-8')).get('done'))
                    except Exception: pass
                    break
                sid=min(candidates); state['active_state_id']=sid; state['next_target']=1
            sid=int(state['active_state_id']); row=rowmap.get(sid)
            if row is None:
                state['active_state_id']=None; state['next_source_state_id']=sid+1; state['next_target']=1; continue
            curve=row['curve']; hashes=row['policy_sha256']; t=int(state['next_target'])
            while t<len(curve) and not frac_positive(curve[t]): t+=1
            if t>=len(curve):
                state['active_state_id']=None; state['next_source_state_id']=sid+1; state['next_target']=1; continue
            if time.monotonic()>=deadline-a.target_cap_seconds-5: break
            try:
                signal.setitimer(signal.ITIMER_REAL,a.target_cap_seconds)
                comp,states=solve_one(eng,bp,pc,cc,row['north'],row['south'],t,curve[t],hashes[t])
                signal.setitimer(signal.ITIMER_REAL,0)
                entries.append({'schema':ENTRY_SCHEMA,'plan_id':PLAN_ID,'worker_id':a.worker_id,'state_id':sid,'north':row['north'],'south':row['south'],'target':t,
                                'probability_fraction':curve[t],'policy_sha256':hashes[t],'policy_states':states,'extractor':EXTRACTOR,'compact':comp,'materialized_at_utc':utcnow()})
                pass_ok+=1; state['materialized_targets']+=1
            except TargetTimeout:
                signal.setitimer(signal.ITIMER_REAL,0)
                deferred.append({'schema':DEFER_SCHEMA,'plan_id':PLAN_ID,'worker_id':a.worker_id,'state_id':sid,'north':row['north'],'south':row['south'],'target':t,
                                 'probability_fraction':curve[t],'policy_sha256':hashes[t],'target_cap_seconds':a.target_cap_seconds,'reason':'TARGET_TIMEOUT','extractor':EXTRACTOR,'deferred_at_utc':utcnow()})
                pass_def+=1; state['deferred_targets']+=1
            t+=1
            while t<len(curve) and not frac_positive(curve[t]): t+=1
            state['next_target']=t
            if t>=len(curve): state['active_state_id']=None; state['next_source_state_id']=sid+1; state['next_target']=1
    finally:
        signal.setitimer(signal.ITIMER_REAL,0); signal.signal(signal.SIGALRM,old_handler)
    seq=int(state['sequence'])
    if entries:
        p=root/'dictionary'/'chunks'/f'chunk_{seq:06d}.jsonl'
        with p.open('w',encoding='utf-8') as f:
            for x in entries: f.write(json.dumps(x,sort_keys=True,separators=(',',':'),ensure_ascii=False)+'\n')
    if deferred:
        p=root/'dictionary'/'deferred'/f'deferred_{seq:06d}.jsonl'
        with p.open('w',encoding='utf-8') as f:
            for x in deferred: f.write(json.dumps(x,sort_keys=True,separators=(',',':'),ensure_ascii=False)+'\n')
    state['sequence']=seq+1; state['updated_at_utc']=utcnow(); state['extractor']=EXTRACTOR
    state['last_pass']={'sequence':seq,'materialized_targets':pass_ok,'deferred_targets':pass_def,'elapsed_seconds':round(time.monotonic()-started,6),'extractor':EXTRACTOR}
    (root/'dictionary'/'state.json').write_text(json.dumps(state,sort_keys=True,indent=2,ensure_ascii=False)+'\n',encoding='utf-8')
    print(json.dumps({'status':'CAUGHT_UP' if state['caught_up'] else 'BUDGET_STOP','worker_id':a.worker_id,'extractor':EXTRACTOR,
                      'pass_materialized_targets':pass_ok,'pass_deferred_targets':pass_def,'cumulative_materialized_targets':state['materialized_targets'],
                      'cumulative_deferred_targets':state['deferred_targets'],'next_source_state_id':state['next_source_state_id'],'active_state_id':state['active_state_id']},sort_keys=True))
if __name__=='__main__': main()

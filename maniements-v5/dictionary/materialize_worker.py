#!/usr/bin/env python3
from __future__ import annotations
import argparse, ast, datetime, json, signal, sys, time
from fractions import Fraction
from pathlib import Path

SCHEMA='MANIEMENTS_V5_DICTIONARY_WORKER_STATE_V1'
ENTRY_SCHEMA='MANIEMENTS_V5_DICTIONARY_ENTRY_V1'
PLAN_ID='MANIEMENTS_V5_PRIORITY_P1_COMMON_SPLITS_PLUS_BOUNDARY_V1'
RANK_FR={'A':'A','K':'R','Q':'D','J':'V','T':'10','9':'9','8':'8','7':'7','6':'6','5':'5','4':'4','3':'3','2':'2','-':'-'}
SEAT_FR={'N':'Nord','S':'Sud','E':'Est','W':'Ouest'}

class TargetTimeout(Exception): pass

def alarm_handler(signum, frame): raise TargetTimeout()
def utcnow(): return datetime.datetime.now(datetime.timezone.utc).replace(microsecond=0).isoformat()

def fr_rank(r): return RANK_FR.get(r,r)
def fr_seat(s): return SEAT_FR.get(s,s)
def frac_positive(fr): return Fraction(fr)>0

def blank_state(worker,cap):
    return {'schema':SCHEMA,'plan_id':PLAN_ID,'worker_id':worker,'target_cap_seconds':cap,
            'next_source_state_id':1,'active_state_id':None,'next_target':1,'sequence':0,
            'materialized_targets':0,'deferred_targets':0,'caught_up':False,'source_done':False,
            'updated_at_utc':utcnow()}

def load_state(root,worker,cap):
    p=root/'dictionary'/'state.json'
    if not p.exists(): return blank_state(worker,cap)
    s=json.loads(p.read_text())
    for k,v in {'schema':SCHEMA,'plan_id':PLAN_ID,'worker_id':worker}.items():
        if s.get(k)!=v: raise RuntimeError(f'state mismatch {k}')
    if abs(float(s.get('target_cap_seconds'))-cap)>1e-9: raise RuntimeError('target cap mismatch')
    return s

def iter_source_rows(source:Path,min_sid:int):
    for p in sorted((source/'priority'/'chunks').glob('chunk_*.jsonl')):
        with p.open(encoding='utf-8') as f:
            for line in f:
                if not line.strip(): continue
                row=json.loads(line)
                if row.get('policy_swap_to_input'): continue
                sid=int(row['state_id'])
                if sid < min_sid: continue
                yield row

def parse_action(a):
    seat,rank=a.split(':',1); return seat,rank

def fr_card_with_article(r):
    x=fr_rank(r)
    if x=='A': return "l'A"
    if x=='D': return 'la D'
    return 'le '+x

def action_fr(a,lead=False):
    seat,rank=parse_action(a)
    if rank=='-': return f'{fr_seat(seat)} est à sec'
    card=fr_card_with_article(rank)
    if lead:
        x=fr_rank(rank)
        prep=("de l'A" if x=='A' else 'de la D' if x=='D' else 'du '+x)
        return f'partir {prep} de {fr_seat(seat)}'
    return f'jouer {card} de {fr_seat(seat)}'

def cards_fr(cards):
    vals=[c for c in cards if c!='-']; has_void='-' in cards
    order={'2':2,'3':3,'4':4,'5':5,'6':6,'7':7,'8':8,'9':9,'T':10,'J':11,'Q':12,'K':13,'A':14}
    vals=sorted(set(vals),key=lambda x:order[x],reverse=True)
    parts=[fr_card_with_article(c) for c in vals]
    if len(parts)==1: txt=parts[0]
    elif len(parts)==2: txt=parts[0]+' ou '+parts[1]
    elif parts: txt=', '.join(parts[:-1])+' ou '+parts[-1]
    else: txt=''
    if has_void: txt += (' ou ' if txt else '')+'est chicane'
    return txt or '—'

def choose_policy_action(policy,s):
    return policy.get(repr(s.public_key_tuple())) if hasattr(s,'public_key_tuple') else None

def compile_summary(engine,policy,target,probability):
    root=engine.initial()
    pk=repr(engine.public_key(root))
    lead=policy.get(pk)
    if not lead:
        return {'kind':'no_policy','summary_fr':'Ligne exacte non matérialisable sous forme courte.'}
    seat,rank=parse_action(lead)
    SType=type(root)
    ls=SType(root.north,root.south,root.west_seen,root.east_seen,root.west_void,root.east_void,seat,0,tuple(),root.won)
    after=engine.decl_play(ls,seat,engine.R2I[rank] if hasattr(engine,'R2I') else 0)
    dseat=engine.order(after.leader)[after.pos]
    groups={}
    branches=[]
    for rr,legal in engine.defender_actions(after,dseat):
        ns=engine.close(engine.def_play(after,dseat,rr))
        term=engine.terminal(ns)
        if term is not None:
            act='__TERM__'
        else:
            act=policy.get(repr(engine.public_key(ns))) or '__MISSING__'
        rc='-' if not rr else engine.I2R[rr]
        groups.setdefault(act,[]).append(rc)
        branches.append((rc,act,ns))
    sentence=action_fr(lead,True); sentence=sentence[0].upper()+sentence[1:]+'.'
    clauses=[]
    for act,cards in groups.items():
        cond=cards_fr(cards)
        if cards==['-']:
            prefix=f'Si {fr_seat(dseat)} est chicane'
        elif '-' in cards:
            real=cards_fr([c for c in cards if c!='-'])
            prefix=f'Si {fr_seat(dseat)} fournit {real} ou est chicane'
        else:
            prefix=f'Si {fr_seat(dseat)} fournit {cond}'
        if act=='__TERM__': rhs='l’objectif est déjà décidé'
        elif act=='__MISSING__': rhs='continuer selon la ligne exacte'
        else: rhs=action_fr(act,False)
        clauses.append(prefix+', '+rhs)
    if clauses: sentence+=' '+' ; '.join(clauses)+'.'

    next_leads=[]
    for rc,act,ns in branches:
        if act.startswith('__'): continue
        aseat,arank=parse_action(act)
        rint=engine.R2I.get(arank,0)
        ns2=engine.close(engine.decl_play(ns,aseat,rint))
        if engine.terminal(ns2) is not None: continue
        if ns2.pos==0:
            na=policy.get(repr(engine.public_key(ns2)))
            if na: next_leads.append(na)
            continue
        d2=engine.order(ns2.leader)[ns2.pos]
        if d2 in ('N','S'): continue
        for rr2,legal2 in engine.defender_actions(ns2,d2):
            ns3=engine.close(engine.def_play(ns2,d2,rr2))
            if engine.terminal(ns3) is not None: continue
            if ns3.pos==0:
                na=policy.get(repr(engine.public_key(ns3)))
                if na: next_leads.append(na)
    if next_leads and len(set(next_leads))==1:
        sentence+=' Puis '+action_fr(next_leads[0],True)+'.'

    return {'kind':'public_support_dp','lead':lead,
            'first_defender':dseat,
            'response_groups':[{'cards':cards,'action':act} for act,cards in groups.items()],
            'common_next_lead':next_leads[0] if next_leads and len(set(next_leads))==1 else None,
            'summary_fr':sentence,
            'probability_fraction':probability,'target':target}

def boundary_summary(engmod,north,south,target,probability):
    n=engmod.parse(north); s=engmod.parse(south); cn,cs,sw=engmod.canonical_frame(n,s)
    root=engmod._boundary_root_action_map(cn,cs,target)
    if sw: root=dict((engmod.swap_action(k),v) for k,v in root.items())
    best=[]
    p=Fraction(probability)
    for a,fr in root.items():
        if Fraction(fr)==p: best.append(a)
    lead=sorted(best)[0] if best else (sorted(root)[0] if root else None)
    text=(action_fr(lead,True).capitalize()+'.') if lead else 'Jouer les cartes maîtresses disponibles.'
    return {'kind':'boundary_closed_form','lead':lead,'summary_fr':text,
            'probability_fraction':probability,'target':target}

def solve_one(engmod,north,south,target,expected_prob,expected_hash):
    n=engmod.parse(north); s=engmod.parse(south); cn,cs,sw=engmod.canonical_frame(n,s)
    if sw: raise RuntimeError('source row is not canonical')
    if engmod.is_w3_supported_masks(cn,cs):
        e=engmod.Engine2(north,south,target)
        e.R2I=engmod.R2I; e.I2R=engmod.I2R
        base=e.solve(include_policy=True)
        prob=base['probability_fraction']
        ph=engmod.policy_recipe(north,south,target)['policy_sha256']
        if prob!=expected_prob: raise RuntimeError(f'probability mismatch {prob} != {expected_prob}')
        if ph!=expected_hash: raise RuntimeError('policy hash mismatch')
        comp=compile_summary(e,base['policy'],target,prob)
        states=base.get('policy_states',0)
    else:
        res=engmod.solve_target_integrated(north,south,target,False)
        prob=res['probability_fraction']; ph=res['policy_sha256']
        if prob!=expected_prob or ph!=expected_hash: raise RuntimeError('boundary verification mismatch')
        comp=boundary_summary(engmod,north,south,target,prob); states='programmatic_total'
    return comp,states

def main():
    ap=argparse.ArgumentParser()
    ap.add_argument('--runtime-root',required=True)
    ap.add_argument('--source-root',required=True)
    ap.add_argument('--state-root',required=True)
    ap.add_argument('--worker-id',type=int,required=True)
    ap.add_argument('--budget-seconds',type=float,default=900)
    ap.add_argument('--close-reserve-seconds',type=float,default=90)
    ap.add_argument('--target-cap-seconds',type=float,default=210)
    a=ap.parse_args()
    sys.path.insert(0,str(Path(a.runtime_root)/'runtime'))
    import integrated_engine as eng

    source=Path(a.source_root); root=Path(a.state_root)
    (root/'dictionary'/'chunks').mkdir(parents=True,exist_ok=True)
    (root/'dictionary'/'deferred').mkdir(parents=True,exist_ok=True)
    state=load_state(root,a.worker_id,a.target_cap_seconds)
    state['caught_up']=False
    started=time.monotonic(); deadline=started+a.budget_seconds-a.close_reserve_seconds
    entries=[]; deferred=[]; pass_ok=pass_def=0
    old=signal.signal(signal.SIGALRM,alarm_handler)
    try:
        rows=list(iter_source_rows(source,int(state['next_source_state_id']) if state['active_state_id'] is None else int(state['active_state_id'])))
        rowmap={int(r['state_id']):r for r in rows}
        while time.monotonic() < deadline-a.target_cap_seconds-5:
            if state['active_state_id'] is None:
                candidates=sorted(sid for sid in rowmap if sid>=int(state['next_source_state_id']))
                if not candidates:
                    state['caught_up']=True
                    try:
                        ps=json.loads((source/'priority'/'state.json').read_text())
                        state['source_done']=bool(ps.get('done'))
                    except Exception: pass
                    break
                sid=candidates[0]; state['active_state_id']=sid; state['next_target']=1
            sid=int(state['active_state_id']); row=rowmap.get(sid)
            if row is None:
                state['active_state_id']=None; state['next_source_state_id']=sid+1; continue
            curve=row['curve']; hashes=row['policy_sha256']; t=int(state['next_target'])
            while t<len(curve) and not frac_positive(curve[t]): t+=1
            if t>=len(curve):
                state['active_state_id']=None; state['next_source_state_id']=sid+1; state['next_target']=1; continue
            if time.monotonic() >= deadline-a.target_cap_seconds-5: break
            try:
                signal.setitimer(signal.ITIMER_REAL,a.target_cap_seconds)
                comp,states=solve_one(eng,row['north'],row['south'],t,curve[t],hashes[t])
                signal.setitimer(signal.ITIMER_REAL,0)
                entries.append({'schema':ENTRY_SCHEMA,'plan_id':PLAN_ID,'worker_id':a.worker_id,
                    'state_id':sid,'north':row['north'],'south':row['south'],'target':t,
                    'probability_fraction':curve[t],'policy_sha256':hashes[t],
                    'policy_states':states,'compact':comp,'materialized_at_utc':utcnow()})
                pass_ok+=1; state['materialized_targets']+=1
            except TargetTimeout:
                signal.setitimer(signal.ITIMER_REAL,0)
                deferred.append({'schema':'MANIEMENTS_V5_DICTIONARY_DEFERRED_TARGET_V1','plan_id':PLAN_ID,
                    'worker_id':a.worker_id,'state_id':sid,'north':row['north'],'south':row['south'],
                    'target':t,'probability_fraction':curve[t],'policy_sha256':hashes[t],
                    'target_cap_seconds':a.target_cap_seconds,'deferred_at_utc':utcnow()})
                pass_def+=1; state['deferred_targets']+=1
            t+=1; state['next_target']=t
            while t<len(curve) and not frac_positive(curve[t]): t+=1
            state['next_target']=t
            if t>=len(curve):
                state['active_state_id']=None; state['next_source_state_id']=sid+1; state['next_target']=1
    finally:
        signal.setitimer(signal.ITIMER_REAL,0); signal.signal(signal.SIGALRM,old)

    seq=int(state['sequence'])
    if entries:
        p=root/'dictionary'/'chunks'/f'chunk_{seq:06d}.jsonl'
        with p.open('w',encoding='utf-8') as f:
            for x in entries: f.write(json.dumps(x,sort_keys=True,separators=(',',':'))+'\n')
    if deferred:
        p=root/'dictionary'/'deferred'/f'deferred_{seq:06d}.jsonl'
        with p.open('w',encoding='utf-8') as f:
            for x in deferred: f.write(json.dumps(x,sort_keys=True,separators=(',',':'))+'\n')
    state['sequence']=seq+1; state['updated_at_utc']=utcnow()
    state['last_pass']={'sequence':seq,'materialized_targets':pass_ok,'deferred_targets':pass_def,
                        'elapsed_seconds':round(time.monotonic()-started,6)}
    (root/'dictionary'/'state.json').write_text(json.dumps(state,sort_keys=True,indent=2)+'\n')
    print(json.dumps({'status':'CAUGHT_UP' if state['caught_up'] else 'BUDGET_STOP','worker_id':a.worker_id,
                      'pass_materialized_targets':pass_ok,'pass_deferred_targets':pass_def,
                      'cumulative_materialized_targets':state['materialized_targets'],
                      'cumulative_deferred_targets':state['deferred_targets'],
                      'next_source_state_id':state['next_source_state_id'],'active_state_id':state['active_state_id']},sort_keys=True))

if __name__=='__main__': main()

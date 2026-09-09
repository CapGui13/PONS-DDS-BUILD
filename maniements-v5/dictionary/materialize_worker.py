#!/usr/bin/env python3
from __future__ import annotations
import argparse, datetime, json, signal, sys, time
from fractions import Fraction
from pathlib import Path

SCHEMA = 'MANIEMENTS_V5_DICTIONARY_WORKER_STATE_V1'
ENTRY_SCHEMA = 'MANIEMENTS_V5_DICTIONARY_ENTRY_V1'
DEFER_SCHEMA = 'MANIEMENTS_V5_DICTIONARY_DEFERRED_TARGET_V1'
PLAN_ID = 'MANIEMENTS_V5_PRIORITY_P1_COMMON_SPLITS_PLUS_BOUNDARY_V1'
EXTRACTOR = 'LOCAL_WITNESS_FIRST_DEFENSE_V2'
RANK_FR = {'A':'A','K':'R','Q':'D','J':'V','T':'10','9':'9','8':'8','7':'7','6':'6','5':'5','4':'4','3':'3','2':'2','-':'-'}
SEAT_FR = {'N':'Nord','S':'Sud','E':'Est','W':'Ouest'}

class TargetTimeout(Exception):
    pass

def alarm_handler(signum, frame):
    raise TargetTimeout()

def utcnow():
    return datetime.datetime.now(datetime.timezone.utc).replace(microsecond=0).isoformat()

def fr_rank(r):
    return RANK_FR.get(r, r)

def fr_seat(s):
    return SEAT_FR.get(s, s)

def frac_positive(fr):
    return Fraction(fr) > 0

def blank_state(worker, cap):
    return {
        'schema':SCHEMA, 'plan_id':PLAN_ID, 'worker_id':worker,
        'target_cap_seconds':cap, 'extractor':EXTRACTOR,
        'next_source_state_id':1, 'active_state_id':None, 'next_target':1,
        'sequence':0, 'materialized_targets':0, 'deferred_targets':0,
        'caught_up':False, 'source_done':False, 'updated_at_utc':utcnow(),
    }

def load_state(root, worker, cap):
    p = root/'dictionary'/'state.json'
    if not p.exists():
        return blank_state(worker, cap)
    s = json.loads(p.read_text(encoding='utf-8'))
    for k,v in {'schema':SCHEMA,'plan_id':PLAN_ID,'worker_id':worker}.items():
        if s.get(k) != v:
            raise RuntimeError(f'state mismatch {k}')
    if abs(float(s.get('target_cap_seconds')) - cap) > 1e-9:
        raise RuntimeError('target cap mismatch')
    s['extractor'] = EXTRACTOR
    return s

def iter_source_rows(source:Path, min_sid:int):
    for p in sorted((source/'priority'/'chunks').glob('chunk_*.jsonl')):
        with p.open(encoding='utf-8') as f:
            for line in f:
                if not line.strip():
                    continue
                row = json.loads(line)
                if row.get('policy_swap_to_input'):
                    continue
                sid = int(row['state_id'])
                if sid >= min_sid:
                    yield row

def parse_action(a):
    return a.split(':', 1)

def fr_card_with_article(r):
    x = fr_rank(r)
    if x == 'A':
        return "l'A"
    if x == 'D':
        return 'la D'
    return 'le ' + x

def action_fr(a, lead=False):
    seat, rank = parse_action(a)
    if rank == '-':
        return f'{fr_seat(seat)} est à sec'
    if lead:
        x = fr_rank(rank)
        prep = "de l'A" if x == 'A' else ('de la D' if x == 'D' else 'du '+x)
        return f'partir {prep} de {fr_seat(seat)}'
    return f'jouer {fr_card_with_article(rank)} de {fr_seat(seat)}'

def cards_fr(cards):
    vals = [c for c in cards if c != '-']
    has_void = '-' in cards
    order = {'2':2,'3':3,'4':4,'5':5,'6':6,'7':7,'8':8,'9':9,'T':10,'J':11,'Q':12,'K':13,'A':14}
    vals = sorted(set(vals), key=lambda x:order[x], reverse=True)
    parts = [fr_card_with_article(c) for c in vals]
    if len(parts) == 1:
        txt = parts[0]
    elif len(parts) == 2:
        txt = parts[0] + ' ou ' + parts[1]
    elif parts:
        txt = ', '.join(parts[:-1]) + ' ou ' + parts[-1]
    else:
        txt = ''
    if has_void:
        txt += (' ou ' if txt else '') + 'est chicane'
    return txt or '—'

def terminal_code(e, s):
    if e.target == 0 or s.won >= e.target:
        return '__SUCCESS__'
    if s.pos == 0 and not (s.north or s.south):
        return '__END__'
    future = max(s.north.bit_count(), s.south.bit_count()) + (1 if s.pos else 0)
    if s.won + future < e.target:
        return '__IMPOSSIBLE__'
    return None

def select_root_witness(engmod, e, s, mask):
    candidates = []
    for seat,hand in (('N',s.north),('S',s.south)):
        for r in engmod.ranks(hand):
            lead = engmod.PublicState(s.north,s.south,s.west_seen,s.east_seen,s.west_void,s.east_void,seat,0,tuple(),s.won)
            ns = e.decl_play(lead, seat, r)
            for cm in e.frontier(ns):
                if (mask | cm) == cm:
                    candidates.append((seat,r,ns,cm))
    if not candidates:
        raise AssertionError('no root witness')
    candidates.sort(key=lambda x:(0 if x[0]=='N' else 1, x[1], -float(e.model.weight(x[3])), -x[3]))
    seat,r,ns,cm = candidates[0]
    return f'{seat}:{engmod.I2R[r]}', ns, cm

def select_decl_witness(engmod, e, s, mask):
    seat = e.order(s.leader)[s.pos]
    if seat not in engmod.DECL:
        raise AssertionError('expected declarer node')
    hand = s.north if seat == 'N' else s.south
    acts = engmod.ranks(hand) if hand else (engmod.VOID,)
    candidates = []
    for r in acts:
        ns = e.close(e.decl_play(s, seat, r))
        for cm in e.frontier(ns):
            if (mask | cm) == cm:
                candidates.append((r,ns,cm))
    if not candidates:
        raise AssertionError('no declarer continuation witness')
    candidates.sort(key=lambda x:(x[0], -float(e.model.weight(x[2])), -x[2]))
    r,ns,cm = candidates[0]
    return f"{seat}:{'-' if not r else engmod.I2R[r]}", ns, cm

def select_defender_child(e, s, mask, seat, r, legal):
    ns = e.close(e.def_play(s, seat, r))
    need = mask & legal
    feasible = [cm for cm in e.frontier(ns) if (need | cm) == cm]
    if not feasible:
        raise AssertionError('defender branch lacks witness')
    cm = max(feasible, key=lambda x:(e.model.weight(x), x))
    return ns, cm

def compact_local_witness(engmod, e, probability):
    """Extract root lead + exact response to every observable first-defense card.

    This intentionally avoids recursively collapsing the entire proof DAG into one
    global public-state action table. The frozen full extractor can encounter a
    transposition conflict on some targets. For the concise dictionary, the root
    lead and first-defense responses are enough and can be selected with exactly
    the same local witness/tie-break rules without modifying the frozen engine.
    """
    root = e.initial()
    fr = e.frontier(root)
    best = max(fr, key=lambda m:(e.model.weight(m), m))
    p = e.model.weight(best)
    if f'{p.numerator}/{p.denominator}' != probability:
        raise AssertionError('root probability mismatch during compact extraction')

    lead, after_lead, lead_mask = select_root_witness(engmod, e, root, best)
    dseat = e.order(after_lead.leader)[after_lead.pos]
    if dseat in engmod.DECL:
        raise AssertionError('expected first defender after lead')

    groups = {}
    structured = []
    for r,legal in e.defender_actions(after_lead, dseat):
        ns, branch_mask = select_defender_child(e, after_lead, lead_mask, dseat, r, legal)
        term = terminal_code(e, ns)
        if term:
            act = term
        else:
            act, _, _ = select_decl_witness(engmod, e, ns, branch_mask)
        rc = '-' if not r else engmod.I2R[r]
        groups.setdefault(act, []).append(rc)
        structured.append({'card':rc,'action':act})

    sentence = action_fr(lead, True)
    sentence = sentence[0].upper() + sentence[1:] + '.'
    clauses = []
    for act,cards in groups.items():
        if cards == ['-']:
            prefix = f'Si {fr_seat(dseat)} est chicane'
        elif '-' in cards:
            real = cards_fr([c for c in cards if c != '-'])
            prefix = f'Si {fr_seat(dseat)} fournit {real} ou est chicane'
        else:
            prefix = f'Si {fr_seat(dseat)} fournit {cards_fr(cards)}'
        if act == '__SUCCESS__':
            rhs = "l'objectif est atteint"
        elif act == '__IMPOSSIBLE__':
            rhs = "l'objectif devient impossible"
        elif act == '__END__':
            rhs = 'la couleur est terminée'
        else:
            rhs = action_fr(act, False)
        clauses.append(prefix + ', ' + rhs)
    if clauses:
        sentence += ' ' + ' ; '.join(clauses) + '.'

    return {
        'kind':'public_support_dp_local_witness',
        'extractor':EXTRACTOR,
        'lead':lead,
        'first_defender':dseat,
        'response_groups':[{'cards':cards,'action':act} for act,cards in groups.items()],
        'first_defender_branches':structured,
        'summary_fr':sentence,
        'probability_fraction':probability,
        'target':e.target,
    }

def boundary_summary(engmod, north, south, target, probability):
    n = engmod.parse(north); s = engmod.parse(south)
    cn,cs,sw = engmod.canonical_frame(n,s)
    root = engmod._boundary_root_action_map(cn,cs,target)
    if sw:
        root = dict((engmod.swap_action(k),v) for k,v in root.items())
    p = Fraction(probability)
    best = [a for a,fr in root.items() if Fraction(fr) == p]
    lead = sorted(best)[0] if best else (sorted(root)[0] if root else None)
    txt = (action_fr(lead,True).capitalize()+'.') if lead else 'Jouer les cartes maîtresses disponibles.'
    return {
        'kind':'boundary_closed_form','extractor':EXTRACTOR,'lead':lead,
        'summary_fr':txt,'probability_fraction':probability,'target':target,
    }

def solve_one(engmod, north, south, target, expected_prob, expected_hash):
    n = engmod.parse(north); s = engmod.parse(south)
    cn,cs,sw = engmod.canonical_frame(n,s)
    if sw:
        raise RuntimeError('source row is not canonical')
    ph = engmod.policy_recipe(north,south,target)['policy_sha256']
    if ph != expected_hash:
        raise RuntimeError('policy recipe hash mismatch')

    if engmod.is_w3_supported_masks(cn,cs):
        e = engmod.Engine2(north,south,target)
        base = e.solve(include_policy=False)
        prob = base['probability_fraction']
        if prob != expected_prob:
            raise RuntimeError(f'probability mismatch {prob} != {expected_prob}')
        comp = compact_local_witness(engmod, e, prob)
        states = len(e.cache)
    else:
        res = engmod.solve_target_integrated(north,south,target,False)
        prob = res['probability_fraction']
        if prob != expected_prob or res['policy_sha256'] != expected_hash:
            raise RuntimeError('boundary verification mismatch')
        comp = boundary_summary(engmod,north,south,target,prob)
        states = 'programmatic_total'
    return comp, states

def main():
    ap = argparse.ArgumentParser()
    ap.add_argument('--runtime-root',required=True)
    ap.add_argument('--source-root',required=True)
    ap.add_argument('--state-root',required=True)
    ap.add_argument('--worker-id',type=int,required=True)
    ap.add_argument('--budget-seconds',type=float,default=900)
    ap.add_argument('--close-reserve-seconds',type=float,default=90)
    ap.add_argument('--target-cap-seconds',type=float,default=210)
    a = ap.parse_args()
    sys.path.insert(0,str(Path(a.runtime_root)/'runtime'))
    import integrated_engine as eng

    source = Path(a.source_root); root = Path(a.state_root)
    (root/'dictionary'/'chunks').mkdir(parents=True,exist_ok=True)
    (root/'dictionary'/'deferred').mkdir(parents=True,exist_ok=True)
    state = load_state(root,a.worker_id,a.target_cap_seconds)
    state['caught_up'] = False
    started = time.monotonic(); deadline = started+a.budget_seconds-a.close_reserve_seconds
    entries=[]; deferred=[]; pass_ok=pass_def=0
    old_handler = signal.signal(signal.SIGALRM,alarm_handler)
    try:
        start_sid = int(state['active_state_id']) if state['active_state_id'] is not None else int(state['next_source_state_id'])
        rows = list(iter_source_rows(source,start_sid))
        rowmap = {int(r['state_id']):r for r in rows}
        while time.monotonic() < deadline-a.target_cap_seconds-5:
            if state['active_state_id'] is None:
                candidates = [sid for sid in rowmap if sid >= int(state['next_source_state_id'])]
                if not candidates:
                    state['caught_up'] = True
                    try:
                        ps=json.loads((source/'priority'/'state.json').read_text(encoding='utf-8'))
                        state['source_done']=bool(ps.get('done'))
                    except Exception:
                        pass
                    break
                sid=min(candidates); state['active_state_id']=sid; state['next_target']=1

            sid=int(state['active_state_id']); row=rowmap.get(sid)
            if row is None:
                state['active_state_id']=None; state['next_source_state_id']=sid+1; state['next_target']=1
                continue
            curve=row['curve']; hashes=row['policy_sha256']; t=int(state['next_target'])
            while t < len(curve) and not frac_positive(curve[t]):
                t += 1
            if t >= len(curve):
                state['active_state_id']=None; state['next_source_state_id']=sid+1; state['next_target']=1
                continue
            if time.monotonic() >= deadline-a.target_cap_seconds-5:
                break

            try:
                signal.setitimer(signal.ITIMER_REAL,a.target_cap_seconds)
                comp,states=solve_one(eng,row['north'],row['south'],t,curve[t],hashes[t])
                signal.setitimer(signal.ITIMER_REAL,0)
                entries.append({
                    'schema':ENTRY_SCHEMA,'plan_id':PLAN_ID,'worker_id':a.worker_id,
                    'state_id':sid,'north':row['north'],'south':row['south'],'target':t,
                    'probability_fraction':curve[t],'policy_sha256':hashes[t],
                    'policy_states':states,'extractor':EXTRACTOR,'compact':comp,
                    'materialized_at_utc':utcnow(),
                })
                pass_ok+=1; state['materialized_targets']+=1
            except TargetTimeout:
                signal.setitimer(signal.ITIMER_REAL,0)
                deferred.append({
                    'schema':DEFER_SCHEMA,'plan_id':PLAN_ID,'worker_id':a.worker_id,
                    'state_id':sid,'north':row['north'],'south':row['south'],'target':t,
                    'probability_fraction':curve[t],'policy_sha256':hashes[t],
                    'target_cap_seconds':a.target_cap_seconds,'reason':'TARGET_TIMEOUT',
                    'extractor':EXTRACTOR,'deferred_at_utc':utcnow(),
                })
                pass_def+=1; state['deferred_targets']+=1

            t += 1
            while t < len(curve) and not frac_positive(curve[t]):
                t += 1
            state['next_target']=t
            if t >= len(curve):
                state['active_state_id']=None; state['next_source_state_id']=sid+1; state['next_target']=1
    finally:
        signal.setitimer(signal.ITIMER_REAL,0)
        signal.signal(signal.SIGALRM,old_handler)

    seq=int(state['sequence'])
    if entries:
        p=root/'dictionary'/'chunks'/f'chunk_{seq:06d}.jsonl'
        with p.open('w',encoding='utf-8') as f:
            for x in entries:
                f.write(json.dumps(x,sort_keys=True,separators=(',',':'),ensure_ascii=False)+'\n')
    if deferred:
        p=root/'dictionary'/'deferred'/f'deferred_{seq:06d}.jsonl'
        with p.open('w',encoding='utf-8') as f:
            for x in deferred:
                f.write(json.dumps(x,sort_keys=True,separators=(',',':'),ensure_ascii=False)+'\n')

    state['sequence']=seq+1; state['updated_at_utc']=utcnow(); state['extractor']=EXTRACTOR
    state['last_pass']={
        'sequence':seq,'materialized_targets':pass_ok,'deferred_targets':pass_def,
        'elapsed_seconds':round(time.monotonic()-started,6),'extractor':EXTRACTOR,
    }
    (root/'dictionary'/'state.json').write_text(json.dumps(state,sort_keys=True,indent=2,ensure_ascii=False)+'\n',encoding='utf-8')
    print(json.dumps({
        'status':'CAUGHT_UP' if state['caught_up'] else 'BUDGET_STOP',
        'worker_id':a.worker_id,'extractor':EXTRACTOR,
        'pass_materialized_targets':pass_ok,'pass_deferred_targets':pass_def,
        'cumulative_materialized_targets':state['materialized_targets'],
        'cumulative_deferred_targets':state['deferred_targets'],
        'next_source_state_id':state['next_source_state_id'],'active_state_id':state['active_state_id'],
    },sort_keys=True))

if __name__=='__main__':
    main()

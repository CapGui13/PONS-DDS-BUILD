#!/usr/bin/env python3
from __future__ import annotations
import argparse, ast, json, sys
from collections import Counter, defaultdict
from fractions import Fraction
from pathlib import Path


def normalize_state(key_text):
    k=ast.literal_eval(key_text)
    north,south,west_seen,east_seen,west_void,east_void,leader,pos,trick,won,target=k
    return {
        'north_remaining':north,
        'south_remaining':south,
        'west_seen':west_seen,
        'east_seen':east_seen,
        'west_void':bool(west_void),
        'east_void':bool(east_void),
        'leader':leader,
        'pos':pos,
        'trick':[{'seat':seat,'card':card} for seat,card in trick],
        'won':won,
        'target':target,
    }


def holding_len(text):
    return 0 if text=='-' else len(text)


def state_depth(st, north0, south0):
    visible0=holding_len(north0)+holding_len(south0)
    visible_now=holding_len(st['north_remaining'])+holding_len(st['south_remaining'])
    return visible0-visible_now


def main():
    ap=argparse.ArgumentParser()
    ap.add_argument('--runtime-root',required=True)
    ap.add_argument('--north',required=True)
    ap.add_argument('--south',required=True)
    ap.add_argument('--target',type=int,required=True)
    ap.add_argument('--winning-mask',type=int,
                    help='Previously certified exact optimal success mask in this WorldModel ordering.')
    ap.add_argument('--expected-probability',
                    help='Optional exact fraction used to verify a certified-mask replay, e.g. 135/161.')
    a=ap.parse_args()

    sys.path.insert(0,str(Path(a.runtime_root)/'runtime'))
    import integrated_engine as eng

    e=eng.Engine2(a.north,a.south,a.target)
    policy_source={'mode':'FULL_SOLVE'}
    if a.winning_mask is not None:
        original_all=e.model.all
        if a.winning_mask <= 0 or (a.winning_mask | original_all) != original_all:
            raise SystemExit('winning mask is not a non-empty subset of the WorldModel universe')
        exact_weight=e.model.weight(a.winning_mask)
        if a.expected_probability is not None and exact_weight != Fraction(a.expected_probability):
            raise SystemExit(f'certified mask weight mismatch: {exact_weight} != {a.expected_probability}')
        # Restrict only the initial hidden-world universe. World indices, owner masks,
        # and exact weights remain identical to the original full solve, so the saved
        # success mask can be replayed without changing its semantics.
        e.model.all=a.winning_mask
        policy_source={
            'mode':'CERTIFIED_WINNING_MASK_REPLAY',
            'winning_mask':str(a.winning_mask),
            'winning_worlds':a.winning_mask.bit_count(),
            'certified_probability_fraction':f'{exact_weight.numerator}/{exact_weight.denominator}',
        }

    solved=e.solve(include_policy=True)
    if a.expected_probability is not None and Fraction(solved['probability_fraction']) != Fraction(a.expected_probability):
        raise SystemExit(f'policy solve probability mismatch: {solved["probability_fraction"]} != {a.expected_probability}')
    if a.winning_mask is not None and solved['success_worlds'] != a.winning_mask.bit_count():
        raise SystemExit('restricted policy did not preserve every certified winning world')

    policy=solved.pop('policy')
    rows=[]
    by_depth=Counter()
    by_action=Counter()
    fresh_actions=Counter()
    for key_text,action in policy.items():
        st=normalize_state(key_text)
        depth=state_depth(st,a.north,a.south)
        row={'depth':depth,'action':action,**st}
        rows.append(row)
        by_depth[depth]+=1
        by_action[action]+=1
        if st['pos']==0:
            fresh_actions[action]+=1
    rows.sort(key=lambda r:(r['depth'],r['won'],r['leader'],r['pos'],r['west_seen'],r['east_seen'],r['north_remaining'],r['south_remaining'],r['action']))

    fresh_by_depth=defaultdict(list)
    for r in rows:
        if r['pos']==0:
            fresh_by_depth[str(r['depth'])].append({
                'won':r['won'],
                'west_seen':r['west_seen'],
                'east_seen':r['east_seen'],
                'west_void':r['west_void'],
                'east_void':r['east_void'],
                'north_remaining':r['north_remaining'],
                'south_remaining':r['south_remaining'],
                'action':r['action'],
            })

    out={
        'schema':'MANIEMENTS_V5_DICTIONARY_V3_NATIVE_POLICY_V2',
        'case':{'north':a.north,'south':a.south,'target':a.target},
        'policy_source':policy_source,
        'solve':solved,
        'policy_state_count':len(rows),
        'policy_states':rows,
        'summary':{
            'states_by_depth':dict(sorted(by_depth.items())),
            'actions':dict(sorted(by_action.items())),
            'fresh_trick_actions':dict(sorted(fresh_actions.items())),
        },
        'fresh_trick_states_by_depth':dict(fresh_by_depth),
    }
    print(json.dumps(out,ensure_ascii=False,indent=2,sort_keys=True))


if __name__=='__main__':
    main()

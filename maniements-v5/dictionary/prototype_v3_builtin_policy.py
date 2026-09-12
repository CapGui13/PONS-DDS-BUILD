#!/usr/bin/env python3
from __future__ import annotations
import argparse, ast, json, sys
from collections import Counter, defaultdict
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


def state_depth(st, north0, south0):
    visible0=len(north0)+len(south0)
    visible_now=len(st['north_remaining'])+len(st['south_remaining'])
    return visible0-visible_now


def main():
    ap=argparse.ArgumentParser()
    ap.add_argument('--runtime-root',required=True)
    ap.add_argument('--north',required=True)
    ap.add_argument('--south',required=True)
    ap.add_argument('--target',type=int,required=True)
    a=ap.parse_args()

    sys.path.insert(0,str(Path(a.runtime_root)/'runtime'))
    import integrated_engine as eng

    e=eng.Engine2(a.north,a.south,a.target)
    solved=e.solve(include_policy=True)
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

    # Compact conditional tables for fresh-trick declarer decisions. These are
    # especially useful for bridge-language compilation because they identify
    # when observed defensive cards change the next-round plan.
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
        'schema':'MANIEMENTS_V5_DICTIONARY_V3_NATIVE_POLICY_V1',
        'case':{'north':a.north,'south':a.south,'target':a.target},
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

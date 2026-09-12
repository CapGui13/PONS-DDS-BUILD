#!/usr/bin/env python3
from __future__ import annotations
import argparse, json, sys
from collections import deque
from pathlib import Path

import prototype_v3_inspect as base


def declarer_candidates(eng, e, s, mask):
    seat = e.order(s.leader)[s.pos]
    hand = s.north if seat == 'N' else s.south
    acts = eng.ranks(hand) if hand else (eng.VOID,)
    cands=[]
    for r in acts:
        ns=e.close(e.decl_play(s,seat,r))
        for cm in e.frontier(ns):
            if (mask | cm) == cm:
                cands.append((r,ns,cm))
    cands.sort(key=lambda x:(x[0],-float(e.model.weight(x[2])),-x[2]))
    return seat, cands


def card_text(eng, r):
    return '-' if not r else eng.I2R[r]


def graph_key(state, support):
    return (base.state_key(state), support)


def build_policy_graph(eng, e, start_state, start_mask, max_nodes=5000, max_depth=10):
    nodes={}
    seen={}
    queue=deque()
    stats={
        'unique_nodes':0,
        'declarer_nodes':0,
        'defender_nodes':0,
        'defender_branches':0,
        'terminal_nodes':0,
        'depth_limited_nodes':0,
        'budget_limited_links':0,
        'deduplicated_links':0,
        'max_depth_seen':0,
    }

    def register(state, support, depth):
        key=graph_key(state,support)
        if key in seen:
            stats['deduplicated_links'] += 1
            return seen[key]
        if len(seen) >= max_nodes:
            stats['budget_limited_links'] += 1
            return None
        node_id=len(seen)
        seen[key]=node_id
        queue.append((node_id,state,support,depth))
        stats['unique_nodes']=len(seen)
        return node_id

    root_id=register(start_state,start_mask,0)

    while queue:
        node_id,state,support,depth=queue.popleft()
        stats['max_depth_seen']=max(stats['max_depth_seen'],depth)
        common={
            'id':node_id,
            'depth':depth,
            'won':state.won,
            'support_mass':str(e.model.weight(support)),
            'support_bits':support.bit_count(),
        }
        term=base.terminal_code(e,state)
        if term:
            stats['terminal_nodes'] += 1
            nodes[str(node_id)]={**common,'role':'TERMINAL','terminal':term}
            continue
        if depth >= max_depth:
            stats['depth_limited_nodes'] += 1
            nodes[str(node_id)]={**common,'role':'TRUNCATED','reason':'DEPTH_LIMIT'}
            continue

        seat=e.order(state.leader)[state.pos]
        if seat in eng.DECL:
            stats['declarer_nodes'] += 1
            dseat,cands=declarer_candidates(eng,e,state,support)
            if not cands:
                nodes[str(node_id)]={**common,'role':'DECL','seat':seat,'error':'no declarer witness'}
                continue
            r,ns,cm=cands[0]
            alternatives=[]
            action_seen=set()
            for ar,_,acm in cands:
                txt=card_text(eng,ar)
                if txt in action_seen:
                    continue
                action_seen.add(txt)
                alternatives.append({
                    'card':txt,
                    'support_mass':str(e.model.weight(acm)),
                    'support_bits':acm.bit_count(),
                })
            child_id=register(ns,cm,depth+1)
            nodes[str(node_id)]={
                **common,
                'role':'DECL',
                'seat':dseat,
                'card':card_text(eng,r),
                'equivalent_preserving_actions':alternatives,
                'next_id':child_id,
            }
            continue

        stats['defender_nodes'] += 1
        branches=[]
        for r,legal in e.defender_actions(state,seat):
            need=support & legal
            if not need:
                continue
            child=base.select_def_child(e,state,support,seat,r,legal)
            if child is None:
                continue
            ns,cm=child
            child_id=register(ns,cm,depth+1)
            stats['defender_branches'] += 1
            branches.append({
                'card':card_text(eng,r),
                'compatible_mass':str(e.model.weight(need)),
                'compatible_bits':need.bit_count(),
                'next_id':child_id,
            })
        nodes[str(node_id)]={
            **common,
            'role':'DEF',
            'seat':seat,
            'branches':branches,
        }

    return {'root_id':root_id,'nodes':nodes},stats


def main():
    ap=argparse.ArgumentParser()
    ap.add_argument('--runtime-root',required=True)
    ap.add_argument('--north',required=True)
    ap.add_argument('--south',required=True)
    ap.add_argument('--target',type=int,required=True)
    ap.add_argument('--max-nodes',type=int,default=5000)
    ap.add_argument('--max-depth',type=int,default=10)
    a=ap.parse_args()

    sys.path.insert(0,str(Path(a.runtime_root)/'runtime'))
    import integrated_engine as eng

    e=eng.Engine2(a.north,a.south,a.target)
    solved=e.solve(include_policy=False)
    root=e.initial(); fr=e.frontier(root)
    best=max(fr,key=lambda m:(e.model.weight(m),m))
    seat,rank,after_lead,lead_mask=base.select_root(eng,e,root,best)
    graph,stats=build_policy_graph(
        eng,e,after_lead,lead_mask,
        max_nodes=a.max_nodes,
        max_depth=a.max_depth,
    )
    out={
        'schema':'MANIEMENTS_V5_DICTIONARY_V3_POLICY_GRAPH_V2',
        'case':{'north':a.north,'south':a.south,'target':a.target},
        'probability_fraction':solved['probability_fraction'],
        'root_lead':f'{seat}:{rank}',
        'best_mask_bits':best.bit_count(),
        'policy_graph_stats':stats,
        'policy_graph_after_lead':graph,
    }
    print(json.dumps(out,ensure_ascii=False,indent=2,sort_keys=True))


if __name__=='__main__':
    main()

#!/usr/bin/env python3
from __future__ import annotations
import argparse, json, sys
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


def build_policy_tree(eng, e, s, mask, max_nodes=1600, max_depth=36):
    stats={
        'nodes':0,
        'declarer_nodes':0,
        'defender_nodes':0,
        'defender_branches':0,
        'terminal_nodes':0,
        'truncated_nodes':0,
        'max_depth_seen':0,
    }

    def rec(state, support, depth):
        stats['max_depth_seen']=max(stats['max_depth_seen'], depth)
        if stats['nodes'] >= max_nodes:
            stats['truncated_nodes'] += 1
            return {'truncated':'NODE_BUDGET','depth':depth}
        stats['nodes'] += 1

        term=base.terminal_code(e,state)
        if term:
            stats['terminal_nodes'] += 1
            return {
                'role':'TERMINAL',
                'terminal':term,
                'won':state.won,
                'support_mass':str(e.model.weight(support)),
                'support_bits':support.bit_count(),
            }
        if depth >= max_depth:
            stats['truncated_nodes'] += 1
            return {
                'truncated':'DEPTH_LIMIT',
                'depth':depth,
                'support_mass':str(e.model.weight(support)),
                'support_bits':support.bit_count(),
            }

        seat=e.order(state.leader)[state.pos]
        if seat in eng.DECL:
            stats['declarer_nodes'] += 1
            dseat,cands=declarer_candidates(eng,e,state,support)
            if not cands:
                return {'role':'DECL','seat':seat,'error':'no declarer witness'}
            r,ns,cm=cands[0]
            alternatives=[]
            seen=set()
            for ar,_,acm in cands:
                txt=card_text(eng,ar)
                if txt in seen:
                    continue
                seen.add(txt)
                alternatives.append({
                    'card':txt,
                    'support_mass':str(e.model.weight(acm)),
                    'support_bits':acm.bit_count(),
                })
            return {
                'role':'DECL',
                'seat':dseat,
                'card':card_text(eng,r),
                'support_mass':str(e.model.weight(support)),
                'support_bits':support.bit_count(),
                'equivalent_preserving_actions':alternatives,
                'next':rec(ns,cm,depth+1),
            }

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
            stats['defender_branches'] += 1
            branches.append({
                'card':card_text(eng,r),
                'compatible_mass':str(e.model.weight(need)),
                'compatible_bits':need.bit_count(),
                'next':rec(ns,cm,depth+1),
            })
        return {
            'role':'DEF',
            'seat':seat,
            'support_mass':str(e.model.weight(support)),
            'support_bits':support.bit_count(),
            'branches':branches,
        }

    tree=rec(s,mask,0)
    return tree,stats


def main():
    ap=argparse.ArgumentParser()
    ap.add_argument('--runtime-root',required=True)
    ap.add_argument('--north',required=True)
    ap.add_argument('--south',required=True)
    ap.add_argument('--target',type=int,required=True)
    ap.add_argument('--max-nodes',type=int,default=1600)
    ap.add_argument('--max-depth',type=int,default=36)
    a=ap.parse_args()

    sys.path.insert(0,str(Path(a.runtime_root)/'runtime'))
    import integrated_engine as eng

    e=eng.Engine2(a.north,a.south,a.target)
    solved=e.solve(include_policy=False)
    root=e.initial(); fr=e.frontier(root)
    best=max(fr,key=lambda m:(e.model.weight(m),m))
    seat,rank,after_lead,lead_mask=base.select_root(eng,e,root,best)
    tree,stats=build_policy_tree(
        eng,e,after_lead,lead_mask,
        max_nodes=a.max_nodes,
        max_depth=a.max_depth,
    )
    out={
        'schema':'MANIEMENTS_V5_DICTIONARY_V3_POLICY_TREE_V1',
        'case':{'north':a.north,'south':a.south,'target':a.target},
        'probability_fraction':solved['probability_fraction'],
        'root_lead':f'{seat}:{rank}',
        'best_mask_bits':best.bit_count(),
        'policy_tree_stats':stats,
        'policy_tree_after_lead':tree,
    }
    print(json.dumps(out,ensure_ascii=False,indent=2,sort_keys=True))


if __name__=='__main__':
    main()

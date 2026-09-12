#!/usr/bin/env python3
from __future__ import annotations
from fractions import Fraction


def _root_action_probabilities(eng, e, root):
    rows=[]
    for seat,hand in (('N',root.north),('S',root.south)):
        for r in eng.ranks(hand):
            lead=eng.PublicState(root.north,root.south,root.west_seen,root.east_seen,
                                 root.west_void,root.east_void,seat,0,tuple(),root.won)
            ns=e.decl_play(lead,seat,r)
            fr=e.frontier(ns)
            if not fr:
                continue
            best=max(fr,key=lambda m:(e.model.weight(m),m))
            rows.append((f'{seat}:{eng.I2R[r]}',e.model.weight(best)))
    return rows


def _split_signature(e, i):
    a=e.model.world_w[i].bit_count()
    b=e.model.world_e[i].bit_count()
    return tuple(sorted((a,b),reverse=True))


def _distribution_only_winning_splits(e, best_mask):
    """Return unordered split signatures iff mask membership depends only on split."""
    groups={}
    for i in range(e.model.n):
        sig=_split_signature(e,i)
        g=groups.setdefault(sig,[0,0])
        g[0]+=1
        if (best_mask>>i)&1:
            g[1]+=1
    for total,winning in groups.values():
        if winning not in (0,total):
            return None, set(groups)
    wins={sig for sig,(total,winning) in groups.items() if winning==total}
    return wins,set(groups)


def _split_fr(sig):
    return f'{sig[0]}–{sig[1]}'


def _join_fr(items):
    items=list(items)
    if not items:
        return ''
    if len(items)==1:
        return items[0]
    if len(items)==2:
        return items[0]+' ou '+items[1]
    return ', '.join(items[:-1])+' ou '+items[-1]


def semantic_success_explanation(eng,e,best_mask,probability,north,south,target):
    """Produce a bridge-first explanation when exact success is distribution-only.

    This deliberately refuses to simplify if honor placement matters inside a given
    split. The exact policy program remains the authority in those cases.
    """
    win_splits,all_splits=_distribution_only_winning_splits(e,best_mask)
    if win_splits is None:
        return None

    long_len=max(len(north.replace('-','')),len(south.replace('-','')))
    # Pure length winners: after exhausting the longest defender holding, at least
    # target cards remain in our long hand. This is independent of honor location.
    length_splits={sig for sig in all_splits if long_len-max(sig)>=target}
    if win_splits != length_splits or not win_splits:
        return None

    root=e.initial()
    root_probs=_root_action_probabilities(eng,e,root)
    p=Fraction(probability)
    first_move_irrelevant=bool(root_probs) and all(fr==p for _,fr in root_probs)

    ordered=sorted(win_splits,key=lambda x:(max(x),min(x)))
    split_text=_join_fr(_split_fr(s) for s in ordered)
    if target==1:
        summary=f'On peut faire une levée si les cartes adverses sont réparties {split_text}.'
    else:
        summary=f'On peut faire {target} levées si les cartes adverses sont réparties {split_text}.'
    if first_move_irrelevant:
        summary += ' Quel que soit le maniement adopté.'

    return {
        'semantic_kind':'LENGTH_DISTRIBUTION_ONLY',
        'summary_fr':summary,
        'success_condition_fr':f'Répartition adverse {split_text}.',
        'winning_splits':[_split_fr(s) for s in ordered],
        'first_move_irrelevant':first_move_irrelevant,
        'root_action_count':len(root_probs),
    }

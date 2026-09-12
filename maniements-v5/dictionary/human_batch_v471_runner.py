#!/usr/bin/env python3
from __future__ import annotations

from collections import defaultdict
import human_batch_v47 as v47

b=v47.b
v46=v47.v46


def branch_groups(n):
    groups=defaultdict(list)
    low_owner={}
    for cards,ch in n.branches or []:
        acts=v47.first_decl_actions(ch)
        if len(acts)!=1:
            continue
        act=next(iter(acts))
        for c in v47.flatten(cards):
            if c not in groups[act]:groups[act].append(c)
            if c in '765432':low_owner[c]=act
    # Collapse low cards to generic "petite" only when every low-card branch
    # genuinely leads to the same semantic declarer action.
    if low_owner and len(set(low_owner.values()))==1:
        owner=next(iter(low_owner.values()))
        for act in list(groups):
            groups[act]=[c for c in groups[act] if c not in '765432']
        groups[owner].append('x')
    return groups


def condition_fr(cards):
    cats=[]
    for c in cards:
        if c not in cats:cats.append(c)
    if cats==['-']:return "si l’adversaire défausse"
    names=[v47.fr_card(c) for c in cats]
    if len(names)==1:return "si l’adversaire fournit "+names[0]
    return "si l’adversaire fournit "+', '.join(names[:-1])+' ou '+names[-1]


def action_fr(action,cards):
    _,rank=action
    concrete=[c for c in cards if c not in ('x','-')]
    if rank=='x':return 'jouer petit'
    if rank=='-':return 'ne plus fournir dans la couleur'
    # "Couvrir" only when the defence has actually played a significant card.
    high=[c for c in concrete if c in 'AKQJT']
    if high and all(b.RANK_VALUE.get(rank,0)>b.RANK_VALUE.get(c,0) for c in high):
        return 'couvrir avec '+b.fr_article(rank)
    if rank in ('T','9','8'):
        return 'passer '+b.fr_article(rank)
    if rank=='A':return 'jouer l’As'
    if rank=='K':return 'jouer le Roi'
    if rank=='Q':return 'jouer la Dame'
    if rank=='J':return 'jouer le Valet'
    return 'jouer '+b.fr_article(rank)


def first_defender_map_human(eng,e,row):
    s=row['state']; mask=row['mask']; dseat=e.order(s.leader)[s.pos]; rows=[]
    for r,legal in e.defender_actions(s,dseat):
        need=mask & legal
        if not need:continue
        ns=e.close(e.def_play(s,dseat,r))
        term=e.terminal(ns)
        dec=None
        if term is None:
            cands=v46.feasible_actions(eng,e,ns,need)
            if cands:
                z=v46.choose_human_action(eng,e,ns,need,cands)
                dec=(z[0],'-' if not z[1] else eng.I2R[z[1]])
        rows.append({'defender':dseat,'def_card':'-' if not r else eng.I2R[r],'mass':e.model.weight(need),'next':dec})
    return rows


def choose_root(eng,e,best_mask):
    root=e.initial(); cands=v46.feasible_actions(eng,e,root,best_mask)
    seat,r,ns,support=v46.choose_human_action(eng,e,root,best_mask,cands)
    row={'seat':seat,'rank':eng.I2R[r],'mask':support,'prob':e.model.weight(support),'state':ns}
    phrase,_=b.root_phrase(row,first_defender_map_human(eng,e,row))
    return row,phrase

v47.branch_groups=branch_groups
v47.condition_fr=condition_fr
v47.action_fr=action_fr
v47.choose_root=choose_root

if __name__=='__main__':
    v47.main()

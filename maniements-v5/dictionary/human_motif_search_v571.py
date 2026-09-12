#!/usr/bin/env python3
from __future__ import annotations

import human_motif_search_v57 as v


def strategy_action(eng,e,s,cash,feeder,target,targets):
    if s.pos==0:
        for c in cash:
            for seat in ('N','S'):
                if v.has(eng,s,seat,c):return (seat,c)
        t=v.next_target(eng,s,target,targets)
        if t is not None and v.hand_mask(s,feeder):
            return (feeder,v.lowest(eng,v.hand_mask(s,feeder)))
        # Once the finesse sequence is exhausted, finish by cashing the highest
        # remaining partnership card. This matters, e.g. after three successful
        # passes toward 9-10-J when the Ace is still a fourth trick.
        opts=[]
        for seat in ('N','S'):
            hand=v.hand_mask(s,seat)
            if hand:
                c=v.highest(eng,hand);opts.append((v.RVAL[c],seat,c))
        if opts:
            _,seat,c=max(opts);return (seat,c)
        return None

    seat=e.order(s.leader)[s.pos]
    if seat not in eng.DECL:return None
    active=v.next_target(eng,s,target,targets)
    # A finesse response exists only while a target card from the sequence remains.
    if seat==target and s.leader==feeder and active is not None:
        prev=None
        for q,r in reversed(s.trick):
            if q not in eng.DECL:
                prev='-' if not r else eng.I2R[r];break
        if prev not in (None,'-') and v.RVAL[prev]>v.RVAL[active]:
            w=v.cheapest_winner(eng,v.hand_mask(s,target),prev)
            if w:return (target,w)
        return (target,active)
    # Cash/final-master tricks: partner unloads its cheapest card.
    return (seat,v.lowest(eng,v.hand_mask(s,seat)))


v.strategy_action=strategy_action

if __name__=='__main__':
    v.main()

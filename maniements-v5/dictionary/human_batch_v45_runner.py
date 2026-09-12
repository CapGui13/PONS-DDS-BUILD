#!/usr/bin/env python3
from __future__ import annotations

import human_batch_v45 as v45


def _flatten_cards(value):
    if isinstance(value, (tuple, list)):
        out = []
        for item in value:
            out.extend(_flatten_cards(item))
        return out
    return [value]


def card_condition(cards):
    cards = _flatten_cards(cards)
    cards = list(dict.fromkeys(cards))
    if cards == ['-']:
        return "si l’adversaire défausse"
    names = [v45.b.fr_article(c) for c in cards]
    if len(names) == 1:
        return f"si l’adversaire fournit {names[0]}"
    return "si l’adversaire fournit " + ", ".join(names[:-1]) + " ou " + names[-1]


def feasible_actions(eng, e, s, need):
    """Keep an action when *one of its frontier masks* covers the required mask.

    V4.5 originally kept only the maximum-weight frontier for each action. Frontier
    masks can be incomparable, so that discarded a different mask which preserved
    the exact target and could incorrectly leave a public state with no feasible
    declarer action.
    """
    acts = []
    if s.pos == 0:
        pools = tuple((seat, hand) for seat, hand in (('N', s.north), ('S', s.south)) if hand)
    else:
        seat = e.order(s.leader)[s.pos]
        if seat not in eng.DECL:
            return []
        pools = ((seat, s.north if seat == 'N' else s.south),)

    for seat, hand in pools:
        ranks = eng.ranks(hand) if hand else ((eng.VOID,) if s.pos else tuple())
        for r in ranks:
            if s.pos == 0:
                lead = eng.PublicState(s.north, s.south, s.west_seen, s.east_seen,
                                       s.west_void, s.east_void, seat, 0, tuple(), s.won)
                ns = e.close(e.decl_play(lead, seat, r))
            else:
                ns = e.close(e.decl_play(s, seat, r))
            frontier = e.frontier(ns)
            covering = [cm for cm in frontier if not need or (need | cm) == cm]
            if not covering:
                continue
            support = max(covering, key=lambda cm: (e.model.weight(cm), cm))
            acts.append((seat, r, ns, support))
    return acts


v45.card_condition = card_condition
v45.feasible_actions = feasible_actions

if __name__ == '__main__':
    v45.main()

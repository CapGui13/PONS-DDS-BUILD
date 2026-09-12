#!/usr/bin/env python3
from __future__ import annotations

import argparse
from functools import lru_cache
from fractions import Fraction
from pathlib import Path
import sys


def evaluate(eng, north, south, target, strategy):
    e = eng.Engine2(north, south, target)

    @lru_cache(maxsize=None)
    def F(s):
        term = e.terminal(s)
        if term is not None:
            return term[0]

        if s.pos == 0:
            seat, card = strategy(e, s)
            r = 0 if card == '-' else eng.R2I[card]
            lead = eng.PublicState(s.north, s.south, s.west_seen, s.east_seen,
                                   s.west_void, s.east_void, seat, 0, tuple(), s.won)
            return F(e.close(e.decl_play(lead, seat, r)))

        seat = e.order(s.leader)[s.pos]
        if seat in eng.DECL:
            act = strategy(e, s)
            if act is None or act[0] != seat:
                return 0
            r = 0 if act[1] == '-' else eng.R2I[act[1]]
            return F(e.close(e.decl_play(s, seat, r)))

        belief = e.belief(s)
        successful = belief
        for r, legal in e.defender_actions(s, seat):
            ns = e.close(e.def_play(s, seat, r))
            branch = F(ns)
            successful &= ((belief & ~legal) | branch)
        return successful

    mask = F(e.initial())
    return e, e.model.weight(mask), mask


def two_probe_strategy(eng, s):
    used = 7 - (s.north.bit_count() + s.south.bit_count())
    if s.pos == 0:
        trick = used // 2 + 1
        if trick == 1:
            return ('S', 'A')
        if trick == 2:
            return ('S', 'K')
        if trick == 3:
            j_seen = (s.west_seen | s.east_seen) & (1 << eng.R2I['J'])
            return ('S', 'Q') if j_seen else ('N', 'T')
        if trick == 4:
            return ('S', 'Q') if s.south & (1 << eng.R2I['Q']) else ('S', '7')

    seat = eng.Engine2.order(s.leader)[s.pos]
    if seat == 'N':
        if not s.north:
            return ('N', '-')
        return ('N', eng.I2R[min(eng.ranks(s.north))])
    if seat == 'S':
        cur_e = next((r for q, r in s.trick if q == 'E'), None)
        if cur_e == eng.R2I['J'] and s.south & (1 << eng.R2I['Q']):
            return ('S', 'Q')
        if s.south & (1 << eng.R2I['7']):
            return ('S', '7')
        return ('S', eng.I2R[max(eng.ranks(s.south))])
    return None


def progressive_strategy(eng, s):
    # Human line: lead 8, then 9, then 10 from T98 toward AKQ7.
    # Normally play Q, then K, then A. If the fourth-hand defender has already
    # shown out and J has not appeared, duck with 7 to finesse J in second hand.
    if s.pos == 0:
        if s.north:
            return ('N', eng.I2R[min(eng.ranks(s.north))])
        return ('S', eng.I2R[max(eng.ranks(s.south))])

    seat = eng.Engine2.order(s.leader)[s.pos]
    if seat == 'N':
        return ('N', eng.I2R[min(eng.ranks(s.north))]) if s.north else ('N', '-')
    if seat != 'S':
        return None

    cur_e = next((r for q, r in s.trick if q == 'E'), None)
    j = eng.R2I['J']
    j_seen = bool((s.west_seen | s.east_seen) & (1 << j))

    if cur_e == j:
        for c in ('Q', 'K', 'A'):
            if s.south & (1 << eng.R2I[c]):
                return ('S', c)

    if s.west_void and not j_seen and s.south & (1 << eng.R2I['7']):
        return ('S', '7')

    if cur_e == 0 and not j_seen and s.south & (1 << eng.R2I['7']):
        # This branch cannot add a winning layout for four tricks, but keep the
        # strategy public and deterministic.
        return ('S', '7')

    for c in ('Q', 'K', 'A'):
        if s.south & (1 << eng.R2I[c]):
            return ('S', c)
    return ('S', '7') if s.south & (1 << eng.R2I['7']) else ('S', '-')


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument('--runtime-root', required=True)
    a = ap.parse_args()
    sys.path.insert(0, str(Path(a.runtime_root) / 'runtime'))
    import integrated_engine as eng

    e = eng.Engine2('T98', 'AKQ7', 4)
    solved = e.solve(include_policy=False)
    optimum = Fraction(solved['probability_fraction'])

    _, probe_p, _ = evaluate(eng, 'T98', 'AKQ7', 4, two_probe_strategy)
    _, human_p, human_mask = evaluate(eng, 'T98', 'AKQ7', 4, progressive_strategy)

    assert optimum == Fraction(1961, 3220), optimum
    assert probe_p == Fraction(83, 140), probe_p
    assert human_p == optimum, (human_p, optimum)
    assert human_mask.bit_count() == 38

    print('X98 / ARD7 -> 4 levées')
    print('optimum exact:', optimum, float(optimum))
    print('deux coups de sonde puis impasse:', probe_p, float(probe_p))
    print('ligne humaine progressive:', human_p, float(human_p))
    print('status: HUMAN_TREE_EXACT')


if __name__ == '__main__':
    main()

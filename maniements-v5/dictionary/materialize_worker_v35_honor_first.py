#!/usr/bin/env python3
from __future__ import annotations

# Thin policy layer over the qualified V3.4 honor-first worker.
# In bridge, A/K/Q/J/T are treated as honors for production priority.
import materialize_worker_v34_honor_first as v34

v34.PRIORITY_MODE = 'HONOR_FIRST_X_FAMILY_V2_AKQJT'
v34.MAJOR = 'AKQJT'
v34.INTERMEDIATE = '98'


def family_priority(row):
    n = row['north']; s = row['south']
    hn = sum(c in v34.MAJOR for c in n)
    hs = sum(c in v34.MAJOR for c in s)
    h = hn + hs
    one_hand_two = int(max(hn, hs) >= 2)
    split = int(hn > 0 and hs > 0)

    # First produce useful technical families: 2-4 honors owned.
    # One-honor and all-five-honor families follow, then explicit 9/8 cases,
    # and only then holdings made solely of low cards.
    if h in (2, 3, 4):
        tier = 7
    elif h == 1:
        tier = 6
    elif h == 5:
        tier = 5
    elif any(c in '98' for c in n + s):
        tier = 3
    else:
        tier = 1

    inter = sum(c in '98' for c in n + s)
    xcount = sum(c in v34.LOW for c in n + s)
    total = len(n) + len(s)
    ordinary = int(5 <= total <= 8)
    # Higher tuple sorts first in V3.4.
    return (tier, one_hand_two, split, h, inter, ordinary, xcount, -abs(len(n)-len(s)))


v34.family_priority = family_priority


def main():
    return v34.main()


if __name__ == '__main__':
    main()

#!/usr/bin/env python3
from __future__ import annotations

import argparse
import json
from pathlib import Path

STRATEGIC = "AKQJT98"
HONORS = set("AKQJT")
LOW = "234567"

# First practical expansion: the ordinary eight-card fits missing from P1.
SPLITS = [(5, 3), (4, 4)]

RANK = {c: i for i, c in enumerate("23456789TJQKA", start=2)}


def hand_pattern(cards, low_count):
    cards = sorted(cards, key=lambda c: RANK[c], reverse=True)
    return "".join(cards) + "x" * low_count


def norm_pair(a, b):
    # Human display orientation is irrelevant to the mathematical family.
    return min((a, b), (b, a))


def split_score(a, b):
    z = tuple(sorted((a, b), reverse=True))
    return {(5, 3): 4, (4, 4): 3}.get(z, 0)


def honor_score(h):
    # Classical suit-combination problems with 2–3 owned honors are more useful
    # than the mostly-easy/all-control 4-honor families.
    return {3: 4, 2: 3, 4: 2}.get(h, 0)


def family_priority(npat, spat):
    a, b = len(npat), len(spat)
    owned = npat.replace("x", "") + spat.replace("x", "")
    hn = sum(c in HONORS for c in npat)
    hs = sum(c in HONORS for c in spat)
    h = hn + hs
    inter = sum(c in "98" for c in owned)
    xcount = npat.count("x") + spat.count("x")
    one_hand_two = int(max(hn, hs) >= 2)
    honors_split = int(hn > 0 and hs > 0)
    # Higher tuple sorts first.
    return (
        split_score(a, b),
        honor_score(h),
        one_hand_two,
        honors_split,
        -inter,     # generic honor families before 9/8 refinements
        xcount,
        -abs(a - b),
        npat,
        spat,
    )


def enumerate_families():
    out = {}
    # 0 absent, 1 hand A, 2 hand B for each strategic rank.
    total = 3 ** len(STRATEGIC)
    for code in range(total):
        z = code
        na, sa = [], []
        for c in STRATEGIC:
            d = z % 3
            z //= 3
            if d == 1:
                na.append(c)
            elif d == 2:
                sa.append(c)
        h = sum(c in HONORS for c in na + sa)
        if h not in (2, 3, 4):
            continue
        for la, lb in SPLITS:
            orientations = [(la, lb)] if la == lb else [(la, lb), (lb, la)]
            for nlen, slen in orientations:
                nl = nlen - len(na)
                sl = slen - len(sa)
                if nl < 0 or sl < 0 or nl + sl > len(LOW):
                    continue
                n = hand_pattern(na, nl)
                s = hand_pattern(sa, sl)
                n, s = norm_pair(n, s)
                key = n + "/" + s
                out[key] = {"north_pattern": n, "south_pattern": s}
    rows = list(out.values())
    rows.sort(key=lambda r: family_priority(r["north_pattern"], r["south_pattern"]), reverse=True)
    for i, r in enumerate(rows, start=1):
        r["family_id"] = f"F{i:04d}"
        r["priority_rank"] = i
        r["priority"] = list(family_priority(r["north_pattern"], r["south_pattern"]))
    return rows


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--output", required=True)
    ap.add_argument("--limit", type=int, default=800)
    a = ap.parse_args()
    rows = enumerate_families()

    # Force a few regression/user-facing examples into the selected set.
    required = {
        norm_pair("AKT9x", "xxx"),
        norm_pair("AK98", "JT2"),
    }
    selected = rows[: a.limit]
    have = {(r["north_pattern"], r["south_pattern"]) for r in selected}
    for r in rows:
        pair = (r["north_pattern"], r["south_pattern"])
        if pair in required and pair not in have:
            selected.append(r)
            have.add(pair)

    doc = {
        "schema": "MANIEMENTS_V5_PRACTICAL_FAMILY_PLAN_V2",
        "scope": "8-card fits first: 5-3 then 4-4; 2-3 honors before 4; generic before 9/8",
        "strategic_ranks": STRATEGIC,
        "low_cards": LOW,
        "total_families_available": len(rows),
        "selected_family_count": len(selected),
        "families": selected,
    }
    p = Path(a.output)
    p.parent.mkdir(parents=True, exist_ok=True)
    p.write_text(json.dumps(doc, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(json.dumps({k: doc[k] for k in ("schema","total_families_available","selected_family_count")}, ensure_ascii=False))


if __name__ == "__main__":
    main()

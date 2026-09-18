#!/usr/bin/env python3
from __future__ import annotations

import argparse
import json
import sys
import time
from collections import Counter
from fractions import Fraction
from pathlib import Path

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))

import human_motif_v54 as v54
import human_prefix_exact_v511 as v511
import human_prefix_residual_v515 as v515
import human_qualification_v50 as v50

FROZEN_SHA256 = "a0b580531f3c9e8bb00710b9c3e1c183b27cbfe9231c9d584e29a374ba88835d"


def novel_profiles(eng):
    rows = []
    for cid, north, south in v50.HOLDINGS:
        display = [v50.disp(north), v50.disp(south)]
        for target in range(1, max(len(north), len(south)) + 1):
            e = eng.Engine2(north, south, target)
            opt = Fraction(e.solve(include_policy=False)["probability_fraction"])
            if opt in (0, 1):
                continue
            rows.append({
                "id": cid,
                "north": north,
                "south": south,
                "display": display,
                "target": target,
                "fraction": str(opt),
            })
    return rows


def profile_key(row):
    return f"{row['id']}::T{int(row['target'])}"


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--runtime-root", required=True)
    ap.add_argument("--out-dir", required=True)
    ap.add_argument("--phase", choices=("prefix", "residual"), required=True)
    ap.add_argument("--shard-index", type=int, required=True)
    ap.add_argument("--shard-count", type=int, required=True)
    args = ap.parse_args()

    if args.shard_count < 1 or not 0 <= args.shard_index < args.shard_count:
        raise SystemExit("invalid shard")

    eng = v54.load_engine(args.runtime_root)
    profiles = novel_profiles(eng)
    selected = [
        (i, c) for i, c in enumerate(profiles)
        if i % args.shard_count == args.shard_index
    ]

    out_rows = []
    counts = Counter()
    t0 = time.monotonic()

    for global_index, c in selected:
        p0 = time.monotonic()
        if args.phase == "prefix":
            r = v511.analyze(eng, c)
            counts["profiles"] += 1
            counts["found"] += int(r["found"])
            event = {
                "phase": args.phase,
                "shard": args.shard_index,
                "global_index": global_index,
                "case": c["id"],
                "target": c["target"],
                "found": r["found"],
                "prefix_rounds": (r.get("best") or {}).get("prefix_rounds"),
                "sec": round(time.monotonic() - p0, 3),
            }
        else:
            r = v515.analyze(eng, c, 0)
            counts["profiles"] += 1
            counts["found_prefix"] += int(r["found_prefix"])
            counts["compact"] += int(r["bridge_compact_exact"])
            event = {
                "phase": args.phase,
                "shard": args.shard_index,
                "global_index": global_index,
                "case": c["id"],
                "target": c["target"],
                "found_prefix": r["found_prefix"],
                "compact": r["bridge_compact_exact"],
                "lines": len((r.get("best") or {}).get("full_lines") or []),
                "sec": round(time.monotonic() - p0, 3),
            }

        r["global_index"] = global_index
        r["profile_key"] = profile_key(c)
        out_rows.append(r)
        print(json.dumps(event, ensure_ascii=False), flush=True)

    summary = {
        "schema": "MANIEMENTS_V5_HUMAN_V517_SHARDED_V1",
        "phase": args.phase,
        "shard_index": args.shard_index,
        "shard_count": args.shard_count,
        "total_nontrivial_profiles": len(profiles),
        "selected_profiles": len(selected),
        **dict(counts),
        "elapsed_seconds": round(time.monotonic() - t0, 3),
        "runtime_frozen_sha256": FROZEN_SHA256,
    }

    od = Path(args.out_dir)
    od.mkdir(parents=True, exist_ok=True)
    tag = f"{args.phase.upper()}_SHARD_{args.shard_index:02d}"
    payload = {"summary": summary, "profiles": out_rows}
    (od / f"HUMAN_V517_{tag}.json").write_text(
        json.dumps(payload, ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
    )
    (od / f"SUMMARY_{tag}.txt").write_text(
        "\n".join(f"{k}={v}" for k, v in summary.items()) + "\n",
        encoding="utf-8",
    )
    print(json.dumps(summary, ensure_ascii=False), flush=True)


if __name__ == "__main__":
    main()

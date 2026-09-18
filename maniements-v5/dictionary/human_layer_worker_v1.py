#!/usr/bin/env python3
from __future__ import annotations

import argparse
import datetime
import json
import signal
import sys
import time
from collections import defaultdict
from fractions import Fraction
from pathlib import Path

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))

import human_motif_v54 as v54
import human_prefix_residual_v515 as v515
import human_qualification_v50 as v50

SCHEMA = "MANIEMENTS_V5_HUMAN_LAYER_V1_ENTRY"
STATE_SCHEMA = "MANIEMENTS_V5_HUMAN_LAYER_V1_STATE"
ALGO = "V515_PREFIX_RESIDUAL_ON_DICTIONARY_V1"
FROZEN_SHA256 = "a0b580531f3c9e8bb00710b9c3e1c183b27cbfe9231c9d584e29a374ba88835d"
HONORS = "AKQJT"
LOW = "234567"


class TargetTimeout(Exception):
    pass


def alarm_handler(signum, frame):
    raise TargetTimeout()


def utcnow():
    return datetime.datetime.now(datetime.timezone.utc).replace(microsecond=0).isoformat()


def iter_jsonl(root: Path, subdir: str, prefix: str):
    d = root / subdir
    if not d.exists():
        return
    for p in sorted(d.glob(prefix + "*.jsonl")):
        with p.open(encoding="utf-8") as f:
            for line in f:
                if line.strip():
                    yield json.loads(line)


def latest_exact_rows(source: Path):
    rows = {}
    for r in iter_jsonl(source, "dictionary/chunks", "chunk_"):
        rows[(int(r["state_id"]), int(r["target"]))] = r
    return rows


def existing_results(root: Path):
    rows = {}
    for r in iter_jsonl(root, "human/chunks", "chunk_"):
        rows[(int(r["state_id"]), int(r["target"]))] = r
    return rows


def existing_deferred(root: Path):
    rows = {}
    for r in iter_jsonl(root, "human/deferred", "deferred_"):
        rows[(int(r["state_id"]), int(r["target"]))] = r
    return rows


def family_priority(north: str, south: str):
    hn = sum(c in HONORS for c in north)
    hs = sum(c in HONORS for c in south)
    h = hn + hs
    one_hand_two = int(max(hn, hs) >= 2)
    split = int(hn > 0 and hs > 0)
    if h in (2, 3, 4):
        tier = 7
    elif h == 1:
        tier = 6
    elif h == 5:
        tier = 5
    elif any(c in "98" for c in north + south):
        tier = 3
    else:
        tier = 1
    inter = sum(c in "98" for c in north + south)
    xcount = sum(c in LOW for c in north + south)
    total = len(north) + len(south)
    ordinary = int(5 <= total <= 8)
    return (tier, one_hand_two, split, h, inter, ordinary, xcount, -abs(len(north) - len(south)))


def eligible_holding(north: str, south: str):
    total = len(north) + len(south)
    h = sum(c in HONORS for c in north + south)
    return 5 <= total <= 8 and 2 <= h <= 4


def is_nontrivial(prob):
    p = Fraction(prob)
    return 0 < p < 1


def display_hand(hand: str):
    return v50.disp(hand)


def compact_result(src, r):
    b = r.get("best") or {}
    if r.get("bridge_compact_exact"):
        status = "COMPACT_EXACT"
    elif r.get("found_prefix"):
        status = "EXACT_PREFIX_NONCOMPACT"
    else:
        status = "NO_EXACT_PREFIX"
    return {
        "schema": SCHEMA,
        "algorithm": ALGO,
        "state_id": int(src["state_id"]),
        "north": src["north"],
        "south": src["south"],
        "target": int(src["target"]),
        "probability_fraction": src["probability_fraction"],
        "policy_sha256": src.get("policy_sha256"),
        "x_family": src.get("x_family"),
        "status": status,
        "found_prefix": bool(r.get("found_prefix")),
        "bridge_compact_exact": bool(r.get("bridge_compact_exact")),
        "source": b.get("source"),
        "prefix_rounds": b.get("prefix_rounds"),
        "full_lines": b.get("full_lines") or [],
        "prefix_lines": b.get("prefix_lines") or [],
        "residual_lines": b.get("residual_lines") or [],
        "residual_states": b.get("residual_states"),
        "candidates": r.get("candidates"),
        "tested": r.get("tested"),
        "elapsed_seconds": r.get("elapsed_seconds"),
        "runtime_frozen_sha256": FROZEN_SHA256,
        "generated_at_utc": utcnow(),
    }


def recompute_state(root: Path, source_rows, worker_id: int, cap: float):
    results = existing_results(root)
    deferred = existing_deferred(root)
    by_state = defaultdict(list)
    for (sid, t), r in source_rows.items():
        if eligible_holding(r["north"], r["south"]) and is_nontrivial(r["probability_fraction"]):
            by_state[sid].append(t)

    processed_holdings = 0
    for sid, targets in by_state.items():
        if all((sid, t) in results or (sid, t) in deferred for t in targets):
            processed_holdings += 1

    counts = defaultdict(int)
    for r in results.values():
        counts["analyzed_targets"] += 1
        if r.get("found_prefix"):
            counts["prefix_targets"] += 1
        if r.get("bridge_compact_exact"):
            counts["compact_targets"] += 1
        if r.get("status") == "EXACT_PREFIX_NONCOMPACT":
            counts["noncompact_targets"] += 1
        if r.get("status") == "NO_EXACT_PREFIX":
            counts["missing_prefix_targets"] += 1

    return {
        "schema": STATE_SCHEMA,
        "algorithm": ALGO,
        "worker_id": worker_id,
        "eligible_holdings": len(by_state),
        "processed_holdings": processed_holdings,
        "deferred_targets": len(deferred),
        **dict(counts),
        "target_cap_seconds": cap,
        "runtime_frozen_sha256": FROZEN_SHA256,
        "updated_at_utc": utcnow(),
    }


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--runtime-root", required=True)
    ap.add_argument("--source-root", required=True)
    ap.add_argument("--state-root", required=True)
    ap.add_argument("--worker-id", type=int, required=True)
    ap.add_argument("--budget-seconds", type=float, default=4800)
    ap.add_argument("--close-reserve-seconds", type=float, default=240)
    ap.add_argument("--target-cap-seconds", type=float, default=720)
    ap.add_argument("--max-new-holdings", type=int, default=10)
    a = ap.parse_args()

    source = Path(a.source_root)
    root = Path(a.state_root)
    (root / "human/chunks").mkdir(parents=True, exist_ok=True)
    (root / "human/deferred").mkdir(parents=True, exist_ok=True)

    eng = v54.load_engine(a.runtime_root)
    source_rows = latest_exact_rows(source)
    done = existing_results(root)
    deferred = existing_deferred(root)

    by_state = defaultdict(list)
    sample = {}
    for (sid, target), r in source_rows.items():
        if not eligible_holding(r["north"], r["south"]):
            continue
        if not is_nontrivial(r["probability_fraction"]):
            continue
        by_state[sid].append((target, r))
        sample[sid] = r

    pending_holdings = []
    for sid, items in by_state.items():
        pending = [(t, r) for t, r in items if (sid, t) not in done and (sid, t) not in deferred]
        if pending:
            pending_holdings.append((sid, pending))
    pending_holdings.sort(
        key=lambda x: (family_priority(sample[x[0]]["north"], sample[x[0]]["south"]), x[0]),
        reverse=True,
    )

    started = time.monotonic()
    deadline = started + a.budget_seconds - a.close_reserve_seconds
    new_rows = []
    new_deferred = []
    new_holdings = 0
    old_handler = signal.signal(signal.SIGALRM, alarm_handler)
    stop = False

    try:
        for sid, items in pending_holdings:
            if stop or new_holdings >= a.max_new_holdings:
                break
            touched = False
            for target, src in sorted(items):
                if time.monotonic() >= deadline - min(a.target_cap_seconds, 120) - 10:
                    stop = True
                    break
                case = {
                    "id": f"D{sid}",
                    "north": src["north"],
                    "south": src["south"],
                    "display": [display_hand(src["north"]), display_hand(src["south"])],
                    "target": int(target),
                }
                t0 = time.monotonic()
                try:
                    signal.setitimer(signal.ITIMER_REAL, a.target_cap_seconds)
                    r = v515.analyze(eng, case, 0)
                    signal.setitimer(signal.ITIMER_REAL, 0)
                    if Fraction(r["fraction"]) != Fraction(src["probability_fraction"]):
                        raise RuntimeError(
                            f"probability mismatch {r['fraction']} != {src['probability_fraction']}"
                        )
                    out = compact_result(src, r)
                    new_rows.append(out)
                    done[(sid, int(target))] = out
                    touched = True
                    print(json.dumps({
                        "state_id": sid,
                        "case": f"{src['north']}/{src['south']}",
                        "target": target,
                        "status": out["status"],
                        "prefix": out["found_prefix"],
                        "compact": out["bridge_compact_exact"],
                        "sec": round(time.monotonic() - t0, 3),
                    }, ensure_ascii=False), flush=True)
                except TargetTimeout:
                    signal.setitimer(signal.ITIMER_REAL, 0)
                    d = {
                        "schema": "MANIEMENTS_V5_HUMAN_LAYER_V1_DEFERRED",
                        "algorithm": ALGO,
                        "state_id": sid,
                        "north": src["north"],
                        "south": src["south"],
                        "target": int(target),
                        "probability_fraction": src["probability_fraction"],
                        "reason": "TARGET_TIMEOUT",
                        "target_cap_seconds": a.target_cap_seconds,
                        "runtime_frozen_sha256": FROZEN_SHA256,
                        "deferred_at_utc": utcnow(),
                    }
                    new_deferred.append(d)
                    deferred[(sid, int(target))] = d
                    touched = True
                    print(json.dumps({
                        "state_id": sid,
                        "case": f"{src['north']}/{src['south']}",
                        "target": target,
                        "status": "TARGET_TIMEOUT",
                        "sec": round(time.monotonic() - t0, 3),
                    }, ensure_ascii=False), flush=True)
            if touched:
                new_holdings += 1
    finally:
        signal.setitimer(signal.ITIMER_REAL, 0)
        signal.signal(signal.SIGALRM, old_handler)

    state_file = root / "human/state.json"
    seq = 0
    if state_file.exists():
        try:
            seq = int(json.loads(state_file.read_text(encoding="utf-8")).get("sequence", 0))
        except Exception:
            seq = 0

    if new_rows:
        p = root / "human/chunks" / f"chunk_{seq:06d}.jsonl"
        with p.open("w", encoding="utf-8") as f:
            for r in new_rows:
                f.write(json.dumps(r, ensure_ascii=False, sort_keys=True, separators=(",", ":")) + "\n")
    if new_deferred:
        p = root / "human/deferred" / f"deferred_{seq:06d}.jsonl"
        with p.open("w", encoding="utf-8") as f:
            for r in new_deferred:
                f.write(json.dumps(r, ensure_ascii=False, sort_keys=True, separators=(",", ":")) + "\n")

    state = recompute_state(root, source_rows, a.worker_id, a.target_cap_seconds)
    state["sequence"] = seq + 1
    state["last_pass"] = {
        "new_holdings": new_holdings,
        "new_results": len(new_rows),
        "new_deferred": len(new_deferred),
        "elapsed_seconds": round(time.monotonic() - started, 3),
        "pending_holdings_before": len(pending_holdings),
    }
    state_file.write_text(json.dumps(state, ensure_ascii=False, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    print(json.dumps(state, ensure_ascii=False, sort_keys=True), flush=True)


if __name__ == "__main__":
    main()

#!/usr/bin/env python3
from __future__ import annotations

import argparse
import datetime
import hashlib
import itertools
import json
import signal
import sys
import time
from fractions import Fraction
from pathlib import Path

LOW = "234567"
RANK = {c: i for i, c in enumerate("23456789TJQKA", start=2)}
FROZEN_SHA256 = "a0b580531f3c9e8bb00710b9c3e1c183b27cbfe9231c9d584e29a374ba88835d"
SCHEMA = "MANIEMENTS_V5_PRACTICAL_FAMILY_EXACT_V2"
STATE_SCHEMA = "MANIEMENTS_V5_PRACTICAL_FAMILY_WORKER_STATE_V2"


class TargetTimeout(Exception):
    pass


def alarm_handler(signum, frame):
    raise TargetTimeout()


def utcnow():
    return datetime.datetime.now(datetime.timezone.utc).replace(microsecond=0).isoformat()


def worker_for(family_id: str, count: int) -> int:
    h = hashlib.sha256(("MANIEMENTS_V5_FAMILY_V2:" + family_id).encode("ascii")).digest()
    return int.from_bytes(h[:8], "big") % count


def parse_pattern(pat: str):
    exact = [c for c in pat if c != "x"]
    return "".join(exact), pat.count("x")


def sort_hand(cards):
    return "".join(sorted(cards, key=lambda c: RANK[c], reverse=True))


def expand_family(npat: str, spat: str):
    ne, nx = parse_pattern(npat)
    se, sx = parse_pattern(spat)
    used = set(ne + se)
    pool = [c for c in LOW if c not in used]
    if nx + sx > len(pool):
        raise RuntimeError("not enough low cards")
    out = []
    for nc in itertools.combinations(pool, nx):
        rem = [c for c in pool if c not in nc]
        for sc in itertools.combinations(rem, sx):
            n = sort_hand(ne + "".join(nc))
            s = sort_hand(se + "".join(sc))
            out.append((n, s))
    return out


def load_state(root: Path, worker_id: int, worker_count: int):
    p = root / "family_v2/state.json"
    if not p.exists():
        return {
            "schema": STATE_SCHEMA,
            "worker_id": worker_id,
            "worker_count": worker_count,
            "completed_family_ids": [],
            "deferred_family_ids": [],
            "updated_at_utc": utcnow(),
            "sequence": 0,
        }
    s = json.loads(p.read_text(encoding="utf-8"))
    if s.get("worker_id") != worker_id or s.get("worker_count") != worker_count:
        raise RuntimeError("worker state mismatch")
    return s


def target_curve(eng, north: str, south: str, cap: float):
    vals = {}
    hashes = {}
    max_t = max(len(north), len(south))
    for t in range(1, max_t + 1):
        signal.setitimer(signal.ITIMER_REAL, cap)
        e = eng.Engine2(north, south, t)
        r = e.solve(include_policy=False)
        signal.setitimer(signal.ITIMER_REAL, 0)
        vals[str(t)] = r["probability_fraction"]
        try:
            hashes[str(t)] = eng.policy_recipe(north, south, t)["policy_sha256"]
        except Exception:
            hashes[str(t)] = None
    return vals, hashes


def summarize_family(variants):
    targets = sorted({t for v in variants for t in v["curve"]}, key=int)
    summary = {}
    for t in targets:
        vals = sorted({v["curve"].get(t) for v in variants if t in v["curve"]})
        summary[t] = {
            "generic": len(vals) == 1,
            "probability_fraction": vals[0] if len(vals) == 1 else None,
            "distinct_probability_count": len(vals),
        }
    return summary


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--runtime-root", required=True)
    ap.add_argument("--plan", required=True)
    ap.add_argument("--state-root", required=True)
    ap.add_argument("--worker-id", type=int, required=True)
    ap.add_argument("--worker-count", type=int, default=20)
    ap.add_argument("--budget-seconds", type=float, default=4800)
    ap.add_argument("--close-reserve-seconds", type=float, default=240)
    ap.add_argument("--target-cap-seconds", type=float, default=180)
    ap.add_argument("--max-new-families", type=int, default=3)
    a = ap.parse_args()

    sys.path.insert(0, str(Path(a.runtime_root) / "runtime"))
    import integrated_engine as eng

    plan = json.loads(Path(a.plan).read_text(encoding="utf-8"))
    root = Path(a.state_root)
    outdir = root / "family_v2/families"
    outdir.mkdir(parents=True, exist_ok=True)
    state = load_state(root, a.worker_id, a.worker_count)
    completed = set(state.get("completed_family_ids") or [])
    deferred = set(state.get("deferred_family_ids") or [])

    mine = [
        f for f in plan["families"]
        if worker_for(f["family_id"], a.worker_count) == a.worker_id
        and f["family_id"] not in completed
        and f["family_id"] not in deferred
    ]
    mine.sort(key=lambda f: int(f["priority_rank"]))

    started = time.monotonic()
    deadline = started + a.budget_seconds - a.close_reserve_seconds
    new_done = 0
    new_def = 0
    old_handler = signal.signal(signal.SIGALRM, alarm_handler)
    try:
        for fam in mine:
            if new_done + new_def >= a.max_new_families:
                break
            if time.monotonic() >= deadline - min(a.target_cap_seconds, 120) - 10:
                break
            fid = fam["family_id"]
            variants = []
            t0 = time.monotonic()
            try:
                for n, s in expand_family(fam["north_pattern"], fam["south_pattern"]):
                    if time.monotonic() >= deadline - min(a.target_cap_seconds, 120) - 10:
                        raise TargetTimeout()
                    curve, hashes = target_curve(eng, n, s, a.target_cap_seconds)
                    variants.append({
                        "north": n,
                        "south": s,
                        "curve": curve,
                        "policy_sha256": hashes,
                    })
                rec = {
                    "schema": SCHEMA,
                    "family_id": fid,
                    "priority_rank": fam["priority_rank"],
                    "north_pattern": fam["north_pattern"],
                    "south_pattern": fam["south_pattern"],
                    "variant_count": len(variants),
                    "variants": variants,
                    "targets": summarize_family(variants),
                    "runtime_frozen_sha256": FROZEN_SHA256,
                    "computed_at_utc": utcnow(),
                    "elapsed_seconds": round(time.monotonic() - t0, 3),
                }
                (outdir / f"{fid}.json").write_text(
                    json.dumps(rec, ensure_ascii=False, separators=(",", ":")) + "\n",
                    encoding="utf-8",
                )
                completed.add(fid)
                new_done += 1
                print(json.dumps({
                    "family": fid,
                    "pattern": fam["north_pattern"] + "/" + fam["south_pattern"],
                    "status": "DONE",
                    "variants": len(variants),
                    "sec": rec["elapsed_seconds"],
                }, ensure_ascii=False), flush=True)
            except TargetTimeout:
                signal.setitimer(signal.ITIMER_REAL, 0)
                deferred.add(fid)
                new_def += 1
                print(json.dumps({
                    "family": fid,
                    "pattern": fam["north_pattern"] + "/" + fam["south_pattern"],
                    "status": "DEFERRED",
                    "computed_variants_before_timeout": len(variants),
                    "sec": round(time.monotonic() - t0, 3),
                }, ensure_ascii=False), flush=True)
    finally:
        signal.setitimer(signal.ITIMER_REAL, 0)
        signal.signal(signal.SIGALRM, old_handler)

    state["completed_family_ids"] = sorted(completed)
    state["deferred_family_ids"] = sorted(deferred)
    state["sequence"] = int(state.get("sequence", 0)) + 1
    state["updated_at_utc"] = utcnow()
    state["last_pass"] = {
        "new_completed_families": new_done,
        "new_deferred_families": new_def,
        "elapsed_seconds": round(time.monotonic() - started, 3),
        "pending_before": len(mine),
    }
    (root / "family_v2/state.json").write_text(
        json.dumps(state, ensure_ascii=False, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )
    print(json.dumps(state["last_pass"], ensure_ascii=False), flush=True)


if __name__ == "__main__":
    main()

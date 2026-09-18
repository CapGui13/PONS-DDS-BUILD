#!/usr/bin/env python3
from __future__ import annotations

import argparse
import datetime
import json
import signal
import sys
import time
from pathlib import Path

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))

# Installs the qualified semantic exact-policy extractor into materialize_worker_v3.
import materialize_worker_v31  # noqa: F401
import materialize_worker_v3 as base

FROZEN_SHA256 = "a0b580531f3c9e8bb00710b9c3e1c183b27cbfe9231c9d584e29a374ba88835d"


class TargetTimeout(Exception):
    pass


def alarm_handler(signum, frame):
    raise TargetTimeout()


def utcnow():
    return datetime.datetime.now(datetime.timezone.utc).replace(microsecond=0).isoformat()


def read_jsonl(paths):
    for p in paths:
        with p.open(encoding="utf-8") as f:
            for line in f:
                if line.strip():
                    yield json.loads(line)


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--runtime-root", required=True)
    ap.add_argument("--state-root", required=True)
    ap.add_argument("--worker-id", type=int, required=True)
    ap.add_argument("--budget-seconds", type=float, default=4800)
    ap.add_argument("--close-reserve-seconds", type=float, default=240)
    ap.add_argument("--target-cap-seconds", type=float, default=600)
    a = ap.parse_args()

    sys.path.insert(0, str(Path(a.runtime_root) / "runtime"))
    import integrated_engine as eng
    import prototype_v3_builtin_policy as bp
    import prototype_v3_policy_compress as pc
    import prototype_v3_compile as cc

    root = Path(a.state_root)
    chunks = sorted((root / "dictionary/chunks").glob("chunk_*.jsonl"))
    deferred_files = sorted((root / "dictionary/deferred").glob("deferred_*.jsonl"))
    done = {}
    for r in read_jsonl(chunks):
        done[(int(r["state_id"]), int(r["target"]))] = r

    deferred = {}
    for r in read_jsonl(deferred_files):
        k = (int(r["state_id"]), int(r["target"]))
        if k not in done:
            deferred[k] = r

    state_path = root / "dictionary/state.json"
    state = json.loads(state_path.read_text(encoding="utf-8"))
    seq = int(state.get("sequence", 0))

    started = time.monotonic()
    deadline = started + a.budget_seconds - a.close_reserve_seconds
    successes = []
    still_timed_out = []
    old_handler = signal.signal(signal.SIGALRM, alarm_handler)

    try:
        for k, r in sorted(deferred.items()):
            if time.monotonic() >= deadline - min(a.target_cap_seconds, 120) - 10:
                break
            t0 = time.monotonic()
            try:
                signal.setitimer(signal.ITIMER_REAL, a.target_cap_seconds)
                comp, states = base.solve_one(
                    eng, bp, pc, cc,
                    r["north"], r["south"], int(r["target"]),
                    r["probability_fraction"], r["policy_sha256"],
                )
                signal.setitimer(signal.ITIMER_REAL, 0)
                out = {
                    "schema": base.ENTRY_SCHEMA,
                    "plan_id": base.PLAN_ID,
                    "worker_id": a.worker_id,
                    "state_id": int(r["state_id"]),
                    "north": r["north"],
                    "south": r["south"],
                    "target": int(r["target"]),
                    "probability_fraction": r["probability_fraction"],
                    "policy_sha256": r["policy_sha256"],
                    "policy_states": states,
                    "extractor": base.EXTRACTOR,
                    "compact": comp,
                    "materialized_at_utc": utcnow(),
                    "priority_mode": r.get("priority_mode", state.get("priority_mode")),
                    "x_family": r.get("x_family"),
                    "retry_of_deferred": True,
                    "retry_target_cap_seconds": a.target_cap_seconds,
                }
                successes.append(out)
                done[k] = out
                print(json.dumps({
                    "state_id": r["state_id"],
                    "target": r["target"],
                    "status": "RECOVERED",
                    "sec": round(time.monotonic() - t0, 3),
                }), flush=True)
            except (base.TargetTimeout, TargetTimeout):
                signal.setitimer(signal.ITIMER_REAL, 0)
                still_timed_out.append(k)
                print(json.dumps({
                    "state_id": r["state_id"],
                    "target": r["target"],
                    "status": "STILL_TIMEOUT",
                    "sec": round(time.monotonic() - t0, 3),
                }), flush=True)
    finally:
        signal.setitimer(signal.ITIMER_REAL, 0)
        signal.signal(signal.SIGALRM, old_handler)

    if successes:
        p = root / "dictionary/chunks" / f"chunk_{seq:06d}.jsonl"
        with p.open("w", encoding="utf-8") as f:
            for r in successes:
                f.write(json.dumps(r, ensure_ascii=False, sort_keys=True, separators=(",", ":")) + "\n")
        seq += 1

    unresolved = [k for k in deferred if k not in done]
    state["sequence"] = seq
    state["materialized_targets"] = len(done)
    state["deferred_targets"] = len(unresolved)
    state["updated_at_utc"] = utcnow()
    state["last_deferred_retry"] = {
        "target_cap_seconds": a.target_cap_seconds,
        "recovered": len(successes),
        "still_unresolved": len(unresolved),
        "elapsed_seconds": round(time.monotonic() - started, 3),
        "runtime_frozen_sha256": FROZEN_SHA256,
    }
    state_path.write_text(json.dumps(state, ensure_ascii=False, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    print(json.dumps(state["last_deferred_retry"], ensure_ascii=False, sort_keys=True), flush=True)


if __name__ == "__main__":
    main()

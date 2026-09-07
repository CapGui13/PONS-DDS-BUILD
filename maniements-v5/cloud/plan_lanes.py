#!/usr/bin/env python3
from __future__ import annotations
import argparse, json, subprocess
from pathlib import Path

LANE_COUNT = 64


def git_show(ref: str, path: str):
    p = subprocess.run(
        ["git", "show", f"{ref}:{path}"],
        stdout=subprocess.PIPE,
        stderr=subprocess.DEVNULL,
        text=True,
        check=False,
    )
    if p.returncode != 0:
        return None
    return p.stdout


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--pool-size", type=int, default=20)
    ap.add_argument("--details", action="store_true")
    a = ap.parse_args()

    if not (1 <= a.pool_size <= LANE_COUNT):
        raise SystemExit("invalid pool size")

    # Priority mode intentionally preserves every exhaustive lane branch but stops
    # allocating runners to them. This lets the targeted exact cache use the free
    # GitHub runner pool without deleting or mutating exhaustive scientific state.
    if Path("maniements-v5/PRIORITY_MODE").exists():
        if a.details:
            print(json.dumps({
                "schema":"MANIEMENTS_V3_GEN_V5_ROLLING_POOL_PLAN_V1",
                "pool_size":a.pool_size,"selected_lanes":[],"eligible_count":0,
                "hard_stall_count":0,"done_count":0,"not_started_count":0,
                "paused_for_priority_mode":True,"lanes":[],
            },sort_keys=True,separators=(",",":")))
        else:
            print("[]")
        return

    eligible = []
    rows = []
    for lane in range(LANE_COUNT):
        pad = f"{lane:02d}"
        ref = f"refs/remotes/origin/maniements-v5-lane-{pad}"
        raw = git_show(ref, "state/progress.json")
        orch_raw = git_show(ref, "state/orchestration.json")
        if raw is None:
            status = "NOT_STARTED"
            pass_no = None
            hard_stall = False
        else:
            d = json.loads(raw)
            status = d.get("status", "UNKNOWN")
            pass_no = d.get("pass_no")
            orch = json.loads(orch_raw) if orch_raw else {}
            hard_stall = bool(orch.get("hard_stall", False))
        runnable = status != "LANE_DONE" and not hard_stall
        if runnable:
            eligible.append(lane)
        rows.append({
            "lane": lane,
            "status": status,
            "pass_no": pass_no,
            "hard_stall": hard_stall,
            "runnable": runnable,
        })

    selected = eligible[: a.pool_size]
    if a.details:
        print(json.dumps({
            "schema": "MANIEMENTS_V3_GEN_V5_ROLLING_POOL_PLAN_V1",
            "pool_size": a.pool_size,
            "selected_lanes": selected,
            "eligible_count": len(eligible),
            "hard_stall_count": sum(1 for r in rows if r["hard_stall"]),
            "done_count": sum(1 for r in rows if r["status"] == "LANE_DONE"),
            "not_started_count": sum(1 for r in rows if r["status"] == "NOT_STARTED"),
            "paused_for_priority_mode": False,
            "lanes": rows,
        }, sort_keys=True, separators=(",", ":")))
    else:
        print(json.dumps(selected, separators=(",", ":")))


if __name__ == "__main__":
    main()

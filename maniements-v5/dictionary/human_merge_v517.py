#!/usr/bin/env python3
from __future__ import annotations

import argparse
import json
from pathlib import Path

FROZEN_SHA256 = "a0b580531f3c9e8bb00710b9c3e1c183b27cbfe9231c9d584e29a374ba88835d"
EXPECTED_PROFILES = 35


def load_phase(root: Path, phase: str):
    files = sorted(root.glob(f"HUMAN_V517_{phase.upper()}_SHARD_*.json"))
    rows = []
    shards = []
    for p in files:
        data = json.loads(p.read_text(encoding="utf-8"))
        s = data["summary"]
        if s.get("runtime_frozen_sha256") != FROZEN_SHA256:
            raise SystemExit(f"runtime SHA mismatch in {p}")
        if s.get("phase") != phase:
            raise SystemExit(f"phase mismatch in {p}")
        shards.append(int(s["shard_index"]))
        rows.extend(data.get("profiles", []))
    rows.sort(key=lambda r: int(r["global_index"]))
    keys = [r["profile_key"] for r in rows]
    if len(keys) != len(set(keys)):
        raise SystemExit(f"duplicate profiles in {phase}")
    if len(rows) != EXPECTED_PROFILES:
        raise SystemExit(f"{phase}: expected {EXPECTED_PROFILES} profiles, got {len(rows)}")
    return files, shards, rows


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--input-dir", required=True)
    ap.add_argument("--out-dir", required=True)
    args = ap.parse_args()

    root = Path(args.input_dir)
    pf, psh, prefix = load_phase(root, "prefix")
    rf, rsh, residual = load_phase(root, "residual")

    pkeys = [r["profile_key"] for r in prefix]
    rkeys = [r["profile_key"] for r in residual]
    if pkeys != rkeys:
        raise SystemExit("prefix/residual profile sets differ")

    prefix_found = [r for r in prefix if r.get("found")]
    residual_prefix = [r for r in residual if r.get("found_prefix")]
    compact = [r for r in residual if r.get("bridge_compact_exact")]

    summary = {
        "schema": "MANIEMENTS_V5_HUMAN_V517_COMPLETE_V1",
        "profiles": EXPECTED_PROFILES,
        "prefix_v511_found": len(prefix_found),
        "prefix_v511_rate_percent": f"{100*len(prefix_found)/EXPECTED_PROFILES:.2f}",
        "v515_found_prefix": len(residual_prefix),
        "v515_found_prefix_rate_percent": f"{100*len(residual_prefix)/EXPECTED_PROFILES:.2f}",
        "v515_compact_exact": len(compact),
        "v515_compact_exact_rate_percent": f"{100*len(compact)/EXPECTED_PROFILES:.2f}",
        "prefix_v511_misses": [r["profile_key"] for r in prefix if not r.get("found")],
        "v515_prefix_misses": [r["profile_key"] for r in residual if not r.get("found_prefix")],
        "v515_compact_misses": [r["profile_key"] for r in residual if not r.get("bridge_compact_exact")],
        "prefix_shards_seen": sorted(set(psh)),
        "residual_shards_seen": sorted(set(rsh)),
        "runtime_frozen_sha256": FROZEN_SHA256,
        "meaning": "V5.11 certifies exact human prefixes; V5.15 certifies exact human prefix plus exact residual compression on all 35 non-trivial novel profiles.",
    }

    od = Path(args.out_dir)
    od.mkdir(parents=True, exist_ok=True)
    payload = {"summary": summary, "prefix_profiles": prefix, "residual_profiles": residual}
    (od / "HUMAN_V517_COMPLETE.json").write_text(
        json.dumps(payload, ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
    )
    (od / "SUMMARY.txt").write_text(
        "\n".join(
            f"{k}={json.dumps(v, ensure_ascii=False) if isinstance(v, list) else v}"
            for k, v in summary.items()
        ) + "\n",
        encoding="utf-8",
    )
    print(json.dumps(summary, ensure_ascii=False), flush=True)


if __name__ == "__main__":
    main()

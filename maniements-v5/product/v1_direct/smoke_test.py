#!/usr/bin/env python3
from pathlib import Path
from server import DirectSolver

HERE=Path(__file__).resolve().parent
s=DirectSolver(HERE/"runtime",HERE/"engine_tools",HERE/"smoke_cache.sqlite")
r=s.query("AKT92","765",use_cache=False)
assert r["schema"]=="MANIEMENTS_V5_DIRECT_QUERY_V1"
assert r["north"]=="AKT92" and r["south"]=="765"
assert len(r["curve"])==5
assert all(x["status"]=="EXACT" for x in r["curve"])
print("GREEN", [(x["target"],x["fraction"],x["strategy_kind"]) for x in r["curve"]])

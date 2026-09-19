#!/usr/bin/env python3
import json, subprocess, sys
from fractions import Fraction
from pathlib import Path

HERE=Path(__file__).resolve().parent
out=HERE/"REPORT_ARX92_765.json"
html=HERE/"REPORT_ARX92_765.html"
subprocess.check_call([
    sys.executable,str(HERE/"comparator_v60.py"),
    "--runtime-root",str(HERE/"runtime"),
    "--tools-root",str(HERE/"engine_tools"),
    "--north","AKT92","--south","765",
    "--output",str(out),"--html",str(html)
])
r=json.loads(out.read_text(encoding="utf-8"))
curve={x["target"]:Fraction(x["fraction"]) for x in r["curve"]}
assert curve[5]==Fraction(507,2300),curve
assert curve[4]==Fraction(103,115),curve
assert curve[3]==Fraction(451,460),curve
assert curve[2]==1,curve
assert [o["target"] for o in r["objectives"]]==[5,4,3],r["objectives"]
for o in r["objectives"]:
    assert o["candidate_count"]>0,o
    assert o["oracle_matched"],o
print("GREEN",[(o["target"],o["oracle_fraction"],o["candidate_count"],o["optimal_candidate_count"]) for o in r["objectives"]])

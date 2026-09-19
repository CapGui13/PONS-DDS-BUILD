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
    if o["target"] in (5,4,3):
        assert o["human_oracle_matched"],o
t4=next(o for o in r["objectives"] if o["target"]==4)
assert t4["candidates"][0]["label"]=="IMPASSE_PROFONDE_ADAPTATIVE",t4["candidates"][:3]
assert t4["candidates"][0]["source"]=="V61",t4["candidates"][0]
assert t4["candidates"][0]["layout_reason"]["mode"]=="CERTIFIED_V61_FAILURE_BREAKDOWN",t4["candidates"][0]["layout_reason"]

t5=next(o for o in r["objectives"] if o["target"]==5)
best5=t5["candidates"][0]
assert best5["label"]=="IMPASSE_REPETEE",best5
assert best5["layout_reason"]["mode"]=="CERTIFIED_V61_CASE_BREAKDOWN",best5["layout_reason"]
assert sum(Fraction(x["fraction"]) for x in best5["layout_reason"]["cases"])==Fraction(best5["fraction"])

probe5=next(x for x in t5["candidates"] if x["label"]=="COUP_DE_SONDE_PUIS_IMPASSE" and x["fraction"]=="52/575")
assert probe5["layout_reason"]["mode"]=="CERTIFIED_V61_CASE_BREAKDOWN",probe5["layout_reason"]
assert sum(Fraction(x["fraction"]) for x in probe5["layout_reason"]["cases"])==Fraction(probe5["fraction"])

print("GREEN",[(o["target"],o["oracle_fraction"],o["candidate_count"],o["optimal_candidate_count"],o["human_oracle_matched"]) for o in r["objectives"]])

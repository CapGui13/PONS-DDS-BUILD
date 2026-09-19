#!/usr/bin/env python3
import argparse,json,sys
from fractions import Fraction
from pathlib import Path

ap=argparse.ArgumentParser()
ap.add_argument('--runtime-root',required=True)
ap.add_argument('--tools-root',required=True)
a=ap.parse_args()
sys.path.insert(0,str(Path(a.runtime_root)/'runtime'))
sys.path.insert(0,a.tools_root)
import integrated_engine as eng
import prototype_v3_inspect as inspect
import human_oracle_v61 as v61

r=v61.recognize(eng,inspect,'AKT92','765',4)
assert r and r['certified'],r
assert Fraction(r['probability_fraction'])==Fraction(103,115),r
assert Fraction(r['failure_fraction'])==Fraction(12,115),r
print(json.dumps(r,ensure_ascii=False,indent=2))
print('GREEN V6.1 certified humanization')

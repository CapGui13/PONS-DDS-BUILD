#!/usr/bin/env python3
from fractions import Fraction
import argparse, sys
from pathlib import Path

ap=argparse.ArgumentParser(); ap.add_argument('--runtime-root',required=True); a=ap.parse_args()
sys.path.insert(0,str(Path(a.runtime_root)/'runtime'))
import integrated_engine as eng

for target in (4,5):
    e=eng.Engine2('AQ854','T32',target)
    s=e.solve(include_policy=True)
    print('target',target,'prob',s.get('probability_fraction'),s.get('probability'))
    print(s)

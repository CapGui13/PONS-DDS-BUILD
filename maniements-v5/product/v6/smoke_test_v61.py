#!/usr/bin/env python3
import sys
from fractions import Fraction
from pathlib import Path
HERE=Path(__file__).resolve().parent
sys.path.insert(0,str(HERE/'runtime'))
sys.path.insert(0,str(HERE/'engine_tools'))
import integrated_engine as eng
import human_motif_v61_adaptive_double_finesse as v61
p,m=v61.evaluate(eng,'AKT92','765',4)
oracle=Fraction(eng.Engine2('AKT92','765',4).solve(include_policy=False)['probability_fraction'])
print('candidate',p,'oracle',oracle,'mask',m)
assert p==oracle==Fraction(103,115),(p,oracle)
print('GREEN V6.1 ARX92/765 target4 exact motif')

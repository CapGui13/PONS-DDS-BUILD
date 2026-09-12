#!/usr/bin/env python3
from __future__ import annotations
import argparse,json,time
from fractions import Fraction
from pathlib import Path
import human_batch_v44 as v44
import human_motif_v54 as v54
import human_prefix_exact_v511 as v511

# These are structural encodings of the already reviewed source instructions.
# The exact oracle is used only AFTER the stated prefix; therefore this checks
# that the human instruction itself preserves the optimum without assuming its tail.
SPECS={
 'BS_A':({'cash':(), 'feeder':'S','target':'N','seq':('K',),'probe':None,'mode':'cover','probe_mode':'cover'},1),
 'BS_B':({'cash':('A',),'feeder':'N','target':'S','seq':('Q',),'probe':None,'mode':'cover','probe_mode':'cover'},1),
 'BS_C':({'cash':(), 'feeder':'N','target':'S','seq':('T',),'probe':None,'mode':'cover','probe_mode':'cover'},1),
 'BS_D':({'cash':(), 'feeder':'S','target':'N','seq':('Q','T'),'probe':None,'mode':'cover','probe_mode':'cover'},2),
 'BS_E':({'cash':(), 'feeder':'S','target':'N','seq':('J',),'probe':None,'mode':'cover','probe_mode':'cover'},1),
 'SUITPLAY_ENC':({'cash':(), 'feeder':'N','target':'S','seq':('9',),'probe':None,'mode':'duck','probe_mode':'cover'},1),
 'ROUD_2':({'cash':('K',),'feeder':'S','target':'S','seq':(), 'probe':None,'mode':'cover','probe_mode':'cover'},1),
 'BH_1':({'cash':(), 'feeder':'S','target':'N','seq':('9','Q'),'probe':None,'mode':'cover','probe_mode':'cover'},2),
 'BH_2':({'cash':('A',),'feeder':'N','target':'S','seq':(), 'probe':None,'mode':'cover','probe_mode':'cover'},1),
 # X98/ARD7 is tested by its dedicated exact progressive strategy elsewhere;
 # here the first round is encoded as 8 toward Q by using only that target.
 'X98_ARD7':({'cash':(), 'feeder':'N','target':'S','seq':('Q',),'probe':None,'mode':'cover','probe_mode':'cover'},1),
}

def main():
 ap=argparse.ArgumentParser();ap.add_argument('--runtime-root',required=True);ap.add_argument('--out-dir',required=True);a=ap.parse_args();eng=v54.load_engine(a.runtime_root);rows=[];ok=0;t0=time.monotonic()
 for c in v44.CASES:
  spec,rounds=SPECS[c['id']];e=eng.Engine2(c['north'],c['south'],c['target']);opt=Fraction(e.solve(include_policy=False)['probability_fraction']);p,_=v511.evaluate_prefix(eng,c['north'],c['south'],c['target'],spec,rounds);good=p==opt;ok+=good
  row={'id':c['id'],'display':c['display'],'target':c['target'],'prefix_rounds':rounds,'oracle_fraction':str(opt),'prefix_fraction':str(p),'prefix_exact':good,'spec':{k:(list(v) if isinstance(v,tuple) else v) for k,v in spec.items()}};rows.append(row);print(json.dumps(row,ensure_ascii=False),flush=True)
 summary={'schema':'MANIEMENTS_V5_HUMAN_V516_REFERENCE_PREFIX_V1','cases':len(rows),'prefix_exact':ok,'rate_percent':f'{100*ok/len(rows):.2f}','runtime_frozen_sha256':'a0b580531f3c9e8bb00710b9c3e1c183b27cbfe9231c9d584e29a374ba88835d','meaning':'reviewed human source prefix is forced, then exact oracle completes the unspecified continuation'}
 od=Path(a.out_dir);od.mkdir(parents=True,exist_ok=True);(od/'HUMAN_V516_REFERENCE_PREFIX.json').write_text(json.dumps({'summary':summary,'cases':rows},ensure_ascii=False,indent=2)+'\n');(od/'SUMMARY.txt').write_text('\n'.join(f'{k}={v}' for k,v in summary.items())+'\n');print(json.dumps(summary,ensure_ascii=False),flush=True)
if __name__=='__main__':main()

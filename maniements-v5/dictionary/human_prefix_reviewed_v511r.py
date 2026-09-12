#!/usr/bin/env python3
from __future__ import annotations
import argparse,json,time
from collections import Counter
from pathlib import Path
import human_prefix_exact_v511 as v
import human_batch_v44 as v44
import human_motif_v54 as v54

def main():
    ap=argparse.ArgumentParser();ap.add_argument('--runtime-root',required=True);ap.add_argument('--out-dir',required=True);a=ap.parse_args();eng=v54.load_engine(a.runtime_root);rows=[];cnt=Counter();t0=time.monotonic()
    for c in v44.CASES:
        r=v.analyze(eng,c);rows.append(r);cnt['cases']+=1;cnt['found']+=int(r['found']);
        print(json.dumps({'case':c['id'],'found':r['found'],'prefix':(r['best'] or {}).get('prefix_rounds'),'lines':(r['best'] or {}).get('lines')},ensure_ascii=False),flush=True)
    summary={'schema':'MANIEMENTS_V5_HUMAN_V511R_REVIEWED_PREFIX_V1',**dict(cnt),'coverage_percent':f"{100*cnt['found']/cnt['cases']:.2f}",'elapsed_seconds':round(time.monotonic()-t0,3),'runtime_frozen_sha256':'a0b580531f3c9e8bb00710b9c3e1c183b27cbfe9231c9d584e29a374ba88835d'}
    od=Path(a.out_dir);od.mkdir(parents=True,exist_ok=True);(od/'HUMAN_V511R_REVIEWED_PREFIX.json').write_text(json.dumps({'summary':summary,'cases':rows},ensure_ascii=False,indent=2)+'\n');(od/'SUMMARY.txt').write_text('\n'.join(f'{k}={vv}' for k,vv in summary.items())+'\n');print(json.dumps(summary,ensure_ascii=False),flush=True)
if __name__=='__main__':main()

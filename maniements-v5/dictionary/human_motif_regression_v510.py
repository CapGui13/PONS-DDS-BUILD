#!/usr/bin/env python3
from __future__ import annotations

import argparse,json,sys,time
from fractions import Fraction
from pathlib import Path

HERE=Path(__file__).resolve().parent
sys.path.insert(0,str(HERE))
import human_batch_v44 as v44
import human_motif_v54 as v54
import human_motif_search_v571 as b571
import human_motif_search_v591 as x591

base=b571.v
ext=x591.m


def baseline_candidates(eng,c,opt):
    rows=[]
    for cash,feeder,target,seq in base.candidate_specs(c['north'],c['south']):
        try:p,_=base.evaluate(eng,c['north'],c['south'],c['target'],cash,feeder,target,seq)
        except Exception:continue
        if p!=opt:continue
        lines=base.procedure(cash,feeder,target,seq,c['display'])
        rows.append({'source':'V57','motif':base.motif_name(c['north'],c['south'],cash,seq),'lines':lines,'score':[len(lines),len(cash)+len(seq)]})
    return rows


def extended_candidates(eng,c,opt):
    rows=[]
    for s in x591.specs(c['north'],c['south']):
        try:p,_=ext.evaluate(eng,c['north'],c['south'],c['target'],s)
        except Exception:continue
        if p!=opt:continue
        ll=ext.lines(s,c['display'])
        rows.append({'source':'V591','motif':ext.motif(s),'lines':ll,'score':[len(ll),int(bool(s.get('probe'))),len(s['cash'])+len(s['seq'])]})
    return rows


def main():
    ap=argparse.ArgumentParser();ap.add_argument('--runtime-root',required=True);ap.add_argument('--out-dir',required=True);a=ap.parse_args();eng=v54.load_engine(a.runtime_root)
    out=[];found=0;t0=time.monotonic()
    for c in v44.CASES:
        e=eng.Engine2(c['north'],c['south'],c['target']);opt=Fraction(e.solve(include_policy=False)['probability_fraction'])
        rows=baseline_candidates(eng,c,opt)+extended_candidates(eng,c,opt)
        rows.sort(key=lambda r:(tuple(r['score']),r['source'],r['motif']))
        best=rows[0] if rows else None;found+=int(bool(best))
        z={'id':c['id'],'display':c['display'],'north':c['north'],'south':c['south'],'target':c['target'],'fraction':str(opt),'found':bool(best),'best':best,'exact_candidates':len(rows)};out.append(z)
        print(json.dumps({'case':c['id'],'found':bool(best),'source':(best or {}).get('source'),'motif':(best or {}).get('motif'),'candidates':len(rows)},ensure_ascii=False),flush=True)
    summary={'schema':'MANIEMENTS_V5_HUMAN_V510_REVIEWED_REGRESSION_V1','cases':len(out),'found':found,'coverage_percent':f'{100*found/len(out):.2f}','runtime_frozen_sha256':'a0b580531f3c9e8bb00710b9c3e1c183b27cbfe9231c9d584e29a374ba88835d','note':'motif candidates are accepted only when exhaustive replay equals the exact oracle; this regression does not use the reviewed maniement text as an answer key'}
    od=Path(a.out_dir);od.mkdir(parents=True,exist_ok=True);(od/'HUMAN_V510_REVIEWED_REGRESSION.json').write_text(json.dumps({'summary':summary,'cases':out},ensure_ascii=False,indent=2)+'\n',encoding='utf-8');(od/'SUMMARY.txt').write_text('\n'.join(f'{k}={v}' for k,v in summary.items())+'\n',encoding='utf-8');print(json.dumps(summary,ensure_ascii=False),flush=True)

if __name__=='__main__':main()

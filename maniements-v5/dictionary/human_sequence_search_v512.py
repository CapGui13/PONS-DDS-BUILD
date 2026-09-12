#!/usr/bin/env python3
from __future__ import annotations

import argparse,itertools,json,sys,time
from collections import Counter
from fractions import Fraction
from pathlib import Path

HERE=Path(__file__).resolve().parent
sys.path.insert(0,str(HERE))
import human_batch_v44 as v44
import human_motif_v54 as v54
import human_motif_search_v59 as m

RVAL=m.RVAL
STR='AKQJT98'


def ordered_sequences(hand):
    cards=[c for c in STR if c in hand]
    out=[]
    for k in range(1,min(3,len(cards))+1):
        for p in itertools.permutations(cards,k):
            if p not in out:out.append(p)
    return out


def cash_options(north,south):
    owned=north+south;out=[tuple()]
    for c in 'AKQJT':
        if c in owned:out.append((c,))
    return out


def specs(north,south):
    out=[];seen=set();cash=cash_options(north,south)
    def add(z):
        key=(z['cash'],z['feeder'],z['target'],z['seq'],z.get('probe'),z.get('mode'),z.get('probe_mode'))
        if key not in seen:seen.add(key);out.append(z)
    for feeder,target,fh,th in [('N','S',north,south),('S','N',south,north)]:
        seqs=ordered_sequences(th)
        for seq in seqs:
            for ca in cash:
                if set(ca)&set(seq):continue
                for mode in ('cover','duck'):
                    add({'cash':ca,'feeder':feeder,'target':target,'seq':seq,'probe':None,'mode':mode,'probe_mode':'cover'})
        # Honour-probe family; limit follow-up to 0/1/2-card ordered sequences.
        probes=[c for c in fh if c in 'KQJT']
        short=[tuple()]+[s for s in seqs if len(s)<=2]
        for probe in probes:
            for seq in short:
                for ca in cash:
                    if len(ca)>1 or probe in ca or set(ca)&set(seq):continue
                    for mode in ('cover','duck'):
                        for pm in ('cover','duck'):
                            add({'cash':ca,'feeder':feeder,'target':target,'seq':seq,'probe':probe,'mode':mode,'probe_mode':pm})
    return out


def human_score(s,ll):
    # Prefer no probe, no cash, short target sequence, then fewer lines.
    return (len(ll),int(bool(s.get('probe'))),len(s.get('cash') or ()),len(s.get('seq') or ()),int(s.get('mode')=='duck'))


def analyze(eng,c,max_candidates=0):
    e=eng.Engine2(c['north'],c['south'],c['target']);opt=Fraction(e.solve(include_policy=False)['probability_fraction']);rows=[];tested=0;t0=time.monotonic();ss=specs(c['north'],c['south'])
    if max_candidates:ss=ss[:max_candidates]
    for s in ss:
        try:p,mask=m.evaluate(eng,c['north'],c['south'],c['target'],s);tested+=1
        except Exception:continue
        if p!=opt:continue
        ll=m.lines(s,c['display']);rows.append({'spec':{k:(list(v) if isinstance(v,tuple) else v) for k,v in s.items()},'motif':m.motif(s) if s.get('probe') or s.get('mode')=='duck' else 'ORDERED_FINESSE_SEQUENCE','lines':ll,'mask':str(mask),'score':list(human_score(s,ll))})
    rows.sort(key=lambda r:tuple(r['score']));best=rows[0] if rows else None
    return {'id':c['id'],'display':c['display'],'north':c['north'],'south':c['south'],'target':c['target'],'fraction':str(opt),'found':bool(best),'best':best,'exact_candidates':len(rows),'tested':tested,'elapsed_seconds':round(time.monotonic()-t0,3)}


def main():
    ap=argparse.ArgumentParser();ap.add_argument('--runtime-root',required=True);ap.add_argument('--out-dir',required=True);ap.add_argument('--max-candidates',type=int,default=0);a=ap.parse_args();eng=v54.load_engine(a.runtime_root);rows=[];found=0;t0=time.monotonic()
    for c in v44.CASES:
        r=analyze(eng,c,a.max_candidates);rows.append(r);found+=int(r['found']);print(json.dumps({'case':c['id'],'found':r['found'],'candidates':r['exact_candidates'],'tested':r['tested'],'spec':(r['best'] or {}).get('spec'),'sec':r['elapsed_seconds']},ensure_ascii=False),flush=True)
    summary={'schema':'MANIEMENTS_V5_HUMAN_V512_ORDERED_SEQUENCE_REVIEWED_V1','cases':len(rows),'found':found,'coverage_percent':f'{100*found/len(rows):.2f}','elapsed_seconds':round(time.monotonic()-t0,3),'runtime_frozen_sha256':'a0b580531f3c9e8bb00710b9c3e1c183b27cbfe9231c9d584e29a374ba88835d','rule':'all ordered-sequence candidates are replayed exhaustively and accepted only when the exact oracle optimum is matched'}
    od=Path(a.out_dir);od.mkdir(parents=True,exist_ok=True);(od/'HUMAN_V512_ORDERED_SEQUENCE_REVIEWED.json').write_text(json.dumps({'summary':summary,'cases':rows},ensure_ascii=False,indent=2)+'\n',encoding='utf-8');(od/'SUMMARY.txt').write_text('\n'.join(f'{k}={v}' for k,v in summary.items())+'\n',encoding='utf-8');print(json.dumps(summary,ensure_ascii=False),flush=True)

if __name__=='__main__':main()

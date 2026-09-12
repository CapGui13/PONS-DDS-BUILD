#!/usr/bin/env python3
from __future__ import annotations

import argparse,json,sys,time
from collections import Counter
from fractions import Fraction
from functools import lru_cache
from pathlib import Path

HERE=Path(__file__).resolve().parent
sys.path.insert(0,str(HERE))
import human_batch_v44 as v44
import human_qualification_v50 as v50
import human_motif_v54 as v54
import human_motif_search_v591 as x591

m=x591.m


def to_spec_v57(z):
    cash,feeder,target,seq=z
    return {'cash':tuple(cash),'feeder':feeder,'target':target,'seq':tuple(seq),'probe':None,'mode':'cover','probe_mode':'cover'}


def candidate_specs(north,south):
    out=[];seen=set()
    for z in m.v.candidate_specs(north,south):
        s=to_spec_v57(z);k=repr(s)
        if k not in seen:seen.add(k);out.append(('V57',s))
    for s in x591.specs(north,south):
        k=repr(s)
        if k not in seen:seen.add(k);out.append(('V591',s))
    return out


def best_frontier(e,s):
    fr=e.frontier(s)
    return max(fr,key=lambda z:(e.model.weight(z),z)) if fr else 0


def evaluate_prefix(eng,north,south,goal,spec,prefix_rounds):
    e=eng.Engine2(north,south,goal)
    @lru_cache(maxsize=None)
    def F(s,rnd):
        term=e.terminal(s)
        if term is not None:return term[0]
        # Once a complete requested number of rounds has been played, hand the
        # continuation back to the exact oracle. This certifies the human prefix,
        # not an invented deterministic tail.
        if rnd>prefix_rounds and s.pos==0:
            return best_frontier(e,s)
        if s.pos==0:
            a=m.action(eng,e,s,spec)
            if a is None:return 0
            seat,c=a;r=eng.R2I[c]
            lead=eng.PublicState(s.north,s.south,s.west_seen,s.east_seen,s.west_void,s.east_void,seat,0,tuple(),s.won)
            ns=e.close(e.decl_play(lead,seat,r));return F(ns,rnd)
        seat=e.order(s.leader)[s.pos]
        if seat in eng.DECL:
            a=m.action(eng,e,s,spec)
            if a is None or a[0]!=seat:return 0
            c=a[1];r=eng.VOID if c=='-' else eng.R2I[c]
            ns=e.close(e.decl_play(s,seat,r));nr=rnd+1 if ns.pos==0 else rnd;return F(ns,nr)
        belief=e.belief(s);successful=belief
        for r,legal in e.defender_actions(s,seat):
            ns=e.close(e.def_play(s,seat,r));nr=rnd+1 if ns.pos==0 else rnd
            successful &= ((belief&~legal)|F(ns,nr))
        return successful
    mask=F(e.initial(),1);return e.model.weight(mask),mask


def short_desc(spec,display,prefix):
    ll=m.lines(spec,display)
    # Keep only the opening pieces relevant to a short prefix audit.
    return ll[:min(len(ll),max(1,prefix+1))]


def analyze(eng,c):
    e=eng.Engine2(c['north'],c['south'],c['target']);opt=Fraction(e.solve(include_policy=False)['probability_fraction']);rows=[];tested=0;t0=time.monotonic()
    for source,spec in candidate_specs(c['north'],c['south']):
        for pr in (1,2,3):
            try:p,_=evaluate_prefix(eng,c['north'],c['south'],c['target'],spec,pr);tested+=1
            except Exception:continue
            if p!=opt:continue
            lines=short_desc(spec,c['display'],pr);score=(pr,len(lines),int(bool(spec.get('probe'))),len(spec.get('cash') or ())+len(spec.get('seq') or ()))
            rows.append({'source':source,'prefix_rounds':pr,'lines':lines,'spec':{k:(list(v) if isinstance(v,tuple) else v) for k,v in spec.items()},'score':list(score)})
    rows.sort(key=lambda r:tuple(r['score']));best=rows[0] if rows else None
    return {'id':c['id'],'display':c['display'],'north':c['north'],'south':c['south'],'target':c['target'],'fraction':str(opt),'found':bool(best),'best':best,'exact_prefixes':len(rows),'tested':tested,'elapsed_seconds':round(time.monotonic()-t0,3)}


def main():
    ap=argparse.ArgumentParser();ap.add_argument('--runtime-root',required=True);ap.add_argument('--out-dir',required=True);a=ap.parse_args();eng=v54.load_engine(a.runtime_root)
    reviewed=[];novel=[];cnt=Counter();t0=time.monotonic()
    for c in v44.CASES:
        r=analyze(eng,c);reviewed.append(r);cnt['reviewed']+=1;cnt['reviewed_found']+=int(r['found']);print(json.dumps({'set':'reviewed','case':c['id'],'found':r['found'],'prefix':(r['best'] or {}).get('prefix_rounds')},ensure_ascii=False),flush=True)
    for cid,north,south in v50.HOLDINGS:
        for target in range(1,max(len(north),len(south))+1):
            e=eng.Engine2(north,south,target);opt=Fraction(e.solve(include_policy=False)['probability_fraction'])
            if opt in (0,1):continue
            c={'id':cid,'north':north,'south':south,'display':[v50.disp(north),v50.disp(south)],'target':target}
            r=analyze(eng,c);novel.append(r);cnt['novel']+=1;cnt['novel_found']+=int(r['found']);print(json.dumps({'set':'novel','case':cid,'target':target,'found':r['found'],'prefix':(r['best'] or {}).get('prefix_rounds')},ensure_ascii=False),flush=True)
    summary={'schema':'MANIEMENTS_V5_HUMAN_V511_PREFIX_EXACT_V1',**dict(cnt),'reviewed_rate_percent':f"{100*cnt['reviewed_found']/cnt['reviewed']:.2f}",'novel_rate_percent':f"{100*cnt['novel_found']/cnt['novel']:.2f}",'elapsed_seconds':round(time.monotonic()-t0,3),'runtime_frozen_sha256':'a0b580531f3c9e8bb00710b9c3e1c183b27cbfe9231c9d584e29a374ba88835d','meaning':'HUMAN_PREFIX_EXACT proves that the displayed motif prefix preserves the exact optimum; unspecified continuation is completed by the oracle and is not yet a finished public maniement'}
    od=Path(a.out_dir);od.mkdir(parents=True,exist_ok=True);(od/'HUMAN_V511_PREFIX_EXACT.json').write_text(json.dumps({'summary':summary,'reviewed':reviewed,'novel':novel},ensure_ascii=False,indent=2)+'\n',encoding='utf-8');(od/'SUMMARY.txt').write_text('\n'.join(f'{k}={v}' for k,v in summary.items())+'\n',encoding='utf-8');print(json.dumps(summary,ensure_ascii=False),flush=True)

if __name__=='__main__':main()

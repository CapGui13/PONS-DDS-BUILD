#!/usr/bin/env python3
from __future__ import annotations

import argparse, copy, datetime, json, signal, sys, time
from fractions import Fraction
from pathlib import Path

VERSION='BRIDGE_SEMANTICS_V2'
STATE_SCHEMA='MANIEMENTS_V5_SEMANTIC_BACKFILL_STATE_V1'

class TargetTimeout(Exception):
    pass

def _alarm(signum, frame):
    raise TargetTimeout()

def utcnow():
    return datetime.datetime.now(datetime.timezone.utc).replace(microsecond=0).isoformat()


def iter_regular_entries(root:Path):
    for p in sorted((root/'dictionary'/'chunks').glob('chunk_*.jsonl')):
        with p.open(encoding='utf-8') as f:
            for line in f:
                if line.strip():
                    yield json.loads(line)


def latest_entries(root:Path):
    # Production chunks are append-only. Keep the latest record for a state/target.
    rows={}
    for r in iter_regular_entries(root):
        rows[(int(r['state_id']),int(r['target']))]=r
    return [rows[k] for k in sorted(rows)]


def blank_state():
    return {
        'schema':STATE_SCHEMA,
        'version':VERSION,
        'next_index':0,
        'sequence':0,
        'checked_entries':0,
        'semantic_entries':0,
        'timeouts':0,
        'caught_up':False,
        'updated_at_utc':utcnow(),
    }


def load_state(root:Path):
    p=root/'dictionary'/'semantic_backfill'/'state.json'
    if not p.exists():
        return blank_state()
    d=json.loads(p.read_text(encoding='utf-8'))
    if d.get('schema')!=STATE_SCHEMA or d.get('version')!=VERSION:
        return blank_state()
    return d


def semanticize(eng,sem,r):
    c=r.get('compact') or {}
    if c.get('semantic'):
        return None
    if c.get('coverage')!='EXACT_POLICY_PROGRAM':
        return None
    n=r['north']; s=r['south']; t=int(r['target'])
    e=eng.Engine2(n,s,t)
    fr=e.frontier(e.initial())
    if not fr:
        return None
    best=max(fr,key=lambda m:(e.model.weight(m),m))
    expected=Fraction(r['probability_fraction'])
    if e.model.weight(best)!=expected:
        raise RuntimeError(f"probability mismatch {n}/{s} target {t}: {e.model.weight(best)} != {expected}")
    x=sem.semantic_success_explanation(eng,e,best,r['probability_fraction'],n,s,t)
    if x is None:
        return None
    out=copy.deepcopy(r)
    out['compact']['summary_fr']=x['summary_fr']
    out['compact']['semantic']=x
    out['compact']['display_policy_by_default']=False
    out['semantic_backfill_version']=VERSION
    out['semantic_backfilled_at_utc']=utcnow()
    return out


def main():
    ap=argparse.ArgumentParser()
    ap.add_argument('--runtime-root',required=True)
    ap.add_argument('--state-root',required=True)
    ap.add_argument('--budget-seconds',type=float,default=90.0)
    ap.add_argument('--target-cap-seconds',type=float,default=8.0)
    a=ap.parse_args()

    sys.path.insert(0,str(Path(a.runtime_root)/'runtime'))
    import integrated_engine as eng
    here=Path(__file__).resolve().parent
    sys.path.insert(0,str(here))
    import prototype_v3_semantics as sem

    root=Path(a.state_root)
    outdir=root/'dictionary'/'semantic_backfill'
    outdir.mkdir(parents=True,exist_ok=True)
    state=load_state(root)
    rows=latest_entries(root)
    i=min(int(state.get('next_index',0)),len(rows))
    seq=int(state.get('sequence',0))
    corrections=[]
    started=time.monotonic()
    deadline=started+a.budget_seconds
    old_handler=signal.signal(signal.SIGALRM,_alarm)

    try:
        while i<len(rows) and time.monotonic()<deadline-2:
            r=rows[i]
            state['checked_entries']=int(state.get('checked_entries',0))+1
            try:
                signal.setitimer(signal.ITIMER_REAL,a.target_cap_seconds)
                x=semanticize(eng,sem,r)
                signal.setitimer(signal.ITIMER_REAL,0)
                if x is not None:
                    corrections.append(x)
                    state['semantic_entries']=int(state.get('semantic_entries',0))+1
            except TargetTimeout:
                signal.setitimer(signal.ITIMER_REAL,0)
                state['timeouts']=int(state.get('timeouts',0))+1
            i+=1
            state['next_index']=i
    finally:
        signal.setitimer(signal.ITIMER_REAL,0)
        signal.signal(signal.SIGALRM,old_handler)

    if corrections:
        p=outdir/f'chunk_{seq:06d}.jsonl'
        with p.open('w',encoding='utf-8') as f:
            for r in corrections:
                f.write(json.dumps(r,ensure_ascii=False,sort_keys=True,separators=(',',':'))+'\n')
        seq+=1

    state['sequence']=seq
    state['source_entry_count']=len(rows)
    state['caught_up']=i>=len(rows)
    state['updated_at_utc']=utcnow()
    state['last_pass']={
        'checked':i-int(state.get('next_index_before_pass',0)) if 'next_index_before_pass' in state else None,
        'corrections':len(corrections),
        'elapsed_seconds':round(time.monotonic()-started,6),
    }
    state.pop('next_index_before_pass',None)
    (outdir/'state.json').write_text(json.dumps(state,ensure_ascii=False,sort_keys=True,indent=2)+'\n',encoding='utf-8')
    print(json.dumps({
        'version':VERSION,
        'next_index':state['next_index'],
        'source_entry_count':len(rows),
        'pass_corrections':len(corrections),
        'cumulative_semantic_entries':state['semantic_entries'],
        'timeouts':state['timeouts'],
        'caught_up':state['caught_up'],
    },sort_keys=True))

if __name__=='__main__':
    main()

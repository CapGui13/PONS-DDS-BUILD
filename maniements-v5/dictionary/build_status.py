#!/usr/bin/env python3
import argparse,json,datetime
from pathlib import Path
ap=argparse.ArgumentParser(); ap.add_argument('states_dir'); ap.add_argument('json_out'); ap.add_argument('md_out'); a=ap.parse_args()
root=Path(a.states_dir); workers=[]
for p in sorted(root.glob('worker_*.json')):
    try: workers.append(json.loads(p.read_text()))
    except Exception: pass
out={
 'schema':'MANIEMENTS_V5_DICTIONARY_STATUS_V1',
 'plan_id':'MANIEMENTS_V5_PRIORITY_P1_COMMON_SPLITS_PLUS_BOUNDARY_V1',
 'updated_at_utc':datetime.datetime.now(datetime.timezone.utc).replace(microsecond=0).isoformat(),
 'workers_seen':len(workers),
 'materialized_targets':sum(int(w.get('materialized_targets',0)) for w in workers),
 'deferred_targets':sum(int(w.get('deferred_targets',0)) for w in workers),
 'caught_up_workers':sum(bool(w.get('caught_up')) for w in workers),
 'source_done_workers':sum(bool(w.get('source_done')) for w in workers),
 'workers':workers,
}
Path(a.json_out).write_text(json.dumps(out,sort_keys=True,indent=2)+'\n')
lines=['# MANIEMENTS V5 — Dictionary materialization','',f"Updated: `{out['updated_at_utc']}`",'',
       f"- workers seen: **{out['workers_seen']}/20**",f"- materialized targets: **{out['materialized_targets']:,}**",
       f"- deferred targets: **{out['deferred_targets']:,}**",f"- caught-up workers: **{out['caught_up_workers']}/20**",
       f"- source-done workers: **{out['source_done_workers']}/20**",'',
       '| Worker | Materialized | Deferred | Next state | Active | Caught up | Source done |','|---:|---:|---:|---:|---:|:---:|:---:|']
for w in sorted(workers,key=lambda x:int(x['worker_id'])):
    lines.append(f"| {int(w['worker_id']):02d} | {int(w.get('materialized_targets',0)):,} | {int(w.get('deferred_targets',0)):,} | {int(w.get('next_source_state_id',0)):,} | {w.get('active_state_id') or ''} | {'yes' if w.get('caught_up') else 'no'} | {'yes' if w.get('source_done') else 'no'} |")
Path(a.md_out).write_text('\n'.join(lines)+'\n')

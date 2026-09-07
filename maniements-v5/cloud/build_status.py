#!/usr/bin/env python3
from __future__ import annotations
import argparse, datetime, json
from pathlib import Path

LANE_TOTALS=[12613,12635,12354,12745,12373,12356,12475]
GLOBAL_ORBITS=797161
GLOBAL_ROWS=1594322
GLOBAL_TARGETS=5183400


def load_json(path: Path, default=None):
    if not path.exists():
        return {} if default is None else default
    return json.loads(path.read_text(encoding='utf-8'))


def main():
    ap=argparse.ArgumentParser()
    ap.add_argument('status_dir')
    ap.add_argument('markdown')
    ap.add_argument('json_out')
    a=ap.parse_args()
    rows=[]
    for lane in range(7):
        p=Path(a.status_dir)/f'lane_{lane:02d}.json'
        d=json.loads(p.read_text(encoding='utf-8'))
        orch=load_json(Path(a.status_dir)/f'lane_{lane:02d}.orchestration.json')
        total=LANE_TOTALS[lane]
        d['lane_total_orbits']=total
        d['lane_percent']=round(100*d['cumulative_completed_orbits']/total,4)
        d['orchestration']=orch
        d['orchestration_mode']=orch.get('last_pass_mode', d.get('orchestration_mode','NORMAL'))
        d['next_mode']=orch.get('next_mode','NORMAL')
        d['stall_count']=int(orch.get('stall_count',0) or 0)
        d['hard_stall']=bool(orch.get('hard_stall',False))
        d['last_scientific_progress_at_utc']=orch.get('last_scientific_progress_at_utc')
        rows.append(d)
    done=sum(x['cumulative_completed_orbits'] for x in rows)
    active_total=sum(LANE_TOTALS)
    emitted=sum(x['cumulative_emitted_ordered_rows'] for x in rows)
    targets=sum(x['cumulative_completed_targets'] for x in rows)
    all_done=all(x['status']=='LANE_DONE' for x in rows)
    hard_stall_count=sum(1 for x in rows if x['status']!='LANE_DONE' and x['hard_stall'])
    runnable_lane_count=sum(1 for x in rows if x['status']!='LANE_DONE' and not x['hard_stall'])
    all_unfinished_hard_stalled=(not all_done and runnable_lane_count==0)
    now=datetime.datetime.now(datetime.timezone.utc).replace(microsecond=0).isoformat()
    out={
      'schema':'MANIEMENTS_V3_GEN_V5_GITHUB_STATUS_V2',
      'updated_at_utc':now,
      'active_lanes':[0,1,2,3,4,5,6],
      'active_lane_completed_orbits':done,
      'active_lane_total_orbits':active_total,
      'active_lane_percent':round(100*done/active_total,6),
      'global_completed_orbits':done,
      'global_total_orbits':GLOBAL_ORBITS,
      'global_orbit_percent':round(100*done/GLOBAL_ORBITS,6),
      'emitted_ordered_rows':emitted,
      'global_total_rows':GLOBAL_ROWS,
      'completed_targets':targets,
      'global_total_targets':GLOBAL_TARGETS,
      'all_active_lanes_done':all_done,
      'hard_stall_count':hard_stall_count,
      'runnable_lane_count':runnable_lane_count,
      'all_unfinished_hard_stalled':all_unfinished_hard_stalled,
      'lanes':rows,
    }
    Path(a.json_out).write_text(json.dumps(out,sort_keys=True,indent=2)+'\n',encoding='utf-8')
    md=[]
    md += ['# MANIEMENTS V5 — progression cloud','',f'Dernière mise à jour : `{now}`','']
    md += [f'**7 lanes : {done:,} / {active_total:,} orbites — {out["active_lane_percent"]:.3f}%**'.replace(',',' ')]
    md += [f'Contribution à l’univers global : {done:,} / {GLOBAL_ORBITS:,} — {out["global_orbit_percent"]:.3f}%'.replace(',',' ')]
    md += [f'Hard stalls : **{hard_stall_count}** — lanes encore exécutables : **{runnable_lane_count}**','']
    md += ['| Lane | PASS | Statut | Mode | Next | Stall | Orbites | Total lane | % | Targets | Active target | Dernier progrès |','|---:|---:|:---|:---|:---|---:|---:|---:|---:|---:|:---|:---|']
    for x in rows:
        active='—' if x.get('active_rep_state_id') is None else f"{x.get('active_rep_state_id')} / {x.get('active_next_target')}/{x.get('active_max_target')}"
        last=x.get('last_scientific_progress_at_utc') or '—'
        mode=x.get('orchestration_mode','NORMAL')
        nxt=x.get('next_mode','NORMAL')
        if x.get('hard_stall'):
            nxt='HARD_STALL'
        md.append(f"| {x['lane_id']:02d} | {x['pass_no']:06d} | {x['status']} | {mode} | {nxt} | {x.get('stall_count',0)} | {x['cumulative_completed_orbits']} | {x['lane_total_orbits']} | {x['lane_percent']:.2f}% | {x['cumulative_completed_targets']} | {active} | {last} |")
    md += ['','Chaque commit sur `maniements-v5-lane-XX` correspond à un PASS durable. `state/latest.zip` est le prédécesseur exact du PASS suivant.','']
    Path(a.markdown).write_text('\n'.join(md),encoding='utf-8')
if __name__=='__main__': main()

#!/usr/bin/env python3
from __future__ import annotations
import argparse, datetime, json
from math import comb
from pathlib import Path

PLAN_ID='MANIEMENTS_V5_PRIORITY_P1_COMMON_SPLITS_PLUS_BOUNDARY_V1'
PLAN_TOTAL_ORBITS=146641
PLAN_RANDOM_DEAL_MASS=0.4611817577950189
WORKERS=20
DEN=comb(52,13)*comb(39,13)

def per_orbit_mass(split:str)->float:
    a,b=(int(x) for x in split.split('-',1))
    return 2.0 * (comb(39,13-a)*comb(26+a,13-b) / DEN)

def main():
    ap=argparse.ArgumentParser()
    ap.add_argument('status_dir'); ap.add_argument('markdown'); ap.add_argument('json_out')
    a=ap.parse_args(); root=Path(a.status_dir)
    workers=[]; complete=deferred=targets=0; captured_mass=0.0
    for w in range(WORKERS):
        p=root/f'worker_{w:02d}.json'
        if p.exists():
            d=json.loads(p.read_text(encoding='utf-8'))
            if d.get('plan_id')!=PLAN_ID: raise SystemExit(f'worker {w} plan mismatch')
            status='DONE' if d.get('done') else 'RUNNING'
            c=int(d.get('completed_orbits',0)); q=int(d.get('deferred_orbits',0))
            for split,n in (d.get('completed_by_split') or {}).items():
                captured_mass += int(n)*per_orbit_mass(split)
            complete+=c; deferred+=q; targets+=int(d.get('completed_targets',0))
            active=(d.get('active_orbit') or {}).get('rep_state_id')
            cursor=d.get('next_scan_state_id')
            workers.append({'worker_id':w,'status':status,'completed_orbits':c,'deferred_orbits':q,'completed_targets':int(d.get('completed_targets',0)),'cursor':cursor,'active_rep_state_id':active,'sequence':d.get('sequence',0),'updated_at_utc':d.get('updated_at_utc')})
        else:
            workers.append({'worker_id':w,'status':'NOT_STARTED','completed_orbits':0,'deferred_orbits':0,'completed_targets':0,'cursor':1,'active_rep_state_id':None,'sequence':0,'updated_at_utc':None})
    scanned=complete+deferred
    all_done=all(x['status']=='DONE' for x in workers)
    now=datetime.datetime.now(datetime.timezone.utc).replace(microsecond=0).isoformat()
    out={
      'schema':'MANIEMENTS_V5_PRIORITY_STATUS_V1','plan_id':PLAN_ID,'updated_at_utc':now,
      'plan_total_orbits':PLAN_TOTAL_ORBITS,'plan_random_deal_probability_mass':PLAN_RANDOM_DEAL_MASS,
      'completed_orbits':complete,'deferred_orbits':deferred,'scanned_orbits':scanned,
      'remaining_unscanned_orbits':max(0,PLAN_TOTAL_ORBITS-scanned),
      'scan_percent':round(100*scanned/PLAN_TOTAL_ORBITS,6),
      'exact_completed_percent':round(100*complete/PLAN_TOTAL_ORBITS,6),
      'captured_random_deal_probability_mass':captured_mass,
      'captured_random_deal_probability_percent':round(100*captured_mass,6),
      'completed_targets':targets,'all_workers_done':all_done,'workers':workers,
    }
    Path(a.json_out).write_text(json.dumps(out,sort_keys=True,indent=2)+'\n',encoding='utf-8')
    md=['# MANIEMENTS V5 — Priority P1','','Objectif : calcul exact ciblé des splits de couleur les plus fréquents `2-3`, `2-4`, `3-3`, `3-4`, plus tout le domaine boundary fermé-forme.','',f'Dernière mise à jour : `{now}`','',f'**Scanné : {scanned:,} / {PLAN_TOTAL_ORBITS:,} orbites — {out["scan_percent"]:.2f}%**'.replace(',',' '),f'Exactement calculées : **{complete:,}** — différées car target > cap : **{deferred:,}**'.replace(',',' '),f'Couverture probabiliste exacte déjà capturée (modèle de donne aléatoire) : **{100*captured_mass:.3f}%**',f'Couverture maximale de P1 si aucun différé : **{100*PLAN_RANDOM_DEAL_MASS:.3f}%**','', '| Worker | État | Exactes | Différées | Targets | Cursor | Active |','|---:|:---|---:|---:|---:|---:|---:|']
    for x in workers:
        md.append(f"| {x['worker_id']:02d} | {x['status']} | {x['completed_orbits']} | {x['deferred_orbits']} | {x['completed_targets']} | {x['cursor']} | {x['active_rep_state_id'] if x['active_rep_state_id'] is not None else '—'} |")
    md += ['','Aucune valeur approximative n’est enregistrée : une orbite est soit calculée exactement, soit différée pour une passe spécialisée plus longue.','']
    Path(a.markdown).write_text('\n'.join(md),encoding='utf-8')
if __name__=='__main__': main()

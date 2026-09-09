#!/usr/bin/env python3
from __future__ import annotations
import argparse, datetime as dt, hashlib, json, os, sqlite3, subprocess, tarfile
from pathlib import Path

PLAN_ID="MANIEMENTS_V5_PRIORITY_P1_COMMON_SPLITS_PLUS_BOUNDARY_V1"
WORKER_COUNT=20
STATE_SCHEMA="MANIEMENTS_V5_PRIORITY_WORKER_STATE_V1"
DEFERRED_SCHEMA="MANIEMENTS_V5_PRIORITY_DEFERRED_ORBIT_V1"
DB_SCHEMA="MANIEMENTS_V5_PRODUCT_V0_SQLITE_V1"
DDL='''
CREATE TABLE meta(key TEXT PRIMARY KEY,value TEXT NOT NULL);
CREATE TABLE exact_rows(state_id INTEGER PRIMARY KEY,north TEXT NOT NULL,south TEXT NOT NULL,visible_count INTEGER NOT NULL,missing_ranks INTEGER NOT NULL,solver_mode TEXT NOT NULL,max_mode_target INTEGER NOT NULL,curve_json TEXT NOT NULL,policy_sha256_json TEXT NOT NULL,policy_swap_to_input INTEGER NOT NULL CHECK(policy_swap_to_input IN (0,1)),source_worker INTEGER NOT NULL,source_chunk TEXT NOT NULL);
CREATE TABLE deferred_rows(state_id INTEGER PRIMARY KEY,rep_state_id INTEGER NOT NULL,swap_state_id INTEGER NOT NULL,north TEXT NOT NULL,south TEXT NOT NULL,split TEXT NOT NULL,blocked_target INTEGER NOT NULL,target_cap_seconds REAL NOT NULL,completed_prefix_targets_json TEXT NOT NULL,policy_swap_to_input INTEGER NOT NULL CHECK(policy_swap_to_input IN (0,1)),source_worker INTEGER NOT NULL,source_file TEXT NOT NULL);
CREATE TABLE worker_state(worker_id INTEGER PRIMARY KEY,next_scan_state_id INTEGER NOT NULL,active_rep_state_id INTEGER,completed_orbits INTEGER NOT NULL,completed_targets INTEGER NOT NULL,deferred_orbits INTEGER NOT NULL,sequence INTEGER NOT NULL,done INTEGER NOT NULL CHECK(done IN (0,1)),updated_at_utc TEXT NOT NULL,branch_head TEXT NOT NULL);
'''
def utcnow(): return dt.datetime.now(dt.timezone.utc).replace(microsecond=0).isoformat()
def run(*args): return subprocess.check_output(args,text=True).strip()
def canonical_json(o): return json.dumps(o,sort_keys=True,separators=(",",":"),ensure_ascii=False)
def swap_state_id(sid:int)->int:
    code=sid; out=0; mul=1
    for _ in range(2,15):
        d=code%3; code//=3
        if d==1:d=2
        elif d==2:d=1
        out+=d*mul; mul*=3
    return out

def iter_priority_archive(ref):
    p=subprocess.Popen(["git","archive","--format=tar",ref,"priority"],stdout=subprocess.PIPE,stderr=subprocess.PIPE)
    assert p.stdout is not None
    try:
        with tarfile.open(fileobj=p.stdout,mode="r|") as tf:
            for m in tf:
                if not m.isfile(): continue
                f=tf.extractfile(m)
                if f is not None: yield m.name,f.read()
    finally:
        p.stdout.close(); err=p.stderr.read().decode("utf-8","replace") if p.stderr else ""; rc=p.wait()
        if rc: raise RuntimeError(f"git archive failed for {ref}: {err}")

def ensure_state(s,w):
    exp={"schema":STATE_SCHEMA,"plan_id":PLAN_ID,"worker_id":w,"worker_count":WORKER_COUNT}
    for k,v in exp.items():
        if s.get(k)!=v: raise RuntimeError(f"worker {w:02d}: state mismatch {k}: {s.get(k)!r} != {v!r}")

def insert_exact(c,row,w,src):
    curve=row.get("curve"); pol=row.get("policy_sha256")
    if not isinstance(curve,list) or not isinstance(pol,list) or len(curve)!=len(pol): raise RuntimeError(f"{src}: invalid curve/policy lengths")
    vals=(int(row["state_id"]),str(row["north"]),str(row["south"]),int(row["visible_count"]),int(row["missing_ranks"]),str(row["solver_mode"]),int(row["max_mode_target"]),canonical_json(curve),canonical_json(pol),1 if row.get("policy_swap_to_input") else 0,w,src)
    old=c.execute("SELECT north,south,visible_count,missing_ranks,solver_mode,max_mode_target,curve_json,policy_sha256_json,policy_swap_to_input FROM exact_rows WHERE state_id=?",(vals[0],)).fetchone()
    if old is not None:
        if tuple(old)!=vals[1:10]: raise RuntimeError(f"conflicting duplicate exact state_id={vals[0]}")
        return 0
    c.execute("INSERT INTO exact_rows VALUES (?,?,?,?,?,?,?,?,?,?,?,?)",vals); return 1

def insert_def(c,state_id,rec,swap,w,src):
    vals=(int(state_id),int(rec["rep_state_id"]),int(rec["swap_state_id"]),str(rec["south"] if swap else rec["north"]),str(rec["north"] if swap else rec["south"]),str(rec["split"]),int(rec["blocked_target"]),float(rec["target_cap_seconds"]),canonical_json(rec.get("completed_prefix_targets",[])),1 if swap else 0,w,src)
    old=c.execute("SELECT rep_state_id,swap_state_id,north,south,split,blocked_target,target_cap_seconds,completed_prefix_targets_json,policy_swap_to_input FROM deferred_rows WHERE state_id=?",(vals[0],)).fetchone()
    if old is not None:
        if tuple(old)!=vals[1:10]: raise RuntimeError(f"conflicting duplicate deferred state_id={vals[0]}")
        return 0
    c.execute("INSERT INTO deferred_rows VALUES (?,?,?,?,?,?,?,?,?,?,?,?)",vals); return 1

def sha256_file(p):
    h=hashlib.sha256()
    with open(p,"rb") as f:
        for b in iter(lambda:f.read(1024*1024),b""): h.update(b)
    return h.hexdigest()

def main():
    ap=argparse.ArgumentParser(); ap.add_argument("--repo",default="."); ap.add_argument("--output",required=True); ap.add_argument("--manifest",required=True); ap.add_argument("--ref-template",default="refs/remotes/origin/maniements-v5-priority-p1-{worker:02d}"); a=ap.parse_args()
    repo=Path(a.repo).resolve(); out=Path(a.output).resolve(); man=Path(a.manifest).resolve(); out.parent.mkdir(parents=True,exist_ok=True); man.parent.mkdir(parents=True,exist_ok=True)
    if out.exists(): out.unlink()
    c=sqlite3.connect(out); c.execute("PRAGMA journal_mode=OFF"); c.execute("PRAGMA synchronous=OFF"); c.execute("PRAGMA temp_store=MEMORY"); c.executescript(DDL)
    states=[]; heads={}; oldcwd=Path.cwd()
    try:
        os.chdir(repo)
        for w in range(WORKER_COUNT):
            ref=a.ref_template.format(worker=w); head=run("git","rev-parse",ref); heads[f"{w:02d}"]=head; state=None; files=[]
            for name,raw in iter_priority_archive(ref):
                if name=="priority/state.json": state=json.loads(raw.decode())
                elif (name.startswith("priority/chunks/") or name.startswith("priority/deferred/")) and name.endswith(".jsonl"): files.append((name,raw))
            if state is None: raise RuntimeError(f"worker {w:02d}: state missing")
            ensure_state(state,w)
            for name,raw in sorted(files):
                for lineno,line in enumerate(raw.splitlines(),1):
                    if not line.strip(): continue
                    obj=json.loads(line); src=f"{name}:{lineno}"
                    if name.startswith("priority/chunks/"): insert_exact(c,obj,w,src)
                    else:
                        if obj.get("schema")!=DEFERRED_SCHEMA or obj.get("plan_id")!=PLAN_ID: raise RuntimeError(f"{src}: deferred schema/plan mismatch")
                        rep=int(obj["rep_state_id"]); sw=int(obj["swap_state_id"])
                        if swap_state_id(rep)!=sw: raise RuntimeError(f"{src}: swap mismatch")
                        insert_def(c,rep,obj,False,w,src); insert_def(c,sw,obj,True,w,src)
            act=state.get("active_orbit"); active_sid=None if act is None else int(act["rep_state_id"])
            c.execute("INSERT INTO worker_state VALUES (?,?,?,?,?,?,?,?,?,?)",(w,int(state["next_scan_state_id"]),active_sid,int(state["completed_orbits"]),int(state["completed_targets"]),int(state["deferred_orbits"]),int(state["sequence"]),1 if state.get("done") else 0,str(state["updated_at_utc"]),head))
            states.append(state)
        c.commit()
        exact=c.execute("SELECT COUNT(*) FROM exact_rows").fetchone()[0]; deferred=c.execute("SELECT COUNT(*) FROM deferred_rows").fetchone()[0]
        eo=sum(int(s["completed_orbits"]) for s in states); do=sum(int(s["deferred_orbits"]) for s in states); targets=sum(int(s["completed_targets"]) for s in states)
        if exact!=2*eo: raise RuntimeError(f"exact row count mismatch db={exact} expected={2*eo}")
        if deferred!=2*do: raise RuntimeError(f"deferred row count mismatch db={deferred} expected={2*do}")
        overlap=c.execute("SELECT COUNT(*) FROM exact_rows e JOIN deferred_rows d USING(state_id)").fetchone()[0]
        if overlap: raise RuntimeError(f"exact/deferred overlap={overlap}")
        meta={"schema":DB_SCHEMA,"plan_id":PLAN_ID,"generated_at_utc":utcnow(),"worker_count":WORKER_COUNT,"exact_orbits":eo,"exact_ordered_rows":exact,"completed_targets":targets,"deferred_orbits":do,"deferred_ordered_rows":deferred}
        for k,v in meta.items(): c.execute("INSERT INTO meta VALUES (?,?)",(k,canonical_json(v)))
        c.commit(); c.execute("VACUUM"); c.close()
        manifest={**meta,"sqlite_sha256":sha256_file(out),"sqlite_bytes":out.stat().st_size,"branch_heads":heads,"workers":[{"worker_id":int(s["worker_id"]),"next_scan_state_id":int(s["next_scan_state_id"]),"active_rep_state_id":None if s.get("active_orbit") is None else int(s["active_orbit"]["rep_state_id"]),"completed_orbits":int(s["completed_orbits"]),"completed_targets":int(s["completed_targets"]),"deferred_orbits":int(s["deferred_orbits"]),"sequence":int(s["sequence"]),"done":bool(s.get("done")),"updated_at_utc":str(s["updated_at_utc"])} for s in states]}
        man.write_text(json.dumps(manifest,indent=2,sort_keys=True)+"\n",encoding="utf-8")
        print(json.dumps({k:manifest[k] for k in ("schema","exact_orbits","exact_ordered_rows","completed_targets","deferred_orbits","deferred_ordered_rows","sqlite_bytes","sqlite_sha256")},sort_keys=True))
    finally:
        try:c.close()
        except Exception:pass
        os.chdir(oldcwd)
if __name__=="__main__": main()

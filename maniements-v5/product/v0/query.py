#!/usr/bin/env python3
from __future__ import annotations

import argparse
import hashlib
import json
import sqlite3
from fractions import Fraction
from pathlib import Path

WORKER_HASH_PREFIX = "MANIEMENTS_V5_PRIORITY_P1_WORKER_V1:"
WORKER_COUNT = 20
COMMON_SPLITS = {(2, 3), (2, 4), (3, 3), (3, 4)}
RANK_TO_VALUE = {"2":2,"3":3,"4":4,"5":5,"6":6,"7":7,"8":8,"9":9,"T":10,"J":11,"Q":12,"K":13,"A":14}
VALUE_TO_RANK = {v:k for k,v in RANK_TO_VALUE.items()}

def normalize_cards(text: str) -> str:
    s = text.upper().replace("10", "T")
    for ch in " -_,./": s = s.replace(ch, "")
    if not s: raise ValueError("main vide")
    vals=[]; seen=set()
    for ch in s:
        if ch not in RANK_TO_VALUE: raise ValueError(f"rang invalide: {ch!r}")
        v=RANK_TO_VALUE[ch]
        if v in seen: raise ValueError(f"carte dupliquée dans la main: {ch}")
        seen.add(v); vals.append(v)
    vals.sort(reverse=True)
    return "".join(VALUE_TO_RANK[v] for v in vals)

def encode_state_id(north: str, south: str) -> tuple[int,int,int]:
    n=normalize_cards(north); s=normalize_cards(south)
    nvals={RANK_TO_VALUE[c] for c in n}; svals={RANK_TO_VALUE[c] for c in s}
    dup=nvals&svals
    if dup:
        ranks="".join(VALUE_TO_RANK[v] for v in sorted(dup, reverse=True))
        raise ValueError(f"carte(s) présente(s) des deux côtés: {ranks}")
    sid=0; mul=1; nmask=smask=0
    for rank in range(2,15):
        if rank in nvals: digit=1; nmask|=1<<rank
        elif rank in svals: digit=2; smask|=1<<rank
        else: digit=0
        sid += digit*mul; mul*=3
    return sid,nmask,smask

def swap_state_id(sid:int)->int:
    code=sid; out=0; mul=1
    for _ in range(2,15):
        d=code%3; code//=3
        if d==1: d=2
        elif d==2: d=1
        out += d*mul; mul*=3
    return out

def worker_for(rep_sid:int)->int:
    h=hashlib.sha256(f"{WORKER_HASH_PREFIX}{rep_sid}".encode("ascii")).digest()
    return int.from_bytes(h[:8],"big")%WORKER_COUNT

def eligible_counts(nc:int,sc:int)->bool:
    a,b=sorted((nc,sc)); v=a+b
    return (v==1) or (a==1 and b==1) or (v>=12) or ((a,b) in COMMON_SPLITS)

def pct(frac:str)->float: return float(Fraction(frac))*100.0

def query(conn:sqlite3.Connection,north:str,south:str)->dict:
    n=normalize_cards(north); s=normalize_cards(south)
    sid,nmask,smask=encode_state_id(n,s)
    row=conn.execute("SELECT north,south,visible_count,missing_ranks,solver_mode,max_mode_target,curve_json,policy_sha256_json,policy_swap_to_input FROM exact_rows WHERE state_id=?",(sid,)).fetchone()
    if row:
        curve=json.loads(row[6]); policies=json.loads(row[7])
        return {"status":"EXACT","state_id":sid,"north":row[0],"south":row[1],"visible_count":row[2],"missing_ranks":row[3],"solver_mode":row[4],"max_mode_target":row[5],"curve":[{"target":i,"fraction":f,"percent":round(pct(f),6),"policy_sha256":policies[i]} for i,f in enumerate(curve)],"policy_swap_to_input":bool(row[8])}
    d=conn.execute("SELECT rep_state_id,swap_state_id,north,south,split,blocked_target,target_cap_seconds,completed_prefix_targets_json,policy_swap_to_input FROM deferred_rows WHERE state_id=?",(sid,)).fetchone()
    if d:
        return {"status":"DEFERRED","state_id":sid,"rep_state_id":d[0],"swap_state_id":d[1],"north":d[2],"south":d[3],"split":d[4],"blocked_target":d[5],"target_cap_seconds":d[6],"completed_prefix_targets":json.loads(d[7]),"policy_swap_to_input":bool(d[8])}
    nc,sc=len(n),len(s)
    if not eligible_counts(nc,sc):
        return {"status":"OUTSIDE_P1","state_id":sid,"north":n,"south":s,"split":f"{min(nc,sc)}-{max(nc,sc)}","message":"Cette position n'appartient pas au périmètre P1 actuel."}
    swap=swap_state_id(sid)
    rep_sid=sid if (nmask,smask)<(smask,nmask) else swap
    worker=worker_for(rep_sid)
    ws=conn.execute("SELECT next_scan_state_id,active_rep_state_id,done,updated_at_utc FROM worker_state WHERE worker_id=?",(worker,)).fetchone()
    if ws is None: return {"status":"UNKNOWN","state_id":sid,"message":"État worker absent du snapshot."}
    next_scan,active_sid,done,updated=ws
    if active_sid==rep_sid: status="ACTIVE"
    elif rep_sid>=next_scan and not done: status="PENDING"
    elif done: status="MISSING_AFTER_DONE"
    else: status="SCANNED_NO_ROW"
    return {"status":status,"state_id":sid,"rep_state_id":rep_sid,"worker_id":worker,"north":n,"south":s,"next_scan_state_id":next_scan,"worker_updated_at_utc":updated}

def main():
    ap=argparse.ArgumentParser(); ap.add_argument("--db",required=True); ap.add_argument("--north",required=True); ap.add_argument("--south",required=True); ap.add_argument("--json",action="store_true"); a=ap.parse_args()
    conn=sqlite3.connect(f"file:{Path(a.db).resolve()}?mode=ro",uri=True)
    try: result=query(conn,a.north,a.south)
    except ValueError as e: raise SystemExit(str(e))
    finally: conn.close()
    if a.json: print(json.dumps(result,indent=2,ensure_ascii=False,sort_keys=True)); return
    print(f"Statut : {result['status']}"); print(f"Nord   : {result.get('north','')}"); print(f"Sud    : {result.get('south','')}"); print(f"state  : {result.get('state_id')}")
    if result["status"]=="EXACT":
        print(f"Mode   : {result['solver_mode']}"); print("Courbe exacte :")
        for item in result["curve"]: print(f"  target {item['target']}: {item['fraction']} = {item['percent']:.6f}%")
    elif result["status"]=="DEFERRED": print(f"Différé au target {result['blocked_target']} (cap {result['target_cap_seconds']} s)")
    else:
        if result.get("message"): print(result["message"])
        if "worker_id" in result: print(f"Worker : {result['worker_id']:02d}")
if __name__=="__main__": main()

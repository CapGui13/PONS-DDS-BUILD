#!/usr/bin/env python3
from __future__ import annotations

import argparse
import datetime
import json
import sqlite3
import sys
import threading
import webbrowser
from fractions import Fraction
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from urllib.parse import parse_qs, urlparse

FROZEN_SHA256 = "a0b580531f3c9e8bb00710b9c3e1c183b27cbfe9231c9d584e29a374ba88835d"
RANK_TO_VALUE = {"2":2,"3":3,"4":4,"5":5,"6":6,"7":7,"8":8,"9":9,"T":10,"J":11,"Q":12,"K":13,"A":14}
VALUE_TO_RANK = {v:k for k,v in RANK_TO_VALUE.items()}
FR_IN = {"R":"K","D":"Q","V":"J","X":"T"}
FR_OUT = {"K":"R","Q":"D","J":"V","T":"X"}


def utcnow():
    return datetime.datetime.now(datetime.timezone.utc).replace(microsecond=0).isoformat()


def normalize_cards(text: str) -> str:
    s = str(text or "").replace("10", "T")
    for ch in " -_,./":
        s = s.replace(ch, "")
    if not s:
        raise ValueError("main vide")
    vals = []
    seen = set()
    for raw in s:
        if raw == "x":
            raise ValueError("Pour le calcul direct V1, remplace chaque x par sa petite carte exacte (2 à 7).")
        c = raw.upper()
        c = FR_IN.get(c, c)
        if c not in RANK_TO_VALUE:
            raise ValueError(f"rang invalide : {raw!r}")
        v = RANK_TO_VALUE[c]
        if v in seen:
            raise ValueError(f"carte répétée dans la main : {raw}")
        seen.add(v)
        vals.append(v)
    vals.sort(reverse=True)
    return "".join(VALUE_TO_RANK[v] for v in vals)


def fr_hand(s: str) -> str:
    return "".join(FR_OUT.get(c, c) for c in s)


def cache_key(n: str, s: str) -> str:
    return n + "|" + s


class DirectSolver:
    def __init__(self, runtime_root: Path, tools_root: Path, cache_path: Path):
        self.runtime_root = runtime_root
        self.tools_root = tools_root
        self.cache_path = cache_path
        sys.path.insert(0, str(runtime_root))
        sys.path.insert(0, str(tools_root))
        import integrated_engine as eng
        import materialize_worker_v3 as mw
        import prototype_v3_builtin_policy as bp
        import prototype_v3_policy_compress as pc
        import prototype_v3_compile as cc
        self.eng = eng
        self.mw = mw
        self.bp = bp
        self.pc = pc
        self.cc = cc
        self._init_cache()

    def _connect(self):
        c = sqlite3.connect(self.cache_path)
        c.execute("PRAGMA journal_mode=WAL")
        return c

    def _init_cache(self):
        c = self._connect()
        try:
            c.execute("""
                CREATE TABLE IF NOT EXISTS direct_cache(
                    cache_key TEXT PRIMARY KEY,
                    north TEXT NOT NULL,
                    south TEXT NOT NULL,
                    result_json TEXT NOT NULL,
                    runtime_sha256 TEXT NOT NULL,
                    created_at_utc TEXT NOT NULL
                )
            """)
            c.commit()
        finally:
            c.close()

    def cached(self, n, s):
        c = self._connect()
        try:
            row = c.execute(
                "SELECT result_json,runtime_sha256 FROM direct_cache WHERE cache_key=?",
                (cache_key(n, s),),
            ).fetchone()
        finally:
            c.close()
        if not row or row[1] != FROZEN_SHA256:
            return None
        r = json.loads(row[0])
        r["cache"] = "HIT"
        return r

    def store(self, n, s, result):
        c = self._connect()
        try:
            c.execute(
                "INSERT OR REPLACE INTO direct_cache VALUES (?,?,?,?,?,?)",
                (
                    cache_key(n, s), n, s,
                    json.dumps(result, ensure_ascii=False, separators=(",", ":")),
                    FROZEN_SHA256, utcnow(),
                ),
            )
            c.commit()
        finally:
            c.close()

    def compute_target(self, n, s, target):
        e = self.eng.Engine2(n, s, target)
        base = e.solve(include_policy=False)
        prob = base["probability_fraction"]
        row = {
            "target": target,
            "fraction": prob,
            "percent": round(float(Fraction(prob)) * 100.0, 8),
            "status": "EXACT",
        }
        p = Fraction(prob)
        if p in (0, 1):
            row["strategy_kind"] = "TRIVIAL"
            return row

        # The policy program is the exact machine-readable source of truth.
        # It is NOT advertised as a human maniement.
        try:
            comp, policy_states = self.mw.supported_plan(
                self.eng, self.bp, self.pc, self.cc,
                n, s, target, prob,
            )
            row.update({
                "strategy_kind": "EXACT_POLICY_PROGRAM",
                "policy_states": policy_states,
                "lead": comp.get("lead"),
                "automatic_summary_unreviewed": comp.get("summary_fr") or "",
                "policy_program": comp.get("policy_program"),
                "program_stats": comp.get("program_stats"),
                "coverage": comp.get("coverage"),
            })
        except Exception as exc:
            row.update({
                "strategy_kind": "EXACT_PROBABILITY_ONLY",
                "policy_error": f"{type(exc).__name__}: {exc}",
            })
        return row

    def query(self, north, south, use_cache=True):
        n = normalize_cards(north)
        s = normalize_cards(south)
        dup = set(n) & set(s)
        if dup:
            raise ValueError("carte(s) présente(s) des deux côtés : " + "".join(sorted(dup, key=lambda c:RANK_TO_VALUE[c], reverse=True)))
        if use_cache:
            hit = self.cached(n, s)
            if hit is not None:
                return hit
        max_target = max(len(n), len(s))
        rows = [self.compute_target(n, s, t) for t in range(1, max_target + 1)]
        result = {
            "schema": "MANIEMENTS_V5_DIRECT_QUERY_V1",
            "north": n,
            "south": s,
            "north_fr": fr_hand(n),
            "south_fr": fr_hand(s),
            "runtime_frozen_sha256": FROZEN_SHA256,
            "cache": "MISS",
            "computed_at_utc": utcnow(),
            "curve": rows,
        }
        self.store(n, s, result)
        return result


PAGE = r'''<!doctype html><html lang="fr"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1">
<title>MANIEMENTS — calcul direct V1</title><style>
:root{color-scheme:dark;--bg:#0b0f14;--p:#151b23;--p2:#10161d;--l:#2b3542;--t:#eef4fa;--m:#98a6b5;--g:#77e3aa;--b:#86c2ff;--gold:#e7c46a}
*{box-sizing:border-box}body{margin:0;background:var(--bg);color:var(--t);font:16px/1.5 system-ui,-apple-system,Segoe UI,Roboto,sans-serif}main{max-width:900px;margin:auto;padding:30px 16px 70px}
h1{margin:0 0 5px}.muted{color:var(--m)}.card{background:var(--p);border:1px solid var(--l);border-radius:15px;padding:18px;margin-top:16px}.grid{display:grid;grid-template-columns:1fr;gap:14px}@media(min-width:650px){.grid{grid-template-columns:1fr 1fr}}
label{display:block;font-weight:800;margin-bottom:6px}input{width:100%;padding:13px 14px;border:1px solid #3c4959;border-radius:11px;background:#0a1016;color:#fff;font:800 1.2rem ui-monospace,Consolas,monospace}
button{border:0;border-radius:11px;padding:12px 17px;font-weight:850;font-size:1rem;cursor:pointer}.entry{background:var(--p2);border:1px solid var(--l);border-radius:13px;padding:15px;margin-top:11px}.head{display:flex;justify-content:space-between;gap:12px;align-items:baseline;flex-wrap:wrap}.prob{color:var(--g);font-weight:850}.badge{display:inline-block;font-size:.73rem;font-weight:850;padding:2px 8px;border:1px solid #496172;border-radius:999px;margin-left:7px}.exact{border-color:#6c5d2c;color:var(--gold)}.tree{border-color:#347450;color:var(--g)}
details{margin-top:10px;border-top:1px solid #29333f;padding-top:9px}summary{cursor:pointer;font-weight:800}.ctx{margin:10px 0;padding:10px 12px;background:#0c1219;border-left:3px solid #46576a;border-radius:8px}.branch{margin:6px 0 0 16px;padding-left:12px;border-left:1px solid #34414e}.small{font-size:.88rem}.plan{margin-top:10px;padding:11px 12px;background:#0c1513;border-left:3px solid var(--g);border-radius:8px}.useful{border-left-color:#4d8d70}.act{margin:5px 0;font-weight:700}.otherwise{margin-top:5px}.decision{margin-top:7px}.error{border-left:3px solid #ff9898;padding-left:11px}
</style></head><body><main><h1>Calcul direct des maniements <span class="badge exact">V1</span></h1>
<p class="muted">Cette version calcule la combinaison demandée avec le moteur exact. Pour l’instant, saisis les petites cartes réelles : <b>ARX92 / 765</b>, par exemple. Le français automatique n’est pas considéré comme un maniement humain validé.</p>
<section class="card"><form id="f"><div class="grid"><div><label>Main 1</label><input id="n" value="ARX92"></div><div><label>Main 2</label><input id="s" value="765"></div></div><div style="margin-top:14px"><button>Calculer</button></div></form></section>
<section class="card" id="out"><div class="muted">Entre une combinaison.</div></section>
<script>
'use strict';
const out=document.getElementById('out');
function esc(s){return String(s??'').replace(/[&<>"']/g,c=>({'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;',"'":'&#39;'}[c]))}
function rankFr(r){return {A:"l’As",K:'le Roi',Q:'la Dame',J:'le Valet',T:'le 10'}[r]||'le '+r}
function seatFr(s){return {N:'Main 1',S:'Main 2',E:'Est',W:'Ouest'}[s]||s}
function actionFr(a){if(!a)return '—';let [s,r]=a.split(':');if(r==='-')return seatFr(s)+' est chicane';return 'jouer '+rankFr(r)+' de '+seatFr(s)}
function featureFr(f){
  let p=f.split('_');const side=x=>x==='W'?'Ouest':'Est';
  if((p[0]==='W'||p[0]==='E')&&p[1]==='VOID')return side(p[0])+' a déjà montré qu’il était chicane';
  if((p[0]==='W'||p[0]==='E')&&p[1]==='SEEN')return rankFr(p[2])+' est déjà tombé chez '+side(p[0]);
  if(p[0]==='CUR'){
    if(p[2]==='-')return side(p[1])+' défausse';
    return side(p[1])+' fournit '+rankFr(p[2]);
  }
  return f;
}
function leaves(v,out=new Set()){if(typeof v==='string'){out.add(v);return out}leaves(v[1],out);leaves(v[2],out);return out}
function decision(v,depth=0){
  if(typeof v==='string')return '<div class="act">→ '+esc(actionFr(v))+'</div>';
  const [feat,no,yes]=v;
  return '<div class="decision"><b>Si '+esc(featureFr(feat))+' :</b><div class="branch">'+decision(yes,depth+1)+'</div><div class="otherwise"><span class="muted">Sinon :</span><div class="branch">'+decision(no,depth+1)+'</div></div></div>';
}
function handFrRaw(x){return String(x||'-').replaceAll('K','R').replaceAll('Q','D').replaceAll('J','V').replaceAll('T','X')}
function contextTitle(k){
  const n=handFrRaw(k[0]),s=handFrRaw(k[1]),won=Number(k[4]||0),pos=Number(k[3]||0);
  let lead=pos===0?'Nouveau tour de couleur':'Pendant la levée';
  return lead+' · '+won+' levée'+(won===1?'':'s')+' déjà gagnée'+(won===1?'':'s')+' · reste '+n+' / '+s;
}
function policyUseful(pp){
  if(!pp||!pp.contexts)return '<div class="muted">Arbre non disponible.</div>';
  let rows=[...pp.contexts].filter(([k,v])=>Number(k[3])===0 || leaves(v).size>1);
  if(!rows.length)return '<div class="muted">Aucune décision stratégique supplémentaire : la suite est forcée.</div>';
  let shown=rows.slice(0,14);
  let h=shown.map(([k,v],i)=>'<div class="ctx useful"><b>'+esc(contextTitle(k))+'</b>'+decision(v)+'</div>').join('');
  if(rows.length>shown.length)h+='<div class="muted small">'+(rows.length-shown.length)+' autres contextes stratégiques sont conservés dans le diagnostic technique.</div>';
  return h;
}
function policyRaw(pp){
  if(!pp||!pp.contexts)return '<div class="muted">Arbre non disponible.</div>';
  return [...pp.contexts].map(([k,v],i)=>'<div class="ctx"><b>Contexte exact '+(i+1)+'</b><div class="small muted">'+esc(contextTitle(k))+'</div>'+decision(v)+'</div>').join('');
}
function render(r){let h='<div><b>'+esc(r.north_fr)+' — '+esc(r.south_fr)+'</b> <span class="muted small">cache '+esc(r.cache)+'</span></div>';for(const e of [...r.curve].sort((a,b)=>b.target-a.target)){h+='<div class="entry"><div class="head"><div><b>Pour '+e.target+' levée'+(e.target===1?'':'s')+'</b> <span class="badge exact">exact</span>'+(e.strategy_kind==='EXACT_POLICY_PROGRAM'?' <span class="badge tree">arbre exact</span>':'')+'</div><div class="prob">'+Number(e.percent).toFixed(2).replace('.',',')+' %</div></div>';if(e.strategy_kind==='TRIVIAL')h+='<div class="muted" style="margin-top:8px">'+(e.fraction==='1/1'?'Objectif assuré.':'Objectif impossible.')+'</div>';else if(e.strategy_kind==='EXACT_POLICY_PROGRAM'){h+='<div class="plan"><div><b>Premier coup exact :</b> '+esc(actionFr(e.lead))+'</div><div class="muted small">Lecture simplifiée de la politique exacte — ce n’est pas encore le maniement humain final.</div></div><details open><summary>Voir les décisions utiles</summary>'+policyUseful(e.policy_program)+'</details><details><summary>Diagnostic technique complet</summary>'+policyRaw(e.policy_program)+'</details>'}else h+='<div class="muted" style="margin-top:8px">Probabilité exacte calculée ; arbre non matérialisé pour ce cas.</div>';h+='</div>'}out.innerHTML=h}
document.getElementById('f').onsubmit=async e=>{e.preventDefault();out.innerHTML='<div class="muted">Calcul exact en cours… la première requête peut prendre un peu de temps.</div>';try{const u='/api/query?north='+encodeURIComponent(n.value)+'&south='+encodeURIComponent(s.value);const resp=await fetch(u),j=await resp.json();if(!resp.ok)throw Error(j.error||'Erreur');render(j)}catch(err){out.innerHTML='<div class="error"><b>Erreur :</b> '+esc(err.message||err)+'</div>'}};
</script></main></body></html>'''


class Handler(BaseHTTPRequestHandler):
    solver: DirectSolver

    def send_bytes(self, status, body, ctype):
        self.send_response(status)
        self.send_header("Content-Type", ctype)
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def do_GET(self):
        u = urlparse(self.path)
        if u.path == "/":
            self.send_bytes(200, PAGE.encode("utf-8"), "text/html; charset=utf-8")
            return
        if u.path == "/api/query":
            q = parse_qs(u.query)
            north = q.get("north", [""])[0]
            south = q.get("south", [""])[0]
            try:
                result = self.solver.query(north, south)
                self.send_bytes(200, json.dumps(result, ensure_ascii=False).encode("utf-8"), "application/json; charset=utf-8")
            except Exception as exc:
                self.send_bytes(400, json.dumps({"error": str(exc)}, ensure_ascii=False).encode("utf-8"), "application/json; charset=utf-8")
            return
        self.send_bytes(404, b"Not found", "text/plain; charset=utf-8")

    def log_message(self, fmt, *args):
        print(f"[http] {self.address_string()} {fmt % args}")


def main():
    here = Path(__file__).resolve().parent
    ap = argparse.ArgumentParser()
    ap.add_argument("--runtime-root", default=str(here / "runtime"))
    ap.add_argument("--tools-root", default=str(here / "engine_tools"))
    ap.add_argument("--cache", default=str(here / "direct_cache.sqlite"))
    ap.add_argument("--host", default="127.0.0.1")
    ap.add_argument("--port", type=int, default=0)
    ap.add_argument("--open", action="store_true")
    a = ap.parse_args()

    Handler.solver = DirectSolver(Path(a.runtime_root), Path(a.tools_root), Path(a.cache))
    # port=0 asks the OS for an actually free local port, avoiding collisions
    # with the user's other local bridge tools.
    srv = ThreadingHTTPServer((a.host, a.port), Handler)
    actual_port = int(srv.server_address[1])
    url = f"http://{a.host}:{actual_port}"
    print("MANIEMENTS V5 direct V1:", url)
    if a.open:
        threading.Timer(0.8, lambda: webbrowser.open(url)).start()
    try:
        srv.serve_forever()
    except KeyboardInterrupt:
        pass


if __name__ == "__main__":
    main()

#!/usr/bin/env python3
from __future__ import annotations

import argparse
import datetime
import json
import subprocess
from fractions import Fraction
from pathlib import Path

EXACT_PREFIX = "maniements-v5-dictionary-v3-p1-"
HUMAN_PREFIX = "maniements-v5-human-v1-p1-"
HONORS = "AKQJT"


def git_text(repo: Path, ref: str, path: str) -> str:
    return subprocess.check_output(["git", "-C", str(repo), "show", f"{ref}:{path}"], text=True)


def list_paths(repo: Path, ref: str, prefix: str):
    try:
        out = subprocess.check_output(
            ["git", "-C", str(repo), "ls-tree", "-r", "--name-only", ref, prefix],
            text=True,
            stderr=subprocess.DEVNULL,
        )
    except subprocess.CalledProcessError:
        return []
    return [x for x in out.splitlines() if x]


def iter_ref_jsonl(repo: Path, ref: str, prefix: str):
    for p in list_paths(repo, ref, prefix):
        if not p.endswith(".jsonl"):
            continue
        for line in git_text(repo, ref, p).splitlines():
            if line.strip():
                yield json.loads(line)


def eligible(north: str, south: str):
    total = len(north) + len(south)
    h = sum(c in HONORS for c in north + south)
    return 5 <= total <= 8 and 2 <= h <= 4


def safe_exact_summary(s):
    s = str(s or "")
    bad = (
        "contextes de décision",
        "La suite optimale dépend ensuite des cartes fournies par la défense",
    )
    if any(x in s for x in bad):
        return "Calcul exact disponible."
    return s or "Calcul exact disponible."


def load_exact(repo: Path):
    rows = {}
    for w in range(20):
        ref = f"refs/remotes/origin/{EXACT_PREFIX}{w:02d}"
        for r in iter_ref_jsonl(repo, ref, "dictionary/chunks"):
            if eligible(r["north"], r["south"]):
                rows[(int(r["state_id"]), int(r["target"]))] = r
    return rows


def load_human(repo: Path):
    rows = {}
    deferred = {}
    states = []
    for w in range(20):
        ref = f"refs/remotes/origin/{HUMAN_PREFIX}{w:02d}"
        for r in iter_ref_jsonl(repo, ref, "human/chunks"):
            rows[(int(r["state_id"]), int(r["target"]))] = r
        for r in iter_ref_jsonl(repo, ref, "human/deferred"):
            deferred[(int(r["state_id"]), int(r["target"]))] = r
        try:
            states.append(json.loads(git_text(repo, ref, "human/state.json")))
        except Exception:
            pass
    return rows, deferred, states


def build_payload(exact, human, deferred):
    by_state = {}
    for (sid, t), r in exact.items():
        st = by_state.setdefault(sid, {"n": r["north"], "s": r["south"], "targets": {}})
        st["targets"][t] = r

    out = {}
    compact_targets = 0
    total_targets = 0
    fully_processed = 0

    for sid, st in by_state.items():
        nontrivial = [
            t for t, r in st["targets"].items()
            if 0 < Fraction(r["probability_fraction"]) < 1
        ]
        if not nontrivial:
            continue
        if not all((sid, t) in human or (sid, t) in deferred for t in nontrivial):
            continue

        compact_here = sum(
            1 for t in nontrivial
            if human.get((sid, t), {}).get("bridge_compact_exact")
        )
        if compact_here == 0:
            continue

        fully_processed += 1
        dst = {"n": st["n"], "s": st["s"], "t": {}}
        for t, r in sorted(st["targets"].items()):
            h = human.get((sid, t))
            d = deferred.get((sid, t))
            e = {
                "p": r["probability_fraction"],
                "exact": safe_exact_summary((r.get("compact") or {}).get("summary_fr")),
                "coverage": (r.get("compact") or {}).get("coverage"),
            }
            if h:
                e["human_status"] = h["status"]
                e["human_lines"] = h.get("full_lines") or []
                e["prefix_rounds"] = h.get("prefix_rounds")
                e["human_source"] = h.get("source")
                if h.get("bridge_compact_exact"):
                    compact_targets += 1
            elif d:
                e["human_status"] = "TARGET_TIMEOUT"
            else:
                e["human_status"] = "NOT_HUMANIZED"
            dst["t"][str(t)] = e
            total_targets += 1
        out[str(sid)] = dst

    return out, {
        "state_count": len(out),
        "fully_processed_holdings": fully_processed,
        "target_count": total_targets,
        "compact_targets": compact_targets,
    }


INDEX = r'''<!doctype html>
<html lang="fr">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width,initial-scale=1">
<title>Dictionnaire des maniements — V1 humaine</title>
<style>
:root{color-scheme:dark;--bg:#0b0f14;--p:#151b23;--p2:#10161d;--l:#2b3542;--t:#eef4fa;--m:#98a6b5;--g:#77e3aa;--b:#86c2ff;--gold:#e7c46a;--warn:#f0b34f}
*{box-sizing:border-box}body{margin:0;background:var(--bg);color:var(--t);font:16px/1.5 system-ui,-apple-system,Segoe UI,Roboto,sans-serif}
main{max-width:880px;margin:auto;padding:30px 16px 70px}h1{margin:0 0 6px;font-size:clamp(1.65rem,4vw,2.3rem)}.muted{color:var(--m)}.small{font-size:.88rem}
.card{background:var(--p);border:1px solid var(--l);border-radius:15px;padding:18px;margin-top:16px}.grid{display:grid;grid-template-columns:1fr;gap:14px}
@media(min-width:650px){.grid{grid-template-columns:1fr 1fr}}label{display:block;font-weight:800;margin-bottom:6px}
input{width:100%;padding:13px 14px;border:1px solid #3c4959;border-radius:11px;background:#0a1016;color:#fff;font:800 1.2rem ui-monospace,Consolas,monospace;letter-spacing:.05em}
button{border:0;border-radius:11px;padding:12px 17px;font-weight:850;font-size:1rem;cursor:pointer;background:#f4f7fa;color:#111820}
.entry{background:var(--p2);border:1px solid var(--l);border-radius:13px;padding:15px;margin-top:11px}.head{display:flex;justify-content:space-between;gap:12px;align-items:baseline;flex-wrap:wrap}
.title{font-size:1.14rem;font-weight:900}.prob{color:var(--g);font-weight:850}.hands{font-size:1.15rem;font-weight:850}.play{font-size:1.06rem;margin-top:9px}
.badge{display:inline-block;font-size:.73rem;font-weight:850;padding:2px 8px;border:1px solid #496172;border-radius:999px;margin-left:7px}.exact{border-color:#6c5d2c;color:var(--gold)}
.human{border-color:#347450;color:var(--g)}.pending{border-color:#7d6530;color:var(--warn)}ol{margin:8px 0 0;padding-left:24px}li{margin:5px 0}.info{border-left:3px solid var(--b);padding-left:11px}.error{border-left:3px solid #ff9898;padding-left:11px}
code{font-family:ui-monospace,Consolas,monospace;color:#fff}
</style>
</head>
<body><main>
<h1>Dictionnaire des maniements <span class="badge human">V1 humaine</span></h1>
<p class="muted">Saisis les deux mains en notation française. <b>X = 10</b> ; <b>x = petite carte quelconque de 2 à 7</b>.</p>
<section class="card"><form id="f"><div class="grid">
<div><label>Main 1</label><input id="n" value="ARX9x" autocomplete="off"></div>
<div><label>Main 2</label><input id="s" value="xxx" autocomplete="off"></div>
</div><div style="margin-top:14px"><button>Chercher</button></div></form></section>
<section class="card" id="out"><div class="muted">Chargement…</div></section>
<p class="muted small" id="count"></p>
</main>
<script>
'use strict';
const DB=__DATA__, MAN=__MANIFEST__;
const R={2:2,3:3,4:4,5:5,6:6,7:7,8:8,9:9,T:10,J:11,Q:12,K:13,A:14},REV={2:'2',3:'3',4:'4',5:'5',6:'6',7:'7',8:'8',9:'9',10:'T',11:'J',12:'Q',13:'K',14:'A'};
const nEl=document.getElementById('n'),sEl=document.getElementById('s'),out=document.getElementById('out');
function esc(s){return String(s).replace(/[&<>"']/g,c=>({'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;',"'":'&#39;'}[c]))}
function fr(x){return [...String(x||'')].map(c=>c==='K'?'R':c==='Q'?'D':c==='J'?'V':c==='T'?'X':c).join('')}
function pct(frac){const[a,b]=frac.split('/').map(Number);return 100*a/b}
function swapSid(sid){let c=sid,o=0,m=1;for(let i=0;i<13;i++){let d=c%3;c=Math.floor(c/3);if(d===1)d=2;else if(d===2)d=1;o+=d*m;m*=3}return o}
function swapText(x){return String(x||'').replaceAll('Nord','§N§').replaceAll('Sud','Nord').replaceAll('§N§','Sud').replaceAll('main 1','§M1§').replaceAll('main 2','main 1').replaceAll('§M1§','main 2')}
function normExact(x){let z=String(x||'').toUpperCase().replaceAll('10','T').replaceAll('X','T').replaceAll('R','K').replaceAll('D','Q').replaceAll('V','J').replace(/[ \-_,.\/]/g,'');if(!z)throw Error('Main vide.');let seen=new Set(),v=[];for(const c of z){if(!(c in R))throw Error('Carte invalide : '+c);if(seen.has(c))throw Error('Carte répétée : '+c);seen.add(c);v.push(R[c])}v.sort((a,b)=>b-a);return v.map(x=>REV[x]).join('')}
function enc(n0,s0){const n=normExact(n0),s=normExact(s0),ns=new Set([...n].map(c=>R[c])),ss=new Set([...s].map(c=>R[c]));for(const v of ns)if(ss.has(v))throw Error('Une même carte figure dans les deux mains.');let sid=0,m=1,nm=0,sm=0;for(let r=2;r<=14;r++){let d=0;if(ns.has(r)){d=1;nm|=1<<r}else if(ss.has(r)){d=2;sm|=1<<r}sid+=d*m;m*=3}return{n,s,sid,nm,sm}}
function lookupExact(n,s){const q=enc(n,s),canonical=q.nm<q.sm,rep=canonical?q.sid:swapSid(q.sid);return{q,canonical,rep,st:DB[String(rep)]||null}}
function parsePattern(raw){let z=String(raw||'').replaceAll('10','T').replace(/[ \-_,.\/]/g,'');if(!z)throw Error('Main vide.');let seen=new Set(),exact=[],wild=0;for(const rc of z){if(rc==='x'){wild++;continue}let c=rc.toUpperCase();if(c==='X')c='T';if(c==='R')c='K';if(c==='D')c='Q';if(c==='V')c='J';if(!(c in R))throw Error('Carte invalide : '+rc);if(seen.has(c))throw Error('Carte répétée : '+rc);seen.add(c);exact.push(c)}exact.sort((a,b)=>R[b]-R[a]);return{exact:exact.join(''),wild}}
function choose(a,k,start=0,cur=[],out=[]){if(k===0){out.push([...cur]);return out}for(let i=start;i<=a.length-k;i++){cur.push(a[i]);choose(a,k-1,i+1,cur,out);cur.pop()}return out}
function expandWild(n0,s0){const np=parsePattern(n0),sp=parsePattern(s0),ne=new Set(np.exact),se=new Set(sp.exact);for(const c of ne)if(se.has(c))throw Error('Une même carte figure dans les deux mains.');const used=new Set([...ne,...se]),pool=['2','3','4','5','6','7'].filter(c=>!used.has(c)),need=np.wild+sp.wild;if(need>pool.length)throw Error('Pas assez de petites cartes distinctes pour remplacer tous les x.');let out=[];for(const nc of choose(pool,np.wild)){const ns=new Set(nc),rem=pool.filter(c=>!ns.has(c));for(const sc of choose(rem,sp.wild))out.push({n:np.exact+nc.join(''),s:sp.exact+sc.join('')})}return{np,sp,variants:out}}
function genericText(x){return String(x||'').replace(/\b(le|du|de la|la) ([2-7])\b/g,'une petite carte')}
function patternFr(p){return fr(p.exact)+'x'.repeat(p.wild)}
function entryHtml(t,e,swap=false,family=false){let lines=(e.human_lines||[]).map(x=>swap?swapText(x):x);let h='<div class="entry"><div class="head"><div class="title">Pour '+t+' levée'+(t==='1'?'':'s');if(lines.length&&e.human_status==='COMPACT_EXACT')h+=' <span class="badge human">'+(family?'famille x certifiée':'maniement humain exact')+'</span>';else h+=' <span class="badge exact">probabilité exacte</span>';h+='</div><div class="prob">'+pct(e.p).toFixed(2).replace('.',',')+' %</div></div>';if(lines.length&&e.human_status==='COMPACT_EXACT'){h+='<div class="play"><ol>'+lines.map(x=>'<li>'+esc(family?genericText(x):x)+'</li>').join('')+'</ol></div>'}else if(e.human_status==='EXACT_PREFIX_NONCOMPACT'){h+='<div class="play muted">Le départ optimal est certifié, mais la continuation n’est pas encore assez compacte pour être publiée.</div>'}else if(e.human_status==='NO_EXACT_PREFIX'){h+='<div class="play muted">Probabilité exacte disponible ; maniement humain encore à résoudre.</div>'}else if(e.human_status==='TARGET_TIMEOUT'){h+='<div class="play muted">Probabilité exacte disponible ; humanisation différée (cas coûteux).</div>'}else{h+='<div class="play">'+esc(e.exact||'Calcul exact disponible.')+'</div>'}return h+'</div>'}
function showExact(){const r=lookupExact(nEl.value,sEl.value);nEl.value=fr(r.q.n);sEl.value=fr(r.q.s);if(!r.st){out.innerHTML='<div class="info"><b>Pas encore dans la base humaine V1.</b><br><span class="muted">La base honor-first continue de s’agrandir sur GitHub.</span></div>';return}let h='<div class="hands">Main 1 <code>'+fr(r.q.n)+'</code> — Main 2 <code>'+fr(r.q.s)+'</code></div>';for(const[t,e]of Object.entries(r.st.t).sort((a,b)=>Number(b[0])-Number(a[0])))h+=entryHtml(t,e,!r.canonical,false);out.innerHTML=h}
function showWild(){const ex=expandWild(nEl.value,sEl.value),rows=ex.variants.map(v=>lookupExact(v.n,v.s));nEl.value=patternFr(ex.np);sEl.value=patternFr(ex.sp);if(rows.some(r=>!r.st)){out.innerHTML='<div class="info"><b>Famille x encore incomplète dans la base humaine V1.</b><br><span class="muted">Précise les petites cartes 2–7, ou réessaie plus tard pendant que GitHub enrichit la base.</span></div>';return}const targets=Object.keys(rows[0].st.t).sort((a,b)=>Number(b)-Number(a));let h='<div class="hands">Main 1 <code>'+esc(patternFr(ex.np))+'</code> — Main 2 <code>'+esc(patternFr(ex.sp))+'</code></div>';for(const t of targets){const vals=rows.map(r=>{const e=r.st.t[t];return{p:e.p,status:e.human_status,lines:(e.human_lines||[]).map(x=>genericText(r.canonical?x:swapText(x)))}});const v0=vals[0],same=vals.every(v=>v.p===v0.p&&v.status==='COMPACT_EXACT'&&JSON.stringify(v.lines)===JSON.stringify(v0.lines));if(same){h+=entryHtml(t,{p:v0.p,human_status:'COMPACT_EXACT',human_lines:v0.lines},false,true)}else{h+='<div class="entry"><div class="head"><div class="title">Pour '+t+' levée'+(t==='1'?'':'s')+'</div></div><div class="play muted">Les petites cartes exactes modifient encore le maniement ou toutes les variantes ne sont pas humanisées. Précise les cartes 2–7.</div></div>'}}out.innerHTML=h}
function show(){try{if(String(nEl.value).includes('x')||String(sEl.value).includes('x'))showWild();else showExact()}catch(e){out.innerHTML='<div class="error"><b>Erreur :</b> '+esc(e.message||e)+'</div>'}}
document.getElementById('f').onsubmit=e=>{e.preventDefault();show()};
document.getElementById('count').textContent=MAN.state_count.toLocaleString('fr-FR')+' combinaisons honor-first · '+MAN.compact_targets.toLocaleString('fr-FR')+' objectifs avec maniement humain compact exact';
show();
</script></body></html>'''


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--repo", default=".")
    ap.add_argument("--output-dir", required=True)
    a = ap.parse_args()
    repo = Path(a.repo)
    out = Path(a.output_dir)
    out.mkdir(parents=True, exist_ok=True)

    exact = load_exact(repo)
    human, deferred, worker_states = load_human(repo)
    payload, stats = build_payload(exact, human, deferred)
    manifest = {
        "schema": "MANIEMENTS_V5_HUMAN_DICTIONARY_WEB_V1",
        "generated_at_utc": datetime.datetime.now(datetime.timezone.utc).replace(microsecond=0).isoformat(),
        **stats,
        "worker_states_seen": len(worker_states),
        "priority": "HONOR_FIRST_AKQJT_2_TO_4_TOTAL_5_TO_8",
    }
    html = INDEX.replace("__DATA__", json.dumps(payload, ensure_ascii=False, separators=(",", ":")))
    html = html.replace("__MANIFEST__", json.dumps(manifest, ensure_ascii=False, separators=(",", ":")))
    (out / "MANIEMENTS_V5_DICTIONNAIRE_HUMAIN_V1.html").write_text(html, encoding="utf-8")
    (out / "manifest.json").write_text(json.dumps(manifest, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    (out / "worker_states.json").write_text(json.dumps(worker_states, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(json.dumps(manifest, ensure_ascii=False, sort_keys=True))


if __name__ == "__main__":
    main()

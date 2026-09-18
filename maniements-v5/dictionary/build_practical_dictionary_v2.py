#!/usr/bin/env python3
from __future__ import annotations

import argparse
import datetime
import json
import subprocess
from pathlib import Path

P1_PREFIX = "maniements-v5-dictionary-v3-p1-"
P2_PREFIX = "maniements-v5-practical-family-v2-"
HUMAN_V1_PREFIX = "maniements-v5-human-v1-p1-"
HONORS = set("AKQJT")
LOW = set("234567")
RANK = {c: i for i, c in enumerate("23456789TJQKA", start=2)}


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


def iter_jsonl_ref(repo: Path, ref: str, prefix: str):
    for p in list_paths(repo, ref, prefix):
        if not p.endswith(".jsonl"):
            continue
        for line in git_text(repo, ref, p).splitlines():
            if line.strip():
                yield json.loads(line)


def exact_key(n, s):
    return "|".join(sorted((n, s)))


def family_hand(hand):
    return "".join("x" if c in LOW else c for c in hand)


def family_key(n, s):
    return "|".join(sorted((family_hand(n), family_hand(s))))


def eligible_p1(n, s):
    total = len(n) + len(s)
    h = sum(c in HONORS for c in n + s)
    return 5 <= total <= 7 and 2 <= h <= 4


def add_exact(db, n, s, target, probability):
    k = exact_key(n, s)
    st = db.setdefault(k, {"n": n, "s": s, "t": {}})
    st["t"][str(target)] = {"p": probability}


def load_p1(repo: Path, db):
    for w in range(20):
        ref = f"refs/remotes/origin/{P1_PREFIX}{w:02d}"
        for r in iter_jsonl_ref(repo, ref, "dictionary/chunks"):
            n, s = r["north"], r["south"]
            if not eligible_p1(n, s):
                continue
            add_exact(db, n, s, int(r["target"]), r["probability_fraction"])


def load_p2(repo: Path, db, famdb):
    families = 0
    for w in range(20):
        ref = f"refs/remotes/origin/{P2_PREFIX}{w:02d}"
        for p in list_paths(repo, ref, "family_v2/families"):
            if not p.endswith(".json"):
                continue
            r = json.loads(git_text(repo, ref, p))
            families += 1
            fk = "|".join(sorted((r["north_pattern"], r["south_pattern"])))
            famdb[fk] = {
                "n": r["north_pattern"],
                "s": r["south_pattern"],
                "targets": r["targets"],
                "variant_count": r["variant_count"],
                "priority_rank": r["priority_rank"],
            }
            for v in r["variants"]:
                for t, prob in v["curve"].items():
                    add_exact(db, v["north"], v["south"], int(t), prob)
    return families


def load_human_overlay(repo: Path):
    # V1 records are intentionally NOT published. Only future records carrying
    # publication_ready=true may appear in the V2 dictionary.
    out = {}
    legacy = 0
    for w in range(20):
        ref = f"refs/remotes/origin/{HUMAN_V1_PREFIX}{w:02d}"
        for r in iter_jsonl_ref(repo, ref, "human/chunks"):
            legacy += 1
            if not r.get("publication_ready"):
                continue
            k = (exact_key(r["north"], r["south"]), str(r["target"]))
            out[k] = {
                "lines": r.get("full_lines") or [],
                "audit": r.get("publication_audit") or {},
            }
    return out, legacy


def apply_human(db, human):
    n = 0
    for (k, t), h in human.items():
        if k in db and t in db[k]["t"]:
            db[k]["t"][t]["human"] = h["lines"]
            n += 1
    return n


INDEX = r'''<!doctype html><html lang="fr"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1">
<title>Dictionnaire des maniements — V2 pratique</title>
<style>
:root{color-scheme:dark;--bg:#0b0f14;--p:#151b23;--p2:#10161d;--l:#2b3542;--t:#eef4fa;--m:#98a6b5;--g:#77e3aa;--b:#86c2ff;--gold:#e7c46a;--warn:#f0b34f}
*{box-sizing:border-box}body{margin:0;background:var(--bg);color:var(--t);font:16px/1.5 system-ui,-apple-system,Segoe UI,Roboto,sans-serif}main{max-width:900px;margin:auto;padding:30px 16px 70px}
h1{margin:0 0 5px;font-size:clamp(1.7rem,4vw,2.35rem)}.muted{color:var(--m)}.small{font-size:.88rem}.card{background:var(--p);border:1px solid var(--l);border-radius:15px;padding:18px;margin-top:16px}
.grid{display:grid;grid-template-columns:1fr;gap:14px}@media(min-width:650px){.grid{grid-template-columns:1fr 1fr}}label{display:block;font-weight:800;margin-bottom:6px}
input{width:100%;padding:13px 14px;border:1px solid #3c4959;border-radius:11px;background:#0a1016;color:#fff;font:800 1.2rem ui-monospace,Consolas,monospace;letter-spacing:.05em}
button{border:0;border-radius:11px;padding:12px 17px;font-weight:850;font-size:1rem;cursor:pointer;background:#f4f7fa;color:#111820}.entry{background:var(--p2);border:1px solid var(--l);border-radius:13px;padding:15px;margin-top:11px}
.head{display:flex;justify-content:space-between;gap:12px;align-items:baseline;flex-wrap:wrap}.title{font-size:1.14rem;font-weight:900}.prob{color:var(--g);font-weight:850}.play{font-size:1.06rem;margin-top:9px}.hands{font-size:1.15rem;font-weight:850}
.badge{display:inline-block;font-size:.73rem;font-weight:850;padding:2px 8px;border:1px solid #496172;border-radius:999px;margin-left:7px}.exact{border-color:#6c5d2c;color:var(--gold)}.human{border-color:#347450;color:var(--g)}.pending{border-color:#7d6530;color:var(--warn)}
.info{border-left:3px solid var(--b);padding-left:11px}.error{border-left:3px solid #ff9898;padding-left:11px}code{font-family:ui-monospace,Consolas,monospace;color:#fff}ol{margin:8px 0 0;padding-left:24px}
</style></head><body><main>
<h1>Dictionnaire des maniements <span class="badge exact">V2 pratique</span></h1>
<p class="muted">Notation française : <b>A R D V X</b>. <b>X = 10</b> ; <b>x = petite carte quelconque de 2 à 7</b>.</p>
<section class="card"><form id="f"><div class="grid"><div><label>Main 1</label><input id="n" value="ARX9x" autocomplete="off"></div><div><label>Main 2</label><input id="s" value="xxx" autocomplete="off"></div></div><div style="margin-top:14px"><button>Chercher</button></div></form></section>
<section class="card" id="out"><div class="muted">Chargement…</div></section><p class="muted small" id="count"></p>
<script>
'use strict';
const DB=__DB__, FAM=__FAM__, MAN=__MAN__;
const R={2:2,3:3,4:4,5:5,6:6,7:7,8:8,9:9,T:10,J:11,Q:12,K:13,A:14},REV={2:'2',3:'3',4:'4',5:'5',6:'6',7:'7',8:'8',9:'9',10:'T',11:'J',12:'Q',13:'K',14:'A'};
const nEl=document.getElementById('n'),sEl=document.getElementById('s'),out=document.getElementById('out');
function esc(s){return String(s).replace(/[&<>"']/g,c=>({'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;',"'":'&#39;'}[c]))}
function fr(x){return [...String(x||'')].map(c=>c==='K'?'R':c==='Q'?'D':c==='J'?'V':c==='T'?'X':c).join('')}
function pct(fr){const[a,b]=String(fr).split('/').map(Number);return 100*a/b}
function sortHand(z){return [...z].sort((a,b)=>R[b]-R[a]).join('')}
function normExact(raw){let z=String(raw||'').toUpperCase().replaceAll('10','T').replaceAll('X','T').replaceAll('R','K').replaceAll('D','Q').replaceAll('V','J').replace(/[ \-_,.\/]/g,'');if(!z)throw Error('Main vide.');let seen=new Set();for(const c of z){if(!(c in R))throw Error('Carte invalide : '+c);if(seen.has(c))throw Error('Carte répétée : '+c);seen.add(c)}return sortHand(z)}
function ekey(n,s){return [n,s].sort().join('|')}
function parsePattern(raw){let z=String(raw||'').replaceAll('10','T').replace(/[ \-_,.\/]/g,'');if(!z)throw Error('Main vide.');let seen=new Set(),ex=[],wild=0;for(const rc of z){if(rc==='x'){wild++;continue}let c=rc.toUpperCase();if(c==='X')c='T';if(c==='R')c='K';if(c==='D')c='Q';if(c==='V')c='J';if(!(c in R))throw Error('Carte invalide : '+rc);if(seen.has(c))throw Error('Carte répétée : '+rc);seen.add(c);ex.push(c)}return{exact:sortHand(ex.join('')),wild}}
function patText(p){return fr(p.exact)+'x'.repeat(p.wild)}
function fkey(np,sp){return [np,sp].sort().join('|')}
function choose(a,k,start=0,cur=[],out=[]){if(k===0){out.push([...cur]);return out}for(let i=start;i<=a.length-k;i++){cur.push(a[i]);choose(a,k-1,i+1,cur,out);cur.pop()}return out}
function expand(np,sp){const used=new Set([...np.exact,...sp.exact]),pool=['2','3','4','5','6','7'].filter(c=>!used.has(c));if(np.wild+sp.wild>pool.length)throw Error('Pas assez de petites cartes distinctes.');let o=[];for(const nc of choose(pool,np.wild)){const rem=pool.filter(c=>!nc.includes(c));for(const sc of choose(rem,sp.wild))o.push([sortHand(np.exact+nc.join('')),sortHand(sp.exact+sc.join(''))])}return o}
function entry(t,e,family=false){let h='<div class="entry"><div class="head"><div class="title">Pour '+t+' levée'+(t==='1'?'':'s');if(e.human&&e.human.length)h+=' <span class="badge human">maniement humain validé</span>';else h+=' <span class="badge exact">probabilité exacte</span>';h+='</div><div class="prob">'+pct(e.p).toFixed(2).replace('.',',')+' %</div></div>';if(e.human&&e.human.length)h+='<div class="play"><ol>'+e.human.map(x=>'<li>'+esc(x)+'</li>').join('')+'</ol></div>';else if(e.p==='1/1')h+='<div class="play muted">Objectif assuré à 100 %. Le maniement pédagogique sera ajouté seulement après validation humaine.</div>';else h+='<div class="play muted">Maniement humain en cours de certification.</div>';return h+'</div>'}
function showExact(){const n=normExact(nEl.value),s=normExact(sEl.value);for(const c of n)if(s.includes(c))throw Error('Une même carte figure dans les deux mains.');nEl.value=fr(n);sEl.value=fr(s);const st=DB[ekey(n,s)];if(!st){out.innerHTML='<div class="info"><b>Cette combinaison exacte n’est pas encore calculée dans la base pratique.</b><br><span class="muted">Les 5–3 et 4–4 sont maintenant calculés en priorité dans V2.</span></div>';return}let h='<div class="hands">Main 1 <code>'+fr(n)+'</code> — Main 2 <code>'+fr(s)+'</code></div>';for(const[t,e]of Object.entries(st.t).sort((a,b)=>Number(b[0])-Number(a[0])))h+=entry(t,e,false);out.innerHTML=h}
function showWild(){const np=parsePattern(nEl.value),sp=parsePattern(sEl.value),nk=patText(np),sk=patText(sp);nEl.value=nk;sEl.value=sk;const direct=FAM[fkey(nk.replaceAll('R','K').replaceAll('D','Q').replaceAll('V','J').replaceAll('X','T'),sk.replaceAll('R','K').replaceAll('D','Q').replaceAll('V','J').replaceAll('X','T'))];if(direct){let h='<div class="hands">Main 1 <code>'+esc(nk)+'</code> — Main 2 <code>'+esc(sk)+'</code></div><div class="muted small">'+direct.variant_count+' affectations concrètes des petites cartes vérifiées.</div>';for(const[t,x]of Object.entries(direct.targets).sort((a,b)=>Number(b[0])-Number(a[0]))){if(x.generic)h+=entry(t,{p:x.probability_fraction},true);else h+='<div class="entry"><div class="head"><div class="title">Pour '+t+' levée'+(t==='1'?'':'s')+'</div></div><div class="play muted">Les petites cartes exactes influencent la probabilité : précise les cartes 2–7.</div></div>'}out.innerHTML=h;return}
const vars=expand(np,sp),rows=vars.map(([n,s])=>DB[ekey(n,s)]);if(rows.some(x=>!x)){out.innerHTML='<div class="info"><b>Famille x encore incomplète.</b><br><span class="muted">Toutes les affectations 2–7 ne sont pas encore calculées.</span></div>';return}const targets=Object.keys(rows[0].t).sort((a,b)=>Number(b)-Number(a));let h='<div class="hands">Main 1 <code>'+esc(nk)+'</code> — Main 2 <code>'+esc(sk)+'</code></div><div class="muted small">'+rows.length+' affectations concrètes vérifiées.</div>';for(const t of targets){const vals=rows.map(r=>r.t[t]?.p);if(vals.every(x=>x===vals[0]))h+=entry(t,{p:vals[0]},true);else h+='<div class="entry"><div class="head"><div class="title">Pour '+t+' levée'+(t==='1'?'':'s')+'</div></div><div class="play muted">Les petites cartes exactes influencent la probabilité : précise les cartes 2–7.</div></div>'}out.innerHTML=h}
function show(){try{if(String(nEl.value).includes('x')||String(sEl.value).includes('x'))showWild();else showExact()}catch(e){out.innerHTML='<div class="error"><b>Erreur :</b> '+esc(e.message||e)+'</div>'}}
document.getElementById('f').onsubmit=e=>{e.preventDefault();show()};document.getElementById('count').textContent=MAN.exact_state_count.toLocaleString('fr-FR')+' combinaisons exactes · '+MAN.family_count.toLocaleString('fr-FR')+' familles x V2 · '+MAN.published_human_targets.toLocaleString('fr-FR')+' maniements humains publiés';show();
</script></main></body></html>'''


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--repo", default=".")
    ap.add_argument("--output-dir", required=True)
    a = ap.parse_args()
    repo = Path(a.repo)
    db, famdb = {}, {}
    load_p1(repo, db)
    p2_count = load_p2(repo, db, famdb)
    human, legacy = load_human_overlay(repo)
    published = apply_human(db, human)
    manifest = {
        "schema": "MANIEMENTS_V5_PRACTICAL_DICTIONARY_V2",
        "generated_at_utc": datetime.datetime.now(datetime.timezone.utc).replace(microsecond=0).isoformat(),
        "exact_state_count": len(db),
        "family_count": len(famdb),
        "p2_family_files": p2_count,
        "published_human_targets": published,
        "legacy_human_candidates_hidden": legacy,
        "publication_rule": "probabilities exact; human lines only with publication_ready semantic audit",
    }
    out = Path(a.output_dir)
    out.mkdir(parents=True, exist_ok=True)
    html = INDEX.replace("__DB__", json.dumps(db, ensure_ascii=False, separators=(",", ":")))
    html = html.replace("__FAM__", json.dumps(famdb, ensure_ascii=False, separators=(",", ":")))
    html = html.replace("__MAN__", json.dumps(manifest, ensure_ascii=False, separators=(",", ":")))
    (out / "MANIEMENTS_V5_DICTIONNAIRE_PRATIQUE_V2.html").write_text(html, encoding="utf-8")
    (out / "manifest.json").write_text(json.dumps(manifest, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(json.dumps(manifest, ensure_ascii=False, sort_keys=True))


if __name__ == "__main__":
    main()

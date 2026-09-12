#!/usr/bin/env python3
from __future__ import annotations
import argparse, datetime, json, subprocess
from pathlib import Path

SHARD_SIZE = 256
SCHEMA = 'MANIEMENTS_V5_DICTIONARY_WEB_V3'


def git_text(repo: Path, ref: str, path: str) -> str:
    return subprocess.check_output(['git','-C',str(repo),'show',f'{ref}:{path}'], text=True)


def list_paths(repo: Path, ref: str, prefix: str):
    try:
        out = subprocess.check_output(['git','-C',str(repo),'ls-tree','-r','--name-only',ref,prefix], text=True, stderr=subprocess.DEVNULL)
    except subprocess.CalledProcessError:
        return []
    return [x for x in out.splitlines() if x]


def iter_branch_entries(repo: Path, branch_prefix: str):
    for w in range(20):
        ref = f'refs/remotes/origin/{branch_prefix}{w:02d}'
        for p in list_paths(repo, ref, 'dictionary/chunks'):
            if not p.endswith('.jsonl'):
                continue
            for line in git_text(repo, ref, p).splitlines():
                if line.strip():
                    yield json.loads(line)


def iter_input_entries(input_root: Path):
    for p in sorted((input_root/'dictionary'/'chunks').glob('chunk_*.jsonl')):
        with p.open(encoding='utf-8') as f:
            for line in f:
                if line.strip():
                    yield json.loads(line)


def slim_entry(r):
    c = r['compact']
    out = {
        'p': r['probability_fraction'],
        'x': c.get('summary_fr') or '',
        'coverage': c.get('coverage'),
        'pattern': c.get('pattern'),
    }
    if c.get('lead'):
        out['lead'] = c['lead']
    if c.get('policy_program'):
        out['pp'] = c['policy_program']
    if c.get('program_stats'):
        out['stats'] = c['program_stats']
    return out


def write_site(entries, outdir: Path):
    states = {}
    targets = 0
    for r in entries:
        sid = int(r['state_id']); t = int(r['target'])
        st = states.setdefault(str(sid), {'n': r['north'], 's': r['south'], 't': {}})
        st['t'][str(t)] = slim_entry(r)
        targets += 1

    data_dir = outdir/'data'; data_dir.mkdir(parents=True, exist_ok=True)
    shards = {}
    for sid, st in states.items():
        shard = int(sid)//SHARD_SIZE
        shards.setdefault(shard, {})[sid] = st
    for shard, shard_states in shards.items():
        p = data_dir/f'{shard:05d}.json'
        p.write_text(json.dumps({'states': shard_states}, ensure_ascii=False, separators=(',',':'))+'\n', encoding='utf-8')

    manifest = {
        'schema': SCHEMA,
        'generated_at_utc': datetime.datetime.now(datetime.timezone.utc).replace(microsecond=0).isoformat(),
        'state_count': len(states),
        'target_count': targets,
        'shard_size': SHARD_SIZE,
        'shard_count': len(shards),
    }
    (outdir/'manifest.json').write_text(json.dumps(manifest, ensure_ascii=False, separators=(',',':'))+'\n', encoding='utf-8')
    (outdir/'index.html').write_text(INDEX_HTML.replace('__SHARD_SIZE__', str(SHARD_SIZE)), encoding='utf-8')
    return manifest


INDEX_HTML = r'''<!doctype html><html lang="fr"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1"><title>Dictionnaire des maniements V3</title><style>
:root{color-scheme:dark;--bg:#0b0f14;--p:#151b23;--p2:#10161d;--l:#2b3542;--t:#eef4fa;--m:#98a6b5;--g:#77e3aa;--b:#86c2ff;--gold:#e7c46a}*{box-sizing:border-box}body{margin:0;background:var(--bg);color:var(--t);font:16px/1.5 system-ui,-apple-system,Segoe UI,Roboto,sans-serif}main{max-width:860px;margin:auto;padding:32px 16px 70px}h1{margin:0 0 5px;font-size:clamp(1.7rem,4vw,2.35rem)}.muted{color:var(--m)}.card{background:var(--p);border:1px solid var(--l);border-radius:15px;padding:18px;margin-top:16px}.grid{display:grid;grid-template-columns:1fr;gap:14px}@media(min-width:650px){.grid{grid-template-columns:1fr 1fr}}label{display:block;font-weight:800;margin-bottom:6px}input{width:100%;padding:13px 14px;border:1px solid #3c4959;border-radius:11px;background:#0a1016;color:#fff;font:800 1.2rem ui-monospace,Consolas,monospace;text-transform:uppercase;letter-spacing:.05em}button{border:0;border-radius:11px;padding:12px 17px;font-weight:850;font-size:1rem;cursor:pointer;background:#f4f7fa;color:#111820}.entry{background:var(--p2);border:1px solid var(--l);border-radius:13px;padding:15px;margin-top:11px}.head{display:flex;justify-content:space-between;gap:12px;align-items:baseline;flex-wrap:wrap}.title{font-size:1.14rem;font-weight:900}.prob{color:var(--g);font-weight:850}.play{font-size:1.08rem;margin-top:9px}.hands{font-size:1.15rem;font-weight:850}code{font-family:ui-monospace,Consolas,monospace;color:#fff}.error{border-left:3px solid #ff9898;padding-left:11px}.info{border-left:3px solid var(--b);padding-left:11px}.badge{display:inline-block;font-size:.75rem;font-weight:850;padding:2px 8px;border:1px solid #496172;border-radius:999px;color:#b9d8ee;margin-left:7px}.badge.exact{border-color:#6c5d2c;color:var(--gold)}details{margin-top:12px;border-top:1px solid #29333f;padding-top:10px}summary{cursor:pointer;font-weight:850;color:#dbeafb}.ctx{margin:10px 0;padding:10px 12px;background:#0c1219;border-left:3px solid #46576a;border-radius:8px}.ctx-title{font-weight:800;margin-bottom:5px}.decision{margin:4px 0 0 0}.branch{margin:6px 0 0 16px;padding-left:12px;border-left:1px solid #34414e}.yes{color:#c8eed7}.no{color:#d8dce0}.small{font-size:.88rem}.loading{opacity:.75}
</style></head><body><main><h1>Dictionnaire des maniements <span class="badge exact">V3 exact</span></h1><p class="muted">Entre les deux mains en notation française : A, R, D, V, X…</p><section class="card"><form id="f"><div class="grid"><div><label>Nord</label><input id="n" value="764" autocomplete="off"></div><div><label>Sud</label><input id="s" value="9532" autocomplete="off"></div></div><div style="margin-top:14px"><button>Chercher</button></div></form></section><section class="card" id="out"><div class="muted">Chargement…</div></section><p class="muted small" id="count"></p></main><script>
'use strict';
const SHARD_SIZE=__SHARD_SIZE__,R={2:2,3:3,4:4,5:5,6:6,7:7,8:8,9:9,T:10,J:11,Q:12,K:13,A:14},REV={2:'2',3:'3',4:'4',5:'5',6:'6',7:'7',8:'8',9:'9',10:'T',11:'J',12:'Q',13:'K',14:'A'};
const nEl=document.getElementById('n'),sEl=document.getElementById('s'),out=document.getElementById('out'),count=document.getElementById('count'),cache=new Map();let MAN=null;
function norm(x){let z=String(x||'').toUpperCase().replaceAll('10','T').replaceAll('X','T').replaceAll('R','K').replaceAll('D','Q').replaceAll('V','J').replace(/[ \-_,.\/]/g,'');if(!z)throw Error('Main vide.');let seen=new Set(),v=[];for(const c of z){if(!(c in R))throw Error('Carte invalide : '+c);if(seen.has(c))throw Error('Carte répétée : '+c);seen.add(c);v.push(R[c])}v.sort((a,b)=>b-a);return v.map(x=>REV[x]).join('')}
function fr(x){if(x==='-')return '—';return [...x].map(c=>c==='K'?'R':c==='Q'?'D':c==='J'?'V':c==='T'?'X':c).join('')}
function enc(n0,s0){const n=norm(n0),s=norm(s0),ns=new Set([...n].map(c=>R[c])),ss=new Set([...s].map(c=>R[c]));for(const v of ns)if(ss.has(v))throw Error('Une même carte figure dans les deux mains.');let sid=0,m=1,nm=0,sm=0;for(let r=2;r<=14;r++){let d=0;if(ns.has(r)){d=1;nm|=1<<r}else if(ss.has(r)){d=2;sm|=1<<r}sid+=d*m;m*=3}return{n,s,sid,nm,sm}}
function swapSid(sid){let c=sid,o=0,m=1;for(let i=0;i<13;i++){let d=c%3;c=Math.floor(c/3);if(d===1)d=2;else if(d===2)d=1;o+=d*m;m*=3}return o}
function swapSeat(s){return s==='N'?'S':s==='S'?'N':s==='E'?'W':s==='W'?'E':s}
function seatFr(s){return {N:'Nord',S:'Sud',E:'Est',W:'Ouest'}[s]||s}
function swapText(x){return String(x||'').replaceAll('Nord','§N§').replaceAll('Sud','Nord').replaceAll('§N§','Sud').replaceAll('Est','§E§').replaceAll('Ouest','Est').replaceAll('§E§','Ouest')}
function pct(frac){const[a,b]=frac.split('/').map(Number);return 100*a/b}
function rankFr(r){return {A:"l’As",K:'le Roi',Q:'la Dame',J:'le Valet',T:'le 10'}[r]||'le '+r}
function actionFr(a,sw){if(!a)return '—';let [s,r]=a.split(':');if(sw)s=swapSeat(s);if(r==='-')return seatFr(s)+' est chicane';return 'jouer '+rankFr(r)+' de '+seatFr(s)}
function featureFr(f,sw){let p=f.split('_');if(sw){if(p[0]==='W')p[0]='E';else if(p[0]==='E')p[0]='W';if(p[0]==='CUR'){if(p[1]==='W')p[1]='E';else if(p[1]==='E')p[1]='W'}}const side=x=>x==='W'?'Ouest':'Est';if(p[0]==='W'&&p[1]==='VOID'||p[0]==='E'&&p[1]==='VOID')return side(p[0])+' a déjà montré une chicane';if((p[0]==='W'||p[0]==='E')&&p[1]==='SEEN')return side(p[0])+' a déjà fourni '+rankFr(p[2]);if(p[0]==='CUR'){if(p[2]==='-')return side(p[1])+' défausse sur ce tour';return side(p[1])+' fournit '+rankFr(p[2])+' sur ce tour'}return f}
function esc(s){return String(s).replace(/[&<>"']/g,c=>({'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;',"'":'&#39;'}[c]))}
function decisionHtml(v,sw){if(typeof v==='string')return '<div class="decision">→ '+esc(actionFr(v,sw))+'</div>';const [feat,no,yes]=v,cond=featureFr(feat,sw);return '<div class="decision"><b>Si '+esc(cond)+'</b><div class="branch yes">Oui : '+decisionHtml(yes,sw)+'</div><div class="branch no">Sinon : '+decisionHtml(no,sw)+'</div></div>'}
function contextHtml(k,v,sw,initial){let [nr,sr,leader,pos,won,trick]=k;if(sw){[nr,sr]=[sr,nr];leader=swapSeat(leader);trick=trick.map(([s,c])=>[swapSeat(s),c])}const used=(initial[0].replace('-','').length+initial[1].replace('-','').length)-(nr.replace('-','').length+sr.replace('-','').length);let bits=[];bits.push('Nord '+fr(nr)+' · Sud '+fr(sr));if(won)bits.push(won+' levée'+(won>1?'s':'')+' déjà gagnée'+(won>1?'s':''));if(trick.length){bits.push('tour en cours : '+trick.map(([s,c])=>seatFr(s)+' '+(c==='*'?'a fourni une carte':fr(c))).join(', '))}else bits.push('nouvelle levée');return '<div class="ctx"><div class="ctx-title">Étape '+(used+1)+'</div><div class="muted small">'+esc(bits.join(' · '))+'</div>'+decisionHtml(v,sw)+'</div>'}
function policyHtml(pp,sw){let initial=[pp.case[0],pp.case[1]];if(sw)initial=[initial[1],initial[0]];let rows=[...pp.contexts];rows.sort((a,b)=>{const ka=a[0],kb=b[0];const ua=(pp.case[0].replace('-','').length+pp.case[1].replace('-','').length)-(ka[0].replace('-','').length+ka[1].replace('-','').length),ub=(pp.case[0].replace('-','').length+pp.case[1].replace('-','').length)-(kb[0].replace('-','').length+kb[1].replace('-','').length);return ua-ub||ka[4]-kb[4]||String(ka).localeCompare(String(kb))});return rows.map(([k,v])=>contextHtml(k,v,sw,initial)).join('')}
async function loadShard(rep){const id=Math.floor(rep/SHARD_SIZE),key=String(id).padStart(5,'0');if(cache.has(key))return cache.get(key);let r=await fetch('data/'+key+'.json',{cache:'no-store'});if(r.status===404){cache.set(key,{states:{}});return cache.get(key)}if(!r.ok)throw Error('Impossible de charger la fiche ('+r.status+').');let d=await r.json();cache.set(key,d);return d}
async function show(){try{out.classList.add('loading');const q=enc(nEl.value,sEl.value);nEl.value=fr(q.n);sEl.value=fr(q.s);const canonical=q.nm<q.sm,rep=canonical?q.sid:swapSid(q.sid),sh=await loadShard(rep),st=sh.states[String(rep)];if(!st){out.innerHTML='<div class="info"><b>Cette fiche V3 n’est pas encore matérialisée.</b><br><span class="muted">La base se complète automatiquement pendant le calcul.</span></div>';return}let h='<div class="hands">Nord <code>'+fr(q.n)+'</code> — Sud <code>'+fr(q.s)+'</code></div>';const ts=Object.entries(st.t).sort((a,b)=>Number(b[0])-Number(a[0]));for(const[t,e]of ts){let txt=canonical?e.x:swapText(e.x),exact=e.coverage==='EXACT_POLICY_PROGRAM';h+='<div class="entry"><div class="head"><div class="title">Pour '+t+' levée'+(t==='1'?'':'s')+(exact?' <span class="badge exact">politique exacte</span>':'')+'</div><div class="prob">'+pct(e.p).toFixed(2).replace('.',',')+' %</div></div><div class="play">'+esc(txt)+'</div>';if(e.pp)h+='<details><summary>Voir le maniement complet</summary>'+policyHtml(e.pp,!canonical)+'</details>';h+='</div>'}out.innerHTML=h}catch(e){out.innerHTML='<div class="error"><b>Erreur :</b> '+esc(e.message||e)+'</div>'}finally{out.classList.remove('loading')}}
async function boot(){try{MAN=await fetch('manifest.json',{cache:'no-store'}).then(r=>r.json());count.textContent=MAN.state_count.toLocaleString('fr-FR')+' configurations · '+MAN.target_count.toLocaleString('fr-FR')+' objectifs V3 matérialisés · '+MAN.shard_count.toLocaleString('fr-FR')+' fragments';await show()}catch(e){out.innerHTML='<div class="error"><b>Erreur de chargement :</b> '+esc(e.message||e)+'</div>'}}
document.getElementById('f').onsubmit=e=>{e.preventDefault();show()};boot();
</script></body></html>'''


def main():
    ap=argparse.ArgumentParser()
    ap.add_argument('--repo', default='.')
    ap.add_argument('--output-dir', required=True)
    ap.add_argument('--branch-prefix', default='maniements-v5-dictionary-v3-p1-')
    ap.add_argument('--input-root')
    a=ap.parse_args()
    if a.input_root:
        entries=iter_input_entries(Path(a.input_root))
    else:
        entries=iter_branch_entries(Path(a.repo), a.branch_prefix)
    outdir=Path(a.output_dir); outdir.mkdir(parents=True,exist_ok=True)
    manifest=write_site(entries,outdir)
    print(json.dumps(manifest, ensure_ascii=False, sort_keys=True))

if __name__=='__main__': main()

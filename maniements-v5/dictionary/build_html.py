#!/usr/bin/env python3
from __future__ import annotations
import argparse, json, subprocess
from pathlib import Path

def git_text(repo,ref,path):
    return subprocess.check_output(['git','-C',str(repo),'show',f'{ref}:{path}'],text=True)

def list_paths(repo,ref,prefix):
    try:
        out=subprocess.check_output(['git','-C',str(repo),'ls-tree','-r','--name-only',ref,prefix],text=True)
    except subprocess.CalledProcessError:
        return []
    return [x for x in out.splitlines() if x]

def main():
    ap=argparse.ArgumentParser(); ap.add_argument('--repo',default='.'); ap.add_argument('--output',required=True); a=ap.parse_args(); repo=Path(a.repo)
    states={}; targets=0
    for w in range(20):
        ref=f'refs/remotes/origin/maniements-v5-dictionary-p1-{w:02d}'
        for p in list_paths(repo,ref,'dictionary/chunks'):
            if not p.endswith('.jsonl'): continue
            for line in git_text(repo,ref,p).splitlines():
                if not line.strip(): continue
                r=json.loads(line); sid=int(r['state_id']); t=int(r['target'])
                st=states.setdefault(str(sid),{'n':r['north'],'s':r['south'],'t':{}})
                st['t'][str(t)]={'p':r['probability_fraction'],'x':r['compact']['summary_fr']}
                targets+=1
    data={'states':states,'state_count':len(states),'target_count':targets}
    payload=json.dumps(data,ensure_ascii=False,separators=(',',':')).replace('</script>','<\\/script>')
    template='''<!doctype html><html lang="fr"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1"><title>Dictionnaire des maniements</title><style>:root{color-scheme:dark;--bg:#0b0f14;--p:#151b23;--p2:#10161d;--l:#2b3542;--t:#eef4fa;--m:#98a6b5;--g:#77e3aa;--b:#86c2ff}*{box-sizing:border-box}body{margin:0;background:var(--bg);color:var(--t);font:16px/1.5 system-ui,-apple-system,Segoe UI,Roboto,sans-serif}main{max-width:880px;margin:auto;padding:32px 16px 70px}h1{margin:0 0 5px;font-size:clamp(1.7rem,4vw,2.35rem)}.muted{color:var(--m)}.card{background:var(--p);border:1px solid var(--l);border-radius:15px;padding:18px;margin-top:16px}.grid{display:grid;grid-template-columns:1fr 1fr;gap:14px}label{display:block;font-weight:800;margin-bottom:6px}input{width:100%;padding:13px 14px;border:1px solid #3c4959;border-radius:11px;background:#0a1016;color:#fff;font:800 1.2rem ui-monospace,Consolas,monospace;text-transform:uppercase;letter-spacing:.05em}button{border:0;border-radius:11px;padding:12px 17px;font-weight:850;font-size:1rem;cursor:pointer;background:#f4f7fa;color:#111820}.entry{background:var(--p2);border:1px solid var(--l);border-radius:13px;padding:15px;margin-top:11px}.head{display:flex;justify-content:space-between;gap:12px;align-items:baseline;flex-wrap:wrap}.title{font-size:1.14rem;font-weight:900}.prob{color:var(--g);font-weight:850}.play{font-size:1.08rem;margin-top:9px}.hands{font-size:1.15rem;font-weight:850}code{font-family:ui-monospace,Consolas,monospace;color:#fff}.error{border-left:3px solid #ff9898;padding-left:11px}.info{border-left:3px solid var(--b);padding-left:11px}@media(max-width:650px){.grid{grid-template-columns:1fr}}</style></head><body><main><h1>Dictionnaire des maniements</h1><p class="muted">Entre les deux mains en notation française : A, R, D, V, 10…</p><section class="card"><form id="f"><div class="grid"><div><label>Nord</label><input id="n" value="AD2" autocomplete="off"></div><div><label>Sud</label><input id="s" value="V963" autocomplete="off"></div></div><div style="margin-top:14px"><button>Chercher</button></div></form></section><section class="card" id="out"></section><p class="muted" style="font-size:.82rem" id="count"></p></main><script id="data" type="application/json">__DATA__</script><script>'use strict';const DB=JSON.parse(document.getElementById('data').textContent),R={2:2,3:3,4:4,5:5,6:6,7:7,8:8,9:9,T:10,J:11,Q:12,K:13,A:14},REV={2:'2',3:'3',4:'4',5:'5',6:'6',7:'7',8:'8',9:'9',10:'T',11:'J',12:'Q',13:'K',14:'A'};const nEl=document.getElementById('n'),sEl=document.getElementById('s'),out=document.getElementById('out');function norm(x){let z=String(x||'').toUpperCase().replaceAll('10','T').replaceAll('R','K').replaceAll('D','Q').replaceAll('V','J').replace(/[ \\-_,.\\/]/g,'');if(!z)throw Error('Main vide.');let seen=new Set(),v=[];for(const c of z){if(!(c in R))throw Error('Carte invalide : '+c);if(seen.has(c))throw Error('Carte répétée : '+c);seen.add(c);v.push(R[c])}v.sort((a,b)=>b-a);return v.map(x=>REV[x]).join('')}function fr(x){return [...x].map(c=>c==='K'?'R':c==='Q'?'D':c==='J'?'V':c==='T'?'10':c).join('')}function enc(n0,s0){const n=norm(n0),s=norm(s0),ns=new Set([...n].map(c=>R[c])),ss=new Set([...s].map(c=>R[c]));for(const v of ns)if(ss.has(v))throw Error('Une même carte figure dans les deux mains.');let sid=0,m=1,nm=0,sm=0;for(let r=2;r<=14;r++){let d=0;if(ns.has(r)){d=1;nm|=1<<r}else if(ss.has(r)){d=2;sm|=1<<r}sid+=d*m;m*=3}return{n,s,sid,nm,sm}}function swapSid(sid){let c=sid,o=0,m=1;for(let i=0;i<13;i++){let d=c%3;c=Math.floor(c/3);if(d===1)d=2;else if(d===2)d=1;o+=d*m;m*=3}return o}function swapText(x){return x.replaceAll('Nord','§N§').replaceAll('Sud','Nord').replaceAll('§N§','Sud').replaceAll('Est','§E§').replaceAll('Ouest','Est').replaceAll('§E§','Ouest')}function pct(frac){const[a,b]=frac.split('/').map(Number);return 100*a/b}function show(){try{const q=enc(nEl.value,sEl.value);nEl.value=fr(q.n);sEl.value=fr(q.s);const canonical=q.nm<q.sm,rep=canonical?q.sid:swapSid(q.sid),st=DB.states[String(rep)];if(!st){out.innerHTML='<div class="info"><b>Cette fiche n’est pas encore matérialisée dans le dictionnaire.</b><br><span class="muted">La base se complète automatiquement à partir des calculs exacts P1.</span></div>';return}let h='<div class="hands">Nord <code>'+fr(q.n)+'</code> — Sud <code>'+fr(q.s)+'</code></div>';const ts=Object.entries(st.t).sort((a,b)=>Number(b[0])-Number(a[0]));for(const[t,e]of ts){let txt=canonical?e.x:swapText(e.x);h+='<div class="entry"><div class="head"><div class="title">Pour '+t+' levée'+(t==='1'?'':'s')+'</div><div class="prob">'+pct(e.p).toFixed(2).replace('.',',')+' %</div></div><div class="play">'+txt+'</div></div>'}out.innerHTML=h}catch(e){out.innerHTML='<div class="error"><b>Erreur :</b> '+String(e.message||e)+'</div>'}}document.getElementById('f').onsubmit=e=>{e.preventDefault();show()};document.getElementById('count').textContent=DB.state_count.toLocaleString('fr-FR')+' configurations · '+DB.target_count.toLocaleString('fr-FR')+' objectifs matérialisés';show();</script></body></html>'''
    Path(a.output).write_text(template.replace('__DATA__',payload),encoding='utf-8')
    print(json.dumps({'states':len(states),'targets':targets,'output':a.output},sort_keys=True))

if __name__=='__main__': main()

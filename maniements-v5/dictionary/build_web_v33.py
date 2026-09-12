#!/usr/bin/env python3
from __future__ import annotations

import argparse, json
from pathlib import Path

import build_web_v3 as core
import build_web_v32 as source


def wildcard_html() -> str:
    h = core.INDEX_HTML
    h = h.replace('text-transform:uppercase;', '')
    h = h.replace(
        'Entre les deux mains en notation française : A, R, D, V, X…',
        'Notation française : A, R, D, V, X… · X = 10 · x = petite carte quelconque de 2 à 7'
    )
    # V4 presentation safety: make the classical suit-combination assumption explicit
    # and never expose the internal policy-automaton prose as if it were a bridge line.
    h = h.replace(
        '</p><section class="card"><form id="f">',
        '</p><p class="muted small"><b>Hypothèse standard :</b> communications extérieures suffisantes pour revenir dans la main voulue entre deux tours de la couleur, sauf indication contraire.</p><section class="card"><form id="f">',
        1,
    )
    h = h.replace('politique exacte</span>', 'calcul exact</span>')
    h = h.replace('Voir le maniement complet', 'Voir les données techniques exactes')

    anchor = "function fr(x){if(x==='-')return '—';return [...x].map(c=>c==='K'?'R':c==='Q'?'D':c==='J'?'V':c==='T'?'X':c).join('')}\n"
    extra = r'''function hasWild(x){return String(x||'').includes('x')}
function safeSummary(x){const s=String(x||'');if(s.includes('contextes de décision')||s.includes('La suite optimale dépend ensuite des cartes fournies par la défense'))return 'Calcul exact disponible — explication du maniement en cours de certification.';return s}
function parsePattern(raw){let z=String(raw||'').replaceAll('10','T').replace(/[ \-_,.\/]/g,'');if(!z)throw Error('Main vide.');let seen=new Set(),exact=[],wild=0;for(const rawc of z){if(rawc==='x'){wild++;continue}let c=rawc.toUpperCase();if(c==='X')c='T';if(c==='R')c='K';if(c==='D')c='Q';if(c==='V')c='J';if(!(c in R))throw Error('Carte invalide : '+rawc);if(seen.has(c))throw Error('Carte répétée : '+rawc);seen.add(c);exact.push(c)}exact.sort((a,b)=>R[b]-R[a]);return{exact:exact.join(''),wild}}
function choose(a,k,start=0,cur=[],out=[]){if(k===0){out.push([...cur]);return out}for(let i=start;i<=a.length-k;i++){cur.push(a[i]);choose(a,k-1,i+1,cur,out);cur.pop()}return out}
function expandWild(n0,s0){const np=parsePattern(n0),sp=parsePattern(s0),ne=new Set(np.exact),se=new Set(sp.exact);for(const c of ne)if(se.has(c))throw Error('Une même carte figure dans les deux mains.');const used=new Set([...ne,...se]),pool=['2','3','4','5','6','7'].filter(c=>!used.has(c)),need=np.wild+sp.wild;if(need>pool.length)throw Error('Pas assez de petites cartes distinctes (2–7) pour remplacer tous les x.');let out=[];for(const nc of choose(pool,np.wild)){const ns=new Set(nc),rem=pool.filter(c=>!ns.has(c));for(const sc of choose(rem,sp.wild)){out.push({n:norm(np.exact+nc.join('')),s:norm(sp.exact+sc.join(''))})}}return{np,sp,variants:out}}
function genericText(x){return String(x||'').replace(/\ble ([2-7])\b/g,'une petite carte').replace(/\bdu ([2-7])\b/g,'d’une petite carte')}
function patternFr(p){return fr(p.exact)+'x'.repeat(p.wild)}
async function lookupExact(n,s){const q=enc(n,s),canonical=q.nm<q.sm,rep=canonical?q.sid:swapSid(q.sid),sh=await loadShard(rep);return{q,canonical,rep,st:sh.states[String(rep)]||null}}
async function showWild(){const ex=expandWild(nEl.value,sEl.value),vars=ex.variants;nEl.value=patternFr(ex.np);sEl.value=patternFr(ex.sp);let rows=[];for(const v of vars)rows.push(await lookupExact(v.n,v.s));const have=rows.filter(r=>r.st);if(have.length!==rows.length){out.innerHTML='<div class="info"><b>Famille x encore incomplète.</b><br><span class="muted">'+have.length+' / '+rows.length+' affectations concrètes des petites cartes sont matérialisées. Le dictionnaire ne généralisera pas avant de les avoir toutes vérifiées.</span></div>';return}const targetLists=rows.map(r=>Object.keys(r.st.t).sort((a,b)=>Number(a)-Number(b)).join(','));if(!targetLists.every(x=>x===targetLists[0])){out.innerHTML='<div class="info"><b>Les petites cartes exactes influencent cette famille.</b><br><span class="muted">La notation x est trop générale ici : précise les petites cartes.</span></div>';return}let h='<div class="hands">Nord <code>'+esc(patternFr(ex.np))+'</code> — Sud <code>'+esc(patternFr(ex.sp))+'</code></div><div class="muted small" style="margin-top:5px">Famille vérifiée sur '+rows.length+' affectations distinctes des x parmi 2–7.</div>';const targets=Object.keys(rows[0].st.t).sort((a,b)=>Number(b)-Number(a));for(const t of targets){let vals=rows.map(r=>{const e=r.st.t[t],raw=r.canonical?e.x:swapText(e.x);return{p:e.p,x:genericText(safeSummary(raw)),technical:String(raw||'').includes('contextes de décision')}});const p0=vals[0].p,x0=vals[0].x;if(!vals.every(v=>v.p===p0&&v.x===x0&&!v.technical)){h+='<div class="entry"><div class="head"><div class="title">Pour '+t+' levée'+(t==='1'?'':'s')+'</div></div><div class="play">Les petites cartes exactes peuvent modifier le maniement ou son explication. Précise les cartes 2–7 pour ce nombre de levées.</div></div>';continue}h+='<div class="entry"><div class="head"><div class="title">Pour '+t+' levée'+(t==='1'?'':'s')+' <span class="badge exact">famille x certifiée</span></div><div class="prob">'+pct(p0).toFixed(2).replace('.',',')+' %</div></div><div class="play">'+esc(x0)+'</div></div>'}out.innerHTML=h}
'''
    if anchor not in h:
        raise RuntimeError('build_web_v3 HTML anchor not found')
    h = h.replace(anchor, anchor + extra, 1)

    # Sanitize legacy exact entries already materialized before V4. Exact policies
    # remain available under technical details, but their automaton counts are no
    # longer presented as a finished human bridge explanation.
    old_txt = "let txt=canonical?e.x:swapText(e.x),exact=e.coverage==='EXACT_POLICY_PROGRAM';"
    new_txt = "let txt=safeSummary(canonical?e.x:swapText(e.x)),exact=e.coverage==='EXACT_POLICY_PROGRAM';"
    if old_txt not in h:
        raise RuntimeError('exact summary anchor not found')
    h = h.replace(old_txt, new_txt, 1)

    old = "async function show(){try{out.classList.add('loading');const q=enc(nEl.value,sEl.value);"
    new = "async function show(){try{out.classList.add('loading');if(hasWild(nEl.value)||hasWild(sEl.value)){await showWild();return}const q=enc(nEl.value,sEl.value);"
    if old not in h:
        raise RuntimeError('show() anchor not found')
    h = h.replace(old, new, 1)
    return h


def main():
    ap=argparse.ArgumentParser()
    ap.add_argument('--repo',default='.')
    ap.add_argument('--output-dir',required=True)
    ap.add_argument('--branch-prefix',default='maniements-v5-dictionary-v3-p1-')
    ap.add_argument('--input-root')
    a=ap.parse_args()
    if a.input_root:
        entries=source.iter_input_entries(Path(a.input_root))
    else:
        entries=source.iter_branch_entries(Path(a.repo),a.branch_prefix)
    out=Path(a.output_dir); out.mkdir(parents=True,exist_ok=True)
    manifest=core.write_site(entries,out)
    (out/'index.html').write_text(wildcard_html().replace('__SHARD_SIZE__',str(core.SHARD_SIZE)),encoding='utf-8')
    print(json.dumps(manifest,ensure_ascii=False,sort_keys=True))


if __name__=='__main__':
    main()

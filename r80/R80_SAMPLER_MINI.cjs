#!/usr/bin/env node
'use strict';
const fs=require('fs'),crypto=require('crypto');
const SUITS=['S','H','D','C'],RANKS='AKQJT98765432';
const SEED_VERSION='r66-par-distribution-precision-v12-sync-lineage-conditioning-epoch-seat-perspective-stability-auction-lineage-dealerpar-adaptive-public';
function parseHand(s){const z=String(s).split('.');return{S:z[0]||'',H:z[1]||'',D:z[2]||'',C:z[3]||''};}
function readBoards(p){return fs.readFileSync(p,'utf8').trim().split(/\r?\n/).filter(Boolean).map(line=>{const z=line.split('\t');if(z.length!==5)throw new Error('bad board row');return{board:+z[0],dealer:z[1],vulnerable:z[2],hands:{N:parseHand(z[3]),S:parseHand(z[4])}};});}
function xmur3(text){let h=1779033703^String(text).length;for(let i=0;i<String(text).length;i++){h=Math.imul(h^String(text).charCodeAt(i),3432918353);h=h<<13|h>>>19;}return function(){h=Math.imul(h^(h>>>16),2246822507);h=Math.imul(h^(h>>>13),3266489909);return(h^=h>>>16)>>>0;};}
function mulberry32(seed){let a=seed>>>0;return function(){a|=0;a=a+0x6D2B79F5|0;let t=Math.imul(a^a>>>15,1|a);t=t+Math.imul(t^t>>>7,61|t)^t;return((t^t>>>14)>>>0)/4294967296;};}
function standardDeck(){const d=[];for(const s of SUITS)for(const r of RANKS)d.push(s+r);return d;}
function cards(h){const o=[];for(const s of SUITS)for(const r of String(h[s]||''))o.push(s+r);return o;}
function shuffle(xs,rng){const o=xs.slice();for(let i=o.length-1;i>0;i--){const r=Number(rng()),b=Number.isFinite(r)?Math.min(Math.max(r,0),0.9999999999999999):0,j=Math.floor(b*(i+1));[o[i],o[j]]=[o[j],o[i]];}return o;}
function handFromCards(xs){const h={S:'',H:'',D:'',C:''},ri=Object.fromEntries(Array.from(RANKS).map((r,i)=>[r,i]));for(const c of xs)h[c[0]]+=c.slice(1);for(const s of SUITS)h[s]=Array.from(h[s]).sort((a,b)=>ri[a]-ri[b]).join('');return h;}
function sample(d,i){const known=`N:${SUITS.map(s=>d.hands.N[s]||'').join('.')}|S:${SUITS.map(s=>d.hands.S[s]||'').join('.')}`;const material=[SEED_VERSION,String(d.board),String(d.dealer),String(d.vulnerable),'two-known-hands',known,String(i)].join('~');const rng=mulberry32(xmur3(material)()),seen=new Set([...cards(d.hands.N),...cards(d.hands.S)]),pool=shuffle(standardDeck().filter(c=>!seen.has(c)),rng);return{N:{...d.hands.N},E:handFromCards(pool.slice(0,13)),S:{...d.hands.S},W:handFromCards(pool.slice(13,26))};}
const hs=h=>`${h.S||''}.${h.H||''}.${h.D||''}.${h.C||''}`,pbn=h=>`N:${hs(h.N)} ${hs(h.E)} ${hs(h.S)} ${hs(h.W)}`,sha=s=>crypto.createHash('sha256').update(s).digest('hex');
const [,,mode,boardFile,arg,outFile]=process.argv;
if(!mode||!boardFile||!arg||!outFile)throw new Error('usage: sampler shard boards.tsv 01 out.tsv | sampler all boards.tsv 20 out.tsv');
let boards=readBoards(boardFile),samples;
if(mode==='shard'){const sh=Number(arg);if(!Number.isInteger(sh)||sh<1||sh>10||boards.length!==50)throw new Error('bad shard');boards=boards.slice((sh-1)*5,sh*5);samples=288;}
else if(mode==='all'){samples=Number(arg);if(!Number.isInteger(samples)||samples<1||samples>288)throw new Error('bad sample count');}
else throw new Error('bad mode');
const lines=[];for(const d of boards)for(let i=0;i<samples;i++){const x=pbn(sample(d,i));lines.push([d.board,i,sha(x),x].join('\t'));}
fs.writeFileSync(outFile,lines.join('\n')+'\n');console.log(JSON.stringify({mode,boards:boards.map(d=>d.board),samples,rows:lines.length,seedVersion:SEED_VERSION}));

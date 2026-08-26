import fs from 'node:fs';
import {performance} from 'node:perf_hooks';
const endpoint='https://api-gen-beta.vercel.app/api/dds';
const input=fs.readFileSync(process.argv[2],'utf8').trim().split(/\r?\n/).filter(Boolean).slice(0,72).map((l,i)=>{const z=l.split('\t');return{idx:i,pbn:z.slice(3).join('\t')}});
async function call(rows,label){
  const t0=performance.now();
  try{
    const r=await fetch(endpoint,{method:'POST',headers:{'content-type':'application/json','origin':'https://capgui13.github.io','user-agent':'PLAY-R85-parallel-probe/1.0'},body:JSON.stringify({items:rows.map(x=>({id:x.idx,pbn:x.pbn}))}),signal:AbortSignal.timeout(25000)});
    const text=await r.text(); let j=null; try{j=JSON.parse(text)}catch{}
    return{label,status:r.status,ok:r.ok,ms:+(performance.now()-t0).toFixed(1),results:Array.isArray(j?.results)?j.results.length:null,tables:Array.isArray(j?.results)?j.results.filter(x=>x?.table).length:null,bodyPreview:text.slice(0,200)};
  }catch(e){return{label,ok:false,ms:+(performance.now()-t0).toFixed(1),error:String(e?.message||e)}}
}
const chunks=[input.slice(0,24),input.slice(24,48),input.slice(48,72)];
const t0=performance.now();
const res=await Promise.all(chunks.map((c,i)=>call(c,`parallel-${i+1}`)));
const out={total:72,totalMs:+(performance.now()-t0).toFixed(1),ddsPerSecond:+(72/((performance.now()-t0)/1000)).toFixed(3),allOk:res.every(x=>x.ok&&x.tables===24),requests:res};
fs.writeFileSync(process.argv[3]||'R85_PARALLEL_PROBE.json',JSON.stringify(out,null,2));
console.log(JSON.stringify(out,null,2));

import fs from 'node:fs';
import { performance } from 'node:perf_hooks';

const endpoint = process.env.DDS_URL || 'https://api-gen-beta.vercel.app/api/dds';
const inputPath = process.argv[2] || 'equiv_input.tsv';
const expectedPath = process.argv[3] || 'equiv_expected.tsv';
const reportPath = process.argv[4] || 'R85_HTTP_BENCHMARK.json';

const inputLines = fs.readFileSync(inputPath,'utf8').trim().split(/\r?\n/).filter(Boolean).slice(0,120);
const expectedLines = fs.readFileSync(expectedPath,'utf8').trim().split(/\r?\n/).filter(Boolean).slice(0,120);
if(inputLines.length < 120 || expectedLines.length < 120) throw new Error(`Need 120 rows, got input=${inputLines.length} expected=${expectedLines.length}`);

const rows = inputLines.map((line,i)=>{
  const z=line.split('\t');
  if(z.length<4) throw new Error(`bad input row ${i}`);
  const e=expectedLines[i].split('\t');
  if(e.length<4) throw new Error(`bad expected row ${i}`);
  if(z[0]!==e[0] || z[1]!==e[1] || z[2]!==e[2]) throw new Error(`input/expected key mismatch row ${i}`);
  return { idx:i, board:Number(z[0]), sample:Number(z[1]), sha:z[2], pbn:z.slice(3).join('\t'), expected:e[3] };
});

function canonical(table){
  if(!table) return null;
  const strains=['N','S','H','D','C'];
  const seats=['N','S','E','W'];
  if(strains.every(s=>table[s] && typeof table[s]==='object')) {
    return strains.flatMap(s=>seats.map(p=>Number(table[s][p]))).join(',');
  }
  const rt=table.resTable;
  if(Array.isArray(rt) && rt.length>=5){
    const si=[4,0,1,2,3], hi=[0,2,1,3];
    return si.flatMap(s=>hi.map(h=>Number(rt[s][h]))).join(',');
  }
  if(Array.isArray(table) && table.length>=5 && Array.isArray(table[0])){
    const si=[4,0,1,2,3], hi=[0,2,1,3];
    return si.flatMap(s=>hi.map(h=>Number(table[s][h]))).join(',');
  }
  return null;
}

async function postRows(batchRows, label){
  const items=batchRows.map(r=>({id:r.idx,pbn:r.pbn}));
  const started=performance.now();
  let response, text='';
  try{
    response=await fetch(endpoint,{
      method:'POST',
      headers:{'content-type':'application/json','origin':'https://capgui13.github.io','user-agent':'PLAY-R85-benchmark/1.0'},
      body:JSON.stringify({items}),
      signal:AbortSignal.timeout(60000)
    });
    text=await response.text();
  }catch(err){
    return {label,n:items.length,ok:false,transportError:String(err?.message||err),elapsedMs:performance.now()-started};
  }
  const elapsedMs=performance.now()-started;
  let data=null;
  try{data=JSON.parse(text);}catch{}
  const out={label,n:items.length,httpStatus:response.status,elapsedMs,ok:false,resultCount:Array.isArray(data?.results)?data.results.length:null,bodyPreview:text.slice(0,500)};
  if(!response.ok || !Array.isArray(data?.results)) return out;
  const byId=new Map(data.results.map(r=>[Number(r?.id),r]));
  const mismatches=[], missing=[], errors=[];
  for(const r of batchRows){
    const got=byId.get(r.idx);
    if(!got){missing.push(r.idx); continue;}
    if(got.error || !got.table){errors.push({id:r.idx,error:got.error||'no table'}); continue;}
    const c=canonical(got.table);
    if(c!==r.expected) mismatches.push({id:r.idx,expected:r.expected,actual:c});
  }
  Object.assign(out,{ok:missing.length===0&&errors.length===0&&mismatches.length===0,missingCount:missing.length,errorCount:errors.length,mismatchCount:mismatches.length,missing:missing.slice(0,5),errors:errors.slice(0,5),mismatches:mismatches.slice(0,3)});
  delete out.bodyPreview;
  return out;
}

async function series(label,total,chunkSize,repeats=3){
  const runs=[];
  for(let rep=0;rep<repeats;rep++){
    const started=performance.now();
    const requests=[];
    let ok=true;
    for(let pos=0;pos<total;pos+=chunkSize){
      const rr=await postRows(rows.slice(pos,Math.min(total,pos+chunkSize)),`${label}-r${rep+1}-${pos}`);
      requests.push(rr); if(!rr.ok){ok=false; break;}
    }
    runs.push({rep:rep+1,ok,elapsedMs:performance.now()-started,requests});
  }
  const good=runs.filter(r=>r.ok).map(r=>r.elapsedMs);
  good.sort((a,b)=>a-b);
  const median=good.length?good[Math.floor(good.length/2)]:null;
  return {label,total,chunkSize,runs,medianMs:median,ddsPerSecond:median?total/(median/1000):null};
}

const report={endpoint,startedAt:new Date().toISOString(),node:process.version,capacity:[],series:[]};
report.firstObserved=await postRows(rows.slice(0,1),'first-observed-1');
for(const n of [1,6,10,12,24,40]) report.capacity.push(await postRows(rows.slice(0,n),`capacity-${n}`));
for(const [total,chunk] of [[24,10],[24,24],[72,10],[72,24],[120,10],[120,24]]){
  const cap=report.capacity.find(x=>x.n===chunk);
  if(cap && !cap.ok){ report.series.push({label:`${total}-by-${chunk}`,total,chunkSize:chunk,skipped:true,reason:'capacity probe failed'}); continue; }
  report.series.push(await series(`${total}-by-${chunk}`,total,chunk,2));
}
report.finishedAt=new Date().toISOString();
fs.writeFileSync(reportPath,JSON.stringify(report,null,2));
console.log(JSON.stringify({firstObserved:report.firstObserved,capacity:report.capacity.map(x=>({n:x.n,ok:x.ok,status:x.httpStatus,ms:x.elapsedMs,mismatch:x.mismatchCount,error:x.errorCount})),series:report.series.map(s=>({label:s.label,medianMs:s.medianMs,ddsPerSecond:s.ddsPerSecond,skipped:s.skipped}))},null,2));

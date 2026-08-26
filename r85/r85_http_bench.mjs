import fs from 'node:fs';
import { performance } from 'node:perf_hooks';

const endpoint = process.env.R85_ENDPOINT || 'https://api-gen-beta.vercel.app/api/dds';
const inputPath = process.argv[2];
const oraclePath = process.argv[3];
const outDir = process.argv[4] || '.';
if (!inputPath || !oraclePath) throw new Error('usage: node r85_http_bench.mjs input.tsv oracle.tsv outdir');
fs.mkdirSync(outDir,{recursive:true});
const parse=(p)=>fs.readFileSync(p,'utf8').trim().split(/\r?\n/).filter(Boolean).map(l=>l.split('\t'));
const inputRows=parse(inputPath).map(z=>({id:`${z[0]}-${z[1]}`, board:Number(z[0]), sample:Number(z[1]), sha:z[2], pbn:z[3]}));
const oracle=new Map(parse(oraclePath).map(z=>[`${z[0]}-${z[1]}`,z[3]]));
function canonical(table){
  if (!table) return null;
  if (Array.isArray(table) && table.length===20) return table.map(Number).join(',');
  const strains=['N','S','H','D','C']; const seats=['N','S','E','W'];
  try { const vals=[]; for (const s of strains) for (const h of seats) vals.push(Number(table[s][h])); if(vals.every(Number.isFinite)) return vals.join(','); } catch {}
  try { const vals=[]; for (const s of strains) for (const h of seats) vals.push(Number(table[h][s])); if(vals.every(Number.isFinite)) return vals.join(','); } catch {}
  return null;
}
async function post(items,label){
  const body=JSON.stringify({items:items.map(x=>({id:x.id,pbn:x.pbn}))});
  const t0=performance.now(); let resp, text='', json=null, err=null;
  try{ resp=await fetch(endpoint,{method:'POST',headers:{'content-type':'application/json','user-agent':'PLAY-R85-benchmark'},body,signal:AbortSignal.timeout(60000)}); text=await resp.text(); try{json=JSON.parse(text)}catch{} }catch(e){err=String(e)}
  const ms=performance.now()-t0; const results=Array.isArray(json?.results)?json.results:[];
  let exact=0, missing=0, malformed=0, mismatch=0;
  for(const x of items){ const r=results.find(q=>String(q.id)===x.id); if(!r){missing++;continue;} const c=canonical(r.table); if(!c){malformed++;continue;} const o=oracle.get(x.id); if(c===o) exact++; else mismatch++; }
  const row={label,n:items.length,status:resp?.status??null,ok:!!resp?.ok,ms:+ms.toFixed(1),dds_per_s:resp?.ok?+(items.length/(ms/1000)).toFixed(3):0,exact,missing,malformed,mismatch,resultCount:results.length,error:err,bodyPreview:(text||'').slice(0,300)};
  console.log(JSON.stringify(row)); return row;
}
const metrics=[];
metrics.push(await post(inputRows.slice(0,1),'first-request-1'));
for(const n of [1,6,10,12,24]) for(let r=1;r<=3;r++) metrics.push(await post(inputRows.slice((r-1)*24,(r-1)*24+n),`batch-${n}-r${r}`));
const accepted=metrics.filter(x=>x.label.startsWith('batch-')&&x.ok&&x.mismatch===0&&x.malformed===0&&x.missing===0).map(x=>x.n);
const maxAccepted=accepted.length?Math.max(...accepted):0;
for(const total of [24,72,120]){
  if(!maxAccepted) break;
  const t0=performance.now(); let exact=0, failures=0; const chunks=[];
  for(let pos=0;pos<total;pos+=maxAccepted){ const sub=inputRows.slice(pos,Math.min(total,pos+maxAccepted)); const rr=await post(sub,`total-${total}-chunk-${chunks.length+1}`); chunks.push(rr); exact+=rr.exact; if(!rr.ok||rr.mismatch||rr.malformed||rr.missing) failures++; }
  const elapsed=performance.now()-t0;
  metrics.push({label:`TOTAL-${total}`,n:total,status:failures?0:200,ok:failures===0,ms:+elapsed.toFixed(1),dds_per_s:+(total/(elapsed/1000)).toFixed(3),exact,missing:0,malformed:0,mismatch:0,resultCount:exact,error:null,maxAccepted,chunks:chunks.length});
}
fs.writeFileSync(`${outDir}/R85_HTTP_METRICS.json`,JSON.stringify({endpoint,maxAccepted,metrics},null,2));
fs.writeFileSync(`${outDir}/R85_HTTP_METRICS.tsv`,['label\tn\tstatus\tok\tms\tdds_per_s\texact\tmissing\tmalformed\tmismatch',...metrics.map(x=>[x.label,x.n,x.status,x.ok,x.ms,x.dds_per_s,x.exact,x.missing,x.malformed,x.mismatch].join('\t'))].join('\n')+'\n');

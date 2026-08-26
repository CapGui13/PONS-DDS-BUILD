#!/usr/bin/env python3
import argparse, json, time, urllib.request

STRAINS=('N','S','H','D','C'); SEATS=('N','S','E','W')

def load_rows(inp, exp):
    ins=[x.rstrip('\n').split('\t',3) for x in open(inp,encoding='utf-8') if x.strip()]
    exs=[x.rstrip('\n').split('\t',3) for x in open(exp,encoding='utf-8') if x.strip()]
    assert len(ins)==len(exs)
    out=[]
    for i,(a,e) in enumerate(zip(ins,exs)):
        assert a[:3]==e[:3]
        out.append({'idx':i,'board':int(a[0]),'sample':int(a[1]),'pbn':a[3],'expected':e[3]})
    return out

def canonical(t):
    return ','.join(str(int(t[s][p])) for s in STRAINS for p in SEATS)

def post(url, rows, timeout=60):
    body=json.dumps({'items':[{'id':r['idx'],'pbn':r['pbn']} for r in rows]},separators=(',',':')).encode()
    req=urllib.request.Request(url,data=body,headers={'Content-Type':'application/json','Origin':'https://capgui13.github.io'},method='POST')
    started=time.perf_counter()
    with urllib.request.urlopen(req,timeout=timeout) as resp:
        data=json.loads(resp.read()); assert resp.status==200
    elapsed=(time.perf_counter()-started)*1000
    got={int(x['id']):x for x in data['results']}; assert len(got)==len(rows)
    for r in rows:
        assert canonical(got[r['idx']]['table'])==r['expected'], (r['board'],r['sample'])
    return elapsed

def progression(url, rows):
    assert len(rows)>=120
    chunk_ms=[]; cumulative=0.0; marks={}
    for i in range(0,120,24):
        ms=post(url,rows[i:i+24]); chunk_ms.append(ms); cumulative+=ms
        n=i+24
        if n in (24,72,120): marks[f't{n}Ms']=cumulative
    marks['chunkMs']=chunk_ms
    marks['ddsPerSec120']=120/(marks['t120Ms']/1000)
    return marks

def main():
    ap=argparse.ArgumentParser()
    ap.add_argument('--url',default='http://127.0.0.1:18086/api/dds')
    ap.add_argument('--input',required=True)
    ap.add_argument('--expected',required=True)
    ap.add_argument('--boards',default='51,66,81,96')
    ap.add_argument('--threads',type=int,required=True)
    ap.add_argument('--output',required=True)
    a=ap.parse_args()
    rows=load_rows(a.input,a.expected)
    by={}
    for r in rows: by.setdefault(r['board'],[]).append(r)
    for v in by.values(): v.sort(key=lambda x:x['sample'])
    boards=[int(x) for x in a.boards.split(',') if x.strip()]
    assert all(b in by and len(by[b])>=120 for b in boards)
    results=[]
    for b in boards:
        x=progression(a.url,by[b]); x['board']=b; results.append(x)
    report={'status':'PASS','threads':a.threads,'batchSize':24,'boards':results}
    json.dump(report,open(a.output,'w'),indent=2,sort_keys=True)
    print(json.dumps(report,indent=2,sort_keys=True))

if __name__=='__main__': main()

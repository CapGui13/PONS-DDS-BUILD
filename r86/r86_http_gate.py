#!/usr/bin/env python3
import argparse
import concurrent.futures
import json
import statistics
import time
import urllib.request

STRAINS=('N','S','H','D','C')
SEATS=('N','S','E','W')

def parse_rows(inp, exp):
    ins=[x.rstrip('\n').split('\t',3) for x in open(inp,encoding='utf-8') if x.strip()]
    exs=[x.rstrip('\n').split('\t',3) for x in open(exp,encoding='utf-8') if x.strip()]
    assert len(ins)==len(exs)
    rows=[]
    for i,(a,e) in enumerate(zip(ins,exs)):
        assert a[:3]==e[:3], (i,a[:3],e[:3])
        rows.append({'idx':i,'pbn':a[3],'expected':e[3]})
    return rows

def canonical(table):
    return ','.join(str(int(table[s][p])) for s in STRAINS for p in SEATS)

def post(url, rows, timeout=30):
    body=json.dumps({'items':[{'id':r['idx'],'pbn':r['pbn']} for r in rows]},separators=(',',':')).encode()
    req=urllib.request.Request(url,data=body,headers={'Content-Type':'application/json','Origin':'https://capgui13.github.io'},method='POST')
    t=time.perf_counter()
    with urllib.request.urlopen(req,timeout=timeout) as resp:
        raw=resp.read(); status=resp.status
    ms=(time.perf_counter()-t)*1000
    data=json.loads(raw)
    assert status==200
    byid={int(x['id']):x for x in data['results']}
    assert len(byid)==len(rows)
    for r in rows:
        assert canonical(byid[r['idx']]['table'])==r['expected'], r['idx']
    return {'tables':len(rows),'elapsedMs':ms,'ddsPerSec':len(rows)/(ms/1000)}

def scenario(url, rows, total, chunk, repeats):
    runs=[]
    for rep in range(repeats):
        t=time.perf_counter(); reqs=[]
        for pos in range(0,total,chunk):
            reqs.append(post(url,rows[pos:min(total,pos+chunk)]))
        ms=(time.perf_counter()-t)*1000
        runs.append({'rep':rep+1,'elapsedMs':ms,'ddsPerSec':total/(ms/1000),'requests':reqs})
    med=statistics.median(x['elapsedMs'] for x in runs)
    return {'total':total,'chunk':chunk,'runs':runs,'medianMs':med,'ddsPerSec':total/(med/1000)}

def main():
    ap=argparse.ArgumentParser()
    ap.add_argument('--url',default='http://127.0.0.1:18086/api/dds')
    ap.add_argument('--input',required=True)
    ap.add_argument('--expected',required=True)
    ap.add_argument('--mode',choices=['benchmark','exhaustive','parallel'],required=True)
    ap.add_argument('--output',required=True)
    ap.add_argument('--start',type=int,default=0)
    ap.add_argument('--count',type=int,default=0)
    args=ap.parse_args()
    allrows=parse_rows(args.input,args.expected)
    if args.count:
        rows=allrows[args.start:args.start+args.count]
        assert len(rows)==args.count
        for j,r in enumerate(rows): r['idx']=j
    else: rows=allrows
    out={'mode':args.mode,'url':args.url,'rows':len(rows),'status':'PASS'}
    if args.mode=='benchmark':
        assert len(rows)>=120
        cold=post(args.url,rows[:24])
        warmup=post(args.url,rows[24:48])
        series=[scenario(args.url,rows,24,24,3),scenario(args.url,rows,72,24,2),scenario(args.url,rows,120,24,2)]
        out.update({'cold24':cold,'warmup24':warmup,'series':series})
    elif args.mode=='exhaustive':
        t=time.perf_counter(); n=0; reqs=0
        for pos in range(0,len(rows),24):
            rr=post(args.url,rows[pos:pos+24],timeout=45); n+=rr['tables']; reqs+=1
        ms=(time.perf_counter()-t)*1000
        out.update({'verified':n,'requests':reqs,'elapsedMs':ms,'ddsPerSec':n/(ms/1000)})
    else:
        assert len(rows)>=72
        chunks=[rows[0:24],rows[24:48],rows[48:72]]
        t=time.perf_counter()
        with concurrent.futures.ThreadPoolExecutor(max_workers=3) as ex:
            rs=list(ex.map(lambda c:post(args.url,c,timeout=30),chunks))
        ms=(time.perf_counter()-t)*1000
        out.update({'verified':72,'elapsedMs':ms,'ddsPerSec':72/(ms/1000),'requests':rs})
    json.dump(out,open(args.output,'w'),indent=2,sort_keys=True)
    print(json.dumps(out,indent=2,sort_keys=True))

if __name__=='__main__': main()

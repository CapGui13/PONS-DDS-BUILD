#!/usr/bin/env python3
import argparse, json, math, statistics, time, urllib.request

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

def percentile(vals,p):
    s=sorted(vals); return s[max(0,min(len(s)-1,math.ceil(p*len(s))-1))]

def main():
    ap=argparse.ArgumentParser()
    ap.add_argument('--url',default='http://127.0.0.1:18086/api/dds')
    ap.add_argument('--input',required=True)
    ap.add_argument('--expected',required=True)
    ap.add_argument('--stops',required=True)
    ap.add_argument('--threads',type=int,default=2)
    ap.add_argument('--boards',default='51-100')
    ap.add_argument('--output',required=True)
    a=ap.parse_args()
    rows=load_rows(a.input,a.expected)
    stop_doc=json.load(open(a.stops,encoding='utf-8'))
    stops={int(k):int(v) for k,v in stop_doc['stops'].items()}
    if '-' in a.boards and ',' not in a.boards:
        lo,hi=(int(x) for x in a.boards.split('-',1)); selected=list(range(lo,hi+1))
    else:
        selected=[int(x) for x in a.boards.split(',') if x.strip()]
    assert selected and all(b in stops for b in selected), selected
    by={}
    for r in rows:
        if r['board'] in selected: by.setdefault(r['board'],[]).append(r)
    for v in by.values(): v.sort(key=lambda x:x['sample'])
    assert sorted(by)==sorted(selected), (sorted(by),selected)

    board_results=[]
    total_requested=0
    total_logical=0
    for board in selected:
        logical=stops[board]
        requested=min(120, int(math.ceil(logical/24.0))*24)
        assert requested in (24,48,72,96,120)
        assert len(by[board])>=requested
        chunks=[]; elapsed=0.0
        for i in range(0,requested,24):
            ms=post(a.url,by[board][i:i+24]); chunks.append(ms); elapsed+=ms
        total_requested+=requested; total_logical+=logical
        board_results.append({
            'board':board,
            'logicalStop':logical,
            'requestedSamples':requested,
            'chunkOvershoot':requested-logical,
            'elapsedMs':elapsed,
            'chunkMs':chunks,
            'ddsPerSec':requested/(elapsed/1000.0),
        })

    vals=[x['elapsedMs'] for x in board_results]
    report={
        'campaign':'PLAY_R86_R81_EFFECTIVE_HTTP_WORKLOAD',
        'status':'PASS',
        'threads':a.threads,
        'batchSize':24,
        'selectedBoards':selected,
        'boards':board_results,
        'metrics':{
            'medianMs':statistics.median(vals),
            'p90Ms':percentile(vals,.90),
            'p95Ms':percentile(vals,.95),
            'maxMs':max(vals),
            'meanMs':statistics.mean(vals),
            'totalElapsedMs':sum(vals),
            'logicalSamples':total_logical,
            'requestedSamples':total_requested,
            'httpChunkOvershootSamples':total_requested-total_logical,
        },
        'slowest':sorted(board_results,key=lambda x:x['elapsedMs'],reverse=True)[:10],
        'stopSource':stop_doc.get('campaign'),
        'provenance':stop_doc.get('provenance'),
    }
    json.dump(report,open(a.output,'w'),indent=2,sort_keys=True)
    print(json.dumps(report,indent=2,sort_keys=True))

if __name__=='__main__': main()

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

def canonical(t): return ','.join(str(int(t[s][p])) for s in STRAINS for p in SEATS)

def post(url, rows, timeout=30):
    body=json.dumps({'items':[{'id':r['idx'],'pbn':r['pbn']} for r in rows]},separators=(',',':')).encode()
    req=urllib.request.Request(url,data=body,headers={'Content-Type':'application/json','Origin':'https://capgui13.github.io'},method='POST')
    t=time.perf_counter()
    with urllib.request.urlopen(req,timeout=timeout) as resp:
        data=json.loads(resp.read()); assert resp.status==200
    ms=(time.perf_counter()-t)*1000
    by={int(x['id']):x for x in data['results']}; assert len(by)==len(rows)
    for r in rows: assert canonical(by[r['idx']]['table'])==r['expected'], (r['board'],r['sample'])
    return ms

def percentile(vals,p):
    s=sorted(vals); return s[max(0,min(len(s)-1,math.ceil(p*len(s))-1))]

def run_progression(url, rows):
    assert len(rows)>=120
    chunks=[rows[0:24],rows[24:48],rows[48:72],rows[72:96],rows[96:120]]
    cumul=0.0; marks={}; per=[]
    for i,c in enumerate(chunks,1):
        ms=post(url,c); per.append(ms); cumul+=ms
        if i==1: marks['t24Ms']=cumul
        if i==3: marks['t72Ms']=cumul
        if i==5: marks['t120Ms']=cumul
    marks['chunkMs']=per
    marks['ddsPerSec120']=120/(marks['t120Ms']/1000)
    return marks

def main():
    ap=argparse.ArgumentParser(); ap.add_argument('--url',default='http://127.0.0.1:18086/api/dds'); ap.add_argument('--input',required=True); ap.add_argument('--expected',required=True); ap.add_argument('--output',required=True)
    a=ap.parse_args(); rows=load_rows(a.input,a.expected)
    by={}
    for r in rows: by.setdefault(r['board'],[]).append(r)
    for v in by.values(): v.sort(key=lambda x:x['sample'])
    selected=[51,56,61,66,71,76,81,86,91,96]
    assert all(b in by and len(by[b])>=120 for b in selected)
    board_results=[]
    for b in selected:
        x=run_progression(a.url,by[b][:120]); x['board']=b; board_results.append(x)
    metrics={}
    for key in ('t24Ms','t72Ms','t120Ms'):
        vals=[x[key] for x in board_results]
        metrics[key]={'median':statistics.median(vals),'p90':percentile(vals,.9),'max':max(vals),'min':min(vals)}
    # Separate stress mix: the 140 equivalence witnesses are intentionally hard/atypical.
    stress_rows=[r for r in rows if r['board'] not in range(51,101)]
    if len(stress_rows)<120: stress_rows=rows[:140]
    stress=run_progression(a.url,stress_rows[:120])
    report={'status':'PASS','selectedBoards':selected,'boards':board_results,'ordinary':metrics,'stressMix':stress}
    json.dump(report,open(a.output,'w'),indent=2,sort_keys=True)
    print(json.dumps(report,indent=2,sort_keys=True))

if __name__=='__main__': main()

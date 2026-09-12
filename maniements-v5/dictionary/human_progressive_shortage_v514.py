#!/usr/bin/env python3
from __future__ import annotations

import argparse,json,sys,time
from collections import Counter
from fractions import Fraction
from functools import lru_cache
from pathlib import Path

HERE=Path(__file__).resolve().parent
sys.path.insert(0,str(HERE))
import human_batch_v44 as v44
import human_qualification_v50 as v50
import human_motif_v54 as v54

RVAL={'2':2,'3':3,'4':4,'5':5,'6':6,'7':7,'8':8,'9':9,'T':10,'J':11,'Q':12,'K':13,'A':14}
STR='AKQJT98'

def hand(s,seat):return s.north if seat=='N' else s.south
def has(eng,s,seat,c):return bool(hand(s,seat)&(1<<eng.R2I[c]))
def low(eng,m):
    rr=list(eng.ranks(m));return eng.I2R[min(rr)] if rr else '-'
def seen_key(eng,s,key):return bool((s.west_seen|s.east_seen)&(1<<eng.R2I[key]))
def prev_def(eng,s):
    for q,r in reversed(s.trick):
        if q not in eng.DECL:return '-' if not r else eng.I2R[r]
    return None

def cheapest_above(eng,m,c):
    rr=sorted((eng.I2R[r] for r in eng.ranks(m)),key=lambda x:RVAL[x]);return next((x for x in rr if RVAL[x]>RVAL[c]),None)


def spec_candidates(north,south):
    owned=set(north+south);missing=[c for c in 'KQJ' if c not in owned];out=[]
    for feeder,target,fh,th in [('N','S',north,south),('S','N',south,north)]:
        feed=sorted([c for c in fh if c in 'T98'],key=lambda c:RVAL[c])
        if len(feed)<2:continue
        for key in missing:
            honors=sorted([c for c in th if RVAL[c]>RVAL[key] and c in 'AKQJ'],key=lambda c:RVAL[c])
            lows=sorted([c for c in th if RVAL[c]<RVAL[key]],key=lambda c:RVAL[c])
            if not honors or not lows:continue
            # Require feeder cards directly below or near the missing key; this keeps
            # the motif recognisable rather than brute-forcing arbitrary programs.
            if max(RVAL[c] for c in feed)>=RVAL[key]:continue
            out.append({'feeder':feeder,'target':target,'key':key,'feed_seq':tuple(feed),'honor_seq':tuple(honors),'duck_card':lows[0]})
    return out


def next_present(eng,s,seat,seq):
    for c in seq:
        if has(eng,s,seat,c):return c
    return None


def fourth_void(s,feeder):
    # Engine order for a declarer lead is N-E-S-W or S-W-N-E.
    return bool(s.west_void) if feeder=='N' else bool(s.east_void)


def action(eng,e,s,z):
    feeder=z['feeder'];target=z['target'];key=z['key'];fc=next_present(eng,s,feeder,z['feed_seq']);hc=next_present(eng,s,target,z['honor_seq'])
    if s.pos==0:
        if fc:return feeder,fc
        if hand(s,target):
            # once feeder sequence is exhausted, finish in head
            rr=sorted((eng.I2R[r] for r in eng.ranks(hand(s,target))),key=lambda c:RVAL[c],reverse=True);return target,rr[0] if rr else '-'
        return None
    seat=e.order(s.leader)[s.pos]
    if seat not in eng.DECL:return None
    if seat==target and s.leader==feeder:
        p=prev_def(eng,s)
        if p==key and hc:
            w=cheapest_above(eng,hand(s,target),key)
            if w:return target,w
        if fourth_void(s,feeder) and not seen_key(eng,s,key):
            # key is now localised in second hand: duck to finesse it.
            d=low(eng,hand(s,target));return target,d
        if hc:return target,hc
        return target,low(eng,hand(s,target))
    return seat,low(eng,hand(s,seat))


def evaluate(eng,north,south,goal,z):
    e=eng.Engine2(north,south,goal)
    @lru_cache(maxsize=None)
    def F(s):
        term=e.terminal(s)
        if term is not None:return term[0]
        if s.pos==0:
            a=action(eng,e,s,z)
            if a is None:return 0
            seat,c=a;r=eng.R2I[c];lead=eng.PublicState(s.north,s.south,s.west_seen,s.east_seen,s.west_void,s.east_void,seat,0,tuple(),s.won);return F(e.close(e.decl_play(lead,seat,r)))
        seat=e.order(s.leader)[s.pos]
        if seat in eng.DECL:
            a=action(eng,e,s,z)
            if a is None or a[0]!=seat:return 0
            c=a[1];r=eng.VOID if c=='-' else eng.R2I[c];return F(e.close(e.decl_play(s,seat,r)))
        belief=e.belief(s);ok=belief
        for r,legal in e.defender_actions(s,seat):ok &= ((belief&~legal)|F(e.close(e.def_play(s,seat,r))))
        return ok
    m=F(e.initial());return e.model.weight(m),m


def fr(c):return {'A':'As','K':'Roi','Q':'Dame','J':'Valet','T':'10','9':'9','8':'8'}.get(c,c)
def article(c):return 'l’As' if c=='A' else ('la Dame' if c=='Q' else 'le '+fr(c))
def describe(z,display):
    h=display[0] if z['feeder']=='N' else display[1];targets=', puis '.join('vers '+article(c) for c in z['honor_seq'])
    return [f"Jouer progressivement les cartes de {h}, {targets}.",f"Si {article(z['key'])} apparaît en deuxième, le couvrir au plus juste.",f"Si l’adversaire placé après la main aux honneurs a montré une chicane et que {article(z['key'])} n’est pas encore apparu, laisser courir la carte de {h} au lieu de dépenser l’honneur suivant : {article(z['key'])} est alors localisé en deuxième."]


def analyze(eng,c):
    e=eng.Engine2(c['north'],c['south'],c['target']);opt=Fraction(e.solve(include_policy=False)['probability_fraction']);rows=[];t0=time.monotonic();tested=0
    for z in spec_candidates(c['north'],c['south']):
        try:p,mask=evaluate(eng,c['north'],c['south'],c['target'],z);tested+=1
        except Exception:continue
        if p==opt:rows.append({'spec':{k:(list(v) if isinstance(v,tuple) else v) for k,v in z.items()},'lines':describe(z,c['display']),'mask':str(mask)})
    return {'id':c['id'],'display':c['display'],'north':c['north'],'south':c['south'],'target':c['target'],'fraction':str(opt),'found':bool(rows),'best':rows[0] if rows else None,'exact_candidates':len(rows),'tested':tested,'elapsed_seconds':round(time.monotonic()-t0,3)}


def main():
    ap=argparse.ArgumentParser();ap.add_argument('--runtime-root',required=True);ap.add_argument('--out-dir',required=True);a=ap.parse_args();eng=v54.load_engine(a.runtime_root);reviewed=[];novel=[];cnt=Counter();t0=time.monotonic()
    for c in v44.CASES:
        r=analyze(eng,c);reviewed.append(r);cnt['reviewed']+=1;cnt['reviewed_found']+=int(r['found']);print(json.dumps({'set':'reviewed','case':c['id'],'found':r['found']},ensure_ascii=False),flush=True)
    for cid,north,south in v50.HOLDINGS:
        for target in range(1,max(len(north),len(south))+1):
            e=eng.Engine2(north,south,target);opt=Fraction(e.solve(include_policy=False)['probability_fraction'])
            if opt in (0,1):continue
            c={'id':cid,'north':north,'south':south,'display':[v50.disp(north),v50.disp(south)],'target':target};r=analyze(eng,c);novel.append(r);cnt['novel']+=1;cnt['novel_found']+=int(r['found']);
            if r['found']:print(json.dumps({'set':'novel','case':cid,'target':target,'found':True,'spec':r['best']['spec']},ensure_ascii=False),flush=True)
    summary={'schema':'MANIEMENTS_V5_HUMAN_V514_PROGRESSIVE_SHORTAGE_V1',**dict(cnt),'reviewed_rate_percent':f"{100*cnt['reviewed_found']/cnt['reviewed']:.2f}",'novel_rate_percent':f"{100*cnt['novel_found']/cnt['novel']:.2f}",'elapsed_seconds':round(time.monotonic()-t0,3),'runtime_frozen_sha256':'a0b580531f3c9e8bb00710b9c3e1c183b27cbfe9231c9d584e29a374ba88835d','rule':'progressive shortage-reveal motif is fully replayed; exact oracle equality required'}
    od=Path(a.out_dir);od.mkdir(parents=True,exist_ok=True);(od/'HUMAN_V514_PROGRESSIVE_SHORTAGE.json').write_text(json.dumps({'summary':summary,'reviewed':reviewed,'novel':novel},ensure_ascii=False,indent=2)+'\n',encoding='utf-8');(od/'SUMMARY.txt').write_text('\n'.join(f'{k}={v}' for k,v in summary.items())+'\n',encoding='utf-8');print(json.dumps(summary,ensure_ascii=False),flush=True)

if __name__=='__main__':main()

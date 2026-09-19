#!/usr/bin/env python3
from __future__ import annotations

import argparse, json, sys, time
from collections import Counter
from fractions import Fraction
from functools import lru_cache
from pathlib import Path

HERE=Path(__file__).resolve().parent
sys.path.insert(0,str(HERE))
import human_motif_v54 as v54
import human_motif_search_v571 as base571

v=base571.v
RVAL=v.RVAL


def hand(s,seat):return s.north if seat=='N' else s.south

def has(eng,s,seat,c):return bool(hand(s,seat)&(1<<eng.R2I[c]))

def lowest(eng,m):
    rr=list(eng.ranks(m));return eng.I2R[min(rr)] if rr else '-'

def highest(eng,m):
    rr=list(eng.ranks(m));return eng.I2R[max(rr)] if rr else '-'

def cheapest_winner(eng,m,c):
    x=sorted((eng.I2R[r] for r in eng.ranks(m)),key=lambda z:RVAL[z]);return next((z for z in x if RVAL[z]>RVAL.get(c,0)),None)

def prev_def(eng,s):
    for q,r in reversed(s.trick):
        if q not in eng.DECL:return '-' if not r else eng.I2R[r]
    return None

def lead_rank(eng,s):
    for q,r in s.trick:
        if q==s.leader:return '-' if not r else eng.I2R[r]
    return None

def active_target(eng,s,seat,seq):
    for c in seq:
        if has(eng,s,seat,c):return c
    return None


def action(eng,e,s,spec):
    cash=spec['cash'];feeder=spec['feeder'];target=spec['target'];seq=spec['seq'];probe=spec.get('probe');mode=spec.get('mode','cover');probe_mode=spec.get('probe_mode','cover')
    if s.pos==0:
        for c in cash:
            for seat in ('N','S'):
                if has(eng,s,seat,c):return seat,c
        if probe and has(eng,s,feeder,probe):return feeder,probe
        if active_target(eng,s,target,seq) is not None and hand(s,feeder):return feeder,lowest(eng,hand(s,feeder))
        opts=[]
        for seat in ('N','S'):
            if hand(s,seat):
                c=highest(eng,hand(s,seat));opts.append((RVAL[c],seat,c))
        if opts:
            _,seat,c=max(opts);return seat,c
        return None
    seat=e.order(s.leader)[s.pos]
    if seat not in eng.DECL:return None
    lr=lead_rank(eng,s)
    if lr in cash:return seat,lowest(eng,hand(s,seat))
    if probe and s.leader==feeder and lr==probe and seat==target:
        prev=prev_def(eng,s)
        if probe_mode=='cover' and prev not in (None,'-') and RVAL.get(prev,0)>RVAL[probe]:
            w=cheapest_winner(eng,hand(s,target),prev)
            if w:return target,w
        return target,lowest(eng,hand(s,target))
    cur=active_target(eng,s,target,seq)
    if s.leader==feeder and seat==target and cur is not None:
        prev=prev_def(eng,s)
        if prev not in (None,'-') and RVAL.get(prev,0)>RVAL[cur]:
            if mode=='duck':
                return target,lowest(eng,hand(s,target))
            w=cheapest_winner(eng,hand(s,target),prev)
            if w:
                return target,w
            # In normal cover mode, if the inserted card cannot be covered,
            # duck cheaply instead of wasting the scheduled finesse card.
            return target,lowest(eng,hand(s,target))
        return target,cur
    return seat,lowest(eng,hand(s,seat))


def evaluate(eng,north,south,goal,spec):
    e=eng.Engine2(north,south,goal)
    @lru_cache(maxsize=None)
    def F(s):
        term=e.terminal(s)
        if term is not None:return term[0]
        if s.pos==0:
            a=action(eng,e,s,spec)
            if a is None:return 0
            seat,c=a;r=eng.R2I[c]
            lead=eng.PublicState(s.north,s.south,s.west_seen,s.east_seen,s.west_void,s.east_void,seat,0,tuple(),s.won)
            return F(e.close(e.decl_play(lead,seat,r)))
        seat=e.order(s.leader)[s.pos]
        if seat in eng.DECL:
            a=action(eng,e,s,spec)
            if a is None or a[0]!=seat:return 0
            c=a[1];r=eng.VOID if c=='-' else eng.R2I[c]
            return F(e.close(e.decl_play(s,seat,r)))
        belief=e.belief(s);successful=belief
        for r,legal in e.defender_actions(s,seat):
            ns=e.close(e.def_play(s,seat,r));successful &= ((belief&~legal)|F(ns))
        return successful
    m=F(e.initial());return e.model.weight(m),m


def seqs(h):
    s=sorted({c for c in h if c in 'AKQJT98'},key=lambda c:RVAL[c]);out=[]
    for k in range(1,min(4,len(s))+1):out.append(tuple(s[:k]))
    if len(s)>=2:out.append(tuple(s[1:min(len(s),4)]))
    z=[]
    for x in out:
        if x and x not in z:z.append(x)
    return z


def top_prefix(north,south):
    own=set(north+south);r=[]
    for c in 'AKQJT98':
        if c in own:r.append(c)
        else:break
    return r


def specs(north,south):
    top=top_prefix(north,south);cash_opts=[tuple()]+[tuple(top[:k]) for k in range(1,min(2,len(top))+1)]
    out=[]
    def add(z):
        key=(z['cash'],z['feeder'],z['target'],z['seq'],z.get('probe'),z.get('mode'),z.get('probe_mode'))
        if key not in seen:seen.add(key);out.append(z)
    seen=set()
    for feeder,target,fh,th in [('N','S',north,south),('S','N',south,north)]:
        ss=seqs(th)
        # Safety duck variant for ordinary low leads.
        for seq in ss:
            for cash in cash_opts:
                if set(cash)&set(seq):continue
                add({'cash':cash,'feeder':feeder,'target':target,'seq':seq,'probe':None,'mode':'duck','probe_mode':'cover'})
        # Honor-probe variants: present J/Q/K/T from the feeder, then continue with a short finesse sequence.
        probes=[c for c in fh if c in 'KQJT']
        for probe in probes:
            for seq in ss[:4]:
                for cash in cash_opts[:2]:
                    if probe in cash or set(cash)&set(seq):continue
                    for pm in ('cover','duck'):
                        add({'cash':cash,'feeder':feeder,'target':target,'seq':seq,'probe':probe,'mode':'cover','probe_mode':pm})
    return out


def fr(c):return {'A':'As','K':'Roi','Q':'Dame','J':'Valet','T':'10','9':'9','8':'8'}.get(c,c)
def art(c):return ('l’'+fr(c)) if c=='A' else ('le '+fr(c))

def lines(spec,display):
    out=[]
    if spec['cash']:out.append('Commencer par tirer '+' puis '.join(art(c) for c in spec['cash'])+'.')
    h=display[0] if spec['feeder']=='N' else display[1]
    if spec.get('probe'):
        out.append(f"Présenter {art(spec['probe'])} de {h}.")
        if spec['probe_mode']=='cover':out.append('Si l’adversaire en deuxième monte au-dessus, couvrir au plus juste ; sinon laisser courir.')
        else:out.append('Laisser courir ce premier honneur, même si l’adversaire en deuxième monte au-dessus.')
    if spec['seq']:
        ts=[fr(c) for c in spec['seq']]
        out.append('Puis jouer '+('successivement ' if len(ts)>1 else '')+'petit de '+h+' '+', puis '.join('vers le '+x for x in ts)+'.')
        if spec['mode']=='duck':out.append('Si l’adversaire en deuxième monte au-dessus de la carte visée, laisser prendre au lieu de couvrir.')
        else:out.append('Si l’adversaire en deuxième monte au-dessus de la carte visée, couvrir au plus juste.')
    out.append('Finir en jouant la couleur en tête avec les cartes restantes si nécessaire.')
    return out


def motif(spec):
    if spec.get('probe'):
        return 'HONOR_PROBE_THEN_'+('FINESSE' if spec['mode']=='cover' else 'SAFETY')
    return 'SAFETY_DUCK_FINESSE'


def analyze(eng,c,p):
    goal=int(p['target']);opt=Fraction(p['fraction']);rows=[];tested=0;t0=time.monotonic()
    for s in specs(c['north'],c['south']):
        try:prob,mask=evaluate(eng,c['north'],c['south'],goal,s);tested+=1
        except Exception:continue
        if prob!=opt:continue
        ll=lines(s,c['display']);score=(len(ll),int(bool(s.get('probe'))),len(s['cash'])+len(s['seq']))
        rows.append({'motif':motif(s),'spec':{k:(list(vv) if isinstance(vv,tuple) else vv) for k,vv in s.items()},'lines':ll,'mask':str(mask),'score':list(score)})
    rows.sort(key=lambda r:tuple(r['score']));return {'target':goal,'fraction':str(opt),'tested':tested,'found':bool(rows),'best':rows[0] if rows else None,'exact_candidates':len(rows),'elapsed_seconds':round(time.monotonic()-t0,3)}


def main():
    ap=argparse.ArgumentParser();ap.add_argument('--v52',required=True);ap.add_argument('--v57',required=True);ap.add_argument('--runtime-root',required=True);ap.add_argument('--out-dir',required=True);a=ap.parse_args()
    eng=v54.load_engine(a.runtime_root);src=json.load(open(a.v52,encoding='utf-8'));old=json.load(open(a.v57,encoding='utf-8'))
    oldmap={(c['id'],p['target']):p for c in old['cases'] for p in c['profiles']};cases=[];cnt=Counter();t0=time.monotonic()
    for c in src['cases']:
        cc={'id':c['id'],'north':c['north'],'south':c['south'],'display':c['display'],'profiles':[]}
        for p in c['profiles']:
            if not p.get('qualification',{}).get('counted'):continue
            prev=oldmap.get((c['id'],p['target'])) or {};cnt['profiles']+=1
            if prev.get('found'):
                cc['profiles'].append({'target':p['target'],'already_v57':True,'found':True,'source':'V57','best':prev.get('best')});cnt['already']+=1;continue
            r=analyze(eng,c,p);r['already_v57']=False;r['source']='V59' if r['found'] else 'NONE';cc['profiles'].append(r);cnt['new_found']+=int(r['found'])
            print(json.dumps({'case':c['id'],'target':p['target'],'new':r['found'],'motif':(r['best'] or {}).get('motif'),'tested':r['tested'],'sec':r['elapsed_seconds']},ensure_ascii=False),flush=True)
        cases.append(cc)
    total=cnt['already']+cnt['new_found'];summary={'schema':'MANIEMENTS_V5_HUMAN_V59_SAFETY_PROBE_V1',**dict(cnt),'combined_found':total,'combined_coverage_percent':f"{100*total/cnt['profiles']:.2f}",'elapsed_seconds':round(time.monotonic()-t0,3),'runtime_frozen_sha256':'a0b580531f3c9e8bb00710b9c3e1c183b27cbfe9231c9d584e29a374ba88835d','promotion_rule':'every new safety/probe candidate is exhaustively replayed and accepted only at the exact oracle optimum'}
    od=Path(a.out_dir);od.mkdir(parents=True,exist_ok=True);(od/'HUMAN_V59_SAFETY_PROBE.json').write_text(json.dumps({'summary':summary,'cases':cases},ensure_ascii=False,indent=2)+'\n',encoding='utf-8');(od/'SUMMARY.txt').write_text('\n'.join(f'{k}={json.dumps(v,ensure_ascii=False) if isinstance(v,(dict,list)) else v}' for k,v in summary.items())+'\n',encoding='utf-8');print(json.dumps(summary,ensure_ascii=False),flush=True)

if __name__=='__main__':main()

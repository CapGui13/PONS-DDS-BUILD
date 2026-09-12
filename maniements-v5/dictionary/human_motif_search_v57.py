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

RVAL={'2':2,'3':3,'4':4,'5':5,'6':6,'7':7,'8':8,'9':9,'T':10,'J':11,'Q':12,'K':13,'A':14}
FR={'A':'As','K':'Roi','Q':'Dame','J':'Valet','T':'10','9':'9','8':'8'}


def hand_mask(s,seat):
    return s.north if seat=='N' else s.south


def has(eng,s,seat,card):
    return bool(hand_mask(s,seat)&(1<<eng.R2I[card]))


def lowest(eng,mask):
    rr=list(eng.ranks(mask));return eng.I2R[min(rr)] if rr else '-'


def highest(eng,mask):
    rr=list(eng.ranks(mask));return eng.I2R[max(rr)] if rr else '-'


def next_target(eng,s,seat,targets):
    for c in targets:
        if has(eng,s,seat,c):return c
    return None


def cheapest_winner(eng,mask,against):
    av=RVAL.get(against,0);cards=sorted((eng.I2R[r] for r in eng.ranks(mask)),key=lambda c:RVAL[c])
    return next((c for c in cards if RVAL[c]>av),None)


def lead_card(s):
    for seat,r in s.trick:
        if seat==s.leader:return r
    return None


def strategy_action(eng,e,s,cash,feeder,target,targets):
    # At a fresh trick, cash the prescribed top cards first. Once they are gone,
    # repeatedly enter the feeder hand and lead its cheapest card toward target.
    if s.pos==0:
        for c in cash:
            for seat in ('N','S'):
                if has(eng,s,seat,c):return (seat,c)
        t=next_target(eng,s,target,targets)
        if t is not None and hand_mask(s,feeder):return (feeder,lowest(eng,hand_mask(s,feeder)))
        return None

    seat=e.order(s.leader)[s.pos]
    if seat not in eng.DECL:return None
    lr=lead_card(s);lead='-' if lr in (None,0) else eng.I2R[lr]

    # If this trick was led by a declarer cash-card, the partner simply unloads low.
    if s.leader in eng.DECL and lead in cash:
        return (seat,lowest(eng,hand_mask(s,seat)))

    # Finesse response in the target hand: play the current target unless the
    # defender in front has played higher, in which case cover as cheaply as possible.
    if seat==target and s.leader==feeder:
        t=next_target(eng,s,target,targets)
        if t is None:return (seat,lowest(eng,hand_mask(s,seat)))
        prev=None
        # The target hand acts after the defender immediately in front of it.
        for q,r in reversed(s.trick):
            if q not in eng.DECL:
                prev='-' if not r else eng.I2R[r];break
        if prev not in (None,'-') and RVAL[prev]>RVAL[t]:
            w=cheapest_winner(eng,hand_mask(s,target),prev)
            if w:return (target,w)
        return (target,t)

    # Any other declarer response is non-strategic for this motif.
    return (seat,lowest(eng,hand_mask(s,seat)))


def evaluate(eng,north,south,target_goal,cash,feeder,target,targets):
    e=eng.Engine2(north,south,target_goal)
    @lru_cache(maxsize=None)
    def F(s):
        term=e.terminal(s)
        if term is not None:return term[0]
        if s.pos==0:
            act=strategy_action(eng,e,s,cash,feeder,target,targets)
            if act is None:return 0
            seat,card=act;r=eng.R2I[card]
            lead=eng.PublicState(s.north,s.south,s.west_seen,s.east_seen,s.west_void,s.east_void,seat,0,tuple(),s.won)
            return F(e.close(e.decl_play(lead,seat,r)))
        seat=e.order(s.leader)[s.pos]
        if seat in eng.DECL:
            act=strategy_action(eng,e,s,cash,feeder,target,targets)
            if act is None or act[0]!=seat:return 0
            card=act[1];r=eng.VOID if card=='-' else eng.R2I[card]
            return F(e.close(e.decl_play(s,seat,r)))
        belief=e.belief(s);successful=belief
        for r,legal in e.defender_actions(s,seat):
            ns=e.close(e.def_play(s,seat,r));branch=F(ns)
            successful &= ((belief & ~legal)|branch)
        return successful
    m=F(e.initial());return e.model.weight(m),m


def top_prefix(north,south):
    owned=set(north+south);out=[]
    for c in 'AKQJT98':
        if c in owned:out.append(c)
        else:break
    return out


def seq_variants(hand):
    seq=sorted({c for c in hand if c in 'AKQJT98'},key=lambda c:RVAL[c])
    out=[]
    def add(x):
        x=tuple(x)
        if x and x not in out:out.append(x)
    add(seq)
    if len(seq)>1:add(seq[:-1])
    if len(seq)>2:add(seq[:-2])
    if len(seq)>1:add(seq[1:])
    if len(seq)>2:add(seq[1:-1])
    # Natural low-to-high prefixes catch one- and two-stage finesse motifs.
    for k in range(1,min(3,len(seq))+1):add(seq[:k])
    return out[:7]


def candidate_specs(north,south):
    top=top_prefix(north,south);cash_opts=[tuple()]
    for k in range(1,min(2,len(top))+1):cash_opts.append(tuple(top[:k]))
    specs=[]
    for feeder,target,th in [('N','S',south),('S','N',north)]:
        for seq in seq_variants(th):
            for cash in cash_opts:
                # A card cannot be both scheduled for cashing and needed later as a target.
                if set(cash)&set(seq):continue
                z=(cash,feeder,target,seq)
                if z not in specs:specs.append(z)
    # Pure play-in-head candidates: cash 1..3 top partnership honours.
    for k in range(1,min(3,len(top))+1):
        specs.append((tuple(top[:k]),'N','S',tuple()))
    return specs


def fr_card(c):return FR.get(c,c)


def procedure(cash,feeder,target,targets,display):
    parts=[]
    if cash:
        names=[fr_card(c) for c in cash]
        parts.append('Tirer '+(' puis '.join(('l’'+x if x=='As' else 'le '+x) for x in names))+'.')
    if targets:
        hand=display[0] if feeder=='N' else display[1]
        ts=[fr_card(c) for c in targets]
        if len(ts)==1:
            parts.append(f'Jouer petit de {hand} vers le {ts[0]}.')
        else:
            parts.append('Jouer successivement petit de '+hand+' '+', puis '.join('vers le '+x for x in ts)+'.')
        parts.append('Si l’adversaire intercale une carte supérieure à la carte visée, couvrir au plus juste.')
    return parts


def motif_name(north,south,cash,targets):
    owned=set(north+south);missing=[c for c in 'AKQJT' if c not in owned]
    if targets and len(missing)==1 and len(targets)>=2:
        return 'IMPASSE_REPETEE_'+missing[0]
    if cash and targets:return 'CASH_THEN_FINESSE_SEQUENCE'
    if targets:return 'FINESSE_SEQUENCE'
    return 'PLAY_TOP'


def score(spec,lines):
    cash,feeder,target,targets=spec
    return (len(lines),len(cash)+len(targets),0 if len(targets)>=2 else 1,len(cash))


def analyze(eng,c,p,max_candidates=0):
    goal=int(p['target']);opt=Fraction(p['fraction']);specs=candidate_specs(c['north'],c['south'])
    if max_candidates:specs=specs[:max_candidates]
    exact=[];started=time.monotonic();tested=0
    for spec in specs:
        cash,feeder,target,targets=spec
        try:
            prob,_=evaluate(eng,c['north'],c['south'],goal,cash,feeder,target,targets);tested+=1
        except Exception:
            continue
        if prob!=opt:continue
        lines=procedure(cash,feeder,target,targets,c['display'])
        exact.append({'motif':motif_name(c['north'],c['south'],cash,targets),'cash':list(cash),'feeder':feeder,'target_hand':target,'targets':list(targets),'lines':lines,'probability_fraction':str(prob),'score':list(score(spec,lines))})
    exact.sort(key=lambda x:tuple(x['score']))
    best=exact[0] if exact else None
    why=''
    if best:
        # Reuse the exact-world reasoner as a conservative first explanation layer.
        why=v54.exact_reason(eng,c['north'],c['south'],goal,p.get('qualification',{}).get('candidate_why') or p.get('why') or '')
    return {'target':goal,'fraction':str(opt),'tested_candidates':tested,'exact_motifs':len(exact),'found':bool(best),'best':best,'why':why,'elapsed_seconds':round(time.monotonic()-started,3)}


def main():
    ap=argparse.ArgumentParser();ap.add_argument('--input',required=True);ap.add_argument('--runtime-root',required=True);ap.add_argument('--out-dir',required=True);ap.add_argument('--max-candidates',type=int,default=0);a=ap.parse_args()
    eng=v54.load_engine(a.runtime_root);src=json.load(open(a.input,encoding='utf-8'));cases=[];cnt=Counter();started=time.monotonic()
    for c in src['cases']:
        cc={'id':c['id'],'north':c['north'],'south':c['south'],'display':c['display'],'profiles':[]}
        for p in c['profiles']:
            if not p.get('qualification',{}).get('counted'):continue
            r=analyze(eng,c,p,a.max_candidates);cc['profiles'].append(r);cnt['profiles']+=1;cnt['found']+=int(r['found']);cnt['multi_exact']+=int(r['exact_motifs']>1)
            print(json.dumps({'case':c['id'],'target':r['target'],'found':r['found'],'motifs':r['exact_motifs'],'best':(r['best'] or {}).get('motif'),'sec':r['elapsed_seconds']},ensure_ascii=False),flush=True)
        cases.append(cc)
    summary={'schema':'MANIEMENTS_V5_HUMAN_V57_MOTIF_SEARCH_V1',**dict(cnt),'coverage_percent':f"{100*cnt['found']/cnt['profiles']:.2f}" if cnt['profiles'] else '0.00','elapsed_seconds':round(time.monotonic()-started,3),'runtime_frozen_sha256':'a0b580531f3c9e8bb00710b9c3e1c183b27cbfe9231c9d584e29a374ba88835d','motifs':'PLAY_TOP; FINESSE_SEQUENCE; CASH_THEN_FINESSE_SEQUENCE; repeated-finesse specialization','promotion_rule':'candidate strategy is replayed exhaustively and promoted only when its exact success fraction equals the oracle optimum'}
    od=Path(a.out_dir);od.mkdir(parents=True,exist_ok=True);(od/'HUMAN_V57_MOTIF_SEARCH.json').write_text(json.dumps({'summary':summary,'cases':cases},ensure_ascii=False,indent=2)+'\n',encoding='utf-8');(od/'SUMMARY.txt').write_text('\n'.join(f'{k}={json.dumps(v,ensure_ascii=False) if isinstance(v,(dict,list)) else v}' for k,v in summary.items())+'\n',encoding='utf-8');print(json.dumps(summary,ensure_ascii=False),flush=True)

if __name__=='__main__':main()

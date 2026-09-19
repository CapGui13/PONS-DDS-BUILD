#!/usr/bin/env python3
from __future__ import annotations
import itertools
from functools import lru_cache

RVAL={'2':2,'3':3,'4':4,'5':5,'6':6,'7':7,'8':8,'9':9,'T':10,'J':11,'Q':12,'K':13,'A':14}
STR='AKQJT98'

def hand(s,seat): return s.north if seat=='N' else s.south
def has(eng,s,seat,c): return bool(hand(s,seat)&(1<<eng.R2I[c]))
def lowest(eng,mask):
    rr=list(eng.ranks(mask)); return eng.I2R[min(rr)] if rr else '-'
def highest(eng,mask):
    rr=list(eng.ranks(mask)); return eng.I2R[max(rr)] if rr else '-'
def seen_union(eng,s):
    return {eng.I2R[r] for r in eng.ranks(s.west_seen|s.east_seen)}

def prior_seen_union(eng,s):
    # Information available before the current trick. Defender cards already
    # played on the current trick must not retroactively alter a choice made
    # from the preceding probe/cash trick.
    seen=set(seen_union(eng,s))
    for seat,r in s.trick:
        if seat not in eng.DECL and r:
            seen.discard(eng.I2R[r])
    return seen
def prev_def(eng,s):
    for q,r in reversed(s.trick):
        if q not in eng.DECL: return '-' if not r else eng.I2R[r]
    return None
def cheapest_winner(eng,mask,against):
    av=RVAL.get(against,0)
    cs=sorted((eng.I2R[r] for r in eng.ranks(mask)),key=lambda c:RVAL[c])
    return next((c for c in cs if RVAL[c]>av),None)

def choose_target(eng,s,spec):
    target=spec['target']; a=spec['if_seen']; b=spec['if_not']
    # Once either branch card has been consumed, the conditional decision has
    # already been made and executed; do not switch branches on later evidence.
    if not has(eng,s,target,a) or not has(eng,s,target,b):
        return None
    evidence = seen_union(eng,s) if s.pos==0 else prior_seen_union(eng,s)
    return a if (evidence&set(spec['trigger'])) else b

def action(eng,e,s,spec):
    feeder=spec['feeder']; target=spec['target']; cash=spec['cash']
    if s.pos==0:
        if has(eng,s,feeder,cash):
            return feeder,cash
        t=choose_target(eng,s,spec)
        if t is not None and hand(s,feeder):
            return feeder,lowest(eng,hand(s,feeder))
        opts=[]
        for seat in ('N','S'):
            if hand(s,seat):
                c=highest(eng,hand(s,seat)); opts.append((RVAL[c],seat,c))
        if opts:
            _,seat,c=max(opts); return seat,c
        return None

    seat=e.order(s.leader)[s.pos]
    if seat not in eng.DECL: return None

    # Partner follows low on the initial cash.
    first=next((('-' if not r else eng.I2R[r]) for q,r in s.trick if q==s.leader),None)
    if s.leader==feeder and first==cash:
        return seat,lowest(eng,hand(s,seat))

    t=choose_target(eng,s,spec)
    if seat==target and s.leader==feeder and t is not None:
        p=prev_def(eng,s)
        if p not in (None,'-') and RVAL[p]>RVAL[t]:
            w=cheapest_winner(eng,hand(s,target),p)
            if w: return target,w
            return target,lowest(eng,hand(s,target))
        return target,t
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
            seat,c=a; r=eng.R2I[c]
            lead=eng.PublicState(s.north,s.south,s.west_seen,s.east_seen,
                                 s.west_void,s.east_void,seat,0,tuple(),s.won)
            return F(e.close(e.decl_play(lead,seat,r)))
        seat=e.order(s.leader)[s.pos]
        if seat in eng.DECL:
            a=action(eng,e,s,spec)
            if a is None or a[0]!=seat:return 0
            c=a[1]; r=eng.VOID if c=='-' else eng.R2I[c]
            return F(e.close(e.decl_play(s,seat,r)))
        belief=e.belief(s); successful=belief
        for r,legal in e.defender_actions(s,seat):
            ns=e.close(e.def_play(s,seat,r))
            successful &= ((belief&~legal)|F(ns))
        return successful
    m=F(e.initial())
    return e.model.weight(m),m

def specs(north,south):
    owned=set(north+south)
    missing=[c for c in STR if c not in owned]
    out=[]; seen=set()
    for feeder,target,fh,th in [('N','S',north,south),('S','N',south,north)]:
        cashes=[c for c in fh if c in 'AKQJT']
        targets=[c for c in th if c in STR]
        for cash in cashes:
            for a,b in itertools.permutations(targets,2):
                # Prefer distinct strategic cards; a is selected when trigger seen.
                for k in range(1,min(3,len(missing))+1):
                    for trig in itertools.combinations(missing,k):
                        z={'cash':cash,'feeder':feeder,'target':target,
                           'trigger':trig,'if_seen':a,'if_not':b}
                        key=(cash,feeder,target,trig,a,b)
                        if key not in seen:
                            seen.add(key); out.append(z)
    return out

def lines(spec,display):
    fh=display[0] if spec['feeder']=='N' else display[1]
    th=display[0] if spec['target']=='N' else display[1]
    fr={'A':'As','K':'Roi','Q':'Dame','J':'Valet','T':'10'}
    art=lambda c: ("l’"+fr[c]) if c=='A' else ("la "+fr[c] if c=='Q' else "le "+fr.get(c,c))
    trig=', '.join(fr.get(c,c) for c in spec['trigger'])
    return [
      f"Commencer par tirer {art(spec['cash'])}.",
      f"Observer les cartes fournies par les adversaires sur ce tour.",
      f"Si l’une des cartes {trig} apparaît, jouer ensuite petit de {fh} vers {art(spec['if_seen'])} ; sinon vers {art(spec['if_not'])}.",
      "Si l’adversaire en deuxième joue une carte supérieure à la carte visée, couvrir au plus juste si possible ; sinon fournir petit.",
      "Finir ensuite en jouant la couleur en tête."
    ]

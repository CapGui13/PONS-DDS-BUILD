#!/usr/bin/env python3
from __future__ import annotations
import itertools
from functools import lru_cache

RVAL={'2':2,'3':3,'4':4,'5':5,'6':6,'7':7,'8':8,'9':9,'T':10,'J':11,'Q':12,'K':13,'A':14}
STRATEGIC='AKQJT98'

def hand(s,seat): return s.north if seat=='N' else s.south
def has(eng,s,seat,c): return bool(hand(s,seat)&(1<<eng.R2I[c]))
def lowest(eng,m):
    rr=list(eng.ranks(m)); return eng.I2R[min(rr)] if rr else '-'
def highest(eng,m):
    rr=list(eng.ranks(m)); return eng.I2R[max(rr)] if rr else '-'
def seen_side(eng,s,side):
    m=s.west_seen if side=='W' else s.east_seen
    return {eng.I2R[r] for r in eng.ranks(m)}
def lead_rank(eng,s):
    for q,r in s.trick:
        if q==s.leader:return '-' if not r else eng.I2R[r]
    return None
def prev_def(eng,s):
    for q,r in reversed(s.trick):
        if q not in eng.DECL:return '-' if not r else eng.I2R[r]
    return None
def cheapest_winner(eng,m,c):
    rr=sorted((eng.I2R[r] for r in eng.ranks(m)),key=lambda x:RVAL[x])
    return next((x for x in rr if RVAL[x]>RVAL.get(c,0)),None)

def chosen(eng,s,z):
    return z['if_target'] if (seen_side(eng,s,z['watch'])&set(z['switch'])) else z['else_target']

def action(eng,e,s,z):
    cash=z['cash'];feeder=z['feeder'];target=z['target']
    if s.pos==0:
        # Probe first, exactly once.
        if not (s.west_seen or s.east_seen) and has(eng,s,feeder,cash):
            return feeder,cash
        c=chosen(eng,s,z)
        if has(eng,s,target,c) and hand(s,feeder):
            return feeder,lowest(eng,hand(s,feeder))
        # Once the selected finesse card has been consumed, cash the suit high.
        opts=[]
        for seat in ('N','S'):
            if hand(s,seat):
                h=highest(eng,hand(s,seat));opts.append((RVAL[h],seat,h))
        return max(opts)[1:] if opts else None

    seat=e.order(s.leader)[s.pos]
    if seat not in eng.DECL:return None
    lr=lead_rank(eng,s)
    # On the probe trick, partner contributes cheaply; the watched defender's
    # card is then available as public information for the next trick.
    if lr==cash:
        return seat,lowest(eng,hand(s,seat))

    c=chosen(eng,s,z)
    if s.leader==feeder and seat==target and has(eng,s,target,c):
        p=prev_def(eng,s)
        if p not in (None,'-') and RVAL.get(p,0)>RVAL[c]:
            w=cheapest_winner(eng,hand(s,target),p)
            if w:return target,w
            return target,lowest(eng,hand(s,target))
        return target,c
    return seat,lowest(eng,hand(s,seat))

def evaluate(eng,north,south,goal,z):
    e=eng.Engine2(north,south,goal)
    @lru_cache(maxsize=None)
    def F(s):
        term=e.terminal(s)
        if term is not None:return term[0]
        if s.pos==0:
            a=action(eng,e,s,z)
            if a is None:return 0
            seat,c=a
            if c=='-':return 0
            r=eng.R2I[c]
            lead=eng.PublicState(s.north,s.south,s.west_seen,s.east_seen,
                                 s.west_void,s.east_void,seat,0,tuple(),s.won)
            return F(e.close(e.decl_play(lead,seat,r)))
        seat=e.order(s.leader)[s.pos]
        if seat in eng.DECL:
            a=action(eng,e,s,z)
            if a is None or a[0]!=seat:return 0
            c=a[1];r=eng.VOID if c=='-' else eng.R2I[c]
            return F(e.close(e.decl_play(s,seat,r)))
        belief=e.belief(s);ok=belief
        for r,legal in e.defender_actions(s,seat):
            ok &= ((belief&~legal)|F(e.close(e.def_play(s,seat,r))))
        return ok
    m=F(e.initial())
    return e.model.weight(m),m

def specs(north,south):
    owned=set(north+south)
    missing=[c for c in STRATEGIC if c not in owned]
    out=[];seen=set()
    for feeder,target,fh,th in [('N','S',north,south),('S','N',south,north)]:
        cashes=[c for c in fh if c in 'AKQ']
        targets=[c for c in th if c in 'JT98']
        if len(targets)<2:continue
        switches=[]
        for k in range(1,min(3,len(missing))+1):
            switches.extend(itertools.combinations(missing,k))
        for cash,watch,sw,a,b in itertools.product(cashes,('W','E'),switches,targets,targets):
            if a==b:continue
            z={'cash':cash,'feeder':feeder,'target':target,'watch':watch,
               'switch':tuple(sw),'if_target':a,'else_target':b}
            key=(cash,feeder,target,watch,tuple(sw),a,b)
            if key not in seen:
                seen.add(key);out.append(z)
    return out

def describe(z,display):
    fh=display[0] if z['feeder']=='N' else display[1]
    th=display[0] if z['target']=='N' else display[1]
    fr={'A':'As','K':'Roi','Q':'Dame','J':'Valet','T':'10','9':'9','8':'8'}
    article=lambda c: ("l’"+fr[c]) if c=='A' else ("la "+fr[c] if c=='Q' else "le "+fr.get(c,c))
    watch='Ouest' if z['watch']=='W' else 'Est'
    drops=', '.join(article(c) for c in z['switch'])
    return [
      f"Commencer par tirer {article(z['cash'])}.",
      f"Observer la carte fournie par {watch} sur ce coup.",
      f"Si {watch} fournit {drops}, jouer ensuite petit de {fh} vers {article(z['if_target'])} ; sinon vers {article(z['else_target'])}.",
      "Si l’adversaire en deuxième monte au-dessus de la carte visée, couvrir au plus juste.",
      "Encaisser ensuite les cartes maîtresses restantes."
    ]

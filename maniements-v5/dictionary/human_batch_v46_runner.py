#!/usr/bin/env python3
from __future__ import annotations

from collections import Counter
import human_batch_v45 as v45


def sem_rank(rank):
    if isinstance(rank, (tuple, list)):
        return tuple(sem_rank(x) for x in rank)
    if rank in ('A','K','Q','J','T','9','8','-'):
        return rank
    return 'x'


def _flatten(value):
    if isinstance(value, (tuple, list)):
        out=[]
        for item in value:
            out.extend(_flatten(item))
        return out
    return [value]


def feasible_actions(eng,e,s,need):
    acts=[]
    if s.pos==0:
        pools=tuple((seat,hand) for seat,hand in (('N',s.north),('S',s.south)) if hand)
    else:
        seat=e.order(s.leader)[s.pos]
        if seat not in eng.DECL:return []
        pools=((seat,s.north if seat=='N' else s.south),)
    for seat,hand in pools:
        ranks=eng.ranks(hand) if hand else ((eng.VOID,) if s.pos else tuple())
        for r in ranks:
            if s.pos==0:
                lead=eng.PublicState(s.north,s.south,s.west_seen,s.east_seen,s.west_void,s.east_void,seat,0,tuple(),s.won)
                ns=e.close(e.decl_play(lead,seat,r))
            else:
                ns=e.close(e.decl_play(s,seat,r))
            covering=[cm for cm in e.frontier(ns) if not need or (need|cm)==cm]
            if not covering:continue
            support=max(covering,key=lambda cm:(e.model.weight(cm),cm))
            acts.append((seat,r,ns,support))
    return acts


def choose_human_action(eng,e,s,need,cands):
    if not cands:raise RuntimeError('no feasible declarer action')
    bestw=max(e.model.weight(x[3]) for x in cands)
    top=[x for x in cands if e.model.weight(x[3])==bestw]
    if s.pos==0:
        # If an exact-equivalent direct honour cash exists, prefer it over the
        # cosmetically equivalent route "small towards that honour".
        honours=[x for x in top if eng.I2R[x[1]] in 'AKQJ']
        if honours:
            return max(honours,key=lambda x:(v45.b.RANK_VALUE[eng.I2R[x[1]]],-((s.north if x[0]=='N' else s.south).bit_count())))
        spots=[x for x in top if eng.I2R[x[1]] not in 'AKQJ']
        pool=spots or top
        def key(x):
            seat,r,_,_=x
            hand=s.north if seat=='N' else s.south
            rank=eng.I2R[r]
            return (hand.bit_count(),v45.b.RANK_VALUE[rank],0 if seat=='N' else 1)
        return min(pool,key=key)
    prev=v45.previous_def_card(eng,e,s)
    rows=[(x,eng.I2R[x[1]] if x[1] else '-') for x in top]
    if prev:
        p='-' if not prev else eng.I2R[prev]
        if p!='-' and v45.b.RANK_VALUE[p]>=10:
            beat=[z for z in rows if z[1]!='-' and v45.b.RANK_VALUE[z[1]]>v45.b.RANK_VALUE[p]]
            if beat:return min(beat,key=lambda z:v45.b.RANK_VALUE[z[1]])[0]
            return min(rows,key=lambda z:v45.b.RANK_VALUE.get(z[1],0))[0]
    strategic=[z for z in rows if z[1]!='-' and v45.b.RANK_VALUE[z[1]]>=8]
    if strategic:return min(strategic,key=lambda z:v45.b.RANK_VALUE[z[1]])[0]
    return min(rows,key=lambda z:v45.b.RANK_VALUE.get(z[1],0))[0]


def sig(n):
    if n.kind=='T':return ('T',n.terminal)
    if n.kind=='D':
        seat,rank=n.action
        return ('D',(seat,sem_rank(rank)),sig(n.branches[0]))
    grouped={}
    for card,ch in n.branches or []:
        key=(sem_rank(card),sig(ch))
        grouped[key]=1
    return ('F',tuple(sorted(grouped.keys(),key=str)))


def collapse(n):
    if n.kind=='T':return n
    if n.kind=='D':
        n.branches=[collapse(n.branches[0])]
        return n
    bs=[(c,collapse(ch)) for c,ch in n.branches]
    # First merge exact future semantic policies, ignoring concrete low-card pips.
    grouped={}
    for c,ch in bs:
        grouped.setdefault(sig(ch),[ch,[]])[1].extend(_flatten(c))
    if len(grouped)==1:
        return next(iter(grouped.values()))[0]
    n.branches=[(tuple(dict.fromkeys(v[1])),v[0]) for v in grouped.values()]
    return n


def card_condition(cards):
    cards=list(dict.fromkeys(_flatten(cards)))
    cats=[]
    for c in cards:
        sc=sem_rank(c)
        if sc not in cats:cats.append(sc)
    if cats==['-']:return "si l’adversaire défausse"
    names=[]
    for c in cats:
        if c=='x':names.append('une petite carte')
        else:names.append(v45.b.fr_article(c))
    if len(names)==1:return f"si l’adversaire fournit {names[0]}"
    return "si l’adversaire fournit " + ", ".join(names[:-1]) + " ou " + names[-1]


def action_phrase(n,first=False):
    seat,rank=n.action
    s=n.state
    if s.pos==0:
        nxt=first_decl_action_mode(n.branches[0]) if n.branches else None
        if rank in '765432':
            if nxt and nxt[0]!=seat and nxt[1] not in ('-','x'):
                return f"{'Commencer' if first else 'Jouer'} par petit vers {v45.b.fr_article(nxt[1])}."
            return "Jouer petit."
        if rank=='A':return "Tirer l’As."
        if rank=='K':return "Tirer le Roi."
        if rank=='Q':return "Jouer la Dame."
        if rank=='J':return "Jouer le Valet."
        if rank in 'T98':
            if nxt and nxt[0]!=seat and nxt[1] not in ('-','x'):
                return f"{'Commencer' if first else 'Jouer'} par {v45.b.fr_article(rank)} vers {v45.b.fr_article(nxt[1])}."
            return f"Jouer {v45.b.fr_article(rank)}."
    prev=v45.previous_def_card(_ENG,_E,s)
    prev_rank=None if prev is None else ('-' if not prev else _ENG.I2R[prev])
    if prev_rank and prev_rank!='-' and v45.b.RANK_VALUE.get(rank,0)>v45.b.RANK_VALUE.get(prev_rank,99):
        return f"Couvrir avec {v45.b.fr_article(rank)}."
    if rank in '765432':return "Fournir petit."
    return f"Passer {v45.b.fr_article(rank)}."


def first_decl_action_mode(n):
    vals=[]
    def walk(x,depth=0):
        if depth>2:return
        if x.kind=='D':
            vals.append((x.action[0],sem_rank(x.action[1])));return
        if x.kind=='F':
            for _,ch in x.branches or []:walk(ch,depth+1)
    walk(n)
    if not vals:return None
    counts=Counter(vals)
    return counts.most_common(1)[0][0]


_ENG=None;_E=None
v45.feasible_actions=feasible_actions
v45.choose_human_action=choose_human_action
v45.sig=sig
v45.collapse=collapse
v45.card_condition=card_condition
v45.action_phrase=action_phrase

_orig_main=v45.main

def main():
    # v45.main assigns its engine to v45 globals; mirror these through a small
    # previous-card adapter used by the renderer.
    global _ENG,_E
    old_prev=v45.previous_def_card_cached
    def prev_cached(s):
        r=v45.previous_def_card(v45._ENG,v45._E,s)
        return None if r is None else ('-' if not r else v45._ENG.I2R[r])
    v45.previous_def_card_cached=prev_cached
    return _orig_main()

if __name__=='__main__':
    main()

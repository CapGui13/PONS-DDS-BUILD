#!/usr/bin/env python3
from __future__ import annotations
from functools import lru_cache
from fractions import Fraction

RVAL={'2':2,'3':3,'4':4,'5':5,'6':6,'7':7,'8':8,'9':9,'T':10,'J':11,'Q':12,'K':13,'A':14}
HONORS={'Q','J'}

def hand(s,seat):
    return s.north if seat=='N' else s.south

def cards(eng,mask):
    return sorted((eng.I2R[r] for r in eng.ranks(mask)),key=lambda c:RVAL[c])

def has(eng,s,seat,c):
    return bool(hand(s,seat)&(1<<eng.R2I[c]))

def low(eng,mask):
    c=cards(eng,mask)
    return c[0] if c else '-'

def prev_def(eng,s):
    for seat,r in reversed(s.trick):
        if seat not in eng.DECL:
            return '-' if not r else eng.I2R[r]
    return None

def seen_at(eng,s,seat):
    mask=s.west_seen if seat=='W' else s.east_seen
    return {eng.I2R[r] for r in eng.ranks(mask)}

def cheapest_above(eng,mask,c):
    for x in cards(eng,mask):
        if RVAL[x]>RVAL.get(c,0):
            return x
    return None

def target_low_card(eng,s,target):
    # The finesse ladder is the lowest remaining card in the target hand
    # below the partnership's top honours A/K.
    cs=[c for c in cards(eng,hand(s,target)) if c not in ('A','K')]
    return cs[0] if cs else None

def cheapest_top(eng,s,target):
    # Prefer K before A when both are present: same trick result, preserves A.
    for c in ('K','A'):
        if has(eng,s,target,c):
            return c
    return None

def action(eng,e,s,z):
    feeder=z['feeder']; target=z['target']
    before='W' if feeder=='S' and target=='N' else 'E'
    behind='E' if before=='W' else 'W'

    if s.pos==0:
        # Key adaptive branch: if the first deep finesse card (9) has lost to
        # Q/J behind the target hand, cash K immediately before continuing.
        # This distinguishes the 4-trick safety line from a mechanical repeat.
        if (seen_at(eng,s,behind)&HONORS) and (not has(eng,s,target,'9')) and has(eng,s,target,'K'):
            return target,'K'
        if hand(s,feeder):
            return feeder,low(eng,hand(s,feeder))
        if hand(s,target):
            return target,cards(eng,hand(s,target))[-1]
        return None

    seat=e.order(s.leader)[s.pos]
    if seat not in eng.DECL:
        return None

    # Partner of the target hand simply unloads low if target hand led.
    if seat==feeder:
        return seat,low(eng,hand(s,seat))

    if seat!=target or s.leader!=feeder:
        return seat,low(eng,hand(s,seat))

    p=prev_def(eng,s)
    # If second hand inserts Q/J, cover as cheaply as possible.
    if p in HONORS:
        w=cheapest_above(eng,hand(s,target),p)
        if w:
            return target,w

    # Otherwise continue the progressive deep finesse: 9, then 10, ...
    t=target_low_card(eng,s,target)
    if t:
        return target,t

    t=cheapest_top(eng,s,target)
    return (target,t) if t else None

def evaluate(eng,north,south,goal,z=None):
    z=z or {'feeder':'S','target':'N'}
    e=eng.Engine2(north,south,goal)
    @lru_cache(maxsize=None)
    def F(s):
        term=e.terminal(s)
        if term is not None:
            return term[0]
        if s.pos==0:
            a=action(eng,e,s,z)
            if a is None:return 0
            seat,c=a; r=eng.R2I[c]
            lead=eng.PublicState(s.north,s.south,s.west_seen,s.east_seen,
                                 s.west_void,s.east_void,seat,0,tuple(),s.won)
            return F(e.close(e.decl_play(lead,seat,r)))
        seat=e.order(s.leader)[s.pos]
        if seat in eng.DECL:
            a=action(eng,e,s,z)
            if a is None or a[0]!=seat:return 0
            c=a[1]; r=eng.VOID if c=='-' else eng.R2I[c]
            return F(e.close(e.decl_play(s,seat,r)))
        belief=e.belief(s); ok=belief
        for r,legal in e.defender_actions(s,seat):
            ok &= ((belief&~legal)|F(e.close(e.def_play(s,seat,r))))
        return ok
    m=F(e.initial())
    return e.model.weight(m),m

def lines_fr():
    return [
      "Commencer par jouer petit de Main 2 vers le 9 de Main 1.",
      "Si l’adversaire placé en deuxième fournit la Dame ou le Valet, couvrir au plus juste.",
      "S’il fournit petit, jouer d’abord le 9.",
      "Si un des deux honneurs, Dame ou Valet, apparaît ensuite derrière Main 1, jouer un gros honneur au tour suivant ; sinon poursuivre la finesse progressive."
    ]

def label():
    return 'IMPASSE_PROFONDE_ADAPTATIVE'

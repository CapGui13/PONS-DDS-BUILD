#!/usr/bin/env python3
from __future__ import annotations

import argparse,itertools,json,sys,time
from collections import Counter
from fractions import Fraction
from functools import lru_cache
from pathlib import Path

HERE=Path(__file__).resolve().parent
sys.path.insert(0,str(HERE))
import human_batch_v44 as v44
import human_motif_v54 as v54
import human_motif_search_v59 as b

RVAL=b.RVAL
STR='AKQJT98'

def hand(s,seat):return s.north if seat=='N' else s.south
def has(eng,s,seat,c):return bool(hand(s,seat)&(1<<eng.R2I[c]))
def has_any(eng,s,c):return has(eng,s,'N',c) or has(eng,s,'S',c)
def low(eng,m):
    rr=list(eng.ranks(m));return eng.I2R[min(rr)] if rr else '-'
def high(eng,m):
    rr=list(eng.ranks(m));return eng.I2R[max(rr)] if rr else '-'
def prev_def(eng,s):
    for q,r in reversed(s.trick):
        if q not in eng.DECL:return '-' if not r else eng.I2R[r]
    return None
def lead_rank(eng,s):
    for q,r in s.trick:
        if q==s.leader:return '-' if not r else eng.I2R[r]
    return None
def seen(eng,s):return {eng.I2R[r] for r in eng.ranks(s.west_seen|s.east_seen)}
def cheapest_winner(eng,m,c):
    rr=sorted((eng.I2R[r] for r in eng.ranks(m)),key=lambda x:RVAL[x]);return next((x for x in rr if RVAL[x]>RVAL.get(c,0)),None)


def action_drop_switch(eng,e,s,z):
    cash=z['cash'];feeder=z['feeder'];target=z['target'];sw=set(z['switch']);ti=z['if_target'];te=z['else_target']
    chosen=ti if seen(eng,s)&sw else te
    if s.pos==0:
        if has_any(eng,s,cash):
            seat='N' if has(eng,s,'N',cash) else 'S';return seat,cash
        if has(eng,s,target,chosen) and hand(s,feeder):return feeder,low(eng,hand(s,feeder))
        opts=[]
        for seat in ('N','S'):
            if hand(s,seat):
                c=high(eng,hand(s,seat));opts.append((RVAL[c],seat,c))
        return max(opts)[1:] if opts else None
    seat=e.order(s.leader)[s.pos]
    if seat not in eng.DECL:return None
    lr=lead_rank(eng,s)
    if lr==cash:return seat,low(eng,hand(s,seat))
    if s.leader==feeder and seat==target and has(eng,s,target,chosen):
        p=prev_def(eng,s)
        if p not in (None,'-') and RVAL.get(p,0)>RVAL[chosen]:
            w=cheapest_winner(eng,hand(s,target),p)
            if w:return target,w
        return target,chosen
    return seat,low(eng,hand(s,seat))


def action_safety_force(eng,e,s,z):
    feeder=z['feeder'];target=z['target'];primary=z['primary'];secondary=z['secondary'];rescue=z['rescue']
    prim=has(eng,s,target,primary);sec=has(eng,s,feeder,secondary);resc=has_any(eng,s,rescue);defseen=bool(s.west_seen|s.east_seen)
    if s.pos==0:
        if prim and not defseen:return feeder,low(eng,hand(s,feeder))
        # If the primary was preserved after an honour was inserted, force with it now.
        if prim and defseen:return target,primary
        # If the primary was actually played and lost, cash the rescue honour first.
        if (not prim) and resc and s.won==0:
            seat='N' if has(eng,s,'N',rescue) else 'S';return seat,rescue
        # Then lead from the former primary hand toward the secondary card.
        if sec and hand(s,target):return target,low(eng,hand(s,target))
        opts=[]
        for seat in ('N','S'):
            if hand(s,seat):
                c=high(eng,hand(s,seat));opts.append((RVAL[c],seat,c))
        return max(opts)[1:] if opts else None
    seat=e.order(s.leader)[s.pos]
    if seat not in eng.DECL:return None
    lr=lead_rank(eng,s);p=prev_def(eng,s)
    if lr==rescue:return seat,low(eng,hand(s,seat))
    # Initial low lead toward primary: duck a higher second-hand card to preserve primary.
    if s.leader==feeder and seat==target and prim:
        if p not in (None,'-') and RVAL.get(p,0)>RVAL[primary]:return target,low(eng,hand(s,target))
        return target,primary
    # Primary led as a forcing card: partner unloads low.
    if s.leader==target and lr==primary:return seat,low(eng,hand(s,seat))
    # Secondary finesse in the opposite direction.
    if s.leader==target and seat==feeder and sec:
        if p not in (None,'-') and RVAL.get(p,0)>RVAL[secondary]:
            w=cheapest_winner(eng,hand(s,feeder),p)
            if w:return feeder,w
        return feeder,secondary
    return seat,low(eng,hand(s,seat))


def evaluate(eng,north,south,goal,z,kind):
    e=eng.Engine2(north,south,goal);fn=action_drop_switch if kind=='DROP_SWITCH' else action_safety_force
    @lru_cache(maxsize=None)
    def F(s):
        term=e.terminal(s)
        if term is not None:return term[0]
        if s.pos==0:
            a=fn(eng,e,s,z)
            if a is None:return 0
            seat,c=a;r=eng.R2I[c];lead=eng.PublicState(s.north,s.south,s.west_seen,s.east_seen,s.west_void,s.east_void,seat,0,tuple(),s.won);return F(e.close(e.decl_play(lead,seat,r)))
        seat=e.order(s.leader)[s.pos]
        if seat in eng.DECL:
            a=fn(eng,e,s,z)
            if a is None or a[0]!=seat:return 0
            c=a[1];r=eng.VOID if c=='-' else eng.R2I[c];return F(e.close(e.decl_play(s,seat,r)))
        belief=e.belief(s);ok=belief
        for r,legal in e.defender_actions(s,seat):
            ok &= ((belief&~legal)|F(e.close(e.def_play(s,seat,r))))
        return ok
    m=F(e.initial());return e.model.weight(m),m


def drop_specs(north,south):
    owned=north+south;missing=[c for c in STR if c not in owned];switches=[]
    for k in range(1,min(3,len(missing))+1):switches += list(itertools.combinations(missing,k))
    for cash in [c for c in 'AKQJT' if c in owned]:
        for feeder,target,th in [('N','S',south),('S','N',north)]:
            cards=[c for c in STR if c in th and c!=cash]
            for ti,te in itertools.permutations(cards,2):
                for sw in switches:yield {'cash':cash,'feeder':feeder,'target':target,'if_target':ti,'else_target':te,'switch':tuple(sw)}


def safety_specs(north,south):
    for feeder,target,fh,th in [('N','S',north,south),('S','N',south,north)]:
        prim=[c for c in STR if c in th];sec=[c for c in STR if c in fh];resc=[c for c in 'AKQJ' if c in fh]
        for p,s,r in itertools.product(prim,sec,resc):
            if s==r:continue
            yield {'feeder':feeder,'target':target,'primary':p,'secondary':s,'rescue':r}


def article(c):
    name={'A':'As','K':'Roi','Q':'Dame','J':'Valet','T':'10','9':'9','8':'8'}.get(c,c)
    return 'l’As' if c=='A' else ('la Dame' if c=='Q' else 'le '+name)

def toward(c):return 'vers '+article(c)


def describe(kind,z,display):
    if kind=='DROP_SWITCH':
        h=display[0] if z['feeder']=='N' else display[1];cards=' / '.join(article(c) for c in z['switch'])
        return [f"Commencer par tirer {article(z['cash'])}.",f"Si {cards} apparaît sur ce coup, jouer ensuite petit de {h} {toward(z['if_target'])} ; sinon {toward(z['else_target'])}.",'Si l’adversaire en deuxième monte au-dessus de la carte visée, couvrir au plus juste, puis jouer la couleur en tête.']
    h=display[0] if z['feeder']=='N' else display[1]
    return [f"Commencer par petit de {h} {toward(z['primary'])}.",f"Si l’adversaire joue au-dessus de {article(z['primary'])} en deuxième, conserver cette carte et la rejouer en forçante au tour suivant.",f"Si {article(z['primary'])} est pris après avoir été joué, tirer {article(z['rescue'])}, puis jouer petit dans l’autre sens {toward(z['secondary'])}."]


def analyze(eng,c,limit=0):
    e=eng.Engine2(c['north'],c['south'],c['target']);opt=Fraction(e.solve(include_policy=False)['probability_fraction']);rows=[];tested=0;t0=time.monotonic()
    streams=[('DROP_SWITCH',drop_specs(c['north'],c['south'])),('SAFETY_FORCE',safety_specs(c['north'],c['south']))]
    for kind,stream in streams:
        for z in stream:
            if limit and tested>=limit:break
            try:p,mask=evaluate(eng,c['north'],c['south'],c['target'],z,kind);tested+=1
            except Exception:continue
            if p==opt:rows.append({'kind':kind,'spec':{k:(list(v) if isinstance(v,tuple) else v) for k,v in z.items()},'lines':describe(kind,z,c['display']),'mask':str(mask)})
        if limit and tested>=limit:break
    rows.sort(key=lambda r:(len(r['lines']),0 if r['kind']=='SAFETY_FORCE' else 1,len(json.dumps(r['spec']))));return {'id':c['id'],'display':c['display'],'north':c['north'],'south':c['south'],'target':c['target'],'fraction':str(opt),'found':bool(rows),'best':rows[0] if rows else None,'exact_candidates':len(rows),'tested':tested,'elapsed_seconds':round(time.monotonic()-t0,3)}


def main():
    ap=argparse.ArgumentParser();ap.add_argument('--runtime-root',required=True);ap.add_argument('--out-dir',required=True);ap.add_argument('--limit',type=int,default=0);a=ap.parse_args();eng=v54.load_engine(a.runtime_root);rows=[];found=0;t0=time.monotonic()
    for c in v44.CASES:
        r=analyze(eng,c,a.limit);rows.append(r);found+=int(r['found']);print(json.dumps({'case':c['id'],'found':r['found'],'kind':(r['best'] or {}).get('kind'),'tested':r['tested'],'sec':r['elapsed_seconds']},ensure_ascii=False),flush=True)
    summary={'schema':'MANIEMENTS_V5_HUMAN_V513_CONDITIONAL_REVIEWED_V1','cases':len(rows),'found':found,'coverage_percent':f'{100*found/len(rows):.2f}','elapsed_seconds':round(time.monotonic()-t0,3),'runtime_frozen_sha256':'a0b580531f3c9e8bb00710b9c3e1c183b27cbfe9231c9d584e29a374ba88835d','families':'DROP_SWITCH; SAFETY_FORCE','rule':'complete conditional strategy is replayed exhaustively; only exact oracle matches are accepted'}
    od=Path(a.out_dir);od.mkdir(parents=True,exist_ok=True);(od/'HUMAN_V513_CONDITIONAL_REVIEWED.json').write_text(json.dumps({'summary':summary,'cases':rows},ensure_ascii=False,indent=2)+'\n',encoding='utf-8');(od/'SUMMARY.txt').write_text('\n'.join(f'{k}={v}' for k,v in summary.items())+'\n',encoding='utf-8');print(json.dumps(summary,ensure_ascii=False),flush=True)

if __name__=='__main__':main()

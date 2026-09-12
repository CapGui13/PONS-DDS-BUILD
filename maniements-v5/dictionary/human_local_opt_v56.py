#!/usr/bin/env python3
from __future__ import annotations

import argparse, json, sys, time
from collections import Counter, defaultdict
from fractions import Fraction
from functools import lru_cache
from pathlib import Path

HERE=Path(__file__).resolve().parent
sys.path.insert(0,str(HERE))
import human_semantic_v52 as v52
import human_motif_v54 as v54


def next_round(s,ns,rnd):
    return rnd+1 if s.pos>0 and ns.pos==0 else rnd


def decl_candidates(eng,e,s):
    rows=[]
    if s.pos==0:
        pools=[(seat,s.north if seat=='N' else s.south) for seat in ('N','S') if (s.north if seat=='N' else s.south)]
    else:
        seat=e.order(s.leader)[s.pos]
        if seat not in eng.DECL:return []
        pools=[(seat,s.north if seat=='N' else s.south)]
    for seat,hand in pools:
        rr=eng.ranks(hand) if hand else ((eng.VOID,) if s.pos else tuple())
        for r in rr:
            if s.pos==0:
                lead=eng.PublicState(s.north,s.south,s.west_seen,s.east_seen,s.west_void,s.east_void,seat,0,tuple(),s.won)
                ns=e.close(e.decl_play(lead,seat,r))
            else:
                ns=e.close(e.decl_play(s,seat,r))
            fr=e.frontier(ns)
            val=max((e.model.weight(m) for m in fr),default=Fraction())
            rows.append((seat,r,ns,val))
    if not rows:return []
    best=max(x[3] for x in rows)
    return [(seat,r,ns,val,val==best) for seat,r,ns,val in rows]


def action_sets(eng,e,s,cands):
    if s.pos==0:
        pools=[(seat,s.north if seat=='N' else s.south) for seat in ('N','S') if (s.north if seat=='N' else s.south)]
    else:
        seat=e.order(s.leader)[s.pos]
        if seat not in eng.DECL:return set(),set()
        pools=[(seat,s.north if seat=='N' else s.south)]
    exact_raw={(seat,'-' if not r else eng.I2R[r]) for seat,r,_,_,ok in cands if ok}
    legal=set();exact=set()
    for seat,hand in pools:
        rr=['-' if not r else eng.I2R[r] for r in (eng.ranks(hand) if hand else (eng.VOID,))]
        ex=[r for a,r in exact_raw if a==seat]
        l,e2=v52.sem_low_set(rr,ex)
        legal|={(seat,r) for r in l};exact|={(seat,r) for r in e2}
    return legal,exact


def collect_all_optimal_states(eng,e):
    rows=[];seen=set();cache={}
    def dc(s):
        if s not in cache:cache[s]=decl_candidates(eng,e,s)
        return cache[s]
    def walk(s,rnd):
        key=(s,rnd)
        if key in seen:return
        seen.add(key)
        if e.terminal(s) is not None:return
        if s.pos==0 or e.order(s.leader)[s.pos] in eng.DECL:
            cands=dc(s);legal,exact=action_sets(eng,e,s,cands)
            f=v52.base_features(eng,e,s,rnd)
            rows.append({'features':f,'legal':legal,'exact':exact,'irrelevant':bool(legal) and legal==exact,'state':s})
            for _,_,ns,_,ok in cands:
                if ok:walk(ns,next_round(s,ns,rnd))
            return
        seat=e.order(s.leader)[s.pos]
        for r,_legal in e.defender_actions(s,seat):
            ns=e.close(e.def_play(s,seat,r));walk(ns,next_round(s,ns,rnd))
    walk(e.initial(),1)
    return rows,cache


def concrete_match(eng,sem,seat,r):
    a,x=sem
    if a!=seat:return False
    c='-' if not r else eng.I2R[r]
    if x=='x':return c in v52.LOW
    return c==x


def natural_concrete(eng,e,s,cands,sem=None):
    good=[x for x in cands if x[4]]
    if sem is not None:
        z=[x for x in good if concrete_match(eng,sem,x[0],x[1])]
        if z:good=z
    if not good:return None
    if s.pos==0:
        def key(x):
            seat,r,_,_,_=x;c='-' if not r else eng.I2R[r];v=v52.b.RANK_VALUE.get(c,0)
            # If a semantic action is prescribed, keep the cheapest matching concrete spot.
            if sem is not None:return (v,0 if seat=='N' else 1)
            # On strategically irrelevant leads prefer a top honour, otherwise the cheapest card.
            pref=0 if c in 'AKQJ' else 1
            return (pref,-v if pref==0 else v,0 if seat=='N' else 1)
        return min(good,key=key)
    prev=v52.v45.previous_def_card(eng,e,s)
    def key(x):
        seat,r,_,_,_=x;c='-' if not r else eng.I2R[r];v=v52.b.RANK_VALUE.get(c,0)
        if prev and prev!=eng.VOID:
            pc=eng.I2R[prev];pv=v52.b.RANK_VALUE.get(pc,0)
            return (0 if v>pv else 1,v)
        return (v,)
    return min(good,key=key)


def build_maps(norm):
    coarse={};fine={}
    for r in norm:
        if r['tier']=='strategic':coarse[v52.coarse_key(r['features'])]=r['action']
        else:fine[v52.exact_key(r['features'])]=r['action']
    return coarse,fine


def replay_policy(eng,e,coarse,fine,cand_cache):
    @lru_cache(maxsize=None)
    def F(s,rnd):
        term=e.terminal(s)
        if term is not None:return term[0]
        if s.pos==0 or e.order(s.leader)[s.pos] in eng.DECL:
            f=v52.base_features(eng,e,s,rnd)
            sem=fine.get(v52.exact_key(f),coarse.get(v52.coarse_key(f)))
            cands=cand_cache.get(s)
            if cands is None:
                cands=decl_candidates(eng,e,s);cand_cache[s]=cands
            row=natural_concrete(eng,e,s,cands,sem)
            if row is None:return 0
            _seat,_r,ns,_v,_ok=row
            return F(ns,next_round(s,ns,rnd))
        seat=e.order(s.leader)[s.pos];belief=e.belief(s);successful=belief
        for r,legal in e.defender_actions(s,seat):
            ns=e.close(e.def_play(s,seat,r));branch=F(ns,next_round(s,ns,rnd))
            successful &= ((belief & ~legal) | branch)
        return successful
    return F(e.initial(),1)


def render_lines(norm,top,bottom):
    grouped=defaultdict(list)
    for r in norm:
        f=r['features'];key=(f['round'],f['phase'],f.get('leader'),f.get('seat'))
        grouped[key].append({'features':f,'label':v52.public_action(r['action'],f['phase']),'tier':r['tier']})
    lines=[];spot=False;rules=0
    for key,ss in sorted(grouped.items(),key=lambda kv:str(kv[0])):
        c,sp=v52.compress_group(ss,top,bottom)
        if c is None:return {'ok':False,'reason':'rules_not_separable','lines':[],'spot':True,'rules':rules}
        spot|=sp or any(x['tier']=='spots' for x in ss)
        rnd,phase,leader,seat=key;prefix=f"Au {rnd}{'er' if rnd==1 else 'e'} tour"
        for rr in c['rules']:
            cond=' et '.join(v52.human_atom(k,v,top,bottom) for k,v in rr['if'])
            prev=next((v for k,v in rr['if'] if k=='prev_card'),None)
            lines.append(f"{prefix}, si {cond} : {v52.action_text(rr['label'],phase,top,bottom,prev)}.");rules+=1
        if not (phase=='response' and c['default']=='-'):
            lines.append(f"{prefix}, {'sinon : ' if c['rules'] else ''}{v52.action_text(c['default'],phase,top,bottom)}.");rules+=1
    ded=[]
    for x in lines:
        if x not in ded:ded.append(x)
    return {'ok':True,'lines':ded,'spot':spot,'rules':rules}


def analyze(eng,c,p):
    target=int(p['target']);e=eng.Engine2(c['north'],c['south'],target);root=e.initial();fr=e.frontier(root);opt=max(e.model.weight(m) for m in fr)
    rows,cache=collect_all_optimal_states(eng,e)
    norm,refined,conflicts,irrelevant=v52.normalize_states(rows)
    top,bottom=c['display']
    if conflicts:
        return {'target':target,'fraction':str(opt),'ok':False,'reason':'observable_conflict','conflicts':conflicts[:5],'all_opt_states':len(rows),'normalized_states':len(norm)}
    coarse,fine=build_maps(norm);mask=replay_policy(eng,e,coarse,fine,cache);p_replay=e.model.weight(mask);exact=(p_replay==opt)
    rendered=render_lines(norm,top,bottom)
    lines=v54.naturalize(rendered['lines'],c['display']) if rendered.get('ok') else []
    generic=rendered.get('ok',False) and not rendered.get('spot',True) and refined==0
    compact=exact and generic and v54.exact_quality(lines)
    ready=compact and v54.bridge_ready(lines)
    upstream=v54.clean(p.get('qualification',{}).get('candidate_why') or p.get('why') or '',c['display'])
    why=v54.exact_reason(eng,c['north'],c['south'],target,upstream) if ready else upstream
    return {'target':target,'fraction':str(opt),'ok':exact,'replay_fraction':str(p_replay),'all_opt_states':len(rows),'normalized_states':len(norm),'irrelevant_states':irrelevant,'refined_states':refined,'generic':generic,'exact_compact':compact,'bridge_ready':ready,'raw_rule_count':rendered.get('rules',0),'lines':lines,'why':why,'coarse_rules':len(coarse),'fine_rules':len(fine)}


def main():
    ap=argparse.ArgumentParser();ap.add_argument('--input',required=True);ap.add_argument('--runtime-root',required=True);ap.add_argument('--out-dir',required=True);a=ap.parse_args()
    eng=v54.load_engine(a.runtime_root);src=json.load(open(a.input,encoding='utf-8'));out=[];cnt=Counter();started=time.monotonic()
    for c in src['cases']:
        cc={'id':c['id'],'north':c['north'],'south':c['south'],'display':c['display'],'profiles':[]}
        for p in c['profiles']:
            if not p.get('qualification',{}).get('counted'):continue
            t0=time.monotonic();r=analyze(eng,c,p);r['elapsed_seconds']=round(time.monotonic()-t0,3);cc['profiles'].append(r)
            cnt['profiles']+=1;cnt['exact_replay']+=int(r.get('ok',False));cnt['generic']+=int(r.get('generic',False));cnt['exact_compact']+=int(r.get('exact_compact',False));cnt['bridge_ready']+=int(r.get('bridge_ready',False));cnt['conflicts']+=int(r.get('reason')=='observable_conflict')
            print(json.dumps({'case':c['id'],'target':r['target'],'exact':r.get('ok'),'generic':r.get('generic'),'compact':r.get('exact_compact'),'ready':r.get('bridge_ready'),'states':r.get('all_opt_states'),'norm':r.get('normalized_states'),'sec':r['elapsed_seconds']},ensure_ascii=False),flush=True)
        out.append(cc)
    summary={'schema':'MANIEMENTS_V5_HUMAN_V56_LOCAL_OPT_V1',**dict(cnt),'exact_compact_rate_percent':f"{100*cnt['exact_compact']/cnt['profiles']:.2f}" if cnt['profiles'] else '0.00','bridge_ready_rate_percent':f"{100*cnt['bridge_ready']/cnt['profiles']:.2f}" if cnt['profiles'] else '0.00','elapsed_seconds':round(time.monotonic()-started,3),'runtime_frozen_sha256':'a0b580531f3c9e8bb00710b9c3e1c183b27cbfe9231c9d584e29a374ba88835d','principle':'synthesize from all locally co-optimal public actions, then exact-replay the resulting abstract policy'}
    od=Path(a.out_dir);od.mkdir(parents=True,exist_ok=True);(od/'HUMAN_V56_LOCAL_OPT.json').write_text(json.dumps({'summary':summary,'cases':out},ensure_ascii=False,indent=2)+'\n',encoding='utf-8');(od/'SUMMARY.txt').write_text('\n'.join(f'{k}={json.dumps(v,ensure_ascii=False) if isinstance(v,(dict,list)) else v}' for k,v in summary.items())+'\n',encoding='utf-8');print(json.dumps(summary,ensure_ascii=False),flush=True)

if __name__=='__main__':main()

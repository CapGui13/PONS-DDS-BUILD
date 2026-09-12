#!/usr/bin/env python3
from __future__ import annotations

import argparse, itertools, json, sys, time
from collections import Counter
from pathlib import Path

HERE=Path(__file__).resolve().parent
sys.path.insert(0,str(HERE))
import human_motif_search_v572 as w

v=w.v
FR={'A':'As','K':'Roi','Q':'Dame','J':'Valet','T':'10','9':'9','8':'8'}
ORD={1:'sec',2:'second',3:'troisième',4:'quatrième',5:'cinquième',6:'sixième',7:'septième'}


def relation_side(best):
    # When South leads toward North, West is the defender in second hand; vice versa.
    if not best:return None,None
    feeder=best.get('feeder');target=best.get('target_hand')
    if feeder=='S' and target=='N':return 'W','E'
    if feeder=='N' and target=='S':return 'E','W'
    return None,None


def owner_mask(e,rank,side):
    return e.model.owner[side][v54_engine(e).R2I[rank]]


def v54_engine(e):
    # integrated_engine module is the module owning the engine class.
    return sys.modules[e.__class__.__module__]


def atomic_masks(eng,e):
    missing=[eng.I2R[r] for r in e.model.missing]
    strategic=[r for r in missing if r in 'AKQJT98']
    n=e.model.n;atoms=[]
    for r in strategic:
        for side in ('W','E'):
            own=e.model.owner[side][eng.R2I[r]]
            atoms.append((own,('owner',r,side),1))
            for k in range(1,len(missing)+1):
                m=0
                for i in range(n):
                    h=e.model.world_w[i] if side=='W' else e.model.world_e[i]
                    if h.bit_count()==k and (own&(1<<i)):m|=1<<i
                if m:atoms.append((m,('owner_len',r,side,k),2))
    for side in ('W','E'):
        for k in range(0,len(missing)+1):
            m=0
            for i in range(n):
                h=e.model.world_w[i] if side=='W' else e.model.world_e[i]
                if h.bit_count()==k:m|=1<<i
            if m:atoms.append((m,('len',side,k),2))
    for a,b in itertools.combinations(strategic,2):
        for side in ('W','E'):
            m=e.model.owner[side][eng.R2I[a]]&e.model.owner[side][eng.R2I[b]]
            if m:atoms.append((m,('pair',a,b,side),2))
    # Keep the cheapest label for each identical predicate mask.
    d={}
    for m,lab,cost in atoms:
        if m not in d or cost<d[m][1]:d[m]=(lab,cost)
    return [(m,lab,cost) for m,(lab,cost) in d.items()]


def expression_for(eng,e,success):
    allm=e.model.all;fail=allm&~success;atoms=atomic_masks(eng,e)
    # Terms are atoms or conjunctions of two atoms.  This is deliberately bounded:
    # reasons more complex than two small bridge conditions remain uncertified prose.
    terms={}
    for m,lab,cost in atoms:terms[m]=(cost,('atom',lab))
    for i,(m1,l1,c1) in enumerate(atoms):
        for m2,l2,c2 in atoms[i+1:]:
            m=m1&m2
            if not m:continue
            cost=c1+c2+1
            if m not in terms or cost<terms[m][0]:terms[m]=(cost,('and',l1,l2))
    rows=[(m,c,x) for m,(c,x) in terms.items()]
    for target,kind in ((success,'success'),(fail,'fail')):
        direct=[(c,x) for m,c,x in rows if m==target]
        if direct:
            c,x=min(direct,key=lambda z:z[0]);return {'kind':kind,'expr':x,'cost':c}
        sub=[(m,c,x) for m,c,x in rows if m and not (m&~target)]
        sub.sort(key=lambda z:z[1]);sub=sub[:450]
        best=None
        for i,(m1,c1,x1) in enumerate(sub):
            for m2,c2,x2 in sub[i+1:]:
                if (m1|m2)!=target:continue
                cost=c1+c2+1
                if best is None or cost<best[0]:best=(cost,('or',x1,x2))
        if best:return {'kind':kind,'expr':best[1],'cost':best[0]}
    return None


def rank_fr(r):
    x=FR.get(r,r)
    return ('l’'+x) if x=='As' else ('le '+x)


def side_phrase(side,onside,offside):
    if side==onside:return 'chez l’adversaire placé en deuxième'
    if side==offside:return 'chez l’autre adversaire'
    return 'dans cette main adverse'


def atom_fr(atom,onside,offside,total_missing):
    typ=atom[0]
    if typ=='owner':
        _,r,side=atom
        if side==onside:return rank_fr(r)+' est placé'
        if side==offside:return rank_fr(r)+' est mal placé'
        return rank_fr(r)+' est '+side_phrase(side,onside,offside)
    if typ=='pair':
        _,a,b,side=atom
        names=rank_fr(a)+' et '+rank_fr(b)
        if side==onside:return names+' sont tous les deux placés'
        if side==offside:return names+' sont tous les deux mal placés'
        return names+' sont réunis '+side_phrase(side,onside,offside)
    if typ=='owner_len':
        _,r,side,k=atom;qual=ORD.get(k,str(k)+'ième')
        if side==onside:return rank_fr(r)+' est '+qual+' chez l’adversaire placé en deuxième'
        if side==offside:return rank_fr(r)+' est '+qual+' chez l’autre adversaire'
        return rank_fr(r)+' est '+qual
    if typ=='len':
        _,side,k=atom
        who='l’adversaire placé en deuxième' if side==onside else 'l’autre adversaire'
        if k==0:return who+' est chicane'
        if k==total_missing:return who+' possède toutes les cartes manquantes (partage '+str(total_missing)+'–0)'
        return who+' possède '+str(k)+' carte'+('s' if k!=1 else '')+' dans la couleur'
    return str(atom)


def expr_fr(expr,onside,offside,total_missing):
    typ=expr[0]
    if typ=='atom':return atom_fr(expr[1],onside,offside,total_missing)
    if typ=='and':return atom_fr(expr[1],onside,offside,total_missing)+' et '+atom_fr(expr[2],onside,offside,total_missing)
    if typ=='or':
        a=expr_fr(expr[1],onside,offside,total_missing);b=expr_fr(expr[2],onside,offside,total_missing)
        return a+' ; ou '+b
    return str(expr)


def exact_reason(eng,c,p,best):
    cash=tuple(best['cash']);feeder=best['feeder'];target=best['target_hand'];targets=tuple(best['targets'])
    prob,mask=v.evaluate(eng,c['north'],c['south'],int(p['target']),cash,feeder,target,targets)
    e=eng.Engine2(c['north'],c['south'],int(p['target']))
    x=expression_for(eng,e,mask)
    if not x:return {'certified':False,'reason':'','expression':None}
    onside,offside=relation_side(best);total=len(e.model.missing);body=expr_fr(x['expr'],onside,offside,total)
    if x['kind']=='success':text='Avec ce maniement, l’objectif est atteint exactement lorsque '+body+'.'
    else:text='Avec ce maniement, l’objectif n’échoue que lorsque '+body+'.'
    # Keep the normal view simple. More complicated exact formulae remain metadata.
    return {'certified':x['cost']<=5,'reason':text,'expression':x,'probability_fraction':str(prob)}


def main():
    ap=argparse.ArgumentParser();ap.add_argument('--input',required=True);ap.add_argument('--runtime-root',required=True);ap.add_argument('--out-dir',required=True);a=ap.parse_args()
    eng=v.v54.load_engine(a.runtime_root);src=json.load(open(a.input,encoding='utf-8'));cases=[];cnt=Counter();started=time.monotonic()
    for c in src['cases']:
        cc={'id':c['id'],'north':c['north'],'south':c['south'],'display':c['display'],'profiles':[]}
        for p in c['profiles']:
            cnt['profiles']+=1
            z=dict(p);best=z.get('best')
            if not z.get('found') or not best:
                z['reason_certification']={'certified':False,'reason':'','expression':None};z['bridge_ready']=False;cc['profiles'].append(z);continue
            rc=exact_reason(eng,c,z,best);z['reason_certification']=rc;z['bridge_ready']=bool(rc['certified']);cnt['motif_exact']+=1;cnt['reason_certified']+=int(rc['certified']);cnt['bridge_ready']+=int(z['bridge_ready']);cc['profiles'].append(z)
            print(json.dumps({'case':c['id'],'target':z['target'],'motif':best['motif'],'reason':rc['certified'],'cost':(rc.get('expression') or {}).get('cost')},ensure_ascii=False),flush=True)
        cases.append(cc)
    summary={'schema':'MANIEMENTS_V5_HUMAN_V58_WORLD_REASON_V1',**dict(cnt),'motif_coverage_percent':f"{100*cnt['motif_exact']/cnt['profiles']:.2f}" if cnt['profiles'] else '0.00','reason_certified_percent':f"{100*cnt['reason_certified']/cnt['profiles']:.2f}" if cnt['profiles'] else '0.00','runtime_frozen_sha256':'a0b580531f3c9e8bb00710b9c3e1c183b27cbfe9231c9d584e29a374ba88835d','reason_rule':'exact success/failure world set must equal a bounded Boolean formula of bridge-visible layout predicates'}
    od=Path(a.out_dir);od.mkdir(parents=True,exist_ok=True);(od/'HUMAN_V58_WORLD_REASON.json').write_text(json.dumps({'summary':summary,'cases':cases},ensure_ascii=False,indent=2)+'\n',encoding='utf-8');(od/'SUMMARY.txt').write_text('\n'.join(f'{k}={json.dumps(v,ensure_ascii=False) if isinstance(v,(dict,list)) else v}' for k,v in summary.items())+'\n',encoding='utf-8');print(json.dumps(summary,ensure_ascii=False),flush=True)

if __name__=='__main__':main()

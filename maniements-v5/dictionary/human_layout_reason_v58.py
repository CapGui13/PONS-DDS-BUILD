#!/usr/bin/env python3
from __future__ import annotations

import argparse, itertools, json, sys, time
from collections import Counter
from pathlib import Path

HERE=Path(__file__).resolve().parent
sys.path.insert(0,str(HERE))

import human_motif_v54 as v54
import human_motif_search_v571 as v571

v=v571.v

ART={'A':"l’As",'K':'le Roi','Q':'la Dame','J':'le Valet','T':'le 10','9':'le 9','8':'le 8'}
STR='AKQJT98'


def owner(e,i,r):
    return 'W' if e.model.owner['W'][r] & (1<<i) else 'E'


def wmasks(e):
    n=e.model.all.bit_count()
    return range(n)


def mask_where(e,pred):
    m=0
    for i in wmasks(e):
        if pred(i):m|=1<<i
    return m


def side_len(e,i,side):
    return (e.model.world_w[i] if side=='W' else e.model.world_e[i]).bit_count()


def cname(eng,r):
    return ART.get(eng.I2R[r],'le '+eng.I2R[r])


def add_atom(rows,mask,text,cost=1,kind='layout',meta=None):
    if mask in (0,):return
    row={'mask':mask,'text':text,'cost':cost,'kind':kind,'meta':meta or {}}
    old=next((x for x in rows if x['mask']==mask),None)
    if old is None or (cost,len(text)) < (old['cost'],len(old['text'])):
        if old is not None:rows.remove(old)
        rows.append(row)


def build_atoms(eng,e,target_hand=None):
    rows=[];allm=e.model.all
    missing=[r for r in e.model.missing if eng.I2R[r] in STR]
    fav=None
    if target_hand in ('N','S'):
        fav='W' if target_hand=='N' else 'E'
        bad='E' if fav=='W' else 'W'
        for r in missing:
            pm=mask_where(e,lambda i,r=r:owner(e,i,r)==fav)
            add_atom(rows,pm,f"{cname(eng,r)} est placé",1,'placement',{'rank':eng.I2R[r],'value':'fav'})
            add_atom(rows,allm&~pm,f"{cname(eng,r)} est mal placé",1,'placement',{'rank':eng.I2R[r],'value':'bad'})
            for ln,label in ((1,'sec'),(2,'second')):
                mm=mask_where(e,lambda i,r=r,ln=ln: owner(e,i,r)==fav and side_len(e,i,fav)==ln)
                add_atom(rows,mm,f"{cname(eng,r)} est {label} et placé",2,'honor_length',{'rank':eng.I2R[r],'value':'fav','len':ln})
                mm=mask_where(e,lambda i,r=r,ln=ln: owner(e,i,r)==bad and side_len(e,i,bad)==ln)
                add_atom(rows,mm,f"{cname(eng,r)} est {label} et mal placé",2,'honor_length',{'rank':eng.I2R[r],'value':'bad','len':ln})

    # Orientation-free distribution and honour-combination atoms.
    total=len(e.model.missing)
    for a in range(total+1):
        b=total-a
        if a>b:continue
        mm=mask_where(e,lambda i,a=a,b=b: sorted((side_len(e,i,'W'),side_len(e,i,'E')))==[a,b])
        add_atom(rows,mm,f"le partage adverse est {b}–{a}",2,'split',{'split':[b,a]})

    for r in missing:
        mm=mask_where(e,lambda i,r=r: (owner(e,i,r)=='W' and side_len(e,i,'W')==1) or (owner(e,i,r)=='E' and side_len(e,i,'E')==1))
        add_atom(rows,mm,f"{cname(eng,r)} est sec",2,'honor_length',{'rank':eng.I2R[r],'len':1})
        mm=mask_where(e,lambda i,r=r: (owner(e,i,r)=='W' and side_len(e,i,'W')==2) or (owner(e,i,r)=='E' and side_len(e,i,'E')==2))
        add_atom(rows,mm,f"{cname(eng,r)} est second",2,'honor_length',{'rank':eng.I2R[r],'len':2})

    for a,b in itertools.combinations(missing,2):
        an,bn=cname(eng,a),cname(eng,b)
        same=mask_where(e,lambda i,a=a,b=b:owner(e,i,a)==owner(e,i,b))
        add_atom(rows,same,f"{an} et {bn} sont réunis dans la même main adverse",2,'pair',{'ranks':[eng.I2R[a],eng.I2R[b]],'relation':'same'})
        add_atom(rows,allm&~same,f"{an} et {bn} sont séparés",2,'pair',{'ranks':[eng.I2R[a],eng.I2R[b]],'relation':'split'})
        dbl=mask_where(e,lambda i,a=a,b=b: owner(e,i,a)==owner(e,i,b) and side_len(e,i,owner(e,i,a))==2)
        add_atom(rows,dbl,f"{an} et {bn} sont seconds ensemble",2,'pair_doubleton',{'ranks':[eng.I2R[a],eng.I2R[b]]})
        if fav:
            af=next((x for x in rows if x['kind']=='placement' and x['meta'].get('rank')==eng.I2R[a] and x['meta'].get('value')=='fav'),None)
            bf=next((x for x in rows if x['kind']=='placement' and x['meta'].get('rank')==eng.I2R[b] and x['meta'].get('value')=='fav'),None)
            if af and bf:
                add_atom(rows,af['mask']|bf['mask'],f"au moins l’un de {an} ou {bn} est placé",2,'pair_placement',{'ranks':[eng.I2R[a],eng.I2R[b]],'relation':'any_fav'})
                add_atom(rows,af['mask']&bf['mask'],f"{an} et {bn} sont tous deux placés",2,'pair_placement',{'ranks':[eng.I2R[a],eng.I2R[b]],'relation':'both_fav'})
                add_atom(rows,allm&( ~(af['mask']|bf['mask']) ),f"{an} et {bn} sont tous deux mal placés",2,'pair_placement',{'ranks':[eng.I2R[a],eng.I2R[b]],'relation':'both_bad'})
    return rows


def best_formula(target,atoms,allm):
    cand=[]
    for a in atoms:
        if a['mask']==target:cand.append((a['cost'],len(a['text']),a['text'],[a]))
    # Two-atom formulas cover placement + split, paired honours, safety layouts, etc.
    for a,b in itertools.combinations(atoms,2):
        for op,mask,word,extra in (
            ('AND',a['mask']&b['mask'],' et ',1),
            ('OR',a['mask']|b['mask'],' ou ',1),
            ('A_NOT_B',a['mask']&(allm&~b['mask']),' et non ',2),
        ):
            if mask!=target:continue
            text=(a['text']+word+b['text'])
            cand.append((a['cost']+b['cost']+extra,len(text),text,[a,b]))
    if not cand:return None
    cand.sort(key=lambda x:(x[0],x[1]))
    cost,_,text,used=cand[0]
    return {'text':text,'cost':cost,'atoms':[{'text':x['text'],'kind':x['kind'],'meta':x['meta']} for x in used]}


def one_world_reason(eng,e,mask,success):
    ids=[i for i in wmasks(e) if mask&(1<<i)]
    if len(ids)!=1:return None
    i=ids[0];w=e.model.world_w[i];ee=e.model.world_e[i]
    def cards(m):
        conv={'K':'R','Q':'D','J':'V','T':'X'}
        return ''.join(conv.get(eng.I2R[r],eng.I2R[r]) for r in sorted(eng.ranks(m),reverse=True)) or '—'
    a,b=w.bit_count(),ee.bit_count()
    if success:
        return f"Le maniement ne réussit que contre cette position précise : {cards(w)} d’un côté et {cards(ee)} de l’autre (partage {max(a,b)}–{min(a,b)})."
    return f"Le maniement n’échoue que contre cette position précise : {cards(w)} d’un côté et {cards(ee)} de l’autre (partage {max(a,b)}–{min(a,b)})."


def reason_for_mask(eng,e,mask,target_hand=None):
    allm=e.model.all;fail=allm&~mask;atoms=build_atoms(eng,e,target_hand)
    sf=best_formula(mask,atoms,allm);ff=best_formula(fail,atoms,allm)
    choices=[]
    if sf:choices.append((sf['cost'],0,'success',sf))
    if ff:choices.append((ff['cost'],1,'failure',ff))
    # Prefer a one-world failure/success explanation when no equally simple symbolic formula exists.
    owf=one_world_reason(eng,e,fail,False);ows=one_world_reason(eng,e,mask,True)
    if owf:choices.append((3,2,'failure_world',{'text':owf,'cost':3,'atoms':[]}))
    if ows:choices.append((3,3,'success_world',{'text':ows,'cost':3,'atoms':[]}))
    if not choices:return {'certified':False,'reason':'','mode':'NONE'}
    choices.sort(key=lambda x:(x[0],x[1],len(x[3]['text'])))
    _,_,mode,f=choices[0]
    if mode=='success':text='Le maniement réussit exactement lorsque '+f['text']+'.'
    elif mode=='failure':text='Le maniement échoue exactement lorsque '+f['text']+' ; toutes les autres positions sont couvertes.'
    else:text=f['text']
    return {'certified':True,'reason':text,'mode':mode,'formula':f}


def profile_mask(eng,c,p):
    best=p.get('best') or {}
    e=eng.Engine2(c['north'],c['south'],int(p['target']))
    if best:
        prob,mask=v.evaluate(eng,c['north'],c['south'],int(p['target']),tuple(best.get('cash') or []),best.get('feeder','N'),best.get('target_hand','S'),tuple(best.get('targets') or []))
        return e,mask,best.get('target_hand') if best.get('targets') else None,'MOTIF'
    # No motif yet: mine the default exact success set anyway, useful for future motif work.
    fr=e.frontier(e.initial());mask=max(fr,key=lambda m:(e.model.weight(m),m))
    return e,mask,None,'ORACLE_DEFAULT'


def main():
    ap=argparse.ArgumentParser();ap.add_argument('--motifs',required=True);ap.add_argument('--runtime-root',required=True);ap.add_argument('--out-dir',required=True);a=ap.parse_args()
    eng=v54.load_engine(a.runtime_root);src=json.load(open(a.motifs,encoding='utf-8'));out=[];cnt=Counter();started=time.monotonic()
    for c in src['cases']:
        cc={k:c[k] for k in ('id','north','south','display')};cc['profiles']=[]
        for p in c['profiles']:
            e,mask,target_hand,source=profile_mask(eng,c,p);r=reason_for_mask(eng,e,mask,target_hand)
            z={'target':p['target'],'fraction':p['fraction'],'motif_found':bool(p.get('found')),'motif':(p.get('best') or {}).get('motif'),'source_mask':source,'target_hand':target_hand,**r}
            cc['profiles'].append(z);cnt['profiles']+=1;cnt['motif_profiles']+=int(bool(p.get('found')));cnt['reason_certified']+=int(r['certified']);cnt['motif_reason_certified']+=int(bool(p.get('found')) and r['certified'])
            print(json.dumps({'case':c['id'],'target':p['target'],'motif':bool(p.get('found')),'reason':r['certified'],'mode':r.get('mode')},ensure_ascii=False),flush=True)
        out.append(cc)
    summary={'schema':'MANIEMENTS_V5_HUMAN_V58_LAYOUT_REASON_V1',**dict(cnt),'reason_rate_percent':f"{100*cnt['reason_certified']/cnt['profiles']:.2f}" if cnt['profiles'] else '0.00','motif_reason_rate_percent':f"{100*cnt['motif_reason_certified']/cnt['motif_profiles']:.2f}" if cnt['motif_profiles'] else '0.00','elapsed_seconds':round(time.monotonic()-started,3),'runtime_frozen_sha256':'a0b580531f3c9e8bb00710b9c3e1c183b27cbfe9231c9d584e29a374ba88835d','rule':'only exact Boolean characterizations of the exhaustively replayed success/failure world set are promoted'}
    od=Path(a.out_dir);od.mkdir(parents=True,exist_ok=True);(od/'HUMAN_V58_LAYOUT_REASON.json').write_text(json.dumps({'summary':summary,'cases':out},ensure_ascii=False,indent=2)+'\n',encoding='utf-8');(od/'SUMMARY.txt').write_text('\n'.join(f'{k}={json.dumps(v,ensure_ascii=False) if isinstance(v,(dict,list)) else v}' for k,v in summary.items())+'\n',encoding='utf-8');print(json.dumps(summary,ensure_ascii=False),flush=True)

if __name__=='__main__':main()

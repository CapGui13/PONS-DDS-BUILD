#!/usr/bin/env python3
from __future__ import annotations

import itertools
import human_layout_reason_v58 as v58


def _candidate(cand,mask,target,text,cost,used):
    if mask==target:
        cand.append((cost,len(text),text,used))


def best_formula(target,atoms,allm):
    cand=[]
    for a in atoms:
        _candidate(cand,a['mask'],target,a['text'],a['cost'],[a])
    for a,b in itertools.combinations(atoms,2):
        _candidate(cand,a['mask']&b['mask'],target,a['text']+' et '+b['text'],a['cost']+b['cost']+1,[a,b])
        _candidate(cand,a['mask']|b['mask'],target,a['text']+' ou '+b['text'],a['cost']+b['cost']+1,[a,b])
        _candidate(cand,a['mask']&(allm&~b['mask']),target,a['text']+' et non '+b['text'],a['cost']+b['cost']+2,[a,b])
    # Three atoms: only common bridge-readable Boolean shapes. This is exhaustive
    # over the selected atoms for these shapes; no approximate formula is accepted.
    for a,b,c in itertools.combinations(atoms,3):
        aa,bb,cc=a['mask'],b['mask'],c['mask']
        ca=a['cost']+b['cost']+c['cost']
        _candidate(cand,aa&bb&cc,target,a['text']+' et '+b['text']+' et '+c['text'],ca+2,[a,b,c])
        _candidate(cand,aa|bb|cc,target,a['text']+' ou '+b['text']+' ou '+c['text'],ca+2,[a,b,c])
        _candidate(cand,(aa&bb)|cc,target,'('+a['text']+' et '+b['text']+') ou '+c['text'],ca+3,[a,b,c])
        _candidate(cand,(aa|bb)&cc,target,'('+a['text']+' ou '+b['text']+') et '+c['text'],ca+3,[a,b,c])
        _candidate(cand,(aa&cc)|bb,target,'('+a['text']+' et '+c['text']+') ou '+b['text'],ca+3,[a,b,c])
        _candidate(cand,(aa|cc)&bb,target,'('+a['text']+' ou '+c['text']+') et '+b['text'],ca+3,[a,b,c])
        _candidate(cand,(bb&cc)|aa,target,'('+b['text']+' et '+c['text']+') ou '+a['text'],ca+3,[a,b,c])
        _candidate(cand,(bb|cc)&aa,target,'('+b['text']+' ou '+c['text']+') et '+a['text'],ca+3,[a,b,c])
    if not cand:return None
    cand.sort(key=lambda x:(x[0],x[1]))
    cost,_,text,used=cand[0]
    return {'text':text,'cost':cost,'atoms':[{'text':x['text'],'kind':x['kind'],'meta':x['meta']} for x in used]}


def clean_reason(s:str)->str:
    s=s.replace('au moins l’un de le Valet ou le Roi est placé','au moins l’un des deux, le Valet ou le Roi, est placé')
    s=s.replace('au moins l’un de le Roi ou le Valet est placé','au moins l’un des deux, le Roi ou le Valet, est placé')
    s=s.replace('au moins l’un de la Dame ou le Roi est placé','au moins l’une des deux cartes, la Dame ou le Roi, est placée')
    s=s.replace('au moins l’un de le Roi ou la Dame est placé','au moins l’une des deux cartes, le Roi ou la Dame, est placée')
    s=s.replace('— d’un côté et ','une chicane d’un côté et ')
    return s


def reason_for_mask(eng,e,mask,target_hand=None):
    # Same exact gate as V5.8, with a larger but still short-form Boolean language.
    allm=e.model.all;fail=allm&~mask;atoms=v58.build_atoms(eng,e,target_hand)
    sf=best_formula(mask,atoms,allm);ff=best_formula(fail,atoms,allm);choices=[]
    if sf:choices.append((sf['cost'],0,'success',sf))
    if ff:choices.append((ff['cost'],1,'failure',ff))
    owf=v58.one_world_reason(eng,e,fail,False);ows=v58.one_world_reason(eng,e,mask,True)
    if owf:choices.append((3,2,'failure_world',{'text':owf,'cost':3,'atoms':[]}))
    if ows:choices.append((3,3,'success_world',{'text':ows,'cost':3,'atoms':[]}))
    if not choices:return {'certified':False,'reason':'','mode':'NONE'}
    choices.sort(key=lambda x:(x[0],x[1],len(x[3]['text'])))
    _,_,mode,f=choices[0]
    if mode=='success':text='Le maniement réussit exactement lorsque '+f['text']+'.'
    elif mode=='failure':text='Le maniement échoue exactement lorsque '+f['text']+' ; toutes les autres positions sont couvertes.'
    else:text=f['text']
    return {'certified':True,'reason':clean_reason(text),'mode':mode,'formula':f}


v58.best_formula=best_formula
v58.reason_for_mask=reason_for_mask

if __name__=='__main__':
    v58.main()

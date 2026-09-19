#!/usr/bin/env python3
from __future__ import annotations
import argparse,json,sys
from collections import Counter,defaultdict
from pathlib import Path

CASES={
 'ROUD_2':('K62','AJ853',5,'R62','AV853'),
 'SUITPLAY_ENC':('AT42','953',2,'AX42','953'),
}
ap=argparse.ArgumentParser()
ap.add_argument('--runtime-root',required=True);ap.add_argument('--tools-root',required=True)
ap.add_argument('--case-id',required=True);ap.add_argument('--output',required=True)
a=ap.parse_args()
sys.path.insert(0,str(Path(a.runtime_root)/'runtime'));sys.path.insert(0,a.tools_root)
import integrated_engine as eng
import human_semantic_v62 as sem
import human_semantic_v52 as v52

def collect_flexible(eng,e,root):
    rows=[];seen=set()
    def walk(n,rnd):
        k=(id(n),rnd)
        if k in seen:return
        seen.add(k)
        if n.kind=='T':return
        if n.kind=='D':
            legal,exact=v52.state_action_sets(eng,e,n)
            f=sem.enrich(v52.base_features(eng,e,n.state,rnd))
            acts=sem.semantic_action_set(f,exact)
            if not (legal and legal==exact):
                rows.append({'features':f,'actions':acts,'raw_exact':exact})
            ch=n.branches[0];walk(ch,v52.v51.edge_round(n,ch,rnd));return
        for _,ch in n.branches or []:walk(ch,v52.v51.edge_round(n,ch,rnd))
    walk(root,1)
    return rows

def compress_flexible(eng,e,root,top,bottom):
    rows=collect_flexible(eng,e,root)
    groups=defaultdict(list);conf=[]
    for key,grp0 in __import__('itertools').groupby(sorted(rows,key=lambda r:str(sem.group_key(r['features']))),key=lambda r:sem.group_key(r['features'])):
        grp=list(grp0)
        label=sem.choose_common(grp)
        if label is not None:
            z=grp[0].copy();z['label']=label;groups[key].append(z);continue
        for r in grp:
            if not r['actions']:
                conf.append({'key':key,'features':r['features']});continue
            r=dict(r);r['label']=sem.choose_common([r]) or sorted(r['actions'])[0]
            groups[key].append(r)
    if conf:return {'ok':False,'reason':'semantic_action_missing','conflicts':conf[:5]}
    lines=[];program=[]
    for key,ss in sorted(groups.items(),key=lambda kv:str(kv[0])):
        counts=Counter(s['label'] for s in ss);default=counts.most_common(1)[0][0]
        uncovered=set(range(len(ss)));rules=[]
        for label,_ in counts.most_common():
            if label==default:continue
            while any(ss[i]['label']==label for i in uncovered):
                found=sem.rule_search(ss,label,uncovered)
                if not found:return {'ok':False,'reason':'not_separable','group':key,'counts':dict(counts)}
                _,_,cond,matched=found;rules.append((tuple(cond),label))
                for i in matched:
                    if ss[i]['label']==label:uncovered.discard(i)
        rnd,phase,leader,seat,won,nstr,sstr=key
        prefix=f"Au {rnd}{'er' if rnd==1 else 'e'} tour"
        for cond,label in rules:
            lines.append(prefix+', si '+' et '.join(sem.atom_fr(k,v) for k,v in cond)+' : '+sem.action_fr(label,phase,top,bottom)+'.')
        lines.append(prefix+', '+('sinon : ' if rules else '')+sem.action_fr(default,phase,top,bottom)+'.')
        program.append({'key':[rnd,phase,leader,seat,won,nstr,sstr],
                        'rules':[{'if':[[k,v] for k,v in cond],'action':label} for cond,label in rules],
                        'default':default})
    ded=[]
    for x in lines:
        if x not in ded:ded.append(x)
    return {'ok':True,'lines':ded,'visible_lines':len(ded),'program':program,'semantic_states':len(rows)}

north,south,target,top,bottom=CASES[a.case_id]
e=eng.Engine2(north,south,target);root=e.initial();best=max(e.frontier(root),key=lambda m:(e.model.weight(m),m))
v52.v45._ENG=eng;v52.v45._E=e
tree=v52.v45.explore(eng,e,root,best,[],[],{})
r=compress_flexible(eng,e,tree,top,bottom)
if r.get('ok'):
    p,m,diag=sem.evaluate_program(eng,north,south,target,r['program'],debug=True)
    r.update({'replay_fraction':str(p),'replay_matches_oracle':p==e.model.weight(best),
              'mask_matches_oracle':int(m)==int(best),'diag':diag})
r.update({'id':a.case_id,'oracle':str(e.model.weight(best))})
Path(a.output).write_text(json.dumps(r,ensure_ascii=False,indent=2)+'\n')
print(json.dumps({k:r.get(k) for k in ('id','oracle','visible_lines','replay_fraction','replay_matches_oracle','mask_matches_oracle','reason')},ensure_ascii=False,indent=2))
if r.get('lines'): print('\n'.join(r['lines']))

#!/usr/bin/env python3
from __future__ import annotations
import argparse, json, math
from collections import Counter, defaultdict
from pathlib import Path

RANKS='AKQJT98765432'
FR={'A':"l'As",'K':'le Roi','Q':'la Dame','J':'le Valet','T':'le 10','9':'le 9','8':'le 8','7':'le 7','6':'le 6','5':'le 5','4':'le 4','3':'le 3','2':'le 2','-':'une chicane'}

def context_key(r):
    trick=tuple((t['seat'], t['card'] if t['seat'] in ('N','S') else '*') for t in r['trick'])
    return (r['north_remaining'],r['south_remaining'],r['leader'],r['pos'],r['won'],trick)

def context_json(k):
    n,s,leader,pos,won,trick=k
    return {'north_remaining':n,'south_remaining':s,'leader':leader,'pos':pos,'won':won,'trick_shape':[{'seat':a,'card':b} for a,b in trick]}

def feature_map(r):
    f={}
    for rank in RANKS:
        f[f'W_SEEN_{rank}']=rank in r['west_seen']; f[f'E_SEEN_{rank}']=rank in r['east_seen']
    f['W_VOID']=bool(r['west_void']); f['E_VOID']=bool(r['east_void'])
    for seat in ('E','W'):
        cur=next((t['card'] for t in r['trick'] if t['seat']==seat),None)
        for rank in RANKS+'-': f[f'CUR_{seat}_{rank}']=(cur==rank)
    return f

def feature_fr(name):
    if name=='W_VOID': return 'Ouest a déjà montré une chicane dans la couleur'
    if name=='E_VOID': return 'Est a déjà montré une chicane dans la couleur'
    parts=name.split('_')
    if parts[0] in ('W','E') and parts[1]=='SEEN':
        side='Ouest' if parts[0]=='W' else 'Est'; return f'{side} a déjà fourni {FR[parts[2]]}'
    if parts[0]=='CUR':
        side='Ouest' if parts[1]=='W' else 'Est'; rank=parts[2]
        if rank=='-': return f'{side} défausse sur ce tour'
        return f'{side} fournit {FR[rank]} sur ce tour'
    return name

def entropy(labels):
    c=Counter(labels); n=sum(c.values())
    if not n:return 0.0
    return -sum((v/n)*math.log2(v/n) for v in c.values())

def make_tree(rows,features):
    labels=[a for _,a in rows]
    if len(set(labels))==1:return {'action':labels[0]}
    base=entropy(labels); best=None
    for feat in features:
        left=[x for x in rows if not x[0][feat]]; right=[x for x in rows if x[0][feat]]
        if not left or not right:continue
        score=base-(len(left)/len(rows))*entropy([a for _,a in left])-(len(right)/len(rows))*entropy([a for _,a in right])
        cand=(score,min(len(left),len(right)),feat,left,right)
        if best is None or cand[:2]>best[:2] or (cand[:2]==best[:2] and feat<best[2]):best=cand
    if best is None:return {'error':'UNSEPARABLE','actions':dict(Counter(labels))}
    _,_,feat,left,right=best; remaining=[x for x in features if x!=feat]
    no=make_tree(left,remaining); yes=make_tree(right,remaining)
    if no==yes:return no
    return {'if':feat,'condition_fr':feature_fr(feat),'no':no,'yes':yes}

def tree_stats(t):
    if 'action' in t or 'error' in t:return (1,1,0)
    n1,l1,d1=tree_stats(t['no']); n2,l2,d2=tree_stats(t['yes'])
    return (1+n1+n2,l1+l2,1+max(d1,d2))

def leaf_rules(t,path=None):
    path=list(path or [])
    if 'action' in t:return [{'conditions':path,'action':t['action']}]
    if 'error' in t:return [{'conditions':path,'error':t}]
    cond=t['condition_fr']; feat=t['if']
    return leaf_rules(t['no'],path+[{'feature':feat,'condition':cond,'value':False}])+leaf_rules(t['yes'],path+[{'feature':feat,'condition':cond,'value':True}])

def main():
    ap=argparse.ArgumentParser(); ap.add_argument('policy'); ap.add_argument('--output'); a=ap.parse_args(); d=json.loads(Path(a.policy).read_text(encoding='utf-8'))
    groups=defaultdict(list)
    for r in d['policy_states']:groups[context_key(r)].append(r)
    contexts=[]; total_nodes=total_leaves=max_depth=conditional=errors=0
    all_features=[]
    for rank in RANKS:all_features += [f'W_SEEN_{rank}',f'E_SEEN_{rank}']
    all_features += ['W_VOID','E_VOID']
    for seat in ('E','W'):all_features += [f'CUR_{seat}_{rank}' for rank in RANKS+'-']
    for k,rs in sorted(groups.items(),key=lambda kv:str(kv[0])):
        actions=Counter(r['action'] for r in rs); item={'context':context_json(k),'state_count':len(rs),'actions':dict(sorted(actions.items()))}
        if len(actions)==1:item['unconditional_action']=next(iter(actions)); n=l=1; depth=0
        else:
            conditional+=1; tree=make_tree([(feature_map(r),r['action']) for r in rs],all_features); item['decision_tree']=tree; item['rules']=leaf_rules(tree)
            n,l,depth=tree_stats(tree)
            if any('error' in z for z in item['rules']):errors+=1
        item['tree_stats']={'nodes':n,'leaves':l,'depth':depth}; total_nodes+=n; total_leaves+=l; max_depth=max(max_depth,depth); contexts.append(item)
    out={'schema':'MANIEMENTS_V5_DICTIONARY_V3_POLICY_PROGRAM_V2','case':d['case'],'probability_fraction':d['solve']['probability_fraction'],'native_policy_states':d['policy_state_count'],'context_count':len(contexts),'conditional_context_count':conditional,'program_stats':{'nodes':total_nodes,'leaves':total_leaves,'max_conditional_depth':max_depth,'unseparable_contexts':errors},'contexts':contexts}
    text=json.dumps(out,ensure_ascii=False,indent=2,sort_keys=True)
    if a.output:Path(a.output).write_text(text+'\n',encoding='utf-8')
    print(text)
if __name__=='__main__':main()

#!/usr/bin/env python3
from __future__ import annotations
from collections import Counter,defaultdict
import itertools

import human_semantic_v52 as v52

RVAL=v52.b.RANK_VALUE
LOW=set('765432')
MID=set('T98')
HON=set('AKQJ')

def ranks_from_text(t):
    return [x for x in str(t or '').split() if x in RVAL]

def hand_ranks(f,seat):
    return ranks_from_text(f['n_rem'] if seat=='N' else f['s_rem'])

def exact_has(exact,seat,rank):
    if (seat,rank) in exact:
        return True
    if rank in LOW and (seat,'x') in exact:
        return True
    return False

def semantic_action_set(f, exact):
    phase=f['phase']
    seat = None
    if phase=='response':
        seat=f['seat']
        if seat not in ('N','S'):
            return set()
        cards=hand_ranks(f,seat)
        if not cards:
            return {'VOID'} if any(r=='-' for _,r in exact) else set()
        out=set()
        lo=min(cards,key=lambda r:RVAL[r]); hi=max(cards,key=lambda r:RVAL[r])
        if exact_has(exact,seat,lo): out.add('LOW')
        if exact_has(exact,seat,hi): out.add('HIGH')
        prev=f.get('prev_card')
        if prev not in (None,'-','x'):
            wins=[r for r in cards if RVAL[r]>RVAL.get(prev,99)]
            if wins:
                cover=min(wins,key=lambda r:RVAL[r])
                if exact_has(exact,seat,cover): out.add('COVER_CHEAPEST')
        for r in cards:
            if r in 'AKQJT98' and exact_has(exact,seat,r):
                out.add('RANK:'+r)
        return out

    out=set()
    for seat in ('N','S'):
        cards=hand_ranks(f,seat)
        if not cards: continue
        lo=min(cards,key=lambda r:RVAL[r]); hi=max(cards,key=lambda r:RVAL[r])
        if exact_has(exact,seat,lo): out.add(seat+':LOW')
        if exact_has(exact,seat,hi): out.add(seat+':HIGH')
        for r in cards:
            if r in 'AKQJT98' and exact_has(exact,seat,r):
                out.add(seat+':RANK:'+r)
    return out

def enrich(f):
    z=dict(f)
    p=f.get('prev_card')
    if p is None: pc='NONE'
    elif p=='-': pc='VOID'
    elif p in HON: pc='HONOR'
    elif p in MID: pc='INTERMEDIATE'
    else: pc='LOW'
    z['prev_class']=pc
    z['seen_KQJ']=sum(bool(f.get('seen_'+r)) for r in 'KQJ')
    z['seen_QJ']=sum(bool(f.get('seen_'+r)) for r in 'QJ')
    z['seen_T98']=sum(bool(f.get('seen_'+r)) for r in 'T98')
    z['west_KQJ']=sum(bool(f.get('west_'+r)) for r in 'KQJ')
    z['east_KQJ']=sum(bool(f.get('east_'+r)) for r in 'KQJ')
    z['west_T98']=sum(bool(f.get('west_'+r)) for r in 'T98')
    z['east_T98']=sum(bool(f.get('east_'+r)) for r in 'T98')
    z['n_strat']=''.join(x for x in ranks_from_text(f.get('n_rem')) if x in 'AKQJT98')
    z['s_strat']=''.join(x for x in ranks_from_text(f.get('s_rem')) if x in 'AKQJT98')
    return z

def collect(eng,e,root):
    rows=[]
    seen=set()
    def walk(n,rnd):
        k=(id(n),rnd)
        if k in seen:return
        seen.add(k)
        if n.kind=='T':return
        if n.kind=='D':
            legal,exact=v52.state_action_sets(eng,e,n)
            f=enrich(v52.base_features(eng,e,n.state,rnd))
            acts=semantic_action_set(f,exact)
            # If all legal card actions are exact, there is no strategic instruction.
            if not (legal and legal==exact):
                rows.append({'features':f,'actions':acts,'raw_exact':exact})
            ch=n.branches[0]
            walk(ch,v52.v51.edge_round(n,ch,rnd))
            return
        for _,ch in n.branches or []:
            walk(ch,v52.v51.edge_round(n,ch,rnd))
    walk(root,1)
    return rows

def group_key(f):
    return (
      f['round'],f['phase'],f.get('leader'),f.get('seat'),
      f['won'],f['n_strat'],f['s_strat']
    )

def choose_common(grp):
    sets=[r['actions'] for r in grp]
    if not sets or any(not s for s in sets): return None
    common=set.intersection(*sets)
    if not common:return None
    def score(a):
        if a.endswith(':LOW') or a=='LOW': return (0,a)
        if a=='COVER_CHEAPEST': return (1,a)
        if a.startswith('RANK:9') or a.endswith(':RANK:9'): return (2,a)
        if a.startswith('RANK:T') or a.endswith(':RANK:T'): return (3,a)
        if a=='HIGH' or a.endswith(':HIGH'): return (4,a)
        return (5,a)
    return min(common,key=score)

FEATURES=[
 'prev_class','prev_card',
 'seen_KQJ','seen_QJ','seen_T98',
 'seen_K','seen_Q','seen_J','seen_T','seen_9','seen_8',
 'west_KQJ','east_KQJ','west_T98','east_T98',
 'west_K','west_Q','west_J','east_K','east_Q','east_J',
 'west_void','east_void','won'
]

def rule_search(samples,label,uncovered):
    targets=[i for i in uncovered if samples[i]['label']==label]
    best=None
    for size in (1,2,3):
        for i in targets:
            atoms=[(k,samples[i]['features'].get(k)) for k in FEATURES]
            for cond in itertools.combinations(atoms,size):
                matched=[j for j,s in enumerate(samples) if all(s['features'].get(k)==v for k,v in cond)]
                if not matched: continue
                if any(samples[j]['label']!=label for j in matched): continue
                cov=sum(j in targets for j in matched)
                cand=(cov,-size,cond,matched)
                if best is None or cand[:2]>best[:2]:best=cand
        if best and best[0]==len(targets):break
    return best

def atom_fr(k,v):
    if k=='prev_class':
        return {
          'HONOR':"l’adversaire vient de fournir un honneur",
          'INTERMEDIATE':"l’adversaire vient de fournir une carte intermédiaire",
          'LOW':"l’adversaire vient de fournir une petite carte",
          'VOID':"l’adversaire vient de défausser",
          'NONE':"aucune carte adverse n’a encore été fournie",
        }[v]
    if k=='prev_card':
        if v is None:return "aucune carte adverse n’a encore été fournie"
        if v=='-':return "l’adversaire vient de défausser"
        if v in LOW:return "l’adversaire vient de fournir une petite carte"
        return "l’adversaire vient de fournir "+v52.v51.fr_rank(v)
    if k.startswith('seen_') and k not in ('seen_KQJ','seen_QJ','seen_T98'):
        r=k[5:]; return v52.v51.fr_rank(r)+(" est déjà apparu" if v else " n’est pas encore apparu")
    if k in ('seen_KQJ','seen_QJ','seen_T98'):
        return f"{v} carte(s) du groupe {k[5:]} sont déjà apparues"
    if k in ('west_KQJ','east_KQJ','west_T98','east_T98'):
        side='Ouest' if k.startswith('west') else 'Est'
        return f"{side} a déjà montré {v} carte(s) du groupe {k.split('_',1)[1]}"
    if k in ('west_void','east_void'):
        side='Ouest' if k.startswith('west') else 'Est'
        return f"{side} {'a' if v else 'n’a pas'} montré une chicane"
    if k=='won': return f"{v} levée(s) ont déjà été gagnées"
    if k.startswith('west_') or k.startswith('east_'):
        side='Ouest' if k.startswith('west') else 'Est';r=k.split('_',1)[1]
        return f"{side} {'a déjà montré' if v else 'n’a pas montré'} {v52.v51.fr_rank(r)}"
    return f"{k}={v}"

def action_fr(label,phase,top,bottom):
    if phase=='lead':
        seat,kind,*rest=label.split(':')
        h=top if seat=='N' else bottom
        if kind=='LOW':return f"jouer une petite carte de {h}"
        if kind=='HIGH':return f"jouer la plus forte carte de {h}"
        if kind=='RANK':
            r=rest[0]
            if r=='A':return "tirer l’As"
            if r=='K':return "tirer le Roi"
            return f"jouer {v52.v51.fr_rank(r)} de {h}"
    if label=='LOW':return "fournir la plus petite carte"
    if label=='HIGH':return "fournir la plus forte carte"
    if label=='COVER_CHEAPEST':return "couvrir au plus juste"
    if label=='VOID':return "ne plus fournir dans la couleur"
    if label.startswith('RANK:'):
        r=label.split(':')[1]
        if r=='A':return "prendre de l’As"
        return "jouer "+v52.v51.fr_rank(r)
    return label

def compress(eng,e,root,top,bottom,max_lines=12):
    rows=collect(eng,e,root)
    groups=defaultdict(list)
    conflicts=[]
    for key,grp0 in itertools.groupby(sorted(rows,key=lambda r:str(group_key(r['features']))),
                                       key=lambda r:group_key(r['features'])):
        grp=list(grp0)
        label=choose_common(grp)
        if label is not None:
            z=grp[0].copy();z['label']=label;groups[key].append(z)
            continue
        # Keep each abstract public state but never refine by exact low spots.
        # We will ask the rule learner to separate them using bridge-semantic features.
        for r in grp:
            if not r['actions']:
                conflicts.append({'key':key,'features':r['features']})
                continue
            # Pick a deterministic preferred exact-preserving semantic action.
            r=dict(r);r['label']=choose_common([r]) or sorted(r['actions'])[0]
            groups[key].append(r)
    if conflicts:
        return {'ok':False,'reason':'semantic_action_missing','conflicts':conflicts[:5]}

    lines=[];rule_count=0
    for key,ss in sorted(groups.items(),key=lambda kv:str(kv[0])):
        counts=Counter(s['label'] for s in ss)
        default=counts.most_common(1)[0][0]
        uncovered=set(range(len(ss)))
        rules=[]
        for label,_ in counts.most_common():
            if label==default:continue
            while any(ss[i]['label']==label for i in uncovered):
                found=rule_search(ss,label,uncovered)
                if not found:
                    return {'ok':False,'reason':'semantic_rules_not_separable','group':key,'counts':dict(counts)}
                _,_,cond,matched=found
                rules.append((cond,label))
                for i in matched:
                    if ss[i]['label']==label:uncovered.discard(i)
        rnd,phase,leader,seat,won,nstr,sstr=key
        prefix=f"Au {rnd}{'er' if rnd==1 else 'e'} tour"
        for cond,label in rules:
            txt=' et '.join(atom_fr(k,v) for k,v in cond)
            lines.append(f"{prefix}, si {txt} : {action_fr(label,phase,top,bottom)}.")
            rule_count+=1
        leadin='sinon : ' if rules else ''
        lines.append(f"{prefix}, {leadin}{action_fr(default,phase,top,bottom)}.")
        rule_count+=1
    ded=[]
    for x in lines:
        if x not in ded:ded.append(x)
    return {
      'ok':True,'lines':ded,'visible_lines':len(ded),'rule_count':rule_count,
      'human_safe':len(ded)<=max_lines,'semantic_states':len(rows),
      'spot_fallback_used':False
    }

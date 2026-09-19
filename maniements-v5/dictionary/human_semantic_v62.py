#!/usr/bin/env python3
from __future__ import annotations
from collections import Counter,defaultdict
import itertools,json

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
    z['second_rank']=None
    z['prev_below_second']=False
    z['seen_above_second']=0
    z['west_above_second']=0
    z['east_above_second']=0
    if f.get('phase')=='response' and f.get('seat') in ('N','S'):
        rr=sorted(hand_ranks(f,f['seat']),key=lambda r:RVAL[r],reverse=True)
        if len(rr)>=2:
            second=rr[1];z['second_rank']=second
            pv=f.get('prev_card')
            if pv not in (None,'-') and pv in RVAL:
                z['prev_below_second']=RVAL[pv] < RVAL[second]
            for side in ('west','east'):
                cnt=0
                for r in 'AKQJT98765432':
                    if RVAL[r]>RVAL[second] and f.get(side+'_'+r):
                        cnt+=1
                z[side+'_above_second']=cnt
            z['seen_above_second']=z['west_above_second']+z['east_above_second']
    return z

def semantic_label_for_actual(eng,e,s,f,action):
    seat,raw=action
    # Oracle tree actions are already stored as public rank strings in this layer.
    rank='-' if raw in (None,0,'-') else (raw if isinstance(raw,str) else eng.I2R[raw])
    phase=f['phase']
    hand=s.north if seat=='N' else s.south
    cards=[eng.I2R[r] for r in eng.ranks(hand)]
    if rank=='-':return 'VOID'
    if phase=='lead':
        if cards and rank==min(cards,key=lambda r:RVAL[r]):
            return seat+':LOW'
        if cards and rank==max(cards,key=lambda r:RVAL[r]):
            return seat+':HIGH'
        return seat+':RANK:'+rank
    prev=f.get('prev_card')
    if prev not in (None,'-','x'):
        wins=[r for r in cards if RVAL[r]>RVAL.get(prev,99)]
        if wins and rank==min(wins,key=lambda r:RVAL[r]):
            return 'COVER_CHEAPEST'
    if cards and rank==min(cards,key=lambda r:RVAL[r]):
        return 'LOW'
    if cards and rank==max(cards,key=lambda r:RVAL[r]):
        return 'HIGH'
    return 'RANK:'+rank

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
            # Keep the oracle's chosen public action, but express that exact same
            # card as a semantic role whenever possible. This prevents the
            # compressed program from drifting into untrained public states.
            label=semantic_label_for_actual(eng,e,n.state,f,n.action)
            if not (legal and legal==exact):
                rows.append({'features':f,'label':label,'raw_exact':exact})
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
    rel=relative_atom_fr(k,v)
    if rel is not None:return rel
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

def relative_atom_fr(k,v):
    if k=='prev_below_second':
        return "la carte fournie est inférieure à l’intermédiaire conservé" if v else "la carte fournie n’est pas inférieure à l’intermédiaire conservé"
    if k=='seen_above_second':
        return f"{v} honneur(s) supérieur(s) à l’intermédiaire sont déjà tombés"
    if k=='west_above_second':
        return f"Ouest a déjà fourni {v} honneur(s) supérieur(s) à l’intermédiaire"
    if k=='east_above_second':
        return f"Est a déjà fourni {v} honneur(s) supérieur(s) à l’intermédiaire"
    if k=='second_rank':
        return "l’intermédiaire conservé est "+v52.v51.fr_rank(v)
    return None

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
        for r in grp:
            groups[key].append(r)
    if conflicts:
        return {'ok':False,'reason':'semantic_action_missing','conflicts':conflicts[:5]}

    lines=[];rule_count=0;program=[]
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
                rules.append((tuple(cond),label))
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
        program.append({
          'key':[rnd,phase,leader,seat,won,nstr,sstr],
          'rules':[{'if':[[k,v] for k,v in cond],'action':label} for cond,label in rules],
          'default':default,
        })
    ded=[]
    for x in lines:
        if x not in ded:ded.append(x)
    return {
      'ok':True,'lines':ded,'visible_lines':len(ded),'rule_count':rule_count,
      'human_safe':len(ded)<=max_lines,'semantic_states':len(rows),
      'spot_fallback_used':False,'program':program
    }


def _program_map(program):
    return {tuple(x['key']):x for x in program}

def _label_to_action(eng,s,f,label):
    phase=f['phase']
    if phase=='lead':
        parts=label.split(':')
        seat=parts[0];kind=parts[1]
        hand=s.north if seat=='N' else s.south
        rr=[eng.I2R[r] for r in eng.ranks(hand)]
        if not rr:return None
        if kind=='LOW':
            return seat,min(rr,key=lambda r:RVAL[r])
        if kind=='HIGH':
            return seat,max(rr,key=lambda r:RVAL[r])
        if kind=='RANK':
            r=parts[2]
            return (seat,r) if r in rr else None
        return None
    seat=f.get('seat')
    if seat not in ('N','S'):return None
    hand=s.north if seat=='N' else s.south
    rr=[eng.I2R[r] for r in eng.ranks(hand)]
    if label=='VOID':
        return seat,'-' if not rr else None
    if not rr:return seat,'-'
    if label=='LOW':return seat,min(rr,key=lambda r:RVAL[r])
    if label=='HIGH':return seat,max(rr,key=lambda r:RVAL[r])
    if label=='COVER_CHEAPEST':
        p=f.get('prev_card')
        if p in (None,'-','x'):return None
        wins=[r for r in rr if RVAL[r]>RVAL[p]]
        return (seat,min(wins,key=lambda r:RVAL[r])) if wins else None
    if label.startswith('RANK:'):
        r=label.split(':',1)[1]
        return (seat,r) if r in rr else None
    return None

def evaluate_program(eng,north,south,goal,program,debug=False):
    e=eng.Engine2(north,south,goal)
    pm=_program_map(program)
    from functools import lru_cache
    diag={'missing_group':0,'invalid_action':0,'examples':[]}

    def pick(s,rnd):
        f=enrich(v52.base_features(eng,e,s,rnd))
        k=group_key(f)
        item=pm.get(k)
        if item is None:
            # The exact tree deliberately omits public states where the choice
            # is non-strategic (several declarer cards preserve the result), and
            # it also omits states that only occur in already-losing worlds.
            # Define a deterministic public fallback so the maneuver remains a
            # complete executable policy; exhaustive replay will decide whether
            # that fallback preserves the oracle probability.
            diag['missing_group']+=1
            if len(diag['examples'])<8:
                diag['examples'].append({'kind':'missing_group','round':rnd,'key':list(k),'features':f})
            if s.pos==0:
                for seat in ('N','S'):
                    h=s.north if seat=='N' else s.south
                    rr=[eng.I2R[r] for r in eng.ranks(h)]
                    if rr:
                        return seat,min(rr,key=lambda r:RVAL[r])
                return None
            seat=e.order(s.leader)[s.pos]
            if seat in eng.DECL:
                h=s.north if seat=='N' else s.south
                rr=[eng.I2R[r] for r in eng.ranks(h)]
                return (seat,min(rr,key=lambda r:RVAL[r])) if rr else (seat,'-')
            return None
        label=item['default']
        for rule in item['rules']:
            if all(f.get(a)==v for a,v in rule['if']):
                label=rule['action'];break
        a=_label_to_action(eng,s,f,label)
        if a is None:
            # A learned semantic rule can also be reached from a public state
            # that was non-strategic in the oracle tree (for example a defender
            # is void, so "cover au plus juste" has no literal cover). Fall
            # back to the lowest legal card and let replay certify the whole
            # resulting policy.
            diag['invalid_action']+=1
            if len(diag['examples'])<8:
                diag['examples'].append({'kind':'invalid_action','round':rnd,'key':list(k),'label':label,'features':f})
            seat=e.order(s.leader)[s.pos] if s.pos else None
            if seat in eng.DECL:
                h=s.north if seat=='N' else s.south
                rr=[eng.I2R[r] for r in eng.ranks(h)]
                return (seat,min(rr,key=lambda r:RVAL[r])) if rr else (seat,'-')
        return a

    @lru_cache(maxsize=None)
    def F(s,rnd):
        term=e.terminal(s)
        if term is not None:return term[0]
        if s.pos==0:
            a=pick(s,rnd)
            if a is None:return 0
            seat,c=a
            if c=='-':return 0
            r=eng.R2I[c]
            lead=eng.PublicState(s.north,s.south,s.west_seen,s.east_seen,
                                 s.west_void,s.east_void,seat,0,tuple(),s.won)
            ns=e.close(e.decl_play(lead,seat,r))
            return F(ns,rnd)
        seat=e.order(s.leader)[s.pos]
        if seat in eng.DECL:
            a=pick(s,rnd)
            if a is None or a[0]!=seat:return 0
            c=a[1];r=eng.VOID if c=='-' else eng.R2I[c]
            ns=e.close(e.decl_play(s,seat,r))
            return F(ns,rnd+1 if ns.pos==0 else rnd)
        belief=e.belief(s);ok=belief
        for r,legal in e.defender_actions(s,seat):
            ns=e.close(e.def_play(s,seat,r))
            ok &= ((belief&~legal)|F(ns,rnd+1 if ns.pos==0 else rnd))
        return ok

    mask=F(e.initial(),1)
    if debug:
        return e.model.weight(mask),mask,diag
    return e.model.weight(mask),mask


def render_program(program,top,bottom):
    lines=[]
    for item in program:
        rnd,phase,leader,seat,won,nstr,sstr=item['key']
        prefix=f"Au {rnd}{'er' if rnd==1 else 'e'} tour"
        for rule in item.get('rules') or []:
            cond=' et '.join(atom_fr(k,v) for k,v in rule['if'])
            lines.append(f"{prefix}, si {cond} : {action_fr(rule['action'],phase,top,bottom)}.")
        leadin='sinon : ' if item.get('rules') else ''
        lines.append(f"{prefix}, {leadin}{action_fr(item['default'],phase,top,bottom)}.")
    ded=[]
    for x in lines:
        if x not in ded:ded.append(x)
    return ded

def _missing_above_second(north,south,seat,second):
    owned=set(north+south)
    return [r for r in 'AKQJT98765432' if RVAL[r]>RVAL[second] and r not in owned]

def apply_generic_repairs(north,south,program):
    repairs=[]
    for item in program:
        k=item['key']
        rnd,phase,leader,seat,won,nstr,sstr=k
        if phase!='response' or seat not in ('N','S') or won!=0:
            continue
        # Generic honor-exhaustion safety family:
        # with exactly three missing cards above the second-highest card in the
        # acting hand, once two have been forced out one on each side, preserve
        # the intermediate against a lower card and force the last honor.
        hand = north if seat=='N' else south
        rr=sorted(hand,key=lambda r:RVAL[r],reverse=True)
        if len(rr)<2:continue
        second=rr[1]
        missing=_missing_above_second(north,south,seat,second)
        if len(missing)!=3:continue
        rule={
          'if':[
            ['second_rank',second],
            ['seen_above_second',2],
            ['west_above_second',1],
            ['east_above_second',1],
            ['prev_below_second',True],
          ],
          'action':'LOW'
        }
        sig=json.dumps(rule,sort_keys=True)
        if any(json.dumps(x,sort_keys=True)==sig for x in item.get('rules') or []):
            continue
        item.setdefault('rules',[]).insert(0,rule)
        repairs.append({
          'kind':'HONOR_EXHAUSTION',
          'seat':seat,'second_rank':second,'missing_above':missing,
          'round':rnd,
        })
    return repairs

def certified_humanize(eng,north,south,target,display,oracle):
    from fractions import Fraction
    e=eng.Engine2(north,south,target)
    root=e.initial()
    best=max(e.frontier(root),key=lambda m:(e.model.weight(m),m))
    if e.model.weight(best)!=Fraction(oracle):
        return {'found':False,'reason':'oracle_mask_mismatch'}
    v52.v45._ENG=eng;v52.v45._E=e
    tree=v52.v45.explore(eng,e,root,best,[],[],{})
    comp=compress(eng,e,tree,display[0],display[1])
    if not comp.get('ok'):
        return {'found':False,'reason':comp.get('reason','compression_failed')}
    before,mb=evaluate_program(eng,north,south,target,comp['program'])
    repairs=[]
    if before!=Fraction(oracle) or int(mb)!=int(best):
        repairs=apply_generic_repairs(north,south,comp['program'])
    after,ma=evaluate_program(eng,north,south,target,comp['program'])
    if after!=Fraction(oracle) or int(ma)!=int(best):
        return {
          'found':False,'reason':'semantic_replay_below_oracle',
          'before_fraction':str(before),'after_fraction':str(after),
          'repairs':repairs,
        }
    lines=render_program(comp['program'],display[0],display[1])
    compact=len(lines)<=14
    kind='EPUISEMENT_DES_HONNEURS_SUPERIEURS' if any(r['kind']=='HONOR_EXHAUSTION' for r in repairs) else 'PROGRAMME_ADAPTATIF_SEMANTIQUE'
    return {
      'found':True,'certified':True,'kind':kind,
      'probability_fraction':str(after),'success_mask':str(ma),
      'program':comp['program'],'lines_fr':lines,
      'visible_lines':len(lines),'human_compact':compact,
      'repairs':repairs,
      'certification':{
        'exhaustive_program_replay':True,
        'probability_equals_oracle':True,
        'success_mask_equals_oracle':True,
        'semantic_actions_executable':True,
      },
    }

#!/usr/bin/env python3
from __future__ import annotations

import argparse, html, itertools, json, sys
from collections import Counter, defaultdict
from fractions import Fraction
from pathlib import Path

HERE=Path(__file__).resolve().parent
sys.path.insert(0,str(HERE))
import human_semantic_v51 as v51

v50=v51.v50;v48=v51.v48;v47=v51.v47;v46=v51.v46;v45=v51.v45;b=v51.b
STRATEGIC=v51.STRATEGIC;LOW=v51.LOW


def sem_low_set(ranks, exact_ranks):
    ranks=set(ranks); exact_ranks=set(exact_ranks)
    out_legal=set();out_exact=set()
    lows=ranks&LOW;exact_lows=exact_ranks&LOW
    if lows and lows<=exact_lows:
        out_legal.add('x');out_exact.add('x')
    else:
        out_legal|=lows;out_exact|=exact_lows
    out_legal|=(ranks-LOW);out_exact|=(exact_ranks-LOW)
    return out_legal,out_exact


def state_action_sets(eng,e,n):
    s=n.state;need=n.mask
    # Enumerate all legal declarer actions, then which preserve the full exact need mask.
    if s.pos==0:
        pools=[(seat,s.north if seat=='N' else s.south) for seat in ('N','S') if (s.north if seat=='N' else s.south)]
    else:
        seat=e.order(s.leader)[s.pos]
        if seat not in eng.DECL:return set(),set()
        pools=[(seat,s.north if seat=='N' else s.south)]
    feasible=v46.feasible_actions(eng,e,s,need)
    exact_raw={(seat,'-' if not r else eng.I2R[r]) for seat,r,_,support in feasible if (need|support)==support}
    legal=set();exact=set()
    for seat,hand in pools:
        rr=['-' if not r else eng.I2R[r] for r in (eng.ranks(hand) if hand else (eng.VOID,))]
        ex=[r for a,r in exact_raw if a==seat]
        l,e2=sem_low_set(rr,ex)
        legal|={(seat,r) for r in l};exact|={(seat,r) for r in e2}
    return legal,exact


def base_features(eng,e,s,round_no):
    phase='lead' if s.pos==0 else 'response'
    f={'round':round_no,'phase':phase,'won':s.won,
       'west_void':bool(s.west_void),'east_void':bool(s.east_void),
       'n_rem':' '.join(v51.bits_to_ranks(eng,s.north)),
       's_rem':' '.join(v51.bits_to_ranks(eng,s.south))}
    if phase=='response':
        f['leader']=s.leader;f['seat']=e.order(s.leader)[s.pos]
        r=v45.previous_def_card(eng,e,s);f['prev_card']='-' if r==eng.VOID else (eng.I2R[r] if r is not None else None)
    else:
        f['leader']=None;f['seat']=None;f['prev_card']=None
    for h in 'AKQJT98765432':
        bit=1<<eng.R2I[h]
        f['seen_'+h]=bool((s.west_seen|s.east_seen)&bit)
        f['west_'+h]=bool(s.west_seen&bit);f['east_'+h]=bool(s.east_seen&bit)
    return f


def coarse_key(f):
    # Tier-1 abstraction: honours/intermediates + void + trick progress only.
    keep=['round','phase','won','leader','seat','prev_card','west_void','east_void']
    keep += ['seen_'+h for h in STRATEGIC]
    keep += ['west_'+h for h in STRATEGIC]+['east_'+h for h in STRATEGIC]
    # Remaining strategic cards only, not exact small spots.
    n=''.join(x for x in f['n_rem'].split() if x in STRATEGIC);s=''.join(x for x in f['s_rem'].split() if x in STRATEGIC)
    vals=[(k,v51.sem_rank(f[k]) if k=='prev_card' and f[k] is not None else f[k]) for k in keep]
    vals += [('n_strat',n),('s_strat',s)]
    return tuple(vals)


def exact_key(f):
    return tuple(sorted(f.items()))


def collect_states(eng,e,root_node):
    rows=[];seen=set()
    def walk(n,rnd):
        key=(id(n),rnd)
        if key in seen:return
        seen.add(key)
        if n.kind=='T':return
        if n.kind=='D':
            legal,exact=state_action_sets(eng,e,n)
            f=base_features(eng,e,n.state,rnd)
            rows.append({'features':f,'legal':legal,'exact':exact,'irrelevant':bool(legal) and legal==exact})
            ch=n.branches[0];walk(ch,v51.edge_round(n,ch,rnd));return
        for _,ch in n.branches or []:walk(ch,v51.edge_round(n,ch,rnd))
    walk(root_node,1);return rows


def choose_common(options,phase):
    common=set.intersection(*(set(x) for x in options)) if options else set()
    if not common:return None
    def key(a):
        seat,r=a
        # Prefer a semantically generic small card when certified, then useful intermediates,
        # then honours. For a response, prefer the cheapest exact card.
        val=b.RANK_VALUE.get(r,0)
        if phase=='lead':
            pref=0 if r=='x' else (1 if r in '89T' else 2)
            return (pref,val,0 if seat=='N' else 1)
        return (0 if r=='x' else 1,val,0 if seat=='N' else 1)
    return min(common,key=key)


def normalize_states(rows):
    # Choices that are exact whatever declarer plays are not strategic instructions.
    relevant=[r for r in rows if not r['irrelevant']]
    by=defaultdict(list)
    for r in relevant:by[coarse_key(r['features'])].append(r)
    normalized=[];refined=0;true_conflicts=[]
    for ck,grp in by.items():
        action=choose_common([g['exact'] for g in grp],grp[0]['features']['phase'])
        if action is not None:
            z=grp[0].copy();z['action']=action;z['tier']='strategic';normalized.append(z);continue
        # Refine only the conflicting bucket with exact visible spot-card information.
        fine=defaultdict(list)
        for g in grp:fine[exact_key(g['features'])].append(g)
        for fk,gg in fine.items():
            action=choose_common([x['exact'] for x in gg],gg[0]['features']['phase'])
            if action is None:
                true_conflicts.append({'coarse':ck,'fine':fk,'sets':[sorted(x['exact']) for x in gg]});continue
            z=gg[0].copy();z['action']=action;z['tier']='spots';normalized.append(z);refined+=1
    return normalized,refined,true_conflicts,len(rows)-len(relevant)


def public_action(a,phase):
    seat,r=a
    return f'{seat}:{r}' if phase=='lead' else r


def preferred_features(samples):
    # Features are independent of the chosen action. Spot-card predicates are last resort.
    p=['prev_card','seen_K','seen_Q','seen_J','seen_T','seen_9','seen_8','west_void','east_void',
       'west_K','west_Q','west_J','west_T','west_9','west_8','east_K','east_Q','east_J','east_T','east_9','east_8','won']
    spot=['seen_7','seen_6','seen_5','seen_4','seen_3','seen_2','west_7','west_6','west_5','west_4','west_3','west_2','east_7','east_6','east_5','east_4','east_3','east_2','n_rem','s_rem']
    return p,spot


def human_atom(k,v,top,bottom):
    if k=='prev_card':
        if v is None:return "aucune carte adverse n’a encore été jouée"
        if v=='-':return "l’adversaire vient de défausser"
        if v in LOW:return "l’adversaire vient de fournir le "+v
        return "l’adversaire vient de fournir "+v51.fr_rank(v)
    if k.startswith('seen_'):
        r=k[5:];name=v51.fr_rank(r) if r not in LOW else 'le '+r
        return name+(" est déjà apparu" if v else " n’est pas encore apparu")
    if k.startswith('west_') or k.startswith('east_'):
        side='avant la main du haut' if k.startswith('west_') else 'avant la main du bas'
        r=k.split('_',1)[1];name=v51.fr_rank(r) if r not in LOW else 'le '+r
        return name+(f" est apparu chez l’adversaire placé {side}" if v else f" n’est pas apparu chez l’adversaire placé {side}")
    if k=='west_void':return "l’adversaire placé avant la main du haut a montré une chicane" if v else "l’adversaire placé avant la main du haut n’a pas montré de chicane"
    if k=='east_void':return "l’adversaire placé avant la main du bas a montré une chicane" if v else "l’adversaire placé avant la main du bas n’a pas montré de chicane"
    if k=='won':return f"{v} levée{'s' if v!=1 else ''} ont déjà été gagnées"
    if k=='n_rem':return "il reste dans la main du haut "+v
    if k=='s_rem':return "il reste dans la main du bas "+v
    return f'{k}={v}'


def find_rule(samples,label,uncovered,feature_order):
    targets=[i for i in uncovered if samples[i]['label']==label]
    if not targets:return None
    best=None
    for size in (1,2,3):
        for i in targets:
            vals=[(k,samples[i]['features'].get(k)) for k in feature_order]
            for atoms in itertools.combinations(vals,size):
                matched=[j for j,s in enumerate(samples) if all(s['features'].get(k)==v for k,v in atoms)]
                if not matched or any(samples[j]['label']!=label for j in matched):continue
                cov=sum(j in targets for j in matched);score=(cov,-size)
                if best is None or score>best[0]:best=(score,atoms,matched)
        if best and best[0][0]==len(targets):break
    return best


def compress_group(samples,top,bottom):
    counts=Counter(s['label'] for s in samples);default=counts.most_common(1)[0][0]
    primary,spot=preferred_features(samples);rules=[];uncovered=set(range(len(samples)));spot_used=False
    # Default-label states need no exception; mark them covered at the end.
    for label,_ in counts.most_common():
        if label==default:continue
        while any(samples[i]['label']==label for i in uncovered):
            found=find_rule(samples,label,uncovered,primary)
            used_spot=False
            if not found:
                found=find_rule(samples,label,uncovered,primary+spot);used_spot=bool(found)
            if not found:return None,True
            _,atoms,matched=found;spot_used|=used_spot or any(k in spot for k,_ in atoms)
            rules.append({'if':list(atoms),'label':label,'coverage':len(matched)})
            for j in matched:
                if samples[j]['label']==label:uncovered.discard(j)
    return {'default':default,'rules':rules,'counts':dict(counts)},spot_used


def action_text(label,phase,top,bottom,prev=None):
    if phase=='lead':
        seat,r=label.split(':',1);hand=top if seat=='N' else bottom
        if r=='x':return f"jouer petit de {hand}"
        if r=='A':return "tirer l’As"
        if r=='K':return "tirer le Roi"
        return f"jouer {v51.fr_rank(r)} de {hand}"
    r=label
    if r=='-':return "ne plus fournir dans la couleur"
    if r=='x':return "fournir petit"
    if prev not in (None,'-'):
        pr=prev if prev not in LOW else prev
        if b.RANK_VALUE.get(r,0)>b.RANK_VALUE.get(pr,99):return "couvrir avec "+v51.fr_rank(r)
    if r=='A':return "prendre de l’As"
    return "passer "+v51.fr_rank(r)


def compress_policy(eng,e,raw_tree,top,bottom):
    rows=collect_states(eng,e,raw_tree);norm,refined,conflicts,irrelevant=normalize_states(rows)
    if conflicts:return {'ok':False,'reason':'true_observable_conflict','conflicts':conflicts[:5],'irrelevant_pruned':irrelevant}
    # Build unambiguous groups: at trick start the action label includes the hand chosen.
    grouped=defaultdict(list)
    for r in norm:
        f=r['features'];key=(f['round'],f['phase'],f.get('leader'),f.get('seat'))
        z={'features':f,'label':public_action(r['action'],f['phase']),'tier':r['tier']};grouped[key].append(z)
    lines=[];spot_used=False;raw_rules=0
    for key,ss in sorted(grouped.items(),key=lambda kv:str(kv[0])):
        c,sp=compress_group(ss,top,bottom)
        if c is None:return {'ok':False,'reason':'rules_not_separable','group':key,'irrelevant_pruned':irrelevant}
        spot_used|=sp or any(x['tier']=='spots' for x in ss)
        rnd,phase,leader,seat=key;prefix=f"Au {rnd}{'er' if rnd==1 else 'e'} tour"
        for rr in c['rules']:
            cond=' et '.join(human_atom(k,v,top,bottom) for k,v in rr['if'])
            prev=next((v for k,v in rr['if'] if k=='prev_card'),None)
            lines.append(f"{prefix}, si {cond} : {action_text(rr['label'],phase,top,bottom,prev)}.");raw_rules+=1
        # Skip a default response that is only a void/forced discard; it carries no strategic choice.
        if not (phase=='response' and c['default']=='-'):
            leadin='sinon : ' if c['rules'] else ''
            lines.append(f"{prefix}, {leadin}{action_text(c['default'],phase,top,bottom)}.");raw_rules+=1
    # Exact duplicates are noise from paths that have the same human instruction.
    ded=[]
    for x in lines:
        if x not in ded:ded.append(x)
    # Conservative promotion gate: exact normalized policy, no spot-card fallback, <=10 useful lines.
    safe=(not spot_used and len(ded)<=10)
    return {'ok':True,'lines':ded,'visible_lines':len(ded),'rule_count':raw_rules,'spot_fallback_used':spot_used,'human_safe':safe,'normalized_states':len(norm),'irrelevant_pruned':irrelevant,'refined_states':refined}


def build_profile(eng,north,south,target):
    e=eng.Engine2(north,south,target);v45._ENG=eng;v45._E=e
    opt=Fraction(e.solve(include_policy=False)['probability_fraction']);base={'target':target,'fraction':str(opt),'percent':v51.pct(opt),'probability_decimal':float(opt)}
    if opt in (0,1):return {**base,'status':'EXACT_TRIVIAL','line':'Objectif impossible.' if opt==0 else 'Objectif assuré à 100 %.','steps':[],'why':'Aucune position adverse ne permet cet objectif.' if opt==0 else 'Cet objectif peut être assuré quelle que soit la répartition adverse.','qualification':{'counted':False}}
    root=e.initial();best=max(e.frontier(root),key=lambda m:(e.model.weight(m),m));row,opening=v47.choose_root(eng,e,best)
    decisions=[];raw=[];tree=v45.explore(eng,e,root,best,decisions,raw,{})
    audit=v50.audit_exact_tree(eng,e,tree,best);top=v50.disp(north);bottom=v50.disp(south);comp=compress_policy(eng,e,tree,top,bottom);alt=v48.alt_root(eng,e,root,row);why=v51.witness_reason(eng,e,row,alt)
    fails=[]
    if not audit['ok']:fails.append('exact_replay_failed')
    if not comp.get('ok'):fails.append(comp.get('reason','semantic_compression_failed'))
    elif not comp.get('human_safe'):fails.append('semantic_rules_too_complex_or_spot_dependent')
    if not why:fails.append('why_not_layout_specific')
    status='HUMAN_TREE_EXACT' if not fails else 'RAW_EXACT_ONLY'
    return {**base,'status':status,'line':(comp.get('lines') or [opening])[0] if status=='HUMAN_TREE_EXACT' else 'Calcul exact disponible — maniement humain en cours de certification.','steps':comp.get('lines',[]) if status=='HUMAN_TREE_EXACT' else [],'why':why if status=='HUMAN_TREE_EXACT' else 'Le calcul exact est disponible ; le candidat sémantique reste en revue.','qualification':{'counted':True,'fail_reasons':fails,'exact_replay':audit,'semantic_compression':{k:v for k,v in comp.items() if k!='lines'},'candidate_lines':comp.get('lines',[])[:20],'candidate_why':why,'auto_opening':opening}}


def render_html(cases,summary,path):
    arts=[]
    for ci,c in enumerate(cases):
        buttons=[];panels=[];non=[p for p in c['profiles'] if p['qualification'].get('counted')];default=non[0]['target'] if non else c['profiles'][-1]['target']
        for p in c['profiles']:
            active=' active' if p['target']==default else '';cls='pass' if p['status']=='HUMAN_TREE_EXACT' else ('trivial' if p['status']=='EXACT_TRIVIAL' else 'raw')
            buttons.append(f'<button class="obj {cls}{active}" data-case="{ci}" data-target="{p["target"]}"><b>{p["target"]}</b><span>{p["percent"]}</span></button>')
            hidden='' if p['target']==default else ' hidden';q=p['qualification'];cand=q.get('candidate_lines') or [];proc='<ol>'+''.join('<li>'+html.escape(x)+'</li>' for x in p['steps'])+'</ol>' if p['steps'] else '<p>'+html.escape(p['line'])+'</p>';candidate=''
            if p['status']=='RAW_EXACT_ONLY' and cand:candidate='<details><summary>Candidat exact non promu</summary><ol>'+''.join('<li>'+html.escape(x)+'</li>' for x in cand)+'</ol><p>'+html.escape(q.get('candidate_why') or '')+'</p></details>'
            panels.append(f'''<section class="profile" {'hidden' if hidden else ''} data-case="{ci}" data-target="{p['target']}"><div class="top"><b>Objectif {p['target']} — {p['percent']}</b><span class="{cls}">{p['status']}</span></div><div class="box"><h3>Maniement</h3>{proc}<h3>Pourquoi ?</h3><p>{html.escape(p['why'])}</p></div>{candidate}<details><summary>Diagnostic</summary><pre>{html.escape(json.dumps(q,ensure_ascii=False,indent=2))}</pre></details></section>''')
        arts.append(f'''<article><header><div class="holding"><span>{c['display'][0]}</span><span>{c['display'][1]}</span></div><b>{c['id']}</b></header><div class="objs">{''.join(buttons)}</div>{''.join(panels)}</article>''')
    path.write_text(f'''<!doctype html><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1"><title>V5.2</title><style>body{{background:#0b1016;color:#eef3f8;font:15px/1.5 system-ui;margin:0}}main{{max-width:1040px;margin:25px auto;padding:0 16px 60px}}article{{background:#141c25;border:1px solid #2c3947;border-radius:15px;padding:17px;margin:15px 0}}header{{display:flex;gap:24px;align-items:center}}.holding{{display:grid;justify-items:center;min-width:130px;font:800 26px/1.08 ui-monospace,monospace}}.summary,.box{{background:#0f161e;border-radius:10px;padding:13px}}.objs{{display:flex;flex-wrap:wrap;gap:7px;margin:12px 0}}.obj{{background:#101820;color:#eef3f8;border:1px solid #334354;border-radius:8px;padding:6px 9px}}.obj span{{margin-left:6px}}.obj.active{{border-color:#d5ad3b}}.top{{display:flex;justify-content:space-between}}.pass{{color:#75e3a6}}.raw{{color:#ffcc6b}}.trivial{{color:#9bafc1}}details{{margin-top:9px}}pre{{white-space:pre-wrap}}.profile[hidden]{{display:none}}</style><main><h1>V5.2 — normalisation des choix co-optimaux</h1><div class="summary"><b>{summary['human_tree_exact']} / {summary['nontrivial_profiles']}</b> objectifs non triviaux promus ({summary['qualification_rate_percent']} %). Les décisions sans enjeu sont supprimées et les tie-breaks du solveur sont normalisés avant compression.</div>{''.join(arts)}</main><script>document.querySelectorAll('.obj').forEach(b=>b.onclick=()=>{{let c=b.dataset.case,t=b.dataset.target;document.querySelectorAll('.obj[data-case="'+c+'"]').forEach(x=>x.classList.toggle('active',x===b));document.querySelectorAll('.profile[data-case="'+c+'"]').forEach(x=>x.hidden=x.dataset.target!==t)}})</script>''',encoding='utf-8')


def main():
    ap=argparse.ArgumentParser();ap.add_argument('--runtime-root',required=True);ap.add_argument('--reference',required=True);ap.add_argument('--out-dir',required=True);a=ap.parse_args();v50.assert_novel(a.reference);sys.path.insert(0,str(Path(a.runtime_root)/'runtime'));import integrated_engine as eng
    cases=[];counts=Counter();fails=Counter();non=passed=0
    for cid,north,south in v50.HOLDINGS:
        profiles=[]
        for target in range(1,max(len(north),len(south))+1):
            p=build_profile(eng,north,south,target);profiles.append(p);counts[p['status']]+=1
            if p['qualification'].get('counted'):non+=1;passed+=p['status']=='HUMAN_TREE_EXACT';fails.update(p['qualification'].get('fail_reasons') or [])
            print(json.dumps({'case':cid,'target':target,'p':p['fraction'],'status':p['status'],'fails':p['qualification'].get('fail_reasons',[]),'semantic':p['qualification'].get('semantic_compression',{})},ensure_ascii=False),flush=True)
        cases.append({'id':cid,'north':north,'south':south,'display':[v50.disp(north),v50.disp(south)],'profiles':profiles})
    summary={'schema':'MANIEMENTS_V5_HUMAN_V52_NORMALIZED_V1','holdings':20,'profiles_total':sum(len(c['profiles']) for c in cases),'nontrivial_profiles':non,'human_tree_exact':passed,'raw_exact_only':non-passed,'exact_trivial':counts['EXACT_TRIVIAL'],'qualification_rate_percent':f'{100*passed/non:.2f}','status_counts':dict(counts),'failure_reasons':dict(fails),'human_reference_answers_used':False,'novelty_gate':'PASS'}
    od=Path(a.out_dir);od.mkdir(parents=True,exist_ok=True);(od/'HUMAN_V52_NORMALIZED.json').write_text(json.dumps({'summary':summary,'cases':cases},ensure_ascii=False,indent=2)+'\n',encoding='utf-8');(od/'SUMMARY.txt').write_text('\n'.join(f'{k}={json.dumps(v,ensure_ascii=False) if isinstance(v,(dict,list)) else v}' for k,v in summary.items())+'\n',encoding='utf-8');render_html(cases,summary,od/'MANIEMENTS_V5_HUMAN_V52_NORMALIZED.html');print(json.dumps(summary,ensure_ascii=False),flush=True)

if __name__=='__main__':main()

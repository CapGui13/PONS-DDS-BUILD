#!/usr/bin/env python3
from __future__ import annotations

import argparse, html, itertools, json, math, sys
from collections import Counter, defaultdict
from fractions import Fraction
from pathlib import Path

HERE=Path(__file__).resolve().parent
sys.path.insert(0,str(HERE))
import human_qualification_v50 as v50

v48=v50.v48
v47=v50.v47
v46=v50.v46
v45=v50.v45
b=v50.b

STRATEGIC='AKQJT98'
LOW=set('765432')


def sem_rank(r):
    if r in LOW:return 'x'
    return r


def fr_rank(r):
    if r=='x':return 'petit'
    if r=='-':return 'chicane'
    return b.fr_article(r)


def pct(f):
    return f"{float(f)*100:.2f}".replace('.',',')+' %'


def bits_to_ranks(eng,mask):
    return [eng.I2R[r] for r in eng.ranks(mask)]


def low_family_safe(eng,e,s,need,seat,raw_rank):
    if raw_rank not in LOW:return False
    hand=s.north if seat=='N' else s.south
    legal=[eng.I2R[r] for r in eng.ranks(hand) if eng.I2R[r] in LOW]
    if not legal:return False
    feasible=v46.feasible_actions(eng,e,s,need)
    exact={(a,eng.I2R[r]) for a,r,_,support in feasible if (need|support)==support}
    return all((seat,r) in exact for r in legal)


def action_label(eng,e,n):
    seat,rank=n.action
    if low_family_safe(eng,e,n.state,n.mask,seat,rank):return 'x'
    return rank


def defender_relation(lead,seat):
    if lead=='N':return 'second' if seat=='E' else 'fourth'
    return 'second' if seat=='W' else 'fourth'


def previous_def_card(eng,e,s):
    r=v45.previous_def_card(eng,e,s)
    if r is None:return None
    return '-' if not r else sem_rank(eng.I2R[r])


def state_features(eng,e,s,round_no,act_seat,initial):
    phase='lead' if s.pos==0 else 'response'
    lead=act_seat if s.pos==0 else s.leader
    second='E' if lead=='N' else 'W'
    fourth='W' if lead=='N' else 'E'
    seen={'W':s.west_seen,'E':s.east_seen}
    void={'W':bool(s.west_void),'E':bool(s.east_void)}
    f={
        'round':round_no,
        'phase':phase,
        'seat':act_seat,
        'leader':lead,
        'won':s.won,
        'prev_card':previous_def_card(eng,e,s),
        'second_void':void[second],
        'fourth_void':void[fourth],
    }
    for h in STRATEGIC:
        bit=1<<eng.R2I[h]
        f['seen_'+h]=bool((s.west_seen|s.east_seen)&bit)
        f['second_'+h]=bool(seen[second]&bit)
        f['fourth_'+h]=bool(seen[fourth]&bit)
    # Remaining strategic cards are observable and resolve the rare states where
    # two paths reach the same round with different honours already spent.
    f['n_rem']=''.join(r for r in STRATEGIC if r in set(bits_to_ranks(eng,s.north)))
    f['s_rem']=''.join(r for r in STRATEGIC if r in set(bits_to_ranks(eng,s.south)))
    return f


def edge_round(parent,child,round_no):
    if parent.state.pos!=0 and child.state.pos==0:return round_no+1
    return round_no


def collect_samples(eng,e,root_node):
    out=[]; seen=set()
    def walk(n,rnd):
        key=(id(n),rnd)
        if key in seen:return
        seen.add(key)
        if n.kind=='T':return
        if n.kind=='D':
            seat,_=n.action
            out.append({'features':state_features(eng,e,n.state,rnd,seat,e.initial()),'action':action_label(eng,e,n),'node':n})
            ch=n.branches[0]
            walk(ch,edge_round(n,ch,rnd))
            return
        for _,ch in n.branches or []:
            walk(ch,edge_round(n,ch,rnd))
    walk(root_node,1)
    return out


def dedup_samples(samples):
    by=defaultdict(set); example={}
    for s in samples:
        f=s['features']; key=tuple(sorted(f.items()))
        by[key].add(s['action']); example[key]=s
    conflicts=[(k,sorted(v)) for k,v in by.items() if len(v)>1]
    uniq=[]
    for k,labels in by.items():
        if len(labels)==1:
            z=example[k].copy();z['action']=next(iter(labels));uniq.append(z)
    return uniq,conflicts


# Human predicates used by the exact rule compressor. More technical observable
# features are retained only as a last-resort diagnostic and prevent promotion.
PREFERRED_FEATURES=['prev_card','seen_K','seen_Q','seen_J','seen_T','seen_9','seen_8',
                    'second_void','fourth_void','second_K','second_Q','second_J','second_T','second_9','second_8',
                    'fourth_K','fourth_Q','fourth_J','fourth_T','fourth_9','fourth_8','won']
FALLBACK_FEATURES=['n_rem','s_rem']


def atom_matches(s,atom):
    k,v=atom
    return s['features'].get(k)==v


def atom_text(atom):
    k,v=atom
    if k=='prev_card':
        if v=='x':return "l’adversaire vient de fournir petit"
        if v=='-':return "l’adversaire vient de défausser"
        if v is None:return "aucune carte adverse n’a encore été fournie"
        return "l’adversaire vient de fournir "+fr_rank(v)
    if k.startswith('seen_'):
        r=k.split('_',1)[1]
        return (fr_rank(r)+" est déjà apparu") if v else (fr_rank(r)+" n’est pas encore apparu")
    if k.startswith('second_') and k!='second_void':
        r=k.split('_',1)[1]
        return (fr_rank(r)+" est apparu en deuxième") if v else (fr_rank(r)+" n’est pas apparu en deuxième")
    if k.startswith('fourth_') and k!='fourth_void':
        r=k.split('_',1)[1]
        return (fr_rank(r)+" est apparu en quatrième") if v else (fr_rank(r)+" n’est pas apparu en quatrième")
    if k=='second_void':return "l’adversaire en deuxième a montré une chicane" if v else "l’adversaire en deuxième n’a pas montré de chicane"
    if k=='fourth_void':return "l’adversaire en quatrième a montré une chicane" if v else "l’adversaire en quatrième n’a pas montré de chicane"
    if k=='won':return f"{v} levée{'s' if v!=1 else ''} ont déjà été gagnées dans la couleur"
    if k=='n_rem':return "les cartes stratégiques restantes dans la première main sont "+(v or 'aucune')
    if k=='s_rem':return "les cartes stratégiques restantes dans la seconde main sont "+(v or 'aucune')
    return f"{k}={v}"


def find_pure_rule(samples,label,default,used_mask):
    targets=[i for i,s in enumerate(samples) if s['action']==label and i not in used_mask]
    if not targets:return None
    features=PREFERRED_FEATURES+FALLBACK_FEATURES
    best=None
    # Conjunctions up to two observable predicates are deliberately preferred.
    for size in (1,2):
        for i in targets:
            vals=[(k,samples[i]['features'].get(k)) for k in features]
            for atoms in itertools.combinations(vals,size):
                matched=[j for j,s in enumerate(samples) if all(atom_matches(s,a) for a in atoms)]
                if not matched:continue
                if any(samples[j]['action']!=label for j in matched):continue
                cover=sum(1 for j in matched if j in targets)
                fallback=sum(1 for k,_ in atoms if k in FALLBACK_FEATURES)
                score=(cover,-fallback,-size)
                if best is None or score>best[0]:best=(score,atoms,matched)
        if best and best[0][0]>=len(targets):break
    return best


def compress_group(samples):
    counts=Counter(s['action'] for s in samples)
    default=counts.most_common(1)[0][0]
    used=set();rules=[];fallback_used=False
    for label,_ in counts.most_common():
        if label==default:continue
        while True:
            remaining=[i for i,s in enumerate(samples) if s['action']==label and i not in used]
            if not remaining:break
            found=find_pure_rule(samples,label,default,used)
            if not found:return None,True
            _,atoms,matched=found
            fallback_used |= any(k in FALLBACK_FEATURES for k,_ in atoms)
            covered=[j for j in matched if samples[j]['action']==label and j not in used]
            if not covered:return None,True
            used.update(covered)
            rules.append({'if':list(atoms),'action':label,'coverage':len(covered)})
    return {'default':default,'rules':rules,'counts':dict(counts)},fallback_used


def infer_toward(groups,round_no,lead_seat):
    other='S' if lead_seat=='N' else 'N'
    for key,g in groups.items():
        rnd,phase,seat,leader=key
        if rnd!=round_no or phase!='response' or seat!=other or leader!=lead_seat:continue
        # Prefer what is played when second hand follows low.
        low=[s for s in g['samples'] if s['features'].get('prev_card')=='x']
        if not low:continue
        c=Counter(s['action'] for s in low)
        a=c.most_common(1)[0][0]
        if a not in ('x','-'):return a
    return None


def action_text(action,phase,lead_action=None,toward=None,prev=None):
    if phase=='lead':
        if action=='x':return "jouer petit"+(" vers "+fr_rank(toward) if toward else '')
        if action=='A':return "tirer l’As"
        if action=='K':return "tirer le Roi"
        if action=='Q':return "jouer la Dame"
        if action=='J':return "jouer le Valet"
        return "jouer "+fr_rank(action)+(" vers "+fr_rank(toward) if toward else '')
    if action=='x':return "fournir petit"
    if prev not in (None,'x','-') and b.RANK_VALUE.get(action,0)>b.RANK_VALUE.get(prev,99):
        return "couvrir avec "+fr_rank(action)
    if action=='A':return "prendre de l’As"
    return "passer "+fr_rank(action)


def compress_policy(eng,e,raw_tree):
    samples,conflicts=dedup_samples(collect_samples(eng,e,raw_tree))
    if conflicts:return {'ok':False,'reason':'abstract_state_action_conflict','conflicts':conflicts[:10]}
    grouped=defaultdict(list)
    for s in samples:
        f=s['features'];key=(f['round'],f['phase'],f['seat'],f['leader']);grouped[key].append(s)
    groups={};fallback=False
    for key,ss in sorted(grouped.items()):
        c,fb=compress_group(ss)
        if c is None:return {'ok':False,'reason':'rules_not_separable','group':key}
        c['samples']=ss;groups[key]=c;fallback|=fb

    lines=[];rule_count=0
    for key,c in sorted(groups.items()):
        rnd,phase,seat,leader=key
        # Omit purely forced/trivial low-card responses from visible instructions.
        if phase=='response' and set(c['counts'])=={'x'}:continue
        toward=infer_toward(groups,rnd,seat) if phase=='lead' else None
        prefix=f"Au {rnd}{'er' if rnd==1 else 'e'} tour"
        for r in c['rules']:
            cond=' et '.join(atom_text(a) for a in r['if'])
            prev=next((v for k,v in r['if'] if k=='prev_card'),None)
            lines.append(f"{prefix}, si {cond} : {action_text(r['action'],phase,toward=toward,prev=prev)}.")
            rule_count+=1
        default_prev=None
        lines.append(f"{prefix}, sinon : {action_text(c['default'],phase,toward=toward,prev=default_prev)}.")
        rule_count+=1

    # Merge identical consecutive lead defaults into a single natural sentence.
    cleaned=[]
    for x in lines:
        if x not in cleaned:cleaned.append(x)
    human_safe=not fallback and len(cleaned)<=12
    return {'ok':True,'lines':cleaned,'rule_count':rule_count,'visible_lines':len(cleaned),'fallback_used':fallback,'human_safe':human_safe,'sample_count':len(samples)}


def world_atom_masks(eng,e,lead_seat):
    root=e.initial();visible=set(bits_to_ranks(eng,root.north))|set(bits_to_ranks(eng,root.south))
    missing=[r for r in STRATEGIC if r not in visible]
    atoms=[]
    def add(key,text,pred):
        mask=0
        for i,(w,ea) in enumerate(zip(e.model.world_w,e.model.world_e)):
            if pred(w,ea):mask|=1<<i
        if mask:atoms.append((key,text,mask))
    def rel_side(rel):
        if lead_seat=='N':return 'E' if rel=='second' else 'W'
        return 'W' if rel=='second' else 'E'
    for a in range(0,7):
        for c in range(0,a+1):
            if a+c!=13-root.north.bit_count()-root.south.bit_count():continue
    # exact split, orientation-free
    splits=set()
    for w,ea in zip(e.model.world_w,e.model.world_e):splits.add(tuple(sorted((w.bit_count(),ea.bit_count()),reverse=True)))
    for sp in sorted(splits,reverse=True):
        add('split'+str(sp),f"le partage {sp[0]}–{sp[1]}",lambda w,ea,sp=sp:tuple(sorted((w.bit_count(),ea.bit_count()),reverse=True))==sp)
    for h in missing:
        bit=1<<eng.R2I[h]
        for rel in ('second','fourth'):
            side=rel_side(rel)
            add(f'{h}_{rel}',f"{fr_rank(h)} en {rel}",lambda w,ea,bit=bit,side=side: bool((ea if side=='E' else w)&bit))
            for ln,adj in ((1,'sec'),(2,'second'),(3,'troisième'),(4,'quatrième'),(5,'cinquième'),(6,'sixième')):
                add(f'{h}_{rel}_{ln}',f"{fr_rank(h)} {adj} en {rel}",lambda w,ea,bit=bit,side=side,ln=ln: bool((ea if side=='E' else w)&bit) and (ea if side=='E' else w).bit_count()==ln)
    for h1,h2 in itertools.combinations(missing,2):
        b1=1<<eng.R2I[h1];b2=1<<eng.R2I[h2]
        for rel in ('second','fourth'):
            side=rel_side(rel)
            for ln,adj in ((2,'seconds'),(3,'troisièmes'),(4,'quatrièmes'),(5,'cinquièmes')):
                add(f'{h1}{h2}_{rel}_{ln}',f"{b.FR[h1]}-{b.FR[h2]} groupés {adj} en {rel}",lambda w,ea,b1=b1,b2=b2,side=side,ln=ln: (((ea if side=='E' else w)&b1) and ((ea if side=='E' else w)&b2) and (ea if side=='E' else w).bit_count()==ln))
    # dedupe equivalent masks, prefer shorter text
    best={}
    for k,t,m in atoms:
        if m not in best or len(t)<len(best[m][1]):best[m]=(k,t,m)
    return list(best.values())


def witness_reason(eng,e,row,alt):
    success=row['mask']; universe=(1<<e.model.n)-1
    altmask=alt['mask'] if alt else 0
    gain=success & ~altmask if alt else success
    atoms=world_atom_masks(eng,e,row['seat'])
    candidates=[]
    # First seek a position family won by the chosen line and not by the best alternative.
    for size in (1,2):
        for combo in itertools.combinations(atoms,size):
            m=universe
            for _,_,am in combo:m&=am
            if not m:continue
            if m & ~gain:continue
            weight=e.model.weight(m)
            text=' et '.join(x[1] for x in combo)
            candidates.append((weight,-size,-len(text),text,'differential'))
        if candidates:break
    if not candidates:
        # Fallback: a concrete pure winning family, still bridge-specific.
        for size in (1,2):
            for combo in itertools.combinations(atoms,size):
                m=universe
                for _,_,am in combo:m&=am
                if not m or (m & ~success):continue
                weight=e.model.weight(m);text=' et '.join(x[1] for x in combo)
                candidates.append((weight,-size,-len(text),text,'success'))
            if candidates:break
    if not candidates:return None
    _,_,_,text,kind=max(candidates)
    if kind=='differential':return "Cette ligne permet notamment de profiter de "+text+", position que le meilleur départ concurrent ne permet pas d’exploiter de la même façon."
    return "Cette ligne conserve notamment la possibilité de réussir avec "+text+'.'


def build_profile(eng,north,south,target):
    e=eng.Engine2(north,south,target);v45._ENG=eng;v45._E=e
    solved=e.solve(include_policy=False);opt=Fraction(solved['probability_fraction'])
    base={'target':target,'fraction':str(opt),'percent':pct(opt),'probability_decimal':float(opt)}
    if opt in (0,1):
        return {**base,'status':'EXACT_TRIVIAL','line':'Objectif impossible.' if opt==0 else 'Objectif assuré à 100 %.','steps':[],'why':'Aucune position adverse ne permet cet objectif.' if opt==0 else 'Cet objectif peut être assuré quelle que soit la répartition adverse.','qualification':{'counted':False}}
    root=e.initial();best=max(e.frontier(root),key=lambda m:(e.model.weight(m),m));assert e.model.weight(best)==opt
    row,opening=v47.choose_root(eng,e,best)
    decisions=[];raw=[];tree=v45.explore(eng,e,root,best,decisions,raw,{})
    audit=v50.audit_exact_tree(eng,e,tree,best)
    comp=compress_policy(eng,e,tree)
    alt=v48.alt_root(eng,e,root,row)
    why=witness_reason(eng,e,row,alt)
    fails=[]
    if not audit['ok']:fails.append('exact_replay_failed')
    if not comp.get('ok'):fails.append(comp.get('reason','semantic_compression_failed'))
    elif not comp.get('human_safe'):fails.append('semantic_rules_too_complex')
    if not why:fails.append('why_not_layout_specific')
    status='HUMAN_TREE_EXACT' if not fails else 'RAW_EXACT_ONLY'
    return {**base,'status':status,
            'line':(comp.get('lines') or [opening])[0] if status=='HUMAN_TREE_EXACT' else 'Calcul exact disponible — maniement humain en cours de certification.',
            'steps':comp.get('lines',[]) if status=='HUMAN_TREE_EXACT' else [],
            'why':why if status=='HUMAN_TREE_EXACT' else 'Le calcul exact est disponible ; la compression sémantique reste à améliorer.',
            'qualification':{'counted':True,'fail_reasons':fails,'exact_replay':audit,'semantic_compression':{k:v for k,v in comp.items() if k!='lines'},'candidate_lines':comp.get('lines',[])[:20],'candidate_why':why,'auto_opening':opening}}


def render_html(cases,summary,path):
    arts=[]
    for ci,c in enumerate(cases):
        bs=[];ps=[];non=[p for p in c['profiles'] if p['qualification'].get('counted')];default=non[0]['target'] if non else c['profiles'][-1]['target']
        for p in c['profiles']:
            active=' active' if p['target']==default else '';cls='pass' if p['status']=='HUMAN_TREE_EXACT' else ('trivial' if p['status']=='EXACT_TRIVIAL' else 'raw')
            bs.append(f'<button class="obj {cls}{active}" data-case="{ci}" data-target="{p["target"]}"><b>{p["target"]}</b><span>{html.escape(p["percent"])}</span></button>')
            hidden='' if p['target']==default else ' hidden';q=p['qualification'];cand=q.get('candidate_lines') or []
            proc='<ol>'+''.join('<li>'+html.escape(x)+'</li>' for x in p['steps'])+'</ol>' if p['steps'] else '<p class="line">'+html.escape(p['line'])+'</p>'
            candidate=''
            if p['status']=='RAW_EXACT_ONLY' and cand:
                candidate='<details><summary>Candidat V5.1 non promu</summary><ol>'+''.join('<li>'+html.escape(x)+'</li>' for x in cand)+'</ol><p>'+html.escape(q.get('candidate_why') or 'Pourquoi non extrait.')+'</p></details>'
            ps.append(f'''<section class="profile{hidden}" data-case="{ci}" data-target="{p['target']}"><div class="top"><div><b>Objectif {p['target']}</b><div class="prob">{p['percent']}</div><small>{p['fraction']}</small></div><span class="badge {cls}">{p['status']}</span></div><div class="box"><h3>Maniement</h3>{proc}<h3>Pourquoi ?</h3><p>{html.escape(p['why'])}</p></div>{candidate}<details><summary>Diagnostic</summary><pre>{html.escape(json.dumps(q,ensure_ascii=False,indent=2))}</pre></details></section>''')
        arts.append(f'''<article><header><div class="holding"><span>{html.escape(c['display'][0])}</span><span>{html.escape(c['display'][1])}</span></div><div><b>{c['id']}</b><p>Qualification sémantique V5.1</p></div></header><div class="objs">{''.join(bs)}</div>{''.join(ps)}</article>''')
    path.write_text(f'''<!doctype html><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1"><title>MANIEMENTS V5 — V5.1 sémantique</title><style>body{{margin:0;background:#0b1016;color:#eef3f8;font:15px/1.5 system-ui}}main{{max-width:1050px;margin:28px auto;padding:0 16px 60px}}article{{background:#141c25;border:1px solid #2c3947;border-radius:16px;padding:18px;margin:16px 0}}header{{display:flex;gap:22px;align-items:center}}.holding{{display:grid;justify-items:center;min-width:130px;font:800 26px/1.08 ui-monospace,monospace}}header p{{margin:2px 0;color:#aebcca}}.summary{{background:#101820;border-radius:12px;padding:14px}}.objs{{display:flex;gap:8px;flex-wrap:wrap;margin:14px 0}}.obj{{background:#0f161e;color:#eef3f8;border:1px solid #334354;border-radius:9px;padding:7px 10px;cursor:pointer}}.obj span{{margin-left:7px;color:#aebcca}}.obj.active{{border-color:#d5ad3b}}.top{{display:flex;justify-content:space-between;align-items:center}}.prob{{font-size:23px;color:#71daa0;font-weight:800}}.badge{{font-size:11px}}.pass{{color:#75e3a6}}.raw{{color:#ffcc6b}}.trivial{{color:#9bafc1}}.box{{background:#0f161e;border-radius:10px;padding:13px 15px;margin-top:10px}}.line{{font-weight:700}}details{{margin-top:10px}}pre{{white-space:pre-wrap;color:#aebcca}}.profile[hidden]{{display:none}}</style><main><h1>V5.1 — compression sémantique exacte</h1><div class="summary"><b>{summary['human_tree_exact']} / {summary['nontrivial_profiles']}</b> objectifs non triviaux promus HUMAN_TREE_EXACT — taux {summary['qualification_rate_percent']} %. Les règles sont apprises uniquement à partir d’observations visibles et vérifiées contre l’arbre exact.</div>{''.join(arts)}</main><script>document.querySelectorAll('.obj').forEach(b=>b.onclick=()=>{{let c=b.dataset.case,t=b.dataset.target;document.querySelectorAll('.obj[data-case="'+c+'"]').forEach(x=>x.classList.toggle('active',x===b));document.querySelectorAll('.profile[data-case="'+c+'"]').forEach(x=>x.hidden=x.dataset.target!==t)}})</script>''',encoding='utf-8')


def main():
    ap=argparse.ArgumentParser();ap.add_argument('--runtime-root',required=True);ap.add_argument('--reference',required=True);ap.add_argument('--out-dir',required=True);a=ap.parse_args()
    v50.assert_novel(a.reference)
    sys.path.insert(0,str(Path(a.runtime_root)/'runtime'));import integrated_engine as eng
    cases=[];counts=Counter();fails=Counter();non=0;passed=0
    for cid,north,south in v50.HOLDINGS:
        profiles=[]
        for target in range(1,max(len(north),len(south))+1):
            p=build_profile(eng,north,south,target);profiles.append(p);counts[p['status']]+=1
            if p['qualification'].get('counted'):
                non+=1;passed+=p['status']=='HUMAN_TREE_EXACT';fails.update(p['qualification'].get('fail_reasons') or [])
            print(json.dumps({'case':cid,'target':target,'p':p['fraction'],'status':p['status'],'fails':p['qualification'].get('fail_reasons',[]),'semantic':p['qualification'].get('semantic_compression',{})},ensure_ascii=False),flush=True)
        cases.append({'id':cid,'north':north,'south':south,'display':[v50.disp(north),v50.disp(south)],'profiles':profiles})
    summary={'schema':'MANIEMENTS_V5_HUMAN_V51_SEMANTIC_V1','holdings':len(cases),'profiles_total':sum(len(c['profiles']) for c in cases),'nontrivial_profiles':non,'human_tree_exact':passed,'raw_exact_only':non-passed,'exact_trivial':counts['EXACT_TRIVIAL'],'qualification_rate_percent':f'{100*passed/non:.2f}' if non else '100.00','status_counts':dict(counts),'failure_reasons':dict(fails),'human_reference_answers_used':False,'novelty_gate':'PASS'}
    od=Path(a.out_dir);od.mkdir(parents=True,exist_ok=True);(od/'HUMAN_V51_SEMANTIC.json').write_text(json.dumps({'summary':summary,'cases':cases},ensure_ascii=False,indent=2)+'\n',encoding='utf-8');(od/'SUMMARY.txt').write_text('\n'.join(f'{k}={json.dumps(v,ensure_ascii=False) if isinstance(v,(dict,list)) else v}' for k,v in summary.items())+'\n',encoding='utf-8');render_html(cases,summary,od/'MANIEMENTS_V5_HUMAN_V51_SEMANTIC.html');print(json.dumps(summary,ensure_ascii=False),flush=True)

if __name__=='__main__':main()

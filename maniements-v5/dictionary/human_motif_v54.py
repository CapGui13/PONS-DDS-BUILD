#!/usr/bin/env python3
from __future__ import annotations

import argparse, html, itertools, json, re, sys
from collections import Counter, defaultdict
from pathlib import Path

HERE=Path(__file__).resolve().parent
sys.path.insert(0,str(HERE))
import human_motif_v53 as v53

ROUND_COND_RE=re.compile(r'^Au (\d+)(?:er|e) tour, si (.+?)\s*:\s*(.+)\.$')
ROUND_ELSE_RE=re.compile(r'^Au (\d+)(?:er|e) tour, sinon\s*:\s*(.+)\.$')
ROUND_ANY_RE=re.compile(r'^Au (\d+)(?:er|e) tour, (.+)\.$')
LOW_COND_RE=re.compile(r'(?:fournir le|fourni le) ([2-7])\b')


def rl(n:int)->str:
    return '1er' if n==1 else f'{n}e'


def clean(s:str,display)->str:
    top,bottom=display
    s=v53.clean_fr(s)
    s=s.replace('apparuee','apparue').replace('apparuue','apparue')
    s=s.replace(' en fourth',' en quatrième')
    s=s.replace('la main du haut',top).replace('la main du bas',bottom)
    s=s.replace('1 levée ont déjà été gagnées','1 levée a déjà été gagnée')
    s=s.replace('1 levées ont déjà été gagnées','1 levée a déjà été gagnée')
    s=re.sub(r'\s+([,.;:])',r'\1',s)
    return re.sub(r'\s{2,}',' ',s).strip()


def split_atoms(cond):
    return [x.strip() for x in cond.split(' et ') if x.strip()]


def atom_family(a):
    if a.startswith('l’adversaire vient de fournir '): return 'prev'
    if 'n’est pas encore apparu' in a or 'est déjà apparu' in a: return 'seen'
    if 'chez l’adversaire placé avant ' in a: return 'side'
    if 'chicane' in a: return 'void'
    if 'levée' in a and 'gagnée' in a: return 'won'
    return 'other'


def or_phrase(atoms):
    atoms=list(dict.fromkeys(atoms))
    if len(atoms)==1:return atoms[0]
    pref='l’adversaire vient de fournir '
    if all(a.startswith(pref) for a in atoms):
        return pref+' ou '.join(a[len(pref):] for a in atoms)
    return '('+' ou '.join(atoms)+')'


def factor_conditions(conds):
    sets=[]
    for c in conds:
        z=set(split_atoms(c))
        if z not in sets:sets.append(z)
    if len(sets)==1:return ' et '.join(split_atoms(conds[0]))
    common=set.intersection(*sets) if sets else set()
    residual=[s-common for s in sets]
    pieces=sorted(common,key=lambda a:(atom_family(a),a))
    if residual and all(len(r)==1 for r in residual):
        pieces.append(or_phrase([next(iter(r)) for r in residual]))
        return ' et '.join(pieces)
    fams=sorted(set(atom_family(a) for r in residual for a in r))
    if len(fams)==2 and all(len(r)==2 and {atom_family(a) for a in r}==set(fams) for r in residual):
        vals={f:set() for f in fams};combos=set()
        for r in residual:
            pair=[]
            for f in fams:
                a=next(a for a in r if atom_family(a)==f);vals[f].add(a);pair.append(a)
            combos.add(tuple(pair))
        if combos==set(itertools.product(*[sorted(vals[f]) for f in fams])):
            pieces += [or_phrase(sorted(vals[f])) for f in fams]
            return ' et '.join(pieces)
    expr=[]
    source=residual if common else sets
    for r in source:
        x=' et '.join(sorted(r,key=lambda a:(atom_family(a),a)))
        expr.append('('+x+')' if len(r)>1 else x)
    pieces.append(' ou '.join(expr))
    return ' et '.join(pieces)


def merge_same_action(lines,display):
    lines=[clean(x,display) for x in lines];parsed=[]
    for i,x in enumerate(lines):
        m=ROUND_COND_RE.match(x)
        if m:parsed.append((i,int(m.group(1)),m.group(2),m.group(3)))
    groups=defaultdict(list)
    for r in parsed:groups[(r[1],r[3])].append(r)
    rep={};remove=set()
    for (rnd,act),rows in groups.items():
        if len(rows)<2:continue
        first=min(r[0] for r in rows)
        rep[first]=f'Au {rl(rnd)} tour, si {factor_conditions([r[2] for r in rows])}: {act}.'
        remove.update(r[0] for r in rows if r[0]!=first)
    return [rep.get(i,x) for i,x in enumerate(lines) if i not in remove]


def phase(act):
    z=act.strip().lower()
    if z.startswith(('jouer','tirer','présenter','commencer')):return 'lead'
    if z.startswith(('fournir','couvrir','prendre','passer','ne plus fournir')):return 'response'
    return 'other'


def merge_round_blocks(lines,display,max_branches=4):
    lines=[clean(x,display) for x in lines];out=[];i=0
    while i<len(lines):
        m=ROUND_COND_RE.match(lines[i]) or ROUND_ELSE_RE.match(lines[i])
        if not m:out.append(lines[i]);i+=1;continue
        rnd=int(m.group(1))
        def act(x):
            c=ROUND_COND_RE.match(x);e=ROUND_ELSE_RE.match(x)
            return c.group(3) if c else (e.group(2) if e else '')
        ph=phase(act(lines[i]));run=[];j=i
        while j<len(lines):
            mm=ROUND_COND_RE.match(lines[j]) or ROUND_ELSE_RE.match(lines[j])
            if not mm or int(mm.group(1))!=rnd or phase(act(lines[j]))!=ph:break
            run.append(lines[j]);j+=1
        if 2<=len(run)<=max_branches:
            parts=[]
            for x in run:
                c=ROUND_COND_RE.match(x);e=ROUND_ELSE_RE.match(x)
                parts.append(f'si {c.group(2)}, {c.group(3)}' if c else f'sinon, {e.group(2)}')
            out.append(f'Au {rl(rnd)} tour: '+'; '.join(parts)+'.')
        else:out.extend(run)
        i=j
    return out


def safe_scaffold(lines,display):
    rounds=[]
    for x in lines:
        m=ROUND_ANY_RE.match(clean(x,display))
        if m:rounds.append(int(m.group(1)))
    if not rounds or min(rounds)<=1:return []
    first=min(rounds);cards=''.join(display).replace('R','K').replace('D','Q').replace('V','J').replace('X','T')
    names=[]
    for h,fr in [('A','l’As'),('K','le Roi'),('Q','la Dame'),('J','le Valet')]:
        if h not in cards:break
        names.append(fr)
        if len(names)>=first-1:break
    if len(names)<first-1:return []
    if len(names)==1:return ['Commencer par tirer '+names[0]+'.']
    return ['Commencer par tirer '+', puis '.join(names[:-1])+' puis '+names[-1]+'.']


def naturalize(lines,display):
    scaffold=safe_scaffold(lines,display)
    x=[clean(s,display) for s in lines]
    x=v53.combine_lead_with_default(x)
    x=v53.compress_lead_sequence(x)
    x=v53.merge_repeated_exception(x)
    x=merge_same_action(x,display)
    x=merge_round_blocks(x,display,4)
    return scaffold+[clean(s,display) for s in x]


def condition_count(lines):
    return sum(len(re.findall(r'\bsi\b',x.lower())) for x in lines)


def spot_count(lines):
    return sum(len(LOW_COND_RE.findall(x)) for x in lines if 'si ' in x.lower())


def exact_quality(lines):
    text=' '.join(lines).lower()
    bad=('main du haut','main du bas','void','il reste dans','n_rem','s_rem','contexte','masque','witness','apparuee',' en fourth','de le ')
    return bool(lines) and len(lines)<=6 and len(text)<=1100 and condition_count(lines)<=7 and spot_count(lines)<=2 and max(map(len,lines))<=430 and not any(z in text for z in bad)


def bridge_ready(lines):
    text=' '.join(lines).lower()
    if not exact_quality(lines) or len(lines)>5 or max(map(len,lines))>280 or condition_count(lines)>5:return False
    bad=('1 levée a déjà été gagnée','est apparu chez l’adversaire placé avant','n’est pas apparu chez l’adversaire placé avant','au 1er tour, puis au 2e tour','au 2e tour, puis au 3e tour')
    if any(z in text for z in bad):return False
    if re.search(r'vers le (\w+), puis vers le \1',text):return False
    for x in lines:
        if 'si ' in x.lower() and LOW_COND_RE.search(x):return False
    return True


def load_engine(root):
    root=Path(root)
    for p in (root/'runtime',root/'engine',root):
        if (p/'integrated_engine.py').exists():
            sys.path.insert(0,str(p));import integrated_engine as eng;return eng
    raise FileNotFoundError('integrated_engine.py introuvable')


def indices(mask):
    while mask:
        b=mask&-mask;yield b.bit_length()-1;mask-=b


def fr_rank(eng,r):
    c=eng.I2R[r];return {'A':'l’As','K':'le Roi','Q':'la Dame','J':'le Valet','T':'le 10'}.get(c,'le '+c)


def fr_cards(eng,mask):
    conv={'K':'R','Q':'D','J':'V','T':'X'}
    return ''.join(conv.get(eng.I2R[r],eng.I2R[r]) for r in sorted(eng.ranks(mask),reverse=True))


def exact_reason(eng,north,south,target,upstream):
    e=eng.Engine2(north,south,target);front=e.frontier(e.initial());best=max(front,key=lambda m:(e.model.weight(m),m));allm=e.model.all;fail=allm&~best;succ=best;n=allm.bit_count()
    def owner(i,r):return 'W' if e.model.owner['W'][r]&(1<<i) else 'E'
    for r in sorted(e.model.missing,reverse=True):
        if eng.I2R[r] not in 'AKQJT98':continue
        for side in ('W','E'):
            pred=sum(1<<i for i in range(n) if owner(i,r)==side)
            if succ==pred:return f"L’objectif réussit exactement lorsque {fr_rank(eng,r)} est du côté favorable à l’impasse ; sa position résume entièrement le problème."
            if fail==pred:return f"L’objectif échoue exactement lorsque {fr_rank(eng,r)} est du mauvais côté ; toutes les autres positions de cette carte sont couvertes."
    strategic=[r for r in e.model.missing if eng.I2R[r] in 'AKQJT98']
    for a,b in itertools.combinations(sorted(strategic,reverse=True),2):
        for side in ('W','E'):
            pred=sum(1<<i for i in range(n) if owner(i,a)==side and owner(i,b)==side)
            if fail==pred:return f"La ligne échoue exactement lorsque {fr_rank(eng,a)} et {fr_rank(eng,b)} sont réunis du mauvais côté ; toutes leurs autres positions sont couvertes."
    fi=list(indices(fail))
    if len(fi)==1:
        i=fi[0];wm=e.model.world_w[i];em=e.model.world_e[i];wc,ec=wm.bit_count(),em.bit_count();bad=wm if wc>ec else em
        return f"L’objectif n’échoue que contre le partage {max(wc,ec)}–{min(wc,ec)} défavorable, avec {fr_cards(eng,bad)} réunis dans la même main adverse."
    return upstream


def priority(q,lines,exact_compact):
    return (150 if exact_compact else 0)+(100 if q.get('semantic_policy_generic') else 0)+max(0,40-5*len(lines))+max(0,20-3*condition_count(lines))-10*spot_count(lines)


def build(src,eng):
    cases=[];counts=Counter();queue=[];non=compact=ready_n=0
    for c in src['cases']:
        profiles=[]
        for p in c['profiles']:
            z=dict(p);q=dict(z.get('qualification') or {})
            if not q.get('counted'):
                q['bridge_ready_v54']=False;z['qualification']=q;profiles.append(z);counts[z['status']]+=1;continue
            non+=1;lines=naturalize(q.get('candidate_lines') or q.get('motif_lines') or [],c['display']);upstream=clean(q.get('candidate_why') or z.get('why',''),c['display']);generic=bool(q.get('semantic_policy_generic'))
            exact_compact=generic and exact_quality(lines) and bool(upstream);ready=exact_compact and bridge_ready(lines);why=exact_reason(eng,c['north'],c['south'],int(z['target']),upstream) if ready else upstream
            z['status']='HUMAN_TREE_EXACT' if exact_compact else 'RAW_EXACT_ONLY';z['steps']=lines if ready else [];z['line']=lines[0] if ready else 'Calcul exact disponible — explication en cours de certification.';z['why']=why if ready else 'Le calcul exact est disponible ; la formulation humaine reste en revue.'
            q.update({'bridge_lines_v54':lines,'bridge_quality_v54':exact_quality(lines),'bridge_ready_v54':ready,'exact_layout_reason_v54':why,'condition_count_v54':condition_count(lines),'spot_condition_count_v54':spot_count(lines)});z['qualification']=q
            compact+=int(exact_compact);ready_n+=int(ready);counts[z['status']]+=1;profiles.append(z)
            if not ready:queue.append({'case':c['id'],'display':c['display'],'target':z['target'],'percent':z.get('percent'),'priority':priority(q,lines,exact_compact),'generic':generic,'exact_compact':exact_compact,'lines':lines,'why_candidate':why,'conditions':condition_count(lines),'spot_conditions':spot_count(lines)})
        cases.append({k:v for k,v in c.items() if k!='profiles'}|{'profiles':profiles})
    queue.sort(key=lambda x:(-x['priority'],len(x['lines']),x['case'],x['target']))
    summary={'schema':'MANIEMENTS_V5_HUMAN_V54_BRIDGE_MOTIF_V2','holdings':len(cases),'profiles_total':sum(len(c['profiles']) for c in cases),'nontrivial_profiles':non,'human_tree_exact':compact,'bridge_ready':ready_n,'raw_exact_only':non-compact,'exact_trivial':counts['EXACT_TRIVIAL'],'qualification_rate_percent':f'{100*compact/non:.2f}','bridge_ready_rate_percent':f'{100*ready_n/non:.2f}','status_counts':dict(counts),'review_queue_size':len(queue),'source':'V5.2 exact normalized policies; lossless bridge compaction + strict presentation gate'}
    return cases,summary,queue


def render_html(cases,summary,path):
    arts=[]
    for ci,c in enumerate(cases):
        non=[p for p in c['profiles'] if p.get('qualification',{}).get('counted')];default=non[0]['target'] if non else c['profiles'][-1]['target'];buttons=[];panels=[]
        for p in c['profiles']:
            q=p.get('qualification') or {};ready=q.get('bridge_ready_v54',False);active=' active' if p['target']==default else '';cls='ready' if ready else ('exact' if p['status']=='HUMAN_TREE_EXACT' else ('trivial' if p['status']=='EXACT_TRIVIAL' else 'raw'));buttons.append(f'<button class="obj {cls}{active}" data-case="{ci}" data-target="{p["target"]}"><b>{p["target"]}</b><span>{p["percent"]}</span></button>');hide='' if p['target']==default else ' hidden'
            if ready:proc='<ol>'+''.join('<li>'+html.escape(x)+'</li>' for x in p['steps'])+'</ol>';why='<p>'+html.escape(p['why'])+'</p>'
            elif p['status']=='EXACT_TRIVIAL':proc='<p>'+html.escape(p['line'])+'</p>';why='<p>'+html.escape(p['why'])+'</p>'
            else:proc='<p>Calcul exact disponible — explication en cours de certification.</p>';why='<p>La formulation n’est pas encore assez naturelle pour la vue normale.</p>'
            cand='';lines=q.get('bridge_lines_v54') or []
            if not ready and lines:cand='<details><summary>Candidat exact V5.4</summary><ol>'+''.join('<li>'+html.escape(x)+'</li>' for x in lines)+'</ol></details>'
            panels.append(f'<section class="profile"{hide} data-case="{ci}" data-target="{p["target"]}"><div class="top"><b>Objectif {p["target"]} — {p["percent"]}</b><span class="{cls}">{"BRIDGE_READY" if ready else p["status"]}</span></div><div class="box"><h3>Maniement</h3>{proc}<h3>Pourquoi ?</h3>{why}</div>{cand}</section>')
        arts.append(f'<article><header><div class="holding"><span>{c["display"][0]}</span><span>{c["display"][1]}</span></div><b>{c["id"]}</b></header><div class="objs">{"".join(buttons)}</div>{"".join(panels)}</article>')
    path.write_text(f'''<!doctype html><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1"><title>V5.4 bridge motifs</title><style>body{{background:#0b1016;color:#eef3f8;font:15px/1.5 system-ui;margin:0}}main{{max-width:1040px;margin:25px auto;padding:0 16px 60px}}article{{background:#141c25;border:1px solid #2c3947;border-radius:15px;padding:17px;margin:15px 0}}header{{display:flex;gap:24px;align-items:center}}.holding{{display:grid;justify-items:center;min-width:130px;font:800 26px/1.08 ui-monospace,monospace}}.summary,.box{{background:#0f161e;border-radius:10px;padding:13px}}.objs{{display:flex;flex-wrap:wrap;gap:7px;margin:12px 0}}.obj{{background:#101820;color:#eef3f8;border:1px solid #334354;border-radius:8px;padding:6px 9px}}.obj span{{margin-left:6px}}.obj.active{{border-color:#d5ad3b}}.top{{display:flex;justify-content:space-between}}.ready{{color:#75e3a6}}.exact{{color:#6bbcff}}.raw{{color:#ffcc6b}}.trivial{{color:#9bafc1}}.profile[hidden]{{display:none}}</style><main><h1>V5.4 — motifs de bridge</h1><div class="summary"><b>{summary['human_tree_exact']} / {summary['nontrivial_profiles']}</b> compressions exactes ; <b>{summary['bridge_ready']} / {summary['nontrivial_profiles']}</b> assez naturelles pour la vue normale.</div>{''.join(arts)}</main><script>document.querySelectorAll('.obj').forEach(b=>b.onclick=()=>{{let c=b.dataset.case,t=b.dataset.target;document.querySelectorAll('.obj[data-case="'+c+'"]').forEach(x=>x.classList.toggle('active',x===b));document.querySelectorAll('.profile[data-case="'+c+'"]').forEach(x=>x.hidden=x.dataset.target!==t)}})</script>''',encoding='utf-8')


def main():
    ap=argparse.ArgumentParser();ap.add_argument('--input',required=True);ap.add_argument('--runtime-root',required=True);ap.add_argument('--out-dir',required=True);a=ap.parse_args();eng=load_engine(a.runtime_root);src=json.load(open(a.input,encoding='utf-8'));cases,summary,queue=build(src,eng);od=Path(a.out_dir);od.mkdir(parents=True,exist_ok=True)
    (od/'HUMAN_V54_BRIDGE_MOTIF.json').write_text(json.dumps({'summary':summary,'cases':cases},ensure_ascii=False,indent=2)+'\n',encoding='utf-8');(od/'HUMAN_V54_REVIEW_QUEUE.json').write_text(json.dumps({'summary':summary,'queue':queue},ensure_ascii=False,indent=2)+'\n',encoding='utf-8');(od/'SUMMARY.txt').write_text('\n'.join(f'{k}={json.dumps(v,ensure_ascii=False) if isinstance(v,(dict,list)) else v}' for k,v in summary.items())+'\n',encoding='utf-8');render_html(cases,summary,od/'MANIEMENTS_V5_HUMAN_V54_BRIDGE_MOTIF.html');print(json.dumps(summary,ensure_ascii=False),flush=True)

if __name__=='__main__':main()

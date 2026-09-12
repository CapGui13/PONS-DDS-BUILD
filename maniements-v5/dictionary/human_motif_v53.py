#!/usr/bin/env python3
from __future__ import annotations

import argparse, html, json, re, sys
from collections import Counter, defaultdict
from pathlib import Path

HERE=Path(__file__).resolve().parent
sys.path.insert(0,str(HERE))
import human_semantic_v52 as v52

v50=v52.v50

ROUND_RE=re.compile(r'^Au (\d+)(?:er|e) tour, (.*)$')
LEAD_LOW_RE=re.compile(r'^Au (\d+)(?:er|e) tour, jouer petit de (.+?)(?: vers (.+?))?\.$')
DEFAULT_PASS_RE=re.compile(r'^Au (\d+)(?:er|e) tour, sinon : passer (.+)\.$')
PLAIN_PASS_RE=re.compile(r'^Au (\d+)(?:er|e) tour, passer (.+)\.$')


def round_label(n:int)->str:
    return '1er' if n==1 else f'{n}e'


def clean_fr(s:str)->str:
    s=s.replace('de le partage','du partage')
    s=s.replace('de le Roi','du Roi').replace('de le Valet','du Valet').replace('de le 10','du 10')
    s=s.replace(' en second',' en deuxième').replace(' en fourth',' en quatrième')
    s=s.replace('la Dame n’est pas encore apparu','la Dame n’est pas encore apparue')
    s=s.replace('la Dame est déjà apparu','la Dame est déjà apparue')
    s=s.replace('la Dame n’est pas apparu','la Dame n’est pas apparue')
    s=s.replace('la Dame est apparu','la Dame est apparue')
    s=s.replace('1 levée ont déjà été gagnées','1 levée a déjà été gagnée')
    s=s.replace('1 levées ont déjà été gagnées','1 levée a déjà été gagnée')
    s=s.replace('le void','la chicane').replace('du void','de la chicane')
    s=s.replace('le Roi en deuxième','le Roi placé en deuxième')
    s=s.replace('la Dame en deuxième','la Dame placée en deuxième')
    s=s.replace('le Valet en deuxième','le Valet placé en deuxième')
    s=s.replace('le 10 en deuxième','le 10 placé en deuxième')
    return s


def combine_lead_with_default(lines):
    """Lossless wording merge: lead small + default pass X -> small toward X.

    Conditional response clauses remain unchanged and keep their round label.
    """
    lines=[clean_fr(x) for x in lines]
    out=[];i=0
    while i<len(lines):
        m=LEAD_LOW_RE.match(lines[i])
        if not m or m.group(3):
            out.append(lines[i]);i+=1;continue
        rnd=int(m.group(1));hand=m.group(2);j=i+1;end=j;target_idx=None;target=None
        while end<len(lines):
            rm=ROUND_RE.match(lines[end])
            if not rm or int(rm.group(1))!=rnd:break
            dm=DEFAULT_PASS_RE.match(lines[end]) or PLAIN_PASS_RE.match(lines[end])
            if dm:
                target_idx=end;target=dm.group(2)
            end+=1
        if target_idx is None:
            out.append(lines[i]);i+=1;continue
        out.append(f'Au {round_label(rnd)} tour, jouer petit de {hand} vers {target}.')
        for k in range(i+1,end):
            if k!=target_idx:out.append(lines[k])
        i=end
    return out


def compress_lead_sequence(lines):
    """Merge repeated small-card leads from the same hand without changing branches.

    Only the unconditional lead sentences are merged; all conditional clauses keep
    their original round labels, so the structured policy remains losslessly readable.
    """
    lead=[]
    for i,x in enumerate(lines):
        m=LEAD_LOW_RE.match(x)
        if m:lead.append((i,int(m.group(1)),m.group(2),m.group(3)))
    by_hand=defaultdict(list)
    for row in lead:by_hand[row[2]].append(row)
    replace={};remove=set()
    for hand,rows in by_hand.items():
        rows=sorted(rows,key=lambda z:z[1])
        # Split into consecutive round runs.
        runs=[];cur=[]
        for r in rows:
            if not cur or r[1]==cur[-1][1]+1:cur.append(r)
            else:
                if len(cur)>=2:runs.append(cur)
                cur=[r]
        if len(cur)>=2:runs.append(cur)
        for run in runs:
            desc=[]
            for _,rnd,_,target in run:
                desc.append(target)
            rounds=[r[1] for r in run]
            if all(desc):
                seq=', puis '.join('vers '+d for d in desc)
                txt=f'Jouer successivement petit de {hand} {seq}.'
            elif not any(desc):
                txt=f'Jouer successivement de {hand} aux tours {", ".join(round_label(r) for r in rounds)}.'
            else:
                parts=[]
                for rnd,target in zip(rounds,desc):
                    parts.append(f'au {round_label(rnd)} tour'+((' vers '+target) if target else ''))
                txt=f'Jouer petit de {hand} '+', puis '.join(parts)+'.'
            replace[run[0][0]]=txt
            remove.update(r[0] for r in run[1:])
    out=[]
    for i,x in enumerate(lines):
        if i in remove:continue
        out.append(replace.get(i,x))
    return out


def merge_repeated_exception(lines):
    """Merge the same conditional reaction repeated over consecutive rounds."""
    parsed=[]
    pat=re.compile(r'^Au (\d+)(?:er|e) tour, si (.+?) : (.+)\.$')
    for i,x in enumerate(lines):
        m=pat.match(x)
        if m:parsed.append((i,int(m.group(1)),m.group(2),m.group(3)))
    groups=defaultdict(list)
    for r in parsed:groups[(r[2],r[3])].append(r)
    rep={};remove=set()
    for (cond,act),rows in groups.items():
        rows=sorted(rows,key=lambda z:z[1]);runs=[];cur=[]
        for r in rows:
            if not cur or r[1]==cur[-1][1]+1:cur.append(r)
            else:
                if len(cur)>=2:runs.append(cur)
                cur=[r]
        if len(cur)>=2:runs.append(cur)
        for run in runs:
            a,b=run[0][1],run[-1][1]
            rep[run[0][0]]=f'Du {round_label(a)} au {round_label(b)} tour, si {cond} : {act}.'
            remove.update(r[0] for r in run[1:])
    return [rep.get(i,x) for i,x in enumerate(lines) if i not in remove]


def prepend_master_scaffold(lines,display):
    """Restore a natural scaffold when all earlier rounds were strategically irrelevant.

    This is applied only when the first visible instruction starts after round 1 and
    the partnership owns the top consecutive master honours needed for those omitted
    rounds. Because V5.2 pruned exactly the states in which every legal declarer action
    preserved the optimum, choosing these masters is exact-preserving.
    """
    rounds=[]
    for x in lines:
        m=ROUND_RE.match(x)
        if m:rounds.append(int(m.group(1)))
    if not rounds:return lines
    first=min(rounds)
    if first<=1:return lines
    cards=''.join(display).replace('R','K').replace('D','Q').replace('V','J').replace('X','T')
    wanted=[]
    for h,fr in [('A','l’As'),('K','le Roi'),('Q','la Dame'),('J','le Valet')]:
        if h in cards:wanted.append(fr)
        else:break
        if len(wanted)>=first-1:break
    if len(wanted)<first-1:return lines
    chosen=wanted[:first-1]
    if len(chosen)==1:txt='Commencer par tirer '+chosen[0]+'.'
    else:txt='Commencer par tirer '+', puis '.join(chosen[:-1])+' puis '+chosen[-1]+'.'
    return [txt]+lines


def motif_render(lines,display):
    lines=combine_lead_with_default(lines)
    lines=compress_lead_sequence(lines)
    lines=merge_repeated_exception(lines)
    lines=prepend_master_scaffold(lines,display)
    return [clean_fr(x) for x in lines]


def human_quality(lines):
    text=' '.join(lines).lower()
    bad=('main du haut','main du bas','void','il reste dans','n_rem','s_rem','calcul exact','contexte','masque','witness')
    if any(x in text for x in bad):return False
    # The dictionary target remains a short procedure, not a rewritten automaton.
    return 0<len(lines)<=7 and len(text)<=1150


def build_cases(src):
    cases=[];counts=Counter();non=passed=0;fails=Counter()
    for c in src['cases']:
        profiles=[]
        for p in c['profiles']:
            q=dict(p.get('qualification') or {})
            if not q.get('counted'):
                z=dict(p);z['why']=clean_fr(z.get('why',''));profiles.append(z);counts[z['status']]+=1;continue
            non+=1
            sem=q.get('semantic_compression') or {}
            candidate=q.get('candidate_lines') or p.get('steps') or []
            motif=motif_render(candidate,c['display']) if candidate else []
            why=clean_fr(q.get('candidate_why') or p.get('why') or '')
            exact_semantic=bool(sem.get('ok')) and not sem.get('spot_fallback_used',False) and not any(r in (q.get('fail_reasons') or []) for r in ('exact_replay_failed','true_observable_conflict','rules_not_separable'))
            good=exact_semantic and human_quality(motif) and bool(why)
            status='HUMAN_TREE_EXACT' if good else 'RAW_EXACT_ONLY'
            if good:passed+=1
            else:
                if not exact_semantic:fails['semantic_policy_not_generic']+=1
                elif not human_quality(motif):fails['motif_still_too_complex']+=1
                elif not why:fails['why_missing']+=1
            nq=dict(q);nq['motif_lines']=motif;nq['motif_line_count']=len(motif);nq['motif_human_quality']=human_quality(motif);nq['semantic_policy_generic']=exact_semantic
            z=dict(p);z['status']=status;z['steps']=motif if good else [];z['line']=motif[0] if good and motif else 'Calcul exact disponible — maniement humain en cours de certification.';z['why']=why if good else 'Le calcul exact est disponible ; la formulation humaine reste en revue.';z['qualification']=nq
            profiles.append(z);counts[status]+=1
        cases.append({k:v for k,v in c.items() if k!='profiles'}|{'profiles':profiles})
    summary={'schema':'MANIEMENTS_V5_HUMAN_V53_MOTIF_V1','holdings':len(cases),'profiles_total':sum(len(c['profiles']) for c in cases),'nontrivial_profiles':non,'human_tree_exact':passed,'raw_exact_only':non-passed,'exact_trivial':counts['EXACT_TRIVIAL'],'qualification_rate_percent':f'{100*passed/non:.2f}' if non else '100.00','status_counts':dict(counts),'failure_reasons':dict(fails),'human_reference_answers_used':False,'source':'V5.2 normalized exact semantic policies'}
    return cases,summary


def render_html(cases,summary,path):
    arts=[]
    for ci,c in enumerate(cases):
        buttons=[];panels=[];non=[p for p in c['profiles'] if p.get('qualification',{}).get('counted')];default=non[0]['target'] if non else c['profiles'][-1]['target']
        for p in c['profiles']:
            active=' active' if p['target']==default else '';cls='pass' if p['status']=='HUMAN_TREE_EXACT' else ('trivial' if p['status']=='EXACT_TRIVIAL' else 'raw')
            buttons.append(f'<button class="obj {cls}{active}" data-case="{ci}" data-target="{p["target"]}"><b>{p["target"]}</b><span>{p["percent"]}</span></button>')
            hidden='' if p['target']==default else ' hidden';q=p.get('qualification') or {};motif=q.get('motif_lines') or [];proc='<ol>'+''.join('<li>'+html.escape(x)+'</li>' for x in p.get('steps',[]))+'</ol>' if p.get('steps') else '<p>'+html.escape(p['line'])+'</p>';cand=''
            if p['status']=='RAW_EXACT_ONLY' and motif:cand='<details><summary>Candidat motif non promu</summary><ol>'+''.join('<li>'+html.escape(x)+'</li>' for x in motif)+'</ol><p>'+html.escape(clean_fr(q.get('candidate_why') or ''))+'</p></details>'
            panels.append(f'''<section class="profile" {'hidden' if hidden else ''} data-case="{ci}" data-target="{p['target']}"><div class="top"><b>Objectif {p['target']} — {p['percent']}</b><span class="{cls}">{p['status']}</span></div><div class="box"><h3>Maniement</h3>{proc}<h3>Pourquoi ?</h3><p>{html.escape(p['why'])}</p></div>{cand}<details><summary>Diagnostic</summary><pre>{html.escape(json.dumps(q,ensure_ascii=False,indent=2))}</pre></details></section>''')
        arts.append(f'''<article><header><div class="holding"><span>{c['display'][0]}</span><span>{c['display'][1]}</span></div><b>{c['id']}</b></header><div class="objs">{''.join(buttons)}</div>{''.join(panels)}</article>''')
    path.write_text(f'''<!doctype html><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1"><title>V5.3 motifs</title><style>body{{background:#0b1016;color:#eef3f8;font:15px/1.5 system-ui;margin:0}}main{{max-width:1040px;margin:25px auto;padding:0 16px 60px}}article{{background:#141c25;border:1px solid #2c3947;border-radius:15px;padding:17px;margin:15px 0}}header{{display:flex;gap:24px;align-items:center}}.holding{{display:grid;justify-items:center;min-width:130px;font:800 26px/1.08 ui-monospace,monospace}}.summary,.box{{background:#0f161e;border-radius:10px;padding:13px}}.objs{{display:flex;flex-wrap:wrap;gap:7px;margin:12px 0}}.obj{{background:#101820;color:#eef3f8;border:1px solid #334354;border-radius:8px;padding:6px 9px}}.obj span{{margin-left:6px}}.obj.active{{border-color:#d5ad3b}}.top{{display:flex;justify-content:space-between}}.pass{{color:#75e3a6}}.raw{{color:#ffcc6b}}.trivial{{color:#9bafc1}}details{{margin-top:9px}}pre{{white-space:pre-wrap}}.profile[hidden]{{display:none}}</style><main><h1>V5.3 — rendu par motifs de bridge</h1><div class="summary"><b>{summary['human_tree_exact']} / {summary['nontrivial_profiles']}</b> objectifs non triviaux ont maintenant une procédure exacte assez courte pour la vue normale ({summary['qualification_rate_percent']} %). Les fusions de texte sont lossless : elles ne changent aucune condition de la politique V5.2.</div>{''.join(arts)}</main><script>document.querySelectorAll('.obj').forEach(b=>b.onclick=()=>{{let c=b.dataset.case,t=b.dataset.target;document.querySelectorAll('.obj[data-case="'+c+'"]').forEach(x=>x.classList.toggle('active',x===b));document.querySelectorAll('.profile[data-case="'+c+'"]').forEach(x=>x.hidden=x.dataset.target!==t)}})</script>''',encoding='utf-8')


def main():
    ap=argparse.ArgumentParser();ap.add_argument('--input',required=True);ap.add_argument('--out-dir',required=True);a=ap.parse_args();src=json.loads(Path(a.input).read_text(encoding='utf-8'));cases,summary=build_cases(src);od=Path(a.out_dir);od.mkdir(parents=True,exist_ok=True);(od/'HUMAN_V53_MOTIF.json').write_text(json.dumps({'summary':summary,'cases':cases},ensure_ascii=False,indent=2)+'\n',encoding='utf-8');(od/'SUMMARY.txt').write_text('\n'.join(f'{k}={json.dumps(v,ensure_ascii=False) if isinstance(v,(dict,list)) else v}' for k,v in summary.items())+'\n',encoding='utf-8');render_html(cases,summary,od/'MANIEMENTS_V5_HUMAN_V53_MOTIF.html');print(json.dumps(summary,ensure_ascii=False))
if __name__=='__main__':main()

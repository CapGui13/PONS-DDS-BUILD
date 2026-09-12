#!/usr/bin/env python3
from __future__ import annotations

import argparse, html, json, re
from collections import Counter
from pathlib import Path


def clean_sentence(s:str)->str:
    # Idempotent French cleanup; V5.3 may already have applied part of it.
    s=s.replace('apparuee','apparue')
    s=s.replace('1 levée ont déjà été gagnées','1 levée a déjà été gagnée')
    s=s.replace('1 levées ont déjà été gagnées','1 levée a déjà été gagnée')
    s=s.replace('de le partage','du partage').replace('de le Roi','du Roi').replace('de le Valet','du Valet').replace('de le 10','du 10')
    s=s.replace(' en second',' en deuxième').replace(' en fourth',' en quatrième')
    s=s.replace('la Dame n’est pas encore apparu','la Dame n’est pas encore apparue')
    s=s.replace('la Dame est déjà apparu','la Dame est déjà apparue')
    s=s.replace('la Dame n’est pas apparu','la Dame n’est pas apparue')
    s=s.replace('la Dame est apparu','la Dame est apparue')
    s=s.replace('le void','la chicane')
    return s


def ordinal_word(n:int)->str:
    return {1:'premier',2:'deuxième',3:'troisième',4:'quatrième',5:'cinquième',6:'sixième'}.get(n,str(n)+'e')


def naturalize_rule(s:str)->str:
    s=clean_sentence(s)
    # Repeated-cover rule emitted by the lossless V5.3 renderer.
    m=re.match(r'^Du (\d+)(?:er|e) au (\d+)(?:er|e) tour, si l’adversaire vient de fournir (.+?) : couvrir avec (.+)\.$',s)
    if m:
        a,b,card,cover=m.groups();a=int(a);b=int(b)
        if a==1:
            span=f'aux {ordinal_word(b)} premiers tours' if b>1 else 'au premier tour'
        else:
            span=f'du {ordinal_word(a)} au {ordinal_word(b)} tour'
        return f'Si {card} est intercalé {span}, couvrir avec {cover}.'
    # A single-round cover reads more naturally with "intercale".
    m=re.match(r'^Au (\d+)(?:er|e) tour, si l’adversaire vient de fournir (.+?) : couvrir avec (.+)\.$',s)
    if m:
        rnd,card,cover=m.groups();rnd=int(rnd)
        return f'Au {"premier" if rnd==1 else ordinal_word(rnd)} tour, si l’adversaire intercale {card}, couvrir avec {cover}.'
    return s


def naturalize_why(s:str)->str:
    s=clean_sentence(s)
    s=s.replace('Roi-Valet groupés','Roi-Valet groupés').replace('Roi-Dame groupés','Roi-Dame groupés')
    # Remove process/comparison phrasing when the concrete winning layout is already named.
    m=re.match(r'^Cette ligne permet notamment de profiter (.+?), position que le meilleur départ concurrent ne permet pas d’exploiter de la même façon\.$',s)
    if m:
        pos=m.group(1)
        if pos.startswith('du partage'):
            return 'Cette ligne permet notamment de profiter '+pos+'.'
        if pos.startswith('du Roi'):
            return 'Cette ligne gagne notamment avec '+pos.replace('du Roi','le Roi',1)+'.'
        if pos.startswith('de la Dame'):
            return 'Cette ligne gagne notamment avec '+pos.replace('de la Dame','la Dame',1)+'.'
        if pos.startswith("de l’As"):
            return 'Cette ligne gagne notamment avec '+pos.replace("de l’As","l’As",1)+'.'
        if pos.startswith('de Roi-') or pos.startswith('de Dame-') or pos.startswith('de Valet-'):
            return 'Cette ligne gagne notamment contre '+pos[3:]+'.'
        return 'Cette ligne permet notamment de profiter '+pos+'.'
    return s


def motif_type(lines:list[str])->str:
    t=' '.join(lines)
    if re.search(r'Jouer successivement petit de .* vers .*puis vers',t):
        return 'IMPASSES_PROGRESSIVES'
    if t.startswith('Commencer par tirer') and 'jouer petit' in t.lower():
        return 'COUP_DE_SONDE_PUIS_MANOEUVRE'
    if 'si l’adversaire intercale' in t.lower() and 'vers ' in t:
        return 'IMPASSE_AVEC_COUVERTURE'
    if t.startswith('Commencer par tirer'):
        return 'HONNEURS_EN_TETE'
    if 'jouer petit' in t.lower():
        return 'JEU_VERS_UN_HONNEUR_OU_INTERMEDIAIRE'
    return 'PROCEDURE_CONDITIONNELLE'


def polish(src:dict):
    cases=[];raw_priority=[];counts=Counter()
    for c in src['cases']:
        ps=[]
        for p in c['profiles']:
            z=dict(p);q=dict(p.get('qualification') or {})
            motif=[naturalize_rule(x) for x in (q.get('motif_lines') or p.get('steps') or [])]
            z['steps']=[naturalize_rule(x) for x in p.get('steps',[])]
            z['line']=naturalize_rule(p.get('line',''))
            z['why']=naturalize_why(p.get('why',''))
            q['motif_lines_v54']=motif
            q['motif_type']=motif_type(motif) if motif else None
            z['qualification']=q
            ps.append(z);counts[z['status']]+=1
            if q.get('counted') and z['status']=='RAW_EXACT_ONLY':
                sem=q.get('semantic_compression') or {}
                score=(0 if sem.get('spot_fallback_used') else 100) - 4*len(motif) + min(20,sem.get('irrelevant_pruned',0)//50)
                raw_priority.append({'id':c['id'],'display':c['display'],'target':z['target'],'percent':z['percent'],'priority_score':score,'motif_lines':len(motif),'spot_dependent':bool(sem.get('spot_fallback_used')),'motif_type':q.get('motif_type')})
        cc=dict(c);cc['profiles']=ps;cases.append(cc)
    raw_priority.sort(key=lambda x:(-x['priority_score'],x['id'],x['target']))
    summary=dict(src['summary']);summary['schema']='MANIEMENTS_V5_HUMAN_V54_LANGUAGE_V1';summary['status_counts']=dict(counts);summary['next_priority']=raw_priority[:12]
    return {'summary':summary,'cases':cases,'priority_queue':raw_priority}


def render(data,path:Path):
    s=data['summary'];arts=[]
    for ci,c in enumerate(data['cases']):
        bs=[];panels=[];non=[p for p in c['profiles'] if p.get('qualification',{}).get('counted')];default=non[0]['target'] if non else c['profiles'][-1]['target']
        for p in c['profiles']:
            active=' active' if p['target']==default else '';cls='pass' if p['status']=='HUMAN_TREE_EXACT' else ('trivial' if p['status']=='EXACT_TRIVIAL' else 'raw')
            bs.append(f'<button class="obj {cls}{active}" data-case="{ci}" data-target="{p["target"]}"><b>{p["target"]}</b><span>{p["percent"]}</span></button>')
            hidden='' if p['target']==default else ' hidden';q=p.get('qualification') or {};steps=p.get('steps') or [];proc='<ol>'+''.join('<li>'+html.escape(x)+'</li>' for x in steps)+'</ol>' if steps else '<p>'+html.escape(p['line'])+'</p>';motif=q.get('motif_lines_v54') or [];cand=''
            if p['status']=='RAW_EXACT_ONLY' and motif:cand='<details><summary>Candidat à retravailler — '+html.escape(q.get('motif_type') or '')+'</summary><ol>'+''.join('<li>'+html.escape(x)+'</li>' for x in motif)+'</ol></details>'
            panels.append(f'''<section class="profile" {'hidden' if hidden else ''} data-case="{ci}" data-target="{p['target']}"><div class="top"><b>Objectif {p['target']} — {p['percent']}</b><span class="{cls}">{p['status']}</span></div><div class="box"><small>{html.escape(q.get('motif_type') or '')}</small><h3>Maniement</h3>{proc}<h3>Pourquoi ?</h3><p>{html.escape(p['why'])}</p></div>{cand}</section>''')
        arts.append(f'''<article><header><div class="holding"><span>{c['display'][0]}</span><span>{c['display'][1]}</span></div><b>{c['id']}</b></header><div class="objs">{''.join(bs)}</div>{''.join(panels)}</article>''')
    pr=''.join(f'<li><b>{x["id"]}</b> — objectif {x["target"]} — {x["motif_lines"]} lignes — {html.escape(x["motif_type"] or "")}</li>' for x in data['priority_queue'][:12])
    path.write_text(f'''<!doctype html><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1"><title>V5.4</title><style>body{{background:#0b1016;color:#eef3f8;font:15px/1.5 system-ui;margin:0}}main{{max-width:1050px;margin:25px auto;padding:0 16px 60px}}article{{background:#141c25;border:1px solid #2c3947;border-radius:15px;padding:17px;margin:15px 0}}header{{display:flex;gap:24px;align-items:center}}.holding{{display:grid;justify-items:center;min-width:130px;font:800 26px/1.08 ui-monospace,monospace}}.summary,.box{{background:#0f161e;border-radius:10px;padding:13px}}.objs{{display:flex;gap:7px;flex-wrap:wrap;margin:12px 0}}.obj{{background:#101820;color:#eef3f8;border:1px solid #334354;border-radius:8px;padding:6px 9px}}.obj span{{margin-left:6px}}.obj.active{{border-color:#d5ad3b}}.top{{display:flex;justify-content:space-between}}.pass{{color:#75e3a6}}.raw{{color:#ffcc6b}}.trivial{{color:#9bafc1}}.profile[hidden]{{display:none}}</style><main><h1>V5.4 — langage bridge + file de priorité</h1><div class="summary">Les procédures exactes V5.3 sont reformulées sans vocabulaire de moteur et classées par motif. La file ci-dessous cible d’abord les cas RAW les plus proches d’un maniement humain compact.<ol>{pr}</ol></div>{''.join(arts)}</main><script>document.querySelectorAll('.obj').forEach(b=>b.onclick=()=>{{let c=b.dataset.case,t=b.dataset.target;document.querySelectorAll('.obj[data-case="'+c+'"]').forEach(x=>x.classList.toggle('active',x===b));document.querySelectorAll('.profile[data-case="'+c+'"]').forEach(x=>x.hidden=x.dataset.target!==t)}})</script>''',encoding='utf-8')


def main():
    ap=argparse.ArgumentParser();ap.add_argument('--input',required=True);ap.add_argument('--out-dir',required=True);a=ap.parse_args();src=json.loads(Path(a.input).read_text(encoding='utf-8'));out=polish(src);od=Path(a.out_dir);od.mkdir(parents=True,exist_ok=True);(od/'HUMAN_V54_LANGUAGE.json').write_text(json.dumps(out,ensure_ascii=False,indent=2)+'\n',encoding='utf-8');render(out,od/'MANIEMENTS_V5_HUMAN_V54_LANGUAGE.html');(od/'PRIORITY.json').write_text(json.dumps(out['priority_queue'],ensure_ascii=False,indent=2)+'\n',encoding='utf-8');print(json.dumps(out['summary'],ensure_ascii=False))
if __name__=='__main__':main()

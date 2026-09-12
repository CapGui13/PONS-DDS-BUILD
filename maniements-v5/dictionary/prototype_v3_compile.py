#!/usr/bin/env python3
from __future__ import annotations
import argparse, json
from fractions import Fraction
from pathlib import Path

FR_RANK = {'A':'A','K':'R','Q':'D','J':'V','T':'10','9':'9','8':'8','7':'7','6':'6','5':'5','4':'4','3':'3','2':'2','-':'-'}
FR_SEAT = {'N':'Nord','S':'Sud','E':'Est','W':'Ouest'}
HONORS = 'AKQJT'
RANKS = 'AKQJT98765432'

def fr_rank(r): return FR_RANK.get(r, r)
def rank_noun(r):
    x=fr_rank(r)
    return {'A':"l'As",'R':'le Roi','D':'la Dame','V':'le Valet','10':'le 10'}.get(x,'le '+x)
def article(r): return rank_noun(r)
def with_de(r):
    x=fr_rank(r)
    return {'A':"de l'As",'R':'du Roi','D':'de la Dame','V':'du Valet'}.get(x,'du '+x)
def parse_action(a): return a.split(':',1)
def action_text(a, imperative=False):
    seat,rank=parse_action(a); side=FR_SEAT[seat]; card=rank_noun(rank)
    return f'jouer {card} de {side}' if imperative else f'{card} de {side}'
def probability_value(s): return Fraction(s)
def equivalent_best_actions(report):
    best=probability_value(report['probability_fraction'])
    return [x['action'] for x in report.get('root_action_probabilities',[]) if probability_value(x['probability_fraction'])==best]
def missing_cards(report):
    c=report['case']; visible=set(c['north']+c['south'])
    return [r for r in RANKS if r not in visible]
def fixed_honor_conditions(report):
    worlds=report.get('winning_worlds') or []
    if not worlds:return []
    out=[]
    for r in missing_cards(report):
        if r not in HONORS:continue
        loc=[]; lens=[]
        for w in worlds:
            west=w['west']; east=w['east']
            if r in west:loc.append('W'); lens.append(0 if west=='-' else len(west))
            elif r in east:loc.append('E'); lens.append(0 if east=='-' else len(east))
            else:loc.append('?')
        if len(set(loc))!=1 or loc[0] not in ('W','E'):continue
        seat=loc[0]; mn=min(lens); mx=max(lens); side=FR_SEAT[seat]
        if mn==mx==1:text=f'{article(r)} sec en {side}'
        elif mn==1 and mx==2:text=f'{article(r)} sec ou second en {side}'
        elif mn==mx:text=f'{article(r)} exactement {mn}e en {side}'
        else:text=f'{article(r)} en {side}, au plus {mx}e'
        out.append({'rank':r,'seat':seat,'min_len':mn,'max_len':mx,'text':text})
    return out
def group_first_responses(report):
    groups={}; dseat=None
    for b in report.get('first_defender_branches',[]):
        if not b.get('compatible_success_bits'):continue
        dseat=b['defender']; act=b.get('next_declarer_action') or b.get('terminal_after_defense') or '—'
        groups.setdefault(act,[]).append(b['card'])
    return dseat,groups
def rank_is_higher(a,b): return a in RANKS and b in RANKS and RANKS.index(a)<RANKS.index(b)
def recognize_low_toward_honor(report):
    lead_seat,lead_rank=parse_action(report['root_lead'])
    if lead_rank in HONORS:return None
    dseat,groups=group_first_responses(report)
    if not dseat:return None
    other='N' if lead_seat=='S' else 'S'; c=report['case']; other_hand=set(c['north'] if other=='N' else c['south'])
    ag=[]
    for act,cards in groups.items():
        if ':' not in act:continue
        seat,rank=parse_action(act)
        if seat==other and rank in HONORS and rank in other_hand:ag.append((rank,set(cards)))
    if len(ag)<2:return None
    for cover_response,cover_cards in ag:
        if len(cover_cards)!=1:continue
        cover_card=next(iter(cover_cards))
        if cover_card not in HONORS:continue
        for normal_response,normal_cards in ag:
            if normal_response==cover_response or not normal_cards:continue
            if not rank_is_higher(cover_response,cover_card) or not rank_is_higher(cover_card,normal_response):continue
            lead_txt=f'Jouer petit de {FR_SEAT[lead_seat]} vers {article(normal_response)}.'
            cover_verb=f'prendre {with_de(cover_response)}' if cover_response=='A' else f'couvrir {with_de(cover_response)}'
            branch_txt=f'Si {FR_SEAT[dseat]} fournit {article(cover_card)}, {cover_verb} ; sinon, passer {article(normal_response)}.'
            conds=fixed_honor_conditions(report); hcond=next((x for x in conds if x['rank']==cover_card and x['seat']==dseat),None)
            pieces=[lead_txt,branch_txt]; pattern=f'LOW_TO_{normal_response}_COVER_{cover_card}_WITH_{cover_response}'
            if normal_response=='Q' and cover_card=='K' and cover_response=='A' and hcond and hcond['max_len']<=2:
                pieces.append("Si la Dame fait la levée, tirer ensuite l'As."); pattern='LOW_TO_Q_THEN_A_DROP_K'
            if hcond:pieces.append(f'Condition compacte observée dans les mondes gagnants : {hcond["text"]}.')
            return {'confidence':'HIGH','coverage':'PATTERN','pattern':pattern,'summary_fr':' '.join(pieces),'condition_fr':hcond['text'] if hcond else None}
    return None
def recognize_guaranteed(report):
    if probability_value(report['probability_fraction'])!=1:return None
    target=report['case']['target']; roots=equivalent_best_actions(report); lead=report['root_lead']
    summary=f"L’objectif de {target} levées est garanti quelle que soit la répartition. Le moteur peut commencer par {action_text(lead)}."
    if len(roots)>1:summary+=f' {len(roots)} premiers coups sont équivalents à 100 % dans le calcul exact.'
    return {'confidence':'HIGH','coverage':'FULL_TARGET','pattern':'GUARANTEED_TARGET','summary_fr':summary,'condition_fr':'Toujours'}
def recognize_honor_start(report):
    lead_seat,lead_rank=parse_action(report['root_lead'])
    if lead_rank not in HONORS:return None
    roots=equivalent_best_actions(report); summary=f'Commencer par {article(lead_rank)} de {FR_SEAT[lead_seat]}.'
    alts=[a for a in roots if a!=report['root_lead']]
    if alts:
        rendered=[]; seen=set()
        for a in alts:
            seat,rank=parse_action(a); key=(seat,'H' if rank in HONORS else 'L')
            if key in seen:continue
            seen.add(key); rendered.append(action_text(a))
        if rendered:summary+=' Le calcul exact donne la même probabilité avec '+' ou '.join(rendered)+' en premier coup.'
    conds=fixed_honor_conditions(report)
    if conds:summary+=' Condition compacte observée : '+' ; '.join(x['text'] for x in conds)+'.'
    return {'confidence':'MEDIUM','coverage':'OPENING_ONLY','pattern':'HONOR_START_OPTIMAL','summary_fr':summary,'condition_fr':' ; '.join(x['text'] for x in conds) if conds else None}
def bridge_plan(report):
    for recognizer in (recognize_guaranteed,recognize_low_toward_honor,recognize_honor_start):
        plan=recognizer(report)
        if plan:return plan
    lead_seat,lead_rank=parse_action(report['root_lead'])
    summary=f'Commencer par {article(lead_rank)} de {FR_SEAT[lead_seat]}.' if lead_rank in HONORS else f'Commencer par petit de {FR_SEAT[lead_seat]}.'
    conds=fixed_honor_conditions(report)
    if conds:summary+=' Condition de réussite compacte : '+' ; '.join(x['text'] for x in conds)+'.'
    return {'confidence':'LOW','coverage':'OPENING_ONLY','pattern':'GENERIC_SAFE_FALLBACK','summary_fr':summary,'condition_fr':' ; '.join(x['text'] for x in conds) if conds else None}

def negate_condition(text):
    replacements=((' a déjà fourni '," n'a pas encore fourni "),(' a déjà montré une chicane dans la couleur'," n'a pas encore montré de chicane dans la couleur"),(' fournit ',' ne fournit pas '),(' défausse sur ce tour',' ne défausse pas sur ce tour'))
    for old,new in replacements:
        if old in text:return text.replace(old,new,1)
    return 'non ('+text+')'
def condition_clause(c): return c['condition'] if c['value'] else negate_condition(c['condition'])
def context_text(ctx,case):
    if ctx['north_remaining']==case['north'] and ctx['south_remaining']==case['south'] and ctx['won']==0 and ctx['pos']==0 and not ctx['trick_shape']:return 'Au départ'
    n=ctx['north_remaining']; s=ctx['south_remaining']; won=ctx['won']
    base=f'Quand il reste {n} en Nord et {s} en Sud, avec {won} levée'+(' gagnée' if won==1 else 's gagnées')
    if ctx['trick_shape']:
        shown=[]
        for t in ctx['trick_shape']:
            shown.append(f"{FR_SEAT[t['seat']]} {rank_noun(t['card'])}" if t['card']!='*' else f"{FR_SEAT[t['seat']]} une carte observée")
        base+=', dans le pli en cours : '+', '.join(shown)
    return base
def render_policy_program(program):
    case=program['case']; rendered=[]
    for item in program['contexts']:
        ctx_fr=context_text(item['context'],case)
        if 'unconditional_action' in item:rendered.append({'context_fr':ctx_fr,'instruction_fr':action_text(item['unconditional_action'],imperative=True)+'.','exact':True})
        else:
            rules=[]
            for rule in item.get('rules',[]):
                if 'error' in rule:raise ValueError('policy program contains an unseparable rule')
                clauses=[condition_clause(c) for c in rule['conditions']]; prefix='Si '+', et '.join(clauses)+', ' if clauses else ''
                rules.append(prefix+action_text(rule['action'],imperative=True)+'.')
            rendered.append({'context_fr':ctx_fr,'rules_fr':rules,'exact':True})
    return rendered
def initial_policy_action(program):
    c=program['case']
    for item in program['contexts']:
        ctx=item['context']
        if ctx['north_remaining']==c['north'] and ctx['south_remaining']==c['south'] and ctx['won']==0 and ctx['pos']==0 and not ctx['trick_shape']:
            if 'unconditional_action' not in item:raise ValueError('initial policy context is unexpectedly conditional')
            return item['unconditional_action']
    raise ValueError('initial policy context not found')
def compile_policy_program(program,report=None):
    stats=program.get('program_stats') or {}
    if stats.get('unseparable_contexts',0)!=0:raise ValueError('policy program is not exact: unseparable contexts remain')
    case=program['case']; prob=program['probability_fraction']
    if report is not None:
        if report.get('case')!=case:raise ValueError('report/policy case mismatch')
        if Fraction(report['probability_fraction'])!=Fraction(prob):raise ValueError('report/policy probability mismatch')
    root=initial_policy_action(program); rendered=render_policy_program(program)
    summary=(f'Commencer par {action_text(root)}. La suite optimale dépend ensuite des cartes fournies par la défense ; elle est couverte exactement par {program["context_count"]} contextes de décision, dont {program["conditional_context_count"]} conditionnels, sans ambiguïté.')
    return {'schema':'MANIEMENTS_V5_DICTIONARY_V3_COMPILED_PLAN_PROTOTYPE_V3','case':case,'probability_fraction':prob,'root_lead':root,'equivalent_root_actions':[root],'winning_world_count':None,'fixed_honor_conditions':[],'confidence':'HIGH','coverage':'EXACT_POLICY_PROGRAM','pattern':'NATIVE_POLICY_PROGRAM_EXACT','summary_fr':summary,'condition_fr':'Politique exacte conditionnée par les cartes observées de la défense.','policy_program_stats':stats,'decision_program_fr':rendered,'policy_program':program}
def compile_report(report):
    plan=bridge_plan(report)
    return {'schema':'MANIEMENTS_V5_DICTIONARY_V3_COMPILED_PLAN_PROTOTYPE_V3','case':report['case'],'probability_fraction':report['probability_fraction'],'root_lead':report['root_lead'],'equivalent_root_actions':equivalent_best_actions(report),'winning_world_count':len(report.get('winning_worlds') or []),'fixed_honor_conditions':fixed_honor_conditions(report),**plan}
def main():
    ap=argparse.ArgumentParser(); ap.add_argument('report',nargs='?'); ap.add_argument('--policy-program'); ap.add_argument('--output'); a=ap.parse_args()
    if not a.report and not a.policy_program:ap.error('provide a report and/or --policy-program')
    report=json.loads(Path(a.report).read_text(encoding='utf-8')) if a.report else None
    if a.policy_program:out=compile_policy_program(json.loads(Path(a.policy_program).read_text(encoding='utf-8')),report)
    else:out=compile_report(report)
    text=json.dumps(out,ensure_ascii=False,indent=2,sort_keys=True)
    if a.output:Path(a.output).write_text(text+'\n',encoding='utf-8')
    print(text)
if __name__=='__main__':main()

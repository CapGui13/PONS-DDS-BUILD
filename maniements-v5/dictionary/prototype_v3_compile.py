#!/usr/bin/env python3
from __future__ import annotations
import argparse, json
from pathlib import Path

FR_RANK = {'A':'A','K':'R','Q':'D','J':'V','T':'X','9':'9','8':'8','7':'7','6':'6','5':'5','4':'4','3':'3','2':'2','-':'-'}
FR_SEAT = {'N':'Nord','S':'Sud','E':'Est','W':'Ouest'}
HONORS = 'AKQJT'


def fr_rank(r):
    return FR_RANK.get(r, r)


def article(r):
    x = fr_rank(r)
    if x == 'A': return "l'As"
    if x == 'D': return 'la Dame'
    if x == 'V': return 'le Valet'
    if x == 'R': return 'le Roi'
    if x == 'X': return 'le X'
    return 'le ' + x


def parse_action(a):
    seat, rank = a.split(':', 1)
    return seat, rank


def missing_cards(report):
    c = report['case']
    visible = set(c['north'] + c['south'])
    return [r for r in 'AKQJT98765432' if r not in visible]


def fixed_honor_conditions(report):
    worlds = report.get('winning_worlds') or []
    if not worlds:
        return []
    out=[]
    for r in missing_cards(report):
        if r not in HONORS:
            continue
        loc=[]
        lens=[]
        for w in worlds:
            west=w['west']; east=w['east']
            if r in west:
                loc.append('W'); lens.append(0 if west == '-' else len(west))
            elif r in east:
                loc.append('E'); lens.append(0 if east == '-' else len(east))
            else:
                loc.append('?')
        if len(set(loc)) != 1 or loc[0] not in ('W','E'):
            continue
        seat=loc[0]
        mn=min(lens); mx=max(lens)
        rank=fr_rank(r)
        side=FR_SEAT[seat]
        if mn == mx == 1:
            text=f'{article(r)} sec en {side}'
        elif mn == 1 and mx == 2:
            text=f'{article(r)} sec ou second en {side}'
        elif mn == mx:
            text=f'{article(r)} exactement {mn}e en {side}'
        else:
            text=f'{article(r)} en {side}, au plus {mx}e'
        out.append({'rank':r,'seat':seat,'min_len':mn,'max_len':mx,'text':text})
    return out


def group_first_responses(report):
    groups={}
    dseat=None
    for b in report.get('first_defender_branches', []):
        if not b.get('compatible_success_bits'):
            continue
        dseat=b['defender']
        act=b.get('next_declarer_action') or b.get('terminal_after_defense') or '—'
        groups.setdefault(act, []).append(b['card'])
    return dseat, groups


def bridge_plan(report):
    lead_seat, lead_rank = parse_action(report['root_lead'])
    dseat, groups = group_first_responses(report)
    c=report['case']
    north=set(c['north']); south=set(c['south'])
    other = 'N' if lead_seat == 'S' else 'S'
    other_hand = north if other == 'N' else south
    lead_is_low = lead_rank not in HONORS

    # Recognize the common finesse pattern: low towards Q/A, with K requiring A.
    q_act=f'{other}:Q'; a_act=f'{other}:A'
    if lead_is_low and q_act in groups and a_act in groups and 'Q' in other_hand and 'A' in other_hand and dseat:
        king_cards=set(groups[a_act])
        if king_cards == {'K'}:
            lead_txt=f'Jouer petit de {FR_SEAT[lead_seat]} vers la Dame.'
            first_txt=f'Si {FR_SEAT[dseat]} fournit le Roi, prendre de l\'As ; sinon, passer la Dame.'
            conds=fixed_honor_conditions(report)
            kcond=next((x for x in conds if x['rank']=='K'), None)
            if kcond and kcond['seat']==dseat and kcond['max_len'] <= 2:
                follow='Si la Dame fait la levée, tirer ensuite l\'As.'
                success=f'Le maniement réussit lorsque {kcond["text"]}.'
                return {
                    'confidence':'HIGH',
                    'pattern':'LOW_TO_Q_THEN_A_DROP_K',
                    'summary_fr':' '.join([lead_txt, first_txt, follow, success]),
                    'condition_fr':kcond['text'],
                }
            return {
                'confidence':'MEDIUM',
                'pattern':'LOW_TO_Q_WITH_K_COVER',
                'summary_fr':' '.join([lead_txt, first_txt]),
                'condition_fr':None,
            }

    # Conservative generic fallback: say only what is safely inferred.
    lead_desc = article(lead_rank) if lead_rank in HONORS else f'petit de {FR_SEAT[lead_seat]}'
    if lead_rank in HONORS:
        summary=f'Commencer par {lead_desc} de {FR_SEAT[lead_seat]}.'
    else:
        summary=f'Commencer par {lead_desc}.'
    conds=fixed_honor_conditions(report)
    if conds:
        summary += ' Condition de réussite compacte : ' + ' ; '.join(x['text'] for x in conds) + '.'
    return {
        'confidence':'LOW',
        'pattern':'GENERIC_SAFE_FALLBACK',
        'summary_fr':summary,
        'condition_fr':' ; '.join(x['text'] for x in conds) if conds else None,
    }


def main():
    ap=argparse.ArgumentParser()
    ap.add_argument('report')
    ap.add_argument('--output')
    a=ap.parse_args()
    report=json.loads(Path(a.report).read_text(encoding='utf-8'))
    plan=bridge_plan(report)
    out={
        'schema':'MANIEMENTS_V5_DICTIONARY_V3_COMPILED_PLAN_PROTOTYPE_V1',
        'case':report['case'],
        'probability_fraction':report['probability_fraction'],
        'root_lead':report['root_lead'],
        'winning_world_count':len(report.get('winning_worlds') or []),
        'fixed_honor_conditions':fixed_honor_conditions(report),
        **plan,
    }
    text=json.dumps(out,ensure_ascii=False,indent=2,sort_keys=True)
    if a.output:
        Path(a.output).write_text(text+'\n',encoding='utf-8')
    print(text)

if __name__=='__main__':
    main()

#!/usr/bin/env python3
from __future__ import annotations

import argparse, html, json, sys
from fractions import Fraction
from pathlib import Path

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))
import human_novel_v48 as v48

v47 = v48.v47
v46 = v48.v46
v45 = v48.v45
b = v48.b
TR = v48.TR

# Same 10 genuinely novel holdings reviewed in V4.8.2, but now the holding is
# the primary entry and every attainable trick objective is computed separately.
HOLDINGS = [
    ('N25', 'AQ854', 'T32'),
    ('N12', 'AQT84', '632'),
    ('N21', 'A9854', 'K32'),
    ('N22', 'K9854', 'A32'),
    ('N16', 'AQJ84', '632'),
    ('N24', 'AJ854', 'K32'),
    ('N26', 'KQ854', 'J32'),
    ('N23', 'QJ854', 'A32'),
    ('N15', 'KQ984', 'J32'),
    ('N13', 'AJ984', 'Q32'),
]


def disp(h: str) -> str:
    return ''.join(TR.get(c, c) for c in h)


def pct(f: Fraction) -> str:
    return f"{float(f) * 100:.2f}".replace('.', ',') + ' %'


def profile_for_target(eng, north: str, south: str, target: int):
    e = eng.Engine2(north, south, target)
    v45._ENG = eng
    v45._E = e
    solved = e.solve(include_policy=False)
    opt = Fraction(solved['probability_fraction'])

    base = {
        'target': target,
        'fraction': str(opt),
        'percent': pct(opt),
        'probability_decimal': float(opt),
    }

    if opt == 0:
        return {
            **base,
            'status': 'IMPOSSIBLE',
            'opening': 'Objectif impossible avec cette combinaison.',
            'critical': [],
            'why': 'Aucune position adverse ne permet d’atteindre cet objectif.',
            'decision_count': 0,
            'def_nodes': 0,
            'diag': {},
        }

    root = e.initial()
    fr = e.frontier(root)
    best = max(fr, key=lambda m: (e.model.weight(m), m))
    assert e.model.weight(best) == opt
    row, opening = v47.choose_root(eng, e, best)

    if opt == 1:
        return {
            **base,
            'status': 'EXACT',
            'opening': opening,
            'critical': [],
            'why': 'Cet objectif peut être assuré à 100 %. Le maniement affiché est un des maniements exacts qui le garantit.',
            'decision_count': 0,
            'def_nodes': 0,
            'diag': {'root': [row['seat'], row['rank']]},
        }

    alt = v48.alt_root(eng, e, root, row)
    decisions = []
    raw = []
    tree = v45.explore(eng, e, root, best, decisions, raw, {})
    tree = v46.collapse(tree)
    crit, total_def = v47.critical_nodes(tree, root, limit=3)
    why, diag = v48.why_auto(eng, e, row, alt)

    return {
        **base,
        'status': 'EXACT_AUTO_NON_RELU',
        'opening': opening,
        'critical': v48.critical_lines(crit),
        'why': why,
        'decision_count': len(decisions),
        'def_nodes': total_def,
        'diag': diag,
    }


def html_report(cases, path: Path):
    cards = []
    for ci, case in enumerate(cases):
        buttons = []
        panels = []
        # Default to the 4-trick objective when available, to preserve V4.8 comparison.
        default_target = 4 if any(p['target'] == 4 for p in case['profiles']) else max(p['target'] for p in case['profiles'])
        for p in case['profiles']:
            active = ' active' if p['target'] == default_target else ''
            buttons.append(
                f'<button class="obj{active}" data-case="{ci}" data-target="{p["target"]}">'
                f'<b>{p["target"]}</b><span>{html.escape(p["percent"])}</span></button>'
            )
            cond = ''.join('<li>' + html.escape(x) + '</li>' for x in p['critical'])
            if not cond and p['status'] not in ('IMPOSSIBLE',):
                cond = '<li>Aucune adaptation précoce distincte à afficher.</li>'
            hidden = '' if p['target'] == default_target else ' hidden'
            panels.append(f'''<section class="profile{hidden}" data-case="{ci}" data-target="{p['target']}">
<div class="profiletop"><div><b>Objectif : {p['target']} levée{'s' if p['target'] > 1 else ''}</b><div class="p">{html.escape(p['percent'])}</div><small>{html.escape(p['fraction'])}</small></div><strong>{html.escape(p['status'])}</strong></div>
<div class="box"><h3>Maniement généré</h3><p class="line">{html.escape(p['opening'])}</p>{('<ul>'+cond+'</ul>') if cond else ''}<h3>Pourquoi ?</h3><p>{html.escape(p['why'])}</p></div>
<details><summary>Contrôle exact</summary><p>{p['decision_count']} décisions déclarant analysées — {p['def_nodes']} nœuds défense.</p><pre>{html.escape(json.dumps(p['diag'], ensure_ascii=False, indent=2))}</pre></details>
</section>''')
        cards.append(f'''<article><header><div class="holding"><span>{html.escape(case['display'][0])}</span><span>{html.escape(case['display'][1])}</span></div><div><h2>{html.escape(case['id'])}</h2><p>Choisir le nombre de levées recherché.</p></div><strong>NOUVEAU — AUTO, NON RELU</strong></header><div class="objectives">{''.join(buttons)}</div>{''.join(panels)}</article>''')

    path.write_text(f'''<!doctype html><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1"><title>MANIEMENTS V5 — V4.9 multi-objectifs</title>
<style>
body{{margin:0;background:#0b1016;color:#eef3f8;font:15px/1.5 system-ui}}main{{max-width:1040px;margin:28px auto;padding:0 16px 60px}}h1{{margin-bottom:4px}}.intro{{color:#aebcca;margin-top:0;max-width:900px}}article{{background:#141c25;border:1px solid #2c3947;border-radius:16px;padding:18px;margin:18px 0}}header{{display:grid;grid-template-columns:160px 1fr auto;gap:18px;align-items:center}}header h2{{margin:0;font-size:14px;color:#91a6b9}}header p{{margin:3px 0;color:#aebcca}}.holding{{display:grid;justify-items:center;width:max-content;min-width:120px;font:800 26px/1.08 ui-monospace,monospace}}strong{{font-size:11px;color:#ffdb78}}.objectives{{display:flex;flex-wrap:wrap;gap:8px;margin:16px 0 10px}}.obj{{border:1px solid #334354;background:#0f161e;color:#eef3f8;border-radius:10px;padding:7px 11px;cursor:pointer;display:flex;gap:8px;align-items:baseline}}.obj span{{font-size:12px;color:#aebcca}}.obj.active{{border-color:#d5ad3b;box-shadow:0 0 0 1px #d5ad3b inset}}.obj.active span{{color:#71daa0}}.profile[hidden]{{display:none}}.profiletop{{display:flex;justify-content:space-between;gap:12px;align-items:center}}.p{{font-size:24px;color:#71daa0;font-weight:800}}.box{{background:#0f161e;border-radius:11px;padding:14px 16px;margin-top:10px}}.box h3{{margin:6px 0 3px}}.line{{font-weight:700;font-size:16px}}details{{margin-top:12px}}summary{{cursor:pointer;color:#b7cbe0}}pre{{white-space:pre-wrap;color:#aebcca}}@media(max-width:700px){{header{{grid-template-columns:1fr}}}}
</style>
<main><h1>V4.9 — mêmes 10 combinaisons, objectifs séparés</h1><p class="intro">Une combinaison n’a plus un seul « objectif choisi par le générateur ». Chaque nombre de levées possible est calculé séparément, avec sa probabilité exacte et son propre maniement. Le maniement optimal peut donc changer lorsque l’objectif change.</p>{''.join(cards)}</main>
<script>
document.querySelectorAll('.obj').forEach(btn=>btn.addEventListener('click',()=>{{
 const c=btn.dataset.case,t=btn.dataset.target;
 document.querySelectorAll('.obj[data-case="'+c+'"]').forEach(x=>x.classList.toggle('active',x===btn));
 document.querySelectorAll('.profile[data-case="'+c+'"]').forEach(x=>x.hidden=x.dataset.target!==t);
}}));
</script>''', encoding='utf-8')


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument('--runtime-root', required=True)
    ap.add_argument('--out-dir', required=True)
    a = ap.parse_args()

    sys.path.insert(0, str(Path(a.runtime_root) / 'runtime'))
    import integrated_engine as eng

    cases = []
    for cid, north, south in HOLDINGS:
        max_target = max(len(north), len(south))
        profiles = []
        for target in range(1, max_target + 1):
            p = profile_for_target(eng, north, south, target)
            profiles.append(p)
            print(json.dumps({'case': cid, 'target': target, 'p': p['fraction'], 'opening': p['opening']}, ensure_ascii=False), flush=True)
        cases.append({'id': cid, 'display': [disp(north), disp(south)], 'north': north, 'south': south, 'profiles': profiles})

    out = Path(a.out_dir)
    out.mkdir(parents=True, exist_ok=True)
    payload = {
        'schema': 'MANIEMENTS_V5_HUMAN_V49_MULTI_TARGET_V1',
        'holding_centric': True,
        'target_is_first_class_dimension': True,
        'human_reference_answers_used': False,
        'cases': cases,
    }
    (out / 'HUMAN_V49_MULTI_TARGET.json').write_text(json.dumps(payload, ensure_ascii=False, indent=2) + '\n', encoding='utf-8')
    html_report(cases, out / 'MANIEMENTS_V5_HUMAN_V49_MULTI_TARGET.html')
    print(json.dumps({'status': 'OK', 'holdings': len(cases), 'profiles': sum(len(c['profiles']) for c in cases)}, ensure_ascii=False), flush=True)


if __name__ == '__main__':
    main()

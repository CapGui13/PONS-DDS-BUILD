#!/usr/bin/env python3
from __future__ import annotations

import argparse
import html
import json
import re
import sys
from collections import Counter
from fractions import Fraction
from pathlib import Path

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))

import human_novel_v48 as v48

v47 = v48.v47
v46 = v48.v46
v45 = v48.v45
b = v48.b

TR = {'K': 'R', 'Q': 'D', 'J': 'V', 'T': 'X'}
FR_BACK = str.maketrans({'R': 'K', 'D': 'Q', 'V': 'J', 'X': 'T'})

# Qualification pool deliberately excludes the reviewed corpus and all V4.8/V4.9
# review holdings. It mixes 5-3, 4-4 and 6-2 suit lengths.
HOLDINGS = [
    ('Q01', 'AQT93', '642'),
    ('Q02', 'AJT93', '642'),
    ('Q03', 'KQT93', 'A42'),
    ('Q04', 'KJT93', 'A42'),
    ('Q05', 'AQJ93', '642'),
    ('Q06', 'AKT93', '642'),
    ('Q07', 'AQ983', 'J42'),
    ('Q08', 'AJ983', 'Q42'),
    ('Q09', 'KQ983', 'J42'),
    ('Q10', 'QJ983', 'A42'),
    ('Q11', 'AQT9', '8642'),
    ('Q12', 'AJT9', 'Q642'),
    ('Q13', 'KQT9', 'A642'),
    ('Q14', 'AQJ9', '8642'),
    ('Q15', 'KJ98', 'A642'),
    ('Q16', 'AQT983', '42'),
    ('Q17', 'AJT983', 'Q2'),
    ('Q18', 'KQT983', 'A2'),
    ('Q19', 'AQJ983', '42'),
    ('Q20', 'KJ9874', 'A2'),
]

PREVIOUS_REVIEW_HOLDINGS = {
    ('AQT84', '632'), ('AJ984', 'Q32'), ('KJT84', 'A32'), ('KQ984', 'J32'),
    ('AQJ84', '632'), ('AK984', 'Q32'), ('A9854', 'K32'), ('K9854', 'A32'),
    ('QJ854', 'A32'), ('AJ854', 'K32'), ('AQ854', 'T32'), ('KQ854', 'J32'),
}

BAD_VISIBLE_TOKENS = (
    'politique', 'contexte de décision', 'automate', 'witness', 'masque',
    'north', 'south', 'east', 'west', 'N:', 'S:', 'E:', 'W:'
)


def disp(h: str) -> str:
    return ''.join(TR.get(c, c) for c in h)


def pct(f: Fraction) -> str:
    return f"{float(f) * 100:.2f}".replace('.', ',') + ' %'


def canonical_pair(a: str, c: str):
    return min((a, c), (c, a))


def known_reference_holdings(path: str):
    data = json.loads(Path(path).read_text(encoding='utf-8'))
    out = set()
    for r in data['cases']:
        a = r['north_fr'].translate(FR_BACK)
        c = r['south_fr'].translate(FR_BACK)
        # Wildcard reference families are not exact concrete holdings.
        if 'x' in a.lower() or 'x' in c.lower():
            continue
        out.add(canonical_pair(a, c))
    return out


def assert_novel(reference_path: str):
    known = known_reference_holdings(reference_path)
    previous = {canonical_pair(a, c) for a, c in PREVIOUS_REVIEW_HOLDINGS}
    seen = set()
    for cid, north, south in HOLDINGS:
        k = canonical_pair(north, south)
        if k in known:
            raise AssertionError(f'{cid} is already in the reviewed reference corpus: {north}/{south}')
        if k in previous:
            raise AssertionError(f'{cid} was already used in V4.8/V4.9: {north}/{south}')
        if k in seen:
            raise AssertionError(f'duplicate qualification holding: {north}/{south}')
        seen.add(k)


def rank_to_int(eng, rank: str):
    return eng.VOID if rank == '-' else eng.R2I[rank]


def audit_exact_tree(eng, e, root_node, exact_mask: int):
    """Replay every action/defender branch of the generated raw human tree.

    The tree is allowed to omit branches outside exact_mask: those are worlds where
    the target is already outside the optimal success set. Within exact_mask every
    legal defender continuation must be represented and every declarer action is
    replayed to the exact stored public state.
    """
    errors = []
    seen = set()

    if root_node.mask != exact_mask:
        errors.append('root mask differs from exact optimum')

    def walk(n):
        key = id(n)
        if key in seen:
            return
        seen.add(key)
        s = n.state
        term = e.terminal(s)

        if n.kind == 'T':
            if term is None:
                errors.append('terminal node is not terminal when replayed')
            if n.mask and n.terminal != 'SUCCESS':
                errors.append('non-empty exact-success mask labelled non-success')
            return

        if term is not None:
            errors.append('non-terminal human-tree node is terminal in engine')
            return

        if n.kind == 'D':
            seat, rank = n.action
            r = rank_to_int(eng, rank)
            if s.pos == 0:
                hand = s.north if seat == 'N' else s.south
                if r not in eng.ranks(hand):
                    errors.append(f'illegal declarer lead {seat}:{rank}')
                    return
                lead = eng.PublicState(
                    s.north, s.south, s.west_seen, s.east_seen,
                    s.west_void, s.east_void, seat, 0, tuple(), s.won
                )
                ns = e.close(e.decl_play(lead, seat, r))
            else:
                expected = e.order(s.leader)[s.pos]
                if expected != seat:
                    errors.append(f'declarer seat mismatch: expected {expected}, got {seat}')
                    return
                hand = s.north if seat == 'N' else s.south
                legal = eng.ranks(hand) if hand else (eng.VOID,)
                if r not in legal:
                    errors.append(f'illegal declarer play {seat}:{rank}')
                    return
                ns = e.close(e.decl_play(s, seat, r))

            if not n.branches or len(n.branches) != 1:
                errors.append('declarer node does not have exactly one continuation')
                return
            ch = n.branches[0]
            if v45.state_id(ns) != v45.state_id(ch.state):
                errors.append(f'declarer replay state mismatch after {seat}:{rank}')
            if ch.mask != n.mask:
                errors.append('declarer continuation changed required exact-success mask')
            walk(ch)
            return

        if n.kind == 'F':
            seat = e.order(s.leader)[s.pos]
            if seat in eng.DECL:
                errors.append('defender node points to declarer seat')
                return
            legal_rows = {('-' if not r else eng.I2R[r]): (r, legal) for r, legal in e.defender_actions(s, seat)}
            union = 0
            for card, ch in n.branches or []:
                if isinstance(card, (tuple, list)):
                    errors.append('raw replay unexpectedly received grouped defender cards')
                    continue
                if card not in legal_rows:
                    errors.append(f'illegal defender card in tree: {seat}:{card}')
                    continue
                r, legal = legal_rows[card]
                need = n.mask & legal
                if not need:
                    errors.append(f'defender branch {seat}:{card} has empty required mask')
                    continue
                ns = e.close(e.def_play(s, seat, r))
                union |= need
                if ch.mask != need:
                    errors.append(f'defender branch mask mismatch after {seat}:{card}')
                if v45.state_id(ns) != v45.state_id(ch.state):
                    errors.append(f'defender replay state mismatch after {seat}:{card}')
                walk(ch)
            if union != n.mask:
                errors.append('defender branches do not cover the full exact-success mask')
            return

        errors.append(f'unknown tree kind {n.kind}')

    walk(root_node)
    return {
        'ok': not errors,
        'errors': errors[:20],
        'nodes_replayed': len(seen),
        'root_mask_matches_exact': root_node.mask == exact_mask,
    }


def compactness(steps):
    text = '\n'.join(steps)
    return {
        'lines': len(steps),
        'chars': len(text),
        'ellipsis': '…' in text,
        'compact': bool(steps) and len(steps) <= 8 and len(text) <= 900 and '…' not in text,
    }


def visible_language_safe(steps, why):
    text = ('\n'.join(steps) + '\n' + why).lower()
    return not any(tok.lower() in text for tok in BAD_VISIBLE_TOKENS)


def clean_why(why: str):
    # Keep the bridge reason, remove the internal comparison statistic from the
    # normal qualification card. Exact diagnostics stay available in metadata.
    why = re.sub(r'\s*Différentiel exact\s*:\s*[^.]+\.', '', why)
    return why.strip()


def build_profile(eng, north: str, south: str, target: int):
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
            'status': 'EXACT_TRIVIAL',
            'line': 'Objectif impossible avec cette combinaison.',
            'steps': [],
            'why': 'Aucune position adverse ne permet d’atteindre cet objectif.',
            'qualification': {'counted': False, 'reason': 'probability_zero'},
        }

    root = e.initial()
    frontier = e.frontier(root)
    best = max(frontier, key=lambda m: (e.model.weight(m), m))
    if e.model.weight(best) != opt:
        raise AssertionError('frontier optimum differs from solver probability')

    row, opening = v47.choose_root(eng, e, best)
    decisions = []
    raw_rows = []
    raw_tree = v45.explore(eng, e, root, best, decisions, raw_rows, {})
    audit = audit_exact_tree(eng, e, raw_tree, best)

    collapsed = v46.collapse(raw_tree)
    # Full, untruncated human procedure; qualification decides whether it is
    # compact enough for the normal dictionary view.
    steps = v45.render_tree(collapsed, max_depth=99)
    comp = compactness(steps)
    why_raw, why_decision = v45.why_from_decisions(eng, e, decisions)
    why = clean_why(why_raw)

    features = []
    if why_decision:
        features = list(dict.fromkeys((why_decision.get('gain_features') or []) + (why_decision.get('loss_features') or [])))
    why_specific = bool(features)
    language_safe = visible_language_safe(steps, why)

    if opt == 1:
        status = 'EXACT_TRIVIAL'
        counted = False
        fail_reasons = []
    else:
        fail_reasons = []
        if not audit['ok']:
            fail_reasons.append('exact_replay_failed')
        if not comp['compact']:
            fail_reasons.append('procedure_too_complex')
        if not why_specific:
            fail_reasons.append('why_not_layout_specific')
        if not language_safe:
            fail_reasons.append('visible_language_not_clean')
        status = 'HUMAN_TREE_EXACT' if not fail_reasons else 'RAW_EXACT_ONLY'
        counted = True

    line = steps[0] if steps else opening
    if status == 'RAW_EXACT_ONLY':
        line = 'Calcul exact disponible — maniement humain en cours de certification.'

    return {
        **base,
        'status': status,
        'line': line,
        'steps': steps if status == 'HUMAN_TREE_EXACT' else [],
        'why': why if status == 'HUMAN_TREE_EXACT' else 'Le calcul exact est disponible, mais la procédure humaine ou son explication n’a pas encore franchi le seuil de qualification.',
        'qualification': {
            'counted': counted,
            'fail_reasons': fail_reasons,
            'exact_replay': audit,
            'compactness': comp,
            'why_specific': why_specific,
            'layout_features': features,
            'visible_language_safe': language_safe,
            'auto_opening': opening,
            'generated_why_raw': why_raw,
            'decision_count': len(decisions),
        },
    }


def render_html(cases, summary, out_path: Path):
    cards = []
    for ci, case in enumerate(cases):
        buttons = []
        panels = []
        nontrivial = [p for p in case['profiles'] if p['qualification']['counted']]
        default_target = nontrivial[0]['target'] if nontrivial else case['profiles'][-1]['target']

        for p in case['profiles']:
            active = ' active' if p['target'] == default_target else ''
            cls = 'pass' if p['status'] == 'HUMAN_TREE_EXACT' else ('trivial' if p['status'] == 'EXACT_TRIVIAL' else 'raw')
            buttons.append(
                f'<button class="obj {cls}{active}" data-case="{ci}" data-target="{p["target"]}">'
                f'<b>{p["target"]}</b><span>{html.escape(p["percent"])}</span></button>'
            )
            hidden = '' if p['target'] == default_target else ' hidden'
            if p['steps']:
                procedure = '<ol>' + ''.join('<li>' + html.escape(x) + '</li>' for x in p['steps']) + '</ol>'
            else:
                procedure = '<p class="line">' + html.escape(p['line']) + '</p>'
            q = p['qualification']
            fails = ', '.join(q.get('fail_reasons') or []) or '—'
            panels.append(f'''<section class="profile{hidden}" data-case="{ci}" data-target="{p['target']}">
<div class="profiletop"><div><b>Objectif : {p['target']} levée{'s' if p['target'] > 1 else ''}</b><div class="prob">{html.escape(p['percent'])}</div><small>{html.escape(p['fraction'])}</small></div><span class="badge {cls}">{html.escape(p['status'])}</span></div>
<div class="box"><h3>Maniement</h3>{procedure}<h3>Pourquoi ?</h3><p>{html.escape(p['why'])}</p></div>
<details><summary>Diagnostic de qualification</summary><pre>{html.escape(json.dumps(q, ensure_ascii=False, indent=2))}</pre><p><b>Échec(s) :</b> {html.escape(fails)}</p></details>
</section>''')

        cards.append(f'''<article><header><div class="holding"><span>{html.escape(case['display'][0])}</span><span>{html.escape(case['display'][1])}</span></div><div><h2>{html.escape(case['id'])}</h2><p>20 combinaisons inédites — tous les objectifs calculés séparément.</p></div></header><div class="objectives">{''.join(buttons)}</div>{''.join(panels)}</article>''')

    rate = summary['qualification_rate_percent'].replace('.', ',')
    doc = f'''<!doctype html><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1"><title>MANIEMENTS V5 — Qualification V5.0</title>
<style>
body{{margin:0;background:#0b1016;color:#eef3f8;font:15px/1.5 system-ui}}main{{max-width:1060px;margin:28px auto;padding:0 16px 60px}}h1{{margin-bottom:4px}}.intro{{color:#aebcca;margin-top:0;max-width:930px}}.summary{{display:grid;grid-template-columns:repeat(4,1fr);gap:10px;margin:18px 0}}.stat{{background:#141c25;border:1px solid #2c3947;border-radius:12px;padding:12px}}.stat b{{display:block;font-size:22px}}article{{background:#141c25;border:1px solid #2c3947;border-radius:16px;padding:18px;margin:18px 0}}header{{display:grid;grid-template-columns:160px 1fr;gap:18px;align-items:center}}header h2{{margin:0;font-size:14px;color:#91a6b9}}header p{{margin:3px 0;color:#aebcca}}.holding{{display:grid;justify-items:center;width:max-content;min-width:120px;font:800 26px/1.08 ui-monospace,monospace}}.objectives{{display:flex;flex-wrap:wrap;gap:8px;margin:16px 0 10px}}.obj{{border:1px solid #334354;background:#0f161e;color:#eef3f8;border-radius:10px;padding:7px 11px;cursor:pointer;display:flex;gap:8px;align-items:baseline}}.obj span{{font-size:12px;color:#aebcca}}.obj.active{{box-shadow:0 0 0 1px currentColor inset}}.obj.pass{{color:#71daa0}}.obj.raw{{color:#ffcf73}}.obj.trivial{{color:#91a6b9}}.profile[hidden]{{display:none}}.profiletop{{display:flex;justify-content:space-between;gap:12px;align-items:center}}.prob{{font-size:24px;color:#71daa0;font-weight:800}}.badge{{font-size:11px;font-weight:800}}.badge.pass{{color:#71daa0}}.badge.raw{{color:#ffcf73}}.badge.trivial{{color:#91a6b9}}.box{{background:#0f161e;border-radius:11px;padding:14px 16px;margin-top:10px}}.box h3{{margin:6px 0 3px}}.line{{font-weight:700;font-size:16px}}ol{{margin-top:5px}}details{{margin-top:12px}}summary{{cursor:pointer;color:#b7cbe0}}pre{{white-space:pre-wrap;color:#aebcca}}@media(max-width:760px){{.summary{{grid-template-columns:1fr 1fr}}header{{grid-template-columns:1fr}}}}
</style>
<main><h1>V5.0 — qualification automatique sur 20 combinaisons inédites</h1><p class="intro">Chaque combinaison est calculée pour tous ses objectifs possibles. Les objectifs à 0 % ou 100 % sont isolés comme cas triviaux. Pour chaque objectif non trivial, le générateur doit rejouer exactement sa procédure, rester compact et produire un « Pourquoi ? » fondé sur une position de cartes identifiable. Sinon la fiche reste RAW_EXACT_ONLY.</p>
<div class="summary"><div class="stat"><span>Combinaisons</span><b>{summary['holdings']}</b></div><div class="stat"><span>Objectifs non triviaux</span><b>{summary['nontrivial_profiles']}</b></div><div class="stat"><span>HUMAN_TREE_EXACT</span><b>{summary['human_tree_exact']}</b></div><div class="stat"><span>Taux de qualification</span><b>{rate} %</b></div></div>
{''.join(cards)}</main>
<script>document.querySelectorAll('.obj').forEach(btn=>btn.addEventListener('click',()=>{{const c=btn.dataset.case,t=btn.dataset.target;document.querySelectorAll('.obj[data-case="'+c+'"]').forEach(x=>x.classList.toggle('active',x===btn));document.querySelectorAll('.profile[data-case="'+c+'"]').forEach(x=>x.hidden=x.dataset.target!==t);}}));</script>'''
    out_path.write_text(doc, encoding='utf-8')


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument('--runtime-root', required=True)
    ap.add_argument('--reference', required=True)
    ap.add_argument('--out-dir', required=True)
    a = ap.parse_args()

    assert_novel(a.reference)
    sys.path.insert(0, str(Path(a.runtime_root) / 'runtime'))
    import integrated_engine as eng

    cases = []
    status_counts = Counter()
    fail_counts = Counter()
    nontrivial = 0
    exact_pass = 0

    for cid, north, south in HOLDINGS:
        profiles = []
        max_target = max(len(north), len(south))
        for target in range(1, max_target + 1):
            p = build_profile(eng, north, south, target)
            profiles.append(p)
            status_counts[p['status']] += 1
            if p['qualification']['counted']:
                nontrivial += 1
                if p['status'] == 'HUMAN_TREE_EXACT':
                    exact_pass += 1
                for reason in p['qualification'].get('fail_reasons') or []:
                    fail_counts[reason] += 1
            print(json.dumps({
                'case': cid, 'holding': [north, south], 'target': target,
                'p': p['fraction'], 'status': p['status'],
                'fails': p['qualification'].get('fail_reasons', []),
            }, ensure_ascii=False), flush=True)
        cases.append({'id': cid, 'north': north, 'south': south, 'display': [disp(north), disp(south)], 'profiles': profiles})

    rate = (100.0 * exact_pass / nontrivial) if nontrivial else 0.0
    summary = {
        'schema': 'MANIEMENTS_V5_HUMAN_V50_QUALIFICATION_V1',
        'holdings': len(cases),
        'profiles_total': sum(len(c['profiles']) for c in cases),
        'nontrivial_profiles': nontrivial,
        'human_tree_exact': exact_pass,
        'raw_exact_only': status_counts['RAW_EXACT_ONLY'],
        'exact_trivial': status_counts['EXACT_TRIVIAL'],
        'qualification_rate_percent': f'{rate:.2f}',
        'status_counts': dict(status_counts),
        'failure_reasons': dict(fail_counts),
        'runtime_sha256_expected': 'a0b580531f3c9e8bb00710b9c3e1c183b27cbfe9231c9d584e29a374ba88835d',
        'human_reference_answers_used': False,
        'novelty_gate': 'PASS',
    }

    out = Path(a.out_dir)
    out.mkdir(parents=True, exist_ok=True)
    payload = {'summary': summary, 'cases': cases}
    (out / 'HUMAN_V50_QUALIFICATION.json').write_text(json.dumps(payload, ensure_ascii=False, indent=2) + '\n', encoding='utf-8')
    render_html(cases, summary, out / 'MANIEMENTS_V5_HUMAN_V50_QUALIFICATION.html')
    (out / 'SUMMARY.txt').write_text(
        '\n'.join([
            'MANIEMENTS V5 HUMAN V5.0 QUALIFICATION',
            f"holdings={summary['holdings']}",
            f"profiles_total={summary['profiles_total']}",
            f"nontrivial_profiles={summary['nontrivial_profiles']}",
            f"human_tree_exact={summary['human_tree_exact']}",
            f"raw_exact_only={summary['raw_exact_only']}",
            f"exact_trivial={summary['exact_trivial']}",
            f"qualification_rate_percent={summary['qualification_rate_percent']}",
            'failure_reasons=' + json.dumps(summary['failure_reasons'], ensure_ascii=False, sort_keys=True),
            'novelty_gate=PASS',
        ]) + '\n', encoding='utf-8'
    )
    print(json.dumps(summary, ensure_ascii=False, sort_keys=True), flush=True)


if __name__ == '__main__':
    main()

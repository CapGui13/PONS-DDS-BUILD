#!/usr/bin/env python3
from __future__ import annotations

import argparse
import json
import sys
from fractions import Fraction
from pathlib import Path

SCHEMA = 'MANIEMENTS_V5_HUMAN_POLICY_EXPLORER_V1'
DECL = {'N', 'S'}


def build_graph(eng, north: str, south: str, target: int) -> dict:
    e = eng.Engine2(north, south, int(target))
    solved = e.solve(include_policy=True)
    policy = solved['policy']

    def policy_action(state):
        return policy.get(repr(e.public_key(state)))

    def apply_decl(state, action: str):
        seat, card = action.split(':', 1)
        rank = 0 if card == '-' else eng.R2I[card]
        if state.pos == 0:
            state = eng.PublicState(
                state.north, state.south,
                state.west_seen, state.east_seen,
                state.west_void, state.east_void,
                seat, 0, tuple(), state.won,
            )
        return e.close(e.decl_play(state, seat, rank))

    ids = {}
    nodes = []
    queue = []

    def ensure(state):
        key = repr(e.public_key(state))
        if key in ids:
            return ids[key]
        idx = len(nodes)
        ids[key] = idx
        nodes.append(None)
        queue.append((idx, state))
        return idx

    root = ensure(e.initial())
    cursor = 0
    while cursor < len(queue):
        idx, state = queue[cursor]
        cursor += 1
        terminal = e.terminal(state)
        common = {
            'north_remaining': eng.text(state.north),
            'south_remaining': eng.text(state.south),
            'won': state.won,
            'trick': [
                [seat, '-' if rank == 0 else eng.I2R[rank]]
                for seat, rank in state.trick
            ],
        }
        if terminal is not None:
            nodes[idx] = {
                'type': 'terminal',
                **common,
                'target_reached': state.won >= int(target),
            }
            continue

        if state.pos == 0 or e.order(state.leader)[state.pos] in DECL:
            action = policy_action(state)
            if action is None:
                raise RuntimeError(f'missing policy action at {e.public_key(state)!r}')
            nxt = apply_decl(state, action)
            nodes[idx] = {
                'type': 'declarer',
                **common,
                'action': action,
                'new_round': state.pos == 0,
                'next': ensure(nxt),
            }
            continue

        seat = e.order(state.leader)[state.pos]
        branches = []
        for rank, legal_worlds in e.defender_actions(state, seat):
            nxt = e.close(e.def_play(state, seat, rank))
            branches.append({
                'card': '-' if rank == 0 else eng.I2R[rank],
                'next': ensure(nxt),
                'legal_world_weight_fraction': str(e.model.weight(legal_worlds)),
            })
        nodes[idx] = {
            'type': 'defender',
            **common,
            'seat': seat,
            'branches': branches,
        }

    root_actions = e.root_action_analysis()
    best = max(Fraction(x) for x in root_actions.values())
    best_actions = [a for a, p in root_actions.items() if Fraction(p) == best]

    return {
        'schema': SCHEMA,
        'case': {'north': north, 'south': south, 'target': int(target)},
        'probability_fraction': solved['probability_fraction'],
        'best_root_actions': best_actions,
        'root_action_probabilities': root_actions,
        'root': root,
        'node_count': len(nodes),
        'nodes': nodes,
        'presentation_note_fr': (
            "Les noeuds internes restent une preuve technique. L'interface utilisateur doit "
            "présenter les actions comme des cartes jouées et les branches comme des cartes "
            "observées de la défense. Lorsqu'une nouvelle levée démarre depuis l'autre main, "
            "elle doit annoncer qu'une entrée extérieure est nécessaire."
        ),
    }


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument('--runtime-root', required=True)
    ap.add_argument('--north', required=True)
    ap.add_argument('--south', required=True)
    ap.add_argument('--target', required=True, type=int)
    ap.add_argument('--output', required=True)
    args = ap.parse_args()

    sys.path.insert(0, str(Path(args.runtime_root) / 'runtime'))
    import integrated_engine as eng

    out = build_graph(eng, args.north, args.south, args.target)
    Path(args.output).write_text(
        json.dumps(out, ensure_ascii=False, sort_keys=True, separators=(',', ':')) + '\n',
        encoding='utf-8',
    )
    print(json.dumps({
        'schema': out['schema'],
        'case': out['case'],
        'probability_fraction': out['probability_fraction'],
        'node_count': out['node_count'],
        'best_root_actions': out['best_root_actions'],
    }, ensure_ascii=False, sort_keys=True))


if __name__ == '__main__':
    main()

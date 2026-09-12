#!/usr/bin/env python3
from __future__ import annotations

import human_batch_v45 as v45


def _flatten_cards(value):
    if isinstance(value, (tuple, list)):
        out = []
        for item in value:
            out.extend(_flatten_cards(item))
        return out
    return [value]


def card_condition(cards):
    cards = _flatten_cards(cards)
    # Keep stable order while removing duplicates introduced by nested collapse.
    cards = list(dict.fromkeys(cards))
    if cards == ['-']:
        return "si l’adversaire défausse"
    names = [v45.b.fr_article(c) for c in cards]
    if len(names) == 1:
        return f"si l’adversaire fournit {names[0]}"
    return "si l’adversaire fournit " + ", ".join(names[:-1]) + " ou " + names[-1]


v45.card_condition = card_condition

if __name__ == '__main__':
    v45.main()

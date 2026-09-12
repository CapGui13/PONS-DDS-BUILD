#!/usr/bin/env python3
from __future__ import annotations
from fractions import Fraction

RANKS = 'AKQJT98765432'
RANK_FR = {
    'A': "l'As",
    'K': 'le Roi',
    'Q': 'la Dame',
    'J': 'le Valet',
    'T': 'le 10',
    '9': 'le 9',
    '8': 'le 8',
    '7': 'le 7',
    '6': 'le 6',
    '5': 'le 5',
    '4': 'le 4',
    '3': 'le 3',
    '2': 'le 2',
}


def _root_action_probabilities(eng, e, root):
    rows=[]
    for seat,hand in (('N',root.north),('S',root.south)):
        for r in eng.ranks(hand):
            lead=eng.PublicState(root.north,root.south,root.west_seen,root.east_seen,
                                 root.west_void,root.east_void,seat,0,tuple(),root.won)
            ns=e.decl_play(lead,seat,r)
            fr=e.frontier(ns)
            if not fr:
                continue
            best=max(fr,key=lambda m:(e.model.weight(m),m))
            rows.append((f'{seat}:{eng.I2R[r]}',e.model.weight(best)))
    return rows


def _split_signature(e, i):
    a=e.model.world_w[i].bit_count()
    b=e.model.world_e[i].bit_count()
    return tuple(sorted((a,b),reverse=True))


def _distribution_only_winning_splits(e, best_mask):
    """Return unordered split signatures iff mask membership depends only on split."""
    groups={}
    for i in range(e.model.n):
        sig=_split_signature(e,i)
        g=groups.setdefault(sig,[0,0])
        g[0]+=1
        if (best_mask>>i)&1:
            g[1]+=1
    for total,winning in groups.values():
        if winning not in (0,total):
            return None, set(groups)
    wins={sig for sig,(total,winning) in groups.items() if winning==total}
    return wins,set(groups)


def _split_fr(sig):
    return f'{sig[0]}–{sig[1]}'


def _join_fr(items):
    items=list(items)
    if not items:
        return ''
    if len(items)==1:
        return items[0]
    if len(items)==2:
        return items[0]+' ou '+items[1]
    return ', '.join(items[:-1])+' ou '+items[-1]


def _join_cards_fr(cards):
    cards=list(cards)
    names=[RANK_FR[c] for c in cards]
    if not names:
        return ''
    if len(names)==1:
        return names[0]
    if len(names)==2:
        return names[0]+' et '+names[1]
    return ', '.join(names[:-1])+' et '+names[-1]


def _compact_rank_list(cards):
    return '-'.join('10' if c=='T' else {'K':'R','Q':'D','J':'V'}.get(c,c) for c in cards)


def _world_cards(eng, mask):
    return {eng.I2R[r] for r in eng.ranks(mask)}


def _bare_higher_honors_promotion(eng,e,best_mask,probability,north,south,target):
    """Recognize promotion of the highest visible card when every higher missing card
    must be bare in one defender hand and all lower missing cards are in the other.

    Example: 54 opposite J632 succeeds for one trick exactly when AKQ are bare in
    one defender hand and T987 are in the other. This is a bridge-level statement,
    not a description of the policy automaton.
    """
    if target != 1:
        return None

    visible=set((north or '').replace('-','')+(south or '').replace('-',''))
    hero=next((r for r in RANKS if r in visible),None)
    if hero is None:
        return None
    hidx=RANKS.index(hero)
    higher=[r for r in RANKS[:hidx] if r not in visible]
    lower_missing=[r for r in RANKS[hidx+1:] if r not in visible]
    if not higher or not lower_missing:
        return None

    higher_set=set(higher); lower_set=set(lower_missing)
    for i in range(e.model.n):
        w=_world_cards(eng,e.model.world_w[i])
        east=_world_cards(eng,e.model.world_e[i])
        condition=((w==higher_set and east==lower_set) or
                   (east==higher_set and w==lower_set))
        if bool((best_mask>>i)&1) != condition:
            return None

    # If the hand containing our highest card has enough lower companions, the
    # human bridge line is to preserve that card while forcing the bare higher
    # cards. The exact engine assumes outside entries between rounds, so the text
    # must say so rather than silently implying suit-only communication.
    hero_hand=north if hero in north else south
    lower_companions=[r for r in hero_hand if RANKS.index(r)>hidx]

    higher_text=_join_cards_fr(higher)
    lower_text=_compact_rank_list(lower_missing)
    summary=(f"Une levée n'est possible que si {higher_text} sont groupés dans une même main adverse, "
             f"sans autre carte dans la couleur, tandis que l'autre adversaire détient {lower_text}.")

    if len(lower_companions) >= len(higher):
        hero_text=RANK_FR[hero]
        n=len(higher)
        times={1:'une fois',2:'deux fois',3:'trois fois',4:'quatre fois',5:'cinq fois'}.get(n,f'{n} fois')
        summary+=(f" Ne pas jouer {hero_text} avant d'avoir forcé {higher_text}. "
                  f"Avec les communications extérieures nécessaires, jouer petit {times} de la main qui contient {hero_text}, "
                  f"en revenant dans cette main entre les tours : {higher_text} sont forcés, puis {hero_text} est maître.")

    root_probs=_root_action_probabilities(eng,e,e.initial())
    p=Fraction(probability)
    lower_root=[fr for act,fr in root_probs if RANKS.index(act.split(':',1)[1])>hidx]
    first_small_irrelevant=bool(lower_root) and all(fr==p for fr in lower_root)

    return {
        'semantic_kind':'BARE_HIGHER_HONORS_PROMOTION',
        'summary_fr':summary,
        'success_condition_fr':f'{higher_text} groupés sans petite carte dans une main adverse ; {lower_text} dans l’autre.',
        'promoted_card':hero,
        'higher_missing':higher,
        'other_defender_cards':lower_missing,
        'first_small_irrelevant':first_small_irrelevant,
        'root_action_count':len(root_probs),
    }


def semantic_success_explanation(eng,e,best_mask,probability,north,south,target):
    """Produce a bridge-first explanation when an exact simple condition is found.

    The exact policy program remains the authority. This layer only replaces the
    technical automaton summary when the winning mask itself admits a compact,
    exact bridge interpretation.
    """
    win_splits,all_splits=_distribution_only_winning_splits(e,best_mask)
    if win_splits is not None:
        long_len=max(len(north.replace('-','')),len(south.replace('-','')))
        # Pure length winners: after exhausting the longest defender holding, at least
        # target cards remain in our long hand. This is independent of honor location.
        length_splits={sig for sig in all_splits if long_len-max(sig)>=target}
        if win_splits == length_splits and win_splits:
            root=e.initial()
            root_probs=_root_action_probabilities(eng,e,root)
            p=Fraction(probability)
            first_move_irrelevant=bool(root_probs) and all(fr==p for _,fr in root_probs)

            ordered=sorted(win_splits,key=lambda x:(max(x),min(x)))
            split_text=_join_fr(_split_fr(s) for s in ordered)
            if target==1:
                summary=f'On peut faire une levée si les cartes adverses sont réparties {split_text}.'
            else:
                summary=f'On peut faire {target} levées si les cartes adverses sont réparties {split_text}.'
            if first_move_irrelevant:
                summary += ' Quel que soit le maniement adopté.'

            return {
                'semantic_kind':'LENGTH_DISTRIBUTION_ONLY',
                'summary_fr':summary,
                'success_condition_fr':f'Répartition adverse {split_text}.',
                'winning_splits':[_split_fr(s) for s in ordered],
                'first_move_irrelevant':first_move_irrelevant,
                'root_action_count':len(root_probs),
            }

    promotion=_bare_higher_honors_promotion(eng,e,best_mask,probability,north,south,target)
    if promotion is not None:
        return promotion

    return None

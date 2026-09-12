#!/usr/bin/env python3
from __future__ import annotations

import human_motif_search_v571 as w

v=w.v


def fr_toward(c):
    name=v.fr_card(c)
    if name=='As':return "vers l’As"
    if name=='Dame':return 'vers la Dame'
    return 'vers le '+name


def procedure(cash,feeder,target,targets,display):
    if not targets:
        return ['Jouer la couleur en tête.']
    parts=[]
    if cash:
        names=[]
        for c in cash:
            name=v.fr_card(c)
            names.append(('l’'+name) if name=='As' else (('la '+name) if name=='Dame' else ('le '+name)))
        parts.append('Commencer par tirer '+' puis '.join(names)+'.')
    hand=display[0] if feeder=='N' else display[1]
    if len(targets)==1:
        parts.append(f'Jouer ensuite petit de {hand} {fr_toward(targets[0])}.')
    else:
        parts.append('Jouer successivement petit de '+hand+' '+', puis '.join(fr_toward(c) for c in targets)+'.')
    parts.append('Si l’adversaire placé en deuxième intercale une carte supérieure à la carte visée, couvrir au plus juste.')
    parts.append('Puis jouer la couleur en tête avec les cartes restantes si l’objectif n’est pas encore atteint.')
    return parts


def motif_name(north,south,cash,targets):
    owned=set(north+south);missing=[c for c in 'AKQJT' if c not in owned]
    if not targets:return 'PLAY_TOP'
    if len(missing)==1 and len(targets)>=2:
        return ('CASH_THEN_' if cash else '')+'REPEATED_FINESSE_'+missing[0]
    if cash:return 'CASH_THEN_FINESSE_THEN_PLAY_TOP'
    return 'FINESSE_THEN_PLAY_TOP'


v.procedure=procedure
v.motif_name=motif_name

if __name__=='__main__':
    v.main()

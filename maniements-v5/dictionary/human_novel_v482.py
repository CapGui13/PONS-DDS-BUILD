#!/usr/bin/env python3
from __future__ import annotations

from collections import defaultdict, deque
import human_novel_v481 as fast

v48=fast.v48
v47=v48.v47
b=v48.b


def action_phrase_one(action, card):
    _,rank=action
    if rank=='x': return 'jouer petit'
    if rank=='-': return 'ne plus fournir dans la couleur'
    significant = card in 'AKQJT'
    if significant and b.RANK_VALUE.get(rank,0)>b.RANK_VALUE.get(card,99):
        return 'couvrir avec '+b.fr_article(rank)
    if rank in ('T','9','8'):
        return 'passer '+b.fr_article(rank)
    if rank=='A': return 'jouer l’As'
    if rank=='K': return 'jouer le Roi'
    if rank=='Q': return 'passer la Dame' if not significant else 'jouer la Dame'
    if rank=='J': return 'passer le Valet' if not significant else 'jouer le Valet'
    return 'jouer '+b.fr_article(rank)


def critical_nodes_clean(root, initial, limit=3):
    q=deque([root]); seen=set(); out=[]; defender_nodes=0
    while q:
        n=q.popleft()
        if id(n) in seen: continue
        seen.add(id(n))
        if n.kind=='D':
            q.extend(n.branches or []); continue
        if n.kind=='F':
            defender_nodes+=1
            groups=v47.branch_groups(n)
            if len(groups)>=2:
                rules=[]
                for act,cards in groups.items():
                    by_phrase=defaultdict(list)
                    for c in cards:
                        by_phrase[action_phrase_one(act,c)].append(c)
                    for phrase,cs in by_phrase.items():
                        rules.append(v47.condition_fr(cs)+' → '+phrase)
                # stable dedupe
                rules=list(dict.fromkeys(rules))
                score=sum(2 if any(c in ('A','K','Q','J','T','-') for c in cards) else 1 for cards in groups.values())
                out.append({'depth':v47.node_depth(initial,n),'score':score,'rules':rules})
            for _,ch in n.branches or []: q.append(ch)
    out.sort(key=lambda x:(x['depth'],-x['score'],len(x['rules'])))
    # eliminate duplicate visible decisions
    ded=[]; sig=set()
    for z in out:
        k=tuple(z['rules'])
        if k in sig: continue
        sig.add(k); ded.append(z)
        if len(ded)>=limit: break
    return ded,defender_nodes


def de_feature(x):
    if x.startswith('le '): return 'du '+x[3:]
    if x.startswith('la '): return 'de la '+x[3:]
    if x.startswith('les '): return 'des '+x[4:]
    if x.startswith('l’') or x.startswith("l'"): return 'de '+x
    return 'de '+x


def why_auto_clean(eng,e,row,alt):
    if alt is None:
        return "Plusieurs départs atteignent exactement la même probabilité. Le départ affiché est retenu pour sa lisibilité, pas parce qu’il serait mathématiquement supérieur.", {'gain':'0','loss':'0'}
    gain=row['mask'] & ~alt['mask']; loss=alt['mask'] & ~row['mask']
    gp=e.model.weight(gain); lp=e.model.weight(loss)
    gf=b.position_features(eng,e,gain,row['seat']); lf=b.position_features(eng,e,loss,row['seat'])
    if gf:
        txt='Ce départ permet notamment de profiter '+', '.join(de_feature(x) for x in gf)+'.'
        if lf:
            txt+=' L’autre départ gagne en échange avec '+', '.join(x for x in lf)+'.'
        if gp or lp:
            txt+=f" Différentiel exact : +{v48.pct(gp)} / -{v48.pct(lp)}."
    else:
        txt=f"Ce départ gagne {v48.pct(gp)} de positions que la meilleure alternative perd"
        if lp: txt+=f", tandis que l’alternative gagne {v48.pct(lp)} d’autres positions"
        txt+='. Les positions différentielles sont trop variées pour être résumées proprement par une seule formule ; cette explication reste donc à relire.'
    return txt,{'gain':str(gp),'loss':str(lp),'gain_features':gf,'loss_features':lf,'alternative':[alt['seat'],alt['rank']]}

v47.critical_nodes=critical_nodes_clean
v48.why_auto=why_auto_clean

if __name__=='__main__':
    v48.main()

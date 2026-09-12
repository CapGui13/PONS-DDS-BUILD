#!/usr/bin/env python3
from __future__ import annotations

import human_motif_search_v59 as m

v=m.v
RVAL=m.RVAL


def specs(north,south):
    owned=set(north+south)
    cash_opts=[tuple()]
    # A useful probe/coup-de-sonde is not necessarily the partnership's absolute
    # top card (e.g. K first while A is held in the other hand). Search every
    # single strategic honour, plus the natural AK/AQ/KQ and top-prefix pairs.
    for c in 'AKQJT':
        if c in owned:cash_opts.append((c,))
    for a,b in (('A','K'),('A','Q'),('K','Q'),('A','J'),('K','J'),('Q','J')):
        if a in owned and b in owned:cash_opts.append((a,b))
    top=m.top_prefix(north,south)
    if len(top)>=2:cash_opts.append(tuple(top[:2]))
    cash_opts=list(dict.fromkeys(cash_opts))

    out=[];seen=set()
    def add(z):
        key=(z['cash'],z['feeder'],z['target'],z['seq'],z.get('probe'),z.get('mode'),z.get('probe_mode'))
        if key not in seen:seen.add(key);out.append(z)

    for feeder,target,fh,th in [('N','S',north,south),('S','N',south,north)]:
        ss=m.seqs(th)
        for seq in ss:
            for cash in cash_opts:
                if set(cash)&set(seq):continue
                add({'cash':cash,'feeder':feeder,'target':target,'seq':seq,'probe':None,'mode':'duck','probe_mode':'cover'})

        probes=[c for c in fh if c in 'KQJT']
        for probe in probes:
            for seq in [tuple()]+ss[:4]:
                for cash in cash_opts:
                    if len(cash)>1:continue
                    if probe in cash or set(cash)&set(seq):continue
                    for pm in ('cover','duck'):
                        add({'cash':cash,'feeder':feeder,'target':target,'seq':seq,'probe':probe,'mode':'cover','probe_mode':pm})
    return out


def article(c):
    name=m.fr(c)
    if c=='A':return 'l’As'
    if c=='Q':return 'la Dame'
    return 'le '+name


def toward(c):
    if c=='A':return "vers l’As"
    if c=='Q':return 'vers la Dame'
    return 'vers le '+m.fr(c)


def lines(spec,display):
    out=[]
    if spec['cash']:out.append('Commencer par tirer '+' puis '.join(article(c) for c in spec['cash'])+'.')
    h=display[0] if spec['feeder']=='N' else display[1]
    if spec.get('probe'):
        out.append(f"Présenter {article(spec['probe'])} de {h}.")
        if spec['probe_mode']=='cover':out.append('Si l’adversaire en deuxième monte au-dessus, couvrir au plus juste ; sinon laisser courir.')
        else:out.append('Laisser courir ce premier honneur, même si l’adversaire en deuxième monte au-dessus.')
    if spec['seq']:
        ts=list(spec['seq'])
        out.append('Puis jouer '+('successivement ' if len(ts)>1 else '')+'petit de '+h+' '+', puis '.join(toward(c) for c in ts)+'.')
        if spec['mode']=='duck':out.append('Si l’adversaire en deuxième monte au-dessus de la carte visée, laisser prendre au lieu de couvrir.')
        else:out.append('Si l’adversaire en deuxième monte au-dessus de la carte visée, couvrir au plus juste.')
    out.append('Finir en jouant la couleur en tête avec les cartes restantes si nécessaire.')
    return out


m.specs=specs
m.lines=lines

if __name__=='__main__':
    m.main()

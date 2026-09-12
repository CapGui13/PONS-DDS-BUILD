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
        # Safety duck after an ordinary low lead.
        for seq in ss:
            for cash in cash_opts:
                if set(cash)&set(seq):continue
                add({'cash':cash,'feeder':feeder,'target':target,'seq':seq,'probe':None,'mode':'duck','probe_mode':'cover'})

        # Honour probe, optionally followed by no finesse at all (probe then play top)
        # or by one of the short finesse sequences.
        probes=[c for c in fh if c in 'KQJT']
        for probe in probes:
            for seq in [tuple()]+ss[:4]:
                for cash in cash_opts:
                    if len(cash)>1:continue
                    if probe in cash or set(cash)&set(seq):continue
                    for pm in ('cover','duck'):
                        add({'cash':cash,'feeder':feeder,'target':target,'seq':seq,'probe':probe,'mode':'cover','probe_mode':pm})
    return out


m.specs=specs

if __name__=='__main__':
    m.main()

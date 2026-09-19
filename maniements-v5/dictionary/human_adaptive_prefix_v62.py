#!/usr/bin/env python3
from __future__ import annotations
import time
from fractions import Fraction

import human_prefix_residual_v515 as v515

def find_candidate(eng,north,south,target,display,oracle,max_seconds=0.0):
    """Find a compact exact two-round human prefix + exact compressed residual.

    V6.2 uses this only after simpler maneuver families failed. The candidate is
    accepted only when the human prefix itself preserves the exact oracle
    probability and the residual exact public policy compresses without spot
    fallback to at most 7 visible lines total.
    """
    started=time.monotonic()
    e=eng.Engine2(north,south,target)
    oracle=Fraction(oracle)
    rows=[]
    tested=0
    for source,spec in v515.all_specs(north,south):
        if max_seconds and time.monotonic()-started>max_seconds:
            break
        try:
            p,mask=v515.v511.evaluate_prefix(eng,north,south,target,spec,2)
            tested+=1
        except Exception:
            continue
        if p!=oracle:
            continue
        states=v515.residual_states(eng,e,spec,2)
        comp=v515.compress_forest(eng,e,states,display[0],display[1])
        if not comp.get('ok') or comp.get('spot_fallback_used'):
            continue
        pref=v515.prefix_lines(spec,display,2)
        residual=v515.clean_residual(comp.get('lines') or [])
        lines=pref+residual
        if len(lines)>7:
            continue
        score=(len(lines),len(residual),comp.get('normalized_states',9999),source)
        rows.append({
            'source_family':source,
            'spec':{k:(list(v) if isinstance(v,tuple) else v) for k,v in spec.items()},
            'prefix_rounds':2,
            'lines':lines,
            'mask':int(mask),
            'probability_fraction':str(p),
            'residual_states':len(states),
            'residual':comp,
            'score':score,
        })
        # Six concise lines is already within the reviewed V6.2 quality target.
        if len(lines)<=6:
            break
    rows.sort(key=lambda r:r['score'])
    if not rows:
        return {
            'found':False,'tested':tested,
            'elapsed_seconds':round(time.monotonic()-started,3)
        }
    b=rows[0]
    return {
        'found':True,
        'kind':'ADAPTATIF_MULTI_TOURS',
        'certified':True,
        'probability_fraction':b['probability_fraction'],
        'success_mask':str(b['mask']),
        'lines_fr':b['lines'],
        'spec':b['spec'],
        'source_family':b['source_family'],
        'prefix_rounds':2,
        'residual_states':b['residual_states'],
        'residual':b['residual'],
        'tested':tested,
        'elapsed_seconds':round(time.monotonic()-started,3),
        'certification':{
            'prefix_probability_equals_oracle':True,
            'residual_exact_public_policy':True,
            'spot_fallback_used':False,
            'visible_lines':len(b['lines']),
        },
    }

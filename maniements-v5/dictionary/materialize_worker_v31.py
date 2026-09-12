#!/usr/bin/env python3
from __future__ import annotations
from fractions import Fraction

import materialize_worker_v3 as base
import prototype_v3_semantics as sem

SEMANTIC_EXTRACTOR='NATIVE_PUBLIC_POLICY_COMPRESSED_V3_SEMANTIC_V1'


def supported_plan(eng,bp,pc,cc,north,south,target,expected_prob):
    e=eng.Engine2(north,south,target)
    solved_base=e.solve(include_policy=False)
    prob=solved_base['probability_fraction']
    if Fraction(prob)!=Fraction(expected_prob):
        raise RuntimeError(f'probability mismatch {prob} != {expected_prob}')

    root=e.initial(); fr=e.frontier(root)
    best=max(fr,key=lambda m:(e.model.weight(m),m))
    if e.model.weight(best)!=Fraction(expected_prob):
        raise RuntimeError('optimal-mask probability mismatch')

    source={'mode':'FULL_SOLVE'}
    try:
        solved=e.solve(include_policy=True)
    except (AssertionError,RuntimeError,ValueError):
        e2=eng.Engine2(north,south,target); e2.model.all=best
        solved=e2.solve(include_policy=True)
        if solved['success_worlds']!=best.bit_count():
            raise RuntimeError('optimal-mask replay lost winning worlds')
        source={'mode':'OPTIMAL_MASK_REPLAY','winning_worlds':best.bit_count(),'winning_mask':str(best)}

    if Fraction(solved['probability_fraction'])!=Fraction(expected_prob):
        raise RuntimeError('policy probability mismatch')

    native=base.native_policy_dict(bp,north,south,target,solved,source)
    program=pc.compress_policy_dict(native)
    if program['program_stats']['unseparable_contexts']!=0:
        raise RuntimeError('unseparable V3 policy contexts')
    compiled=cc.compile_policy_program(program)
    compact=pc.compact_policy_program(program)

    semantic=sem.semantic_success_explanation(eng,e,best,prob,north,south,target)
    summary=semantic['summary_fr'] if semantic else compiled['summary_fr']

    out={
        'kind':'native_public_policy_v31',
        'extractor':SEMANTIC_EXTRACTOR,
        'lead':compiled['root_lead'],
        'summary_fr':summary,
        'probability_fraction':prob,
        'target':target,
        'confidence':'HIGH',
        'coverage':'EXACT_POLICY_PROGRAM',
        'pattern':'NATIVE_POLICY_PROGRAM_EXACT',
        'policy_source':source,
        'program_stats':program['program_stats'],
        'policy_program':compact,
    }
    if semantic:
        out['semantic']=semantic
        out['display_policy_by_default']=False
    else:
        out['display_policy_by_default']=True
    return out,native['policy_state_count']


# Patch the qualified V3 worker without duplicating its durable-state machinery.
base.supported_plan=supported_plan
base.EXTRACTOR=SEMANTIC_EXTRACTOR

if __name__=='__main__':
    base.main()

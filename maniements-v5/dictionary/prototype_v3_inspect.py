#!/usr/bin/env python3
from __future__ import annotations
import argparse, json, sys
from pathlib import Path


def short(v, n=500):
    try:
        s = repr(v)
    except Exception as e:
        return f'<repr failed: {e}>'
    return s if len(s) <= n else s[:n] + '…'


def state_key(s):
    return (
        s.north, s.south, s.west_seen, s.east_seen,
        s.west_void, s.east_void, s.leader, s.pos,
        tuple(s.trick), s.won,
    )


def terminal_code(e, s):
    if e.target == 0 or s.won >= e.target:
        return 'SUCCESS'
    if s.pos == 0 and not (s.north or s.south):
        return 'END'
    future = max(s.north.bit_count(), s.south.bit_count()) + (1 if s.pos else 0)
    if s.won + future < e.target:
        return 'IMPOSSIBLE'
    return None


def select_decl(eng, e, s, mask):
    seat = e.order(s.leader)[s.pos]
    hand = s.north if seat == 'N' else s.south
    acts = eng.ranks(hand) if hand else (eng.VOID,)
    cands=[]
    for r in acts:
        ns=e.close(e.decl_play(s,seat,r))
        for cm in e.frontier(ns):
            if (mask | cm) == cm:
                cands.append((r,ns,cm))
    if not cands:
        return None
    cands.sort(key=lambda x:(x[0],-float(e.model.weight(x[2])),-x[2]))
    r,ns,cm=cands[0]
    return seat, ('-' if not r else eng.I2R[r]), ns, cm


def select_def_child(e,s,mask,seat,r,legal):
    ns=e.close(e.def_play(s,seat,r))
    need=mask & legal
    feasible=[cm for cm in e.frontier(ns) if (need | cm) == cm]
    if not feasible:
        return None
    cm=max(feasible,key=lambda x:(e.model.weight(x),x))
    return ns,cm


def select_root(eng,e,s,mask):
    cands=[]
    for seat,hand in (('N',s.north),('S',s.south)):
        for r in eng.ranks(hand):
            lead=eng.PublicState(s.north,s.south,s.west_seen,s.east_seen,s.west_void,s.east_void,seat,0,tuple(),s.won)
            ns=e.decl_play(lead,seat,r)
            for cm in e.frontier(ns):
                if (mask | cm) == cm:
                    cands.append((seat,r,ns,cm))
    cands.sort(key=lambda x:(0 if x[0]=='N' else 1,x[1],-float(e.model.weight(x[3])),-x[3]))
    seat,r,ns,cm=cands[0]
    return seat,eng.I2R[r],ns,cm


def trace_one(eng,e,s,mask,max_actions=40):
    out=[]
    for _ in range(max_actions):
        term=terminal_code(e,s)
        if term:
            out.append({'terminal':term,'won':s.won})
            break
        seat=e.order(s.leader)[s.pos]
        if seat in eng.DECL:
            z=select_decl(eng,e,s,mask)
            if z is None:
                out.append({'error':'no declarer witness'}); break
            seat,rank,s,mask=z
            out.append({'seat':seat,'role':'DECL','card':rank,'won_after':s.won,'pos_after':s.pos})
        else:
            choices=[]
            for r,legal in e.defender_actions(s,seat):
                need=mask & legal
                if not need:
                    continue
                child=select_def_child(e,s,mask,seat,r,legal)
                if child is None:
                    continue
                ns,cm=child
                choices.append((e.model.weight(need),r,legal,ns,cm))
            if not choices:
                out.append({'error':'no defender branch'}); break
            choices.sort(key=lambda x:(x[0],x[1]),reverse=True)
            w,r,legal,s,mask=choices[0]
            out.append({'seat':seat,'role':'DEF','card':'-' if not r else eng.I2R[r], 'success_support_mass':str(w),'won_after':s.won,'pos_after':s.pos})
    return out


def main():
    ap=argparse.ArgumentParser()
    ap.add_argument('--runtime-root',required=True)
    ap.add_argument('--north',default='AQ2')
    ap.add_argument('--south',default='J963')
    ap.add_argument('--target',type=int,default=4)
    a=ap.parse_args()
    sys.path.insert(0,str(Path(a.runtime_root)/'runtime'))
    import integrated_engine as eng

    e=eng.Engine2(a.north,a.south,a.target)
    base=e.solve(include_policy=False)
    root=e.initial(); fr=e.frontier(root)
    best=max(fr,key=lambda m:(e.model.weight(m),m))
    seat,rank,after_lead,lead_mask=select_root(eng,e,root,best)

    report={
        'case':{'north':a.north,'south':a.south,'target':a.target},
        'probability_fraction':base['probability_fraction'],
        'probability':base.get('probability'),
        'root_lead':f'{seat}:{rank}',
        'frontier_size':len(fr),
        'best_mask_bits':best.bit_count(),
        'best_mask_bit_length':best.bit_length(),
        'model_type':type(e.model).__name__,
        'model_dict':{},
        'model_dir':[x for x in dir(e.model) if not x.startswith('__')],
        'engine_cache_states':len(e.cache),
    }
    for k,v in getattr(e.model,'__dict__',{}).items():
        info={'type':type(v).__name__}
        try: info['len']=len(v)
        except Exception: pass
        info['repr']=short(v)
        report['model_dict'][k]=info

    first=[]
    dseat=e.order(after_lead.leader)[after_lead.pos]
    for r,legal in e.defender_actions(after_lead,dseat):
        need=lead_mask & legal
        child=select_def_child(e,after_lead,lead_mask,dseat,r,legal) if need else None
        row={
            'defender':dseat,
            'card':'-' if not r else eng.I2R[r],
            'compatible_success_mass':str(e.model.weight(need)) if need else '0',
            'compatible_success_bits':need.bit_count() if isinstance(need,int) else None,
        }
        if child:
            ns,cm=child
            term=terminal_code(e,ns)
            row['terminal_after_defense']=term
            if not term:
                dec=select_decl(eng,e,ns,cm)
                if dec:
                    row['next_declarer_action']=f'{dec[0]}:{dec[1]}'
                    row['principal_continuation']=trace_one(eng,e,dec[2],dec[3],max_actions=28)
        first.append(row)
    report['first_defender_branches']=first
    report['principal_line_from_after_lead']=trace_one(eng,e,after_lead,lead_mask,max_actions=36)

    print(json.dumps(report,ensure_ascii=False,indent=2,sort_keys=True))

if __name__=='__main__':
    main()

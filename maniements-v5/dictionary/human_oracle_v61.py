#!/usr/bin/env python3
from __future__ import annotations

from fractions import Fraction

HONORS=('Q','J')
RVAL={'2':2,'3':3,'4':4,'5':5,'6':6,'7':7,'8':8,'9':9,'T':10,'J':11,'Q':12,'K':13,'A':14}

def _cards(eng,mask):
    return [eng.I2R[r] for r in sorted(eng.ranks(mask),reverse=True)]

def _holding(s,seat):
    return s.north if seat=='N' else s.south

def _side_mask(e,side,i):
    return e.model.world_w[i] if side=='W' else e.model.world_e[i]

def _owner_mask(e,side,rank_i):
    return e.model.owner[side][rank_i]

def _predicate_mask(e,pred):
    m=0
    for i in range(e.model.n):
        if pred(i):
            m |= 1<<i
    return m

def _orientation(north,south):
    ns=set(north); ss=set(south)
    # V6.1 first certified family: AKT9x opposite lows.
    if {'A','K','T','9'} <= ns and not ({'Q','J'} & ns):
        return 'S','N','W','E'
    if {'A','K','T','9'} <= ss and not ({'Q','J'} & ss):
        return 'N','S','E','W'
    return None

def recognize(eng,inspect,north,south,target):
    ori=_orientation(north,south)
    if not ori:
        return None
    feeder,target_hand,before,behind=ori
    if target != 4:
        return None

    e=eng.Engine2(north,south,target)
    base=e.solve(include_policy=False)
    probability=Fraction(base['probability_fraction'])
    root=e.initial()
    frontier=e.frontier(root)
    best=max(frontier,key=lambda m:(e.model.weight(m),m))
    if e.model.weight(best)!=probability:
        return None

    missing={eng.I2R[r] for r in e.model.missing}
    if not {'Q','J'} <= missing:
        return None

    qi,ji=eng.R2I['Q'],eng.R2I['J']
    # Exact failure condition for this family:
    # Q and J both behind the AKT9 hand, in a holding of at least four cards.
    fail=_predicate_mask(
        e,
        lambda i: bool(_owner_mask(e,behind,qi)&(1<<i))
                  and bool(_owner_mask(e,behind,ji)&(1<<i))
                  and _side_mask(e,behind,i).bit_count()>=4
    )
    if best != (e.model.all & ~fail):
        return None

    seat,rank,after_lead,lead_mask=inspect.select_root(eng,e,root,best)
    if seat!=feeder:
        return None
    feeder_cards=_cards(eng,_holding(root,feeder))
    if rank != min(feeder_cards,key=lambda c:RVAL[c]):
        return None

    # Verify the first strategic response exactly on every successful second-hand branch.
    checked_low=checked_honor=0
    second=e.order(after_lead.leader)[after_lead.pos]
    if second!=before:
        return None
    low_branch_states=[]
    for r,legal in e.defender_actions(after_lead,second):
        need=lead_mask & legal
        if not need:
            continue
        child=inspect.select_def_child(e,after_lead,lead_mask,second,r,legal)
        if child is None:
            return None
        ns,cm=child
        dec=inspect.select_decl(eng,e,ns,cm)
        if dec is None:
            return None
        card='-' if not r else eng.I2R[r]
        if card in HONORS:
            if dec[0]!=target_hand or dec[1]!='K':
                return None
            checked_honor+=1
        elif card!='-':
            if dec[0]!=target_hand or dec[1]!='9':
                return None
            checked_low+=1
            low_branch_states.append((card,dec[2],dec[3]))

    if not checked_low or not checked_honor:
        return None

    # Verify the key adaptive switch: when 9 loses to Q/J behind,
    # the next fresh-trick action is K from the target hand.
    checked_switch=0
    for low_card,st,mask in low_branch_states:
        seat2=e.order(st.leader)[st.pos]
        if seat2!=behind:
            continue
        for r,legal in e.defender_actions(st,seat2):
            card='-' if not r else eng.I2R[r]
            if card not in HONORS:
                continue
            need=mask & legal
            if not need:
                continue
            child=inspect.select_def_child(e,st,mask,seat2,r,legal)
            if child is None:
                return None
            ns,cm=child
            if ns.pos!=0:
                return None
            a=inspect.select_root(eng,e,ns,cm)
            if a[0]!=target_hand or a[1]!='K':
                return None
            checked_switch+=1

    if not checked_switch:
        return None

    fail_p=e.model.weight(fail)
    success_p=e.model.weight(best)
    before_fr="l’adversaire placé en deuxième"
    behind_fr="l’adversaire placé derrière Main 1"
    return {
        'schema':'MANIEMENTS_V61_CERTIFIED_HUMAN_MOTIF_V1',
        'kind':'IMPASSE_PROFONDE_ADAPTATIVE',
        'target':target,
        'probability_fraction':str(success_p),
        'probability_percent':float(success_p)*100.0,
        'failure_fraction':str(fail_p),
        'failure_percent':float(fail_p)*100.0,
        'feeder':feeder,
        'target_hand':target_hand,
        'before_defender':before,
        'behind_defender':behind,
        'success_mask':str(best),
        'failure_mask':str(fail),
        'certified':True,
        'certification':{
            'exact_mask_complement':True,
            'root_low_lead_verified':True,
            'second_hand_honor_cover_verified':True,
            'second_hand_low_play_9_verified':True,
            'post_loss_king_switch_verified':True,
            'checked_low_branches':checked_low,
            'checked_honor_branches':checked_honor,
            'checked_post_loss_switches':checked_switch,
        },
        'lines_fr':[
            "Commencer par jouer petit de Main 2 vers le 9 de Main 1.",
            f"Si {before_fr} fournit la Dame ou le Valet, couvrir du Roi.",
            "S’il fournit une petite carte, jouer le 9.",
            f"Si le 9 est pris par la Dame ou le Valet chez {behind_fr}, tirer ensuite le Roi avant de poursuivre le maniement."
        ],
        'success_condition_fr':(
            "Le maniement ne perd l’objectif que lorsque Dame et Valet sont tous les deux "
            "derrière Main 1, dans une longueur d’au moins quatre cartes."
        ),
    }


def explain_qj_mask(eng,north,south,target,mask,target_hand):
    """Recognize exact, disjoint Q/J layout cases for the AKT9 family.

    Returns None unless the supplied success mask equals one of the certified
    bridge-readable templates below. Percentages are computed from the exact
    WorldModel weights, never from independent approximations.
    """
    ori=_orientation(north,south)
    if not ori:
        return None
    feeder,th,before,behind=ori
    if target_hand not in (None,th):
        return None
    e=eng.Engine2(north,south,target)
    mask=int(mask)
    qi,ji=eng.R2I['Q'],eng.R2I['J']

    def own(i,side,r):
        return bool(e.model.owner[side][r]&(1<<i))
    def slen(i,side):
        return _side_mask(e,side,i).bit_count()
    def pm(pred):
        return _predicate_mask(e,pred)
    def part(name,m):
        p=e.model.weight(m)
        return {
            'name':name,'mask':str(m),'fraction':str(p),
            'percent':float(p)*100.0,
        }

    before_pair_len={
        k:pm(lambda i,k=k: own(i,before,qi) and own(i,before,ji) and slen(i,before)==k)
        for k in range(2,6)
    }
    behind_pair_len={
        k:pm(lambda i,k=k: own(i,behind,qi) and own(i,behind,ji) and slen(i,behind)==k)
        for k in range(2,6)
    }
    q_single_behind=pm(lambda i: own(i,behind,qi) and slen(i,behind)==1 and own(i,before,ji))
    j_single_behind=pm(lambda i: own(i,behind,ji) and slen(i,behind)==1 and own(i,before,qi))

    templates=[]

    # Repeated deep finesse for all tricks: QJ together in front, at most fourth.
    m=before_pair_len[2]|before_pair_len[3]|before_pair_len[4]
    templates.append((
        m,
        "Dame et Valet sont réunis devant Main 1, au plus quatrièmes.",
        [
            part("Dame-Valet seconds devant Main 1",before_pair_len[2]),
            part("Dame-Valet troisièmes devant Main 1",before_pair_len[3]),
            part("Dame-Valet quatrièmes devant Main 1",before_pair_len[4]),
        ],
    ))

    # Probe then finesse: either QJ drop together doubleton in front, or exactly
    # one of the two is singleton behind and the other can then be finessed.
    m=before_pair_len[2]|q_single_behind|j_single_behind
    templates.append((
        m,
        "Le coup de sonde gagne si Dame-Valet sont seconds ensemble devant Main 1, "
        "ou si la Dame ou le Valet est sec derrière Main 1 et l’autre honneur est devant.",
        [
            part("Dame-Valet seconds ensemble devant Main 1",before_pair_len[2]),
            part("Dame sèche derrière Main 1, Valet devant",q_single_behind),
            part("Valet sec derrière Main 1, Dame devant",j_single_behind),
        ],
    ))

    # One deep finesse then play top: QJ together in front, second or third.
    m=before_pair_len[2]|before_pair_len[3]
    templates.append((
        m,
        "Dame et Valet sont réunis devant Main 1, au plus troisièmes.",
        [
            part("Dame-Valet seconds devant Main 1",before_pair_len[2]),
            part("Dame-Valet troisièmes devant Main 1",before_pair_len[3]),
        ],
    ))

    for tm,reason,cases in templates:
        if mask==tm:
            total=e.model.weight(mask)
            # Drop zero-probability pieces defensively and verify exact disjoint sum.
            cases=[x for x in cases if Fraction(x['fraction'])>0]
            if sum((Fraction(x['fraction']) for x in cases),Fraction(0))!=total:
                continue
            return {
                'certified':True,
                'mode':'CERTIFIED_V61_CASE_BREAKDOWN',
                'reason':reason,
                'cases':cases,
                'fraction':str(total),
                'percent':float(total)*100.0,
            }

    # Success everywhere except QJ together behind in a long holding.
    for min_len in (5,4):
        fail=0
        for k in range(min_len,6):
            fail |= behind_pair_len[k]
        if mask==(e.model.all & ~fail):
            fp=e.model.weight(fail); sp=e.model.weight(mask)
            fcases=[
                part(f"Dame-Valet {'quatrièmes' if k==4 else 'cinquièmes'} derrière Main 1",behind_pair_len[k])
                for k in range(min_len,6) if behind_pair_len[k]
            ]
            return {
                'certified':True,
                'mode':'CERTIFIED_V61_FAILURE_BREAKDOWN',
                'reason':(
                    "Le maniement échoue uniquement lorsque Dame et Valet sont réunis "
                    f"derrière Main 1 dans une longueur d’au moins {min_len} cartes."
                ),
                'cases':fcases,
                'failure_fraction':str(fp),
                'failure_percent':float(fp)*100.0,
                'fraction':str(sp),
                'percent':float(sp)*100.0,
            }
    return None

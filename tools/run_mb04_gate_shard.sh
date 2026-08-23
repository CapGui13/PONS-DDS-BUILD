#!/usr/bin/env bash
set -euo pipefail
SHARD="$1"; SEED="$2"; DEALS_SHA="$3"
PACKAGE=PONS_R7_FIXED_MB01_D9_GATE_PACKAGE.zip
R7_CRITIC_SHA=f1991fba7f818668aa55ab1776c63afd6b4f52b3b8a9565b599bc44ec236ca85
MB01_CRITIC_SHA=52d548cdd5c41206e89c1d970e12c663850b0955f6157da03bd938dae0df59c8
MB02_CRITIC_SHA=6f236dcb597ec5502b44e7e66cd79515051be5268de9f9d010fd621dea8b0511
MB03_CRITIC_SHA=7f8c10371be03ed35729f7ca0adbd8a374ebd01afed90aa987fc94ae4e02d35a
MB04_CRITIC_SHA=0838c8bba44bea70a7faf719d180683de45c7d5a8c5753483eed5bbdd68c7e8c
MB03_PATCH_SHA=697fae933ce44104fb4824f2aa8f35aa64d3a78797f9eb28eb04fe877819c9f1
MB04_PATCH_SHA=562f2f40e6730c081c7189373ab8c8f5acd2ad29e2d2733db1389c6ad52b41d3

test "$(sha256sum tools/MB02_TO_MB03_BRANCHK.patch | awk '{print $1}')" = "$MB03_PATCH_SHA"
test "$(sha256sum tools/MB03_TO_MB04_DELAYED_SPADES_RKCB.patch | awk '{print $1}')" = "$MB04_PATCH_SHA"
rm -rf work && mkdir -p work/pkg work/r7zip work/mb01 work/mb02 work/mb03 work/mb04
unzip -q "$PACKAGE" -d work/pkg
(cd work/pkg && sha256sum -c SHA256SUMS.txt)
unzip -q work/pkg/R7_GREEN.zip -d work/r7zip
R7_RUNTIME="$(dirname "$(find work/r7zip -type f -name pons-critic.js | head -1)")"
test -n "$R7_RUNTIME"
test "$(sha256sum "$R7_RUNTIME/pons-critic.js" | awk '{print $1}')" = "$R7_CRITIC_SHA"
cp -a "$R7_RUNTIME"/. work/mb01/
cp work/pkg/MB01_pons-critic.js work/mb01/pons-critic.js
test "$(sha256sum work/mb01/pons-critic.js | awk '{print $1}')" = "$MB01_CRITIC_SHA"
cp -a work/mb01/. work/mb02/
(cd work && patch --batch --forward mb02/pons-critic.js < ../tools/MB01_TO_MB02_D13.patch)
node --check work/mb02/pons-critic.js
test "$(sha256sum work/mb02/pons-critic.js | awk '{print $1}')" = "$MB02_CRITIC_SHA"
cp -a work/mb02/. work/mb03/
(cd work && patch --batch --forward mb03/pons-critic.js < ../tools/MB02_TO_MB03_BRANCHK.patch)
node --check work/mb03/pons-critic.js
test "$(sha256sum work/mb03/pons-critic.js | awk '{print $1}')" = "$MB03_CRITIC_SHA"
cp -a work/mb03/. work/mb04/
(cd work && patch --batch --forward mb04/pons-critic.js < ../tools/MB03_TO_MB04_DELAYED_SPADES_RKCB.patch)
node --check work/mb04/pons-critic.js
test "$(sha256sum work/mb04/pons-critic.js | awk '{print $1}')" = "$MB04_CRITIC_SHA"

python3 work/pkg/GENERATOR.py work/deals.jsonl 20000 "$SEED"
test "$(wc -l < work/deals.jsonl)" -eq 20000
echo "$DEALS_SHA  work/deals.jsonl" | sha256sum -c -
node work/pkg/GATE_RUNNER_FIXED.mjs "$(realpath work/mb03)" work/deals.jsonl work/mb03.jsonl
node work/pkg/GATE_RUNNER_FIXED.mjs "$(realpath work/mb04)" work/deals.jsonl work/mb04.jsonl

SHARD="$SHARD" python3 - <<'PY'
import json,os
shard=os.environ['SHARD']
def load(p):
    d={}
    with open(p) as f:
        for line in f:
            x=json.loads(line); d[(int(x['index_global']),int(x['seed']))]=x
    return d
A=load('work/mb03.jsonl'); B=load('work/mb04.jsonl')
assert A.keys()==B.keys() and len(A)==20000
changed=exact=collateral=0; examples=[]
for k,a in A.items():
    b=B[k]
    if a['auction']==b['auction']: continue
    changed+=1
    n=min(len(a['auction']),len(b['auction']))
    i=next((j for j in range(n) if a['auction'][j]!=b['auction'][j]),n)
    bm=next((m for m in b.get('marks',[]) if m.get('i')==i),None)
    pref=b['auction'][:i]
    try: first=next(j for j,c in enumerate(pref) if c not in ('PASS','X','XX'))
    except StopIteration: first=len(pref)
    rel=pref[first:]
    ok=(i<n and a['auction'][i]=='4S' and b['auction'][i]=='4NT' and bm and
        bm.get('reviewedSource')=='r7-fixed-mb04-delayed-spade-fit-rkcb-after-opener-3S' and
        len(rel)==6 and rel[0]=='1S' and rel[1]=='PASS' and rel[2] in ('2C','2D') and
        rel[3]=='PASS' and rel[4]=='3S' and rel[5]=='PASS')
    if ok: exact+=1
    else:
        collateral+=1
        if len(examples)<5: examples.append({'key':k,'i':i,'mb03':a['auction'],'mb04':b['auction'],'mark':bm})
summary={'shard':shard,'deals':20000,'same':20000-changed,'changed':changed,'exact_mb04':exact,'collateral':collateral,'collateral_examples':examples,'status':'SHARD_PASS' if collateral==0 else 'SHARD_FAIL'}
json.dump(summary,open(f'{shard}_SUMMARY.json','w'),indent=2,sort_keys=True)
print(json.dumps(summary,indent=2))
assert collateral==0 and exact==changed
PY

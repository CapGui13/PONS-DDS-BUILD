#!/usr/bin/env bash
set -euo pipefail
SHARD="$1"; SEED="$2"; DEALS_SHA="$3"
PACKAGE=PONS_R7_FIXED_MB01_D9_GATE_PACKAGE.zip
R7_CRITIC_SHA=f1991fba7f818668aa55ab1776c63afd6b4f52b3b8a9565b599bc44ec236ca85
MB01_CRITIC_SHA=52d548cdd5c41206e89c1d970e12c663850b0955f6157da03bd938dae0df59c8
MB02_CRITIC_SHA=6f236dcb597ec5502b44e7e66cd79515051be5268de9f9d010fd621dea8b0511
MB03_CRITIC_SHA=7f8c10371be03ed35729f7ca0adbd8a374ebd01afed90aa987fc94ae4e02d35a
MB04_CRITIC_SHA=0838c8bba44bea70a7faf719d180683de45c7d5a8c5753483eed5bbdd68c7e8c
MB05_CRITIC_SHA=cd3ff1ef67e4848b14f526cf0de0c929f9b3df856e0d847b7a37002cf1898468
MB06_CRITIC_SHA=6f74d0d55ecf63e8679c21b5f46fc50a48545f9d41cdcc4f26cc51dec4db701c
MB03_PATCH_SHA=697fae933ce44104fb4824f2aa8f35aa64d3a78797f9eb28eb04fe877819c9f1
MB04_PATCH_SHA=562f2f40e6730c081c7189373ab8c8f5acd2ad29e2d2733db1389c6ad52b41d3
MB05_PATCH_SHA=14bb9546a5f634a6c5996a096c68e67bf0a0474c77821ff3432f135e1313770c
MB06_PATCH_SHA=39832c8bd153a3ec19360fc47e46c79633f685b178f85567477fb35279e6fa48

test "$(sha256sum tools/MB02_TO_MB03_BRANCHK.patch | awk '{print $1}')" = "$MB03_PATCH_SHA"
test "$(sha256sum tools/MB03_TO_MB04_DELAYED_SPADES_RKCB.patch | awk '{print $1}')" = "$MB04_PATCH_SHA"
test "$(sha256sum tools/MB04_TO_MB05_DELAYED_HEARTS_RKCB.patch | awk '{print $1}')" = "$MB05_PATCH_SHA"
test "$(sha256sum tools/MB05_TO_MB06_O2_SIXCARD_ROLLBACK.patch | awk '{print $1}')" = "$MB06_PATCH_SHA"
rm -rf work && mkdir -p work/pkg work/r7zip work/mb01 work/mb02 work/mb03 work/mb04 work/mb05 work/mb06
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
test "$(sha256sum work/mb02/pons-critic.js | awk '{print $1}')" = "$MB02_CRITIC_SHA"
cp -a work/mb02/. work/mb03/
(cd work && patch --batch --forward mb03/pons-critic.js < ../tools/MB02_TO_MB03_BRANCHK.patch)
test "$(sha256sum work/mb03/pons-critic.js | awk '{print $1}')" = "$MB03_CRITIC_SHA"
cp -a work/mb03/. work/mb04/
(cd work && patch --batch --forward mb04/pons-critic.js < ../tools/MB03_TO_MB04_DELAYED_SPADES_RKCB.patch)
test "$(sha256sum work/mb04/pons-critic.js | awk '{print $1}')" = "$MB04_CRITIC_SHA"
cp -a work/mb04/. work/mb05/
(cd work && patch --batch --forward mb05/pons-critic.js < ../tools/MB04_TO_MB05_DELAYED_HEARTS_RKCB.patch)
test "$(sha256sum work/mb05/pons-critic.js | awk '{print $1}')" = "$MB05_CRITIC_SHA"
cp -a work/mb05/. work/mb06/
(cd work && patch --batch --forward mb06/pons-critic.js < ../tools/MB05_TO_MB06_O2_SIXCARD_ROLLBACK.patch)
test "$(sha256sum work/mb06/pons-critic.js | awk '{print $1}')" = "$MB06_CRITIC_SHA"
node --check work/mb05/pons-critic.js
node --check work/mb06/pons-critic.js

python3 work/pkg/GENERATOR.py work/deals.jsonl 20000 "$SEED"
test "$(wc -l < work/deals.jsonl)" -eq 20000
echo "$DEALS_SHA  work/deals.jsonl" | sha256sum -c -
node work/pkg/GATE_RUNNER_FIXED.mjs "$(realpath work/mb05)" work/deals.jsonl work/mb05.jsonl
node work/pkg/GATE_RUNNER_FIXED.mjs "$(realpath work/mb06)" work/deals.jsonl work/mb06.jsonl

SHARD="$SHARD" python3 - <<'PY'
import json,os
shard=os.environ['SHARD']; seats='NESW'
def load(p):
 d={}
 with open(p) as f:
  for line in f:
   x=json.loads(line); d[(int(x['index_global']),int(x['seed']))]=x
 return d
A=load('work/mb05.jsonl'); B=load('work/mb06.jsonl')
assert A.keys()==B.keys() and len(A)==20000
changed=exact=collateral=0; examples=[]
for k,a in A.items():
 b=B[k]
 if a['auction']==b['auction']: continue
 changed+=1
 n=min(len(a['auction']),len(b['auction']))
 i=next((j for j in range(n) if a['auction'][j]!=b['auction'][j]),n)
 am=next((m for m in a.get('marks',[]) if m.get('i')==i),None)
 seat=seats[(seats.index(a['dealer'])+i)%4]
 call=a['auction'][i] if i<len(a['auction']) else None
 suit=call[-1] if call in ('2H','2S') else None
 length=len(a.get('hands',{}).get(seat,{}).get(suit,'')) if suit else -1
 ok=(i<n and call in ('2H','2S') and am and am.get('reviewedSource')=='instance-o2-direct-weak-jump-major' and length==6 and b['auction'][i]!=call)
 if ok: exact+=1
 else:
  collateral+=1
  if len(examples)<5: examples.append({'key':k,'i':i,'mb05':a['auction'],'mb06':b['auction'],'mark':am,'seat':seat,'length':length})
summary={'shard':shard,'deals':20000,'same':20000-changed,'changed':changed,'exact_mb06':exact,'collateral':collateral,'collateral_examples':examples,'status':'SHARD_PASS' if collateral==0 and exact==changed else 'SHARD_FAIL'}
json.dump(summary,open(f'{shard}_SUMMARY.json','w'),indent=2,sort_keys=True)
print(json.dumps(summary,indent=2))
assert collateral==0 and exact==changed
PY

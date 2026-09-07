#!/usr/bin/env bash
set -euo pipefail

LANE_ID="$1"
RUNTIME_ROOT="$2"
STATE_WORKTREE="$3"
MAX_PASSES="${4:-14}"
WALL_LIMIT_SECONDS="${WALL_LIMIT_SECONDS:-20700}"
NORMAL_BUDGET_SECONDS="${NORMAL_BUDGET_SECONDS:-1320}"
NORMAL_CLOSE_RESERVE_SECONDS="${NORMAL_CLOSE_RESERVE_SECONDS:-120}"
RESCUE_BUDGET_SECONDS="${RESCUE_BUDGET_SECONDS:-16200}"
RESCUE_CLOSE_RESERVE_SECONDS="${RESCUE_CLOSE_RESERVE_SECONDS:-300}"
RESCUE_MAX_BUDGET_SECONDS="${RESCUE_MAX_BUDGET_SECONDS:-19800}"
RESCUE_MAX_CLOSE_RESERVE_SECONDS="${RESCUE_MAX_CLOSE_RESERVE_SECONDS:-300}"
STALL_PASSES="${STALL_PASSES:-3}"
LANE_PAD=$(printf '%02d' "$LANE_ID")
BRANCH="maniements-v5-lane-${LANE_PAD}"
LATEST="$STATE_WORKTREE/state/latest.zip"
VERIFY="$RUNTIME_ROOT/runtime/verify_orbit_pass_v5.py"
PASSER="$RUNTIME_ROOT/runtime/orbit_pass_v5.py"
ORCH="$STATE_WORKTREE/state/orchestration.json"

if [[ ! -f "$LATEST" ]]; then
  mkdir -p "$STATE_WORKTREE/state"
else
  python3 "$VERIFY" "$LATEST"
fi

cd "$STATE_WORKTREE"
git config user.name "github-actions[bot]"
git config user.email "41898282+github-actions[bot]@users.noreply.github.com"

START_EPOCH=$(date +%s)
COMPLETED_THIS_JOB=0

read_manifest_field() {
  local zip="$1" field="$2"
  python3 - "$zip" "$field" <<'PY'
import json,sys,zipfile
p,f=sys.argv[1],sys.argv[2]
with zipfile.ZipFile(p) as z:
    m=json.loads(z.read('PASS_MANIFEST.json'))
v=m.get(f)
if v is None: print('')
elif isinstance(v,bool): print('true' if v else 'false')
else: print(v)
PY
}

stall_decision() {
  python3 - "$STALL_PASSES" <<'PY'
import json,sys
need=int(sys.argv[1])
try:
    rows=[json.loads(x) for x in open('state/history.jsonl',encoding='utf-8') if x.strip()]
except FileNotFoundError:
    rows=[]
if not rows:
    print('NORMAL|0||')
    raise SystemExit
latest=rows[-1]
key_names=('cumulative_completed_orbits','cumulative_completed_targets','active_rep_state_id','active_next_target')
def key(x): return tuple(x.get(k) for k in key_names)
group=[latest]
for prev in reversed(rows[:-1]):
    cur=group[-1]
    if prev.get('status')!='BUDGET_STOP' or cur.get('status')!='BUDGET_STOP':
        break
    if key(prev)!=key(latest):
        break
    pp,cp=prev.get('pass_no'),cur.get('pass_no')
    if not isinstance(pp,int) or not isinstance(cp,int) or pp+1!=cp:
        break
    group.append(prev)
stall=max(0,len(group)-1)
oldest=group[-1]
last_progress=oldest.get('updated_at_utc') or ''
last_mode=str(latest.get('orchestration_mode') or 'NORMAL')
mode='NORMAL'
reason=''
if last_mode=='RESCUE_MAX' and stall>=1:
    mode='HARD_STALL'
    reason='RESCUE_MAX completed without scientific progress'
elif last_mode=='RESCUE' and stall>=1:
    mode='RESCUE_MAX'
    reason='RESCUE completed without scientific progress'
elif stall>=need:
    mode='RESCUE'
    reason=f'{stall} consecutive zero-progress PASSes on the same active target'
print(f'{mode}|{stall}|{last_progress}|{reason}')
PY
}

write_state_metadata() {
  local zip="$1" sha="$2" source="$3" mode="$4"
  python3 - "$zip" "$sha" "$source" "$mode" <<'PY'
import datetime,json,sys,zipfile
p,sha,source,mode=sys.argv[1:5]
with zipfile.ZipFile(p) as z:
    m=json.loads(z.read('PASS_MANIFEST.json'))
obj=dict(m)
obj['zip_sha256']=sha
obj['updated_at_utc']=datetime.datetime.now(datetime.timezone.utc).replace(microsecond=0).isoformat()
obj['state_source']=source
obj['orchestration_mode']=mode
open('state/progress.json','w',encoding='utf-8').write(json.dumps(obj,sort_keys=True,indent=2)+'\n')
hist={k:obj.get(k) for k in [
    'lane_id','pass_no','status','pass_completed_orbits','pass_emitted_ordered_rows',
    'pass_completed_targets','cumulative_completed_orbits','cumulative_emitted_ordered_rows',
    'cumulative_completed_targets','active_rep_state_id','active_next_target','active_max_target',
    'elapsed_seconds','budget_seconds','close_reserve_seconds','orchestration_mode',
    'zip_sha256','predecessor_zip_sha256','updated_at_utc','state_source']}
line=json.dumps(hist,sort_keys=True,separators=(',',':'))
try:
    existing=open('state/history.jsonl',encoding='utf-8').read().splitlines()
except FileNotFoundError:
    existing=[]
if not any(json.loads(x).get('pass_no')==hist['pass_no'] and json.loads(x).get('zip_sha256')==sha for x in existing if x.strip()):
    with open('state/history.jsonl','a',encoding='utf-8') as f:
        f.write(line+'\n')
PY
}

write_orchestration_state() {
  local last_mode="$1" next_mode="$2" stall_count="$3" last_progress="$4" reason="$5"
  python3 - "$last_mode" "$next_mode" "$stall_count" "$last_progress" "$reason" <<'PY'
import datetime,json,sys,zipfile
last_mode,next_mode,stall,last_progress,reason=sys.argv[1:6]
now=datetime.datetime.now(datetime.timezone.utc).replace(microsecond=0).isoformat()
obj={
  'schema':'MANIEMENTS_V3_GEN_V5_ORCHESTRATION_STATE_V1',
  'lane_id':None,
  'last_pass_no':None,
  'last_pass_mode':last_mode,
  'next_mode':next_mode,
  'stall_count':int(stall),
  'last_scientific_progress_at_utc':last_progress or None,
  'hard_stall': next_mode=='HARD_STALL',
  'reason':reason or None,
  'updated_at_utc':now,
}
try:
  with zipfile.ZipFile('state/latest.zip') as z:
    m=json.loads(z.read('PASS_MANIFEST.json'))
  obj['lane_id']=m.get('lane_id')
  obj['last_pass_no']=m.get('pass_no')
  obj['active_rep_state_id']=m.get('active_rep_state_id')
  obj['active_next_target']=m.get('active_next_target')
  obj['active_max_target']=m.get('active_max_target')
  obj['cumulative_completed_orbits']=m.get('cumulative_completed_orbits')
  obj['cumulative_completed_targets']=m.get('cumulative_completed_targets')
except FileNotFoundError:
  pass
open('state/orchestration.json','w',encoding='utf-8').write(json.dumps(obj,sort_keys=True,indent=2)+'\n')
PY
}

commit_orchestration_marker_if_needed() {
  if [[ -z "$(git status --porcelain -- state/orchestration.json)" ]]; then
    return 0
  fi
  git add state/orchestration.json
  git commit -m "MANIEMENTS V5 lane ${LANE_PAD}: orchestration HARD_STALL"
  git push origin "HEAD:${BRANCH}"
}

for ((ITER=0; ITER<MAX_PASSES; ITER++)); do
  if [[ -f "$LATEST" ]]; then
    CURRENT_STATUS=$(read_manifest_field "$LATEST" status)
    CURRENT_PASS=$(read_manifest_field "$LATEST" pass_no)
    if [[ "$CURRENT_STATUS" == "LANE_DONE" ]]; then
      echo "Lane ${LANE_PAD} already complete at PASS ${CURRENT_PASS}."
      break
    fi
    NEXT_PASS=$((CURRENT_PASS+1))
    PRED_SHA=$(sha256sum "$LATEST" | awk '{print $1}')
  else
    NEXT_PASS=0
    PRED_SHA=""
  fi

  IFS='|' read -r MODE STALL_COUNT LAST_PROGRESS REASON < <(stall_decision)
  if [[ "$MODE" == "HARD_STALL" ]]; then
    write_orchestration_state "RESCUE_MAX" "HARD_STALL" "$STALL_COUNT" "$LAST_PROGRESS" "$REASON"
    commit_orchestration_marker_if_needed
    echo "HARD_STALL: lane=${LANE_PAD} pass=${CURRENT_PASS:-none} active target cannot finish even with RESCUE_MAX."
    break
  fi

  BUDGET_SECONDS="$NORMAL_BUDGET_SECONDS"
  CLOSE_RESERVE_SECONDS="$NORMAL_CLOSE_RESERVE_SECONDS"
  if [[ "$MODE" == "RESCUE" ]]; then
    BUDGET_SECONDS="$RESCUE_BUDGET_SECONDS"
    CLOSE_RESERVE_SECONDS="$RESCUE_CLOSE_RESERVE_SECONDS"
  elif [[ "$MODE" == "RESCUE_MAX" ]]; then
    BUDGET_SECONDS="$RESCUE_MAX_BUDGET_SECONDS"
    CLOSE_RESERVE_SECONDS="$RESCUE_MAX_CLOSE_RESERVE_SECONDS"
  fi

  NOW=$(date +%s)
  ELAPSED=$((NOW-START_EPOCH))
  if (( ELAPSED + BUDGET_SECONDS + 120 > WALL_LIMIT_SECONDS )); then
    echo "Job wall budget reached after ${COMPLETED_THIS_JOB} pass(es); next pass would be ${MODE} (${BUDGET_SECONDS}s)."
    break
  fi

  OUT="$RUNNER_TEMP/MANIEMENTS_V3_GEN_V5_LANE_${LANE_PAD}_PASS_$(printf '%06d' "$NEXT_PASS").zip"
  rm -f "$OUT"

  echo "=== Lane ${LANE_PAD} PASS $(printf '%06d' "$NEXT_PASS") mode=${MODE} budget=${BUDGET_SECONDS}s reserve=${CLOSE_RESERVE_SECONDS}s stall_count=${STALL_COUNT} ==="
  if (( NEXT_PASS == 0 )); then
    python3 "$PASSER" \
      --output-zip "$OUT" \
      --lane-id "$LANE_ID" \
      --lane-count 64 \
      --pass-no 0 \
      --budget-seconds "$BUDGET_SECONDS" \
      --close-reserve-seconds "$CLOSE_RESERVE_SECONDS"
    python3 "$VERIFY" "$OUT"
  else
    python3 "$PASSER" \
      --output-zip "$OUT" \
      --lane-id "$LANE_ID" \
      --lane-count 64 \
      --pass-no "$NEXT_PASS" \
      --budget-seconds "$BUDGET_SECONDS" \
      --close-reserve-seconds "$CLOSE_RESERVE_SECONDS" \
      --predecessor "$LATEST" \
      --predecessor-sha256 "$PRED_SHA"
    python3 "$VERIFY" "$OUT" --predecessor "$LATEST"
  fi

  NEW_STATUS=$(read_manifest_field "$OUT" status)
  if [[ "$NEW_STATUS" != "BUDGET_STOP" && "$NEW_STATUS" != "LANE_DONE" ]]; then
    echo "Unexpected pass status: $NEW_STATUS" >&2
    exit 41
  fi

  NEW_SHA=$(sha256sum "$OUT" | awk '{print $1}')
  mv "$OUT" "$LATEST"
  printf '%s  latest.zip\n' "$NEW_SHA" > state/latest.zip.sha256
  write_state_metadata "$LATEST" "$NEW_SHA" "github-actions" "$MODE"

  IFS='|' read -r NEXT_MODE NEXT_STALL NEXT_LAST_PROGRESS NEXT_REASON < <(stall_decision)
  write_orchestration_state "$MODE" "$NEXT_MODE" "$NEXT_STALL" "$NEXT_LAST_PROGRESS" "$NEXT_REASON"

  git add state/latest.zip state/latest.zip.sha256 state/progress.json state/history.jsonl state/orchestration.json
  git commit -m "MANIEMENTS V5 lane ${LANE_PAD}: PASS $(printf '%06d' "$NEXT_PASS") ${NEW_STATUS} ${MODE}"
  git push origin "HEAD:${BRANCH}"
  COMPLETED_THIS_JOB=$((COMPLETED_THIS_JOB+1))

  ORBITS=$(read_manifest_field "$LATEST" cumulative_completed_orbits)
  TARGETS=$(read_manifest_field "$LATEST" cumulative_completed_targets)
  echo "Durable: lane=${LANE_PAD} pass=${NEXT_PASS} mode=${MODE} next_mode=${NEXT_MODE} stall_count=${NEXT_STALL} status=${NEW_STATUS} orbits=${ORBITS} targets=${TARGETS} sha=${NEW_SHA}"

  if [[ "$NEW_STATUS" == "LANE_DONE" ]]; then
    break
  fi
done

python3 - "$LATEST" <<'PY' >> "$GITHUB_STEP_SUMMARY"
import json,sys,zipfile
with zipfile.ZipFile(sys.argv[1]) as z:
    m=json.loads(z.read('PASS_MANIFEST.json'))
try:
    o=json.load(open('state/orchestration.json',encoding='utf-8'))
except FileNotFoundError:
    o={}
print(f"### Lane {m['lane_id']:02d}")
print(f"- PASS: `{m['pass_no']:06d}`")
print(f"- Status: **{m['status']}**")
print(f"- Dernier mode: **{o.get('last_pass_mode','NORMAL')}**")
print(f"- Prochain mode: **{o.get('next_mode','NORMAL')}**")
print(f"- Stall count: **{o.get('stall_count',0)}**")
print(f"- Budget: **{m.get('budget_seconds')} s**")
print(f"- Orbites: **{m['cumulative_completed_orbits']}**")
print(f"- Rows: **{m['cumulative_emitted_ordered_rows']}**")
print(f"- Targets: **{m['cumulative_completed_targets']}**")
PY

#!/usr/bin/env bash
set -euo pipefail

LANE_ID="$1"
RUNTIME_ROOT="$2"
STATE_WORKTREE="$3"
MAX_PASSES="${4:-14}"
WALL_LIMIT_SECONDS="${WALL_LIMIT_SECONDS:-17400}"
LANE_PAD=$(printf '%02d' "$LANE_ID")
BRANCH="maniements-v5-lane-${LANE_PAD}"
LATEST="$STATE_WORKTREE/state/latest.zip"
VERIFY="$RUNTIME_ROOT/runtime/verify_orbit_pass_v5.py"
PASSER="$RUNTIME_ROOT/runtime/orbit_pass_v5.py"

FRESH=false
if [[ ! -f "$LATEST" ]]; then
  FRESH=true
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

write_state_metadata() {
  local zip="$1" sha="$2" source="$3"
  python3 - "$zip" "$sha" "$source" <<'PY'
import datetime,json,sys,zipfile
p,sha,source=sys.argv[1:4]
with zipfile.ZipFile(p) as z:
    m=json.loads(z.read('PASS_MANIFEST.json'))
obj=dict(m)
obj['zip_sha256']=sha
obj['updated_at_utc']=datetime.datetime.now(datetime.timezone.utc).replace(microsecond=0).isoformat()
obj['state_source']=source
open('state/progress.json','w',encoding='utf-8').write(json.dumps(obj,sort_keys=True,indent=2)+'\n')
hist={k:obj.get(k) for k in [
    'lane_id','pass_no','status','pass_completed_orbits','pass_emitted_ordered_rows',
    'pass_completed_targets','cumulative_completed_orbits','cumulative_emitted_ordered_rows',
    'cumulative_completed_targets','active_rep_state_id','active_next_target','active_max_target',
    'elapsed_seconds','zip_sha256','predecessor_zip_sha256','updated_at_utc','state_source']}
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

for ((ITER=0; ITER<MAX_PASSES; ITER++)); do
  NOW=$(date +%s)
  ELAPSED=$((NOW-START_EPOCH))
  if (( ELAPSED + 1320 + 120 > WALL_LIMIT_SECONDS )); then
    echo "Job wall budget reached after ${COMPLETED_THIS_JOB} pass(es)."
    break
  fi

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

  OUT="$RUNNER_TEMP/MANIEMENTS_V3_GEN_V5_LANE_${LANE_PAD}_PASS_$(printf '%06d' "$NEXT_PASS").zip"
  rm -f "$OUT"

  echo "=== Lane ${LANE_PAD} PASS $(printf '%06d' "$NEXT_PASS") ==="
  if (( NEXT_PASS == 0 )); then
    python3 "$PASSER" \
      --output-zip "$OUT" \
      --lane-id "$LANE_ID" \
      --lane-count 64 \
      --pass-no 0 \
      --budget-seconds 1320 \
      --close-reserve-seconds 120
    python3 "$VERIFY" "$OUT"
  else
    python3 "$PASSER" \
      --output-zip "$OUT" \
      --lane-id "$LANE_ID" \
      --lane-count 64 \
      --pass-no "$NEXT_PASS" \
      --budget-seconds 1320 \
      --close-reserve-seconds 120 \
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
  write_state_metadata "$LATEST" "$NEW_SHA" "github-actions"

  git add state/latest.zip state/latest.zip.sha256 state/progress.json state/history.jsonl
  git commit -m "MANIEMENTS V5 lane ${LANE_PAD}: PASS $(printf '%06d' "$NEXT_PASS") ${NEW_STATUS}"
  git push origin "HEAD:${BRANCH}"
  COMPLETED_THIS_JOB=$((COMPLETED_THIS_JOB+1))

  ORBITS=$(read_manifest_field "$LATEST" cumulative_completed_orbits)
  TARGETS=$(read_manifest_field "$LATEST" cumulative_completed_targets)
  echo "Durable: lane=${LANE_PAD} pass=${NEXT_PASS} status=${NEW_STATUS} orbits=${ORBITS} targets=${TARGETS} sha=${NEW_SHA}"

  if [[ "$NEW_STATUS" == "LANE_DONE" ]]; then
    break
  fi
done

python3 - "$LATEST" <<'PY' >> "$GITHUB_STEP_SUMMARY"
import json,sys,zipfile
with zipfile.ZipFile(sys.argv[1]) as z:
    m=json.loads(z.read('PASS_MANIFEST.json'))
print(f"### Lane {m['lane_id']:02d}")
print(f"- PASS: `{m['pass_no']:06d}`")
print(f"- Status: **{m['status']}**")
print(f"- Orbites: **{m['cumulative_completed_orbits']}**")
print(f"- Rows: **{m['cumulative_emitted_ordered_rows']}**")
print(f"- Targets: **{m['cumulative_completed_targets']}**")
PY

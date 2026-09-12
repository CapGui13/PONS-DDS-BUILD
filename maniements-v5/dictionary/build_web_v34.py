#!/usr/bin/env python3
from __future__ import annotations

import argparse, json
from pathlib import Path

import build_web_v3 as core
import build_web_v32 as source
import build_web_v33 as ui


def iter_exact_branch_entries(repo:Path, branch_prefix:str):
    """Read exact V3 production only.

    Legacy `dictionary/semantic_backfill` records intentionally do NOT override
    exact entries here.  That layer predates the reviewed V4/V5 human contract
    and remains hidden until a HUMAN_TREE_EXACT/REFERENCE_VERIFIED replacement
    is integrated.
    """
    rows={}
    for w in range(20):
        ref=f'refs/remotes/origin/{branch_prefix}{w:02d}'
        for r in source._iter_ref_jsonl(repo,ref,'dictionary/chunks'):
            rows[(int(r['state_id']),int(r['target']))]=r
    for k in sorted(rows):
        yield rows[k]


def iter_exact_input_entries(root:Path):
    # `core.iter_input_entries` reads the regular exact dictionary chunks only.
    rows={}
    for r in core.iter_input_entries(root):
        rows[(int(r['state_id']),int(r['target']))]=r
    for k in sorted(rows):
        yield rows[k]


def main():
    ap=argparse.ArgumentParser()
    ap.add_argument('--repo',default='.')
    ap.add_argument('--output-dir',required=True)
    ap.add_argument('--branch-prefix',default='maniements-v5-dictionary-v3-p1-')
    ap.add_argument('--input-root')
    a=ap.parse_args()
    if a.input_root:
        entries=iter_exact_input_entries(Path(a.input_root))
    else:
        entries=iter_exact_branch_entries(Path(a.repo),a.branch_prefix)
    out=Path(a.output_dir);out.mkdir(parents=True,exist_ok=True)
    manifest=core.write_site(entries,out)
    manifest['human_layer']='LEGACY_SEMANTIC_BACKFILL_HIDDEN_PENDING_V5_QUALIFICATION'
    (out/'manifest.json').write_text(json.dumps(manifest,ensure_ascii=False,sort_keys=True,separators=(',',':')),encoding='utf-8')
    (out/'index.html').write_text(ui.wildcard_html().replace('__SHARD_SIZE__',str(core.SHARD_SIZE)),encoding='utf-8')
    print(json.dumps(manifest,ensure_ascii=False,sort_keys=True))


if __name__=='__main__':
    main()

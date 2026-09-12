#!/usr/bin/env python3
from __future__ import annotations

import argparse, json
from pathlib import Path

import build_web_v3 as base


def _iter_ref_jsonl(repo:Path, ref:str, prefix:str):
    for p in base.list_paths(repo,ref,prefix):
        if not p.endswith('.jsonl'):
            continue
        for line in base.git_text(repo,ref,p).splitlines():
            if line.strip():
                yield json.loads(line)


def iter_branch_entries(repo:Path, branch_prefix:str):
    rows={}
    for w in range(20):
        ref=f'refs/remotes/origin/{branch_prefix}{w:02d}'
        # Exact production records first.
        for r in _iter_ref_jsonl(repo,ref,'dictionary/chunks'):
            rows[(int(r['state_id']),int(r['target']))]=r
        # Human semantic corrections override the same exact record.
        for r in _iter_ref_jsonl(repo,ref,'dictionary/semantic_backfill'):
            rows[(int(r['state_id']),int(r['target']))]=r
    for k in sorted(rows):
        yield rows[k]


def iter_input_entries(root:Path):
    rows={}
    for r in base.iter_input_entries(root):
        rows[(int(r['state_id']),int(r['target']))]=r
    for p in sorted((root/'dictionary'/'semantic_backfill').glob('chunk_*.jsonl')):
        with p.open(encoding='utf-8') as f:
            for line in f:
                if line.strip():
                    r=json.loads(line)
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
        entries=iter_input_entries(Path(a.input_root))
    else:
        entries=iter_branch_entries(Path(a.repo),a.branch_prefix)
    out=Path(a.output_dir); out.mkdir(parents=True,exist_ok=True)
    manifest=base.write_site(entries,out)
    print(json.dumps(manifest,ensure_ascii=False,sort_keys=True))

if __name__=='__main__':
    main()

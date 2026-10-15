#!/usr/bin/env python3
"""Run the Checker (two versions) on the PRE-fix and POST-fix checkout of every verified bug-fix commit.
Snapshots (git archive, committed state): /tmp/jh_snap/v2 <- branch checker-rules-v2 (57018c8), /tmp/jh_snap/v3fixes <- branch v3-fixes (763fe65); see docs/jankeesvw-history.md.
Output data/checker_runs.jsonl: {repo, commit, ver, side, findings:[...]} (resumable)."""
import json, os, subprocess, sys, tempfile
from concurrent.futures import ThreadPoolExecutor
ROOT = '/workspace/ref/jankeesvw'; T = '/tmp/jh_trees'; W = os.path.dirname(os.path.abspath(__file__)) + '/checker_worker.py'
SNAPS = {'v2': '/tmp/jh_snap/v2', 'v3fixes_763fe65': '/tmp/jh_snap/v3fixes', 'v3fixes_d00fcc0': '/tmp/jh_snap/v3fixes-head'}
os.makedirs(T, exist_ok=True)
def tree(repo, sha, tag):
    d = f'{T}/{repo}_{sha[:10]}_{tag}'
    if not os.path.exists(d + '/.ok'):
        os.makedirs(d, exist_ok=True)
        p = subprocess.run(f"git -C {ROOT}/{repo} archive {sha} | tar -x -C {d}", shell=True, capture_output=True)
        open(d + '/.ok', 'w').write('1')
    return d
def run(job):
    repo, commit, parent, ver, side = job
    d = tree(repo, parent if side == 'pre' else commit, side)
    try:
        r = subprocess.run(['python3', W, SNAPS[ver], d], capture_output=True, text=True, timeout=180, cwd='/tmp')
        fs = json.loads(r.stdout) if r.stdout.strip() else [dict(layer='error', text=r.stderr[-300:])]
    except Exception as e: fs = [dict(layer='error', text=repr(e)[:200])]
    return dict(repo=repo, commit=commit, ver=ver, side=side, findings=fs)
if __name__ == '__main__':
    bugs = [json.loads(l) for l in open('data/bugs.jsonl')]
    bugs = [b for b in bugs if b['status'] in ('removed', 'adjacent')]
    out = 'data/checker_runs.jsonl'; done = set()
    if os.path.exists(out): done = {(j['repo'], j['commit'], j['ver'], j['side']) for j in map(json.loads, open(out))}
    jobs = [(b['repo'], b['commit'], b['parent'], v, s) for b in bugs for v in SNAPS for s in ('pre', 'post') if (b['repo'], b['commit'], v, s) not in done]
    with ThreadPoolExecutor(8) as ex, open(out, 'a') as f:
        for r in ex.map(run, jobs): f.write(json.dumps(r) + '\n'); f.flush()
    print('jobs', len(jobs))

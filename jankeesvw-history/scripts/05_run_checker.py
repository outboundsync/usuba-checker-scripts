#!/usr/bin/env python3
"""Run the Checker (two versions) on the PRE-fix and POST-fix checkout of every verified bug-fix commit.
Snapshots (git archive, committed state): /tmp/jh_snap/v2 <- branch checker-rules-v2 (57018c8), /tmp/jh_snap/v3fixes <- branch v3-fixes (763fe65); see docs/jankeesvw-history.md.
Output data/checker_runs.jsonl: {repo, commit, ver, side, findings:[...]} (resumable)."""
import json, os, subprocess, sys, tempfile
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from archive_util import git_archive
from concurrent.futures import ThreadPoolExecutor
ROOT = '/workspace/ref/jankeesvw'; T = '/tmp/jh_trees'; W = os.path.dirname(os.path.abspath(__file__)) + '/checker_worker.py'
SNAPS = {'v2': '/tmp/jh_snap/v2', 'v3fixes_763fe65': '/tmp/jh_snap/v3fixes', 'v3fixes_d00fcc0': '/tmp/jh_snap/v3fixes-head'}
os.makedirs(T, exist_ok=True)
def tree(repo, sha, tag):
    d = f'{T}/{repo}_{sha[:10]}_{tag}'
    if not os.path.exists(d + '/.ok'):
        git_archive(f'{ROOT}/{repo}', sha, d)
    return d
def run(job):
    repo, commit, parent, ver, side = job
    try:
        d = tree(repo, parent if side == 'pre' else commit, side)
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
        n_err = 0
        for r in ex.map(run, jobs):
            if any(x.get('layer') == 'error' for x in r['findings']): n_err += 1; continue   # audit A5: a failure is not a result; re-run retries it
            f.write(json.dumps(r) + '\n'); f.flush()
    print('jobs', len(jobs), 'errors (not recorded, will retry on re-run)', n_err)
    if n_err: sys.exit(1)

#!/usr/bin/env python3
"""Measure USB-JV rules: recall on the pre-fix defect (same file, +-5 lines, rule family matches the bug), whether the same rule is silent on the post-fix tree, false-fire rate on every
repo HEAD (his hardened code) and on a sample of other authors' plugins (/workspace/sweep_repos, fire counts only). Output data/jv_rules_metrics.json."""
import json, os, sys, collections, random, subprocess
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from archive_util import git_archive
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__))); import jv_rules as J
SN = '/tmp/jh_snap/v3fixes-head'; sys.path[:0] = [SN + '/functest']; import functest
ROOT = '/workspace/ref/jankeesvw'; T = '/tmp/jh_trees'
BUG = [json.loads(l) for l in open('data/bugs_final.jsonl')]; REAL = [b for b in BUG if b['real_defect']]
def read(d): return {p: c for p, c in functest.read_dir(d).items()}
res = {r: dict(summary=J.RULES[r], pre_hits_at_defect=[], pre_hits_elsewhere=0, post_still_fires_at_defect=0, head_fires=0, head_files=[], external_plugins_firing=0) for r in J.RULES}
pre_cache = {}
for b in REAL:
    pre = read(f"{T}/{b['repo']}_{b['parent'][:10]}_pre"); post = read(f"{T}/{b['repo']}_{b['commit'][:10]}_post")
    fp = J.check(pre); fq = J.check(post)
    for f in fp:
        near = f['file'] == b['file'] and abs(f['line'] - b['line']) <= 5
        if near: res[f['rule']]['pre_hits_at_defect'].append(b['id'].split(':', 1)[1])
        else: res[f['rule']]['pre_hits_elsewhere'] += 1
    for f in fq:
        if f['file'] == b['file'] and abs(f['line'] - b['line']) <= 8: res[f['rule']]['post_still_fires_at_defect'] += 1
for repo in sorted(os.listdir(ROOT)):
    if repo in ('omarchy-clippy', 'omarchy-time-machine'): continue
    d = f'{T}/{repo}_HEAD'
    if not os.path.exists(d + '/.ok'):
        git_archive(f'{ROOT}/{repo}', 'HEAD', d)
    for f in J.check(read(d)): res[f['rule']]['head_fires'] += 1; res[f['rule']]['head_files'].append(f"{repo}:{f['file']}:{f['line']}")
S = '/workspace/sweep_repos'; names = sorted(n for n in os.listdir(S) if not n.startswith('jankeesvw__')); random.Random(7).shuffle(names); names = names[:250]; n_ext = 0
for n in names:
    try: fs = read(f'{S}/{n}'); n_ext += 1
    except Exception: continue
    for r in {f['rule'] for f in J.check(fs)}: res[r]['external_plugins_firing'] += 1
for r, v in res.items(): v['pre_hits_at_defect_n'] = len(v['pre_hits_at_defect']); v['external_plugins_sampled'] = n_ext
json.dump(res, open('data/jv_rules_metrics.json', 'w'), indent=1)
for r, v in res.items(): print(r, 'recall@defect', v['pre_hits_at_defect_n'], 'elsewhere', v['pre_hits_elsewhere'], 'post-still', v['post_still_fires_at_defect'], 'HEAD fires', v['head_fires'], 'external', v['external_plugins_firing'], '/', n_ext)

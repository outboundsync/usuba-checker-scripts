#!/usr/bin/env python3
"""Inventory every commit (all refs, merges included) of the jankeesvw repos except the two excluded ones.
Output data/commits.jsonl. Inputs: /workspace/ref/jankeesvw/<repo> (full history)."""
import json, os, re, subprocess, sys
ROOT = '/workspace/ref/jankeesvw'
EXCLUDE = {'omarchy-clippy', 'omarchy-time-machine'}   # HANCORE holdout / existing holdout: never read
AUTHOR = 'Jankees van Woezik'
BIN = re.compile(r'\.(png|jpe?g|gif|webp|wav|mp3|ogg|flac|ico|icns|svg|ttf|otf|woff2?|gz|zip|tar|pdf|mp4|webm|gif|bin|so|a)$', re.I)
def g(d, *a):
    return subprocess.run(['git', '-C', d] + list(a), capture_output=True, text=True, errors='replace', timeout=120).stdout
out = []
for repo in sorted(os.listdir(ROOT)):
    if repo in EXCLUDE: continue
    d = f'{ROOT}/{repo}'
    raw = g(d, 'log', '--all', '--topo-order', '--format=%H%x1f%P%x1f%an%x1f%ae%x1f%aI%x1f%cI%x1f%s%x1f%b%x1e')
    commits = [c.strip('\n') for c in raw.split('\x1e') if c.strip()]
    n = len(commits)
    for i, c in enumerate(commits):
        h, par, an, ae, ad, cd, subj, body = (c.split('\x1f') + [''] * 8)[:8]
        parents = par.split()
        ns = g(d, 'diff', '--numstat', '--no-renames', (parents[0] if parents else '4b825dc642cb6eb9a060e54bf8d69288fbd3904'), h)
        files = []
        for l in ns.splitlines():
            p = l.split('\t')
            if len(p) != 3: continue
            isbin = p[0] == '-' or bool(BIN.search(p[2]))
            files.append(dict(path=p[2], add=0 if p[0] == '-' else int(p[0]), dele=0 if p[1] == '-' else int(p[1]), binary=isbin))
        out.append(dict(repo=repo, commit=h, parents=parents, is_merge=len(parents) > 1, author=an, author_email=ae, author_date=ad, commit_date=cd,
                        subject=subj, body=body.strip(), by_jankees=(an == AUTHOR), files=files, repo_commit_count=n))
os.makedirs('data', exist_ok=True)
with open('data/commits.jsonl', 'w') as f:
    for x in out: f.write(json.dumps(x) + '\n')
print(len(out), 'commits in', len({x['repo'] for x in out}), 'repos;', sum(x['by_jankees'] for x in out), 'by', AUTHOR, ';', sum(x['is_merge'] for x in out), 'merges')

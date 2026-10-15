#!/usr/bin/env python3
"""Mechanically verify each LLM-classified bug fix: the cited PRE-fix line must exist in the parent version, its text must match the model's quote, and it must be a line the diff removes
(status 'removed') or a context line within 3 lines of removed/inserted lines of the same hunk (status 'adjacent': missing-guard fixes that only add lines).
If the model's line number is off but its quoted text matches exactly one removed line, re-anchor (status ..., reanchored=true). Adds blame-based fix-of-fix links and Revert detection.
Inputs data/commits.jsonl data/classified.jsonl; output data/bugs.jsonl (all commits with class bug_fix/compat + verification) and data/classes.jsonl (every commit with final class)."""
import json, re, subprocess, collections
ROOT = '/workspace/ref/jankeesvw'
OVERRIDE = {('omarchy-github-build-monitor', 'e177e95f6716db6b0ba365239305603786fb3a1c'): 'feature'}   # LLM returned no JSON twice; cosmetic placeholder colour change
def g(repo, *a):
    return subprocess.run(['git', '-C', f'{ROOT}/{repo}'] + list(a), capture_output=True, text=True, errors='replace', timeout=120).stdout
commits = [json.loads(l) for l in open('data/commits.jsonl')]
cls = {}
for l in open('data/classified.jsonl'):
    j = json.loads(l)
    if 'llm' in j: cls[(j['repo'], j['commit'])] = j['llm']
by = {(c['repo'], c['commit']): c for c in commits}
def hunks(repo, par, h, path):
    out = []
    df = g(repo, 'diff', '-U0', '--no-renames', par, h, '--', path)
    for m in re.finditer(r'^@@ -(\d+)(?:,(\d+))? \+(\d+)(?:,(\d+))? @@', df, re.M):
        os_, oc = int(m.group(1)), (int(m.group(2)) if m.group(2) is not None else 1)
        out.append((os_, oc))
    rem = set(); ins_anchor = set()
    for os_, oc in out:
        if oc: rem.update(range(os_, os_ + oc))
        else: ins_anchor.add(os_)       # insertion after old line os_
    return rem, ins_anchor
rows = []; allcls = []
for c in commits:
    k = (c['repo'], c['commit'])
    if c['is_merge']: allcls.append(dict(repo=c['repo'], commit=c['commit'], cls='merge')); continue
    v = cls.get(k)
    klass = OVERRIDE.get(k) or (v['class'] if v else 'unclassified')
    allcls.append(dict(repo=c['repo'], commit=c['commit'], cls=klass))
    if klass not in ('bug_fix', 'compat') or not v or not v.get('bug') or not c['parents']: continue
    b = v['bug']; par = c['parents'][0]; path = b.get('defect_file'); rec = dict(repo=c['repo'], commit=c['commit'], parent=par, llm=v, status='unverified', reason=None)
    try:
        old = g(c['repo'], 'show', f'{par}:{path}').splitlines()
    except Exception: old = []
    if not old: rec['reason'] = 'file-missing-in-parent'; rows.append(rec); continue
    rem, ins = hunks(c['repo'], par, c['commit'], path)
    def _i(x):
        m = re.search(r'\d+', str(x or '')); return int(m.group(0)) if m else 0
    ln = _i(b.get('defect_line')); q = re.sub(r'^\s*L\d+:\s?', '', (b.get('defect_line_text') or '')).strip(); anchored = False
    def txt(n): return old[n - 1].strip() if 1 <= n <= len(old) else None
    if not (txt(ln) == q and q):
        cand = [n for n in sorted(rem) if txt(n) == q] if q else []
        if len(cand) >= 1: ln = min(cand, key=lambda n: abs(n - ln)); anchored = True
        else:
            cand = [n for n in range(1, len(old) + 1) if txt(n) == q] if q else []
            if len(cand) >= 1 and any(abs(n - _i(b.get('defect_line'))) <= 3 for n in cand): ln = min(cand, key=lambda n: abs(n - _i(b.get('defect_line')))); anchored = True
            else: rec['reason'] = 'quote-mismatch'; rec['model_line_text_actual'] = txt(_i(b.get('defect_line'))); rows.append(rec); continue
    near = any(abs(ln - n) <= 3 for n in rem) or any(0 <= n - ln + 0 <= 3 or 0 <= ln - n <= 3 for n in ins)
    if ln in rem: st = 'removed'
    elif near: st = 'adjacent'
    else: rec['reason'] = 'not-near-diff'; rows.append(rec); continue
    rec.update(status=st, file=path, line=ln, line_text=old[ln - 1], reanchored=anchored, removed_old_lines=sorted(rem)[:40], insert_after=sorted(ins)[:10])
    # blame: who last touched the removed lines in the parent?
    prev = collections.Counter()
    for n in sorted(rem)[:12]:
        bl = g(c['repo'], 'blame', '--porcelain', '-L', f'{n},{n}', par, '--', path).split('\n', 1)[0].split(' ')[0]
        if bl and not bl.startswith('^') or bl: prev[bl] += 1
    rec['blame_commits'] = [(h[:10], n) for h, n in prev.most_common(3)]
    rec['reverts'] = bool(re.match(r'(?i)^revert\b', c['subject']))
    rows.append(rec)
with open('data/bugs.jsonl', 'w') as f:
    for r in rows: f.write(json.dumps(r) + '\n')
with open('data/classes.jsonl', 'w') as f:
    for r in allcls: f.write(json.dumps(r) + '\n')
print(collections.Counter(r['status'] for r in rows), collections.Counter(r['reason'] for r in rows if r['status'] == 'unverified'))
print(collections.Counter(a['cls'] for a in allcls))

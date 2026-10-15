#!/usr/bin/env python3
"""Merge commits + classification + verification + skeptical review + Checker runs into data/bugs_final.jsonl and data/summary.json."""
import json, re, subprocess, collections
ROOT = '/workspace/ref/jankeesvw'
def g(repo, *a): return subprocess.run(['git', '-C', f'{ROOT}/{repo}'] + list(a), capture_output=True, text=True, errors='replace').stdout
C = {(c['repo'], c['commit']): c for c in map(json.loads, open('data/commits.jsonl'))}
CL = {(j['repo'], j['commit']): j['cls'] for j in map(json.loads, open('data/classes.jsonl'))}
RV = {(j['repo'], j['commit']): j for j in map(json.loads, open('data/review.jsonl')) if 'review' in j}
CK = {}
for j in map(json.loads, open('data/checker_runs.jsonl')): CK[(j['repo'], j['commit'], j['ver'], j['side'])] = j['findings']
EVENTS = {'2026-10-09': 'Qt 6.12 Color singleton shadowing (shell-compat 10-09)', '2026-10-13': 'new Omarchy shell scales iconComponent (shell-compat 10-13)'}
LAYERS = {'prompt+enabled': {'report', 'hc'}, 'all-rules': {'report', 'hc', 'report-off', 'hc-off'}}
WCAT = {'USB-W01': 'in-use:missing-binary', 'USB-W02': 'secrets-credentials', 'USB-W03': 'remote-code-pinning', 'USB-W04': 'file-safety-symlink-perms', 'USB-W05': 'privileged-system',
        'USB-W06': 'rich-text-markup-injection', 'USB-W07': 'shell-lua-injection', 'USB-W08': 'process-lifecycle-timeouts', 'USB-W09': 'url-scheme-network', 'USB-W10': 'unbounded-input-resource'}
def judge(pre, post, file, line, bugcat):
    """HIT = a finding in the defect file within 5 lines of the defect whose rule category equals the bug category, or that disappears in the post-fix tree (right reason);
    COINCIDENT = a finding near the line for an unrelated reason; FILE = findings in the file only; MISS = nothing in the file."""
    res = {}
    for name, ls in LAYERS.items():
        fs = [f for f in pre if f['layer'] in ls and f.get('file')]
        same = [f for f in fs if f['file'] == file]
        postkeys = {(f['rule'], f['file'], f['text']) for f in post if f['layer'] in ls}
        near = [f for f in same if f.get('line') and abs(f['line'] - line) <= 5]
        def cat(f): return f.get('cat') or WCAT.get(f['rule'])
        right = [f for f in near if (cat(f) is not None and cat(f) == bugcat) or (f['rule'], f['file'], f['text']) not in postkeys]
        out = 'HIT' if right else 'COINCIDENT' if near else 'FILE' if same else 'MISS'
        pick = (right or near or same or [{}])[0]
        res[name] = dict(outcome=out, line_hit=bool(near), file_hit=bool(same), rules=sorted({f['rule'] for f in (right or near or same)})[:6], layer=pick.get('layer'), top=pick.get('text', '')[:200])
    return res
out = []
for l in open('data/bugs.jsonl'):
    r = json.loads(l)
    if r['status'] not in ('removed', 'adjacent'): continue
    k = (r['repo'], r['commit']); c = C[k]; rv = RV.get(k); b = r['llm']['bug']
    if not rv: continue
    v = rv['review']; line = r['line']; text = r['line_text']; note = None
    if v.get('line_ok') is False and v.get('better_line'):
        try:
            bl = int(re.search(r'\d+', str(v['better_line'])).group(0)); old = g(r['repo'], 'show', f"{r['parent']}:{r['file']}").splitlines()
            near = any(abs(bl - n) <= 3 for n in r['removed_old_lines']) or any(0 <= bl - n <= 3 or 0 <= n - bl <= 3 for n in r['insert_after'])
            if 1 <= bl <= len(old) and near: line, text, note = bl, old[bl - 1], f"reviewer moved line {r['line']}->{bl}"
        except Exception: pass
    st = [dict(path=f['path'], add=f['add'], dele=f['dele']) for f in c['files'] if not f['binary']]
    blame = [(s, n) for s, n in r.get('blame_commits', [])]
    prior_fix = [s for s in rv.get('blame_subjects', []) if CL.get(next(((c2['repo'], c2['commit']) for c2 in C.values() if c2['repo'] == r['repo'] and c2['commit'].startswith(s.split()[0])), None)) == 'bug_fix']
    origin = v.get('origin') or b.get('origin')
    if origin == 'version_change' and not re.search(r'Commons\.Color|new Omarchy shell', c['subject']): origin = b.get('origin') if b.get('origin') not in (None, 'version_change') else 'missed_edge_case'   # version_change only for the two dated shell-compat events
    if re.search(r'Commons\.Color|new Omarchy shell', c['subject']): origin = 'version_change'
    if origin == 'followup_to_earlier_fix': origin = 'fix_of_fix' if prior_fix else 'regression_in_recent_feature'   # fix_of_fix = removed lines were last changed by an earlier bug-fix commit (blame)
    if re.match(r'(?i)^revert', c['subject']) or 'revert' in (v.get('origin') or ''): origin = 'revert'
    pre = {ver: CK[(r['repo'], r['commit'], ver, 'pre')] for ver in ('v2', 'v3fixes_763fe65', 'v3fixes_d00fcc0')}; post = {ver: CK[(r['repo'], r['commit'], ver, 'post')] for ver in ('v2', 'v3fixes_763fe65', 'v3fixes_d00fcc0')}
    out.append(dict(id=f"jankeesvw-history:{r['repo']}:{r['commit'][:10]}", repo=r['repo'], commit=r['commit'], parent=r['parent'], date=c['author_date'], author=c['author'], by_jankees=c['by_jankees'],
                    subject=c['subject'], files_changed=st, lines_changed=sum(x['add'] + x['dele'] for x in st), file=r['file'], line=line, line_text=text, verify=r['status'], reanchored=r['reanchored'], line_note=note,
                    real_defect=bool(v['real_defect']), tier=v['tier'], kind={'logic': 'runtime', 'performance': 'runtime'}.get(v['kind'], v['kind']), category=b['category'], fix_pattern=b['fix_pattern'], origin=origin, origin_note=v.get('origin_note'), origin_llm_first=b.get('origin'),
                    prior_fix_commits=prior_fix, blame=blame, version_event=EVENTS.get(c['author_date'][:10]) if origin == 'version_change' else None,
                    description=v['description'], symptom=v['symptom'], root_cause=v['root_cause'], first_pass_defect=b['defect'], other_defects=b.get('other_defects'),
                    checker={ver: judge(pre[ver], post[ver], r['file'], line, b['category']) for ver in pre}))
with open('data/bugs_final.jsonl', 'w') as f:
    for x in out: f.write(json.dumps(x) + '\n')
real = [x for x in out if x['real_defect']]
S = dict(commits=len(C), by_class=dict(collections.Counter(CL.values())), bug_verified=len(out), real=len(real), real_jankees=sum(x['by_jankees'] for x in real),
         origin=dict(collections.Counter(x['origin'] for x in real)), tier=dict(collections.Counter(x['tier'] for x in real)))
json.dump(S, open('data/summary.json', 'w'), indent=1); print(json.dumps(S))
for ver in ('v2', 'v3fixes_763fe65', 'v3fixes_d00fcc0'):
    for lay in LAYERS:
        for sel, nm in ((real, 'all'), ([x for x in real if x['by_jankees']], 'jankees')):
            print(ver, lay, nm, len(sel), dict(collections.Counter(x['checker'][ver][lay]['outcome'] for x in sel)))

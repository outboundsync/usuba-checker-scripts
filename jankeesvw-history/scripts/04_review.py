#!/usr/bin/env python3
"""Second, skeptical pass (qwen/qwen3.5-397b-a17b via OpenRouter, no reasoning, temp 0) over every mechanically verified bug fix: is the PRE-fix line a concrete defect on its own, and
write the plain-words description used in the training row. Input data/bugs.jsonl (status removed/adjacent). Output data/review.jsonl (resumable)."""
import json, os, re, subprocess, sys, urllib.request
from concurrent.futures import ThreadPoolExecutor, as_completed
KEY = os.environ['OPENROUTER_API_KEY']; MODEL = 'qwen/qwen3.5-397b-a17b'; BUDGET = float(os.environ.get('BUDGET', '1.5'))
ROOT = '/workspace/ref/jankeesvw'
def g(repo, *a): return subprocess.run(['git', '-C', f'{ROOT}/{repo}'] + list(a), capture_output=True, text=True, errors='replace', timeout=120).stdout
C = {(c['repo'], c['commit']): c for c in map(json.loads, open('data/commits.jsonl'))}
def excerpt(r, n=14):
    old = g(r['repo'], 'show', f"{r['parent']}:{r['file']}").splitlines()
    a = max(1, r['line'] - n); b = min(len(old), r['line'] + n)
    return '\n'.join(f"{i}{'>' if i == r['line'] else ' '} {old[i-1]}" for i in range(a, b + 1))
def fixdiff(r, cap=3500):
    return g(r['repo'], 'diff', '-U2', '--no-renames', r['parent'], r['commit'], '--', r['file'])[:cap]
PROMPT = """You are an experienced Omarchy (Quickshell/QML + helper scripts) plugin developer. A commit in repo {repo} ({date}) changed `{file}`. Subject: {subject}
Omarchy shell compat events: 2026-10-09 (Qt 6.12 `Color` singleton shadowed by Qt's own type, fix = `Commons.Color`) and 2026-10-13 (new Omarchy shell scales `iconComponent` to bar icon size).
Earlier commits that last touched the changed lines: {blame}
PRE-fix file (line numbers; `>` marks the line proposed as the defect):
{excerpt}
The fix diff:
{diff}

Judge strictly. Answer JSON only:
{{"real_defect": true/false  (false if the pre-fix code at/around the marked line was not wrong on its own: cosmetic preference, new feature, refactor, performance nicety without a failure, documentation wording, a comment, or a version bump),
 "tier": "A" (functional failure, crash, hang, data loss, security or breakage on a newer shell/Qt) or "B" (visible but cosmetic/UX/perf polish),
 "line_ok": true/false (does the marked line itself, or the statement it belongs to, exhibit the defect; if false give "better_line": <number from the excerpt>),
 "description": "ONE or TWO plain sentences stating what is wrong at that line in the code as it stands, naming the construct in backticks and what goes wrong and when. No words like commit, fix, review, should, consider. Under 300 characters.",
 "symptom": "<=25 words: what the user or shell sees, and the trigger",
 "root_cause": "<=25 words",
 "kind": one of ["load","qml","runtime","in-use","config","packaging","security"],
 "origin": one of ["version_change","missed_edge_case","followup_to_earlier_fix","revert","original_bug"],
 "origin_note": "<=20 words, naming the earlier commit sha if followup/revert, else null"}}"""
def ask(r):
    c = C[(r['repo'], r['commit'])]
    bl = []
    for sha, n in r.get('blame_commits', []):
        full = g(r['repo'], 'rev-parse', sha).strip()
        s = g(r['repo'], 'log', '-1', '--format=%h %ad %s', '--date=short', full).strip()
        bl.append(s)
    p = PROMPT.format(repo=r['repo'], date=c['author_date'][:10], file=r['file'], subject=c['subject'], blame='; '.join(bl) or 'n/a', excerpt=excerpt(r), diff=fixdiff(r))
    req = dict(model=MODEL, messages=[dict(role='user', content=p)], max_tokens=600, temperature=0, reasoning=dict(enabled=False), usage=dict(include=True), response_format=dict(type='json_object'))
    err = None
    for t in range(3):
        try:
            rq = urllib.request.Request('https://openrouter.ai/api/v1/chat/completions', json.dumps(req).encode(), {'Authorization': 'Bearer ' + KEY, 'Content-Type': 'application/json'})
            j = json.load(urllib.request.urlopen(rq, timeout=90)); txt = j['choices'][0]['message']['content'] or ''
            return dict(repo=r['repo'], commit=r['commit'], review=json.loads(re.search(r'\{.*\}', txt, re.S).group(0)), cost=j.get('usage', {}).get('cost') or 0, blame_subjects=bl)
        except Exception as e: err = str(e)[:100]
    return dict(repo=r['repo'], commit=r['commit'], error=err)
if __name__ == '__main__':
    out = 'data/review.jsonl'; done = set()
    if os.path.exists(out): done = {(j['repo'], j['commit']) for j in map(json.loads, open(out)) if 'review' in j}
    todo = [r for r in map(json.loads, open('data/bugs.jsonl')) if r['status'] in ('removed', 'adjacent') and (r['repo'], r['commit']) not in done]
    ex = ThreadPoolExecutor(12); f = open(out, 'a'); spent = 0.0
    futs = [ex.submit(ask, r) for r in todo]
    try:
        for fu in as_completed(futs, timeout=int(os.environ.get('WALL', '600'))):
            x = fu.result(); spent += x.get('cost', 0) or 0; f.write(json.dumps(x) + '\n'); f.flush()
            if spent > BUDGET: break
    except Exception as e: print('wall-clock stop', type(e).__name__)
    ex.shutdown(wait=False, cancel_futures=True); print('spent', round(spent, 3), 'n', len(todo))

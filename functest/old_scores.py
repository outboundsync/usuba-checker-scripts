#!/usr/bin/env python3
"""Recompute the OLD shallow score (validator/validate.py on the eval_local.py stub tree) for every gen file,
so models without a scores_*.json (the *_big runs) get a like-for-like old number. qmllint is not re-run."""
import json, os, re, sys, glob
ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__))); sys.path.insert(0, os.path.join(ROOT, "validator"))
from validate import validate_files
from build_parse import parse
RUN = os.path.join(ROOT, "runs/smoke-2026-10-11")
hold = [json.loads(l) for l in open(os.path.join(ROOT, "data/holdout.jsonl"))]
def old_row(h, g):
    task = h['task'].split(':')[0]; files = parse(g['output'])
    full = task in ('build_from_spec', 'add_panel')
    if full or not h['meta'].get('validate_tree') and task != 'fix_manifest': tree = dict(files)
    else:
        tree = {m.group(1): 'x\n' for m in re.finditer(r'^- (\S+) \(\d+ KB\)', h['messages'][1]['content'], re.M)}
        ref = parse(h['messages'][2]['content'])
        um = re.search(r'Other files in the folder: (.*)', h['messages'][1]['content'])
        if um: tree.update({p.strip(): 'x\n' for p in um.group(1).split(',') if p.strip()})
        pm = re.search(r'```json\n(.*?)\n```', h['messages'][1]['content'], re.S)
        if pm and task != 'fix_manifest': tree['manifest.json'] = pm.group(1) + '\n'
        for p in ref: tree.setdefault(p, 'x\n')
        if task == 'fix_manifest':
            tree.update({p: 'x\n' for p in ref if p != 'manifest.json'}); tree.pop('manifest.json', None)
        tree.update(files)
        if 'manifest.json' not in tree and 'manifest.json' in ref: tree['manifest.json'] = ref['manifest.json']
    safe = {p: c for p, c in tree.items() if '..' not in p and not p.startswith('/')}
    return (validate_files(safe) if files else 'no files parsed') is None
def old(name):
    if name == "REFERENCE": gens = [{"output": h["messages"][2]["content"]} for h in hold]
    else: gens = [json.loads(l) for l in open(os.path.join(RUN, f"gen_{name}.jsonl"))]
    rows = [old_row(h, g) for h, g in zip(hold, gens)]
    full = [r for r, h in zip(rows, hold) if h['task'].split(':')[0] in ('build_from_spec', 'add_panel')]
    return rows, f"{sum(rows)}/{len(rows)}", f"{sum(full)}/{len(full)}"
if __name__ == "__main__":
    for f in sorted(glob.glob(os.path.join(RUN, "gen_*.jsonl"))):
        n = os.path.basename(f)[4:-6]; _, a, b = old(n); print(n, a, b)

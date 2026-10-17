#!/usr/bin/env python3
"""Pick the HANCORE held-out eval set (run FIRST; everything else excludes these plugins).
Positives: plugins whose findings at the reviewed commit include a fixed/confirmed one, stratified round-robin over the target categories.
Negatives: plugins HANCORE reviewed (at a known commit) with no findings and an approval / listing."""
import sys, os, random, json, collections
H = os.path.dirname(os.path.abspath(__file__)); sys.path.insert(0, os.path.join(H, "../../hancore"))
import common, fetch
CATS = ["install-deps-packaging", "unbounded-input-resource", "file-safety-symlink-perms", "secrets-credentials", "privileged-system",
        "process-lifecycle-timeouts", "remote-code-pinning", "url-scheme-network", "rich-text-markup-injection", "shell-lua-injection", "scope-policy-duplicate"]
N_POS, PER = 300, 300 // len(CATS) + 1
rng = random.Random(1337); d = common.load()
cand = {c: sorted(p for p, v in d.items() if v["sha"] and any(x["fixed"].startswith("fixed:") and c in x["categories"] for x in v["gt"])) for c in CATS}
for c in CATS: rng.shuffle(cand[c])
chosen, why = [], {}
def ok(p):
    return fetch.fetch(common.repo_of(p), d[p]["sha"]) is not None and len(fetch.read_files(fetch.fetch(common.repo_of(p), d[p]["sha"]))) > 0
cnt = collections.Counter()
while len(chosen) < N_POS:
    prog = False
    for c in sorted(CATS, key=lambda c: cnt[c]):
        while cand[c]:
            p = cand[c].pop()
            if p in why: continue
            if ok(p): chosen.append(p); why[p] = c; cnt[c] += 1; prog = True; break
        if len(chosen) >= N_POS: break
    if not prog: break
negs = sorted(p for p, v in d.items() if v["sha"] and not v["findings"] and (v["approved"] or v["listed"]))
negs = [p for p in negs if ok(p)]
os.makedirs(H + "/code", exist_ok=True)
man = []
import tarfile
for p, label in [(p, "positive") for p in chosen] + [(p, "negative") for p in negs]:
    v = d[p]; src = fetch.fetch(common.repo_of(p), v["sha"])
    files = sorted(fetch.read_files(src))
    arc = f"code/{common.repo_of(p).replace('/', '__')}@{v['sha'][:12]}.tar.gz"
    with tarfile.open(os.path.join(H, arc), "w:gz") as t: t.add(src, arcname=".", filter=lambda ti: None if ti.name.endswith((".ok", ".fail")) else ti)
    man.append(dict(plugin=p, repo=common.repo_of(p), commit=v["sha"], label=label, strata=why.get(p),
        threads=sorted({x["thread"] for x in v["items"]}), code_archive=arc, n_files=len(files),
        findings=[dict(url=x["url"], categories=x["categories"], fixed=x["fixed"], strength=common.strength(x["fixed"]), heading=x["heading"][:300]) for x in v["gt"]]))
with open(H + "/manifest.jsonl", "w") as f:
    for m in man: f.write(json.dumps(m) + "\n")
open(H + "/plugin_ids.txt", "w").write("\n".join(m["plugin"] for m in man) + "\n")
print(len(chosen), len(negs), dict(cnt))

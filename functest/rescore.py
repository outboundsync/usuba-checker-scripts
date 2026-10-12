#!/usr/bin/env python3
"""Rescore runs/smoke-2026-10-11/gen_*.jsonl with the functional test.
Full-plugin tasks (build_from_spec, add_panel): the model's files ARE the plugin.
Tree tasks (chunk_*, fix_manifest): model files are overlaid on the real upstream plugin tree at the holdout commit
(sources/repos/<id>, or Omarchy's first-party dir); failures already present in the untouched upstream tree
(baseline) are subtracted, so only regressions caused by the model count."""
import json, os, re, sys, glob, hashlib, collections
from concurrent.futures import ThreadPoolExecutor
HERE = os.path.dirname(os.path.abspath(__file__)); ROOT = os.path.dirname(HERE)
sys.path.insert(0, HERE); sys.path.insert(0, os.path.join(ROOT, "validator"))
import functest
from build_parse import parse
RUN = os.path.join(ROOT, "runs/smoke-2026-10-11")
hold = [json.loads(l) for l in open(os.path.join(ROOT, "data/holdout.jsonl"))]
FULL = ("build_from_spec", "add_panel")
REPO_FOR = {"https://github.com/salted-sorbet/salted.bar": "salted.bar", "https://github.com/RohitKaushal7/omarchy-beam": "dev.reuk.beam",
            "https://github.com/pxllbt/better-bar": "pix.bar", "https://github.com/TECHNOCRAFT27/floating-waybar": "floating-waybar",
            "https://github.com/varlet99/omarchy-tablet": "surface.tablet", "https://github.com/jankeesvw/omarchy-time-machine": "jankeesvw.time-machine",
            "https://github.com/scottjones/omarchy-flush-bar": "scottjones.flush-bar"}
def tree_dir(h):
    m = h["meta"]
    if m["origin"] == "first-party": return "/opt/ft/omarchy/" + m["plugin_path"]
    return os.path.join(ROOT, "sources/repos", REPO_FOR[m["repo"]])
CACHE = os.path.join(HERE, "cache"); os.makedirs(CACHE, exist_ok=True)

def norm(e): return re.sub(r"\d+", "N", re.sub(r"/opt/ft/runs/\w+", "", e))

def build_tree(h, files):
    task = h["task"].split(":")[0]
    base = functest.read_dir(tree_dir(h))
    prompt = h["messages"][1]["content"]
    pm = re.search(r"```json\n(.*?)\n```", prompt, re.S)
    if task == "fix_manifest":
        base.pop("manifest.json", None)                    # model must supply the fixed manifest
    elif pm and task != "chunk_manifest_entry":
        base["manifest.json"] = pm.group(1) + "\n"        # the manifest as given in the prompt
    if task == "chunk_manifest_entry":
        # model writes manifest + entry file(s): drop upstream versions of those
        ref = parse(h["messages"][2]["content"])
        for p in ref: base.pop(p, None)
    t = dict(base); t.update({p: c for p, c in files.items() if ".." not in p and not p.startswith("/")})
    return base, t

_baseline = {}
def baseline(i, h):
    if i in _baseline: return _baseline[i]
    ref = parse(h["messages"][2]["content"])
    _, t = build_tree(h, ref)                              # upstream tree + reference answer = known-good state
    r = functest.test(files=t)
    _baseline[i] = ({tuple(x) for x in r["static_fails"]}, {norm(e) for e in (r["runtime"] or {}).get("errors", [])}, r)
    return _baseline[i]

def score_row(i, h, g):
    task = h["task"].split(":")[0]
    files = parse(g["output"])
    if not files: return dict(task=h["task"], pass_=False, categories=["no-files-parsed"], finish=g["finish"])
    if task in FULL:
        key = hashlib.sha1(json.dumps(files, sort_keys=True).encode()).hexdigest()
        cp = os.path.join(CACHE, key + ".json")
        if os.path.exists(cp): r = json.load(open(cp))
        else:
            r = functest.test(files=files); json.dump(r, open(cp, "w"))
    else:
        bs, br, _ = baseline(i, h)
        _, t = build_tree(h, files)
        key = hashlib.sha1(json.dumps(t, sort_keys=True).encode()).hexdigest()
        cp = os.path.join(CACHE, key + ".json")
        if os.path.exists(cp): r = json.load(open(cp))
        else:
            r = functest.test(files=t); json.dump(r, open(cp, "w"))
        r = json.loads(json.dumps(r))
        r["static_fails"] = [x for x in r["static_fails"] if tuple(x) not in bs]
        if r["runtime"]:
            r["runtime"]["errors"] = [e for e in r["runtime"]["errors"] if norm(e) not in br]
            r["runtime"]["pass"] = not r["runtime"]["errors"]
        r["categories"] = functest.categories(r["static_fails"], r["runtime"])
        r["pass"] = not r["static_fails"] and (r["runtime"] is None or r["runtime"]["pass"])
    rt = r.get("runtime") or {}
    return dict(task=h["task"], pass_=bool(r["pass"]), categories=r["categories"], finish=g["finish"],
                static_fails=[f"{a}: {b}"[:200] for a, b in r["static_fails"]][:8],
                runtime_errors=[e[:240] for e in rt.get("errors", [])][:8], runtime_checks=rt.get("checks"),
                soft=[e[:160] for e in rt.get("soft", [])][:4], files=sorted(files)[:12])

def summarize(rows, old):
    full = [r for r in rows if r["task"].split(":")[0] in FULL]
    per = collections.defaultdict(lambda: [0, 0])
    for r in rows: t = r["task"].split(":")[0]; per[t][0] += r["pass_"]; per[t][1] += 1
    cats = collections.Counter(c for r in rows if not r["pass_"] for c in r["categories"])
    return dict(new_overall=f"{sum(r['pass_'] for r in rows)}/{len(rows)}", new_full_plugin=f"{sum(r['pass_'] for r in full)}/{len(full)}",
                old_overall=old.get("validate_pass"), old_full_plugin=old.get("full_plugin_pass"),
                per_task={k: f"{a}/{b}" for k, (a, b) in per.items()}, failure_categories=dict(cats.most_common()),
                truncated=sum(r["finish"] == "length" for r in rows))

if __name__ == "__main__":
    names = sys.argv[1:] or sorted(os.path.basename(f)[4:-6] for f in glob.glob(os.path.join(RUN, "gen_*.jsonl")))
    old = json.load(open(os.path.join(RUN, "summary.json")))
    # old shallow scores for models missing from summary.json: recompute from scores_*.json
    def old_for(n):
        if n in old: return old[n]
        p = os.path.join(RUN, f"scores_{n}.json")
        if not os.path.exists(p): return {}
        s = json.load(open(p)); f = [r for r in s if r["task"].split(":")[0] in FULL]
        return {"validate_pass": f"{sum(r['pass_'] for r in s)}/{len(s)}", "full_plugin_pass": f"{sum(r['pass_'] for r in f)}/{len(f)}"}
    # baselines first (sequential per tree; cheap)
    with ThreadPoolExecutor(8) as ex:
        list(ex.map(lambda i: baseline(i, hold[i]), [i for i, h in enumerate(hold) if h["task"].split(":")[0] not in FULL]))
    out_path = os.path.join(HERE, "results.json")
    results = json.load(open(out_path)) if os.path.exists(out_path) else {"models": {}, "rows": {}}
    for n in names:
        if n == "REFERENCE": gens = [{"output": h["messages"][2]["content"], "finish": "stop"} for h in hold]
        else: gens = [json.loads(l) for l in open(os.path.join(RUN, f"gen_{n}.jsonl"))]
        with ThreadPoolExecutor(8) as ex:
            rows = list(ex.map(lambda a: score_row(*a), [(i, hold[i], g) for i, g in enumerate(gens)]))
        results["rows"][n] = rows
        results["models"][n] = summarize(rows, old_for(n))
        print(n, json.dumps({k: results["models"][n][k] for k in ("old_overall", "new_overall", "old_full_plugin", "new_full_plugin")}), flush=True)
        json.dump(results, open(out_path, "w"), indent=1)

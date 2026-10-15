#!/usr/bin/env python3
"""Audit (v3-fixes task 4): approve rows whose tree breaks the lifecycle/manifest contract, and the Dell-sweep labels that a stale static rule produced.
For every row (jsonl / jsonl.gz, last user message holds the files as `### path` + fenced code): parse the files, run lifecycle_rules (all rules on) and report
  - approve rows (verdict approve) where USB-L01 (overlay/panel/menu without open+close, service-driven HUDs excluded), USB-N01, USB-N02 or USB-L03 fire  -> `drop_or_relabel`
  - broken rows for the same rules (confirmations)
  - rows whose few-shot prefix still carries the old shot 6 (overlay with only toggle()) -> `old_prefix`  (fix = prompt_v3.rebuild)
and, with --pool, the pool plugins whose Dell-sweep label is `broken` only because of `bad-import` that the manifest-scoped import check no longer reports (label_noise.json).
No deletions: outputs are lists; r3 decides. usage: python3 hancore/audit_lifecycle.py --rows A.jsonl.gz B.jsonl.gz --out /workspace/usuba-runs/v3-fixes [--pool]"""
import sys, os, json, gzip, re, argparse, collections
H = os.path.dirname(os.path.abspath(__file__)); ROOT = os.path.dirname(H)
sys.path[:0] = [os.path.join(ROOT, "functest/usuba"), os.path.join(ROOT, "functest"), H]
import lifecycle_rules as LR
FENCE = re.compile(r"^### (.+?)\n```\n(.*?)\n```(?=\n\n### |\Z)", re.S | re.M)
OLD6 = "function toggle() { opened = !opened }\n  Process { id: launch"
def parse_files(user):
    code = user.split("## Plugin source\n", 1)[-1]
    return {m.group(1): m.group(2) for m in FENCE.finditer(code)}
def opener(p): return gzip.open(p, "rt") if p.endswith(".gz") else open(p)
def main():
    ap = argparse.ArgumentParser(); ap.add_argument("--rows", nargs="*", default=[]); ap.add_argument("--out", default="/workspace/usuba-runs/v3-fixes"); ap.add_argument("--pool", action="store_true")
    a = ap.parse_args(); os.makedirs(a.out, exist_ok=True); allr = set(LR.RULES) - {"USB-W14"}
    res = dict(files={}, drop_or_relabel=[], confirmed_broken=[], old_prefix=0)
    for fn in a.rows:
        c = collections.Counter(); n = 0
        for l in opener(fn):
            r = json.loads(l); n += 1; msgs = r["messages"]
            if any(OLD6 in m["content"] for m in msgs[:-2]): res["old_prefix"] += 1; c["old_prefix"] += 1
            users = [m for m in msgs if m["role"] == "user"]; files = parse_files(users[-1]["content"])
            if "manifest.json" not in files: c["no_manifest_in_prompt"] += 1; continue
            hit = sorted({f["rule"] for f in LR.check(files, enabled=allr) if f["rule"] in ("USB-L01", "USB-N01", "USB-N02", "USB-L03")})
            if not hit: continue
            c["fires"] += 1; ent = dict(file=os.path.basename(fn), id=r.get("id"), source=r.get("source"), verdict=r.get("verdict"), label=r.get("label"), rules=hit)
            if r.get("verdict") == "approve": res["drop_or_relabel"].append(ent); c["approve_fires"] += 1
            else: res["confirmed_broken"].append(ent)
        res["files"][fn] = dict(rows=n, **c)
    # which rules / sources among the approve offenders
    res["approve_offenders_by_rule"] = dict(collections.Counter(r for e in res["drop_or_relabel"] for r in e["rules"]))
    res["approve_offenders_by_source"] = dict(collections.Counter(e["source"] for e in res["drop_or_relabel"]))
    json.dump(res, open(a.out + "/audit_rows.json", "w"), indent=1)
    print(json.dumps({k: v for k, v in res.items() if k not in ("drop_or_relabel", "confirmed_broken")}, indent=1))
    if a.pool:
        import static_checks as N   # the in-repo functest/static_checks.py (was: sys.path.insert(0, "/tmp"), i.e. whatever sits in a world-writable dir)
        import importlib.util as U
        spec = U.spec_from_file_location("static_old", os.path.join(a.out, "static_checks_before.py")); O = U.module_from_spec(spec); spec.loader.exec_module(O)
        from rules_v2_pool import read_tree
        pool = json.load(open("/workspace/usuba-runs/checker-rules/pool.json")); noise = []
        for repo, r in pool.items():
            if r["label"] != "broken": continue
            f = read_tree(r["src"]); a_ = O.check(f)[0]; b_ = N.check(f)[0]
            if any(x[0] == "bad-import" for x in a_) and not any(x[0] == "bad-import" for x in b_) and not b_:
                noise.append(dict(repo=repo, split=r["split"], old=[x for x in a_ if x[0] == "bad-import"][:3]))
        json.dump(noise, open(a.out + "/label_noise.json", "w"), indent=1); print("broken plugins whose only static failure was an out-of-scope bad-import:", len(noise), collections.Counter(x["split"] for x in noise))
if __name__ == "__main__": main()

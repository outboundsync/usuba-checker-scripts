#!/usr/bin/env python3
"""Model-assisted rule proposal (open-weights model via OpenRouter only: qwen/qwen3.5-397b-a17b).
Input: DESIGN-split HANCORE finding prose + flagged source snippet (+ the existing rule summaries). Output: candidate detection specs -> cands_raw/*.json.
Never reads test split, Dell key or holdout. The API key is read from the environment and is never printed or logged."""
import sys, os, json, random, re, time, hashlib, collections, urllib.request
H = os.path.dirname(os.path.abspath(__file__)); ROOT = os.path.dirname(H); sys.path[:0] = [H, os.path.join(ROOT, "functest/usuba")]
OUT = "/workspace/usuba-runs/checker-rules"; MODEL = "qwen/qwen3.5-397b-a17b"
CATS = ["secrets-credentials", "file-safety-symlink-perms", "url-scheme-network", "remote-code-pinning", "rich-text-markup-injection", "shell-lua-injection", "process-lifecycle-timeouts"]
SPEC = """Each candidate is a JSON object:
{"name": short title, "category": one of the category ids, "summary": one line,
 "file_types": list from [".sh",".py",".qml",".js",".lua"] (extensionless shell scripts count as .sh),
 "line_regex": Python `re` regex searched against ONE source line (comment-only lines are already dropped),
 "line_exclude_regex": optional regex; line is skipped if it matches,
 "file_must_contain_regex": optional regex that must match somewhere in the same file (multiline text),
 "file_must_not_contain_regex": optional regex; if it matches anywhere in the file the rule does not fire (the mitigation),
 "window_must_not_contain_regex": optional regex checked against the matched line plus the next 5 lines (a local mitigation),
 "ignore_case": bool,
 "why": what vulnerability this indicates, "example_hit": a line from the examples it should match, "example_ok": a safe line it must not match}
Rules must be precise: they will be rejected unless, on a large corpus of ~3,800 plugins, they fire on plugins with a matching HANCORE finding at least 1.5x more often than the base rate and fire on <=5% of plugins that HANCORE found no such issue in. Prefer specific, structural patterns over broad keywords; avoid regexes with nested quantifiers."""
def post(body):
    req = urllib.request.Request("https://openrouter.ai/api/v1/chat/completions", data=json.dumps(body).encode(),
        headers={"Authorization": "Bearer " + os.environ["OPENROUTER_API_KEY"], "Content-Type": "application/json", "HTTP-Referer": "https://github.com/", "X-Title": "usuba-checker-rules"})
    with urllib.request.urlopen(req, timeout=600) as r: return json.load(r)
def examples(cat, split="design"):
    pool = json.load(open(OUT + "/pool.json")); F = json.load(open(OUT + "/findings.json")); hits = {}
    for l in open(OUT + "/hits.jsonl"): d = json.loads(l); hits[d["repo"]] = d["hits"]
    ex = []
    from rules_v2_pool import read_tree
    import measure_v3 as M
    for repo, fl in F.items():
        r = pool[repo]
        if r["split"] != split: continue
        for f in fl:
            if f["cat"] != cat or f["clean"] or not f["files"]: continue
            # cited file:line with line > 0
            cands = [(fn, ln) for fn, ls in f["files"].items() for ln in ls if ln > 0]
            if not cands: continue
            caught = any(M.fmatch(h["file"], fn) for h in hits.get(repo, []) for fn, _ in cands)
            ex.append(dict(repo=repo, src=r["src"], text=f["text"], cands=cands[:3], caught=caught, kinds=f["kinds"]))
    return ex
def snippet(src, fn, ln, tree_cache):
    if src not in tree_cache:
        from rules_v2_pool import read_tree
        tree_cache[src] = read_tree(src)
    t = tree_cache[src]
    key = next((p for p in t if p == fn or p.endswith("/" + fn) or os.path.basename(p) == os.path.basename(fn)), None)
    if not key: return None
    L = t[key].split("\n"); a = max(0, ln - 6); b = min(len(L), ln + 5)
    return key, "\n".join(f"{i+1}: {L[i][:220]}" for i in range(a, b))
def build_prompt(cat, exs, existing):
    parts = [f"You are helping write static detection rules for a linter that checks Omarchy/Quickshell/Hyprland desktop-plugin source (QML, JS, shell, Python, Lua).\nTarget category: {cat}.\nBelow are real findings from a human security reviewer (HANCORE) with the source lines they cite. Existing rules for this category already cover: {existing}\nPropose NEW candidate rules (up to 8) that would flag code like these examples and generalise to other plugins, emphasising patterns the existing rules miss.\n\n{SPEC}\n\nReply with ONLY a JSON array of candidate objects, no prose.\n\nEXAMPLES:"]
    for i, e in enumerate(exs, 1):
        parts.append(f"--- example {i} (file {e['file']})\nREVIEWER FINDING: {re.sub(chr(10)+'+', ' ', e['text'])[:650]}\nSOURCE:\n{e['snip']}")
    return "\n".join(parts)
if __name__ == "__main__":
    import hancore_rules_v2 as V
    cat = sys.argv[1]; nrounds = int(sys.argv[2]); per = int(sys.argv[3]) if len(sys.argv) > 3 else 25
    os.makedirs(OUT + "/cands_raw", exist_ok=True)
    ex = examples(cat); missed = [e for e in ex if not e["caught"]]
    rnd = random.Random(int(hashlib.md5(cat.encode()).hexdigest()[:8], 16)); rnd.shuffle(missed)
    existing = "; ".join(f"{k}: {v[1]}" for k, v in V.RULES.items() if v[0] == cat) or "(none)"
    print(cat, "design findings with cited lines:", len(ex), "missed by existing rules:", len(missed), flush=True)
    tc = {}; tot = 0.0
    for rd in range(nrounds):
        outp = f"{OUT}/cands_raw/{cat}.{rd}.json"
        if os.path.exists(outp): continue
        chosen = []
        for e in missed[rd * per * 2:(rd + 1) * per * 2]:
            for fn, ln in e["cands"]:
                s = snippet(e["src"], fn, ln, tc)
                if s: chosen.append(dict(e, file=s[0], snip=s[1])); break
            if len(chosen) >= per: break
        if not chosen: break
        prompt = build_prompt(cat, chosen, existing)
        body = dict(model=MODEL, messages=[{"role": "user", "content": prompt}], max_tokens=16000, temperature=0.4, reasoning={"effort": "low"}, provider={"data_collection": "deny"})
        try: resp = post(body)
        except Exception as e: print("ERR", cat, rd, str(e)[:200]); continue
        u = resp.get("usage", {}); cost = u.get("cost")
        content = resp["choices"][0]["message"].get("content") or ""
        json.dump(dict(cat=cat, round=rd, n_examples=len(chosen), repos=[c["repo"] for c in chosen], usage=u, model=resp.get("model"), provider=resp.get("provider"), content=content), open(outp, "w"), indent=1)
        print(cat, rd, "ex", len(chosen), "usage", {k: u.get(k) for k in ("prompt_tokens", "completion_tokens", "cost")}, flush=True)

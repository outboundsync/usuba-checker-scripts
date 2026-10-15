#!/usr/bin/env python3
"""Recover file:line labels for HANCORE strong/likely findings that carry NO file reference in the prose
(label_concrete.py failure 'parse:no_file_reference'). An open-weights model (qwen/qwen3.5-397b-a17b via OpenRouter) is
shown the finding prose + line-numbered excerpts of the plugin source at the reviewed commit and must return file, line and the
verbatim code at that line. Nothing is accepted on the model's word: verify() mechanically requires
  (1) the file exists at the commit and the line is in range, (2) cited span <= 2 lines (line..line+1),
  (3) the model's quoted code occurs verbatim (whitespace-normalised) inside that span,
  (4) the described construct is on the span: an identifier/backticked token from the prose occurs in it (confidence high),
      or the bug-kind construct regex from label_concrete.CONSTRUCT matches it (confidence medium).
Exclusions are label_concrete's (holdout 329 repos/ids/trees, Dell-key ids/repos/trees; only ids/paths of the key are touched).
Usage: label_recover.py [--limit N] [--max-cost USD] [--workers N] ; resumable via raw cache.  Outputs -> OUT dir."""
import sys, os, re, json, collections, argparse, threading, time, urllib.request, concurrent.futures as cf
H = os.path.dirname(os.path.abspath(__file__)); sys.path.insert(0, H)
OUT = "/workspace/usuba-runs/hancore-labels-r2"; MODEL = "qwen/qwen3.5-397b-a17b"
ws = lambda s: re.sub(r"\s+", " ", s).strip()

SYS = ("You locate the exact source line a code-review finding is about. You get the finding text (written by a reviewer who did not "
       "cite a file) and numbered excerpts of the plugin's files at the reviewed commit (format `N: code`; '...' marks omitted lines). "
       "Pick the ONE file and line where the described construct literally appears (the call/statement that has the problem, not a nearby comment). "
       "If you cannot find it in the excerpts, say located=false; never guess. Reply with JSON only: "
       '{"located":true|false,"file":"path exactly as listed","line":N,"line_end":N or null (at most line+1),'
       '"quote":"verbatim code copied from that line (no line number prefix)","bug_kind":"one of the allowed kinds"}')

def candidate_text(files, text, budget=22000, per_file=7000):
    toks = set(); 
    for m in re.finditer(r"`([^`\n]{3,100})`", text):
        toks.add(m.group(1).strip())
    ids = set(re.findall(r"[A-Za-z_][\w.-]{5,}", text)); stop = set("should would before without which where because between current finding blocker review plugin script command could their there about after under still those these being using" .split())
    ids = {i for i in ids if i.lower() not in stop and not re.fullmatch(r"[0-9a-f]{7,40}", i)}
    scored = []
    for p, src in files.items():
        if p.startswith(".") or p.endswith((".png", ".svg", ".lock")) or p.lower() in ("license", "license.md"): continue
        lines = src.split("\n"); low = src
        hits = {}  # line idx -> weight
        sc = 0
        for t in toks:
            if len(t) >= 3 and t in low:
                sc += 3
                for i, l in enumerate(lines):
                    if t in l: hits[i] = hits.get(i, 0) + 3
        for t in ids:
            if t in low:
                sc += 1
                for i, l in enumerate(lines):
                    if t in l: hits[i] = hits.get(i, 0) + 1
        if sc: scored.append((sc / (1 + len(lines) / 400), p, lines, hits))
    scored.sort(key=lambda x: -x[0]); out = []; used = 0
    for sc, p, lines, hits in scored[:12]:
        if used >= budget: break
        body = "\n".join(f"{i+1}: {l[:300]}" for i, l in enumerate(lines))
        if len(body) > per_file:   # windows around the best hit lines
            keep = set()
            for i, w in sorted(hits.items(), key=lambda kv: -kv[1])[:40]:
                if len(keep) > 90: break
                keep.update(range(max(0, i - 6), min(len(lines), i + 7)))
            segs = []; prev = -2
            for i in sorted(keep):
                if i != prev + 1: segs.append("...")
                segs.append(f"{i+1}: {lines[i][:300]}"); prev = i
            body = "\n".join(segs)[:per_file]
        out.append(f"=== {p} ===\n{body}"); used += len(body)
    return "\n\n".join(out), [p for _, p, _, _ in scored[:12]]

def build_prompt(files, text, kinds):
    ex, _ = candidate_text(files, text)
    tree = "\n".join(sorted(p for p in files if not p.startswith("."))[:120])
    return (f"Allowed bug kinds: {', '.join(kinds)}\n\nFILES AT COMMIT:\n{tree}\n\nFINDING TEXT:\n{text[:2500]}\n\nSOURCE EXCERPTS:\n{ex}\n\nJSON only.")

def call(prompt, key):
    body = dict(model=MODEL, messages=[{"role": "system", "content": SYS}, {"role": "user", "content": prompt}], max_tokens=500, temperature=0,
                reasoning={"enabled": False}, provider={"data_collection": "deny"}, response_format={"type": "json_object"})
    for att in range(4):
        try:
            req = urllib.request.Request("https://openrouter.ai/api/v1/chat/completions", data=json.dumps(body).encode(),
                                         headers={"Authorization": "Bearer " + key, "Content-Type": "application/json"})
            with urllib.request.urlopen(req, timeout=180) as r: return json.load(r)
        except Exception as e:
            time.sleep(3 * (att + 1)); err = e
    return {"error": type(err).__name__}

def parse_json(c):
    c = re.sub(r"<think>.*?</think>", "", c or "", flags=re.S)
    m = re.search(r"\{.*\}", c, re.S)
    try: return json.loads(m.group(0)) if m else None
    except Exception: return None

def verify(files, ans, text, cats, lc):
    """-> (row_fields | None, reason)"""
    if not ans or not ans.get("located"): return None, "model:not_located"
    try: ln = int(ans["line"]); le = int(ans["line_end"]) if ans.get("line_end") else None
    except Exception: return None, "bad_line"
    p = lc.resolve(files, str(ans.get("file") or ""))
    if p is None or p == "AMBIG": return None, "file_missing_or_ambiguous"
    lines = files[p].split("\n")
    if ln < 1 or ln > len(lines): return None, "line_out_of_range"
    if le is not None and (le < ln or le > ln + 1): le = None if le < ln else ln + 1
    hi = le or ln
    span = lines[ln - 1:min(len(lines), hi + (0 if le else 1))]   # cited line (+ the next one: same statement)
    w = ws(" ".join(span)); q = ws(str(ans.get("quote") or ""))
    if len(q) < 6 or q not in w: return None, "quote_not_on_cited_lines"
    kind = None
    c13 = [x for x in cats if x in lc.K13]
    if len(c13) == 1: kind = c13[0]
    elif ans.get("bug_kind") in lc.K13 and (not c13 or ans["bug_kind"] in c13): kind = ans["bug_kind"]
    else: kind = lc.kind_for(cats, text, 0)
    if kind is None: return None, "no_bug_kind"
    toks = lc.tokens(text, p)
    why = None
    for t in toks:
        if ws(t) in w: why = "prose_token_on_line"; break
    if why is None:
        for t in toks:
            if any(i in w and len(i) >= 6 for i in re.findall(r"[A-Za-z_][\w.]{4,}", t)): why = "prose_identifier_on_line"; break
    conf = "high"
    if why is None:
        if any(re.search(r, "\n".join(span), re.I) for r in lc.CONSTRUCT.get(kind, [])): why = "category_construct_on_line"; conf = "medium"
        else: return None, "construct_not_on_line"
    return dict(file=p, line=ln, line_end=le, bug_kind=kind, verify="llm_" + why, confidence=conf), "ok"

def main():
    ap = argparse.ArgumentParser(); ap.add_argument("--limit", type=int, default=0); ap.add_argument("--max-cost", type=float, default=9.0)
    ap.add_argument("--workers", type=int, default=8); ap.add_argument("--out", default=OUT); a = ap.parse_args()
    key = os.environ["OPENROUTER_API_KEY"]
    import label_concrete as lc, common
    os.makedirs(a.out, exist_ok=True); rawp = a.out + "/raw.jsonl"
    done = {}
    if os.path.exists(rawp):
        for l in open(rawp):
            r = json.loads(l); done[r["comment_url"]] = r
    D = common.load(); tasks = []; excl = collections.Counter(); st = collections.Counter(); hold = set(lc.hold_urls)
    for p, v in sorted(D.items()):
        if not v["sha"]: continue
        gt = [x for x in v["gt"] if common.strength(x["fixed"]) in ("strong", "likely")]
        if not gt: continue
        repo = lc.norm(p)
        if p in hold or repo in lc.ex_repos: excl["holdout_or_dellkey_repo"] += len(gt); continue
        if {(c.get("plugin_id") or "").lower() for c in lc.by_repo.get(repo, [])} & lc.ex_ids: excl["manifest_id_match"] += len(gt); continue
        cand = [x for x in gt if not lc.parse(x["text"]) and not (lc.CLEAN_RE.search(x["text"]) and not re.search(r"(?i)blocker[s]? (?:found|:)|must|please|should|fix", x["text"]))]
        if not cand: continue
        files, origin = lc.source_for(repo, v["sha"], common.repo_of(p))
        if not files:
            files = lc.full_fetch(common.repo_of(p), v["sha"]); origin = "gh_tarball" if files else None
        if not files: st["no_source_at_commit"] += len(cand); continue
        mid = (lc.manifest_id(files) or "").lower()
        if mid and mid in lc.ex_ids: excl["manifest_id_match"] += len(cand); continue
        nd = lc.near_dup(lc.fp_dir(files))
        if nd: excl["near_duplicate_tree:" + nd.split(":")[0]] += len(cand); continue
        for x in cand:
            tasks.append((p, repo, v["sha"], x, files, origin))
    print("candidate findings:", len(tasks), "excluded:", dict(excl), "no source:", st["no_source_at_commit"], flush=True)
    if a.limit: tasks = tasks[::max(1, len(tasks) // a.limit)][:a.limit]
    lock = threading.Lock(); spent = [sum((r.get("cost") or 0) for r in done.values())]; stop = threading.Event()
    rf = open(rawp, "a")
    def work(t):
        p, repo, sha, x, files, origin = t
        if x["url"] in done or stop.is_set(): return
        if spent[0] >= a.max_cost: stop.set(); return
        resp = call(build_prompt(files, x["text"], lc.K13), key)
        u = resp.get("usage") or {}; c = u.get("cost") or 0
        content = ((resp.get("choices") or [{}])[0].get("message") or {}).get("content")
        rec = dict(comment_url=x["url"], plugin=repo, content=content, cost=c, ptok=u.get("prompt_tokens"), ctok=u.get("completion_tokens"), err=resp.get("error"))
        with lock:
            spent[0] += c; rf.write(json.dumps(rec) + "\n"); rf.flush(); done[x["url"]] = rec
    with cf.ThreadPoolExecutor(a.workers) as ex: list(ex.map(work, tasks))
    # ---- verify + write ----
    rows = []; why = collections.Counter()
    for p, repo, sha, x, files, origin in tasks:
        r = done.get(x["url"])
        if not r: why["not_run"] += 1; continue
        if r.get("err") or not r.get("content"): why["call_failed"] += 1; continue
        f, reason = verify(files, parse_json(r["content"]), x["text"], x["categories"], lc); why[reason] += 1
        if not f: continue
        rows.append(dict(plugin=repo, plugin_url=p, commit=sha, outcome=x["fixed"], strength=common.strength(x["fixed"]), comment_url=x["url"],
                         fix_evidence_url=x["fixed_evidence_url"], hancore_categories=x["categories"], file=f["file"], line=f["line"], line_end=f["line_end"],
                         bug_kind=f["bug_kind"], sub_kind=lc.subkind(f["bug_kind"], x["text"]), verify=f["verify"], confidence=f["confidence"],
                         source_origin=(origin or "") + "+llm:" + MODEL, n_refs=0, prose=lc.scrub(ws(x["text"][:330])), recovered=True))
    with open(a.out + "/recovered.jsonl", "w") as fo:
        for r in rows: fo.write(json.dumps(r, ensure_ascii=False) + "\n")
    n = len(tasks); kc = collections.Counter(r["bug_kind"] for r in rows)
    summ = dict(candidates=n, recovered=len(rows), rate=round(len(rows) / max(1, n), 3), reasons=dict(why.most_common()), per_kind=dict(kc.most_common()),
                with_line=sum(1 for r in rows if r["line"]), confidence=dict(collections.Counter(r["confidence"] for r in rows)),
                strength=dict(collections.Counter(r["strength"] for r in rows)), cost_usd=round(spent[0], 4), excluded=dict(excl), model=MODEL,
                plugins=len({r["plugin"] for r in rows}))
    json.dump(summ, open(a.out + "/summary.json", "w"), indent=1); print(json.dumps(summ, indent=1))
if __name__ == "__main__": main()

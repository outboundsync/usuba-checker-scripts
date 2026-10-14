#!/usr/bin/env python3
"""Head-to-head on the frozen HANCORE holdout (329 plugins: 300 positive, 29 negative). Never used for training.

Backends (same Usuba skill prompt, train/prompt.py, for every model):
  --backend checker                         Usuba Checker scripts alone (USB-W rule -> category map), no model
  --backend openai --base-url URL --model M  any OpenAI-compatible endpoint:
        local 9B:  eval/hancore_holdout/serve_llama.sh usuba-9b-Q4_K_M.gguf  (4 slots x 32k = -c 131072 -np 4)  ->  --base-url http://127.0.0.1:8080/v1 --model usuba-9b
        frontier:  --base-url https://openrouter.ai/api/v1 --model <frontier id>   (key read from $OPENROUTER_API_KEY, never printed)
  Thinking is OFF by default for every backend (training used enable_thinking=False); pass --think to allow it.
  --backend dry                             build prompts and score an always-'changes_requested' baseline (pipeline smoke test)
Metrics: verdict accuracy, positive recall (changes_requested on a positive), false-alarm rate on negatives, per-category recall of HANCORE
finding categories (strong/likely findings at the reviewed commit), category precision, JSON-valid rate, $ cost (from usage tokens and
--price-in/--price-out per 1M tokens), seconds per plugin. Output: eval/hancore_holdout/results/<name>.json (+ raw .jsonl)."""
import argparse, json, os, re, sys, tarfile, time, collections, urllib.request, urllib.error
from concurrent.futures import ThreadPoolExecutor
H = os.path.dirname(os.path.abspath(__file__)); ROOT = os.path.dirname(os.path.dirname(H))
sys.path[:0] = [os.path.join(ROOT, "train"), os.path.join(ROOT, "functest")]
import prompt
from build_reviewer_scrub import scrub
CODE_CAP, FILE_CAP = 24000, 8000
W_MAP = {"USB-W01": "install-deps-packaging", "USB-W02": "secrets-credentials", "USB-W03": "remote-code-pinning", "USB-W04": "file-safety-symlink-perms",
         "USB-W05": "privileged-system", "USB-W06": "rich-text-markup-injection", "USB-W07": "shell-lua-injection", "USB-W08": "process-lifecycle-timeouts",
         "USB-W09": "url-scheme-network", "USB-W10": "unbounded-input-resource"}
SCORED = set(W_MAP.values()) | {"scope-policy-duplicate", "user-config-modification", "listing-metadata-docs"}

def files_of(arc):
    out = {}
    with tarfile.open(os.path.join(H, arc)) as t:
        for m in t.getmembers():
            if m.isfile() and m.size < 2_000_000:
                try: out[m.name.split("/", 1)[-1]] = t.extractfile(m).read().decode("utf-8")
                except Exception: pass
    return out
def code_blob(files):
    order = lambda p: (0 if p == "manifest.json" else 1 if p.endswith((".qml", ".js", ".sh", ".py", ".lua", ".bash")) else 2 if p.lower().startswith("readme") else 3, p)
    out, n = [], 0
    for p in sorted(files, key=order):
        c = files[p][:FILE_CAP]
        if n + len(c) > CODE_CAP: out.append(f"### {p}\n(omitted: {len(files[p])} chars)"); continue
        out.append(f"### {p}\n```\n{c}\n```"); n += len(c)
    return "\n\n".join(out)
DATA_EXT_CAP = 20000   # whole-file mode still omits big non-code data files (catalog/*.json presets, lockfiles); code, manifest and README are never cut
def is_code(p): return p == "manifest.json" or p.endswith((".qml", ".js", ".mjs", ".sh", ".py", ".lua", ".bash", ".conf", ".toml", ".css")) or p.lower().startswith("readme")
def code_blob_whole(files):
    order = lambda p: (0 if p == "manifest.json" else 1 if p.endswith((".qml", ".js", ".sh", ".py", ".lua", ".bash")) else 2 if p.lower().startswith("readme") else 3, p)
    out = []
    for p in sorted(files, key=order):
        if not is_code(p) and len(files[p]) > DATA_EXT_CAP: out.append(f"### {p}\n(data file omitted: {len(files[p])} chars)"); continue
        out.append(f"### {p}\n```\n{files[p]}\n```")
    return "\n\n".join(out)
def est_tokens(msgs): return int(sum(len(m["content"]) for m in msgs) / 3.2) + 16 * len(msgs)   # conservative chars->tokens for code
# Dell-key plugin dirs also hold test-harness notes that are not part of the plugin: SOURCE.txt (generator + box functest verdict,
# e.g. "FAIL ... PanelContent.qml: No such file") and checklist.md ("Expected fooled case: ..."). Before 2026-10-14 these were in
# the prompt, leaking the answer. Never show them to a model.
from checker_report import HARNESS_FILES
def strip_harness(files): return {p: c for p, c in files.items() if p not in HARNESS_FILES}
def checker(files):
    import checker_report   # shared with train/build_train_set.py so train and eval reports are identical
    rep, w = checker_report.report_and_warn_rules(files, timeout=0)
    return rep, {W_MAP[f["rule"]] for f in w if f["rule"] in W_MAP}

# The skill prompt names categories in prose; models that were not fine-tuned answer with those prose names.
# Map them to the HANCORE slugs so category recall is comparable across backends (slugs pass through unchanged).
NORM = [("unbounded", "unbounded-input-resource"), ("install", "install-deps-packaging"), ("depend", "install-deps-packaging"), ("packag", "install-deps-packaging"),
        ("symlink", "file-safety-symlink-perms"), ("file safety", "file-safety-symlink-perms"), ("file-safety", "file-safety-symlink-perms"), ("permission", "file-safety-symlink-perms"),
        ("secret", "secrets-credentials"), ("credential", "secrets-credentials"), ("privilege", "privileged-system"), ("system change", "privileged-system"),
        ("lifecycle", "process-lifecycle-timeouts"), ("timeout", "process-lifecycle-timeouts"), ("remote code", "remote-code-pinning"), ("pinning", "remote-code-pinning"),
        ("url", "url-scheme-network"), ("network", "url-scheme-network"), ("rich-text", "rich-text-markup-injection"), ("markup", "rich-text-markup-injection"),
        ("shell/lua", "shell-lua-injection"), ("shell-lua", "shell-lua-injection"), ("injection", "shell-lua-injection"), ("user-config", "user-config-modification"),
        ("user config", "user-config-modification"), ("scope", "scope-policy-duplicate"), ("policy", "scope-policy-duplicate"), ("listing", "listing-metadata-docs"), ("metadata", "listing-metadata-docs")]
def norm_cat(c):
    c = (c or "").strip().lower()
    if c in SCORED or c.startswith(("in-use:", "load:", "checker:")): return c
    return next((slug for k, slug in NORM if k in c), c)
def parse(txt):
    if (txt or "").startswith(("ERROR ", "SKIPPED")): return None   # transport/context errors are invalid output, even though they contain JSON
    txt = re.sub(r"<think>.*?</think>", "", txt or "", flags=re.S).strip()
    m = re.search(r"\{.*\}", txt, re.S)
    try: return json.loads(m.group(0)) if m else None
    except Exception: return None
# Exam pitfall (2026-10-14): llama-server -c is the TOTAL context, split evenly across -np slots. -c 16384 with 4 slots is
# 4k per slot, but HANCORE / Dell prompts are ~6.7k-8k tokens (+ up to --max-tokens 2048 output), so 1002/1054 requests failed
# with "Context size has been exceeded". Require >= 32k per slot: 4 slots x 32768 = -c 131072 (see serve_llama.sh).
MIN_CTX_PER_SLOT = 32768
CTX_ERR = "Context size has been exceeded"
def is_ctx_overflow(txt):
    t = (txt or "").lower()
    return "context size has been exceeded" in t or "exceeds the available context" in t or "exceed_context_size" in t
def check_server_ctx(a):
    """llama-server only: read /props and refuse to run if the per-slot context is too small. Other endpoints are skipped."""
    try:
        with urllib.request.urlopen(a.base_url.rstrip("/").removesuffix("/v1") + "/props", timeout=10) as r: p = json.load(r)
    except Exception: return None
    n_ctx = (p.get("default_generation_settings") or {}).get("n_ctx") or p.get("n_ctx"); slots = p.get("total_slots") or 1
    if not n_ctx: return None
    print(f"llama-server: n_ctx per slot={n_ctx}, slots={slots} (total -c ~ {n_ctx * slots})", file=sys.stderr)
    if n_ctx < a.min_ctx_per_slot:
        sys.exit(f"ABORT: llama-server per-slot context {n_ctx} < {a.min_ctx_per_slot}. Exam prompts are ~6.7k-8k tokens + output; "
                 f"restart with -c {a.min_ctx_per_slot * slots} -np {slots} (eval/hancore_holdout/serve_llama.sh), or pass --min-ctx-per-slot to override.")
    return n_ctx
def call_openai(a, msgs):
    body = dict(model=a.model, messages=msgs, temperature=0, max_tokens=a.max_tokens)
    if not a.think:   # parity with training (enable_thinking=False -> empty <think></think> block)
        if "openrouter.ai" in a.base_url: body["reasoning"] = {"enabled": False, "exclude": True}
        else: body["chat_template_kwargs"] = {"enable_thinking": False}   # llama-server needs --jinja for this
    if a.provider: body["provider"] = {"order": [a.provider], "allow_fallbacks": False}
    if a.zdr and "openrouter.ai" in a.base_url: body.setdefault("provider", {}).update(zdr=True, data_collection="deny")
    if "openrouter.ai" in a.base_url: body["usage"] = {"include": True}
    hdr = {"Content-Type": "application/json"}
    key = os.environ.get(a.key_env) if a.key_env else None
    if key: hdr["Authorization"] = "Bearer " + key
    req = urllib.request.Request(a.base_url.rstrip("/") + "/chat/completions", data=json.dumps(body).encode(), headers=hdr)
    for i in range(4):
        try:
            with urllib.request.urlopen(req, timeout=600) as r: j = json.load(r)
            u = j.get("usage") or {}
            return j["choices"][0]["message"].get("content") or "", u
        except Exception as e:
            msg = ""
            if isinstance(e, urllib.error.HTTPError):
                try: msg = e.read().decode("utf-8", "replace")[:300]
                except Exception: pass
            if is_ctx_overflow(msg): return f"ERROR {CTX_ERR}: {msg}", {}   # retrying cannot help
            if i == 3: return f"ERROR {type(e).__name__} {msg}".strip(), {}
            time.sleep(5 * (i + 1))

def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--set", choices=["hancore", "dellkey"], default="hancore", help="hancore = 329-plugin review holdout; dellkey = Dell answer key (in-use, decided rows only)")
    ap.add_argument("--max-cost", type=float, default=0, help="stop sending requests once estimated $ spend reaches this")
    ap.add_argument("--backend", choices=["checker", "openai", "dry"], required=True); ap.add_argument("--name", required=True)
    ap.add_argument("--base-url"); ap.add_argument("--model"); ap.add_argument("--key-env", default=None)
    ap.add_argument("--price-in", type=float, default=0.0); ap.add_argument("--price-out", type=float, default=0.0)
    ap.add_argument("--max-tokens", type=int, default=2048); ap.add_argument("--workers", type=int, default=4)
    ap.add_argument("--think", action="store_true", help="allow thinking (default off, matching training)")
    ap.add_argument("--provider", default=None, help="OpenRouter provider pin"); ap.add_argument("--limit", type=int, default=0)
    ap.add_argument("--min-ctx-per-slot", type=int, default=MIN_CTX_PER_SLOT, help="abort if llama-server /props reports less context per slot")
    ap.add_argument("--ctx-check-n", type=int, default=20, help="fail-fast window: abort if too many of the first N responses overflow context")
    ap.add_argument("--ctx-max-rate", type=float, default=0.10, help="abort once context-overflow rate exceeds this (after --ctx-check-n responses)")
    ap.add_argument("--prompt", choices=["v1", "v2"], default="v1", help="v1 = train/prompt.py (as v1 was trained); v2 = train/prompt_v2.py (approve rule + few-shot)")
    ap.add_argument("--whole-files", choices=["auto", "on", "off"], default="auto", help="auto = on for --set dellkey: no 8000/24000-char truncation")
    ap.add_argument("--zdr", action="store_true", help="OpenRouter: only zero-data-retention endpoints")
    ap.add_argument("--model-ctx", type=int, default=0, help="non-llama endpoints: model context; prompts that would not fit are recorded as context overflow (invalid) instead of being sent")
    a = ap.parse_args()
    whole = a.whole_files == "on" or (a.whole_files == "auto" and a.set == "dellkey")
    P = __import__("prompt_v2") if a.prompt == "v2" else prompt
    blob = code_blob_whole if whole else code_blob
    srv_ctx = check_server_ctx(a) if a.backend == "openai" else None
    ctx_limit = srv_ctx or a.model_ctx
    if a.set == "dellkey":   # in-use eval: the Dell answer key (real hardware verdicts), excluded from training
        M = []
        for l in open(os.path.join(ROOT, "functest", "dell_ground_truth.jsonl")):
            g = json.loads(l)
            if g["real_verdict"] not in ("WORKS", "BROKEN"): continue
            d = next((x for x in (os.path.join(ROOT, g["path"]), os.path.join("/workspace/omarchy-specialist", g["path"])) if os.path.isdir(x)), None)
            if d: M.append(dict(plugin=g["id"], label="positive" if g["real_verdict"] == "BROKEN" else "negative", dir=d, findings=[], source=g["source"]))
    else: M = [json.loads(l) for l in open(os.path.join(H, "manifest.jsonl"))]
    if a.limit: M = M[:a.limit]
    import threading; spent = [0.0]; lock = threading.Lock(); seen = [0, 0]; abort = threading.Event()
    def one(m):
        if "dir" in m:
            import functest; files = strip_harness(functest.read_dir(m["dir"]))
        else: files = files_of(m["code_archive"])
        rep, wcats = checker(files)
        gt = {c for f in m["findings"] if f.get("strength") in ("strong", "likely") for c in f["categories"]} & SCORED
        t0 = time.time(); usage = {}; raw = None; ptok = None
        if a.backend == "checker":
            out = dict(verdict="changes_requested" if wcats else "approve", findings=[{"category": c} for c in sorted(wcats)])
        elif a.backend == "dry":
            msgs = P.messages(scrub(blob(files)), [scrub(r) for r in rep] if rep is not None else None)
            ptok = est_tokens(msgs); out = dict(verdict="changes_requested", findings=[], _prompt_chars=sum(len(x["content"]) for x in msgs))
        else:
            msgs = P.messages(scrub(blob(files)), [scrub(r) for r in rep] if rep is not None else None)
            ptok = est_tokens(msgs); need = ptok + a.max_tokens
            if ctx_limit and need > ctx_limit and srv_ctx:   # llama-server: fail fast, never silently truncate
                abort.set(); raise SystemExit(f"ABORT: {m['plugin']} needs ~{need} tokens of context but the server slot has {srv_ctx}; restart with CTX_PER_SLOT>={need} (serve_llama.sh).")
            if ctx_limit and need > ctx_limit: raw, usage, out = f"ERROR {CTX_ERR}: est {need} > model ctx {ctx_limit}", {}, None
            elif a.max_cost and spent[0] >= a.max_cost: raw, usage, out = "SKIPPED max-cost", {}, None
            else:
                if abort.is_set(): raise SystemExit("aborted: context overflow")
                raw, usage = call_openai(a, msgs); out = parse(raw)
                with lock:
                    seen[0] += 1; seen[1] += is_ctx_overflow(raw)
                    if seen[0] >= a.ctx_check_n and seen[1] / seen[0] > a.ctx_max_rate and not abort.is_set():
                        abort.set()
                        print(f"\nABORT: {seen[1]}/{seen[0]} responses hit '{CTX_ERR}'. The server context per slot is too small for these "
                              f"prompts (~6.7k-8k tokens). Restart llama-server with >= {MIN_CTX_PER_SLOT} per slot "
                              f"(4 slots: -c {4 * MIN_CTX_PER_SLOT} -np 4) and rerun. No results written.", file=sys.stderr, flush=True)
                with lock: spent[0] += usage.get("prompt_tokens", 0) / 1e6 * a.price_in + usage.get("completion_tokens", 0) / 1e6 * a.price_out
        secs = time.time() - t0
        pred = {norm_cat(f.get("category")) for f in (out or {}).get("findings", []) if isinstance(f, dict)}
        pred |= {norm_cat(c) for f in (out or {}).get("findings", []) if isinstance(f, dict) for c in (f.get("also") or []) if isinstance(c, str)}
        return dict(plugin=m["plugin"], label=m["label"], gt=sorted(gt), pred=sorted(pred), verdict=(out or {}).get("verdict"), valid=out is not None, prompt_tokens_est=ptok,
                    secs=round(secs, 2), usage=usage, raw=raw if raw is None else raw[:20000])
    with ThreadPoolExecutor(a.workers) as ex:
        try: R = list(ex.map(one, M))
        except SystemExit:
            ex.shutdown(wait=False, cancel_futures=True); sys.exit(2)
    if abort.is_set(): sys.exit(2)
    nctx = sum(is_ctx_overflow(r["raw"]) for r in R)
    if nctx: print(f"WARNING: {nctx}/{len(R)} responses hit '{CTX_ERR}'; those rows score as invalid.", file=sys.stderr)
    pos = [r for r in R if r["label"] == "positive"]; neg = [r for r in R if r["label"] == "negative"]
    flag = lambda r: r["verdict"] == "changes_requested"
    cat = {}
    for c in sorted(SCORED):
        tp = sum(1 for r in R if c in r["gt"] and c in r["pred"]); fn = sum(1 for r in R if c in r["gt"] and c not in r["pred"]); fp = sum(1 for r in R if c not in r["gt"] and c in r["pred"])
        cat[c] = dict(gt=tp + fn, recall=round(tp / (tp + fn), 3) if tp + fn else None, precision=round(tp / (tp + fp), 3) if tp + fp else None)
    tin = sum(r["usage"].get("prompt_tokens", 0) for r in R); tout = sum(r["usage"].get("completion_tokens", 0) for r in R)
    tp_all = sum(len(set(r["gt"]) & set(r["pred"])) for r in R); gt_all = sum(len(r["gt"]) for r in R); pr_all = sum(len(set(r["pred"]) & SCORED) for r in R)
    s = sorted(r["secs"] for r in R)
    res = dict(name=a.name, backend=a.backend, model=a.model, n=len(R), positives=len(pos), negatives=len(neg),
               verdict_accuracy=round((sum(flag(r) for r in pos) + sum(not flag(r) for r in neg)) / len(R), 3),
               positive_recall=round(sum(flag(r) for r in pos) / max(1, len(pos)), 3), negative_false_alarm=round(sum(flag(r) for r in neg) / max(1, len(neg)), 3),
               category_recall_micro=round(tp_all / max(1, gt_all), 3), category_precision_micro=round(tp_all / max(1, pr_all), 3),
               json_valid=round(sum(r["valid"] for r in R) / len(R), 3), tokens_in=tin, tokens_out=tout,
               cost_usd=round(sum(r["usage"].get("cost", 0) or 0 for r in R) or (tin / 1e6 * a.price_in + tout / 1e6 * a.price_out), 4), prompt=a.prompt, whole_files=whole, secs_median=s[len(s)//2], secs_total=round(sum(s), 1), per_category=cat)
    od = os.path.join(H, "results"); os.makedirs(od, exist_ok=True)
    json.dump(res, open(os.path.join(od, a.name + ".json"), "w"), indent=1)
    with open(os.path.join(od, a.name + ".raw.jsonl"), "w") as f:
        for r in R: f.write(json.dumps(r) + "\n")
    print(json.dumps({k: v for k, v in res.items() if k != "per_category"}, indent=1))
if __name__ == "__main__": main()

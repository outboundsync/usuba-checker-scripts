#!/usr/bin/env python3
"""Head-to-head on the frozen HANCORE holdout (329 plugins: 300 positive, 29 negative). Never used for training.

Backends (same Usuba skill prompt, train/prompt.py, for every model):
  --backend checker                         Usuba Checker scripts alone (USB-W rule -> category map), no model
  --backend openai --base-url URL --model M  any OpenAI-compatible endpoint:
        local 9B:  eval/hancore_holdout/serve_llama.sh usuba-9b-Q4_K_M.gguf  (4 slots x 32k = -c 131072 -np 4)  ->  --base-url http://127.0.0.1:8080/v1 --model usuba-9b
        frontier:  --base-url https://openrouter.ai/api/v1 --model <frontier id>   (key read from $OPENROUTER_API_KEY by default for openrouter.ai, never printed; a 401/403 aborts at once)
  Thinking is OFF by default for every backend (training used enable_thinking=False); pass --think to allow it.
  --backend dry                             build prompts and score an always-'changes_requested' baseline (pipeline smoke test)
Metrics (scoring.py, shared with rescore.py; audit B1-B4): THREE-WAY verdict approve | changes_requested | invalid (invalid is wrong for both classes),
verdict accuracy, positive recall, false-alarm rate on negatives, n_invalid / n_error / n_length_stop, per-category recall with n, category precision,
bootstrap 95% CIs, $ cost (usage.cost when the provider reports it, else tokens x --price-in/--price-out per 1M), seconds per plugin.
Output: eval/hancore_holdout/results/<name>.json (+ <name>.raw.jsonl with the FULL model text and finish_reason; never overwritten without --overwrite)."""
import argparse, hashlib, json, os, re, subprocess, sys, tarfile, time, collections, urllib.request, urllib.error
from concurrent.futures import ThreadPoolExecutor
H = os.path.dirname(os.path.abspath(__file__)); ROOT = os.path.dirname(os.path.dirname(H))
# The prompts, the scrubber and checker_report live in the MODELS repo (train/). Locate it: $USUBA_MODELS_DIR, ./train, or a sibling checkout.
def _models_train():
    for c in (os.environ.get("USUBA_MODELS_DIR"), os.path.join(ROOT, "train"), os.path.join(os.path.dirname(ROOT), "usuba-checker-models")):
        if c and os.path.isfile(os.path.join(c, "train", "prompt.py")): return os.path.join(c, "train")
        if c and os.path.isfile(os.path.join(c, "prompt.py")): return c
    return None
sys.path[:0] = [H, os.path.join(ROOT, "functest")] + ([_models_train()] if _models_train() else [])
import scoring
prompt = scrub = None
def _load_models_side():
    """Import the prompt / scrub modules on demand so scoring and the helpers here stay importable (and testable) without the models repo."""
    global prompt, scrub
    if _models_train() is None: sys.exit("cannot find the models repo's train/ (prompt.py): set USUBA_MODELS_DIR to a usuba-checker-models checkout")
    import prompt as _p
    from build_reviewer_scrub import scrub as _s
    prompt, scrub = _p, _s
CODE_CAP, FILE_CAP = 24000, 8000
W_MAP = {"USB-W01": "install-deps-packaging", "USB-W02": "secrets-credentials", "USB-W03": "remote-code-pinning", "USB-W04": "file-safety-symlink-perms",
         "USB-W05": "privileged-system", "USB-W06": "rich-text-markup-injection", "USB-W07": "shell-lua-injection", "USB-W08": "process-lifecycle-timeouts",
         "USB-W09": "url-scheme-network", "USB-W10": "unbounded-input-resource"}
SCORED = set(scoring.SCORED)
assert set(W_MAP.values()) <= SCORED

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
HARNESS_FILES = {"SOURCE.txt", "checklist.md"}   # same set as the models repo's checker_report.HARNESS_FILES
def strip_harness(files): return {p: c for p, c in files.items() if p not in HARNESS_FILES}
def checker(files):
    import checker_report   # shared with train/build_train_set.py so train and eval reports are identical
    rep, w = checker_report.report_and_warn_rules(files, timeout=checker_report.CHECKER_TIMEOUT)
    return rep, {W_MAP[f["rule"]] for f in w if f["rule"] in W_MAP}

# Category normalisation, JSON parsing and schema validation live in scoring.py (exact slug list + explicit alias table; unknown -> "unknown").
norm_cat = scoring.norm_cat
def parse(txt, finish_reason=None):
    """Validated model answer or None (kept for callers that only need the dict)."""
    return scoring.parse_answer(txt, finish_reason)[0]
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
class AuthError(SystemExit):
    pass
def resolve_key(a):
    """API key from --key-env, else $OPENROUTER_API_KEY for openrouter.ai. Never printed."""
    name = a.key_env or ("OPENROUTER_API_KEY" if "openrouter.ai" in (a.base_url or "") else None)
    return os.environ.get(name) if name else None
def call_openai(a, msgs, key=None):
    """-> (text, usage, finish_reason). 401/403 raise AuthError at once (retrying a bad key only burns the run)."""
    body = dict(model=a.model, messages=msgs, temperature=0, max_tokens=a.max_tokens)
    if not a.think:   # parity with training (enable_thinking=False -> empty <think></think> block)
        if "openrouter.ai" in a.base_url: body["reasoning"] = {"enabled": False, "exclude": True}
        else: body["chat_template_kwargs"] = {"enable_thinking": False}   # llama-server needs --jinja for this
    if a.provider: body["provider"] = {"order": [a.provider], "allow_fallbacks": False}
    if a.zdr and "openrouter.ai" in a.base_url: body.setdefault("provider", {}).update(zdr=True, data_collection="deny")
    if "openrouter.ai" in a.base_url: body["usage"] = {"include": True}
    hdr = {"Content-Type": "application/json"}
    if key: hdr["Authorization"] = "Bearer " + key
    req = urllib.request.Request(a.base_url.rstrip("/") + "/chat/completions", data=json.dumps(body).encode(), headers=hdr)
    for i in range(4):
        try:
            with urllib.request.urlopen(req, timeout=600) as r: j = json.load(r)
            u = j.get("usage") or {}
            ch = j["choices"][0]
            return ch["message"].get("content") or "", u, ch.get("finish_reason")
        except Exception as e:
            msg = ""
            if isinstance(e, urllib.error.HTTPError):
                if e.code in (401, 403): raise AuthError("ABORT: HTTP %d from %s: the API key is missing or rejected (set $%s / --key-env). No results written." % (e.code, a.base_url, getattr(a, "key_env", None) or "OPENROUTER_API_KEY"))
                try: msg = e.read().decode("utf-8", "replace")[:300]
                except Exception: pass
            if is_ctx_overflow(msg): return f"ERROR {CTX_ERR}: {msg}", {}, "error"   # retrying cannot help
            if i == 3: return f"ERROR {type(e).__name__} {msg}".strip(), {}, "error"
            time.sleep(5 * (i + 1))

def git_sha(path):
    try:
        sha = subprocess.run(["git", "-C", path, "rev-parse", "HEAD"], capture_output=True, text=True, timeout=20, check=True).stdout.strip()
        dirty = bool(subprocess.run(["git", "-C", path, "status", "--porcelain", "--untracked-files=no"], capture_output=True, text=True, timeout=20, check=True).stdout.strip())
        return sha, dirty
    except Exception: return None, None
def file_sha256(path):
    if not path or not os.path.isfile(path): return None
    h = hashlib.sha256()
    with open(path, "rb") as f:
        for b in iter(lambda: f.read(1 << 20), b""): h.update(b)
    return h.hexdigest()
def provenance(a, P, whole):
    """What produced this result (audit A7/B5): prompt hash, Checker git sha + rules hash, weights hash, decoding settings."""
    from usuba import provenance as cp
    sha, dirty = git_sha(ROOT)
    return dict(schema_version=scoring.SCHEMA_VERSION, prompt=a.prompt, prompt_sha256=file_sha256(P.__file__), checker_git_sha=sha, checker_git_dirty=dirty,
                rules_hash=cp.rules_hash(), code_blob_policy=getattr(sys.modules.get('code_blob'), 'POLICY_ID', 'legacy-8000/24000-unnumbered'), weights_sha256=a.weights_sha256, system=a.system or a.name, base_url_host=urllib.request.urlparse(a.base_url).netloc if a.base_url else None,
                decoding=dict(temperature=0, max_tokens=a.max_tokens, thinking=bool(a.think), provider=a.provider, zdr=bool(a.zdr)), whole_files=whole,
                generated_at=time.strftime("%Y-%m-%dT%H:%M:%S%z"))

def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--set", choices=["hancore", "dellkey"], default="hancore", help="hancore = 329-plugin review holdout; dellkey = Dell answer key (in-use, decided rows only)")
    ap.add_argument("--max-cost", type=float, default=0, help="stop sending requests once estimated $ spend reaches this")
    ap.add_argument("--backend", choices=["checker", "openai", "dry"], required=True); ap.add_argument("--name", required=True)
    ap.add_argument("--base-url"); ap.add_argument("--model"); ap.add_argument("--key-env", default=None, help="env var holding the API key (default: OPENROUTER_API_KEY for openrouter.ai, none for local servers)")
    ap.add_argument("--price-in", type=float, default=0.0); ap.add_argument("--price-out", type=float, default=0.0)
    ap.add_argument("--max-tokens", type=int, default=2048); ap.add_argument("--workers", type=int, default=4)
    ap.add_argument("--think", action="store_true", help="allow thinking (default off, matching training)")
    ap.add_argument("--provider", default=None, help="OpenRouter provider pin"); ap.add_argument("--limit", type=int, default=0)
    ap.add_argument("--min-ctx-per-slot", type=int, default=MIN_CTX_PER_SLOT, help="abort if llama-server /props reports less context per slot")
    ap.add_argument("--ctx-check-n", type=int, default=20, help="fail-fast window: abort if too many of the first N responses overflow context")
    ap.add_argument("--ctx-max-rate", type=float, default=0.10, help="abort once context-overflow rate exceeds this (after --ctx-check-n responses)")
    ap.add_argument("--prompt", choices=["v1", "v2", "v3", "v4"], required=True, help="v4 = train/prompt_v4.py + the shared train/code_blob.py renderer (numbered lines, explicit truncation markers; exactly what r5 trains on); v1 = train/prompt.py (as v1 was trained); v2 = train/prompt_v2.py (approve rule + few-shot); v3 = train/prompt_v3.py (rules match the v3 data; use for ALL systems in the exam)")
    ap.add_argument("--whole-files", choices=["auto", "on", "off"], default="auto", help="auto = on for --set dellkey: no 8000/24000-char truncation")
    ap.add_argument("--zdr", action="store_true", help="OpenRouter: only zero-data-retention endpoints")
    ap.add_argument("--weights-sha256", default=None, help="sha256 of the weights file served (recorded in the result; audit B5)")
    ap.add_argument("--system", default=None, help="unique run label, e.g. usuba-9b-v1-q4km (recorded in the result)")
    ap.add_argument("--expected-n", type=int, default=0, help="assert this many rows were scored (default: 329 for hancore; none for dellkey)")
    ap.add_argument("--allow-missing", action="store_true", help="dellkey: do not fail when plugin directories are missing (n shrinks)")
    ap.add_argument("--overwrite", action="store_true", help="replace an existing results/<name>.json (default: refuse)")
    ap.add_argument("--n-boot", type=int, default=1000, help="bootstrap resamples for the 95%% CIs")
    ap.add_argument("--model-ctx", type=int, default=0, help="non-llama endpoints: model context; prompts that would not fit are recorded as context overflow (invalid) instead of being sent")
    a = ap.parse_args()
    _load_models_side()
    if a.backend == "openai" and not a.base_url: sys.exit("--backend openai needs --base-url")
    od = os.path.join(H, "results")
    if os.path.exists(os.path.join(od, a.name + ".json")) and not a.overwrite:
        sys.exit("results/%s.json exists: pick a unique --name per run (or --overwrite)" % a.name)
    key = resolve_key(a) if a.backend == "openai" else None
    if a.backend == "openai" and "openrouter.ai" in a.base_url and not key: sys.exit("ABORT: no API key: set $OPENROUTER_API_KEY or pass --key-env NAME")
    whole = a.whole_files == "on" or (a.whole_files == "auto" and a.set == "dellkey")
    P = __import__("prompt_v4") if a.prompt == "v4" else __import__("prompt_v3") if a.prompt == "v3" else __import__("prompt_v2") if a.prompt == "v2" else prompt
    blob = code_blob_whole if whole else code_blob
    if a.prompt == "v4":   # audit A1: eval renders code with the SAME shared renderer as the r5 builders (never whole-file mode: that would change what the model saw in training)
        import code_blob as _cb
        blob = _cb.code_blob; whole = False
    srv_ctx = check_server_ctx(a) if a.backend == "openai" else None
    ctx_limit = srv_ctx or a.model_ctx
    missing_dirs = []
    if a.set == "dellkey":   # in-use eval: the Dell answer key (real hardware verdicts), excluded from training
        M = []
        for l in open(os.path.join(ROOT, "functest", "dell_ground_truth.jsonl")):
            g = json.loads(l)
            if g["real_verdict"] not in ("WORKS", "BROKEN"): continue
            if g["id"].startswith(("b3.opus55.",)): continue   # plugins written by Claude are excluded from the key (docs/ANTHROPIC_TERMS_COMPLIANCE.md in the models repo)
            d = next((x for x in (os.path.join(ROOT, g["path"]), os.path.join(os.environ.get("FT_DELL_PLUGINS", "/workspace/omarchy-specialist"), g["path"])) if os.path.isdir(x)), None)
            if d: M.append(dict(plugin=g["id"], label="positive" if g["real_verdict"] == "BROKEN" else "negative", dir=d, findings=[], source=g["source"]))
            else: missing_dirs.append(g["id"])
        if missing_dirs and not a.allow_missing:
            sys.exit("ABORT: %d Dell-key plugin directories are missing (n would shrink silently): %s ... (--allow-missing to accept)" % (len(missing_dirs), missing_dirs[:5]))
    else: M = [json.loads(l) for l in open(os.path.join(H, "manifest.jsonl"))]
    if a.limit: M = M[:a.limit]
    import threading; spent = [0.0]; inflight = [0]; lock = threading.Lock(); seen = [0, 0]; abort = threading.Event()
    est_cost = [a.max_tokens / 1e6 * a.price_out + 8000 / 1e6 * a.price_in]   # per-request reservation until real costs are observed
    def one(m):
        if "dir" in m:
            import functest; files = strip_harness(functest.read_dir(m["dir"]))
        else: files = files_of(m["code_archive"])
        rep, wcats = checker(files)
        gt = {c for f in m["findings"] if f.get("strength") in ("strong", "likely") for c in f["categories"]} & SCORED
        t0 = time.time(); usage = {}; raw = None; ptok = None; fin = None
        if a.backend == "checker":
            out = dict(verdict="changes_requested" if wcats else "approve", findings=[{"category": c} for c in sorted(wcats)]); raw = json.dumps(out)
        elif a.backend == "dry":
            msgs = P.messages(scrub(blob(files)), [scrub(r) for r in rep] if rep is not None else None)
            ptok = est_tokens(msgs); out = dict(verdict="changes_requested", findings=[]); raw = json.dumps(out)
        else:
            msgs = P.messages(scrub(blob(files)), [scrub(r) for r in rep] if rep is not None else None)
            ptok = est_tokens(msgs); need = ptok + a.max_tokens
            if ctx_limit and need > ctx_limit and srv_ctx:   # llama-server: fail fast, never silently truncate
                abort.set(); raise SystemExit(f"ABORT: {m['plugin']} needs ~{need} tokens of context but the server slot has {srv_ctx}; restart with CTX_PER_SLOT>={need} (serve_llama.sh).")
            skip = False
            if a.max_cost:   # reserve before sending: with N workers the old "spent >= cap" check let N requests overshoot (audit B3)
                with lock:
                    if spent[0] + (inflight[0] + 1) * est_cost[0] > a.max_cost: skip = True
                    else: inflight[0] += 1
            if ctx_limit and need > ctx_limit:
                raw, usage = f"ERROR {CTX_ERR}: est {need} > model ctx {ctx_limit}", {}
                if a.max_cost and not skip:
                    with lock: inflight[0] -= 1
            elif skip: raw, usage = "SKIPPED max-cost", {}
            else:
                if abort.is_set(): raise SystemExit("aborted: context overflow")
                try: raw, usage, fin = call_openai(a, msgs, key)
                except AuthError: abort.set(); raise
                finally:
                    if a.max_cost:
                        with lock: inflight[0] -= 1
                with lock:
                    seen[0] += 1; seen[1] += is_ctx_overflow(raw)
                    if seen[0] >= a.ctx_check_n and seen[1] / seen[0] > a.ctx_max_rate and not abort.is_set():
                        abort.set()
                        print(f"\nABORT: {seen[1]}/{seen[0]} responses hit '{CTX_ERR}'. The server context per slot is too small for these "
                              f"prompts (~6.7k-8k tokens). Restart llama-server with >= {MIN_CTX_PER_SLOT} per slot "
                              f"(4 slots: -c {4 * MIN_CTX_PER_SLOT} -np 4) and rerun. No results written.", file=sys.stderr, flush=True)
                with lock:
                    c = usage.get("cost")   # provider-reported $ wins over price flags
                    c = c if isinstance(c, (int, float)) else usage.get("prompt_tokens", 0) / 1e6 * a.price_in + usage.get("completion_tokens", 0) / 1e6 * a.price_out
                    spent[0] += c
                    if c > 0: est_cost[0] = max(est_cost[0] * 0.5, c)
        secs = time.time() - t0
        cl = scoring.classify_row(raw, fin)   # three-way verdict, schema-validated; the SAME function rescore.py uses
        return dict(plugin=m["plugin"], label=m["label"], gt=sorted(gt), pred=cl["pred"], verdict=cl["verdict"], invalid_reason=cl["invalid_reason"], finish_reason=fin,
                    prompt_tokens_est=ptok, secs=round(secs, 2), usage=usage, raw=raw)
    with ThreadPoolExecutor(a.workers) as ex:
        try: R = list(ex.map(one, M))
        except SystemExit:
            ex.shutdown(wait=False, cancel_futures=True); sys.exit(2)
    if abort.is_set(): sys.exit(2)
    nctx = sum(is_ctx_overflow(r["raw"]) for r in R)
    if nctx: print(f"WARNING: {nctx}/{len(R)} responses hit '{CTX_ERR}'; those rows score as invalid.", file=sys.stderr)
    exp = a.expected_n or (329 if a.set == "hancore" and not a.limit else 0)
    m = scoring.score_rows(R, expected_n=exp or None, n_boot=a.n_boot)   # raises if n shrank
    tin = sum(r["usage"].get("prompt_tokens", 0) for r in R); tout = sum(r["usage"].get("completion_tokens", 0) for r in R)
    s_ = sorted(r["secs"] for r in R)
    cost = sum(r["usage"].get("cost", 0) or 0 for r in R) or (tin / 1e6 * a.price_in + tout / 1e6 * a.price_out)
    res = dict(name=a.name, backend=a.backend, model=a.model, set=a.set, tokens_in=tin, tokens_out=tout, cost_usd=round(cost, 4),
               secs_median=s_[len(s_) // 2] if s_ else None, secs_total=round(sum(s_), 1), n_missing_dirs=len(missing_dirs), **m)
    res["provenance"] = provenance(a, P, whole)
    os.makedirs(od, exist_ok=True)
    with open(os.path.join(od, a.name + ".json"), "w") as f: json.dump(res, f, indent=1)
    with open(os.path.join(od, a.name + ".raw.jsonl"), "w") as f:
        for r in R: f.write(json.dumps(r) + "\n")
    print(json.dumps({k: v for k, v in res.items() if k not in ("per_category", "provenance")}, indent=1))
if __name__ == "__main__": main()

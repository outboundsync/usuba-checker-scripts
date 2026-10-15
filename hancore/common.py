"""Shared HANCORE helpers: per-plugin reviewed commit + ground-truth categories (read-only over dell/sweep/hancore_reviews.jsonl)."""
import json, re, os, collections
ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
REV = os.path.join(ROOT, "dell/sweep/hancore_reviews.jsonl")
SHA = re.compile(r"(?<![0-9a-f])[0-9a-f]{40}(?![0-9a-f])")
STRONG = ("fixed:",)
WEAK = ("not-fixed:closed-stale", "not-fixed:closed-not_planned", "not-fixed:closed-completed", "not-fixed:closed-unknown", "not-fixed:closed-duplicate")
_FIXCTX = re.compile(r"(fix(ed|es)?|resolved|addressed|patched|landed|merged|reverted)\W[^.\n]{0,60}$|(by|in|via)\s+(commit\s+)?$", re.I)
_FOREIGN = re.compile(r"github\.com/([\w.-]+/[\w.-]+)/(?:commit|tree|blob)/$")
def reviewed_shas(text, plugin_repo=None):
    """40-hex SHAs in a comment that can be the REVIEWED (pre-fix) commit. Audit E: a "fixed in/at <sha>" sentence names the FIXED code and a
    commit URL of another repo is not this plugin's commit; both are skipped (strict mode only; see load(strict_sha=True))."""
    out = []
    for m in SHA.finditer(text):
        pre = text[max(0, m.start() - 90):m.start()].replace("\n", " ")
        fm = _FOREIGN.search(pre)
        if fm and plugin_repo and fm.group(1).lower() != plugin_repo.lower(): continue
        if _FIXCTX.search(pre.rstrip("` ")) or _FIXCTX.search(pre): continue
        out.append(m.group(0))
    return out
def strength(fx):
    if fx.startswith("fixed:"): return "strong"
    if fx.startswith("likely:"): return "likely"
    if fx.startswith("open"): return "open"
    if fx in ("not-fixed:closed-stale",): return "stale"
    if fx in ("not-fixed:closed-not_planned",): return "not_planned"
    return "closed_no_fix"
def load(strict_sha=False):
    """strict_sha=False reproduces the historical attribution bit for bit (any 40-hex in a comment, back-filled). True: audit E fix, see reviewed_shas."""
    r = [json.loads(l) for l in open(REV)]
    r = [x for x in r if x["thread_repo"] == "omacom/omarchy-plugin-marketplace" and x["plugin"].startswith("https://github.com/")]
    P = collections.defaultdict(list)
    for x in r: P[x["plugin"]].append(x)
    out = {}
    for p, xs in P.items():
        xs.sort(key=lambda x: x["date"]); cur = None
        def pick(x, p=p):
            if not strict_sha: m = SHA.search(x["text"]); return m.group(0) if m else None
            c = reviewed_shas(x["text"], repo_of(p)); return c[0] if c else None
        first = next((pick(x) for x in xs if pick(x)), None)
        for x in xs:
            m = pick(x); cur = m if m else (cur or first); x["_sha"] = cur
        fin = [x for x in xs if x["item_type"] == "finding" and not set(x["categories"]) <= {"clean-review-no-blocker"}]
        c = collections.Counter(x["_sha"] for x in fin if x["_sha"])
        sha = c.most_common(1)[0][0] if c else first
        gt = [x for x in fin if x["_sha"] == sha]
        out[p] = dict(plugin=p, sha=sha, items=xs, findings=fin, gt=gt,
                      approved=any(x["item_type"] == "approval-or-confirmed-fix" or "clean-review-no-blocker" in x["categories"] for x in xs),
                      listed=any("listed" in x["labels"] for x in xs))
    return out
def repo_of(p): return "/".join(p.rstrip("/").split("/")[3:5])

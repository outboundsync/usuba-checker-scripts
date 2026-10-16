"""[Canonical home: usuba-checker-scripts. usuba-checker-models imports this module via a thin shim; do not copy it back.]
The ONE renderer for the 'Plugin source' part of the prompt, imported by every data builder, train_lora's parity checks and the eval harness
(audit A1). Pure function of the file contents: file order, per-file caps and truncation never depend on the label or on where a finding sits.

  blob, info = render(files)         files: {path: text}
  info[path] = dict(lines=<total>, shown=<lines visible, 0 if omitted>, truncated=bool, omitted=bool)

Policy (POLICY_ID goes into every row's meta and every result file):
  * order: manifest.json, then code files (.qml .js .mjs .sh .bash .py .lua) by path, then README*, then everything else by path
  * every file is cut at FILE_CAP characters on a line boundary and carries an explicit marker  (truncated: showing lines 1-N of M, K chars not shown)
  * a file that would push the total over CODE_CAP characters is replaced by (omitted: N chars, M lines); the manifest is never omitted
  * every shown line is prefixed with its 1-based number  `  12| code`  so cited line numbers need no counting (NUMBERED)
"""
import hashlib

FILE_CAP = 12000
CODE_CAP = 40000
NUMBERED = True
POLICY_ID = f"code_blob/v1 file_cap={FILE_CAP} code_cap={CODE_CAP} numbered={int(NUMBERED)}"
CODE_EXT = (".qml", ".js", ".mjs", ".sh", ".bash", ".py", ".lua")


def order_key(p):
    return (0 if p == "manifest.json" else 1 if p.endswith(CODE_EXT) else 2 if p.lower().startswith("readme") else 3, p)


def _numbered(lines, first=1):
    w = max(4, len(str(first + len(lines))))
    return "\n".join(f"{i:>{w}}| {l}" for i, l in enumerate(lines, first))


def norm_newlines(t):
    """CRLF/CR -> LF: the Checker's loader reads text-mode (normalised) while a tar-based eval loader keeps \\r; one rule for both (audit B3)"""
    return t.replace("\r\n", "\n").replace("\r", "\n")


def render_file(p, text, cap=FILE_CAP, numbered=NUMBERED):
    """-> (block, info). Cuts on a line boundary; never cuts inside the first line."""
    text = norm_newlines(text)
    lines = text.split("\n")
    if len(text) <= cap:
        body, shown = lines, len(lines); note = ""
    else:
        body, n = [], 0
        for l in lines:
            if body and n + len(l) + 1 > cap: break
            body.append(l); n += len(l) + 1
        shown = len(body)
        note = f"\n(truncated: showing lines 1-{shown} of {len(lines)}; {len(text) - n} chars not shown)"
    txt = _numbered(body) if numbered else "\n".join(body)
    return f"### {p}\n```\n{txt}\n```{note}", dict(lines=len(lines), shown=shown, truncated=bool(note), omitted=False)


def render(files, file_cap=FILE_CAP, code_cap=CODE_CAP, numbered=NUMBERED):
    out, info, used = [], {}, 0
    for p in sorted(files, key=order_key):
        t = norm_newlines(files[p])
        block, inf = render_file(p, t, file_cap, numbered)
        cost = min(len(t), file_cap)
        if used + cost > code_cap and p != "manifest.json":
            out.append(f"### {p}\n(omitted: {len(t)} chars, {len(t.split(chr(10)))} lines)")
            info[p] = dict(lines=len(t.split("\n")), shown=0, truncated=False, omitted=True); continue
        out.append(block); info[p] = inf; used += cost
    return "\n\n".join(out), info


def code_blob(files, **kw):
    """The string used in the prompt."""
    return render(files, **kw)[0]


def line_visible(info, path, line):
    i = info.get(path)
    if not i: return False
    if not i["omitted"] and 1 <= line <= i["shown"]: return True
    return any(a <= line <= b for a, b in i.get("windows", ()))


# ---- anchored windows (code_blob/v2): the cited-line windows of the Checker findings that are in the prompt ------------------------------------
# A pure function of (files, anchors) where anchors = the (file, line) pairs of the Checker report that is ALSO in the prompt. Anchors never depend on
# a label, so train and inference render the same bytes. Findings whose line is already visible add nothing; the rest get +-WINDOW lines,
# appended after the normal blob as `### path [window lines a-b of M]` blocks, within ANCHOR_CAP characters and MAX_WINDOWS windows.
WINDOW = 30
WIN_CHARS = 5000
ANCHOR_CAP = 24000
MAX_WINDOWS = 16
POLICY_ID_V2 = POLICY_ID.replace("code_blob/v1", "code_blob/v2") + f" window={WINDOW} anchor_cap={ANCHOR_CAP}"


def render_anchored(files, anchors, **kw):
    """-> (blob, info). Same as render() plus windows around anchors that the base render hides. anchors: iterable of (path, line)."""
    blob, info = render(files, **kw)
    norm = {p: norm_newlines(t).split("\n") for p, t in files.items()}
    want = sorted({(p, int(l)) for p, l in anchors if p in norm and isinstance(l, int) and 1 <= l <= len(norm[p]) and not line_visible(info, p, l)},
                  key=lambda x: (order_key(x[0]), x[1]))
    blocks, used, nwin = [], 0, 0
    for p, l in want:
        if nwin >= MAX_WINDOWS: break
        if line_visible(info, p, l): continue                # covered by an earlier window of the same file
        ls = norm[p]; a, b = max(1, l - WINDOW), min(len(ls), l + WINDOW)
        while b > a and sum(len(x) + 8 for x in ls[a - 1:b]) > WIN_CHARS:       # shrink away from the anchor, keeping it inside
            if b - l >= l - a: b -= 1
            else: a += 1
        cost = sum(len(x) + 8 for x in ls[a - 1:b])
        if used + cost > ANCHOR_CAP: continue
        blocks.append(f"### {p} [window lines {a}-{b} of {len(ls)}]\n```\n{_numbered(ls[a - 1:b], a)}\n```")
        info[p].setdefault("windows", []).append((a, b)); used += cost; nwin += 1
    return ("\n\n".join([blob] + blocks) if blocks else blob), info


def blob_sha(files):
    return hashlib.sha256(code_blob(files).encode()).hexdigest()

#!/usr/bin/env python3
"""Pre-publication scan for this repository: working tree AND full git history. Exit code 1 on any finding.

Checks (patterns only; matched values are never printed, only file, commit and rule name):
  1. credential-shaped strings (API keys, tokens, JWTs, private keys, URL credentials, long key assignments)
  2. home-directory paths other than the neutral placeholders (/home/user/...)
  3. file names of private evaluation/device material (answer keys, labels, raw model outputs, device captures, raw review dumps)
  4. blobs larger than 20 MB, Git LFS pointer files
  5. (audit C4) /Users/<x>/ and /root/ paths, e-mail addresses inside files, GPU-cloud instance ids and bucket URLs, raw model output
     fields, and the decompressed contents of .gz files (plain and tar.gz members, size-capped)

Run:  python3 tools/scan_public.py [--no-history]
"""
import gzip, io, json, re, subprocess, sys, tarfile

SELF = "tools/scan_public.py"
CRED = {
    "openrouter-key": r"sk-or-v1-[A-Za-z0-9]{16,}",
    "anthropic-key": r"sk-ant-[A-Za-z0-9_-]{16,}",
    "openai-style-key": r"\bsk-(?:proj-|svcacct-|admin-)?[A-Za-z0-9_-]{32,}",
    "github-token": r"\b(?:ghp|gho|ghu|ghs|ghr)_[A-Za-z0-9]{30,}|github_pat_[A-Za-z0-9_]{30,}",
    "huggingface-token": r"\bhf_[A-Za-z0-9]{30,}\b",
    "aws-key-id": r"\b(?:AKIA|ASIA)[0-9A-Z]{16}\b",
    "google-api-key": r"\bAIza[0-9A-Za-z_-]{35}\b",
    "slack-token": r"\bxox[baprs]-[A-Za-z0-9-]{10,}",
    "stripe-key": r"\b(?:sk|rk)_live_[A-Za-z0-9]{16,}",
    "private-key-block": r"-----BEGIN [A-Z ]*PRIVATE KEY-----",
    "jwt": r"\beyJ[A-Za-z0-9_-]{8,}\.eyJ[A-Za-z0-9_-]{8,}\.[A-Za-z0-9_-]*",
    "bearer-token": r"(?i)\bBearer\s+[A-Za-z0-9._~+/=-]{24,}",
    "url-credentials": r"(?i)\b[a-z][a-z0-9+.-]*://[^\s/:@'\"]{2,}:[^\s/:@'\"]{4,}@(?!localhost|example)[A-Za-z0-9.-]+",
    "key-assignment": r"(?i)\b(?:api[_-]?key|secret[_-]?key|access[_-]?token|auth[_-]?token|password)\b[\"']?\s*[:=]\s*[\"'][A-Za-z0-9/+_=-]{24,}[\"']",
}
NEUTRAL_HOMES = {"user", "runner", "username", "you", "me", "name", "foo", "someone", "example", "alice", "bob", "$USER", "USER", "<user>"}
HOME = re.compile(r"(?:/home|/Users)/([A-Za-z0-9_.$<>-]+)/")
ROOT_PATH = re.compile(r"(?<![A-Za-z0-9_.-])/root/[A-Za-z0-9_.$<>-]")   # root's real home on a build/GPU box
EMAIL = re.compile(r"(?<![A-Za-z0-9._%+-])[A-Za-z0-9._%+-]+@([A-Za-z0-9-]+(?:\.[A-Za-z0-9-]+)*\.[A-Za-z]{2,})\b")
NOT_EMAIL_TLDS = {"service", "slice", "socket", "timer", "target", "desktop", "mount", "path", "sh", "py", "conf", "qml", "js", "json", "md", "txt"}   # systemd unit / file names: foo@tty1.service
OK_EMAIL_ADDRESSES = {"git@github.com"}   # ssh clone URLs
EMAIL_OK_PATHS = re.compile(r"^(NOTICE$|sources/licenses/)")   # upstream copyright lines are reproduced verbatim there (licence conditions)
OK_EMAIL_DOMAINS = {"users.noreply.github.com", "noreply.github.com", "outboundsync.com", "example.com", "example.org", "example.invalid", "example.net", "localhost", "anthropic.com"}
INFRA = {   # GPU-cloud instance ids and object-storage buckets
    "vast-instance-id": r"(?i)\b(?:vast(?:\.ai)?[ _-]?(?:instance|contract)|instance[_ -]?id)\b[\"']?\s*[:=#]?\s*[\"']?\d{6,}",
    "vast-instance-id-bare": r"(?i)\binstance\s+#?\d{7,}\b",
    "bucket-url": r"\b(?:s3|gs|r2|b2|az)://[A-Za-z0-9][A-Za-z0-9._-]{2,}",
}
MAX_DECOMPRESSED = 200_000_000
RAW_FIELD = re.compile(r'"(?:raw|raw_output|completion|generation|output_text|output)"\s*:\s*"(?:[^"\\]|\\.){2000,}"')
PRIVATE_NAMES = re.compile(r"(?i)(dell_ground_truth|(^|/)labels_(draft|final)|ground_truth_(rows|additions)|dellkey.*\.(raw|reason)|\.raw\.jsonl$|\.reason\.json$|(^|/)teacher-|dell-capture/|^dell/|dell_rounds/|dell-batch|dell-smoke|(^|/)\.env(\.|$)|\.pem$|id_rsa|hancore_labels|data/reviews/|hancore_reviewer/|hancore_holdout/(manifest\.jsonl|code/))")
# reviewed 2026-10-16 by Harris: Dell hyprland captures are not sensitive (no history rewrite; this path is exempt from the private-file-name rule)
PRIVATE_EXEMPT = "functest/fixtures/hyprland-0.56.2/dell-capture/"


def is_private(path):
    return PRIVATE_NAMES.search(path) is not None and PRIVATE_EXEMPT not in path


ALLOW_ABS = {"/home/user", "/home/runner", "/root/.cache", "/root/.config"}   # neutral paths that may appear in docs (prefixes)
# Exact (path, rule) pairs reviewed and accepted. These are historical blobs that cannot be rewritten (no force-push): /root/... paths
# on throwaway rented GPU boxes (not a person's home) and ids of rented, already-stopped GPU instances (useless without the account).
# Anything new must be fixed, not added here.
ACCEPTED = {(p, r) for p, r in [
    ("docs/TRAINING_PLAN.md", "home-path"), ("docs/TRAINING_PLAN.md", "vast-instance-id"), ("docs/TRAINING_PLAN.md", "vast-instance-id-bare"),
    ("reviews/context_pack.md", "home-path"), ("runs/q27/README.md", "vast-instance-id-bare"), ("runs/q27/dbg.py", "home-path"),
    ("runs/q27/pipe.sh", "home-path"), ("runs/q27/train.log", "home-path"), ("runs/q27/train_q27.py", "home-path"),
    ("runs/smoke-2026-10-11/PROGRESS.md", "vast-instance-id-bare"), ("runs/v3/run_404.log", "home-path"), ("train/launch_vast.sh", "home-path"),
    ("runs/smoke-2026-10-11/hf4bit_adapter_v2_check.json", "raw-model-output"),   # open-model generations, removed from the tree (audit F2), still in history
    # same files after the audit-F7 move to legacy/ (the old paths above stay: history blobs are checked under their old names)
    ("legacy/runs/q27/README.md", "vast-instance-id-bare"),
    ("legacy/runs/q27/dbg.py", "home-path"),
    ("legacy/runs/q27/pipe.sh", "home-path"),
    ("legacy/runs/q27/train.log", "home-path"),
    ("legacy/runs/q27/train_q27.py", "home-path"),
    ("legacy/runs/smoke-2026-10-11/PROGRESS.md", "vast-instance-id-bare"),
    ("legacy/runs/v3/run_404.log", "home-path"),
    ("legacy/runs/smoke-2026-10-11/hf4bit_adapter_v2_check.json", "raw-model-output"),
    # reviewed 2026-10-16 by Harris: Dell hyprland captures are not sensitive; the rented-instance number in earlier docs/post/draft.md
    # revisions (history only, removed from the tree, no history rewrite) is accepted. dell-capture/ itself is exempt via PRIVATE_EXEMPT.
    ("docs/post/draft.md", "vast-instance-id-bare"),
]}


def sh(*a, **k):
    return subprocess.run(a, capture_output=True, **k)


def scan_text(label, path, text, out):
    for rule, rx in CRED.items():
        if re.search(rx, text):
            out.append((label, path, rule))
    for m in HOME.finditer(text):
        if m.group(1) not in NEUTRAL_HOMES:
            out.append((label, path, "home-path"))
            break
    for m in ROOT_PATH.finditer(text):
        if not any(text.startswith(a, m.start()) for a in ALLOW_ABS):
            out.append((label, path, "home-path"))
            break
    for m in EMAIL.finditer(text):
        dom = m.group(1).lower()
        if m.group(0).lower() in OK_EMAIL_ADDRESSES or dom.rsplit(".", 1)[-1] in NOT_EMAIL_TLDS or EMAIL_OK_PATHS.match(path):
            continue
        if not any(dom == d or dom.endswith("." + d) for d in OK_EMAIL_DOMAINS):
            out.append((label, path, "email-address"))
            break
    for rule, rx in INFRA.items():
        if re.search(rx, text):
            out.append((label, path, rule))
    if RAW_FIELD.search(text):
        out.append((label, path, "raw-model-output"))


def scan_bytes(label, path, data, out):
    """Scan one blob; .gz blobs are decompressed (size-capped) and their text, or tar members, scanned too."""
    if data.startswith(b"version https://git-lfs"):
        out.append((label, path, "lfs-pointer"))
    if data[:2] == b"\x1f\x8b":
        try:
            raw = gzip.GzipFile(fileobj=io.BytesIO(data)).read(MAX_DECOMPRESSED + 1)
        except (OSError, EOFError):
            out.append((label, path, "unreadable-gzip"))
            return
        if len(raw) > MAX_DECOMPRESSED:
            out.append((label, path, "gzip>200MB-decompressed"))
            return
        if raw[257:262] == b"ustar":
            try:
                with tarfile.open(fileobj=io.BytesIO(raw)) as t:
                    for m in t:
                        if m.isfile() and m.size < 20_000_000:
                            if is_private(m.name):
                                out.append((label, path + "!" + m.name, "private-file-name"))
                                continue
                            body = t.extractfile(m).read()
                            if b"\0" not in body[:8192]:
                                scan_text(label, path + "!" + m.name, body.decode("utf-8", "replace"), out)
            except tarfile.TarError:
                out.append((label, path, "unreadable-tar"))
            return
        data = raw
    if b"\0" in data[:8192]:
        return
    scan_text(label, path, data.decode("utf-8", "replace"), out)


def main():
    history = "--no-history" not in sys.argv
    out = []
    files = sh("git", "ls-files", "-z").stdout.decode().split("\0")
    for f in filter(None, files):
        if f == SELF:
            continue
        if is_private(f):
            out.append(("tree", f, "private-file-name"))
            continue
        try:
            data = open(f, "rb").read()
        except OSError:
            continue
        scan_bytes("tree", f, data, out)
    if history:
        # every distinct blob in history, once
        objs = sh("git", "rev-list", "--objects", "--all").stdout.decode().splitlines()
        batch = sh("git", "cat-file", "--batch-check=%(objecttype) %(objectname) %(objectsize) %(rest)", input="\n".join(o.split()[0] for o in objs).encode()).stdout.decode().splitlines()
        names = {}
        for o in objs:
            p = o.split(" ", 1)
            names[p[0]] = {p[1]} if len(p) > 1 else set()
        # rev-list --objects names each blob once; collect EVERY path a blob ever had (audit C4)
        for ln in sh("git", "log", "--all", "--format=", "--raw", "--no-abbrev").stdout.decode().splitlines():
            if ln.startswith(":"):
                meta, _, path = ln.partition("\t")
                names.setdefault(meta.split()[3], set()).add(path)
        todo = []
        for line in batch:
            t, h, size, *_ = line.split(" ")
            if t != "blob":
                continue
            ps = sorted(names.get(h) or {""})
            if SELF in ps:
                continue
            p = ps[0]
            if int(size) > 20_000_000:
                out.append(("history", p, "blob>20MB"))
            bad = [q for q in ps if is_private(q)]
            for q in bad:
                out.append(("history", q, "private-file-name"))
            if bad:
                continue
            todo.append((h, p))
        proc = subprocess.Popen(["git", "cat-file", "--batch"], stdin=subprocess.PIPE, stdout=subprocess.PIPE)
        for h, p in todo:
            proc.stdin.write((h + "\n").encode()); proc.stdin.flush()
            hdr = proc.stdout.readline().split()
            n = int(hdr[2]); data = proc.stdout.read(n); proc.stdout.read(1)
            scan_bytes("history", p, data, out)
        proc.stdin.close(); proc.wait()
        # commit metadata: only the maintainer's addresses may appear
        emails = set(sh("git", "log", "--all", "--format=%ae%n%ce").stdout.decode().split())
        for e in emails:
            if not (e == "noreply@github.com" or e.endswith("@users.noreply.github.com") or e.endswith("@outboundsync.com")):
                out.append(("history", "commit-metadata", "unexpected-author-email"))
    seen = set()
    for label, path, rule in out:
        k = (label, path, rule)
        if k in seen or (path, rule) in ACCEPTED:
            continue
        seen.add(k)
        print(f"FINDING {label} {path} {rule}")
    print(f"scan_public: {len(seen)} finding(s)")
    sys.exit(1 if seen else 0)


if __name__ == "__main__":
    main()

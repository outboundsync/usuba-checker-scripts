#!/usr/bin/env python3
"""Finding-level table for rule measurement (v3 measurement fixes).
Per HANCORE strong/likely finding at the reviewed commit of a pooled plugin: categories, named files (+lines) parsed from the prose,
clean-review flag (prose says 'no high/medium issue identified' although tagged with a category), and bug kinds (keyword taxonomy).
Reads only the HANCORE reviews (dell/sweep/hancore_reviews.jsonl) and pool.json; no Dell-key labels. Writes findings.json."""
import sys, os, re, json
H = os.path.dirname(os.path.abspath(__file__)); sys.path.insert(0, H)
import common
OUT = "/workspace/usuba-runs/checker-rules"
EXT = r"qml|sh|bash|py|js|mjs|lua|json|md|conf|toml|ya?ml|html|txt|desktop|service|ini|ts|rs|go|css|jsonc"
FILE_RE = re.compile(r"(?<![\w/.-])((?:[\w.-]+/)*[\w.-]+\.(?:%s))\b(?::(\d+))?" % EXT)
EXTLESS_RE = re.compile(r"`((?:[\w.-]+/)*[\w-]+)(?::(\d+))`")   # `bin/foo:12`
CLEAN_RE = re.compile(r"(?i)\bno (?:high|medium|critical|blocking|security|material|significant)[\w\s,/-]{0,40}(?:issue|finding|blocker|concern|risk)s?\b[^.]{0,60}(?:identified|found|observed|remain)|\bno blocker|\bno blocking|did not find (?:any )?(?:high|medium|blocking)")
KINDS = {
 "unbounded-input-resource": [
  ("curl-wget-nocap", r"curl|wget|download"), ("python-body-read", r"urlopen|requests|\.read\(|python|socket|recv"), ("qml-xhr", r"XMLHttpRequest|responseText|\bXHR\b"),
  ("response-body-unbounded", r"unbounded|no (?:size|length|byte)|without (?:a )?(?:size|length|byte)|memory|response bod|max-filesize|size limit|cap\b"), ("file-read-unbounded", r"FileView|readFile|cat |large file|file size")],
 "file-safety-symlink-perms": [
  ("predictable-tmp", r"/tmp|predictable|mktemp|temporary"), ("symlink", r"symlink|ln -s|O_NOFOLLOW|symbolic link"), ("world-writable-perms", r"777|666|world-(?:writable|readable)|umask|chmod|permission|0600|0700|mode"),
  ("rm-rf-delete", r"rm -rf|recursive(?:ly)? delet|deletes?\b|removal|unlink"), ("race-toctou", r"race|toctou|time-of-check"), ("path-traversal", r"traversal|\.\./|canonical|realpath|outside")],
 "secrets-credentials": [
  ("hardcoded-literal", r"hard-?coded|embedded|literal|committed|checked in|shipped|default (?:key|token|password)"), ("argv-exposure", r"argv|command[- ]line|process (?:list|arg|inspect)|\bps\b|/proc|visible to other"),
  ("url-query-token", r"query|in the URL|url param|request URLs?"), ("secret-file-perms", r"0600|permission|world-readable|mode|plaintext (?:file|storage)|stored in (?:plain|a file)|config file"),
  ("secret-logged", r"\blog(?:s|ged|ging)?\b|echo|printed|stdout|notification|diagnostic")],
 "url-scheme-network": [
  ("plain-http", r"http://|plaintext|cleartext|unencrypted|non-?TLS|\bHTTP\b"), ("tls-verification-off", r"verif|insecure|-k\b|--insecure|certificate|TLS"), ("redirect", r"redirect|-L\b"),
  ("open-url-scheme", r"openUrlExternally|xdg-open|scheme|file:|javascript:|open(?:s|ing)? (?:a )?(?:URL|link)|browser"), ("untrusted-host", r"base URL|user-?(?:editable|configurable)|host|endpoint|private|allowlist|SSRF|localhost")],
 "remote-code-pinning": [
  ("curl-pipe-sh", r"curl[^.\n]{0,30}\|\s*(?:ba)?sh|pipe[sd]? (?:to|into) (?:a )?shell|piped"), ("unpinned-git", r"git clone|branch|\bmain\b|HEAD|tag\b|commit|ref\b|git pull|mutable"),
  ("unpinned-package", r"pip|npm|npx|cargo|go install|@latest|uvx|yay|paru|pacman|package|version|AUR|latest"), ("raw-main-url", r"raw\.githubusercontent|releases/latest|/main/|/master/"), ("no-checksum", r"checksum|signature|hash|sha256|verify|integrity|gpg")],
 "rich-text-markup-injection": [
  ("autotext-default", r"AutoText|default"), ("explicit-richtext", r"RichText|StyledText|Markdown|textFormat"), ("notification-body", r"notif|body|summary"), ("external-data-in-text", r"remote|API|network|stdout|output|metadata|title|name|track|ssid|artist")],
 "shell-lua-injection": [
  ("sh-c-interpolation", r"sh -c|bash -c|shell|interpolat|concatenat|splic"), ("eval", r"\beval\b"), ("hyprctl-dispatch", r"hyprctl|dispatch|keyword|Hyprland"), ("lua-string", r"\bLua\b|lua"),
  ("quoting-escaping", r"quot|escap|sanitiz|inject"), ("option-injection", r"option inject|argument inject|leading -|--\b|argv")],
 "process-lifecycle-timeouts": [
  ("no-timeout", r"timeout|hang|stall|indefinite|blocks?\b"), ("orphan-cleanup", r"orphan|zombie|kill|cleanup|clean up|trap|lingering|terminate|leak"), ("polling-loop", r"poll|loop|interval|timer|repeat|every"),
  ("lock-singleton", r"lock|flock|single|concurrent|race|duplicate instance|pidfile|pid file")],
 "privileged-system": [("sudo-pkexec", r"sudo|pkexec|root|polkit"), ("system-write", r"/etc|/usr|/opt|systemctl|system-level|udev|modprobe"), ("device-access", r"/dev/|uinput|input group|capabilit|setcap")],
}
def parse_files(text):
    out = {}
    for m in FILE_RE.finditer(text): out.setdefault(m.group(1), set()).add(int(m.group(2)) if m.group(2) else 0)
    for m in EXTLESS_RE.finditer(text): out.setdefault(m.group(1), set()).add(int(m.group(2)))
    return {k: sorted(v) for k, v in out.items() if not k.startswith("http") and "github.com" not in k}
def kinds_of(cat, text):
    return [k for k, rx in KINDS.get(cat, []) if re.search(rx, text, re.I)] or ["other"]
def build():
    pool = json.load(open(OUT + "/pool.json")); D = common.load()
    norm = lambda s: s.lower().rstrip("/").removesuffix(".git").split("github.com/")[-1]
    res = {}
    for p, v in D.items():
        r = pool.get(norm(p))
        if not r or not r["reviewed"]: continue
        fl = []
        for x in v["gt"]:
            if common.strength(x["fixed"]) not in ("strong", "likely"): continue
            t = x["text"]; files = parse_files(t); clean = bool(CLEAN_RE.search(t[:400]))
            for c in x["categories"]:
                if c in ("clean-review-no-blocker",): continue
                fl.append(dict(cat=c, files=files, clean=clean, kinds=kinds_of(c, t), strength=common.strength(x["fixed"]), text=t[:1500], url=x["url"]))
        res[r["repo"]] = fl
    json.dump(res, open(OUT + "/findings.json", "w"))
    import collections
    n = sum(len(v) for v in res.values()); cl = sum(f["clean"] for v in res.values() for f in v); pf = sum(bool(f["files"]) for v in res.values() for f in v if not f["clean"])
    print("plugins", len(res), "category-findings", n, "clean-flagged", cl, "non-clean with parsed files", pf)
    print(collections.Counter(k for v in res.values() for f in v if not f["clean"] for k in f["kinds"] if f["cat"] in KINDS).most_common(50))
if __name__ == "__main__": build()

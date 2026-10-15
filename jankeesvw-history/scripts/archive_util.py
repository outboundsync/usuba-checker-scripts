"""git archive -> directory without a shell (audit C3), failing loudly; the .ok marker is only written on success (audit A5: never cache a failure)."""
import os
import re
import subprocess

_REV = re.compile(r"^[0-9A-Za-z._/-]+$")


def git_archive(repo_dir, rev, dest):
    if not _REV.match(rev):
        raise ValueError(f"unsafe revision: {rev!r}")
    os.makedirs(dest, exist_ok=True)
    ga = subprocess.Popen(["git", "-C", repo_dir, "archive", rev], stdout=subprocess.PIPE)
    tar = subprocess.run(["tar", "-x", "-C", dest], stdin=ga.stdout, capture_output=True, check=False)
    ga.stdout.close()
    if ga.wait() != 0 or tar.returncode != 0:
        raise RuntimeError(f"git archive {rev} of {repo_dir} failed: {tar.stderr[-200:]!r}")
    with open(os.path.join(dest, ".ok"), "w") as f:
        f.write("1")

"""Sandbox hardening tests (audit C1, C2, C3). Argument checks always run; real bwrap checks run only where bwrap works."""
import os
import shutil
import subprocess
import sys

import pytest

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
FT = os.path.join(ROOT, "functest")
HC = os.path.join(ROOT, "tools", "hitcheck")


def _bwrap_works():
    if not shutil.which("bwrap"):
        return False
    return subprocess.run(["bwrap", "--ro-bind", "/usr", "/usr", "--symlink", "usr/bin", "/bin", "--symlink", "usr/lib", "/lib",
                           "--symlink", "usr/lib64", "/lib64", "--proc", "/proc", "--dev", "/dev", "true"], capture_output=True).returncode == 0


needs_bwrap = pytest.mark.skipif(not _bwrap_works(), reason="bwrap unavailable")


@pytest.fixture(scope="module")
def runtime():
    sys.path.insert(0, FT)
    import runtime as r
    return r


def _pair(cmd, flag):
    return [cmd[i + 1] for i, c in enumerate(cmd[:-1]) if c == flag]


def test_runtime_sandbox_args_do_not_bind_root(runtime, tmp_path):
    cmd = runtime.sandbox_cmd(str(tmp_path), {"HOME": str(tmp_path)}, ["/bin/true"])
    ro = [(cmd[i + 1], cmd[i + 2]) for i, c in enumerate(cmd) if c in ("--ro-bind", "--bind")]
    assert ("/", "/") not in ro
    tmpfs = _pair(cmd, "--tmpfs")
    for d in ("/home", "/root", "/run", "/tmp"):
        assert d in tmpfs, d
    for flag in ("--new-session", "--clearenv", "--unshare-net", "--unshare-pid", "--unshare-ipc", "--die-with-parent"):
        assert flag in cmd, flag
    assert "--dev-bind" not in cmd
    assert cmd[-1] == "/bin/true"


@needs_bwrap
def test_runtime_sandbox_hides_home_run_and_stdin(runtime, tmp_path, monkeypatch):
    monkeypatch.setenv("SECRET", "x")   # inherited by the harness process; --clearenv must hide it
    secret = os.path.expanduser("~")
    probe = ("ls -A /home /root /run | tr '\\n' ' '; echo; test -e %s/.config && echo HOMEVISIBLE; "
             "readlink /proc/self/fd/0; env | grep -c ^SECRET= ; true") % secret
    cmd = runtime.sandbox_cmd(str(tmp_path), {"HOME": str(tmp_path)}, ["/bin/bash", "-c", probe], runs=str(tmp_path), omarchy=runtime.OMARCHY)
    out, timed_out = runtime.run_capped(cmd, 30)
    txt = out.decode()
    assert not timed_out
    assert "HOMEVISIBLE" not in txt
    assert "/dev/null" in txt           # stdin is /dev/null
    assert txt.strip().endswith("0")    # SECRET not inherited (--clearenv)


@needs_bwrap
def test_runtime_run_capped_kills_runaway_output(runtime):
    out, over = runtime.run_capped(["/bin/sh", "-c", "yes"], timeout=20, cap=1_000_000)
    assert over and len(out) <= 1_000_000 + 65536


def test_safe_read_refuses_symlink_fifo_escape_and_caps(runtime, tmp_path):
    root = tmp_path / "run"
    root.mkdir()
    (root / "ok.txt").write_text("hello")
    os.symlink("/etc/hostname", root / "link.txt")
    os.mkfifo(root / "fifo")
    (root / "big.txt").write_text("a" * 5000)
    assert runtime.safe_read(str(root / "ok.txt"), root=str(root)) == "hello"
    with pytest.raises(OSError):
        runtime.safe_read(str(root / "link.txt"), root=str(root))
    with pytest.raises(OSError):
        runtime.safe_read(str(root / "fifo"), root=str(root))      # must not hang
    assert len(runtime.safe_read(str(root / "big.txt"), cap=100)) == 100
    os.symlink(str(root), tmp_path / "alias")
    (tmp_path / "outside.txt").write_text("secret")
    os.symlink(str(tmp_path), root / "dirlink")
    with pytest.raises(OSError):
        runtime.safe_read(str(root / "dirlink" / "outside.txt"), root=str(root))   # parent-directory symlink escape


def test_parse_exec_log_ignores_symlinked_log(runtime, tmp_path):
    target = tmp_path / "real"
    target.write_text("S\t1\t0\tcurl\n")
    link = tmp_path / "exec.log"
    os.symlink(target, link)
    assert runtime.parse_exec_log(str(link)) == []


# ---- hitcheck (C2) ------------------------------------------------------------------------------------------
def sh(script, env=None, timeout=60):
    e = dict(os.environ, HC_SOURCE_ONLY="1", **(env or {}))
    return subprocess.run(["bash", "-c", script], capture_output=True, text=True, env=e, timeout=timeout)


def test_hitcheck_script_parses_and_is_strict():
    path = os.path.join(HC, "run_hitcheck.sh")
    assert subprocess.run(["bash", "-n", path]).returncode == 0
    assert "set -euo pipefail" in open(path).read().split("\n", 12)[-1] or "set -euo pipefail" in open(path).read()


@pytest.mark.parametrize("name,ok", [("job-1.a_b", True), ("A", True), ("..", False), (".", False), ("a/b", False), ("a b", False), ("", False),
                                     ("-rf", False), ("a;rm", False), ("$(id)", False), ("x\ny", False)])
def test_hitcheck_valid_name(name, ok):
    r = sh('source "%s"; valid_name "$1" && echo OK || echo NO' % os.path.join(HC, "run_hitcheck.sh") + "", env={})
    r = subprocess.run(["bash", "-c", 'source "$0"; valid_name "$1" && echo OK || echo NO', os.path.join(HC, "run_hitcheck.sh"), name],
                       capture_output=True, text=True, env=dict(os.environ, HC_SOURCE_ONLY="1"))
    assert r.stdout.strip() == ("OK" if ok else "NO"), r.stderr


def test_hitcheck_job_rejects_traversal_name(tmp_path):
    r = subprocess.run(["bash", os.path.join(HC, "run_hitcheck.sh"), "--job", "../../victim"], capture_output=True, text=True,
                       env=dict(os.environ, HOME=str(tmp_path)))
    assert r.returncode == 2 and "refusing job name" in r.stderr


def _bw_args(tmp_path, extra_env=None):
    j = tmp_path / "job"
    (j / "tmp").mkdir(parents=True)
    xrd = tmp_path / "xrd"
    xrd.mkdir()
    script = ('source "$0"; ENVV=(HOME=/h HC_ID=x); build_bwrap_args "$1" "$2" "$3"; printf "%s\\n" "${BW[@]}"')
    r = subprocess.run(["bash", "-c", script, os.path.join(HC, "run_hitcheck.sh"), str(j), str(tmp_path / "home"), str(xrd)], capture_output=True, text=True,
                       env=dict(os.environ, HC_SOURCE_ONLY="1", WAYLAND_DISPLAY="wayland-1", **(extra_env or {})))
    assert r.returncode == 0, r.stderr
    return r.stdout.split("\n")[:-1]


def test_hitcheck_bwrap_args_hardened(tmp_path):
    a = _bw_args(tmp_path)
    pairs = [(a[i + 1], a[i + 2]) for i, x in enumerate(a[:-2]) if x in ("--ro-bind", "--bind")]
    assert ("/", "/") not in pairs
    assert "--dev-bind" not in a                      # no full host /dev
    assert "--dev" in a and "--clearenv" in a and "--new-session" in a and "--unshare-net" in a
    tmpfs = [a[i + 1] for i, x in enumerate(a[:-1]) if x == "--tmpfs"]
    for d in ("/home", "/root", "/run", "/var", "/tmp"):
        assert d in tmpfs, d
    assert "DBUS_SESSION_BUS_ADDRESS" not in a


@needs_bwrap
def test_hitcheck_sandbox_runs_and_hides_host(tmp_path):
    a = _bw_args(tmp_path)
    secret = tmp_path / "home" / "secret.txt"
    secret.parent.mkdir(exist_ok=True)
    secret.write_text("s")
    env = {"DBUS_SESSION_BUS_ADDRESS": "unix:path=/x", "SECRET_TOKEN": "abc"}
    probe = "env | grep -c -E 'SECRET_TOKEN|DBUS' ; find /home /root /run -mindepth 1 | wc -l; test -e %s && echo LEAK || echo hidden; ls /dev | tr '\\n' ' '" % secret
    r = subprocess.run(["bwrap"] + a + ["/bin/bash", "-c", probe], capture_output=True, text=True, env=dict(os.environ, **env), stdin=subprocess.DEVNULL)
    assert r.returncode == 0, r.stderr
    lines = r.stdout.split("\n")
    assert lines[0] == "0" and lines[1] == "0" and lines[2] == "hidden"
    for dangerous in ("input", "snd", "video0", "uinput", "mem", "kmsg"):
        assert dangerous not in lines[3].split()


def test_hc_safe_never_follows_symlinks_or_fifos(tmp_path):
    sys.path.insert(0, HC)
    import hc_safe
    (tmp_path / "t.txt").write_text("a\nb\n")
    (tmp_path / "host.txt").write_text("HOST SECRET")
    os.symlink(tmp_path / "host.txt", tmp_path / "toggle.txt")
    os.mkfifo(tmp_path / "ipc_list.txt")
    assert hc_safe.safe_lines(str(tmp_path / "t.txt")) == ["a", "b"]
    assert hc_safe.safe_lines(str(tmp_path / "toggle.txt")) == []
    assert hc_safe.safe_lines(str(tmp_path / "ipc_list.txt")) == []
    assert hc_safe.safe_lines(str(tmp_path / "missing")) == []
    (tmp_path / "big").write_text("x" * 3000)
    assert len(hc_safe.safe_read_bytes(str(tmp_path / "big"), cap=100)) == 100


def test_hc_signal_does_not_copy_symlinked_evidence(tmp_path):
    raw = tmp_path / "raw"
    raw.mkdir()
    (tmp_path / "host.txt").write_text("exit=0 HOSTSECRETLINE")
    os.symlink(tmp_path / "host.txt", raw / "toggle.txt")
    os.symlink(tmp_path / "host.txt", raw / "ipc_list.txt")
    jobs = tmp_path / "jobs.json"
    jobs.write_text('{"jobs":[{"job":"j","batch":"A","kinds":["panel"]}]}')
    r = subprocess.run([sys.executable, os.path.join(HC, "hc_signal.py"), str(raw), str(jobs), "j", "x.y"], capture_output=True, text=True)
    assert r.returncode == 0, r.stderr
    assert "HOSTSECRETLINE" not in r.stdout


def test_build_package_no_shell_true():
    src = open(os.path.join(HC, "build_package.py")).read()
    assert "shell=True" not in src

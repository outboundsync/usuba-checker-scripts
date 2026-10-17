"""tools/hitcheck/build_package.py must extract tarballs on Python 3.12 (data filter) and on 3.10 patch releases without tarfile.data_filter."""
import importlib.util
import io
import os
import tarfile

import pytest

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))


def _load():
    spec = importlib.util.spec_from_file_location("build_package_under_test", os.path.join(ROOT, "tools", "hitcheck", "build_package.py"))
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


def _tar(entries):
    buf = io.BytesIO()
    with tarfile.open(fileobj=buf, mode="w") as t:
        for name, data in entries:
            ti = tarfile.TarInfo(name)
            ti.size = len(data)
            t.addfile(ti, io.BytesIO(data))
    buf.seek(0)
    return tarfile.open(fileobj=buf)


@pytest.fixture(params=["with_filter", "without_filter"])
def mod(request, monkeypatch):
    m = _load()
    if request.param == "without_filter":
        monkeypatch.delattr(tarfile, "data_filter", raising=False)  # emulate 3.10.<12
    return m


def test_extracts_regular_members(mod, tmp_path):
    t = _tar([("a/b.txt", b"hi")])
    mod.tar_extract(t, path=str(tmp_path))
    assert (tmp_path / "a" / "b.txt").read_bytes() == b"hi"


def test_extracts_single_member(mod, tmp_path):
    t = _tar([("x.txt", b"1"), ("y.txt", b"2")])
    mod.tar_extract(t, t.getmember("y.txt"), str(tmp_path))
    assert not (tmp_path / "x.txt").exists() and (tmp_path / "y.txt").read_bytes() == b"2"


def test_refuses_path_traversal(mod, tmp_path):
    t = _tar([("../evil.txt", b"x")])
    with pytest.raises(tarfile.TarError):
        mod.tar_extract(t, path=str(tmp_path / "out"))
    assert not (tmp_path / "evil.txt").exists()

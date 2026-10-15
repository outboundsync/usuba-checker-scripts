"""run_eval / rescore integration on hand-made data (audit B1-B3). No network, no model: a local fake OpenAI server."""
import json
import os
import subprocess
import sys
import threading
import http.server

import pytest

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
EH = os.path.join(ROOT, "eval", "hancore_holdout")


def _rescore():
    """eval/hancore_holdout/rescore.py by path: functest/rescore.py (a different module) shadows the name on sys.path."""
    import importlib.util
    spec = importlib.util.spec_from_file_location("hh_rescore", os.path.join(EH, "rescore.py"))
    m = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(m)
    return m


def raw_row(label, text, **kw):
    return dict(plugin="p", label=label, gt=[], pred=[], raw=text, usage={}, **kw)


def test_rescore_reproduces_run_eval_and_does_not_overwrite(tmp_path):
    rescore = _rescore()
    good = json.dumps({"verdict": "approve", "load": "works", "findings": []})
    flag = json.dumps({"verdict": "changes_requested", "findings": [{"category": "Secrets", "also": ["url-scheme-network"]}]})
    rows = [raw_row("negative", good, finish_reason="stop"), raw_row("negative", "garbage", finish_reason="stop"),
            dict(raw_row("positive", flag, finish_reason="stop"), gt=["secrets-credentials", "url-scheme-network"])]
    (tmp_path / "t.raw.jsonl").write_text("\n".join(json.dumps(r) for r in rows))
    (tmp_path / "t.json").write_text(json.dumps({"name": "t", "n": 3, "verdict_accuracy": 0.9}))
    res, out = rescore.rescore("t", str(tmp_path), n_boot=20)
    assert out.endswith("t.rescored.json")
    assert json.load(open(tmp_path / "t.json"))["verdict_accuracy"] == 0.9      # original untouched
    assert res["n_invalid"] == 1 and res["n_invalid_negative"] == 1
    assert res["verdict_accuracy"] == round(2 / 3, 3)
    assert res["per_category"]["url-scheme-network"]["recall"] == 1.0          # `also` honoured (old rescore ignored it)


def test_rescore_legacy_cut_text_keeps_stored_outcome(tmp_path):
    rescore = _rescore()
    cut = "x" * 20000   # a legacy raw cut at 20000 chars: re-parsing would be invalid, but the original run had parsed the full text
    rows = [dict(plugin="p", label="positive", gt=[], pred=[], raw=cut, valid=True, verdict="changes_requested", usage={})]
    (tmp_path / "old.raw.jsonl").write_text(json.dumps(rows[0]))
    res, _ = rescore.rescore("old", str(tmp_path), n_boot=10)
    assert res["n_invalid"] == 0 and res["n_legacy_text_cut"] == 1


def test_rescore_row_count_mismatch_is_an_error(tmp_path):
    rescore = _rescore()
    (tmp_path / "t.raw.jsonl").write_text(json.dumps(raw_row("positive", "{}", finish_reason="stop")))
    (tmp_path / "t.json").write_text(json.dumps({"n": 5}))
    with pytest.raises(ValueError):
        rescore.rescore("t", str(tmp_path), n_boot=10)


class _H(http.server.BaseHTTPRequestHandler):
    status = 200
    seen = []

    def do_POST(self):
        n = int(self.headers.get("Content-Length", 0))
        self.rfile.read(n)
        _H.seen.append(self.headers.get("Authorization"))
        if _H.status != 200:
            self.send_response(_H.status)
            self.end_headers()
            self.wfile.write(b"{}")
            return
        body = json.dumps({"choices": [{"message": {"content": '{"verdict":"approve","findings":[]}'}, "finish_reason": "stop"}], "usage": {"cost": 0.5}}).encode()
        self.send_response(200)
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def log_message(self, *a):
        pass


@pytest.fixture
def server():
    srv = http.server.HTTPServer(("127.0.0.1", 0), _H)
    t = threading.Thread(target=srv.serve_forever, daemon=True)
    t.start()
    _H.status, _H.seen = 200, []
    yield "http://127.0.0.1:%d/v1" % srv.server_port
    srv.shutdown()


def test_call_openai_returns_finish_reason_and_sends_key(server):
    import run_eval

    class A:
        base_url, model, max_tokens, think, provider, zdr = server, "m", 10, False, None, False
    text, usage, fin = run_eval.call_openai(A, [{"role": "user", "content": "x"}], key="K")
    assert fin == "stop" and usage["cost"] == 0.5 and _H.seen == ["Bearer K"]


def test_call_openai_401_aborts_immediately(server):
    import run_eval
    _H.status = 401

    class A:
        base_url, model, max_tokens, think, provider, zdr = server, "m", 10, False, None, False
    with pytest.raises(run_eval.AuthError):
        run_eval.call_openai(A, [{"role": "user", "content": "x"}], key="bad")
    assert len(_H.seen) == 1     # no retries on a rejected key


def test_resolve_key_defaults_to_openrouter_env(monkeypatch):
    import run_eval

    class A:
        key_env, base_url = None, "https://openrouter.ai/api/v1"
    monkeypatch.setenv("OPENROUTER_API_KEY", "abc")
    assert run_eval.resolve_key(A) == "abc"
    A.base_url = "http://127.0.0.1:8080/v1"
    assert run_eval.resolve_key(A) is None


def test_prompt_flag_is_required():
    r = subprocess.run([sys.executable, os.path.join(EH, "run_eval.py"), "--backend", "dry", "--name", "x"], capture_output=True, text=True)
    assert r.returncode != 0 and "--prompt" in r.stderr

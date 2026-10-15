"""Verdict-policy switches (audit D9). Every switch defaults to the historical behaviour so published verdicts and already-built
training rows do not move; flipping one is a deliberate, recorded decision (see docs/POLICY_D9.md).

``FT_STRICT_D9=1`` enables both D9 items together:
  * no zero-size pardon: a bar widget with zero size stays an ERROR even when its source has a ``visible:``/``width:`` conditional;
  * "Binding loop detected" attributed to the plugin is an ERROR, not a soft warning.
``active()`` is stamped into every report (``report_meta()['policies']``) and into ``rules_hash``-adjacent cache keys.
"""
import os


def strict_d9():
    return os.environ.get("FT_STRICT_D9", "").strip().lower() in ("1", "true", "yes", "on")


def active():
    return {"strict_d9": strict_d9()}

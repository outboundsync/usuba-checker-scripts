import hashlib
import os

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))


def test_scan_public_matches_recorded_hash():
    """tools/scan_public.py is copied into both repos. The recorded hash must equal the file; update tools/scan_public.sha256 in BOTH repos together."""
    h = hashlib.sha256(open(os.path.join(ROOT, "tools", "scan_public.py"), "rb").read()).hexdigest()
    rec = open(os.path.join(ROOT, "tools", "scan_public.sha256")).read().split()[0]
    assert h == rec

import hashlib
import json

from waterjet_lab.verification import run_verification


def test_verification_report_contains_reproducible_evidence(tmp_path):
    report = run_verification(tmp_path)
    assert report["all_passed"]
    assert len(report["checks"]) == 7
    for filename, expected in report["trace_sha256"].items():
        raw = (tmp_path / filename).read_bytes()
        assert b"\r" not in raw  # canonical LF keeps hashes stable through Git on Windows/Linux
        assert hashlib.sha256(raw).hexdigest() == expected
    assert json.loads((tmp_path / "verification.json").read_text())["all_passed"]

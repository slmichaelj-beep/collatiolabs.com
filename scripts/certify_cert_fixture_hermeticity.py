#!/usr/bin/env python3
"""certify_cert_fixture_hermeticity — cert fixtures must not dirty real .anima.

Some older live-path subcerts used synthetic creatures but ran part of their setup outside the
shared hermetic temp store. This cert snapshots the known synthetic-fixture footprint in the real
store, runs the formerly leaky cert family, and fails if any synthetic fixture file is created or
mutated under the user's real .anima.

Exit 0 == CERTIFIED; 1 == FAIL.
"""
from __future__ import annotations

import hashlib
import os
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
REAL_ANIMA = ROOT / ".anima"

SYNTHETIC_MARKERS = (
    "SecBaseCert",
    "HPCert",
    "AiSecCert",
    "PrivCert",
    "PrivPortCopy",
    "SecureStoreCert",
    "st_g0p_exp",
)
SENSITIVE_FIXTURE_FILES = {
    "model-usage.json",
    "security_events.jsonl",
    "Vera.continuity.jsonl",
    "Vera.history.json",
    "Vera.intake.jsonl",
    "Vera.json",
    "Vera.mem.json",
    "Vera.metrics.jsonl",
    "Vera.meaning.jsonl",
    "privacy/Vera.privacy_receipts.jsonl",
    "traces/whole_mri/Vera.jsonl",
    "Vera.trajectory.jsonl",
    "privacy/global.egress.jsonl",
}
SENSITIVE_FIXTURE_PREFIXES = (
    "Vera.intake_staging/",
)
TARGET_CERTS = (
    "certify_security_baseline.py",
    "certify_host_pressure.py",
    "certify_ai_security.py",
    "certify_privacy.py",
    "certify_live_ux.py",
    "certify_response_latency.py",
    "certify_total_reality.py",
)


def _selected(rel: Path) -> bool:
    rel_s = rel.as_posix()
    return (
        any(marker in rel_s for marker in SYNTHETIC_MARKERS)
        or rel_s in SENSITIVE_FIXTURE_FILES
        or any(rel_s.startswith(prefix) for prefix in SENSITIVE_FIXTURE_PREFIXES)
    )


def _fingerprint() -> dict[str, str]:
    out: dict[str, str] = {}
    if not REAL_ANIMA.exists():
        return out
    for path in sorted(REAL_ANIMA.rglob("*")):
        if not path.is_file():
            continue
        rel = path.relative_to(REAL_ANIMA)
        if not _selected(rel):
            continue
        h = hashlib.sha256()
        h.update(rel.as_posix().encode("utf-8"))
        try:
            h.update(path.read_bytes())
        except OSError:
            h.update(b"<unreadable>")
        out[rel.as_posix()] = h.hexdigest()
    return out


def _run_cert(script: str) -> tuple[bool, str]:
    env = dict(os.environ)
    env.pop("ANIMA_CERT_LIVE_MODEL_ADVISORY", None)
    cp = subprocess.run(
        [sys.executable, str(ROOT / "scripts" / script)],
        cwd=str(ROOT),
        env=env,
        capture_output=True,
        text=True,
        timeout=600,
    )
    lines = [ln for ln in (cp.stdout or "").splitlines() if "CERT:" in ln or "CERTIFIED" in ln]
    verdict = lines[-1].strip() if lines else "(no verdict line)"
    if cp.returncode != 0 and cp.stderr:
        verdict += " stderr=" + cp.stderr[-400:].replace("\n", " ")
    return cp.returncode == 0 and "CERTIFIED" in verdict and "FAIL" not in verdict, verdict


def main() -> int:
    fails: list[str] = []

    def ck(label: str, cond: bool):
        print(("  ok   " if cond else "  XX   ") + label)
        if not cond:
            fails.append(label)

    print("CERT FIXTURE HERMETICITY — synthetic certs do not dirty real .anima")
    print("=" * 82)

    before = _fingerprint()
    cert_results = []
    for script in TARGET_CERTS:
        ok, verdict = _run_cert(script)
        cert_results.append((script, ok, verdict))
        ck(f"{script} returns certified", ok)

    after = _fingerprint()
    changed = sorted(
        rel for rel in set(before) | set(after)
        if before.get(rel) != after.get(rel)
    )
    ck("real .anima synthetic-fixture footprint is byte-identical before/after", not changed)

    if changed:
        print("  changed fixture paths:")
        for rel in changed:
            print("    - " + rel)
    for script, ok, verdict in cert_results:
        print("  %-34s %s" % (script, verdict if ok else "FAIL: " + verdict))

    green = not fails
    print("\nCERT-FIXTURE-HERMETICITY CERT: " + ("CERTIFIED" if green else f"FAIL ({len(fails)})"))
    return 0 if green else 1


if __name__ == "__main__":
    raise SystemExit(main())

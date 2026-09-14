#!/usr/bin/env python3
"""certify_host_adaptive_expansion — benchmark downgrade + portability + support matrix + docs.

Benchmark-based downgrade steps the profile down on slow chat / high pressure / low disk.
Portability flags cross-host cert results stale + requires .anima migration confirmation.
The support matrix + docs are capability-certified (Host Fit), never chip-generation requirements.
"""
from __future__ import annotations

import sys, tempfile, time
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))
from anima.host import profile as prof, portability, support_matrix   # noqa: E402

oks, fails = [], []
def ck(l, c): (oks if c else fails).append(l); print(("  ok   " if c else "  XX   ") + l)


def main() -> int:
    t0 = time.perf_counter()
    print("HOST-ADAPTIVE EXPANSION — benchmark downgrade, portability, capability-certified support")
    print("=" * 92)

    # ---- benchmark downgrade -----------------------------------------------------------------
    base = prof.select_with_benchmark(36)
    ck("1. fast 36GB host holds the recommended Performance profile",
       base["recommended"] == "Performance" and base["selected"] == "Performance")
    slow = prof.select_with_benchmark(36, simple_chat_ms=9000)
    ck("2. slow simple chat downgrades a step (Performance -> Balanced)",
       slow["selected"] == "Balanced")
    press = prof.select_with_benchmark(64, host_pressure="high")
    ck("3. high host pressure downgrades a step (Ultra -> Performance)",
       press["selected"] == "Performance")
    disk = prof.select_with_benchmark(24, disk_free_gb=5)
    ck("4. low disk downgrades a step (Balanced -> Portable)", disk["selected"] == "Portable")
    stack = prof.select_with_benchmark(36, simple_chat_ms=9000, disk_free_gb=5)
    ck("5. multiple misses stack downward (Performance -> Balanced -> Portable)",
       stack["selected"] == "Portable" and len(stack["reasons"]) >= 2)

    # ---- portability -------------------------------------------------------------------------
    with tempfile.TemporaryDirectory() as td:
        st = Path(td); N = "PortCert"
        rec = portability.register_current(N, role="primary_daily", store=st)
        ck("6. the current host registers in the host registry (host_id + role)",
           rec["host_id"] and rec["role"] == "primary_daily")
        ck("7. a report from another host is NOT treated as from this host",
           not portability.is_report_from_this_host("deadbeefdeadbeef"))
        ck("8. .anima migration requires explicit confirmation (never automatic)",
           portability.migration_requires_confirmation()["automatic"] is False)

    # ---- support matrix + docs ----------------------------------------------------------------
    m = support_matrix.build(write_docs=True)
    ck("9. support is capability-certified (Host Fit), minimum = Portable-certified",
       "Host Fit" in m["doctrine"] and m["minimum_supported"] == "Portable-certified")
    ck("10. Intel Macs are Unsupported; no chip-generation hard requirement in the doctrine",
       any(r["class"] == "Intel Mac" and r["likely"] == "Unsupported" for r in m["matrix"])
       and "generation" in m["doctrine"])
    doc = (ROOT / "docs" / "system_requirements.md")
    ck("11. docs match the policy (Host Fit language, examples not requirements)",
       doc.exists() and "Host Fit" in doc.read_text() and "not by chip generation" in doc.read_text())

    green = not fails
    try:
        from anima.verification import cert_result as cr
        cr.emit("certify_host_adaptive_expansion", "green" if green else "red",
                files_observed=["anima/host/profile.py", "anima/host/portability.py",
                                "anima/host/support_matrix.py"],
                report_paths=["reports/apple_support_matrix.json"],
                duration_sec=time.perf_counter() - t0, failures=fails)
    except Exception as e:
        print("  (emit failed: %r)" % e)
    print("\nHOST-ADAPTIVE-EXPANSION CERT: " + ("CERTIFIED" if green else "FAIL (%d)" % len(fails)))
    return 0 if green else 1


if __name__ == "__main__":
    sys.exit(main())

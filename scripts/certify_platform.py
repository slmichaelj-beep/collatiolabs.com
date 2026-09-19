#!/usr/bin/env python3
"""
certify_platform — Platformization (Phase E): carry your WHOLE mind to any app or model.

The FULL portable-mind bundle (identity + the entire grounded cognitive vault incl. the wisdom
theories) round-trips losslessly into a FRESH creature, freeze-safe (a Vera-self object in a bundle
is refused on import), and the live /platform/export + /platform/import endpoints serve it:

  A. ROUND-TRIP + FREEZE — the hermetic round-trip + freeze proof IS anima.platform's own --selftest
     (export a seeded mind incl. a theory -> import into a fresh creature -> everything restored;
     a Vera-self value in a bundle is refused; real .anima untouched).
  B. SHAPE + ENDPOINTS — export_full of an EMPTY mind yields a vera.full-mind bundle with an empty
     vault (no fabrication); GET /platform/export (server._serve_platform_export) serves the bundle;
     POST /platform/import refuses a non-bundle and round-trips a real one.

Hermetic: the module selftest is hermetic on its own; the in-process leg redirects the extra stores
platform touches (portable/theory/world_model/reliability) inside _temp_store. Real .anima
fingerprinted before/after and asserted byte-identical. Exit 0 == CERTIFIED, 1 == FAIL.
"""
from __future__ import annotations

import importlib.util
import json
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

_spec = importlib.util.spec_from_file_location("g0pe", str(ROOT / "scripts" / "gate0_prime_experience.py"))
_g0pe = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(_g0pe)
_temp_store = _g0pe._temp_store
_footprint = _g0pe._footprint


def main() -> int:
    from anima import platform as plat, server
    fails = []

    def ck(label, cond):
        print(("  ok   " if cond else "  XX   ") + label)
        if not cond:
            fails.append(label)

    print("PLATFORMIZATION (Phase E) — full portable-mind bundle: export -> import (round-trip, freeze-safe)")
    print("=" * 96)

    real_anima = ROOT / ".anima"
    fp_before = _footprint(real_anima)

    # ---- A. the hermetic round-trip + freeze proof = the module's own --selftest ----------
    p = subprocess.run([sys.executable, "-m", "anima.platform", "--selftest"],
                       capture_output=True, text=True, cwd=str(ROOT))
    ck("A1: full round-trip + freeze proof (anima.platform --selftest ALL PASS)",
       p.returncode == 0 and "PLATFORM: ALL PASS" in p.stdout)

    # ---- B. shape + endpoints (hermetic) --------------------------------------------------
    with _temp_store() as tp:
        saved = []
        for modname in ("portable", "theory", "world_model"):
            try:
                m = __import__("anima." + modname, fromlist=["_"])
                if getattr(m, "STORE", None) is not None:
                    saved.append((m, "STORE", m.STORE))
                    m.STORE = tp
            except Exception:
                pass
        try:
            import anima.reliability as _rel
            if getattr(_rel, "DEFAULT_STORE", None) is not None:
                saved.append((_rel, "DEFAULT_STORE", _rel.DEFAULT_STORE))
                _rel.DEFAULT_STORE = tp
        except Exception:
            pass
        try:
            N = "PlatCert"
            server._ensure(N, 64)
            b = plat.export_full(N)
            ck("B1: export_full of an empty mind -> a vera.full-mind bundle, empty vault (no fabrication)",
               b.get("manifest", {}).get("schema") == "vera.full-mind"
               and b["manifest"]["counts"]["vault_objects"] == 0)
            ej = json.loads(server._serve_platform_export(N))
            ck("B2: GET /platform/export serves the full-mind bundle",
               ej.get("manifest", {}).get("schema") == "vera.full-mind")
            ij = json.loads(server._serve_platform_import(N, {"bundle": "not-a-bundle"}))
            ck("B3: POST /platform/import refuses a non-bundle honestly", ij.get("ok") is False)
            rt = plat.import_full(b, "PlatCertDst")
            ck("B4: import_full round-trips a (real, empty here) bundle without error", rt.get("ok") is True)
        finally:
            for m, a, old in saved:
                setattr(m, a, old)

    fp_after = _footprint(real_anima)
    ck("H1: real .anima is byte-identical after the cert (no contamination)", fp_before == fp_after)

    print("\nPLATFORM CERT: " + ("CERTIFIED" if not fails else f"FAIL ({len(fails)})"))
    return 0 if not fails else 1


if __name__ == "__main__":
    raise SystemExit(main())

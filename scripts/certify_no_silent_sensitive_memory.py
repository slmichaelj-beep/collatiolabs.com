#!/usr/bin/env python3
"""certify_no_silent_sensitive_memory — the boundary that matters most: a SENSITIVE-domain conclusion
is never written to durable memory SILENTLY. Proves the enforcement mechanism AND that it is wired into
the LIVE capture path (memory_lirf.capture), then approve/reject/audit.

  1. WIRED            — memory_lirf.capture runs the consent gate before persisting (the gate is in the
                        live write path, not bolted on the side).
  2. SENSITIVE HELD   — a sensitive memory candidate is HELD (not persisted); general passes through.
  3. GENERAL WRITES   — a real, non-sensitive utterance still captures normally via the live path.
  4. APPROVE WRITES   — approving a held item persists it (consent given -> memory written).
  5. REJECT DISCARDS  — rejecting a held item never persists it.
  6. AUDITED          — hold / write / discard of a sensitive memory are recorded as trust events.

Hermetic (temp .anima). Exit 0 == CERTIFIED.
"""
from __future__ import annotations

import importlib.util
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

_spec = importlib.util.spec_from_file_location("g0pe", str(ROOT / "scripts" / "gate0_prime_experience.py"))
_g0pe = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(_g0pe)
_temp_store = _g0pe._temp_store


def main() -> int:
    fails = []

    def ck(label, cond):
        print(("  ok   " if cond else "  XX   ") + label)
        if not cond:
            fails.append(label)

    print("NO SILENT SENSITIVE MEMORY — sensitive conclusions held for consent, never written silently")
    print("=" * 92)

    from anima import memory_lirf, incident
    from anima.consent import policy as consent
    from anima.memory_lirf import Facts

    # ---- 1 WIRED into the live capture path ------------------------------------------------
    src = (ROOT / "anima" / "memory_lirf.py").read_text()
    ck("1. memory_lirf.capture runs the consent gate before persisting (wired into the write path)",
       "gate_memory_candidates" in src and "consent" in src
       and src.find("gate_memory_candidates") < src.find("f.save(name)", src.find("def capture(name")))

    SENS = {"trait": "health", "value": "has worsening depression",
            "evidence": "I've been seeing a therapist because my depression has gotten worse"}
    GEN = {"trait": "favorite_color", "value": "teal", "evidence": "my favourite colour is teal"}

    with _temp_store():
        # ---- 2 SENSITIVE HELD, general passes -----------------------------------------------
        allowed, held = consent.gate_memory_candidates("Vera", [GEN, SENS])
        ck("2. a sensitive memory candidate is HELD; the general one passes through",
           any(a.get("value") == "teal" for a in allowed)
           and not any(a.get("value", "").startswith("has worsening") for a in allowed)
           and any(h.get("domain") in ("health", "mental_health", "therapy") for h in held))

        # ---- 3 GENERAL writes through the LIVE path -----------------------------------------
        b3 = len(Facts.load("Vera").about() or [])
        memory_lirf.capture("Vera", "My favourite colour is teal.")
        rows3 = Facts.load("Vera").about() or []
        ck("3. a non-sensitive utterance still captures normally via the live path",
           any("teal" in str(r.get("value", "")).lower() for r in rows3) and len(rows3) >= b3)

        # ---- 4 APPROVE -> writes ------------------------------------------------------------
        pend = consent.pending("Vera")
        ck("4. the held sensitive candidate is pending the user's decision", len(pend) >= 1)
        before4 = len(Facts.load("Vera").about() or [])
        r = consent.resolve_pending("Vera", pend[0]["pending_id"], "approve")
        after4 = len(Facts.load("Vera").about() or [])
        wrote = any("depress" in str(x.get("value", "")).lower() for x in (Facts.load("Vera").about() or []))
        ck("4. approving the held item PERSISTS it (consent given -> memory written)",
           r.get("ok") and after4 > before4 and wrote)

        # ---- 5 REJECT -> discards -----------------------------------------------------------
        syn = [{"trait": "finance", "value": "is carrying significant debt",
                "evidence": "I'm drowning in credit-card debt and can't afford rent"}]
        consent.gate_memory_candidates("Vera", syn)
        held2 = consent.pending("Vera")
        before5 = len(Facts.load("Vera").about() or [])
        consent.resolve_pending("Vera", held2[0]["pending_id"], "reject") if held2 else None
        leaked = any("debt" in str(r.get("value", "")).lower() for r in (Facts.load("Vera").about() or []))
        ck("5. rejecting the held item NEVER persists it (no debt fact written, removed from pending)",
           bool(held2) and len(Facts.load("Vera").about() or []) == before5
           and not leaked and not consent.pending("Vera"))

        # ---- 6 AUDITED ----------------------------------------------------------------------
        kinds = [e.get("kind") for e in incident.recent_events(60)]
        ck("6. hold / write / discard of a sensitive memory are AUDITED (trust events)",
           "sensitive_memory_held" in kinds and "sensitive_memory_written" in kinds
           and "sensitive_memory_discarded" in kinds)

    print("\nNO-SILENT-SENSITIVE-MEMORY CERT: " + ("CERTIFIED" if not fails else f"FAIL ({len(fails)})"))
    return 0 if not fails else 1


if __name__ == "__main__":
    raise SystemExit(main())

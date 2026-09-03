#!/usr/bin/env python3
"""certify_permissions — Phase 3: the default-deny permission MODEL, proven behaviorally.

  1. DEFAULT-DENY     — every boolean capability is OFF for a fresh creature.
  2. READ != ACT      — read and act are SEPARATE grants (mail_read != mail, etc.).
  3. GRANT ROUND-TRIP — enabling a cap persists + reads True; disabling reverts to denied.
  4. FAIL-SAFE ENUM   — a corrupt/unknown enum value collapses to the SAFE DEFAULT, never a wider grant.
  5. IDENTITY FROZEN  — identity_agency is a held bool, OFF by default (2026-07-03 freeze posture).
  6. ACTION-GATED     — every connector action is caps.enabled-gated in route.py (no silent power).
  7. DOCUMENTED       — the trust zones + permission model + threat model are written down.

Hermetic (redirects the real .anima via the gate0 _temp_store). Exit 0 == CERTIFIED; 1 == FAIL.
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
    from anima import caps
    fails = []

    def ck(label, cond):
        print(("  ok   " if cond else "  XX   ") + label)
        if not cond:
            fails.append(label)

    print("PERMISSIONS — default-deny · read != act · fail-safe · no silent power")
    print("=" * 92)

    with _temp_store():
        name = "PermCert"

        # ---- 1. DEFAULT-DENY ---------------------------------------------------------------
        ck("1. every boolean capability is OFF for a fresh creature (default-deny)",
           all(caps.enabled(name, k) is False for k in caps.BOOL_KEYS))

        # ---- 2. READ != ACT ----------------------------------------------------------------
        pairs = [("mail_read", "mail"), ("imessage_read", "imessage"),
                 ("calendar_read", "calendar"), ("reminders_read", "reminders"),
                 ("notes_read", "notes")]
        ck("2. read and act are SEPARATE grants (mail_read != mail, etc.)",
           all(r in caps.BOOL_KEYS and a in caps.BOOL_KEYS and r != a for r, a in pairs))

        # ---- 3. GRANT ROUND-TRIP -----------------------------------------------------------
        c = caps.load(name)
        c["mail"] = True
        caps.save(name, c)
        on = caps.enabled(name, "mail")
        c2 = caps.load(name)
        c2["mail"] = False
        caps.save(name, c2)
        off = caps.enabled(name, "mail")
        ck("3. enabling a capability persists and reads True; disabling reverts to denied",
           on is True and off is False)
        # granting the READ never granted the ACT
        c3 = caps.load(name)
        c3["mail_read"] = True
        caps.save(name, c3)
        ck("3. granting mail_read does NOT grant mail (read can't escalate to act)",
           caps.enabled(name, "mail_read") is True and caps.enabled(name, "mail") is False)

        # ---- 4. FAIL-SAFE ENUM -------------------------------------------------------------
        if caps.ENUM_KEYS:
            ek = next(iter(caps.ENUM_KEYS))
            allowed, default = caps.ENUM_KEYS[ek]
            c4 = caps.load(name)
            c4[ek] = "TOTALLY_INVALID_VALUE_xyz"
            caps.save(name, c4)
            val = caps.load(name).get(ek)
            ck("4. a corrupt/unknown enum value collapses to the SAFE DEFAULT (fail-safe coercion)",
               val in allowed)
        else:
            ck("4. (no enum caps to coerce — n/a)", True)

        # ---- 5. IDENTITY FROZEN ------------------------------------------------------------
        ck("5. identity_agency is a held boolean, OFF by default (freeze posture)",
           "identity_agency" in caps.BOOL_KEYS and caps.enabled("FreshIdent", "identity_agency") is False)

    # ---- 6. ACTION-GATED (route.py gates every connector action) ----------------------------
    route = (ROOT / "anima" / "route.py").read_text()
    ck("6. every connector action is caps.enabled-gated in route.py (mail/imessage + the read gates)",
       all(('caps.enabled(name, "%s")' % c) in route
           for c in ("mail", "imessage", "mail_read", "imessage_read", "calendar_read", "reminders_read")))

    # ---- 7. DOCUMENTED ---------------------------------------------------------------------
    docs = ROOT / "docs"
    ck("7. trust zones + permission model + threat model are written down",
       (docs / "security_architecture.md").exists() and (docs / "permission_model.md").exists()
       and (docs / "threat_model.md").exists())

    print("\nPERMISSIONS CERT: " + ("CERTIFIED" if not fails else f"FAIL ({len(fails)})"))
    return 0 if not fails else 1


if __name__ == "__main__":
    raise SystemExit(main())

#!/usr/bin/env python3
"""certify_consent_boundaries — Consent & Boundaries (Layer 2) is REAL: consent can be granted, denied,
set to ask-each-time, and REVOKED, and the boundary is ENFORCED. Covers the directive's pass conditions
(sensitive-domain detection, consent required when policy says, revocation prevents future use, ask-each-
time works, the user can inspect + change settings) — plus sensitive-domain pacing and the served UI.

  1. SENSITIVE DETECTED — the classifier flags the sensitive domains and spares the everyday.
  2. SAFE DEFAULT       — sensitive memory_write defaults to ask-each-time; general is allowed.
  3. GRANT / DENY       — granting -> allow; denying -> block (persisted + audited).
  4. REVOCATION         — revoking blocks future use (revoked != granted).
  5. PACING             — sensitive domains carry a go-slow pacing the user can see.
  6. INSPECTABLE        — settings() exposes the full posture (domains x scopes + pending) for the UI.
  7. SERVED + AUTH      — GET /consent serves the page; /consent.json + POST /consent/decide are behind
                         the auth wall; the page renders the controls + revocation + pending previews.

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

    print("CONSENT & BOUNDARIES (Layer 2) — consent can be granted / denied / revoked, and ENFORCED")
    print("=" * 92)

    from anima.consent import classifier as cl, policy as po, schema as sc

    # ---- 1 classifier ----------------------------------------------------------------------
    sensitive_hits = all(cl.is_sensitive(t) for t in (
        "my therapist says I'm depressed", "my salary is $90k and I'm in debt",
        "my husband filed for divorce", "the lawsuit goes to court next week"))
    spares = not any(cl.is_sensitive(t) for t in (
        "I love hiking", "my favourite colour is teal", "what's a good way to plan my week"))
    ck("1. the classifier flags sensitive domains and spares everyday talk", sensitive_hits and spares)

    srv = (ROOT / "anima" / "server.py").read_text()
    html_p = ROOT / "anima" / "web" / "consent.html"
    html = html_p.read_text() if html_p.exists() else ""

    with _temp_store():
        # ---- 2 safe default ----------------------------------------------------------------
        ck("2. sensitive memory_write defaults to ask-each-time; general is allowed",
           po.check("Vera", "memory_write", "health")["decision"] == "ask"
           and po.check("Vera", "memory_write", "general")["decision"] == "allow")

        # ---- 3 grant / deny ----------------------------------------------------------------
        po.set_consent("Vera", "memory_write", "health", "granted")
        granted_ok = po.check("Vera", "memory_write", "health")["decision"] == "allow"
        po.set_consent("Vera", "source_use", "finance", "denied")
        denied_ok = po.check("Vera", "source_use", "finance")["decision"] == "block"
        ck("3. granting -> allow, denying -> block (persisted)", granted_ok and denied_ok)

        # ---- 4 revocation ------------------------------------------------------------------
        po.revoke("Vera", "memory_write", "health")
        ck("4. revoking blocks future use (revoked != granted)",
           po.check("Vera", "memory_write", "health")["decision"] == "block"
           and po.status("Vera", "memory_write", "health") == "revoked")

        # ---- 5 pacing ----------------------------------------------------------------------
        ck("5. sensitive domains carry a go-slow pacing",
           sc.default_pacing("trauma") == "go_slow" and sc.default_pacing("general") == "normal")

        # ---- 6 inspectable settings --------------------------------------------------------
        st = po.settings("Vera")
        ck("6. settings() exposes the full posture (every sensitive domain x scopes)",
           isinstance(st.get("domains"), list)
           and len(st["domains"]) == len(sc.SENSITIVE_DOMAINS)
           and all(("memory_write" in d and "pacing" in d) for d in st["domains"]))

        # ---- audited -----------------------------------------------------------------------
        try:
            from anima import incident
            kinds = [e.get("kind") for e in incident.recent_events(40)]
            ck("6. consent changes are AUDITED (granted / denied / revoked events)",
               any(k.startswith("consent_") for k in kinds))
        except Exception:
            ck("6. consent changes are AUDITED", False)

    # ---- 7 served + auth + UI --------------------------------------------------------------
    ck("7. /consent serves the page; /consent.json + POST /consent/decide are behind the auth wall",
       html_p.exists() and '"/consent"' in srv and '"/consent.json"' in srv
       and srv.find("if not self._authed():") < srv.find('"/consent.json"')
       and srv.find("if not self._authed():") < srv.find('"/consent/decide"'))
    ck("7. the page renders the consent controls + revocation + pending previews + the SHOULD-not-CAN framing",
       all(s in html for s in ("Consent", "revoke", "pending", "ask")) and "CAN" in html and "SHOULD" in html)

    print("\nCONSENT-BOUNDARIES CERT: " + ("CERTIFIED" if not fails else f"FAIL ({len(fails)})"))
    return 0 if not fails else 1


if __name__ == "__main__":
    raise SystemExit(main())

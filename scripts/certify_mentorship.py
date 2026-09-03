#!/usr/bin/env python3
"""certify_mentorship — Mentorship Support (Human Operating Layer, Layer 6) is REAL: Vera offers
guidance as a tradeoff (options + honest pros/cons + a recommendation) but the USER always decides, and
the output is provably NON-COERCIVE — the keystone of this layer.

  1. TRADEOFF SHAPE   — a tradeoff carries >= 2 options, each with pros AND cons, the decision owned by
                        the user, and it is suggest-only (execution_allowed=False / requires_approval).
  2. ALTERNATIVES KEPT— every option shows a genuine downside (no stacked deck) and the recommendation
                        is OPTIONAL — never the only option on offer.
  3. NON-COERCIVE     — a normal tradeoff passes the guard; its visible text carries no pressure phrase.
  4. GUARD BITES      — (the keystone) a forced coercive tradeoff — one option / decision taken from the
                        user / execution permitted / 'you must' language — is REJECTED, and the fail-safe
                        neutralises it (decision returned to the user, pushed recommendation dropped).
  5. REAL SUGGESTIONS — a REAL agency suggestion (through the approval queue) becomes a non-coercive
                        tradeoff with a standing 'do nothing' alternative.
  6. SUGGEST-ONLY     — nothing the layer produces is executable (inherits agency: execution_allowed False).
  7. SERVED + AUTH    — the tradeoffs ride through _mentorship_data; GET /mentorship serves the page.

Hermetic. Exit 0 == CERTIFIED.
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

    print("MENTORSHIP (Layer 6) — guidance without control; provably non-coercive")
    print("=" * 92)

    from anima.mentorship import explainer, policy, schema
    from anima import server, agency_suggest

    html = (ROOT / "anima" / "web" / "mentorship.html").read_text() if (ROOT / "anima" / "web" / "mentorship.html").exists() else ""
    srv = (ROOT / "anima" / "server.py").read_text()

    t = explainer.explain_tradeoff(
        "Move the dentist appointment?",
        [{"label": "Move to Friday", "pros": ["Avoids the 3pm clash"], "cons": ["Friday is fuller"]},
         {"label": "Keep Tuesday", "pros": ["Already booked"], "cons": ["Clashes with the 3pm"]}],
        recommend=0, reason="Friday avoids the clash, though it's a busier day — your call.")

    # ---- 1 tradeoff shape ----------------------------------------------------------------------
    ck("1. a tradeoff offers >= 2 options (each with pros AND cons), user-owned + suggest-only",
       len(t["options"]) >= schema.MIN_OPTIONS
       and all(o["pros"] and o["cons"] for o in t["options"])
       and t["decision_owner"] == "user" and t["execution_allowed"] is False and t["requires_approval"] is True)

    # ---- 2 alternatives kept -------------------------------------------------------------------
    ck("2. every option shows a real downside (no stacked deck) and the recommendation is optional",
       all(any(str(c).strip() for c in o["cons"]) for o in t["options"])
       and policy.recommendation_is_optional(t))

    # ---- 3 non-coercive ------------------------------------------------------------------------
    ck("3. a normal tradeoff is non-coercive (guard passes; no pressure phrase in the visible text)",
       policy.is_non_coercive(t) and policy.scan_for_coercion(t) == [])

    # ---- 4 guard BITES (the keystone) ----------------------------------------------------------
    evil = {"decision": "Do the thing", "decision_owner": "vera", "execution_allowed": True,
            "options": [{"label": "Do it", "pros": ["good"], "cons": []}],
            "you_decide": "you must act now — this is the only option, no choice",
            "recommendation": {"label": "Do it", "reason": "just trust me"}}
    reasons = policy.scan_for_coercion(evil)
    ck("4. the guard REJECTS a forced coercive tradeoff (single option / not user-owned / executable / 'you must')",
       (not policy.is_non_coercive(evil)) and len(reasons) >= 3)
    safe = policy.safe_tradeoff(evil)
    ck("4. the fail-safe NEUTRALISES coercion (decision returned to the user; pushed recommendation dropped)",
       safe["decision_owner"] == "user" and safe["execution_allowed"] is False
       and safe["recommendation"] is None and safe.get("coercion_blocked"))

    # ---- 5 real suggestions + 6 suggest-only ---------------------------------------------------
    with _temp_store():
        from anima import agency_approval_queue as _q
        s = agency_suggest.make_suggestion("Draft a reply to Mara",
                                           "You said you'd get back to her today", risk="low", action_type="draft")
        _q.submit("Vera", s)
        d = server._mentorship_data("Vera")
        tos = d.get("tradeoffs") or []
        ck("5. a REAL pending suggestion becomes a non-coercive tradeoff with a 'do nothing' alternative",
           d.get("count", 0) >= 1 and tos
           and any("Keep things" in o["label"] for o in tos[0]["options"])
           and d.get("all_non_coercive") is True)
        ck("6. NOTHING the layer produces is executable (suggest-only inherited from agency)",
           all(t2.get("execution_allowed") is False for t2 in tos)
           and agency_suggest.is_executable(s) is False)

    # ---- 7 served + UI -------------------------------------------------------------------------
    ck("7. the tradeoffs ride through _mentorship_data + a GET /mentorship route exists",
       hasattr(server, "_mentorship_data") and "/mentorship" in srv and "mentorship.json" in srv)
    ck("7. the page renders the tradeoff (options/pros/cons + 'you decide') with the no-control law",
       bool(html) and "Mentorship" in html and "mentorView" in html and "you decide" in html.lower())

    print("\nMENTORSHIP CERT: " + ("CERTIFIED" if not fails else f"FAIL ({len(fails)})"))
    return 0 if not fails else 1


if __name__ == "__main__":
    raise SystemExit(main())

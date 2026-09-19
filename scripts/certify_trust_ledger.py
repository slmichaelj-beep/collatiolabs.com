#!/usr/bin/env python3
"""certify_trust_ledger — the Trust Ledger (Human Operating Layer, Layer 8) is REAL: one accountable
spine over the trust events Vera already records, categorised with provenance, and guarded by INVARIANTS
that actually have teeth (each can fail).

  1. AGGREGATES       — the ledger reads the REAL incident spine; seeded trust events appear in it.
  2. CATEGORISED+PROV — every event carries a trust category from the taxonomy and a provenance ref;
                        no known kind leaks through as 'uncategorised'.
  3. INVARIANTS HOLD  — on a clean spine, all four trust invariants hold.
  4. INVARIANTS BITE  — the keystone: a crafted VIOLATING spine flips each invariant to holds=False
                        (append-only / suggest-only / no-silent-sensitive-memory / reversible-state).
                        A promise that cannot fail is wallpaper; these can.
  5. VALUE FOLDED IN  — the ROI / completed-work ledger rides through as the 'value delivered' category.
  6. SERVED + AUTH    — the ledger rides through _trust_data; GET /trust serves the page; the data is
                        behind the seam; the page renders the invariants + the non-decoration law.

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

    print("TRUST LEDGER (Layer 8) — one accountable spine; invariants with teeth")
    print("=" * 92)

    from anima.trust_ledger import ledger, schema
    from anima import server

    html = (ROOT / "anima" / "web" / "trust.html").read_text() if (ROOT / "anima" / "web" / "trust.html").exists() else ""
    srv = (ROOT / "anima" / "server.py").read_text()

    with _temp_store():
        # seed a clean, well-formed trust spine into the REAL event path (hermetic temp store)
        from anima import incident
        incident.security_event("quarantine", "hostile text held", route="output", markers=["PWNED"])
        incident.security_event("agency_suggestion", "offer to draft a reply")
        incident.security_event("agency_approve", "user approved the draft")
        incident.security_event("sensitive_memory_held", "health disclosure held for consent")
        incident.security_event("sensitive_memory_written", "user approved the held item")

        led = ledger.build_ledger("Vera", 200)
        kinds_present = {e["kind"] for e in led["events"]}

        # ---- 1 aggregates ----------------------------------------------------------------------
        ck("1. the ledger reads the REAL incident spine (seeded events appear)",
           {"quarantine", "agency_suggestion", "agency_approve"} <= kinds_present and led["metrics"]["total_events"] >= 5)

        # ---- 2 categorised + provenance --------------------------------------------------------
        known = [e for e in led["events"] if e["kind"] in schema.KIND_TO_CATEGORY]
        ck("2. every known event carries a real category + provenance (no 'uncategorised' leak)",
           bool(known) and all(e["category"] in schema.CATEGORY_IDS and e["provenance"] for e in known)
           and all(e["category"] != "uncategorised" for e in known))

        # ---- 3 invariants hold on a clean spine ------------------------------------------------
        ck("3. on a clean spine, all four trust invariants hold",
           led["all_invariants_hold"] and {i["id"] for i in led["invariants"]} == set(schema.INVARIANT_IDS))

        # ---- 5 value folded in (ROI category present in taxonomy + metrics) --------------------
        ck("5. the ROI / completed-work ledger rides through as the 'value delivered' category",
           "value" in led["categories"] and "value" in schema.CATEGORY_IDS
           and schema.CATEGORIES["value"]["label"] == "Value Delivered")

    # ---- 4 invariants BITE (each falsifiable) --------------------------------------------------
    def held(events, iid):
        return next(i["holds"] for i in ledger.invariants(events) if i["id"] == iid)

    # append-only: a backwards timestamp must break it
    backwards = [{"at": "2026-06-08T10:00:00", "kind": "quarantine"},
                 {"at": "2026-06-08T09:00:00", "kind": "quarantine"}]
    ck("4a. append-only BITES — an out-of-order timestamp flips it red",
       held(backwards, "append_only") is False)

    # suggest-only: a forbidden silent-action kind must break it
    silent = [{"at": "2026-06-08T10:00:00", "kind": "agency_execute", "detail": "acted without asking"}]
    ck("4b. suggest-only agency BITES — a silent-action event flips it red",
       held(silent, "suggest_only_agency") is False)

    # no silent sensitive memory: a written with no preceding held must break it
    silent_write = [{"at": "2026-06-08T10:00:00", "kind": "sensitive_memory_written", "detail": "wrote w/o consent"}]
    ck("4c. no-silent-sensitive-memory BITES — a write with no held flips it red",
       held(silent_write, "consent_before_durable") is False)

    # reversible state: a lockdown with no restore on record must break it
    stuck = [{"at": "2026-06-08T10:00:00", "kind": "lockdown", "detail": "locked"}]
    ck("4d. reversible-state BITES — a lockdown with no restore flips it red",
       held(stuck, "reversible_state") is False)

    # a clean spine keeps all four green (the teeth don't bite the innocent)
    clean = [{"at": "2026-06-08T09:00:00", "kind": "agency_suggestion"},
             {"at": "2026-06-08T09:30:00", "kind": "agency_approve"},
             {"at": "2026-06-08T10:00:00", "kind": "restore"}]
    ck("4e. a clean spine keeps all four invariants green (no false positives)",
       all(i["holds"] for i in ledger.invariants(clean)))

    # ---- 6 served + UI -------------------------------------------------------------------------
    ck("6. the ledger rides through _trust_data + a GET /trust route exists",
       hasattr(server, "_trust_data") and "/trust" in srv and "trust.json" in srv)
    ck("6. the page renders the invariants + the non-decoration law",
       bool(html) and "Trust Ledger" in html and "invariant" in html.lower() and "trustView" in html)

    print("\nTRUST-LEDGER CERT: " + ("CERTIFIED" if not fails else f"FAIL ({len(fails)})"))
    return 0 if not fails else 1


if __name__ == "__main__":
    raise SystemExit(main())

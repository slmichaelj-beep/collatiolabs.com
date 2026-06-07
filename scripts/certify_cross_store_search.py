#!/usr/bin/env python3
"""
certify_cross_store_search — the cross-store knowledge search (/search) and its hard non-blur contract.

One search box reaches every store — personal memory (LIRF), the uploaded Reference Library, learned
LERF skills, the personal model, and the world model — and the result of each is labeled with its TRUE
source_type, which is NEVER blurred (your private memory is never mislabeled as an external reference,
and vice-versa). Certified through the SAME intake_search.search + server._serve_search the UI calls:

  A. LABELED HITS — a token stored as a personal FACT is found with source_type='memory'; a token
     stored as an uploaded REFERENCE is found with a reference-family source_type (reference/web_page/
     uploaded_pdf) — and NEVER 'memory'. The two source_types differ: memory and external are not blurred.
  B. SCOPES + EMPTY — scopes=[reference] hides memory hits and vice-versa; an empty/whitespace query
     returns [] (no scan, no noise).
  C. ENDPOINT — server._serve_search returns {ok:True, results:[...]} for a real query and {ok:False}
     (q required) for an empty one.

Hermetic: every store via _temp_store; the real .anima is fingerprinted before/after and asserted
byte-identical. Exit 0 == CERTIFIED, 1 == FAIL.
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
_footprint = _g0pe._footprint


def main() -> int:
    from anima import intake_search as S, intake_queue, memory_lirf, server
    fails = []

    def ck(label, cond):
        print(("  ok   " if cond else "  XX   ") + label)
        if not cond:
            fails.append(label)

    print("CROSS-STORE SEARCH — one box, every store, source_type NEVER blurred")
    print("=" * 70)

    real_anima = ROOT / ".anima"
    fp_before = _footprint(real_anima)

    with _temp_store():
        N = "SearchCert"
        server._ensure(N, 64)

        # Seed a personal FACT (memory) and an uploaded REFERENCE, each with a unique token.
        memory_lirf.capture(N, "my dog's name is Zephyrqx")   # -> durable LIRF fact (source_type memory)
        intake_queue.add_reference(
            N, source_id="src_aldermere", title="Aldermere Ledger",
            provenance={"rights_category": "user-provided", "url_or_file": "aldermere.txt"},
            chunks=[{"text": "The Aldermere ledger records a blue copper ladder of nine rungs.",
                     "idx": 0}])

        # ---- A. LABELED HITS + NON-BLUR --------------------------------------------------
        mem = S.search("Zephyrqx", name=N)
        ck("A1: a personal fact is found and labeled source_type='memory'",
           len(mem) >= 1 and all(r["source_type"] == "memory" for r in mem))
        ref = S.search("Aldermere", name=N)
        ref_types = {r["source_type"] for r in ref}
        ck("A2: an uploaded reference is found with a reference-family label, NEVER 'memory'",
           len(ref) >= 1 and "memory" not in ref_types
           and ref_types <= {"reference", "web_page", "uploaded_pdf"})
        ck("A3: memory and external source_types are distinct (the hard non-blur contract)",
           {r["source_type"] for r in mem}.isdisjoint(ref_types))

        # ---- B. SCOPES + EMPTY -----------------------------------------------------------
        ck("B1: an empty / whitespace query returns [] (no scan)",
           S.search("", name=N) == [] and S.search("   ", name=N) == [])
        only_ref = S.search("Zephyrqx", name=N, scopes=[S.SCOPE_REFERENCE])
        ck("B2: scoping to [reference] hides the memory hit", all(r["source_type"] != "memory"
                                                                  for r in only_ref))
        only_mem = S.search("Aldermere", name=N, scopes=[S.SCOPE_MEMORY])
        ck("B3: scoping to [memory] hides the reference hit",
           all(r["source_type"] == "memory" for r in only_mem))

        # ---- C. ENDPOINT -----------------------------------------------------------------
        good = server._serve_search(N, {"q": "Zephyrqx"})
        ck("C1: POST /search returns ok with results for a real query",
           good.get("ok") is True and len(good.get("results", [])) >= 1)
        empty = server._serve_search(N, {"q": "   "})
        ck("C2: POST /search refuses an empty query (q required)",
           empty.get("ok") is False and empty.get("results") == [])

    fp_after = _footprint(real_anima)
    ck("H1: real .anima is byte-identical after the cert (no contamination)", fp_before == fp_after)

    print("\nCROSS-STORE-SEARCH CERT: " + ("CERTIFIED" if not fails else f"FAIL ({len(fails)})"))
    return 0 if not fails else 1


if __name__ == "__main__":
    raise SystemExit(main())

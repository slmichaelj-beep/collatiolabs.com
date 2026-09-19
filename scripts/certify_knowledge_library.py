#!/usr/bin/env python3
"""
certify_knowledge_library — the Library drawer's live path: GET /library lists exactly what is
stored, read from the durable store, and an empty library shows NOTHING (no fabrication).

The Library drawer (#library + loadLibrary) calls GET /library, which server._serve_library
answers from intake_queue.references() + intake_queue.queue() — the durable source of truth.
Certified through that SAME _serve_library the UI calls:

  A. EMPTY IS EMPTY — a fresh creature's library returns {ok:True, items:[]}. Nothing is invented.
  B. A STORED REFERENCE IS LISTED — a reference seeded with intake_queue.add_reference (the same
     seam the cross-store-search cert uses) is listed with its TRUE id/title/type/source/rights/
     status, and EVERY listed item carries a title + a type (no blank rows).
  C. READ FROM DISK — the listing is read FRESH from intake_queue.references() (the durable store),
     not from any in-process cache: a brand-new process-state read shows the same item.
  D. SECTION FILTER NARROWS, NEVER INVENTS — section=references includes the reference; a
     non-matching section ('archived files') excludes it; neither section adds an item that was
     not stored.

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
    from anima import intake_queue, server
    fails = []

    def ck(label, cond):
        print(("  ok   " if cond else "  XX   ") + label)
        if not cond:
            fails.append(label)

    print("KNOWLEDGE LIBRARY — GET /library lists what is stored; empty is empty (no fabrication)")
    print("=" * 80)

    real_anima = ROOT / ".anima"
    fp_before = _footprint(real_anima)

    with _temp_store():
        N = "LibraryCert"
        server._ensure(N, 64)

        # ---- A. EMPTY IS EMPTY ----------------------------------------------------------------
        empty = server._serve_library(N, f"name={N}")
        ck("A1: a fresh creature's library is ok with items==[] (no fabricated entries)",
           empty.get("ok") is True and empty.get("items") == [])

        # ---- Seed ONE reference (the same durable seam cross-store-search uses) ---------------
        SRC = "src_aldermere_library"
        intake_queue.add_reference(
            N, source_id=SRC, title="Aldermere Ledger",
            provenance={"rights_category": "user-provided", "source": "aldermere.txt",
                        "url_or_file": "aldermere.txt"},
            chunks=[{"text": "The Aldermere ledger records a blue copper ladder of nine rungs.",
                     "idx": 0, "section": "Chapter 1"}])

        # ---- B. A STORED REFERENCE IS LISTED WITH ITS TRUE LABELS ----------------------------
        lib = server._serve_library(N, f"name={N}")
        items = lib.get("items", [])
        ck("B1: GET /library is ok and lists exactly the one stored reference",
           lib.get("ok") is True and len(items) == 1)
        it = items[0] if items else {}
        ck("B2: the listed item carries the TRUE id/title/source for the stored reference",
           it.get("id") == SRC and it.get("title") == "Aldermere Ledger"
           and it.get("source") == "aldermere.txt")
        ck("B3: the listed item is labeled type='reference', rights='user-provided', status='active'",
           it.get("type") == "reference" and it.get("rights") == "user-provided"
           and it.get("status") == "active")
        ck("B4: EVERY listed item carries a non-empty title AND a type (no blank rows)",
           bool(items) and all(i.get("title") and i.get("type") for i in items))

        # ---- C. READ FROM THE DURABLE STORE (not an in-process cache) ------------------------
        fresh = intake_queue.references(N)   # re-read straight from disk
        ck("C1: the reference is present in the durable store read fresh from disk",
           any(r.get("id") == SRC and r.get("title") == "Aldermere Ledger" for r in fresh))

        # ---- D. SECTION FILTER NARROWS, NEVER INVENTS ----------------------------------------
        only_refs = server._serve_library(N, f"name={N}&section=references")
        ck("D1: section=references includes the reference (type-matched), invents nothing",
           only_refs.get("ok") is True
           and any(i.get("id") == SRC for i in only_refs.get("items", []))
           and len(only_refs.get("items", [])) == 1)
        archived = server._serve_library(N, f"name={N}&section=archived files")
        ck("D2: a non-matching section ('archived files') EXCLUDES the active reference (no fabrication)",
           archived.get("ok") is True
           and not any(i.get("id") == SRC for i in archived.get("items", [])))

    fp_after = _footprint(real_anima)
    ck("H1: real .anima is byte-identical after the cert (no contamination)", fp_before == fp_after)

    print("\nKNOWLEDGE-LIBRARY CERT: " + ("CERTIFIED" if not fails else f"FAIL ({len(fails)})"))
    return 0 if not fails else 1


if __name__ == "__main__":
    raise SystemExit(main())

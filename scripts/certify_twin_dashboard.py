#!/usr/bin/env python3
"""
certify_twin_dashboard — the Personal Digital Twin composer is REAL, DETERMINISTIC, and HONEST.

twin_dashboard.compose() builds ONE read-only portrait of what Vera actually knows about the PERSON,
across five dimensions (identity / how_you_think / trajectory / what_matters / your_world), each sourced
from a real grounded per-creature store. This certifies the no-wallpaper contract for a personal
portrait — an empty store yields an honest "nothing yet", never an invented trait — through the SAME
compose() the `vera_status` founder CLI ('KNOWS YOU') renders:

  A. HONEST ON EMPTY — compose() on a FRESH person is richness 'empty', ALL five dimensions
     present=False with 0 items, coverage items_known=0, and the synthesis says nothing is grounded
     yet. No dimension fabricates a trait off an empty store.
  B. KEYED TO THE PERSON + READS THE STORES (NOT A CONSTANT) — a DIFFERENT fresh name is independently
     empty too; the portrait carries that exact person + the five declared dimension keys. So compose
     is a function OF the person's stores, not a fixed payload.
  C. GROUNDED FILLS IN, UNGROUNDED STAYS HONEST — after seeding 4 real identity facts (memory_lirf.
     capture), the identity dimension flips present=True, COUNTS the grounded facts (>=4) and its items
     mention the seeded name; an UNGROUNDED dimension (how_you_think — no personal-intelligence seeded)
     stays honestly present=False; richness rises off 'empty'; the synthesis names a present dimension
     AND the remaining gaps.
  D. DETERMINISTIC + RANKED — compose() twice on the same store is byte-identical (no randomness in the
     compose path); rank_dimensions puts a PRESENT dimension first and an ABSENT one last (richest-first).
  E. SAVE ROUND-TRIPS — save() writes valid JSON whose coverage reflects the grounded items.

Hermetic + offline: every grounded store the composer reads (memory_lirf / personal's lerf+portrait /
world_state / meaning / trajectory) is redirected into a temp dir via gate0_prime_experience._temp_store;
NO model, NO network, NO server — compose() is pure store-reads. The real .anima is fingerprinted
before/after and asserted byte-identical (read-only). Exit 0 == CERTIFIED, 1 == FAIL.
"""
from __future__ import annotations

import importlib.util
import json
import sys
import tempfile
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
    from anima import twin_dashboard as td
    fails = []

    def ck(label, cond):
        print(("  ok   " if cond else "  XX   ") + label)
        if not cond:
            fails.append(label)

    print("TWIN DASHBOARD — the personal digital twin composer is real, deterministic, and honest")
    print("=" * 86)

    real_anima = ROOT / ".anima"
    fp_before = _footprint(real_anima)

    with _temp_store():
        from anima import memory_lirf as ml
        N = "TwinDashCert"
        DIMS = {"identity", "how_you_think", "trajectory", "what_matters", "your_world"}

        # ---- A. HONEST ON EMPTY ---------------------------------------------------------
        empty = td.compose(N)
        ck("A1: a fresh person -> richness 'empty'", empty.get("richness") == "empty")
        ck("A2: the five declared dimensions are all present (keys), all present=False",
           {d["key"] for d in empty["dimensions"]} == DIMS
           and all(d["present"] is False for d in empty["dimensions"]))
        ck("A3: an empty store invents NOTHING — every dimension has 0 items and count 0",
           all(d["count"] == 0 and d["items"] == [] for d in empty["dimensions"]))
        ck("A4: coverage on empty is 0 present / 0 items_known",
           empty["coverage"]["dimensions_present"] == 0
           and empty["coverage"]["items_known"] == 0
           and empty["coverage"]["dimensions_total"] == 5)
        ck("A5: the empty synthesis honestly says nothing is grounded yet",
           "empty" in empty["synthesis"].lower() or "nothing" in empty["synthesis"].lower())

        # ---- B. KEYED TO THE PERSON + READS THE STORES (NOT A CONSTANT) -----------------
        ck("B1: the portrait names the person it was asked about", empty.get("person") == N)
        other = td.compose("TwinDashCertOther")
        ck("B2: a DIFFERENT fresh name is independently empty too (per-person read, not a cached const)",
           other.get("person") == "TwinDashCertOther" and other.get("richness") == "empty"
           and all(d["present"] is False for d in other["dimensions"]))

        # ---- C. GROUNDED FILLS IN, UNGROUNDED STAYS HONEST ------------------------------
        ml.capture(N, "my name is Lamar")
        ml.capture(N, "my birthday is March 4, 1991")
        ml.capture(N, "I work at Collatio")
        ml.capture(N, "my dog's name is Biscuit")
        t = td.compose(N)
        by = {d["key"]: d for d in t["dimensions"]}
        ck("C1: the identity dimension flips present=True after seeding real facts",
           by["identity"]["present"] is True)
        ck("C2: identity COUNTS the grounded facts (>=4)", by["identity"]["count"] >= 4)
        ck("C3: identity items mention the seeded name (grounded, not invented)",
           any("lamar" in i.lower() for i in by["identity"]["items"]))
        ck("C4: an UNGROUNDED dimension (how_you_think) stays honestly present=False",
           by["how_you_think"]["present"] is False)
        ck("C5: richness rises off 'empty' once a dimension is grounded",
           t["richness"] in ("sparse", "forming", "rich"))
        ck("C6: coverage reflects the grounded evidence (>=1 present, >=4 items_known)",
           t["coverage"]["dimensions_present"] >= 1 and t["coverage"]["items_known"] >= 4)
        ck("C7: the synthesis names a PRESENT dimension and the remaining gaps",
           "who you are" in t["synthesis"].lower() and "nothing yet" in t["synthesis"].lower())

        # ---- D. DETERMINISTIC + RANKED -------------------------------------------------
        t_again = td.compose(N)
        ck("D1: compose() twice on the same store is byte-identical (no compose-path randomness)",
           json.dumps(t, sort_keys=True) == json.dumps(t_again, sort_keys=True))
        ranked = td.rank_dimensions(t["dimensions"])
        ck("D2: rank_dimensions puts a PRESENT dimension first and an ABSENT one last (richest-first)",
           ranked[0]["present"] is True and ranked[-1]["present"] is False)
        ck("D3: identity is among the present dimensions in the ranking",
           any(d["key"] == "identity" and d["present"] for d in ranked))

        # ---- E. SAVE ROUND-TRIPS -------------------------------------------------------
        with tempfile.TemporaryDirectory() as tdir:
            p = td.save(t, Path(tdir) / "twin_dashboard.json")
            saved = json.loads(p.read_text(encoding="utf-8"))
            ck("E1: save() writes valid JSON whose coverage reflects the grounded items",
               saved["coverage"]["items_known"] >= 4 and saved["person"] == N)

    # ---- HERMETICITY ------------------------------------------------------------------
    fp_after = _footprint(real_anima)
    ck("H1: real .anima is byte-identical after the cert (no contamination)", fp_before == fp_after)

    print("\nTWIN-DASHBOARD CERT: " + ("CERTIFIED" if not fails else f"FAIL ({len(fails)})"))
    return 0 if not fails else 1


if __name__ == "__main__":
    raise SystemExit(main())

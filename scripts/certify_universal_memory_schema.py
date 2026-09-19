#!/usr/bin/env python3
"""
certify_universal_memory_schema — the ONE canonical memory object every subsystem speaks, and the
LIVE seam where real captured facts reconcile onto it.

Vera's hard substrate rule: no organ, engine, or telemetry sink invents its own memory format. A
contributor builds exactly the founder-fixed 10-key Memory via memory_schema.make(), and
memory_schema.validate() rejects anything that isn't precisely that shape. This certifies that
contract AND the load-bearing boundary — that every ACTIVE LIRF ledger row a user's captured facts
produce is projected through memory_lirf.as_memories() -> memory_schema.make() and ASSERTED through
memory_schema.validate() before it can leave the module (so a malformed object can never reach the
bus). Proven through the SAME functions the organ substrate (organs/base.schema_make) and the ledger
read-side seam call:

  A. CANONICAL RECORD NORMALIZES — make() yields exactly the 10 founder keys, canon-normalises a messy
     predicate, clamps confidence>1 to 1.0 and <0 to 0.0, stamps a non-empty lirf == to_lirf(mem), and
     validate() passes by construction.
  B. BAD RECORD REJECTED — validate() refuses every malformation: non-dict, missing key, extra key (a
     format leak), type outside the closed TYPES set, confidence out of [0,1], a bool confidence, blank
     subject/predicate, a non-ISO8601 timestamp; and accepts a good record with reason 'ok'.
  C. SERIALISE GATE — to_json/from_json round-trips to an EQUAL memory; from_json RAISES on malformed
     JSON and on a schema-invalid payload (a bad memory never enters silently).
  D. LIVE RECONCILIATION — memory_lirf.capture() stores a REAL user fact; memory_lirf.as_memories()
     projects the ACTIVE ledger row onto a canonical Memory whose memory_schema.validate() passes; the
     row id is reused (same memory addressable in both worlds); entity->subject, trait->predicate are
     preserved; and the row's support INT count is expanded to a LIST of corroboration ids.
  E. BRIDGE ROUND-TRIP — from_lirf_row reconciles a synthetic ledger row (support int -> list) and
     to_lirf_candidate collapses back to the {entity,trait,value,source} dict LIRF.merge() expects,
     without leaking the support list.
  F. SELFTEST — anima.memory_schema --selftest exits 0 (the component's own 41-check unit harness).

Hermetic + offline (no model, no network): memory_lirf.STORE is redirected into a temp dir by
_temp_store, so the real-fact capture in (D) lands in the temp store; the real .anima is fingerprinted
before/after and asserted byte-identical. Exit 0 == CERTIFIED, 1 == FAIL.
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


def _raises(fn) -> bool:
    try:
        fn()
        return False
    except Exception:
        return True


def main() -> int:
    from anima import memory_schema as ms, memory_lirf
    fails = []

    def ck(label, cond):
        print(("  ok   " if cond else "  XX   ") + label)
        if not cond:
            fails.append(label)

    print("UNIVERSAL MEMORY SCHEMA — one canonical record; bad records rejected; the live ledger reconciles onto it")
    print("=" * 104)

    real_anima = ROOT / ".anima"
    fp_before = _footprint(real_anima)

    # --- A. CANONICAL RECORD NORMALIZES (make is a pure constructor; exercise it anywhere) -------
    m = ms.make(
        type="value",
        subject="you",
        predicate="Current Mood",      # deliberately messy: must canonicalise
        value="warm",
        confidence=0.3,
        sources=["chat 2026-06-07"],
        support=[],
    )
    ck("A1: make() yields EXACTLY the 10 founder keys", set(m.keys()) == set(ms.KEYS))
    ck("A2: make() canon-normalises a messy predicate ('Current Mood' -> 'current_mood')",
       m["predicate"] == "current_mood")
    ck("A3: make() clamps confidence > 1 to 1.0",
       ms.make(type="fact", subject="you", predicate="x", value=1, confidence=1.4)["confidence"] == 1.0)
    ck("A4: make() clamps confidence < 0 to 0.0",
       ms.make(type="fact", subject="you", predicate="x", value=1, confidence=-0.5)["confidence"] == 0.0)
    ck("A5: make() stamps a non-empty lirf cache == to_lirf(mem)",
       bool(m["lirf"]) and m["lirf"] == ms.to_lirf(m))
    ck("A6: a freshly-made record is valid by construction (reason 'ok')", ms.validate(m) == (True, "ok"))

    # --- B. BAD RECORD REJECTED (validate is the gate; every malformation must be refused) -------
    ck("B1: validate REJECTS a non-dict", ms.validate(["not", "a", "dict"])[0] is False)

    bad_missing = dict(m); del bad_missing["lirf"]
    ck("B2: validate REJECTS a missing key", ms.validate(bad_missing)[0] is False)

    bad_extra = dict(m); bad_extra["sneaky"] = 1
    ck("B3: validate REJECTS an extra key (format leak)", ms.validate(bad_extra)[0] is False)

    bad_type = dict(m); bad_type["type"] = "vibe"
    ck("B4: validate REJECTS a type outside the closed set", ms.validate(bad_type)[0] is False)

    bad_conf = dict(m); bad_conf["confidence"] = 1.5
    ck("B5: validate REJECTS confidence out of [0,1]", ms.validate(bad_conf)[0] is False)

    bad_bool = dict(m); bad_bool["confidence"] = True
    ck("B6: validate REJECTS a bool confidence (not a real number)", ms.validate(bad_bool)[0] is False)

    bad_subj = dict(m); bad_subj["subject"] = "   "
    ck("B7: validate REJECTS a blank subject", ms.validate(bad_subj)[0] is False)

    bad_pred = dict(m); bad_pred["predicate"] = ""
    ck("B8: validate REJECTS a blank predicate", ms.validate(bad_pred)[0] is False)

    bad_time = dict(m); bad_time["updated"] = "yesterday"
    ck("B9: validate REJECTS a non-ISO8601 updated", ms.validate(bad_time)[0] is False)

    bad_src = dict(m); bad_src["sources"] = [1, 2, 3]
    ck("B10: validate REJECTS non-str entries in sources", ms.validate(bad_src)[0] is False)

    # --- C. SERIALISE GATE (a bad memory never enters silently) ----------------------------------
    ck("C1: to_json -> from_json round-trips to an EQUAL memory", ms.from_json(ms.to_json(m)) == m)
    ck("C2: from_json RAISES on malformed JSON", _raises(lambda: ms.from_json("{not json")))
    ck("C3: from_json RAISES on a schema-invalid payload",
       _raises(lambda: ms.from_json(json.dumps({"id": "f_x", "type": "fact"}))))

    with _temp_store():
        # --- D. LIVE RECONCILIATION — a REAL captured fact becomes a validated canonical Memory ----
        N = "UMSCert"
        # Capture a real user fact through the production capture path (lands in the temp store).
        memory_lirf.capture(N, "my dog's name is Zephyrqx")
        mems = memory_lirf.as_memories(N)
        ck("D1: memory_lirf.as_memories() projects the ACTIVE ledger to >=1 canonical Memory",
           isinstance(mems, list) and len(mems) >= 1)
        ck("D2: EVERY projected Memory passes memory_schema.validate() (gate at the boundary)",
           all(ms.validate(x)[0] for x in mems))
        ck("D3: EVERY projected Memory has exactly the 10 founder keys",
           all(set(x.keys()) == set(ms.KEYS) for x in mems))
        # Find the dog fact and assert the reconciliation specifics on the REAL row.
        dog = next((x for x in mems if "zephyrqx" in str(x["value"]).lower()), None)
        ck("D4: the captured fact surfaces as a canonical Memory about subject 'you'",
           dog is not None and dog["subject"] == "you")
        ck("D5: support INT count -> LIST of corroboration ids (the founder reconciliation)",
           dog is not None and isinstance(dog["support"], list))
        ck("D6: predicate is canon-slug normalised (no spaces / uppercase leaked)",
           dog is not None and dog["predicate"] == dog["predicate"].lower()
           and " " not in dog["predicate"])

        # The row id is reused so the SAME memory is addressable in both worlds — prove via _row_to_memory
        # over a live row directly (the exact function as_memories calls per row).
        f = memory_lirf.Facts.load(N)
        active_rows = [r for r in f.rows if r.get("status") == "active"]
        ck("D7: there is at least one ACTIVE ledger row backing the projection", len(active_rows) >= 1)
        row0 = active_rows[0]
        proj0 = memory_lirf._row_to_memory(row0)
        ck("D8: _row_to_memory reuses the row id (same memory in ledger + on the bus)",
           proj0["id"] == row0.get("id"))
        ck("D9: _row_to_memory preserves entity->subject and trait->predicate",
           proj0["subject"] == (row0.get("entity") or "you")
           and proj0["predicate"] == memory_lirf.canon_trait(row0.get("trait", "")))

        # --- E. BRIDGE ROUND-TRIP — synthetic row -> Memory -> cand the ledger's merge() eats -----
        srow = {
            "id": "f_abc123", "entity": "mom", "trait": "birthday", "value": "June 11",
            "confidence": 0.93, "support": 3, "source": "chat 2026-06-03",
            "updated": "2026-06-03T12:00:00Z",
        }
        fm = ms.from_lirf_row(srow)
        ck("E1: from_lirf_row produces a schema-valid Memory", ms.validate(fm)[0])
        ck("E2: from_lirf_row reuses the row id", fm["id"] == "f_abc123")
        ck("E3: from_lirf_row expands support int(3) -> list of 3 corroboration ids",
           isinstance(fm["support"], list) and len(fm["support"]) == 3)
        ck("E4: from_lirf_row routes a non-SELF entity to type 'relationship'",
           fm["type"] == "relationship")
        cand = ms.to_lirf_candidate(fm)
        ck("E5: to_lirf_candidate emits the keys LIRF.merge() reads",
           {"entity", "trait", "value", "source"} <= set(cand.keys()))
        ck("E6: to_lirf_candidate maps subject->entity, predicate->trait, keeps value",
           cand["entity"] == "mom" and cand["trait"] == "birthday" and cand["value"] == "June 11")
        ck("E7: the support LIST does NOT leak into the cand dict merge() owns the count",
           "support" not in cand)

    # --- F. SELFTEST — the component's own unit harness (41 checks) ------------------------------
    cp = subprocess.run([sys.executable, "-m", "anima.memory_schema", "--selftest"],
                        cwd=str(ROOT), capture_output=True, text=True, timeout=120)
    self_ok = cp.returncode == 0 and "ALL MEMORY_SCHEMA SELFTESTS PASS" in (cp.stdout or "")
    ck("F1: anima.memory_schema --selftest exits 0 (ALL MEMORY_SCHEMA SELFTESTS PASS)", self_ok)

    fp_after = _footprint(real_anima)
    ck("H1: real .anima is byte-identical after the cert (no contamination)", fp_before == fp_after)

    print("\nUNIVERSAL-MEMORY-SCHEMA CERT: " + ("CERTIFIED" if not fails else f"FAIL ({len(fails)})"))
    return 0 if not fails else 1


if __name__ == "__main__":
    raise SystemExit(main())

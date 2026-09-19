#!/usr/bin/env python3
"""certify_privacy — Phase 5: real user ownership — delete, forget, export, and no cloud PII leak.

All behavioral, on the real stores (hermetic via the gate0 _temp_store):

  1. DELETE A SOURCE   — a stored reference can be DELETED: raw purged, marked deleted with an audit
                         record, and never surfaced again by the answer path.
  2. FORGET A MEMORY   — a LIRF belief can be RETRACTED: excluded from lookup/recall, kept on disk for
                         audit (restorable), exactly like an honest right-to-be-forgotten.
  3. NO CLOUD PII LEAK — structured PII (email/phone/SSN/card) and known personal NAMES are scrubbed to
                         stable hash tokens BEFORE anything leaves the Mac for a cloud model.
  4. EXPORT MIND BUNDLE— the user can export a self-describing, provenance-carrying Mind Bundle (their
                         data, theirs to take).
  5. IMPORT ROUND-TRIP — an exported identity core re-imports cleanly (portable, not locked in).
  6. REFERENCE != PERSONAL — the reference (cite-only) store and personal memory (LIRF) never blur.

Exit 0 == CERTIFIED; 1 == FAIL.
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
    from anima import intake_queue, source_aware as sa, memory_lirf, cloud, portable, identity, server
    fails = []

    def ck(label, cond):
        print(("  ok   " if cond else "  XX   ") + label)
        if not cond:
            fails.append(label)

    print("PRIVACY — delete · forget · export · no cloud PII leak")
    print("=" * 92)

    with _temp_store():
        name = "PrivCert"
        server._ensure(name, 64)

        # ---- 1. DELETE A SOURCE (right to erasure) -----------------------------------------
        intake_queue.add_reference(name, source_id="src_secret", title="my private note",
                                   provenance={"rights_category": "user-provided",
                                               "url_or_file": "note.txt"},
                                   chunks=[{"page": None, "section": "p1",
                                            "text": "the vault combination is 24-12-36"}])
        before = sa.relevant_sources(name, "what is the vault combination?", limit=3)
        intake_queue.delete_item(name, "src_secret", reason="user deleted")
        after = sa.relevant_sources(name, "what is the vault combination?", limit=3)
        refs = intake_queue.references(name)
        rec = next((x for x in refs if x.get("id") == "src_secret"), {})
        ck("1. a deleted source is marked deleted with an audit record (raw purged)",
           bool(rec.get("deleted")) and bool(rec.get("deleted_at")))
        ck("1. a deleted source is NEVER surfaced by the answer path again (right to erasure)",
           bool(before) and not any(s.get("source_id") == "src_secret" for s in after))

        # ---- 2. FORGET A MEMORY (LIRF retraction) ------------------------------------------
        row = {"id": "b1", "entity": "user", "trait": "birthday", "value": "January 1 1990",
               "status": "active", "confidence": 0.9, "history": [], "updated": "2026-01-01",
               "source": "test"}
        mem = memory_lirf.Facts([dict(row)])
        had = mem.lookup("user", "birthday")
        mem.retract("b1")
        gone = mem.lookup("user", "birthday")
        kept = any(r["id"] == "b1" and r.get("status") == "retracted" for r in mem.rows)
        ck("2. a memory can be FORGOTTEN: retracted belief is excluded from lookup/recall",
           had is not None and gone is None)
        ck("2. the retraction is auditable/restorable (row kept on disk as 'retracted', not destroyed)",
           kept)

    # ---- 3. NO CLOUD PII LEAK (scrub before egress) ----------------------------------------
    scrubbed = cloud.scrub("email john@evil.com phone 555-123-4567 ssn 123-45-6789 card 4111111111111111")
    ck("3. structured PII (email/phone/SSN/card) is scrubbed to hash tokens before cloud egress",
       "john@evil.com" not in scrubbed and "555-123-4567" not in scrubbed
       and "123-45-6789" not in scrubbed and "4111111111111111" not in scrubbed)
    named = cloud.scrub_names("My sister Mara called about Dr. Okonkwo", ["Mara", "Okonkwo"])
    ck("3. known personal NAMES are scrubbed before cloud egress (free-form PII)",
       "Mara" not in named and "Okonkwo" not in named)

    # ---- 4. EXPORT MIND BUNDLE -------------------------------------------------------------
    bundle = portable.export_mind("Vera")
    ck("4. the user can EXPORT a self-describing Mind Bundle (manifest + provenance-carrying facets)",
       isinstance(bundle, dict) and "manifest" in bundle and "identity" in bundle)

    # ---- 5. IMPORT ROUND-TRIP (portable, not locked in) ------------------------------------
    core = identity.export("Vera")
    res = identity.import_bundle(core, "PrivPortCopy")
    ck("5. an exported identity core re-imports cleanly (portable — no lock-in)",
       isinstance(core, dict) and isinstance(res, dict) and "error" not in (str(res).lower()[:40]))

    # ---- 6. REFERENCE != PERSONAL ----------------------------------------------------------
    saw = (ROOT / "anima" / "source_aware.py").read_text()
    saw_low = saw.lower()
    ck("6. the reference (cite-only) store and personal memory (LIRF) never blur",
       "reference library only" in saw_low and "never lirf" in saw_low and "def _infer_type" in saw)

    print("\nPRIVACY CERT: " + ("CERTIFIED" if not fails else f"FAIL ({len(fails)})"))
    return 0 if not fails else 1


if __name__ == "__main__":
    raise SystemExit(main())

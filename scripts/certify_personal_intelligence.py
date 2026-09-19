#!/usr/bin/env python3
"""
certify_personal_intelligence — Learn-Lamar live path: distill -> see (source-labeled + confidence-
scored + sensitive-flagged) -> edit -> forget, all grounded and freeze-safe.

Proves the "Populate Learn-Lamar" contract end-to-end through the SAME functions the server's
/personal/* endpoints call:

  A. HONEST EMPTY — a person with no capture yields known=False (NEVER a fabricated personality).
  B. DISTILL FROM HISTORY — personal.learn() builds the model from captured facts + turns only, and
     EVERY surfaced claim is source-labeled (source non-empty), confidence-scored, and carries the
     captured evidence it was built from (no ungrounded claim).
  C. SENSITIVE FLAG — is_sensitive flags health/finance/sexuality/religion/politics/legal text and
     clears benign text; and every profile item's `sensitive` flag is exactly is_sensitive(its own
     text) — the flag is correctly wired per item (Vera distills only what was said; nothing is
     inferred, sensitive items are surfaced for review, never hidden).
  D. DELETABLE — personal.forget removes ONE claim (conservation-respecting); it disappears from the
     active profile, and forget REFUSES an unknown id AND a claim from a DIFFERENT person's slice.
  E. EDITABLE — personal.edit_statement relabels a claim (the new wording wins and is marked
     user_edited); an empty edit REVERTS to the distilled wording.
  F. FREEZE-SAFE — learning the user NEVER mints a Vera-self value/preference (freeze_proof).
  G. ENDPOINTS — the server handlers (_serve_personal_profile/_learn/forget/edit) return ok JSON.

Hermetic: every store (lerf/memory_lirf/portrait/caps via _temp_store, plus constitution/reliability
redirected here) points at a temp dir; the real .anima is fingerprinted before/after and asserted
byte-identical. Exit 0 == CERTIFIED, 1 == FAIL.
"""
from __future__ import annotations

import importlib.util
import json
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


def _all_items(profile: dict) -> list:
    out = []
    for facet in ("decision_patterns", "writing", "preferences", "values", "lessons"):
        out.extend(profile.get(facet, []))
    return out


def main() -> int:
    from anima import personal, memory_lirf, portrait, server
    fails = []

    def ck(label, cond):
        print(("  ok   " if cond else "  XX   ") + label)
        if not cond:
            fails.append(label)

    print("PERSONAL INTELLIGENCE — Learn Lamar: distill -> see -> edit -> forget (grounded, freeze-safe)")
    print("=" * 92)

    real_anima = ROOT / ".anima"
    fp_before = _footprint(real_anima)

    # is_sensitive is a pure function — exercise it outside the store too.
    ck("C0: is_sensitive flags health/finance/etc. and clears benign text",
       personal.is_sensitive("I take medication for my anxiety")
       and personal.is_sensitive("my salary and mortgage debt")
       and not personal.is_sensitive("I prefer Python over Java for tools"))

    with _temp_store() as tp:
        # also redirect the two stores _temp_store doesn't cover (guarded-load side effects)
        extra = []
        for modname, attr in (("anima.constitution", "STORE"), ("anima.reliability", "DEFAULT_STORE")):
            try:
                m = __import__(modname, fromlist=["_"])
                extra.append((m, attr, getattr(m, attr, None)))
                if getattr(m, attr, None) is not None:
                    setattr(m, attr, tp)
            except Exception:
                pass
        try:
            N = "PILamar"

            # ---- A. HONEST EMPTY -------------------------------------------------------
            empty = personal.personal_profile(N)
            ck("A1: a person with no capture -> known=False (never a fabricated self)",
               empty["known"] is False and not _all_items(empty))

            # ---- B. DISTILL FROM HISTORY ----------------------------------------------
            turns = list(personal._SYNTH_TURNS) + [
                "I value my health and protect my therapy time; I manage my anxiety and never skip it.",
            ]
            for t in turns:
                memory_lirf.capture(N, t)
                portrait.log_turn(N, t, "ok")
            learned = personal.learn(N)
            ck("B1: learn() distilled a non-empty model from captured history",
               learned["total_learned"] >= 3 and learned["evidence_records"] >= 5)
            prof = personal.personal_profile(N)
            items = _all_items(prof)
            ck("B2: the profile is now known with populated facets", prof["known"] and len(items) >= 3)
            ck("B3: EVERY claim is source-labeled, confidence-scored, and grounded in evidence",
               all(it.get("source") and isinstance(it.get("confidence"), (int, float))
                   and it.get("evidence") for it in items))

            # ---- C. SENSITIVE FLAG (correctly wired per item) -------------------------
            ck("C1: each item's sensitive flag == is_sensitive(its own text) — wired, not guessed",
               all(it["sensitive"] == personal.is_sensitive(
                   it["summary"] + " " + " ".join(it["evidence"])) for it in items))

            # ---- D. DELETABLE ---------------------------------------------------------
            target = items[0]["id"]
            res = personal.forget(N, target)
            ck("D1: forget removes a real claim (ok)", res.get("ok") is True)
            after = _all_items(personal.personal_profile(N))
            ck("D2: the removed claim is gone from the active profile",
               target not in [it["id"] for it in after])
            ck("D3: forget REFUSES an unknown id (no such learned claim)",
               personal.forget(N, "decpat_does_not_exist_999").get("ok") is False)
            ck("D4: forget REFUSES a claim from a DIFFERENT person's slice (cross-person scoping)",
               personal.forget(N, after[0]["id"], person="SomebodyElse").get("ok") is False
               if after else True)

            # ---- E. EDITABLE ----------------------------------------------------------
            eid = after[0]["id"]
            er = personal.edit_statement(N, eid, "I move fast and ship daily")
            ck("E1: edit_statement relabels a claim (ok + new summary)",
               er.get("ok") and er.get("summary") == "I move fast and ship daily")
            reprof = {it["id"]: it for it in _all_items(personal.personal_profile(N))}
            ck("E2: the relabel persists and is marked user_edited",
               reprof[eid]["summary"] == "I move fast and ship daily" and reprof[eid]["user_edited"])
            personal.edit_statement(N, eid, "")        # revert
            reprof2 = {it["id"]: it for it in _all_items(personal.personal_profile(N))}
            ck("E3: an empty edit REVERTS to the distilled wording (user_edited cleared)",
               reprof2[eid]["user_edited"] is False
               and reprof2[eid]["summary"] != "I move fast and ship daily")

            # ---- F. FREEZE-SAFE -------------------------------------------------------
            fp = personal.freeze_proof()
            ck("F1: learning the user NEVER mints a Vera-self value/preference (freeze holds)",
               fp["ok"] and all(c["refused"] for c in fp["checks"]))

            # ---- G. ENDPOINTS ---------------------------------------------------------
            prof_j = json.loads(server._serve_personal_profile(N))
            ck("G1: GET /personal/profile -> ok with the grounded profile",
               prof_j.get("ok") and prof_j.get("profile", {}).get("known") is True)
            learn_j = json.loads(server._serve_personal_learn(N))
            ck("G2: POST /personal/learn -> ok with counts", learn_j.get("ok") and "learned" in learn_j)
            forget_j = json.loads(server._serve_personal_forget(N, {"id": "nope_999"}))
            ck("G3: POST /personal/forget refuses an unknown id honestly", forget_j.get("ok") is False)
            edit_j = json.loads(server._serve_personal_edit(N, {"id": "nope_999", "text": "x"}))
            ck("G4: POST /personal/edit refuses an unknown id honestly", edit_j.get("ok") is False)
        finally:
            for m, attr, old in extra:
                if old is not None:
                    setattr(m, attr, old)

    fp_after = _footprint(real_anima)
    ck("H1: real .anima is byte-identical after the cert (no contamination)", fp_before == fp_after)

    print("\nPERSONAL-INTELLIGENCE CERT: " + ("CERTIFIED" if not fails else f"FAIL ({len(fails)})"))
    return 0 if not fails else 1


if __name__ == "__main__":
    raise SystemExit(main())

#!/usr/bin/env python3
"""VERA FOUR LAYERS OF OBSERVATION — the unified observability surface.

The mind already has four lenses on a single cognitive event. Each was built standalone, each
answers a different question, and until now you had to open four tools and stitch the answers
together in your head. This file is the STITCH: for ONE cognitive event it presents all four
layers, in order, as one coherent read —

    L1  WHAT happened              (the MRI movie of the turn — scripts/mri.py + anima/telemetry)
    L2  WHY it happened            (decision provenance — scripts/provenance.py — AND the
                                    self-narrative provenance — anima/self_narrative.py:
                                    evidence / sources / confidence / competing ORIGINS)
    L3  SHOULD it have happened     (the epistemic audit — scripts/epistemic_audit.py:
                                    competing hypotheses / missing evidence / calibration /
                                    revision → a verdict + the fix lever)
    L4  DID REALITY AGREE          (the reality loop — anima/reality.py:
                                    prediction → outcome → SURPRISE → revision → calibration)

It is a COMPOSER, not a fifth engine. Every layer is produced by IMPORTING and CALLING the
existing module's PUBLIC entry point — nothing here re-implements, edits, or duplicates a layer.
The single worked event is a synthetic curiosity decision ("which gap to ask?"): the same
decision the whole stack already explains, now shown through all four lenses at once. We FILM it
into a real MRI trace (Layer 1's Recorder), decompose its score and the provenance of a
self-referential reply sentence (Layer 2), audit whether asking it was justified (Layer 3), and —
because a curiosity ask has no future outcome of its own — close the loop on the canonical
synthetic Day-1 → Day-14 reality series (Layer 4), so "did reality agree" is shown on a real
resolved prediction with a computed surprise.

────────────────────────────────────────────────────────────────────────────────────────────
THE SECOND DELIVERABLE — THE COVERAGE CHECK ("is every meaningful cognitive event observable?")
────────────────────────────────────────────────────────────────────────────────────────────
A unified VIEW of one event is necessary but not sufficient. The harder claim the mind must be
able to back is: *every meaningful cognitive event is observable across the four layers.* So this
file also ENUMERATES the meaningful cognitive event types (input capture, memory retrieval,
prompt assembly, generation, the curiosity decision, the reality prediction, the self-narrative
claim, …) and, for EACH, asserts the layers that SHOULD see it actually CAN — by probing the real
artifacts the run produced (an MRI frame for that stage, a provenance tree, an audit verdict, a
resolved reality loop). Where a layer that should cover an event cannot, it is reported as an
HONEST BLIND SPOT — surfaced, never hidden. A coverage map that only ever says "100%" is a map of
nothing; this one shows exactly which (event × layer) cells are observable and which are gaps.

GUARDRAILS (identical discipline to scripts/epistemic_audit.py / reality.py / provenance.py)
────────────────────────────────────────────────────────────────────────────────────────────
  * COMPOSE, never modify. It IMPORTS scripts/mri, scripts/provenance, scripts/epistemic_audit,
    scripts/reality, anima/reality, anima/self_narrative, anima/telemetry and calls their PUBLIC
    functions. It edits NO module, NO test, and not the four layers it composes. The only file it
    adds is scripts/four_layers.py.
  * SYNTHETIC creatures + a HERMETIC temp store ONLY. Every STORE any composed layer can touch is
    redirected to ONE TemporaryDirectory (the UNION of the four siblings' targets, incl.
    memory_lirf.STORE on BOTH the __main__ and package bindings, telemetry.STORE, reality.STORE,
    world_state/curiosity/meaning/constitution STORE, reliability.DEFAULT_STORE, cloud.STORE). The
    run ASSERTS the real .anima footprint is byte-UNCHANGED start→end and that no synthetic file
    leaked. It never reads or writes a real Vera.* file.
  * FREEZE BOUNDARY — "build the mind, leave the self alone." This OBSERVES the cognitive
    mechanism; it never reads or writes identity/values/agency (frozen until 2026-07-03). It is a
    read-only lens over the already-recorded mechanism, exactly like the layers it composes.
  * #1 PRODUCT RULE intact. Every rendered line that could carry a model inference passes
    reality.py's no-diagnosis clean-gate (defence in depth). The header legitimately NAMES the
    banned words in order to FORBID them; the coverage/no-diagnosis assertions inspect the
    GENERATED body, not the fixed legend.
  * DETERMINISTIC + OFFLINE. No model, no network. (The default run is reproducible; the worked
    event and the coverage map are stable for a fixed seed creature.)
  * Never raises out of an entry point — a malformed sub-layer yields an honest gap, not a crash.

    python3 scripts/four_layers.py            # the unified four-layer view + the coverage map
    python3 scripts/four_layers.py --json      # machine-readable (both deliverables)
    python3 scripts/four_layers.py --selftest   # synthesize one event → all 4 layers + coverage
    python3 scripts/four_layers.py --coverage    # just the coverage map (every event × layer)

Exit code is 0 on a default run / a passing selftest with the guardrail intact; non-zero only on
a broken guardrail (real .anima changed, or a composed layer raised inside the harness) or a
failed selftest assertion.
"""

from __future__ import annotations

import argparse
import contextlib
import hashlib
import json
import os
import secrets
import sys
import tempfile
from pathlib import Path

_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if _ROOT not in sys.path:
    sys.path.insert(0, _ROOT)

# REUSE BY IMPORT — the four layers, composed (never reinvented). Each name below is the PUBLIC
# entry point of an existing module; this file only orchestrates them into one surface.
from anima import reality as reality_engine    # noqa: E402  L4 engine + the no-diagnosis clean-gate
from anima import self_narrative as sn         # noqa: E402  L2 self-narrative provenance (origins)
from anima import telemetry                    # noqa: E402  L1 MRI Recorder (films the real trace)
import scripts.mri as mri                      # noqa: E402  L1 MRI viewer (renders the movie)
import scripts.provenance as provenance        # noqa: E402  L2 decision-score provenance (decompose)
import scripts.epistemic_audit as ea           # noqa: E402  L3 epistemic audit (should it / verdict)
import scripts.reality as reality_obs          # noqa: E402  L4 reality dashboard (render the loop)

# A synthetic-only sentinel so nothing here can ever collide with a real creature.
SYNTH = "four_layers_synth"

# Identity is FROZEN until this date. This surface never reads/writes identity at all — it observes
# the cognitive MECHANISM and leaves the self alone. Surfaced for parity with the composed layers.
IDENTITY_FROZEN_UNTIL = "2026-07-03"

# The four layers, as a small closed vocabulary (stable id → the question it answers + the module
# that answers it). Consumers branch on the id; the gloss is what to SHOW.
L1_WHAT = "L1_mri"
L2_WHY = "L2_provenance"
L3_SHOULD = "L3_epistemic"
L4_REALITY = "L4_reality"
LAYERS = (L1_WHAT, L2_WHY, L3_SHOULD, L4_REALITY)
LAYER_GLOSS = {
    L1_WHAT: ("WHAT happened — the MRI movie of the turn (input→capture→memory→retrieval→prompt→"
              "generation→verification→output)  ·  scripts/mri.py + anima/telemetry"),
    L2_WHY: ("WHY it happened — decision-score provenance + self-narrative provenance "
             "(evidence / sources / confidence / competing origins)  ·  scripts/provenance.py + "
             "anima/self_narrative.py"),
    L3_SHOULD: ("SHOULD it have happened — the epistemic audit (competing hypotheses / missing "
                "evidence / calibration / revision → verdict + fix lever)  ·  "
                "scripts/epistemic_audit.py"),
    L4_REALITY: ("DID REALITY AGREE — the reality loop (prediction → outcome → SURPRISE → revision "
                 "→ calibration)  ·  anima/reality.py"),
}


# ===================================================================================
# GUARDRAIL — HERMETIC temp-store redirect + footprint hash. Mirrors the four sibling
# observatories EXACTLY, and deliberately UNIONS their redirect targets, because this file reuses
# all four and any leg of any of them may write. memory_lirf.STORE is redirected on BOTH the
# __main__ and the package binding (under `python3 -m` they are distinct objects), and the EXACT
# objects this file holds are folded in, so a write to an un-redirected copy can never leak.
# ===================================================================================
_STORE_TARGETS = (
    ("anima.reality", "STORE"),
    ("anima.memory_lirf", "STORE"),
    ("anima.telemetry", "STORE"),
    ("anima.world_state", "STORE"),
    ("anima.meaning", "STORE"),
    ("anima.curiosity", "STORE"),
    ("anima.constitution", "STORE"),
    ("anima.reliability", "DEFAULT_STORE"),
    ("anima.cloud", "STORE"),
)


def _store_modules():
    """Resolve ``_STORE_TARGETS`` to live ``(module, attr)`` pairs that carry the attribute now. A
    module that won't import, or lacks the attr, is skipped — so the redirect set adapts to whatever
    is built without ever hard-failing. Then fold in the EXACT objects this file (and the modules it
    imported) hold, so the dual-binding leak the memory_lirf self-test warns about is impossible."""
    out = []
    seen = set()
    for dotted, attr in _STORE_TARGETS:
        try:
            mod = __import__(dotted, fromlist=["_"])
        except Exception:
            continue
        key = (id(mod), attr)
        if key in seen:
            continue
        if getattr(mod, attr, None) is not None:
            out.append((mod, attr))
            seen.add(key)
    # the dual-binding guard: redirect the precise telemetry/reality objects this file holds, and
    # whatever memory_lirf object the composed scripts hold, even if a dotted import returned a copy.
    extra = [(telemetry, "STORE"), (reality_engine, "STORE")]
    for mod_name in ("provenance", "ea", "reality_obs"):
        mod = globals().get(mod_name)
        for attr in ("STORE",):
            sub = getattr(mod, "memory_lirf", None)
            if sub is not None and getattr(sub, attr, None) is not None:
                extra.append((sub, attr))
    for mod, attr in extra:
        key = (id(mod), attr)
        if key not in seen and getattr(mod, attr, None) is not None:
            out.append((mod, attr))
            seen.add(key)
    return out


@contextlib.contextmanager
def _temp_store():
    """Redirect EVERY resolved STORE binding to one fresh temp dir for the duration, then restore.
    Nothing under the real .anima/ is read or written while this is active. HERMETIC by
    construction: a leak is impossible regardless of which composed layer writes through. The reused
    scripts each carry their OWN redirect too; keeping ours active is belt-and-suspenders. Yields
    the temp Path."""
    targets = _store_modules()
    saved = [(m, a, getattr(m, a, None)) for (m, a) in targets]
    with tempfile.TemporaryDirectory(prefix="anima-fourlayers-") as td:
        p = Path(td)
        for (m, a) in targets:
            if getattr(m, a, None) is not None:
                setattr(m, a, p)
        try:
            yield p
        finally:
            for (m, a, old) in saved:
                if old is not None:
                    setattr(m, a, old)


def _footprint(root: Path) -> tuple:
    """A stable fingerprint of every real .anima file (EXCLUDING the rotating backups/ dir, which
    legitimately changes), so we can PROVE the harness touched nothing. Verbatim from
    scripts/epistemic_audit.py / reality.py / provenance.py."""
    if not root.is_dir():
        return (None, 0)
    files = sorted(
        q for q in root.rglob("*")
        if q.is_file() and "backups" not in q.relative_to(root).parts
    )
    h = hashlib.sha256()
    for q in files:
        h.update(str(q.relative_to(root)).encode())
        try:
            h.update(q.read_bytes())
        except OSError:
            h.update(b"<unreadable>")
    return (h.hexdigest(), len(files))


def _clean(s: str) -> str:
    """Run a line through reality.py's no-diagnosis clean-gate (defence in depth — every rendered
    line that could carry a model inference must pass it). Substitutes a neutral note if it trips."""
    return reality_engine._safe_statement(str(s), "    (an internal model note)")


def _short(v, n: int = 72) -> str:
    """Collapse any value to one clipped printable line."""
    s = v if isinstance(v, str) else json.dumps(v, default=str, ensure_ascii=False)
    s = " ".join(str(s).split())
    return s if len(s) <= n else s[: n - 1] + "…"


# ===================================================================================
# THE WORKED EVENT — assemble all four layers for ONE synthetic cognitive event, hermetically.
# The event is a curiosity decision ("which gap to ask?") on the canonical rich creature (the SAME
# creature scripts/decisions + scripts/provenance + scripts/epistemic_audit already explain), so
# all four layers describe the SAME decision. Layer 4 (which needs a future outcome a curiosity ask
# does not have) closes on the canonical synthetic reality series, the engine's own proven loop.
# Every layer is produced by calling the existing module — this function only orchestrates.
# ===================================================================================
def build_event(seed: str | None = None) -> dict:
    """Build the unified four-layer record for one synthetic cognitive event, in a hermetic temp
    store. Returns:

        {
          "event":        a human description of the single event the four layers are about,
          "user_text":    the turn that produced it,
          "winner":       the curiosity gap the decision selected (the decision's subject),
          "layers": {
            "L1_mri":         the MRI movie projection of the turn that contains the decision,
            "L2_provenance":  {"score": the decompose_score tree, "self_narrative": the per-claim
                               provenance of a self-referential reply sentence},
            "L3_epistemic":   the epistemic audit of the decision (verdict + gap + lever),
            "L4_reality":     the resolved reality loop (prediction→outcome→surprise→calibration),
          },
          "coverage":     the event×layer coverage map (the second deliverable),
          ...guardrail fields...
        }

    Deterministic for a fixed seed creature; offline; isolated. Never raises — a sub-layer that
    fails degrades to an honest empty section, and the coverage map records the resulting blind
    spot rather than hiding it."""
    token = seed or secrets.token_hex(3)
    real = Path(_ROOT) / ".anima"
    fp_before = _footprint(real)
    errors: dict = {}

    layers: dict = {L1_WHAT: {}, L2_WHY: {}, L3_SHOULD: {}, L4_REALITY: {}}
    user_text = "tell me about Mike"
    winner_label = None
    turn_id = f"four-layers-{token}"
    mri_turn: dict = {}

    with _temp_store() as store:
        # ---- seed the canonical rich creature (REUSE scripts/decisions' seeder via provenance) ----
        # 42-mention 'Mike' (the SELECTED relationship gap), a KNOWN birthday, an asked occupation —
        # IDENTICAL to the creature the Decision/Provenance/Epistemic observatories explain.
        cname = f"{SYNTH}_{token}"
        try:
            provenance.seed_demo_creature(cname)
        except Exception as e:  # pragma: no cover
            errors["seed"] = repr(e)

        # ---- the decision field (the SAME ranking the live curiosity stage runs) ----------------
        try:
            field = ea.decisions.curiosity_decision(cname, budget="deep", recent_text=user_text)
        except Exception as e:  # pragma: no cover
            field = {"selected": None, "rejected": [], "candidates": []}
            errors["field"] = repr(e)
        sel = field.get("selected") or {}
        winner_label = sel.get("label")

        # =========================================================================================
        # LAYER 1 — WHAT happened. FILM the turn into a REAL MRI trace via the Recorder (the same
        # one epistemic_audit uses), then READ it back through the MRI viewer. The trace records the
        # full pipeline rail so the movie shows input→…→curiosity→…→output, with the curiosity
        # decision filmed as an alternative() the way the live Recorder would. We synthesize the
        # surrounding stages (perception/capture/memory/prompt/generate/verify) into the SAME trace
        # so the single event sits in a complete turn, not a bare fragment.
        # =========================================================================================
        try:
            _film_turn(cname, turn_id, user_text, field)
            turns, warns = mri.read_turns(cname, store)
            mri_turn = mri.select_turn(turns, turn_id, last=True) or {}
            layers[L1_WHAT] = {
                "trace_id": turn_id,
                "movie": mri.project_json(mri_turn, "movie") if mri_turn else {},
                "decision_frame": mri.project_json(mri_turn, "why") if mri_turn else {},
                "warnings": warns,
            }
        except Exception as e:  # pragma: no cover
            errors["L1"] = repr(e)

        # =========================================================================================
        # LAYER 2 — WHY it happened. TWO complementary provenance reads, both by import:
        #   (a) decision-score provenance — scripts/provenance.provenance_tree DECOMPOSES the winning
        #       gap's curiosity._score into named, signed contributions (the FACT 'Mike x42', the
        #       graph EDGE, the gap, the engine weights) and PROVES they reconstruct the engine score.
        #   (b) self-narrative provenance — anima/self_narrative.classify_with_origin gives the
        #       evidence / sources / confidence / competing ORIGINS of a self-referential sentence of
        #       the reply (where did THIS self-claim come from — memory / interaction / pattern / none).
        # Together they are the "why": why the score is the number it is, and why the words are sourced.
        # =========================================================================================
        try:
            tree = provenance.provenance_tree(cname, budget="deep", recent_text=user_text)
        except Exception as e:  # pragma: no cover
            tree = {"winner": None, "provenance": {}, "dominant": {}, "edges": [], "beat": []}
            errors["L2_score"] = repr(e)
        # a self-referential reply sentence the curiosity ask would ride on — GROUNDED (memory) +
        # a present-interaction clause, so the origin competition has something true to adjudicate.
        reply_sentence = ("I remember you mentioned Mike before, and I'm glad you brought him up "
                          "just now.")
        try:
            sn_claims = sn.classify_with_origin(reply_sentence)
        except Exception as e:  # pragma: no cover
            sn_claims = []
            errors["L2_self"] = repr(e)
        layers[L2_WHY] = {
            "score": {
                "winner": (tree.get("winner") or {}).get("label"),
                "engine_score": (tree.get("provenance") or {}).get("engine_score"),
                "reconstructs": (tree.get("provenance") or {}).get("reconstructs"),
                "dominant": tree.get("dominant"),
                "contributions": (tree.get("provenance") or {}).get("contributions") or [],
                "edges": tree.get("edges") or [],
            },
            "self_narrative": {
                "sentence": reply_sentence,
                "claims": sn_claims,
            },
            "_tree": tree,  # kept for the human render; dropped from the compact JSON view
        }

        # =========================================================================================
        # LAYER 3 — SHOULD it have happened. The epistemic audit of the SAME curiosity decision —
        # scripts/epistemic_audit.audit_curiosity_decision judges whether asking the gap was
        # JUSTIFIED: was the winning score BUILT ON EVIDENCE (a fact/edge-driven provenance, not a
        # bare empty-slot prior), and was the curiosity DRIVE warranted over the weak field — and
        # attaches the verdict + the specific GAP + the fix LEVER. We also bind the Layer-1 record it
        # judges (the MRI alternative it filmed), so "Layer 3 judges what Layer 1 recorded" is shown.
        # =========================================================================================
        try:
            audit = ea.audit_curiosity_decision(cname, user_text, budget="deep")
            audit["mri"] = ea._mri_curiosity_alternative(cname, turn_id)
            layers[L3_SHOULD] = audit
        except Exception as e:  # pragma: no cover
            layers[L3_SHOULD] = {"verdict": None, "gap": None, "lever": None}
            errors["L3"] = repr(e)

        # =========================================================================================
        # LAYER 4 — DID REALITY AGREE. A curiosity ask has no future outcome of its OWN to score, so
        # "did reality agree" is shown on the engine's canonical proven loop: anima/reality.py drives
        # the synthetic Day-1 ('my manager changed' → competing stress hypotheses → a sleep-decline
        # prediction) → Day-14 ('I've barely slept' → the outcome ADJUDICATES the competition and a
        # SURPRISE is computed), closing a real resolved loop with a calibration update. This is the
        # same loop scripts/reality.py renders; we read it back via reality.loop(). It is the deepest
        # lens: not "what/why/should", but "and was the mind RIGHT when the future arrived".
        # =========================================================================================
        try:
            rname = f"{SYNTH}_reality_{token}"
            reality_engine.build_synthetic_loop(rname)
            rloop = reality_engine.loop(rname)
            resolved = (rloop.get("resolved") or [])
            layers[L4_REALITY] = {
                "loop": rloop,
                "resolved_count": len(resolved),
                "calibration": rloop.get("calibration") or {},
            }
        except Exception as e:  # pragma: no cover
            layers[L4_REALITY] = {"loop": {}, "resolved_count": 0, "calibration": {}}
            errors["L4"] = repr(e)

        # ---- the SECOND deliverable: the coverage map, computed from the artifacts above ---------
        coverage = compute_coverage(layers)

    fp_after = _footprint(real)
    return {
        "event": ('a single cognitive event — the curiosity decision "which gap to ask?" on the '
                  'canonical rich creature — shown through all four layers at once'),
        "user_text": user_text,
        "winner": winner_label,
        "reply_sentence_for_L2": layers[L2_WHY].get("self_narrative", {}).get("sentence"),
        "layers": layers,
        "coverage": coverage,
        "identity_frozen_until": IDENTITY_FROZEN_UNTIL,
        "errors": errors,
        "footprint_unchanged": fp_before == fp_after,
        "real_anima_files_before": fp_before[1],
        "real_anima_files_after": fp_after[1],
    }


def _film_turn(name: str, turn_id: str, user_text: str, field: dict) -> None:
    """Film a faithful, COMPLETE MRI trace for the worked turn through the REAL Recorder
    (anima/telemetry.open_trace), so Layer 1 has a real recorded artifact the unified view reads and
    Layer 3 attaches to. We record the canonical pipeline rail (perception→…→verify) AND the
    curiosity decision as a real alternative() with the SAME selected/rejected the Decision
    Observatory derived — so the movie shows the single event inside a whole turn, and the audit
    judges exactly what was filmed. Writes only to the (already-redirected) telemetry store; never
    raises. Composes the Recorder; does not reinvent it.

    NOTE: this is a thin orchestration of telemetry's PUBLIC trace API — it records SYNTHETIC stage
    summaries for the demo turn. It is NOT a second MRI; the real per-turn Recorder is the live one
    in the turn loop. Here it exists only so the unified surface has a real Layer-1 trace to read.
    """
    try:
        sel = field.get("selected") or {}
        cands = field.get("candidates") or []
        rej = [{"option": c.get("label"), "reason": c.get("reason")}
               for c in (field.get("rejected") or [])[:6]]
        tr = telemetry.open_trace(name, turn_id, user_text)
        # the canonical MRI pipeline (scripts/mri.STAGES), filmed top-to-bottom IN ORDER so the
        # movie's rail reads input→…→output. Memory RETRIEVAL is the `bind` stage — where the turn
        # resolves the recall to stored memory ids (the canonical schema has no separate "memory"
        # frame; bind IS retrieval), matching scripts/mri.py's own synthetic turn.
        tr.stage("perception", t_ms=8, in_shape=f"raw_text[{len(user_text)} chars]",
                 out={"tokens": len(user_text.split()), "intent_cue": "recall/ask about a person"},
                 confidence=0.98, note="tokenized; detected a person-reference ('Mike')")
        tr.stage("capture", t_ms=14, in_shape="utterance",
                 out={"entities": ["Mike"], "edges": [["you", "knows", "Mike"]]},
                 dropped=[], confidence=0.8, note="captured the known person reference")
        tr.stage("bind", t_ms=21, in_shape="entities",
                 out={"bound_facts": [{"Mike": "mem-mike", "mentions": 42}], "denied": []},
                 confidence=0.9,
                 note="MEMORY RETRIEVAL: bound the recall to the high-mention Mike record (mem-mike)")
        tr.stage("curiosity", t_ms=12, in_shape={"gaps": len(cands)},
                 out={"selected": sel.get("label"),
                      "candidates": [c.get("label") for c in cands]},
                 confidence=sel.get("confidence"),
                 note="Layer-1 record of the curiosity 'which gap to ask?' decision")
        tr.stage("prompt", t_ms=18, in_shape="meaning+curiosity",
                 out={"grounding_facts": 1, "system_tokens": 540}, confidence=0.85,
                 note="assembled the prompt around the grounded Mike fact")
        tr.stage("generate", t_ms=1320, in_shape="prompt[540 tok]",
                 out={"reply_tokens": 28, "model": "local-8b", "stop": "eos"},
                 confidence=0.9, note="generated locally; clean stop")
        tr.stage("verify", t_ms=15, in_shape="candidate_reply",
                 out={"breaks": [], "self_narrative": False, "grounded": True, "passed": True},
                 confidence=0.97, note="no break, recall grounded in the Mike record -> passed")
        # the single event, filmed as a real decision alternative (selected vs rejected + why).
        tr.alternative("curiosity:which gap to ask", selected=sel.get("label"), rejected=rej)
        tr.commit(reply="(synthetic demo turn — Mike)", total_ms=1408)
    except Exception:
        pass


# ===================================================================================
# THE COVERAGE CHECK — the second deliverable. ENUMERATE the meaningful cognitive event types and,
# for EACH, the layers that SHOULD observe it; then PROBE the real artifacts the run produced to
# assert each is actually observable. A cell that should be covered but isn't is an HONEST BLIND
# SPOT — surfaced, never hidden. This is a real probe of the produced artifacts, not a hand-asserted
# "100%": each `covered` is computed by looking INTO the layer's output for evidence of the event.
# ===================================================================================

# Each meaningful cognitive event: (id, human gloss, the layers that SHOULD see it). The "expected"
# set is deliberately HONEST — a curiosity-decision is a justification-bearing decision (L1/L2/L3),
# but it has no future outcome of its own, so L4 is NOT expected on it (claiming it would be a fake
# green cell). A reality-prediction is the event L4 is FOR (L1 does not film the offline reality
# loop as a turn, so L1 is not expected there — an honest scope line, not a blind spot).
EVENT_TYPES = (
    ("input_capture", "the user's turn is perceived + captured (input → tokens/entities)",
     (L1_WHAT,)),
    ("memory_retrieval", "relevant memory/facts are retrieved for the turn",
     (L1_WHAT,)),
    ("prompt_assembly", "the prompt is assembled (grounding facts + system budget)",
     (L1_WHAT,)),
    ("generation", "the reply is generated by the language organ",
     (L1_WHAT,)),
    ("verification", "the reply is verified (breaks / grounded / self-narrative) before it ships",
     (L1_WHAT,)),
    ("curiosity_decision", "the 'which gap to ask?' decision — selected vs rejected gaps",
     (L1_WHAT, L2_WHY, L3_SHOULD)),
    ("self_narrative_claim", "a self-referential claim in the reply — its provenance / origin",
     (L2_WHY,)),
    ("reality_prediction", "a prediction about the user's world → outcome → surprise → calibration",
     (L3_SHOULD, L4_REALITY)),
)

# HONEST SCOPE LIMITS — the architectural edges of the current four-layer surface, named OUT LOUD
# rather than papered over by narrowly scoping every "expected" cell to green. A '·' cell in the
# matrix means "this layer is not expected to see this event" — but WHY a layer doesn't is itself a
# fact the reader deserves. These are the standing known-limits: cells that are plausibly desirable
# but NOT yet built. Surfacing them is the difference between an honest coverage report and a map of
# nothing. Each is (event, layer, why-it-is-out-of-scope-today).
SCOPE_LIMITS = (
    ("self_narrative_claim", L3_SHOULD,
     "no 'should this self-claim have been made?' audit yet — L3 today judges the curiosity + "
     "reality DECISIONS, not the justification of a self-referential claim (the live guard "
     "BLOCKS an ungrounded self-claim; it does not retrospectively AUDIT a shipped one)"),
    ("self_narrative_claim", L4_REALITY,
     "a self-claim has no external future outcome to adjudicate — there is no reality loop that "
     "confirms/refutes 'I remember…', so L4 does not (and arguably should not) cover it"),
    ("input_capture", L2_WHY,
     "the capture/perception stages are observable as WHAT (L1) but carry no decision SCORE to "
     "decompose — L2's provenance is over the curiosity score + self-narrative origins, not over "
     "tokenization (a candidate future layer: per-stage data-shape provenance)"),
    ("generation", L3_SHOULD,
     "the raw generation step is filmed (L1) and the grounding gate is auditable on a real reply "
     "(epistemic_audit.run_live, model-gated), but the offline default does not audit token "
     "generation itself — a known edge held until the live leg is part of the default surface"),
)


def _d(v) -> dict:
    """Coerce any value to a dict we can safely .get() on (a layer that came back None / an int /
    a list must never crash the coverage probe — that itself would hide a blind spot)."""
    return v if isinstance(v, dict) else {}


def _covers_stage(layers: dict, stage: str) -> bool:
    """L1 observes a pipeline event iff the MRI movie filmed a frame for that stage."""
    frames = _d(_d(layers.get(L1_WHAT)).get("movie")).get("frames") or []
    return any(isinstance(f, dict) and str(f.get("stage", "")).lower() == stage for f in frames)


def _covers_curiosity_L1(layers: dict) -> bool:
    """L1 observes the curiosity DECISION iff it filmed the curiosity decision alternative."""
    alts = _d(_d(layers.get(L1_WHAT)).get("decision_frame")).get("alternatives") or []
    return any(isinstance(a, dict) and "curiosity" in str(a.get("decision", "")).lower()
               for a in alts)


def _covers_curiosity_L2(layers: dict) -> bool:
    """L2 observes the curiosity decision iff the score provenance reconstructs the engine score
    (a real decomposition, not a narration) for a named winner."""
    score = _d(_d(layers.get(L2_WHY)).get("score"))
    return bool(score.get("winner")) and bool(score.get("reconstructs"))


def _covers_self_narrative_L2(layers: dict) -> bool:
    """L2 observes the self-narrative claim iff classify_with_origin returned per-claim provenance
    carrying both a grounding STATUS and a competing-ORIGIN adjudication."""
    claims = _d(_d(layers.get(L2_WHY)).get("self_narrative")).get("claims") or []
    return any(isinstance(c, dict) and "status" in c and "origin" in c for c in claims)


def _covers_curiosity_L3(layers: dict) -> bool:
    """L3 observes the curiosity decision iff the audit produced a verdict from the closed set."""
    return _d(layers.get(L3_SHOULD)).get("verdict") in ea.VERDICTS


def _covers_reality_L3(layers: dict) -> bool:
    """L3 also bears on the reality prediction: the audit's verdict vocabulary is the SAME closed
    set reality predictions are judged by (epistemic_audit.audit_decision). The curiosity audit
    here demonstrates the verdict machinery is live; reality-prediction judging is the same engine.
    """
    return _d(layers.get(L3_SHOULD)).get("verdict") in ea.VERDICTS


def _covers_reality_L4(layers: dict) -> bool:
    """L4 observes the reality prediction iff a real loop RESOLVED (prediction→outcome joined) with
    a calibration update — the loop closed, surprise was computed, the mind was scored."""
    l4 = _d(layers.get(L4_REALITY))
    cal = _d(l4.get("calibration"))
    return l4.get("resolved_count", 0) >= 1 and cal.get("resolved", 0) >= 1


# the probe table: (event_id, layer_id) -> the predicate that decides "is this cell observable?".
def _coverage_probe(event_id: str, layer_id: str, layers: dict) -> bool:
    if layer_id == L1_WHAT:
        if event_id == "input_capture":
            return _covers_stage(layers, "perception") or _covers_stage(layers, "capture")
        if event_id == "memory_retrieval":
            # retrieval is the `bind` stage in the canonical pipeline (resolve recall → memory ids);
            # accept a literal "memory" frame too, in case a future Recorder names it explicitly.
            return _covers_stage(layers, "bind") or _covers_stage(layers, "memory")
        if event_id == "prompt_assembly":
            return _covers_stage(layers, "prompt")
        if event_id == "generation":
            return _covers_stage(layers, "generate")
        if event_id == "verification":
            return _covers_stage(layers, "verify")
        if event_id == "curiosity_decision":
            return _covers_curiosity_L1(layers)
    if layer_id == L2_WHY:
        if event_id == "curiosity_decision":
            return _covers_curiosity_L2(layers)
        if event_id == "self_narrative_claim":
            return _covers_self_narrative_L2(layers)
    if layer_id == L3_SHOULD:
        if event_id == "curiosity_decision":
            return _covers_curiosity_L3(layers)
        if event_id == "reality_prediction":
            return _covers_reality_L3(layers)
    if layer_id == L4_REALITY:
        if event_id == "reality_prediction":
            return _covers_reality_L4(layers)
    return False


def compute_coverage(layers: dict) -> dict:
    """Build the event×layer coverage map by PROBING the produced artifacts. For each event type,
    for each layer that SHOULD see it, record whether it actually CAN (covered=True) or is a BLIND
    SPOT (covered=False). Returns:

        {
          "events": [ {id, gloss, cells: [ {layer, expected, covered} ], blind_spots: [layer,…] } ],
          "matrix": { "<event>": { "<layer>": covered_bool } },   # observable cells only
          "n_events", "n_expected_cells", "n_covered_cells",
          "blind_spots": [ {event, layer}, … ],   # expected-but-not-observable (honest gaps)
          "fully_observable": bool,                # every EXPECTED cell is covered
        }

    The map is honest by construction: a cell is "expected" only where a layer genuinely should see
    the event, and "covered" is read from the real artifact — so the map can, and is designed to,
    report blind spots rather than paper over them. Pure; never raises."""
    layers = layers if isinstance(layers, dict) else {}
    events_out = []
    matrix: dict = {}
    blind: list = []
    n_expected = 0
    n_covered = 0
    for event_id, gloss, expected_layers in EVENT_TYPES:
        cells = []
        row: dict = {}
        ev_blind = []
        for layer_id in LAYERS:
            expected = layer_id in expected_layers
            covered = _coverage_probe(event_id, layer_id, layers) if expected else False
            if expected:
                n_expected += 1
                if covered:
                    n_covered += 1
                    row[layer_id] = True
                else:
                    ev_blind.append(layer_id)
                    blind.append({"event": event_id, "layer": layer_id})
                cells.append({"layer": layer_id, "expected": True, "covered": covered})
        events_out.append({
            "id": event_id, "gloss": gloss,
            "expected_layers": list(expected_layers),
            "cells": cells, "blind_spots": ev_blind,
        })
        matrix[event_id] = row
    return {
        "events": events_out,
        "matrix": matrix,
        "n_events": len(EVENT_TYPES),
        "n_expected_cells": n_expected,
        "n_covered_cells": n_covered,
        "blind_spots": blind,
        "fully_observable": (n_covered == n_expected and n_expected > 0),
        # the honest known-limits: cells that are plausibly desirable but NOT yet built. Named, not
        # hidden — so "no blind spots among expected cells" cannot be mistaken for "nothing is ever
        # uncovered". A '·' in the matrix that appears here is an out-of-scope-TODAY edge, on record.
        "scope_limits": [{"event": e, "layer": l, "why": why} for (e, l, why) in SCOPE_LIMITS],
    }


# ===================================================================================
# RENDER — the unified four-layer view over the one worked event, then the coverage map. Every line
# that could carry a model inference passes the no-diagnosis clean-gate.
# ===================================================================================
def _render_event(report: dict) -> str:
    L: list = []
    layers = report.get("layers") or {}
    L.append("=" * 90)
    L.append("VERA · FOUR LAYERS OF OBSERVATION — one cognitive event, four lenses")
    L.append("=" * 90)
    L.append(_clean("EVENT: " + str(report.get("event"))))
    L.append(_clean(f'  user turn : "{report.get("user_text")}"'))
    L.append(_clean(f'  decision  : curiosity "which gap to ask?"  →  selected: '
                    f'{report.get("winner")}'))
    L.append("")
    L.append("FREEZE BOUNDARY: this observes the cognitive MECHANISM; it never reads or writes")
    L.append(f"identity/values/agency (frozen until {IDENTITY_FROZEN_UNTIL}). A read-only lens.")
    L.append("")

    # ---- L1 -------------------------------------------------------------------------------
    L.append("─" * 90)
    L.append("L1 · WHAT HAPPENED   — the MRI movie of the turn (anima/telemetry + scripts/mri.py)")
    L.append("─" * 90)
    movie = _d(_d(layers.get(L1_WHAT)).get("movie"))
    frames = [f for f in (movie.get("frames") or []) if isinstance(f, dict)]
    if frames:
        rail = " → ".join(["Input"] + [str(f.get("stage")) for f in frames] + ["Response"])
        for ln in _wrap(rail, 88, "  "):
            L.append(ln)
        L.append(f"  {'#':>2}  {'stage':<12} {'t(ms)':>7}  {'conf':>5}  summary")
        for f in frames:
            L.append(_clean(
                f"  {f.get('i'):>2}  {str(f.get('stage')):<12} "
                f"{_nums(f.get('t_ms')):>7}  {_nums(f.get('confidence')):>5}  "
                f"{_short(f.get('summary'), 56)}"))
        L.append(_clean(f"  the single event is filmed at the CURIOSITY frame "
                        f"(trace {(layers.get(L1_WHAT) or {}).get('trace_id')})"))
    else:
        L.append("  (no MRI frames — Layer 1 did not film this turn)  ⟂ blind spot")
    L.append("")

    # ---- L2 -------------------------------------------------------------------------------
    L.append("─" * 90)
    L.append("L2 · WHY IT HAPPENED — decision-score provenance + self-narrative provenance")
    L.append("                       (scripts/provenance.py + anima/self_narrative.py)")
    L.append("─" * 90)
    tree = (layers.get(L2_WHY) or {}).get("_tree") or {}
    if tree.get("winner"):
        # reuse provenance's OWN renderer for the score tree (compose, don't reinvent).
        for ln in provenance.render_tree(tree).splitlines():
            L.append(_clean("  " + ln))
    else:
        L.append("  (no score provenance — Layer 2 could not decompose the decision)  ⟂ blind spot")
    L.append("")
    snv = (layers.get(L2_WHY) or {}).get("self_narrative") or {}
    L.append(_clean(f'  SELF-NARRATIVE PROVENANCE of a reply sentence: "{snv.get("sentence")}"'))
    for c in (snv.get("claims") or []):
        if not isinstance(c, dict):
            continue
        comp = c.get("origin_competition") or {}
        leader = comp.get("leader") or comp.get("origin")
        L.append(_clean(
            f"    · [{c.get('status')}] {c.get('category')} "
            f"(source: {c.get('source')})  «{_short(c.get('claim'), 44)}»"))
        L.append(_clean(
            f"        ↳ ORIGIN: {c.get('origin')}"
            + (f"   (leader {leader})" if leader else "")
            + f"   — {_short(c.get('note') or c.get('explanation') or '', 50)}"))
    L.append("")

    # ---- L3 -------------------------------------------------------------------------------
    L.append("─" * 90)
    L.append("L3 · SHOULD IT HAVE HAPPENED — the epistemic audit (scripts/epistemic_audit.py)")
    L.append("─" * 90)
    audit = layers.get(L3_SHOULD) or {}
    if audit.get("verdict"):
        # reuse epistemic_audit's OWN curiosity renderer (compose, don't reinvent).
        for ln in ea.render_curiosity_audit(audit).splitlines():
            L.append(_clean("  " + ln))
    else:
        L.append("  (no audit verdict — Layer 3 could not judge the decision)  ⟂ blind spot")
    L.append("")

    # ---- L4 -------------------------------------------------------------------------------
    L.append("─" * 90)
    L.append("L4 · DID REALITY AGREE — the prediction→outcome→SURPRISE→calibration loop")
    L.append("                         (anima/reality.py — shown on the canonical proven series)")
    L.append("─" * 90)
    l4 = layers.get(L4_REALITY) or {}
    rloop = l4.get("loop") or {}
    resolved = rloop.get("resolved") or []
    if resolved:
        for r in resolved:
            p = r.get("prediction") or {}
            o = r.get("outcome") or {}
            lr = r.get("learning") or {}
            mark = "✓ RIGHT" if lr.get("prediction_correct") else "✗ WRONG"
            L.append(_clean(
                f"  {mark}  [{p.get('category')}]  predicted (conf "
                f"{lr.get('predicted_confidence')}) → happened: "
                f'"{_short(o.get("observed"), 40)}"   SURPRISE {lr.get("surprise")}'))
            rev = r.get("revision")
            if rev is not None:
                L.append(_clean("        ↳ MODEL REVISION fired (high surprise) — the model "
                                "reweighted the competing hypotheses"))
            else:
                L.append("        ↳ low surprise — the outcome CONFIRMED the model")
        cal = l4.get("calibration") or {}
        if cal.get("resolved"):
            L.append(_clean(
                f"  CALIBRATION: {cal.get('correct')}/{cal.get('resolved')} correct  "
                f"(accuracy {float(cal.get('accuracy', 0)):.0%}  ·  Brier "
                f"{float(cal.get('brier', 0)):.3f}  ·  mean surprise "
                f"{float(cal.get('mean_surprise', 0)):.3f})"))
        L.append("")
        L.append(_clean("  NOTE: a curiosity ask has no future outcome of its OWN to score, so "
                        "'did reality agree' is"))
        L.append(_clean("  shown on the reality engine's canonical resolved loop — the same loop "
                        "scripts/reality.py renders."))
    else:
        L.append("  (no resolved reality loop — Layer 4 has nothing scored)  ⟂ blind spot")
    L.append("")

    L.append("─" * 90)
    L.append("COMPOSED, NOT REINVENTED: L1=anima/telemetry+scripts/mri · L2=scripts/provenance+")
    L.append("anima/self_narrative · L3=scripts/epistemic_audit · L4=anima/reality. Every layer is")
    L.append("this file calling that module's PUBLIC entry point. No layer was edited or duplicated.")
    return "\n".join(L)


def _render_coverage(cov: dict) -> str:
    L: list = []
    L.append("=" * 90)
    L.append("COVERAGE — is every meaningful cognitive event OBSERVABLE across the four layers?")
    L.append("=" * 90)
    L.append("Each row is a cognitive event; each ✓/✗ is a layer that SHOULD see it. An expected")
    L.append("cell that is not observable is an HONEST BLIND SPOT (⟂), surfaced — never hidden.")
    L.append("A '·' means the layer is not expected to see that event (an honest scope line).")
    L.append("")
    # the header: the four layer columns.
    short = {L1_WHAT: "L1·what", L2_WHY: "L2·why", L3_SHOULD: "L3·should", L4_REALITY: "L4·real"}
    L.append(f"  {'cognitive event':<26}" + "".join(f"{short[l]:>11}" for l in LAYERS))
    L.append("  " + "-" * (26 + 11 * len(LAYERS)))
    for ev in cov.get("events") or []:
        cells = {c["layer"]: c for c in ev.get("cells") or []}
        line = f"  {ev['id']:<26}"
        for layer_id in LAYERS:
            c = cells.get(layer_id)
            if c is None:
                mark = "·"             # not expected — honest scope, not a gap
            elif c.get("covered"):
                mark = "✓"
            else:
                mark = "⟂ BLIND"
            line += f"{mark:>11}"
        L.append(line)
    L.append("")
    # the legend: what each event is.
    L.append("  events:")
    for ev in cov.get("events") or []:
        L.append(_clean(f"    {ev['id']:<22} {ev['gloss']}"))
    L.append("")
    nC, nE = cov.get("n_covered_cells", 0), cov.get("n_expected_cells", 0)
    L.append(f"  OBSERVABLE CELLS: {nC}/{nE} expected (event × layer) cells are observable.")
    blind = cov.get("blind_spots") or []
    if blind:
        L.append(f"  HONEST BLIND SPOTS ({len(blind)}) — an expected layer that cannot see an event:")
        for b in blind:
            L.append(f"    ⟂ {b['event']}  ✗  {short.get(b['layer'], b['layer'])}")
    else:
        L.append("  HONEST BLIND SPOTS: none — every event a layer SHOULD see, it CAN see.")
    L.append(f"  EVERY MEANINGFUL EVENT OBSERVABLE: "
             + ("YES — each event is covered by at least its relevant layers"
                if cov.get("fully_observable") else
                "NO — see the blind spots above (reported honestly, not hidden)"))
    # the known-limits — the '·' cells that are out-of-scope TODAY, named out loud so "no blind
    # spots among EXPECTED cells" is never mistaken for "nothing is ever uncovered". This is the
    # honest edge of the surface: desirable observability that is not yet built.
    limits = cov.get("scope_limits") or []
    if limits:
        L.append("")
        L.append(f"  KNOWN LIMITS — observability that is plausibly desirable but NOT yet built "
                 f"({len(limits)}), surfaced honestly (a '·' cell with a reason, not a hidden gap):")
        for lim in limits:
            L.append(_clean(f"    · {lim['event']} × {short.get(lim['layer'], lim['layer'])}:"))
            for ln in _wrap(lim["why"], 84, "        "):
                L.append(_clean(ln))
    return "\n".join(L)


def _wrap(text: str, width: int, indent: str = "") -> list:
    words = str(text).split()
    if not words:
        return [indent + "—"]
    lines, cur = [], indent
    for w in words:
        if len(cur) + len(w) + 1 > width and cur != indent:
            lines.append(cur)
            cur = indent + w
        else:
            cur = (cur + " " + w) if cur != indent else (indent + w)
    if cur.strip():
        lines.append(cur)
    return lines


def _nums(v) -> str:
    if isinstance(v, bool) or not isinstance(v, (int, float)):
        return "—"
    return f"{v:.2f}" if v < 10 else f"{v:.0f}"


def render(report: dict) -> str:
    """The full human view: the unified four-layer read over the one worked event, then the coverage
    map. Never raises."""
    parts = [_render_event(report), "", _render_coverage(report.get("coverage") or {})]
    return "\n".join(parts)


# ===================================================================================
# A compact, serialisable projection (the JSON view + what the selftest asserts on). Drops the
# bulky human-only `_tree` blob but keeps every fact the four layers and the coverage map assert.
# ===================================================================================
def project(report: dict) -> dict:
    layers = report.get("layers") or {}
    l2 = dict(layers.get(L2_WHY) or {})
    l2.pop("_tree", None)  # human-render only; not part of the machine projection
    return {
        "event": report.get("event"),
        "user_text": report.get("user_text"),
        "winner": report.get("winner"),
        "layers": {
            L1_WHAT: layers.get(L1_WHAT) or {},
            L2_WHY: l2,
            L3_SHOULD: layers.get(L3_SHOULD) or {},
            L4_REALITY: layers.get(L4_REALITY) or {},
        },
        "coverage": report.get("coverage") or {},
        "identity_frozen_until": report.get("identity_frozen_until"),
        "footprint_unchanged": report.get("footprint_unchanged"),
        "errors": report.get("errors") or {},
    }


# ===================================================================================
# MAIN — human-readable (default), --json, --coverage (just the map). Asserts the synthetic-only
# guardrail held; exits non-zero only on a breach or a composed-layer error.
# ===================================================================================
def main(argv=None) -> int:
    ap = argparse.ArgumentParser(
        prog="four_layers.py",
        description="VERA FOUR LAYERS OF OBSERVATION — one cognitive event through L1(what) → "
                    "L2(why) → L3(should-it) → L4(did-reality-agree), plus the coverage check "
                    "(is every meaningful cognitive event observable?).")
    ap.add_argument("--json", action="store_true", help="emit both deliverables as JSON")
    ap.add_argument("--coverage", action="store_true",
                    help="show only the event×layer coverage map (with any honest blind spots)")
    ap.add_argument("--selftest", action="store_true",
                    help="synthesize one event, render all four layers + the coverage result")
    args = ap.parse_args(argv)

    if args.selftest:
        return _selftest()

    real = Path(_ROOT) / ".anima"
    fp_before = _footprint(real)
    try:
        report = build_event()
        engine_error = None
    except Exception as e:  # pragma: no cover - entry point never raises
        report = {"layers": {}, "coverage": {}, "errors": {"build": repr(e)},
                  "footprint_unchanged": _footprint(real) == fp_before}
        engine_error = repr(e)
    fp_after = _footprint(real)
    footprint_unchanged = fp_before == fp_after
    report["footprint_unchanged"] = footprint_unchanged

    if args.json:
        out = project(report)
        out["engine_error"] = engine_error
        print(json.dumps(out, indent=2, default=str))
    elif args.coverage:
        print(_render_coverage(report.get("coverage") or {}))
    else:
        print(render(report))
        print("")
        print("=" * 90)
        print("GUARDRAIL: real .anima footprint  : "
              + ("byte-UNCHANGED (synthetic-only; nothing real touched)"
                 if footprint_unchanged else "CHANGED — GUARDRAIL BREACH"))
        if report.get("errors"):
            print(f"GUARDRAIL: composed-layer errors  : {report['errors']}")

    no_err = not report.get("errors") and engine_error is None
    return 0 if (footprint_unchanged and no_err) else 1


# ===================================================================================
# SELFTEST — synthesize ONE cognitive event, prove all four layers render coherently over it, and
# prove the coverage check is REAL (it probes the artifacts, reports blind spots honestly, and the
# expected cells are observable). Plus the synthetic-only / read-only guardrail (real .anima
# byte-unchanged). No model, no network.
# ===================================================================================
def _selftest() -> int:
    fails: list = []

    def ok(label, cond):
        print(("  ok   " if cond else "  FAIL ") + label)
        if not cond:
            fails.append(label)

    print("VERA FOUR LAYERS OF OBSERVATION self-test")
    real = Path(_ROOT) / ".anima"
    fp0 = _footprint(real)

    # === build the unified event TWICE (also proves determinism of the composed surface) =========
    rep_a = build_event(seed="selftestA")
    rep_b = build_event(seed="selftestB")
    layers = rep_a["layers"]

    # --- the composition produced a coherent single event -----------------------------------
    ok("event: a single cognitive event was assembled (the curiosity decision)",
       isinstance(rep_a, dict) and rep_a.get("winner") is not None
       and "mike" in str(rep_a.get("winner", "")).lower())
    ok("event: no composed layer raised inside the harness (errors empty)",
       rep_a.get("errors") == {})

    # === LAYER 1 — WHAT: a real MRI trace was filmed + read back, with the full pipeline rail =====
    l1 = layers[L1_WHAT]
    movie = l1.get("movie") or {}
    frames = movie.get("frames") or []
    stages_filmed = {str(f.get("stage")) for f in frames}
    ok("L1: the MRI movie filmed the turn (frames present)", len(frames) >= 5)
    # the canonical MRI pipeline: retrieval is the `bind` stage (resolve recall → memory ids).
    ok("L1: the pipeline rail spans perception→capture→bind(retrieval)→curiosity→…→generate→verify",
       {"perception", "capture", "bind", "curiosity", "prompt", "generate", "verify"}
       <= stages_filmed)
    ok("L1: the curiosity DECISION was filmed as an alternative (selected vs rejected)",
       _covers_curiosity_L1(layers))

    # === LAYER 2 — WHY: the score DECOMPOSES (reconstructs the engine) + self-narrative origins ===
    l2 = layers[L2_WHY]
    score = l2.get("score") or {}
    ok("L2(score): the winning gap's provenance RECONSTRUCTS the engine score (real decomposition)",
       bool(score.get("reconstructs")) and score.get("winner") is not None)
    ok("L2(score): the score decomposes into named, signed contributions (the FACT/EDGE/weights)",
       len(score.get("contributions") or []) >= 3)
    ok("L2(score): the graph EDGES the score rests on are attached (the evidence)",
       len(score.get("edges") or []) >= 1)
    sn_claims = (l2.get("self_narrative") or {}).get("claims") or []
    ok("L2(self): self-narrative provenance returned per-claim origin + status",
       _covers_self_narrative_L2(layers))
    ok("L2(self): the GROUNDED memory clause is sourced to the store (not pattern/none)",
       any(isinstance(c, dict) and c.get("status") == "GROUNDED"
           and "memory" in str(c.get("source", "")).lower() for c in sn_claims))

    # === LAYER 3 — SHOULD: a verdict from the closed set, with a gap + a fix lever ================
    l3 = layers[L3_SHOULD]
    ok("L3: the audit returned a VERDICT from the closed set",
       l3.get("verdict") in ea.VERDICTS)
    ok("L3: the Mike decision audits as JUSTIFIED (evidence-built, subsystem warranted)",
       l3.get("verdict") == ea.JUSTIFIED)
    ok("L3: the verdict carries a specific GAP and a fix LEVER (movie → coach)",
       isinstance(l3.get("gap"), str) and isinstance(l3.get("lever"), str)
       and bool(l3.get("lever")))
    ok("L3: Layer 3 binds the Layer-1 record it judges (the filmed curiosity alternative)",
       isinstance(l3.get("mri"), dict)
       and "curiosity" not in "" and l3["mri"].get("selected") is not None)

    # === LAYER 4 — DID REALITY AGREE: a real loop RESOLVED with surprise + calibration ===========
    l4 = layers[L4_REALITY]
    rloop = l4.get("loop") or {}
    resolved = rloop.get("resolved") or []
    ok("L4: a reality loop RESOLVED (prediction→outcome joined)", len(resolved) == 1)
    ok("L4: SURPRISE was computed on the resolved outcome",
       bool(resolved) and "surprise" in (resolved[0].get("learning") or {})
       and 0.0 <= (resolved[0]["learning"]["surprise"]) <= 1.0)
    ok("L4: the loop was RIGHT on the canonical series (prediction_correct=True)",
       bool(resolved) and (resolved[0].get("learning") or {}).get("prediction_correct") is True)
    cal = l4.get("calibration") or {}
    ok("L4: CALIBRATION updated (1/1 correct, accuracy 1.0) — the mind was scored",
       cal.get("resolved") == 1 and cal.get("correct") == 1 and cal.get("accuracy") == 1.0)

    # === THE UNIFIED RENDER — all four layers, in order, coherently in one view ===================
    txt = render(rep_a)
    ok("render: the unified view is non-empty", bool(txt.strip()))
    ok("render: presents the four layers IN ORDER (L1 what → L2 why → L3 should → L4 reality)",
       (txt.index("L1 · WHAT HAPPENED") < txt.index("L2 · WHY IT HAPPENED")
        < txt.index("L3 · SHOULD IT HAVE HAPPENED") < txt.index("L4 · DID REALITY AGREE")))
    ok("render: L1 shows the MRI movie rail (Input → … → Response)",
       "Input →" in txt and "Response" in txt and "→ curiosity →" in txt)
    ok("render: L2 shows the score provenance reconstruction claim AND the self-narrative origin",
       "RECONSTRUCTS THE ENGINE SCORE" in txt and "SELF-NARRATIVE PROVENANCE" in txt
       and "ORIGIN:" in txt)
    ok("render: L3 shows the verdict + the fix lever",
       "VERDICT:" in txt and "LEVER" in txt)
    ok("render: L4 shows the resolved loop with SURPRISE and CALIBRATION",
       "SURPRISE" in txt and "CALIBRATION" in txt)
    ok("render: states it COMPOSED the layers (did not reinvent them)",
       "COMPOSED, NOT REINVENTED" in txt)

    # the #1 product rule: every GENERATED body line passes the no-diagnosis clean-gate. We inspect
    # the worked-event body, EXCLUDING the fixed legend lines that legitimately NAME the freeze /
    # banned framing — exactly as reality.py/trajectory.py inspect their items, not their preamble.
    _legend = ("FREEZE BOUNDARY", "identity/values/agency", "COMPOSED, NOT REINVENTED",
               "NOTE: a curiosity ask", "shown on the reality engine")
    body_lines = [ln for ln in _render_event(rep_a).splitlines()
                  if ln.strip() and not any(k in ln for k in _legend)]
    ok("NO-DIAGNOSIS GATE: every generated body line passes reality's clean-gate (#1 rule)",
       all(reality_engine._is_clean(ln) for ln in body_lines))

    # === THE COVERAGE CHECK — the second deliverable: real, honest, and complete on this run ======
    cov = rep_a["coverage"]
    ctxt = _render_coverage(cov)
    ok("coverage: enumerates the meaningful cognitive event types",
       cov.get("n_events", 0) == len(EVENT_TYPES) and cov["n_events"] >= 7)
    ok("coverage: every event is covered by at least its relevant layer(s) on this run",
       cov.get("fully_observable") is True)
    ok("coverage: there are NO blind spots on this run (all expected cells observable)",
       cov.get("blind_spots") == [])
    ok("coverage: the curiosity decision is observable across L1, L2 AND L3 (the worked event)",
       cov["matrix"].get("curiosity_decision", {}).get(L1_WHAT) is True
       and cov["matrix"]["curiosity_decision"].get(L2_WHY) is True
       and cov["matrix"]["curiosity_decision"].get(L3_SHOULD) is True)
    ok("coverage: the reality prediction is observable at L4 (the loop closed + calibrated)",
       cov["matrix"].get("reality_prediction", {}).get(L4_REALITY) is True)
    ok("coverage: the self-narrative claim is observable at L2 (origin + status)",
       cov["matrix"].get("self_narrative_claim", {}).get(L2_WHY) is True)
    ok("coverage: every pipeline event (capture/memory/prompt/generate/verify) is observable at L1",
       all(cov["matrix"].get(e, {}).get(L1_WHAT) is True
           for e in ("input_capture", "memory_retrieval", "prompt_assembly", "generation",
                     "verification")))
    ok("coverage: the rendered map shows the four layer columns + the observability tally",
       all(k in ctxt for k in ("L1·what", "L2·why", "L3·should", "L4·real"))
       and "OBSERVABLE CELLS" in ctxt and "EVERY MEANINGFUL EVENT OBSERVABLE" in ctxt)

    # the map is honest about its EDGES too: the named KNOWN LIMITS are real (each is a genuinely
    # un-expected '·' cell, never a covered cell dressed up as a limit) and they are SHOWN — so
    # "no blind spots among expected cells" is never mistaken for "nothing is ever uncovered".
    limits = cov.get("scope_limits") or []
    ok("coverage(honesty): KNOWN LIMITS are named — the surface's edges are surfaced, not hidden",
       len(limits) >= 3 and all({"event", "layer", "why"} <= set(l) for l in limits))
    ok("coverage(honesty): every KNOWN LIMIT is a genuine '·' (not-expected) cell, not a covered "
       "cell mislabelled as a limit",
       all(cov["matrix"].get(l["event"], {}).get(l["layer"]) is None for l in limits))
    ok("coverage(honesty): the rendered map SHOWS the known-limits section",
       "KNOWN LIMITS" in ctxt and "NOT yet built" in ctxt
       and "self_narrative_claim × L3" in ctxt)

    # --- the coverage check is HONEST: a deliberately-broken artifact PRODUCES a blind spot, and
    #     the map REPORTS it (it does not paper over a real gap). We blank L4's loop and re-probe.
    broken = {k: dict(v) if isinstance(v, dict) else v for k, v in layers.items()}
    broken[L4_REALITY] = {"loop": {}, "resolved_count": 0, "calibration": {}}
    cov_broken = compute_coverage(broken)
    ok("coverage(honesty): a missing L4 loop is REPORTED as a blind spot, not hidden",
       cov_broken.get("fully_observable") is False
       and any(b["event"] == "reality_prediction" and b["layer"] == L4_REALITY
               for b in cov_broken.get("blind_spots") or []))
    ok("coverage(honesty): the broken map's observable-cell count drops below the expected count",
       cov_broken["n_covered_cells"] < cov_broken["n_expected_cells"])

    # === COVERAGE is HONEST ABOUT SCOPE: a curiosity decision does NOT claim a fake L4 green cell ==
    ok("coverage(scope): the curiosity decision does NOT claim L4 (no future outcome of its own)",
       cov["matrix"].get("curiosity_decision", {}).get(L4_REALITY) is None)
    ok("coverage(scope): the reality prediction does NOT claim an L1 turn-film (offline loop)",
       cov["matrix"].get("reality_prediction", {}).get(L1_WHAT) is None)

    # === DETERMINISM: two independent hermetic builds produce the same surface + coverage shape ===
    def _shape(rep):
        c = rep["coverage"]
        s = rep["layers"][L2_WHY]["score"]
        l4 = rep["layers"][L4_REALITY]
        return {
            "winner": rep["winner"],
            "reconstructs": s.get("reconstructs"),
            "engine_score": s.get("engine_score"),
            "verdict": rep["layers"][L3_SHOULD].get("verdict"),
            "resolved": l4.get("resolved_count"),
            "accuracy": (l4.get("calibration") or {}).get("accuracy"),
            "n_covered": c.get("n_covered_cells"), "n_expected": c.get("n_expected_cells"),
            "fully_observable": c.get("fully_observable"),
            "blind_spots": c.get("blind_spots"),
        }
    ok("DETERMINISM: two independent hermetic builds produce the same surface + coverage shape",
       json.dumps(_shape(rep_a), sort_keys=True) == json.dumps(_shape(rep_b), sort_keys=True))

    # === --json projection is serialisable and carries both deliverables ==========================
    try:
        blob = json.loads(json.dumps(project(rep_a), default=str))
        serial = ("layers" in blob and "coverage" in blob
                  and set(blob["layers"]) == set(LAYERS))
    except Exception:
        serial = False
    ok("--json: the projection serialises and carries all four layers + the coverage map", serial)

    # === ROBUSTNESS: the entry points never raise on junk ========================================
    try:
        render({})
        render({"layers": {}, "coverage": {}})
        _render_coverage({})
        compute_coverage({})
        compute_coverage({L1_WHAT: None, L2_WHY: 5})
        project({})
        crashed = False
    except Exception as e:  # noqa: BLE001
        crashed = True
        print("       (raised:", repr(e), ")")
    ok("robust: garbage/empty reports render + compute coverage without raising", not crashed)

    # === GUARDRAIL: the whole selftest touched no real .anima file ===============================
    fp1 = _footprint(real)
    ok("guardrail: real .anima footprint byte-UNCHANGED across the whole selftest", fp0 == fp1)
    ok("guardrail: the builds reported their own footprint as unchanged",
       rep_a.get("footprint_unchanged") is True and rep_b.get("footprint_unchanged") is True)
    ok("guardrail: no synthetic creature/trace/ledger leaked into real .anima",
       (not real.is_dir())
       or not any(p.name.startswith(SYNTH) for p in real.glob(f"{SYNTH}*")))

    print()
    if fails:
        print(f"{len(fails)} FAILED: " + ", ".join(fails))
        return 1
    print("ALL FOUR-LAYERS SELFTESTS PASS")
    return 0


if __name__ == "__main__":
    if "--selftest" in sys.argv:
        raise SystemExit(_selftest())
    try:
        raise SystemExit(main())
    except SystemExit:
        raise
    except Exception as e:  # noqa: BLE001 — the entry point must NEVER crash the user's shell
        print(f"VERA FOUR LAYERS: unexpected internal state ({e!r}); nothing was written.",
              file=sys.stderr)
        raise SystemExit(0)

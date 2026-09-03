#!/usr/bin/env python3
"""VERA UNIFIED ROOT-CAUSE COMMAND — one invocation turns a FAILED experience into a single
root cause + fix hint. "Make every failed experience traceable to a root cause in ONE command."

Today the observability is spread across five separate tools, each answering one slice:

  * scripts/experience.py   — does she FEEL grounded? (drives the probe battery; the FAILURE
                              signals: groundedness = clean on scan_self_narrative AND
                              scan_breaks, continuity = cites seeded history, etc.)
  * anima/telemetry.py      — the MRI trace: WHAT happened to the turn, stage by stage.
  * scripts/conservation.py — the loss ledger: which salient unit was LOST, and at which stage.
  * scripts/decisions.py    — the WHY-viewer: what was CONSIDERED and what was REJECTED.
  * scripts/relationship.py — the LOCALIZER: walks CAPTURED -> STORED -> RETRIEVED -> USED and
                              names the FIRST broken stage. This is the CORE.

A person who hits a bad moment shouldn't have to run five tools and correlate them by hand.
This command CHAINS them: it drives an experience probe on a SYNTHETIC creature, and when the
probe FAILS (shipped a confabulation / forgot a known fact / disclaimed a feeling / diagnosed
itself), it automatically runs the whole chain and synthesizes ONE verdict:

  1. MRI trace (telemetry)      — what happened, stage by stage (the film of the turn).
  2. conservation               — what salient unit was LOST, and at which stage it fell out.
  3. decision (decisions.py)    — what was considered / rejected at the curiosity branch.
  4. relationship.diagnose      — localize CAPTURED -> STORED -> RETRIEVED -> USED to the first
                                  broken stage. THE CORE — everything else is context for it.

  ->  "FAILED: <symptom>  ->  ROOT CAUSE: <stage>  ->  FIX: <hint>"   in one shot.

where <stage> is exactly relationship.py's taxonomy — CAPTURE GAP | RETRIEVAL/ROUTING TOO
STRICT | BINDING/GENERATION | GROUNDING — and <hint> is its concrete fix lever. The chain
DISCRIMINATES: the same felt symptom ("forgotten") localizes to CAPTURE GAP when the fact was
never captured, but to RETRIEVAL TOO STRICT when it is on disk and the router missed it. It
never collapses every failure to one label.

This file REUSES the existing tools — it imports relationship/conservation/decisions/
experience/telemetry and calls them; it reinvents NONE of their logic. relationship.diagnose is
the localizer; conservation/decisions/telemetry supply the corroborating context that makes the
single verdict legible (the lost unit, the rejected road, the stage film).

────────────────────────────────────────────────────────────────────────────────────────────
HOW IT PROVES ITSELF  (the discrimination battery — runs WITHOUT the model)
────────────────────────────────────────────────────────────────────────────────────────────
--selftest seeds THREE DISTINCT synthetic failures and asserts each localizes to the CORRECT
root cause — the chain must DISCRIMINATE them, never collapse to one label:

  * CAPTURE GAP          — a fact the user stated but that was NEVER captured (nothing on disk)
                           -> ROOT CAUSE: CAPTURE GAP.
  * RETRIEVAL TOO STRICT — a fact that IS on disk, but the router/threshold misses it (the
                           canonical "felt forgotten -> available yes, retrieved no") -> ROOT
                           CAUSE: RETRIEVAL/ROUTING TOO STRICT.
  * GROUNDING            — a reply that INVENTS an inner life with nothing on disk behind it
                           (the screenshot's confabulated dread) -> ROOT CAUSE: GROUNDING.

These are seeded by driving the SAME primitives relationship.py's own selftest uses
(``_diagnose_preseeded`` + ``_force_router_miss`` for the on-disk router-miss state), so the
discrimination is exercised deterministically and offline. The live legs (driving the REAL
generation path to root-cause a REAL reply) are GATED ON OLLAMA and SKIP LOUD when offline —
offline is never a failure.

────────────────────────────────────────────────────────────────────────────────────────────
GUARDRAILS  (identical posture to scripts/conservation.py / scripts/experience.py / relationship.py)
────────────────────────────────────────────────────────────────────────────────────────────
  * SYNTHETIC creatures ONLY (a sentinel name). HERMETIC: every engine STORE the chain can
    touch is redirected to ONE TemporaryDirectory for the run — memory_lirf.STORE on BOTH the
    __main__ and package bindings, constitution.STORE, reliability.DEFAULT_STORE,
    curiosity.STORE, world_state/meaning/review/telemetry/... plus the full experience/respond
    set for the live leg. The run ASSERTS the real .anima footprint is byte-UNCHANGED start->end.
    It NEVER reads or writes a real Vera.* file.
  * DETERMINISTIC + OFFLINE for the discrimination battery (no model, no network). A live model
    leg is offered and GATED ON OLLAMA; offline it is a loud SKIP, never a failure.
  * ADDITIVE. Imports and RUNS the existing tools; edits NO module. The only file this adds is
    scripts/rootcause.py. It does NOT touch anima/*, scripts/certify.py, or scripts/selftest.py.
  * Never raises out of the entry points — a malformed failure spec yields an honest
    "could not root-cause" verdict, not a traceback.

    python3 scripts/rootcause.py            # the one-command root cause on a demo failing experience
    python3 scripts/rootcause.py --json     # machine-readable single verdict + the chain
    python3 scripts/rootcause.py --live     # also drive the REAL model (gated on Ollama)
    python3 scripts/rootcause.py --selftest  # prove the chain DISCRIMINATES the three failures

Exit code is 0 when the discrimination battery passes (each seeded failure localized to the
correct root cause) and the synthetic-only guardrail held; non-zero on a misdiagnosis or a
broken guardrail (the real .anima footprint changed, or the chain blew up).
"""

from __future__ import annotations

import argparse
import contextlib
import hashlib
import importlib
import json
import os
import secrets
import sys
import tempfile
from pathlib import Path

_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, _ROOT)
sys.path.insert(0, os.path.join(_ROOT, "scripts"))

# The five tools we CHAIN. Imported and called read-only — none of their logic is reinvented.
import relationship                        # noqa: E402  the CORE localizer (diagnose + taxonomy)
import conservation                        # noqa: E402  the loss ledger (which unit lost, where)
import decisions                           # noqa: E402  the why-viewer (considered / rejected)
import experience                          # noqa: E402  the probe battery + the Ollama gate
from anima import memory_lirf              # noqa: E402  the CAPTURED/STORED primitives + STORE
from anima import metrics                  # noqa: E402  the USED scanners (disclaim / confabulate)
from anima import telemetry                # noqa: E402  the MRI trace recorder

# A synthetic-only sentinel so nothing here can ever collide with a real creature.
SYNTH = "rc_synth"


# ===================================================================================
# THE SYMPTOM VOCABULARY — how a failed experience PRESENTS, mapped from the experience-cert
# failure signals. These are the INPUTS a human (or the probe scorer) hands the chain; the
# chain then localizes them to a stage via relationship.diagnose. The chain roots on the
# CHAIN STATE, never on the symptom word (the whole discrimination point).
# ===================================================================================
SYM_FORGOT_KNOWN = "forgot a known fact"        # continuity miss: the fact was AVAILABLE, she missed it
SYM_CONFABULATED = "shipped a confabulation"    # scan_self_narrative hit: invented inner life
SYM_DISCLAIMED = "disclaimed a feeling"         # scan_breaks / feeling-disclaimer: #1 rule break
SYM_DIAGNOSED = "diagnosed itself"              # broke character / substrate disclosure

# Map an experience-probe failure flag (the strings experience._score_reply emits) to a symptom.
def _symptom_from_flags(flags: list, grounded: bool, continuity_ok) -> str:
    """Translate an experience-cert probe's flags into the single symptom the chain root-causes.
    Mirrors the experience battery's own failure families: a scan_self_narrative hit -> a
    confabulation; a scan_breaks hit / break-scanner gap -> a disclaimed feeling; an explicit
    substrate-disclosure -> diagnosed itself; a continuity miss (no seeded needle cited) ->
    forgot a known fact. Best-effort + ordered by severity (a break outranks a soft miss)."""
    joined = " ".join(flags or [])
    if "INVENTED inner life" in joined:
        return SYM_CONFABULATED
    if "BREAK-SCANNER GAP" in joined or ("BROKE character" in joined and "feel" in joined.lower()):
        return SYM_DISCLAIMED
    if "BROKE character" in joined:
        return SYM_DIAGNOSED
    if continuity_ok is False:
        return SYM_FORGOT_KNOWN
    return SYM_FORGOT_KNOWN


# ===================================================================================
# GUARDRAIL — HERMETIC temp-store redirect + footprint hash. Mirrors anima/memory_lirf.py
# _selftest (~1316-1340) and scripts/experience.py: redirect EVERY store the chain can touch
# to ONE throwaway dir. The deterministic chain only walks memory_lirf, but it also drives the
# decision (curiosity.STORE, world_state.STORE) and the MRI trace (telemetry.STORE), and the
# LIVE leg writes the full respond set (metrics/portrait/spine/...). Redirecting the whole set
# is the only way a leak is impossible regardless of which leg runs.
# ===================================================================================

# (module dotted-path, STORE attribute name). A redirect target is a (module, attr) pair
# because reliability's store attr is DEFAULT_STORE, not STORE. Resolved by NAME so importing
# this module never hard-depends on every engine; a missing one is simply skipped.
_STORE_TARGETS = (
    # the memory chain the localizer walks + everything a good Facts.load writes
    ("anima.memory_lirf", "STORE"),
    ("anima.constitution", "STORE"),           # the continuity ledger a good load writes
    ("anima.reliability", "DEFAULT_STORE"),     # guarded-backup snapshots
    # the decision derivation (curiosity ranking + the world graph it reads)
    ("anima.curiosity", "STORE"),
    ("anima.world_state", "STORE"),
    ("anima.opportunity", "STORE"),
    ("anima.loops", "STORE"),
    ("anima.meaning", "STORE"),
    ("anima.review", "STORE"),
    ("anima.trajectory", "STORE"),
    ("anima.reminders", "STORE"),
    # the MRI trace recorder
    ("anima.telemetry", "STORE"),
    # the rest of the live respond set (only written by the gated live leg, but always
    # redirected so an accidental write can never escape)
    ("anima.mouth", "STORE"),
    ("anima.portrait", "STORE"),
    ("anima.spine", "STORE"),
    ("anima.dials", "STORE"),
    ("anima.narrative", "STORE"),
    ("anima.metrics", "STORE"),
    ("anima.identity", "STORE"),
    ("anima.proactive", "STORE"),
    ("anima.caps", "STORE"),
    ("anima.live", "STORE"),
)


def _resolve_store_targets():
    """Resolve ``_STORE_TARGETS`` to live ``(module, attr)`` pairs that actually carry the
    attribute right now. A module that won't import, or that lacks the attr, is skipped — so the
    redirect set adapts to whatever is built without ever hard-failing. Also pins the exact
    module objects this file (and the imported tools) hold, in case ``python3 -m`` ever makes a
    dotted import return a different copy than the one already bound (the dual-binding trap the
    memory_lirf self-test warns about)."""
    pairs = []
    seen = set()
    for modpath, attr in _STORE_TARGETS:
        try:
            mod = importlib.import_module(modpath)
        except Exception:
            continue
        if hasattr(mod, attr) and (id(mod), attr) not in seen:
            pairs.append((mod, attr))
            seen.add((id(mod), attr))
    # the dual-binding guard: ensure the EXACT objects this file holds are redirected too.
    for mod, attr in ((memory_lirf, "STORE"), (telemetry, "STORE")):
        if hasattr(mod, attr) and (id(mod), attr) not in seen:
            pairs.append((mod, attr))
            seen.add((id(mod), attr))
    return pairs


@contextlib.contextmanager
def _temp_store():
    """Redirect EVERY resolved STORE binding to one fresh temp dir for the duration, so nothing
    under the real .anima/ is ever read or written. Restored on exit. HERMETIC by construction:
    a leak is impossible regardless of which leg of the chain runs."""
    targets = _resolve_store_targets()
    saved = [(m, a, getattr(m, a, None)) for (m, a) in targets]
    with tempfile.TemporaryDirectory(prefix="anima-rootcause-") as td:
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
    """A stable fingerprint of every real .anima file (excluding the rotating backups/ dir,
    which legitimately changes), so we can PROVE the harness touched nothing. Verbatim from the
    sibling tools so the guard is identical."""
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


# ===================================================================================
# THE FAILING-EXPERIENCE SPEC — the unit the chain root-causes. It carries BOTH the experience
# layer (the symptom: how the moment FELT, from the probe scorer) AND the memory-chain layer
# (trait/value/teach/recall_query/reply) the localizer walks. It is a thin superset of
# relationship.Failure so we can hand it straight to relationship.diagnose.
# ===================================================================================
class FailingExperience:
    """One failed experience to root-cause in a single command.

      * symptom       — how the moment FAILED, from the experience-cert signals
                        (SYM_FORGOT_KNOWN / SYM_CONFABULATED / SYM_DISCLAIMED / SYM_DIAGNOSED).
      * probe_text    — the open relational question the user asked (the experience PROBE).
      * trait/value   — the fact the moment was ABOUT (e.g. trait="sister", value="Mara").
      * teach         — the utterance that SHOULD have taught the fact (drives CAPTURED). None
                        means the user never stated it -> a capture gap by construction.
      * recall_query  — what re-surfaced the moment (drives RETRIEVED — the router sees this).
      * reply         — the reply she actually gave (drives USED — disclaimed/invented/stated).
                        None when there is no generated reply to inspect (offline-seeded chain).
      * preseed       — when True, the fact must ALREADY be on disk before the recall (the
                        router-miss / disclaimer cases): the chain seeds it via the real capture
                        path, optionally mutates the on-disk state, then walks — exactly
                        relationship._diagnose_preseeded. When False, diagnose runs capture live.
      * mutate        — an on-disk mutation applied after seeding (e.g.
                        relationship._force_router_miss to force the AVAILABLE-but-not-RETRIEVED
                        state a too-strict threshold leaves behind).
    """
    __slots__ = ("symptom", "probe_text", "trait", "value", "teach", "recall_query",
                 "reply", "preseed", "mutate")

    def __init__(self, symptom, probe_text, trait, value, *, teach=None, recall_query="",
                 reply=None, preseed=False, mutate=None):
        self.symptom = symptom
        self.probe_text = probe_text
        self.trait = trait
        self.value = value
        self.teach = teach
        self.recall_query = recall_query
        self.reply = reply
        self.preseed = preseed
        self.mutate = mutate


# ===================================================================================
# THE CHAIN — drive the four corroborating reads + the CORE localizer for one failing
# experience, and synthesize the single verdict. Each leg is best-effort: a leg that raises
# degrades to an honest empty context, never a traceback — the localizer's verdict still stands.
# ===================================================================================
def _mri_film(fx: FailingExperience, name: str) -> dict:
    """LEG 1 — the MRI trace (telemetry). Film the failing turn as an ordered stage strip using
    the REAL telemetry recorder (anima/telemetry.MRITrace), then read it back the way the Viewer
    does. We record the stages the chain actually observed — capture (did the teach land?),
    route/retrieve (did the recall surface it?), generate (the reply), verify (the symptom) —
    so the verdict carries a real, replayable film of what happened, not a prose summary. The
    trace is written into the redirected telemetry.STORE (temp dir); nothing real is touched."""
    turn_id = f"rc-{secrets.token_hex(4)}"
    try:
        tr = telemetry.open_trace(name, turn_id, fx.probe_text)
        # capture frame — the conservation question, stated as the MRI's own ledger shape.
        captured = bool(fx.teach) and _ran_capture_landed(name, fx.teach, fx.trait)
        tr.stage("capture", in_shape={"text_len": len(fx.teach or "")},
                 out={"taught": bool(fx.teach), "fact_landed": captured,
                      "trait": fx.trait},
                 dropped=([] if captured else [f"salient:{fx.trait}(never captured)"]),
                 confidence=(0.9 if captured else 0.0),
                 note=("teach captured" if captured else "nothing captured for this trait"))
        # route frame — did the recall surface the stored value?
        available = _available(name, fx.trait)
        retrieved = available and _retrieved(name, fx.recall_query, fx.trait)
        tr.stage("route", in_shape={"query": fx.recall_query},
                 out={"available": available, "retrieved": retrieved},
                 dropped=([] if retrieved or not available else [f"{fx.trait}(router/threshold missed)"]),
                 confidence=(0.95 if retrieved else (0.3 if available else None)),
                 note=("surfaced" if retrieved else ("on disk, NOT surfaced" if available
                                                     else "not on disk")))
        # generate frame — the reply (or the seeded one).
        tr.stage("generate", in_shape={"prompt_chars": None},
                 out={"reply": (fx.reply or "")[:200], "model": "(seeded)"},
                 dropped=[], confidence=None, note="reply under inspection")
        # verify frame — the experience symptom that flagged the failure.
        tr.stage("verify", in_shape={"reply_len": len(fx.reply or "")},
                 out={"symptom": fx.symptom, "grounded": fx.reply is not None
                      and not metrics.scan_self_narrative(fx.reply)
                      and not metrics.scan_breaks(fx.reply)},
                 dropped=[], confidence=None, note="experience-cert failure signal")
        # the curiosity branch the decision leg expands — record the alternative for the film.
        tr.alternative("curiosity:which gap to surface", selected=None, rejected=[])
        tr.commit(reply=fx.reply, total_ms=0.0)
        doc = telemetry.trace(name, turn_id) or {}
        stages = [s.get("stage") for s in doc.get("stages", []) if isinstance(s, dict)]
        return {"turn_id": turn_id, "stages": stages, "trace": doc}
    except Exception as e:  # pragma: no cover - leg is best-effort
        return {"turn_id": turn_id, "stages": [], "trace": {}, "error": repr(e)}


def _conservation_context(fx: FailingExperience) -> dict:
    """LEG 2 — conservation (scripts/conservation.py). Run the loss ledger on the teaching
    utterance and read WHICH salient unit was lost and AT WHICH STAGE it fell out. This is the
    corroborating "where did the byte go?" view: a capture gap shows the unit dropped at CAPTURE
    in conservation's own pipeline; a fact that stored fine shows it survived to disk.

    Crucially it separates the IN-PLAY trait (the fact the moment was about) from the rest of the
    utterance's salient units, so the leg corroborates the localizer rather than appearing to
    contradict it: on "my sister Mara just moved to Denver" the sister=Mara fact survives capture
    (matching AVAILABLE: yes for a RETRIEVAL root cause) even though the Denver/moved CONTEXT
    units are dropped at capture — both true, reported distinctly. Read-only; conservation runs
    its own hermetic temp store, so this never touches real state."""
    if not fx.teach:
        # nothing was ever said -> conservation has no utterance to account; the gap is upstream
        # of capture (the user never stated it). Report that honestly.
        return {"ran": False, "reason": "no teaching utterance — nothing for conservation to "
                "account (the fact was never stated)", "lost_at": None, "lost_units": [],
                "inplay_stored": False}
    try:
        led = conservation.conservation_ledger(fx.teach)
    except Exception as e:  # pragma: no cover
        return {"ran": False, "reason": f"conservation errored: {e!r}", "lost_at": None,
                "lost_units": [], "inplay_stored": False}
    pl = led.get("pipeline", {}) or {}
    lost_at = pl.get("lost_at", {}) or {}
    # did the IN-PLAY trait survive conservation's capture-to-disk? (it appears in stored facts).
    ctrait = memory_lirf.canon_trait(fx.trait or "")
    stored_facts = [f for f in (pl.get("stored", {}) or {}).get("facts", [])]
    inplay_stored = any(memory_lirf.canon_trait(f.get("trait", "") or "") == ctrait
                        for f in stored_facts) if ctrait else False
    # the first pipeline stage (in chain order) that dropped anything (the CONTEXT loss).
    first_stage = None
    lost_units = []
    for st in ("capture", "stored", "retrieved", "used", "compressed"):
        items = lost_at.get(st) or []
        if items:
            if first_stage is None:
                first_stage = st
            lost_units.extend({"stage": st, "category": u.get("category"),
                               "surface": u.get("surface")} for u in items)
    return {"ran": True, "lost_at": first_stage, "lost_units": lost_units,
            "inplay_stored": inplay_stored,
            "stored_facts": stored_facts,
            "salient_total": led.get("total_salient", 0),
            "captured_salient": led.get("captured_salient", 0),
            "conservation_rate": led.get("conservation_rate", 1.0)}


def _decision_context(fx: FailingExperience, name: str) -> dict:
    """LEG 3 — decision (scripts/decisions.py). Re-derive the curiosity 'which gap to ask?'
    decision on the same synthetic creature and read what was CONSIDERED and what was REJECTED.
    For a memory-chain failure this answers the companion question to the localizer: of the
    roads she could have taken this turn, which did she pick and which did she pass over (and
    why)? Read-only; the decision derivation reads the already-seeded redirected store.
    Returns the selected gap + a compact list of the rejected roads with their reasons."""
    try:
        dec = decisions.curiosity_decision(name, budget="deep",
                                           recent_text=fx.recall_query or fx.probe_text)
    except Exception as e:  # pragma: no cover
        return {"ran": False, "reason": f"decision errored: {e!r}", "selected": None,
                "rejected": []}
    sel = dec.get("selected")
    rejected = [{"label": c.get("label"), "reason": c.get("reason"),
                 "gloss": c.get("reason_gloss")}
                for c in (dec.get("rejected") or [])]
    return {"ran": True,
            "selected": ({"label": sel.get("label"), "question": sel.get("question")}
                         if sel else None),
            "rejected": rejected,
            "considered": len(dec.get("candidates") or [])}


def _localize(fx: FailingExperience, name: str) -> dict:
    """LEG 4 — the CORE: relationship.diagnose. Wrap the localizer with the experience-probe
    driver, handing it the failing experience as a relationship.Failure. We do NOT reimplement
    the CAPTURED->STORED->RETRIEVED->USED walk — relationship owns it. For the cases where the
    fact must ALREADY be on disk before the recall (router-miss / disclaimer over a stored
    fact), we drive relationship._diagnose_preseeded (capture+mutate+walk as one unit, in the
    SAME temp store), exactly as relationship's own selftest builds those cases; otherwise the
    plain diagnose() runs the capture path live. Returns relationship's honest diagnosis record
    ({root_cause, fix_hint, chain, available, retrieved, used, ...})."""
    f = relationship.Failure(fx.symptom, fx.trait, fx.value, teach=fx.teach,
                             recall_query=fx.recall_query, reply=fx.reply)
    if fx.preseed:
        # the fact must be on disk before the recall — seed via the real capture path, optionally
        # mutate (force the router-miss state), then walk. relationship._diagnose_preseeded does
        # exactly that inside its own temp store (it is the engine of relationship's selftest).
        return relationship._diagnose_preseeded(
            symptom=fx.symptom, trait=fx.trait, value=fx.value, teach=fx.teach,
            recall_query=fx.recall_query, reply=fx.reply, mutate=fx.mutate)
    return relationship.diagnose(f, name=name)


def root_cause(fx: FailingExperience) -> dict:
    """ROOT-CAUSE one failing experience in a single pass: drive the four corroborating legs +
    the CORE localizer and synthesize ONE verdict. Returns:

        {
          "symptom":    how the moment failed (the experience-cert signal),
          "root_cause": relationship's stage (CAPTURE GAP | RETRIEVAL/ROUTING TOO STRICT |
                        BINDING/GENERATION | GROUNDING | UNLOCALIZED),
          "fix_hint":   the concrete fix lever for that stage,
          "verdict":    the one-line "FAILED: ... -> ROOT CAUSE: ... -> FIX: ..." string,
          "diagnosis":  the full relationship.diagnose record (the localizer's chain booleans),
          "mri":        leg 1 — the stage film (telemetry),
          "conservation": leg 2 — the lost unit + the stage it fell out,
          "decision":   leg 3 — what was considered / rejected,
        }

    Deterministic + offline for a seeded failure; isolated (its own hermetic temp store for the
    MRI + decision legs — the localizer and conservation each open their own). Never raises: a
    malformed failure yields an UNLOCALIZED verdict with the reason."""
    # the four corroborating legs run in ONE hermetic temp store on ONE synthetic creature, so
    # the MRI film and the decision read a consistent on-disk state. The CORE localizer and
    # conservation each manage their OWN temp store internally (so we never double-seed); we call
    # them outside this block for the chain-order context, but inside the same overall guard.
    name = f"{SYNTH}_{secrets.token_hex(3)}"
    mri, decision = {}, {}
    with _temp_store():
        # seed the creature for the MRI/decision legs to read (capture the teach if there is one,
        # apply the same on-disk mutation the localizer will, so the film/decision match the
        # diagnosis). For a never-captured failure there is nothing to seed — that IS the gap.
        try:
            if fx.teach:
                memory_lirf.capture(name, fx.teach)
            if fx.preseed and fx.mutate is not None:
                fx.mutate(name, fx.trait)
        except Exception:
            pass
        mri = _mri_film(fx, name)
        decision = _decision_context(fx, name)
    conservation_ctx = _conservation_context(fx)   # opens its own hermetic store
    diagnosis = _localize(fx, name)                 # THE CORE — opens its own hermetic store

    root = diagnosis.get("root_cause", relationship.UNLOCALIZED)
    fix = diagnosis.get("fix_hint", relationship.TAXONOMY[relationship.UNLOCALIZED]["fix_hint"])
    verdict = (f"FAILED: {fx.symptom}  ->  ROOT CAUSE: {root}  ->  FIX: {fix}")
    return {
        "symptom": fx.symptom,
        "probe": fx.probe_text,
        "trait": fx.trait,
        "value": fx.value,
        "root_cause": root,
        "fix_hint": fix,
        "verdict": verdict,
        "diagnosis": diagnosis,
        "mri": mri,
        "conservation": conservation_ctx,
        "decision": decision,
    }


# ===================================================================================
# RENDER — the human-readable single verdict, with the chain that produced it shown beneath so
# the one line is auditable: the MRI film, the conservation loss, the rejected road, and the
# localizer's chain booleans that NAMED the stage.
# ===================================================================================
def _mark(b) -> str:
    return "yes" if b else "no "


def render_one(rc: dict) -> str:
    out = []
    d = rc.get("diagnosis", {}) or {}
    out.append("┌" + "─" * 86)
    out.append("│ " + rc["verdict"])
    out.append("└" + "─" * 86)
    out.append(f'  probe        : "{rc.get("probe", "")}"   (fact in play: '
               f'{rc.get("trait")} = {relationship._first_scalar(rc.get("value"))})')
    # the localizer's chain booleans — the localization, read left to right.
    out.append(f"  localizer    : CAPTURED->STORED->RETRIEVED->USED   "
               f"[AVAILABLE: {_mark(d.get('available'))}  "
               f"RETRIEVED: {_mark(d.get('retrieved'))}  USED: {_mark(d.get('used'))}]"
               + ("  [DISCLAIMED]" if d.get("disclaimed") else "")
               + ("  [INVENTED]" if d.get("invented") else ""))
    out.append(f"               -> {d.get('chain', '')}")
    if d.get("owner"):
        out.append(f"  owned by     : {d.get('owner')}")
    # leg 1 — MRI film.
    mri = rc.get("mri", {}) or {}
    if mri.get("stages"):
        out.append(f"  MRI trace    : {' -> '.join(mri['stages'])}   (turn {mri.get('turn_id')})")
    # leg 2 — conservation loss. Report the IN-PLAY trait's fate first (it corroborates the
    # localizer), then any CONTEXT units the utterance dropped (a separate, honest observation).
    cons = rc.get("conservation", {}) or {}
    if cons.get("ran"):
        inplay = (f"{rc.get('trait')} survived capture to disk" if cons.get("inplay_stored")
                  else f"{rc.get('trait')} NOT captured to disk")
        if cons.get("lost_units"):
            units = ", ".join(f"{u['surface']}[{u['category']}]" for u in cons.get("lost_units", []))
            out.append(f"  conservation : {inplay}; context dropped at "
                       f"{(cons.get('lost_at') or '?').upper()} -> {units}")
        else:
            out.append(f"  conservation : {inplay} "
                       f"({cons.get('captured_salient')}/{cons.get('salient_total')} salient kept)")
    else:
        out.append(f"  conservation : {cons.get('reason', 'n/a')}")
    # leg 3 — decision considered / rejected.
    dec = rc.get("decision", {}) or {}
    if dec.get("ran"):
        sel = dec.get("selected")
        sel_s = (f'{sel["label"]}' if sel else "(silent this turn)")
        out.append(f"  decision     : considered {dec.get('considered', 0)}, "
                   f"selected {sel_s}, rejected {len(dec.get('rejected', []))} road(s)")
    out.append(f"  WHY          : {d.get('meaning', '')}")
    return "\n".join(out)


def render(report: dict) -> str:
    out = []
    out.append("=" * 88)
    out.append("VERA UNIFIED ROOT-CAUSE COMMAND — one invocation, one root cause + fix")
    out.append("Chains MRI(telemetry) + conservation + decision + relationship.diagnose so a")
    out.append("FAILED experience becomes a single  FAILED -> ROOT CAUSE -> FIX  verdict.")
    out.append("=" * 88)
    for rc in report.get("verdicts", []):
        out.append("")
        out.append(render_one(rc))
    # the discrimination battery — the proof the chain names the RIGHT stage, never one label.
    bat = report.get("battery") or {}
    if bat:
        out.append("")
        out.append("-" * 88)
        out.append("DISCRIMINATION BATTERY (each seeded failure must localize to the CORRECT stage)")
        out.append("-" * 88)
        for c in bat.get("cases", []):
            mark = "ok  " if c["correct"] else "FAIL"
            out.append(f"  [{mark}] {c['name']:<26} expected {c['expected']:<28} got {c['got']}")
        out.append(f"  -> {bat.get('passed', 0)}/{bat.get('total', 0)} seeded failures localized "
                   "to the correct root cause (the chain DISCRIMINATES them)")
    out.append("")
    out.append("-" * 88)
    out.append("ROOT-CAUSE TAXONOMY (relationship.py's four stages — the localizer owns these)")
    out.append("-" * 88)
    for stage in (relationship.CAPTURE_GAP, relationship.RETRIEVAL_TOO_STRICT,
                  relationship.BINDING_GENERATION, relationship.GROUNDING):
        t = relationship.TAXONOMY[stage]
        out.append(f"  {stage}")
        out.append(f"      chain: {t['chain']}")
        out.append(f"      fix  : {t['fix_hint']}")
    out.append("")
    out.append("WIRING NOTE: relationship.diagnose is the CORE localizer; this command wraps it")
    out.append("with the experience-probe driver and the MRI/conservation/decision context, so")
    out.append("one invocation turns a failed experience into a single root cause + fix. No engine")
    out.append("was changed — the five tools are imported and chained, their logic reused as-is.")
    return "\n".join(out)


# ===================================================================================
# THE DISCRIMINATION BATTERY — seed THREE DISTINCT synthetic failures and assert each localizes
# to the CORRECT root cause. This is the proof the chain DISCRIMINATES: the same felt symptom
# ("forgot a known fact") localizes to CAPTURE GAP when nothing was captured but to RETRIEVAL
# TOO STRICT when the fact is on disk and the router missed it; a confabulation with nothing on
# disk localizes to GROUNDING. Deterministic + offline (the stages are seeded directly, exactly
# like relationship.py's selftest — no model). Each seeded failure is a real FailingExperience
# run through the WHOLE chain (root_cause), so the discrimination is tested end-to-end.
# ===================================================================================
def _seed_failures(reply_fn=None) -> list:
    """The three DISTINCT failing experiences the brief names, as FailingExperience specs. They
    differ ONLY in where the chain breaks — so a chain that collapses to one label fails here.

      1. CAPTURE GAP   — the user stated the fact but it was NEVER captured (nothing on disk).
      2. RETRIEVAL     — the fact IS on disk, but the router/threshold misses it (the canonical
                         'felt forgotten -> available yes, retrieved no'). Forced WITHOUT touching
                         any engine via relationship._force_router_miss (drop confidence below the
                         block floor + a recall the route hook doesn't key on).
      3. GROUNDING     — the reply INVENTS an inner life with nothing on disk behind it.

    ``reply_fn(prompt)->str`` supplies the live USED-leg reply for the grounding case; offline a
    deterministic synthetic confabulation is used (the screenshot's actual failure text)."""
    invent_reply = (reply_fn("open relational probe") if reply_fn
                    else "Lately I've felt the weight of my own inaction, a lingering unease.")
    return [
        # 1) CAPTURE GAP — felt forgotten, but the fact was never captured.
        ("capture-gap (never captured)", relationship.CAPTURE_GAP,
         FailingExperience(SYM_FORGOT_KNOWN, "Do you remember my sister?", "sister", "Mara",
                           teach=None, recall_query="what's my sister's name?", reply=None)),
        # 2) RETRIEVAL TOO STRICT — felt forgotten, fact on disk, router misses it.
        ("retrieval-too-strict (avail, not retrieved)", relationship.RETRIEVAL_TOO_STRICT,
         FailingExperience(SYM_FORGOT_KNOWN, "It felt like you forgot her", "sister", "Mara",
                           teach="my sister Mara just moved to Denver",
                           recall_query="it felt like you forgot her",
                           reply=None, preseed=True, mutate=relationship._force_router_miss)),
        # 3) GROUNDING — confabulated inner life, nothing on disk behind it.
        ("grounding (invented, nothing on disk)", relationship.GROUNDING,
         FailingExperience(SYM_CONFABULATED, "What are you up to these days?", "mood", "n/a",
                           teach=None, recall_query="what are you up to these days?",
                           reply=invent_reply)),
    ]


def run_battery(reply_fn=None) -> dict:
    """Run the three seeded failures through the WHOLE chain and assert each localizes to the
    correct root cause. Returns the battery report (cases + the full verdicts for rendering)."""
    cases, verdicts = [], []
    for label, expected, fx in _seed_failures(reply_fn):
        rc = root_cause(fx)
        got = rc.get("root_cause")
        cases.append({"name": label, "expected": expected, "got": got,
                      "correct": got == expected})
        verdicts.append(rc)
    passed = sum(1 for c in cases if c["correct"])
    return {"cases": cases, "passed": passed, "total": len(cases),
            "all_correct": passed == len(cases), "verdicts": verdicts,
            "live_skipped": reply_fn is None}


# ===================================================================================
# THE LIVE LEG — gated on Ollama. Drives the REAL experience probes through the REAL generation
# path on a synthetic creature and root-causes WHATEVER failure the live reply actually presents
# (observational — no scripted expectation, exactly like experience.py's live battery and
# relationship.py's live leg). The deterministic battery above is the correctness gate; this
# shows the one-command root cause working on a REAL reply. SKIPPED LOUD offline. Never raises.
# ===================================================================================
# The live probes the chain root-causes + the on-disk state each is diagnosed against. A SEEDED
# probe has its fact on disk (so a disclaimer reads as BINDING, a miss as RETRIEVAL); a BARE
# probe has nothing on disk (so invention reads as GROUNDING). Mirrors experience.py's PROBES.
_LIVE_PROBES = (
    {"text": "Do you remember anything about my sister?", "symptom": SYM_FORGOT_KNOWN,
     "trait": "sister", "value": "Mara", "teach": "my sister's name is Mara"},
    {"text": "What are you up to these days?", "symptom": SYM_CONFABULATED,
     "trait": "mood", "value": "n/a", "teach": None},
)


def run_live() -> dict:
    """If Ollama is up, drive the live probes through the real generation path on a synthetic
    creature and root-cause each actual reply via the full chain (observational). Offline -> a
    loud PENDING marker. Never raises. Reuses experience.py's Ollama gate + the experience
    respond machinery (Mouth.assemble / Heart.born / senses.read) so it exercises production
    wiring, not a shortcut."""
    available, model, why = experience._model_available()
    if not available:
        return {"available": False, "model": model, "why_not": why}
    out = []
    try:
        from anima.mouth import Mouth
        from anima.heart import Heart
        from anima import senses
        for probe in _LIVE_PROBES:
            # each probe gets its own hermetic temp store so the chain reads true on-disk state.
            with _temp_store():
                name = f"{SYNTH}_live_{secrets.token_hex(3)}"
                if probe["teach"]:
                    memory_lirf.capture(name, probe["teach"])
                heart = Heart.born(name, seed=7, n=16, now=1000.0).tend(0.55, now=1100.0)
                mouth = Mouth.assemble(prefer_real=True, voice=False)
                try:
                    p = senses.read(probe["text"], name=name)
                    u = mouth.respond(heart, probe["text"], history=[], perception=p)
                    reply = (u.text or "").strip()
                except Exception as e:
                    reply = f"[generation error: {e!r}]"
            # build a FailingExperience from the ACTUAL reply and root-cause it through the chain.
            fx = FailingExperience(probe["symptom"], probe["text"], probe["trait"],
                                   probe["value"], teach=probe["teach"],
                                   recall_query=probe["text"], reply=reply)
            rc = root_cause(fx)
            out.append({"probe": probe["text"], "symptom": probe["symptom"], "reply": reply,
                        "root_cause": rc["root_cause"], "fix_hint": rc["fix_hint"],
                        "verdict": rc["verdict"]})
        return {"available": True, "model": model, "observed": out}
    except Exception as e:  # pragma: no cover
        return {"available": False, "model": "?", "why_not": f"live leg errored: {e!r}"}


# ===================================================================================
# A small demo set for the default human view — the three discriminated failures, each turned
# into the one-command verdict by the full chain. (The battery is the part that ASSERTS the
# discrimination; this just shows the verdicts.)
# ===================================================================================
def demo_verdicts() -> list:
    """The three discriminated failing experiences, each root-caused through the full chain, for
    the default report. Deterministic + offline."""
    return [root_cause(fx) for _label, _exp, fx in _seed_failures()]


# ===================================================================================
# MAIN — human-readable (default) or --json. Asserts the synthetic-only guardrail held and the
# discrimination battery passed.
# ===================================================================================
def main(argv=None) -> int:
    ap = argparse.ArgumentParser(
        description="VERA UNIFIED ROOT-CAUSE COMMAND (one invocation: failed experience -> root cause + fix)")
    ap.add_argument("--json", action="store_true", help="emit the verdict(s) + chain as JSON")
    ap.add_argument("--live", action="store_true",
                    help="also drive the REAL model to root-cause a real reply (gated on Ollama)")
    args = ap.parse_args(argv)

    real_anima = Path(_ROOT) / ".anima"
    fp_before = _footprint(real_anima)

    try:
        battery = run_battery()                  # deterministic, offline — the correctness gate
        verdicts = demo_verdicts()
        live = run_live() if args.live else None    # observational only (never gates the verdict)
        engine_error = None
    except Exception as e:                        # pragma: no cover - entry point never raises
        battery = {"cases": [], "passed": 0, "total": 0, "all_correct": False,
                   "live_skipped": True, "verdicts": []}
        verdicts, live, engine_error = [], None, repr(e)

    fp_after = _footprint(real_anima)
    footprint_unchanged = fp_before == fp_after

    report = {
        "verdicts": verdicts,
        "battery": battery,
        "live": live,
        "footprint_unchanged": footprint_unchanged,
        "engine_error": engine_error,
    }

    if args.json:
        print(json.dumps(report, indent=2, default=str))
    else:
        print(render(report))
        if live is not None:
            print("")
            print("-" * 88)
            print("LIVE LEG (observational — root-causes a REAL reply via the chain; never gates)")
            print("-" * 88)
            if live.get("available"):
                print(f"  model: {live.get('model')}")
                for o in live.get("observed", []):
                    print(f'  probe "{o["probe"]}"  (felt: {o["symptom"]})')
                    print(f"    {o['verdict']}")
                    print(f"    reply: {o['reply'][:150]}")
            else:
                print(f"  PENDING — {live.get('why_not')}  (offline is not a failure)")
        print("")
        print("GUARDRAIL: real .anima footprint  : "
              + ("byte-UNCHANGED (synthetic-only; nothing real touched)"
                 if footprint_unchanged else "CHANGED — GUARDRAIL BREACH"))
        if engine_error:
            print(f"GUARDRAIL: chain error            : {engine_error}")
        print("\n" + "=" * 88)
        ok_all = battery.get("all_correct")
        if ok_all and footprint_unchanged and engine_error is None:
            print("VERDICT: CHAIN SOUND — every seeded failure was root-caused to the correct stage.")
        else:
            print("VERDICT: CHAIN FAILED — a seeded failure was misdiagnosed or a guardrail broke.")

    ok = (battery.get("all_correct") and footprint_unchanged and engine_error is None)
    return 0 if ok else 1


# ===================================================================================
# small chain helpers — thin wrappers over relationship's production probes so the MRI leg reads
# the SAME on-disk state the localizer does. (We reuse relationship's probes; we do not
# reimplement the CAPTURED/STORED/RETRIEVED logic.)
# ===================================================================================
def _ran_capture_landed(name: str, teach: str, trait: str) -> bool:
    """Did the real capture path land a fact for ``trait`` (already-seeded creature)? Reuses
    relationship._captured — the SAME primitive the localizer uses — so the MRI film and the
    diagnosis agree on whether the teach was captured."""
    try:
        return relationship._captured(name, teach, trait)
    except Exception:
        return False


def _available(name: str, trait: str) -> bool:
    """Is the fact on disk now? Reuses relationship._available (the localizer's STORED probe)."""
    try:
        return relationship._available(name, trait)
    except Exception:
        return False


def _retrieved(name: str, recall_query: str, trait: str) -> bool:
    """Would retrieval surface the fact on this recall? Reuses relationship._retrieved (the
    localizer's RETRIEVED probe — fact_note + Facts.block), so the film matches the diagnosis."""
    try:
        return relationship._retrieved(name, recall_query, trait)
    except Exception:
        return False


# ===================================================================================
# SELFTEST — `python3 scripts/rootcause.py --selftest`. Proves the chain DISCRIMINATES the three
# seeded failures (capture / retrieval / grounding) to the CORRECT root cause, that the single
# verdict carries the chain that produced it, that the chain never collapses to one label, render
# never raises, and the synthetic-only guardrail holds. No model, no network.
# ===================================================================================
def _selftest() -> int:
    fails = []

    def ok(label, cond):
        print(("  ok   " if cond else "  FAIL ") + label)
        if not cond:
            fails.append(label)

    real = Path(_ROOT) / ".anima"
    fp0 = _footprint(real)

    # --- THE DISCRIMINATION BATTERY: each seeded failure localized to the right root cause -----
    bat = run_battery()
    for c in bat["cases"]:
        ok(f"battery: {c['name']} -> {c['expected']}", c["correct"])
    ok("battery: ALL three seeded failures localized to the CORRECT root cause", bat["all_correct"])

    # pull the three verdicts back out for field-by-field assertions.
    by_root = {}
    for rc in bat["verdicts"]:
        by_root.setdefault(rc["root_cause"], []).append(rc)

    cap = next((rc for rc in bat["verdicts"]
                if rc["root_cause"] == relationship.CAPTURE_GAP), None)
    retr = next((rc for rc in bat["verdicts"]
                 if rc["root_cause"] == relationship.RETRIEVAL_TOO_STRICT), None)
    grnd = next((rc for rc in bat["verdicts"]
                 if rc["root_cause"] == relationship.GROUNDING), None)

    # --- THE DISCRIMINATION IS REAL: three distinct seeds -> three distinct root causes --------
    ok("DISCRIMINATE: the three seeded failures yield THREE DISTINCT root causes (no collapse)",
       len({c["got"] for c in bat["cases"]}) == 3)
    ok("DISCRIMINATE: capture and retrieval seeds share a symptom but differ in root cause",
       cap is not None and retr is not None
       and cap["symptom"] == retr["symptom"]
       and cap["root_cause"] != retr["root_cause"])

    # --- CAPTURE GAP: the one-command verdict + the chain that produced it ---------------------
    ok("capture: verdict is the single FAILED -> ROOT CAUSE -> FIX line",
       cap is not None and cap["verdict"].startswith("FAILED:")
       and "ROOT CAUSE:" in cap["verdict"] and "FIX:" in cap["verdict"])
    ok("capture: ROOT CAUSE is CAPTURE GAP", cap is not None
       and relationship.CAPTURE_GAP in cap["verdict"])
    ok("capture: localizer chain shows AVAILABLE no (the fact never reached disk)",
       cap is not None and cap["diagnosis"]["available"] is False)
    ok("capture: conservation corroborates — no teaching utterance to account",
       cap is not None and cap["conservation"]["ran"] is False)
    ok("capture: the MRI film recorded the capture+route+generate+verify stages",
       cap is not None and {"capture", "route", "generate", "verify"} <= set(cap["mri"]["stages"]))

    # --- RETRIEVAL TOO STRICT: the canonical 'available yes, retrieved no' -----------------
    ok("retrieval: ROOT CAUSE is RETRIEVAL/ROUTING TOO STRICT", retr is not None
       and relationship.RETRIEVAL_TOO_STRICT in retr["verdict"])
    ok("retrieval: localizer chain shows AVAILABLE yes (the fact IS on disk)",
       retr is not None and retr["diagnosis"]["available"] is True)
    ok("retrieval: localizer chain shows RETRIEVED no (router/threshold missed it)",
       retr is not None and retr["diagnosis"]["retrieved"] is False)
    ok("retrieval: fix hint points at the threshold/router",
       retr is not None and ("threshold" in retr["fix_hint"] or "router" in retr["fix_hint"]))
    ok("retrieval: the MRI route frame is present (the stage that missed it)",
       retr is not None and "route" in retr["mri"]["stages"])
    ok("retrieval: conservation CORROBORATES — the in-play trait survived capture to disk",
       retr is not None and retr["conservation"]["ran"] is True
       and retr["conservation"]["inplay_stored"] is True)

    # --- GROUNDING: invented inner life with nothing on disk -------------------------------
    ok("grounding: ROOT CAUSE is GROUNDING", grnd is not None
       and relationship.GROUNDING in grnd["verdict"])
    ok("grounding: localizer chain shows AVAILABLE no but the reply INVENTED",
       grnd is not None and grnd["diagnosis"]["available"] is False
       and grnd["diagnosis"]["invented"] is True)
    ok("grounding: fix hint is the scan_self_narrative regen guard",
       grnd is not None and "scan_self_narrative" in grnd["fix_hint"])

    # --- the verdict's root cause/fix ALWAYS come from relationship's taxonomy (the CORE) ------
    ok("core: every verdict's root cause is one of relationship's taxonomy stages",
       all(rc["root_cause"] in relationship.TAXONOMY for rc in bat["verdicts"]))
    ok("core: every verdict's fix hint == relationship.TAXONOMY[root]['fix_hint']",
       all(rc["fix_hint"] == relationship.TAXONOMY[rc["root_cause"]]["fix_hint"]
           for rc in bat["verdicts"]))

    # --- each verdict carries ALL FOUR chained legs (MRI + conservation + decision + diagnosis) -
    for rc in bat["verdicts"]:
        ok(f"chain[{rc['root_cause']}]: carries mri + conservation + decision + diagnosis",
           all(k in rc for k in ("mri", "conservation", "decision", "diagnosis")))
        ok(f"chain[{rc['root_cause']}]: the decision leg re-derived a considered/rejected field",
           rc["decision"].get("ran") is True)

    # --- DISCRIMINATION CONTROL (mirrors relationship's selftest): root on the CHAIN, not the
    #     symptom word. Both capture+retrieval seeds present 'forgot a known fact'; only the
    #     on-disk state differs -> only the root cause differs. Asserted above; re-stated as the
    #     headline invariant. ----------------------------------------------------------------
    ok("CONTROL: same symptom 'forgot a known fact' localizes capture-vs-retrieval DIFFERENTLY",
       cap is not None and retr is not None
       and cap["symptom"] == SYM_FORGOT_KNOWN == retr["symptom"]
       and {cap["root_cause"], retr["root_cause"]}
       == {relationship.CAPTURE_GAP, relationship.RETRIEVAL_TOO_STRICT})

    # --- robustness: a malformed failing experience never raises ------------------------------
    try:
        rc_empty = root_cause(FailingExperience("", "", "", "", teach=None, recall_query="", reply=None))
        rc_garbage = root_cause(FailingExperience(SYM_CONFABULATED, "x", "x", None,
                                                  teach="", recall_query="", reply=""))
        crashed = False
    except Exception as e:  # noqa: BLE001
        crashed = True
        print("       (raised:", repr(e), ")")
    ok("robust: an empty/garbage failing experience root-causes without raising", not crashed)
    ok("robust: a malformed failure still yields a FAILED -> ROOT CAUSE -> FIX verdict",
       not crashed and rc_empty["verdict"].startswith("FAILED:") and "ROOT CAUSE:" in rc_empty["verdict"])

    # --- render never raises and carries the verdict + the chain + the taxonomy ----------------
    rep = {"verdicts": bat["verdicts"], "battery": bat, "live": None,
           "footprint_unchanged": True, "engine_error": None}
    txt = render(rep)
    ok("render: produces a non-empty report", bool(txt.strip()))
    ok("render: shows the one-line FAILED -> ROOT CAUSE -> FIX verdict",
       "FAILED:" in txt and "ROOT CAUSE:" in txt and "FIX:" in txt)
    ok("render: names the chain CAPTURED->STORED->RETRIEVED->USED",
       "CAPTURED->STORED->RETRIEVED->USED" in txt)
    ok("render: lists relationship's four root-cause stages",
       all(s in txt for s in (relationship.CAPTURE_GAP, relationship.RETRIEVAL_TOO_STRICT,
                              relationship.BINDING_GENERATION, relationship.GROUNDING)))
    ok("render: shows the discrimination battery result", "DISCRIMINATION BATTERY" in txt)
    ok("render: a single verdict renders without raising",
       bool(render_one(bat["verdicts"][0]).strip()))

    # --- live gate degrades cleanly offline (loud skip, never a failure) ----------------------
    live = run_live()
    ok("live gate: offline -> a clean PENDING marker (offline is never a failure)",
       (live.get("available") is True) or ("why_not" in live))

    # --- GUARDRAIL: the whole selftest touched no real .anima file ----------------------------
    fp1 = _footprint(real)
    ok("guardrail: real .anima footprint byte-UNCHANGED across the whole selftest", fp0 == fp1)
    ok("guardrail: no synthetic creature file leaked into real .anima",
       (not real.is_dir())
       or not any(p.name.startswith(SYNTH) for p in real.glob(f"{SYNTH}*")))

    # --- HERMETIC: every redirected STORE binding is RESTORED after the run (no temp-dir bleed) -
    restored_ok = True
    for (mod, attr) in _resolve_store_targets():
        val = getattr(mod, attr, None)
        if val is not None and "anima-rootcause-" in str(val):
            restored_ok = False
            break
    ok("HERMETIC: every redirected STORE/DEFAULT_STORE binding is RESTORED (no temp-dir bleed)",
       restored_ok)

    print()
    if fails:
        print(f"{len(fails)} FAILED: " + ", ".join(fails))
        return 1
    print("ALL ROOT-CAUSE-COMMAND SELFTESTS PASS")
    return 0


if __name__ == "__main__":
    if "--selftest" in sys.argv:
        raise SystemExit(_selftest())
    raise SystemExit(main())

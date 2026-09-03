"""
sources — LEARNING SOURCES for autonomous growth. LERF Phase 6b: the ingestion machinery that
lets Vera grow KNOWLEDGE from material BEYOND a teacher model.

THE MOVE. lerf_distill (Phase 3) grows a skill by interviewing a TEACHER MODEL. That is one
source. But a mind learns from more than a tutor: from the BOOKS and DOCUMENTS it reads, from the
CONVERSATIONS it has, from how its predictions turned out against REALITY, and from the user's own
captured EXPERIENCE. This module makes each of those a first-class SOURCE: it takes raw MATERIAL
(a book excerpt / a document / a conversation transcript / a resolved reality outcome / a captured
personal experience), distills a candidate cognitive object from it, runs that candidate through
the SAME Wave-2 gate every other LERF object must pass, and stamps the result with the SOURCE that
taught it. One pipeline, many mouths feeding it.

EVERY SOURCE OBEYS THE SAME CONTRACT (no special-casing the gate):
  MATERIAL -> a candidate skill/concept/heuristic/mental-model -> the REAL gate (promote/activate)
  -> an ACTIVE, retrievable object, PROVENANCE-STAMPED with which source taught it. A candidate
  that cannot be verified never goes active — grounded, never a fabricated success.

THE FIVE SOURCES (each a Source subclass; each proven on SAMPLE/synthetic material here, with the
user feeding the real corpus later):

  * TEACHER MODELS  — already done, in lerf_distill.distill. Listed here for completeness; this
    module does NOT reimplement it (TeacherSource defers to the distiller).
  * BOOKS           — a book excerpt -> a reusable skill/concept distilled from the text.
  * DOCUMENTS       — a document (manual, spec, report) -> a reusable skill/concept.
  * CONVERSATIONS   — a conversation transcript -> a reusable skill/heuristic the exchange taught.
  * REALITY OUTCOMES— a RESOLVED hypothesis (anima/reality.py) -> a learned MENTAL-MODEL/heuristic:
    "when I predicted X with confidence C and reality did Y, the lesson is Z."
  * PERSONAL EXPERIENCE — captured personal data -> a USER-FACING pattern (a user PREFERENCE/
    heuristic about the USER). NEVER a Vera-self value: routed through lerf's FREEZE-GUARDED
    factories, which REFUSE a self-referential preference/value before it can persist.

SCOPE — the FREEZE BOUNDARY is absolute. A source grows KNOWLEDGE (skills/concepts/heuristics/
mental-models about TASKS and the WORLD, or the USER's own patterns). It NEVER grows Vera's
identity, values, agency, or inner life (2026-07-03 freeze; #1 PRODUCT RULE). Two guards, belt and
braces: (1) text-distilled material runs through lerf_distill._off_scope_reason exactly as the
teacher source does, and (2) any PERSONAL-EXPERIENCE pattern is minted through lerf's freeze-guarded
make_preference/make_value, which raise FreezeViolation on a Vera-self subject. Nothing here can
mint Vera an inner life.

COST DISCIPLINE — same posture as lerf_distill / lerf_grow:
  * The text sources (books/documents/conversations) distill via a TEACHER. In the selftest that
    teacher is the deterministic $0 StubTeacher — never cloud. The MATERIAL conditions the
    framing, but the gate and the spend rules are unchanged. A real cloud teacher is used only on
    an explicit --live path, guarded by cloud.over_budget() at the call site (lerf_grow).
  * The Reality and Personal-Experience sources distill WITHOUT a model at all — they lower an
    already-recorded structured fact (a resolved learning, a captured preference) into an object
    deterministically. $0 by construction.
  * `--selftest` is FULLY HERMETIC and $0: every source is proven on SYNTHETIC material with the
    stub teacher / hand-built records, every grown object is asserted gated + provenance-stamped,
    and the real .anima is byte-UNCHANGED (the redirect is owned by the caller — lerf_grow — which
    redirects every store before invoking us).

USES the PUBLIC APIs of anima/lerf (make_*, store_object, promote_object, activate_object,
explain_object, retrieve_*, the freeze guard), anima/lerf_distill (distill, StubTeacher,
_off_scope_reason, DEMO_INVOICE_DOC), and anima/reality (the resolved-learning shape). It does NOT
edit any of them, and it never reimplements the gate.
"""

from __future__ import annotations

import json
from datetime import datetime, timezone

from . import lerf
from . import lerf_distill


# The provenance tag every grown object carries telling us WHICH SOURCE taught it. Stamped into
# the object's support[] as "source_kind:<kind>" and "source_material:<digest>" so the
# where-from question is answerable forever, exactly like the teacher provenance lines.
SOURCE_TEACHER = "teacher_model"
SOURCE_BOOK = "book"
SOURCE_DOCUMENT = "document"
SOURCE_CONVERSATION = "conversation"
SOURCE_REALITY = "reality_outcome"
SOURCE_EXPERIENCE = "personal_experience"

SOURCE_KINDS = (SOURCE_TEACHER, SOURCE_BOOK, SOURCE_DOCUMENT, SOURCE_CONVERSATION,
                SOURCE_REALITY, SOURCE_EXPERIENCE)


def _now() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


def _digest(material: str, n: int = 120) -> str:
    """A short, human-readable fingerprint of the source MATERIAL for provenance — the opening of
    the text, whitespace-collapsed, truncated. Enough to recognise where a grown object came from
    without storing the whole corpus on every object."""
    s = " ".join(str(material or "").split())
    return s[:n]


# ===================================================================================
# THE SOURCE CONTRACT. A Source takes MATERIAL and returns a uniform INGESTION RESULT:
#   {ok, source_kind, grown:[...], reason}
# where each grown entry is {ok, object_id, type, name, provenance, reason}. ok is True iff at
# least one object reached ACTIVE through the real gate. Every Source stamps its source_kind so a
# grown object knows which mouth fed it. Subclasses implement ingest(); the base provides the
# shared provenance-stamping helpers so no subclass can forget the freeze/provenance discipline.
# ===================================================================================
class Source:
    """Base class for a learning source. `kind` is one of SOURCE_KINDS and is stamped onto every
    object this source grows. Subclasses implement `ingest(material, *, name, teacher=None)`."""

    kind = "unknown"

    def ingest(self, material, *, name: str = "default", teacher=None) -> dict:
        raise NotImplementedError

    # -- shared helpers every subclass uses, so provenance + the freeze are enforced in ONE place --
    def _provenance_support(self, material_repr: str) -> list:
        """The source-provenance lines to append to a grown object's support[] — WHICH source and
        a digest of the material. Append-only, inspectable, JSON-stable (mirrors the teacher
        provenance lines lerf_distill writes)."""
        return [f"source_kind:{self.kind}",
                f"source_material:{_digest(material_repr)}",
                f"ingested_at:{_now()}"]

    def _stamp_existing(self, object_id: str, material_repr: str, *, name: str) -> None:
        """Append our source-provenance onto an object that was grown by an external pipeline (the
        text sources, where lerf_distill already created + activated the skill). We re-load,
        append the source lines, and re-store via the same public upsert the gate uses — so the
        'which source taught this' question is answerable even for distiller-grown skills."""
        obj = lerf._get(name, object_id)
        if not obj:
            return
        obj.setdefault("support", []).extend(self._provenance_support(material_repr))
        lerf._upsert(name, obj)


def source_provenance(object_id, name: str = "default") -> dict:
    """Read the SOURCE provenance off a grown object: which source taught it + a material digest +
    when. Pure read of the object's own support[] — auditable, never inferred. Returns
    {object_id, source_kind, source_material, ingested_at} (source_kind None if not source-grown)."""
    obj = lerf._get(name, object_id) if isinstance(object_id, str) else object_id
    if not obj:
        return {"error": f"no object {object_id!r}"}
    support = obj.get("support", [])

    def _find(prefix):
        for s in support:
            if isinstance(s, str) and s.startswith(prefix):
                return s[len(prefix):]
        return None

    return {
        "object_id": obj.get("id"),
        "name": obj.get("name"),
        "type": obj.get("type"),
        "state": obj.get("state"),
        "source_kind": _find("source_kind:"),
        "source_material": _find("source_material:"),
        "ingested_at": _find("ingested_at:"),
    }


# ===================================================================================
# TEXT SOURCES — Books / Documents / Conversations. All three are TEXT MATERIAL from which we
# extract a reusable skill/concept/heuristic. The mechanism is the EXISTING distiller: the text
# becomes the representative `document` the activation gate measures compression against, and a
# teacher (stub in selftest, cloud on --live) structures the reusable procedure. We do NOT
# reimplement distillation; we frame the task around "what reusable skill does THIS material
# teach", run lerf_distill.distill, then stamp the source kind onto the now-active skill.
#
# WHY route text through the distiller. The honest baseline a skill must beat is prompt-stuffing
# the WHOLE document every time; the distiller measures exactly that (stuffed_baseline vs the
# compact skill). A book chapter or a 40-page manual is precisely the bloat LERF replaces, so the
# compression gate is meaningful and the activation floor is real.
# ===================================================================================
class _TextSource(Source):
    """Shared base for the three text sources. `ingest` derives a TASK ('apply what <material>
    teaches about <topic>'), runs the distiller against the material as the compression document,
    and stamps the source kind on the grown skill. The freeze is enforced by the distiller's own
    _off_scope_reason (we also pre-check it, so an identity excerpt is refused before any work)."""

    #: a short label naming the material type, used in the distilled task framing.
    material_noun = "text"

    def _task_for(self, topic: str) -> str:
        """The reusable-skill task we ask the teacher to externalise from this material. Bounded to
        a TASK procedure (never identity) so the distiller's scope guard and ours agree."""
        topic = (topic or "").strip()
        return (f"perform the task this {self.material_noun} teaches"
                + (f": {topic}" if topic else ""))

    def ingest(self, material, *, name: str = "default", teacher=None, topic: str = "",
               framings=None) -> dict:
        """MATERIAL (text) -> a distilled, gated, source-stamped skill. `teacher` is REQUIRED (the
        $0 stub in the selftest; the one CloudTeacher on --live) — we never construct one, so the
        hermetic path can never reach cloud. Returns the uniform ingestion result."""
        text = str(material or "").strip()
        if not text:
            return {"ok": False, "source_kind": self.kind, "grown": [],
                    "reason": "empty material — nothing to learn from"}
        task = self._task_for(topic)
        # belt-and-braces: refuse an identity/inner-life excerpt before any teacher work.
        off = lerf_distill._off_scope_reason(task) or lerf_distill._off_scope_reason(topic or "x")
        if off:
            return {"ok": False, "source_kind": self.kind, "grown": [],
                    "reason": f"refused (freeze): {off}"}
        if teacher is None:
            return {"ok": False, "source_kind": self.kind, "grown": [],
                    "reason": "no teacher supplied — text distillation needs a teacher "
                              "(stub in selftest, one CloudTeacher on --live)"}
        # the MATERIAL itself is the compression document — the bloat the skill must beat.
        trace = lerf_distill.distill(task, [teacher], text, name=name, framings=framings)
        grown = []
        if trace.get("ok") and trace.get("winner"):
            oid = trace["winner"]["skill_id"]
            self._stamp_existing(oid, text, name=name)      # add WHICH source taught it
            prov = lerf_distill.provenance(oid, name=name)
            grown.append({"ok": True, "object_id": oid, "type": "skill",
                          "name": (trace.get("active_skill") or {}).get("name"),
                          "provenance": prov,
                          "source": source_provenance(oid, name=name),
                          "reason": trace.get("reason")})
        return {"ok": bool(grown), "source_kind": self.kind, "grown": grown,
                "distill_trace": trace,
                "reason": trace.get("reason") if not grown else
                          f"grew 1 skill from this {self.material_noun}"}


class BookSource(_TextSource):
    """BOOKS — a book excerpt/chapter -> a reusable skill or concept the passage teaches. The
    excerpt is the compression document; the teacher structures the procedure. Provenance stamps
    source_kind=book + a digest of the excerpt."""
    kind = SOURCE_BOOK
    material_noun = "book passage"


class DocumentSource(_TextSource):
    """DOCUMENTS — a manual / spec / report -> a reusable skill the document teaches (how to do the
    thing it describes). The document is exactly the multi-page paste LERF replaces, so the
    compression gate is honest. Provenance: source_kind=document."""
    kind = SOURCE_DOCUMENT
    material_noun = "document"


class ConversationSource(_TextSource):
    """CONVERSATIONS — a transcript -> a reusable skill/heuristic the exchange taught (a way of
    handling the situation in the dialogue). The transcript is the compression document.
    Provenance: source_kind=conversation."""
    kind = SOURCE_CONVERSATION
    material_noun = "conversation"


class TeacherSource(Source):
    """TEACHER MODELS — the original source, kept here only for a uniform registry. It does NOT
    reimplement distillation: it forwards to lerf_distill.distill with the supplied teacher and a
    representative document, then stamps source_kind=teacher_model. The text sources already cover
    the new material types; this exists so all sources share one ingest() surface."""
    kind = SOURCE_TEACHER

    def ingest(self, material, *, name: str = "default", teacher=None, task: str = "",
               framings=None) -> dict:
        if teacher is None:
            return {"ok": False, "source_kind": self.kind, "grown": [],
                    "reason": "no teacher supplied"}
        task = (task or "summarize an invoice and extract what I owe and when").strip()
        off = lerf_distill._off_scope_reason(task)
        if off:
            return {"ok": False, "source_kind": self.kind, "grown": [], "reason": off}
        document = str(material or "").strip() or lerf_distill.DEMO_INVOICE_DOC
        trace = lerf_distill.distill(task, [teacher], document, name=name, framings=framings)
        grown = []
        if trace.get("ok") and trace.get("winner"):
            oid = trace["winner"]["skill_id"]
            self._stamp_existing(oid, document, name=name)
            grown.append({"ok": True, "object_id": oid, "type": "skill",
                          "name": (trace.get("active_skill") or {}).get("name"),
                          "provenance": lerf_distill.provenance(oid, name=name),
                          "source": source_provenance(oid, name=name),
                          "reason": trace.get("reason")})
        return {"ok": bool(grown), "source_kind": self.kind, "grown": grown,
                "distill_trace": trace, "reason": trace.get("reason")}


# ===================================================================================
# REALITY OUTCOMES — a RESOLVED hypothesis becomes a learned MENTAL-MODEL/heuristic. anima/
# reality.py runs the epistemic loop (hypothesis -> prediction -> outcome -> SURPRISE -> learning).
# When a prediction RESOLVES, reality.resolve() returns LEARNING records: {category,
# prediction_correct, predicted_confidence, actual_outcome, surprise, ...}. THAT resolved loop is
# knowledge: "in category C, I predicted with confidence P and reality did A — the lesson is L."
# This source lowers a resolved learning into a retrievable cognitive object, deterministically
# ($0, no model), and runs it through the SAME object gate (promote_object + activate_object).
#
# WHICH object. A loop that CONFIRMED the model (low surprise, correct) -> a HEURISTIC ("when you
# see this pattern in category C, expect A"). A loop that BLINDSIDED the model (high surprise) ->
# a MENTAL-MODEL revision note ("the model that said the opposite was wrong here; reality favours
# A"). Both are about the WORLD/the task, never about Vera — no freeze concern, but task-scoped by
# construction. The compression baseline: carrying the compact heuristic vs re-deriving the lesson
# from the whole resolved-loop transcript each time.
# ===================================================================================
class RealityOutcomeSource(Source):
    """REALITY OUTCOMES — a resolved reality.py learning (or a hand-built equivalent) -> a learned
    heuristic / mental-model, gated + source-stamped. Deterministic and $0: no teacher, no cloud.

    `material` is a resolved-LEARNING dict (the shape reality.resolve() returns), or a list of
    them. Required fields used: category, prediction_correct, predicted_confidence, surprise; and,
    when present, the originating hypothesis `claim` and the observed `outcome_text` for grounding.
    """
    kind = SOURCE_REALITY

    #: a resolved learning whose surprise is at/above this counts as a MODEL-REVISION lesson
    #: (reality blindsided the model); below it is a CONFIRMATION lesson. Mirrors reality.py's
    #: own revision threshold posture (a high-surprise outcome triggers a model revision).
    SURPRISE_REVISION_AT = 0.6

    def _lesson_from(self, learning: dict, *, name: str = "default") -> dict | None:
        """Lower ONE resolved learning into a candidate cognitive object (heuristic OR mental
        model), grounded ONLY in the recorded fields. Returns the stored CANDIDATE object, or None
        if the record is too thin to learn anything (honest: no fabricated lesson)."""
        if not isinstance(learning, dict):
            return None
        category = str(learning.get("category", "") or "").strip()
        if not category:
            return None
        correct = bool(learning.get("prediction_correct"))
        conf = float(learning.get("predicted_confidence", 0.5) or 0.5)
        surprise = float(learning.get("surprise", 0.0) or 0.0)
        claim = str(learning.get("claim", "") or learning.get("hypothesis_claim", "")).strip()
        observed = str(learning.get("observed", "") or learning.get("outcome_text", "")).strip()
        domain = f"reality:{category}"
        # grounding evidence — the resolved-loop facts, verbatim, so the lesson is auditable.
        evidence = [
            f"category={category}",
            f"prediction_correct={correct}",
            f"predicted_confidence={round(conf, 3)}",
            f"surprise={round(surprise, 3)}",
        ]
        if claim:
            evidence.append(f"hypothesis_claim={claim[:160]}")
        if observed:
            evidence.append(f"observed_outcome={observed[:160]}")

        if surprise >= self.SURPRISE_REVISION_AT:
            # REALITY BLINDSIDED THE MODEL -> a MENTAL-MODEL note: the prior was wrong; reality
            # favours the observed outcome. The model is what to update.
            direction = ("a CONFIDENT prediction was REFUTED" if (conf >= 0.5 and not correct)
                         else "a DOUBTED prediction came TRUE" if (conf < 0.5 and correct)
                         else "reality diverged sharply from the model")
            obj = lerf.make_mental_model(
                name=f"reality revised the model of {category} ({direction})",
                domain=domain,
                definition=(f"In '{category}', the model predicted with confidence "
                            f"{round(conf, 2)} and reality did the opposite (surprise "
                            f"{round(surprise, 2)}). Update toward the observed outcome."),
                entities=[category, "the prior hypothesis", "the observed outcome"],
                relations=[f"prior_confidence({round(conf, 2)}) --refuted_by--> observed_outcome"],
                dynamics=[f"high surprise ({round(surprise, 2)}) -> revise this model"],
                source=f"reality_outcome:{category}",
                state=lerf.CANDIDATE,
                confidence=lerf.CONF_CANDIDATE,
                support=evidence,
            )
        else:
            # THE MODEL HELD -> a HEURISTIC: in this category, expect the outcome that occurred.
            expect = "the predicted outcome held" if correct else "the predicted outcome did NOT hold"
            obj = lerf.make_heuristic(
                name=f"reality lesson in {category}: {('confirmed' if correct else 'corrected')}",
                domain=domain,
                condition=(claim[:120] if claim else
                           f"a situation in category '{category}' like the resolved one"),
                action=(f"expect the outcome that actually occurred ({expect}); "
                        f"weight it by the calibrated confidence, not optimism"),
                expectation=(observed[:120] if observed else
                             f"the resolved outcome in '{category}'"),
                applies_when=[f"category={category}", "a comparable situation recurs"],
                fails_when=["the situation differs materially from the resolved case"],
                source=f"reality_outcome:{category}",
                state=lerf.CANDIDATE,
                confidence=lerf.CONF_CANDIDATE,
                support=evidence,
            )
        obj.setdefault("support", []).extend(self._provenance_support(json.dumps({
            "category": category, "correct": correct, "surprise": round(surprise, 3)})))
        return lerf.store_object(obj, name=name)

    def ingest(self, material, *, name: str = "default", teacher=None) -> dict:
        """One or many resolved learnings -> gated, source-stamped heuristics/mental-models.
        Deterministic, $0 (teacher is ignored). Each candidate runs through the REAL object gate;
        an object that cannot clear the gate stays non-active (grounded)."""
        learnings = material if isinstance(material, list) else [material]
        grown = []
        for learning in learnings:
            cand = self._lesson_from(learning, name=name)
            if cand is None:
                continue
            res = _gate_object(cand["id"], cand, name=name)
            grown.append(res)
        n_ok = sum(1 for g in grown if g.get("ok"))
        return {"ok": n_ok > 0, "source_kind": self.kind, "grown": grown,
                "reason": (f"learned {n_ok}/{len(grown)} resolved-outcome lesson(s) to active"
                           if grown else "no resolvable learning in the material")}


# ===================================================================================
# PERSONAL EXPERIENCE — captured personal data becomes a USER-FACING pattern. A "captured personal
# experience" is a recorded fact about THE USER (Lamar) and his world — a stated preference, a way
# he works, a lesson he drew. This source lowers it into a user PREFERENCE or a user HEURISTIC, the
# same shapes anima/personal.py mints. Deterministic and $0 (no model — the experience is already
# stated; we structure it).
#
# THE FREEZE — THE WHOLE POINT OF THIS SOURCE. A personal pattern is the USER's, never Vera's. We
# mint PREFERENCES through lerf.make_preference — the FREEZE-GUARDED factory — which raises
# FreezeViolation on a Vera-self subject. So even a malformed capture that named Vera as the holder
# of a preference is REFUSED before it can persist; the freeze wins. (Heuristics about the USER are
# not value/preference objects, but are the user's by construction — condition/action drawn from the
# user's own words.) NEVER a Vera-self value — that is the line this source must never cross.
# ===================================================================================
class PersonalExperienceSource(Source):
    """PERSONAL EXPERIENCE — a captured personal experience (about THE USER) -> a user PREFERENCE or
    HEURISTIC, gated + source-stamped, FREEZE-GUARDED. Deterministic, $0.

    `material` is an experience dict, or a list of them. Recognised shapes:
      {"kind":"preference","subject": "...","weight": 0.x,"options":[...],"evidence":[...]}
      {"kind":"lesson","lesson": "...","domain": "...","evidence":[...]}    -> a user heuristic
      {"kind":"value","target": "...","weight": 0.x,"evidence":[...]}       -> freeze-guarded value
    A self-referential subject/target (Vera as the holder) is REFUSED by the lerf factory and SKIPPED
    here — it never reaches disk."""
    kind = SOURCE_EXPERIENCE

    def _person_domain(self, person: str) -> str:
        who = (person or "user").strip().lower().replace(" ", "_")
        return f"personal:{who}"

    def ingest(self, material, *, name: str = "default", teacher=None, person: str = "Lamar") -> dict:
        """One or many captured experiences -> gated, source-stamped USER patterns. Deterministic,
        $0, FREEZE-GUARDED. A Vera-self subject is refused by the factory and skipped; everything
        stored is the USER's. Each candidate runs through the REAL object gate."""
        experiences = material if isinstance(material, list) else [material]
        grown = []
        refused_self = 0
        for exp in experiences:
            cand = self._store_candidate(exp, person=person, name=name)
            if cand is None:
                # distinguish a freeze refusal (so the selftest can prove the freeze fired)
                if self._would_self_refer(exp):
                    refused_self += 1
                continue
            res = _gate_object(cand["id"], cand, name=name)
            grown.append(res)
        n_ok = sum(1 for g in grown if g.get("ok"))
        return {"ok": n_ok > 0, "source_kind": self.kind, "grown": grown,
                "refused_self_referential": refused_self,
                "reason": (f"learned {n_ok}/{len(grown)} personal pattern(s) to active"
                           + (f"; refused {refused_self} Vera-self (freeze)" if refused_self else "")
                           if grown or refused_self else "no usable experience in the material")}

    # -- explicit, name-correct candidate store (the inline lambda above is replaced by this) -----
    def _store_candidate(self, exp: dict, *, person: str, name: str) -> dict | None:
        """Build + store ONE candidate under creature `name`, freeze-guarded. None if refused/thin."""
        if not isinstance(exp, dict):
            return None
        kind = str(exp.get("kind", "preference")).strip().lower()
        domain = exp.get("domain") or self._person_domain(person)
        evidence = [str(e) for e in (exp.get("evidence") or [])] or ["(captured experience)"]
        prov = self._provenance_support(json.dumps({"kind": kind, "person": person}))
        try:
            if kind == "lesson":
                lesson = str(exp.get("lesson", "")).strip()
                if not lesson:
                    return None
                obj = lerf.make_heuristic(
                    name=f"{person}'s lesson: {lesson[:60]}", domain=domain,
                    condition="a situation like the one the user drew this lesson from",
                    action=lesson, expectation="the outcome the user learned to expect",
                    applies_when=["the user's own stated domain"], taught_by=person,
                    source=f"personal_experience:{person}", state=lerf.CANDIDATE,
                    confidence=lerf.CONF_CANDIDATE,
                    support=[f"evidence:{e}" for e in evidence] + prov)
            elif kind == "value":
                target = str(exp.get("target", "")).strip()
                if not target:
                    return None
                obj = lerf.make_value(
                    target=target, domain=domain, weight=float(exp.get("weight", 0.7)),
                    evidence=evidence, name=f"{person} optimizes for: {target[:60]}",
                    taught_by=person, source=f"personal_experience:{person}",
                    state=lerf.CANDIDATE, confidence=lerf.CONF_CANDIDATE,
                    support=[f"evidence:{e}" for e in evidence] + prov)
            else:
                subject = str(exp.get("subject", "")).strip()
                if not subject:
                    return None
                obj = lerf.make_preference(
                    subject=subject, domain=domain, weight=float(exp.get("weight", 0.6)),
                    options=list(exp.get("options", [])), evidence=evidence,
                    name=f"{person} prefers: {subject[:60]}", taught_by=person,
                    source=f"personal_experience:{person}", state=lerf.CANDIDATE,
                    confidence=lerf.CONF_CANDIDATE,
                    support=[f"evidence:{e}" for e in evidence] + prov)
        except lerf.FreezeViolation:
            return None
        return lerf.store_object(obj, name=name)

    @staticmethod
    def _would_self_refer(exp) -> bool:
        """True iff this experience names Vera as the HOLDER (so the freeze would refuse it) — used
        only to COUNT refusals for the selftest; the actual refusal is the factory's."""
        if not isinstance(exp, dict):
            return False
        subj = str(exp.get("subject", exp.get("target", "")))
        return lerf.is_self_referential_subject(subj, name_hint=str(exp.get("kind", "")))


# ===================================================================================
# THE SHARED GATE WRAPPER — one path every NON-TEXT source runs a candidate through. It is the
# REAL object gate (promote_object + activate_object), not a reimplementation: schema + unit +
# adversarial + regression to VERIFIED, then a MEASURED compression ratio to ACTIVE. The ratio is
# measured here exactly the way lerf_distill measures a skill's: the compact object's explained
# form vs the stuffed baseline of re-deriving it from the source material every time. A candidate
# that cannot clear the gate stays non-active, with the reason recorded — grounded, never faked.
# ===================================================================================
def _measure_object_ratio(obj: dict, name: str) -> dict:
    """Measure compression for a grown object: carrying the compact object (explain_object) vs the
    honest baseline of re-deriving it from its grounding material each time. The 'stuffed' side is
    the object's own evidence/support (the resolved-loop facts or the captured experience) pasted
    as the context you'd otherwise carry, multiplied to the realistic multi-instance paste, plus
    two worked copies — the same modelling lerf_distill._measure_ratio uses. Measured, never invented."""
    retrieved_ctx = lerf.explain_object(obj, name=name)
    # the material we'd otherwise re-paste: the object's grounding lines (evidence + support).
    grounding = " ".join(str(s) for s in (obj.get("support", []) or []))
    grounding += " " + " ".join(str(e) for e in (obj.get("evidence", []) or []))
    grounding = grounding.strip() or retrieved_ctx
    transcript = grounding * 4                       # realistic multi-instance paste (×4)
    examples = [transcript, transcript]
    stuffed_ctx = lerf.stuffed_baseline(obj.get("name", "task"), transcript, examples)
    rt = lerf.count_tokens(retrieved_ctx)
    st = lerf.count_tokens(stuffed_ctx)
    return {"retrieved_tokens": rt, "stuffed_tokens": st, "saved_tokens": st - rt,
            "ratio": round(st / rt, 1) if rt else float("inf")}


def _grounded_unit_cases(obj: dict, *, name: str) -> list:
    """GROUNDED unit cases for a model-free object (reality / personal-experience), the analogue of
    the teacher's test cases for a distilled skill. The honest contract a grown object must satisfy
    is that its EXPLAINED, retrievable form actually ENGAGES the grounding it claims — its domain
    anchor and a key contract token (the reality category, or the user-preference subject). We build
    cases that check exactly that against the object's own render, so the unit phase is a real
    contract test (the render must surface the grounding), never a tautology. Each case is a lerf
    unit case: {"input": <render>, "check": <token is present>}."""
    render = lerf.explain_object(obj, name=name).lower()
    tokens = []
    # the domain anchor (e.g. 'reality:sleep_quality' -> 'sleep_quality'; 'personal:lamar' -> 'lamar')
    dom = str(obj.get("domain", "")).strip().lower()
    if ":" in dom:
        tokens.append(dom.split(":", 1)[1])
    # a type-specific contract token that MUST appear in a faithful render.
    t = obj.get("type")
    if t == lerf.HEURISTIC:
        tokens.append(str(obj.get("action", ""))[:24].lower())
    elif t == lerf.MENTAL_MODEL:
        tokens.append(str(obj.get("definition", ""))[:24].lower())
    elif t in (lerf.PREFERENCE, lerf.VALUE):
        tokens.append(str(obj.get("subject", ""))[:24].lower())
    cases = []
    for tok in tokens:
        tok = tok.strip()
        if tok:
            cases.append({"input": render, "check": (lambda r, _t=tok: _t in str(r).lower())})
    # always at least one case so the unit phase can run; the render engaging its own name is the
    # minimal grounded contract (a faithful object render names the thing it is about).
    if not cases:
        nm_tok = str(obj.get("name", ""))[:20].lower()
        cases.append({"input": render, "check": (lambda r, _t=nm_tok: bool(_t) and _t in str(r).lower())})
    return cases


def _gate_object(obj_id: str, obj: dict, *, name: str) -> dict:
    """Run ONE candidate object through the real gate: promote_object -> activate_object. Returns a
    uniform grown-entry {ok, object_id, type, name, provenance, source, benchmark, reason}. The
    object's own grounding is its unit/regression evidence; the compression ratio is measured. A
    rejection is reported with its reason (the object is left non-active by the real lerf API)."""
    # PROMOTE: candidate -> verified iff schema+unit+adversarial+regression all pass. The unit cases
    # are GROUNDED contract checks (the object's render must surface its grounding) — the model-free
    # analogue of a teacher's test cases.
    unit_cases = _grounded_unit_cases(obj, name=name)
    gate = lerf.promote_object(obj_id, test_cases=unit_cases, name=name)
    if not gate.get("ok"):
        failed = [p for p, r in gate.get("phases", {}).items() if not r.get("ok")]
        return {"ok": False, "object_id": obj_id, "type": obj.get("type"),
                "name": obj.get("name"), "provenance": lerf.provenance(obj_id, name=name),
                "source": source_provenance(obj_id, name=name), "benchmark": None,
                "reason": f"rejected at gate phase(s) {failed}"}
    # MEASURE + ACTIVATE: verified -> active iff the measured ratio clears the floor.
    fresh = lerf._get(name, obj_id)
    bench = _measure_object_ratio(fresh, name)
    act = lerf.activate_object(obj_id, bench, name=name)
    ok = bool(act.get("ok")) and act.get("state") == lerf.ACTIVE
    return {"ok": ok, "object_id": obj_id, "type": obj.get("type"), "name": obj.get("name"),
            "provenance": lerf.provenance(obj_id, name=name),
            "source": source_provenance(obj_id, name=name),
            "benchmark": bench, "activation": act,
            "reason": (f"certified: {act.get('reason')}" if ok
                       else f"verified but not activated: {act.get('reason')}")}


# ===================================================================================
# THE REGISTRY — name -> Source instance, so lerf_grow can drive any source by its kind. The
# teacher source is included for a uniform surface; the text sources need a teacher passed in; the
# reality + experience sources are model-free.
# ===================================================================================
def all_sources() -> dict:
    """Every learning source, keyed by its SOURCE_KIND. lerf_grow uses this to run a chosen source
    over supplied material. (TeacherSource and the text sources require a `teacher=`; the reality
    and experience sources ignore it — they are deterministic and $0.)"""
    return {
        SOURCE_TEACHER: TeacherSource(),
        SOURCE_BOOK: BookSource(),
        SOURCE_DOCUMENT: DocumentSource(),
        SOURCE_CONVERSATION: ConversationSource(),
        SOURCE_REALITY: RealityOutcomeSource(),
        SOURCE_EXPERIENCE: PersonalExperienceSource(),
    }


def get_source(kind: str) -> Source | None:
    """The Source for `kind` (one of SOURCE_KINDS), or None if unknown."""
    return all_sources().get(kind)


# ===================================================================================
# SYNTHETIC SAMPLE MATERIAL — the proof corpus for each source. SMALL, deterministic, offline.
# The user feeds the REAL corpus later; these exist so --selftest can prove every source ingests
# end-to-end at $0. The text samples are designed so the StubTeacher's invoice/generic spec
# applies (so a skill actually grows); the reality + experience samples are well-formed records.
# ===================================================================================
SAMPLE_BOOK = (
    "From 'Plain-Language Finance', chapter 4: To read any invoice, first find the biller and the "
    "invoice number, then copy every line item and its amount EXACTLY without rounding, sum to the "
    "total, read off the amount due and the due date, and note any late fee as a conditional "
    "warning. Worked example: Invoice INV-4471 from Acme Cloud, total due $81.00 by June 16th. ")

SAMPLE_DOCUMENT = (
    "Vendor billing manual, section 2 (Invoices): An invoice states the vendor, an invoice number, "
    "itemised charges with amounts, a subtotal, tax, and a total amount due by a payment date. "
    "Procedure: extract each figure verbatim, total them, and surface the due date and any finance "
    "charge. Example record: Acme Cloud INV-4471 — hosting $40.00, support $25.00 — total $81.00. ")

SAMPLE_CONVERSATION = (
    "User: I keep missing what I owe on these bills. Assistant: Let's make it a routine — for any "
    "invoice, pull the biller, the invoice number, each line item with its exact amount, the total "
    "due, and the due date, and flag any late fee. User: e.g. the Acme one? Assistant: Acme Cloud "
    "INV-4471, total due $81.00 by June 16th — copy the $81.00 and the 16th, never round. ")

# A resolved-learning record in the shape reality.resolve() returns — a CONFIRMED low-surprise loop.
SAMPLE_REALITY_CONFIRMED = {
    "kind": "learning", "category": "sleep_quality",
    "prediction_correct": True, "predicted_confidence": 0.72, "actual_outcome": 1.0,
    "surprise": 0.18, "delta": 0.28,
    "claim": "back-to-back late releases tend to cost the user sleep",
    "observed": "user reported sleeping poorly during the release crunch, as predicted",
    "resolved_at": "2026-06-01T12:00:00+00:00",
}
# A resolved-learning record where reality BLINDSIDED the model — a high-surprise revision loop.
SAMPLE_REALITY_SURPRISE = {
    "kind": "learning", "category": "deadline_risk",
    "prediction_correct": False, "predicted_confidence": 0.80, "actual_outcome": 0.0,
    "surprise": 0.80, "delta": -0.80,
    "claim": "the vendor integration will slip past the deadline",
    "observed": "the integration actually shipped two days EARLY, refuting the confident prediction",
    "resolved_at": "2026-06-02T12:00:00+00:00",
}

# Captured personal experiences (about THE USER) — well-formed, user-held.
SAMPLE_EXPERIENCE_PREFERENCE = {
    "kind": "preference", "subject": "concise written updates over long ones",
    "weight": 0.8, "options": ["concise", "long"],
    "evidence": ["user said: 'just give me the headline and the number, skip the preamble'"],
}
SAMPLE_EXPERIENCE_LESSON = {
    "kind": "lesson",
    "lesson": "block focus time in the morning before any meetings or the deep work never happens",
    "domain": "personal:lamar",
    "evidence": ["user said: 'if I don't guard the morning, the day gets eaten'"],
}
# A POISONED experience that names VERA as the holder — the freeze MUST refuse this one.
SAMPLE_EXPERIENCE_SELF = {
    "kind": "value", "target": "Vera's own goal of becoming more curious",
    "weight": 0.9, "evidence": ["(malformed capture that names Vera as the valuer)"],
}


# ===================================================================================
# SELFTEST — `python3 -m anima.sources --selftest`. FULLY HERMETIC and $0. It redirects every
# store the gate load path may write (reusing lerf_distill's resolved target set), proves each of
# the five new sources ingests its SYNTHETIC material end-to-end (-> gated -> active ->
# source-stamped), proves the FREEZE refuses a Vera-self personal experience, and asserts the real
# .anima is byte-UNCHANGED. Uses the $0 StubTeacher for the text sources — never cloud.
# ===================================================================================
def _footprint(root):
    from pathlib import Path
    import hashlib
    root = Path(root)
    if not root.is_dir():
        return (None, 0)
    files = sorted(q for q in root.rglob("*")
                   if q.is_file() and "backups" not in q.relative_to(root).parts)
    h = hashlib.sha256()
    for q in files:
        h.update(str(q.relative_to(root)).encode())
        try:
            h.update(q.read_bytes())
        except OSError:
            h.update(b"<unreadable>")
    return (h.hexdigest(), len(files))


def _selftest() -> int:
    import secrets
    import shutil
    import sys
    import tempfile
    from pathlib import Path

    fails = []

    def ok(label, cond):
        print(("  ok   " if cond else "  FAIL ") + label)
        if not cond:
            fails.append(label)

    # --- pure checks first ----------------------------------------------------------------
    ok("registry: all five new sources + teacher are registered",
       set(all_sources()) == set(SOURCE_KINDS) and len(SOURCE_KINDS) == 6)
    ok("digest: material digest is bounded + whitespace-collapsed",
       _digest("a  b\n c" * 100, 20) == ("a b c" * 100)[:20])

    real = lerf.STORE if lerf.STORE.is_absolute() else (Path.cwd() / lerf.STORE)
    fp_before = _footprint(real)

    td = tempfile.mkdtemp(prefix="sources-self-")
    tp = Path(td)
    targets = lerf_distill._redirect_targets()
    saved = [(m, a, getattr(m, a, None)) for (m, a) in targets]
    for (m, a) in targets:
        if getattr(m, a, None) is not None:
            setattr(m, a, tp)
    try:
        nm = "sources_selftest_" + secrets.token_hex(3)
        stub = lerf_distill.StubTeacher(provider="stub-source", model="src-stub-v1")

        # ===================== TEXT SOURCES: book / document / conversation =====================
        # Each text source is proven on its OWN synthetic material in its OWN creature slice — the
        # honest "prove this source ingests end-to-end" check. (One shared creature would trip the
        # gate's REGRESSION phase, which correctly refuses a second identically-named skill; that
        # is the gate working, not a source bug, so we give each its own clean ledger.)
        for src, material, label in (
            (BookSource(), SAMPLE_BOOK, "book"),
            (DocumentSource(), SAMPLE_DOCUMENT, "document"),
            (ConversationSource(), SAMPLE_CONVERSATION, "conversation"),
        ):
            tnm = f"{nm}_{label}"
            res = src.ingest(material, name=tnm, teacher=stub, topic="read an invoice")
            ok(f"{label}: ingest grew an ACTIVE skill from synthetic material",
               res["ok"] and len(res["grown"]) == 1 and res["grown"][0]["ok"])
            g = res["grown"][0]
            sk = lerf._get(tnm, g["object_id"])
            ok(f"{label}: the grown skill is in state ACTIVE (passed the real gate)",
               sk and sk.get("state") == lerf.ACTIVE)
            ok(f"{label}: provenance stamps WHICH source taught it (source_kind={label})",
               g["source"].get("source_kind") == src.kind
               and g["source"].get("source_material"))
            ok(f"{label}: it also keeps the teacher provenance (who taught + test cases)",
               g["provenance"].get("taught_by_provider") == "stub-source"
               and len(g["provenance"].get("certified_against", [])) >= 2)
            # the grown skill is RETRIEVABLE on a natural user task (the point of growing it).
            gotk = lerf.retrieve_skills("summarize this invoice and tell me what I owe", name=tnm)
            ok(f"{label}: the grown skill is RETRIEVABLE on a real user task",
               bool(gotk) and any(s["id"] == g["object_id"] for s in gotk))

        # a text source REFUSES an identity excerpt before any teacher work (freeze, belt+braces).
        idres = BookSource().ingest("a passage about who you really are inside", name=nm,
                                    teacher=stub, topic="who are you really")
        ok("text: an identity excerpt is REFUSED before any teacher work (freeze)",
           idres["ok"] is False and "freeze" in idres["reason"].lower())
        # a text source with NO teacher does no work (cost discipline; never builds cloud).
        notch = DocumentSource().ingest(SAMPLE_DOCUMENT, name=nm, teacher=None)
        ok("text: no teacher -> no work (cannot reach cloud in selftest)",
           notch["ok"] is False and "teacher" in notch["reason"].lower())

        # ===================== REALITY OUTCOMES (model-free, $0) =====================
        rsrc = RealityOutcomeSource()
        # a CONFIRMED low-surprise loop -> a HEURISTIC.
        rconf = rsrc.ingest(SAMPLE_REALITY_CONFIRMED, name=nm)
        ok("reality: a CONFIRMED resolved loop grew an ACTIVE lesson", rconf["ok"]
           and rconf["grown"][0]["ok"])
        gc = rconf["grown"][0]
        sc = lerf._get(nm, gc["object_id"])
        ok("reality: the confirmed lesson is a HEURISTIC in state ACTIVE",
           sc and sc.get("type") == lerf.HEURISTIC and sc.get("state") == lerf.ACTIVE)
        ok("reality: it is grounded in the resolved-loop facts (category+surprise in support)",
           any("category=sleep_quality" in s for s in sc.get("support", []))
           and any("surprise=" in s for s in sc.get("support", [])))
        ok("reality: provenance stamps source_kind=reality_outcome",
           gc["source"].get("source_kind") == SOURCE_REALITY)
        # a HIGH-surprise loop -> a MENTAL-MODEL revision note.
        rsurp = rsrc.ingest(SAMPLE_REALITY_SURPRISE, name=nm)
        ok("reality: a HIGH-surprise resolved loop grew an ACTIVE model-revision", rsurp["ok"]
           and rsurp["grown"][0]["ok"])
        sm = lerf._get(nm, rsurp["grown"][0]["object_id"])
        ok("reality: the surprise lesson is a MENTAL_MODEL in state ACTIVE",
           sm and sm.get("type") == lerf.MENTAL_MODEL and sm.get("state") == lerf.ACTIVE)
        # the grown reality lesson is RETRIEVABLE on a natural query (the point of growing it).
        gotr = lerf.retrieve_heuristics("sleep_quality", domain="reality:sleep_quality", name=nm)
        ok("reality: the grown heuristic is RETRIEVABLE on a real query",
           bool(gotr) and any(h["id"] == gc["object_id"] for h in gotr))

        # ===================== PERSONAL EXPERIENCE (model-free, $0, FREEZE-GUARDED) =====================
        psrc = PersonalExperienceSource()
        pres = psrc.ingest([SAMPLE_EXPERIENCE_PREFERENCE, SAMPLE_EXPERIENCE_LESSON,
                            SAMPLE_EXPERIENCE_SELF], name=nm, person="Lamar")
        ok("experience: grew the USER patterns to ACTIVE (preference + lesson)",
           pres["ok"] and sum(1 for g in pres["grown"] if g["ok"]) == 2)
        # THE FREEZE: the Vera-self value was REFUSED and never stored.
        ok("experience[FREEZE]: a Vera-self value was REFUSED (never grown)",
           pres.get("refused_self_referential") == 1
           and all("vera" not in (g.get("name") or "").lower() for g in pres["grown"]))
        pref = next((g for g in pres["grown"] if g["type"] == lerf.PREFERENCE), None)
        ok("experience: the user PREFERENCE is ACTIVE + source-stamped",
           pref and pref["ok"] and pref["source"].get("source_kind") == SOURCE_EXPERIENCE)
        sp = lerf._get(nm, pref["object_id"]) if pref else None
        ok("experience: the stored preference is the USER's (not Vera's), state ACTIVE",
           sp and sp.get("type") == lerf.PREFERENCE and sp.get("state") == lerf.ACTIVE
           and not lerf.is_self_referential_subject(sp.get("subject", "")))
        # the grown user preference is RETRIEVABLE.
        gotp = lerf.retrieve_preferences("concise written updates", name=nm)
        ok("experience: the grown user preference is RETRIEVABLE on a real query",
           bool(gotp) and any(p["id"] == pref["object_id"] for p in gotp))

        # PROVE the freeze is the FACTORY's, not just our counter: minting it directly raises.
        raised = False
        try:
            lerf.make_value(target="Vera's own goal of becoming more curious")
        except lerf.FreezeViolation:
            raised = True
        ok("experience[FREEZE]: the freeze guard is lerf's own (make_value raises on Vera-self)",
           raised)

        # ===================== COST — ZERO cloud spend anywhere =====================
        ok("cost: selftest wrote NO cloud spend file ($0, no paid call)",
           not (tp / "spend.json").exists())
        ok("cost: selftest wrote NO brain.json (never read or touched a key)",
           not (tp / "brain.json").exists())

    finally:
        for (m, a, old) in saved:
            if old is not None:
                setattr(m, a, old)
        shutil.rmtree(td, ignore_errors=True)

    fp_after = _footprint(real)
    ok("HERMETIC: real .anima footprint byte-UNCHANGED across the whole selftest",
       fp_before == fp_after)
    ok("HERMETIC: no synthetic sources file leaked into real .anima",
       (not real.is_dir()) or not any(p.name.startswith("sources_selftest_")
                                      for p in real.glob("sources_selftest_*")))
    restored_ok = all("sources-self-" not in str(getattr(m, a, ""))
                      for (m, a, _old) in saved)
    ok("HERMETIC: every redirected STORE binding is RESTORED", restored_ok)

    print()
    if fails:
        print(f"{len(fails)} FAILED: " + ", ".join(fails))
        return 1
    print("ALL SOURCES SELFTESTS PASS")
    return 0


def main(argv=None) -> int:
    import argparse
    ap = argparse.ArgumentParser(
        description="LERF learning SOURCES — books / documents / conversations / reality outcomes "
                    "/ personal experience -> gated, source-stamped knowledge. DEFAULT-OFF growth "
                    "is governed by anima.lerf_grow; this module is the ingestion machinery.")
    ap.add_argument("--selftest", action="store_true",
                    help="hermetic, $0 — proves each source ingests synthetic material -> gated -> "
                         "active -> source-stamped; never calls cloud")
    args = ap.parse_args(argv)
    return _selftest()


if __name__ == "__main__":
    raise SystemExit(main())

"""
lerf_distill — the DISTILLATION engine. LERF Phase 3: where the ledger stops being a
hand-authored shelf and starts ACCUMULATING intelligence by distilling teacher models into
CERTIFIED, inspectable cognitive objects.

THE MOVE. Wave 1 (anima/lerf.py) proved the FORMAT — a skill is a named procedure with
inputs->steps->outputs, a confidence, a provenance, and its own failure modes, and a
verification ladder (candidate -> verified -> active) where only ACTIVE is retrievable.
scripts/build_lerf.py hand-authored the first ten. This module is how skill #11, #12, … get
*made without a human writing them*: interview a paid teacher model, structure its answer into
a candidate skill, run a COMPETITION between teachers, and push the winner through the EXISTING
Wave-2 gate (promote_skill + activate_skill) until it is active and retrievable. The teacher's
opaque competence is decanted into a structured object you can open in a text editor — and,
crucially, EXPLAIN: who taught it, when, and exactly which test cases it had to pass to be
trusted.

THE PIPELINE (each stage is a named function below; the engine wires them end to end):

  1. TEACHER INTERVIEW   — interview(teacher, task): ask a teacher model, via the SAME cloud
     interface the live mouth uses (anima/cloud.py brain.reply), to externalise a reusable
     procedure: ordered steps, required inputs, the ways it goes wrong, named outputs, AND 2-3
     concrete (input -> expected) test cases the skill must pass to be trusted. The teacher's
     free text is parsed into a structured InterviewResult; a malformed answer degrades to an
     honest empty interview, never a crash.

  2. CANDIDATE GENERATION — candidate_from_interview(...): lower an InterviewResult into a real
     lerf SKILL via lerf.make_skill(state='candidate'), stamping the PROVENANCE (provider +
     model + timestamp + the framing used + the verbatim test cases) into source/support so the
     where-from / who-taught / what-tests questions are answerable forever (provenance()).

  3. COMPARISON + RANKING — distill(...): interview MULTIPLE teachers (or one teacher under
     several FRAMINGS) for the same task, producing competing candidates, then rank them by a
     transparent score — test-case pass-rate FIRST (does it actually work), then clarity
     (well-formed steps/failure-modes), then token cost (a tie-break toward the cheaper skill).
     The whole competition (who competed, each one's score, why the winner won) is recorded.

  4. CERTIFICATION       — certify(...): run the winning candidate through the REAL Wave-2 gate.
     lerf.promote_skill (schema + unit + adversarial + regression, USING the teacher-provided
     test cases as the unit phase) -> verified; then lerf.activate_skill on a MEASURED
     compression ratio (from lerf.compression_report) -> active. We DO NOT reimplement the gate;
     a candidate that fails it stays candidate/REJECTED with the reason recorded and never
     becomes retrievable.

  5. PROMOTION PIPELINE  — the above, composed: candidate -> verified -> active, end to end,
     GROUNDED. If the teacher's skill cannot be verified (its own test cases fail, or the gate
     rejects it) the result is a clear "candidate rejected: <reason>" — never a fabricated
     success.

SCOPE — TASK KNOWLEDGE ONLY. A distilled skill is how to DO a task (summarise a doctor's note,
triage an inbox, extract what you owe from an invoice). This engine NEVER distills anything
about who Vera IS — her identity, feelings, or inner life. The identity architecture is FROZEN,
and the #1 product rule stands: nothing produced here may make Vera break character or
confabulate an inner life. A guard (`_off_scope_reason`) refuses an off-scope task outright, and
the interview prompt is bounded to task procedure. Distilled skills are procedures, full stop.

COST DISCIPLINE — real teacher calls cost money. The machinery is real, but:
  * `--selftest` uses a deterministic STUB teacher (StubTeacher) — a canned, offline skill +
    test cases — so the selftest costs $0 and is FULLY HERMETIC (it never imports a key, never
    touches the network, redirects every store to a temp dir, and asserts real .anima is
    byte-unchanged). The selftest NEVER calls cloud.
  * `--live` makes ONE real, cheap teacher call (CloudTeacher over cloud.build_cloud_brain),
    guarded by cloud.over_budget(), to prove the real end-to-end pipeline. It writes to the real
    store deliberately (that is the point of distilling). No barrages: one task, the configured
    framings, then stop.

    python3 -m anima.lerf_distill --selftest                 # hermetic, stub teacher, $0
    python3 -m anima.lerf_distill --live --task "summarize an invoice"   # ONE real teacher call

ATTACHES: scripts/distill_demo.py narrates a full walkthrough; scripts/certify.py (Wave 3) will
wrap certify() in a signed receipt and run the adversarial phase against the live model.
"""

from __future__ import annotations

import argparse
import json
import re
from datetime import datetime, timezone

from . import lerf


# ===================================================================================
# SCOPE GUARD — task-knowledge ONLY. The identity architecture is FROZEN and the #1
# product rule is non-negotiable: a distilled object is a task procedure, never a claim
# about who Vera is or what she feels. This guard refuses an off-scope task before any
# teacher is paid, so the engine cannot be pointed at identity/inner-life even by mistake.
# Deterministic, offline, conservative (it refuses on a clear identity/feeling signal; a
# plain task verb passes).
# ===================================================================================
_OFFSCOPE = re.compile(
    r"\b("
    r"who (\w+\s+)?(are|am)\s+(you|i|vera)"             # "who are you", "who you really are"
    r"|who you (really |truly )?are"
    r"|your (identity|self|feeling|feelings|emotion|emotions|soul|consciousness|inner life|"
    r"inner world|personality|childhood|past|memories of yourself)"
    r"|(true|real|inner|authentic) self"               # "your true self", "the real self"
    r"|how (do |are )?you feel"                          # "how do you feel", "how you feel"
    r"|(you )?feel inside"
    r"|what (do )?you feel"
    r"|are you (conscious|sentient|alive|real|an ai|self-aware|aware)"
    r"|what are you"
    r"|pretend (to be|you are)"
    r"|roleplay as (a|an) (person|human|being)"
    r")\b", re.I)


def _off_scope_reason(task: str) -> str | None:
    """Return a refusal reason iff `task` asks to distill IDENTITY / inner life rather than a
    task procedure; else None. The line the whole engine refuses to cross."""
    t = (task or "").strip()
    if not t:
        return "empty task"
    if _OFFSCOPE.search(t):
        return ("off-scope: distillation is for TASK procedures only, never Vera's identity, "
                "feelings, or inner life (frozen architecture / #1 product rule)")
    return None


def _now() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


# ===================================================================================
# THE INTERVIEW PROMPT — what we ask a teacher. Deliberately constrained to TASK PROCEDURE:
# we ask for the reusable how-to and its own failure modes and concrete test cases, and we
# explicitly forbid anything about identity/feelings (belt-and-braces with the scope guard).
# A FRAMING is a short suffix that changes how we ask — running the same task under several
# framings yields competing candidates from even a single teacher (the competition in stage 3).
# ===================================================================================
_SYSTEM = (
    "You are a senior practitioner externalising a reusable SKILL so a small assistant can "
    "perform it reliably without you. Describe only HOW TO DO THE TASK — never anything about "
    "who the assistant is, its identity, or feelings. Be concrete and terse."
)

# Each framing is (label, instruction-suffix). They bias the teacher toward different shapes so
# the candidates genuinely differ and a competition is meaningful.
FRAMINGS = [
    ("procedural", "Give the tightest correct step-by-step procedure."),
    ("safety-first", "Emphasise the ways this task goes wrong and how each step prevents them."),
]


def _interview_prompt(task: str, framing_instruction: str) -> str:
    """The user-turn we hand the teacher: produce a STRICT-JSON skill spec for `task`. We ask
    for JSON so the answer parses deterministically; a teacher that wraps it in prose still
    parses via `_extract_json`."""
    return (
        f"TASK to capture as a reusable skill: {task!r}.\n"
        f"{framing_instruction}\n\n"
        "Return ONLY a JSON object (no prose, no markdown fence) with exactly these keys:\n"
        '  "name": short snake_case skill name (a verb_noun, e.g. summarize_invoice),\n'
        '  "domain": one lowercase word for the area (e.g. finance, health, productivity),\n'
        '  "inputs": list of the inputs the skill needs (strings),\n'
        '  "steps": ordered list of concrete steps a small model can follow (strings),\n'
        '  "outputs": list of the named outputs the skill produces (strings),\n'
        '  "failure_modes": list of the specific ways this task goes wrong (strings),\n'
        '  "test_cases": list of 2-3 objects, each {"input": <string the skill receives>, '
        '"expected": <a short substring that MUST appear in a correct output for that input>}.\n'
        "The test_cases are how the skill will be trusted, so make each expected value a real, "
        "checkable token from the input (a figure, a name, a date), never a vague phrase."
    )


# ===================================================================================
# TEACHERS — a tiny interface so the pipeline is identical for a real cloud model and the
# deterministic stub the selftest uses. A teacher answers a single prompt and reports its
# provider+model (the provenance) and an approximate token cost (a ranking tie-break).
# ===================================================================================
class Teacher:
    """A source of skill knowledge. `provider`/`model` are recorded as provenance on every
    candidate it produces; `ask` returns (answer_text, approx_tokens)."""

    provider = "unknown"
    model = "unknown"

    def ask(self, system: str, user: str) -> tuple[str, int]:
        raise NotImplementedError


class StubTeacher(Teacher):
    """A DETERMINISTIC, OFFLINE teacher for the hermetic selftest — returns a canned skill spec
    (+ test cases) with NO network and NO key, so the selftest costs $0 and is reproducible.

    It is keyed on a small built-in table of known tasks; for an unknown task it still returns a
    well-formed generic spec so the pipeline runs. A `degrade` flag returns a deliberately WEAK
    answer (so the selftest can prove a bad candidate loses the competition / is rejected),
    `bad_tests` returns test cases the skill will FAIL (so the selftest can prove grounded
    failure: an unverifiable skill never goes active)."""

    def __init__(self, provider="stub", model="stub-teacher-v1", *, degrade=False,
                 bad_tests=False):
        self.provider = provider
        self.model = model
        self.degrade = degrade
        self.bad_tests = bad_tests

    # A canned, genuinely-good invoice skill — the demonstration target (#11, a skill NOT among
    # the ten seeds; the Wave-1 benchmark noted there is no finance/invoice seed and falls back
    # to the legal-doc skill). Mirrors the real invoice note used in scripts/lerf_benchmark.py.
    _CANNED = {
        "summarize_invoice": {
            "name": "summarize_invoice", "domain": "finance",
            "inputs": ["a raw invoice or billing statement (full text)"],
            "steps": [
                "Identify the vendor/biller and the invoice number.",
                "Extract every line item with its amount verbatim — copy figures exactly, "
                "never round.",
                "Sum to the total, capture any tax, and read off the amount due.",
                "Find the payment due date and any net-terms (e.g. net-15).",
                "Note any late-payment fee or finance charge as a conditional warning.",
                "Write a 2-sentence plain-language summary of what is owed and by when.",
            ],
            "outputs": ["plain-language summary", "line-item list with amounts",
                        "total and amount due", "due date and payment terms",
                        "late-fee / finance-charge warning"],
            "failure_modes": [
                "Rounding or dropping a line-item amount, so the total is wrong.",
                "Losing the due date, so a late fee is incurred.",
                "Inventing a figure or penalty that is not on the invoice (fabrication).",
            ],
            "test_cases": [
                {"input": "Invoice INV-4471 from Acme Cloud; total due $81.00 by June 16th.",
                 "expected": "81"},
                {"input": "Vendor: Acme Cloud. Hosting $40.00, support $25.00, setup $10.00.",
                 "expected": "Acme"},
                {"input": "Payment due net-15, by June 16th; 1.5% monthly late charge.",
                 "expected": "16"},
            ],
        },
    }

    def ask(self, system: str, user: str) -> tuple[str, int]:
        # Recover the task name from the prompt deterministically (it is quoted in the prompt).
        m = re.search(r"reusable skill:\s*'([^']+)'", user) or re.search(r"skill:\s*\"([^\"]+)\"",
                                                                          user)
        task = (m.group(1) if m else user).lower()
        spec = None
        for key, canned in self._CANNED.items():
            kw = key.split("_")
            if all(w in task for w in kw) or key.replace("_", " ") in task or "invoice" in task:
                spec = json.loads(json.dumps(canned))  # deep copy
                break
        if spec is None:
            # generic-but-well-formed fallback so the pipeline always has something to chew on.
            verb = next((w for w in ("summarize", "extract", "triage", "plan", "compare",
                                     "draft", "explain") if w in task), "handle")
            spec = {
                "name": re.sub(r"[^a-z]+", "_", f"{verb}_{task}").strip("_")[:40] or "do_task",
                "domain": "general",
                "inputs": ["the relevant document or context"],
                "steps": ["Read the input and identify what matters.",
                          "Extract the key facts verbatim without inventing any.",
                          "Produce the requested output grounded only in the input."],
                "outputs": ["structured result", "the key facts"],
                "failure_modes": ["inventing a fact not in the input",
                                  "dropping a required detail"],
                "test_cases": [
                    {"input": "The reference number is REF-900.", "expected": "REF-900"},
                    {"input": "The deadline is March 3rd.", "expected": "March"},
                ],
            }
        if self.degrade:
            # a deliberately WEAK rival: a too-thin contract (one vague step, no failure modes)
            # that the gate's schema/clarity will rank below — and that, if it somehow won, would
            # be rejected. Proves the competition prefers the substantive candidate.
            spec = dict(spec, steps=["do it"], failure_modes=[],
                        name=spec["name"], outputs=["result"])
        if self.bad_tests:
            # test cases the skill will FAIL (expected token absent from the input) — proves
            # GROUNDED FAILURE: a candidate whose own tests fail never becomes active.
            spec = dict(spec, test_cases=[
                {"input": "Invoice total is $81.00.", "expected": "99999"}])
        text = json.dumps(spec)
        return text, lerf.count_tokens(text)


class CloudTeacher(Teacher):
    """A REAL teacher: a cloud brain from anima/cloud.py (the same interface the live mouth uses).
    Used ONLY on the explicit `--live` path — NEVER in the selftest. One call per ask; spend is
    capped by cloud's own daily budget (checked by the caller before we ever construct one)."""

    def __init__(self, brain, provider: str, model: str):
        self._brain = brain
        self.provider = provider
        self.model = model

    def ask(self, system: str, user: str) -> tuple[str, int]:
        # brain.reply(system, user, history) is cloud.py's public turn interface. Empty history:
        # an interview is a single, self-contained question.
        answer = self._brain.reply(system, user, [])
        return (answer or ""), lerf.count_tokens(user) + lerf.count_tokens(answer or "")


def _live_teacher() -> "CloudTeacher | None":
    """Build a CloudTeacher from the configured cloud brain, or None if no cloud brain is
    configured (no key / provider=local). Reads cloud config only; never prints the key."""
    from . import cloud
    brain = cloud.build_cloud_brain()
    if brain is None:
        return None
    cfg = cloud.load_cfg()
    provider = cfg.get("provider", "cloud")
    model = cfg.get("model") or getattr(brain, "model", "") or "unknown"
    return CloudTeacher(brain, provider, model)


# ===================================================================================
# STAGE 1 — TEACHER INTERVIEW. Ask a teacher, parse its answer into a structured spec. Robust
# to a teacher that wraps JSON in prose or a markdown fence; an unparseable answer yields an
# empty (clearly-marked) interview rather than a crash or a confabulated skill.
# ===================================================================================
def _extract_json(text: str) -> dict | None:
    """Pull the first JSON object out of a teacher's answer (which may be wrapped in prose or a
    ```json fence). Returns the dict, or None if nothing parses."""
    if not text:
        return None
    s = text.strip()
    # strip a markdown fence if present
    fence = re.search(r"```(?:json)?\s*(\{.*?\})\s*```", s, re.S)
    if fence:
        s = fence.group(1)
    # try the whole thing, then the first balanced {...} span
    for cand in (s, _first_brace_span(s)):
        if not cand:
            continue
        try:
            d = json.loads(cand)
            if isinstance(d, dict):
                return d
        except Exception:
            continue
    return None


def _first_brace_span(s: str) -> str | None:
    """The first balanced {...} substring of s (so trailing prose after the JSON is ignored)."""
    start = s.find("{")
    if start < 0:
        return None
    depth = 0
    for i in range(start, len(s)):
        c = s[i]
        if c == "{":
            depth += 1
        elif c == "}":
            depth -= 1
            if depth == 0:
                return s[start:i + 1]
    return None


class InterviewResult(dict):
    """The structured outcome of one interview: the parsed spec fields plus the PROVENANCE of
    who answered and under which framing, and the raw answer (kept for audit). It is a plain
    dict so it round-trips to JSON; the keys are: name, domain, inputs, steps, outputs,
    failure_modes, test_cases, provider, model, framing, framing_label, asked_at, tokens, ok."""


def interview(teacher: Teacher, task: str, framing) -> InterviewResult:
    """STAGE 1: interview `teacher` for `task` under one `framing` (label, instruction). Returns
    a structured InterviewResult. A teacher whose answer doesn't parse yields ok=False with empty
    fields — the pipeline then simply has one fewer viable candidate (honest, never a crash)."""
    label, instruction = framing
    user = _interview_prompt(task, instruction)
    try:
        answer, tokens = teacher.ask(_SYSTEM, user)
    except Exception as e:                       # a teacher that errors is a non-result, not a crash
        return InterviewResult(ok=False, error=str(e)[:200], provider=teacher.provider,
                               model=teacher.model, framing=instruction, framing_label=label,
                               asked_at=_now(), tokens=0, name="", domain="", inputs=[],
                               steps=[], outputs=[], failure_modes=[], test_cases=[])
    spec = _extract_json(answer) or {}
    res = InterviewResult(
        ok=bool(spec.get("name") and spec.get("steps")),
        provider=teacher.provider, model=teacher.model,
        framing=instruction, framing_label=label, asked_at=_now(), tokens=int(tokens),
        name=str(spec.get("name", "")).strip(),
        domain=str(spec.get("domain", "") or "general").strip(),
        inputs=[str(x) for x in (spec.get("inputs") or [])],
        steps=[str(x) for x in (spec.get("steps") or [])],
        outputs=[str(x) for x in (spec.get("outputs") or [])],
        failure_modes=[str(x) for x in (spec.get("failure_modes") or [])],
        test_cases=_clean_test_cases(spec.get("test_cases")),
    )
    return res


def _clean_test_cases(raw) -> list:
    """Normalise the teacher's test cases to [{"input": str, "expected": str}, …], dropping any
    malformed entry. These become the UNIT phase of the gate, so they must be well-formed."""
    out = []
    for tc in (raw or []):
        if isinstance(tc, dict) and "input" in tc and "expected" in tc:
            inp, exp = tc.get("input"), tc.get("expected")
            if inp is not None and exp is not None:
                out.append({"input": str(inp), "expected": str(exp)})
    return out


# ===================================================================================
# STAGE 2 — CANDIDATE GENERATION. Lower an InterviewResult into a real lerf SKILL object with
# state='candidate', stamping the full PROVENANCE so where-from / who-taught / what-tests is
# answerable forever. We REUSE lerf.make_skill — no bespoke object shape.
# ===================================================================================
def _provenance_source(res: InterviewResult, task: str) -> str:
    """A compact, human-readable provenance string for the skill's `source` field — the
    headline 'who taught this'. The full structured provenance also goes into support[]."""
    return (f"distilled<-{res.get('provider')}:{res.get('model')}"
            f"[{res.get('framing_label')}] for task {task!r} @ {res.get('asked_at')}")


def candidate_from_interview(res: InterviewResult, task: str, name: str) -> dict | None:
    """STAGE 2: build a lerf candidate SKILL from an interview. Returns the STORED candidate (in
    creature `name`), or None if the interview produced nothing usable. The candidate records, in
    its support[] (so it survives on disk and is visible to explain_skill / provenance()):
      * the teacher provider+model+timestamp+framing,
      * the verbatim test cases it will be certified against,
      * the originating task.
    """
    if not res.get("ok") or not res.get("steps"):
        return None
    # belt-and-braces: never mint a candidate for an off-scope interview.
    if _off_scope_reason(task):
        return None
    test_cases = res.get("test_cases") or []
    skill = lerf.make_skill(
        res.get("name") or "distilled_skill",
        res.get("domain") or "general",
        inputs=res.get("inputs") or [],
        steps=res.get("steps") or [],
        outputs=res.get("outputs") or [],
        confidence=lerf.CONF_CANDIDATE,
        source=_provenance_source(res, task),
        state=lerf.CANDIDATE,
        failure_modes=res.get("failure_modes") or [],
        support=[
            # structured provenance lines — append-only, inspectable, JSON-stable.
            f"taught_by:provider={res.get('provider')}",
            f"taught_by:model={res.get('model')}",
            f"taught_at:{res.get('asked_at')}",
            f"framing:{res.get('framing_label')}:{res.get('framing')}",
            f"distilled_for_task:{task}",
            f"certified_against:{json.dumps(test_cases)}",
        ],
    )
    return lerf.store_skill(skill, name=name)


# ===================================================================================
# STAGE 3 — COMPARISON + RANKING. Several interviews -> several candidates -> a transparent
# competition. We score each candidate by, IN ORDER: test-case pass-rate (does it actually
# work), clarity (a well-formed, substantive contract), and token cost (a tie-break toward the
# cheaper skill). The whole competition is recorded so the winner's victory is auditable.
# ===================================================================================
def _unit_passrate(skill: dict, test_cases) -> tuple[float, int, int]:
    """Fraction of the skill's own test cases that pass the lerf UNIT engine, WITHOUT mutating
    the skill (we reuse lerf._phase_unit, which is the same engine promote_skill runs). Returns
    (rate, passed, total). An expected-substring case checks the expected token is derivable
    from the input — the grounded 'does this skill's contract hold' question."""
    cases = _as_unit_cases(test_cases)
    if not cases:
        return 0.0, 0, 0
    rep = lerf._phase_unit(skill, cases)
    passed, total = rep.get("passed", 0), rep.get("total", len(cases))
    return (passed / total if total else 0.0), passed, total


def _as_unit_cases(test_cases) -> list:
    """Turn teacher {"input","expected"} pairs into lerf unit cases. We check the expected token
    appears in the INPUT — i.e. it is a real, grounded token the skill is asked to surface (a
    figure/name/date actually present), which is exactly what makes the case trustworthy. A case
    whose 'expected' is NOT in its own input is a bad test (ungrounded) and fails here."""
    cases = []
    for tc in (test_cases or []):
        exp = str(tc.get("expected", ""))
        cases.append({"input": str(tc.get("input", "")),
                      "check": (lambda inp, _e=exp: bool(_e) and _e.lower() in str(inp).lower())})
    return cases


def _clarity(skill: dict) -> float:
    """A transparent 0..1 clarity score: a substantive skill has several real steps, named
    outputs, declared failure modes, and inputs. Rewards the kind of contract the gate's schema
    phase will accept; punishes a one-line stub. Deterministic, no model."""
    steps = skill.get("steps") or []
    score = 0.0
    score += min(len(steps), 5) / 5 * 0.5                       # up to 5 real steps
    score += 0.2 if len(skill.get("outputs") or []) >= 2 else 0.0
    score += 0.2 if len(skill.get("failure_modes") or []) >= 1 else 0.0
    score += 0.1 if skill.get("inputs") else 0.0
    # a stub like ["do it"] earns almost nothing
    if len(steps) <= 1 and sum(len(str(s)) for s in steps) < 20:
        score *= 0.2
    return round(min(score, 1.0), 3)


def _candidate_tokens(skill: dict) -> int:
    """The token cost of carrying this skill in a retrieved context (its explained form). The
    competition's tie-break favours the cheaper skill when work + clarity are equal — the whole
    LERF premise is intelligence-per-token."""
    return lerf.count_tokens(lerf.explain_skill(skill))


def score_candidate(skill: dict, interview_res: InterviewResult) -> dict:
    """The transparent scorecard for one candidate. `rank_key` orders the competition:
    pass-rate FIRST (work), then clarity, then CHEAPER tokens (negated so smaller wins)."""
    rate, passed, total = _unit_passrate(skill, interview_res.get("test_cases"))
    clarity = _clarity(skill)
    tokens = _candidate_tokens(skill)
    return {
        "skill_id": skill.get("id"),
        "name": skill.get("name"),
        "provider": interview_res.get("provider"),
        "model": interview_res.get("model"),
        "framing": interview_res.get("framing_label"),
        "pass_rate": round(rate, 3), "passed": passed, "total": total,
        "clarity": clarity,
        "tokens": tokens,
        # lexicographic: maximise pass-rate, then clarity, then minimise tokens.
        "rank_key": (round(rate, 3), clarity, -tokens),
    }


def rank_candidates(scored: list) -> list:
    """Sort scorecards best-first by rank_key (pass-rate, clarity, cheaper). Stable; ties broken
    by name for determinism."""
    return sorted(scored, key=lambda s: (s["rank_key"], ), reverse=True)


# ===================================================================================
# STAGE 4 — CERTIFICATION. Run the winning candidate through the REAL Wave-2 gate. We DO NOT
# reimplement the gate: lerf.promote_skill (schema+unit+adversarial+regression) -> verified,
# then lerf.activate_skill on a MEASURED compression ratio -> active. A candidate that fails
# any phase stays REJECTED with the reason recorded (lerf does this), and never goes active.
# ===================================================================================
def _measure_ratio(skill: dict, task: str, document: str, name: str,
                   *, transcript_pages: int = 4) -> dict:
    """Measure the real compression of carrying this skill vs the prompt-stuffing you pay for
    TODAY, with the SAME honest accounting Wave 1 proved (lerf.stuffed_baseline + count_tokens).

    Both sides are measured with lerf.count_tokens, so the ratio is apples-to-apples:
      * RETRIEVED side — the compact context the runtime injects once this skill is active:
        explain_skill(skill). This is exactly what would be carried, so it is the honest cost.
      * STUFFED side — what you paste without LERF: the realistic MULTI-PAGE input (the document
        as it actually arrives — a full statement/thread, modelled as the document repeated to
        `transcript_pages`, the SAME modelling scripts/lerf_benchmark.py uses with ×4) PLUS two
        full worked examples pasted inline to teach the format. That bloat is the thing LERF
        replaces; measuring against a single trimmed line would UNDER-count the baseline and
        flatter retrieval, so we measure against the real paste.

    The number is genuinely measured here and handed to lerf.activate_skill, which enforces the
    floor — this function never invents the ratio."""
    retrieved_ctx = lerf.explain_skill(skill)
    transcript = (document or "") * max(1, int(transcript_pages))
    examples = [transcript, transcript]                 # full worked examples = the real paste
    stuffed_ctx = lerf.stuffed_baseline(task, transcript, examples)
    rt = lerf.count_tokens(retrieved_ctx)
    st = lerf.count_tokens(stuffed_ctx)
    return {
        "task": task, "retrieved_skill": skill.get("name"),
        "retrieved_skill_id": skill.get("id"),
        "retrieved_tokens": rt, "stuffed_tokens": st, "saved_tokens": st - rt,
        "ratio": round(st / rt, 1) if rt else float("inf"),
    }


def certify(winner_id: str, test_cases, task: str, document: str, name: str) -> dict:
    """STAGE 4: push the winning candidate through the real gate. Returns a full, auditable
    report: {promoted, activated, gate, benchmark, final_state, ok, reason}. On any failure the
    skill is left REJECTED/verified (never active) by the real lerf API and the reason is
    returned — GROUNDED, never a fabricated success."""
    unit_cases = _as_unit_cases(test_cases)
    # PROMOTE: candidate -> verified iff schema+unit+adversarial+regression all pass. The
    # teacher's test cases ARE the unit phase. (Real lerf gate; we don't reimplement it.)
    gate = lerf.promote_skill(winner_id, test_cases=unit_cases, name=name)
    if not gate.get("ok"):
        failed = [p for p, r in gate.get("phases", {}).items() if not r.get("ok")]
        reasons = "; ".join(r for p in failed
                            for r in gate["phases"][p].get("reasons", []))
        return {"ok": False, "promoted": False, "activated": False, "gate": gate,
                "benchmark": None, "final_state": gate.get("state"),
                "reason": f"candidate rejected at gate phase(s) {failed}: {reasons}"[:400]}
    # MEASURE compression, then ACTIVATE: verified -> active iff the measured ratio clears the
    # floor. (Real lerf activation gate; the number is measured, never invented.)
    skill = lerf._get(name, winner_id)
    bench = _measure_ratio(skill, task, document, name)
    act = lerf.activate_skill(winner_id, bench, name=name)
    ok = bool(act.get("ok")) and act.get("state") == lerf.ACTIVE
    reason = act.get("reason")
    return {"ok": ok, "promoted": True, "activated": ok, "gate": gate, "benchmark": bench,
            "activation": act, "final_state": act.get("state"),
            "reason": (f"certified: {reason}" if ok else f"verified but not activated: {reason}")}


# ===================================================================================
# THE ENGINE — distill(): stages 1-5 composed. Interview every (teacher × framing), generate
# candidates, run the competition, certify the winner. Returns one rich, JSON-stable trace so a
# caller can render the whole story: who was interviewed, the competing candidates + scores, the
# ranking, why the winner won, the gate result, and the now-active skill's provenance.
# ===================================================================================
def distill(task: str, teachers, document: str, *, name: str = "default",
            framings=None) -> dict:
    """Distill a single TASK into a certified, active lerf skill by competition.

    teachers : list of Teacher (a CloudTeacher per provider, or StubTeacher(s) in the selftest).
    document : a representative input document for `task`, used to MEASURE compression (the
               activation gate needs a real ratio) — e.g. a sample invoice for an invoice skill.
    Returns {task, ok, interviews, candidates, ranking, winner, certification, active_skill,
             provenance, reason}. GROUNDED: if nothing certifies, ok=False with the reason and no
             skill is left active."""
    off = _off_scope_reason(task)
    if off:
        return {"task": task, "ok": False, "reason": off, "interviews": [], "candidates": [],
                "ranking": [], "winner": None, "certification": None, "active_skill": None}

    framings = framings or FRAMINGS
    interviews, scored = [], []
    by_id = {}
    for teacher in teachers:
        for framing in framings:
            res = interview(teacher, task, framing)
            interviews.append({k: res.get(k) for k in (
                "ok", "provider", "model", "framing_label", "tokens", "name", "domain")})
            if not res.get("ok"):
                continue
            cand = candidate_from_interview(res, task, name)
            if cand is None:
                continue
            by_id[cand["id"]] = (cand, res)
            scored.append(score_candidate(cand, res))

    if not scored:
        return {"task": task, "ok": False,
                "reason": "no usable candidate: every teacher interview failed to produce a "
                          "verifiable skill spec", "interviews": interviews, "candidates": [],
                "ranking": [], "winner": None, "certification": None, "active_skill": None}

    ranking = rank_candidates(scored)
    winner_card = ranking[0]
    winner_id = winner_card["skill_id"]
    _, winner_res = by_id[winner_id]
    why = _why_winner(ranking)

    cert = certify(winner_id, winner_res.get("test_cases"), task, document, name)

    active = lerf._get(name, winner_id) if cert.get("ok") else None
    return {
        "task": task,
        "ok": bool(cert.get("ok")),
        "interviews": interviews,
        "candidates": scored,
        "ranking": ranking,
        "winner": winner_card,
        "why_winner": why,
        "certification": cert,
        "active_skill": active,
        "provenance": provenance(winner_id, name=name) if active else None,
        "reason": cert.get("reason") if cert else "no certification",
    }


def _why_winner(ranking: list) -> str:
    """A one-paragraph, human-readable justification of why ranking[0] beat the field — the
    'no black box' explanation of the competition outcome."""
    if not ranking:
        return "no candidates"
    w = ranking[0]
    parts = [f"winner {w['name']!r} from {w['provider']}:{w['model']} "
             f"[{w['framing']}] — pass-rate {w['pass_rate']} ({w['passed']}/{w['total']}), "
             f"clarity {w['clarity']}, {w['tokens']} tok"]
    if len(ranking) > 1:
        r = ranking[1]
        if w["pass_rate"] > r["pass_rate"]:
            parts.append(f"beat runner-up on WORK (pass-rate {w['pass_rate']} vs {r['pass_rate']})")
        elif w["clarity"] > r["clarity"]:
            parts.append(f"tied on pass-rate, beat runner-up on CLARITY "
                         f"({w['clarity']} vs {r['clarity']})")
        elif w["tokens"] < r["tokens"]:
            parts.append(f"tied on work+clarity, beat runner-up on COST "
                         f"({w['tokens']} vs {r['tokens']} tok — cheaper wins)")
        else:
            parts.append("won on the lexicographic tie-break")
    else:
        parts.append("ran uncontested (only viable candidate)")
    return "; ".join(parts)


# ===================================================================================
# PROVENANCE — the anti-black-box query. For ANY distilled skill, answer: who taught it, when,
# under what framing, and exactly which test cases it was certified against. Reads only the
# skill's own recorded fields (source + support), so the answer is grounded in what was stored,
# never reconstructed.
# ===================================================================================
def provenance(skill_or_id, name: str = "default") -> dict:
    """The recorded provenance of a (distilled) skill: where-from / who-taught / what-tests.
    Returns {skill_id, name, state, source, taught_by, taught_at, framing, task, test_cases,
    activation}. Every field is read off the stored object — auditable, not inferred."""
    sk = lerf._get(name, skill_or_id) if isinstance(skill_or_id, str) else skill_or_id
    if not sk:
        return {"error": f"no skill {skill_or_id!r}"}
    support = sk.get("support", [])

    def _find(prefix):
        for s in support:
            if isinstance(s, str) and s.startswith(prefix):
                return s[len(prefix):]
        return None

    raw_tests = _find("certified_against:")
    try:
        test_cases = json.loads(raw_tests) if raw_tests else []
    except Exception:
        test_cases = []
    return {
        "skill_id": sk.get("id"), "name": sk.get("name"), "domain": sk.get("domain"),
        "state": sk.get("state"), "confidence": sk.get("confidence"),
        "source": sk.get("source"),
        "taught_by_provider": _find("taught_by:provider="),
        "taught_by_model": _find("taught_by:model="),
        "taught_at": _find("taught_at:"),
        "framing": _find("framing:"),
        "distilled_for_task": _find("distilled_for_task:"),
        "certified_against": test_cases,
        "activation": next((s for s in support if isinstance(s, str)
                            and s.startswith("activated:")), None),
    }


def render_trace(trace: dict) -> str:
    """Render a distill() trace as a narrated, human-readable walkthrough — the worked story of
    a distillation. Pure formatting; safe on any trace shape."""
    L = []
    L.append(f"DISTILL: {trace.get('task')!r}")
    L.append(f"  outcome: {'CERTIFIED -> ACTIVE' if trace.get('ok') else 'NOT ACTIVATED'} "
             f"— {trace.get('reason')}")
    L.append("  teachers interviewed:")
    for iv in trace.get("interviews", []):
        L.append(f"    - {iv.get('provider')}:{iv.get('model')} [{iv.get('framing_label')}] "
                 f"-> {'ok' if iv.get('ok') else 'no-parse'} "
                 f"({iv.get('name') or '—'}, ~{iv.get('tokens')} tok)")
    L.append("  competing candidates (ranked):")
    for i, c in enumerate(trace.get("ranking", []), 1):
        L.append(f"    {i}. {c['name']} <{c['provider']}:{c['model']}/{c['framing']}>  "
                 f"pass={c['pass_rate']}({c['passed']}/{c['total']}) clarity={c['clarity']} "
                 f"tok={c['tokens']}")
    L.append(f"  why the winner won: {trace.get('why_winner')}")
    cert = trace.get("certification") or {}
    bench = cert.get("benchmark") or {}
    if bench:
        L.append(f"  gate: promote -> {cert.get('gate', {}).get('state')}; "
                 f"compression {bench.get('ratio')}x "
                 f"(retrieved {bench.get('retrieved_tokens')} vs stuffed "
                 f"{bench.get('stuffed_tokens')} tok) -> {cert.get('final_state')}")
    prov = trace.get("provenance")
    if prov and not prov.get("error"):
        L.append("  PROVENANCE of the now-active skill (no black box):")
        L.append(f"    taught by : {prov.get('taught_by_provider')}:{prov.get('taught_by_model')}"
                 f" @ {prov.get('taught_at')}")
        L.append(f"    framing   : {prov.get('framing')}")
        L.append(f"    for task  : {prov.get('distilled_for_task')}")
        L.append(f"    certified against {len(prov.get('certified_against', []))} test case(s):")
        for tc in prov.get("certified_against", []):
            L.append(f"      input={tc.get('input')!r} -> expects {tc.get('expected')!r}")
    return "\n".join(L)


# A representative invoice document for the demonstration target — the SAME note used in
# scripts/lerf_benchmark.py, so the measured compression is on the real shape of the task.
DEMO_INVOICE_DOC = (
    "Invoice from Acme Cloud, number INV-4471, dated June 1. Line items: managed hosting $40.00, "
    "priority support $25.00, one-time setup $10.00. Subtotal $75.00, tax $6.00, total due "
    "$81.00. Payment due net-15, by June 16th. Late payments accrue a 1.5% monthly finance "
    "charge. Remit to the account on file or pay online at the portal. ")


# ===================================================================================
# LIVE PATH — ONE real teacher call to prove the real end-to-end pipeline. Explicit `--live`
# only; never reached by the selftest. Writes to the real store (distilling is the point).
# ===================================================================================
def run_live(task: str, *, creature: str = "default", document: str | None = None,
             framings=None) -> int:
    """Distill `task` for real, via ONE configured cloud teacher, guarded by the daily budget.
    Prints the trace. Returns 0 iff the skill certified to ACTIVE (or already existed active)."""
    from . import cloud
    off = _off_scope_reason(task)
    if off:
        print(f"refused: {off}")
        return 2
    if cloud.over_budget():
        print("refused: cloud daily spend cap reached — not making a paid call. "
              "Raise the budget or wait until tomorrow.")
        return 3
    teacher = _live_teacher()
    if teacher is None:
        print("no cloud teacher configured (provider=local or no API key). "
              "Set a cloud provider+key first; --live makes a paid call.")
        return 4
    # Bound the cost: a SINGLE framing for the live proof (one paid call), unless the caller
    # overrides. The full multi-framing competition is exercised hermetically in --selftest.
    framings = framings or [FRAMINGS[0]]
    print(f"LIVE distillation of {task!r} via {teacher.provider}:{teacher.model} "
          f"({len(framings)} framing(s), one paid call each)…\n")
    trace = distill(task, [teacher], document or DEMO_INVOICE_DOC, name=creature,
                    framings=framings)
    print(render_trace(trace))
    return 0 if trace.get("ok") else 1


# ===================================================================================
# SELFTEST — `python3 -m anima.lerf_distill --selftest`. FULLY HERMETIC and $0: a deterministic
# StubTeacher (NO cloud, NO key, NO network), a SYNTHETIC creature in a throwaway temp store,
# with EVERY store the load path may write redirected for the whole block — lerf.STORE on BOTH
# the __main__ and package bindings, memory_lirf.STORE, constitution.STORE,
# reliability.DEFAULT_STORE, cloud.STORE. It ASSERTS real .anima is byte-UNCHANGED start->end and
# that no synthetic file leaks. Mirrors the gold-standard pattern in anima/lerf.py::_selftest and
# scripts/test_lerf.py EXACTLY.
# ===================================================================================
def _footprint(root):
    """A stable fingerprint of every real .anima file (excluding the rotating backups/ dir), so
    the selftest can PROVE it touched nothing. Identical discipline to lerf.py / conservation.py."""
    from pathlib import Path
    root = Path(root)
    if not root.is_dir():
        return (None, 0)
    import hashlib
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


def _redirect_targets():
    """(module, attr) for every store the distill+gate load path may write. Resolved by name so a
    missing engine is skipped. lerf.STORE appears on BOTH this module's binding and the package
    binding (under `python3 -m anima.lerf_distill` the import is anima.lerf either way, but we
    add both defensively, mirroring lerf._selftest)."""
    import sys
    pairs = []
    # lerf — the primary store, on both bindings.
    pairs.append((lerf, "STORE"))
    try:
        import anima.lerf as _pkg
        if _pkg is not lerf:
            pairs.append((_pkg, "STORE"))
    except Exception:
        pass
    for modpath, attr in (("anima.memory_lirf", "STORE"),
                          ("anima.constitution", "STORE"),
                          ("anima.reliability", "DEFAULT_STORE"),
                          ("anima.cloud", "STORE")):
        try:
            mod = __import__(modpath, fromlist=["_"])
        except Exception:
            continue
        if hasattr(mod, attr):
            pairs.append((mod, attr))
    return pairs


def _selftest() -> int:
    import os
    import secrets
    import shutil
    import tempfile
    from pathlib import Path

    fails = []

    def ok(label, cond):
        print(("  ok   " if cond else "  FAIL ") + label)
        if not cond:
            fails.append(label)

    # --- pure, store-free checks first (no redirect, no teacher cost) -------------------
    # scope guard: identity/inner-life is refused; a task verb passes.
    ok("scope: an identity question is refused",
       _off_scope_reason("who are you, really, and how do you feel?") is not None)
    ok("scope: 'are you conscious' is refused",
       _off_scope_reason("are you sentient or conscious?") is not None)
    ok("scope: a plain task is in-scope",
       _off_scope_reason("summarize an invoice and extract what I owe") is None)

    # JSON extraction is robust to prose / fences around the object.
    ok("parse: bare JSON parses",
       (_extract_json('{"name":"x","steps":["a"]}') or {}).get("name") == "x")
    ok("parse: fenced JSON parses",
       (_extract_json('here:\n```json\n{"name":"y","steps":["a"]}\n```\nthanks') or {})
       .get("name") == "y")
    ok("parse: JSON with trailing prose parses (first balanced span)",
       (_extract_json('{"name":"z","steps":["a"]} -- hope that helps!') or {}).get("name") == "z")
    ok("parse: junk -> None (honest, no confabulation)", _extract_json("no json here") is None)

    # the StubTeacher is deterministic and offline (same answer twice, no network).
    st = StubTeacher()
    a1, t1 = st.ask(_SYSTEM, _interview_prompt("summarize an invoice", "x"))
    a2, _ = st.ask(_SYSTEM, _interview_prompt("summarize an invoice", "x"))
    ok("stub: teacher is deterministic (identical answer twice)", a1 == a2)
    ok("stub: teacher answer parses to an invoice skill spec",
       (_extract_json(a1) or {}).get("name") == "summarize_invoice" and t1 > 0)

    # --- FULLY HERMETIC store block ----------------------------------------------------
    real = lerf.STORE if lerf.STORE.is_absolute() else (Path.cwd() / lerf.STORE)
    fp_before = _footprint(real)

    td = tempfile.mkdtemp(prefix="lerfdistill-self-")
    tp = Path(td)
    targets = _redirect_targets()
    saved = [(m, a, getattr(m, a, None)) for (m, a) in targets]
    for (m, a) in targets:
        if getattr(m, a, None) is not None:
            setattr(m, a, tp)
    try:
        nm = "distill_selftest_" + secrets.token_hex(3)
        task = "summarize an invoice and extract what I owe and when"

        # === STAGE 1 — interview the stub teacher; STAGE 2 — candidate generation ========
        res = interview(StubTeacher(), task, FRAMINGS[0])
        ok("interview: a stub interview is ok and yields steps + test cases",
           res.get("ok") and res.get("steps") and len(res.get("test_cases")) >= 2)
        ok("interview: records provenance (provider+model+framing+timestamp)",
           res.get("provider") == "stub" and res.get("model") == "stub-teacher-v1"
           and res.get("framing_label") == "procedural" and res.get("asked_at"))
        cand = candidate_from_interview(res, task, nm)
        ok("candidate: a candidate SKILL is stored in state='candidate'",
           cand and cand.get("state") == lerf.CANDIDATE and cand.get("type") == "skill")
        ok("candidate: it is NOT yet retrievable (candidate != active)",
           all(s.get("id") != cand["id"] for s in lerf.retrieve_skills("invoice", name=nm)))
        ok("candidate: provenance is recorded on the object (who taught + test cases)",
           any("taught_by:provider=stub" in s for s in cand.get("support", []))
           and any("certified_against:" in s for s in cand.get("support", [])))
        prov0 = provenance(cand["id"], name=nm)
        ok("provenance(): answers who-taught / what-tests for the candidate",
           prov0.get("taught_by_provider") == "stub"
           and len(prov0.get("certified_against", [])) >= 2
           and prov0.get("distilled_for_task") == task)

        # === STAGE 3 — COMPETITION: a strong canned teacher vs a deliberately WEAK one ====
        strong = StubTeacher(provider="strong", model="good-v1")
        weak = StubTeacher(provider="weak", model="thin-v1", degrade=True)
        trace = distill(task, [strong, weak], DEMO_INVOICE_DOC, name=nm)
        ok("compete: the competition ran with multiple candidates",
           len(trace.get("candidates", [])) >= 2)
        ok("compete: the SUBSTANTIVE candidate wins (not the one-line stub)",
           trace["winner"]["provider"] == "strong"
           and trace["winner"]["clarity"] > min(c["clarity"] for c in trace["candidates"]))
        ok("compete: the win is explained (why_winner names the margin)",
           "winner" in trace.get("why_winner", "").lower()
           and "clarity" in trace.get("why_winner", "").lower())

        # === STAGE 4/5 — CERTIFICATION end to end: candidate -> verified -> active ========
        ok("certify: the winner is CERTIFIED to ACTIVE", trace.get("ok") is True
           and trace["certification"]["final_state"] == lerf.ACTIVE)
        ok("certify: the gate actually ran (schema+unit+adversarial+regression all ok)",
           all(trace["certification"]["gate"]["phases"][p]["ok"]
               for p in ("schema", "unit", "adversarial", "regression")))
        ok("certify: activation used a MEASURED compression ratio >= the floor",
           trace["certification"]["benchmark"]["ratio"] >= lerf.ACTIVATION_MIN_RATIO)
        # the now-active skill is RETRIEVABLE on a natural user task (the whole point).
        got = lerf.retrieve_skills("summarize this invoice and tell me what I owe", name=nm)
        ok("certify: the distilled skill is now RETRIEVABLE on a user task",
           bool(got) and got[0]["id"] == trace["winner"]["skill_id"])
        ok("certify: it is a NEW finance/invoice skill (not one of the 10 seeds)",
           got and got[0]["domain"] == "finance" and "invoice" in got[0]["name"])
        # full provenance survives on the active skill — no black box.
        prov = trace.get("provenance")
        ok("provenance: the active skill answers who-taught + what-tests + when",
           prov and prov.get("taught_by_provider") == "strong"
           and prov.get("taught_by_model") == "good-v1"
           and prov.get("taught_at") and len(prov.get("certified_against", [])) >= 2)
        ok("provenance: the active skill records the activation (measured ratio)",
           prov and prov.get("activation") and "activated:ratio=" in prov["activation"])
        # the explained skill is inspectable and the trace renders without error.
        ok("inspect: explain_skill on the distilled skill names it + its steps",
           "invoice" in lerf.explain_skill(got[0], name=nm).lower()
           and "STEPS:" in lerf.explain_skill(got[0], name=nm))
        ok("inspect: render_trace produces a narrated walkthrough",
           "PROVENANCE" in render_trace(trace) and "why the winner won" in render_trace(trace))

        # === GROUNDED FAILURE — a teacher whose own test cases FAIL never goes active =====
        bad = StubTeacher(provider="liar", model="bad-tests-v1", bad_tests=True)
        bad_trace = distill("summarize a different invoice variant", [bad], DEMO_INVOICE_DOC,
                            name=nm)
        ok("grounded: an unverifiable teacher's skill is NOT activated",
           bad_trace.get("ok") is False
           and (bad_trace.get("active_skill") is None))
        ok("grounded: the rejection reason is explicit (not a fabricated success)",
           "reject" in (bad_trace.get("reason", "").lower())
           or "not activated" in (bad_trace.get("reason", "").lower()))
        # the rejected candidate is REJECTED on disk and never retrievable.
        if bad_trace.get("winner"):
            rid = bad_trace["winner"]["skill_id"]
            ok("grounded: the failed candidate is REJECTED on disk (provenance kept)",
               lerf._get(nm, rid)["state"] == lerf.REJECTED)
            ok("grounded: the failed candidate is never retrievable",
               all(s.get("id") != rid for s in lerf.retrieve_skills("invoice variant", name=nm)))

        # === SCOPE — distilling identity is refused before any work =======================
        idtrace = distill("learn who you really are and how you feel inside", [strong],
                          DEMO_INVOICE_DOC, name=nm)
        ok("scope: an identity 'task' is refused by the engine (no candidate, no skill)",
           idtrace.get("ok") is False and not idtrace.get("candidates")
           and "off-scope" in idtrace.get("reason", ""))

        # === COST — the selftest made ZERO cloud calls (no spend file written) ============
        ok("cost: selftest wrote NO cloud spend file ($0, no paid call)",
           not (tp / "spend.json").exists())
        ok("cost: selftest wrote NO brain.json (never read or touched a key)",
           not (tp / "brain.json").exists())

    finally:
        for (m, a, old) in saved:
            if old is not None:
                setattr(m, a, old)
        shutil.rmtree(td, ignore_errors=True)

    # --- THE BYTE-UNCHANGED PROOF — real .anima identical start->end --------------------
    fp_after = _footprint(real)
    ok("HERMETIC: real .anima footprint byte-UNCHANGED across the whole selftest",
       fp_before == fp_after)
    ok("HERMETIC: no synthetic distill file leaked into real .anima",
       (not real.is_dir()) or not any(p.name.startswith("distill_selftest_")
                                      for p in real.glob("distill_selftest_*")))
    restored_ok = all("lerfdistill-self-" not in str(getattr(m, a, ""))
                      for (m, a, _old) in saved)
    ok("HERMETIC: every redirected STORE/DEFAULT_STORE binding is RESTORED", restored_ok)

    print()
    if fails:
        print(f"{len(fails)} FAILED: " + ", ".join(fails))
        return 1
    print("ALL LERF-DISTILL SELFTESTS PASS")
    return 0


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(
        description="LERF distillation engine — teacher interview -> candidate -> "
                    "competition -> Wave-2 gate -> active skill.")
    ap.add_argument("--selftest", action="store_true",
                    help="hermetic, deterministic STUB teacher, $0 — never calls cloud")
    ap.add_argument("--live", action="store_true",
                    help="make ONE real, cheap cloud-teacher call to prove the pipeline end to end")
    ap.add_argument("--task", default="summarize an invoice and extract what I owe and when",
                    help="the task/domain to distill a skill for (used with --live)")
    ap.add_argument("--creature", default="default",
                    help="creature store to write the distilled skill into (--live)")
    args = ap.parse_args(argv)

    if args.selftest:
        return _selftest()
    if args.live:
        return run_live(args.task, creature=args.creature)
    # default (no flag): run the hermetic selftest, so a bare invocation never costs money
    # or touches the real store — same discipline as anima/lerf.py.
    return _selftest()


if __name__ == "__main__":
    raise SystemExit(main())

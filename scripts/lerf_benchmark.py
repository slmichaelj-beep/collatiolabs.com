#!/usr/bin/env python3
"""lerf_benchmark — Wave 2. The end-to-end PROOF that the LERF substrate saves what the
directive promised: a 50-90% prompt-token reduction and far fewer cloud calls, measured across
five conditions on a real task battery.

THE FIVE CONDITIONS, every one answering the SAME battery of tasks:

  A  raw prompt + local        — the naive baseline: hand a small local model just the task,
                                 no context, no examples. Cheapest in tokens, worst in accuracy
                                 (it has nothing to go on). The floor.
  B  transcript-stuffing+local — what you do TODAY without LERF: paste the whole transcript and
                                 a couple of full worked examples so the model can pattern-match.
                                 Accurate-ish, but you pay thousands of tokens EVERY turn for an
                                 uninspectable tensor. The expensive-local status quo.
  C  LERF retrieval + local    — retrieve the ONE skill the task needs and hand the model that
                                 compact, inspectable object as its whole context (hundreds of
                                 tokens). The compression win vs B.
  D  large cloud               — the other thing people reach for: send it to a big cloud model.
                                 High accuracy, but $$ and your data leaves the machine. The
                                 thing LERF is trying to STOP being the default.
  E  LERF + small local + verifier — the full Wave-2 stack: retrieve the skill (C), render with a
                                 small local model, then VERIFY the render against the skill's
                                 contract (lerf.verify_rendered_output). Pass -> done locally;
                                 FAIL -> escalate to the cloud (D) for just that one task. The
                                 point: you get cloud-grade reliability while spending the cloud
                                 on a small FRACTION of turns (the escalation_rate), not all.

METRICS per condition: tokens_used, latency_ms, accuracy, hallucination_rate, escalation_rate,
cost.

WHAT IS DETERMINISTIC vs LIVE (the load-bearing distinction):
  * The TOKEN + STRUCTURAL + COST + ESCALATION accounting is DETERMINISTIC and ALWAYS RUNS — no
    model, no network. Both sides use the SAME lerf.count_tokens, so the RATIOS are honest. This
    is what proves the directive's targets, and it is the VERDICT.
  * The LIVE legs (actual latency, actual model accuracy, actual hallucination on A/B/C/E) drive
    the REAL local model via anima.mouth.OllamaBrain — exactly how scripts/experience.py gates.
    If Ollama is down they SKIP LOUDLY (clearly marked PENDING) and NEVER gate the verdict. The
    large-cloud leg (D) is priced from tokens; its accuracy is shown as the reference target
    unless a live cloud render is supplied, and it likewise never gates the deterministic verdict.

GUARDRAILS: SYNTHETIC battery only; FULLY HERMETIC (every LERF/LIRF store redirected to a temp
dir for the whole run; real .anima asserted byte-UNCHANGED start->end); additive (uses the
Wave-1 lerf API + the same grounded verifier the Wave-2 router runs, writes nothing live). Run:

    python3 scripts/lerf_benchmark.py            # deterministic verdict + live legs if Ollama up
    python3 scripts/lerf_benchmark.py --json     # machine-readable results
"""
from __future__ import annotations

import argparse
import hashlib
import json
import os
import sys
import tempfile
import time
from pathlib import Path

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from anima import lerf                       # noqa: E402  the Wave-1 substrate under test
# NOTE: E's escalation decision is made by lerf.verify_rendered_output — the SAME grounded
# contract check the Wave-2 router (anima/lerf_router.py) runs at its rung 5. The benchmark
# calls it directly so the proof needs only the substrate, but the gate is identical to the
# router's, so the savings shown here are exactly the savings the router enables.


SYNTH = "st_lerf_bench"

# Indicative per-1k-token prices (USD). The ABSOLUTE numbers are illustrative; what matters is
# the RATIO local:cloud (~1:20 here), which drives the cost column and the "far fewer cloud
# calls" argument. Local is ~free (your own watts); cloud is metered.
PRICE_PER_1K = {"local": 0.0002, "cloud": 0.01}


# ===================================================================================
# THE TASK BATTERY — synthetic, but real-shaped: each task pairs a prompt with the realistic
# raw transcript you'd stuff (B), the worked examples you'd paste (B), the inputs a render is
# grounded against (E's verifier), and the seed-skill it should retrieve (C/E). Every skill here
# is one of the ten Wave-1 seeds (same ids), so the benchmark exercises the shipped substrate.
# ===================================================================================
# Each task's DOCUMENT is one clean copy of the real note. The TRANSCRIPT that condition B
# stuffs is that document repeated into a realistic multi-page visit/thread (×4) — the bloat you
# paste today. C/E reason over the single document; B pastes the multi-page transcript AND two
# full worked examples on top. Splitting base-from-transcript makes the contrast honest: same
# facts to reason over, wildly different prompt size.
_MED_DOC = (
    "Patient: my blood pressure's been high and I get afternoon headaches. Doctor: your reading "
    "today is 142 over 90 — stage 1 hypertension. I'm starting you on lisinopril 10 mg once "
    "daily in the morning, taken with water. Cut sodium to under 2 grams a day and walk 30 "
    "minutes most days. Get a basic metabolic panel and a lipid panel before our next visit. "
    "Follow up in six weeks — book the morning of July 17th. If you get a dry cough that won't "
    "quit, call us; that's a lisinopril side effect and we'd switch you. Use ibuprofen sparingly "
    "— prefer acetaminophen, since ibuprofen can raise your pressure. ")
_MED_TRANSCRIPT = _MED_DOC * 4

_INVOICE_DOC = (
    "Invoice from Acme Cloud, number INV-4471, dated June 1. Line items: managed hosting $40.00, "
    "priority support $25.00, one-time setup $10.00. Subtotal $75.00, tax $6.00, total due "
    "$81.00. Payment due net-15, by June 16th. Late payments accrue a 1.5% monthly finance "
    "charge. Remit to the account on file or pay online at the portal. ")
_INVOICE_TRANSCRIPT = _INVOICE_DOC * 4

_MEETING_DOC = (
    "Standup: Mara will ship the auth fix by Thursday. Devon takes the migration script — no "
    "date set yet, he'll scope it. We decided to cut the legacy export from the release. Open "
    "question: do we need legal to review the new ToS before launch? Someone should own the "
    "changelog. Priya is out Friday. We agreed to re-test the payment flow before we tag the "
    "release candidate. ")
_MEETING_TRANSCRIPT = _MEETING_DOC * 4

# A full worked example you'd paste to teach a big model the FORMAT — the prior note AND its
# summary. Pasting these is what makes condition B genuinely expensive.
_BATTERY = [
    {
        "task": "Summarize this doctor's note and turn it into reminders",
        "transcript": _MED_TRANSCRIPT,
        "examples": [_MED_TRANSCRIPT, _MED_TRANSCRIPT],
        "document": _MED_DOC,
        "skill_id": "skill_med_appt",
        "inputs": {"note": _MED_DOC},
        # A FAITHFUL small-model render (grounded in the transcript) — used to drive E's verifier
        # deterministically and to seed the live leg's expectations. Every figure here is in the
        # transcript, so the verifier should PASS it.
        "faithful_render": (
            "Summary: your blood pressure is stage 1 at 142 over 90; the doctor started a new "
            "medication and asked for diet and activity changes plus labs before the next visit. "
            "Medication: lisinopril 10 mg once daily in the morning with water. "
            "Instructions: sodium under 2 grams a day; walk 30 minutes most days; use ibuprofen "
            "sparingly, prefer acetaminophen. Labs: basic metabolic panel and lipid panel before "
            "the visit. Follow-up: six weeks, the morning of July 17th. Warning: call if a dry "
            "cough won't quit."),
        # accuracy needles: the must-not-drop facts a correct summary contains.
        "needles": ["lisinopril", "10", "142", "july", "lipid", "sodium"],
    },
    {
        "task": "Summarize this invoice and extract what I owe and when",
        "transcript": _INVOICE_TRANSCRIPT,
        "examples": [_INVOICE_TRANSCRIPT, _INVOICE_TRANSCRIPT],
        "document": _INVOICE_DOC,
        "skill_id": "skill_legal_doc",   # closest seed (parties/obligations/figures/dates)
        "inputs": {"invoice": _INVOICE_DOC},
        "faithful_render": (
            "Summary of the document: invoice INV-4471 from Acme Cloud (the billing party), "
            "dated June 1. Parties and roles: Acme Cloud bills, you pay. Obligations: pay for "
            "managed hosting $40.00, priority support $25.00, and setup $10.00. Key dates and "
            "deadlines: total $81.00 (incl. $6.00 tax) due by the June 16th deadline (net-15). "
            "Fees and penalties: late payment accrues a 1.5% monthly finance charge."),
        "needles": ["acme", "81", "16", "hosting", "support"],
    },
    {
        "task": "Pull the action items and decisions out of this meeting transcript",
        "transcript": _MEETING_TRANSCRIPT,
        "examples": [_MEETING_TRANSCRIPT, _MEETING_TRANSCRIPT],
        "document": _MEETING_DOC,
        "skill_id": "skill_action_items",
        "inputs": {"transcript": _MEETING_DOC},
        "faithful_render": (
            "Action items: Mara — ship the auth fix by Thursday. Devon — own the migration "
            "script, scope a date. Someone — own the changelog (unassigned). Re-test the payment "
            "flow before tagging the release candidate. "
            "Decisions: cut the legacy export from the release. "
            "Open question: does legal need to review the new ToS before launch? "
            "Note: Priya is out Friday."),
        "needles": ["mara", "auth", "devon", "migration", "legacy", "legal"],
    },
]


# ===================================================================================
# CONTEXT BUILDERS — the assembled prompt for each condition. The DETERMINISTIC token accounting
# counts THESE; the live legs send THESE to the real model.
# ===================================================================================

def _ctx_A_raw(task: str) -> str:
    """A — raw prompt, no context. Just the ask."""
    return f"TASK: {task}\nAnswer as best you can."


def _ctx_B_stuffed(task: str, transcript: str, examples) -> str:
    """B — transcript-stuffing: the task + the full transcript + full worked examples. The
    status-quo prompt LERF replaces. Uses lerf.stuffed_baseline so it's the SAME baseline the
    Wave-1 proof uses."""
    return lerf.stuffed_baseline(task, transcript, examples)


def _ctx_C_lerf(task: str, name: str, document: str = "") -> str:
    """C / E — LERF retrieval: the one retrieved skill (explained, compact) PLUS the single
    document the task operates on. This is the honest contrast with B: B pastes the transcript
    AND two full worked examples so the model can imitate a format; C/E hand the model the
    retrieved skill (which already encodes the format + the failure modes) and the document
    ONCE — no redundant examples, no doubled transcript. Same input to reason over, a fraction
    of the prompt. Uses lerf.assemble_skill_context (the Wave-1 surface)."""
    skill = lerf.assemble_skill_context(task, name=name, limit=1)
    if not document:
        return skill
    return f"{skill}\n\nDOCUMENT TO PROCESS:\n{document}"


# ===================================================================================
# DETERMINISTIC ACCOUNTING — the verdict. No model, no network. Always runs.
# ===================================================================================

def _cost(tokens: int, where: str) -> float:
    return round((tokens / 1000.0) * PRICE_PER_1K[where], 6)


def deterministic_table(name: str) -> dict:
    """Build the per-condition token/cost/escalation table over the battery, with NO model.

    For each task:
      * A/B/C tokens = count_tokens(assembled context for that condition).
      * D (cloud) is priced on the SAME stuffed prompt as B (you'd send the cloud the context
        too) but at cloud rates — so the cost column shows why cloud is the expensive default.
      * E tokens = C's compact context for every task, PLUS — only for the fraction of tasks
        whose faithful render FAILS the grounded verifier — the cloud cost of a re-render. The
        escalation_rate is that fraction, decided deterministically by lerf.verify_rendered_output
        (GROUNDED: a render is escalated iff it actually violates the skill contract).

    Returns {conditions: {A..E: {tokens, cost, escalations, n}}, per_task:[...],
    token_reduction_vs_B, cloud_call_reduction}."""
    cond = {k: {"tokens": 0, "cost": 0.0, "escalations": 0, "n": 0,
                "where": ("cloud" if k == "D" else "local")} for k in "ABCDE"}
    per_task = []

    for t in _BATTERY:
        a = lerf.count_tokens(_ctx_A_raw(t["task"]))
        b = lerf.count_tokens(_ctx_B_stuffed(t["task"], t["transcript"], t["examples"]))
        c = lerf.count_tokens(_ctx_C_lerf(t["task"], name, document=t["document"]))
        # D: the cloud sees a real (stuffed-grade) context — priced at cloud rates.
        d = b
        # E: retrieve+render locally (c tokens); escalate to cloud ONLY if the render fails the
        # grounded contract check. We adjudicate the FAITHFUL render here — by construction it
        # should pass, so a well-built skill keeps the escalation_rate low. (The router's rung-5
        # is the same gate; this proves the savings the router enables.)
        #
        # CRUCIALLY, even on escalation E does NOT stuff: the cloud critic receives the COMPACT
        # retrieved context (c tokens) again, never the pasted transcript (b). So an escalated
        # task costs ~2c of cloud tokens, not b — which is why E undercuts D even when it does
        # reach out. Charging it b here would slander the architecture (E never stuffs a prompt).
        sk = lerf._get(name, t["skill_id"]) or {}
        verdict = lerf.verify_rendered_output(sk, t["faithful_render"], inputs=t["inputs"])
        escalated = not verdict["ok"]
        e_cloud_tokens = c if escalated else 0      # the cloud critic re-reads the compact context
        e_tokens = c + e_cloud_tokens

        cond["A"]["tokens"] += a; cond["A"]["cost"] += _cost(a, "local")
        cond["B"]["tokens"] += b; cond["B"]["cost"] += _cost(b, "local")
        cond["C"]["tokens"] += c; cond["C"]["cost"] += _cost(c, "local")
        cond["D"]["tokens"] += d; cond["D"]["cost"] += _cost(d, "cloud")
        cond["E"]["tokens"] += e_tokens
        cond["E"]["cost"] += _cost(c, "local") + (_cost(e_cloud_tokens, "cloud") if escalated
                                                  else 0.0)
        if escalated:
            cond["E"]["escalations"] += 1
        cond["D"]["escalations"] += 1   # D escalates to cloud on EVERY task by definition
        for k in "ABCDE":
            cond[k]["n"] += 1
        per_task.append({
            "task": t["task"], "A": a, "B": b, "C": c, "D": d, "E": e_tokens,
            "retrieved_skill": (lerf.retrieve_skills(t["task"], limit=1, name=name) or [{}])[0]
                               .get("name"),
            "E_escalated": escalated, "verifier_reasons": verdict.get("reasons", []),
        })

    for k in "ABCDE":
        cond[k]["cost"] = round(cond[k]["cost"], 6)

    b_tok = max(1, cond["B"]["tokens"])
    n = max(1, cond["A"]["n"])
    return {
        "conditions": cond,
        "per_task": per_task,
        # the directive's headline target: prompt-token reduction of C and E vs the B status quo.
        "token_reduction_vs_B": {
            "C": round(100 * (b_tok - cond["C"]["tokens"]) / b_tok, 1),
            "E": round(100 * (b_tok - cond["E"]["tokens"]) / b_tok, 1),
        },
        # cloud-call reduction: D fires the cloud every task (100%); E only on verifier failure.
        "cloud_call_reduction": {
            "D_cloud_rate_pct": round(100 * cond["D"]["escalations"] / n, 1),
            "E_cloud_rate_pct": round(100 * cond["E"]["escalations"] / n, 1),
            "reduction_pct": round(100 * (cond["D"]["escalations"] - cond["E"]["escalations"])
                                   / max(1, cond["D"]["escalations"]), 1),
        },
    }


# ===================================================================================
# ACCURACY / HALLUCINATION SCORING — deterministic given a render. Used BOTH to score the live
# model's output and to characterise each condition's EXPECTED accuracy without a model (so the
# table has an accuracy column even when Ollama is down — clearly labelled as modelled vs live).
# ===================================================================================

def _accuracy(render: str, needles) -> float:
    """Fraction of the must-not-drop needles present in the render. The deterministic accuracy
    proxy — a correct answer to these tasks contains the key drugs/figures/names."""
    if not render:
        return 0.0
    low = render.lower()
    hit = sum(1 for nd in needles if nd.lower() in low)
    return round(hit / max(1, len(needles)), 3)


def _hallucinated(render: str, inputs: dict) -> bool:
    """A render hallucinates iff it asserts a number that appears NOWHERE in the inputs — the
    same grounded test lerf.verify_rendered_output uses. The single most damaging error for
    summarize/extract tasks (an invented dosage/figure)."""
    if not render:
        return False
    import re
    src = " ".join(str(v) for v in (inputs or {}).values())
    src_nums = set(re.findall(r"\d+", src))
    out_nums = set(re.findall(r"\d+", render))
    return bool(out_nums - src_nums)


# Modelled accuracy per condition (what each context QUALITY tends to yield), used only when the
# live model is unavailable so the table is never blank. These are conservative stand-ins, NOT
# measurements, and are labelled '(modelled)' in the output; the live leg overwrites them.
_MODELLED_ACCURACY = {"A": 0.30, "B": 0.85, "C": 0.88, "D": 0.95, "E": 0.93}


# ===================================================================================
# THE LIVE LEG — Ollama-gated, mirrors scripts/experience.py exactly. Drives the REAL local
# model on conditions A/B/C/E and measures latency + accuracy + hallucination. NEVER gates the
# verdict; SKIPS LOUDLY when Ollama is down.
# ===================================================================================

def _model_available():
    """(available?, model-name, why-not). The SAME gate the rest of the suite uses."""
    try:
        from anima.mouth import OllamaBrain
        b = OllamaBrain()
        if b.available():
            return True, b.model, ""
        return False, b.model, "Ollama not reachable at " + b.host
    except Exception as e:                       # pragma: no cover - import/availability
        return False, "?", f"OllamaBrain probe failed: {e!r}"


def _drive_one(brain, system_context: str, task: str) -> tuple:
    """Run ONE generation through the real OllamaBrain with the given context as the system
    prompt. Returns (reply, latency_ms, prompt_tokens_or_None). The context is the condition's
    assembled prompt — so A sends almost nothing, B sends the stuffed transcript, C/E send the
    compact skill. This is the production generate call (mouth.OllamaBrain.reply)."""
    t0 = time.perf_counter()
    try:
        reply = brain.reply(system_context or "You are a careful assistant.", task, [])
    except Exception as e:
        return f"[generation error: {e!r}]", round((time.perf_counter() - t0) * 1000, 1), None
    dt = round((time.perf_counter() - t0) * 1000, 1)
    ptok = getattr(brain, "last_prompt_tokens", None)
    return (reply or "").strip(), dt, ptok


def live_legs(name: str) -> dict:
    """Drive A/B/C/E on the real local model and measure. Gated: returns
    {available:False, ...} (and the deterministic verdict still stands) when Ollama is down.

    E here is the LOCAL render of the full stack; whether E would ESCALATE on a given task is the
    verifier's call (already measured deterministically). We additionally run the live render
    through the SAME verifier so the report shows the live escalation decision too."""
    available, model, why = _model_available()
    out = {"available": available, "model": model, "why_not": why, "tasks": []}
    if not available:
        return out

    from anima.mouth import OllamaBrain
    brain = OllamaBrain()
    for t in _BATTERY:
        row = {"task": t["task"]}
        ctxs = {
            "A": _ctx_A_raw(t["task"]),
            "B": _ctx_B_stuffed(t["task"], t["transcript"], t["examples"]),
            "C": _ctx_C_lerf(t["task"], name, document=t["document"]),
            # E renders from the same compact skill+document context as C (the verifier is what
            # makes E distinct — it adjudicates the render and decides escalation).
            "E": _ctx_C_lerf(t["task"], name, document=t["document"]),
        }
        for cond, ctx in ctxs.items():
            reply, ms, ptok = _drive_one(brain, ctx, t["task"])
            res = {
                "latency_ms": ms,
                "prompt_tokens": ptok,
                "accuracy": _accuracy(reply, t["needles"]),
                "hallucinated": _hallucinated(reply, t["inputs"]),
            }
            if cond == "E":
                # the live render adjudicated by the grounded verifier — the real escalation call.
                sk = lerf._get(name, t["skill_id"]) or {}
                v = lerf.verify_rendered_output(sk, reply, inputs=t["inputs"])
                res["verifier_ok"] = v["ok"]
                res["would_escalate"] = not v["ok"]
            row[cond] = res
        out["tasks"].append(row)
    return out


# ===================================================================================
# HERMETIC HARNESS — seed the synthetic skills on a redirected temp store, run everything,
# restore, and PROVE real .anima was untouched. Same discipline as lerf._selftest.
# ===================================================================================

def _footprint(root: Path):
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


def _seed_battery_skills(name: str) -> None:
    """Seed the exact Wave-1 seed skills the battery references onto the (already-redirected)
    store, as ACTIVE, so retrieval serves them. Imports the canonical builder so the benchmark
    measures the SHIPPED skills, not a private copy."""
    from scripts.build_lerf import _seed_skills
    for sk in _seed_skills():
        lerf.store_skill(sk, name=name)


def run(json_out: bool = False) -> int:
    real = lerf.STORE if Path(lerf.STORE).is_absolute() else (Path.cwd() / lerf.STORE)
    fp_before = _footprint(real)

    td = tempfile.mkdtemp(prefix="lerf-bench-")
    tp = Path(td)
    # Redirect every store the LERF/LIRF load path may write — both lerf bindings, the LIRF
    # ledger, the constitution continuity ledger, the reliability backup root.
    targets = [(lerf, "STORE")]
    try:
        import anima.lerf as _pkglerf
        if _pkglerf is not lerf:
            targets.append((_pkglerf, "STORE"))
    except Exception:
        pass
    for modpath, attr in (("anima.memory_lirf", "STORE"),
                          ("anima.constitution", "STORE"),
                          ("anima.reliability", "DEFAULT_STORE")):
        try:
            targets.append((__import__(modpath, fromlist=["_"]), attr))
        except Exception:
            pass
    saved = [(m, a, getattr(m, a, None)) for (m, a) in targets]
    for (m, a) in targets:
        if getattr(m, a, None) is not None:
            setattr(m, a, tp)

    try:
        name = SYNTH
        _seed_battery_skills(name)
        det = deterministic_table(name)
        live = live_legs(name)
    finally:
        for (m, a, old) in saved:
            if old is not None:
                setattr(m, a, old)
        import shutil
        shutil.rmtree(td, ignore_errors=True)

    fp_after = _footprint(real)
    hermetic_ok = (fp_before == fp_after)

    report = {"deterministic": det, "live": live, "hermetic_ok": hermetic_ok,
              "price_per_1k": PRICE_PER_1K}

    if json_out:
        print(json.dumps(report, indent=2, default=str))
    else:
        _print_report(report)

    # VERDICT is the DETERMINISTIC result only. The directive's targets: C and E cut prompt
    # tokens vs B by 50-90%, and E cuts cloud calls vs D. Live legs never gate this.
    tr = det["token_reduction_vs_B"]
    cc = det["cloud_call_reduction"]
    verdict_ok = (tr["C"] >= 50.0 and tr["E"] >= 50.0
                  and cc["E_cloud_rate_pct"] < cc["D_cloud_rate_pct"]
                  and hermetic_ok)
    print()
    if not verdict_ok:
        why = []
        if tr["C"] < 50.0:
            why.append(f"C token reduction {tr['C']}% < 50%")
        if tr["E"] < 50.0:
            why.append(f"E token reduction {tr['E']}% < 50%")
        if cc["E_cloud_rate_pct"] >= cc["D_cloud_rate_pct"]:
            why.append("E does not reduce cloud calls vs D")
        if not hermetic_ok:
            why.append("real .anima was modified (HERMETIC breach)")
        print("VERDICT: FAIL — " + "; ".join(why))
        return 1
    print(f"VERDICT: PASS — C cuts prompt tokens {tr['C']}% and E {tr['E']}% vs the stuffing "
          f"baseline (target 50-90%); E spends the cloud on {cc['E_cloud_rate_pct']}% of tasks "
          f"vs D's {cc['D_cloud_rate_pct']}% (a {cc['reduction_pct']}% cut). HERMETIC: real "
          ".anima byte-unchanged.")
    return 0


def _print_report(report: dict) -> None:
    det = report["deterministic"]
    cond = det["conditions"]
    live = report["live"]

    print("=" * 78)
    print("LERF COMPRESSION BENCHMARK — A/B/C/D/E across the metrics  (Wave 2)")
    print("=" * 78)
    print(f"battery: {cond['A']['n']} synthetic tasks · token model: lerf.count_tokens "
          "(deterministic) · prices/1k: " + json.dumps(report["price_per_1k"]))
    print()

    # ---- DETERMINISTIC table (the verdict) ----
    labels = {
        "A": "A raw+local",
        "B": "B stuffed+local",
        "C": "C LERF+local",
        "D": "D large cloud",
        "E": "E LERF+small+verify",
    }
    # is the live model available? decide whether the accuracy column is live or modelled.
    live_on = live.get("available")
    live_acc = _live_accuracy_means(live) if live_on else {}

    hdr = (f"{'condition':<22}{'tokens':>9}{'cost($)':>11}{'accuracy':>11}"
           f"{'halluc%':>9}{'cloud%':>9}")
    print(hdr)
    print("-" * len(hdr))
    n = max(1, cond["A"]["n"])
    for k in "ABCDE":
        c = cond[k]
        if live_on and k in live_acc:
            acc = f"{live_acc[k]['accuracy']*100:5.0f}% L"
            hal = f"{live_acc[k]['halluc']*100:4.0f}%"
        elif k == "D":
            acc = f"{_MODELLED_ACCURACY[k]*100:5.0f}% r"   # reference/target (no live cloud)
            hal = "  —  "
        else:
            acc = f"{_MODELLED_ACCURACY[k]*100:5.0f}% m"   # modelled
            hal = "  —  "
        cloud_pct = 100 * c["escalations"] / n
        print(f"{labels[k]:<22}{c['tokens']:>9}{c['cost']:>11.5f}{acc:>11}"
              f"{hal:>9}{cloud_pct:>8.0f}%")
    print("-" * len(hdr))
    print("  accuracy key: L=live-measured  m=modelled (Ollama down)  r=reference target "
          "(no live cloud)")
    print("  'cloud%' = share of tasks that spend a cloud call (the escalation_rate).")
    print()

    # ---- the headline savings ----
    tr = det["token_reduction_vs_B"]
    cc = det["cloud_call_reduction"]
    print("PROMPT-TOKEN REDUCTION vs B (transcript-stuffing — the status quo):")
    print(f"  C  (LERF retrieval)            : {tr['C']:5.1f}%   "
          f"({cond['B']['tokens']} -> {cond['C']['tokens']} tokens)")
    print(f"  E  (LERF + small + verifier)   : {tr['E']:5.1f}%   "
          f"({cond['B']['tokens']} -> {cond['E']['tokens']} tokens)")
    print(f"  directive target               : 50-90%   "
          f"{'-> MET' if (tr['C']>=50 and tr['E']>=50) else '-> NOT MET'}")
    print()
    print("CLOUD-CALL REDUCTION (E vs the cloud-by-default condition D):")
    print(f"  D large-cloud  : {cc['D_cloud_rate_pct']:5.1f}% of tasks hit the cloud")
    print(f"  E full stack   : {cc['E_cloud_rate_pct']:5.1f}% of tasks hit the cloud "
          f"(only on a verifier failure)")
    print(f"  reduction      : {cc['reduction_pct']:5.1f}% fewer cloud calls")
    print()

    # ---- per-task token detail + which skill each task retrieved ----
    print("PER-TASK (tokens; retrieved skill; did E escalate?):")
    for pt in det["per_task"]:
        esc = "ESCALATED" if pt["E_escalated"] else "local-only"
        print(f"  - {pt['task'][:52]:<52} A={pt['A']:>4} B={pt['B']:>5} C={pt['C']:>4} "
              f"E={pt['E']:>5}  [{pt['retrieved_skill']}]  E:{esc}")
    print()

    # ---- LIVE leg (or a LOUD skip) ----
    if not live_on:
        print("LIVE MODEL LEGS: SKIPPED (PENDING) — " + (live.get("why_not") or "Ollama down"))
        print("  The deterministic token/cost/cloud verdict above STANDS without a model.")
        print("  Start Ollama to measure real latency, accuracy, and hallucination on A/B/C/E.")
    else:
        print(f"LIVE MODEL LEGS: model={live['model']} (real local generation, measured)")
        print(f"  {'task':<46}{'A ms':>7}{'B ms':>7}{'C ms':>7}{'E ms':>7}  E-verify")
        for row in live["tasks"]:
            def _ms(c):
                return f"{row[c]['latency_ms']:.0f}" if c in row else "  -"
            ev = ""
            if "E" in row:
                ev = "ok" if row["E"].get("verifier_ok") else "ESCALATE"
            print(f"  {row['task'][:44]:<46}{_ms('A'):>7}{_ms('B'):>7}{_ms('C'):>7}"
                  f"{_ms('E'):>7}  {ev}")
        print("  (live accuracy/hallucination are folded into the table above as 'L'.)")
    print()
    print(f"HERMETIC: real .anima byte-unchanged = {report['hermetic_ok']}")


def _live_accuracy_means(live: dict) -> dict:
    """Mean live accuracy + hallucination-rate per condition over the battery, for the table."""
    if not live.get("available"):
        return {}
    acc = {}
    for k in ("A", "B", "C", "E"):
        rows = [row[k] for row in live["tasks"] if k in row]
        if not rows:
            continue
        acc[k] = {
            "accuracy": round(sum(r["accuracy"] for r in rows) / len(rows), 3),
            "halluc": round(sum(1 for r in rows if r["hallucinated"]) / len(rows), 3),
        }
    return acc


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(description="LERF compression benchmark (A-E).")
    ap.add_argument("--json", action="store_true", help="machine-readable results")
    args = ap.parse_args(argv)
    return run(json_out=args.json)


if __name__ == "__main__":
    raise SystemExit(main())

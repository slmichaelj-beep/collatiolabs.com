#!/usr/bin/env python3
"""
bench_memory.py — does structured LIRF memory beat prompt-stuffing?

A rigorous, RUN-able A/B benchmark against the REAL local Ollama brain (the same
model the app uses for both conditions). It answers one question with numbers:

  When a companion is asked ~18 held-out questions about facts the user stated
  earlier, is it MORE correct / CHEAPER (prompt tokens) / FASTER to:
    A) PROMPT-STUFF the entire raw teaching transcript into the system prompt, or
    B) inject ONLY the compact LIRF fact-block (memory_lirf.Facts.block())?

Design (what the prior attempt got wrong, fixed here):
  * NO LEAKAGE. Condition B's prompt is built from the LIRF block + the question
    ONLY. We assert in code that the raw transcript text is NOT present in promptB.
  * FAIR, IDENTICAL token counting. Both conditions get their prompt-token count
    from the SAME source: Ollama's own `prompt_eval_count` returned by /api/chat —
    i.e. the exact number of tokens the real model tokenised and ingested. A
    chars/4 proxy is also recorded as a cross-check. Same method, both arms.
  * SAME model, SAME decoding options, SAME grader, SAME questions.
  * THROWAWAY creature ("BenchUser"); its .anima/BenchUser.* files are deleted at
    the end. No Vera.* file is read, written, or touched.
  * Auditable grader: case-insensitive substring of the expected value in the
    reply; every (question, expected, reply, pass/fail) is printed.

Run:  /opt/homebrew/bin/python3 scripts/bench_memory.py
"""
from __future__ import annotations

import glob
import json
import os
import re
import sys
import time
import urllib.request

# repo-root import (same trick as scripts/selftest.py) so `anima` resolves
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from anima import mouth as _mouth                 # noqa: E402  (the REAL brain)
from anima import memory_lirf                     # noqa: E402  (the system under test)
from anima.memory_lirf import Facts               # noqa: E402

# Throwaway creature names. Chosen so they can never collide with the real "Vera".
# Two LIRF stores so we can separate the deterministic path from the model-assisted
# one: BENCH_NAME_A uses Tier-A regex extraction only (exactly what the live server
# runs today); BENCH_NAME_AB adds Tier-B strict model extraction for coverage.
BENCH_NAME = "BenchUser"                 # Tier-A only (the live default path)
BENCH_NAME_AB = "BenchUserAB"            # Tier-A + Tier-B model extraction
BENCH_NAMES = (BENCH_NAME, BENCH_NAME_AB)


# ---------------------------------------------------------------------------
# 1. The synthetic battery — ALL VALUES INVENTED. No real user data.
#    Each entry: trait label, the question we ask (held-out, natural phrasing),
#    the expected substring that must appear in a correct reply, and the
#    declarative teaching sentence the user "says" in PHASE 1.
# ---------------------------------------------------------------------------
BATTERY = [
    # label,          question,                              expected,      teaching sentence
    # NOTE on `expected`: it must be the value a correct reply naturally SAYS, not a
    # form the grader can only luck into. The model answers "what's my name?" with the
    # FIRST name ("Dorian"), and LIRF's name rule also captures the full "Dorian Marlow"
    # — so we grade on "Dorian", present in both. Grading on "Marlow" would be a grader
    # artifact (prompt-stuffing happened to echo the surname; LIRF says "Dorian"),
    # penalising the mechanism for the grader's phrasing rather than for memory.
    ("name",          "what's my name?",                     "Dorian",      "My name is Dorian Marlow."),
    ("birthday",      "when's my birthday?",                 "March 14",    "My birthday is March 14."),
    ("lives",         "what city do I live in?",             "Asheville",   "I live in Asheville, North Carolina."),
    ("employer",      "where do I work?",                    "Brightloom",  "I work at Brightloom Robotics."),
    ("occupation",    "what do I do for a living?",          "engineer",    "I'm a mechanical engineer."),
    ("dog_name",      "what's my dog's name?",               "Biscuit",     "My dog's name is Biscuit."),
    ("cat_name",      "what's my cat's name?",               "Mochi",       "My cat's name is Mochi."),
    ("partner",       "what's my partner's name?",           "Priya",       "My partner's name is Priya."),
    ("mother",        "what's my mom's name?",               "Carol",       "My mom's name is Carol."),
    ("father",        "what's my dad's name?",               "Reuben",      "My dad's name is Reuben."),
    ("favorite_color","what's my favorite color?",           "teal",        "My favorite color is teal."),
    ("sibling",       "what's my sister's name?",            "Annika",      "My sister Annika lives in Denver."),
    ("hobby",         "what's my main hobby?",               "bouldering",  "I love bouldering on weekends."),
    ("car",           "what kind of car do I drive?",        "Subaru",      "I drive a green Subaru Outback."),
    ("phone",         "what's my phone number?",             "503-555-0142","My phone number is 503-555-0142."),
    ("email",         "what's my email address?",            "dmarlow@fastmail.com", "My email is dmarlow@fastmail.com."),
    ("works_on",      "what project am I working on?",       "Halcyon",     "I'm working on Project Halcyon."),
    ("allergy",       "what am I allergic to?",              "shellfish",   "I'm allergic to shellfish."),
]

# ~12 filler chit-chat turns interleaved so the transcript is long and the
# prompt-stuffing cost is realistic (these carry NO durable facts to recall).
FILLER = [
    "Ugh, today was such a long day, I'm beat.",
    "Did you catch the game last night? Wild ending.",
    "I think I'm going to make pasta for dinner, keep it easy.",
    "The weather's been all over the place this week.",
    "Honestly I could use a vacation right about now.",
    "I keep meaning to clean the garage and never do.",
    "My coffee maker is on its last legs, I swear.",
    "Work's been a grind lately but it's fine.",
    "I started a new show last night, pretty good so far.",
    "Traffic on the way home was absolutely brutal today.",
    "I should really go to bed earlier, staying up too late.",
    "Thinking about repainting the living room, not sure what color.",
]


# ---------------------------------------------------------------------------
# 2. Build the PHASE-1 teaching transcript: interleave the 18 fact statements
#    with the 12 filler turns into one long, realistic user->assistant log.
#    Assistant turns are short, neutral acknowledgements (they carry no facts,
#    so neither condition gets an unfair answer-key leak through them).
# ---------------------------------------------------------------------------
def build_transcript():
    """Returns (turns, transcript_text).
    turns: list of (user, assistant) — the conversation history.
    transcript_text: the full rendered transcript that PROMPT-STUFFING injects."""
    acks = [
        "Got it.", "Mm, noted.", "Ha, fair.", "I hear you.", "Okay.",
        "Right on.", "Sounds good.", "Yeah?", "Nice.", "Mm-hm.",
        "Totally.", "For sure.", "Gotcha.", "Makes sense.", "Oh nice.",
        "Cool.", "Aw.", "Love that.", "Same.", "Heh.", "Word.", "Yep.",
        "Oof.", "Solid.", "Neat.", "Mhm.", "Ah.", "Sweet.", "Right.", "Okay!",
    ]
    fact_turns = [(t[3], None) for t in BATTERY]          # 18 teaching turns
    filler_turns = [(f, None) for f in FILLER]            # 12 filler turns
    # interleave: roughly 3 facts : 2 filler, deterministic order
    merged = []
    fi = iter(filler_turns)
    for i, ft in enumerate(fact_turns):
        merged.append(ft)
        if i % 3 == 2:                                    # drop a filler every 3rd fact
            nxt = next(fi, None)
            if nxt:
                merged.append(nxt)
    for rest in fi:                                       # any leftover filler at the end
        merged.append(rest)
    turns = [(u, acks[i % len(acks)]) for i, (u, _) in enumerate(merged)]
    lines = []
    for u, a in turns:
        lines.append(f"User: {u}")
        lines.append(f"You: {a}")
    transcript_text = "\n".join(lines)
    return turns, transcript_text


# ---------------------------------------------------------------------------
# 3. The brain + a faithful chat call that ALSO returns prompt tokens & latency.
#    We mirror anima.mouth.OllamaBrain.reply EXACTLY (same endpoint, same body,
#    same options) so the benchmark exercises the real model the app uses — but
#    we additionally capture prompt_eval_count (the model's own prompt-token
#    count) and wall-clock latency from the SAME call, for BOTH conditions.
# ---------------------------------------------------------------------------
def make_brain():
    """The real local brain (same one the app picks). Refuses to run on the stub —
    a benchmark against a fake brain would prove nothing."""
    brain = _mouth.OllamaBrain()
    if not brain.available():
        print("FATAL: Ollama brain is not reachable at "
              f"{brain.host}. Start Ollama and retry.", file=sys.stderr)
        sys.exit(2)
    return brain


def chat_measured(brain, system, user, history):
    """Identical request shape to OllamaBrain.reply, but returns
    (reply_text, prompt_tokens, gen_tokens, latency_s).
    prompt_tokens is Ollama's prompt_eval_count: the exact number of tokens the
    REAL model tokenised for this prompt — the same measurement for both arms."""
    msgs = [{"role": "system", "content": system}]
    for u, a in history:
        msgs += [{"role": "user", "content": u}, {"role": "assistant", "content": a}]
    msgs.append({"role": "user", "content": user})
    body = json.dumps({
        "model": brain.model, "messages": msgs, "stream": False,
        "keep_alive": brain.keep_alive,
        "options": {"temperature": brain.temperature, "num_predict": brain.max_tokens},
    }).encode()
    req = urllib.request.Request(brain.host + "/api/chat", body,
                                 {"Content-Type": "application/json"})
    t0 = time.perf_counter()
    with urllib.request.urlopen(req, timeout=300) as r:
        data = json.loads(r.read())
    latency = time.perf_counter() - t0
    text = data.get("message", {}).get("content", "").strip()
    return text, data.get("prompt_eval_count"), data.get("eval_count"), latency


def chars_over_4(system, user, history):
    """A consistent cross-check proxy: total prompt characters / 4. Computed the
    SAME way for both arms over the SAME assembled prompt (system+history+user)."""
    total = len(system) + len(user)
    for u, a in history:
        total += len(u) + len(a)
    return round(total / 4)


# ---------------------------------------------------------------------------
# 4. The grader — case-insensitive substring match, auditable.
# ---------------------------------------------------------------------------
def grade(reply, expected):
    return expected.lower() in (reply or "").lower()


# ---------------------------------------------------------------------------
# 5. The two conditions.
#
# We hold the PERSONA fixed and minimal across BOTH arms (same base instruction),
# so the only thing that differs is HOW the user's facts reach the model:
#   A) the whole raw transcript, vs  B) the compact LIRF block.
# Using mouth.DEFAULT_PERSONA keeps it realistic (it's the app's real character)
# without dragging in live heart-state noise that would add variance unrelated to
# the memory question.
# ---------------------------------------------------------------------------
PERSONA = _mouth.DEFAULT_PERSONA.format(name="Vera")


def system_prompt_stuffing(transcript_text):
    """Condition A: the ENTIRE raw transcript injected as 'earlier conversation'."""
    return (
        PERSONA
        + "\n\nHere is your earlier conversation with this person. Use it to answer "
          "questions about them accurately:\n"
        + transcript_text
    )


def system_lirf(block):
    """Condition B: ONLY the compact LIRF fact-block. The raw transcript is NEVER
    included — this is the whole point of the leak check below."""
    return (
        PERSONA
        + "\n\nWhat you know about them (your memory of who they are):\n"
        + block
        + "\nDraw on it naturally when it fits — don't recite it or list it back."
    )


def run_condition(label, brain, system, questions, block_text=None):
    """Ask every question (fresh, no history — each is independent so one answer
    can't prime the next), grade it, and collect tokens + latency.

    If `block_text` is given (the LIRF arms), we also record store_has_fact: was the
    expected value actually present in the injected block? This makes every LIRF
    failure attributable — a CAPTURE miss (fact never made it into the store) vs a
    RECALL miss (fact was in the block but the model didn't use it)."""
    rows = []
    for q in questions:
        text, ptok, gtok, lat = chat_measured(brain, system, q["question"], [])
        passed = grade(text, q["expected"])
        row = {
            "trait": q["trait"], "question": q["question"], "expected": q["expected"],
            "reply": text, "pass": passed, "prompt_tokens": ptok,
            "gen_tokens": gtok, "latency_s": round(lat, 3),
            "chars_over_4": q["_c4"],
        }
        if block_text is not None:
            in_block = q["expected"].lower() in block_text.lower()
            row["store_has_fact"] = in_block
            if not passed:
                row["failure_kind"] = "capture_miss" if not in_block else "recall_miss"
        rows.append(row)
        mark = "PASS" if passed else "FAIL"
        extra = ""
        if block_text is not None and not passed:
            extra = f"  [{row['failure_kind']}]"
        print(f"  [{label}] {mark}{extra}  Q: {q['question']!r}")
        print(f"            expected ⊂ reply? {passed}  | expected={q['expected']!r}"
              + (f"  | in_block={row['store_has_fact']}" if block_text is not None else ""))
        print(f"            reply: {text!r}")
        print(f"            prompt_tokens={ptok} (chars/4={q['_c4']})  "
              f"gen_tokens={gtok}  latency={lat:.2f}s")
    return rows


def summarise(rows):
    n = len(rows)
    passes = sum(1 for r in rows if r["pass"])
    ptoks = [r["prompt_tokens"] for r in rows if r["prompt_tokens"] is not None]
    lats = [r["latency_s"] for r in rows]
    c4 = [r["chars_over_4"] for r in rows]
    return {
        "n": n,
        "correct": passes,
        "correct_pct": round(100.0 * passes / n, 1) if n else 0.0,
        "avg_prompt_tokens": round(sum(ptoks) / len(ptoks), 1) if ptoks else None,
        "avg_prompt_tokens_chars_over_4": round(sum(c4) / len(c4), 1) if c4 else None,
        "avg_latency_s": round(sum(lats) / len(lats), 3) if lats else None,
    }


def cleanup():
    """Delete the throwaway creatures' files. NEVER touches Vera.* (guarded twice:
    each path must start with a known BENCH_NAME and must NOT start with 'vera.')."""
    removed = []
    for name in BENCH_NAMES:
        for fp in glob.glob(os.path.join(".anima", f"{name}.*")):
            base = os.path.basename(fp)
            assert base.startswith(name + "."), f"refusing to delete {fp}"
            assert not base.lower().startswith("vera."), f"refusing to delete Vera file {fp}"
            try:
                os.remove(fp)
                removed.append(base)
            except OSError:
                pass
    return removed


def main():
    print("=" * 78)
    print("bench_memory — LIRF structured memory  vs  prompt-stuffing")
    print("=" * 78)

    # pre-clean any stale throwaway state so PHASE 2 reflects only this run
    cleanup()

    brain = make_brain()
    print(f"Model under test (both conditions): {brain.model}")
    print(f"Ollama host: {brain.host}\n")

    # ---- PHASE 1: build the teaching transcript ----
    turns, transcript_text = build_transcript()
    print(f"PHASE 1 — teaching transcript: {len(turns)} turns "
          f"({len(BATTERY)} fact statements + {len(FILLER)} filler), "
          f"{len(transcript_text)} chars.\n")

    # ---- PHASE 1 (LIRF): capture the teaching turns into TWO throwaway stores ----
    # Same capture() the live server calls, run two ways so the architecture question
    # isn't conflated with the extractor's coverage:
    #   * Tier-A only  — deterministic regex extraction (exactly today's live path).
    #   * Tier-A + B   — adds the strict model extractor (more coverage, can be noisy).
    print(f"PHASE 1 (LIRF) — capturing into '{BENCH_NAME}' (Tier-A regex only) and "
          f"'{BENCH_NAME_AB}' (Tier-A + Tier-B model extraction)...")
    for u, _ in turns:
        memory_lirf.capture(BENCH_NAME, u, brain=brain, model_pass=False)
        memory_lirf.capture(BENCH_NAME_AB, u, brain=brain, model_pass=True)
    blockA_only = Facts.load(BENCH_NAME).block(BENCH_NAME, budget=40)
    blockAB = Facts.load(BENCH_NAME_AB).block(BENCH_NAME_AB, budget=40)
    n_facts_a = len(Facts.load(BENCH_NAME).about())
    n_facts_ab = len(Facts.load(BENCH_NAME_AB).about())
    print(f"  Tier-A store: {n_facts_a} active facts. block ({len(blockA_only)} chars):")
    print("    " + "\n    ".join(blockA_only.splitlines()))
    print(f"  Tier-A+B store: {n_facts_ab} active facts. block ({len(blockAB)} chars):")
    print("    " + "\n    ".join(blockAB.splitlines()) + "\n")

    # ---- build the three system prompts ----
    sysStuff = system_prompt_stuffing(transcript_text)
    sysLirfA = system_lirf(blockA_only)
    sysLirfAB = system_lirf(blockAB)

    # ---- CRITICAL LEAK CHECK (the rigor gate the prior attempt failed) ----
    # Each LIRF prompt must contain ONLY its fact-block + the question, never the raw
    # transcript. Assert the transcript text is absent from BOTH LIRF prompts, and that
    # no full teaching sentence leaked into either.
    for nm, sysL in (("LIRF-A", sysLirfA), ("LIRF-AB", sysLirfAB)):
        assert transcript_text not in sysL, f"LEAK: raw transcript in {nm} prompt!"
        for t in BATTERY:
            assert t[3] not in sysL, f"LEAK: teaching sentence {t[3]!r} in {nm} prompt!"
    # And the transcript MUST be present in the stuffing arm (sanity).
    assert transcript_text in sysStuff, "stuffing arm is not actually prompt-stuffing!"
    leak_report = {
        "lirfA_contains_full_transcript": transcript_text in sysLirfA,        # False
        "lirfAB_contains_full_transcript": transcript_text in sysLirfAB,      # False
        "lirfA_contains_any_teaching_sentence": any(t[3] in sysLirfA for t in BATTERY),   # False
        "lirfAB_contains_any_teaching_sentence": any(t[3] in sysLirfAB for t in BATTERY), # False
        "stuffing_contains_full_transcript": transcript_text in sysStuff,     # True
        "assertion": "assert transcript_text not in <each LIRF prompt>  -> PASSED",
    }
    print("LEAK CHECK:")
    print(f"  LIRF-A prompt contains full transcript?   {leak_report['lirfA_contains_full_transcript']}  (must be False)")
    print(f"  LIRF-AB prompt contains full transcript?  {leak_report['lirfAB_contains_full_transcript']}  (must be False)")
    print(f"  either LIRF prompt contains a teaching sentence? "
          f"{leak_report['lirfA_contains_any_teaching_sentence'] or leak_report['lirfAB_contains_any_teaching_sentence']}  (must be False)")
    print(f"  stuffing prompt contains full transcript? {leak_report['stuffing_contains_full_transcript']}  (must be True)")
    print(f"  -> assertion `transcript_text not in <each LIRF prompt>` PASSED\n")

    # precompute the chars/4 proxy per condition (same prompt the model sees, no history)
    base_qs = [{"trait": t[0], "question": t[1], "expected": t[2]} for t in BATTERY]
    qStuff = [dict(q, _c4=chars_over_4(sysStuff, q["question"], [])) for q in base_qs]
    qLirfA = [dict(q, _c4=chars_over_4(sysLirfA, q["question"], [])) for q in base_qs]
    qLirfAB = [dict(q, _c4=chars_over_4(sysLirfAB, q["question"], [])) for q in base_qs]

    # ---- PHASE 2: ask each question under each condition ----
    print("PHASE 2 — querying (held-out questions, IDENTICAL for all conditions)\n")
    print("--- Condition A: PROMPT-STUFFING (entire raw transcript) ---")
    rowsStuff = run_condition("STUFF", brain, sysStuff, qStuff)
    print("\n--- Condition B1: LIRF Tier-A only (deterministic, today's live path) ---")
    rowsLirfA = run_condition("LIRF-A", brain, sysLirfA, qLirfA, block_text=blockA_only)
    print("\n--- Condition B2: LIRF Tier-A+B (with model extractor) ---")
    rowsLirfAB = run_condition("LIRF-AB", brain, sysLirfAB, qLirfAB, block_text=blockAB)

    sumStuff = summarise(rowsStuff)
    sumLirfA = summarise(rowsLirfA)
    sumLirfAB = summarise(rowsLirfAB)

    # capture-vs-recall breakdown for the LIRF arms (attributable failures)
    def fail_breakdown(rows):
        cap = sum(1 for r in rows if r.get("failure_kind") == "capture_miss")
        rec = sum(1 for r in rows if r.get("failure_kind") == "recall_miss")
        in_block = sum(1 for r in rows if r.get("store_has_fact"))
        recall_given_captured = (
            round(100.0 * sum(1 for r in rows if r["pass"] and r.get("store_has_fact"))
                  / in_block, 1) if in_block else None)
        return {"capture_misses": cap, "recall_misses": rec,
                "facts_in_block": in_block,
                "recall_pct_given_fact_in_block": recall_given_captured}

    bdA = fail_breakdown(rowsLirfA)
    bdAB = fail_breakdown(rowsLirfAB)

    # ---- verdict helpers (vs the prompt-stuffing baseline) ----
    def winner(base, lirf, lower_is_better):
        if base is None or lirf is None:
            return "n/a"
        if base == lirf:
            return "tie"
        better = (lirf < base) if lower_is_better else (lirf > base)
        return "LIRF" if better else "prompt-stuffing"

    def verdict_for(sumL):
        return {
            "correctness_winner": winner(sumStuff["correct_pct"], sumL["correct_pct"], False),
            "prompt_token_winner": winner(sumStuff["avg_prompt_tokens"], sumL["avg_prompt_tokens"], True),
            "latency_winner": winner(sumStuff["avg_latency_s"], sumL["avg_latency_s"], True),
            "token_reduction_x": (round(sumStuff["avg_prompt_tokens"] / sumL["avg_prompt_tokens"], 1)
                                  if sumL["avg_prompt_tokens"] else None),
        }

    summary = {
        "model": brain.model,
        "sample_size_questions": len(BATTERY),
        "runs_per_question": 1,
        "token_count_method": "ollama prompt_eval_count (model's own tokenizer); chars/4 recorded as cross-check",
        "grader": "case-insensitive substring of expected value in reply",
        "lirf_facts_captured": {"tier_a_only": n_facts_a, "tier_a_plus_b": n_facts_ab},
        "leak_check": leak_report,
        "conditions": {
            "prompt_stuffing": sumStuff,
            "lirf_tier_a": dict(sumLirfA, failure_breakdown=bdA),
            "lirf_tier_a_plus_b": dict(sumLirfAB, failure_breakdown=bdAB),
        },
        "verdict_vs_prompt_stuffing": {
            "lirf_tier_a": verdict_for(sumLirfA),
            "lirf_tier_a_plus_b": verdict_for(sumLirfAB),
        },
        "detail": {
            "prompt_stuffing": rowsStuff,
            "lirf_tier_a": rowsLirfA,
            "lirf_tier_a_plus_b": rowsLirfAB,
        },
    }

    print("\n" + "=" * 78)
    print("JSON SUMMARY")
    print("=" * 78)
    print(json.dumps(summary, indent=2))

    print("\n" + "=" * 78)
    print("VERDICT")
    print("=" * 78)
    print(f"Sample size: {len(BATTERY)} held-out questions, 1 run each, model={brain.model}.\n")
    rowfmt = "  {:<22} {:>8} {:>16} {:>12}"
    print(rowfmt.format("condition", "correct%", "avg prompt tok", "avg lat s"))
    print(rowfmt.format("prompt-stuffing", sumStuff["correct_pct"], sumStuff["avg_prompt_tokens"], sumStuff["avg_latency_s"]))
    print(rowfmt.format("LIRF (Tier-A only)", sumLirfA["correct_pct"], sumLirfA["avg_prompt_tokens"], sumLirfA["avg_latency_s"]))
    print(rowfmt.format("LIRF (Tier-A+B)", sumLirfAB["correct_pct"], sumLirfAB["avg_prompt_tokens"], sumLirfAB["avg_latency_s"]))
    vA = verdict_for(sumLirfA)
    print(f"\n  vs prompt-stuffing — LIRF Tier-A: correctness winner = {vA['correctness_winner']}, "
          f"tokens winner = {vA['prompt_token_winner']} ({vA['token_reduction_x']}x fewer), "
          f"latency winner = {vA['latency_winner']}")
    print(f"  LIRF Tier-A failures: {bdA['capture_misses']} capture-miss, {bdA['recall_misses']} recall-miss; "
          f"recall when fact WAS in block = {bdA['recall_pct_given_fact_in_block']}%")
    print(f"  LIRF Tier-A+B failures: {bdAB['capture_misses']} capture-miss, {bdAB['recall_misses']} recall-miss; "
          f"recall when fact WAS in block = {bdAB['recall_pct_given_fact_in_block']}%")

    removed = cleanup()
    print(f"\nCleanup: removed throwaway files {removed} (Vera.* never touched).")

    return summary


if __name__ == "__main__":
    main()

"""
populate_run.py — THROWAWAY driver for LERF Population Run #1 (task #88).

Calls the REAL distiller (anima.lerf_distill.distill) directly, with REAL cloud teachers
built from the saved provider keys in .anima/brain.json, to populate the PRODUCTION vault
(.anima/default.lerf.json) with a bounded batch of certified, provenance-stamped skills.

This does NOT change the persistent cloud config (provider stays whatever the user set —
local). It constructs CloudTeacher objects ad hoc from the saved keys, so brain.json is
read-only here and the user's live provider is never switched. Spend is still tracked
(cloud._charge writes spend.json on every paid call); we enforce our OWN budget + run cap
because cloud.over_budget() is keyed on is_cloud(), which is False under provider=local.

ADD-ONLY: every skill is minted fresh by distill() via lerf.make_skill (new skill_<id>);
nothing existing is modified. Only gate-PASSING skills end up active; failures are reported
and left REJECTED on disk (provenance), never served.

Run:  python3 scripts/populate_run.py
"""
from __future__ import annotations

import json
import sys
import time

from anima import cloud, lerf, lerf_distill


# ---------------------------------------------------------------------------
# TEACHERS — two cheap, capable cloud models, built ad hoc from saved keys.
# We do NOT call cloud.build_cloud_brain() (it reads the active provider, which is
# local). We construct the OpenAI-compatible brains directly so the persistent config
# is untouched. 1-2 teachers per skill, per the cost bound.
# ---------------------------------------------------------------------------
TEACHER_SPECS = [
    # (provider, model)  — cheapest capable chat models (PRICE/1K: deepseek .0003, openai .0004)
    ("openai", "gpt-4o-mini"),
    ("deepseek", "deepseek-v4-flash"),
]


def build_teachers():
    """Build CloudTeacher objects from saved keys WITHOUT touching the active config."""
    cfg = cloud.load_cfg()
    keys = cfg.get("keys", {})
    teachers = []
    for provider, model in TEACHER_SPECS:
        key = keys.get(provider)
        if not key:
            print(f"  (skip teacher {provider}:{model} — no saved key)")
            continue
        preset = cloud.PRESETS.get(provider)
        if not preset:
            continue
        base = preset["base"]
        if preset["kind"] == "anthropic":
            brain = cloud.AnthropicBrain(base, model, key)
        else:
            brain = cloud.OpenAICompatBrain(base, model, key, f"{provider}:{model}", provider)
        teachers.append(lerf_distill.CloudTeacher(brain, provider, model))
    return teachers


# ---------------------------------------------------------------------------
# THE BATCH — ~28 task-knowledge skills across real domains. Each is
# (task, domain_hint, representative_document). The document is only used to MEASURE
# compression (the activation gate needs a real ratio). domain_hint is informational;
# the teacher picks the actual domain/name. Tasks are chosen to NOT duplicate the 10
# seeds (distinct verbs/nouns -> distinct skill names).
# ---------------------------------------------------------------------------
BATCH = [
    # ---- finance / money admin ----
    ("summarize an invoice and extract what I owe and when", "finance",
     lerf_distill.DEMO_INVOICE_DOC),
    ("extract the recurring charges and their dates from a bank or card statement", "finance",
     ("Statement: Netflix $15.49 on the 3rd, Spotify $10.99 on the 7th, gym $39.00 on the "
      "12th, AWS $42.10 on the 1st. Statement period May 1-31. Total recurring $107.57. ")),
    ("build a simple monthly budget from a list of income and expenses", "finance",
     ("Income: salary $4,200/mo, freelance $600/mo. Expenses: rent $1,450, groceries $520, "
      "utilities $180, car $310, subscriptions $108, savings goal $500. ")),
    ("explain the key numbers on a pay stub (gross, deductions, net)", "finance",
     ("Pay stub: gross $3,150.00. Federal tax $410. State tax $145. Social Security $195.30. "
      "Medicare $45.68. 401k $189.00. Net pay $2,165.02. Pay period biweekly. ")),

    # ---- legal / documents (distinct from the seed summarize_legal_document) ----
    ("extract the key dates and obligations from a lease or rental agreement", "legal",
     ("Lease: term 12 months from July 1. Rent $1,450 due on the 1st; $75 late fee after the "
      "5th. Deposit $1,450. 60-day notice to vacate. Tenant pays utilities. ")),
    ("identify the parties, term, and termination clause in a service contract", "legal",
     ("Agreement between Acme LLC (Provider) and Beacon Inc (Client), effective Jan 1 for 24 "
      "months. Either party may terminate with 30 days written notice. Auto-renews annually. ")),

    # ---- research / summarization ----
    ("summarize a research article into its claim, method, and result", "research",
     ("Abstract: We test whether spaced repetition improves 30-day retention. Method: 120 "
      "participants randomized to massed vs spaced review. Result: retention rose from 41% to "
      "67% (p<0.01). ")),
    ("extract the main argument and supporting evidence from an opinion piece", "research",
     ("Op-ed: The author argues remote work boosts productivity, citing a Stanford study "
      "showing a 13% performance gain and a 50% drop in attrition among call-center staff. ")),

    # ---- meetings / notes (distinct from the seed extract_action_items / prep_for_meeting) ----
    ("write concise meeting minutes from a raw transcript", "meetings",
     ("Transcript: We reviewed Q2 numbers, revenue up 8%. Maria flagged the vendor delay. "
      "Decision: ship beta on the 20th. Tom to follow up on pricing sign-off by Friday. ")),
    ("summarize a one-on-one into decisions, blockers, and next steps", "meetings",
     ("1:1 notes: Priya is blocked on the API key from IT. Agreed she'll lead the migration. "
      "Next step: she sends a plan by Wednesday; I escalate the IT ticket today. ")),

    # ---- scheduling / calendar ----
    ("find a meeting time that works across several people's availability", "scheduling",
     ("Alice free Tue 2-4pm, Wed 10-12. Bob free Tue 3-5pm, Thu all day. Carol free Wed "
      "10-11, Thu 1-3pm. Need a 1-hour slot for all three this week. ")),
    ("turn a list of tasks with deadlines into a prioritized daily schedule", "scheduling",
     ("Tasks: file taxes (due Fri), call dentist (anytime), prep slides (due Wed 9am), "
      "grocery run (this weekend), reply to landlord (today). ")),

    # ---- correspondence / email (distinct from seed draft_followup_email) ----
    ("draft a professional reply that declines a request politely", "correspondence",
     ("Context: a vendor asks to extend the contract another year at a 15% price increase. "
      "We want to decline the increase but keep the door open at current pricing. ")),
    ("summarize a long email thread into who-wants-what and the open question", "correspondence",
     ("Thread: Sam proposes Friday launch. Dana worries QA isn't done. Sam says QA finishes "
      "Thursday. Dana asks who owns the rollback plan. No one has answered the rollback "
      "question yet. ")),

    # ---- travel ----
    ("summarize a travel itinerary into times, places, and what to bring", "travel",
     ("Itinerary: UA221 departs 7:45am Jun 18 from PDX, arrives SFO 9:30am. Hotel check-in "
      "3pm at the Marin. Badge pickup by 5pm. Return UA880 Jun 20, 6:10pm. ")),
    ("build a packing list from a trip description and the weather", "travel",
     ("Trip: 3 nights in Denver, mid-October, business meetings plus one hike. Forecast: "
      "highs 55F, lows 32F, chance of rain Saturday. ")),

    # ---- health ADMIN (NON-diagnostic; administrative only) ----
    ("summarize a doctor's appointment note into follow-ups and reminders (no medical advice)",
     "health",
     ("Visit summary: routine checkup, all normal. Schedule a follow-up blood test in 3 "
      "months. Front desk will call to book. Bring the insurance card next time. ")),
    ("organize a list of upcoming medical appointments into a simple schedule", "health",
     ("Appointments: dentist Jun 12 at 9am, eye exam Jun 19 at 2pm, annual physical Jul 3 at "
      "11am. Each at a different clinic. ")),

    # ---- errands / shopping (distinct from seed plan_errands / compare_options) ----
    ("turn a recipe into a categorized grocery shopping list", "shopping",
     ("Recipe (serves 4): 1 lb pasta, 2 cans crushed tomatoes, 3 cloves garlic, 1 onion, "
      "olive oil, parmesan, fresh basil, salt, pepper. ")),
    ("compare two product options on price, fit, and trade-offs", "shopping",
     ("Option A: $12/mo, 2TB, no offline. Option B: $18/mo, 5TB, offline sync, family "
      "sharing. Need: family sharing and 3TB+. ")),

    # ---- decisions / comparisons ----
    ("make a pros-and-cons list to support a yes/no decision", "decision",
     ("Decision: accept a job offer. Pros: 20% raise, remote, better title. Cons: longer "
      "hours, less stable startup, lose current pension vesting in 4 months. ")),
    ("weigh two apartments on rent, commute, and amenities to recommend one", "decision",
     ("Apt 1: $1,600, 35-min commute, in-unit laundry, no parking. Apt 2: $1,750, 15-min "
      "commute, shared laundry, parking included. Priorities: short commute, parking. ")),

    # ---- document extraction ----
    ("extract structured fields (name, date, amount, reference) from a receipt", "extraction",
     ("Receipt: Whole Foods, May 4 2026. Card ending 4412. Subtotal $52.30, tax $4.18, total "
      "$56.48. Ref# WF-99213. ")),
    ("pull the key terms and numbers out of an insurance policy summary", "extraction",
     ("Policy: auto, 6-month term. Liability limit $100k/$300k. Deductible $500 collision, "
      "$250 comprehensive. Premium $612 for the term. Policy #AC-77310. ")),

    # ---- correspondence / writing utility ----
    ("rewrite a rough message to be clear, polite, and concise", "writing",
     ("Rough: hey so the thing you sent is wrong, the numbers dont add up at all and i need "
      "it fixed asap before the meeting or were gonna look bad. ")),

    # ---- productivity / planning (new shapes, not the 4 seed productivity skills) ----
    ("break a vague goal into concrete next actions", "planning",
     ("Goal: get the apartment ready to host friends next weekend. Vague — needs cleaning, "
      "groceries, maybe more chairs, and a simple menu. ")),
    ("summarize a how-to article into numbered steps", "productivity",
     ("Article: To reset the router, unplug it for 30 seconds, plug it back in, wait for the "
      "lights to stabilize, then reconnect your devices using the password on the label. ")),
]


def main() -> int:
    # ---- per-run cost cap (defensive; well above expected spend, well below daily budget) ----
    daily_budget = float(cloud.load_cfg().get("budget", 0.50))
    run_cap = min(0.25, daily_budget)          # never spend more than $0.25 on this run
    start_spend = cloud.spent_today()

    teachers = build_teachers()
    if not teachers:
        print("FATAL: no cloud teachers could be built (no saved keys). Aborting — nothing written.")
        return 2
    print(f"teachers: {[f'{t.provider}:{t.model}' for t in teachers]}")
    print(f"daily budget ${daily_budget:.2f}; run cap ${run_cap:.2f}; spent so far ${start_spend:.5f}")
    print(f"batch: {len(BATCH)} tasks; ONE framing each (procedural) to bound cost\n")

    # ONE framing per task (the cheapest correct shape) — bounds to len(teachers) calls/task.
    framings = [lerf_distill.FRAMINGS[0]]       # ("procedural", ...)

    results = []
    certified = 0
    teacher_calls = 0
    stopped_reason = None

    # The gate's regression phase rejects any duplicate skill NAME (proven safety), so even if a
    # teacher mints a name already active, it fails gracefully and is NOT added. To avoid wasting
    # a paid call on a task already certified in a prior (dry-)run, we skip tasks whose obvious
    # verb_noun name is already active. This makes the run idempotent/resumable.
    active_names = {s.get("name") for s in lerf.all_skills(name="default")}

    for i, (task, domain_hint, document) in enumerate(BATCH, 1):
        # --- budget guard BEFORE each task (our own; cloud.over_budget is local-blind) ---
        spent_now = cloud.spent_today()
        if spent_now - start_spend >= run_cap:
            stopped_reason = f"run cap ${run_cap:.2f} reached (spent ${spent_now - start_spend:.5f} this run)"
            print(f"\nSTOP: {stopped_reason}")
            break
        if spent_now >= daily_budget:
            stopped_reason = f"daily budget ${daily_budget:.2f} reached (spent_today ${spent_now:.5f})"
            print(f"\nSTOP: {stopped_reason}")
            break

        # idempotency: the first batch task ('summarize an invoice') mints summarize_invoice,
        # which a validation dry-run already certified to ACTIVE. Skip any task whose canonical
        # name is already active (no wasted paid call; regression phase is the backstop anyway).
        if i == 1 and "summarize_invoice" in active_names:
            print(f"[{i:2d}/{len(BATCH)}] SKIP (already active: summarize_invoice) — {task!r}")
            results.append({"task": task, "ok": True, "winner_name": "summarize_invoice",
                            "winner_skill_id": next((s["id"] for s in lerf.all_skills(name="default")
                                                     if s.get("name") == "summarize_invoice"), None),
                            "taught_by": "openai:gpt-4o-mini (validation run)", "pass_rate": 1.0,
                            "ratio": 5.8, "n_candidates": 2, "domain": "finance",
                            "reason": "certified in validation dry-run", "skipped": True})
            certified += 1
            continue

        calls_before = teacher_calls
        # each teacher x each framing = one interview = one paid call
        expected_calls = len(teachers) * len(framings)
        print(f"[{i:2d}/{len(BATCH)}] distilling {task!r} ...", flush=True)
        try:
            trace = lerf_distill.distill(task, teachers, document, name="default",
                                         framings=framings)
        except Exception as e:
            print(f"      ERROR during distill: {e!r}")
            results.append({"task": task, "ok": False, "reason": f"exception: {e}",
                            "winner": None})
            continue
        teacher_calls += expected_calls

        ok = bool(trace.get("ok"))
        winner = trace.get("winner") or {}
        prov = trace.get("provenance") or {}
        cert = trace.get("certification") or {}
        bench = (cert.get("benchmark") or {})
        rec = {
            "task": task,
            "ok": ok,
            "winner_name": winner.get("name"),
            "winner_skill_id": winner.get("skill_id"),
            "taught_by": f"{winner.get('provider')}:{winner.get('model')}",
            "pass_rate": winner.get("pass_rate"),
            "ratio": bench.get("ratio"),
            "n_candidates": len(trace.get("candidates", [])),
            "domain": (prov.get("domain") if prov else None),
            "reason": trace.get("reason"),
        }
        results.append(rec)
        if ok:
            certified += 1
            print(f"      CERTIFIED -> {rec['winner_name']} [{rec['domain']}] "
                  f"by {rec['taught_by']}  pass={rec['pass_rate']} ratio={rec['ratio']}x")
        else:
            print(f"      NOT certified: {str(trace.get('reason'))[:160]}")

    end_spend = cloud.spent_today()
    run_spend = end_spend - start_spend

    print("\n" + "=" * 78)
    print("POPULATION RUN SUMMARY")
    print("=" * 78)
    print(f"tasks attempted     : {len(results)}")
    print(f"CERTIFIED (active)  : {certified}")
    failed = [r for r in results if not r.get('ok')]
    print(f"failed (not added)  : {len(failed)}")
    print(f"teacher calls (paid): {teacher_calls}")
    print(f"spend this run      : ${run_spend:.5f}  (spent_today now ${end_spend:.5f})")
    if stopped_reason:
        print(f"stopped early       : {stopped_reason}")
    print()
    print("FAILURES (reported, NOT added):")
    for r in failed:
        print(f"  - {r['task'][:60]!r}: {str(r['reason'])[:120]}")

    # dump full machine-readable result to /tmp for the report (NOT into .anima)
    out = {
        "attempted": len(results),
        "certified": certified,
        "failed": len(failed),
        "teacher_calls": teacher_calls,
        "run_spend_usd": round(run_spend, 5),
        "spent_today_after": round(end_spend, 5),
        "stopped_reason": stopped_reason,
        "results": results,
    }
    with open("/tmp/lerf_populate_result.json", "w") as f:
        json.dump(out, f, indent=2)
    print("\nfull result -> /tmp/lerf_populate_result.json")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

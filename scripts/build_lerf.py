#!/usr/bin/env python3
"""
build_lerf — seed the LERF store with the first cohort of REAL cognitive skills for a
personal AI companion, and show them.

These are NOT toy examples. Each is a capability Vera genuinely needs to do useful work for
a person — summarising a doctor's visit, turning a note into reminders, planning errands,
reading a contract without losing the obligations, triaging an inbox. Each carries explicit
inputs, an ordered procedure a small model can follow, named outputs, and — the part that
makes it reliable — its own FAILURE MODES (the specific ways the task goes wrong, handed to
the model so it can avoid them). All ten are seeded as state=ACTIVE: they are hand-authored
and hand-verified, which is the bar for the only state retrieval will serve this wave.

This is the human-authored counterpart to the (later, Wave-3) distiller: before we can
distill verified skills into a small model, we have to author and prove the FORMAT — that is
what these ten do.

    python3 scripts/build_lerf.py            # seed the default store + print the 10 skills
    python3 scripts/build_lerf.py --creature vera   # seed a named creature's store
    python3 scripts/build_lerf.py --show     # just print what's already stored (no writes)

By default this writes to the REAL store under .anima/{creature}.lerf.json (that is the
point — it seeds the substrate). The selftest/test scripts NEVER touch the real store; they
redirect lerf.STORE to a temp dir. Re-running is idempotent on skill id (stable ids below),
so seeding twice does not duplicate.
"""

from __future__ import annotations

import argparse
import os
import sys

_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, _ROOT)

from anima import lerf                                  # noqa: E402
from anima.lerf import make_skill, ACTIVE               # noqa: E402


# Stable ids so re-seeding updates-in-place rather than duplicating.
def _seed_skills() -> list:
    return [
        make_skill(
            "summarize_medical_appointment", "health", id="skill_med_appt", state=ACTIVE,
            inputs=["raw doctor's note, visit summary, or appointment transcript"],
            steps=[
                "Identify the assessment/diagnosis and the patient's main concern.",
                "Extract EVERY medication with its exact dosage, frequency, and timing — "
                "copy numbers verbatim, never round or guess.",
                "Extract every instruction (diet, activity, what to avoid) as a concrete action.",
                "List every follow-up, lab, or test WITH its date/timeframe.",
                "Note any stated warning signs ('call us if…') as conditional reminders.",
                "Write a 3-4 sentence plain-language summary a worried person can absorb.",
            ],
            outputs=["plain-language summary", "medication list (drug, dose, schedule)",
                     "action/instruction list", "follow-up & lab list with dates",
                     "warning-sign reminders"],
            failure_modes=[
                "Dropping or rounding a dosage number (10mg becomes '10' or 'some').",
                "Confusing two medications or attaching the wrong dose to a drug.",
                "Losing a follow-up date, so the reminder never fires.",
                "Soothing/editorialising instead of reporting what the doctor actually said.",
            ]),
        make_skill(
            "extract_reminders_from_note", "productivity", id="skill_reminders", state=ACTIVE,
            inputs=["a freeform note, message, or transcript that may contain commitments"],
            steps=[
                "Scan for any commitment, deadline, or thing-to-do, explicit or implied.",
                "For each, resolve the WHEN to a concrete date/time if one is stated or "
                "derivable ('next Friday', 'in two weeks'); otherwise mark it undated.",
                "Phrase each as a short imperative ('Call the dentist', not 'dentist stuff').",
                "Drop anything that is not actually actionable (musings, FYIs).",
                "Flag any reminder whose timing is ambiguous so it can be confirmed, "
                "rather than inventing a time.",
            ],
            outputs=["list of reminders (text, due-date-or-undated, source-quote)",
                     "list of ambiguous-timing items needing confirmation"],
            failure_modes=[
                "Inventing a specific time the note never stated (confabulated due date).",
                "Turning a passing mention ('I should really read more') into a task.",
                "Missing an implicit deadline ('before the trip') because it isn't a date.",
            ]),
        make_skill(
            "plan_errands", "logistics", id="skill_errands", state=ACTIVE,
            inputs=["list of stops (place + rough address/area)", "start location",
                    "any time constraints or opening hours"],
            steps=[
                "Group stops by geographic area to avoid crossing town twice.",
                "Within and across groups, order to minimise total backtracking "
                "(nearest-neighbour from the start, then refine obvious swaps).",
                "Respect hard constraints: opening hours, appointment times, frozen-goods-last.",
                "Surface the ordered route with a one-line reason for the ordering.",
                "Flag any stop that can't be fit within its constraints rather than silently "
                "dropping it.",
            ],
            outputs=["ordered list of stops", "short rationale", "list of infeasible stops"],
            failure_modes=[
                "Ignoring opening hours and routing to a closed shop.",
                "Optimising distance only, putting frozen/perishable stops first.",
                "Assuming an address when the input only gave a vague area.",
            ]),
        make_skill(
            "summarize_legal_document", "legal", id="skill_legal_doc", state=ACTIVE,
            inputs=["a contract, lease, agreement, or legal letter (full text)"],
            steps=[
                "Identify the PARTIES and their roles (who owes what to whom).",
                "Extract every OBLIGATION each party takes on, in plain language.",
                "Extract every DEADLINE, notice period, term length, and renewal/auto-renew clause.",
                "Extract every PENALTY, fee, liability cap, and termination condition.",
                "Note anything unusual, one-sided, or that limits the reader's rights.",
                "Preserve exact figures, dates, and durations verbatim — never paraphrase a number.",
                "State explicitly that this is a summary, not legal advice.",
            ],
            outputs=["parties & roles", "obligations per party", "deadlines & key dates",
                     "penalties & fees", "red-flag clauses", "verbatim-figures note"],
            failure_modes=[
                "Dropping an obligation or deadline — the most damaging possible error here.",
                "Softening a penalty ('a fee may apply' when it's '$500 per day').",
                "Paraphrasing a number or date and changing it.",
                "Presenting the summary as legal advice or a guarantee of completeness.",
            ]),
        make_skill(
            "draft_followup_email", "communication", id="skill_followup_email", state=ACTIVE,
            inputs=["who the email is to + relationship", "the context/last interaction",
                    "the goal of the follow-up", "any deadline"],
            steps=[
                "Open with a specific, non-generic reference to the last interaction.",
                "State the purpose in the first two sentences (respect the reader's time).",
                "Make the ask concrete and singular, with a clear date if one applies.",
                "Match tone to the relationship (warm-direct for a peer, more formal for a stranger).",
                "Keep it short; end with a clear, low-friction next step.",
                "Never assert a fact about the recipient you weren't given.",
            ],
            outputs=["subject line", "email body", "one-line summary of the ask"],
            failure_modes=[
                "Being vague about the actual ask, so nothing happens.",
                "Wrong register (over-familiar with a stranger, stiff with a friend).",
                "Inventing details of the prior conversation that weren't provided.",
                "Burying the request under pleasantries.",
            ]),
        make_skill(
            "triage_inbox", "productivity", id="skill_triage_inbox", state=ACTIVE,
            inputs=["a batch of messages/emails (sender, subject, snippet)",
                    "what the user cares about / is waiting on"],
            steps=[
                "Classify each message: needs-reply, needs-action, FYI, or noise.",
                "For needs-reply/action, estimate urgency from deadlines and sender importance.",
                "Detect anything time-sensitive (today/tomorrow) and surface it first.",
                "Group the rest so the user can batch (e.g. all newsletters together).",
                "Produce a ranked 'do these first' shortlist with a one-line why for each.",
                "Never auto-dismiss a message from a person the user flagged as important.",
            ],
            outputs=["ranked action shortlist (msg, why, suggested action)",
                     "FYI bucket", "noise/archive bucket"],
            failure_modes=[
                "Mislabelling an important personal message as noise (false-negative — the worst).",
                "Over-flagging everything urgent, which is the same as flagging nothing.",
                "Ignoring a stated 'I'm waiting on X' priority.",
            ]),
        make_skill(
            "extract_action_items", "productivity", id="skill_action_items", state=ACTIVE,
            inputs=["a meeting transcript, call notes, or a long thread"],
            steps=[
                "Find every decision made and every task assigned.",
                "For each task capture: WHAT, WHO owns it, and the DUE date if stated.",
                "Separate firm commitments from things merely discussed or proposed.",
                "Note open questions that block a task (so they can be chased).",
                "Mark any task with no clear owner as unassigned rather than guessing one.",
            ],
            outputs=["action items (task, owner, due-or-none)", "decisions made",
                     "open questions / blockers", "unassigned items needing an owner"],
            failure_modes=[
                "Assigning an owner the transcript never named (confabulated accountability).",
                "Recording a hypothetical ('we could maybe…') as a committed task.",
                "Losing the due date, so the item drifts.",
            ]),
        make_skill(
            "compare_options", "decision_support", id="skill_compare_options", state=ACTIVE,
            inputs=["two or more options", "what the user is optimising for (criteria/priorities)"],
            steps=[
                "Pin down the criteria that actually matter to THIS user (ask if unstated).",
                "Build a like-for-like comparison across those criteria, not a feature dump.",
                "Note the key trade-off each option forces (its best case and its cost).",
                "Call out any dealbreaker that removes an option outright.",
                "Give a tentative recommendation tied to the stated priorities — and say what "
                "would change it — without pretending there's one objective answer.",
            ],
            outputs=["criteria used", "per-option strengths/weaknesses", "key trade-offs",
                     "tentative recommendation + what would change it"],
            failure_modes=[
                "Comparing on generic specs instead of what the user actually cares about.",
                "Hiding the trade-off and presenting a winner as obvious.",
                "Stating a preference as fact rather than tied to the user's priorities.",
            ]),
        make_skill(
            "explain_concept_simply", "education", id="skill_explain_simply", state=ACTIVE,
            inputs=["the concept to explain", "the audience's current level / what they know"],
            steps=[
                "Start from something the audience already understands (an anchor/analogy).",
                "Give the one-sentence core idea before any detail.",
                "Build up in small steps, defining each new term as it appears.",
                "Use a concrete example, then state the general rule.",
                "Pre-empt the most common misunderstanding of this concept explicitly.",
                "Keep the analogy honest — flag where it breaks down rather than over-stretching it.",
            ],
            outputs=["one-sentence core idea", "stepped explanation", "worked example",
                     "the common misunderstanding, addressed"],
            failure_modes=[
                "Using jargon to explain jargon (assuming the thing being taught).",
                "An analogy that's memorable but actually wrong, planting a misconception.",
                "Burying the core idea under caveats.",
            ]),
        make_skill(
            "prep_for_meeting", "productivity", id="skill_prep_meeting", state=ACTIVE,
            inputs=["who the meeting is with", "the purpose/desired outcome",
                    "relevant history or open threads", "time available"],
            steps=[
                "State the single outcome that would make this meeting a success.",
                "Pull the relevant history and any open items with this person/group.",
                "Draft a tight agenda ordered by importance, time-boxed to fit.",
                "List the decisions you need from them and the questions to ask.",
                "Anticipate likely objections/concerns and a response to each.",
                "Identify the one thing that must not be forgotten.",
            ],
            outputs=["success outcome", "agenda (time-boxed)", "decisions needed & questions",
                     "anticipated objections + responses", "the must-not-forget item"],
            failure_modes=[
                "A laundry-list agenda with no priority, so the key item gets cut by the clock.",
                "Walking in without the relevant history and re-litigating settled points.",
                "No explicit ask, so the meeting ends without a decision.",
            ]),
    ]


def seed(creature: str) -> list:
    skills = _seed_skills()
    for sk in skills:
        lerf.store_skill(sk, name=creature)
    return skills


def _print_skills(creature: str) -> None:
    skills = lerf.all_skills(name=creature, include_nonactive=True)
    skills.sort(key=lambda s: s.get("name", ""))
    print(f"\nLERF store for creature '{creature}' — {len(skills)} skill(s):\n")
    print(f"  {'NAME':<32}  {'DOMAIN':<16}  STATE     CONF  STEPS  FAILURE-MODES")
    print("  " + "-" * 86)
    for s in skills:
        print(f"  {s['name']:<32}  {s.get('domain',''):<16}  "
              f"{s.get('state',''):<8}  {s.get('confidence',0):.2f}  "
              f"{len(s.get('steps',[])):>4}   {len(s.get('failure_modes',[])):>4}")
    st = lerf.stats(name=creature)
    print(f"\n  totals: {st['total']} objects  by_type={st['by_type']}  by_state={st['by_state']}")

    # show one fully-rendered skill so the INSPECTABILITY is visible on seed.
    if skills:
        demo = next((s for s in skills if s["name"] == "summarize_medical_appointment"), skills[0])
        print("\n  --- explain_skill (inspectable, unlike a weight tensor) ---\n")
        for line in lerf.explain_skill(demo, name=creature).splitlines():
            print("  " + line)


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(description="Seed and show the LERF skill store.")
    ap.add_argument("--creature", default="default",
                    help="creature name -> .anima/{creature}.lerf.json (default: 'default')")
    ap.add_argument("--show", action="store_true",
                    help="only print what is already stored; do not seed/write")
    args = ap.parse_args(argv)

    if not args.show:
        seeded = seed(args.creature)
        print(f"Seeded {len(seeded)} skills into .anima/{args.creature}.lerf.json "
              f"(state=active, hand-verified).")
    _print_skills(args.creature)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

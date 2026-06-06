#!/usr/bin/env python3
"""lerf_utilization — the metric that measures THE SHIFT.

THE QUESTION. The whole point of wiring LERF into the live reply path is to flip the
default: from "every turn goes to the LLM, LERF is a library" to "the certified cognitive
substrate solves the turn FIRST, and the LLM is the last resort." This script measures how
far that flip has gone, from the per-turn route ledger the live mouth writes
(.anima/{name}.lerf_routes.jsonl — one structured line per turn).

THE HEADLINE NUMBER.

    LERF Utilization Rate = % of requests SOLVED BY LERF before the model is reached.

"Solved by LERF" means a certified ACTIVE skill rendered the answer locally and it PASSED
the grounded verifier — the LLM/cloud was never spent for that turn. Today this rate is ~0
(LERF solved nothing on the hot path); the goal trajectory is 0 -> 25 -> 50 -> 75 -> 90%.

ALSO REPORTED, because a single rate hides the economics:
  * the route MIX — % solved by LERF / % partial (LERF tried, verifier withheld -> LLM) /
    % LLM-required (genuine reasoning, no skill) — plus the memory/deterministic rungs.
  * % PROMPT-TOKEN reduction vs the all-LLM baseline (the substrate's compression win).
  * % LATENCY reduction vs the all-LLM baseline.
  * % COST reduction vs the all-LLM baseline (cloud $ avoided + local tokens saved).
  * where we ARE on the 0/25/50/75/90% goal trajectory.

This reader is LIGHTWEIGHT and READ-ONLY: it never writes the ledger, never calls a model,
and tolerates a missing/partly-malformed ledger (a bad line is skipped, not fatal). The
`--selftest` proves the rate computes on synthetic records with NO real ledger and NO real
.anima touched.

    python3 scripts/lerf_utilization.py                 # the default creature's ledger
    python3 scripts/lerf_utilization.py --name Nova     # a specific creature
    python3 scripts/lerf_utilization.py --json          # machine-readable
    python3 scripts/lerf_utilization.py --selftest      # synthetic proof, no real data
"""
from __future__ import annotations

import argparse
import json
import os
import sys
from pathlib import Path

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

STORE = Path(".anima")

# The goal trajectory for the LERF Utilization Rate (the user's milestones).
GOAL_TRAJECTORY = (0, 25, 50, 75, 90)

# Indicative cost weights for the cost-reduction estimate (deterministic, not billed currency).
# A cloud turn costs dollars + data egress; a local turn costs only its prompt tokens at a tiny
# per-token rate. The RATIO is what matters and both baseline and actual use the SAME weights.
_CLOUD_CALL_COST = 1.0          # one avoided cloud call ~= one unit (the dominant term)
_LOCAL_TOKEN_COST = 0.000002    # a local prompt token ~= negligible vs a cloud call


def _read_ledger(path: Path) -> list[dict]:
    """Load a route ledger (JSONL). Read-only + tolerant: a missing file is an empty ledger,
    and a single malformed line is skipped rather than aborting the whole report."""
    rows: list[dict] = []
    if not path.is_file():
        return rows
    try:
        with open(path, "r", encoding="utf-8") as fh:
            for line in fh:
                line = line.strip()
                if not line:
                    continue
                try:
                    obj = json.loads(line)
                    if isinstance(obj, dict):
                        rows.append(obj)
                except (json.JSONDecodeError, ValueError):
                    continue
    except OSError:
        return rows
    return rows


def _solver_of(rec: dict) -> str:
    """Normalise a record to one of the rung buckets used by the report. Prefers the explicit
    `solver` field the live ledger writes; falls back to inferring from `route`/`llm_required`."""
    s = rec.get("solver")
    if s in ("lerf_skill", "lirf_memory", "deterministic_rule", "llm", "cloud"):
        return s
    route = str(rec.get("route", ""))
    if route in ("lerf_skill",) and rec.get("solved"):
        return "lerf_skill"
    if route.startswith("lerf_skill_then_llm") or route == "llm":
        return "llm" if rec.get("llm_required", True) else "lerf_skill"
    if route in ("lirf_memory", "deterministic_rule", "cloud"):
        return route
    return "llm" if rec.get("llm_required", True) else "lerf_skill"


def compute(rows: list[dict]) -> dict:
    """The full metric over a list of route records. Pure arithmetic — no I/O.

    Returns a dict with the utilization rate, the route mix, the token/latency/cost deltas vs
    the all-LLM baseline, and the goal-trajectory position. Safe on an empty ledger (zeros)."""
    n = len(rows)
    out = {
        "turns": n,
        "lerf_solved": 0,            # certified skill rendered + verified locally (LLM not reached)
        "lerf_partial": 0,           # LERF tried but verifier withheld -> escalated to LLM
        "lirf_memory": 0,            # a stored fact answered (memory rung)
        "deterministic": 0,          # code answered (capability rung)
        "llm_required": 0,           # genuine reasoning, no skill -> the LLM as last resort
        "cloud": 0,                  # a cloud brain was spent
    }
    if n == 0:
        out.update({
            "lerf_utilization_rate": 0.0, "lerf_solved_pct": 0.0, "lerf_partial_pct": 0.0,
            "llm_required_pct": 0.0, "memory_pct": 0.0, "deterministic_pct": 0.0,
            "token_reduction_pct": 0.0, "latency_reduction_pct": 0.0, "cost_reduction_pct": 0.0,
            "tokens_used": 0, "tokens_baseline": 0, "ms_used": 0.0, "ms_baseline": 0.0,
            "trajectory": _trajectory(0.0),
        })
        return out

    tokens_used = tokens_baseline = 0
    ms_used = ms_baseline = 0.0
    cost_used = cost_baseline = 0.0
    for rec in rows:
        solver = _solver_of(rec)
        if solver == "lerf_skill":
            out["lerf_solved"] += 1
        elif solver == "lirf_memory":
            out["lirf_memory"] += 1
        elif solver == "deterministic_rule":
            out["deterministic"] += 1
        elif solver == "cloud":
            out["cloud"] += 1
            out["llm_required"] += 1
        else:
            out["llm_required"] += 1
        # a partial = LERF was attempted (it has an lerf_attempt or a then_llm route) yet the
        # turn was NOT lerf-solved. Counts the substrate's near-misses (verifier-withheld).
        if solver != "lerf_skill" and (
                str(rec.get("route", "")).startswith("lerf_skill_then_llm")
                or rec.get("lerf_attempt")):
            out["lerf_partial"] += 1

        # tokens: what this turn actually paid vs the all-LLM baseline for the same turn.
        baseline = int(rec.get("llm_baseline_tokens", rec.get("prompt_tokens", 0)) or 0)
        actual = int(rec.get("prompt_tokens", baseline) or 0)
        tokens_baseline += baseline
        tokens_used += actual

        # latency: the measured turn cost vs an estimate of the all-LLM cost. When a turn was
        # LERF-solved we have its real local latency; the baseline is the same turn's would-be
        # LLM cost, estimated as the observed LLM-path mean (filled below if unknown).
        used_ms = float(rec.get("total_ms", rec.get("latency_ms", 0.0)) or 0.0)
        ms_used += used_ms

        # cost: a cloud turn pays the cloud-call cost; a local turn pays only its tokens. The
        # baseline assumes the all-LLM world routes the SAME turn to its model.
        if solver == "cloud":
            cost_used += _CLOUD_CALL_COST
        else:
            cost_used += actual * _LOCAL_TOKEN_COST
        cost_baseline += baseline * _LOCAL_TOKEN_COST + (
            _CLOUD_CALL_COST if solver == "cloud" else 0.0)

    # latency baseline: estimate each turn's all-LLM cost as the mean observed LLM-path turn
    # (the turns that actually reached the model). If none did, fall back to the overall mean so
    # the figure is defined; the reduction is then ~0 (honest: nothing was offloaded yet).
    llm_ms = [float(r.get("total_ms", r.get("latency_ms", 0.0)) or 0.0)
              for r in rows if _solver_of(r) in ("llm", "cloud")]
    mean_llm_ms = (sum(llm_ms) / len(llm_ms)) if llm_ms else (ms_used / n)
    ms_baseline = mean_llm_ms * n

    solved = out["lerf_solved"]
    rate = 100.0 * solved / n
    out["lerf_utilization_rate"] = round(rate, 1)
    out["lerf_solved_pct"] = round(rate, 1)
    out["lerf_partial_pct"] = round(100.0 * out["lerf_partial"] / n, 1)
    out["llm_required_pct"] = round(100.0 * out["llm_required"] / n, 1)
    out["memory_pct"] = round(100.0 * out["lirf_memory"] / n, 1)
    out["deterministic_pct"] = round(100.0 * out["deterministic"] / n, 1)
    out["tokens_used"] = tokens_used
    out["tokens_baseline"] = tokens_baseline
    out["token_reduction_pct"] = round(
        100.0 * (tokens_baseline - tokens_used) / tokens_baseline, 1) if tokens_baseline else 0.0
    out["ms_used"] = round(ms_used, 1)
    out["ms_baseline"] = round(ms_baseline, 1)
    out["latency_reduction_pct"] = round(
        100.0 * (ms_baseline - ms_used) / ms_baseline, 1) if ms_baseline else 0.0
    out["cost_reduction_pct"] = round(
        100.0 * (cost_baseline - cost_used) / cost_baseline, 1) if cost_baseline else 0.0
    out["trajectory"] = _trajectory(rate)
    return out


def _trajectory(rate: float) -> dict:
    """Where `rate` sits on the 0/25/50/75/90% goal milestones: the last milestone reached and
    the next one to aim for, with the gap to it."""
    reached = max((m for m in GOAL_TRAJECTORY if rate >= m), default=0)
    nxt = next((m for m in GOAL_TRAJECTORY if m > rate), None)
    return {
        "milestones": list(GOAL_TRAJECTORY),
        "reached": reached,
        "next": nxt,
        "gap_to_next": (round(nxt - rate, 1) if nxt is not None else 0.0),
        "at_goal": nxt is None,
    }


def _bar(pct: float, width: int = 40) -> str:
    fill = int(round((max(0.0, min(100.0, pct)) / 100.0) * width))
    return "█" * fill + "·" * (width - fill)


def render(m: dict, name: str) -> str:
    """The human-readable report — the headline rate, the route mix, the deltas, the ladder."""
    L = []
    L.append("=" * 70)
    L.append("LERF UTILIZATION RATE  ::  is the substrate solving turns before the LLM?")
    L.append("=" * 70)
    L.append(f"creature: {name}    turns in ledger: {m['turns']}")
    L.append("")
    rate = m["lerf_utilization_rate"]
    L.append(f"  LERF UTILIZATION RATE : {rate:5.1f}%   {_bar(rate)}")
    L.append(f"  (LERF solved the turn locally + grounded-verified; the LLM was NOT reached)")
    L.append("")
    L.append("  ROUTE MIX (who solved the turn):")
    L.append(f"    LERF skill (solved)   : {m['lerf_solved_pct']:5.1f}%   {_bar(m['lerf_solved_pct'])}")
    L.append(f"    LIRF memory (a fact)  : {m['memory_pct']:5.1f}%   {_bar(m['memory_pct'])}")
    L.append(f"    deterministic (code)  : {m['deterministic_pct']:5.1f}%   {_bar(m['deterministic_pct'])}")
    L.append(f"    LERF partial -> LLM   : {m['lerf_partial_pct']:5.1f}%   {_bar(m['lerf_partial_pct'])}")
    L.append(f"    LLM required (reason) : {m['llm_required_pct']:5.1f}%   {_bar(m['llm_required_pct'])}")
    L.append("")
    L.append("  SAVINGS vs the all-LLM baseline (same turns, routed to the model):")
    L.append(f"    prompt tokens reduced : {m['token_reduction_pct']:5.1f}%   "
             f"({m['tokens_used']} used vs {m['tokens_baseline']} baseline)")
    L.append(f"    latency reduced       : {m['latency_reduction_pct']:5.1f}%   "
             f"({m['ms_used']:.0f}ms vs {m['ms_baseline']:.0f}ms)")
    L.append(f"    cost reduced          : {m['cost_reduction_pct']:5.1f}%   "
             f"(cloud calls avoided + local tokens saved)")
    L.append("")
    t = m["trajectory"]
    marks = "  ".join(
        (f"[{ms}]" if ms == t["reached"] and rate >= ms else f" {ms} ") for ms in t["milestones"])
    L.append("  GOAL TRAJECTORY (0 -> 25 -> 50 -> 75 -> 90%):")
    L.append(f"    {marks}")
    if t["at_goal"]:
        L.append(f"    >>> AT GOAL: {rate:.1f}% >= 90%. The substrate is the primary mind.")
    else:
        L.append(f"    >>> at {rate:.1f}%; next milestone {t['next']}%  (need +{t['gap_to_next']:.1f} pts)")
    L.append("=" * 70)
    return "\n".join(L)


# ===================================================================================
# SELFTEST — synthetic route records prove the rate (and every delta) computes, with NO
# real ledger read and NO real .anima touched. Mirrors the repo's selftest discipline.
# ===================================================================================

def _selftest() -> int:
    fails: list[str] = []

    def ok(label: str, cond: bool) -> None:
        print(("  ok   " if cond else "  FAIL ") + label)
        if not cond:
            fails.append(label)

    print("lerf_utilization self-test")

    # --- empty ledger is safe and reads 0% (the honest starting point) -----------------
    z = compute([])
    ok("empty ledger -> 0% utilization, no crash", z["lerf_utilization_rate"] == 0.0
       and z["turns"] == 0)
    ok("empty ledger -> trajectory next milestone is 25", z["trajectory"]["next"] == 25)

    # --- a synthetic 10-turn ledger: 5 LERF-solved, 1 partial, 2 memory, 1 deterministic,
    #     1 genuine LLM. Hand-built so every bucket and every delta is checkable by hand. ---
    syn = []
    # 5 LERF-solved task turns: cheap local prompt (120) vs a heavy all-LLM baseline (600).
    for i in range(5):
        syn.append({"solver": "lerf_skill", "route": "lerf_skill", "solved": True,
                    "llm_required": False, "prompt_tokens": 120, "llm_baseline_tokens": 600,
                    "total_ms": 300.0, "grounded": True})
    # 1 partial: LERF tried, verifier withheld, escalated to the LLM (pays the full baseline).
    syn.append({"solver": "llm", "route": "lerf_skill_then_llm", "solved": False,
                "llm_required": True, "prompt_tokens": 600, "llm_baseline_tokens": 600,
                "total_ms": 1800.0, "lerf_attempt": {"outcome": "verifier_withheld"}})
    # 2 memory turns (a fact answered) and 1 deterministic (code answered).
    syn.append({"solver": "lirf_memory", "route": "lirf_memory", "solved": True,
                "llm_required": False, "prompt_tokens": 400, "llm_baseline_tokens": 600,
                "total_ms": 250.0})
    syn.append({"solver": "lirf_memory", "route": "lirf_memory", "solved": True,
                "llm_required": False, "prompt_tokens": 400, "llm_baseline_tokens": 600,
                "total_ms": 250.0})
    syn.append({"solver": "deterministic_rule", "route": "deterministic_rule", "solved": True,
                "llm_required": False, "prompt_tokens": 50, "llm_baseline_tokens": 600,
                "total_ms": 20.0})
    # 1 genuine reasoning turn -> the LLM as last resort (pays the full baseline).
    syn.append({"solver": "llm", "route": "llm", "solved": False, "llm_required": True,
                "prompt_tokens": 600, "llm_baseline_tokens": 600, "total_ms": 1800.0})

    m = compute(syn)
    ok("10 turns counted", m["turns"] == 10)
    ok("LERF utilization rate is 50.0% (5 of 10 solved by LERF)",
       m["lerf_utilization_rate"] == 50.0)
    ok("route mix: 5 lerf-solved", m["lerf_solved"] == 5)
    ok("route mix: 1 partial (verifier-withheld -> LLM)", m["lerf_partial"] == 1)
    ok("route mix: 2 memory", m["lirf_memory"] == 2)
    ok("route mix: 1 deterministic", m["deterministic"] == 1)
    ok("route mix: 2 LLM-required (the partial + the genuine reasoning turn)",
       m["llm_required"] == 2)
    # token reduction: used = 5*120 + 600 + 400 + 400 + 50 + 600 = 2650; baseline = 10*600 = 6000.
    ok("tokens_used == 2650 (hand-summed)", m["tokens_used"] == 2650)
    ok("tokens_baseline == 6000 (10 turns * 600)", m["tokens_baseline"] == 6000)
    ok("token reduction == 55.8% ((6000-2650)/6000)", m["token_reduction_pct"] == 55.8)
    ok("token reduction is in (0,100)", 0.0 < m["token_reduction_pct"] < 100.0)
    ok("latency reduction is positive (LERF turns are faster than the LLM baseline)",
       m["latency_reduction_pct"] > 0.0)
    ok("cost reduction is positive (no cloud spent; local tokens saved)",
       m["cost_reduction_pct"] > 0.0)
    ok("trajectory: 50% reached the 50 milestone, next is 75",
       m["trajectory"]["reached"] == 50 and m["trajectory"]["next"] == 75)

    # --- a 90%+ ledger trips the at-goal branch -----------------------------------------
    hi = [{"solver": "lerf_skill", "route": "lerf_skill", "solved": True, "llm_required": False,
           "prompt_tokens": 100, "llm_baseline_tokens": 600, "total_ms": 300.0}
          for _ in range(9)]
    hi.append({"solver": "llm", "route": "llm", "solved": False, "llm_required": True,
               "prompt_tokens": 600, "llm_baseline_tokens": 600, "total_ms": 1800.0})
    mh = compute(hi)
    ok("90% utilization trips the at-goal trajectory branch",
       mh["lerf_utilization_rate"] == 90.0 and mh["trajectory"]["at_goal"] is True)

    # --- the JSONL reader tolerates a malformed line without aborting -------------------
    import tempfile
    td = tempfile.mkdtemp(prefix="lerfutil-self-")
    p = Path(td) / "x.lerf_routes.jsonl"
    p.write_text(
        json.dumps(syn[0]) + "\n" + "{ this is not json\n" + json.dumps(syn[1]) + "\n",
        encoding="utf-8")
    rows = _read_ledger(p)
    ok("reader skips a malformed line, keeps the 2 good ones", len(rows) == 2)
    ok("reader on a missing file returns an empty ledger (no crash)",
       _read_ledger(Path(td) / "nope.jsonl") == [])
    import shutil
    shutil.rmtree(td, ignore_errors=True)

    # --- the renderer produces the headline without raising ----------------------------
    txt = render(m, "selftest")
    ok("render emits the headline rate and the trajectory",
       "LERF UTILIZATION RATE" in txt and "GOAL TRAJECTORY" in txt)

    print()
    if fails:
        print(f"{len(fails)} FAILED: " + ", ".join(fails))
        return 1
    print("ALL LERF_UTILIZATION SELFTESTS PASS")
    return 0


def main() -> int:
    ap = argparse.ArgumentParser(description="LERF Utilization Rate — read the per-turn route ledger.")
    ap.add_argument("--name", default="default", help="creature name (ledger .anima/{name}.lerf_routes.jsonl)")
    ap.add_argument("--json", action="store_true", help="emit the metric as JSON")
    ap.add_argument("--selftest", action="store_true", help="run the synthetic self-test (no real data)")
    args = ap.parse_args()
    if args.selftest:
        return _selftest()
    path = STORE / f"{args.name}.lerf_routes.jsonl"
    rows = _read_ledger(path)
    m = compute(rows)
    if args.json:
        print(json.dumps({"name": args.name, "ledger": str(path), **m}, indent=2))
    else:
        if not rows:
            print(f"(no route ledger yet at {path} — the live mouth writes one line per turn; "
                  f"run some turns, then re-run this.)")
        print(render(m, args.name))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

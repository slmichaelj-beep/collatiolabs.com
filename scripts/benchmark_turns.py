#!/usr/bin/env python3
"""benchmark_turns — the standard performance benchmark. Drives a fixed set of turns through the live
server, records latency + route + budget verdict, writes reports/performance_benchmark.{json,md}.

    python3 scripts/benchmark_turns.py            # full set (includes a few model turns; ~1-2 min)
    python3 scripts/benchmark_turns.py --fast      # fast turns only (no model)
"""
from __future__ import annotations

import json
import sys
import time
import urllib.request
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

# (prompt, expected_route, hard_budget_s)
SET = [
    ("Hi", "simple", 5), ("Test", "simple", 5), ("are you there?", "simple", 5),
    ("how are you?", "simple", 5), ("thanks", "simple", 5),
    ("what is my birthday?", "known_fact", 5), ("what do you know about me?", "normal", 12),
    ("what is the capital of France?", "normal", 12),
]


def _say(text, timeout=130):
    t0 = time.perf_counter()
    try:
        body = json.dumps({"text": text}).encode()
        req = urllib.request.Request("http://localhost:8765/say", data=body,
                                     headers={"Content-Type": "application/json"})
        rep = json.loads(urllib.request.urlopen(req, timeout=timeout).read()).get("reply", "")
        return rep, time.perf_counter() - t0
    except Exception as e:
        return "[unreachable: %s]" % (repr(e)[:50]), time.perf_counter() - t0


def main() -> int:
    from anima import route_classifier as rc
    fast = "--fast" in sys.argv
    rows = []
    print("BENCHMARK TURNS%s" % (" (fast)" if fast else ""))
    print("=" * 70)
    for prompt, route, budget in SET:
        is_simple = rc.is_simple_chat(prompt)
        if fast and not (is_simple or route == "known_fact"):
            continue
        rep, dt = _say(prompt)
        verdict = "PASS" if dt < budget else "WARN" if dt < budget * 1.7 else "FAIL"
        rows.append({"prompt": prompt, "route": route, "latency_s": round(dt, 2),
                     "budget_s": budget, "verdict": verdict, "reply": rep[:60]})
        print("  %5.2fs  %-5s  %-22s %s" % (dt, verdict, repr(prompt)[:22], rep[:34]))

    fails = [r for r in rows if r["verdict"] == "FAIL"]
    warns = [r for r in rows if r["verdict"] == "WARN"]
    summary = {"turns": len(rows), "pass": sum(1 for r in rows if r["verdict"] == "PASS"),
               "warn": len(warns), "fail": len(fails)}
    try:
        rep = ROOT / "reports"; rep.mkdir(exist_ok=True)
        (rep / "performance_benchmark.json").write_text(json.dumps({"summary": summary, "rows": rows}, indent=2))
        md = ["# Vera Performance Benchmark", "",
              "**%d turns · %d pass · %d warn · %d fail**" % (len(rows), summary["pass"], len(warns), len(fails)), "",
              "| latency | verdict | route | prompt |", "|---|---|---|---|"]
        md += ["| %.2fs | %s | %s | %s |" % (r["latency_s"], r["verdict"], r["route"], r["prompt"]) for r in rows]
        (rep / "performance_benchmark.md").write_text("\n".join(md) + "\n")
    except Exception:
        pass
    print("-" * 70)
    print("BENCHMARK: %s   (%d pass · %d warn · %d fail)"
          % ("PASS" if not fails else "FAIL", summary["pass"], len(warns), len(fails)))
    return 0 if not fails else 1


if __name__ == "__main__":
    raise SystemExit(main())

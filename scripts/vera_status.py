#!/usr/bin/env python3
"""
vera_status — the ONE founder command: the whole honest state of Vera, in a glance.

Ties together everything the self-knowledge subsystem produces, so "how is Vera, really?" is a single
command instead of five:

  * HONESTY      — the Program Reality Audit verdict (does any feature lie about itself?)
  * THE MIND     — System Shape (what kind of mind is this becoming?)
  * KNOWS YOU    — the Personal Digital Twin (what is grounded about the person?)
  * IMPROVING    — the Improvement Backlog (work orders certified vs. open)
  * PORTABLE     — the Portable Mind (how much of the mind can be carried out, round-trip)
  * DEPLOYED     — is the live server running exactly the committed code? (LAW 005)

Each line is sourced from a real store/report and is honest when empty — never a flattering guess.
Pure + read-only: composes the existing modules + reports, hits the live /version for deploy state.
Never a model, never a store mutation.

    python3 scripts/vera_status.py                 # the founder glance
    python3 scripts/vera_status.py --name Vera --json
"""
from __future__ import annotations

import argparse
import json
import sys
import urllib.request
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))


def _deploy_state() -> dict:
    """Is the live server running exactly the committed code? (read-only; never restarts anything)."""
    import subprocess
    try:
        head = subprocess.run(["git", "rev-parse", "--short", "HEAD"], cwd=str(ROOT),
                              capture_output=True, text=True).stdout.strip()
    except Exception:
        head = "?"
    running = None
    try:
        with urllib.request.urlopen("http://127.0.0.1:8765/version", timeout=4) as r:
            running = json.loads(r.read().decode("utf-8")).get("sha")
    except Exception:
        running = None
    return {"head": head, "running": running,
            "green": bool(running and running == head), "up": running is not None}


def compose(name: str = "Vera") -> dict:
    from anima import system_shape, twin_dashboard, portable, improvement_engine as ie
    shape = system_shape.compose()
    twin = twin_dashboard.compose(name)
    bundle = portable.export_mind(name)
    pc = bundle["manifest"]["counts"]
    backlog = ie.stats(ie.load_backlog())
    return {
        "person": name,
        "honesty": next((d for d in shape["dimensions"] if d["key"] == "honesty"), {}),
        "mind": {"headline": shape["headline_status"], "synthesis": shape["synthesis"]},
        "knows_you": {"richness": twin["richness"], "synthesis": twin["synthesis"],
                      "coverage": twin["coverage"]},
        "improving": backlog,
        "portable": {"identity_facts": pc.get("identity_facts", 0),
                     "cognitive_objects": pc.get("cognitive_objects", 0),
                     "round_trip_layers": bundle["manifest"].get("round_trip_layers", [])},
        "deployed": _deploy_state(),
    }


def _print(s: dict) -> None:
    bar = "=" * 96
    dep = s["deployed"]
    print(bar)
    print(f"VERA — the whole honest state   ({s['person']})")
    print(bar)
    h = s["honesty"]
    print(f"  HONESTY    {('● ' + h.get('value','?')) if h.get('status')=='strong' else ('○ ' + h.get('value','?'))}")
    print(f"             {h.get('human','')}")
    print(f"  THE MIND   [{s['mind']['headline'].upper()}]  {s['mind']['synthesis']}")
    print(f"  KNOWS YOU  [{s['knows_you']['richness'].upper()}]  {s['knows_you']['synthesis']}")
    imp = s["improving"]
    print(f"  IMPROVING  {imp.get('certified',0)} certified · {imp.get('open_actionable',0)} open "
          f"({imp.get('total',0)} work orders tracked)")
    p = s["portable"]
    print(f"  PORTABLE   {p['identity_facts']} facts + {p['cognitive_objects']} cognitive objects "
          f"round-trip ({', '.join(p['round_trip_layers'])})")
    g = "● GREEN — running == committed" if dep["green"] else (
        "○ BEHIND — running != HEAD" if dep["up"] else "✗ DOWN — server not responding")
    print(f"  DEPLOYED   {g}   (HEAD {dep['head']}, running {dep['running'] or '—'})")
    print(bar)


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(description="The whole honest state of Vera, in one command.")
    ap.add_argument("--name", default="Vera")
    ap.add_argument("--json", action="store_true")
    args = ap.parse_args(argv)
    s = compose(args.name)
    if args.json:
        print(json.dumps(s, indent=2, ensure_ascii=False))
    else:
        _print(s)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

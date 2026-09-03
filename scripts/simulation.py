#!/usr/bin/env python3
"""COGNITIVE SIMULATION (CLI) — ask what WOULD / MIGHT / SHOULD happen, run it on a TWIN.

Phase 22 builds ON the Digital Twin (Phase 21): a twin is an ISOLATED FULL COPY of a creature's
mind under ``.anima/twins/{twin_id}/``; this is where Understanding -> Theory -> Simulation
becomes possible. Every command below runs an EXPERIMENT inside a twin and returns a MEASURED,
inspectable result — the real ``.anima`` and the real Vera identity are NEVER modified (every op
is wrapped in a freeze-guard that asserts the real mind is byte-UNCHANGED around it).

THE FOUR QUESTIONS (anima/simulation.py):
  decision     — "what SHOULD happen?"  project a decision Lamar faces, grounded in his PERSONAL
                 INTELLIGENCE (how he actually decides) + the WORLD MODEL of the situation.
  learning     — "what WOULD happen if we learned X for T?"  drive the twin forward through
                 synthetic learning under a growth MODE; project accumulation + calibration.
  architecture — "what WOULD happen if we changed the architecture?"  the flagship case measures
                 FMLGS vs keyword retrieval on the twin's vault (recall / latency / footprint).
  futures      — "what MIGHT happen?"  several variants -> the DISTRIBUTION/range of outcomes.
  happened     — "what HAPPENED in the twin?"  read the twin MRI after a run.
  ask          — the ROUTER: classify a natural question (WOULD/MIGHT/SHOULD/HAPPENED) and route it.

SAFETY. Commands against a REAL twin only READ-copy state into the twin; every op is
freeze-guarded. ``examples`` and ``--selftest`` run hermetically against a SYNTHETIC source in a
temp store (no real read) so they are pure illustrations, $0, no cloud.

    python3 scripts/simulation.py --selftest                 # hermetic; every engine; exits 0
    python3 scripts/simulation.py examples                   # one worked example of each (hermetic)
    python3 scripts/simulation.py decision <twin_id> --question "ship daily or polish for a month?" \
                                                     --option "ship daily" --option "polish for a month"
    python3 scripts/simulation.py learning <twin_id> --mode medium --periods 4
    python3 scripts/simulation.py architecture <twin_id>     # FMLGS vs keyword on the twin's vault
    python3 scripts/simulation.py futures <twin_id> --variants 5
    python3 scripts/simulation.py happened <twin_id>
    python3 scripts/simulation.py ask <twin_id> --question "what might happen if we keep learning?"
"""
import argparse
import json
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from anima import simulation as sim  # noqa: E402
from anima import twin               # noqa: E402


def _print(obj) -> None:
    print(json.dumps(obj, indent=2, ensure_ascii=False, default=str))


def _resolve_twin(twin_id: str) -> dict:
    man = twin.read_manifest(twin_id)
    if not man:
        print(f"no such twin: {twin_id}  (see: python3 scripts/twin.py list)", file=sys.stderr)
        raise SystemExit(2)
    return man


def _cmd_decision(args) -> int:
    man = _resolve_twin(args.twin_id)
    spec = {"question": args.question, "options": args.option or [],
            "constraints": args.constraint or []}
    res = sim.simulate_decision(man, spec, person=args.person)
    if args.json:
        _print(res)
    else:
        print(f"DECISION (what SHOULD happen?) — twin {res['twin_id']}")
        print(f"  Q: {res['decision']}")
        print(f"  personal model known: {res['personal_known']}  counts={res['profile_counts']}")
        print(f"  recommendation: {res['recommendation']}  (grounded={res['recommendation_grounded']})")
        for o in res["options"]:
            print(f"    option {o['option']!r}: score={o['score']} grounded={o['grounded']}")
            for r in o["reasons"][:3]:
                print(f"        • [{r['kind']}] matched {r['matched_on']} (+{r['points']}) "
                      f"<- {r['from']}")
        sit = res["situation"]
        print(f"  situation (internal-only): {len(sit.get('models', []))} causal model(s), "
              f"nodes={sit.get('nodes')}")
    return 0


def _cmd_learning(args) -> int:
    man = _resolve_twin(args.twin_id)
    plan = {"mode": args.mode, "periods": args.periods}
    if args.cycles is not None:
        plan["cycles"] = args.cycles
    res = sim.simulate_learning(man, plan)
    if args.json:
        _print(res)
    else:
        p = res["projection"]
        print(f"LEARNING (what WOULD happen if we learned X for T?) — twin {res['twin_id']}")
        print(f"  plan: {res['plan']['label']}  ({res['cycles']} cycles, $0, cloud={res['used_cloud']})")
        print(f"  cognitive objects: {p['objects_before']} -> {p['objects_after']} "
              f"(+{p['objects_gained']})")
        print(f"  reality records:   -> {p['reality_records_after']} "
              f"(+{p['reality_records_gained']})")
        for t in res["trajectory"]:
            print(f"    cycle {t['cycle']:>5}: {t['objects']} objects")
    return 0


def _cmd_architecture(args) -> int:
    man = _resolve_twin(args.twin_id)
    res = sim.simulate_architecture(man, args.change)
    if args.json:
        _print(res)
    else:
        print(f"ARCHITECTURE (what WOULD happen if we changed the architecture?) — twin {res['twin_id']}")
        print(f"  change: {res['change']}")
        m = res.get("measurement")
        if m and m.get("available"):
            print(f"  measured on {m['n_objects']} objects @ k={m['k']}:")
            print(f"    recall vs keyword: {m['recall_vs_keyword']}   "
                  f"recall vs exact cosine: {m['recall_vs_linear']}")
            print(f"    latency: fmlgs={m['latency_fmlgs_us']:.1f}us  "
                  f"keyword={m['latency_keyword_us']:.1f}us  "
                  f"(speedup vs keyword {m['speedup_vs_keyword']:.2f}x)")
            print(f"    footprint: {m['footprint_total_bytes']}B total "
                  f"({m['footprint_per_object_bytes']:.0f} B/object, levels={m['footprint_levels']})")
            print(f"    scored fraction: {m['scored_fraction']*100:.0f}% of the vault/query")
        print(f"  verdict: {res['verdict'].get('summary')}")
    return 0


def _cmd_futures(args) -> int:
    man = _resolve_twin(args.twin_id)
    res = sim.alternative_futures(man, variants=args.variants, base_cycles=args.base_cycles,
                                  seed=args.seed)
    if args.json:
        _print(res)
    else:
        d = res["distribution"]
        print(f"ALTERNATIVE FUTURES (what MIGHT happen?) — twin {res['twin_id']}")
        print(f"  {res['variants']} variants, seed={res['seed']}")
        if d:
            print(f"  range of accumulation: min={d['min']} median={d['median']} max={d['max']} "
                  f"(mean {d['mean']}, spread {d['range']})")
        for b in res["branches"]:
            print(f"    {b['variant']:>16}: {b['cycles']} cycles -> {b['objects_after']} objects "
                  f"(certifies={b['certifies']})")
    return 0


def _cmd_happened(args) -> int:
    man = _resolve_twin(args.twin_id)
    res = sim.what_happened(man)
    if args.json:
        _print(res)
    else:
        i = res["interior"]
        print(f"WHAT HAPPENED IN THE TWIN — twin {res['twin_id']}")
        print(f"  objects={i['objects']} active={i['active_objects']} "
              f"reality_records={i['reality_records']} world_links={i['world_links']}")
        print(f"  identity certifies={i['identity_certifies']} "
              f"ungrounded_self_claims={i['ungrounded_self_claims']}")
        gd = res.get("growth_dashboard", {})
        if gd.get("available"):
            print(f"  growth: total_objects={gd.get('total_objects')} "
                  f"utilization={gd.get('utilization')}")
    return 0


def _cmd_ask(args) -> int:
    man = _resolve_twin(args.twin_id)
    kwargs = {}
    if args.option or args.question_decision:
        kwargs["decision"] = {"question": args.question_decision or args.question,
                              "options": args.option or []}
    if args.mode:
        kwargs["plan"] = {"mode": args.mode, "periods": args.periods}
    if args.change:
        kwargs["change"] = args.change
    res = sim.simulate(args.question, man, **kwargs)
    if args.json:
        _print(res)
    else:
        print(f"ASK — twin {res['twin_id']}")
        print(f"  Q: {res['question']}")
        print(f"  intent: {res['intent'].upper()}  ->  {res['result'].get('kind')}")
        print(f"  (see --json for the full measured result)")
    return 0


def _cmd_examples(args) -> int:
    import shutil
    import tempfile
    from pathlib import Path
    td = tempfile.mkdtemp(prefix="sim-ex-")
    tp = Path(td)
    saved = sim.STORE
    saved_twin = twin.STORE
    try:
        from anima import identity_sandbox as _ids
        _ids_saved = _ids.STORE
    except Exception:
        _ids = None
        _ids_saved = None
    try:
        sim.STORE = tp
        twin.STORE = tp
        if _ids is not None:
            _ids.STORE = tp
        twin._seed_synthetic_source(tp, "SynTwinSrc")
        print("COGNITIVE SIMULATION — worked examples (hermetic, synthetic source, $0):\n")
        sim.worked_examples(root=tp, quiet=False)
    finally:
        sim.STORE = saved
        twin.STORE = saved_twin
        if _ids is not None and _ids_saved is not None:
            _ids.STORE = _ids_saved
        shutil.rmtree(td, ignore_errors=True)
    return 0


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(
        prog="simulation",
        description="COGNITIVE SIMULATION — ask what WOULD / MIGHT / SHOULD happen, run it on a "
                    "TWIN. Decision / Learning / Architecture simulation + the alternative-futures "
                    "range. Every run is on an isolated copy; the real mind is freeze-guarded.")
    ap.add_argument("--selftest", action="store_true",
                    help="run every engine on a synthetic twin; real .anima byte-unchanged; exits 0")
    sub = ap.add_subparsers(dest="cmd")

    p = sub.add_parser("decision", help="what SHOULD happen? — project a decision grounded in how Lamar decides")
    p.add_argument("twin_id")
    p.add_argument("--question", required=True)
    p.add_argument("--option", action="append", help="an option to weigh (repeatable)")
    p.add_argument("--constraint", action="append", help="a constraint (repeatable)")
    p.add_argument("--person", default=sim.PERSON)
    p.add_argument("--json", action="store_true")
    p.set_defaults(fn=_cmd_decision)

    p = sub.add_parser("learning", help="what WOULD happen if we learned X for T? — project accumulation")
    p.add_argument("twin_id")
    p.add_argument("--mode", default="medium", help="off|low|medium|high|research")
    p.add_argument("--periods", type=int, default=1)
    p.add_argument("--cycles", type=int, default=None, help="explicit cycle budget (overrides mode*periods)")
    p.add_argument("--json", action="store_true")
    p.set_defaults(fn=_cmd_learning)

    p = sub.add_parser("architecture", help="what WOULD happen if we changed the architecture? (FMLGS vs keyword)")
    p.add_argument("twin_id")
    p.add_argument("--change", default="fmlgs_retrieval",
                   help="'fmlgs_retrieval' (default; measured) or a twin change like 'added a world model'")
    p.add_argument("--json", action="store_true")
    p.set_defaults(fn=_cmd_architecture)

    p = sub.add_parser("futures", help="what MIGHT happen? — the distribution/range over variants")
    p.add_argument("twin_id")
    p.add_argument("--variants", type=int, default=5)
    p.add_argument("--base-cycles", type=int, default=20)
    p.add_argument("--seed", type=int, default=0)
    p.add_argument("--json", action="store_true")
    p.set_defaults(fn=_cmd_futures)

    p = sub.add_parser("happened", help="what HAPPENED in the twin? — read the twin MRI")
    p.add_argument("twin_id")
    p.add_argument("--json", action="store_true")
    p.set_defaults(fn=_cmd_happened)

    p = sub.add_parser("ask", help="the ROUTER: classify a natural question and route it")
    p.add_argument("twin_id")
    p.add_argument("--question", required=True)
    p.add_argument("--question-decision", default="", help="explicit decision text for a SHOULD question")
    p.add_argument("--option", action="append", help="an option (for a SHOULD question)")
    p.add_argument("--mode", default="", help="growth mode (for a WOULD-learning question)")
    p.add_argument("--periods", type=int, default=1)
    p.add_argument("--change", default="", help="architecture change (for a WOULD-architecture question)")
    p.add_argument("--json", action="store_true")
    p.set_defaults(fn=_cmd_ask)

    p = sub.add_parser("examples", help="one worked example of each simulation type (hermetic, $0)")
    p.set_defaults(fn=_cmd_examples)

    args = ap.parse_args(argv)

    if args.selftest:
        return sim._selftest()
    if not getattr(args, "cmd", None):
        ap.print_help()
        return 0
    return args.fn(args)


if __name__ == "__main__":
    raise SystemExit(main())

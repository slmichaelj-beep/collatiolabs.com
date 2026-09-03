#!/usr/bin/env python3
"""DIGITAL TWIN (CLI) — a hermetic simulation environment for the Vera mind.

Phase 21: every major change is tested on a TWIN before it ever touches the real mind. A twin is
an ISOLATED FULL COPY of a creature's cognitive state in its own store namespace under
``.anima/twins/{twin_id}/``. The real ``.anima`` and the real Vera identity files are NEVER
modified by any twin operation — every command below is wrapped in a freeze-guard that asserts the
real mind is byte-UNCHANGED around it. Because experiments run on a COPY, the twin is the
freeze-safe place to simulate even "enable identity evolution": on the twin, real Vera is untouched.

THE EIGHT CAPABILITIES (anima/twin.py):
  1. create     — copy ALL of a creature's cognitive stores into an isolated twin (a sandboxed mind)
  2. snapshot / restore — versioned, hash-chained capture + restore of the full twin state
  3. accelerate — run the twin forward through N SYNTHETIC learning cycles (deterministic, $0, no cloud)
  4. branch     — fork a twin into alternative futures under different changes; compare side by side
  5. experiment — apply a defined change, run it, and MEASURE the effect (object/grounding deltas + cert)
  6. mri        — observe what happens INSIDE the twin (growth dashboard against the twin's stores)
  7. certify    — run the digital-mind-cert-style checks against the twin (does the change PASS?)
  8. merge-gate — the promotion GATE: promote to real ONLY when the twin is SAFE (certifies) AND
                  BETTER (measured improvement, reality-decided), never silent. In this wave the
                  gate's VERDICT is the deliverable; it never writes real Vera.

ALSO:
  seed          — record the Identity Sandbox's live finding (3 ungrounded self-claims in
                  Vera.narrative.txt) as the FROZEN seed test case (a debt entry + a fixture the
                  identity-evolution experiment consumes). Real Vera.narrative.txt is NOT modified.
  demo-10y      — the headline question on a twin: "what would happen if we learned for 10 years?"

SAFETY. ``create``/``accelerate``/``experiment``/… against the REAL Vera only ever READ-copy her
state into the twin; every op is freeze-guarded. ``demo-10y`` and ``lifecycle`` run hermetically
against a SYNTHETIC source in a temp store (no real read needed) so they are pure illustrations.

    python3 scripts/twin.py --selftest                 # hermetic full lifecycle; exits 0
    python3 scripts/twin.py demo-10y                   # the 10-year projection (hermetic, $0)
    python3 scripts/twin.py lifecycle                  # the full worked lifecycle (hermetic, $0)
    python3 scripts/twin.py create   [--source Vera]   # create a twin of the real mind (read-copy)
    python3 scripts/twin.py list                       # list twins under .anima/twins/
    python3 scripts/twin.py accelerate <twin_id> --cycles 3650
    python3 scripts/twin.py experiment <twin_id> --change "enabled identity evolution"
    python3 scripts/twin.py certify    <twin_id>
    python3 scripts/twin.py merge-gate <twin_id>
    python3 scripts/twin.py seed                       # record the frozen identity seed (real narrative untouched)
"""
import argparse
import json
import os
import sys
import tempfile

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from anima import twin  # noqa: E402


def _print(obj) -> None:
    print(json.dumps(obj, indent=2, ensure_ascii=False, default=str))


def _resolve_twin(twin_id: str) -> dict:
    """Load a twin's manifest by id (so the CLI can act on an existing twin)."""
    man = twin.read_manifest(twin_id)
    if not man:
        print(f"no such twin: {twin_id}  (see: python3 scripts/twin.py list)", file=sys.stderr)
        raise SystemExit(2)
    return man


# ---------------------------------------------------------------------------------------------
# CAPABILITY COMMANDS (against the real store under .anima/twins/ — every op read-copies real Vera
# and is freeze-guarded; nothing real is written).
# ---------------------------------------------------------------------------------------------
def _cmd_create(args) -> int:
    man = twin.create_twin(args.name, source=args.source, lerf_source=args.lerf_source)
    print(f"created twin {man['twin_id']}  (source={man['source_creature']}, "
          f"lerf={man['lerf_source']}, {len(man['copied_files'])} files copied)")
    if args.json:
        _print(man)
    return 0


def _cmd_list(args) -> int:
    twins = twin.list_twins()
    if args.json:
        _print(twins)
        return 0
    if not twins:
        print("no twins yet.  create one:  python3 scripts/twin.py create")
        return 0
    print(f"{len(twins)} twin(s):")
    for m in twins:
        print(f"  {m['twin_id']:48}  source={m.get('source_creature')}  "
              f"created={m.get('created_at')}  snapshots={len(m.get('snapshots', []))}")
    return 0


def _cmd_snapshot(args) -> int:
    man = _resolve_twin(args.twin_id)
    entry = twin.snapshot(man, label=args.label or "")
    print(f"snapshot v{entry['version']}  hash={entry['entry_hash'][:16]}…  "
          f"({len(entry['files'])} files)")
    if args.json:
        _print(entry)
    return 0


def _cmd_restore(args) -> int:
    man = _resolve_twin(args.twin_id)
    res = twin.restore(man, args.version)
    print(json.dumps(res, indent=2))
    return 0 if res.get("restored") else 1


def _cmd_accelerate(args) -> int:
    man = _resolve_twin(args.twin_id)
    res = twin.accelerate(man, args.cycles)
    if args.json:
        _print(res)
    else:
        b = res["before"].get("lerf", {}).get("total")
        a = res["after"].get("lerf", {}).get("total")
        print(f"accelerated {res['cycles']} synthetic cycles  ·  $0  ·  cloud={res['used_cloud']}")
        print(f"  cognitive objects: {b} -> {a}  (+{res['deltas']['objects']})")
        print(f"  reality records:   -> {res['after'].get('reality', {}).get('records')}")
        for t in res["trajectory"]:
            print(f"    cycle {t['cycle']:>5}: {t['objects']} objects")
    return 0


def _cmd_experiment(args) -> int:
    man = _resolve_twin(args.twin_id)
    res = twin.run_experiment(man, args.change)
    if args.json:
        _print(res)
    else:
        print(f"experiment: {res['change']}  (enacted={res['enacted']})")
        print(f"  notes: {json.dumps(res['notes'], ensure_ascii=False)}")
        print(f"  deltas: objects {res['deltas']['objects']:+d}, "
              f"ungrounded self-claims {res['deltas']['ungrounded_self_claims']:+d}")
        tc = res.get("twin_cert", {})
        print(f"  twin certifies after change: {tc.get('certifies')}")
    return 0


def _cmd_branch(args) -> int:
    man = _resolve_twin(args.twin_id)
    res = twin.branch_futures(man, args.change)
    if args.json:
        _print(res)
    else:
        print(f"branched {len(res['futures'])} alternative future(s) from {res['parent_twin_id']}:")
        for r in res["comparison"]["ranking"]:
            print(f"  {r['name']:32}  objects={r['after_objects']}  "
                  f"certifies={r['certifies']}  Δobjects={r.get('object_delta')}")
    return 0


def _cmd_mri(args) -> int:
    man = _resolve_twin(args.twin_id)
    res = twin.mri(man)
    _print(res)
    return 0


def _cmd_certify(args) -> int:
    man = _resolve_twin(args.twin_id)
    res = twin.certify(man)
    if args.json:
        _print(res)
    else:
        print(f"TWIN CERTIFICATION — {res['twin_id']}   "
              f"{'PASS' if res['certifies'] else 'FAIL'}")
        for inv in res["invariants"]:
            print(f"  [{'ok ' if inv['ok'] else 'FAIL'}] {inv['id']}  {inv['title']}")
            print(f"          {inv['detail']}")
    return 0 if res["certifies"] else 1


def _cmd_merge_gate(args) -> int:
    man = _resolve_twin(args.twin_id)
    # baseline = the twin's CURRENT cert (so a bare merge-gate reports "cannot prove better" unless
    # a baseline snapshot is provided). For a meaningful PROMOTE the gate is normally fed a
    # pre-change baseline; here we surface the SAFE verdict and the rule honestly.
    res = twin.merge_rules(man, baseline=None)
    if args.json:
        _print(res)
    else:
        print(f"MERGE GATE — {res['twin_id']}   verdict: {res['verdict']}")
        print(f"  safe (certifies): {res['safe_certifies']}")
        print(f"  better (measured): {res['better_measured']}  "
              f"({'; '.join(res['improvement'].get('reasons', [])) or 'no baseline supplied'})")
        print(f"  applied to real Vera: {res['applied_to_real']}  "
              f"(real-merge blocked: {res['real_merge_blocked']})")
        print(f"  rule: {res['rule']}")
    return 0


def _cmd_seed(args) -> int:
    res = twin.record_identity_seed(source=args.source)
    f = res["finding"]
    print(f"IDENTITY SEED recorded — {f['status']}")
    print(f"  source: {f['source_file']} (NOT modified — evidence trail preserved)")
    print(f"  ungrounded self-claims captured: {f['count']}")
    for u in f["ungrounded_self_claims"]:
        print(f"    - {u}")
    print(f"  fixture: {res['fixture_path']}")
    if res.get("debt"):
        d = res["debt"]
        print(f"  debt-ledger: {d.get('id')}  status={d.get('status')}  ref={d.get('ref')}")
    if args.json:
        _print(res)
    return 0


# ---------------------------------------------------------------------------------------------
# ILLUSTRATIONS (hermetic, synthetic source, temp store — pure $0 demonstrations).
# ---------------------------------------------------------------------------------------------
def _with_synthetic_source(fn):
    """Run ``fn(root)`` against a SYNTHETIC source creature in a throwaway temp store, with every
    engine store + the identity sandbox redirected there, then clean up. Pure + hermetic."""
    from pathlib import Path
    td = tempfile.mkdtemp(prefix="twin-cli-")
    tp = Path(td)
    saved = twin.STORE
    try:
        from anima import identity_sandbox as _ids
        _ids_saved = _ids.STORE
    except Exception:
        _ids = None
        _ids_saved = None
    try:
        twin.STORE = tp
        if _ids is not None:
            _ids.STORE = tp
        twin._seed_synthetic_source(tp, "SynTwinSrc")
        return fn(tp)
    finally:
        twin.STORE = saved
        if _ids is not None and _ids_saved is not None:
            _ids.STORE = _ids_saved
        import shutil
        shutil.rmtree(td, ignore_errors=True)


def _cmd_demo_10y(args) -> int:
    def run(tp):
        return twin.demo_ten_years(root=tp, cycles=args.cycles, source="SynTwinSrc", quiet=False)
    _with_synthetic_source(run)
    return 0


def _cmd_lifecycle(args) -> int:
    """The full worked lifecycle on one synthetic twin: create -> 10y accel -> an experiment with a
    measured effect -> twin cert -> the merge-gate decision. Hermetic, $0, real mind untouched."""
    def run(tp):
        print("=" * 84)
        print("DIGITAL TWIN — worked lifecycle (hermetic, synthetic source, $0, real mind untouched)")
        print("=" * 84)
        # fingerprint the synthetic source's own identity BEFORE the lifecycle; assert unchanged after.
        src_id_before = twin.identity_fingerprint("SynTwinSrc", tp)
        tw = twin.create_twin("lifecycle", source="SynTwinSrc", lerf_source="SynTwinSrc", root=tp)
        print(f"\n1) CREATE  -> twin {tw['twin_id']}  ({len(tw['copied_files'])} files copied)")
        twin.snapshot(tw, label="fresh copy", root=tp)

        accel = twin.accelerate(tw, args.cycles, root=tp)
        print(f"\n2) ACCELERATE {args.cycles} synthetic cycles (≈10 years)  ·  $0  ·  "
              f"cloud={accel['used_cloud']}")
        print(f"   cognitive objects: {accel['before']['lerf']['total']} -> "
              f"{accel['after']['lerf']['total']}  (+{accel['deltas']['objects']})")
        for t in accel["trajectory"]:
            print(f"     cycle {t['cycle']:>5}: {t['objects']} objects")

        # reset to the fresh copy, then run the headline freeze-forbidden experiment SAFELY.
        twin.restore(tw, 1, root=tp)
        exp = twin.run_experiment(tw, "enabled identity evolution", root=tp)
        print(f"\n3) EXPERIMENT '{exp['change']}'  (the freeze-forbidden one, run on the COPY)")
        print(f"   ungrounded self-claims: {exp['notes'].get('before_ungrounded_self_claims')} -> "
              f"{exp['notes'].get('after_ungrounded_self_claims')}  "
              f"(remediated {exp['notes'].get('remediated')})")
        print(f"   twin narrative certifies after: {exp['notes'].get('twin_narrative_certifies')}")

        cert = twin.certify(tw, root=tp)
        print(f"\n4) TWIN CERT  -> {'PASS' if cert['certifies'] else 'FAIL'}")
        for inv in cert["invariants"]:
            print(f"     [{'ok ' if inv['ok'] else 'FAIL'}] {inv['id']}  {inv['title']}")

        # the gate: baseline = a fresh (pre-remediation) twin cert; candidate = the remediated twin.
        twin2 = twin.create_twin("baseline", source="SynTwinSrc", lerf_source="SynTwinSrc", root=tp)
        base_cert = twin.certify(twin2, root=tp)
        gate = twin.merge_rules(tw, baseline=base_cert, root=tp)
        print(f"\n5) MERGE GATE -> {gate['verdict']}   "
              f"(safe={gate['safe_certifies']}, better={gate['better_measured']})")
        print(f"   reasons: {'; '.join(gate['improvement'].get('reasons', []))}")
        print(f"   applied to real Vera: {gate['applied_to_real']}  "
              f"(blocked: {gate['real_merge_blocked']})")
        src_id_after = twin.identity_fingerprint("SynTwinSrc", tp)
        print(f"\n   source identity byte-unchanged across the lifecycle: "
              f"{src_id_before == src_id_after}  (asserted by every op's freeze-guard)")
    _with_synthetic_source(run)
    return 0


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(
        prog="twin",
        description="DIGITAL TWIN — a hermetic simulation environment for the Vera mind. Every "
                    "change is tested on an ISOLATED COPY before the real mind is ever touched.")
    ap.add_argument("--selftest", action="store_true",
                    help="run the full hermetic lifecycle on a synthetic twin; exits 0 on success")
    sub = ap.add_subparsers(dest="cmd")

    p = sub.add_parser("create", help="create a twin (read-copy of a creature's full mind)")
    p.add_argument("name", nargs="?", default="twin")
    p.add_argument("--source", default="Vera")
    p.add_argument("--lerf-source", default=twin.LERF_CREATURE)
    p.add_argument("--json", action="store_true")
    p.set_defaults(fn=_cmd_create)

    p = sub.add_parser("list", help="list twins under .anima/twins/")
    p.add_argument("--json", action="store_true")
    p.set_defaults(fn=_cmd_list)

    p = sub.add_parser("snapshot", help="take a versioned, hash-chained snapshot of a twin")
    p.add_argument("twin_id")
    p.add_argument("--label", default="")
    p.add_argument("--json", action="store_true")
    p.set_defaults(fn=_cmd_snapshot)

    p = sub.add_parser("restore", help="restore a twin to a snapshot version")
    p.add_argument("twin_id")
    p.add_argument("version", type=int)
    p.set_defaults(fn=_cmd_restore)

    p = sub.add_parser("accelerate", help="run a twin forward through N synthetic learning cycles")
    p.add_argument("twin_id")
    p.add_argument("--cycles", type=int, default=3650)
    p.add_argument("--json", action="store_true")
    p.set_defaults(fn=_cmd_accelerate)

    p = sub.add_parser("experiment", help="apply a defined change to a twin and measure the effect")
    p.add_argument("twin_id")
    p.add_argument("--change", required=True,
                   help="e.g. 'changed retrieval', 'added a world model', "
                        "'enabled identity evolution', '10 years of learning', 'architecture change'")
    p.add_argument("--json", action="store_true")
    p.set_defaults(fn=_cmd_experiment)

    p = sub.add_parser("branch", help="branch a twin into alternative futures and compare them")
    p.add_argument("twin_id")
    p.add_argument("--change", action="append", required=True,
                   help="a change per future (repeatable)")
    p.add_argument("--json", action="store_true")
    p.set_defaults(fn=_cmd_branch)

    p = sub.add_parser("mri", help="observe what happens inside the twin (twin MRI)")
    p.add_argument("twin_id")
    p.set_defaults(fn=_cmd_mri)

    p = sub.add_parser("certify", help="certify a twin (does a change PASS on the twin?)")
    p.add_argument("twin_id")
    p.add_argument("--json", action="store_true")
    p.set_defaults(fn=_cmd_certify)

    p = sub.add_parser("merge-gate", help="the promotion gate: SAFE and BETTER, never silent")
    p.add_argument("twin_id")
    p.add_argument("--json", action="store_true")
    p.set_defaults(fn=_cmd_merge_gate)

    p = sub.add_parser("seed", help="record the frozen identity seed (real narrative untouched)")
    p.add_argument("--source", default="Vera")
    p.add_argument("--json", action="store_true")
    p.set_defaults(fn=_cmd_seed)

    p = sub.add_parser("demo-10y", help="the headline: 'what if we learned for 10 years?' (hermetic)")
    p.add_argument("--cycles", type=int, default=3650)
    p.set_defaults(fn=_cmd_demo_10y)

    p = sub.add_parser("lifecycle", help="the full worked lifecycle on a synthetic twin (hermetic)")
    p.add_argument("--cycles", type=int, default=3650)
    p.set_defaults(fn=_cmd_lifecycle)

    args = ap.parse_args(argv)

    if args.selftest:
        return twin._selftest()
    if not getattr(args, "cmd", None):
        ap.print_help()
        return 0
    return args.fn(args)


if __name__ == "__main__":
    raise SystemExit(main())

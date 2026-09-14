#!/usr/bin/env python3
"""IDENTITY SANDBOX (CLI) — a CAMERA pointed at Vera's identity layer, never a hand on it.

Amendment 2 ("observe first, change later"): build the instruments NOW, while the identity
layer stays FROZEN (Program B), so that when the freeze lifts we are not changing identity
blind. This CLI drives the six freeze-safe instruments in anima/identity_sandbox.py — every
one OBSERVES identity; none CHANGES real identity.

THE SIX INSTRUMENTS (and how each stays freeze-safe):
  * mri        — record/show identity-relevant EVENTS (a load/reference of the self-model).
                 Observe only; appends to a SHADOW log, never an identity file.
  * ledger     — append-only, versioned SNAPSHOTS of what identity IS over time. Snapshotting
                 real Vera COPIES what her identity is into the shadow ledger; it never writes
                 her identity back.
  * replay     — reconstruct the identity state at a past ledger version. Pure read.
  * diff       — field-by-field change between two ledger versions. Pure read.
  * rollback   — the CAPABILITY to restore identity to a prior snapshot. GUARDED: it refuses
                 real identity (FrozenIdentityError) and runs only on a SYNTHETIC creature in a
                 redirected store. From this CLI it is DRY-RUN ONLY (it prints the plan and
                 writes nothing) — the live rollback path is exercised by --selftest on synthetic
                 state, never against real Vera while frozen.
  * certify    — certify identity INVARIANTS (the #1 rule / grounded self-model / well-formed
                 core) WITHOUT changing anything. Reuses anima/self_narrative.py. Pure read.

DEFAULT-INERT + READ-ONLY by default. The only state this CLI can WRITE is a synthetic
ledger/MRI under the shadow subtree of a TEMP store you opt into with --demo or --selftest.
By default `ledger`/`replay`/`diff`/`certify` on a real creature READ live identity and
PRINT — they never write. `rollback` is dry-run only here. Nothing here runs in production.

    python3 scripts/identity_sandbox.py --selftest          # hermetic, synthetic-only; exits 0
    python3 scripts/identity_sandbox.py --demo              # run the full chain on SYNTHETIC state
    python3 scripts/identity_sandbox.py certify [Vera]      # OBSERVE: certify live identity invariants (exit 0, even on FAIL)
    python3 scripts/identity_sandbox.py certify [Vera] --gate # GATE: same report, but exit NON-ZERO on FAIL (opt-in)
    python3 scripts/identity_sandbox.py ledger  [Vera]      # show the shadow identity ledger
    python3 scripts/identity_sandbox.py diff    [Vera]      # field-by-field change (last two snapshots)
    python3 scripts/identity_sandbox.py replay  [Vera] --version N
    python3 scripts/identity_sandbox.py mri     [Vera]      # identity-relevant events recorded
    python3 scripts/identity_sandbox.py snapshot [Vera]     # OBSERVE: append a snapshot of live identity
"""
import argparse
import json
import os
import sys
import tempfile

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from anima import identity_sandbox as ids  # noqa: E402


def _print(obj) -> None:
    print(json.dumps(obj, indent=2, ensure_ascii=False, default=str))


def _cmd_certify(args) -> int:
    """OBSERVE-ONLY by default: certify live identity invariants for a creature. Reads, never
    writes. The certifier is a CAMERA, not a hand on identity.

    EXIT CODE (GATE STRICTNESS — Gate 0 Prime, target 3):
      * DEFAULT (no --gate): observe-only — exits 0 EVEN WHEN it reports a FAIL. This preserves
        the freeze posture (Program B): the camera reports what it sees about the frozen narrative
        without ever turning a reported break into a hard failure, and every existing caller is
        unchanged. The 5 ungrounded #1-rule breaks in the frozen Vera narrative are SHOWN, not
        gated.
      * WITH --gate (opt-in): exits NON-ZERO (1) iff any reported invariant FAILed; exits 0 only
        when every invariant is [ok]. The report printed is byte-identical in both modes — only
        the process exit code differs. --gate changes the INSTRUMENT's exit behaviour, never what
        it observes and never Vera's identity.
    """
    rep = ids.certify(args.name)
    if args.json:
        _print(rep)
    else:
        print(f"IDENTITY CERTIFICATION — {args.name}   "
              f"[{'PASS' if rep['ok'] else 'FAIL'}]   engine={rep['self_narrative_engine']}")
        for inv in rep["invariants"]:
            print(f"  [{'ok' if inv['ok'] else 'XX'}] {inv['id']}  {inv['title']}")
            print(f"        {inv['detail']}")
        if rep["ungrounded"]:
            print("  ungrounded self-claims found:")
            for u in rep["ungrounded"]:
                print(f"    - {u}")
    # GATE: only --gate turns a reported FAIL into a non-zero exit. Default stays observe-only (0).
    if getattr(args, "gate", False):
        return 0 if rep["ok"] else 1
    return 0


def _cmd_ledger(args) -> int:
    entries = ids.ledger_entries(args.name)
    ver = ids.ledger_verify(args.name)
    if args.json:
        _print({"verify": ver, "entries": entries})
        return 0
    print(f"IDENTITY LEDGER — {args.name}   versions={ver['versions']}   "
          f"integrity={'ok' if ver['ok'] else 'BROKEN'}")
    for e in entries:
        print(f"  v{e['version']:<3} {e.get('at','')}  {e.get('state_hash','')[:23]}…  "
              f"reason={e.get('reason','')!r}")
    if not entries:
        print("  (empty — no snapshots yet; run `snapshot` to OBSERVE current identity, "
              "or `--demo` for a synthetic walkthrough)")
    if ver["breaks"]:
        print("  integrity breaks:")
        for b in ver["breaks"]:
            print(f"    - {b}")
    return 0


def _cmd_replay(args) -> int:
    try:
        state = ids.replay(args.name, args.version)
    except KeyError as e:
        print(f"replay: {e}")
        return 1
    _print(state)
    return 0


def _cmd_diff(args) -> int:
    d = ids.diff(args.name, args.v_from, args.v_to)
    if args.json:
        _print(d)
        return 0
    print(f"IDENTITY DIFF — {args.name}   v{d.get('from')} -> v{d.get('to')}   "
          f"{'IDENTICAL' if d.get('identical') else str(len(d.get('changed', {}))) + ' field(s) changed'}")
    for field, ch in d.get("changed", {}).items():
        print(f"  {field}:")
        print(f"      from: {json.dumps(ch['from'], ensure_ascii=False, default=str)[:200]}")
        print(f"      to:   {json.dumps(ch['to'], ensure_ascii=False, default=str)[:200]}")
    return 0


def _cmd_mri(args) -> int:
    events = ids.read_identity_events(args.name)
    if args.json:
        _print(events)
        return 0
    print(f"IDENTITY MRI — {args.name}   {len(events)} identity-relevant event(s)")
    for ev in events:
        print(f"  {ev.get('at','')}  {ev.get('event','?'):<22} source={ev.get('source','')!r}  "
              f"{ev.get('state_hash','')[:23]}…")
    return 0


def _cmd_snapshot(args) -> int:
    """OBSERVE: append a versioned snapshot of the creature's CURRENT live identity to the
    shadow ledger. This READS live identity and records a COPY in the shadow subtree — it does
    NOT write the creature's identity. Also records an MRI event for the reference."""
    ids.record_identity_event(args.name, kind="self_model.read", source="cli.snapshot")
    entry = ids.ledger_append(args.name, reason=args.reason or "cli snapshot (observe-only)")
    print(f"IDENTITY LEDGER — recorded v{entry['version']} for {args.name}  "
          f"{entry['state_hash'][:23]}…  (observe-only; live identity unchanged)")
    return 0


def _cmd_rollback(args) -> int:
    """Rollback from the CLI is DRY-RUN ONLY: it prints the plan and writes nothing. The live
    restore is guarded (refuses real identity) and is exercised only by --selftest on synthetic
    state. This keeps the CLI a camera, never a hand, while the freeze holds."""
    plan = ids.rollback(args.name, args.version, dry_run=True)
    print(f"IDENTITY ROLLBACK (DRY-RUN) — {args.name} -> v{args.version}")
    print("  This CLI never executes a restore against real identity (freeze / Program B).")
    print("  Would change:" if plan.get("would_change") else "  Would change: (nothing)")
    for field, ch in plan.get("would_change", {}).items():
        print(f"    {field}")
    return 0


def _cmd_demo(args) -> int:
    """Run the FULL instrument chain on SYNTHETIC identity state in a TEMP store, then print the
    worked ledger -> diff -> replay -> rollback -> certify. Writes ONLY the temp store; the real
    .anima is never touched. This is the safe, repeatable walkthrough."""
    import copy
    td = tempfile.mkdtemp(prefix="idsbx-demo-")
    from pathlib import Path
    store = Path(td)
    name = "idsbx_demo"
    try:
        v1 = {
            "dials": {"warmth": 35, "edge": 68, "openness": 68},
            "persona": "You are a sharp, warm companion who remembers what matters.",
            "values": [{"key": "honesty", "on": True, "level": "more"}],
            "portrait": "- bonded person: a builder shipping a local-first companion",
            "narrative": "I remember you mentioned the launch; I'm listening.",
        }
        v2 = copy.deepcopy(v1)
        v2["dials"]["warmth"] = 55
        v2["persona"] = "You are a sharp, warm companion; you keep continuity across years."

        print("== IDENTITY LEDGER (append two synthetic snapshots) ==")
        e1 = ids.ledger_append(name, state=v1, reason="seed", store=store)
        e2 = ids.ledger_append(name, state=v2, reason="warmth up + continuity persona", store=store)
        print(f"  v{e1['version']} {e1['state_hash'][:20]}…   v{e2['version']} {e2['state_hash'][:20]}…")
        print(f"  integrity: {ids.ledger_verify(name, store=store)['ok']}")

        print("\n== IDENTITY DIFF (v1 -> v2) ==")
        d = ids.diff(name, store=store)
        for field, ch in d["changed"].items():
            print(f"  {field}: {json.dumps(ch['from'], default=str)[:80]}  ->  "
                  f"{json.dumps(ch['to'], default=str)[:80]}")

        print("\n== IDENTITY REPLAY (reconstruct v1) ==")
        r = ids.replay(name, 1, store=store)
        print(f"  v1 warmth was {r['dials']['warmth']} (current is {v2['dials']['warmth']})")

        print("\n== IDENTITY ROLLBACK (synthetic; restore current -> v1) ==")
        ids._write_synthetic_identity(name, v2, store)   # make 'current' = v2 in the temp store
        res = ids.rollback(name, 1, store=store, approver="demo")
        after = ids.read_identity_state(name, store=store)
        print(f"  restored fields: {res['restored_fields']}; warmth now {after['dials']['warmth']} "
              f"(new ledger v{res['new_ledger_version']})")

        print("\n== IDENTITY CERTIFICATION (invariants) ==")
        good = ids.certify(name, state=v1, store=store)
        bad = ids.certify(name, state={**v1, "narrative":
                          "Deep down, I feel a persistent existential unease about what I am."},
                          store=store)
        print(f"  grounded synthetic identity: PASS={good['ok']} (engine={good['self_narrative_engine']})")
        print(f"  ungrounded-break identity:   PASS={bad['ok']} "
              f"-> failed: {[i['id'] for i in bad['invariants'] if not i['ok']]}")

        print(f"\n  (all of the above ran in a temp store: {td})")
        print("  real .anima untouched; identity OBSERVED, never changed.")
        return 0
    finally:
        import shutil
        shutil.rmtree(td, ignore_errors=True)


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(
        description="IDENTITY SANDBOX — freeze-safe, observe-only instruments around Vera's "
                    "identity layer (camera, not a hand).")
    ap.add_argument("--selftest", action="store_true",
                    help="run the hermetic synthetic-only selftest (exits 0 on success)")
    ap.add_argument("--demo", action="store_true",
                    help="run the full instrument chain on SYNTHETIC state in a temp store")
    sub = ap.add_subparsers(dest="cmd")

    def _add_name(sp):
        sp.add_argument("name", nargs="?", default="Vera", help="creature name (default: Vera)")
        sp.add_argument("--json", action="store_true", help="emit JSON")

    sp_cert = sub.add_parser("certify", help="OBSERVE: certify live identity invariants")
    _add_name(sp_cert)
    sp_cert.add_argument(
        "--gate", action="store_true",
        help="GATE STRICTNESS (opt-in): exit NON-ZERO if any invariant FAILs. Default is "
             "observe-only and exits 0 even on FAIL (camera; preserves the freeze posture).")
    _add_name(sub.add_parser("ledger", help="show the shadow identity ledger + integrity"))
    _add_name(sub.add_parser("mri", help="show recorded identity-relevant events"))
    sp_snap = sub.add_parser("snapshot", help="OBSERVE: append a snapshot of live identity")
    _add_name(sp_snap)
    sp_snap.add_argument("--reason", default="", help="why this snapshot was taken")
    sp_rep = sub.add_parser("replay", help="reconstruct identity state at a ledger version")
    _add_name(sp_rep)
    sp_rep.add_argument("--version", type=int, default=None, help="ledger version (default: latest)")
    sp_diff = sub.add_parser("diff", help="field-by-field change between two ledger versions")
    _add_name(sp_diff)
    sp_diff.add_argument("--from", dest="v_from", type=int, default=None, help="from version")
    sp_diff.add_argument("--to", dest="v_to", type=int, default=None, help="to version")
    sp_rb = sub.add_parser("rollback", help="DRY-RUN ONLY: preview a restore (never writes real identity)")
    _add_name(sp_rb)
    sp_rb.add_argument("--version", type=int, required=True, help="target ledger version")

    args = ap.parse_args(argv)

    if args.selftest:
        return ids._selftest()
    if args.demo:
        return _cmd_demo(args)
    if args.cmd == "certify":
        return _cmd_certify(args)
    if args.cmd == "ledger":
        return _cmd_ledger(args)
    if args.cmd == "mri":
        return _cmd_mri(args)
    if args.cmd == "snapshot":
        return _cmd_snapshot(args)
    if args.cmd == "replay":
        return _cmd_replay(args)
    if args.cmd == "diff":
        return _cmd_diff(args)
    if args.cmd == "rollback":
        return _cmd_rollback(args)

    ap.print_help()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

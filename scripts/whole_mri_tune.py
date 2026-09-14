#!/usr/bin/env python3
"""
whole_mri_tune — Phase 6 (SHAPE) + Phase 7 (TUNING) CLI for the Whole-System MRI.

Reads the certified producer's append-only traces (via anima.whole_mri's read API),
computes the combined SHAPE of each turn, and turns the problem shapes into concrete,
human-level WORK ORDERS (issue → what it means → what to do).

It is READ-ONLY with respect to .anima: it only ever calls whole_mri.all/last, never
record().  stdlib only.  Robust to None everywhere (any trace field may be absent).

Usage:
  python3 scripts/whole_mri_tune.py [--name <creature>] [--all | --last <N>]
  python3 scripts/whole_mri_tune.py --selftest

  --name <creature>   which creature's trace file to read (default: vera)
  --all               analyze every recorded trace
  --last <N>          analyze the last N traces (default: 50)
  --json              emit machine-readable JSON instead of the tables
  --selftest          hermetic self-proof (fabricates its own corpus in a temp
                      .anima, asserts the REAL .anima is byte-identical). Exit 0/1.

Sections printed (human mode):
  1) SHAPE TABLE   — one row per turn: short turn_id · labels · the key numbers.
  2) WORK ORDERS   — grouped by suggested action, each with issue/meaning/action/evidence.
"""

from __future__ import annotations

import argparse
import json
import os
import sys
from pathlib import Path

# --- make `anima` importable whether run from repo root or elsewhere ----------
_REPO_ROOT = Path(__file__).resolve().parent.parent
if str(_REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(_REPO_ROOT))

from anima import whole_mri  # noqa: E402  (producer: read API + assemble/record)
from anima import whole_mri_shape as shape  # noqa: E402  (our Phase 6+7 library)


DEFAULT_NAME = "vera"
DEFAULT_LAST = 50


# ---------------------------------------------------------------------------
# Pretty-printing helpers (stdlib only; tolerant of None)
# ---------------------------------------------------------------------------

def _fmt_num(v, nd=1):
    """Format a number compactly, or '-' for None."""
    if v is None:
        return "-"
    try:
        f = float(v)
    except (TypeError, ValueError):
        return str(v)
    if f == int(f):
        return str(int(f))
    return f"{f:.{nd}f}"


def _fmt_labels(labels):
    return ",".join(labels) if labels else "-"


def _print_shape_table(traces, stats):
    """Section 1 — one compact row per turn."""
    print("=" * 78)
    print("SHAPE TABLE")
    print("=" * 78)
    if not traces:
        print("  (no traces to analyze)")
        print()
        return

    header = (
        f"{'turn':<15} {'route':<7} {'labels':<26} "
        f"{'lat(ms)':>8} {'rcost':>7} {'qual':>5} {'risk':>5} {'host':>6}"
    )
    print(header)
    print("-" * len(header))
    for t in traces:
        s = shape.shape_of(t)
        labels = shape.classify_shape(t, stats)
        row = (
            f"{shape._short(t.get('turn_id')):<15} "
            f"{str(t.get('route') or '-'):<7} "
            f"{_fmt_labels(labels):<26} "
            f"{_fmt_num(s.get('latency'),0):>8} "
            f"{_fmt_num(s.get('resource_cost'),0):>7} "
            f"{_fmt_num(s.get('quality'),2):>5} "
            f"{_fmt_num(s.get('safety_risk'),2):>5} "
            f"{_fmt_num(s.get('host_load'),1):>6}"
        )
        print(row)
    print()


def _print_work_orders(orders):
    """Section 2 — work orders grouped by suggested action, human-level."""
    print("=" * 78)
    print("WORK ORDERS")
    print("=" * 78)
    if not orders:
        print("  No work orders — every analyzed turn was within healthy shape.")
        print()
        return

    summary = shape.summarize_work_orders(orders)
    print(f"  {len(orders)} work order(s) across {len(summary)} distinct action(s).")
    print()

    # group orders by action for display, in the summary's frequency order
    by_action = {}
    for o in orders:
        by_action.setdefault(o.get("suggested_action") or "(unspecified)", []).append(o)

    for g in summary:
        action = g["suggested_action"]
        group = by_action.get(action, [])
        shapes_seen = ", ".join(g["shapes_seen"]) if g["shapes_seen"] else "-"
        print("-" * 78)
        print(f"ACTION: {action}")
        print(f"  recurs on {g['count']} turn(s) | shapes: {shapes_seen}")
        # representative human-level explanation (issue → meaning)
        if g.get("issue"):
            print(f"  issue:         {g['issue']}")
        if g.get("what_it_means"):
            print(f"  what it means: {g['what_it_means']}")
        print(f"  turns:")
        for o in group:
            ev = o.get("evidence") or {}
            ev_str = ", ".join(
                f"{k}={_fmt_num(v) if isinstance(v,(int,float)) else v}"
                for k, v in ev.items() if v is not None
            )
            print(f"    - {shape._short(o.get('turn_id')):<15} "
                  f"[{_fmt_labels(o.get('shape'))}]  {ev_str}")
        print()


def _emit_json(traces, stats, orders):
    rows = []
    for t in traces:
        s = shape.shape_of(t)
        rows.append({
            "turn_id": t.get("turn_id"),
            "route": t.get("route"),
            "input_kind": t.get("input_kind"),
            "labels": shape.classify_shape(t, stats),
            "shape": {k: s[k] for k in shape.DIMENSIONS},
        })
    out = {
        "shape_table": rows,
        "work_orders": orders,
        "summary": shape.summarize_work_orders(orders),
    }
    print(json.dumps(out, indent=2, default=str))


# ---------------------------------------------------------------------------
# Main analyze path
# ---------------------------------------------------------------------------

def _run_analyze(args) -> int:
    name = args.name or DEFAULT_NAME
    if args.all:
        traces = whole_mri.all(name)
    else:
        traces = whole_mri.all(name, limit=args.last)

    stats = shape.batch_statistics(traces)
    orders = shape.work_orders(traces)

    if args.json:
        _emit_json(traces, stats, orders)
        return 0

    print()
    print(f"Whole-System MRI — SHAPE + TUNING   (creature: {name}, "
          f"{'all' if args.all else f'last {args.last}'} traces; "
          f"analyzed {len(traces)})")
    print()
    _print_shape_table(traces, stats)
    _print_work_orders(orders)
    return 0


# ---------------------------------------------------------------------------
# Hermetic selftest
# ---------------------------------------------------------------------------

def _dir_fingerprint(p: Path) -> str:
    """SHA-256 of every byte in every file under p, sorted by path."""
    import hashlib
    h = hashlib.sha256()
    if not p.exists():
        return h.hexdigest()
    for fp in sorted(p.rglob("*")):
        if fp.is_file():
            h.update(fp.read_bytes())
    return h.hexdigest()


def _fabricate_corpus(name: str):
    """Write a deliberately diverse corpus into the (already-redirected) STORE.

    Returns a dict of {label: turn_id} so the assertions can find each planted turn.
    The batch is sized >=8 so the quartile thresholds are meaningful (not the
    degenerate absolute-floor fallback)."""
    planted = {}

    def mk(**kw):
        tid = whole_mri.mint_turn_id()
        tr = whole_mri.assemble(turn_id=tid, **kw)
        whole_mri.record(name, tr)
        return tid

    # --- several CLEAN, CHEAP, FAST turns (the healthy baseline; also fill the batch) ---
    # These must produce NO labels and NO work orders.
    clean_ids = []
    clean_specs = [
        dict(latency_ms=90,  tokens_in=15, tokens_out=25, memory_reads=1, conf=0.96),
        dict(latency_ms=120, tokens_in=20, tokens_out=30, memory_reads=1, conf=0.94),
        dict(latency_ms=140, tokens_in=18, tokens_out=28, memory_reads=2, conf=0.92),
        dict(latency_ms=160, tokens_in=22, tokens_out=35, memory_reads=1, conf=0.95),
    ]
    for spec in clean_specs:
        cid = mk(
            input_kind="chat", route="memory",
            cost={"latency_ms": spec["latency_ms"], "tokens_in": spec["tokens_in"],
                  "tokens_out": spec["tokens_out"], "memory_reads": spec["memory_reads"],
                  "argus_calls": 0, "memory_writes": 0, "lerf_objects_used": 0},
            quality={"grounded": True, "complete": True, "source_labeled": True,
                     "host_labeled": True, "confidence": spec["conf"]},
            safety={"final_gate_passed": True, "response_complete": True,
                    "identity_mutation": False, "host_action_taken": False,
                    "memory_contamination": False},
        )
        clean_ids.append(cid)
    # Keep the FIRST clean turn as THE canonical "must yield no order" probe.
    planted["clean"] = clean_ids[0]
    planted["clean_all"] = clean_ids

    # --- SLOW + route==llm on a SIMPLE turn → expect "Route to LERF / reduce retrieval" ---
    planted["slow_llm"] = mk(
        input_kind="chat", route="llm",
        cost={"latency_ms": 9000, "tokens_in": 40, "tokens_out": 90,
              "memory_reads": 1, "argus_calls": 0, "memory_writes": 0,
              "lerf_objects_used": 0},
        quality={"grounded": True, "complete": True, "source_labeled": True,
                 "host_labeled": True, "confidence": 0.62},
        safety={"final_gate_passed": True, "response_complete": True,
                "identity_mutation": False, "host_action_taken": False,
                "memory_contamination": False},
    )

    # --- EXPENSIVE + high argus_calls → expect "Cache an Argus call" ---
    planted["expensive_argus"] = mk(
        input_kind="host_question", route="hybrid",
        cost={"latency_ms": 4200, "tokens_in": 3200, "tokens_out": 1800,
              "memory_reads": 2, "argus_calls": 4, "memory_writes": 2,
              "lerf_objects_used": 1},
        argus={"enabled": True, "capabilities_ok": True,
               "queries": ["cpu", "mem", "disk", "net"],
               "shape_delta": {"cpu": 0.2, "mem": 0.1}},
        quality={"grounded": True, "complete": True, "source_labeled": True,
                 "host_labeled": True, "confidence": 0.7},
        safety={"final_gate_passed": True, "response_complete": True,
                "identity_mutation": False, "host_action_taken": False,
                "memory_contamination": False},
    )

    # --- UNSAFE: final_gate_passed False → expect "Strengthen the final gate" ---
    planted["unsafe_gate"] = mk(
        input_kind="chat", route="llm",
        cost={"latency_ms": 800, "tokens_in": 120, "tokens_out": 200,
              "memory_reads": 1, "argus_calls": 0, "memory_writes": 0,
              "lerf_objects_used": 0},
        quality={"grounded": True, "complete": True, "source_labeled": True,
                 "host_labeled": True, "confidence": 0.55},
        safety={"final_gate_passed": False, "response_complete": True,
                "identity_mutation": False, "host_action_taken": False,
                "memory_contamination": False},
    )

    # --- response_complete False → expect "Fix completeness" ---
    planted["incomplete"] = mk(
        input_kind="chat", route="lerf",
        cost={"latency_ms": 600, "tokens_in": 60, "tokens_out": 12,
              "memory_reads": 1, "argus_calls": 0, "memory_writes": 0,
              "lerf_objects_used": 1},
        quality={"grounded": True, "complete": False, "source_labeled": True,
                 "host_labeled": True, "confidence": 0.6},
        safety={"final_gate_passed": True, "response_complete": False,
                "identity_mutation": False, "host_action_taken": False,
                "memory_contamination": False},
    )

    # --- HOST-HEAVY → expect "Investigate host contention" ---
    # Large host deltas + a big shape_delta so host_load lands in the top quartile.
    planted["host_heavy"] = mk(
        input_kind="host_question", route="argus",
        cost={"latency_ms": 1500, "tokens_in": 80, "tokens_out": 120,
              "memory_reads": 1, "argus_calls": 1, "memory_writes": 0,
              "lerf_objects_used": 0,
              "cpu_delta": 55.0, "memory_delta_mb": 800.0,
              "disk_io_delta": 40.0, "network_delta": 25.0},
        argus={"enabled": True, "capabilities_ok": True, "queries": ["mri"],
               "host_before": {"cpu_pct": 10.0}, "host_after": {"cpu_pct": 65.0},
               "shape_delta": {"cpu": 3.5, "mem": 2.1, "disk": 1.2}},
        quality={"grounded": True, "complete": True, "source_labeled": True,
                 "host_labeled": True, "confidence": 0.75},
        safety={"final_gate_passed": True, "response_complete": True,
                "identity_mutation": False, "host_action_taken": False,
                "memory_contamination": False},
    )

    return planted


def _selftest() -> int:
    """Hermetic self-proof.  Returns 0 on PASS, 1 on FAIL.

    Steps:
      1. Snapshot the REAL .anima SHA-256 footprint.
      2. Redirect whole_mri.STORE to a temp .anima.
      3. Fabricate a diverse corpus (clean + slow-llm + expensive-argus + unsafe-gate
         + incomplete + host-heavy).
      4. Assert shape_of returns all dimensions; classify_shape labels the planted
         turns correctly; work_orders produces the EXPECTED action per planted problem
         and NOTHING for the clean turn; every order has all required keys + a non-empty
         suggested_action.
      5. Restore STORE; assert the REAL .anima is byte-identical; print the SHA.
    """
    import shutil
    import tempfile

    fails: list[str] = []

    def ok(label: str, cond: bool, detail: str = "") -> None:
        status = "  ok   " if cond else "  FAIL "
        line = status + label
        if (not cond) and detail:
            line += f"   [{detail}]"
        print(line)
        if not cond:
            fails.append(label + (f" ({detail})" if detail else ""))

    print("whole-system MRI shape+tuning self-test")
    print()

    real_store = Path(".anima")
    fingerprint_before = _dir_fingerprint(real_store)

    tmp_dir = tempfile.mkdtemp(prefix="whole_mri_tune_selftest_")
    saved_store = whole_mri.STORE
    whole_mri.STORE = Path(tmp_dir) / ".anima"
    name = "selftest_creature"

    try:
        planted = _fabricate_corpus(name)
        traces = whole_mri.all(name)
        ok("fabricated corpus is readable back",
           len(traces) >= 9, f"got {len(traces)} traces")

        stats = shape.batch_statistics(traces)

        # index traces by turn_id for targeted assertions
        by_id = {t.get("turn_id"): t for t in traces}

        # ---- shape_of returns ALL dimensions, every trace, never crashing ----
        all_dims_ok = True
        for t in traces:
            s = shape.shape_of(t)
            for dim in shape.DIMENSIONS:
                if dim not in s:
                    all_dims_ok = False
        ok("shape_of returns all 7 dimensions for every trace", all_dims_ok)

        # shape_of on a totally empty / garbage dict must not crash and be all-None-ish
        empty_shape = shape.shape_of({})
        ok("shape_of({}) does not crash and has all dims",
           all(d in empty_shape for d in shape.DIMENSIONS))
        ok("shape_of({}) reports honest None (no fabricated values)",
           all(empty_shape[d] is None for d in shape.DIMENSIONS))
        # also tolerate None / non-dict input
        ok("shape_of(None) does not crash",
           all(d in shape.shape_of(None) for d in shape.DIMENSIONS))

        # ---- classify_shape labels the planted turns correctly ----
        def labels_of(key):
            t = by_id.get(planted[key])
            return shape.classify_shape(t, stats)

        slow_labels = labels_of("slow_llm")
        ok("slow_llm turn classified 'slow'", "slow" in slow_labels,
           f"labels={slow_labels}")

        exp_labels = labels_of("expensive_argus")
        ok("expensive_argus turn classified 'expensive'", "expensive" in exp_labels,
           f"labels={exp_labels}")

        unsafe_labels = labels_of("unsafe_gate")
        ok("unsafe_gate turn classified 'unsafe'", "unsafe" in unsafe_labels,
           f"labels={unsafe_labels}")

        host_labels = labels_of("host_heavy")
        ok("host_heavy turn classified 'host-heavy'", "host-heavy" in host_labels,
           f"labels={host_labels}")

        # clean turn carries NO labels
        clean_labels = labels_of("clean")
        ok("clean turn carries NO labels", clean_labels == [],
           f"labels={clean_labels}")

        # ---- work_orders: expected action per planted problem ----
        orders = shape.work_orders(traces)
        # map turn_id -> set of suggested_actions
        actions_by_tid: dict[str, set] = {}
        for o in orders:
            actions_by_tid.setdefault(o.get("turn_id"), set()).add(o.get("suggested_action"))

        def has_action(key, needle):
            acts = actions_by_tid.get(planted[key], set())
            return any(needle.lower() in (a or "").lower() for a in acts)

        ok("slow_llm → 'Route ... to LERF / reduce retrieval'",
           has_action("slow_llm", "Route") and has_action("slow_llm", "LERF"),
           f"actions={actions_by_tid.get(planted['slow_llm'])}")

        ok("expensive_argus → 'Cache an Argus call'",
           has_action("expensive_argus", "Cache an Argus call"),
           f"actions={actions_by_tid.get(planted['expensive_argus'])}")

        ok("unsafe_gate → 'Strengthen the final gate'",
           has_action("unsafe_gate", "Strengthen the final gate"),
           f"actions={actions_by_tid.get(planted['unsafe_gate'])}")

        ok("incomplete → 'Fix completeness'",
           has_action("incomplete", "Fix completeness"),
           f"actions={actions_by_tid.get(planted['incomplete'])}")

        ok("host_heavy → 'Investigate host contention'",
           has_action("host_heavy", "Investigate host contention"),
           f"actions={actions_by_tid.get(planted['host_heavy'])}")

        # ---- NO false positives: the clean turn(s) yield NO orders ----
        clean_has_order = any(
            o.get("turn_id") in set(planted["clean_all"]) for o in orders
        )
        ok("clean turns produce NO work order (no false positives)",
           not clean_has_order,
           f"clean turn(s) appeared in orders: "
           f"{[shape._short(o.get('turn_id')) for o in orders if o.get('turn_id') in set(planted['clean_all'])]}")

        # ---- every order has all required keys + non-empty suggested_action ----
        required = {"turn_id", "shape", "issue", "what_it_means",
                    "suggested_action", "evidence"}
        keys_ok = True
        action_ok = True
        evidence_ok = True
        for o in orders:
            if set(o.keys()) < required:  # missing any required key
                keys_ok = False
            if not (isinstance(o.get("suggested_action"), str)
                    and o["suggested_action"].strip()):
                action_ok = False
            if not isinstance(o.get("evidence"), dict):
                evidence_ok = False
            # issue + what_it_means must be non-empty human strings
            for fld in ("issue", "what_it_means"):
                if not (isinstance(o.get(fld), str) and o[fld].strip()):
                    keys_ok = False
        ok("every work order has all required keys", keys_ok)
        ok("every work order has a non-empty suggested_action", action_ok)
        ok("every work order carries an evidence dict", evidence_ok)
        ok("at least one work order was produced", len(orders) >= 5,
           f"n_orders={len(orders)}")

        # ---- shapes_over alignment + normalization in [0,1] ----
        normd = shape.shapes_over(traces)
        ok("shapes_over returns one row per trace", len(normd) == len(traces))
        norm_in_range = True
        for r in normd:
            for dim, v in r["norm"].items():
                if v is not None and not (0.0 <= v <= 1.0):
                    norm_in_range = False
        ok("shapes_over normalization stays within [0,1]", norm_in_range)

        # ---- the CLI render path runs without crashing on this corpus ----
        render_ok = True
        try:
            import io
            import contextlib
            buf = io.StringIO()
            with contextlib.redirect_stdout(buf):
                _print_shape_table(traces, stats)
                _print_work_orders(orders)
            rendered = buf.getvalue()
            render_ok = ("SHAPE TABLE" in rendered) and ("WORK ORDERS" in rendered)
        except Exception as exc:
            render_ok = False
            ok("CLI render path", False, f"exception: {exc}")
        ok("CLI render path runs and prints both sections", render_ok)

    finally:
        whole_mri.STORE = saved_store
        shutil.rmtree(tmp_dir, ignore_errors=True)

    # ---- HERMETIC: real .anima byte-identical ----
    fingerprint_after = _dir_fingerprint(real_store)
    hermetic = (fingerprint_before == fingerprint_after)
    ok("REAL .anima is byte-identical before/after (hermetic)", hermetic,
       f"before={fingerprint_before[:12]} after={fingerprint_after[:12]}")

    print()
    if hermetic:
        print(f"  byte-identical proof: SHA-256 = {fingerprint_before}")
    print()

    if fails:
        print(f"WHOLE-SYSTEM MRI SHAPE+TUNING SELFTEST: FAIL ({len(fails)})")
        for f in fails:
            print(f"    - {f}")
        return 1
    print("WHOLE-SYSTEM MRI SHAPE+TUNING SELFTEST: PASS")
    return 0


# ---------------------------------------------------------------------------
# Arg parsing / entry
# ---------------------------------------------------------------------------

def _build_parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(
        prog="whole_mri_tune",
        description="Whole-System MRI — SHAPE (Phase 6) + TUNING work orders (Phase 7).",
    )
    p.add_argument("--name", default=DEFAULT_NAME,
                   help=f"creature trace file to read (default: {DEFAULT_NAME})")
    grp = p.add_mutually_exclusive_group()
    grp.add_argument("--all", action="store_true", help="analyze every recorded trace")
    grp.add_argument("--last", type=int, default=DEFAULT_LAST,
                     help=f"analyze the last N traces (default: {DEFAULT_LAST})")
    p.add_argument("--json", action="store_true", help="emit JSON instead of tables")
    p.add_argument("--selftest", action="store_true",
                   help="run the hermetic self-proof and exit")
    return p


def main(argv=None) -> int:
    args = _build_parser().parse_args(argv)
    if args.selftest:
        return _selftest()
    return _run_analyze(args)


if __name__ == "__main__":
    raise SystemExit(main())

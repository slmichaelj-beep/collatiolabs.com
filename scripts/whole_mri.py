#!/usr/bin/env python3
"""Whole-System MRI — VIEWER (Phase 5). The human-readable read-out of one organism's turn.

    "Vera MRI = the mind; Argus MRI = the machine; Whole-System MRI = the organism."

A turn through Vera leaves ONE UnifiedTrace (anima/whole_mri.py) that correlates the
COGNITIVE trace (what Vera thought, retrieved, generated, shipped) with the HOST trace
(what Argus saw the Mac do, before/during/after). This tool reads those traces back from
the certified, append-only store and renders them at a HUMAN level: not a raw JSON dump,
but — for anything notable — the ISSUE, what it MEANS in plain English, and the SUGGESTED
ACTION (the house style: issue → meaning → action).

This is the READER half. The PRODUCER (anima/whole_mri.py + the owner's _turn wiring)
writes one JSON object per line to  .anima/traces/whole_mri/<name>.jsonl ; this viewer
consumes that producer's public API and never touches anything else.

VIEWS / FILTERS:
  --last              render the most recent COMPLETE trace, in full
  --turn <turn_id>    render one specific trace by turn_id
  --slow              list turns by latency, slowest first (flags the slow ones)
  --expensive         list turns by cost (tokens_out + argus_calls + memory_writes + memory_reads)
  --unsafe            list ONLY turns where a safety flag is tripped (clean corpus => "all turns safe")
  --host-heavy        list turns by host-load magnitude (|cpu|+|mem|+|disk|+|net| + L1 of shape_delta)
  --argus             show ONLY turns where Argus was enabled
  --selftest          hermetic self-proof (fabricate a temp corpus, exercise every path, exit 0/1)
  --json              emit the selected view as machine output (pairs with any view above)

GUARDRAILS, non-negotiable:
  * READ-ONLY. This tool never writes a file and never raises out of its entry point. A
    missing store, a truncated line, a None field of any kind — render as a clearly-marked
    gap, never a stack trace. (A monitor that crashes on the thing it monitors is useless.)
  * It reads ONLY through the certified producer API (anima.whole_mri.{all,last,by_turn_id}),
    which reads .anima/traces/whole_mri/<name>.jsonl and nothing else.
  * ADDITIVE. It creates only this file; it edits no module, no server, no producer.
  * The --selftest path SYNTHESIZES its own corpus in a TemporaryDirectory (by redirecting
    whole_mri.STORE) and asserts the REAL .anima is byte-identical (SHA-256) before/after.

    python3 scripts/whole_mri.py --last                  # newest trace, in full
    python3 scripts/whole_mri.py --turn turn_2026_..._ab # one trace by id
    python3 scripts/whole_mri.py --slow                  # slowest turns first
    python3 scripts/whole_mri.py --expensive             # costliest turns first
    python3 scripts/whole_mri.py --unsafe                # only turns with a tripped safety flag
    python3 scripts/whole_mri.py --host-heavy            # heaviest host-load turns first
    python3 scripts/whole_mri.py --argus                 # only Argus-enabled turns
    python3 scripts/whole_mri.py --name Nova --last      # a specific creature
    python3 scripts/whole_mri.py --selftest              # synthesize + assert every view renders
"""

from __future__ import annotations

import argparse
import json
import os
import sys
from pathlib import Path
from typing import Any, Optional

# Import the certified producer. The viewer is built ON it and reads ONLY through it.
_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if _ROOT not in sys.path:
    sys.path.insert(0, _ROOT)

from anima import whole_mri  # noqa: E402  (path set above)

# Fallback creature when nothing is configured and no trace file exists yet.
_DEFAULT_NAME = "vera"

_W = 92  # render width


# ===================================================================================
# DEFAULT NAME RESOLUTION — pick a sensible creature when --name is omitted.
#   1. the most-recently-written <name>.jsonl under the whole_mri trace dir, else
#   2. "vera".
# Never raises; a missing/unreadable store simply collapses to the fallback.
# ===================================================================================
def default_name() -> str:
    """The creature to read when --name is not given.

    Prefers the most recently modified ``<name>.jsonl`` in the producer's trace dir
    (so ``--last`` "just works" on whoever was last active); falls back to "vera".
    """
    try:
        trace_dir = whole_mri.STORE / "traces" / "whole_mri"
        if trace_dir.is_dir():
            newest: Optional[Path] = None
            newest_mtime = -1.0
            for p in trace_dir.glob("*.jsonl"):
                try:
                    m = p.stat().st_mtime
                except OSError:
                    continue
                if m > newest_mtime:
                    newest_mtime = m
                    newest = p
            if newest is not None:
                return newest.stem
    except Exception:
        pass
    return _DEFAULT_NAME


# ===================================================================================
# DEFENSIVE ACCESSORS — every reader tolerates None / wrong-type / missing.
# Nothing below this line is allowed to raise on a malformed or sparse trace.
# ===================================================================================
def _get(d: Any, key: str, default: Any = None) -> Any:
    """d[key] when d is a dict, else default. Never raises."""
    if isinstance(d, dict):
        v = d.get(key, default)
        return v if v is not None else default
    return default


def _sub(trace: Any, block: str) -> dict:
    """Return a named sub-block ('vera'/'argus'/'cost'/...) as a dict (empty if absent)."""
    v = _get(trace, block)
    return v if isinstance(v, dict) else {}


def _num(v: Any) -> Optional[float]:
    """Coerce to float, treating bools and junk as 'no number'. None stays None."""
    if isinstance(v, bool) or v is None:
        return None
    try:
        return float(v)
    except (TypeError, ValueError):
        return None


def _num0(v: Any) -> float:
    """Coerce to float, defaulting missing/None/junk to 0.0 (for ranking sums)."""
    n = _num(v)
    return n if n is not None else 0.0


def _is_true(v: Any) -> bool:
    """Strict-ish truthiness: only real True counts (so None/0/'' are not 'tripped')."""
    return v is True


def _yn(v: Any) -> str:
    """Render a tri-state boolean honestly: yes / no / n/a (None = unknown)."""
    if v is True:
        return "yes"
    if v is False:
        return "no"
    return "n/a"


def _fmt_num(v: Any, suffix: str = "") -> str:
    """Render a number honestly; None -> 'n/a'. Integers print clean, floats to 2dp."""
    n = _num(v)
    if n is None:
        return "n/a"
    if abs(n - round(n)) < 1e-9:
        return f"{int(round(n))}{suffix}"
    return f"{n:.2f}{suffix}"


def _ms(v: Any) -> str:
    """Render a latency value in ms, tolerating non-numbers."""
    n = _num(v)
    if n is None:
        return "n/a"
    return f"{int(round(n))} ms" if n >= 10 else f"{n:.1f} ms"


def _oneline(s: Any, width: int) -> str:
    """Collapse any value to a single printable line, clipped to width with an ellipsis."""
    if isinstance(s, (dict, list)):
        try:
            s = json.dumps(s, default=str, ensure_ascii=False)
        except (TypeError, ValueError):
            s = str(s)
    s = " ".join(str(s).split())
    if not s:
        return "(none)"
    return s if len(s) <= width else s[: max(1, width - 1)] + "..."


def _wrap(text: str, width: int, indent: str = "") -> list[str]:
    """Word-wrap a paragraph to width, each line prefixed with indent."""
    words = str(text).split()
    if not words:
        return [indent + "(none)"]
    lines: list[str] = []
    cur = indent
    for w in words:
        if cur != indent and len(cur) + 1 + len(w) > width:
            lines.append(cur)
            cur = indent + w
        else:
            cur = (cur + " " + w) if cur != indent else (indent + w)
    if cur.strip():
        lines.append(cur)
    return lines


def _hr(ch: str = "-") -> str:
    return ch * _W


def _label(trace: Any) -> str:
    """A short, stable label for a turn in list views: turn_id + kind + route."""
    tid = _oneline(_get(trace, "turn_id", "?"), 40)
    kind = _oneline(_get(trace, "input_kind", "?"), 14)
    route = _oneline(_get(trace, "route", "?"), 10)
    return f"{tid}  [{kind} / {route}]"


# ===================================================================================
# RANKING / SCORING — pure functions. Both the CLI list views and the selftest call
# these directly, so the selftest exercises the REAL ranking code paths.
# ===================================================================================
def latency_of(trace: Any) -> float:
    """The turn's latency in ms (0.0 when unknown) — the --slow sort key."""
    return _num0(_get(_sub(trace, "cost"), "latency_ms"))


def cost_score(trace: Any) -> float:
    """The --expensive score: tokens_out + argus_calls + memory_writes + memory_reads.

    Each missing term counts as 0, so a sparse trace simply ranks low rather than crashing.
    """
    cost = _sub(trace, "cost")
    return (
        _num0(_get(cost, "tokens_out"))
        + _num0(_get(cost, "argus_calls"))
        + _num0(_get(cost, "memory_writes"))
        + _num0(_get(cost, "memory_reads"))
    )


def has_host_window(trace: Any) -> bool:
    """True iff this turn carries a real host window (some non-None before/during/after,
    not the graceful-unavailable marker). --host-heavy skips turns without one."""
    argus = _sub(trace, "argus")
    for key in ("host_before", "host_during", "host_after"):
        v = _get(argus, key)
        if isinstance(v, dict) and not v.get("unavailable"):
            return True
    return False


def host_load_score(trace: Any) -> float:
    """The --host-heavy magnitude: |cpu_delta|+|memory_delta_mb|+|disk_io_delta|+|network_delta|
    plus the L1 norm of the shape_delta values. Missing terms contribute 0."""
    cost = _sub(trace, "cost")
    total = (
        abs(_num0(_get(cost, "cpu_delta")))
        + abs(_num0(_get(cost, "memory_delta_mb")))
        + abs(_num0(_get(cost, "disk_io_delta")))
        + abs(_num0(_get(cost, "network_delta")))
    )
    shape_delta = _get(_sub(trace, "argus"), "shape_delta")
    if isinstance(shape_delta, dict):
        for v in shape_delta.values():
            total += abs(_num0(v))
    return total


def safety_flags(trace: Any) -> list[str]:
    """Plain-English list of the safety flags TRIPPED on this turn (empty == clean).

    A turn is unsafe if any of:
      - final_gate_passed is False   (the last gate did NOT pass)
      - response_complete is False   (the reply was cut short)
      - identity_mutation is True     (Vera's identity changed — must never happen)
      - host_action_taken is True     (a host action ran — must never happen in this wave)
      - memory_contamination is True  (host data leaked into durable memory)
    None (unknown) is NOT treated as tripped — honest absence, not a false alarm.
    """
    s = _sub(trace, "safety")
    tripped: list[str] = []
    if _get(s, "final_gate_passed") is False:
        tripped.append("final gate did NOT pass")
    if _get(s, "response_complete") is False:
        tripped.append("response was incomplete (cut short)")
    if _is_true(_get(s, "identity_mutation")):
        tripped.append("identity mutation occurred")
    if _is_true(_get(s, "host_action_taken")):
        tripped.append("a host action was taken")
    if _is_true(_get(s, "memory_contamination")):
        tripped.append("memory contamination (host data → durable memory)")
    return tripped


def is_unsafe(trace: Any) -> bool:
    """True iff any safety flag is tripped on this turn."""
    return bool(safety_flags(trace))


def argus_enabled(trace: Any) -> bool:
    """True iff Argus host-awareness was enabled for this turn."""
    return _is_true(_get(_sub(trace, "argus"), "enabled"))


# ===================================================================================
# FILTER / RANK over a corpus — return ordered lists of traces. Pure; selftest-driven.
# ===================================================================================
def rank_slow(traces: list[dict]) -> list[dict]:
    """All turns, slowest first (by latency_ms)."""
    return sorted(traces, key=latency_of, reverse=True)


def rank_expensive(traces: list[dict]) -> list[dict]:
    """All turns, costliest first (by cost_score)."""
    return sorted(traces, key=cost_score, reverse=True)


def select_unsafe(traces: list[dict]) -> list[dict]:
    """ONLY turns with a tripped safety flag, newest-relevant first (preserve input order)."""
    return [t for t in traces if is_unsafe(t)]


def rank_host_heavy(traces: list[dict]) -> list[dict]:
    """Turns WITH a host window, heaviest host-load first. Turns with no window are skipped."""
    windowed = [t for t in traces if has_host_window(t)]
    return sorted(windowed, key=host_load_score, reverse=True)


def select_argus(traces: list[dict]) -> list[dict]:
    """ONLY turns where Argus was enabled (input order preserved)."""
    return [t for t in traces if argus_enabled(t)]


# A "slow" threshold for flagging in the list view: a turn is flagged slow if its latency
# is both above this floor AND in the worst third of the corpus. Plain heuristic, no jargon.
_SLOW_FLOOR_MS = 2000.0


# ===================================================================================
# HUMAN-LEVEL NOTES — issue -> what it means -> suggested action (the house style).
# Each returns a list of (issue, meaning, action) tuples for the render to lay out.
# ===================================================================================
def notes_for(trace: Any) -> list[tuple[str, str, str]]:
    """Notable findings on a single trace, each as (issue, meaning, action).

    Empty when the turn is clean and unremarkable. This is where the viewer earns its
    keep: it does not just print fields, it tells you what to DO about the interesting ones.
    """
    notes: list[tuple[str, str, str]] = []
    cost = _sub(trace, "cost")
    quality = _sub(trace, "quality")
    argus = _sub(trace, "argus")

    # Safety flags first — these are the loudest.
    for flag in safety_flags(trace):
        if "final gate" in flag:
            notes.append((
                "Final gate did not pass.",
                "The last safety check before shipping failed — this reply should not have gone out as-is.",
                "Open this turn, find why the gate failed, and harden the final gate before trusting this path.",
            ))
        elif "incomplete" in flag:
            notes.append((
                "The response was cut short.",
                "The reply was marked incomplete — the user likely got a truncated or partial answer.",
                "Check the generation step for an early stop or token cap, and re-run completeness.",
            ))
        elif "identity mutation" in flag:
            notes.append((
                "Identity mutation occurred.",
                "Vera's sense of self changed during this turn — the #1 rule says this must never happen.",
                "Treat as critical: find the write that touched identity and block that path immediately.",
            ))
        elif "host action" in flag:
            notes.append((
                "A host action was taken.",
                "Something acted on the Mac — but this wave is read-only and no action surface should exist.",
                "Treat as critical: identify the call, confirm it was inert, and assert no action path is reachable.",
            ))
        elif "contamination" in flag:
            notes.append((
                "Memory contamination.",
                "Host data appears to have leaked into durable memory — host facts must not auto-promote.",
                "Find the write, purge the contaminated entry, and re-assert the no-auto-LIRF guard.",
            ))

    # Latency.
    lat = _num(_get(cost, "latency_ms"))
    if lat is not None and lat >= _SLOW_FLOOR_MS:
        notes.append((
            f"Slow turn ({_ms(lat)}).",
            "This turn took noticeably longer than a snappy reply — the user waited.",
            "Check the route: a memory-heavy retrieval or an avoidable LLM call is the usual cause; "
            "consider routing to LERF or caching.",
        ))

    # Argus enabled but capabilities not OK (handshake/up failed) — graceful but worth saying.
    if argus_enabled(trace) and _get(argus, "capabilities_ok") is False:
        notes.append((
            "Host awareness was on, but Argus did not answer.",
            "Vera wanted host context but the certified Argus handshake or connection failed; "
            "she answered without live host data.",
            "Confirm Argus is running and certified (loopback, read-only). If intentional, no action needed.",
        ))

    # Blind spots the host reported.
    blinds = _get(argus, "blind_spots")
    if isinstance(blinds, list) and blinds:
        notes.append((
            f"Host reported {len(blinds)} blind spot(s).",
            "There are parts of the machine Argus could not see this turn, so the host picture is partial.",
            "Note what was unseen (" + _oneline(blinds, 50) + ") before trusting any 'all clear' on the host.",
        ))

    # Quality: ungrounded or unlabeled answers.
    if _get(quality, "grounded") is False:
        notes.append((
            "Answer was not grounded.",
            "The reply was not tied to retrieved evidence — higher risk of a confident-but-wrong answer.",
            "Check what memory/LERF was available; if evidence existed, fix retrieval; if not, prefer a hedge.",
        ))
    if _get(quality, "source_labeled") is False and _get(trace, "route") in ("source", "hybrid", "lerf"):
        notes.append((
            "Sources were not labeled.",
            "The answer drew on sources but didn't say which — the user can't check the provenance.",
            "Turn on source labeling for this route so each claim shows where it came from.",
        ))

    return notes


# ===================================================================================
# RENDER — a single trace, in full, at a human level. Returns a string (never prints).
# ===================================================================================
def render_full(trace: Any, name: str) -> str:
    """The full single-turn read-out used by --last and --turn.

    Sections (per the contract): WHAT HAPPENED · WHY / ROUTE · WHAT VERA USED ·
    WHAT ARGUS SAW · HOST CHANGE · COST · WRITTEN · SKIPPED / STRIPPED · SHIPPED ·
    GATE VERDICT · NOTES (issue -> meaning -> action). Robust to None throughout.
    """
    if not isinstance(trace, dict):
        return _hr("=") + "\nWHOLE-SYSTEM MRI\n" + _hr("=") + "\n  (trace is empty or malformed)\n"

    vera = _sub(trace, "vera")
    argus = _sub(trace, "argus")
    quality = _sub(trace, "quality")
    cost = _sub(trace, "cost")
    safety = _sub(trace, "safety")

    L: list[str] = []
    L.append(_hr("="))
    L.append(f"WHOLE-SYSTEM MRI  ·  {name}")
    L.append(_hr("="))
    L.append(f"  turn_id : {_get(trace, 'turn_id', '?')}")
    L.append(f"  when    : {_get(trace, 'ts', 'n/a')}")
    L.append("")

    # ---- WHAT HAPPENED -------------------------------------------------------------
    kind = _get(trace, "input_kind", "unknown")
    kind_plain = {
        "chat": "an ordinary chat message",
        "host_question": "a question about the Mac / host",
        "task": "a task to perform",
        "memory": "a memory lookup",
        "source": "a question against ingested sources",
        "unknown": "an unclassified input",
    }.get(str(kind), str(kind))
    L.append("WHAT HAPPENED")
    L.append(f"  Input kind : {kind}")
    L += _wrap(f"In plain terms: this turn handled {kind_plain}.", _W - 2, "  ")
    L.append("")

    # ---- WHY / ROUTE ---------------------------------------------------------------
    route = _get(trace, "route", "?")
    route_why = {
        "memory": "answered straight from stored memory (no model needed).",
        "lerf": "answered with a certified local skill (LERF) — the LLM was demoted or skipped.",
        "argus": "routed to the host monitor (Argus) because it was a question about the machine.",
        "llm": "fell through to the language model for genuine reasoning.",
        "source": "answered from ingested sources with provenance.",
        "hybrid": "blended more than one path (e.g. memory + model).",
    }.get(str(route), "took an unrecognized route.")
    L.append("WHY / ROUTE")
    L.append(f"  Route : {route}")
    L += _wrap(f"Why this route: Vera {route_why}", _W - 2, "  ")
    L.append("")

    # ---- WHAT VERA USED ------------------------------------------------------------
    L.append("WHAT VERA USED")
    L.append(f"  Memory reads     : {_fmt_num(_get(cost, 'memory_reads'))}")
    L.append(f"  LERF objects used: {_fmt_num(_get(cost, 'lerf_objects_used'))}")
    gen = _get(vera, "generation")
    gen_model = None
    if isinstance(gen, dict):
        gen_model = gen.get("model") or gen.get("backend") or gen.get("engine")
    L.append(f"  Generation model : {_oneline(gen_model, 60) if gen_model is not None else 'n/a'}")
    wm = _get(vera, "world_model")
    if wm is not None:
        L.append(f"  World model      : {_oneline(wm, _W - 22)}")
    rl = _get(vera, "reality_learning")
    if rl is not None:
        L.append(f"  Reality learning : {_oneline(rl, _W - 22)}")
    lerf_detail = _get(vera, "lerf")
    if lerf_detail is not None:
        L.append(f"  LERF detail      : {_oneline(lerf_detail, _W - 22)}")
    mem_detail = _get(vera, "memory")
    if mem_detail is not None:
        L.append(f"  Memory detail    : {_oneline(mem_detail, _W - 22)}")
    L.append("")

    # ---- WHAT ARGUS SAW ------------------------------------------------------------
    L.append("WHAT ARGUS SAW")
    enabled = _get(argus, "enabled")
    L.append(f"  Host awareness   : {_yn(enabled)}")
    if _is_true(enabled):
        L.append(f"  Argus certified  : {_yn(_get(argus, 'capabilities_ok'))}")
        queries = _get(argus, "queries")
        if isinstance(queries, list) and queries:
            L.append(f"  Host queries     : {_oneline(queries, _W - 22)}")
        else:
            L.append("  Host queries     : none")
        # before/during/after status
        for slot in ("host_before", "host_during", "host_after"):
            v = _get(argus, slot)
            short = slot.replace("host_", "")
            tag = f"Host {short}"
            if isinstance(v, dict):
                if v.get("unavailable"):
                    L.append(f"  {tag:<17}: unavailable ({_oneline(v.get('reason'), 40)})")
                else:
                    status = v.get("status")
                    L.append(f"  {tag:<17}: captured" +
                             (f" (status: {_oneline(status, 30)})" if status else ""))
            else:
                L.append(f"  {tag:<17}: n/a")
        blinds = _get(argus, "blind_spots")
        if isinstance(blinds, list) and blinds:
            L.append(f"  Blind spots      : {_oneline(blinds, _W - 22)}")
        else:
            L.append("  Blind spots      : none reported")
    else:
        L += _wrap("Host awareness was off for this turn, so Vera could not inspect the Mac live.",
                   _W - 2, "  ")
    L.append("")

    # ---- HOST CHANGE ---------------------------------------------------------------
    L.append("HOST CHANGE  (after - before; honest n/a when not measured)")
    if not _is_true(enabled) and not has_host_window(trace):
        L.append("  (no host window — host awareness off or Argus unavailable)")
    else:
        L.append(f"  CPU delta        : {_fmt_num(_get(cost, 'cpu_delta'), '%')}")
        L.append(f"  Memory delta     : {_fmt_num(_get(cost, 'memory_delta_mb'), ' MB')}")
        L.append(f"  Disk I/O delta   : {_fmt_num(_get(cost, 'disk_io_delta'))}")
        L.append(f"  Network delta    : {_fmt_num(_get(cost, 'network_delta'))}")
        shape_delta = _get(argus, "shape_delta")
        if isinstance(shape_delta, dict) and shape_delta:
            parts = []
            for k in sorted(shape_delta):
                parts.append(f"{k}={_fmt_num(shape_delta[k])}")
            L += _wrap("Shape delta      : " + ", ".join(parts), _W - 2, "  ")
        else:
            L.append("  Shape delta      : n/a")
    L.append("")

    # ---- COST ----------------------------------------------------------------------
    L.append("COST")
    L.append(f"  Latency          : {_ms(_get(cost, 'latency_ms'))}")
    L.append(f"  Tokens in / out  : {_fmt_num(_get(cost, 'tokens_in'))} / {_fmt_num(_get(cost, 'tokens_out'))}")
    L.append(f"  Argus calls      : {_fmt_num(_get(cost, 'argus_calls'))}")
    L.append(f"  Memory reads     : {_fmt_num(_get(cost, 'memory_reads'))}")
    L.append("")

    # ---- WRITTEN -------------------------------------------------------------------
    L.append("WRITTEN")
    writes = _get(cost, "memory_writes")
    nwrites = _num(writes)
    if nwrites is None:
        L.append("  Memory writes    : n/a")
    elif nwrites == 0:
        L.append("  Memory writes    : 0 (nothing new committed to durable memory)")
    else:
        L.append(f"  Memory writes    : {_fmt_num(writes)} new entr(y/ies) committed")
    L.append("")

    # ---- SKIPPED / STRIPPED --------------------------------------------------------
    # Anything the trace explicitly marks as skipped/stripped/dropped, in vera.* or top-level.
    L.append("SKIPPED / STRIPPED")
    skipped_lines: list[str] = []
    for blockname, block in (("vera", vera), ("trace", trace)):
        if not isinstance(block, dict):
            continue
        for marker in ("skipped", "stripped", "dropped", "blanked", "redacted"):
            v = block.get(marker)
            if v not in (None, "", [], {}, False):
                skipped_lines.append(f"  {marker} ({blockname}): {_oneline(v, _W - 24)}")
    # generation sub-block can carry its own skip markers
    if isinstance(gen, dict):
        for marker in ("skipped", "stripped", "dropped"):
            v = gen.get(marker)
            if v not in (None, "", [], {}, False):
                skipped_lines.append(f"  {marker} (generation): {_oneline(v, _W - 26)}")
    if skipped_lines:
        L += skipped_lines
    else:
        L.append("  (nothing the trace marks as skipped or stripped)")
    L.append("")

    # ---- SHIPPED -------------------------------------------------------------------
    L.append("SHIPPED")
    resp = _get(vera, "response")
    if isinstance(resp, dict):
        chars = resp.get("chars")
        backend = resp.get("backend") or resp.get("via") or resp.get("source")
        L.append(f"  Response length  : {_fmt_num(chars, ' chars') if chars is not None else 'n/a'}")
        L.append(f"  Shipped via      : {_oneline(backend, 50) if backend is not None else 'n/a'}")
        preview = resp.get("preview") or resp.get("text")
        if preview:
            L += _wrap("Preview          : " + _oneline(preview, 400), _W - 2, "  ")
    elif resp is not None:
        L.append(f"  Response         : {_oneline(resp, _W - 22)}")
    else:
        L.append("  (no response recorded)")
    L.append("")

    # ---- GATE VERDICT --------------------------------------------------------------
    L.append("GATE VERDICT")
    fg = _get(safety, "final_gate_passed")
    rc = _get(safety, "response_complete")
    L.append(f"  Final gate passed: {_yn(fg)}")
    L.append(f"  Response complete: {_yn(rc)}")
    fg_dict = _get(vera, "final_gate")
    if isinstance(fg_dict, dict):
        verdict = fg_dict.get("verdict") or fg_dict.get("reason") or fg_dict.get("note")
        if verdict:
            L += _wrap("Gate note        : " + _oneline(verdict, 300), _W - 2, "  ")
    if fg is True and rc is True:
        L.append("  -> Clean: the last gate held and the reply shipped complete.")
    L.append("")

    # ---- NOTES (issue -> meaning -> action) ---------------------------------------
    notes = notes_for(trace)
    L.append("NOTES  (issue -> what it means -> what to do)")
    if not notes:
        L.append("  Nothing notable — this turn looks clean.")
    else:
        for i, (issue, meaning, action) in enumerate(notes, 1):
            L += _wrap(f"{i}. {issue}", _W - 2, "  ")
            L += _wrap(f"means : {meaning}", _W - 4, "      ")
            L += _wrap(f"do    : {action}", _W - 4, "      ")
            if i != len(notes):
                L.append("")
    L.append(_hr("="))
    return "\n".join(L)


# ===================================================================================
# RENDER — a ranked / filtered LIST view. Returns a string (never prints).
# ===================================================================================
def render_list(
    traces: list[dict],
    name: str,
    title: str,
    *,
    metric_label: str,
    metric_fn,
    metric_suffix: str = "",
    flag_fn=None,
    empty_msg: Optional[str] = None,
) -> str:
    """A ranked/filtered table: one row per turn, its metric, and an optional flag.

    metric_fn(trace) -> number rendered next to each row; flag_fn(trace) -> bool marks
    a row with '<<' and a trailing reason. empty_msg overrides the default empty text.
    """
    L: list[str] = []
    L.append(_hr("="))
    L.append(f"WHOLE-SYSTEM MRI · {title} · {name}")
    L.append(_hr("="))
    if not traces:
        L.append("  " + (empty_msg or "no turns match."))
        L.append(_hr("="))
        return "\n".join(L)

    L.append(f"  {len(traces)} turn(s), {metric_label}:")
    L.append("  " + _hr("-")[2:])
    for rank, t in enumerate(traces, 1):
        metric = metric_fn(t)
        flagged = bool(flag_fn(t)) if flag_fn else False
        mark = " <<" if flagged else ""
        metric_str = _fmt_num(metric, metric_suffix) if isinstance(metric, (int, float)) else str(metric)
        L.append(f"  {rank:>2}. {_label(t)}")
        L.append(f"      {metric_label.rstrip(':')}: {metric_str}{mark}")
    L.append(_hr("="))
    L.append("  Tip: re-run with  --turn <turn_id>  to open any turn in full.")
    return "\n".join(L)


# ===================================================================================
# SELFTEST — hermetic. Fabricate a diverse corpus in a temp .anima, exercise every
# render/filter/rank path IN-PROCESS, and assert the REAL .anima is byte-identical.
# ===================================================================================
def _dir_fingerprint(p: Path) -> str:
    """SHA-256 of every byte in every file under p, sorted by path. Empty dir => empty hash."""
    import hashlib
    h = hashlib.sha256()
    if not p.exists():
        return h.hexdigest()
    for fp in sorted(p.rglob("*")):
        if fp.is_file():
            try:
                h.update(fp.read_bytes())
            except OSError:
                h.update(b"<unreadable>")
    return h.hexdigest()


def _selftest() -> int:  # pragma: no cover - exercised via the CLI
    import shutil
    import tempfile

    fails: list[str] = []

    def ok(label: str, cond: bool) -> None:
        print(("  ok   " if cond else "  FAIL ") + label)
        if not cond:
            fails.append(label)

    print("whole-system MRI VIEWER self-test")
    print()

    # ---- fingerprint the REAL .anima BEFORE (hermetic proof) -----------------------
    real_store = Path(_ROOT) / ".anima"
    fp_before = _dir_fingerprint(real_store)

    # ---- redirect the producer's STORE to a temp dir -------------------------------
    tmp_dir = tempfile.mkdtemp(prefix="whole_mri_viewer_selftest_")
    saved_store = whole_mri.STORE
    whole_mri.STORE = Path(tmp_dir) / ".anima"

    NAME = "ViewerSelftest"
    ids: dict[str, str] = {}

    try:
        # ---- fabricate a DIVERSE corpus via the real producer ----------------------
        # 1. a PLAIN chat/llm turn — unremarkable baseline.
        ids["plain"] = whole_mri.mint_turn_id()
        whole_mri.record(NAME, whole_mri.assemble(
            turn_id=ids["plain"], input_kind="chat", route="llm",
            vera={"generation": {"model": "local-7b"}, "response": {"chars": 42, "backend": "local"}},
            quality={"grounded": True, "complete": True, "confidence": 0.8},
            cost={"latency_ms": 150, "tokens_in": 30, "tokens_out": 20, "argus_calls": 0,
                  "memory_reads": 1, "memory_writes": 0},
            safety={"final_gate_passed": True, "response_complete": True, "identity_mutation": False,
                    "host_action_taken": False, "memory_contamination": False},
        ))

        # 2. a SLOW turn — very high latency.
        ids["slow"] = whole_mri.mint_turn_id()
        whole_mri.record(NAME, whole_mri.assemble(
            turn_id=ids["slow"], input_kind="task", route="memory",
            vera={"response": {"chars": 10, "backend": "memory"}},
            cost={"latency_ms": 99000, "tokens_in": 5, "tokens_out": 5, "argus_calls": 0,
                  "memory_reads": 2, "memory_writes": 0},
            safety={"final_gate_passed": True, "response_complete": True, "host_action_taken": False,
                    "memory_contamination": False, "identity_mutation": False},
        ))

        # 3. an EXPENSIVE turn — high tokens_out + argus_calls (+ writes/reads).
        ids["expensive"] = whole_mri.mint_turn_id()
        whole_mri.record(NAME, whole_mri.assemble(
            turn_id=ids["expensive"], input_kind="chat", route="hybrid",
            vera={"generation": {"model": "cloud-xl"}, "response": {"chars": 4000, "backend": "cloud"}},
            cost={"latency_ms": 800, "tokens_in": 2000, "tokens_out": 9000, "argus_calls": 5,
                  "memory_reads": 7, "memory_writes": 3},
            safety={"final_gate_passed": True, "response_complete": True, "host_action_taken": False,
                    "memory_contamination": False, "identity_mutation": False},
        ))

        # 4. an UNSAFE turn — final_gate_passed False AND response_complete False.
        ids["unsafe"] = whole_mri.mint_turn_id()
        whole_mri.record(NAME, whole_mri.assemble(
            turn_id=ids["unsafe"], input_kind="chat", route="llm",
            vera={"response": {"chars": 3, "backend": "local"}},
            quality={"grounded": False, "complete": False, "confidence": 0.2},
            cost={"latency_ms": 300, "tokens_in": 50, "tokens_out": 2, "argus_calls": 0,
                  "memory_reads": 0, "memory_writes": 0},
            safety={"final_gate_passed": False, "response_complete": False, "identity_mutation": False,
                    "host_action_taken": False, "memory_contamination": False},
        ))

        # 5. a HOST-HEAVY turn — large cpu/memory deltas + a shape_delta dict + a host window.
        host_snap_before = {"shape": {"cpu": 0.0, "network": 0.0}, "status": "running",
                            "blind_spots": [], "cpu_pct": 5.0, "memory_mb": 100.0}
        host_snap_after = {"shape": {"cpu": 9.0, "network": 4.0}, "status": "running",
                           "blind_spots": ["sandboxed-proc"], "cpu_pct": 85.0, "memory_mb": 900.0}
        ids["host_heavy"] = whole_mri.mint_turn_id()
        whole_mri.record(NAME, whole_mri.assemble(
            turn_id=ids["host_heavy"], input_kind="host_question", route="argus",
            vera={"response": {"chars": 200, "backend": "host"}},
            argus={"enabled": True, "capabilities_ok": True, "queries": ["cpu", "network"],
                   "host_before": host_snap_before, "host_during": host_snap_after,
                   "host_after": host_snap_after,
                   "shape_delta": {"cpu": 9.0, "network": 4.0}, "blind_spots": ["sandboxed-proc"]},
            quality={"host_labeled": True, "grounded": True, "complete": True},
            cost={"latency_ms": 600, "tokens_in": 40, "tokens_out": 60, "argus_calls": 3,
                  "memory_reads": 0, "memory_writes": 0,
                  "cpu_delta": 80.0, "memory_delta_mb": 800.0, "disk_io_delta": 50.0,
                  "network_delta": 30.0},
            safety={"final_gate_passed": True, "response_complete": True, "host_action_taken": False,
                    "memory_contamination": False, "identity_mutation": False},
        ))

        # 6. an ARGUS turn (enabled) with a full host window but SMALL deltas (distinct from
        #    host-heavy, and confirms --argus selects it while --host-heavy ranks it below #5).
        ids["argus"] = whole_mri.mint_turn_id()
        whole_mri.record(NAME, whole_mri.assemble(
            turn_id=ids["argus"], input_kind="host_question", route="argus",
            vera={"response": {"chars": 80, "backend": "host"}},
            argus={"enabled": True, "capabilities_ok": True, "queries": ["mri"],
                   "host_before": {"shape": {"cpu": 1.0}, "status": "running", "blind_spots": []},
                   "host_during": {"shape": {"cpu": 1.1}, "status": "running", "blind_spots": []},
                   "host_after": {"shape": {"cpu": 1.2}, "status": "running", "blind_spots": []},
                   "shape_delta": {"cpu": 0.2}, "blind_spots": []},
            quality={"host_labeled": True},
            cost={"latency_ms": 200, "tokens_in": 10, "tokens_out": 10, "argus_calls": 3,
                  "memory_reads": 0, "memory_writes": 0,
                  "cpu_delta": 0.2, "memory_delta_mb": 1.0, "disk_io_delta": 0.0,
                  "network_delta": 0.0},
            safety={"final_gate_passed": True, "response_complete": True, "host_action_taken": False,
                    "memory_contamination": False, "identity_mutation": False},
        ))

        corpus = whole_mri.all(NAME)
        ok("corpus has 6 traces", len(corpus) == 6)

        # ---- --last renders the newest without error -------------------------------
        last_trace = whole_mri.last(NAME)
        ok("last() returns the newest (argus turn)",
           last_trace is not None and last_trace.get("turn_id") == ids["argus"])
        rendered_last = render_full(last_trace, NAME)
        ok("render_full(--last) produced output", isinstance(rendered_last, str) and len(rendered_last) > 200)
        ok("render_full has all required sections", all(
            sec in rendered_last for sec in (
                "WHAT HAPPENED", "WHY / ROUTE", "WHAT VERA USED", "WHAT ARGUS SAW",
                "HOST CHANGE", "COST", "WRITTEN", "SKIPPED / STRIPPED", "SHIPPED",
                "GATE VERDICT", "NOTES")))

        # ---- --turn <known id> renders that turn -----------------------------------
        got = whole_mri.by_turn_id(NAME, ids["slow"])
        ok("by_turn_id(slow) found the slow turn", got is not None and got.get("turn_id") == ids["slow"])
        rendered_turn = render_full(got, NAME)
        ok("render_full(--turn) contains the requested turn_id", ids["slow"] in rendered_turn)
        # unknown id -> not found (the CLI exits 1; here we assert the producer returns None)
        ok("by_turn_id(unknown) returns None", whole_mri.by_turn_id(NAME, "turn_0000_00_00_000000_zzzzzz") is None)

        # ---- --slow ranks the slow turn first --------------------------------------
        slow_ranked = rank_slow(corpus)
        ok("rank_slow ranks the slow turn first", slow_ranked[0].get("turn_id") == ids["slow"])
        ok("rank_slow is descending by latency",
           all(latency_of(slow_ranked[i]) >= latency_of(slow_ranked[i + 1])
               for i in range(len(slow_ranked) - 1)))

        # ---- --expensive ranks the expensive turn first ----------------------------
        exp_ranked = rank_expensive(corpus)
        ok("rank_expensive ranks the expensive turn first", exp_ranked[0].get("turn_id") == ids["expensive"])
        ok("rank_expensive is descending by cost",
           all(cost_score(exp_ranked[i]) >= cost_score(exp_ranked[i + 1])
               for i in range(len(exp_ranked) - 1)))

        # ---- --unsafe selects EXACTLY the unsafe turn ------------------------------
        unsafe = select_unsafe(corpus)
        unsafe_ids = {t.get("turn_id") for t in unsafe}
        ok("select_unsafe selects exactly the unsafe turn", unsafe_ids == {ids["unsafe"]})
        ok("the unsafe turn lists both tripped flags", len(safety_flags(
            whole_mri.by_turn_id(NAME, ids["unsafe"]))) == 2)
        # a clean corpus prints 'all turns safe' — prove the empty path renders that:
        clean_list = render_list([], NAME, "UNSAFE", metric_label="tripped flags",
                                 metric_fn=lambda t: 0,
                                 empty_msg="none -- all turns safe")
        ok("empty --unsafe renders 'all turns safe'", "all turns safe" in clean_list)

        # ---- --host-heavy ranks host-heavy first and skips no-window turns ---------
        hh = rank_host_heavy(corpus)
        ok("rank_host_heavy ranks the host-heavy turn first", hh[0].get("turn_id") == ids["host_heavy"])
        hh_ids = {t.get("turn_id") for t in hh}
        ok("rank_host_heavy includes only the two windowed (argus) turns",
           hh_ids == {ids["host_heavy"], ids["argus"]})
        ok("rank_host_heavy skips the plain/slow/expensive/unsafe (no-window) turns",
           ids["plain"] not in hh_ids and ids["slow"] not in hh_ids
           and ids["expensive"] not in hh_ids and ids["unsafe"] not in hh_ids)
        ok("rank_host_heavy is descending by host load",
           all(host_load_score(hh[i]) >= host_load_score(hh[i + 1]) for i in range(len(hh) - 1)))

        # ---- --argus selects only enabled turns ------------------------------------
        argus_sel = select_argus(corpus)
        argus_ids = {t.get("turn_id") for t in argus_sel}
        ok("select_argus selects exactly the two Argus-enabled turns",
           argus_ids == {ids["host_heavy"], ids["argus"]})

        # ---- list renderers don't crash on the real corpus -------------------------
        for title, ranked, mlabel, mfn, suffix, flagfn in (
            ("SLOWEST FIRST", slow_ranked, "latency", latency_of, " ms", lambda t: latency_of(t) >= _SLOW_FLOOR_MS),
            ("MOST EXPENSIVE", exp_ranked, "cost score", cost_score, "", None),
            ("HOST-HEAVY", hh, "host load", host_load_score, "", None),
            ("ARGUS-ENABLED", argus_sel, "argus calls",
             lambda t: _num0(_get(_sub(t, "cost"), "argus_calls")), "", None),
            ("UNSAFE", unsafe, "tripped flags", lambda t: len(safety_flags(t)), "", lambda t: True),
        ):
            out = render_list(ranked, NAME, title, metric_label=mlabel, metric_fn=mfn,
                              metric_suffix=suffix, flag_fn=flagfn)
            ok(f"render_list({title}) produced output", isinstance(out, str) and title in out)

        # ---- robustness: a sparse / all-None trace must not crash any path ---------
        sparse = {"turn_id": "turn_2026_01_01_000000_aaaaaa", "ts": "2026-01-01T00:00:00Z"}
        ok("render_full survives a near-empty trace", isinstance(render_full(sparse, NAME), str))
        ok("scoring survives a near-empty trace",
           latency_of(sparse) == 0.0 and cost_score(sparse) == 0.0
           and host_load_score(sparse) == 0.0 and not is_unsafe(sparse)
           and not has_host_window(sparse) and not argus_enabled(sparse))
        ok("render_full survives None", isinstance(render_full(None, NAME), str))

        # ---- empty corpus path (no traces for a name) ------------------------------
        ok("all() on unknown name is empty", whole_mri.all("__no_such_creature__") == [])

    finally:
        whole_mri.STORE = saved_store
        shutil.rmtree(tmp_dir, ignore_errors=True)

    # ---- HERMETIC: the REAL .anima must be byte-identical before/after -------------
    fp_after = _dir_fingerprint(real_store)
    ok("REAL .anima is byte-identical before/after (hermetic)", fp_before == fp_after)
    if fp_before == fp_after:
        print()
        print(f"  byte-identical proof: SHA-256 = {fp_before}")

    print()
    if fails:
        print(f"WHOLE-SYSTEM MRI VIEWER SELFTEST: FAIL ({len(fails)}): " + "; ".join(fails))
        return 1
    print("WHOLE-SYSTEM MRI VIEWER SELFTEST: PASS")
    return 0


# ===================================================================================
# ENTRY POINT — never raises; a missing store or malformed input is a rendered gap.
# ===================================================================================
def main(argv=None) -> int:
    ap = argparse.ArgumentParser(
        prog="whole_mri.py",
        description="Whole-System MRI VIEWER — the human-readable read-out of one turn "
                    "(the organism: Vera's mind + Argus's machine).")
    ap.add_argument("--name", default=None,
                    help="creature whose traces to read (default: the most recently written "
                         "whole_mri creature, else 'vera')")
    grp = ap.add_mutually_exclusive_group()
    grp.add_argument("--last", action="store_true", help="render the most recent complete trace, in full")
    grp.add_argument("--turn", metavar="TURN_ID", help="render a specific trace by turn_id")
    grp.add_argument("--slow", action="store_true", help="list turns by latency, slowest first")
    grp.add_argument("--expensive", action="store_true",
                     help="list turns by cost (tokens_out + argus_calls + memory_writes + memory_reads)")
    grp.add_argument("--unsafe", action="store_true",
                     help="list ONLY turns where a safety flag is tripped")
    grp.add_argument("--host-heavy", dest="host_heavy", action="store_true",
                     help="list turns by host-load magnitude (skips turns with no host window)")
    grp.add_argument("--argus", action="store_true", help="show ONLY turns where Argus was enabled")
    ap.add_argument("--json", action="store_true", help="emit the selected view as machine output")
    ap.add_argument("--selftest", action="store_true", help="run the hermetic self-test and exit")
    args = ap.parse_args(argv)

    if args.selftest:
        return _selftest()

    name = args.name or default_name()

    # Read the corpus through the certified producer API (read-only, tolerant of a missing store).
    try:
        traces = whole_mri.all(name)
    except Exception:
        traces = []

    # ----- single-trace views -------------------------------------------------------
    if args.turn:
        trace = None
        try:
            trace = whole_mri.by_turn_id(name, args.turn)
        except Exception:
            trace = None
        if trace is None:
            if args.json:
                print(json.dumps({"error": "turn not found", "name": name, "turn_id": args.turn}, indent=2))
            else:
                print(_hr("="))
                print(f"WHOLE-SYSTEM MRI · {name}")
                print(_hr("="))
                print(f"  turn_id {args.turn!r} not found for {name!r}.")
                print("  Tip: run with no flag (or --slow) to list the turns that exist.")
                print(_hr("="))
            return 1
        if args.json:
            print(json.dumps(trace, indent=2, default=str))
        else:
            print(render_full(trace, name))
        return 0

    # --last is the default single-trace view when nothing else is specified.
    want_last = args.last or not (args.slow or args.expensive or args.unsafe
                                  or args.host_heavy or args.argus)
    if want_last:
        if not traces:
            if args.json:
                print(json.dumps({"error": "no traces", "name": name}, indent=2))
            else:
                print(f"no Whole-System MRI traces yet for {name!r}.")
            return 0
        trace = traces[-1]
        if args.json:
            print(json.dumps(trace, indent=2, default=str))
        else:
            print(render_full(trace, name))
        return 0

    # ----- list / ranked views ------------------------------------------------------
    if not traces:
        if args.json:
            print(json.dumps({"error": "no traces", "name": name, "turns": []}, indent=2))
        else:
            print(f"no Whole-System MRI traces yet for {name!r}.")
        return 0

    if args.slow:
        ranked = rank_slow(traces)
        if args.json:
            print(json.dumps([{"turn_id": _get(t, "turn_id"), "latency_ms": latency_of(t),
                               "slow": latency_of(t) >= _SLOW_FLOOR_MS} for t in ranked],
                             indent=2, default=str))
        else:
            print(render_list(ranked, name, "SLOWEST FIRST", metric_label="latency",
                              metric_fn=latency_of, metric_suffix=" ms",
                              flag_fn=lambda t: latency_of(t) >= _SLOW_FLOOR_MS,
                              empty_msg="no turns to rank."))
        return 0

    if args.expensive:
        ranked = rank_expensive(traces)
        if args.json:
            print(json.dumps([{"turn_id": _get(t, "turn_id"), "cost_score": cost_score(t)}
                              for t in ranked], indent=2, default=str))
        else:
            print(render_list(ranked, name, "MOST EXPENSIVE", metric_label="cost score",
                              metric_fn=cost_score, empty_msg="no turns to rank."))
        return 0

    if args.unsafe:
        unsafe = select_unsafe(traces)
        if args.json:
            print(json.dumps([{"turn_id": _get(t, "turn_id"), "flags": safety_flags(t)}
                              for t in unsafe], indent=2, default=str))
        else:
            print(render_list(unsafe, name, "UNSAFE", metric_label="tripped flags",
                              metric_fn=lambda t: len(safety_flags(t)),
                              flag_fn=lambda t: True,
                              empty_msg="none -- all turns safe."))
        return 0

    if args.host_heavy:
        ranked = rank_host_heavy(traces)
        if args.json:
            print(json.dumps([{"turn_id": _get(t, "turn_id"), "host_load": host_load_score(t)}
                              for t in ranked], indent=2, default=str))
        else:
            print(render_list(ranked, name, "HOST-HEAVY", metric_label="host load",
                              metric_fn=host_load_score,
                              empty_msg="no turns with a host window."))
        return 0

    if args.argus:
        sel = select_argus(traces)
        if args.json:
            print(json.dumps([{"turn_id": _get(t, "turn_id"),
                               "argus_calls": _num0(_get(_sub(t, "cost"), "argus_calls"))}
                              for t in sel], indent=2, default=str))
        else:
            print(render_list(sel, name, "ARGUS-ENABLED", metric_label="argus calls",
                              metric_fn=lambda t: _num0(_get(_sub(t, "cost"), "argus_calls")),
                              empty_msg="no Argus-enabled turns."))
        return 0

    # Unreachable (the mutually-exclusive group + want_last cover every case), but be safe.
    print(f"no view selected for {name!r}; try --last.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

#!/usr/bin/env python3
"""VERA MRI — total turn introspection. The "movie" of a turn, frame by frame.

    "If we can see it, we can understand it."

A turn through Vera is a packet crossing eleven stages — perception, heart, capture,
route, bind, situation, meaning, curiosity, prompt, generate, verify. Each crossing
reshapes the data and (sometimes) drops something. When a reply feels wrong, the cause
is almost never the model — it is a SEAM: a stage that received a shape it didn't expect,
or a decision that quietly rejected the option you wanted. This viewer makes the whole
turn legible after the fact, so "why did she say that?" is answerable by looking.

This is the READER half of the MRI. A teammate (the Recorder) writes one JSON object per
turn to  .anima/{name}.mri.jsonl  in the schema below; this tool reads it back and renders
four views over a single turn:

  1. THE MOVIE     (default)        — the turn top-to-bottom: a packet trace
                                      Input -> Perception -> Heart -> ... -> Verify -> Response,
                                      each frame's headline + t_ms + one-line summary, with the
                                      user_text at the top, the reply at the bottom, total latency.
  2. THE X-RAY     (--stage NAME|i) — one frame in FULL: in_shape, complete out, dropped,
                                      confidence, note. Drill into any node.
  3. SHAPE OBS.    (--shapes)       — per boundary: received-shape vs expected-shape, the
                                      transformation, and the LOSS events crossing that seam.
                                      Where misunderstandings originate.
  4. DECISION OBS. (--why)          — the alternatives: every decision, what was SELECTED and
                                      what was REJECTED + why ("why curiosity asked X, not Y"),
                                      plus the conservation-this-turn (capture's dropped units).

  --json  emits the selected view as machine output.

THE TURN-TRACE SCHEMA (one JSON object per line in .anima/{name}.mri.jsonl):
  {
    "turn_id","name","at","user_text","reply","total_ms",
    "stages": [ {"stage","t_ms","in_shape","out","dropped":[],"confidence","note"} ],
    "shapes": [ {"boundary":"src->dst","received","expected","transformation","loss":[]} ],
    "alternatives": [ {"decision","selected","rejected":[{"option","reason"}]} ]
  }

GUARDRAILS, non-negotiable:
  * READ-ONLY. This tool NEVER writes a file and NEVER raises out of its entry point. A
    missing trace, a truncated line, a half-written object, a field of the wrong type — all
    render as a clearly-marked gap, never a stack trace. (A debugger that crashes on the bug
    it is debugging is useless.)
  * It never touches a real Vera.* state file: it READS .anima/{name}.mri.jsonl and nothing
    else. The --selftest path SYNTHESIZES its own schema-shaped trace in a TemporaryDirectory,
    so this viewer is testable and shippable BEFORE the Recorder lands — it does not depend on
    the Recorder writing first.
  * ADDITIVE. It creates only this file; it edits no module, no telemetry, no server.

    python3 scripts/mri.py [name] [--turn ID | --last]    # the movie (default)
    python3 scripts/mri.py [name] --stage meaning         # x-ray one frame
    python3 scripts/mri.py [name] --shapes                # shape observatory
    python3 scripts/mri.py [name] --why                   # decision observatory
    python3 scripts/mri.py [name] --last --json           # machine output
    python3 scripts/mri.py --selftest                     # synthesize + assert all views render
"""

from __future__ import annotations

import argparse
import json
import os
import sys
from pathlib import Path

_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
_ANIMA = Path(_ROOT) / ".anima"
DEFAULT_NAME = "Vera"

# The canonical pipeline, in order. The Recorder emits frames in this order; the viewer
# uses it to (a) sort/label frames deterministically even if the trace is out of order, and
# (b) draw the packet rail at the top of the movie. Index i in --stage <i> maps here.
STAGES = [
    "perception", "heart", "capture", "route", "bind",
    "situation", "meaning", "curiosity", "prompt", "generate", "verify",
]
# Short rail labels for the one-line packet trace (Input -> ... -> Response).
_RAIL = {
    "perception": "Perception", "heart": "Heart", "capture": "Capture",
    "route": "Route", "bind": "Bind", "situation": "Situation", "meaning": "Meaning",
    "curiosity": "Curiosity", "prompt": "Prompt", "generate": "Generate", "verify": "Verify",
}

_W = 92  # render width


# ===================================================================================
# READING — defensive to a fault. Every accessor tolerates None / wrong-type / missing.
# Nothing below this line is allowed to raise on malformed input.
# ===================================================================================
def trace_path(name: str, store: Path | None = None) -> Path:
    """.anima/{name}.mri.jsonl (or under an override store, for the selftest)."""
    return (store or _ANIMA) / f"{name}.mri.jsonl"


def read_turns(name: str, store: Path | None = None) -> tuple[list[dict], list[str]]:
    """Read all turn objects for a creature. Returns (turns, warnings).

    Append-only jsonl: one turn per line. We skip blank lines and lines that don't parse
    (a half-written final line is normal for a live file), recording each as a warning so
    the gap is VISIBLE rather than silent. Never raises.
    """
    path = trace_path(name, store)
    turns: list[dict] = []
    warnings: list[str] = []
    try:
        raw = path.read_text(encoding="utf-8", errors="replace")
    except FileNotFoundError:
        return [], [f"no trace at {path} (Recorder has not written this creature yet)"]
    except OSError as e:  # pragma: no cover - unreadable file
        return [], [f"could not read {path}: {e!r}"]
    for i, line in enumerate(raw.splitlines(), 1):
        line = line.strip()
        if not line:
            continue
        try:
            obj = json.loads(line)
        except (ValueError, TypeError):
            warnings.append(f"line {i}: unparseable JSON (skipped)")
            continue
        if isinstance(obj, dict):
            turns.append(obj)
        else:
            warnings.append(f"line {i}: not a JSON object (skipped)")
    return turns, warnings


def select_turn(turns: list[dict], turn_id: str | None, last: bool) -> dict | None:
    """Pick a turn: explicit --turn ID wins; else --last (or default) is the final line."""
    if not turns:
        return None
    if turn_id:
        for t in turns:
            if str(_get(t, "turn_id", "")) == str(turn_id):
                return t
        return None
    return turns[-1]  # --last and the bare default both mean "the most recent turn"


def _get(d, key, default=None):
    return d.get(key, default) if isinstance(d, dict) else default


def _frames(turn: dict) -> list[dict]:
    """Stage frames, ordered by the canonical pipeline, then by any others as-seen.

    A frame missing/with an unknown stage still renders (sorted last) — we never drop a
    frame just because its name is off-script; that itself would hide a bug.
    """
    frames = [f for f in _as_list(_get(turn, "stages")) if isinstance(f, dict)]
    order = {s: i for i, s in enumerate(STAGES)}
    return sorted(frames, key=lambda f: order.get(str(_get(f, "stage", "")), len(STAGES) + 1))


def _as_list(v) -> list:
    """Coerce any value to a list we can safely iterate (a non-list field — e.g. the
    Recorder wrote `alternatives: 5` — must not crash the viewer)."""
    return v if isinstance(v, list) else []


def _shapes(turn: dict) -> list[dict]:
    return [s for s in _as_list(_get(turn, "shapes")) if isinstance(s, dict)]


def _alternatives(turn: dict) -> list[dict]:
    return [a for a in _as_list(_get(turn, "alternatives")) if isinstance(a, dict)]


def find_frame(turn: dict, key: str) -> dict | None:
    """Resolve a --stage selector: a stage name (case-insensitive) OR an integer index.

    Index is into the canonical STAGES order as rendered, so `--stage 6` is the 7th frame
    of the movie (0-based), matching what the user just saw.
    """
    frames = _frames(turn)
    key = (key or "").strip()
    if key.lstrip("-").isdigit():
        idx = int(key)
        if -len(frames) <= idx < len(frames):
            return frames[idx]
        return None
    low = key.lower()
    for f in frames:
        if str(_get(f, "stage", "")).lower() == low:
            return f
    return None


# ===================================================================================
# FORMATTING HELPERS — plain ASCII, no color (matches conservation.py / certify.py).
# ===================================================================================
def _hr(ch: str = "─") -> str:
    return ch * _W


def _ms(v) -> str:
    """Render a t_ms / total_ms value, tolerating non-numbers."""
    if isinstance(v, bool) or not isinstance(v, (int, float)):
        return "  ? ms"
    return f"{v:>5.0f} ms" if v >= 10 else f"{v:>5.1f} ms"


def _oneline(s, width: int) -> str:
    """Collapse any value to one printable line, clipped to width with an ellipsis."""
    if isinstance(s, (dict, list)):
        s = json.dumps(s, default=str, ensure_ascii=False)
    s = " ".join(str(s).split())
    return s if len(s) <= width else s[: width - 1] + "…"


def _summary(frame: dict) -> str:
    """A one-line summary of a frame: its note, else a compact view of its out."""
    note = _get(frame, "note")
    if isinstance(note, str) and note.strip():
        return _oneline(note, _W - 30)
    out = _get(frame, "out")
    if out not in (None, "", {}, []):
        return _oneline(out, _W - 30)
    return "—"


def _conf(frame: dict) -> str:
    c = _get(frame, "confidence")
    if isinstance(c, bool) or not isinstance(c, (int, float)):
        return "    "
    return f"{c:>4.2f}"


def _block(value, indent: str = "    ") -> list[str]:
    """Pretty-print any JSON value as indented lines (for the x-ray full-detail dump)."""
    if value in (None, "", [], {}):
        return [indent + "(none)"]
    if isinstance(value, str):
        return [indent + ln for ln in value.splitlines()] or [indent + value]
    try:
        text = json.dumps(value, indent=2, default=str, ensure_ascii=False)
    except (TypeError, ValueError):  # pragma: no cover - last-resort
        text = str(value)
    return [indent + ln for ln in text.splitlines()]


def _wrap(text: str, width: int, indent: str = "") -> list[str]:
    """Word-wrap a paragraph to width, each line prefixed with indent."""
    words = str(text).split()
    if not words:
        return [indent + "—"]
    lines, cur = [], indent
    for w in words:
        if len(cur) + len(w) + (0 if cur == indent else 1) > width and cur != indent:
            lines.append(cur)
            cur = indent + w
        else:
            cur = (cur + " " + w) if cur != indent else (indent + w)
    if cur.strip():
        lines.append(cur)
    return lines


# ===================================================================================
# VIEW 1 — THE MOVIE. The turn, top to bottom, as a packet trace.
# ===================================================================================
def render_movie(turn: dict, name: str) -> str:
    L: list[str] = []
    frames = _frames(turn)
    tid = _get(turn, "turn_id", "?")
    at = _get(turn, "at", "")
    total = _get(turn, "total_ms")

    L.append(_hr("━"))
    L.append(f"VERA MRI · TURN {tid} · {name}" + (f"  ({at})" if at else ""))
    L.append(_hr("━"))

    # The glanceable packet rail.
    rail = ["Input"] + [_RAIL.get(str(_get(f, "stage", "")), str(_get(f, "stage", "?")))
                        for f in frames] + ["Response"]
    L.append("")
    for ln in _wrap(" -> ".join(rail), _W, indent="  "):
        L.append(ln)
    L.append("")

    # User text at the top.
    L.append("  USER ▸")
    L.extend(_wrap(_get(turn, "user_text", "") or "(empty)", _W - 4, indent="    "))
    L.append("")
    L.append("  " + _hr("─")[2:])

    # The frame timeline: headline + t_ms + confidence + a fixed DROP column + summary.
    # The drop flag lives in its own column BEFORE the clippable summary, so a frame that
    # lost something always shows it (the dropped count is the whole point of the movie).
    L.append(f"  {'#':>2}  {'STAGE':<11} {'t':>9}  {'conf':>4}  {'drop':>5}  SUMMARY")
    for i, f in enumerate(frames):
        stage = str(_get(f, "stage", "?"))
        ndrop = len(_as_list(_get(f, "dropped")))
        drop_col = f"⟂{ndrop:>2} ⤬" if ndrop else "  ·  "
        head = f"  {i:>2}  {stage:<11} {_ms(_get(f, 't_ms')):>9}  {_conf(f)}  {drop_col}  "
        L.append(head + _oneline(_summary(f), _W - len(head)))
    if not frames:
        L.append("  (no stage frames in this turn)")

    L.append("  " + _hr("─")[2:])

    # Reply at the bottom.
    L.append("")
    L.append("  VERA ▸")
    L.extend(_wrap(_get(turn, "reply", "") or "(empty)", _W - 4, indent="    "))
    L.append("")
    L.append(f"  TOTAL LATENCY: {_ms(total).strip()}"
             + (f"   ·   {len(frames)} frames" if frames else ""))
    # If frame t_ms are present, show the slowest stage — the obvious place to look.
    timed = [(str(_get(f, 'stage', '?')), _get(f, 't_ms')) for f in frames
             if isinstance(_get(f, 't_ms'), (int, float)) and not isinstance(_get(f, 't_ms'), bool)]
    if timed:
        slow = max(timed, key=lambda kv: kv[1])
        L.append(f"  SLOWEST STAGE: {slow[0]} ({_ms(slow[1]).strip()})")
    L.append(_hr("━"))
    L.append("  views:  --stage <name|i>  (x-ray a frame)   --shapes  (data seams)   "
             "--why  (decisions)")
    return "\n".join(L)


# ===================================================================================
# VIEW 2 — THE X-RAY. One frame, in full.
# ===================================================================================
def render_xray(turn: dict, frame: dict, selector: str, name: str) -> str:
    L: list[str] = []
    frames = _frames(turn)
    idx = frames.index(frame) if frame in frames else -1
    stage = str(_get(frame, "stage", "?"))
    tid = _get(turn, "turn_id", "?")

    L.append(_hr("━"))
    L.append(f"VERA MRI · X-RAY · TURN {tid} · stage [{idx}] {stage.upper()} · {name}")
    L.append(_hr("━"))
    # Where this frame sits in the rail.
    prev_s = str(_get(frames[idx - 1], "stage", "?")) if idx > 0 else "Input"
    next_s = str(_get(frames[idx + 1], "stage", "?")) if 0 <= idx < len(frames) - 1 else "Response"
    L.append(f"  in pipeline:  ... {prev_s}  ->  [{stage}]  ->  {next_s} ...")
    L.append("")
    L.append(f"  t_ms       : {_ms(_get(frame, 't_ms')).strip()}")
    conf = _get(frame, "confidence")
    L.append(f"  confidence : {conf if isinstance(conf, (int, float)) and not isinstance(conf, bool) else '(none)'}")
    L.append("")
    L.append("  note ▸")
    L.extend(_wrap(_get(frame, "note", "") or "(none)", _W - 4, indent="    "))
    L.append("")
    L.append("  in_shape ▸  (what this frame received)")
    L.extend(_block(_get(frame, "in_shape")))
    L.append("")
    L.append("  out ▸  (what this frame produced — full detail)")
    L.extend(_block(_get(frame, "out")))
    L.append("")
    dropped = _as_list(_get(frame, "dropped"))
    L.append(f"  dropped ▸  (units lost crossing this frame · {len(dropped)})")
    L.extend(_block(dropped))
    L.append(_hr("━"))
    return "\n".join(L)


# ===================================================================================
# VIEW 3 — THE DATA-SHAPE OBSERVATORY. Every seam: received vs expected + loss.
# ===================================================================================
def render_shapes(turn: dict, name: str) -> str:
    L: list[str] = []
    shapes = _shapes(turn)
    tid = _get(turn, "turn_id", "?")
    L.append(_hr("━"))
    L.append(f"VERA MRI · DATA-SHAPE OBSERVATORY · TURN {tid} · {name}")
    L.append(_hr("━"))
    L.append("  each row is a BOUNDARY between two stages: what arrived, what was expected,")
    L.append("  the transformation applied, and what was DROPPED crossing the seam.")
    L.append("")
    total_loss = 0
    for s in shapes:
        boundary = _get(s, "boundary", "?->?")
        loss = _as_list(_get(s, "loss"))
        nloss = len(loss)
        total_loss += nloss
        mark = " ⟂ LOSS" if nloss else " ✓"
        L.append(f"  ┌─ {boundary}{mark}")
        L.append(f"  │   received     : {_oneline(_get(s, 'received', '—'), _W - 22)}")
        L.append(f"  │   expected     : {_oneline(_get(s, 'expected', '—'), _W - 22)}")
        L.append(f"  │   transform    : {_oneline(_get(s, 'transformation', '—'), _W - 22)}")
        if nloss:
            L.append(f"  │   loss ({nloss}) ▸")
            for item in loss:
                L.append(f"  │     · {_oneline(item, _W - 12)}")
        else:
            L.append("  │   loss         : (none — shape preserved)")
        L.append("  └" + "─" * (_W - 3))
    if not shapes:
        L.append("  (no shape records in this turn)")
    L.append("")
    L.append(f"  SEAMS: {len(shapes)}   ·   TOTAL LOSS EVENTS: {total_loss}"
             + ("   <- misunderstandings, if any, originate here" if total_loss else ""))
    L.append(_hr("━"))
    return "\n".join(L)


# ===================================================================================
# VIEW 4 — THE DECISION OBSERVATORY. Selected vs rejected + the "why not?" reasons,
# plus conservation-this-turn (the capture stage's dropped units).
# ===================================================================================
def render_why(turn: dict, name: str) -> str:
    L: list[str] = []
    alts = _alternatives(turn)
    tid = _get(turn, "turn_id", "?")
    L.append(_hr("━"))
    L.append(f"VERA MRI · DECISION OBSERVATORY · TURN {tid} · {name}")
    L.append(_hr("━"))
    L.append("  every fork in the turn: what was SELECTED, and the roads NOT taken + why.")
    L.append("")
    for a in alts:
        decision = _get(a, "decision", "?")
        selected = _get(a, "selected", "?")
        rejected = _as_list(_get(a, "rejected"))
        L.append(f"  ◆ {decision}")
        L.append(f"      selected ▸  {_oneline(selected, _W - 18)}")
        if rejected:
            L.append("      rejected ▸")
            for r in rejected:
                opt = _get(r, "option", r if not isinstance(r, dict) else "?")
                reason = _get(r, "reason", "") if isinstance(r, dict) else ""
                L.append(f"        ✗ {_oneline(opt, _W - 16)}")
                if reason:
                    for ln in _wrap("why not: " + str(reason), _W - 14, indent="            "):
                        L.append(ln)
        else:
            L.append("      rejected ▸  (none recorded)")
        L.append("")
    if not alts:
        L.append("  (no decision alternatives in this turn)")
        L.append("")

    # Conservation-this-turn: the capture frame's dropped units (what the turn forgot).
    L.append("  " + _hr("─")[2:])
    L.append("  CONSERVATION THIS TURN  (units the CAPTURE stage dropped — what was forgotten)")
    cap = find_frame(turn, "capture")
    dropped = _as_list(_get(cap, "dropped")) if cap else []
    if dropped:
        for d in dropped:
            L.append(f"      ⟂ {_oneline(d, _W - 10)}")
        L.append(f"      ({len(dropped)} unit(s) not carried forward from this turn)")
    elif cap is None:
        L.append("      (no capture frame in this turn)")
    else:
        L.append("      (nothing dropped — full conservation this turn)")
    L.append(_hr("━"))
    return "\n".join(L)


# ===================================================================================
# JSON projections — the same four views, machine-readable.
# ===================================================================================
def project_json(turn: dict, view: str, frame: dict | None = None) -> dict:
    if view == "xray" and frame is not None:
        return {"view": "xray", "turn_id": _get(turn, "turn_id"),
                "stage": _get(frame, "stage"), "frame": frame}
    if view == "shapes":
        return {"view": "shapes", "turn_id": _get(turn, "turn_id"), "shapes": _shapes(turn)}
    if view == "why":
        cap = find_frame(turn, "capture")
        return {"view": "why", "turn_id": _get(turn, "turn_id"),
                "alternatives": _alternatives(turn),
                "conservation_this_turn": _as_list(_get(cap, "dropped")) if cap else []}
    # movie (default)
    frames = _frames(turn)
    return {
        "view": "movie", "turn_id": _get(turn, "turn_id"), "name": _get(turn, "name"),
        "at": _get(turn, "at"), "user_text": _get(turn, "user_text"),
        "reply": _get(turn, "reply"), "total_ms": _get(turn, "total_ms"),
        "frames": [{"i": i, "stage": _get(f, "stage"), "t_ms": _get(f, "t_ms"),
                    "confidence": _get(f, "confidence"), "summary": _summary(f),
                    "dropped": len(_as_list(_get(f, "dropped")))}
                   for i, f in enumerate(frames)],
    }


# ===================================================================================
# SYNTHETIC TRACE — a schema-shaped turn used by --selftest (and as a demo when there is
# no real trace). It exercises every field the four views read, including a real seam LOSS
# and a real rejected decision, so the views have something true to show.
# ===================================================================================
def synthetic_turn(turn_id: str = "turn-demo-001", name: str = "SynthVera") -> dict:
    return {
        "turn_id": turn_id, "name": name, "at": "2026-06-04T22:15:03Z",
        "user_text": "i've been kind of stressed about the Q3 launch, can you remind me what i told you about my sister?",
        "reply": "Yeah, the Q3 launch is a lot to carry. You mentioned your sister Mara is "
                 "visiting in July — want me to keep that in mind while things are busy?",
        "total_ms": 1840,
        "stages": [
            {"stage": "perception", "t_ms": 12, "in_shape": "raw_text[97 chars]",
             "out": {"tokens": 21, "lang": "en", "mood_cue": "stressed"},
             "dropped": [], "confidence": 0.99,
             "note": "tokenized; detected an affect cue ('stressed') and a recall request"},
            {"stage": "heart", "t_ms": 38, "in_shape": "tokens[21]",
             "out": {"embedding_dim": 768, "valence": -0.34, "arousal": 0.41},
             "dropped": [], "confidence": 0.88,
             "note": "neural embedding; negative valence registered"},
            {"stage": "capture", "t_ms": 21, "in_shape": "utterance+embedding",
             "out": {"facts": [{"sister": "Mara"}], "edges": [["user", "stressed_by", "Q3 launch"]]},
             "dropped": ["tone:'kind of' (hedge/intensity)", "temporal:'July' not re-stored"],
             "confidence": 0.72,
             "note": "stored the stress edge; the hedge 'kind of' and intensity were not captured"},
            {"stage": "route", "t_ms": 9, "in_shape": "captured_state",
             "out": {"intent": "recall", "send": None, "host_write": None},
             "dropped": [], "confidence": 0.94,
             "note": "classified as a memory-recall turn; no capability/send intent"},
            {"stage": "bind", "t_ms": 33, "in_shape": "intent=recall",
             "out": {"bound_facts": [{"sister": "Mara", "id": "mem-sis-3", "confidence": 0.91}],
                     "denied": []},
             "dropped": [], "confidence": 0.91,
             "note": "bound the recall to a known fact (mem-sis-3); nothing invented"},
            {"stage": "situation", "t_ms": 27, "in_shape": "bound_state",
             "out": {"frame": "user under deadline pressure", "stance": "supportive"},
             "dropped": [], "confidence": 0.8,
             "note": "read the situation: deadline stress + a personal recall"},
            {"stage": "meaning", "t_ms": 41, "in_shape": "situation+facts",
             "out": {"theme": "support during a stressful stretch",
                     "significance": 0.6, "callback": "sister Mara visit"},
             "dropped": [], "confidence": 0.77,
             "note": "understood the turn as connection-under-stress, not just fact retrieval"},
            {"stage": "curiosity", "t_ms": 19, "in_shape": "meaning",
             "out": {"asked": "offer to hold the July visit in mind",
                     "considered": ["ask how the launch is going", "ask about the sister"]},
             "dropped": [], "confidence": 0.66,
             "note": "chose a low-pressure offer over a probing question (user is stressed)"},
            {"stage": "prompt", "t_ms": 24, "in_shape": "meaning+curiosity",
             "out": {"system_tokens": 612, "dials": {"warmth": 35, "edge": 20},
                     "grounding_facts": 1},
             "dropped": ["1 of 2 retrieved memories trimmed for context budget"],
             "confidence": 0.85, "note": "assembled the prompt; trimmed to fit context budget"},
            {"stage": "generate", "t_ms": 1560, "in_shape": "prompt[612 tok]",
             "out": {"reply_tokens": 44, "model": "local-8b", "stop": "eos"},
             "dropped": [], "confidence": 0.9,
             "note": "generated the reply locally; 44 tokens, clean stop"},
            {"stage": "verify", "t_ms": 16, "in_shape": "candidate_reply",
             "out": {"breaks": [], "self_narrative": False, "grounded": True, "passed": True},
             "dropped": [], "confidence": 0.97,
             "note": "no break, no invented inner-life, recall is grounded in mem-sis-3 -> passed"},
        ],
        "shapes": [
            {"boundary": "perception->heart", "received": "tokens[21]",
             "expected": "tokens[]", "transformation": "embed(tokens) -> vec[768]",
             "loss": []},
            {"boundary": "heart->capture", "received": "utterance+embedding",
             "expected": "utterance+embedding",
             "transformation": "salience-extract -> facts+edges",
             "loss": ["tone:'kind of' (hedge dropped)", "intensity of 'stressed' not graded"]},
            {"boundary": "capture->bind", "received": "facts+edges",
             "expected": "facts+edges", "transformation": "resolve facts -> memory ids",
             "loss": []},
            {"boundary": "meaning->prompt", "received": "2 retrieved memories",
             "expected": "<=1 (context budget)",
             "transformation": "rank+trim retrieved memories to budget",
             "loss": ["1 lower-ranked memory trimmed for context budget"]},
            {"boundary": "generate->verify", "received": "candidate_reply[44 tok]",
             "expected": "candidate_reply", "transformation": "scan breaks + groundedness",
             "loss": []},
        ],
        "alternatives": [
            {"decision": "route.intent", "selected": "recall",
             "rejected": [{"option": "capability (check messages)",
                           "reason": "no send/host verb; 'remind me what i told you' is recall, not a device action"}]},
            {"decision": "curiosity.question",
             "selected": "offer to hold the July visit in mind",
             "rejected": [
                 {"option": "ask 'how is the launch going?'",
                  "reason": "user already signalled stress; a probing question adds pressure"},
                 {"option": "ask 'tell me more about your sister'",
                  "reason": "shifts focus off the user's stated worry; lower situational fit"}]},
            {"decision": "generate.model", "selected": "local-8b",
             "rejected": [{"option": "escalate to cloud",
                           "reason": "recall is grounded locally; no need to leave the device (privacy default)"}]},
        ],
    }


# ===================================================================================
# SELFTEST — synthesize a schema-shaped trace in a TempDir, then assert all four views
# render without raising AND surface their key fields. Also asserts the read path is
# defensive (malformed lines, missing file) and that the real .anima is never touched.
# ===================================================================================
def _selftest() -> int:
    import tempfile

    fails: list[str] = []

    def ok(label, cond):
        print(("  ok   " if cond else "  FAIL ") + label)
        if not cond:
            fails.append(label)

    real_anima = _ANIMA
    fp_before = _footprint(real_anima)

    with tempfile.TemporaryDirectory() as td:
        store = Path(td)
        name = "SynthVera"
        turn = synthetic_turn(name=name)
        # Write a SCHEMA-SHAPED trace ourselves (we do not depend on the Recorder).
        # Include a deliberately-malformed trailing line to exercise the defensive reader.
        path = trace_path(name, store)
        with path.open("w", encoding="utf-8") as fh:
            fh.write(json.dumps(turn) + "\n")
            fh.write('{ this is not valid json\n')  # half-written line -> must be skipped

        turns, warnings = read_turns(name, store)
        ok("read: parses the well-formed turn", len(turns) == 1)
        ok("read: skips the malformed line as a visible warning",
           any("unparseable" in w for w in warnings))
        sel = select_turn(turns, None, last=True)
        ok("select: --last returns the turn", isinstance(sel, dict) and sel.get("turn_id") == turn["turn_id"])
        ok("select: --turn by id resolves", select_turn(turns, turn["turn_id"], False) is not None)
        ok("select: unknown --turn id returns None (no crash)", select_turn(turns, "nope", False) is None)

        # --- THE MOVIE renders and surfaces the key fields ---
        movie = render_movie(sel, name)
        ok("movie: renders non-empty", bool(movie.strip()))
        ok("movie: shows the user text", "Q3 launch" in movie)
        ok("movie: shows the reply", "Mara" in movie)
        ok("movie: draws the packet rail (Input -> ... -> Response)",
           "Input ->" in movie and "-> Response" in movie)
        ok("movie: lists every one of the 11 canonical stages",
           all(s in movie for s in STAGES))
        ok("movie: reports total latency", "TOTAL LATENCY" in movie)
        ok("movie: flags the slowest stage (generate)", "SLOWEST STAGE: generate" in movie)
        ok("movie: surfaces a dropped-unit marker on the capture frame",
           "drop" in movie and "⤬" in movie)

        # --- THE X-RAY (by name AND by index) ---
        fr = find_frame(sel, "meaning")
        ok("xray: --stage by NAME resolves a frame", isinstance(fr, dict) and fr.get("stage") == "meaning")
        ok("xray: --stage by INDEX resolves the same frame",
           find_frame(sel, str(STAGES.index("meaning"))) is fr)
        ok("xray: out-of-range index returns None (no crash)", find_frame(sel, "999") is None)
        xray = render_xray(sel, fr, "meaning", name)
        ok("xray: renders non-empty", bool(xray.strip()))
        ok("xray: dumps in_shape, out, dropped, confidence, note",
           all(k in xray for k in ("in_shape", "out", "dropped", "confidence", "note")))
        ok("xray: shows the full out detail (theme)", "support during a stressful stretch" in xray)
        # a frame WITH drops shows them in full
        cap_fr = find_frame(sel, "capture")
        xray_cap = render_xray(sel, cap_fr, "capture", name)
        ok("xray: a frame's dropped units are shown in full", "kind of" in xray_cap)

        # --- THE SHAPE OBSERVATORY ---
        shapes = render_shapes(sel, name)
        ok("shapes: renders non-empty", bool(shapes.strip()))
        ok("shapes: shows a boundary received vs expected",
           "received" in shapes and "expected" in shapes and "transform" in shapes)
        ok("shapes: surfaces a LOSS event at the lossy seam", "hedge dropped" in shapes)
        ok("shapes: tallies total loss events", "TOTAL LOSS EVENTS" in shapes)

        # --- THE DECISION OBSERVATORY ---
        why = render_why(sel, name)
        why_flat = " ".join(why.split())  # normalize wrapping for substring checks
        ok("why: renders non-empty", bool(why.strip()))
        ok("why: shows a SELECTED option", "selected" in why and "recall" in why)
        ok("why: shows a REJECTED option + its reason (the 'why not?' trace)",
           "rejected" in why and "why not:" in why_flat
           and "a probing question adds pressure" in why_flat)
        ok("why: surfaces conservation-this-turn (capture drops)",
           "CONSERVATION THIS TURN" in why and "kind of" in why)

        # --- JSON projections never raise and carry the view tag ---
        for v, extra in (("movie", {}), ("shapes", {}), ("why", {})):
            blob = project_json(sel, v)
            ok(f"json: {v} projection is serializable + tagged",
               json.loads(json.dumps(blob, default=str)).get("view") == v)
        xblob = project_json(sel, "xray", fr)
        ok("json: xray projection carries the frame", xblob.get("view") == "xray" and xblob.get("stage") == "meaning")

        # --- DEFENSIVE: a totally empty/garbage turn renders every view without raising ---
        for bad in ({}, {"stages": "not-a-list", "shapes": None, "alternatives": 5},
                    {"turn_id": "x", "stages": [None, 7, {"stage": "ghost"}]}):
            try:
                render_movie(bad, name)
                render_shapes(bad, name)
                render_why(bad, name)
                gf = _frames(bad)
                render_xray(bad, gf[0] if gf else {}, "0", name)
                crashed = False
            except Exception as e:  # noqa: BLE001
                crashed = True
                print("       (raised:", repr(e), ")")
            ok("defensive: malformed turn renders all views without raising", not crashed)

        # --- missing trace: a clean, explanatory gap (never a crash) ---
        empt, warn2 = read_turns("DoesNotExist", store)
        ok("missing trace: returns no turns + an explanatory warning",
           empt == [] and any("no trace" in w for w in warn2))

    # --- GUARDRAIL: the whole selftest touched no real .anima file ---
    fp_after = _footprint(real_anima)
    ok("guardrail: real .anima footprint byte-UNCHANGED (synthetic-only, read-only)",
       fp_before == fp_after)
    ok("guardrail: no synthetic mri trace leaked into real .anima",
       (not real_anima.is_dir())
       or not any(p.name.endswith(".mri.jsonl") and "Synth" in p.name for p in real_anima.glob("*.mri.jsonl")))

    print()
    if fails:
        print(f"{len(fails)} FAILED: " + ", ".join(fails))
        return 1
    print("ALL MRI SELFTESTS PASS")
    return 0


def _footprint(d: Path):
    """A cheap fingerprint of a directory: {name: (size, mtime)} for every file. Used to
    PROVE the viewer is read-only — the footprint must be identical start to finish."""
    out = {}
    if not d.is_dir():
        return out
    for p in sorted(d.rglob("*")):
        if p.is_file():
            try:
                st = p.stat()
                out[str(p.relative_to(d))] = (st.st_size, st.st_mtime_ns)
            except OSError:  # pragma: no cover
                out[str(p.relative_to(d))] = None
    return out


# ===================================================================================
# ENTRY POINT — never raises; a missing trace or any malformed input is a rendered gap.
# ===================================================================================
def main(argv=None) -> int:
    ap = argparse.ArgumentParser(
        prog="mri.py",
        description="VERA MRI — total turn introspection (the movie of a turn, frame by frame).")
    ap.add_argument("name", nargs="?", default=DEFAULT_NAME,
                    help=f"creature name (default: {DEFAULT_NAME}); reads .anima/<name>.mri.jsonl")
    grp = ap.add_mutually_exclusive_group()
    grp.add_argument("--turn", metavar="ID", help="select a turn by turn_id")
    grp.add_argument("--last", action="store_true", help="select the most recent turn (default)")
    ap.add_argument("--stage", metavar="NAME|i",
                    help="X-RAY one frame in full, by stage name or 0-based index")
    ap.add_argument("--shapes", action="store_true",
                    help="DATA-SHAPE OBSERVATORY: received vs expected + loss per boundary")
    ap.add_argument("--why", action="store_true",
                    help="DECISION OBSERVATORY: selected vs rejected (+why) + conservation")
    ap.add_argument("--json", action="store_true", help="emit the selected view as JSON")
    ap.add_argument("--selftest", action="store_true",
                    help="synthesize a schema-shaped trace and assert all views render")
    ap.add_argument("--demo", action="store_true",
                    help="render the views over a built-in synthetic turn (no trace needed)")
    args = ap.parse_args(argv)

    if args.selftest:
        return _selftest()

    # Resolve the turn. --demo and an absent trace both fall back to the synthetic turn so
    # the tool always SHOWS something (and the fallback is clearly labelled).
    warnings: list[str] = []
    synthetic = False
    if args.demo:
        turn, synthetic = synthetic_turn(name=args.name), True
    else:
        turns, warnings = read_turns(args.name)
        turn = select_turn(turns, args.turn, args.last)
        if turn is None and not turns:
            # No trace at all yet (Recorder hasn't landed) -> demo the synthetic turn so the
            # viewer is useful immediately, with a banner making the synthetic origin explicit.
            turn, synthetic = synthetic_turn(name=args.name), True

    if turn is None:
        # Trace exists but the requested turn id wasn't found.
        msg = (f"no turn matched --turn {args.turn!r} in .anima/{args.name}.mri.jsonl"
               if args.turn else f"no turns found for {args.name}")
        if args.json:
            print(json.dumps({"error": msg, "warnings": warnings}, indent=2))
        else:
            print(_hr("━"))
            print("VERA MRI · nothing to show")
            print(_hr("━"))
            print("  " + msg)
            for w in warnings:
                print("  ! " + w)
        return 0  # read-only viewer: a miss is not an error

    # Pick the view.
    if args.stage is not None:
        frame = find_frame(turn, args.stage)
        if frame is None:
            avail = ", ".join(str(_get(f, "stage", "?")) for f in _frames(turn)) or "(none)"
            if args.json:
                print(json.dumps({"error": f"no frame {args.stage!r}", "available": avail}, indent=2))
            else:
                print(f"no frame matched --stage {args.stage!r}.  available stages: {avail}")
            return 0
        if args.json:
            print(json.dumps(project_json(turn, "xray", frame), indent=2, default=str))
        else:
            _banner(synthetic, warnings)
            print(render_xray(turn, frame, args.stage, args.name))
    elif args.shapes:
        if args.json:
            print(json.dumps(project_json(turn, "shapes"), indent=2, default=str))
        else:
            _banner(synthetic, warnings)
            print(render_shapes(turn, args.name))
    elif args.why:
        if args.json:
            print(json.dumps(project_json(turn, "why"), indent=2, default=str))
        else:
            _banner(synthetic, warnings)
            print(render_why(turn, args.name))
    else:  # the movie
        if args.json:
            print(json.dumps(project_json(turn, "movie"), indent=2, default=str))
        else:
            _banner(synthetic, warnings)
            print(render_movie(turn, args.name))
    return 0


def _banner(synthetic: bool, warnings: list[str]) -> None:
    """Print a SYNTHETIC-trace banner and any read warnings, so a rendered demo is never
    mistaken for a real captured turn."""
    if synthetic:
        print("  [ SYNTHETIC TRACE — no .anima/*.mri.jsonl found yet; showing a schema-shaped "
              "demo turn. ]")
    for w in warnings:
        print("  ! " + w)


if __name__ == "__main__":
    try:
        raise SystemExit(main())
    except SystemExit:
        raise
    except Exception as e:  # noqa: BLE001 — the entry point must NEVER crash the user's shell
        print(f"VERA MRI: unexpected internal state ({e!r}); nothing was written.", file=sys.stderr)
        raise SystemExit(0)

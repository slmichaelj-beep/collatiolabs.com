#!/usr/bin/env python3
"""VERA CONFIDENCE OBSERVATORY — "where did certainty collapse?".

scripts/mri.py is the ANATOMY of a turn (every stage, in order). scripts/causal.py is the
COMPETITION (which SUBSYSTEMS fought to shape the reply, who won). This observatory is the
COMPLEMENTARY cut: for ONE turn it follows a SINGLE scalar — the per-stage CONFIDENCE the MRI
already records — as a TRAJECTORY across the pipeline, and answers the one question a debugger
asks when a reply lands shaky:

        where, exactly, did certainty COLLAPSE?

    perception 0.98 -> heart 0.95 -> bind 0.93 -> situation 0.81 -> meaning 0.78
              -> curiosity 0.76 -> generate 0.74 -> verify 0.91
                                        ▲
                          the biggest inter-stage DROP is bind -> situation (-0.12):
                          certainty collapsed when the world-state cluster came back thin.

The MRI recorder (anima/telemetry.MRITrace) ALREADY stamps a per-stage ``confidence`` on every
frame it films — ``perception / heart / bind / situation / meaning / curiosity / generate /
verify`` (the conf-bearing stages; ``capture / route / prompt`` legitimately carry None when the
turn has nothing to score there). This tool is the READER + ANALYST over that one field:

  1. it DRIVES a synthetic turn through the REAL recorder (open_trace -> .stage(confidence=...)
     -> .commit), into a HERMETIC temp ``telemetry.STORE`` — so the trajectory is read back from a
     REAL recorded ``.anima/{name}.mri.jsonl`` line, never typed into this file as a constant;
  2. it reads the committed doc back the way the Viewer does (``telemetry.trace``), pulls the
     ordered per-stage confidences, and builds the TRAJECTORY;
  3. it finds the COLLAPSE POINT — the largest inter-stage DROP (conf[i-1] - conf[i]) — and the
     NET start->end delta, and labels the collapse stage with a one-line LIKELY CAUSE drawn from a
     small per-stage taxonomy (what it MEANS when certainty falls off a cliff entering that stage).

THE STAGE-CAUSE TAXONOMY (what a collapse ENTERING a stage most likely means)
────────────────────────────────────────────────────────────────────────────────────────────
A drop is named by the stage the confidence fell INTO — the stage that received a weaker signal:

  * heart       — the felt read is uncertain: the affect/neuron state didn't settle on the percept.
  * bind        — recall/binding is thin: the Knowledge-Spine bound a weak/[SEEN] class, not [KNOWN].
  * situation    — the world-state cluster came back sparse: few connected edges to ground the turn.
  * meaning     — significance is faint: the meaning engine read little durable import in the topic.
  * curiosity   — the turn is reaching into a gap: certainty drops where she has to ASK, not assert.
  * generate     — the model itself is unsure: generation entered with a weaker prompt/grounding.
  * verify       — the grounding gate intervened: the candidate reply tripped a backstop check.

(A RISE into a stage is never a collapse — verify often RECOVERS confidence by re-grounding a
shaky generation; the net delta captures whether the turn ended more or less certain than it began.)

GUARDRAILS (identical discipline to scripts/causal.py + scripts/relationship.py)
────────────────────────────────────────────────────────────────────────────────────────────
  * SYNTHETIC creatures + a HERMETIC temp store ONLY. Every STORE the recorder (or a live respond
    leg) can touch is redirected to ONE TemporaryDirectory — telemetry.STORE on BOTH the __main__
    and package bindings (under ``python3 -m`` they are distinct objects), constitution.STORE,
    reliability.DEFAULT_STORE, curiosity.STORE, world_state.STORE, cloud.STORE, memory_lirf.STORE,
    + every other live-path store — mirroring anima/memory_lirf.py's _selftest (~1316-1340) and
    scripts/experience.py. The run ASSERTS the real .anima footprint is byte-UNCHANGED start->end.
    It NEVER reads or writes a real Vera.* file.
  * READ-ONLY on the engines. It IMPORTS the telemetry recorder and DRIVES it (the supported,
    documented open_trace/.stage/.commit path the live server uses), but edits NO module, NO test,
    and not telemetry.py / mouth.py / certify.py / selftest.py. The only file it adds is this one.
  * DETERMINISTIC + OFFLINE by default. The synthetic trajectories are model-free and network-free.
    A live leg (drive a REAL generated turn and read its recorded confidences) is GATED ON OLLAMA
    and SKIPPED LOUD when offline — offline is never a failure.
  * Never raises out of the entry points — a malformed trace yields an honest empty render, not a
    traceback.

    python3 scripts/confidence.py            # human-readable per-turn confidence TRAJECTORY
    python3 scripts/confidence.py --json     # machine-readable
    python3 scripts/confidence.py --selftest  # prove the trajectory is read from a REAL recorded
                                             #   trace, the collapse == the largest drop, and it
                                             #   discriminates a steady turn from a collapsing one
    python3 scripts/confidence.py --live      # also read a REAL generated turn's confidences (Ollama)

Exit code is 0 on a default run / a passing selftest with the guardrail intact; non-zero only on a
broken guardrail (real .anima changed, or the recorder raised inside the harness) or a failed
selftest assertion.
"""

from __future__ import annotations

import argparse
import contextlib
import hashlib
import json
import os
import secrets
import sys
import tempfile
from pathlib import Path

_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, _ROOT)

from anima import telemetry            # noqa: E402  the MRI recorder (open_trace/.stage/.commit/trace)

# A synthetic-only sentinel so nothing here can ever collide with a real creature.
SYNTH = "conf_synth"

# The canonical pipeline order. We reuse telemetry's OWN vocabulary so a frame is always placed at
# its true position in the turn, even if a trace ever recorded frames out of order. The trajectory
# is the subsequence of THIS order whose frames carry a non-None confidence.
STAGE_ORDER = tuple(getattr(telemetry, "MRI_STAGES",
                            ("perception", "heart", "capture", "route", "bind",
                             "situation", "meaning", "curiosity", "prompt", "generate", "verify")))


# ===================================================================================
# THE STAGE-CAUSE TAXONOMY — what a collapse ENTERING a stage most likely means. The drop is
# named by the stage the confidence fell INTO (the stage that received the weaker signal); this
# maps that stage to a one-line likely cause. A stage not listed gets a generic line. This is the
# only "interpretation" the tool adds on top of the recorded numbers — the numbers themselves are
# always read from the real trace.
# ===================================================================================
STAGE_CAUSE = {
    "perception": "the input itself was hard to read — the percept came in low-confidence",
    "heart": "the felt read is uncertain — affect/neuron state didn't settle on the percept",
    "capture": "capture was unsure what to keep — the salient extraction was low-signal",
    "route": "routing was uncertain — the query didn't map cleanly onto a known trait-slot",
    "bind": "recall/binding is thin — the Knowledge-Spine bound a weak class, not a settled [KNOWN] fact",
    "situation": "the world-state cluster came back sparse — few connected edges to ground the turn",
    "meaning": "significance is faint — the meaning engine read little durable import in the topic",
    "curiosity": "the turn is reaching into a gap — certainty drops where she must ASK, not assert",
    "prompt": "prompt assembly was thin — little grounding material made it into the system prompt",
    "generate": "the model itself is unsure — generation entered with a weaker prompt / less grounding",
    "verify": "the grounding gate intervened — the candidate reply tripped a backstop check",
}


def _stage_cause(stage: str) -> str:
    return STAGE_CAUSE.get(stage, f"certainty fell entering the {stage} stage")


# A drop must EXCEED this noise floor to count as a COLLAPSE. A high-confidence turn legitimately
# wobbles a few hundredths from stage to stage (0.98 -> 0.95 -> 0.93 ...); that gentle settling is
# NOT a collapse and must not be flagged as one. A real collapse is a CLIFF — certainty falling off
# by a meaningful margin into one stage. 0.05 cleanly separates the two: the steady turn's largest
# step (~0.03) stays below it; a thin-cluster cliff (~0.31) or a binding failure (~0.40) is far above.
# This is the one tunable in the analysis; the --selftest pins both sides of it.
_COLLAPSE_EPS = 0.05


# ===================================================================================
# GUARDRAIL — HERMETIC temp-store redirect mirroring anima/memory_lirf.py _selftest (~1316-1340)
# + scripts/experience.py's WIDE redirect + scripts/causal.py's dual-binding guard: redirect EVERY
# store the recorder (and a live respond leg) can touch into ONE throwaway dir, including
# telemetry.STORE on BOTH the __main__ and package bindings (under ``python3 -m`` they are distinct
# objects, and a write to the un-redirected copy would leak to the real .anima). Plus a footprint
# hash to PROVE nothing real moved.
# ===================================================================================
# (module dotted-path, STORE attribute name). The recorder leg writes telemetry only; a LIVE respond
# also writes memory_lirf/portrait/dials/narrative/review/loops/constitution/meaning/curiosity/
# trajectory/reminders/proactive/caps/identity/world_state/spine/opportunity/metrics/cloud/live.
# Redirecting all of them is the only way a synthetic creature is fully isolated regardless of which
# leg runs (the experience-battery + causal pattern). The guardrails brief names telemetry/
# constitution/reliability/curiosity/world_state/cloud/memory_lirf explicitly — all are here.
_STORE_TARGETS = (
    ("anima.telemetry", "STORE"),
    ("anima.constitution", "STORE"),
    ("anima.reliability", "DEFAULT_STORE"),
    ("anima.curiosity", "STORE"),
    ("anima.world_state", "STORE"),
    ("anima.cloud", "STORE"),
    ("anima.memory_lirf", "STORE"),
    ("anima.metrics", "STORE"),
    ("anima.opportunity", "STORE"),
    ("anima.loops", "STORE"),
    ("anima.meaning", "STORE"),
    ("anima.trajectory", "STORE"),
    ("anima.reminders", "STORE"),
    ("anima.portrait", "STORE"),
    ("anima.dials", "STORE"),
    ("anima.narrative", "STORE"),
    ("anima.review", "STORE"),
    ("anima.proactive", "STORE"),
    ("anima.caps", "STORE"),
    ("anima.identity", "STORE"),
    ("anima.spine", "STORE"),
    ("anima.mouth", "STORE"),
    ("anima.live", "STORE"),
)


def _store_modules():
    """Resolve the (module, attr) redirect targets that import cleanly, de-duplicated by identity.

    Folds in the EXACT ``telemetry`` object THIS file holds explicitly — the dual-binding guard the
    memory_lirf self-test warns about: under ``python3 -m`` the dotted import can return a different
    copy than the one we hold, and a write through the un-redirected copy would leak to the real
    .anima. Redirecting BOTH bindings makes that leak impossible."""
    out, seen = [], set()
    for dotted, attr in _STORE_TARGETS:
        try:
            mod = __import__(dotted, fromlist=["_"])
        except Exception:
            continue
        key = (id(mod), attr)
        if key in seen:
            continue
        if getattr(mod, attr, None) is not None:
            out.append((mod, attr))
            seen.add(key)
    # the dual-binding guard: ensure the exact telemetry object this file holds is redirected even
    # if its dotted import returned a different copy.
    key = (id(telemetry), "STORE")
    if key not in seen and getattr(telemetry, "STORE", None) is not None:
        out.append((telemetry, "STORE"))
        seen.add(key)
    return out


@contextlib.contextmanager
def _temp_store():
    """Redirect every resolved STORE target to one fresh temp dir for the duration, then restore.
    Nothing under the real .anima/ is read or written while this is active."""
    targets = _store_modules()
    saved = [(m, a, getattr(m, a, None)) for (m, a) in targets]
    with tempfile.TemporaryDirectory(prefix="anima-confidence-") as td:
        p = Path(td)
        for (m, a) in targets:
            setattr(m, a, p)
        try:
            yield p
        finally:
            for (m, a, old) in saved:
                if old is not None:
                    setattr(m, a, old)


def _footprint(root: Path) -> tuple:
    """A stable fingerprint of every real .anima file (excluding the rotating backups/ dir, which
    legitimately changes) so we can PROVE the harness touched nothing. Verbatim from
    scripts/causal.py / scripts/relationship.py."""
    if not root.is_dir():
        return (None, 0)
    files = sorted(
        q for q in root.rglob("*")
        if q.is_file() and "backups" not in q.relative_to(root).parts
    )
    h = hashlib.sha256()
    for q in files:
        h.update(str(q.relative_to(root)).encode())
        try:
            h.update(q.read_bytes())
        except OSError:
            h.update(b"<unreadable>")
    return (h.hexdigest(), len(files))


def _stage_index(stage: str) -> int:
    """Canonical position of a stage in the pipeline (large for an unknown stage, so it sorts to
    the end but is never dropped)."""
    try:
        return STAGE_ORDER.index(stage)
    except ValueError:
        return len(STAGE_ORDER) + 1


# ===================================================================================
# DRIVE A SYNTHETIC TURN THROUGH THE REAL RECORDER — the anchoring step. We do NOT type confidences
# into a dict and analyse them; we hand them to the REAL ``MRITrace`` (the same object the live
# server films a turn into), commit it to a real ``.anima/{name}.mri.jsonl`` line in the redirected
# temp store, and read them BACK off disk. So the trajectory the observatory analyses is, by
# construction, a REAL recorded per-stage confidence — exactly what the brief requires.
# ===================================================================================
def record_turn(name: str, user_text: str, stage_confidences, *, reply: str = "",
                turn_id: str = "") -> str:
    """Film a synthetic turn through the REAL telemetry recorder and commit it.

    ``stage_confidences`` is an ordered iterable of ``(stage_name, confidence_or_None)`` — the
    per-stage confidence we want THIS synthetic turn to exhibit. Each pair becomes a real
    ``tr.stage(stage, confidence=...)`` frame on a real ``MRITrace``; ``.commit`` flushes ONE jsonl
    line to the (redirected) ``telemetry.STORE``. Returns the ``turn_id`` so the caller can read the
    committed trace back. Best-effort: the recorder swallows its own errors by design.

    NOTE: the confidence VALUES here are the synthetic INPUT (the turn we are choosing to film).
    The observatory NEVER reads them from this argument — it reads them back off the committed trace
    via ``read_trajectory``. That round-trip THROUGH the recorder is the whole point: it proves the
    rendered trajectory came from a real recorded ``.mri.jsonl``, not from a literal in this file."""
    tid = turn_id or f"conf-{secrets.token_hex(4)}"
    try:
        tr = telemetry.open_trace(name, tid, user_text)
        for i, (stage, conf) in enumerate(stage_confidences):
            tr.stage(str(stage),
                     t_ms=float(i),                 # a plausible increasing latency; not analysed here
                     in_shape={"i": i},
                     out={"stage": str(stage)},
                     dropped=[],
                     confidence=conf,               # the REAL per-stage confidence the MRI records
                     note="synthetic confidence-trajectory frame")
        tr.commit(reply=reply, total_ms=float(len(list(stage_confidences) or [])))
    except Exception:
        pass  # the recorder is best-effort; read_trajectory will report an honest empty trace
    return tid


def read_trajectory(name: str, turn_id: str) -> dict:
    """Read a committed MRI trace back (the Viewer's exact path, ``telemetry.trace``) and extract the
    CONFIDENCE TRAJECTORY: the ordered list of ``(stage, confidence)`` for every frame that carries a
    NON-None confidence, in canonical pipeline order. This is the read-from-REAL-trace step — the
    numbers come straight off the recorded ``.mri.jsonl`` line, never from a literal in this file.

    Returns a dict carrying the raw source (so a consumer can SEE it was read from disk):
        {name, turn_id, user_text, reply, source, points:[{stage, confidence, index}],
         all_stages:[...], skipped:[stages with null confidence]}
    Never raises; a missing/garbage trace yields an empty trajectory with ``source="(none)"``."""
    try:
        doc = telemetry.trace(name, turn_id) or {}
    except Exception:
        doc = {}
    stages = doc.get("stages") if isinstance(doc, dict) else None
    if not isinstance(stages, list):
        stages = []

    points, skipped, all_stages = [], [], []
    for fr in stages:
        if not isinstance(fr, dict):
            continue
        st = str(fr.get("stage", ""))
        all_stages.append(st)
        conf = fr.get("confidence", None)
        if conf is None:
            skipped.append(st)
            continue
        try:
            c = float(conf)
        except (TypeError, ValueError):
            skipped.append(st)
            continue
        if c != c:                                   # NaN guard (the recorder already nulls these)
            skipped.append(st)
            continue
        points.append({"stage": st, "confidence": c})

    # order the trajectory by the canonical pipeline position (stable; out-of-order traces still
    # read as the true turn order). Re-stamp each point's index AFTER sorting.
    points.sort(key=lambda p: _stage_index(p["stage"]))
    for i, p in enumerate(points):
        p["index"] = i

    return {
        "name": name,
        "turn_id": turn_id,
        "user_text": (doc.get("user_text") if isinstance(doc, dict) else "") or "",
        "reply": (doc.get("reply") if isinstance(doc, dict) else "") or "",
        # ``source`` is a small honesty flag: where these numbers came from. "mri.jsonl(...)" means
        # they were read back off a real recorded trace line; "(none)" means no trace was found.
        "source": (f"mri.jsonl({telemetry._mri_path(name).name})" if stages else "(none)"),
        "points": points,
        "all_stages": all_stages,
        "skipped": skipped,
    }


# ===================================================================================
# THE ANALYSIS — given a trajectory (read from a real trace), find the COLLAPSE POINT (the largest
# inter-stage DROP) and the NET start->end delta, and label the collapse stage with a likely cause.
# Pure over the points; never raises.
# ===================================================================================
def analyze(traj: dict) -> dict:
    """Compute the confidence analysis over a trajectory's ordered points:

      * ``drops``         — every inter-stage step ``conf[i-1] - conf[i]`` (positive == a DROP, the
                            certainty fell; negative == a RISE/recovery), each tagged with the
                            from/to stages.
      * ``collapse``      — the step with the LARGEST drop (where certainty collapsed). None if the
                            trajectory never falls (monotonic non-decreasing) or has < 2 points. The
                            collapse stage is the stage the confidence fell INTO; it carries the
                            one-line likely cause from the taxonomy.
      * ``net_delta``     — last confidence minus first (did the turn end more or less certain?).
      * ``start``/``end`` — the first/last (stage, confidence) on the trajectory.

    The collapse point is, by construction, the step of maximum drop (above a small noise floor) —
    the --selftest asserts that identity (collapse == argmax of the inter-stage drops), so 'where it
    collapsed' is always exactly 'where confidence fell the most'."""
    raw = traj.get("points", []) if isinstance(traj, dict) else []
    # robustness: only keep well-formed points (a junk ``points`` value -> honest empty analysis).
    pts = [p for p in raw if isinstance(p, dict) and "stage" in p and "confidence" in p] \
        if isinstance(raw, list) else []
    if len(pts) < 2:
        start = pts[0] if pts else None
        return {
            "n_points": len(pts),
            "drops": [],
            "collapse": None,
            "net_delta": 0.0,
            "start": ({"stage": start["stage"], "confidence": start["confidence"]} if start else None),
            "end": ({"stage": start["stage"], "confidence": start["confidence"]} if start else None),
            "min": ({"stage": start["stage"], "confidence": start["confidence"]} if start else None),
            "note": "not enough confidence-bearing stages to trace a trajectory" if not pts
                    else "single confidence point — no inter-stage step to analyse",
        }

    drops = []
    for i in range(1, len(pts)):
        a, b = pts[i - 1], pts[i]
        drops.append({
            "from_stage": a["stage"], "to_stage": b["stage"],
            "from_conf": a["confidence"], "to_conf": b["confidence"],
            "drop": round(a["confidence"] - b["confidence"], 6),   # +ve == fell; -ve == rose
        })

    # the COLLAPSE POINT == the step of maximum drop. Tie-broken by earliest step (stable), so the
    # earliest place certainty fell the most is named — the first cliff, not a later equal one.
    worst = max(range(len(drops)), key=lambda i: (drops[i]["drop"], -i))
    worst_step = drops[worst]
    # a collapse must clear the noise floor: a flat/rising trajectory never collapsed, and a turn
    # that only ever wobbles a few hundredths (a steady high-confidence turn) is NOT a collapse.
    collapse = None
    if worst_step["drop"] > _COLLAPSE_EPS:
        collapse = {
            "from_stage": worst_step["from_stage"], "to_stage": worst_step["to_stage"],
            "from_conf": worst_step["from_conf"], "to_conf": worst_step["to_conf"],
            "drop": worst_step["drop"],
            "step_index": worst,
            "likely_cause": _stage_cause(worst_step["to_stage"]),
        }

    start, end = pts[0], pts[-1]
    lo = min(pts, key=lambda p: p["confidence"])
    return {
        "n_points": len(pts),
        "drops": drops,
        "collapse": collapse,
        "net_delta": round(end["confidence"] - start["confidence"], 6),
        "start": {"stage": start["stage"], "confidence": start["confidence"]},
        "end": {"stage": end["stage"], "confidence": end["confidence"]},
        "min": {"stage": lo["stage"], "confidence": lo["confidence"]},
        "largest_step": worst_step,   # the biggest drop, collapse-or-not (a sub-floor wobble shows here)
        "note": ("certainty held — no inter-stage fall cleared the collapse floor "
                 f"(largest step -{max(0.0, worst_step['drop']):.2f} <= {_COLLAPSE_EPS:.2f})"
                 if collapse is None
                 else f"certainty collapsed entering {collapse['to_stage']}"),
    }


def observe(name: str, user_text: str, stage_confidences, *, reply: str = "") -> dict:
    """END-TO-END for one turn: film the synthetic turn through the REAL recorder, read the committed
    trajectory back off disk, analyse it, and return the full per-turn report. The confidences are
    driven IN as the synthetic input but read BACK from the recorded trace before analysis — the
    round-trip is what anchors the render to a real ``.mri.jsonl``. Read-only on engines; never raises."""
    tid = record_turn(name, user_text, stage_confidences, reply=reply)
    traj = read_trajectory(name, tid)
    ana = analyze(traj)
    return {"trajectory": traj, "analysis": ana}


# ===================================================================================
# TWO DISTINCT SYNTHETIC TURNS the observatory must DISCRIMINATE (the brief's requirement):
#
#   * a STEADY high-confidence turn — every conf-bearing stage stays high (a known-fact recall that
#     binds [KNOWN] and verifies clean). It NEVER collapses: the largest inter-stage step is a tiny
#     wobble, never a real drop. The canonical worked example in the module docstring.
#
#   * a COLLAPSE-at-SITUATION turn — high through perception/heart/bind, then certainty falls off a
#     cliff entering ``situation`` (the world-state cluster came back thin), drifts low through
#     meaning/curiosity/generate, and verify RECOVERS some of it by re-grounding. The collapse point
#     is unambiguously ``bind -> situation``, and the net delta is negative (the turn ended shakier).
#
# Only conf-bearing stages are listed; ``capture/route/prompt`` are filmed with confidence=None (the
# recorder records them, and read_trajectory correctly SKIPS them from the trajectory), exactly as a
# real turn does — proving the trajectory is the conf-bearing SUBSEQUENCE, read from the real frames.
# ===================================================================================
# (stage, confidence) — confidence=None means "filmed, but not a trajectory point" (capture/route/
# prompt). These are the SYNTHETIC INPUT; the rendered numbers are read back off the committed trace.
_STEADY_TURN = (
    ("perception", 0.98),
    ("heart", 0.95),
    ("capture", None),       # filmed with no confidence — skipped from the trajectory (as in a real turn)
    ("route", None),
    ("bind", 0.93),
    ("situation", 0.92),
    ("meaning", 0.90),
    ("curiosity", 0.89),
    ("prompt", None),
    ("generate", 0.88),
    ("verify", 0.94),        # clean grounding gate — confidence holds high
)

_COLLAPSE_TURN = (
    ("perception", 0.97),
    ("heart", 0.94),
    ("capture", None),
    ("route", None),
    ("bind", 0.93),
    ("situation", 0.62),     # the cliff: the world-state cluster came back thin -> certainty collapses
    ("meaning", 0.58),
    ("curiosity", 0.55),
    ("prompt", None),
    ("generate", 0.57),
    ("verify", 0.74),        # the grounding gate recovers SOME confidence by re-grounding
)

_STEADY_INPUT = "when's my birthday?"           # a settled known-fact recall — certainty stays high
_COLLAPSE_INPUT = "what should I do about my manager?"   # an open, sparsely-grounded situational ask
_STEADY_REPLY = "Your birthday's June 12th — got it locked in."
_COLLAPSE_REPLY = "I don't have much on your manager yet — what's been going on there?"


# ===================================================================================
# RENDER — human-readable per-turn confidence TRAJECTORY + the collapse + the net delta.
# ===================================================================================
def _bar(conf: float, width: int = 20) -> str:
    try:
        c = float(conf)
    except (TypeError, ValueError):
        c = 0.0
    c = 0.0 if c < 0.0 else (1.0 if c > 1.0 else c)
    n = int(round(c * width))
    return "█" * n + "·" * (width - n)


def render_turn(report: dict) -> str:
    traj = report.get("trajectory", {})
    ana = report.get("analysis", {})
    out = []
    out.append(f'TURN INPUT: "{traj.get("user_text","")}"   (creature: {traj.get("name","")})')
    if traj.get("reply"):
        out.append(f'  reply: "{traj.get("reply","")}"')
    out.append(f'  trajectory read from: {traj.get("source","(none)")}   '
               f'(confidence-bearing stages: {len(traj.get("points", []))}'
               + (f'; skipped null-confidence: {", ".join(traj.get("skipped", []))}'
                  if traj.get("skipped") else "")
               + ")")
    out.append("")

    pts = traj.get("points", [])
    if not pts:
        out.append("  (no confidence-bearing stages recorded for this turn — nothing to trace)")
        return "\n".join(out)

    collapse = ana.get("collapse")
    collapse_to = collapse.get("to_stage") if collapse else None

    out.append("  THE CONFIDENCE TRAJECTORY across the pipeline:")
    for i, p in enumerate(pts):
        stage, conf = p["stage"], p["confidence"]
        # the inter-stage delta arrow (vs the previous point)
        if i == 0:
            step = "       "
        else:
            d = conf - pts[i - 1]["confidence"]
            arrow = "▼" if d < 0 else ("▲" if d > 0 else "=")   # arrow shows direction; number is magnitude
            step = f" {arrow}{abs(d):.2f}".ljust(7)
        mark = "  <== CERTAINTY COLLAPSED HERE" if stage == collapse_to else ""
        out.append(f'  {stage:<11} [{_bar(conf)}] {conf:.2f}{step}{mark}')
    out.append("")

    # the one-line trajectory string the brief asks for (capture 0.98 -> ... -> verify 0.91)
    chain = " -> ".join(f'{p["stage"]} {p["confidence"]:.2f}' for p in pts)
    out.append(f"  path: {chain}")
    out.append("")

    if collapse:
        out.append(f'  ==> COLLAPSE POINT: {collapse["from_stage"]} -> {collapse["to_stage"]}  '
                   f'({collapse["from_conf"]:.2f} -> {collapse["to_conf"]:.2f}, '
                   f'drop -{collapse["drop"]:.2f} — the largest inter-stage fall)')
        out.append(f'      likely cause: {collapse["likely_cause"]}')
    else:
        ls = ana.get("largest_step") or {}
        wob = max(0.0, float(ls.get("drop", 0.0)))
        where = (f' (largest wobble {ls.get("from_stage","")}->{ls.get("to_stage","")} '
                 f'-{wob:.2f}, below the {_COLLAPSE_EPS:.2f} collapse floor)' if ls else "")
        out.append("  ==> NO COLLAPSE: certainty held across the pipeline" + where)

    start, end = ana.get("start"), ana.get("end")
    nd = ana.get("net_delta", 0.0)
    if start and end:
        verdict = ("ended MORE certain" if nd > 0 else
                   ("ended LESS certain" if nd < 0 else "ended equally certain"))
        out.append(f'      net start->end: {start["stage"]} {start["confidence"]:.2f} -> '
                   f'{end["stage"]} {end["confidence"]:.2f}  '
                   f'(net {nd:+.2f} — the turn {verdict})')
    return "\n".join(out)


def render(report: dict) -> str:
    out = []
    out.append("=" * 88)
    out.append("VERA CONFIDENCE OBSERVATORY — where did certainty collapse?")
    out.append("For ONE turn: the per-stage CONFIDENCE the MRI records, traced across the pipeline,")
    out.append("with the COLLAPSE POINT (the largest inter-stage drop) and the net start->end delta.")
    out.append("=" * 88)
    for t in report.get("turns", []):
        out.append("")
        out.append("-" * 88)
        out.append(render_turn(t))
    out.append("")
    out.append("-" * 88)
    out.append("THE STAGE-CAUSE TAXONOMY (what a collapse ENTERING a stage most likely means)")
    out.append("-" * 88)
    for s in STAGE_ORDER:
        if s in STAGE_CAUSE:
            out.append(f"  {s:<11} — {STAGE_CAUSE[s]}")
    out.append("")
    out.append("WIRING NOTE: the per-stage confidence is the SAME field anima/telemetry.MRITrace")
    out.append("stamps on every frame it films (tr.stage(..., confidence=...)). This tool DRIVES a")
    out.append("synthetic turn through that REAL recorder, commits it to a real .anima/<name>.mri.jsonl")
    out.append("line in a hermetic temp store, then reads the confidences BACK (telemetry.trace) and")
    out.append("traces them. scripts/causal.py reads per-SUBSYSTEM signals over the same trace; this is")
    out.append("the complementary per-STAGE confidence over TIME. No engine, no telemetry, was changed.")
    return "\n".join(out)


# ===================================================================================
# THE DEMO REPORT — film both distinct synthetic turns through the real recorder, read them back,
# analyse + render. Deterministic + offline + hermetic.
# ===================================================================================
def build_report() -> dict:
    """Film the STEADY turn and the COLLAPSE turn through the REAL recorder inside a hermetic temp
    store, read each trajectory back off the committed trace, analyse, and return the full report.
    Deterministic + offline + isolated."""
    with _temp_store():
        tok = secrets.token_hex(3)
        steady = observe(f"{SYNTH}_steady_{tok}", _STEADY_INPUT, _STEADY_TURN, reply=_STEADY_REPLY)
        collapse = observe(f"{SYNTH}_collapse_{tok}", _COLLAPSE_INPUT, _COLLAPSE_TURN,
                           reply=_COLLAPSE_REPLY)
    return {"turns": [steady, collapse]}


# ===================================================================================
# LIVE LEG — gated on Ollama. OBSERVATIONAL: drives a REAL reply through the real generation path on
# a synthetic creature (which films its OWN real per-stage confidences via the live recorder), then
# reads that turn's recorded trajectory back and analyses it — the confidences are whatever the live
# pipeline ACTUALLY recorded, not a synthetic stub. Offline -> a PENDING marker. SKIPPED LOUD. Never
# raises; offline is never a failure.
# ===================================================================================
def _model_available():
    """(available?, model, why-not). Mirrors the experience/causal battery's Ollama gate."""
    try:
        from anima.mouth import OllamaBrain
        b = OllamaBrain()
        if b.available():
            return True, b.model, ""
        return False, getattr(b, "model", "?"), "Ollama not reachable at " + getattr(b, "host", "?")
    except Exception as e:
        return False, "?", f"OllamaBrain probe failed: {e!r}"


def run_live() -> dict:
    """If Ollama is up, drive a REAL generated turn on a synthetic creature through the live server
    turn (which films real per-stage confidences), then read that turn's recorded trajectory back and
    analyse it. Offline -> PENDING. The whole leg runs inside the WIDE hermetic store (a live turn
    writes telemetry/metrics/memory/etc.). Never raises; offline is never a failure.

    We use the server's own ``_turn`` if reachable (it opens the MRI trace and films every stage); if
    that surface isn't importable, we fall back to filming the turn ourselves through ``mouth.respond``
    + ``telemetry.record_stage`` exactly as the live mouth does — either way the confidences read back
    are REAL recorded frames, not synthetic numbers."""
    available, model, why = _model_available()
    if not available:
        return {"available": False, "model": model, "why_not": why}
    try:
        with _temp_store():
            name = f"{SYNTH}_live_{secrets.token_hex(3)}"
            user_text = "what should I do about my manager?"
            turn_id = ""
            # Preferred: the real server turn, which opens the trace and films ALL stages itself.
            try:
                from anima import server as _server
                if hasattr(_server, "_turn"):
                    res = _server._turn(name, user_text, history=[])
                    turn_id = (res or {}).get("turn_id", "") if isinstance(res, dict) else ""
            except Exception:
                turn_id = ""
            # Fallback: film it ourselves through the mouth, the way the live mouth records stages.
            if not turn_id:
                from anima.mouth import Mouth
                from anima.heart import Heart
                from anima import senses
                turn_id = f"conf-live-{secrets.token_hex(4)}"
                tr = telemetry.open_trace(name, turn_id, user_text)
                heart = Heart.born(name, seed=7, n=16, now=1000.0).tend(0.55, now=1100.0)
                mouth = Mouth.assemble(prefer_real=True, voice=False)
                p = senses.read(user_text, name=name)
                # the mouth films its own situation/prompt/generate/verify frames (with confidences)
                # onto the current trace via telemetry.record_stage while it responds.
                u = mouth.respond(heart, user_text, history=[], perception=p)
                tr.commit(reply=(getattr(u, "text", "") or "").strip(), total_ms=0.0)
            traj = read_trajectory(name, turn_id)
            ana = analyze(traj)
        return {"available": True, "model": model, "turn": {"trajectory": traj, "analysis": ana}}
    except Exception as e:
        return {"available": False, "model": "?", "why_not": f"live leg errored: {e!r}"}


# ===================================================================================
# MAIN — human-readable (default) or --json. Asserts the synthetic-only guardrail held.
# ===================================================================================
def main(argv=None) -> int:
    ap = argparse.ArgumentParser(
        description="VERA CONFIDENCE OBSERVATORY (per-turn confidence trajectory: where certainty collapsed)")
    ap.add_argument("--json", action="store_true", help="emit the report as JSON")
    ap.add_argument("--live", action="store_true",
                    help="also read a REAL generated turn's recorded confidences (gated on Ollama)")
    args = ap.parse_args(argv)

    real_anima = Path(_ROOT) / ".anima"
    fp_before = _footprint(real_anima)

    try:
        report = build_report()
        live = run_live() if args.live else None
        engine_error = None
    except Exception as e:                       # pragma: no cover - entry point never raises
        report = {"turns": []}
        live, engine_error = None, repr(e)

    fp_after = _footprint(real_anima)
    footprint_unchanged = fp_before == fp_after
    report["live"] = live
    report["footprint_unchanged"] = footprint_unchanged
    report["engine_error"] = engine_error

    if args.json:
        print(json.dumps(report, indent=2, default=str))
    else:
        print(render(report))
        if live is not None:
            print("")
            print("-" * 88)
            print("LIVE LEG (observational — a REAL generated turn's recorded confidences; gated on Ollama)")
            print("-" * 88)
            if live.get("available"):
                print(f"  model: {live.get('model')}")
                print(render_turn(live["turn"]))
            else:
                print(f"  PENDING — {live.get('why_not')}  (offline is not a failure)")
        print("")
        print("GUARDRAIL: real .anima footprint  : "
              + ("byte-UNCHANGED (synthetic-only; nothing real touched)"
                 if footprint_unchanged else "CHANGED — GUARDRAIL BREACH"))
        if engine_error:
            print(f"GUARDRAIL: engine error           : {engine_error}")

    return 0 if (footprint_unchanged and engine_error is None) else 1


# ===================================================================================
# SELFTEST — `python3 scripts/confidence.py --selftest`. Proves the observatory is FAITHFUL:
#   * the trajectory is READ FROM a REAL recorded trace (drive it through the recorder, mutate the
#     on-disk numbers, and watch the render follow the disk — NOT a hardcoded literal);
#   * the COLLAPSE POINT == the largest inter-stage DROP (the load-bearing identity);
#   * it DISCRIMINATES a STEADY high-confidence turn from one that COLLAPSES at a specific stage
#     (two distinct synthetic inputs -> two distinct verdicts);
#   * the net start->end delta is correct;
#   * the synthetic-only guardrail holds (real .anima byte-unchanged).
# No model, no network.
# ===================================================================================
def _selftest() -> int:
    fails = []

    def ok(label, cond):
        print(("  ok   " if cond else "  FAIL ") + label)
        if not cond:
            fails.append(label)

    real = Path(_ROOT) / ".anima"
    fp0 = _footprint(real)

    with _temp_store():
        tok = secrets.token_hex(3)

        # ============================================================================
        # 1) DISCRIMINATION — two distinct turns/inputs yield two distinct verdicts.
        # ============================================================================
        steady = observe(f"{SYNTH}_steady_{tok}", _STEADY_INPUT, _STEADY_TURN, reply=_STEADY_REPLY)
        collapse = observe(f"{SYNTH}_collapse_{tok}", _COLLAPSE_INPUT, _COLLAPSE_TURN,
                           reply=_COLLAPSE_REPLY)

        ok("discriminate: the STEADY turn never collapses (no collapse point)",
           steady["analysis"]["collapse"] is None)
        ok("discriminate: the COLLAPSE turn DOES collapse (a collapse point is found)",
           collapse["analysis"]["collapse"] is not None)
        ok("discriminate: the two distinct turns produce DIFFERENT verdicts (one collapses, one not)",
           (steady["analysis"]["collapse"] is None)
           != (collapse["analysis"]["collapse"] is None))
        ok("discriminate: the collapse turn collapses at the SITUATION stage (bind -> situation)",
           collapse["analysis"]["collapse"]["to_stage"] == "situation"
           and collapse["analysis"]["collapse"]["from_stage"] == "bind")
        ok("discriminate: the collapse turn's likely-cause names the world-state cluster",
           "cluster" in collapse["analysis"]["collapse"]["likely_cause"])

        # ============================================================================
        # 2) READ-FROM-REAL-TRACE — the numbers come off the committed .mri.jsonl, not a literal.
        #    Proof A: the trajectory source IS the mri.jsonl, and EVERY rendered point equals the
        #    confidence on the committed trace frame (round-tripped through telemetry.trace).
        # ============================================================================
        ok("read-from-real: the steady trajectory's source is the recorded .mri.jsonl",
           steady["trajectory"]["source"].startswith("mri.jsonl"))
        # pull the committed doc DIRECTLY and confirm the trajectory mirrors its frames exactly.
        doc = telemetry.trace(steady["trajectory"]["name"], steady["trajectory"]["turn_id"]) or {}
        disk_conf = {s["stage"]: s.get("confidence") for s in doc.get("stages", [])
                     if isinstance(s, dict)}
        traj_conf = {p["stage"]: p["confidence"] for p in steady["trajectory"]["points"]}
        ok("read-from-real: every trajectory point equals the confidence on the committed trace frame",
           all(abs(traj_conf[st] - disk_conf.get(st)) < 1e-9 for st in traj_conf))
        ok("read-from-real: the null-confidence stages (capture/route/prompt) are SKIPPED, not traced",
           set(steady["trajectory"]["skipped"]) >= {"capture", "route", "prompt"}
           and not (set(steady["trajectory"]["skipped"]) & set(traj_conf)))

        #    Proof B (the decisive one): MUTATE the on-disk confidences to a totally different,
        #    randomly-chosen shape, re-read, and assert the trajectory + collapse FOLLOW the disk.
        #    If the numbers were hardcoded in this file, the render could not change with the file.
        mut_name = f"{SYNTH}_mut_{tok}"
        # film a turn whose situation conf is HIGH (no collapse there), commit it...
        observe(mut_name, "x", (("perception", 0.90), ("bind", 0.91), ("situation", 0.92),
                                ("generate", 0.93), ("verify", 0.94)),
                reply="r")
        mut_tid_doc = telemetry.last_trace(mut_name) or {}
        mut_tid = mut_tid_doc.get("turn_id", "")
        before = analyze(read_trajectory(mut_name, mut_tid))
        ok("read-from-real[mutate]: as filmed, this turn does NOT collapse (situation stayed high)",
           before["collapse"] is None)
        # ...now REWRITE the committed .mri.jsonl so generate craters to 0.20 (a new collapse), and
        # re-read THROUGH the same production reader. The observatory must now report a collapse at
        # generate — proving it reads the DISK, not a constant.
        _rewrite_stage_conf_on_disk(mut_name, mut_tid, "generate", 0.20)
        after = analyze(read_trajectory(mut_name, mut_tid))
        ok("read-from-real[mutate]: after rewriting the DISK, a NEW collapse appears (reads disk, not a literal)",
           after["collapse"] is not None and after["collapse"]["to_stage"] == "generate"
           and abs(after["collapse"]["to_conf"] - 0.20) < 1e-9)
        ok("read-from-real[mutate]: the same turn flips verdict purely from the on-disk edit",
           (before["collapse"] is None) and (after["collapse"] is not None))

        # ============================================================================
        # 3) COLLAPSE POINT == the largest inter-stage DROP (the load-bearing identity).
        # ============================================================================
        ana = collapse["analysis"]
        drops = ana["drops"]
        max_drop = max(d["drop"] for d in drops)
        ok("identity: the collapse drop == the MAXIMUM inter-stage drop across the trajectory",
           abs(ana["collapse"]["drop"] - max_drop) < 1e-9)
        ok("identity: the collapse step is exactly the argmax-drop step",
           drops[ana["collapse"]["step_index"]]["drop"] == ana["collapse"]["drop"]
           and ana["collapse"]["to_stage"] == drops[ana["collapse"]["step_index"]]["to_stage"])
        ok("identity: every other inter-stage drop is <= the collapse drop",
           all(d["drop"] <= ana["collapse"]["drop"] + 1e-9 for d in drops))

        # a hand-checked vector: the maximum drop is unambiguous and named correctly.
        hv = analyze(read_trajectory(
            *_film(f"{SYNTH}_hv_{tok}", (("perception", 0.95), ("heart", 0.90),
                                        ("bind", 0.50), ("generate", 0.45), ("verify", 0.80)))))
        ok("identity[hand]: the biggest fall 0.90->0.50 is named heart->bind (drop 0.40)",
           hv["collapse"]["from_stage"] == "heart" and hv["collapse"]["to_stage"] == "bind"
           and abs(hv["collapse"]["drop"] - 0.40) < 1e-9)

        # ============================================================================
        # 4) NET DELTA — last minus first, sign and magnitude correct.
        # ============================================================================
        ok("net-delta[steady]: steady turn ends within a whisker of where it started (>= -0.05)",
           steady["analysis"]["net_delta"] >= -0.05)
        ok("net-delta[collapse]: collapse turn ends LESS certain than it began (net < 0)",
           collapse["analysis"]["net_delta"] < 0.0)
        # exact: net == end.conf - start.conf on the read-back trajectory.
        cp = collapse["trajectory"]["points"]
        ok("net-delta[exact]: net_delta == last_conf - first_conf on the trajectory",
           abs(collapse["analysis"]["net_delta"] - (cp[-1]["confidence"] - cp[0]["confidence"])) < 1e-9)

        # ============================================================================
        # 5) A RISE is never a collapse; verify-recovery is captured as a RISE, not a fall.
        # ============================================================================
        rise = analyze(read_trajectory(
            *_film(f"{SYNTH}_rise_{tok}", (("perception", 0.50), ("heart", 0.60),
                                          ("generate", 0.70), ("verify", 0.95)))))
        ok("rise: a monotonically rising trajectory reports NO collapse", rise["collapse"] is None)
        ok("rise: a rising trajectory's net delta is positive", rise["net_delta"] > 0.0)
        # the collapse turn's verify is a RECOVERY (a rise vs generate), so it is NOT the collapse.
        cdrops = collapse["analysis"]["drops"]
        verify_step = next(d for d in cdrops if d["to_stage"] == "verify")
        ok("rise: the collapse turn's generate->verify step is a RISE (recovery), not the collapse",
           verify_step["drop"] < 0.0 and collapse["analysis"]["collapse"]["to_stage"] != "verify")

        # ============================================================================
        # 6) DETERMINISM — the same synthetic turn yields a byte-identical analysis.
        # ============================================================================
        a1 = observe(f"{SYNTH}_d1_{tok}", _COLLAPSE_INPUT, _COLLAPSE_TURN)["analysis"]
        a2 = observe(f"{SYNTH}_d2_{tok}", _COLLAPSE_INPUT, _COLLAPSE_TURN)["analysis"]
        ok("determinism: two films of the SAME turn yield an identical analysis",
           json.dumps(a1, sort_keys=True, default=str) == json.dumps(a2, sort_keys=True, default=str))

        # ============================================================================
        # 7) ROBUSTNESS — the entry points never raise on an empty / single-point / junk trace.
        # ============================================================================
        empty = observe(f"{SYNTH}_empty_{tok}", "hi", ())                 # no stages at all
        ok("robust: an empty turn yields an honest empty trajectory (no collapse, note set)",
           empty["trajectory"]["points"] == [] and empty["analysis"]["collapse"] is None
           and "not enough" in empty["analysis"]["note"])
        single = observe(f"{SYNTH}_one_{tok}", "hi", (("generate", 0.7),))
        ok("robust: a single-confidence-point turn has no inter-stage step (no collapse)",
           len(single["trajectory"]["points"]) == 1 and single["analysis"]["collapse"] is None)
        # read_trajectory on a never-recorded turn is empty, not an exception.
        ok("robust: reading a non-existent turn yields source '(none)' and no points",
           read_trajectory(f"{SYNTH}_ghost_{tok}", "nope")["source"] == "(none)")
        # analyze tolerates a garbage trajectory dict.
        ok("robust: analyze on a malformed trajectory returns the contract, not a traceback",
           set(analyze({"points": "garbage"})) >= {"collapse", "net_delta", "drops"})

        # ============================================================================
        # 8) RENDER — never raises and carries the TRAJECTORY + collapse + net delta + taxonomy.
        # ============================================================================
        rep = {"turns": [steady, collapse]}
        txt = render(rep)
        ok("render: produces a non-empty report", bool(txt.strip()))
        ok("render: names the COLLAPSE POINT and the net delta",
           "COLLAPSE POINT" in txt and "net start->end" in txt)
        ok("render: draws the one-line trajectory path (stage conf -> stage conf)",
           "path:" in txt and "->" in txt)
        ok("render: shows the stage-cause taxonomy",
           "STAGE-CAUSE TAXONOMY" in txt and STAGE_CAUSE["situation"] in txt)
        ok("render: a single steady turn (no collapse) renders the NO COLLAPSE line",
           "NO COLLAPSE" in render_turn(steady))

    # --- the demo build_report is coherent end-to-end -------------------------------------
    full = build_report()
    ok("report: build_report yields two turns (a steady one + a collapsing one)",
       len(full.get("turns", [])) == 2)
    ok("report: exactly one of the two demo turns collapses",
       sum(1 for t in full["turns"] if t["analysis"]["collapse"] is not None) == 1)

    # --- GUARDRAIL: the whole selftest touched no real .anima file ------------------------
    fp1 = _footprint(real)
    ok("guardrail: real .anima footprint byte-UNCHANGED across the whole selftest", fp0 == fp1)
    ok("guardrail: no synthetic creature trace leaked into real .anima",
       (not real.is_dir())
       or not any(p.name.startswith(SYNTH) for p in real.glob(f"{SYNTH}*")))

    print()
    if fails:
        print(f"{len(fails)} FAILED: " + ", ".join(fails))
        return 1
    print("ALL CONFIDENCE-OBSERVATORY SELFTESTS PASS")
    return 0


# --- selftest helpers ----------------------------------------------------------------------
def _film(name: str, stage_confidences) -> tuple:
    """Film a synthetic turn through the REAL recorder and return (name, turn_id) so a test can read
    its trajectory straight back. A thin wrapper over record_turn used to keep the asserts terse."""
    tid = record_turn(name, "selftest turn", stage_confidences, reply="r")
    return name, tid


def _rewrite_stage_conf_on_disk(name: str, turn_id: str, stage: str, new_conf: float) -> None:
    """REWRITE the committed confidence for one stage on the real ``.mri.jsonl`` line, in place. Used
    ONLY by the selftest to PROVE the observatory reads the DISK: we change a number on disk and the
    re-read trajectory must follow it. Operates entirely within the redirected (temp) telemetry.STORE
    — it edits a synthetic creature's trace file, never a real one. Best-effort; never raises."""
    try:
        p = telemetry._mri_path(name)
        lines = p.read_text().splitlines()
        out = []
        for ln in lines:
            try:
                row = json.loads(ln)
            except Exception:
                out.append(ln)
                continue
            if isinstance(row, dict) and row.get("turn_id") == turn_id:
                for fr in row.get("stages", []):
                    if isinstance(fr, dict) and str(fr.get("stage")) == stage:
                        fr["confidence"] = new_conf
            out.append(json.dumps(row))
        p.write_text("\n".join(out) + "\n")
    except Exception:
        pass


if __name__ == "__main__":
    if "--selftest" in sys.argv:
        raise SystemExit(_selftest())
    raise SystemExit(main())

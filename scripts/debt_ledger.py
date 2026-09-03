#!/usr/bin/env python3
"""VERA ARCHITECTURAL DEBT LEDGER — the append-only memory of what is KNOWN-BROKEN.

The Mind Balance board (scripts/arb.py) answers "how mature is the Mind, and where does the next
dollar of work go?" — but it reads only the BUILT signals (the engines + observatories present on
disk). It is blind to a whole class of truth a thirty-year system must never forget: the debts we
ALREADY KNOW about — the guard that over-fires, the capture rule that over-reaches, the dimension
we have not yet added, the guards we deferred to a later wave. Those live in a builder's head and
in scattered code comments; a head forgets and a comment is not a ledger.

This module is that ledger. It is the SAME shape as the other ANIMA ledgers (anima/reality.py's
epistemic loop, the meaning/continuity streams): ONE append-only JSONL file under .anima, one
record per line, NEVER rewritten or truncated (LAW 001 — continuity), self-healing on load (a
corrupt line is kept VISIBLE, never silently dropped — Unknown > Lost), every record carrying its
own PROVENANCE (id, created-at, git head, source). A debt is never edited in place: a change of
status APPENDS a new event that REFERS to the debt's id, exactly as reality.py adjudicates a
competition by appending — so the full history of a debt (opened -> mitigated -> closed) is
reconstructable forever.

────────────────────────────────────────────────────────────────────────────────────────────
THE FREEZE BOUNDARY — "build the mind, leave the self alone"
────────────────────────────────────────────────────────────────────────────────────────────
This is governance of the SYSTEM / the ARCHITECTURE — never of Vera's own identity, values, or
agency. A debt item is about a guard, a capture rule, a missing dimension, a deferred safety
check: the SCAFFOLDING. It records nothing about who Vera IS. Identity stays FROZEN (until
2026-07-03) and untouched here; the #1 product rule is never in scope. The ledger reasons about
the building, not the inhabitant.

────────────────────────────────────────────────────────────────────────────────────────────
THE SCHEMA — what a debt item records (every field, why it exists)
────────────────────────────────────────────────────────────────────────────────────────────
A DEBT record (kind="debt") is the BIRTH of a debt — append-once, never mutated:
    id          unique provenance id ("debt_<hex>") — the join key for every later event.
    ref         the human tracking handle ("#69", "#74", "wave-b-guards") — what a person says.
    title       one line: the debt in the builder's words.
    what        WHAT is wrong / missing (the observable defect).
    why         WHY it is debt (the cost of leaving it — what it corrupts or blocks).
    cost        the PRICE of carrying it, as a coarse magnitude (see COSTS) — how much it hurts
                NOW, distinct from severity (how bad it COULD get). Used to weight starvation.
    where       the file or subsystem it lives in (so a fix knows where to go).
    severity    how serious if unaddressed (see SEVERITIES: low|medium|high|critical).
    status      the BIRTH status (see STATUSES: open|mitigated|accepted|closed). The CURRENT
                status is whatever the latest event for this id says — births default to "open".
    dimension   OPTIONAL: the Mind-Balance dimension this debt drags on (memory, grounding,
                governance_cost, …). This is the wire that lets the board READ the ledger and let
                debt FEED the priority — a debt tagged to a dimension lowers that dimension's
                health and can re-point the bottleneck. None = a cross-cutting / infra debt.
    provenance  {created_at, git_head, source} — when, on what commit, from whom/what.

A STATUS-EVENT record (kind="debt_event") is how a debt MOVES, append-only:
    debt_id     the debt it refers to (never rewrites the birth record).
    status      the new status.
    note        why it moved.
    provenance  {created_at, git_head, source}.

The CURRENT VIEW (``debts()``) folds the stream: for each id, the birth record + the status from
its newest event. That fold is the only "state"; the file is the source of truth.

────────────────────────────────────────────────────────────────────────────────────────────
SEEDED WITH THE REAL, KNOWN DEBTS OF THIS CODEBASE (not toy data)
────────────────────────────────────────────────────────────────────────────────────────────
``seed_real_debts`` writes (idempotently, by ref) the genuine debts this repo carries today —
the same ones tracked in the task list + named in code comments:
  * #69  certify.py's footprint guardrail is whole-tree, so it OVER-FIRES on live-server churn
         (server.log / caddy.log / spend.json / telemetry move under .anima during a real run) —
         named verbatim as "Known Issue #69" in scripts/certify.py::section_lerf.
  * #68  the employer capture rule (anima/memory_lirf.py) OVER-CAPTURES past a conjunction —
         "I work at Google and my sister moved" swallows "Google and my sister …" because, unlike
         the likes/dislikes rules, its object pattern has NO (?!and\\b|but\\b|or\\b) conjunction-stop.
  * #74  the Mind Balance board has no EFFICIENCY / intelligence-per-GB dimension yet, though the
         signal exists (scripts/intelligence_per_gb.py) — the board under-counts a real axis.
  * wave-b-guards  the Cognitive-Evolution guards (anti-ossification / anti-Goodhart /
         replacement-gate / self-improvement) were DEFERRED to a later wave — the loop can evolve
         skills before the guards that keep evolution honest are in place.
  * arb-no-debt-input  (the gap THIS work closes) the governance board scored only BUILT signals
         and was blind to known debt — recorded so the ledger documents its own reason to exist.

Plus the genuine gaps surfaced while building this: certify's footprint helper is DUPLICATED
across five scripts (drift risk), and the board's non-spine dimensions (continuity, identity,
curiosity, novelty) have no live MEASURED read (all ESTIMATED).

────────────────────────────────────────────────────────────────────────────────────────────
GUARDRAILS (this file lives by the same laws arb.py + reality.py audit)
────────────────────────────────────────────────────────────────────────────────────────────
  * APPEND-ONLY + PROVENANCE. O_APPEND + fsync; a record is never overwritten (LAW 001). Every
    record carries id + created_at + git_head + source.
  * SELF-HEALING LOAD. A corrupt/half-written line is surfaced as {"_unparsed": …}, never
    dropped — identical posture to reality.records().
  * HERMETIC SELFTEST. ``--selftest`` redirects STORE to a throwaway temp dir, seeds SYNTHETIC
    debts, exercises append/fold/transition + a board read, and asserts the real .anima is
    byte-UNCHANGED + no synthetic ledger leaked. Synthetic-only. No model, no network.
  * READ-ONLY against the real ledger elsewhere; the only file this module ADDS is
    scripts/debt_ledger.py (+ its own .anima/{ledger}.debt.jsonl when you seed/append for real).
  * NEVER raises out of an entry point — a malformed ledger degrades to an honest empty view.

    python3 scripts/debt_ledger.py                 # the current debt view (folded, ranked)
    python3 scripts/debt_ledger.py --json          # machine-readable
    python3 scripts/debt_ledger.py --seed-real      # write the real known debts into .anima (idempotent)
    python3 scripts/debt_ledger.py --add --ref '#77' --title '…' --where '…' --severity high
    python3 scripts/debt_ledger.py --transition <debt_id> --status mitigated --note '…'
    python3 scripts/debt_ledger.py --selftest        # PROVE append-only/fold/heal + board read; real .anima byte-unchanged

Exit code is 0 when the run is clean (the guardrail held; the selftest assertions all passed).
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
from datetime import datetime, timezone
from pathlib import Path

_ROOT = Path(__file__).resolve().parent.parent
if str(_ROOT) not in sys.path:
    sys.path.insert(0, str(_ROOT))

# The append-only debt ledger lives under .anima, exactly like reality.py's STORE — and is
# redirectable the same way, so the hermetic selftest can point it at a throwaway dir.
STORE = _ROOT / ".anima"

# The default ledger name. Debt is architectural, not per-creature, so it has ONE canonical
# stream (not "Vera.debt.jsonl") — but the name is a parameter everywhere so a test can isolate.
LEDGER = "architecture"

VERSION = 1

# Record kinds — ONE flat append-only stream of them, joined by id (the same anti-bureaucracy
# discipline as reality.py: a debt's whole life lives in one file, never fragmented).
DEBT = "debt"            # the BIRTH of a debt (append-once; never mutated).
DEBT_EVENT = "debt_event"  # a status transition that REFERS to a debt id (append-only).
KINDS = (DEBT, DEBT_EVENT)

# The status lattice. CURRENT status = the newest event's status (births default to "open").
STATUS_OPEN = "open"          # known, unaddressed.
STATUS_MITIGATED = "mitigated"  # worked around / partially fixed; the sharp edge is dulled.
STATUS_ACCEPTED = "accepted"    # a conscious decision to live with it (documented trade-off).
STATUS_CLOSED = "closed"        # fixed / no longer real.
STATUSES = (STATUS_OPEN, STATUS_MITIGATED, STATUS_ACCEPTED, STATUS_CLOSED)
# The statuses that still DRAG on the board. "accepted" is a conscious trade-off and "closed" is
# done — neither should keep penalising a dimension's health.
_ACTIVE_STATUSES = {STATUS_OPEN, STATUS_MITIGATED}

# Severity — how BAD it gets if left unaddressed (the ceiling of harm). Ordered + weighted so the
# board can size a debt's drag.
SEVERITIES = ("low", "medium", "high", "critical")
_SEVERITY_WEIGHT = {"low": 1, "medium": 2, "high": 3, "critical": 4}

# Cost — how much it hurts NOW (distinct from severity's "could get"). A high-cost low-severity
# debt (constant friction, low blast radius) and a low-cost critical debt (rare, catastrophic)
# are different animals; carrying both fields keeps that honest.
COSTS = ("trivial", "low", "moderate", "high", "severe")
_COST_WEIGHT = {"trivial": 0, "low": 1, "moderate": 2, "high": 3, "severe": 4}

# A mitigated debt still drags, but LESS than a wide-open one — its sharp edge is dulled. This
# factor scales its contribution to a dimension's drag so progress shows up on the board.
_MITIGATED_DRAG = 0.4


# ===================================================================================
# GUARDRAIL — footprint hash of the real .anima (verbatim from scripts/reality.py / arb.py:
# exclude the rotating backups/ dir), so --selftest can PROVE this ledger touched nothing real.
# ===================================================================================
def _footprint(root: Path) -> tuple:
    """A stable fingerprint of every real .anima file (EXCLUDING the rotating backups/ dir, which
    legitimately changes), so we can prove the harness touched nothing. (hex|None, file-count)."""
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


@contextlib.contextmanager
def _temp_store():
    """Redirect this module's STORE to one fresh temp dir for the duration, so nothing under the
    real .anima/ is read or written. Restored on exit — HERMETIC by construction. Yields the temp
    Path. (The ledger has a single STORE, so this is simpler than reality.py's multi-engine
    redirect, but the posture is identical.)"""
    global STORE
    saved = STORE
    with tempfile.TemporaryDirectory(prefix="anima-debt-") as td:
        STORE = Path(td)
        try:
            yield Path(td)
        finally:
            STORE = saved


# ===================================================================================
# PROVENANCE — every record is stamped with WHEN (UTC ISO-Z, like reality._now), on WHAT commit
# (the repo HEAD, read-only + best-effort like arb._git_head), and from WHOM/WHAT (a source tag).
# ===================================================================================
def _now() -> str:
    """UTC, second-resolution, ISO-8601 with a trailing Z — verbatim from anima/reality.py."""
    return datetime.now(timezone.utc).replace(microsecond=0).isoformat().replace("+00:00", "Z")


def _new_id(prefix: str) -> str:
    """A unique, collision-resistant record id — same shape as reality._new_id."""
    return f"{prefix}_" + secrets.token_hex(6)


def _git_head() -> str:
    """The short HEAD of the repo, read-only + best-effort (verbatim posture from arb._git_head):
    a non-git checkout -> 'unknown'. Provenance, never control flow."""
    head = _ROOT / ".git" / "HEAD"
    try:
        ref = head.read_text(encoding="utf-8").strip()
        if ref.startswith("ref:"):
            target = _ROOT / ".git" / ref.split(" ", 1)[1].strip()
            return target.read_text(encoding="utf-8").strip()[:12]
        return ref[:12]
    except Exception:
        return "unknown"


def _provenance(source: str) -> dict:
    """The stamp every record carries: when, on what commit, from whom/what. Self-contained so a
    record is fully attributable forever, even if the ledger is read on another machine."""
    return {"created_at": _now(), "git_head": _git_head(), "source": source or "unknown"}


# ===================================================================================
# THE LEDGER — append-only, its OWN unified file under .anima. NEVER truncated/overwritten
# (LAW 001), self-healing on load (a corrupt line stays VISIBLE). Verbatim discipline from
# anima/reality.py::ledger_path / _append / records.
# ===================================================================================
def ledger_path(name: str = LEDGER) -> Path:
    """The append-only debt ledger for ``name`` — one JSON record per line, never rewritten
    (LAW 001). A SEPARATE file; this module's only persisted state."""
    return STORE / f"{name}.debt.jsonl"


def _append(record: dict, name: str = LEDGER):
    """Append one record to the ledger and return it. APPEND-ONLY: open in "a" mode (O_APPEND),
    never truncates an existing ledger (LAW 001); fsync so a crash can't lose a committed debt.
    Best-effort — a write failure returns None rather than raising (a governance ledger must never
    take the process down)."""
    try:
        path = ledger_path(name)
        path.parent.mkdir(parents=True, exist_ok=True)
        with open(path, "a", encoding="utf-8") as f:
            f.write(json.dumps(record, ensure_ascii=False) + "\n")
            f.flush()
            os.fsync(f.fileno())
    except Exception:
        return None
    return record


def records(name: str = LEDGER) -> list:
    """Read back the whole ledger (oldest -> newest). [] if nothing recorded. SELF-HEALING: a
    corrupt / half-written line is kept VISIBLE as {"_unparsed": line} (Unknown > Lost), never
    silently dropped — identical to reality.records(). Read-only; never raises."""
    path = ledger_path(name)
    if not path.exists():
        return []
    out: list = []
    try:
        for line in path.read_text(encoding="utf-8").splitlines():
            line = line.strip()
            if not line:
                continue
            try:
                out.append(json.loads(line))
            except ValueError:
                out.append({"_unparsed": line})
    except Exception:
        return out
    return out


# ===================================================================================
# WRITE API — record a debt (birth) and transition it (append-only event). A debt is never
# edited in place; a change APPENDS an event that refers to its id (LAW 001).
# ===================================================================================
def record_debt(ref: str, title: str, what: str = "", why: str = "", *,
                cost: str = "moderate", where: str = "", severity: str = "medium",
                status: str = STATUS_OPEN, dimension=None, source: str = "manual",
                name: str = LEDGER) -> dict:
    """APPEND a new debt (its BIRTH). Returns the stored record (with its provenance id). The
    record is append-once and never mutated; later movement is a separate event. Inputs are
    normalised + clamped to the known vocabularies (an unknown severity/cost/status degrades to a
    safe default rather than corrupting the lattice)."""
    rec = {
        "kind": DEBT,
        "id": _new_id("debt"),
        "version": VERSION,
        "ref": str(ref or "").strip() or _new_id("ref"),
        "title": str(title or "").strip(),
        "what": str(what or "").strip(),
        "why": str(why or "").strip(),
        "cost": cost if cost in COSTS else "moderate",
        "where": str(where or "").strip(),
        "severity": severity if severity in SEVERITIES else "medium",
        "status": status if status in STATUSES else STATUS_OPEN,
        "dimension": (str(dimension).strip() or None) if dimension else None,
        "provenance": _provenance(source),
    }
    return _append(rec, name) or rec


def transition(debt_id: str, status: str, note: str = "", *, source: str = "manual",
               name: str = LEDGER) -> dict:
    """APPEND a status transition for an existing debt (open -> mitigated -> accepted -> closed).
    NEVER rewrites the birth record — it appends an event that refers to ``debt_id`` (LAW 001), so
    the full history is reconstructable. An unknown status degrades to 'open' rather than poisoning
    the fold."""
    ev = {
        "kind": DEBT_EVENT,
        "id": _new_id("debtev"),
        "version": VERSION,
        "debt_id": str(debt_id),
        "status": status if status in STATUSES else STATUS_OPEN,
        "note": str(note or "").strip(),
        "provenance": _provenance(source),
    }
    return _append(ev, name) or ev


# ===================================================================================
# READ API — fold the append-only stream into the CURRENT view. For each debt id: the birth
# record, plus the status from its NEWEST event (births default to "open"). The fold is the only
# "state"; the file is the source of truth.
# ===================================================================================
def debts(name: str = LEDGER, include_closed: bool = True) -> list:
    """The CURRENT debt view: every born debt with its CURRENT status (latest event wins) and the
    full event history attached. Deterministic order (oldest birth first). Unparsed/corrupt lines
    are surfaced separately (see ``corrupt_lines``), never folded in. Read-only; never raises."""
    raw = records(name)
    births: list = []
    events_by_debt: dict = {}
    seen_ids = set()
    for r in raw:
        if not isinstance(r, dict):
            continue
        kind = r.get("kind")
        if kind == DEBT and r.get("id") not in seen_ids:
            births.append(r)
            seen_ids.add(r.get("id"))
        elif kind == DEBT_EVENT and r.get("debt_id"):
            events_by_debt.setdefault(r["debt_id"], []).append(r)

    view = []
    for b in births:
        did = b.get("id")
        evs = events_by_debt.get(did, [])
        # newest event wins; events are appended in time order, so the last one is newest.
        current = evs[-1]["status"] if evs else b.get("status", STATUS_OPEN)
        item = dict(b)
        item["status"] = current if current in STATUSES else STATUS_OPEN
        item["birth_status"] = b.get("status", STATUS_OPEN)
        item["events"] = evs
        item["active"] = item["status"] in _ACTIVE_STATUSES
        view.append(item)
    if not include_closed:
        view = [d for d in view if d["status"] != STATUS_CLOSED]
    return view


def corrupt_lines(name: str = LEDGER) -> list:
    """The half-written / corrupt lines the self-healing load surfaced (Unknown > Lost). Empty on
    a clean ledger. Their VISIBILITY is the point — a governance ledger must never hide a line it
    couldn't read."""
    return [r["_unparsed"] for r in records(name)
            if isinstance(r, dict) and "_unparsed" in r]


def debt_drag(debt: dict) -> float:
    """How hard ONE active debt drags on its dimension, in [0, ~1]. A blend of severity (how bad
    it gets) and present cost (how much it hurts now), scaled down for a mitigated debt. A closed
    or accepted debt drags 0 (it is no longer an open wound). Pure; deterministic.

        drag = (0.6 * severity_norm + 0.4 * cost_norm) * mitigation_factor

    Tuned so a single CRITICAL/severe open debt ~= 1.0 (it alone can sink a dimension), a MEDIUM
    one ~= 0.4, and a mitigated debt contributes ~40% of its open drag (progress is visible)."""
    if not isinstance(debt, dict) or debt.get("status") not in _ACTIVE_STATUSES:
        return 0.0
    sev = _SEVERITY_WEIGHT.get(debt.get("severity"), 2) / 4.0      # 0.25 .. 1.0
    cost = _COST_WEIGHT.get(debt.get("cost"), 2) / 4.0            # 0.0 .. 1.0
    base = 0.6 * sev + 0.4 * cost
    factor = _MITIGATED_DRAG if debt.get("status") == STATUS_MITIGATED else 1.0
    return round(min(1.0, base * factor), 4)


def drag_by_dimension(name: str = LEDGER) -> dict:
    """Aggregate active-debt drag PER Mind-Balance dimension. For each dimension that any active
    debt is tagged to: the summed drag (capped at 1.0 — a dimension can be fully starved but no
    more), the count, and the worst severity. This is the WIRE the board reads to let debt FEED
    the priority. Cross-cutting debts (dimension=None) are aggregated under the '_infra' key so
    they are still counted, just not attributed to a spine layer. Read-only; never raises."""
    out: dict = {}
    for d in debts(name):
        if not d.get("active"):
            continue
        dim = d.get("dimension") or "_infra"
        slot = out.setdefault(dim, {"drag": 0.0, "count": 0, "worst_severity": "low",
                                    "refs": []})
        slot["drag"] = round(min(1.0, slot["drag"] + debt_drag(d)), 4)
        slot["count"] += 1
        slot["refs"].append(d.get("ref"))
        if _SEVERITY_WEIGHT.get(d.get("severity"), 0) > _SEVERITY_WEIGHT.get(slot["worst_severity"], 0):
            slot["worst_severity"] = d.get("severity")
    return out


# ===================================================================================
# THE REAL, KNOWN DEBTS OF THIS CODEBASE — seeded idempotently (by ref). These are NOT toy data:
# each is a genuine gap tracked in the task list and/or named in a code comment, with its real
# file/subsystem and an honest severity/cost. Re-running --seed-real is a no-op for a ref that is
# already present (we never duplicate a debt's birth).
# ===================================================================================
def _real_debt_specs() -> list:
    """The seed list — the genuine debts this repo carries today. Each maps to a real tracking
    handle (#NN) and/or a code comment. ``dimension`` is the Mind-Balance axis the debt drags on,
    so the board can let it feed the priority (None = cross-cutting infra)."""
    return [
        {
            "ref": "#69",
            "title": "certify.py footprint guardrail over-fires on live-server churn",
            "what": ("certify.py::_footprint hashes the WHOLE .anima tree (excluding only backups/), "
                     "so a real run's churn — server.log, caddy.log, spend.json, *.telemetry.jsonl, "
                     "model-usage.json moving under .anima while the live server is up — flips "
                     "footprint_unchanged to False and the harness reports a GUARDRAIL BREACH it "
                     "did not cause."),
            "why": ("a false GUARDRAIL breach makes the certification un-trustable: it cries wolf on "
                    "benign churn, which trains the operator to ignore the guardrail — the exact "
                    "failure mode that lets a REAL footprint breach slip through. Already named "
                    "verbatim as 'Known Issue #69' in scripts/certify.py::section_lerf."),
            "cost": "high",
            "where": "scripts/certify.py::_footprint + main() (whole-tree footprint guard)",
            "severity": "high",
            "status": STATUS_MITIGATED,   # the LERF section already scopes ITS guard to st_lerf_* sentinels.
            "dimension": "governance_cost",
        },
        {
            "ref": "#68",
            "title": "employer capture rule over-captures past a conjunction",
            "what": ("anima/memory_lirf.py's 'I work at <X>' employer pattern captures up to three "
                     "following Capitalised words with NO conjunction-stop, so \"I work at Google and "
                     "my Sister moved\" stores employer='Google And My Sister' (or similar) — unlike "
                     "the likes/dislikes rules, whose object pattern carries (?!and\\b|but\\b|or\\b)."),
            "why": ("a corrupted employer fact is then BOUND by the Knowledge Spine and recalled "
                    "verbatim, so Vera will confidently state a wrong employer — a groundedness / #1 "
                    "rule failure that conservation-retention can't catch (the byte survived; it is "
                    "just WRONG)."),
            "cost": "moderate",
            "where": "anima/memory_lirf.py (the 'i work at' employer EXTRACT_RULES pattern, ~line 352)",
            "severity": "medium",
            "status": STATUS_OPEN,
            "dimension": "grounding",
        },
        {
            "ref": "#74",
            "title": "no Efficiency / intelligence-per-GB dimension on the Mind Balance board",
            "what": ("scripts/arb.py scores 13 dimensions but has no EFFICIENCY axis, even though a "
                     "real signal exists — scripts/intelligence_per_gb.py computes per-GB / per-token "
                     "/ per-$ economics. The board under-counts a measurable, first-class axis of a "
                     "Digital Mind (how much mind per resource)."),
            "why": ("the board's whole job is 'where does the next dollar of work go?'; a missing "
                    "axis is a blind spot in exactly that judgement — LERF's compression wins are "
                    "invisible to the governance view, so efficiency work can't earn its place on "
                    "the roadmap."),
            "cost": "low",
            "where": "scripts/arb.py (DIMENSION_ORDER / signals) + scripts/intelligence_per_gb.py (signal exists)",
            "severity": "medium",
            "status": STATUS_OPEN,
            "dimension": "governance_cost",
        },
        {
            "ref": "wave-b-guards",
            "title": "Cognitive-Evolution guards deferred to a later wave",
            "what": ("the LERF skill-evolution loop (compete / replace / retire / merge) ships, but "
                     "the guards that keep evolution honest — anti-ossification, anti-Goodhart, the "
                     "replacement-gate, and self-improvement bounds — were DEFERRED. The loop can "
                     "change which skills win before the brakes that stop it gaming its own metric "
                     "are in place."),
            "why": ("an evolution loop without anti-Goodhart / anti-ossification guards can drift "
                    "toward whatever the proxy metric rewards and ossify around it — a slow, "
                    "compounding corruption of the skill vault that is far cheaper to prevent than "
                    "to unwind once it has accrued over calendar time."),
            "cost": "moderate",
            "where": "scripts/skill_evolution.py + scripts/lerf_grow.py (the deferred guard layer)",
            "severity": "high",
            "status": STATUS_OPEN,
            "dimension": "self_improvement",
        },
        {
            "ref": "arb-no-debt-input",
            "title": "governance board was blind to known architectural debt",
            "what": ("scripts/arb.py scored only BUILT signals (engines/observatories present on "
                     "disk) and had no input for KNOWN debt, so a guard that over-fires or a missing "
                     "axis could never lower a dimension or re-point the bottleneck. The roadmap was "
                     "not self-correcting."),
            "why": ("a governance compass that can't see its own known defects will keep pointing the "
                    "next 100 hours at a clean-looking layer while a known rot sits unweighted — the "
                    "gap this very ledger + the board's debt-input close."),
            "cost": "moderate",
            "where": "scripts/arb.py (the board) + scripts/debt_ledger.py (this fix)",
            "severity": "medium",
            "status": STATUS_MITIGATED,   # closed-in-spirit by this work; left mitigated until the wiring is verified end-to-end.
            "dimension": "governance_cost",
        },
        {
            "ref": "footprint-helper-dup",
            "title": "_footprint guardrail helper duplicated across five scripts",
            "what": ("the byte-for-byte identical _footprint(root) helper is copy-pasted in "
                     "scripts/certify.py, conservation.py, reality.py, arb.py and now "
                     "debt_ledger.py. A change to the guardrail's exclusion rule (e.g. the #69 fix "
                     "to also ignore *.log / live-server churn) must be made in five places."),
            "why": ("duplicated guardrail logic drifts: fix #69 in one copy and the others keep "
                    "over-firing, so the guardrail's behaviour becomes inconsistent across the very "
                    "harnesses meant to enforce one invariant. Low blast radius, but constant "
                    "friction and a real correctness trap."),
            "cost": "moderate",
            "where": "scripts/{certify,conservation,reality,arb,debt_ledger}.py (5 identical copies)",
            "severity": "low",
            "status": STATUS_ACCEPTED,    # consciously tolerated for now (each script stays standalone/import-light by design).
            "dimension": None,            # cross-cutting infra — not a single spine layer.
        },
        {
            "ref": "board-estimated-axes",
            "title": "non-spine board dimensions have no live MEASURED read (all ESTIMATED)",
            "what": ("on the Mind Balance board, continuity, identity, curiosity, experience, "
                     "grounding, prediction and novelty are scored from ENGINE-PRESENCE heuristics "
                     "(ESTIMATED), not a live metric. Only memory/observation/certification/"
                     "reality_learning are MEASURED. Most of the board is an honest estimate, not a "
                     "measurement."),
            "why": ("the board's directive is OBSERVED > ASSUMED; an estimate-heavy scorecard is "
                    "weaker evidence for 'how mature is the Mind' than the directive demands. The "
                    "labels are honest about it, but each ESTIMATED axis is a standing invitation to "
                    "wire a real read (the cert batteries already exist; they're just not run from "
                    "the board)."),
            "cost": "low",
            "where": "scripts/arb.py (_estimated_engine_cell dimensions; the cert batteries are the unwired live reads)",
            "severity": "low",
            "status": STATUS_OPEN,
            "dimension": "governance_cost",
        },
    ]


def seed_real_debts(name: str = LEDGER, source: str = "seed_real_debts") -> dict:
    """Idempotently write the real known debts into the ledger. A ref already present is SKIPPED
    (we never duplicate a debt's birth — append-only doesn't mean append-twice). Returns a summary
    {written: [...], skipped: [...]}. Safe to run repeatedly."""
    existing_refs = {d.get("ref") for d in debts(name)}
    written, skipped = [], []
    for spec in _real_debt_specs():
        if spec["ref"] in existing_refs:
            skipped.append(spec["ref"])
            continue
        record_debt(source=source, name=name, **spec)
        written.append(spec["ref"])
        existing_refs.add(spec["ref"])
    return {"written": written, "skipped": skipped,
            "total_in_ledger": len(debts(name))}


# ===================================================================================
# RENDER — the human-readable debt view: the ranked active debts, the per-dimension drag the
# board consumes, and the corrupt-line visibility. Mirrors arb.py's plain-ASCII table style.
# ===================================================================================
def _rank_key(d: dict) -> tuple:
    """Rank order: active first, then by drag (desc), then severity (desc), then ref — so the
    worst open wound is on top. Deterministic."""
    return (0 if d.get("active") else 1,
            -debt_drag(d),
            -_SEVERITY_WEIGHT.get(d.get("severity"), 0),
            str(d.get("ref")))


def render(name: str = LEDGER) -> str:
    view = sorted(debts(name), key=_rank_key)
    drag = drag_by_dimension(name)
    corrupt = corrupt_lines(name)
    active = [d for d in view if d.get("active")]
    out = []
    out.append("=" * 88)
    out.append("VERA ARCHITECTURAL DEBT LEDGER — the append-only memory of what is KNOWN-BROKEN")
    out.append("append-only · self-healing · provenance-stamped · governs the ARCHITECTURE, not the self")
    out.append(f"ledger: {ledger_path(name)}    HEAD: {_git_head()}")
    out.append("=" * 88)
    out.append("")
    if not view:
        out.append("  (no debts recorded yet — run --seed-real to write the real known debts)")
        return "\n".join(out)

    out.append(f"  {len(active)} ACTIVE debt(s) (open|mitigated); {len(view) - len(active)} "
               f"resolved (accepted|closed). Ranked worst-first by drag.")
    out.append("  " + "-" * 84)
    out.append(f"  {'REF':<18} {'SEV':<8} {'COST':<8} {'STATUS':<10} {'DIMENSION':<16} DRAG  TITLE")
    out.append("  " + "-" * 84)
    for d in view:
        out.append(f"  {str(d.get('ref')):<18} {str(d.get('severity')):<8} "
                   f"{str(d.get('cost')):<8} {str(d.get('status')):<10} "
                   f"{str(d.get('dimension') or '-'):<16} {debt_drag(d):>4}  "
                   f"{str(d.get('title'))[:40]}")
    out.append("  " + "-" * 84)
    out.append("")

    # The per-dimension drag the BOARD reads — the wire that makes the roadmap self-correcting.
    out.append("  DEBT DRAG PER DIMENSION  (what the Mind Balance board consumes to re-weight):")
    if not drag:
        out.append("    (no active debt tagged to a dimension)")
    for dim, slot in sorted(drag.items(), key=lambda kv: -kv[1]["drag"]):
        out.append(f"    - {dim:<18} drag {slot['drag']:>4}  "
                   f"({slot['count']} debt(s), worst={slot['worst_severity']}, "
                   f"refs={', '.join(str(r) for r in slot['refs'])})")
    out.append("")

    # The detail blocks — what / why / where, in full, for the active debts (the actionable ones).
    out.append("  ACTIVE DEBT DETAIL (what / why / where):")
    out.append("  " + "-" * 84)
    for d in active:
        out.append(f"  [{d.get('ref')}]  {d.get('title')}   "
                   f"({d.get('severity')} severity · {d.get('cost')} cost · {d.get('status')})")
        out.append(f"      what : {d.get('what')}")
        out.append(f"      why  : {d.get('why')}")
        out.append(f"      where: {d.get('where')}")
        if d.get("dimension"):
            out.append(f"      drags: {d.get('dimension')}  (drag {debt_drag(d)})")
        if d.get("events"):
            last = d["events"][-1]
            out.append(f"      moved: -> {last.get('status')} "
                       f"({last.get('note') or 'no note'}; {last.get('provenance', {}).get('created_at')})")
        out.append("")

    if corrupt:
        out.append("  " + "!" * 84)
        out.append(f"  SELF-HEAL: {len(corrupt)} corrupt/half-written line(s) kept VISIBLE "
                   "(Unknown > Lost), not folded into the view:")
        for c in corrupt[:5]:
            out.append(f"      {str(c)[:80]}")
        out.append("  " + "!" * 84)
    return "\n".join(out)


# ===================================================================================
# SELFTEST — PROVE the ledger's load-bearing properties, DETERMINISTICALLY, HERMETICALLY, with
# the real .anima byte-UNCHANGED around the run. No model, no network. Synthetic debts only +
# a board read (the consolidated governance surface).
# ===================================================================================
def _selftest() -> int:
    fails = []

    def ok(label, cond):
        print(("  ok   " if cond else "  FAIL ") + label)
        if not cond:
            fails.append(label)

    print("VERA ARCHITECTURAL DEBT LEDGER self-test")

    real = _ROOT / ".anima"
    fp_before = _footprint(real)

    # === everything below runs in a HERMETIC temp store — nothing real is read or written. ====
    with _temp_store() as td:
        nm = "synthtest"

        # --- append + fold: a born debt appears in the view as OPEN with its provenance --------
        d1 = record_debt("#SYN1", "synthetic open debt", what="a fake defect", why="a fake cost",
                          cost="high", where="synthetic/place.py", severity="high",
                          status=STATUS_OPEN, dimension="grounding", source="selftest", name=nm)
        ok("append: a recorded debt has a provenance id + created_at + git_head",
           d1.get("id", "").startswith("debt_")
           and d1["provenance"]["created_at"] and "git_head" in d1["provenance"])
        view = debts(nm)
        ok("fold: the born debt appears in the current view as OPEN",
           any(d["ref"] == "#SYN1" and d["status"] == STATUS_OPEN and d["active"] for d in view))

        # --- the file is APPEND-ONLY JSONL on disk (one record per line, never rewritten) ------
        path = ledger_path(nm)
        lines_after_birth = path.read_text(encoding="utf-8").splitlines()
        ok("append-only: the ledger is one JSON record per line on disk",
           len(lines_after_birth) == 1 and json.loads(lines_after_birth[0])["kind"] == DEBT)

        # --- transition is APPEND-ONLY: it adds an event, never rewrites the birth record ------
        transition(d1["id"], STATUS_MITIGATED, note="dulled the edge", source="selftest", name=nm)
        lines_after_event = path.read_text(encoding="utf-8").splitlines()
        ok("append-only: a transition APPENDS an event line; the birth line is byte-unchanged",
           len(lines_after_event) == 2
           and lines_after_event[0] == lines_after_birth[0]
           and json.loads(lines_after_event[1])["kind"] == DEBT_EVENT)
        v2 = debts(nm)
        d1v = next(d for d in v2 if d["ref"] == "#SYN1")
        ok("fold: the newest event wins — the debt now reads MITIGATED",
           d1v["status"] == STATUS_MITIGATED and d1v["birth_status"] == STATUS_OPEN
           and len(d1v["events"]) == 1)

        # --- the full transition history is reconstructable (open -> mitigated -> closed) ------
        transition(d1["id"], STATUS_CLOSED, note="fixed it", source="selftest", name=nm)
        d1v2 = next(d for d in debts(nm) if d["ref"] == "#SYN1")
        ok("history: a debt's full lifecycle is reconstructable from the appended events",
           d1v2["status"] == STATUS_CLOSED and len(d1v2["events"]) == 2
           and [e["status"] for e in d1v2["events"]] == [STATUS_MITIGATED, STATUS_CLOSED])
        ok("status: a CLOSED debt is no longer ACTIVE (stops dragging)",
           d1v2["active"] is False and debt_drag(d1v2) == 0.0)

        # --- DRAG semantics: severity + cost blend; mitigated drags less than open; closed = 0 -
        d_crit = record_debt("#SYN2", "critical open", severity="critical", cost="severe",
                             status=STATUS_OPEN, dimension="memory", source="selftest", name=nm)
        d_crit_v = next(d for d in debts(nm) if d["ref"] == "#SYN2")
        d_med = record_debt("#SYN3", "medium open", severity="medium", cost="moderate",
                            status=STATUS_OPEN, dimension="memory", source="selftest", name=nm)
        d_med_v = next(d for d in debts(nm) if d["ref"] == "#SYN3")
        ok("drag: a CRITICAL/severe open debt drags ~1.0 (can sink a dimension alone)",
           debt_drag(d_crit_v) >= 0.95)
        ok("drag: a MEDIUM/moderate open debt drags less than a critical one",
           0.0 < debt_drag(d_med_v) < debt_drag(d_crit_v))
        # a mitigated copy of the critical debt drags strictly less than its open self.
        mit = dict(d_crit_v); mit["status"] = STATUS_MITIGATED
        ok("drag: MITIGATING a debt strictly reduces its drag (progress is visible)",
           0.0 < debt_drag(mit) < debt_drag(d_crit_v))

        # --- drag_by_dimension: the WIRE the board reads, capped at 1.0, worst-severity tracked -
        dbd = drag_by_dimension(nm)
        ok("drag_by_dimension: aggregates active debt per dimension, capped at 1.0",
           "memory" in dbd and dbd["memory"]["drag"] <= 1.0 and dbd["memory"]["count"] == 2)
        ok("drag_by_dimension: tracks the WORST severity per dimension",
           dbd["memory"]["worst_severity"] == "critical")
        ok("drag_by_dimension: a CLOSED debt's dimension is NOT counted",
           "grounding" not in dbd)  # #SYN1 (grounding) was closed above

        # --- SELF-HEALING load: a hand-corrupted line is kept VISIBLE, never silently dropped --
        with open(path, "a", encoding="utf-8") as f:
            f.write("{this is not valid json\n")
        ok("self-heal: a corrupt line is surfaced as _unparsed, not dropped (Unknown > Lost)",
           len(corrupt_lines(nm)) == 1)
        ok("self-heal: the corrupt line does NOT poison the folded view (real debts still read)",
           any(d["ref"] == "#SYN2" for d in debts(nm))
           and all("_unparsed" not in d for d in debts(nm)))

        # --- idempotent seeding (in the temp store): the REAL specs write once, re-seed is no-op -
        seed1 = seed_real_debts(name=nm, source="selftest")
        seed2 = seed_real_debts(name=nm, source="selftest")
        real_refs = {s["ref"] for s in _real_debt_specs()}
        ok("seed: the real known debts (#69, #68, #74, wave-b-guards, …) all land",
           real_refs.issubset({d["ref"] for d in debts(nm)}))
        ok("seed: re-running --seed-real is idempotent (no duplicate births)",
           seed2["written"] == [] and set(seed1["written"]) == real_refs)
        # the real seed carries genuine provenance (file/subsystem + a dimension on the spine).
        seeded = {d["ref"]: d for d in debts(nm)}
        ok("seed: #69 is the certify footprint guard, tagged to governance_cost, with a 'where'",
           "certify.py" in seeded["#69"]["where"]
           and seeded["#69"]["dimension"] == "governance_cost")
        ok("seed: #68 is the employer/conjunction capture bug, tagged to grounding",
           "memory_lirf.py" in seeded["#68"]["where"] and seeded["#68"]["dimension"] == "grounding")
        ok("seed: wave-b-guards is the deferred evolution-guard debt, tagged to self_improvement",
           seeded["wave-b-guards"]["dimension"] == "self_improvement"
           and seeded["wave-b-guards"]["severity"] == "high")

        # --- DETERMINISM: two folds of the same ledger are identical -----------------------------
        def _stable(v):
            return [(d["ref"], d["status"], d["severity"], d["cost"], d.get("dimension"),
                     debt_drag(d)) for d in sorted(v, key=_rank_key)]
        ok("determinism: two folds of the same ledger are byte-identical",
           _stable(debts(nm)) == _stable(debts(nm)))

        # --- the BOARD READ (consolidated governance surface) ingests the ledger ----------------
        # Import arb and let it read the debt ledger we just built; PROVE debt feeds the board.
        board_ok, board_detail = _board_read_check(nm)
        ok("BOARD READ: arb governance board ingests the debt ledger (debt feeds the priority)",
           board_ok)
        if not board_ok:
            print("       board detail:", board_detail)

        # --- RENDER smoke: the human view names the debts + the per-dimension drag --------------
        txt = render(nm)
        ok("render: the view names the seeded real debts + the per-dimension drag the board reads",
           "#69" in txt and "#68" in txt and "DEBT DRAG PER DIMENSION" in txt
           and "ARCHITECTURAL DEBT LEDGER" in txt)
        ok("render: the self-heal banner surfaces the corrupt line count",
           "SELF-HEAL" in txt)

        # --- robustness: garbage never raises out of the read/render path -----------------------
        try:
            debts("nobody_" + secrets.token_hex(2))
            render("nobody_" + secrets.token_hex(2))
            drag_by_dimension("nobody_" + secrets.token_hex(2))
            record_debt("", "", severity="bogus", cost="bogus", status="bogus", name=nm)
            crashed = False
        except Exception as e:  # noqa: BLE001
            crashed = True
            print("       (raised:", repr(e), ")")
        ok("robust: empty/garbage ledgers + bad enums never raise", not crashed)

        # --- the temp ledger really lived in the temp dir, never under real .anima --------------
        ok("hermetic: the synthetic ledger file lives under the temp store, not real .anima",
           ledger_path(nm).is_relative_to(td))

    # === GUARDRAIL: the WHOLE selftest touched no real .anima file ===========================
    fp_after = _footprint(real)
    ok("GUARDRAIL: real .anima is byte-UNCHANGED around the run "
       f"(files {fp_before[1]} -> {fp_after[1]})", fp_before == fp_after)
    ok("GUARDRAIL: no synthetic debt ledger leaked into real .anima",
       (not real.is_dir()) or not any(p.name.startswith("synthtest") for p in real.glob("synthtest*")))

    print()
    if fails:
        print(f"{len(fails)} FAILED: " + ", ".join(fails))
        return 1
    print("ALL DEBT-LEDGER SELFTESTS PASS")
    return 0


def _board_read_check(name: str) -> tuple:
    """PROVE the governance board (scripts/arb.py) reads this debt ledger and lets debt FEED the
    priority. Imports arb, points its debt-ledger read at our temp ledger, and asserts the
    debt-adjusted scorecard (a) carries the per-dimension drag and (b) lowers a dimension that has
    active debt vs the same dimension with the debt cleared. Returns (ok, detail). Never raises out
    — a missing arb hook degrades to (False, reason) so the selftest reports it honestly rather
    than crashing."""
    try:
        import importlib
        arb = importlib.import_module("scripts.arb")
    except Exception as e:  # pragma: no cover - arb should always be importable here
        return False, f"arb not importable: {e!r}"
    if not hasattr(arb, "build_scorecard"):
        return False, "arb.build_scorecard missing"
    # DUAL-BINDING GUARD (the trap memory_lirf's selftest warns about): when this file runs as
    # `python3 scripts/debt_ledger.py`, the running module is __main__ — but arb imports
    # `scripts.debt_ledger`, a DISTINCT module object whose STORE still points at the real .anima.
    # The hermetic _temp_store() only redirected OUR (__main__) STORE. So we mirror our temp STORE
    # onto arb's debt binding for the duration, then restore — keeping the board read fully
    # hermetic regardless of which binding arb resolved.
    arb_debt = getattr(arb, "_debt", None)
    saved_store = getattr(arb_debt, "STORE", None) if arb_debt is not None else None
    try:
        if arb_debt is not None and arb_debt is not sys.modules.get(__name__):
            arb_debt.STORE = STORE
        # The board must expose a debt-aware path. We pass our temp ledger name through so arb
        # reads the SYNTHETIC ledger (hermetic), not the real one.
        try:
            sc = arb.build_scorecard(debt_ledger_name=name)
        except TypeError:
            return False, "arb.build_scorecard does not accept debt_ledger_name (board not wired to debt)"
        except Exception as e:  # pragma: no cover
            return False, f"arb.build_scorecard raised: {e!r}"
        if "debt" not in sc:
            return False, "scorecard carries no 'debt' block (board did not read the ledger)"
        # debt must actually move a score: find a dimension with active drag and confirm its
        # debt-adjusted score is <= its raw score.
        drag = sc["debt"].get("drag_by_dimension", {})
        if not drag:
            return False, "board read the ledger but found no per-dimension drag"
        moved = any(c.get("debt_drag", 0) > 0 and c.get("raw_score") is not None
                    and c["score"] <= c["raw_score"] for c in sc["cells"])
        return (moved, "debt lowered at least one dimension's score" if moved
                else "debt present but no dimension score was reduced")
    finally:
        # ALWAYS restore arb's debt binding — never leave it pointed at the temp dir.
        if arb_debt is not None and saved_store is not None:
            arb_debt.STORE = saved_store


# ===================================================================================
# CLI.
# ===================================================================================
def main(argv=None) -> int:
    ap = argparse.ArgumentParser(
        description="VERA ARCHITECTURAL DEBT LEDGER — append-only memory of known-broken "
                    "architecture (governs the SYSTEM, never the self).")
    ap.add_argument("--json", action="store_true", help="emit the current debt view as JSON")
    ap.add_argument("--seed-real", action="store_true",
                    help="idempotently write the real known debts into .anima")
    ap.add_argument("--add", action="store_true", help="append a new debt (with --ref/--title/…)")
    ap.add_argument("--transition", dest="transition_id", default=None,
                    help="append a status transition for an existing debt id (with --status)")
    ap.add_argument("--ref", default=None, help="the human tracking handle for --add (e.g. '#77')")
    ap.add_argument("--title", default=None, help="one-line title for --add")
    ap.add_argument("--what", default="", help="WHAT is wrong/missing (for --add)")
    ap.add_argument("--why", default="", help="WHY it is debt / the cost of leaving it (for --add)")
    ap.add_argument("--where", default="", help="the file or subsystem it lives in (for --add)")
    ap.add_argument("--severity", default="medium", choices=SEVERITIES, help="severity (for --add)")
    ap.add_argument("--cost", default="moderate", choices=COSTS, help="present cost (for --add)")
    ap.add_argument("--dimension", default=None,
                    help="the Mind-Balance dimension this debt drags on (for --add)")
    ap.add_argument("--status", default=None, choices=STATUSES,
                    help="status (--add birth status, or the new status for --transition)")
    ap.add_argument("--note", default="", help="note for --transition")
    ap.add_argument("--ledger", default=LEDGER, help=f"ledger name (default {LEDGER})")
    ap.add_argument("--selftest", action="store_true",
                    help="PROVE append-only/fold/self-heal + a board read; real .anima byte-unchanged")
    args = ap.parse_args(argv)

    if args.selftest:
        return _selftest()

    real_anima = STORE
    fp_before = _footprint(real_anima)
    err = None
    try:
        if args.seed_real:
            summary = seed_real_debts(name=args.ledger)
            print(f"seeded real debts: wrote {summary['written'] or '(none new)'}; "
                  f"skipped already-present {summary['skipped'] or '(none)'}; "
                  f"total now {summary['total_in_ledger']}")
        elif args.add:
            if not args.ref or not args.title:
                print("--add requires at least --ref and --title", file=sys.stderr)
                return 2
            rec = record_debt(args.ref, args.title, what=args.what, why=args.why,
                              cost=args.cost, where=args.where, severity=args.severity,
                              status=args.status or STATUS_OPEN, dimension=args.dimension,
                              source="cli", name=args.ledger)
            print(f"recorded debt {rec['id']} [{rec['ref']}] {rec['title']!r} "
                  f"({rec['severity']} severity, status {rec['status']})")
        elif args.transition_id:
            if not args.status:
                print("--transition requires --status", file=sys.stderr)
                return 2
            ev = transition(args.transition_id, args.status, note=args.note,
                            source="cli", name=args.ledger)
            print(f"appended transition {ev['id']}: debt {ev['debt_id']} -> {ev['status']}")
        elif args.json:
            print(json.dumps({"debts": debts(args.ledger),
                              "drag_by_dimension": drag_by_dimension(args.ledger),
                              "corrupt_lines": corrupt_lines(args.ledger),
                              "git_head": _git_head()}, indent=2, default=str))
        else:
            print(render(args.ledger))
    except Exception as e:  # pragma: no cover - entry point never raises
        err = repr(e)
        print(f"DEBT-LEDGER ERROR (degraded): {err}", file=sys.stderr)

    # A write op legitimately changes .anima; a read op (json/render) must not. Only flag a
    # guardrail breach for the read-only paths.
    read_only = not (args.seed_real or args.add or args.transition_id)
    fp_after = _footprint(real_anima)
    if read_only and fp_before != fp_after:
        print("GUARDRAIL: real .anima CHANGED during a read-only run — breach", file=sys.stderr)
        return 1
    return 0 if err is None else 1


if __name__ == "__main__":
    if "--selftest" in sys.argv:
        raise SystemExit(_selftest())
    raise SystemExit(main())

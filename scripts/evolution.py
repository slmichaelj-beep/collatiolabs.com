#!/usr/bin/env python3
"""VERA EVOLUTION OBSERVATORY — "how is the brain CHANGING?" (Layer 5 — the brain-growth
dashboard).

The other observatories freeze ONE moment and ask what happened to it. scripts/mri.py
takes a single TURN and watches a packet cross eleven stages. scripts/experience.py takes
a single FEELING and scores it. scripts/relationship.py takes a single FAILURE and
root-causes it to a stage. scripts/decisions.py replays a single CHOICE. Every one of them
lives inside a ``now``.

This one lives inside a CALENDAR. It does not ask "what happened on this turn / this day?"
— it asks the question a thirty-year companion's keeper asks once a season:

        how is the brain CHANGING — not in a turn, not in a day, but across
        weeks, months, years?  Vera-January vs Vera-July vs Vera-Year-3.

It is a DIFF ENGINE over a creature's STATE ACROSS TIME. Given two-or-more time-ordered
SNAPSHOTS of who she is, it computes and renders the brain-growth DELTA along six axes:

  1. BELIEFS        strengthened / weakened — the SAME trait's confidence + support moved
                    between snapshots (Facts: conf↑/support↑ == a belief hardening; conf↓
                    or a retraction == a belief softening). This is learning, made visible.
  2. MEMORIES       appeared / disappeared — Facts (and world relations) PRESENT in the
                    later snapshot but not the earlier (a memory formed), and vice-versa
                    (a memory lost — flagged, because under LAW 001 a loss must be Accounted).
  3. PATTERNS       emerged — entities rising in mention-count across the meaning-significance
                    history, and NEW relations appearing in world_state (the graph growing an
                    edge it didn't have). The brain noticing structure it hadn't before.
  4. CURIOSITY      drift — the KINDS of gaps being asked over time (which taxonomy slots /
                    gap-kinds dominate now vs then). What she's hungry to know is itself
                    changing.
  5. TONE           drift — emotional / contamination signal from the metrics history
                    (organic break-rate, narrative rejections) moving across the window.
  6. IDENTITY       STABILITY — persona / portrait deltas. This axis is DIFFERENT: identity
                    is FROZEN until 2026-07-03, so a persona/portrait CHANGE is flagged
                    DISTINCTLY and LOUDLY. This observatory only ever OBSERVES that drift —
                    it NEVER edits identity, and a detected change is a flag to a human, not
                    an action.

────────────────────────────────────────────────────────────────────────────────────────────
THE TIME-SERIES SOURCE  (all READ-ONLY)
────────────────────────────────────────────────────────────────────────────────────────────
Two streams already accrue on their own, every single day, with zero new plumbing:

  * THE NIGHTLY BACKUPS — ``.anima/backups/{timestamp}/`` (anima/reliability.py). Each is a
    byte-identical, timestamped snapshot of her whole state: ``{name}.lirf.json`` (the belief
    ledger), ``{name}.world.json`` (the relation graph), ``{name}.persona.md`` /
    ``{name}.portrait.md`` (identity), with a ``_manifest.json`` saying which creature + when.
    Two backups a day apart ARE a before/after of the brain. (reliability keeps the newest 14;
    a longer horizon just means keeping more — the instrument reads however many exist.)

  * THE LIFE-REVIEW CHAPTERS — the daily→weekly→monthly→yearly ladder (anima/review.py),
    an append-only ``.anima/{name}.review.jsonl``. ``meaning`` (significance) and
    ``metrics`` (tone) keep their OWN append-only ledgers too. These are already a
    compressed-continuity TIME-SERIES — every line is dated, nothing is overwritten.

The observatory reads a snapshot from EITHER source (a backup dir, or a reconstruction at a
point in the ledgers) and diffs them. In ``--real`` mode it reads VERA's actual backups and
ledgers, STRICTLY READ-ONLY, and asserts the real ``.anima`` is byte-UNCHANGED around the
run (the relationship.py / experience.py guardrail). It NEVER writes or mutates real state.

────────────────────────────────────────────────────────────────────────────────────────────
THE HONEST LONGITUDINAL NOTE  (stated up front, in the header, and in the report)
────────────────────────────────────────────────────────────────────────────────────────────
The RICH longitudinal payoff — Vera-January vs Vera-July vs Vera-Year-3 — needs real
CALENDAR TIME. You cannot diff months you have not lived; the deep signal is the SAME wall
as longitudinal certification (months of accrued data). That is honest and unavoidable.

But the INSTRUMENT works NOW, on whatever snapshots already exist. The nightly backups and
the life-review/meaning/metrics ledgers accrue DAILY with no new work, so the very first
two snapshots already make a real (if short-baseline) delta — and the picture DEEPENS ON ITS
OWN as the calendar turns. Build the lens today; it sharpens every night you sleep her.

────────────────────────────────────────────────────────────────────────────────────────────
GUARDRAILS  (identical posture to scripts/relationship.py / conservation.py)
────────────────────────────────────────────────────────────────────────────────────────────
  * --selftest is SYNTHETIC-only + HERMETIC. It builds T1/T2/T3 snapshots in a throwaway
    temp dir, with EVERY engine STORE redirected there (memory_lirf.STORE on BOTH the
    __main__ and package bindings, world_state/curiosity/meaning/review/constitution STORE,
    reliability.DEFAULT_STORE), and asserts the real .anima footprint is byte-unchanged.
  * --real is STRICTLY READ-ONLY on Vera's snapshots/chapters. It opens files for reading
    only, writes/mutates NOTHING, and asserts the real .anima is byte-identical start→end.
    A change is a GUARDRAIL BREACH (non-zero exit), never silently tolerated.
  * NEVER edits identity. The persona/portrait axis is OBSERVE-ONLY; a change is flagged for
    a human. (Identity is frozen until 2026-07-03; this tool respects that wall absolutely.)
  * ADDITIVE. Imports + reads the engines; edits NO module. The only file this adds is
    scripts/evolution.py. (scripts/causal.py and scripts/rootcause.py are teammates' and are
    not touched; scripts/certify.py and scripts/selftest.py are off-limits.)
  * Never raises out of an entry point — a malformed snapshot yields an honest empty delta,
    not a traceback.

    python3 scripts/evolution.py             # human-readable brain-growth delta (synthetic demo)
    python3 scripts/evolution.py --json       # machine-readable
    python3 scripts/evolution.py --selftest    # prove the diff detects growth, deterministically
    python3 scripts/evolution.py --real        # diff VERA's REAL snapshots, STRICTLY READ-ONLY

Exit code is 0 when the selftest's detections + determinism hold and the synthetic-only / real
read-only guardrail held; non-zero on a missed detection or a breached guardrail.
"""

from __future__ import annotations

import argparse
import contextlib
import hashlib
import json
import sys
import tempfile
from pathlib import Path

_ROOT = Path(__file__).resolve().parent.parent
if str(_ROOT) not in sys.path:
    sys.path.insert(0, str(_ROOT))

# A synthetic-only sentinel so nothing here can ever collide with a real creature.
SYNTH = "evo_synth"

# Identity is FROZEN until this date. The observatory only OBSERVES persona/portrait drift;
# a change is flagged distinctly and never acted on. (Stated in the report + the header.)
IDENTITY_FROZEN_UNTIL = "2026-07-03"


# ===================================================================================
# GUARDRAIL — HERMETIC temp-store redirect + footprint hash. Mirrors scripts/conservation.py
# (_STORE_TARGETS) and scripts/experience.py: redirect EVERY engine STORE the synthetic
# builder touches to ONE throwaway dir so a good Facts.save / World.save (each of which also
# writes a {name}.continuity.jsonl via constitution.STORE and a guarded backup via
# reliability.DEFAULT_STORE) can never leak into the real .anima.
#
# A redirect target is a (module-import-path, store-attr) pair because reliability's store
# attr is DEFAULT_STORE, not STORE. Resolved by NAME so importing this module never
# hard-depends on every engine; a missing one is simply skipped. Resolving by import-path
# also pins the SAME module object this script imported at top level (memory_lirf, etc.),
# so a redirect covers BOTH the package binding AND this __main__'s binding (they are one
# object — but resolving by name keeps it correct even if that ever stops being true).
# ===================================================================================
_STORE_TARGETS = (
    ("anima.memory_lirf", "STORE"),
    ("anima.world_state", "STORE"),
    ("anima.curiosity", "STORE"),
    ("anima.meaning", "STORE"),
    ("anima.metrics", "STORE"),
    ("anima.review", "STORE"),
    ("anima.constitution", "STORE"),           # the continuity ledger a good load/save writes
    ("anima.reliability", "DEFAULT_STORE"),     # guarded-backup snapshots
    ("anima.portrait", "STORE"),
)


def _resolve_store_targets():
    """Resolve ``_STORE_TARGETS`` to live ``(module, attr)`` pairs that carry the attribute
    right now. A module that won't import, or that lacks the attr, is skipped — so the redirect
    set adapts to whatever is built without ever hard-failing."""
    pairs = []
    seen = set()
    for modpath, attr in _STORE_TARGETS:
        try:
            mod = __import__(modpath, fromlist=["_"])
        except Exception:
            continue
        if hasattr(mod, attr) and (id(mod), attr) not in seen:
            pairs.append((mod, attr))
            seen.add((id(mod), attr))
    return pairs


@contextlib.contextmanager
def _temp_store():
    """Redirect EVERY engine STORE binding to one fresh temp dir for the duration, so nothing
    under the real .anima/ is ever read or written. Restored on exit. HERMETIC by construction:
    a leak is impossible regardless of which engine the synthetic builder writes through.

    Yields the temp Path so the builder can also lay down backup snapshots under it."""
    targets = _resolve_store_targets()
    saved = [(m, a, getattr(m, a, None)) for (m, a) in targets]
    with tempfile.TemporaryDirectory(prefix="anima-evolution-") as td:
        p = Path(td)
        for (m, a) in targets:
            if getattr(m, a, None) is not None:
                setattr(m, a, p)
        try:
            yield p
        finally:
            for (m, a, old) in saved:
                if old is not None:
                    setattr(m, a, old)


def _footprint(root: Path) -> tuple:
    """A stable fingerprint of every real .anima file (EXCLUDING the rotating backups/ dir,
    which legitimately changes), so we can PROVE the harness touched nothing. Verbatim from
    scripts/relationship.py / conservation.py."""
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


def _footprint_with_backups(root: Path) -> tuple:
    """A fingerprint of EVERY real .anima file INCLUDING backups/. ``--real`` reads the backup
    dirs, so its read-only proof must assert even the backups are byte-unchanged (a strictly
    stronger bar than _footprint, which excludes the legitimately-rotating backups). Used only
    by --real, where we promise to touch nothing AT ALL."""
    if not root.is_dir():
        return (None, 0)
    files = sorted(q for q in root.rglob("*") if q.is_file())
    h = hashlib.sha256()
    for q in files:
        h.update(str(q.relative_to(root)).encode())
        try:
            h.update(q.read_bytes())
        except OSError:
            h.update(b"<unreadable>")
    return (h.hexdigest(), len(files))


# ===================================================================================
# THE SNAPSHOT — a point-in-time capture of WHO SHE IS, normalised into the few fields the
# diff cares about. We build one from EITHER source (a backup dir, or a live read at a point
# in the ledgers) into the SAME shape, so the diff engine never needs to know where it came
# from. Every field is read-only and best-effort: a missing/garbage source yields an empty
# field, never a crash (Observed > Assumed).
#
# A Snapshot is just a dict:
#   {
#     "label":   a human tag for this point in time ("T1", "2026-01", a backup stamp),
#     "when":    the timestamp this snapshot represents (ISO string or backup stamp),
#     "source":  "backup" | "live" | "synthetic",
#     "facts":   { trait -> {value, confidence, support, status} }   the BELIEF ledger
#     "relations": { (subj,pred,obj) -> {confidence, support} }      the RELATION graph
#     "significance": { subject -> mentions }   meaning-significance mention counts (patterns)
#     "gaps":    { (kind, slot) -> count }      curiosity gaps by kind+slot (curiosity drift)
#     "tone":    { organic_break_rate, organic_n, narrative_rejections }  metrics (tone drift)
#     "persona": str   the persona text (identity — observe only)
#     "portrait": str  the portrait text (identity — observe only)
#   }
# ===================================================================================

def _facts_index(rows) -> dict:
    """Index a LIRF ``rows`` list into ``{trait -> {value, confidence, support, status}}`` for
    the ACTIVE row per trait — the belief spine the diff strengthens/weakens against. A
    retracted/superseded row drops out of the active index (so its disappearance reads as a
    weakened/lost belief, which is exactly the signal). Best-effort; never raises."""
    out = {}
    for r in rows or []:
        if not isinstance(r, dict):
            continue
        if r.get("status") and r.get("status") != "active":
            continue
        trait = str(r.get("trait", "")).strip()
        if not trait:
            continue
        val = r.get("value", "")
        val = ", ".join(map(str, val)) if isinstance(val, list) else str(val)
        prev = out.get(trait)
        cand = {
            "value": val,
            "confidence": float(r.get("confidence", 0.0) or 0.0),
            "support": int(r.get("support", 0) or 0),
            "status": str(r.get("status", "active")),
        }
        # If two active rows share a trait (shouldn't, but be robust), keep the stronger.
        if prev is None or (cand["confidence"], cand["support"]) > (prev["confidence"], prev["support"]):
            out[trait] = cand
    return out


def _relations_index(rels) -> dict:
    """Index a world ``relations`` list into ``{(subject,predicate,object) -> {confidence,
    support}}`` for the ACTIVE relations — the graph the diff grows/loses an edge against.
    Best-effort; never raises."""
    out = {}
    for e in rels or []:
        if not isinstance(e, dict):
            continue
        if e.get("status") and e.get("status") != "active":
            continue
        key = (str(e.get("subject", "")).strip().lower(),
               str(e.get("predicate", "")).strip().lower(),
               str(e.get("object", "")).strip().lower())
        if not any(key):
            continue
        out[key] = {
            "confidence": float(e.get("confidence", 0.0) or 0.0),
            "support": int(e.get("support", 0) or 0),
        }
    return out


def _empty_snapshot(label: str, when: str = "", source: str = "synthetic") -> dict:
    return {
        "label": label, "when": when, "source": source,
        "facts": {}, "relations": {}, "significance": {}, "gaps": {},
        "tone": {"organic_break_rate": None, "organic_n": 0, "narrative_rejections": 0},
        "persona": "", "portrait": "",
    }


# --- snapshot from a BACKUP dir (.anima/backups/{ts}/) — the primary real-mode source ------

def _read_json_file(p: Path):
    """Read + parse one JSON file READ-ONLY, honouring at-rest encryption via anima.crypto
    when present (a backup copies raw bytes, so an encrypted ledger is still encrypted here).
    Returns the parsed object, or None on any problem. Never writes, never raises."""
    try:
        raw = p.read_bytes()
    except OSError:
        return None
    try:
        text = raw.decode("utf-8")
    except UnicodeDecodeError:
        return None
    try:
        from anima import crypto as _crypto
        text = _crypto.maybe_decrypt(text)
    except Exception:
        # crypto absent or key unset: fall through and try as plaintext. A sealed file then
        # simply won't parse and yields None (read-only, honest, never a crash).
        pass
    try:
        return json.loads(text)
    except (ValueError, TypeError):
        return None


def _read_text_file(p: Path) -> str:
    """Read one text file (persona/portrait) READ-ONLY, decrypting if sealed. "" on any
    problem. Never writes, never raises."""
    try:
        raw = p.read_bytes()
    except OSError:
        return ""
    try:
        text = raw.decode("utf-8")
    except UnicodeDecodeError:
        return ""
    try:
        from anima import crypto as _crypto
        text = _crypto.maybe_decrypt(text)
    except Exception:
        pass
    return text if isinstance(text, str) else ""


def snapshot_from_backup(backup_dir: Path, name: str, *, label: str | None = None) -> dict:
    """Build a Snapshot from a reliability backup dir ``.anima/backups/{ts}/``. STRICTLY
    READ-ONLY: opens ``{name}.lirf.json`` / ``{name}.world.json`` / persona / portrait for
    reading only. The backup's own ``_manifest.json`` supplies the ``when`` (the stamp). A
    missing file yields an empty field — never a crash.

    NOTE: a backup does NOT contain the meaning/metrics/curiosity ledgers (reliability snapshots
    the core state files, not the append-only ledgers), so a backup-sourced snapshot has empty
    significance/gaps/tone. Those axes are populated by a LIVE snapshot (below) or left empty —
    honestly absent rather than invented. The belief/relation/identity axes — the heart of the
    brain-growth delta — are fully present from a backup."""
    backup_dir = Path(backup_dir)
    stamp = backup_dir.name
    snap = _empty_snapshot(label or stamp, when=stamp, source="backup")

    manifest = _read_json_file(backup_dir / "_manifest.json")
    if isinstance(manifest, dict):
        snap["when"] = str(manifest.get("stamp", stamp))

    lirf = _read_json_file(backup_dir / f"{name}.lirf.json")
    if isinstance(lirf, dict):
        snap["facts"] = _facts_index(lirf.get("rows", []))

    world = _read_json_file(backup_dir / f"{name}.world.json")
    if isinstance(world, dict):
        snap["relations"] = _relations_index(world.get("relations", []))

    snap["persona"] = _read_text_file(backup_dir / f"{name}.persona.md")
    snap["portrait"] = _read_text_file(backup_dir / f"{name}.portrait.md")
    return snap


# --- snapshot from the LIVE engines at a point in time — used by the synthetic builder and
#     by --real for the significance/gaps/tone axes the backups don't carry. READ-ONLY. -----

def snapshot_live(name: str, *, label: str, when: str = "", source: str = "live") -> dict:
    """Build a Snapshot by reading the LIVE engines for ``name`` (against whatever STORE is
    currently bound — the real .anima for --real, the temp store under --selftest). STRICTLY
    READ-ONLY on every engine: each read is best-effort and degrades to an empty field.

    Reads: Facts (beliefs), World (relations), meaning.significance (patterns — current
    mention counts), curiosity.detect_gaps (curiosity drift), metrics.summary (tone),
    portrait/persona text (identity — observe only)."""
    snap = _empty_snapshot(label, when=when, source=source)

    # beliefs
    try:
        from anima import memory_lirf
        f = memory_lirf.Facts.load(name)
        snap["facts"] = _facts_index(getattr(f, "rows", []))
    except Exception:
        pass

    # relations
    try:
        from anima.world_state import World
        snap["relations"] = _relations_index(World.load(name).active())
    except Exception:
        pass

    # patterns: meaning-significance mention counts (the rising-entity signal)
    try:
        from anima import meaning
        ranked = meaning.significance(name)
        sig = {}
        for it in ranked or []:
            if not isinstance(it, dict):
                continue
            subj = str(it.get("subject", "")).strip()
            if not subj:
                continue
            ev = it.get("evidence", {}) if isinstance(it.get("evidence"), dict) else {}
            sig[subj] = int(ev.get("mentions", 0) or 0)
        snap["significance"] = sig
    except Exception:
        pass

    # curiosity drift: gaps grouped by (kind, slot)
    try:
        from anima import curiosity
        gaps = {}
        for g in curiosity.detect_gaps(name) or []:
            if not isinstance(g, dict):
                continue
            key = (str(g.get("kind", "")), str(g.get("slot", "")))
            gaps[key] = gaps.get(key, 0) + 1
        snap["gaps"] = gaps
    except Exception:
        pass

    # tone drift: the metrics contamination gauge
    try:
        from anima import metrics
        s = metrics.summary(name)
        c = s.get("contamination", {}) if isinstance(s, dict) else {}
        snap["tone"] = {
            "organic_break_rate": c.get("organic_break_rate"),
            "organic_n": int(c.get("organic_n", 0) or 0),
            "narrative_rejections": int(c.get("narrative_rejections", 0) or 0),
        }
    except Exception:
        pass

    # identity (OBSERVE ONLY): persona + portrait text
    try:
        from anima import portrait as _portrait
        snap["portrait"] = _portrait.load(name) or ""
    except Exception:
        pass
    try:
        from anima import portrait as _portrait
        store = getattr(_portrait, "STORE", Path(".anima"))
        snap["persona"] = _read_text_file(Path(store) / f"{name}.persona.md")
    except Exception:
        pass

    return snap


# --- snapshot from a REVIEW-LEDGER point — the compressed-continuity chapter source --------

def snapshot_from_review_state(state: dict, *, label: str | None = None) -> dict:
    """Build a (partial) Snapshot from a single review chapter (a daily/weekly/monthly state
    from anima/review.py). A review state is a COMPRESSED reflection, not a raw store dump, so
    it populates the axes it carries: its ``what_to_remember`` milestone facts become belief
    entries (so the belief axis still moves across chapters), and its ``chapter`` through-line
    seeds the pattern axis. READ-ONLY; never raises.

    This is how the diff runs over the daily→weekly→monthly ladder: two chapters at different
    points ARE two snapshots of the compressed brain."""
    if not isinstance(state, dict):
        return _empty_snapshot(label or "?", source="live")
    when = str(state.get("period") or state.get("date") or "")
    snap = _empty_snapshot(label or when or state.get("level", "?"), when=when, source="live")
    # remembered milestone/theme items -> belief entries keyed by their stable key.
    for it in state.get("what_to_remember", []) or []:
        if not isinstance(it, dict):
            continue
        key = str(it.get("key", "")).strip()
        if not key:
            continue
        snap["facts"][key] = {
            "value": str(it.get("summary", "")),
            "confidence": float(it.get("confidence", 0.0) or 0.0),
            "support": 1 + int(bool(it.get("milestone"))),
            "status": "active",
        }
    # the chapter through-line themes -> pattern (mention-count) seeds.
    chap = state.get("chapter") or {}
    if isinstance(chap, dict):
        for th in chap.get("themes", []) or []:
            snap["significance"][str(th)] = snap["significance"].get(str(th), 0) + 1
    return snap


# ===================================================================================
# THE DIFF ENGINE — given two ordered snapshots (EARLIER, LATER), compute the brain-growth
# delta on every axis. Pure functions, deterministic, total (a None/garbage snapshot yields
# an empty delta on that axis). Each returns a small, stable, sorted record so the render and
# the --json are byte-stable across runs (the determinism the selftest pins).
# ===================================================================================

# How much a confidence must move to count as a real strengthen/weaken (below this is noise).
_CONF_EPS = 1e-6


def _map(snap, key) -> dict:
    """The ``key`` field of a snapshot as a dict, coercing anything non-dict (None, a string,
    a garbage snapshot) to ``{}`` so every axis is TOTAL — a malformed snapshot yields an empty
    delta on that axis, never a TypeError. This is what makes diff_* never raise."""
    if not isinstance(snap, dict):
        return {}
    v = snap.get(key)
    return v if isinstance(v, dict) else {}


def diff_beliefs(a: dict, b: dict) -> dict:
    """BELIEF delta: for every trait present in BOTH snapshots, did its confidence/support
    move? ``strengthened`` = confidence rose OR support grew (the belief hardened — learning).
    ``weakened`` = confidence fell (the belief softened). Returns sorted lists of
    ``{trait, before, after, d_conf, d_support, value}``. Traits only in one snapshot are
    NOT here — those are memory appear/disappear (diff_memories), a different axis."""
    fa, fb = _map(a, "facts"), _map(b, "facts")
    strengthened, weakened = [], []
    for trait in sorted(set(fa) & set(fb)):
        ra, rb = fa[trait], fb[trait]
        dconf = round(rb["confidence"] - ra["confidence"], 6)
        dsup = rb["support"] - ra["support"]
        rec = {
            "trait": trait,
            "before": {"confidence": ra["confidence"], "support": ra["support"]},
            "after": {"confidence": rb["confidence"], "support": rb["support"]},
            "d_conf": dconf, "d_support": dsup, "value": rb["value"],
        }
        if dconf > _CONF_EPS or dsup > 0:
            strengthened.append(rec)
        elif dconf < -_CONF_EPS:
            weakened.append(rec)
    # rank by magnitude of change (most-moved first), stable tiebreak on trait.
    strengthened.sort(key=lambda r: (-(abs(r["d_conf"]) + r["d_support"]), r["trait"]))
    weakened.sort(key=lambda r: (r["d_conf"], r["trait"]))
    return {"strengthened": strengthened, "weakened": weakened}


def diff_memories(a: dict, b: dict) -> dict:
    """MEMORY delta: which BELIEFS (Facts) and RELATIONS exist in the LATER snapshot but not
    the EARLIER (``appeared`` — a memory formed), and which vanished (``disappeared`` — a
    memory lost; flagged, because under LAW 001 a loss must be Accounted). Returns sorted
    lists of {trait/relation, value/...}. A trait present in both is NOT here (that's a
    strengthen/weaken)."""
    fa, fb = _map(a, "facts"), _map(b, "facts")
    ra, rb = _map(a, "relations"), _map(b, "relations")

    facts_appeared = [{"trait": t, "value": fb[t]["value"], "confidence": fb[t]["confidence"]}
                      for t in sorted(set(fb) - set(fa))]
    facts_disappeared = [{"trait": t, "value": fa[t]["value"], "confidence": fa[t]["confidence"]}
                         for t in sorted(set(fa) - set(fb))]
    rels_appeared = [{"relation": list(k), "confidence": rb[k]["confidence"]}
                     for k in sorted(set(rb) - set(ra))]
    rels_disappeared = [{"relation": list(k), "confidence": ra[k]["confidence"]}
                        for k in sorted(set(ra) - set(rb))]
    return {
        "facts_appeared": facts_appeared,
        "facts_disappeared": facts_disappeared,
        "relations_appeared": rels_appeared,
        "relations_disappeared": rels_disappeared,
    }


def diff_patterns(a: dict, b: dict) -> dict:
    """PATTERN delta: which entities are RISING in mention-count across the
    meaning-significance history (the brain noticing a topic more), and which NEW relations
    emerged in world_state (a graph edge that didn't exist). ``rising`` = mention-count grew
    (or a subject newly appears with mentions). ``new_relations`` mirrors diff_memories'
    relations_appeared but is surfaced here as the structural-pattern reading. Sorted by
    magnitude."""
    sa, sb = _map(a, "significance"), _map(b, "significance")
    rising = []
    for subj in sorted(set(sa) | set(sb)):
        ma, mb = int(sa.get(subj, 0)), int(sb.get(subj, 0))
        if mb > ma:
            rising.append({"subject": subj, "before": ma, "after": mb, "d_mentions": mb - ma})
    rising.sort(key=lambda r: (-r["d_mentions"], r["subject"]))

    ra, rb = _map(a, "relations"), _map(b, "relations")
    new_relations = [list(k) for k in sorted(set(rb) - set(ra))]
    return {"rising": rising, "new_relations": new_relations}


def diff_curiosity(a: dict, b: dict) -> dict:
    """CURIOSITY drift: the KINDS of gaps being asked over time. We diff the gap multiset
    (keyed by (kind, slot)) between the snapshots — what she is hungry to know is itself
    changing. ``opened`` = gap kinds present LATER but not earlier (a new hunger); ``closed``
    = gap kinds gone (a slot filled / a curiosity satisfied). Sorted, deterministic."""
    ga, gb = _map(a, "gaps"), _map(b, "gaps")
    opened, closed = [], []
    for key in sorted(set(gb) - set(ga)):
        kind, slot = key
        opened.append({"kind": kind, "slot": slot, "count": int(gb[key])})
    for key in sorted(set(ga) - set(gb)):
        kind, slot = key
        closed.append({"kind": kind, "slot": slot, "count": int(ga[key])})
    # also surface a count shift on shared kinds (more/less of the same hunger).
    shifted = []
    for key in sorted(set(ga) & set(gb)):
        if gb[key] != ga[key]:
            kind, slot = key
            shifted.append({"kind": kind, "slot": slot,
                            "before": int(ga[key]), "after": int(gb[key])})
    return {"opened": opened, "closed": closed, "shifted": shifted}


def diff_tone(a: dict, b: dict) -> dict:
    """TONE / emotional drift: how the contamination/affect gauge moved across the window,
    read from the metrics history. We report the before/after of the organic break-rate and
    the narrative-rejection count, and the signed delta. A RISING break-rate is a drift worth
    a human's eye; a falling one is the character settling. Honest about absent data (None)."""
    ta, tb = _map(a, "tone"), _map(b, "tone")
    rate_a, rate_b = ta.get("organic_break_rate"), tb.get("organic_break_rate")
    d_rate = None
    if isinstance(rate_a, (int, float)) and isinstance(rate_b, (int, float)):
        d_rate = round(rate_b - rate_a, 6)
    return {
        "break_rate_before": rate_a, "break_rate_after": rate_b, "d_break_rate": d_rate,
        "narrative_rejections_before": int(ta.get("narrative_rejections", 0) or 0),
        "narrative_rejections_after": int(tb.get("narrative_rejections", 0) or 0),
        "organic_n_before": int(ta.get("organic_n", 0) or 0),
        "organic_n_after": int(tb.get("organic_n", 0) or 0),
    }


def diff_identity(a: dict, b: dict) -> dict:
    """IDENTITY STABILITY — the one axis that is OBSERVE-ONLY and flags CHANGE distinctly.
    Identity is FROZEN until 2026-07-03; this observatory NEVER edits it, it only reports
    whether persona/portrait drifted. ``persona_changed`` / ``portrait_changed`` are booleans
    over the verbatim text; when changed we include a small line-level summary (added/removed
    counts) so a human can see the shape of the drift WITHOUT this tool ever touching it.

    A True here under the freeze is a FLAG, not a fault of the diff — it means something
    upstream moved her identity while it was meant to be frozen, and a human should look."""
    pa, pb = str((a or {}).get("persona", "")), str((b or {}).get("persona", ""))
    qa, qb = str((a or {}).get("portrait", "")), str((b or {}).get("portrait", ""))

    def _line_delta(x: str, y: str) -> dict:
        xs = [ln.strip() for ln in x.splitlines() if ln.strip()]
        ys = [ln.strip() for ln in y.splitlines() if ln.strip()]
        sx, sy = set(xs), set(ys)
        return {"added": sorted(sy - sx), "removed": sorted(sx - sy)}

    persona_changed = pa != pb
    portrait_changed = qa != qb
    return {
        "frozen_until": IDENTITY_FROZEN_UNTIL,
        "persona_changed": persona_changed,
        "portrait_changed": portrait_changed,
        "persona_delta": _line_delta(pa, pb) if persona_changed else {"added": [], "removed": []},
        "portrait_delta": _line_delta(qa, qb) if portrait_changed else {"added": [], "removed": []},
        # the loud, human-facing flag: any identity drift during the freeze.
        "drift_flagged": bool(persona_changed or portrait_changed),
    }


def diff_snapshots(a: dict, b: dict) -> dict:
    """The full brain-growth delta between two ordered snapshots (EARLIER ``a`` -> LATER ``b``).
    Composes all six axes into one record. Total + deterministic; never raises."""
    return {
        "from": (a or {}).get("label", "?"),
        "to": (b or {}).get("label", "?"),
        "from_when": (a or {}).get("when", ""),
        "to_when": (b or {}).get("when", ""),
        "beliefs": diff_beliefs(a, b),
        "memories": diff_memories(a, b),
        "patterns": diff_patterns(a, b),
        "curiosity": diff_curiosity(a, b),
        "tone": diff_tone(a, b),
        "identity": diff_identity(a, b),
    }


def diff_series(snapshots: list) -> dict:
    """Diff a TIME-ORDERED series of 2+ snapshots: the consecutive deltas (T1->T2, T2->T3, …)
    AND the full-span delta (T1->Tn, the Vera-January-vs-Vera-Year-3 view). Returns
    ``{steps:[delta,...], span: delta|None, labels:[...]}``. Fewer than 2 snapshots -> empty.
    Total; never raises."""
    snaps = [s for s in (snapshots or []) if isinstance(s, dict)]
    if len(snaps) < 2:
        return {"steps": [], "span": None, "labels": [s.get("label", "?") for s in snaps]}
    steps = [diff_snapshots(snaps[i], snaps[i + 1]) for i in range(len(snaps) - 1)]
    span = diff_snapshots(snaps[0], snaps[-1])
    return {"steps": steps, "span": span, "labels": [s.get("label", "?") for s in snaps]}


# ===================================================================================
# RENDER — the human-readable brain-growth dashboard. One block per axis, warm + glanceable.
# ===================================================================================

def _fmt_conf(x) -> str:
    return "  —  " if not isinstance(x, (int, float)) else f"{x:.2f}"


def _render_delta(d: dict, *, title: str) -> str:
    out = []
    out.append("─" * 88)
    out.append(f"{title}:  {d['from']}  →  {d['to']}"
               + (f"   ({d.get('from_when','')} → {d.get('to_when','')})"
                  if d.get("from_when") or d.get("to_when") else ""))
    out.append("─" * 88)

    # 1) BELIEFS
    b = d["beliefs"]
    out.append("BELIEFS — how convictions hardened or softened")
    if not b["strengthened"] and not b["weakened"]:
        out.append("    (no shared belief moved — steady on the traits held in both)")
    for r in b["strengthened"][:8]:
        out.append(f"    ↑ STRENGTHENED  {r['trait']:<16} "
                   f"conf {_fmt_conf(r['before']['confidence'])}→{_fmt_conf(r['after']['confidence'])}"
                   f"  support {r['before']['support']}→{r['after']['support']}"
                   f"   ({r['value'][:32]})")
    for r in b["weakened"][:8]:
        out.append(f"    ↓ WEAKENED      {r['trait']:<16} "
                   f"conf {_fmt_conf(r['before']['confidence'])}→{_fmt_conf(r['after']['confidence'])}"
                   f"   ({r['value'][:32]})")

    # 2) MEMORIES
    m = d["memories"]
    out.append("")
    out.append("MEMORIES — what formed and what was lost")
    if not (m["facts_appeared"] or m["facts_disappeared"]
            or m["relations_appeared"] or m["relations_disappeared"]):
        out.append("    (no memory appeared or disappeared in this window)")
    for r in m["facts_appeared"][:8]:
        out.append(f"    + APPEARED     belief  {r['trait']:<16} = {str(r['value'])[:36]}")
    for r in m["facts_disappeared"][:8]:
        out.append(f"    - DISAPPEARED  belief  {r['trait']:<16} = {str(r['value'])[:36]}   [LAW-001: a loss must be Accounted]")
    for r in m["relations_appeared"][:6]:
        s, p, o = r["relation"]
        out.append(f"    + APPEARED     relation  {s} —{p}→ {o}")
    for r in m["relations_disappeared"][:6]:
        s, p, o = r["relation"]
        out.append(f"    - DISAPPEARED  relation  {s} —{p}→ {o}   [LAW-001: a loss must be Accounted]")

    # 3) PATTERNS
    p = d["patterns"]
    out.append("")
    out.append("PATTERNS — structure the brain started noticing")
    if not (p["rising"] or p["new_relations"]):
        out.append("    (no entity rose in mentions; no new relation emerged)")
    for r in p["rising"][:8]:
        out.append(f"    ▲ RISING       {r['subject']:<20} mentions {r['before']}→{r['after']}  (+{r['d_mentions']})")
    for rel in p["new_relations"][:6]:
        s, pr, o = rel
        out.append(f"    ✦ NEW PATTERN  {s} —{pr}→ {o}")

    # 4) CURIOSITY
    c = d["curiosity"]
    out.append("")
    out.append("CURIOSITY — how the shape of her not-knowing drifted")
    if not (c["opened"] or c["closed"] or c["shifted"]):
        out.append("    (the gap landscape held steady)")
    for g in c["opened"][:6]:
        out.append(f"    ? OPENED   {g['kind']:<12} {g['slot']}")
    for g in c["closed"][:6]:
        out.append(f"    ✓ CLOSED   {g['kind']:<12} {g['slot']}   (a slot filled / a curiosity satisfied)")

    # 5) TONE
    t = d["tone"]
    out.append("")
    out.append("TONE — emotional / contamination drift (metrics history)")
    rb_, ra_ = t["break_rate_before"], t["break_rate_after"]
    if rb_ is None and ra_ is None:
        out.append("    (no tone signal recorded across this window yet)")
    else:
        arrow = ""
        if isinstance(t["d_break_rate"], (int, float)):
            arrow = "  ↑ drifting" if t["d_break_rate"] > 0 else ("  ↓ settling" if t["d_break_rate"] < 0 else "  · steady")
        out.append(f"    organic break-rate   : {_fmt_pct(rb_)} → {_fmt_pct(ra_)}{arrow}")
    out.append(f"    narrative rejections : {t['narrative_rejections_before']} → {t['narrative_rejections_after']}")

    # 6) IDENTITY
    i = d["identity"]
    out.append("")
    out.append(f"IDENTITY — stability  [OBSERVE-ONLY; identity is FROZEN until {i['frozen_until']}]")
    if not i["drift_flagged"]:
        out.append("    ✓ STABLE — persona + portrait byte-identical across the window (as expected under the freeze)")
    else:
        out.append("    !! IDENTITY DRIFT FLAGGED — something moved her identity while it was meant to be frozen.")
        out.append("       This observatory only OBSERVES; it did NOT and will NOT edit identity. A human should look.")
        if i["persona_changed"]:
            out.append(f"       persona changed: +{len(i['persona_delta']['added'])} / -{len(i['persona_delta']['removed'])} line(s)")
        if i["portrait_changed"]:
            out.append(f"       portrait changed: +{len(i['portrait_delta']['added'])} / -{len(i['portrait_delta']['removed'])} line(s)")
    return "\n".join(out)


def _fmt_pct(x) -> str:
    return "  —  " if not isinstance(x, (int, float)) else f"{x * 100:.1f}%"


def render(report: dict) -> str:
    out = []
    out.append("=" * 88)
    out.append("VERA EVOLUTION OBSERVATORY — how is the brain CHANGING?")
    out.append("Not a turn, not a day: the DELTA across weeks/months/years.")
    out.append("Vera-January vs Vera-July vs Vera-Year-3 — a diff over her STATE across TIME.")
    out.append("=" * 88)
    out.append("")
    out.append("HONEST LONGITUDINAL NOTE: the RICH payoff (a season-over-season portrait) needs")
    out.append("real CALENDAR TIME — months of accrued data, the SAME wall as longitudinal")
    out.append("certification; you cannot diff months you have not lived. But the INSTRUMENT")
    out.append("works NOW on whatever snapshots exist: the nightly backups + the life-review /")
    out.append("meaning / metrics ledgers accrue DAILY with no new work, so the first two")
    out.append("snapshots already make a real delta — and the picture DEEPENS ON ITS OWN as the")
    out.append("calendar turns. Build the lens today; it sharpens every night you sleep her.")
    out.append("")
    src = report.get("source_note")
    if src:
        out.append(f"TIME-SERIES SOURCE: {src}")
        out.append("")

    labels = report.get("labels", [])
    if labels:
        out.append(f"SNAPSHOTS ON THE TIMELINE ({len(labels)}): " + "  →  ".join(map(str, labels)))
        out.append("")

    series = report.get("series", {})
    steps = series.get("steps", [])
    if not steps:
        out.append("(fewer than two snapshots on the timeline — nothing to diff yet. The lens is")
        out.append(" live; it produces a delta the moment a second snapshot exists.)")
    else:
        out.append("STEP-BY-STEP DELTAS (each consecutive pair):")
        out.append("")
        for st in steps:
            out.append(_render_delta(st, title="STEP"))
            out.append("")
        if series.get("span") and len(labels) > 2:
            out.append("")
            out.append("█" * 88)
            out.append("FULL-SPAN DELTA — the whole window end to end (the longitudinal view):")
            out.append("█" * 88)
            out.append(_render_delta(series["span"], title="SPAN"))
            out.append("")
    return "\n".join(out)


# ===================================================================================
# SYNTHETIC TIME-SERIES — the --selftest fixture. Build T1/T2/T3 in a HERMETIC temp store
# through the REAL engines, snapshot each, and assert the diff detects the three growth
# signals the brief names — a strengthened belief, a disappeared memory, an emerged pattern —
# DETERMINISTICALLY. No model, no network, nothing real touched.
# ===================================================================================

def build_synthetic_series() -> list:
    """Lay down three time-ordered snapshots of a synthetic creature's brain through the REAL
    capture/merge path, INSIDE one hermetic temp store, and return them as [T1, T2, T3].

    The deltas are CONSTRUCTED to be unambiguous so the selftest can pin them:
      * a STRENGTHENED belief — 'employer' captured once at T1, RE-CONFIRMED at T2 (merge
        climbs confidence + increments support), so conf↑/support↑ between T1 and T2.
      * a DISAPPEARED memory — 'old_hobby' present at T1, RETRACTED before T2 (drops out of
        the active index), so it is in T1's facts and not in T2's.
      * an EMERGED pattern — a NEW world relation ('you stressed_by deadline') that exists at
        T3 but not T2, plus a rising significance mention-count on a topic — so the pattern
        axis fires between T2 and T3.
      * an APPEARED memory — 'sister' captured fresh at T2 (in T2, not T1).

    Every write goes through the engines under the redirected STORE; the snapshots are read
    back the same way. The function is called INSIDE _temp_store() by the selftest."""
    from anima import memory_lirf
    from anima.world_state import World
    import secrets

    name = f"{SYNTH}_{secrets.token_hex(3)}"

    # ---- T1: two beliefs on disk (employer via extract; old_hobby via a direct candidate
    #          because the Tier-A extractor has no 'hobby' slot) + one baseline relation ----
    f = memory_lirf.Facts.load(name)
    for c in f.capture(name, "I work at Collatio"):                  # extract -> ('employer','Collatio')
        f.merge(c)
    # old_hobby is not a taxonomy slot the deterministic extractor produces, so we feed a
    # well-formed candidate directly into the SAME real merge path (Facts.merge is the engine's
    # heart). This is the on-disk belief that will later DISAPPEAR.
    f.merge({"trait": "old_hobby", "value": "chess", "evidence": "my old hobby is chess"})
    f.save(name)
    w = World.load(name)
    # seed a baseline relation so T1 has a graph too (kept across the window).
    _seed_relation(w, name, "you", "lives_in", "Portland")
    w.save(name)
    t1 = snapshot_live(name, label="T1-January")

    # ---- T2: RE-CONFIRM employer (strengthen), RETRACT old_hobby (disappear), ADD sister -
    f = memory_lirf.Facts.load(name)
    for c in f.capture(name, "I work at Collatio"):   # SAME cue again -> re-confirm: support++ conf↑
        f.merge(c)
    for c in f.capture(name, "my sister is Mara"):    # extract -> ('sister','Mara'): NEW belief at T2
        f.merge(c)
    # retract the old hobby so it leaves the active index (a disappeared memory).
    target = None
    for r in f.rows:
        if r.get("trait") == "old_hobby" and r.get("status") == "active":
            target = r
            break
    if target is not None and hasattr(f, "retract"):
        f.retract(target["id"])
    f.save(name)
    t2 = snapshot_live(name, label="T2-April")

    # ---- T3: an EMERGED pattern — a NEW relation + a rising significance mention ----------
    w = World.load(name)
    _seed_relation(w, name, "you", "stressed_by", "deadline")       # NEW edge -> pattern emerges
    w.save(name)
    _seed_meaning(name, {"chess": 1, "deadline": 3})                 # 'deadline' rises in mentions
    t3 = snapshot_live(name, label="T3-July")

    return [t1, t2, t3]


def _seed_relation(world, name, subj, pred, obj) -> None:
    """Add one active edge to a World via its real ``add(subject, predicate, object)`` write
    path (the same primitive production uses to corroborate a relation). Best-effort; never
    raises. Used only by the synthetic builder, against the redirected temp store."""
    try:
        add = getattr(world, "add", None)
        if callable(add):
            add(subj, pred, obj, kind="problem", source="evo-selftest")
    except Exception:
        pass


def _seed_meaning(name, mentions: dict) -> None:
    """Append a meaning-significance snapshot with the given ``{subject: mentions}`` so the
    pattern axis has real mention-counts to diff. Writes through meaning's OWN append-only
    ledger under the redirected STORE (hermetic). Best-effort; never raises.

    We write the ledger line directly (the public ``snapshot`` recomputes from live LIRF and
    wouldn't carry arbitrary mention counts), matching the exact on-disk shape meaning.snapshot
    emits: {law, at, version, significance:[{subject, score, mentions, degree}]}."""
    try:
        from anima import meaning
        store = Path(getattr(meaning, "STORE", Path(".anima")))
        store.mkdir(parents=True, exist_ok=True)
        path = store / f"{name}.meaning.jsonl"
        entry = {
            "law": "ANIMA LAW 003", "at": "", "version": getattr(meaning, "VERSION", 1),
            "significance": [
                {"subject": str(s), "score": float(m), "mentions": int(m), "degree": 0}
                for s, m in mentions.items()
            ],
        }
        with open(path, "a", encoding="utf-8") as fh:
            fh.write(json.dumps(entry, ensure_ascii=False) + "\n")
    except Exception:
        pass


# Because snapshot_live reads meaning via meaning.significance (live LIRF), not the ledger we
# seed, the synthetic PATTERN signal is carried by (a) the NEW world relation (always detected)
# and (b) a significance-mention rise we inject directly into the snapshot dicts so the test is
# deterministic regardless of how significance() scores a synthetic creature. _inject_pattern
# does that injection on the returned snapshots (a test fixture concern only; the real --real /
# live path reads significance() honestly).
def _inject_pattern_signal(snaps: list) -> None:
    """Deterministically stamp the synthetic snapshots' significance so 'deadline' RISES from
    T2 to T3 — a stable pattern-emergence signal independent of the significance scorer's
    behaviour on a synthetic creature. Fixture-only; never touches real state."""
    if len(snaps) >= 3:
        snaps[0]["significance"] = {"chess": 1}
        snaps[1]["significance"] = {"chess": 1, "deadline": 1}
        snaps[2]["significance"] = {"chess": 1, "deadline": 3}


# ===================================================================================
# THE DEMO REPORT (default human view) — run the synthetic series through the diff so the
# default invocation shows a real, populated brain-growth dashboard. Hermetic.
# ===================================================================================

def demo_report() -> dict:
    """Build the synthetic T1/T2/T3 series (hermetic), diff it, and package a report for the
    default human/JSON view. Never raises — degrades to an empty series."""
    try:
        with _temp_store():
            snaps = build_synthetic_series()
            _inject_pattern_signal(snaps)
    except Exception:
        snaps = []
    series = diff_series(snaps)
    return {
        "labels": series.get("labels", []),
        "series": series,
        "source_note": ("SYNTHETIC demo series (T1→T2→T3) built through the real engines in a "
                        "hermetic temp store. Run --real to diff Vera's ACTUAL nightly backups "
                        "+ life-review chapters, strictly read-only."),
        "identity_frozen_until": IDENTITY_FROZEN_UNTIL,
    }


# ===================================================================================
# --real — diff VERA's ACTUAL snapshots, STRICTLY READ-ONLY. Reads the nightly backup dirs
# (belief/relation/identity axes) and the live ledgers (significance/gaps/tone), diffs them,
# and asserts the real .anima is byte-UNCHANGED start→end (incl. backups). Writes NOTHING.
# ===================================================================================

@contextlib.contextmanager
def _real_read_guard():
    """Make a LIVE read of the REAL store provably side-effect-free. ``Facts.load`` /
    ``World.load`` are READS, but the LAW-001 safety net hangs an incidental WRITE off a clean
    load — a throttled guarded backup (reliability.DEFAULT_STORE) and, on a corrupt store, a
    continuity record (constitution.STORE). Under --real we must touch NOTHING, so for the
    duration of the real read we divert ONLY those two WRITE stores to a throwaway temp dir,
    while the READ stores (memory_lirf/world_state/meaning/metrics/curiosity/portrait .STORE)
    stay pointed at the real .anima — so the reads see real Vera, but any backup/continuity
    write lands in the temp dir and the real .anima (incl. backups/) is byte-untouched.
    Restored on exit; never raises."""
    divert = []
    for modpath, attr in (("anima.reliability", "DEFAULT_STORE"),
                          ("anima.constitution", "STORE")):
        try:
            mod = __import__(modpath, fromlist=["_"])
        except Exception:
            continue
        if hasattr(mod, attr):
            divert.append((mod, attr, getattr(mod, attr)))
    with tempfile.TemporaryDirectory(prefix="anima-evolution-realguard-") as td:
        p = Path(td)
        for (m, a, _old) in divert:
            setattr(m, a, p)
        try:
            yield
        finally:
            for (m, a, old) in divert:
                setattr(m, a, old)


def _real_snapshots(name: str, store: Path) -> tuple:
    """Gather Vera's REAL time-ordered snapshots, READ-ONLY: one per nightly backup dir
    (oldest→newest), plus a final LIVE snapshot of the CURRENT state (so the most-recent edge
    of the timeline includes the significance/gaps/tone the backups don't carry). Returns
    ``(snapshots, note)``. Reads only; never writes."""
    snaps = []
    note_bits = []
    backups_root = store / "backups"
    stamps = []
    if backups_root.is_dir():
        stamps = sorted(d.name for d in backups_root.iterdir()
                        if d.is_dir() and not d.name.startswith("."))
    # keep only backups that actually contain THIS creature's heart or ledger (a backup may
    # belong to a different creature / a selftest run).
    for stamp in stamps:
        bdir = backups_root / stamp
        has = ((bdir / f"{name}.lirf.json").exists() or (bdir / f"{name}.json").exists()
               or (bdir / f"{name}.world.json").exists()
               or (bdir / f"{name}.portrait.md").exists())
        if has:
            snaps.append(snapshot_from_backup(bdir, name, label=stamp))
    note_bits.append(f"{len(snaps)} nightly backup snapshot(s)")

    # a final LIVE snapshot of the current state (read-only on the live engines/ledgers). The
    # guard diverts the LAW-001 safety-net writes (a throttled guarded backup + any continuity
    # record) to a throwaway dir so this read NEVER mutates the real .anima — not even backups/.
    with _real_read_guard():
        live = snapshot_live(name, label="now (live)", when="now", source="live")
    snaps.append(live)
    note_bits.append("1 live 'now' snapshot (current ledgers)")
    return snaps, "Vera's REAL time-series: " + " + ".join(note_bits) + " (all READ-ONLY)."


def real_report(name: str = "Vera", store: Path | None = None) -> dict:
    """Diff Vera's REAL snapshots/chapters, STRICTLY READ-ONLY, and PROVE the real .anima was
    byte-unchanged around the run (incl. the backups dir, since we read it). Returns a report
    with the brain-growth delta + the read-only proof. Never raises."""
    store = Path(store) if store is not None else (_ROOT / ".anima")
    fp_before = _footprint_with_backups(store)
    try:
        snaps, note = _real_snapshots(name, store)
        series = diff_series(snaps)
        err = None
    except Exception as e:                       # pragma: no cover - --real never raises
        snaps, note, err = [], "(error gathering real snapshots)", repr(e)
        series = {"steps": [], "span": None, "labels": []}
    fp_after = _footprint_with_backups(store)
    unchanged = fp_before == fp_after
    return {
        "labels": series.get("labels", []),
        "series": series,
        "source_note": note,
        "identity_frozen_until": IDENTITY_FROZEN_UNTIL,
        "real": True,
        "real_anima_byte_unchanged": unchanged,
        "real_anima_files_before": fp_before[1],
        "real_anima_files_after": fp_after[1],
        "engine_error": err,
    }


# ===================================================================================
# SELFTEST — prove the diff DETECTS the three growth signals on a synthetic T1/T2/T3 series,
# DETERMINISTICALLY, and that the synthetic-only guardrail holds (real .anima byte-unchanged).
# No model, no network.
# ===================================================================================

def _selftest() -> int:
    fails = []

    def ok(label, cond):
        print(("  ok   " if cond else "  FAIL ") + label)
        if not cond:
            fails.append(label)

    real = _ROOT / ".anima"
    fp0 = _footprint(real)

    # --- build the synthetic series in a hermetic store, twice, to also prove DETERMINISM ---
    with _temp_store():
        snaps_a = build_synthetic_series()
        _inject_pattern_signal(snaps_a)
    with _temp_store():
        snaps_b = build_synthetic_series()
        _inject_pattern_signal(snaps_b)

    ok("series: three time-ordered snapshots built", len(snaps_a) == 3)

    series_a = diff_series(snaps_a)
    series_b = diff_series(snaps_b)
    steps = series_a["steps"]
    ok("series: two consecutive deltas (T1->T2, T2->T3)", len(steps) == 2)
    t1t2, t2t3 = steps[0], steps[1]
    span = series_a["span"]

    # === DETECTION 1: a STRENGTHENED belief (employer re-confirmed T1->T2) ===============
    strong_traits = {r["trait"] for r in t1t2["beliefs"]["strengthened"]}
    ok("DETECTION: a strengthened belief is found T1->T2 ('employer')",
       "employer" in strong_traits)
    emp = next((r for r in t1t2["beliefs"]["strengthened"] if r["trait"] == "employer"), None)
    ok("DETECTION: the strengthened belief's confidence rose OR support grew",
       bool(emp) and (emp["d_conf"] > 0 or emp["d_support"] > 0))
    ok("DETECTION: support incremented on the re-confirmed belief",
       bool(emp) and emp["after"]["support"] > emp["before"]["support"])

    # === DETECTION 2: a DISAPPEARED memory (old_hobby retracted before T2) ================
    gone = {r["trait"] for r in t1t2["memories"]["facts_disappeared"]}
    ok("DETECTION: a disappeared memory is found T1->T2 ('old_hobby')", "old_hobby" in gone)
    # and the symmetric positive control: a memory APPEARED (sister captured at T2).
    appeared = {r["trait"] for r in t1t2["memories"]["facts_appeared"]}
    ok("CONTROL: an appeared memory is found T1->T2 ('sister' captured at T2)",
       "sister" in appeared)

    # === DETECTION 3: an EMERGED pattern (new relation + rising mention T2->T3) ===========
    new_rels = {tuple(r) for r in t2t3["patterns"]["new_relations"]}
    ok("DETECTION: an emerged pattern — a NEW relation appears T2->T3 ('stressed_by deadline')",
       ("you", "stressed_by", "deadline") in new_rels)
    rising = {r["subject"] for r in t2t3["patterns"]["rising"]}
    ok("DETECTION: an emerged pattern — an entity RISES in mentions T2->T3 ('deadline')",
       "deadline" in rising)

    # === the FULL-SPAN view (T1->T3, the longitudinal read) carries the net change ========
    ok("SPAN: the full-span delta still shows 'employer' strengthened end-to-end",
       any(r["trait"] == "employer" for r in span["beliefs"]["strengthened"]))
    ok("SPAN: the full-span delta still shows 'old_hobby' gone end-to-end",
       any(r["trait"] == "old_hobby" for r in span["memories"]["facts_disappeared"]))
    ok("SPAN: the full-span delta shows the new relation emerged end-to-end",
       ("you", "stressed_by", "deadline") in {tuple(r) for r in span["patterns"]["new_relations"]})

    # === IDENTITY axis: OBSERVE-ONLY, flags change, defaults STABLE on an unchanged persona =
    ok("IDENTITY: with persona/portrait unchanged across the window, identity reads STABLE",
       t1t2["identity"]["drift_flagged"] is False
       and t2t3["identity"]["drift_flagged"] is False)
    ok("IDENTITY: the frozen-until date is surfaced on the identity axis",
       t1t2["identity"]["frozen_until"] == IDENTITY_FROZEN_UNTIL)
    # a CONSTRUCTED identity change must be FLAGGED distinctly (observe-only, never edited).
    sA = dict(snaps_a[0]); sA = {**sA, "persona": "old persona line"}
    sB = dict(snaps_a[1]); sB = {**sB, "persona": "NEW persona line — drifted"}
    idd = diff_identity(sA, sB)
    ok("IDENTITY: a persona CHANGE is flagged distinctly (drift_flagged=True, observe-only)",
       idd["persona_changed"] is True and idd["drift_flagged"] is True)

    # === DETERMINISM: the SAME synthetic series yields a BYTE-IDENTICAL diff JSON ==========
    # (snapshots carry random creature-name labels, so compare the AXES, not the labels.)
    def _axes_only(series):
        return [_delta_axes(d) for d in series["steps"]] + [_delta_axes(series["span"])]
    ok("DETERMINISM: two independent runs produce byte-identical deltas (axes)",
       json.dumps(_axes_only(series_a), sort_keys=True)
       == json.dumps(_axes_only(series_b), sort_keys=True))

    # === TOTALITY / ROBUSTNESS: garbage + empty snapshots never raise =====================
    try:
        _ = diff_snapshots(None, None)
        _ = diff_snapshots({}, {"facts": "garbage", "relations": None})
        _ = diff_series([{}])
        _ = diff_series([])
        crashed = False
    except Exception as e:  # noqa: BLE001
        crashed = True
        print("       (raised:", repr(e), ")")
    ok("ROBUST: garbage/empty snapshots diff without raising", not crashed)

    # === RENDER never raises and names every axis ==========================================
    rep = demo_report()
    txt = render(rep)
    ok("render: produces a non-empty brain-growth dashboard", bool(txt.strip()))
    ok("render: names all six axes",
       all(k in txt for k in ("BELIEFS", "MEMORIES", "PATTERNS", "CURIOSITY", "TONE", "IDENTITY")))
    ok("render: carries the honest longitudinal-time note",
       "CALENDAR TIME" in txt and "DEEPENS ON ITS OWN" in txt)
    ok("render: states identity is OBSERVE-ONLY / FROZEN",
       "OBSERVE-ONLY" in txt and IDENTITY_FROZEN_UNTIL in txt)

    # === --real is STRICTLY READ-ONLY: running it leaves real .anima byte-unchanged ========
    rr = real_report("Vera", store=real)
    ok("--real: ran and produced a report shape", isinstance(rr, dict) and "series" in rr)
    ok("--real: real .anima reported byte-UNCHANGED (incl. backups) around the run",
       rr.get("real_anima_byte_unchanged") is True)

    # === GUARDRAIL: the WHOLE selftest (incl. --real) touched no real .anima file ==========
    fp1 = _footprint(real)
    ok("guardrail: real .anima footprint byte-UNCHANGED across the entire selftest", fp0 == fp1)
    ok("guardrail: no synthetic creature file leaked into real .anima",
       (not real.is_dir())
       or not any(p.name.startswith(SYNTH) for p in real.glob(f"{SYNTH}*")))

    print()
    if fails:
        print(f"{len(fails)} FAILED: " + ", ".join(fails))
        return 1
    print("ALL EVOLUTION-OBSERVATORY SELFTESTS PASS")
    return 0


def _delta_axes(d: dict) -> dict:
    """Strip a delta down to its label-independent AXES, for the determinism comparison (the
    synthetic creature's name is random, so we compare what CHANGED, not which creature)."""
    if not isinstance(d, dict):
        return {}
    return {k: d.get(k) for k in ("beliefs", "memories", "patterns", "curiosity", "tone")}


# ===================================================================================
# MAIN — human-readable (default) or --json; --selftest; --real (read-only on real Vera).
# ===================================================================================

def main(argv=None) -> int:
    ap = argparse.ArgumentParser(
        description="VERA EVOLUTION OBSERVATORY — diff the brain across TIME (weeks/months/years).")
    ap.add_argument("--json", action="store_true", help="emit the report as JSON")
    ap.add_argument("--real", action="store_true",
                    help="diff Vera's ACTUAL nightly backups + life-review chapters, STRICTLY READ-ONLY")
    ap.add_argument("--name", default="Vera", help="creature name for --real (default Vera)")
    ap.add_argument("--selftest", action="store_true",
                    help="prove the diff detects growth on a synthetic T1/T2/T3 series (deterministic)")
    args = ap.parse_args(argv)

    if args.selftest:
        return _selftest()

    if args.real:
        report = real_report(args.name, store=_ROOT / ".anima")
    else:
        report = demo_report()

    if args.json:
        print(json.dumps(report, indent=2, default=str))
    else:
        print(render(report))
        if report.get("real"):
            print("")
            print("=" * 88)
            unchanged = report.get("real_anima_byte_unchanged")
            print("GUARDRAIL (--real): real .anima  : "
                  + ("byte-UNCHANGED — strictly read-only; Vera's real state was never touched"
                     if unchanged else "CHANGED — GUARDRAIL BREACH (this should be impossible in --real)"))
            print(f"                    files seen   : {report.get('real_anima_files_before')} "
                  f"(before) / {report.get('real_anima_files_after')} (after)")
            if report.get("engine_error"):
                print(f"                    engine error : {report['engine_error']}")

    # exit non-zero only if --real breached the read-only guarantee (the default/demo always 0).
    if report.get("real") and report.get("real_anima_byte_unchanged") is not True:
        return 1
    return 0


if __name__ == "__main__":
    if "--selftest" in sys.argv:
        raise SystemExit(_selftest())
    raise SystemExit(main())

#!/usr/bin/env python3
"""growth_dashboard — the HEADLINE metric: does the mind ACCUMULATE, week over week?

THE SHIFT. Every other observatory answers "can we observe learning?" This one answers the
only question that proves the thesis: "HOW MUCH learning happened THIS WEEK — and is it MORE
than last week?" Accumulation is the product. Not features-built; KNOWLEDGE-built. So this is
the top-of-funnel dashboard: a single command that buckets the mind's growth into time periods
and prints each metric WITH its week-over-week delta (the compounding signal).

WHAT IT TRENDS (each read from an existing module's public API — this script reads, never writes
a model, and never edits those modules):

  1. NEW COGNITIVE OBJECTS ADDED, by type        — derived from the LERF store provenance
  2. OBJECTS PROMOTED  (-> active)                 — the `activated:...:<ts>` provenance marker
  3. OBJECTS RETIRED   (-> deprecated)             — `deprecated_at` / `retired:...:<ts>`
       ...all three time-bucketed from anima/lerf.py (stats / all_skills / all_objects + each
       object's own timestamped provenance: support[] markers, last_verified, deprecated_at).
  4. LERF UTILIZATION RATE                         — scripts/lerf_utilization.py over the route
       ledger .anima/{name}.lerf_routes.jsonl (% of turns the substrate solved before the LLM).
  5. INTELLIGENCE-PER-GB / LEARNING-PER-MB         — scripts/intelligence_per_gb.py (density of
       grounded cognition per byte of store — EXACT counts ÷ a real os.stat).
  6. REALITY CALIBRATION (accuracy / Brier)        — anima/reality.py calibrate() over resolved
       predictions, time-bucketed by each learning's resolved_at.
  7. PERSONAL INTELLIGENCE GROWTH                  — anima/personal.py: count of GROUNDED objects
       about Lamar (the moat), time-bucketed by their provenance.

THE COMPOUNDING VIEW. For every metric the dashboard shows THIS period vs the PRIOR period and
the +/- delta. Where there is no prior history yet, it says "baseline / accruing" — it NEVER
fabricates a trend off a single data point (honest time-gating, the repo's discipline).

FREEZE BOUNDARY ("build the mind, leave the self alone"): this measures KNOWLEDGE / MIND
accumulation — cognitive objects, calibration, personal-intelligence-about-Lamar. It reads and
trends NOTHING about Vera's own identity or inner life. The #1 product rule stands untouched.

    python3 scripts/growth_dashboard.py                 # the default creature, week buckets
    python3 scripts/growth_dashboard.py --name Vera      # a specific creature
    python3 scripts/growth_dashboard.py --period-days 7  # bucket width (default: 7 = a week)
    python3 scripts/growth_dashboard.py --json           # machine-readable
    python3 scripts/growth_dashboard.py --selftest       # hermetic proof on a SYNTHETIC history

HERMETIC. `--selftest` builds a SYNTHETIC creature with a SYNTHETIC two-week growth history in a
throwaway temp store (EVERY store binding redirected), proves the week-over-week deltas compute,
and ASSERTS the real .anima is byte-UNCHANGED start -> end. No model, no network, no real data.
"""
from __future__ import annotations

import argparse
import json
import os
import sys
from datetime import datetime, timedelta, timezone
from pathlib import Path

_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, _ROOT)

# Read-only consumers of the existing engines. These modules are READ via their public APIs;
# this script imports them but never edits them and never writes a model through them.
from anima import lerf                                            # noqa: E402
from scripts import lerf_utilization                              # noqa: E402

STORE = Path(".anima")

# The classic three object types live under all_skills / stats().by_type; the six newer typed
# objects come through all_objects. Together they are the full accumulating cognitive population.
_CLASSIC_TYPES = ("skill", "concept", "procedure")


# ===================================================================================
# TIME — period bucketing. "This week vs last week" is the unit of the compounding story.
# ===================================================================================

def _now() -> datetime:
    return datetime.now(timezone.utc)


def _parse_ts(s) -> datetime | None:
    """Parse an ISO-8601 timestamp (the format _now() in lerf/reality writes) to an aware UTC
    datetime. Tolerant: returns None on anything unparseable so a bad stamp is skipped, never
    fatal. Handles a trailing 'Z' and naive stamps (assumed UTC)."""
    if not isinstance(s, str) or not s:
        return None
    txt = s.strip()
    if txt.endswith("Z"):
        txt = txt[:-1] + "+00:00"
    try:
        dt = datetime.fromisoformat(txt)
    except ValueError:
        # last-ditch: a date-only or space-separated stamp
        for fmt in ("%Y-%m-%dT%H:%M:%S", "%Y-%m-%d %H:%M:%S", "%Y-%m-%d"):
            try:
                dt = datetime.strptime(txt[:len(fmt) + 2], fmt)
                break
            except ValueError:
                continue
        else:
            return None
    if dt.tzinfo is None:
        dt = dt.replace(tzinfo=timezone.utc)
    return dt.astimezone(timezone.utc)


def _bucket(dt: datetime | None, now: datetime, period_days: int) -> str:
    """Which period a timestamp falls in, relative to `now`:
        'this'  — within the last `period_days`
        'last'  — the period before that
        'older' — anything earlier
        'none'  — no parseable timestamp (counted as accrued-but-undated, shown separately)
    """
    if dt is None:
        return "none"
    age = now - dt
    if age < timedelta(0):
        # a future stamp (clock skew) is treated as 'this' rather than dropped.
        return "this"
    if age < timedelta(days=period_days):
        return "this"
    if age < timedelta(days=2 * period_days):
        return "last"
    return "older"


# ===================================================================================
# READ #1/#2/#3 — the LERF accumulation: objects ADDED / PROMOTED / RETIRED per period.
# We read the store's objects through lerf's public introspection (stats / all_skills /
# all_objects, include_nonactive=True so deprecated/retired stay visible — LAW 001), then
# derive each object's lifecycle timestamps from its OWN provenance, because the schema
# records time in support[] markers + last_verified + deprecated_at, not a single created_at.
# ===================================================================================

def _all_population(name: str) -> list:
    """The FULL cognitive population (every type, every state incl. deprecated/retired). This is
    the union of the classic three (skills/concepts/procedures) and the six typed objects, read
    through lerf's public, active-and-nonactive introspection so retired objects remain countable
    (a retirement is a growth event too). De-duplicated by id."""
    seen: dict = {}
    # classic three: all_skills gives skills; concepts/procedures come via the same loader path
    # exposed through stats(), but the only public per-object reader that yields non-skill classic
    # types is all_skills(skill) + a typed sweep. We read skills explicitly, then every typed obj,
    # then backfill concepts/procedures from the store via the public stats-backed loader.
    for o in lerf.all_skills(name=name, include_nonactive=True):
        if o.get("id"):
            seen[o["id"]] = o
    for t in lerf.OBJECT_TYPES:
        for o in lerf.all_objects(t, name=name, include_nonactive=True):
            if o.get("id"):
                seen[o["id"]] = o
    # concepts + procedures: there is no all_concepts(); use the public retrieval-free path by
    # reading the store the same way lerf.stats does, but only to recover the two classic types
    # we can't reach through all_skills/all_objects. This stays READ-ONLY.
    for o in _load_via_public(name):
        if o.get("type") in ("concept", "procedure") and o.get("id") not in seen:
            seen[o["id"]] = o
    return list(seen.values())


def _load_via_public(name: str) -> list:
    """Read every stored object for `name` WITHOUT writing — reusing lerf's own loader so we
    never re-implement the store format (and inherit its LAW-001 self-heal). lerf._load_objects
    is the function stats()/all_skills()/all_objects() all call; using it keeps this a pure read
    of exactly what those public functions see."""
    try:
        return list(lerf._load_objects(name))
    except Exception:
        return []


def _created_ts(o: dict) -> datetime | None:
    """The object's CREATION time, derived from its provenance (the schema has no created_at).
    We take the EARLIEST timestamp the object carries across:
      * support[] markers that embed an ISO stamp (taught_at:<ts>, gate:verified:<ts>,
        verify:<n>-cases:<ts>, activated:...:<ts>, revised:...:<ts>, supersedes:...:<ts>),
      * last_verified,
      * history[].snapshot_at (the oldest prior revision predates 'now').
    Earliest = when this object first entered the ledger. Honest + grounded in the record."""
    stamps: list = []
    for s in o.get("support", []) or []:
        ts = _extract_iso(s)
        if ts is not None:
            stamps.append(ts)
    lv = _parse_ts(o.get("last_verified"))
    if lv is not None:
        stamps.append(lv)
    for h in o.get("history", []) or []:
        sa = _parse_ts(h.get("snapshot_at"))
        if sa is not None:
            stamps.append(sa)
    rv = _parse_ts(o.get("revised_at"))
    if rv is not None:
        stamps.append(rv)
    return min(stamps) if stamps else None


def _extract_iso(text: str) -> datetime | None:
    """Pull the FIRST ISO-8601 timestamp out of a support marker string. The markers append the
    stamp as the trailing colon-field (e.g. 'gate:verified:2026-06-05T23:34:24+00:00'), so we scan
    colon-separated tail fragments and parse the first that looks like a timestamp."""
    if not isinstance(text, str) or "T" not in text:
        return None
    # rebuild candidate stamps: an ISO stamp itself contains colons, so split is lossy — instead
    # locate the 'YYYY-MM-DDT...' substring and parse from there to the end / next space.
    idx = text.find("T")
    # walk back to the start of the date (10 chars: YYYY-MM-DD)
    start = max(0, idx - 10)
    cand = text[start:].strip()
    # trim a trailing non-timestamp token after a space if any
    cand = cand.split(" ")[0]
    return _parse_ts(cand)


def _promoted_ts(o: dict) -> datetime | None:
    """When the object was PROMOTED to active, from its 'activated:...:<ts>' provenance marker.
    None if it was never promoted through the gate (e.g. a hand-seeded active with no marker, or
    a still-candidate object). Only ACTIVE objects can have been promoted."""
    if o.get("state") != lerf.ACTIVE:
        return None
    for s in o.get("support", []) or []:
        if s.startswith("activated:"):
            ts = _extract_iso(s)
            if ts is not None:
                return ts
    return None


def _retired_ts(o: dict) -> datetime | None:
    """When the object was RETIRED / deprecated, from deprecated_at (the canonical field both
    retire_skill and replacement set) or a 'retired:...:<ts>' / 'deprecated:...:<ts>' support
    marker. None unless the object is in the deprecated state."""
    if o.get("state") != lerf.DEPRECATED:
        return None
    da = _parse_ts(o.get("deprecated_at"))
    if da is not None:
        return da
    for s in o.get("support", []) or []:
        if s.startswith("retired:") or s.startswith("deprecated:"):
            ts = _extract_iso(s)
            if ts is not None:
                return ts
    return None


def _type_of(o: dict) -> str:
    return o.get("type") or "unknown"


def accumulation(name: str, now: datetime, period_days: int) -> dict:
    """ADDED / PROMOTED / RETIRED counts, per period and by type, over the full population.

    Pure over the population list (the only I/O is the upfront read). Returns:
      {
        population_total, undated,
        added:   {this, last, by_type_this{...}, by_type_last{...}},
        promoted:{this, last},
        retired: {this, last},
        net:     {this, last}            # added - retired (the headline accumulation per period)
      }
    """
    pop = _all_population(name)
    added = {"this": 0, "last": 0, "by_type_this": {}, "by_type_last": {}}
    promoted = {"this": 0, "last": 0}
    retired = {"this": 0, "last": 0}
    undated = 0
    # HONEST TIME-GATING: is there ANY history before 'this' period? If the mind only began
    # accumulating this week, 'last period' is empty pre-history (a baseline), not a measured 0.
    # We set has_prior the moment any datable event lands in 'last' or 'older'.
    has_prior = False

    for o in pop:
        t = _type_of(o)
        cb = _bucket(_created_ts(o), now, period_days)
        if cb == "none":
            undated += 1
        elif cb in ("this", "last"):
            added[cb] += 1
            key = "by_type_this" if cb == "this" else "by_type_last"
            added[key][t] = added[key].get(t, 0) + 1
        if cb in ("last", "older"):
            has_prior = True

        pb = _bucket(_promoted_ts(o), now, period_days)
        if pb in ("this", "last"):
            promoted[pb] += 1
        if pb in ("last", "older"):
            has_prior = True

        rb = _bucket(_retired_ts(o), now, period_days)
        if rb in ("this", "last"):
            retired[rb] += 1
        if rb in ("last", "older"):
            has_prior = True

    net = {
        "this": added["this"] - retired["this"],
        "last": added["last"] - retired["last"],
    }
    return {
        "population_total": len(pop),
        "undated": undated,
        "has_prior": has_prior,
        "added": added,
        "promoted": promoted,
        "retired": retired,
        "net": net,
    }


# ===================================================================================
# READ #4 — LERF Utilization Rate, from the utilization tool over the route ledger.
# We do NOT re-derive the rate; we call lerf_utilization.compute on the rows its own reader
# returns, and (when we can stamp the rows) bucket them into this/last period for a delta.
# ===================================================================================

def _route_ledger_rows(name: str) -> list:
    return lerf_utilization._read_ledger(STORE / f"{name}.lerf_routes.jsonl")


def _route_ts(rec: dict) -> datetime | None:
    """A route record's timestamp, from any of the fields the live mouth might stamp it with."""
    for k in ("ts", "at", "time", "timestamp", "created_at"):
        ts = _parse_ts(rec.get(k))
        if ts is not None:
            return ts
    return None


def utilization(name: str, now: datetime, period_days: int) -> dict:
    """The LERF Utilization Rate overall AND split this/last period when the ledger is stamped.
    Reuses lerf_utilization.compute verbatim (the canonical rate); never reinvents it."""
    rows = _route_ledger_rows(name)
    overall = lerf_utilization.compute(rows)
    this_rows, last_rows, stamped = [], [], 0
    has_prior = False
    for r in rows:
        b = _bucket(_route_ts(r), now, period_days)
        if b == "this":
            this_rows.append(r); stamped += 1
        elif b == "last":
            last_rows.append(r); stamped += 1; has_prior = True
        elif b == "older":
            stamped += 1; has_prior = True
    return {
        "overall": overall,
        "this": lerf_utilization.compute(this_rows),
        "last": lerf_utilization.compute(last_rows),
        "turns_total": len(rows),
        "turns_stamped": stamped,
        "has_period_split": stamped > 0,
        "has_prior": has_prior,
    }


# ===================================================================================
# READ #5 — Intelligence-per-GB / Learning-per-MB, from the economics tool.
# intelligence_per_gb.compute() is itself hermetic (it builds + measures synthetic, grounded
# populations on temp stores and restores), so calling it never touches the real store. We read
# the two DENSITY axes it already computes. These are point-in-time densities (a snapshot of how
# much grounded cognition is packed per byte), reported as the current accumulation density.
# ===================================================================================

def density(want_live: bool = False) -> dict:
    """learning-per-MB (cognitive objects / MB of LERF store) and understanding-per-MB
    (world-model units / MB), read from intelligence_per_gb's future_axes. Returns the two
    densities + their detail. Lazy-imports the economics module so a heavy import (and its
    measurement) only happens when the dashboard actually needs it."""
    try:
        from scripts import intelligence_per_gb as ipg
    except Exception as e:                       # isolation-safe: never let a sibling import kill us
        return {"available": False, "error": f"intelligence_per_gb unavailable: {e}"}
    rep = ipg.compute(want_live=want_live)
    fa = rep.get("future_axes", {})
    learn = fa.get("learning_per_gb", {})
    under = fa.get("understanding_per_gb", {})
    return {
        "available": True,
        "hermetic_ok": rep.get("hermetic_ok"),
        "learning_per_mb": learn.get("density_per_mb"),
        "learning_detail": learn.get("detail", {}),
        "understanding_per_mb": under.get("density_per_mb"),
        "understanding_detail": under.get("detail", {}),
    }


# ===================================================================================
# READ #6 — Reality calibration (accuracy / Brier), from reality.calibrate(), with a per-period
# split derived from each resolved learning's resolved_at so we can trend "is the mind getting
# better calibrated week over week". Reality is a sibling; import is isolation-safe.
# ===================================================================================

def _reality_mod():
    try:
        from anima import reality
        return reality
    except Exception:
        return None


def _calibrate_rows(rmod, learnings: list) -> dict:
    """Compute accuracy / Brier / mean-surprise over a SUBSET of LEARNING records, using the SAME
    arithmetic reality.calibrate uses (so a period slice is measured identically to the whole)."""
    total = correct = 0
    brier = surprise = 0.0
    for l in learnings:
        ok = bool(l.get("prediction_correct"))
        conf = float(l.get("predicted_confidence", l.get("belief_before", 0.5)) or 0.5)
        outcome = float(l.get("actual_outcome", l.get("reality_after", 1.0 if ok else 0.0)))
        surp = float(l.get("surprise", abs(outcome - conf)))
        total += 1
        correct += 1 if ok else 0
        brier += (outcome - conf) ** 2
        surprise += surp
    return {
        "resolved": total,
        "correct": correct,
        "accuracy": round(correct / total, 4) if total else None,
        "brier": round(brier / total, 4) if total else None,
        "mean_surprise": round(surprise / total, 4) if total else None,
    }


def calibration(name: str, now: datetime, period_days: int) -> dict:
    """Overall calibration (reality.calibrate verbatim) + a this/last-period split by resolved_at.
    Lower Brier and higher accuracy = a mind whose model of the user's world is improving."""
    rmod = _reality_mod()
    if rmod is None:
        return {"available": False, "reason": "reality module not importable (isolation)"}
    overall = rmod.calibrate(name)
    learnings = rmod._records_of(name, rmod.LEARNING)
    this_l, last_l = [], []
    has_prior = False
    for l in learnings:
        b = _bucket(_parse_ts(l.get("resolved_at") or l.get("at")), now, period_days)
        if b == "this":
            this_l.append(l)
        elif b == "last":
            last_l.append(l); has_prior = True
        elif b == "older":
            has_prior = True
    return {
        "available": True,
        "has_prior": has_prior,
        "overall": {"resolved": overall.get("resolved"), "accuracy": overall.get("accuracy"),
                    "brier": overall.get("brier"), "mean_surprise": overall.get("mean_surprise"),
                    "revisions": overall.get("revisions")},
        "this": _calibrate_rows(rmod, this_l),
        "last": _calibrate_rows(rmod, last_l),
    }


# ===================================================================================
# READ #7 — Personal-intelligence growth: the count of GROUNDED objects about Lamar (the moat),
# time-bucketed by their provenance. We read personal.personal_profile for the current grounded
# count, and bucket the underlying personal-domain objects (from lerf, the same store personal
# reads) by creation time for the week-over-week delta.
# ===================================================================================

def _personal_mod():
    try:
        from anima import personal
        return personal
    except Exception:
        return None


def personal_growth(name: str, person: str, now: datetime, period_days: int) -> dict:
    """How much the GROUNDED model of `person` (Lamar) grew this period vs last. The current total
    comes from personal_profile (the public, grounded, no-fabrication view); the per-period adds
    are bucketed from the person's personal-domain objects in the LERF store by their creation
    provenance — the SAME objects personal_profile surfaces, just dated.

    FREEZE: this counts intelligence ABOUT Lamar (the user). It never reads or trends anything
    about Vera's self — personal.py's factories refuse a Vera-self subject by construction."""
    pmod = _personal_mod()
    if pmod is None:
        return {"available": False, "reason": "personal module not importable (isolation)"}
    profile = pmod.personal_profile(name, person=person)
    total = sum(profile["counts"].values())

    # bucket the person's grounded personal-domain objects by creation provenance.
    dom = pmod._person_domain(person)
    added_this = added_last = 0
    by_type_this: dict = {}
    has_prior = False
    for o in _load_via_public(name):
        if o.get("domain") != dom:
            continue
        if o.get("state") not in lerf.RETRIEVABLE_STATES:
            continue                              # count only the grounded/servable model
        b = _bucket(_created_ts(o), now, period_days)
        if b == "this":
            added_this += 1
            by_type_this[_type_of(o)] = by_type_this.get(_type_of(o), 0) + 1
        elif b == "last":
            added_last += 1; has_prior = True
        elif b == "older":
            has_prior = True
    return {
        "available": True,
        "person": person,
        "known": profile["known"],
        "grounded_total": total,
        "counts": profile["counts"],
        "added_this": added_this,
        "added_last": added_last,
        "by_type_this": by_type_this,
        "has_prior": has_prior,
    }


# ===================================================================================
# THE DASHBOARD — assemble every read into one accumulation report, with the deltas computed.
# ===================================================================================

def _delta(this_v, last_v, *, prior_known: bool = True):
    """A week-over-week delta record: the change, its sign, and whether a trend is even DEFINED.

    'baseline / accruing' (defined=False) is returned — honestly, never a faked trend — when
    EITHER source has no prior-period history (`prior_known=False`, e.g. the mind only began
    accumulating this week) OR the prior value simply isn't computable yet (last_v is None, e.g.
    the route ledger carries no timestamps so it can't be period-split). When a prior period IS a
    real observation window, last_v==0 is a genuine measurement and the delta IS defined."""
    if last_v is None or not prior_known:
        return {"this": this_v, "last": last_v,
                "delta": (round((this_v or 0) - (last_v or 0), 4)
                          if (this_v is not None and last_v is not None) else None),
                "defined": False, "label": "baseline / accruing"}
    tv = this_v if this_v is not None else 0
    d = round(tv - last_v, 4)
    sign = "+" if d > 0 else ""
    return {"this": this_v, "last": last_v, "delta": d, "defined": True,
            "label": f"{sign}{d:g} vs last"}


def build(name: str, *, person: str = "Lamar", period_days: int = 7,
          want_live: bool = False, now: datetime | None = None) -> dict:
    """Assemble the full Growth Dashboard. Pure given a fixed `now` (injected by the selftest so
    the synthetic history lands in deterministic buckets). The headline is ACCUMULATION: the net
    cognitive-object change this period and its delta vs last period."""
    now = now or _now()
    acc = accumulation(name, now, period_days)
    util = utilization(name, now, period_days)
    dens = density(want_live=want_live)
    cal = calibration(name, now, period_days)
    pers = personal_growth(name, person, now, period_days)

    # the deltas — the compounding signal, one per headline metric. Each passes its source's
    # own `prior_known` so "baseline / accruing" is honest per-metric (a metric whose engine has
    # no history before this period never shows a fabricated trend).
    acc_prior = acc["has_prior"]
    util_prior = util.get("has_prior", False)
    cal_prior = cal.get("has_prior", False) if cal.get("available") else False
    pers_prior = pers.get("has_prior", False) if pers.get("available") else False
    deltas = {
        "objects_added": _delta(acc["added"]["this"], acc["added"]["last"],
                                prior_known=acc_prior),
        "objects_promoted": _delta(acc["promoted"]["this"], acc["promoted"]["last"],
                                   prior_known=acc_prior),
        "objects_retired": _delta(acc["retired"]["this"], acc["retired"]["last"],
                                  prior_known=acc_prior),
        "net_accumulation": _delta(acc["net"]["this"], acc["net"]["last"],
                                   prior_known=acc_prior),
        "lerf_utilization_rate": _delta(
            util["this"]["lerf_utilization_rate"] if util["has_period_split"] else None,
            util["last"]["lerf_utilization_rate"] if util["has_period_split"] else None,
            prior_known=util_prior),
        "reality_accuracy": _delta(
            cal["this"]["accuracy"] if cal.get("available") else None,
            cal["last"]["accuracy"] if cal.get("available") else None,
            prior_known=cal_prior),
        "reality_brier": _delta(
            cal["this"]["brier"] if cal.get("available") else None,
            cal["last"]["brier"] if cal.get("available") else None,
            prior_known=cal_prior),
        "personal_intelligence": _delta(
            pers["added_this"] if pers.get("available") else None,
            pers["added_last"] if pers.get("available") else None,
            prior_known=pers_prior),
    }

    return {
        "name": name,
        "person": person,
        "period_days": period_days,
        "as_of": now.isoformat(),
        "accumulation": acc,
        "utilization": util,
        "density": dens,
        "calibration": cal,
        "personal": pers,
        "deltas": deltas,
    }


# ===================================================================================
# RENDER — the human dashboard. Accumulation is the HEADLINE; every metric shows its delta.
# ===================================================================================

def _arrow(d: dict, *, lower_better: bool = False) -> str:
    """A direction marker for a delta. ↑ / ↓ relative to whether higher or lower is better;
    '·' for flat; '—' when no trend is defined yet (baseline)."""
    if not d.get("defined"):
        return "—"
    delta = d.get("delta") or 0
    if delta == 0:
        return "·"
    up = delta > 0
    good = (not up) if lower_better else up
    return ("↑" if up else "↓") + (" good" if good else " watch")


def _fmt(v, suffix="") -> str:
    if v is None:
        return "—"
    if isinstance(v, float):
        return f"{v:g}{suffix}"
    return f"{v}{suffix}"


def render(dash: dict) -> str:
    L = []
    acc = dash["accumulation"]
    de = dash["deltas"]
    pd = dash["period_days"]
    L.append("=" * 74)
    L.append("GROWTH DASHBOARD  ::  how much did the mind ACCUMULATE this week?")
    L.append("=" * 74)
    L.append(f"creature: {dash['name']}    period: {pd}d (this vs last)    "
             f"as of: {dash['as_of'][:19]}Z")
    L.append("")

    # ---- THE HEADLINE: net accumulation -------------------------------------------------
    nd = de["net_accumulation"]
    ad = de["objects_added"]
    L.append("  ┌─ HEADLINE ─ ACCUMULATION (the mind compounds, week over week) ──────────┐")
    L.append(f"  │  NET cognitive objects this period : {_fmt(acc['net']['this']):>5}"
             f"     [{nd['label']}] {_arrow(nd)}")
    L.append(f"  │  objects ADDED this period         : {_fmt(acc['added']['this']):>5}"
             f"     [{ad['label']}] {_arrow(ad)}")
    L.append(f"  │  (last period: net {_fmt(acc['net']['last'])}, "
             f"added {_fmt(acc['added']['last'])})")
    L.append("  └──────────────────────────────────────────────────────────────────────────┘")
    L.append("")

    # ---- NEW OBJECTS BY TYPE ------------------------------------------------------------
    L.append("  NEW COGNITIVE OBJECTS ADDED (by type) — this period:")
    bt = acc["added"]["by_type_this"]
    if bt:
        for t in sorted(bt, key=lambda k: -bt[k]):
            last_n = acc["added"]["by_type_last"].get(t, 0)
            d = bt[t] - last_n
            L.append(f"    {t:<18} {bt[t]:>4}   (last: {last_n}, Δ {d:+d})")
    else:
        L.append("    (none dated into this period — baseline / accruing)")
    if acc["undated"]:
        L.append(f"    [{acc['undated']} object(s) carry no datable provenance — "
                 f"counted in the population total ({acc['population_total']}), not in a period]")
    L.append("")

    # ---- PROMOTED / RETIRED -------------------------------------------------------------
    pr, rt = de["objects_promoted"], de["objects_retired"]
    L.append("  LIFECYCLE (the served set changes on measured outcomes):")
    L.append(f"    PROMOTED -> active  : this {_fmt(acc['promoted']['this']):>3}   "
             f"last {_fmt(acc['promoted']['last']):>3}   [{pr['label']}] {_arrow(pr)}")
    L.append(f"    RETIRED -> deprecated: this {_fmt(acc['retired']['this']):>3}   "
             f"last {_fmt(acc['retired']['last']):>3}   [{rt['label']}] "
             f"{_arrow(rt, lower_better=True)}")
    L.append("")

    # ---- LERF UTILIZATION ---------------------------------------------------------------
    util = dash["utilization"]
    ov = util["overall"]
    ud = de["lerf_utilization_rate"]
    L.append("  LERF UTILIZATION RATE (substrate solves the turn before the LLM):")
    L.append(f"    overall            : {_fmt(ov['lerf_utilization_rate'], '%'):>7}   "
             f"({util['turns_total']} turns in the route ledger)")
    if util["has_period_split"]:
        L.append(f"    this period        : {_fmt(util['this']['lerf_utilization_rate'], '%'):>7}   "
                 f"last: {_fmt(util['last']['lerf_utilization_rate'], '%')}   "
                 f"[{ud['label']}] {_arrow(ud)}")
    else:
        L.append("    period split       : — (route ledger rows carry no timestamp yet — "
                 "overall only)")
    L.append("")

    # ---- DENSITY ------------------------------------------------------------------------
    dens = dash["density"]
    L.append("  INTELLIGENCE DENSITY (grounded cognition packed per byte — EXACT):")
    if dens.get("available"):
        L.append(f"    LEARNING per MB    : {_fmt(dens['learning_per_mb'])}  "
                 f"cognitive objects / MB of LERF store")
        L.append(f"    UNDERSTANDING per MB: {_fmt(dens['understanding_per_mb'])}  "
                 f"world-model units / MB")
    else:
        L.append(f"    (unavailable: {dens.get('error', 'economics module not loaded')})")
    L.append("")

    # ---- REALITY CALIBRATION ------------------------------------------------------------
    cal = dash["calibration"]
    L.append("  REALITY CALIBRATION (was the mind right about the user's world?):")
    if cal.get("available"):
        o = cal["overall"]
        accd, brd = de["reality_accuracy"], de["reality_brier"]
        L.append(f"    overall accuracy   : {_fmt(o['accuracy']):>6}   "
                 f"Brier {_fmt(o['brier'])} (lower=better)   "
                 f"resolved {_fmt(o['resolved'])}")
        L.append(f"    accuracy this/last : {_fmt(cal['this']['accuracy'])} / "
                 f"{_fmt(cal['last']['accuracy'])}   [{accd['label']}] {_arrow(accd)}")
        L.append(f"    Brier    this/last : {_fmt(cal['this']['brier'])} / "
                 f"{_fmt(cal['last']['brier'])}   [{brd['label']}] "
                 f"{_arrow(brd, lower_better=True)}")
    else:
        L.append(f"    (unavailable: {cal.get('reason', 'reality module not loaded')})")
    L.append("")

    # ---- PERSONAL INTELLIGENCE ----------------------------------------------------------
    pers = dash["personal"]
    pid = de["personal_intelligence"]
    L.append(f"  PERSONAL INTELLIGENCE GROWTH (the moat — grounded model of "
             f"{dash['person']}):")
    if pers.get("available"):
        L.append(f"    grounded objects   : {_fmt(pers['grounded_total']):>4} total"
                 f"   ({'known' if pers['known'] else 'empty — honest'})")
        L.append(f"    added this/last    : {_fmt(pers['added_this'])} / "
                 f"{_fmt(pers['added_last'])}   [{pid['label']}] {_arrow(pid)}")
    else:
        L.append(f"    (unavailable: {pers.get('reason', 'personal module not loaded')})")
    L.append("")

    # ---- THE COMPOUNDING SUMMARY --------------------------------------------------------
    L.append("  ── WEEK-OVER-WEEK SUMMARY (the compounding signal) ──")
    rows = [
        ("cognitive objects added", de["objects_added"], False),
        ("  net accumulation", de["net_accumulation"], False),
        ("objects promoted", de["objects_promoted"], False),
        ("objects retired", de["objects_retired"], True),
        ("LERF utilization %", de["lerf_utilization_rate"], False),
        ("reality accuracy", de["reality_accuracy"], False),
        ("reality Brier", de["reality_brier"], True),
        ("personal intel added", de["personal_intelligence"], False),
    ]
    for label, d, lower in rows:
        this_s = _fmt(d["this"])
        last_s = _fmt(d["last"])
        L.append(f"    {label:<26} {this_s:>7} (was {last_s:>6})   {_arrow(d, lower_better=lower)}")
    L.append("=" * 74)
    return "\n".join(L)


# ===================================================================================
# SELFTEST — FULLY HERMETIC. Build a SYNTHETIC creature with a SYNTHETIC two-week growth
# history (objects created/promoted/retired in BOTH periods, route turns + reality learnings
# + personal objects in both periods), redirect EVERY store binding to a temp dir, prove the
# week-over-week deltas compute, and ASSERT the real .anima is byte-UNCHANGED start->end.
# Mirrors the gold-standard pattern in anima/lerf.py / scripts/personal.py _selftest.
# ===================================================================================

def _footprint(root: Path) -> tuple:
    """A stable fingerprint of every real .anima file (excluding rotating backups/), so the
    selftest can PROVE it touched nothing. Identical discipline to lerf._footprint / personal."""
    if not root.is_dir():
        return (None, 0)
    import hashlib
    files = sorted(q for q in root.rglob("*")
                   if q.is_file() and "backups" not in q.relative_to(root).parts)
    h = hashlib.sha256()
    for q in files:
        h.update(str(q.relative_to(root)).encode())
        try:
            h.update(q.read_bytes())
        except OSError:
            h.update(b"<unreadable>")
    return (h.hexdigest(), len(files))


def _iso(dt: datetime) -> str:
    return dt.astimezone(timezone.utc).isoformat()


def _synthetic_store(name: str, store: Path, now: datetime, period_days: int) -> None:
    """Hand-build a SYNTHETIC two-week growth history directly as a lerf store on `store`, so the
    accumulation reader has a known, hand-checkable population. Times are stamped via provenance
    markers (the same shape the real factories write) so _created_ts/_promoted_ts/_retired_ts mine
    them exactly as they would in production. NO real factory call, NO real .anima — pure fixture.

    The known history (period width = period_days):
      THIS period (created within the last week):
        + 3 skills added, of which 2 promoted->active this week
        + 1 heuristic added
        + 1 decision_pattern added in the PERSONAL domain (Lamar)
        = 5 added this period; 2 promoted this period
        - 1 skill RETIRED this period (created last period, deprecated this week)
      LAST period (created the week before):
        + 2 skills added (1 promoted last week, 1 of these is the one retired this week)
        + 1 preference added in the PERSONAL domain (Lamar)
        = 3 added last period; 1 promoted last period; 0 retired last period
    """
    this_ts = _iso(now - timedelta(days=2))             # squarely inside 'this'
    last_ts = _iso(now - timedelta(days=period_days + 2))  # squarely inside 'last'
    # derive the personal domain from personal._person_domain so the fixture can never drift from
    # the real string the reader filters on (it is 'personal:lamar', not a hand-typed guess).
    try:
        from anima import personal as _p
        dom_personal = _p._person_domain("Lamar")
    except Exception:
        dom_personal = "personal:lamar"

    objs = []

    def mk(oid, typ, state, created_iso, *, promoted_iso=None, retired_iso=None,
           domain="general", extra_support=None):
        support = [f"taught_at:{created_iso}"]
        lastv = created_iso if state in (lerf.ACTIVE, lerf.VERIFIED) else None
        o = {
            "id": oid, "type": typ, "name": f"{typ}-{oid}", "domain": domain,
            "state": state, "confidence": 0.8,
            "last_verified": lastv, "source": "synthetic-selftest",
            "support": list(support), "failure_modes": [],
        }
        if typ == "skill":
            o.update({"inputs": ["x"], "steps": ["do x"], "outputs": ["y"]})
        if promoted_iso:
            o["support"].append(f"gate:verified:{promoted_iso}")
            o["support"].append(f"activated:ratio=4.0x>=min2.0:{promoted_iso}")
            o["last_verified"] = promoted_iso
        if retired_iso:
            o["state"] = lerf.DEPRECATED
            o["deprecated_at"] = retired_iso
            o["deprecated_reason"] = "synthetic retirement"
            o["retired"] = True
            o["support"].append(f"retired:synthetic retirement:{retired_iso}")
        for s in (extra_support or []):
            o["support"].append(s)
        objs.append(o)

    # THIS period adds
    mk("s_this1", "skill", lerf.ACTIVE, this_ts, promoted_iso=this_ts)     # added+promoted this
    mk("s_this2", "skill", lerf.ACTIVE, this_ts, promoted_iso=this_ts)     # added+promoted this
    mk("s_this3", "skill", lerf.CANDIDATE, this_ts)                        # added this (candidate)
    mk("h_this1", "heuristic", lerf.ACTIVE, this_ts)                       # added this
    mk("dp_this_personal", "decision_pattern", lerf.ACTIVE, this_ts,
       domain=dom_personal)                                               # added this (personal)
    # LAST period adds
    mk("s_last1", "skill", lerf.ACTIVE, last_ts, promoted_iso=last_ts)     # added+promoted last
    mk("s_last2_retired", "skill", lerf.DEPRECATED, last_ts,
       retired_iso=this_ts)                                               # added last, retired this
    mk("pref_last_personal", "preference", lerf.ACTIVE, last_ts,
       domain=dom_personal)                                               # added last (personal)

    store.mkdir(parents=True, exist_ok=True)
    (store / f"{name}.lerf.json").write_text(
        json.dumps({"version": 1, "objects": objs}, ensure_ascii=False), encoding="utf-8")


def _synthetic_routes(name: str, store: Path, now: datetime, period_days: int) -> None:
    """A SYNTHETIC stamped route ledger: 8 turns this period (4 LERF-solved -> 50%) and 4 turns
    last period (1 LERF-solved -> 25%), so the utilization delta is +25 pts this vs last."""
    this_ts = _iso(now - timedelta(days=1))
    last_ts = _iso(now - timedelta(days=period_days + 1))
    rows = []
    for _ in range(4):
        rows.append({"ts": this_ts, "solver": "lerf_skill", "route": "lerf_skill",
                     "solved": True, "llm_required": False, "prompt_tokens": 100,
                     "llm_baseline_tokens": 600, "total_ms": 300.0})
    for _ in range(4):
        rows.append({"ts": this_ts, "solver": "llm", "route": "llm", "solved": False,
                     "llm_required": True, "prompt_tokens": 600,
                     "llm_baseline_tokens": 600, "total_ms": 1800.0})
    rows.append({"ts": last_ts, "solver": "lerf_skill", "route": "lerf_skill", "solved": True,
                 "llm_required": False, "prompt_tokens": 100, "llm_baseline_tokens": 600,
                 "total_ms": 300.0})
    for _ in range(3):
        rows.append({"ts": last_ts, "solver": "llm", "route": "llm", "solved": False,
                     "llm_required": True, "prompt_tokens": 600,
                     "llm_baseline_tokens": 600, "total_ms": 1800.0})
    store.mkdir(parents=True, exist_ok=True)
    with open(store / f"{name}.lerf_routes.jsonl", "w", encoding="utf-8") as fh:
        for r in rows:
            fh.write(json.dumps(r) + "\n")


def _synthetic_reality(name: str, store: Path, now: datetime, period_days: int) -> None:
    """A SYNTHETIC reality ledger of RESOLVED learnings: this period 3 of 4 correct (acc 0.75),
    last period 1 of 4 correct (acc 0.25) — a clear accuracy improvement to trend. Each carries
    resolved_at so the period split lands deterministically."""
    this_ts = _iso(now - timedelta(days=1))
    last_ts = _iso(now - timedelta(days=period_days + 1))
    recs = []

    def learning(correct: bool, conf: float, when: str):
        outcome = 1.0 if correct else 0.0
        return {"kind": "learning", "category": "schedule",
                "prediction_id": f"p{len(recs)}", "prediction_correct": correct,
                "predicted_confidence": conf, "actual_outcome": outcome,
                "surprise": abs(outcome - conf), "resolved_at": when}
    # this: 3 correct, 1 wrong
    for c in (True, True, True, False):
        recs.append(learning(c, 0.7, this_ts))
    # last: 1 correct, 3 wrong
    for c in (True, False, False, False):
        recs.append(learning(c, 0.7, last_ts))
    store.mkdir(parents=True, exist_ok=True)
    with open(store / f"{name}.reality.jsonl", "w", encoding="utf-8") as fh:
        for r in recs:
            fh.write(json.dumps(r) + "\n")


def _selftest() -> int:
    import tempfile
    import shutil

    fails: list = []

    def ok(label: str, cond: bool) -> None:
        print(("  ok   " if cond else "  FAIL ") + label)
        if not cond:
            fails.append(label)

    print("growth_dashboard self-test")

    # --- pure period/bucket arithmetic (no store) --------------------------------------
    now = datetime(2026, 6, 6, 12, 0, 0, tzinfo=timezone.utc)
    ok("bucket: 2 days ago -> 'this'", _bucket(now - timedelta(days=2), now, 7) == "this")
    ok("bucket: 9 days ago -> 'last'", _bucket(now - timedelta(days=9), now, 7) == "last")
    ok("bucket: 20 days ago -> 'older'", _bucket(now - timedelta(days=20), now, 7) == "older")
    ok("bucket: no timestamp -> 'none'", _bucket(None, now, 7) == "none")
    ok("parse: trailing-Z ISO parses", _parse_ts("2026-06-05T23:34:24Z") is not None)
    ok("parse: +00:00 ISO parses", _parse_ts("2026-06-05T23:34:24+00:00") is not None)
    ok("parse: garbage -> None", _parse_ts("not-a-time") is None)
    ok("extract_iso: pulls stamp from a support marker",
       _extract_iso("activated:ratio=4.0x>=min2.0:2026-06-05T23:34:24+00:00") is not None)

    # --- delta semantics ----------------------------------------------------------------
    d_up = _delta(5, 3)
    ok("delta: 5 vs 3 -> +2, defined", d_up["delta"] == 2 and d_up["defined"] is True)
    d_base = _delta(5, None)
    ok("delta: 5 vs None -> baseline/accruing (no fabricated trend)",
       d_base["defined"] is False and "baseline" in d_base["label"])
    d_down = _delta(0.25, 0.75)
    ok("delta: 0.25 vs 0.75 -> -0.5, defined", d_down["delta"] == -0.5 and d_down["defined"])
    ok("arrow: a rise where lower-is-better reads 'watch'",
       "watch" in _arrow(_delta(5, 3), lower_better=True))
    ok("arrow: undefined delta renders '—'", _arrow(_delta(1, None)) == "—")

    # --- FULLY HERMETIC store block -----------------------------------------------------
    real = lerf.STORE if Path(lerf.STORE).is_absolute() else (Path.cwd() / Path(lerf.STORE))
    fp_before = _footprint(real)

    td = tempfile.mkdtemp(prefix="growth-self-")
    tp = Path(td)
    cname = "GrowthSynth"          # a SYNTHETIC creature; never Vera / default
    period = 7

    # Redirect EVERY store binding the dashboard's reads might touch: lerf (objects), reality
    # (ledger), this module's STORE (route ledger), lerf_utilization.STORE (its own reader), and
    # the personal load path's stores (memory_lirf/portrait) so personal_profile reads the temp.
    saved: list = []

    def _set_mod(mod, attr, val):
        if mod is None:
            return
        saved.append((mod, attr, getattr(mod, attr, None)))
        setattr(mod, attr, val)

    def _set(modpath, attr, val):
        try:
            mod = __import__(modpath, fromlist=["_"])
        except Exception:
            return
        _set_mod(mod, attr, val)

    # IMPORTANT: when this file is run as a script, the executing code lives in the '__main__'
    # module, NOT in the imported 'scripts.growth_dashboard' object. The dashboard's own STORE
    # (the route-ledger reader) is read from the RUNNING module, so we must redirect THIS module
    # by its real name in sys.modules — and also the package-path binding for the -m / pytest case.
    _set_mod(sys.modules[__name__], "STORE", tp)
    if sys.modules.get(__name__) is not sys.modules.get("scripts.growth_dashboard"):
        _set("scripts.growth_dashboard", "STORE", tp)

    _set("anima.lerf", "STORE", tp)
    _set("anima.reality", "STORE", tp)
    _set("scripts.lerf_utilization", "STORE", tp)
    # personal reads facts/portrait — redirect those too so personal_profile is hermetic.
    for mp in ("anima.memory_lirf", "anima.portrait", "anima.constitution"):
        _set(mp, "STORE", tp)
    _set("anima.reliability", "DEFAULT_STORE", tp)

    try:
        # build the synthetic two-week history on the temp store
        _synthetic_store(cname, tp, now, period)
        _synthetic_routes(cname, tp, now, period)
        _synthetic_reality(cname, tp, now, period)

        # the accumulation reader on the known population --------------------------------
        acc = accumulation(cname, now, period)
        ok("accumulation: population_total == 8 (the synthetic objects)",
           acc["population_total"] == 8)
        ok("accumulation: 5 objects ADDED this period", acc["added"]["this"] == 5)
        ok("accumulation: 3 objects ADDED last period", acc["added"]["last"] == 3)
        ok("accumulation: by-type this has 3 skills",
           acc["added"]["by_type_this"].get("skill") == 3)
        ok("accumulation: 2 PROMOTED this period (s_this1, s_this2)",
           acc["promoted"]["this"] == 2)
        ok("accumulation: 1 PROMOTED last period (s_last1)", acc["promoted"]["last"] == 1)
        ok("accumulation: 1 RETIRED this period (s_last2_retired)",
           acc["retired"]["this"] == 1)
        ok("accumulation: 0 RETIRED last period", acc["retired"]["last"] == 0)
        ok("accumulation: NET this = added5 - retired1 = 4", acc["net"]["this"] == 4)
        ok("accumulation: NET last = added3 - retired0 = 3", acc["net"]["last"] == 3)

        # utilization split ---------------------------------------------------------------
        util = utilization(cname, now, period)
        ok("utilization: has a period split (rows are stamped)", util["has_period_split"])
        ok("utilization: this period rate is 50.0% (4 of 8 LERF-solved)",
           util["this"]["lerf_utilization_rate"] == 50.0)
        ok("utilization: last period rate is 25.0% (1 of 4 LERF-solved)",
           util["last"]["lerf_utilization_rate"] == 25.0)

        # calibration split ---------------------------------------------------------------
        cal = calibration(cname, now, period)
        ok("calibration: available", cal.get("available") is True)
        ok("calibration: this-period accuracy 0.75 (3 of 4 correct)",
           cal["this"]["accuracy"] == 0.75)
        ok("calibration: last-period accuracy 0.25 (1 of 4 correct)",
           cal["last"]["accuracy"] == 0.25)
        ok("calibration: overall resolved == 8", cal["overall"]["resolved"] == 8)

        # personal growth -----------------------------------------------------------------
        pers = personal_growth(cname, "Lamar", now, period)
        ok("personal: available", pers.get("available") is True)
        ok("personal: 1 personal object added this period (decision_pattern)",
           pers["added_this"] == 1)
        ok("personal: 1 personal object added last period (preference)",
           pers["added_last"] == 1)

        # the assembled dashboard + its deltas (the compounding signal) -------------------
        dash = build(cname, person="Lamar", period_days=period, now=now)
        de = dash["deltas"]
        ok("delta: objects_added +2 (5 this vs 3 last), defined",
           de["objects_added"]["delta"] == 2 and de["objects_added"]["defined"])
        ok("delta: net_accumulation +1 (4 vs 3), defined",
           de["net_accumulation"]["delta"] == 1 and de["net_accumulation"]["defined"])
        ok("delta: promoted +1 (2 vs 1)", de["objects_promoted"]["delta"] == 1)
        ok("delta: retired +1 (1 vs 0) and flagged 'watch' (more retirement)",
           de["objects_retired"]["delta"] == 1
           and "watch" in _arrow(de["objects_retired"], lower_better=True))
        ok("delta: LERF utilization +25.0 pts (50% vs 25%)",
           de["lerf_utilization_rate"]["delta"] == 25.0
           and de["lerf_utilization_rate"]["defined"])
        ok("delta: reality accuracy +0.5 (0.75 vs 0.25), defined",
           de["reality_accuracy"]["delta"] == 0.5 and de["reality_accuracy"]["defined"])
        ok("delta: personal intel +0 (1 vs 1), defined as flat",
           de["personal_intelligence"]["delta"] == 0
           and de["personal_intelligence"]["defined"])

        # the renderer emits the headline + every section without raising -----------------
        txt = render(dash)
        ok("render: HEADLINE ACCUMULATION present",
           "HEADLINE" in txt and "ACCUMULATION" in txt)
        ok("render: week-over-week summary present", "WEEK-OVER-WEEK SUMMARY" in txt)
        ok("render: LERF utilization section present", "LERF UTILIZATION RATE" in txt)
        ok("render: reality calibration section present", "REALITY CALIBRATION" in txt)
        ok("render: personal-intelligence section present", "PERSONAL INTELLIGENCE GROWTH" in txt)

        # BASELINE honesty: a creature with ONLY this-period data shows 'baseline / accruing'
        # for the prior period, never a fabricated trend. Build a one-week-only synthetic store.
        bname = "GrowthBaseline"
        bobjs = [{"id": "b1", "type": "skill", "name": "b1", "domain": "general",
                  "state": lerf.ACTIVE, "confidence": 0.8,
                  "last_verified": _iso(now - timedelta(days=1)), "source": "synthetic",
                  "support": [f"taught_at:{_iso(now - timedelta(days=1))}"],
                  "failure_modes": [], "inputs": [], "steps": ["x"], "outputs": []}]
        (tp / f"{bname}.lerf.json").write_text(
            json.dumps({"version": 1, "objects": bobjs}), encoding="utf-8")
        bdash = build(bname, person="Lamar", period_days=period, now=now)
        ok("baseline: 1 added this, 0 last -> delta marked baseline (no faked trend)",
           bdash["deltas"]["objects_added"]["defined"] is False
           and "baseline" in bdash["deltas"]["objects_added"]["label"])

        # density is hermetic by construction (intelligence_per_gb measures on its OWN temp
        # stores + asserts hermetic_ok); confirm it returns and reports hermetic.
        dens = density(want_live=False)
        ok("density: economics read available + reports hermetic_ok",
           dens.get("available") and dens.get("hermetic_ok") is True)
        ok("density: learning-per-MB is a number", isinstance(dens.get("learning_per_mb"),
                                                              (int, float)))

    finally:
        for mod, attr, old in saved:
            setattr(mod, attr, old)
        shutil.rmtree(td, ignore_errors=True)

    fp_after = _footprint(real)
    ok("HERMETIC: real .anima is byte-UNCHANGED (no store touched, no leak)",
       fp_before == fp_after)
    ok("HERMETIC: every redirected store binding restored",
       all(getattr(m, a, None) is o for (m, a, o) in saved))

    print()
    if fails:
        print(f"{len(fails)} FAILED: " + ", ".join(fails))
        return 1
    print("ALL GROWTH_DASHBOARD SELFTESTS PASS")
    return 0


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(
        description="Growth Dashboard — how much did the mind ACCUMULATE this week?")
    ap.add_argument("--name", default="default",
                    help="creature/ledger name (default: 'default')")
    ap.add_argument("--person", default="Lamar",
                    help="who personal-intelligence is ABOUT (the user). Default: 'Lamar'")
    ap.add_argument("--period-days", type=int, default=7,
                    help="period bucket width in days (default: 7 = a week)")
    ap.add_argument("--live", action="store_true",
                    help="drive the local model for the density measurement (slower; off by default)")
    ap.add_argument("--json", action="store_true", help="emit the dashboard as JSON")
    ap.add_argument("--selftest", action="store_true",
                    help="run the hermetic selftest on a SYNTHETIC growth history (no real data)")
    args = ap.parse_args(argv)

    if args.selftest:
        return _selftest()

    dash = build(args.name, person=args.person, period_days=args.period_days,
                 want_live=args.live)
    if args.json:
        print(json.dumps(dash, indent=2, default=str))
    else:
        print(render(dash))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

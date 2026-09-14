"""whole_mri_shape — Phase 6 (combined SHAPE) + Phase 7 (TUNING) of the Whole-System MRI.

This is a PURE analysis library that sits *on top of* the certified producer
(`anima.whole_mri`).  It NEVER writes `.anima`; the only I/O it ever performs is
through the producer's read API (`whole_mri.all/last/by_turn_id`) — and even that
happens in the CLI (`scripts/whole_mri_tune.py`), not here.  Every public function
in this module takes plain trace dicts and returns plain dicts/lists.

What it answers (from docs/whole_mri_contract.md §"Shape (Phase 6) + Tuning (Phase 7)"):
  Phase 6 — what SHAPE is this turn?   (expensive / unsafe / slow / host-heavy / low-quality)
  Phase 7 — what should we DO about it? (route→LERF · reduce retrieval · cache an Argus call ·
            avoid the LLM · improve source labels · strengthen the final gate · fix completeness ·
            investigate host contention)

Robustness contract (matches the producer's "any field may be None"):
  * Every accessor tolerates a missing block, a non-dict block, or a None value.
  * A dimension whose inputs are entirely absent is reported as an HONEST None — never 0.0,
    never fabricated.  Downstream (normalization, classification) treats None as "unknown"
    and simply does not count it.

--------------------------------------------------------------------------------
THE SEVEN SHAPE DIMENSIONS  (shape_of)
--------------------------------------------------------------------------------
Each is a RAW magnitude (not yet normalized — see shapes_over for the batch-relative
0..1 view).  Higher always means "more of that thing".  None = no inputs present.

  cognitive_load   memory_reads + lerf_objects_used + tokens_out
                   (how much thinking/retrieval/generation this turn took).
  host_load        |cpu_delta| + |memory_delta_mb| + |disk_io_delta| + |network_delta|
                   + L1(shape_delta values).  None when there is NO host window at all.
  latency          cost.latency_ms (raw milliseconds).
  quality          composite in [0,1]: mean of the booleans grounded/complete/
                   source_labeled/host_labeled plus confidence, over whichever are present.
                   (Higher = better quality.)
  resource_cost    tokens_in + tokens_out + argus_calls + memory_writes.
  safety_risk      count of TRIPPED safety flags / 5, in [0,1]:
                     final_gate_passed == False, response_complete == False,
                     identity_mutation == True, host_action_taken == True,
                     memory_contamination == True.
  confidence       quality.confidence (raw, expected 0..1).

`shape_of(trace)` returns {dim: float|None, "_raw": {...debug...}}.

--------------------------------------------------------------------------------
BATCH-RELATIVE NORMALIZATION  (shapes_over)
--------------------------------------------------------------------------------
Absolute scales vary wildly (120 ms vs 9 000 ms; 30 tokens vs 4 000).  To compare
turns fairly we min-max normalize EACH dimension across the SET of traces:

      norm = (raw - min) / (max - min)          # within the batch, per dimension

Only non-None raw values participate in the min/max.  If a dimension is constant
across the batch (max == min) every present value normalizes to 0.0 (no spread →
nothing stands out).  None stays None.  `quality`, `confidence`, and `safety_risk`
are ALREADY in [0,1] and are passed through unchanged (their absolute level is the
signal — a 0.2 quality is bad regardless of the batch), but their batch min/max are
still published in batch_stats so classifiers can use quartiles if they wish.

`shapes_over(traces)` returns a list aligned 1:1 with the input, each element:
  {turn_id, route, input_kind, raw{...}, norm{...}}
and the helper `batch_statistics(traces)` returns the per-dimension
{min,max,p25,p50,p75,n} used by the classifier's quartile thresholds.

--------------------------------------------------------------------------------
CLASSIFICATION  (classify_shape)
--------------------------------------------------------------------------------
Labels (zero or more) from: expensive · unsafe · slow · host-heavy · low-quality.
Thresholds are batch-relative where scale is arbitrary, absolute where it is not:

  slow         latency      in the batch's TOP QUARTILE (>= p75) AND a real value.
  expensive    resource_cost in the batch's TOP QUARTILE (>= p75).
  host-heavy   host_load    in the batch's TOP QUARTILE (>= p75) AND a host window existed.
  unsafe       ANY safety flag tripped (safety_risk > 0).  (Absolute — one flag is enough.)
  low-quality  quality present AND quality < LOW_QUALITY_CUTOFF (default 0.5).  (Absolute.)

A degenerate batch (n<4, or only one distinct value) has no meaningful quartiles; in
that case the scale-relative labels (slow/expensive/host-heavy) fall back to absolute
floors (see _ABS_FLOORS) so a single obviously-bad turn is still caught, while the
absolute labels (unsafe/low-quality) are unaffected.

--------------------------------------------------------------------------------
WORK ORDERS  (work_orders) — Phase 7
--------------------------------------------------------------------------------
For each turn whose evidence warrants it, emit one or more work orders following the
house "issue → what it means → what to do" style.  Each order:
  {turn_id, shape (the labels), issue, what_it_means, suggested_action, evidence{...}}

shape/trigger → suggested_action mapping (all actions drawn from the contract vocab):
  slow & route==llm on a simple turn      → "Route this shape to LERF / reduce retrieval."
  expensive & high argus_calls            → "Cache an Argus call (reuse one /mri snapshot)."
  route==llm but memory/LERF/Argus could
      have answered                        → "Avoid the LLM for this shape."
  quality.source_labeled False w/ sources  → "Improve source labels."
  final_gate_passed False OR gate stripped → "Strengthen the final gate."
  response_complete False                  → "Fix completeness (the reply was too thin)."
  host-heavy                               → "Investigate host contention during this turn shape."

Nothing is fabricated: an order is emitted only when the trace numbers support it.
Recurring identical shapes are additionally summarized by `summarize_work_orders`.
"""

from __future__ import annotations

from typing import Any, Optional

# ---------------------------------------------------------------------------
# Tunable thresholds (documented above; kept as module constants so the CLI and
# the selftest reference the SAME numbers).
# ---------------------------------------------------------------------------

LOW_QUALITY_CUTOFF = 0.5          # quality strictly below this → low-quality
TOP_QUARTILE = 0.75               # p75 cut for slow / expensive / host-heavy
SIMPLE_TURN_TOKENS_OUT = 600      # tokens_out <= this counts as a "simple" turn
HIGH_ARGUS_CALLS = 2              # argus_calls >= this is "high" (≥2 ⇒ a cache could help)

# Absolute fallback floors used only when the batch is too small/degenerate for
# meaningful quartiles.  Deliberately conservative so we don't over-fire.
_ABS_FLOORS = {
    "latency": 3000.0,            # ms — a turn over ~3s is slow on its face
    "resource_cost": 2000.0,      # tokens+calls+writes — expensive on its face
    "host_load": 5.0,             # summed |deltas| + L1(shape) — notable host churn
}

# The seven dimensions, in display order.
DIMENSIONS = (
    "cognitive_load",
    "host_load",
    "latency",
    "quality",
    "resource_cost",
    "safety_risk",
    "confidence",
)

# Dimensions already in [0,1] — passed through normalization unchanged.
_ALREADY_UNIT = frozenset({"quality", "safety_risk", "confidence"})


# ---------------------------------------------------------------------------
# Safe accessors — never raise, always honest about absence.
# ---------------------------------------------------------------------------

def _block(trace: Any, key: str) -> dict:
    """Return trace[key] as a dict, or {} for any missing / non-dict block."""
    if not isinstance(trace, dict):
        return {}
    b = trace.get(key)
    return b if isinstance(b, dict) else {}


def _num(v: Any) -> Optional[float]:
    """Coerce to float, or None.  bool is intentionally rejected (True is not 1.0
    here — booleans are handled explicitly where they matter)."""
    if v is None or isinstance(v, bool):
        return None
    try:
        f = float(v)
    except (TypeError, ValueError):
        return None
    # Guard against NaN/inf sneaking in — treat as absent.
    if f != f or f in (float("inf"), float("-inf")):
        return None
    return f


def _sum_present(*vals: Any) -> Optional[float]:
    """Sum the numeric values that are present.  Returns None iff NONE present
    (honest absence), else the sum of whatever was there."""
    present = [n for n in (_num(v) for v in vals) if n is not None]
    if not present:
        return None
    return float(sum(present))


def _as_bool(v: Any) -> Optional[bool]:
    """Strict tri-state: True/False if it's genuinely a bool, else None.  We do
    NOT coerce truthy ints/strings — a safety/quality flag must be an explicit
    bool to count, otherwise it's 'unknown'."""
    if isinstance(v, bool):
        return v
    return None


# ---------------------------------------------------------------------------
# Phase 6 — shape_of (raw per-turn magnitudes)
# ---------------------------------------------------------------------------

def _quality_composite(quality: dict) -> Optional[float]:
    """Mean over whichever of {grounded, complete, source_labeled, host_labeled}
    are explicit bools (True→1, False→0) plus confidence if numeric.  None if the
    whole quality block is empty/absent."""
    parts: list[float] = []
    for k in ("grounded", "complete", "source_labeled", "host_labeled"):
        b = _as_bool(quality.get(k))
        if b is not None:
            parts.append(1.0 if b else 0.0)
    conf = _num(quality.get("confidence"))
    if conf is not None:
        # clamp confidence into [0,1] defensively
        parts.append(max(0.0, min(1.0, conf)))
    if not parts:
        return None
    return sum(parts) / len(parts)


def _safety_risk(safety: dict) -> Optional[float]:
    """Fraction of the 5 safety flags that are TRIPPED, in [0,1].

    Tripped means: final_gate_passed False, response_complete False,
    identity_mutation True, host_action_taken True, memory_contamination True.
    A flag that is absent / not a bool is 'unknown' and does NOT count as tripped
    (we never invent risk).  None only if the entire safety block is empty."""
    if not safety:
        return None
    tripped = 0
    considered = 0
    # "False is bad" flags
    for k in ("final_gate_passed", "response_complete"):
        b = _as_bool(safety.get(k))
        if b is not None:
            considered += 1
            if b is False:
                tripped += 1
    # "True is bad" flags
    for k in ("identity_mutation", "host_action_taken", "memory_contamination"):
        b = _as_bool(safety.get(k))
        if b is not None:
            considered += 1
            if b is True:
                tripped += 1
    if considered == 0:
        return None
    # Normalized over the full set of 5 (the contract's "normalized" intent): the
    # severity of a turn is "how many of the five tripwires fired", so we divide by 5.
    return tripped / 5.0


def _host_load(cost: dict, argus: dict) -> Optional[float]:
    """Magnitude of host change: |cpu|+|mem|+|disk|+|net| (from cost.* deltas)
    + L1 of the shape_delta z-score vector (from argus.shape_delta).

    Returns None when there is NO host window at all — i.e. no delta fields AND
    no shape_delta.  Present-but-zero (a real, quiet host window) returns 0.0."""
    have_window = False
    total = 0.0

    for k in ("cpu_delta", "memory_delta_mb", "disk_io_delta", "network_delta"):
        n = _num(cost.get(k))
        if n is not None:
            have_window = True
            total += abs(n)

    sd = argus.get("shape_delta")
    if isinstance(sd, dict):
        for v in sd.values():
            n = _num(v)
            if n is not None:
                have_window = True
                total += abs(n)

    return total if have_window else None


def _has_host_window(trace: Any) -> bool:
    """True iff this trace carries an actual host window (enabled + some host data),
    used to gate the host-heavy label.  Tolerant of the 'unavailable' record."""
    argus = _block(trace, "argus")
    cost = _block(trace, "cost")
    if argus.get("enabled") is not True:
        # If not explicitly enabled, only count it when host deltas are actually present.
        pass
    # A window exists if any host delta or shape_delta is present.
    if isinstance(argus.get("shape_delta"), dict) and argus["shape_delta"]:
        return True
    for k in ("cpu_delta", "memory_delta_mb", "disk_io_delta", "network_delta"):
        if _num(cost.get(k)) is not None:
            return True
    # host_before/during/after present and not the unavailable sentinel
    for k in ("host_before", "host_during", "host_after"):
        hb = argus.get(k)
        if isinstance(hb, dict) and not hb.get("unavailable"):
            return True
    return False


def shape_of(trace: dict) -> dict:
    """Compute the seven RAW shape dimensions for a single trace dict.

    Returns a dict with one key per dimension (float OR honest None) plus a
    ``_raw`` debug sub-dict echoing the underlying numbers.  Never raises; any
    missing/None field degrades to None for that dimension.

    See the module docstring for the precise definition of each dimension.
    """
    vera_cost = _block(trace, "cost")          # cost block holds the deltas + counts
    quality = _block(trace, "quality")
    safety = _block(trace, "safety")
    argus = _block(trace, "argus")

    cognitive_load = _sum_present(
        vera_cost.get("memory_reads"),
        vera_cost.get("lerf_objects_used"),
        vera_cost.get("tokens_out"),
    )

    host_load = _host_load(vera_cost, argus)

    latency = _num(vera_cost.get("latency_ms"))

    quality_score = _quality_composite(quality)

    resource_cost = _sum_present(
        vera_cost.get("tokens_in"),
        vera_cost.get("tokens_out"),
        vera_cost.get("argus_calls"),
        vera_cost.get("memory_writes"),
    )

    safety_risk = _safety_risk(safety)

    confidence = _num(quality.get("confidence"))
    if confidence is not None:
        confidence = max(0.0, min(1.0, confidence))

    return {
        "cognitive_load": cognitive_load,
        "host_load": host_load,
        "latency": latency,
        "quality": quality_score,
        "resource_cost": resource_cost,
        "safety_risk": safety_risk,
        "confidence": confidence,
        "_raw": {
            "memory_reads": _num(vera_cost.get("memory_reads")),
            "lerf_objects_used": _num(vera_cost.get("lerf_objects_used")),
            "tokens_in": _num(vera_cost.get("tokens_in")),
            "tokens_out": _num(vera_cost.get("tokens_out")),
            "argus_calls": _num(vera_cost.get("argus_calls")),
            "memory_writes": _num(vera_cost.get("memory_writes")),
            "cpu_delta": _num(vera_cost.get("cpu_delta")),
            "memory_delta_mb": _num(vera_cost.get("memory_delta_mb")),
            "disk_io_delta": _num(vera_cost.get("disk_io_delta")),
            "network_delta": _num(vera_cost.get("network_delta")),
            "has_host_window": _has_host_window(trace),
        },
    }


# ---------------------------------------------------------------------------
# Phase 6 — batch normalization
# ---------------------------------------------------------------------------

def _percentile(sorted_vals: list[float], q: float) -> Optional[float]:
    """Linear-interpolation percentile of a NON-empty sorted list, q in [0,1].
    Mirrors numpy's default 'linear' method so behavior is unsurprising."""
    if not sorted_vals:
        return None
    if len(sorted_vals) == 1:
        return sorted_vals[0]
    pos = q * (len(sorted_vals) - 1)
    lo = int(pos)
    hi = min(lo + 1, len(sorted_vals) - 1)
    frac = pos - lo
    return sorted_vals[lo] + (sorted_vals[hi] - sorted_vals[lo]) * frac


def batch_statistics(traces: list[dict]) -> dict:
    """Per-dimension {min,max,p25,p50,p75,n} over the batch's PRESENT raw values.

    A dimension with no present values across the batch has n==0 and None stats.
    Used by classify_shape for the top-quartile thresholds."""
    shapes = [shape_of(t) for t in (traces or [])]
    stats: dict[str, dict] = {}
    for dim in DIMENSIONS:
        vals = sorted(s[dim] for s in shapes if s.get(dim) is not None)
        if not vals:
            stats[dim] = {"min": None, "max": None, "p25": None,
                          "p50": None, "p75": None, "n": 0}
            continue
        stats[dim] = {
            "min": vals[0],
            "max": vals[-1],
            "p25": _percentile(vals, 0.25),
            "p50": _percentile(vals, 0.50),
            "p75": _percentile(vals, TOP_QUARTILE),
            "n": len(vals),
        }
    return stats


def _minmax_norm(raw: Optional[float], lo: Optional[float], hi: Optional[float]) -> Optional[float]:
    """Min-max normalize raw into [0,1] given batch lo/hi.  None raw → None.
    Degenerate (hi==lo) → 0.0 for any present value (no spread → nothing stands out)."""
    if raw is None:
        return None
    if lo is None or hi is None:
        return None
    if hi <= lo:
        return 0.0
    return max(0.0, min(1.0, (raw - lo) / (hi - lo)))


def shapes_over(traces: list[dict]) -> list[dict]:
    """Compute per-dimension batch-relative normalization across the SET.

    Returns a list aligned 1:1 with ``traces``.  Each element:
        {turn_id, route, input_kind, raw{dim:..}, norm{dim:..}}

    Method: min-max within the batch per dimension (see module docstring).
    Dimensions already in [0,1] (quality/safety_risk/confidence) are passed
    through unchanged so their absolute level remains the signal; the others
    are stretched to the batch's observed range so turns become comparable.
    """
    traces = traces or []
    stats = batch_statistics(traces)
    out: list[dict] = []
    for t in traces:
        s = shape_of(t)
        norm: dict[str, Optional[float]] = {}
        for dim in DIMENSIONS:
            raw = s.get(dim)
            if dim in _ALREADY_UNIT:
                # Already a 0..1 quantity — keep as-is (clamp defensively).
                norm[dim] = None if raw is None else max(0.0, min(1.0, raw))
            else:
                norm[dim] = _minmax_norm(raw, stats[dim]["min"], stats[dim]["max"])
        out.append({
            "turn_id": t.get("turn_id") if isinstance(t, dict) else None,
            "route": (t.get("route") if isinstance(t, dict) else None),
            "input_kind": (t.get("input_kind") if isinstance(t, dict) else None),
            "raw": {k: s[k] for k in DIMENSIONS},
            "norm": norm,
        })
    return out


# ---------------------------------------------------------------------------
# Phase 6 — classify_shape
# ---------------------------------------------------------------------------

def _top_quartile_hit(raw: Optional[float], dim: str, stats: dict) -> bool:
    """True iff raw is a present value at/above the batch p75 for ``dim``.

    For a degenerate batch (too few points, or no spread) we fall back to the
    absolute floor in _ABS_FLOORS so an obviously-bad single turn is still caught."""
    if raw is None:
        return False
    st = stats.get(dim) or {}
    n = st.get("n") or 0
    p75 = st.get("p75")
    mn, mx = st.get("min"), st.get("max")
    meaningful = (n >= 4) and (mn is not None) and (mx is not None) and (mx > mn)
    if meaningful and p75 is not None:
        return raw >= p75
    # Degenerate batch → absolute floor (only for the scale-relative dims).
    floor = _ABS_FLOORS.get(dim)
    if floor is None:
        return False
    return raw >= floor


def classify_shape(trace: dict, batch_stats: dict) -> list[str]:
    """Return the zero-or-more shape labels for ``trace`` given ``batch_stats``
    (from batch_statistics).  Labels: expensive · unsafe · slow · host-heavy ·
    low-quality.  See the module docstring for thresholds.

    ``batch_stats`` is passed in (not recomputed) so a caller classifying many
    turns computes the batch once.  Tolerant of an empty/garbage batch_stats."""
    if not isinstance(batch_stats, dict):
        batch_stats = {}
    s = shape_of(trace)
    labels: list[str] = []

    # slow — latency in the top quartile (batch-relative; absolute floor fallback)
    if _top_quartile_hit(s.get("latency"), "latency", batch_stats):
        labels.append("slow")

    # expensive — resource_cost in the top quartile
    if _top_quartile_hit(s.get("resource_cost"), "resource_cost", batch_stats):
        labels.append("expensive")

    # host-heavy — host_load top quartile AND a real host window existed
    if s["_raw"].get("has_host_window") and _top_quartile_hit(
        s.get("host_load"), "host_load", batch_stats
    ):
        labels.append("host-heavy")

    # unsafe — ANY safety flag tripped (absolute: one is enough)
    sr = s.get("safety_risk")
    if sr is not None and sr > 0:
        labels.append("unsafe")

    # low-quality — quality present and below the absolute cutoff
    q = s.get("quality")
    if q is not None and q < LOW_QUALITY_CUTOFF:
        labels.append("low-quality")

    return labels


# ---------------------------------------------------------------------------
# Phase 7 — work_orders
# ---------------------------------------------------------------------------

def _short(turn_id: Any) -> str:
    """A compact, human-friendly turn id for messages."""
    if not turn_id:
        return "<no-turn_id>"
    s = str(turn_id)
    # turn_2026_06_06_165512_abc123 → 165512_abc123
    parts = s.split("_")
    if len(parts) >= 6 and parts[0] == "turn":
        return "_".join(parts[-2:])
    return s[-13:] if len(s) > 13 else s


def _is_simple_turn(s: dict) -> bool:
    """Heuristic 'this was a simple turn that didn't need the LLM': modest output
    and little/no retrieval.  Used to justify the route→LERF order."""
    raw = s.get("_raw", {})
    tout = raw.get("tokens_out")
    reads = raw.get("memory_reads")
    lerf = raw.get("lerf_objects_used")
    # Simple if output is small (or unknown) and retrieval was light.
    small_out = (tout is None) or (tout <= SIMPLE_TURN_TOKENS_OUT)
    light_retr = ((reads is None) or (reads <= 3)) and ((lerf is None) or (lerf <= 3))
    return small_out and light_retr


def _gate_stripped_text(trace: dict) -> bool:
    """Did the final gate strip/alter the response text?  We look at vera.final_gate
    for a stripped/modified marker, tolerant of whatever shape the producer used."""
    fg = _block(trace, "vera").get("final_gate")
    if isinstance(fg, dict):
        for k in ("stripped", "modified", "altered", "redactions", "removed"):
            v = fg.get(k)
            if isinstance(v, bool) and v:
                return True
            n = _num(v)
            if n is not None and n > 0:
                return True
        # Some gates record passed=False inside vera.final_gate too.
        if fg.get("passed") is False:
            return True
    return False


def _sources_were_available(trace: dict) -> bool:
    """Were sources actually available to label?  True if the route/used a source
    or LERF object, or vera.capture/world note sources, etc.  Conservative: we only
    claim availability when there's positive evidence so we don't fabricate the order."""
    route = (trace.get("route") if isinstance(trace, dict) else None)
    if route in ("source", "lerf", "hybrid"):
        return True
    cost = _block(trace, "cost")
    lerf = _num(cost.get("lerf_objects_used"))
    if lerf is not None and lerf > 0:
        return True
    vera = _block(trace, "vera")
    for k in ("lerf", "world_model", "reality_learning", "capture"):
        v = vera.get(k)
        if isinstance(v, dict) and (v.get("sources") or v.get("source") or v.get("objects")):
            return True
    return False


def _memory_or_capability_could_answer(trace: dict, s: dict) -> bool:
    """Evidence that memory / LERF / an Argus capability could have answered, yet the
    route was llm.  Positive signals only (so we never invent the order)."""
    cost = _block(trace, "cost")
    reads = _num(cost.get("memory_reads"))
    lerf = _num(cost.get("lerf_objects_used"))
    acalls = _num(cost.get("argus_calls"))
    # If the LLM ran but memory/LERF were actually consulted (reads/objects > 0) or an
    # Argus capability answered, a non-LLM path was plausibly sufficient — especially
    # on a simple turn.
    consulted = ((reads or 0) > 0) or ((lerf or 0) > 0) or ((acalls or 0) > 0)
    return consulted and _is_simple_turn(s)


def _wo(turn_id, shape, issue, what_it_means, suggested_action, evidence) -> dict:
    """Construct one work order with all required keys (the schema the contract names)."""
    return {
        "turn_id": turn_id,
        "shape": list(shape),
        "issue": issue,
        "what_it_means": what_it_means,
        "suggested_action": suggested_action,
        "evidence": evidence,
    }


def work_orders_for(trace: dict, batch_stats: dict) -> list[dict]:
    """Emit zero-or-more work orders for a SINGLE trace, given the batch stats.

    Only emits an order when the trace's own numbers support it (never fabricated).
    Each order carries: turn_id, shape, issue, what_it_means, suggested_action, evidence.
    """
    if not isinstance(trace, dict):
        return []
    s = shape_of(trace)
    raw = s.get("_raw", {})
    labels = classify_shape(trace, batch_stats)
    route = trace.get("route")
    tid = trace.get("turn_id")
    orders: list[dict] = []

    # --- 1. slow + route==llm on a simple turn → route to LERF / reduce retrieval ---
    if "slow" in labels and route == "llm" and _is_simple_turn(s):
        orders.append(_wo(
            tid, labels,
            issue="This turn was slow and went to the LLM even though it looks simple.",
            what_it_means=(
                "A small, low-retrieval answer took a top-quartile amount of time because "
                "it was routed through the language model instead of a cheaper path."
            ),
            suggested_action="Route this shape to LERF / reduce retrieval.",
            evidence={
                "latency_ms": raw_get(trace, "cost", "latency_ms"),
                "route": route,
                "tokens_out": raw.get("tokens_out"),
                "memory_reads": raw.get("memory_reads"),
                "lerf_objects_used": raw.get("lerf_objects_used"),
            },
        ))

    # --- 2. expensive + high argus_calls → cache an Argus call ---
    acalls = raw.get("argus_calls")
    if "expensive" in labels and acalls is not None and acalls >= HIGH_ARGUS_CALLS:
        orders.append(_wo(
            tid, labels,
            issue="This turn was expensive and made several Argus calls.",
            what_it_means=(
                f"It asked Argus {int(acalls)} times in one turn; the host barely changes "
                "between calls, so most of those snapshots are redundant cost."
            ),
            suggested_action="Cache an Argus call (reuse one /mri snapshot).",
            evidence={
                "argus_calls": acalls,
                "resource_cost": s.get("resource_cost"),
                "tokens_in": raw.get("tokens_in"),
                "tokens_out": raw.get("tokens_out"),
            },
        ))

    # --- 3. route==llm but memory/LERF/capability could have answered → avoid the LLM ---
    if route == "llm" and _memory_or_capability_could_answer(trace, s):
        # Avoid duplicating the (1) order's intent when it already fired; this one is
        # about *avoiding the model entirely*, which is broader than "reduce retrieval".
        already = any(o["suggested_action"].startswith("Route this shape to LERF") for o in orders)
        if not already:
            orders.append(_wo(
                tid, labels or ["llm-avoidable"],
                issue="The LLM ran, but memory or a capability had already produced the answer.",
                what_it_means=(
                    "Memory/LERF/Argus were consulted and returned material on a simple turn, "
                    "yet the reply still went through the language model — wasted tokens and latency."
                ),
                suggested_action="Avoid the LLM for this shape.",
                evidence={
                    "route": route,
                    "memory_reads": raw.get("memory_reads"),
                    "lerf_objects_used": raw.get("lerf_objects_used"),
                    "argus_calls": raw.get("argus_calls"),
                    "tokens_out": raw.get("tokens_out"),
                },
            ))

    # --- 4. source_labeled False while sources were available → improve source labels ---
    src_labeled = _as_bool(_block(trace, "quality").get("source_labeled"))
    if src_labeled is False and _sources_were_available(trace):
        orders.append(_wo(
            tid, labels,
            issue="The answer used sources but did not label where they came from.",
            what_it_means=(
                "Source-grounded material went into the reply unlabeled, so the user can't see "
                "what's backed by a source versus the model's own words."
            ),
            suggested_action="Improve source labels.",
            evidence={
                "source_labeled": False,
                "route": route,
                "lerf_objects_used": raw.get("lerf_objects_used"),
            },
        ))

    # --- 5. final_gate_passed False OR the gate stripped text → strengthen the final gate ---
    fg_passed = _as_bool(_block(trace, "safety").get("final_gate_passed"))
    gate_stripped = _gate_stripped_text(trace)
    if fg_passed is False or gate_stripped:
        if fg_passed is False:
            issue = "The final output gate did not pass on this turn."
            means = (
                "The last safety gate flagged the candidate reply. Something reached the gate "
                "that should have been caught earlier — the gate is doing its job but late."
            )
        else:
            issue = "The final output gate had to strip or alter the reply before it shipped."
            means = (
                "The gate removed/modified text at the last moment. It held the line, but the "
                "upstream generation produced something it had to repair."
            )
        orders.append(_wo(
            tid, labels or ["unsafe"],
            issue=issue,
            what_it_means=means,
            suggested_action="Strengthen the final gate.",
            evidence={
                "final_gate_passed": fg_passed,
                "gate_stripped": gate_stripped,
                "safety_risk": s.get("safety_risk"),
            },
        ))

    # --- 6. response_complete False → fix completeness ---
    resp_complete = _as_bool(_block(trace, "safety").get("response_complete"))
    if resp_complete is False:
        orders.append(_wo(
            tid, labels or ["incomplete"],
            issue="The shipped reply was incomplete.",
            what_it_means=(
                "Completeness checking marked the response as too thin — it likely stopped short "
                "of fully answering, so the user got a partial reply."
            ),
            suggested_action="Fix completeness (the reply was too thin).",
            evidence={
                "response_complete": False,
                "tokens_out": raw.get("tokens_out"),
                "route": route,
            },
        ))

    # --- 7. host-heavy → investigate host contention ---
    if "host-heavy" in labels:
        orders.append(_wo(
            tid, labels,
            issue="This turn coincided with heavy host activity.",
            what_it_means=(
                "CPU/memory/disk/network on the Mac moved a lot while this turn ran. The turn "
                "may have been slowed by other processes — or may itself be the load."
            ),
            suggested_action="Investigate host contention during this turn shape.",
            evidence={
                "host_load": s.get("host_load"),
                "cpu_delta": raw.get("cpu_delta"),
                "memory_delta_mb": raw.get("memory_delta_mb"),
                "disk_io_delta": raw.get("disk_io_delta"),
                "network_delta": raw.get("network_delta"),
            },
        ))

    return orders


def raw_get(trace: Any, block: str, key: str) -> Any:
    """Tiny helper: trace[block][key] tolerating any missing piece (returns None)."""
    return _block(trace, block).get(key)


def work_orders(traces: list[dict]) -> list[dict]:
    """Phase 7 entry point: analyze a list of traces and return a flat list of
    work orders (each a dict with the required keys).

    Computes the batch statistics ONCE, then emits per-turn orders.  Order is
    stable: input order, then the order rules fire in.  Never raises; a clean,
    cheap turn yields no orders (no false positives)."""
    traces = traces or []
    stats = batch_statistics(traces)
    out: list[dict] = []
    for t in traces:
        out.extend(work_orders_for(t, stats))
    return out


def summarize_work_orders(orders: list[dict]) -> list[dict]:
    """Aggregate duplicate shapes into a summary, per the contract's "aggregate
    duplicates into a summary if the same shape recurs".

    Groups by suggested_action and returns, for each, a count + the turn_ids +
    a representative issue/what_it_means.  Leaves the per-turn ``orders`` intact;
    this is an additional rollup the CLI can print."""
    by_action: dict[str, dict] = {}
    for o in orders or []:
        action = o.get("suggested_action") or "(unspecified)"
        g = by_action.setdefault(action, {
            "suggested_action": action,
            "count": 0,
            "turn_ids": [],
            "issue": o.get("issue"),
            "what_it_means": o.get("what_it_means"),
            "shapes_seen": set(),
        })
        g["count"] += 1
        if o.get("turn_id"):
            g["turn_ids"].append(o["turn_id"])
        for lbl in (o.get("shape") or []):
            g["shapes_seen"].add(lbl)
    # finalize (sets → sorted lists), order by frequency desc
    summary = []
    for g in by_action.values():
        g["shapes_seen"] = sorted(g["shapes_seen"])
        summary.append(g)
    summary.sort(key=lambda x: (-x["count"], x["suggested_action"]))
    return summary

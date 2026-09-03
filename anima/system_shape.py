"""
system_shape — the one-glance honest portrait of what kind of mind Vera is RIGHT NOW.

Phase: "System Shape" (the founder's 10^inf build order, item after the Improvement Engine).

Everything else in the moonshot answers a NARROW question (is THIS feature real? what's THIS
turn's trace?). This composes those answers into ONE honest profile across a few axes a founder
actually cares about — and, in the no-wallpaper spirit, it refuses to invent an axis it has no
evidence for: a missing report yields an `unknown` dimension, never a flattering guess.

The axes (all sourced from reports the system already writes about ITSELF):
  * honesty          — does any feature lie about itself?            (program_reality_audit.json)
  * self_knowledge   — how much of the system is formally classified? (live_path_results + inventory)
  * live_integrity   — of what's classified, how much is COMPLETE?    (live_path_results.json)
  * self_improvement — does the system close its own work orders?      (improvement_backlog.json)
  * open_work        — what does the system currently know is wrong?    (patterns.json)

Each axis carries a status (strong | ok | weak | unknown), a short value, a one-line human
explanation, and the raw evidence it was computed from. The whole is a small, auditable object
plus a plain-English synthesis. Pure + hermetic: reads reports/*.json, writes reports/system_shape.json
(when asked). It NEVER runs a model, touches .anima, or hits the live server.
"""
from __future__ import annotations

import json
from dataclasses import asdict, dataclass, field
from pathlib import Path
from typing import Any, Dict, List, Optional

ROOT = Path(__file__).resolve().parent.parent
REPORTS = ROOT / "reports"

STRONG, OK, WEAK, UNKNOWN = "strong", "ok", "weak", "unknown"
_STATUS_RANK = {WEAK: 0, OK: 1, STRONG: 2, UNKNOWN: 3}   # weakest axis first when ranked


@dataclass
class Dimension:
    key: str
    label: str
    status: str
    value: str
    human: str
    evidence: Dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> dict:
        return asdict(self)


def _read_json(name: str, reports_dir: Path) -> Optional[Any]:
    try:
        return json.loads((Path(reports_dir) / name).read_text(encoding="utf-8"))
    except Exception:
        return None


def _counts_from_audit(audit: Any) -> Dict[str, int]:
    c = (audit or {}).get("counts", {}) if isinstance(audit, dict) else {}
    return {k: int(v) for k, v in c.items()} if isinstance(c, dict) else {}


def _dim_honesty(audit: Any) -> Dimension:
    if not isinstance(audit, dict):
        return Dimension("honesty", "Honesty (no-wallpaper)", UNKNOWN, "no audit",
                         "Run the Program Reality Audit to know if any feature lies about itself.")
    counts = _counts_from_audit(audit)
    wall = counts.get("WALLPAPER", 0)
    regr = counts.get("REGRESSED", 0)
    verdict = str(audit.get("verdict", "?"))
    if wall == 0 and regr == 0:
        return Dimension("honesty", "Honesty (no-wallpaper)", STRONG, f"{verdict} · 0 wallpaper",
                         "No feature's surface contradicts its behavior — nothing is pretending to work.",
                         {"verdict": verdict, "wallpaper": wall, "regressed": regr})
    return Dimension("honesty", "Honesty (no-wallpaper)", WEAK,
                     f"{verdict} · {wall} wallpaper, {regr} regressed",
                     f"{wall + regr} feature(s) lie about themselves — surfaces that contradict behavior.",
                     {"verdict": verdict, "wallpaper": wall, "regressed": regr})


def _dim_self_knowledge(live: Any, inventory: Any, audit: Any) -> Dimension:
    classified = 0
    if isinstance(audit, dict):
        classified = sum(_counts_from_audit(audit).values())
    inv = 0
    if isinstance(inventory, dict):
        items = inventory.get("features", inventory.get("count"))
        inv = len(items) if isinstance(items, list) else int(items or 0)
    if not classified or not inv:
        return Dimension("self_knowledge", "Self-knowledge (coverage)", UNKNOWN,
                         f"{classified}/{inv or '?'}",
                         "How much of the system is formally classified is not yet known.",
                         {"classified": classified, "inventory": inv})
    frac = classified / inv
    status = STRONG if frac >= 0.5 else (OK if frac >= 0.1 else WEAK)
    return Dimension("self_knowledge", "Self-knowledge (coverage)", status,
                     f"{classified}/{inv} ({frac*100:.0f}%)",
                     f"{classified} of {inv} claimed features carry a live-path contract; the other "
                     f"{inv - classified} are unverified surface (an honest, named gap).",
                     {"classified": classified, "inventory": inv, "fraction": round(frac, 3)})


def _dim_live_integrity(audit: Any) -> Dimension:
    counts = _counts_from_audit(audit)
    if not counts:
        return Dimension("live_integrity", "Live-path integrity", UNKNOWN, "no audit",
                         "Of what's classified, how much actually works end-to-end is unknown.")
    total = sum(counts.values())
    complete = counts.get("COMPLETE", 0)
    frac = (complete / total) if total else 0.0
    status = STRONG if frac >= 0.8 else (OK if frac >= 0.5 else WEAK)
    partial = counts.get("PARTIAL", 0) + counts.get("UNKNOWN", 0)
    return Dimension("live_integrity", "Live-path integrity", status,
                     f"{complete}/{total} COMPLETE",
                     f"{complete} of {total} classified features prove end-to-end; {partial} are "
                     f"PARTIAL/UNKNOWN (honest gaps, reported not hidden).",
                     {"complete": complete, "classified": total,
                      "partial_or_unknown": partial, "fraction": round(frac, 3)})


def _dim_self_improvement(backlog: Any) -> Dimension:
    if not isinstance(backlog, dict):
        return Dimension("self_improvement", "Self-improvement (loop closure)", UNKNOWN, "no backlog",
                         "Whether the system closes its own work orders is not yet tracked.")
    st = backlog.get("stats", {})
    certified = int(st.get("certified", 0))
    actionable = int(st.get("open_actionable", 0))
    total = int(st.get("total", certified + actionable))
    if total == 0:
        return Dimension("self_improvement", "Self-improvement (loop closure)", OK, "0 work orders",
                         "No outstanding work orders — nothing the observatory has flagged is open.")
    if actionable == 0:
        status, human = STRONG, (f"All {certified} tracked work order(s) are CERTIFIED — every known "
                                 f"issue is proven fixed by its own cert.")
    elif certified >= actionable:
        status, human = OK, (f"{certified} certified vs {actionable} still actionable — the loop is "
                             f"closing more than it opens.")
    else:
        status, human = WEAK, (f"{actionable} actionable vs {certified} certified — more open work "
                               f"than proven fixes.")
    return Dimension("self_improvement", "Self-improvement (loop closure)", status,
                     f"{certified} certified / {actionable} open", human,
                     {"certified": certified, "actionable": actionable, "total": total})


def _dim_open_work(patterns: Any) -> Dimension:
    if not isinstance(patterns, dict):
        return Dimension("open_work", "Known problems (patterns)", UNKNOWN, "no patterns",
                         "What the system currently knows is wrong with itself is not yet computed.")
    c = patterns.get("counts", {})
    p0, p1, p2 = int(c.get("P0", 0)), int(c.get("P1", 0)), int(c.get("P2", 0))
    if p0 > 0:
        status = WEAK
    elif p1 > 0:
        status = OK
    else:
        status = STRONG
    return Dimension("open_work", "Known problems (patterns)", status,
                     f"P0:{p0} P1:{p1} P2:{p2}",
                     (f"{p0} ship-blocking, {p1} important, {p2} cleanup pattern(s) the system has "
                      f"detected in itself." if (p0 + p1 + p2) else
                      "No recurring problems currently detected."),
                     {"P0": p0, "P1": p1, "P2": p2})


def compose(reports_dir: Path = REPORTS) -> Dict[str, Any]:
    """Build the system shape from whatever reports exist (missing -> an honest `unknown` axis)."""
    reports_dir = Path(reports_dir)
    audit = _read_json("program_reality_audit.json", reports_dir)
    live = _read_json("live_path_results.json", reports_dir)
    inventory = _read_json("feature_inventory.json", reports_dir)
    backlog = _read_json("improvement_backlog.json", reports_dir)
    patterns = _read_json("patterns.json", reports_dir)

    dims = [
        _dim_honesty(audit),
        _dim_self_knowledge(live, inventory, audit),
        _dim_live_integrity(audit),
        _dim_self_improvement(backlog),
        _dim_open_work(patterns),
    ]
    return {
        "phase": "System Shape — what kind of mind is this, right now",
        "dimensions": [d.to_dict() for d in dims],
        "synthesis": _synthesize(dims),
        "headline_status": _headline(dims),
        "inputs_present": {
            "program_reality_audit": audit is not None, "live_path_results": live is not None,
            "feature_inventory": inventory is not None, "improvement_backlog": backlog is not None,
            "patterns": patterns is not None,
        },
    }


def _headline(dims: List[Dimension]) -> str:
    """The overall shape: WEAK if any axis is weak, else UNKNOWN if any unknown, else OK/STRONG."""
    statuses = {d.status for d in dims}
    if WEAK in statuses:
        return WEAK
    if all(s == STRONG for s in statuses):
        return STRONG
    if UNKNOWN in statuses:
        return UNKNOWN
    return OK


def _synthesize(dims: List[Dimension]) -> str:
    by = {d.key: d for d in dims}
    bits = []
    h = by.get("honesty")
    if h:
        bits.append("honest" if h.status == STRONG else
                    ("honesty unknown" if h.status == UNKNOWN else "NOT fully honest"))
    sk = by.get("self_knowledge")
    if sk and sk.status != UNKNOWN:
        bits.append(f"{sk.value} of itself formally known")
    li = by.get("live_integrity")
    if li and li.status != UNKNOWN:
        bits.append(f"{li.value}")
    si = by.get("self_improvement")
    if si and si.status != UNKNOWN:
        bits.append("self-improving" if si.status in (STRONG, OK) else "improvement loop behind")
    ow = by.get("open_work")
    if ow and ow.status != UNKNOWN:
        bits.append("no ship-blockers" if ow.evidence.get("P0", 0) == 0 else
                    f"{ow.evidence.get('P0')} ship-blocker(s)")
    return "Vera right now: " + "; ".join(bits) + "." if bits else "Vera right now: insufficient evidence."


def rank_dimensions(dims: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
    """Weakest axis first (so the founder sees what needs attention before what's fine)."""
    return sorted(dims, key=lambda d: _STATUS_RANK.get(d.get("status"), 9))


def save(shape: Dict[str, Any], path: Path = REPORTS / "system_shape.json") -> Path:
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(shape, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
    return path


# --------------------------------------------------------------------------------------------
# selftest — hermetic. Fabricate synthetic reports in a temp dir and assert the shape composes:
# every axis reads its source; a missing report yields `unknown` (no fabrication); the headline +
# synthesis reflect the inputs.
# --------------------------------------------------------------------------------------------
def _selftest() -> int:
    import tempfile
    fails = []

    def ck(label, cond):
        print(("  ok   " if cond else "  XX   ") + label)
        if not cond:
            fails.append(label)

    print("system_shape — the honest one-glance portrait (hermetic)")
    print("=" * 60)
    with tempfile.TemporaryDirectory() as td:
        rd = Path(td)
        # a healthy synthetic world: AMBER audit (0 wallpaper), 12/81 classified, 9 complete,
        # 1 certified work order, 0 P0 patterns.
        (rd / "program_reality_audit.json").write_text(json.dumps({
            "verdict": "AMBER",
            "counts": {"COMPLETE": 9, "PARTIAL": 2, "UNKNOWN": 1}}))
        (rd / "feature_inventory.json").write_text(json.dumps({"features": list(range(81))}))
        (rd / "live_path_results.json").write_text(json.dumps({"features": {}}))
        (rd / "improvement_backlog.json").write_text(json.dumps({
            "stats": {"total": 1, "certified": 1, "open_actionable": 0}}))
        (rd / "patterns.json").write_text(json.dumps({"counts": {"P0": 0, "P1": 1, "P2": 0}}))

        shape = compose(rd)
        by = {d["key"]: d for d in shape["dimensions"]}
        ck("five axes composed", len(shape["dimensions"]) == 5)
        ck("honesty STRONG when 0 wallpaper/regressed", by["honesty"]["status"] == STRONG)
        ck("self_knowledge OK at 12/81 (≥10%)", by["self_knowledge"]["status"] == OK)
        ck("self_knowledge value is 12/81", by["self_knowledge"]["value"].startswith("12/81"))
        ck("live_integrity OK at 9/12 COMPLETE", by["live_integrity"]["status"] == OK)
        ck("self_improvement STRONG when all certified", by["self_improvement"]["status"] == STRONG)
        ck("open_work OK when P0==0 but P1>0", by["open_work"]["status"] == OK)
        ck("headline is OK (no weak axis, not all strong)", shape["headline_status"] == OK)
        ck("synthesis mentions honest + self-improving",
           "honest" in shape["synthesis"] and "self-improving" in shape["synthesis"])

        # a WALLPAPER world flips honesty + headline to weak
        (rd / "program_reality_audit.json").write_text(json.dumps({
            "verdict": "RED", "counts": {"COMPLETE": 8, "WALLPAPER": 1}}))
        shape2 = compose(rd)
        by2 = {d["key"]: d for d in shape2["dimensions"]}
        ck("honesty WEAK with a wallpaper feature", by2["honesty"]["status"] == WEAK)
        ck("headline WEAK when an axis is weak", shape2["headline_status"] == WEAK)
        ck("synthesis says NOT fully honest", "NOT fully honest" in shape2["synthesis"])

        # missing reports -> honest `unknown`, never a fabricated value
        shape3 = compose(Path(td) / "empty")
        ck("all axes unknown when no reports exist",
           all(d["status"] == UNKNOWN for d in shape3["dimensions"]))
        ck("headline unknown with no evidence", shape3["headline_status"] == UNKNOWN)

        # weakest-first ranking
        ranked = rank_dimensions(shape2["dimensions"])
        ck("rank_dimensions puts a weak axis first", ranked[0]["status"] == WEAK)

        # save round-trips
        p = save(shape, rd / "system_shape.json")
        ck("save writes valid JSON", json.loads(p.read_text())["headline_status"] == OK)

    print("\nSYSTEM SHAPE SELFTEST: " + ("PASS" if not fails else f"FAIL ({len(fails)})"))
    return 1 if fails else 0


if __name__ == "__main__":
    raise SystemExit(_selftest())

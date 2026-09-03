"""
twin_dashboard — the PERSONAL DIGITAL TWIN: one honest view of what Vera actually knows about YOU.

System Shape (anima/system_shape) answers "what kind of MIND is Vera?". This answers the other
half of the 10^inf goal — the *portable personal intelligence* — "what does that mind actually
know about the PERSON?". It composes the grounded personal stores Vera already keeps into one
picture across the dimensions that make a twin: who you are, how you think, where you're heading,
what matters to you, and your world.

This is NOT the digital-twin SIMULATION (anima/twin.py — the sandbox that tests a change on a copy
before prod). It is the read-only PORTRAIT of the accumulated knowledge: the thing you'd want to be
able to carry from app to app and model to model.

Dimensions (each sourced from a real store; an empty store yields an honest "nothing yet", never an
invented trait — the no-wallpaper rule applied to a person's portrait):
  * identity              — durable facts about you            (memory_lirf: name, birthday, work, …)
  * how_you_think         — decisions / values / preferences   (personal.personal_profile — Learn Lamar)
  * trajectory            — your direction over time           (trajectory.snapshot_trajectory)
  * what_matters          — meaning / what you care about      (meaning.snapshot)
  * your_world            — people / projects / situations     (world_state / world_model)

Each dimension carries a count, a short list of grounded items, and present/absent. The whole gets a
richness headline (empty / sparse / forming / rich) and a plain-English synthesis. Pure + hermetic:
reads the per-creature stores read-only, writes reports/twin_dashboard.json when asked. NEVER a
model, never the live server, never a mutation of any store.
"""
from __future__ import annotations

import json
from dataclasses import asdict, dataclass, field
from pathlib import Path
from typing import Any, Dict, List

ROOT = Path(__file__).resolve().parent.parent
REPORTS = ROOT / "reports"


@dataclass
class Dimension:
    key: str
    label: str
    count: int
    present: bool
    items: List[str] = field(default_factory=list)

    def to_dict(self) -> dict:
        return asdict(self)


def _safe(fn, default):
    try:
        return fn()
    except Exception:
        return default


def _dict_richness(d: Any) -> int:
    """Count salient items in a snapshot dict: sum of list lengths, else 1 if non-empty."""
    if not isinstance(d, dict):
        return 0
    n = 0
    listy = False
    for v in d.values():
        if isinstance(v, list):
            listy = True
            n += len(v)
    if listy:
        return n
    return 1 if any(v not in (None, "", [], {}, False) for v in d.values()) else 0


def _identity(name: str) -> Dimension:
    def go():
        from . import memory_lirf as ml
        rows = ml.Facts.load(name).about(ml.SELF)
        items = ["%s: %s" % (str(r.get("trait", "?")).replace("_", " "), ml._fmt_value(r.get("value", "")))
                 for r in rows[:10]]
        return Dimension("identity", "Who you are (facts)", len(rows), bool(rows), items)
    return _safe(go, Dimension("identity", "Who you are (facts)", 0, False, []))


def _how_you_think(name: str) -> Dimension:
    def go():
        from . import personal
        p = personal.personal_profile(name)
        c = p.get("counts", {}) or {}
        items = ["%s: %d" % (k.replace("_", " "), v) for k, v in c.items() if v]
        return Dimension("how_you_think", "How you think (decisions/values/preferences)",
                         sum(c.values()), bool(p.get("known")), items)
    return _safe(go, Dimension("how_you_think", "How you think (decisions/values/preferences)", 0, False, []))


def _trajectory(name: str) -> Dimension:
    def go():
        from . import trajectory
        snap = trajectory.snapshot_trajectory(name)
        n = _dict_richness(snap)
        items = []
        if isinstance(snap, dict):
            for k in ("threads", "directions", "themes", "arcs"):
                v = snap.get(k)
                if isinstance(v, list) and v:
                    items += [str((x.get("name") or x.get("label") or x) if isinstance(x, dict) else x)[:60]
                              for x in v[:4]]
        return Dimension("trajectory", "Where you're heading (over time)", n, n > 0, items[:6])
    return _safe(go, Dimension("trajectory", "Where you're heading (over time)", 0, False, []))


def _what_matters(name: str) -> Dimension:
    def go():
        from . import meaning
        snap = meaning.snapshot(name)
        n = _dict_richness(snap)
        items = []
        if isinstance(snap, dict):
            for k in ("themes", "meanings", "cares", "values", "items"):
                v = snap.get(k)
                if isinstance(v, list) and v:
                    items += [str((x.get("name") or x.get("summary") or x) if isinstance(x, dict) else x)[:60]
                              for x in v[:4]]
        return Dimension("what_matters", "What matters to you", n, n > 0, items[:6])
    return _safe(go, Dimension("what_matters", "What matters to you", 0, False, []))


def _your_world(name: str) -> Dimension:
    """Presence + a rough size from world_state/world_model render (no fragile struct parsing)."""
    def go():
        from . import world_state
        txt = world_state.render(name) or ""
        low = txt.lower()
        # the empty render is a header + an explicit "(0 relations) / no situations yet" note.
        empty_markers = ("(0 relations)", "no situations connected", "emerge as you talk",
                         "nothing", "no relationships")
        if any(m in low for m in empty_markers):
            return Dimension("your_world", "Your world (people/projects/situations)", 0, False, [])
        # otherwise count the substantive situation lines, dropping the header line.
        lines = [ln.strip() for ln in txt.splitlines()
                 if ln.strip() and not ln.strip().startswith(("#", "—", "=", "("))]
        substantive = [ln for ln in lines
                       if len(ln) > 12 and "understands about your situation" not in ln.lower()][:8]
        return Dimension("your_world", "Your world (people/projects/situations)",
                         len(substantive), len(substantive) >= 1, substantive[:6])
    return _safe(go, Dimension("your_world", "Your world (people/projects/situations)", 0, False, []))


def compose(name: str = "Vera") -> Dict[str, Any]:
    """Build the personal digital twin portrait for `name` from the grounded personal stores."""
    dims = [_identity(name), _how_you_think(name), _trajectory(name), _what_matters(name),
            _your_world(name)]
    present = sum(1 for d in dims if d.present)
    total_items = sum(d.count for d in dims)
    return {
        "phase": "Personal Digital Twin — what Vera knows about you",
        "person": name,
        "dimensions": [d.to_dict() for d in dims],
        "richness": _richness(present, total_items),
        "synthesis": _synthesize(name, dims),
        "coverage": {"dimensions_present": present, "dimensions_total": len(dims),
                     "items_known": total_items},
    }


def _richness(present: int, total_items: int) -> str:
    if present == 0:
        return "empty"
    if present >= 4 and total_items >= 15:
        return "rich"
    if present >= 2:
        return "forming"
    return "sparse"


def _synthesize(name: str, dims: List[Dimension]) -> str:
    have = [d for d in dims if d.present]
    miss = [d for d in dims if not d.present]
    if not have:
        return ("Vera's picture of you is empty so far — nothing has been grounded yet. "
                "It fills in as you talk, upload, and correct.")
    bits = ["%d %s" % (d.count, d.label.split("(")[0].strip().lower()) for d in have]
    s = "Vera's grounded picture of you: " + "; ".join(bits) + "."
    if miss:
        s += " Nothing yet on: " + ", ".join(d.label.split("(")[0].strip().lower() for d in miss) + "."
    return s


def rank_dimensions(dims: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
    """Richest dimension first (what Vera knows best about you), empty ones last."""
    return sorted(dims, key=lambda d: (d.get("present") is True, d.get("count", 0)), reverse=True)


def save(twin: Dict[str, Any], path: Path = REPORTS / "twin_dashboard.json") -> Path:
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(twin, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
    return path


# --------------------------------------------------------------------------------------------
# selftest — hermetic. Seed a couple of grounded personal stores in a temp dir and assert the twin
# composes honestly: known dimensions count their items; unseeded ones report present=False (no
# fabrication); richness + synthesis reflect the evidence.
# --------------------------------------------------------------------------------------------
def _selftest() -> int:
    import importlib.util
    fails = []

    def ck(label, cond):
        print(("  ok   " if cond else "  XX   ") + label)
        if not cond:
            fails.append(label)

    spec = importlib.util.spec_from_file_location(
        "g0pe", str(ROOT / "scripts" / "gate0_prime_experience.py"))
    g0pe = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(g0pe)

    print("twin_dashboard — the personal digital twin (hermetic)")
    print("=" * 60)
    with g0pe._temp_store():
        from anima import memory_lirf as ml
        name = "TwinProbe"
        # an EMPTY twin first — every dimension honestly absent.
        empty = compose(name)
        ck("empty store -> richness 'empty'", empty["richness"] == "empty")
        ck("empty store -> all dimensions present=False",
           all(not d["present"] for d in empty["dimensions"]))
        ck("empty synthesis says nothing grounded yet",
           "empty" in empty["synthesis"].lower() or "nothing" in empty["synthesis"].lower())

        # seed real identity facts -> the identity dimension fills in, others stay honest.
        ml.capture(name, "my name is Lamar")
        ml.capture(name, "my birthday is March 4, 1991")
        ml.capture(name, "I work at Collatio")
        ml.capture(name, "my dog's name is Biscuit")
        t = compose(name)
        by = {d["key"]: d for d in t["dimensions"]}
        ck("identity dimension present after seeding facts", by["identity"]["present"])
        ck("identity counts the grounded facts (>=4)", by["identity"]["count"] >= 4)
        ck("identity items mention Lamar", any("lamar" in i.lower() for i in by["identity"]["items"]))
        ck("how_you_think stays honestly absent (no personal-intelligence seeded)",
           not by["how_you_think"]["present"])
        ck("richness is at least 'sparse' with identity known", t["richness"] in ("sparse", "forming", "rich"))
        ck("synthesis names a present dimension and the gaps",
           "who you are" in t["synthesis"].lower() and "nothing yet" in t["synthesis"].lower())
        _ranked = rank_dimensions(t["dimensions"])
        ck("rank puts a PRESENT dimension first, an ABSENT one last (richest-first)",
           _ranked[0]["present"] is True and _ranked[-1]["present"] is False)
        ck("identity is among the present dimensions",
           any(d["key"] == "identity" and d["present"] for d in _ranked))

        # save round-trips
        import tempfile
        with tempfile.TemporaryDirectory() as td:
            p = save(t, Path(td) / "twin_dashboard.json")
            ck("save writes valid JSON", json.loads(p.read_text())["coverage"]["items_known"] >= 4)

    print("\nTWIN DASHBOARD SELFTEST: " + ("PASS" if not fails else f"FAIL ({len(fails)})"))
    return 1 if fails else 0


if __name__ == "__main__":
    raise SystemExit(_selftest())

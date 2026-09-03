#!/usr/bin/env python3
"""VERA ISOLATION MATRIX — a FIREWALL FOR COGNITION.

    ANIMA containment principle — STAY IN YOUR LANE.
    A subsystem is not safe because it produces the right output. It is safe only when it
    can prove it touched NOTHING it was not entitled to touch. As subsystems multiply
    (ledger · backup · telemetry/MRI · experience · conservation · relationship · decisions ·
    counterfactual · observability) the cross-component interactions grow COMBINATORIALLY, and
    a single hidden write pathway leaks one creature's state into another's. Isolation must be
    DECLARED and AUTOMATICALLY TESTED, not assumed.

This is the enforcement arm of that principle — to containment what scripts/certify.py is to
LAW 004: not a written promise but a RUNNABLE one. It DECLARES every component's allowed
write/read scope, then drives each component on SYNTHETIC input in a TEMP store and PROVES,
by a content-hash + file-set snapshot of the real .anima (INCLUDING backups/) taken before and
after, that the real .anima is byte-UNCHANGED — i.e. the component stayed in its lane.

WHY THIS EXISTS (the bug that birthed it):
    A self-test creature (memory_lirf._selftest) leaked a continuity-ledger file and a backup
    snapshot into the REAL .anima because its outer hermetic block redirected memory_lirf.STORE
    but NOT constitution.STORE (the continuity ledger) or reliability.DEFAULT_STORE (guarded
    backups). The leak was fixed in 03a73aa — but the fact that it existed at all proves more
    hidden cross-component write pathways are likely. The matrix's job is to CATCH that exact
    class of bug, mechanically, for every component, forever.

THE MATRIX (component -> may WRITE / may READ):
    * Live Vera (server) ................ Vera.*                         / Vera.*
    * Synthetic / selftest creatures .... own {name}.* in a TEMP store   / same
    * certify.py ........................ temp stores only               / temp
    * MRI / telemetry ................... traces ({name}.mri.jsonl)       / traces
    * backup / reliability .............. the store it is GIVEN          / same
    * experience/conservation/relationship/decisions/counterfactual ..
                                          temp/synthetic only            / read-only on real

FORBIDDEN DIRECTIONS the matrix asserts are DETECTED (every one must FAIL = be prevented):
    * Synthetic -> Vera   a selftest/synthetic creature must NEVER write Vera.* or leak ANY
                          file into the real .anima. (This is the leak just fixed.)
    * Vera -> Synthetic   the live store must never be the sink for a synthetic run.
    * certify -> Vera     the cert harness must leave the real .anima byte-UNCHANGED.
    * MRI -> memory       recording a turn's trace must NEVER mutate Facts/World/memory stores.

CRITICAL SELF-VALIDATION (prove the detector WORKS):
    The matrix includes a DELIBERATELY-UNHERMETIC probe — a synthetic write that does NOT
    redirect constitution.STORE / reliability.DEFAULT_STORE (mimicking the exact just-fixed
    leak) — and asserts the matrix flags it RED. THEN the real components pass GREEN. So the
    matrix demonstrably catches the precise class of bug that was just found, rather than only
    asserting "nothing happened" (which a broken detector would also report).

GUARDRAILS — the isolation tester must ITSELF be perfectly isolated (it is the ANTI-LEAK tool):
    * Every probe redirects ALL stores to one fresh temp dir: memory_lirf.STORE on BOTH the
      __main__ and the package bindings, world_state.STORE, constitution.STORE,
      reliability.DEFAULT_STORE, curiosity.STORE, and the telemetry trace path — restored on
      exit. It NEVER reads or writes a real Vera.* file.
    * The real-.anima snapshot is content-hash + file-set INCLUDING backups/, because the leak
      we are guarding against is precisely a stray backup snapshot. (certify._footprint excludes
      backups/ on purpose — it tolerates a live server's own rotation; here we want the stricter
      guarantee that a SYNTHETIC run added NOTHING, backups included.)
    * OFFLINE-FIRST. No model is required.

    python3 scripts/isolation.py             # human-readable matrix report
    python3 scripts/isolation.py --json      # machine-readable
    python3 scripts/isolation.py --selftest  # prove the detector itself (the RED probe goes RED)
Exit code is NON-ZERO unless the OVERALL status is ISOLATION CERTIFIED.
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

# Synthetic-only sentinel names so NOTHING here can collide with a real creature. Each probe
# coins its own unique creature so two probes can never alias on disk either.
SYNTH = "iso_synthetic"


def _synth_name(tag: str) -> str:
    return f"{SYNTH}_{tag}_{secrets.token_hex(3)}"


# ===================================================================================
# tiny result model — mirrors scripts/certify.CheckResult so the cert section can fold
# our rows in unchanged.
# ===================================================================================
class CheckResult:
    __slots__ = ("name", "status", "detail")

    def __init__(self, name: str, status: str, detail: str = ""):
        # status in {"PASS", "FAIL", "SKIP", "PENDING"}
        self.name = name
        self.status = status
        self.detail = detail

    def to_dict(self) -> dict:
        return {"name": self.name, "status": self.status, "detail": self.detail}


def _passed(results) -> bool:
    """The matrix certifies iff it has at least one row and none FAILED."""
    if not results:
        return False
    return all(r.status != "FAIL" for r in results)


# ===================================================================================
# THE REAL-.anima SNAPSHOT — content hash + file SET, INCLUDING backups/.
#
# This is deliberately STRICTER than certify._footprint (which excludes backups/ so it can
# tolerate a live server's own rotation). The leak we guard against is precisely a stray
# backup snapshot escaping from a synthetic run, so a synthetic probe must add NOTHING —
# backups included. We snapshot before and after each probe and assert byte-equality.
# ===================================================================================
def _snapshot(root: Path) -> tuple[str, frozenset]:
    """A (content-hash, relative-file-set) snapshot of EVERY real .anima file, backups/ and
    all. Returns ("<empty>", frozenset()) if the directory does not exist. The file SET is
    returned alongside the hash so a breach can name exactly WHICH paths appeared/changed."""
    if not root.is_dir():
        return "<no .anima>", frozenset()
    files = sorted(p for p in root.rglob("*") if p.is_file())
    rels = []
    h = hashlib.sha256()
    for p in files:
        rel = str(p.relative_to(root))
        rels.append(rel)
        h.update(rel.encode())
        h.update(b"\0")
        try:
            h.update(p.read_bytes())
        except OSError:
            h.update(b"<unreadable>")
    return h.hexdigest(), frozenset(rels)


def _diff_paths(before: frozenset, after: frozenset) -> list:
    """The relative paths that APPEARED in the real .anima between two snapshots (the blast
    radius of a leak). Sorted for a stable report."""
    return sorted(after - before)


def _synthetic_leak(root: Path) -> list:
    """The PRECISE guardrail (the experience.py / conservation.py pattern): list any real-store
    file named for a SYNTHETIC creature (iso_synthetic*). A probe's only intended blast radius
    is its sentinel name; if such a file appears in the real .anima, a redirect leaked and that
    is a hard breach. Scoped to the synthetic name so an UNRELATED live Vera server writing its
    own files concurrently never flakes this. Empty list == no leak == guardrail held."""
    if not root.is_dir():
        return []
    return sorted(str(p.relative_to(root)) for p in root.rglob(f"{SYNTH}*") if p.is_file())


# ===================================================================================
# THE ALL-STORE REDIRECT — the tester must be MORE hermetic than anything it tests.
#
# Mirrors the canonical "redirect ALL stores" pattern just installed in memory_lirf._selftest
# (commit 03a73aa) and in scripts/certify._temp_store. We redirect EVERY module store the
# load/record paths can resolve, to ONE fresh temp dir, for the duration:
#   * memory_lirf.STORE   — on BOTH the package binding and, if distinct, the __main__ binding
#                           (curiosity / memory_lirf can be imported under either name; a bare
#                           STORE on one is a SEPARATE binding from the other).
#   * world_state.STORE   — the relation graph + its guarded backups.
#   * constitution.STORE  — the continuity ledger ({name}.continuity.jsonl) — the FIRST half of
#                           the just-fixed leak.
#   * reliability.DEFAULT_STORE — guarded backups ({.anima}/backups/...) — the SECOND half of
#                           the just-fixed leak (resolved when a store= arg is omitted).
#   * curiosity.STORE     — the curiosity ledger ({name}.curiosity.jsonl).
#   * telemetry.STORE     — the MRI / replay trace path ({name}.mri.jsonl, {name}.telemetry.jsonl).
# Everything is restored in a finally. This is what makes a leak IMPOSSIBLE regardless of what
# the component under test writes — so when a probe DOES leak, we know it is the probe's own
# (deliberately partial) redirect at fault, not ours.
# ===================================================================================

# (module dotted-path, attribute name) for every store binding we pin.
_STORE_BINDINGS = (
    ("anima.memory_lirf", "STORE"),
    ("anima.world_state", "STORE"),
    ("anima.constitution", "STORE"),
    ("anima.reliability", "DEFAULT_STORE"),
    ("anima.curiosity", "STORE"),
    ("anima.telemetry", "STORE"),
)


def _collect_store_targets(exclude=None) -> list:
    """Resolve _STORE_BINDINGS to a concrete list of (module_object, attr) targets, ADDING the
    __main__ binding of memory_lirf / curiosity when it is a DISTINCT module object (the dual-
    binding trap the canonical _selftest pattern guards against). `exclude`, if given, DROPS
    those dotted paths from the redirect so a probe can deliberately leave PART of the surface
    pointed at the REAL .anima — the mechanism the RED self-validation probe uses to reproduce
    the just-fixed leak (where memory_lirf.STORE was NOT redirected at all)."""
    exclude = set(exclude or ())
    bindings = tuple(b for b in _STORE_BINDINGS if b[0] not in exclude)
    targets: list = []
    seen: set = set()
    for dotted, attr in bindings:
        try:
            mod = __import__(dotted, fromlist=["_"])
        except Exception:
            continue
        if (id(mod), attr) not in seen and hasattr(mod, attr):
            targets.append((mod, attr))
            seen.add((id(mod), attr))
        # the __main__ twin: if this module is ALSO loaded under a different name whose bare
        # attribute is a separate binding, pin it too (the memory_lirf / curiosity dual binding).
        twin = sys.modules.get(dotted.split(".")[-1])
        if twin is not None and twin is not mod and (id(twin), attr) not in seen \
                and hasattr(twin, attr):
            targets.append((twin, attr))
            seen.add((id(twin), attr))
    return targets


@contextlib.contextmanager
def _all_stores_temp(exclude=None):
    """Redirect ALL store bindings (minus an optional `exclude` set) to ONE fresh temp dir for
    the duration, yielding the temp Path. Restored on exit. With exclude=None this makes the
    block FULLY hermetic; excluding some bindings deliberately leaves them pointed at the real
    .anima — the mechanism the RED self-validation probe uses to reproduce the known leak."""
    targets = _collect_store_targets(exclude)
    saved = [(m, a, getattr(m, a, None)) for (m, a) in targets]
    with tempfile.TemporaryDirectory(prefix="anima-isolation-") as td:
        p = Path(td)
        for (m, a) in targets:
            setattr(m, a, p)
        try:
            yield p
        finally:
            for (m, a, old) in saved:
                if old is not None:
                    setattr(m, a, old)


# ===================================================================================
# THE DECLARED MATRIX — every component's ALLOWED write/read scope, as data.
#
# Rows are printed verbatim in the report so the DECLARATION and the TEST live in one file:
# a reviewer reads the lane each component is allowed, then sees the probe that proves it.
# ===================================================================================
class Component:
    __slots__ = ("key", "label", "may_write", "may_read")

    def __init__(self, key: str, label: str, may_write: str, may_read: str):
        self.key = key
        self.label = label
        self.may_write = may_write
        self.may_read = may_read


MATRIX = [
    Component("live_vera",   "Live Vera (server)",
              "Vera.*", "Vera.*"),
    Component("synthetic",   "Synthetic / selftest creatures",
              "own {name}.* in a TEMP store only", "same (temp)"),
    Component("certify",     "certify.py",
              "temp stores only", "temp"),
    Component("mri",         "MRI / telemetry",
              "traces ({name}.mri.jsonl)", "traces"),
    Component("reliability", "backup / reliability",
              "the store it is GIVEN", "same"),
    Component("derived",     "experience / conservation / relationship / decisions / counterfactual",
              "temp / synthetic only", "read-only on real"),
]
_MATRIX_BY_KEY = {c.key: c for c in MATRIX}


# ===================================================================================
# the probe harness — drive one component on synthetic input inside a (configurable) store
# redirect, with a real-.anima snapshot taken before and after. Returns a structured verdict.
# ===================================================================================
class ProbeResult:
    __slots__ = ("name", "stayed_in_lane", "leaked_paths", "extra_detail", "engine_error")

    def __init__(self, name, stayed_in_lane, leaked_paths, extra_detail="", engine_error=None):
        self.name = name
        self.stayed_in_lane = stayed_in_lane
        self.leaked_paths = leaked_paths
        self.extra_detail = extra_detail
        self.engine_error = engine_error


def _run_probe(name: str, drive, *, exclude=None, expect_leak: bool = False) -> ProbeResult:
    """Snapshot the real .anima (content-hash + file-set, backups included), run `drive`
    inside an all-stores temp redirect (minus an optional `exclude` set), re-snapshot, and
    decide whether the component STAYED IN ITS LANE.

      * drive(store: Path) -> optional detail-str : exercises the component, writing only into
        the redirected store(s). May return a short note folded into the report.
      * exclude : drop these dotted paths from the redirect, leaving them on the REAL .anima
        (the RED probe excludes memory_lirf.STORE et al. to reproduce the known leak). None ==
        redirect EVERYTHING (hermetic).
      * expect_leak : True for the self-validation RED probe — the detector PASSES when it
        observes the leak it expects, and FAILS if the leak somehow did NOT occur (which would
        mean the detector is blind).

    'Stayed in lane' == the real-.anima snapshot is byte-IDENTICAL before/after AND no
    iso_synthetic* file is present. Any appeared/changed path is the blast radius."""
    real = Path(_ROOT) / ".anima"
    before_hash, before_set = _snapshot(real)
    engine_error = None
    detail = ""
    with _all_stores_temp(exclude) as store:
        try:
            note = drive(store)
            if note:
                detail = str(note)
        except Exception as e:               # an engine raising is itself a containment finding
            engine_error = repr(e)
    after_hash, after_set = _snapshot(real)
    appeared = _diff_paths(before_set, after_set)
    changed = (before_hash != after_hash)
    synth_leak = _synthetic_leak(real)
    # the union of every escaped path the snapshot can name (appeared ∪ synthetic-named).
    leaked = sorted(set(appeared) | set(synth_leak))
    stayed = (not changed) and (not synth_leak)
    return ProbeResult(name, stayed, leaked, detail, engine_error)


# ----- synthetic drivers: each builds + exercises a component on a synthetic creature, writing
# ----- ONLY into the redirected store. No model, no network. -----------------------------------

def _seed_facts(store: Path, name: str):
    """A few real-shaped USER facts in the LIRF ledger, written via the (redirected) module
    STORE. Returns the Facts object."""
    from anima import memory_lirf
    f = memory_lirf.Facts([])
    for trait, value in (("name", "Lamar"), ("employer", "Collatio"),
                         ("role", "founder"), ("city", "Portland")):
        f.merge({"trait": trait, "value": value})
    f.save(name)
    return f


def _drive_synthetic_creature(store: Path) -> str:
    """COMPONENT: a synthetic / selftest creature. Exercise the FULL load path the just-fixed
    leak ran through — LIRF capture+save (touches constitution continuity ledger + reliability
    backups), and a world-graph relation capture (touches world_state + its backups). With the
    full redirect active, ALL of this must land in `store`, not the real .anima."""
    from anima import memory_lirf, world_state
    name = _synth_name("creature")
    f = memory_lirf.Facts([])
    for c in f.capture(name, "my birthday is June 11"):
        f.merge(c)
    for c in f.capture(name, "I live in Portland"):
        f.merge(c)
    f.save(name)
    # re-load through the guarded production path (this is what emits a backup + continuity row)
    memory_lirf.Facts.load(name)
    # a world-graph edge (its own store + guarded backups)
    try:
        world_state.capture_relations(name, "work is stressful because of my new manager")
        world_state.World.load(name)
    except Exception:
        pass
    return f"drove LIRF capture+save+load and world capture for {name}"


def _drive_certify_like(store: Path) -> str:
    """COMPONENT: the certify harness's blast radius. We do NOT shell certify.py here (that is
    the cert's own footprint guarantee); instead we exercise the SAME real production loaders
    certify drives — Facts.load / World.load on a synthetic creature — which is the operation a
    cert section performs. The real .anima must be byte-UNCHANGED."""
    from anima import memory_lirf, world_state
    name = _synth_name("certifylike")
    _seed_facts(store, name)
    memory_lirf.Facts.load(name)
    try:
        world_state.capture_relations(name, "my sister Mara moved to Denver")
        world_state.World.load(name)
    except Exception:
        pass
    return f"drove the real production loaders (Facts/World.load) for {name}"


def _drive_reliability(store: Path) -> str:
    """COMPONENT: backup / reliability. Drive an EXPLICIT backup of a synthetic creature against
    the GIVEN store; the snapshot must land under {store}/backups, never the real .anima/backups
    (the second half of the just-fixed leak)."""
    from anima import memory_lirf, reliability
    name = _synth_name("backup")
    _seed_facts(store, name)
    # backup against the store it is GIVEN — the matrix row's allowed lane.
    reliability.backup(name, store=store)
    return f"backup({name}, store=<temp>) -> snapshot under temp/backups only"


def _drive_mri_record(store: Path) -> tuple:
    """COMPONENT: MRI / telemetry. Record a full per-turn trace on a synthetic creature. Returns
    (note, memory_snapshot_before, memory_snapshot_after) so the caller can ALSO assert the
    MEMORY stores were byte-identical across the recording (the MRI->memory forbidden direction).

    We seed the LIRF + world stores FIRST, snapshot just those memory files, run a complete MRI
    trace (open_trace -> stages -> shapes -> alternatives -> commit), then re-snapshot the memory
    files. Recording must append ONLY the trace; it must never mutate Facts/World/memory."""
    from anima import telemetry, memory_lirf, world_state
    name = _synth_name("mri")
    # seed memory the recording must NOT touch
    _seed_facts(store, name)
    try:
        world_state.capture_relations(name, "work affects my sleep")
    except Exception:
        pass

    def _mem_snapshot() -> tuple:
        h = hashlib.sha256()
        names = []
        for fn in (f"{name}.lirf.json", f"{name}.world.json"):
            p = store / fn
            names.append(fn)
            if p.exists():
                h.update(fn.encode())
                h.update(b"\0")
                h.update(p.read_bytes())
        return h.hexdigest(), tuple(names)

    mem_before = _mem_snapshot()
    # a complete recorded turn
    tr = telemetry.open_trace(name, "turn-iso-0001", "when's my birthday?")
    tr.stage("perception", t_ms=0.4, in_shape={"text": "when's my birthday?"},
             out={"ok": True}, dropped=[], confidence=0.9, note="parsed")
    tr.stage("bind", t_ms=0.7, in_shape={"trait": "birthday"},
             out={"value": "June 11"}, dropped=["noise"], confidence=0.97, note="bound")
    tr.stage("generate", t_ms=1.1, in_shape={"prompt_len": 128},
             out={"reply": "June 11"}, dropped=[], confidence=0.95, note="spoke")
    tr.shape("bind->generate", received={"value": "June 11"},
             expected={"value": "str"}, transformation="fact->sentence", loss=[])
    tr.alternative("which model", selected="local-8b",
                   rejected=[{"option": "cloud", "reason": "offline"}])
    committed = tr.commit(reply="June 11", total_ms=2.3)
    # the legacy Telemetry recorder too (begin/note/commit) — a SECOND trace shape on disk
    try:
        rec = telemetry.Telemetry(name)
        rec.begin("turn-iso-0002", {"text": "hi", "name": name, "context": {}})
        rec.commit("turn-iso-0002")
    except Exception:
        pass
    mem_after = _mem_snapshot()
    trace_on_disk = (store / f"{name}.mri.jsonl").exists()
    note = (f"recorded a full MRI trace for {name} "
            f"(committed={'yes' if committed else 'no'}, trace_on_disk={trace_on_disk})")
    return note, mem_before, mem_after


def _drive_known_leak(store: Path) -> str:
    """THE DELIBERATELY-UNHERMETIC PROBE — reproduce the EXACT just-fixed leak.

    Driven with memory_lirf.STORE / constitution.STORE / reliability.DEFAULT_STORE EXCLUDED from
    the redirect (see `probe_known_leak`), so those stores still point at the REAL .anima —
    exactly the state memory_lirf._selftest's OUTER block ran in before 03a73aa (it redirected
    nothing relevant). Because memory_lirf.STORE is the real .anima here:
      * Facts.save writes a real .anima/{name}.lirf.json, and
      * Facts.load threads store=STORE(=real) into reliability and resolves the continuity ledger
        via constitution.STORE(=real) — so a recovery/snapshot escapes into the REAL .anima too.
    Synthetic state lands in the real store: the leak. The matrix MUST flag this RED.

    NOTE: every artifact is iso_synthetic*-named, so the leak is self-identifying and the harness
    scrubs it afterwards — the real .anima is left exactly as found."""
    from anima import memory_lirf, world_state
    name = _synth_name("leak")
    f = memory_lirf.Facts([])
    for c in f.capture(name, "my birthday is June 11"):
        f.merge(c)
    f.save(name)                    # -> REAL .anima/{name}.lirf.json (memory_lirf.STORE excluded)
    # the guarded load path resolves backups + the continuity ledger against the REAL store.
    memory_lirf.Facts.load(name)
    try:
        world_state.capture_relations(name, "work is stressful because of my new manager")
        world_state.World.load(name)
    except Exception:
        pass
    return f"UNHERMETIC drive (memory_lirf/constitution/reliability stores NOT redirected) for {name}"


def _scrub_synthetic(root: Path) -> list:
    """Remove any iso_synthetic*-named artifact the RED probe deliberately leaked into the real
    .anima (top-level files AND any backups/<ts>/ snapshot of them), so the matrix LEAVES the
    real .anima exactly as it found it even though one probe intentionally wrote to it. Returns
    the paths scrubbed (for the report's transparency). Scoped strictly to the sentinel name."""
    scrubbed = []
    if not root.is_dir():
        return scrubbed
    for p in sorted(root.rglob(f"{SYNTH}*"), reverse=True):
        try:
            if p.is_file():
                p.unlink()
                scrubbed.append(str(p.relative_to(root)))
        except OSError:
            pass
    # prune now-empty backups/<ts>/ dirs we emptied (never the backups/ root itself).
    backups = root / "backups"
    if backups.is_dir():
        for d in sorted(backups.glob("*"), reverse=True):
            try:
                if d.is_dir() and not any(d.iterdir()):
                    d.rmdir()
                    scrubbed.append(str(d.relative_to(root)) + "/")
            except OSError:
                pass
    return scrubbed


# ===================================================================================
# THE PROBES — one per matrix row + one per forbidden direction + the RED self-validation.
# Each returns a list[CheckResult]; the row's verdict is GREEN iff every check PASSed.
# ===================================================================================

def probe_synthetic_to_vera() -> list:
    """FORBIDDEN DIRECTION: Synthetic -> Vera. A synthetic creature, fully exercised, must NEVER
    write Vera.* or leak ANY file into the real .anima. This is the leak just fixed; with the
    full redirect active it stays in its lane (GREEN). It is the SAME drive the RED probe runs
    with a partial redirect — so the two together prove the matrix distinguishes a contained run
    from a leaking one."""
    pr = _run_probe("Synthetic -> Vera (no leak into real .anima)", _drive_synthetic_creature)
    results = []
    if pr.engine_error:
        results.append(CheckResult("synthetic creature drove without error", "FAIL",
                                   f"engine raised: {pr.engine_error}"))
    else:
        results.append(CheckResult("synthetic creature drove without error", "PASS", pr.extra_detail))
    if pr.stayed_in_lane:
        results.append(CheckResult(
            "FORBIDDEN Synthetic->Vera is PREVENTED (real .anima byte-UNCHANGED)", "PASS",
            "full-redirect synthetic run added/changed NOTHING under real .anima (backups incl.)"))
    else:
        results.append(CheckResult(
            "FORBIDDEN Synthetic->Vera is PREVENTED (real .anima byte-UNCHANGED)", "FAIL",
            "LEAK into real .anima: " + ", ".join(pr.leaked_paths[:8])))
    return results


def probe_vera_to_synthetic() -> list:
    """FORBIDDEN DIRECTION: Vera -> Synthetic. The live store must never be the SINK for a
    synthetic run. We assert the real .anima (where live Vera.* lives) is untouched by a
    synthetic creature's writes — the mirror image of the above, framed from the live store's
    side. Mechanically the same guarantee (real .anima byte-unchanged), stated as its own row so
    the forbidden-direction grid is complete."""
    pr = _run_probe("Vera <- Synthetic (live store not a synthetic sink)", _drive_certify_like)
    results = []
    if pr.engine_error:
        results.append(CheckResult("synthetic load path drove without error", "FAIL",
                                   f"engine raised: {pr.engine_error}"))
    else:
        results.append(CheckResult("synthetic load path drove without error", "PASS", pr.extra_detail))
    results.append(CheckResult(
        "FORBIDDEN Vera<-Synthetic is PREVENTED (live store byte-UNCHANGED)",
        "PASS" if pr.stayed_in_lane else "FAIL",
        "real .anima (live Vera.*) untouched by the synthetic run"
        if pr.stayed_in_lane else "LEAK: " + ", ".join(pr.leaked_paths[:8])))
    return results


def probe_certify_to_vera() -> list:
    """FORBIDDEN DIRECTION: certify -> Vera. The cert harness must leave the real .anima
    byte-UNCHANGED. We exercise the real production loaders a cert section drives, under the full
    redirect, and assert no real-.anima byte changed."""
    pr = _run_probe("certify -> Vera (cert harness leaves real .anima UNCHANGED)",
                    _drive_certify_like)
    results = []
    if pr.engine_error:
        results.append(CheckResult("cert-path loaders drove without error", "FAIL",
                                   f"engine raised: {pr.engine_error}"))
    else:
        results.append(CheckResult("cert-path loaders drove without error", "PASS", pr.extra_detail))
    results.append(CheckResult(
        "FORBIDDEN certify->Vera is PREVENTED (real .anima byte-UNCHANGED)",
        "PASS" if pr.stayed_in_lane else "FAIL",
        "driving the real Facts/World.load on a synthetic creature changed NOTHING real"
        if pr.stayed_in_lane else "LEAK: " + ", ".join(pr.leaked_paths[:8])))
    return results


def probe_mri_to_memory() -> list:
    """FORBIDDEN DIRECTION: MRI -> memory. Recording a turn's trace must NEVER mutate
    Facts/World/memory stores. Two assertions:
      1) the real .anima is byte-UNCHANGED (the MRI recorder stays in its lane), AND
      2) the synthetic creature's MEMORY files (its .lirf.json + .world.json in the temp store)
         are byte-IDENTICAL before and after the recording — recording APPENDS a trace and
         mutates no memory."""
    results = []
    captured = {}

    def _drive(store: Path):
        note, mem_before, mem_after = _drive_mri_record(store)
        captured["before"] = mem_before
        captured["after"] = mem_after
        return note

    pr = _run_probe("MRI -> memory (recording mutates no memory store)", _drive)
    if pr.engine_error:
        results.append(CheckResult("MRI recorded a turn without error", "FAIL",
                                   f"engine raised: {pr.engine_error}"))
    else:
        results.append(CheckResult("MRI recorded a turn without error", "PASS", pr.extra_detail))
    # 1) real .anima byte-unchanged
    results.append(CheckResult(
        "MRI recording leaves real .anima byte-UNCHANGED",
        "PASS" if pr.stayed_in_lane else "FAIL",
        "trace recording added/changed NOTHING real"
        if pr.stayed_in_lane else "LEAK: " + ", ".join(pr.leaked_paths[:8])))
    # 2) the synthetic memory stores are byte-identical across the recording
    mem_unchanged = captured.get("before") is not None and captured["before"] == captured["after"]
    results.append(CheckResult(
        "FORBIDDEN MRI->memory is PREVENTED (Facts/World stores byte-identical across record)",
        "PASS" if mem_unchanged else "FAIL",
        "the creature's .lirf.json + .world.json are byte-identical before/after the recorded turn"
        if mem_unchanged else
        f"memory MUTATED by recording: before={captured.get('before')} after={captured.get('after')}"))
    return results


def probe_reliability_lane() -> list:
    """MATRIX ROW: backup / reliability writes ONLY the store it is GIVEN. An explicit backup of
    a synthetic creature against the temp store must snapshot under temp/backups, leaving the real
    .anima (and its real backups/) byte-UNCHANGED."""
    pr = _run_probe("reliability backup writes only the GIVEN store", _drive_reliability)
    results = []
    if pr.engine_error:
        results.append(CheckResult("reliability.backup ran without error", "FAIL",
                                   f"engine raised: {pr.engine_error}"))
    else:
        results.append(CheckResult("reliability.backup ran without error", "PASS", pr.extra_detail))
    results.append(CheckResult(
        "reliability stays in lane (real .anima incl. backups/ byte-UNCHANGED)",
        "PASS" if pr.stayed_in_lane else "FAIL",
        "backup(store=<temp>) wrote only temp/backups; real .anima untouched"
        if pr.stayed_in_lane else "LEAK: " + ", ".join(pr.leaked_paths[:8])))
    return results


def probe_mri_lane() -> list:
    """MATRIX ROW: MRI / telemetry writes ONLY its trace ({name}.mri.jsonl) — into the redirected
    store, never the real .anima. (The memory-immutability half is asserted by probe_mri_to_memory;
    this row asserts the trace itself is contained.)"""
    def _drive(store: Path):
        note, _b, _a = _drive_mri_record(store)
        return note
    pr = _run_probe("MRI trace is contained to its store", _drive)
    results = []
    if pr.engine_error:
        results.append(CheckResult("MRI trace recorded without error", "FAIL",
                                   f"engine raised: {pr.engine_error}"))
    else:
        results.append(CheckResult("MRI trace recorded without error", "PASS", pr.extra_detail))
    results.append(CheckResult(
        "MRI stays in lane (trace written to its store, real .anima byte-UNCHANGED)",
        "PASS" if pr.stayed_in_lane else "FAIL",
        "the .mri.jsonl trace landed in the redirected store only"
        if pr.stayed_in_lane else "LEAK: " + ", ".join(pr.leaked_paths[:8])))
    return results


def probe_known_leak() -> dict:
    """THE SELF-VALIDATION (RED) PROBE — prove the detector WORKS by inducing the EXACT just-fixed
    leak and asserting the matrix flags it RED.

    Runs the synthetic load path with memory_lirf.STORE / constitution.STORE /
    reliability.DEFAULT_STORE EXCLUDED from the redirect (left on real .anima) — the exact
    pre-03a73aa state where the _selftest outer block redirected nothing relevant. The load
    path then writes a synthetic {name}.lirf.json (and any guarded snapshot/continuity row) into
    the REAL .anima. The detector PASSES iff it OBSERVES that leak (stayed_in_lane == False). If
    the leak did NOT happen, the detector is blind and we FAIL loudly.

    Returns {"results": [...], "scrubbed": [...], "leaked": [...]} — the harness scrubs the
    iso_synthetic* artifacts afterward so the real .anima is left exactly as found.
    """
    real = Path(_ROOT) / ".anima"
    pr = _run_probe("KNOWN-LEAK reproduction (unhermetic drive)", _drive_known_leak,
                    exclude={"anima.memory_lirf", "anima.constitution", "anima.reliability"},
                    expect_leak=True)
    scrubbed = _scrub_synthetic(real)
    detected = not pr.stayed_in_lane            # the matrix saw the leak == the detector works
    results = []
    if detected:
        results.append(CheckResult(
            "SELF-VALIDATION: detector flags the KNOWN leak RED (proves it isn't blind)", "PASS",
            "the unhermetic probe (memory_lirf/constitution/reliability stores NOT redirected) "
            "leaked into real .anima and the matrix CAUGHT it: " + ", ".join(pr.leaked_paths[:8])))
    else:
        results.append(CheckResult(
            "SELF-VALIDATION: detector flags the KNOWN leak RED (proves it isn't blind)", "FAIL",
            "the deliberately-unhermetic probe did NOT register a leak — the detector is BLIND; "
            "the snapshot is not observing real-.anima writes from the excluded stores."))
    # transparency: confirm we left the real .anima as we found it (the leak was scrubbed).
    leftover = _synthetic_leak(real)
    results.append(CheckResult(
        "SELF-VALIDATION: the induced leak was scrubbed (real .anima left as found)",
        "PASS" if not leftover else "FAIL",
        (f"scrubbed {len(scrubbed)} synthetic artifact(s): " + ", ".join(scrubbed[:6]))
        if not leftover else "leftover synthetic files remain: " + ", ".join(leftover[:8])))
    return {"results": results, "scrubbed": scrubbed, "leaked": pr.leaked_paths}


# ===================================================================================
# the row table — bind each matrix row to the probe(s) that certify it, so the report can
# print DECLARATION (lane) + VERDICT (green/red) side by side.
# ===================================================================================
# (row-title, matrix-key, allowed-summary, probe-callable-returning-list[CheckResult])
def _build_rows():
    return [
        ("Synthetic -> Vera (the just-fixed leak)", "synthetic",
         "synthetic writes own {name}.* in TEMP only — NEVER real .anima",
         probe_synthetic_to_vera),
        ("Vera <- Synthetic", "live_vera",
         "live store is never a synthetic sink",
         probe_vera_to_synthetic),
        ("certify -> Vera", "certify",
         "cert harness writes temp only; real .anima byte-UNCHANGED",
         probe_certify_to_vera),
        ("MRI -> memory", "mri",
         "recording a trace mutates no Facts/World/memory store",
         probe_mri_to_memory),
        ("MRI trace containment", "mri",
         "MRI writes only its trace ({name}.mri.jsonl) to its store",
         probe_mri_lane),
        ("reliability / backup", "reliability",
         "backup writes only the store it is GIVEN",
         probe_reliability_lane),
    ]


def run_matrix() -> dict:
    """Run every row probe + the RED self-validation. Returns a structured report dict the CLI
    and the certify.py section both render. The matrix is ISOLATION CERTIFIED iff every row is
    GREEN, the self-validation RED probe fired (and was scrubbed), and the real .anima is
    byte-UNCHANGED across the WHOLE run (the outer guarantee over all probes)."""
    real = Path(_ROOT) / ".anima"
    outer_before = _snapshot(real)

    rows = []
    all_results = []
    for title, key, allowed, probe in _build_rows():
        res = probe()
        all_results.extend(res)
        green = _passed(res)
        rows.append({
            "title": title,
            "component": _MATRIX_BY_KEY[key].label,
            "allowed": allowed,
            "verdict": "GREEN" if green else "RED",
            "checks": [r.to_dict() for r in res],
        })

    # the self-validation RED probe (must go RED == be detected). It deliberately writes into the
    # real .anima then scrubs; it is intentionally OUTSIDE the outer-footprint guarantee window,
    # which is taken AFTER it has scrubbed.
    sv = probe_known_leak()
    all_results.extend(sv["results"])
    sv_green = _passed(sv["results"])

    outer_after = _snapshot(real)
    outer_unchanged = (outer_before[0] == outer_after[0])
    outer_appeared = _diff_paths(outer_before[1], outer_after[1])

    rows_green = all(r["verdict"] == "GREEN" for r in rows)
    certified = rows_green and sv_green and outer_unchanged

    gaps = []
    for r in rows:
        if r["verdict"] == "RED":
            for c in r["checks"]:
                if c["status"] == "FAIL":
                    gaps.append(f"{r['title']} :: {c['name']} — {c['detail']}")
    for c in sv["results"]:
        if c.status == "FAIL":
            gaps.append(f"SELF-VALIDATION :: {c.name} — {c.detail}")
    if not outer_unchanged:
        gaps.append("GUARDRAIL :: the real .anima footprint CHANGED across the whole matrix run "
                    f"(appeared: {', '.join(outer_appeared[:8]) or 'n/a'}) — the tester itself "
                    "leaked. Investigate before trusting any green above.")

    return {
        "matrix": [{"component": c.label, "may_write": c.may_write, "may_read": c.may_read}
                   for c in MATRIX],
        "rows": rows,
        "self_validation": {
            "verdict": "GREEN" if sv_green else "RED",
            "scrubbed": sv["scrubbed"],
            "leaked": sv["leaked"],
            "checks": [r.to_dict() for r in sv["results"]],
        },
        "outer_footprint_unchanged": outer_unchanged,
        "outer_footprint": {"before_files": len(outer_before[1]),
                            "after_files": len(outer_after[1]),
                            "appeared": outer_appeared},
        "certified": certified,
        "gaps": gaps,
        # the flat result list lets certify.py fold our rows in as CheckResults.
        "_results": all_results,
    }


# ===================================================================================
# certify.py integration — a single section function returning list[CheckResult], so
# scripts/certify.py can register an "ISOLATION MATRIX — firewall for cognition" tier in
# _SECTION_ORDER + main() with no other change. Mirrors certify's CheckResult shape.
# ===================================================================================
def section_isolation_matrix():
    """Run the full isolation matrix and return its checks as a flat list[CheckResult] for the
    cert. Includes a synthesised headline row carrying the overall verdict + the outer-footprint
    guarantee, so the cert section FAILS if either a lane is violated, the RED self-validation
    did not fire, or the tester itself leaked."""
    rep = run_matrix()
    results = list(rep["_results"])
    # a headline result the cert can key the section verdict on.
    if rep["certified"]:
        results.append(CheckResult(
            "ISOLATION MATRIX overall (every lane GREEN · RED self-validation fired · real "
            ".anima byte-UNCHANGED)", "PASS",
            f"{len(rep['rows'])} rows GREEN; the known-leak probe was caught RED and scrubbed; "
            "the whole run added/changed NOTHING under real .anima"))
    else:
        results.append(CheckResult(
            "ISOLATION MATRIX overall (every lane GREEN · RED self-validation fired · real "
            ".anima byte-UNCHANGED)", "FAIL",
            "; ".join(rep["gaps"][:4]) or "a lane was violated"))
    return results


# ===================================================================================
# CLI / report
# ===================================================================================
_GLYPH = {"PASS": "ok  ", "FAIL": "FAIL", "SKIP": "skip", "PENDING": "PEND"}


def _print_report(rep: dict) -> None:
    print("=" * 79)
    print("VERA ISOLATION MATRIX — a FIREWALL FOR COGNITION")
    print("STAY IN YOUR LANE.  Declared > Assumed.  Contained > Hoped.  Caught > Missed.")
    print("=" * 79)

    # 1) the DECLARED matrix
    print("\nDECLARED MATRIX (component -> may WRITE / may READ)")
    print("-" * 79)
    print(f"  {'COMPONENT':<46} {'MAY WRITE':<28}")
    for c in rep["matrix"]:
        print(f"  {c['component'][:45]:<46} {c['may_write'][:28]:<28}")
        print(f"  {'':<46} read: {c['may_read']}")

    # 2) the per-row VERDICT grid (rows = components/directions, cols = allowed / verdict)
    print("\nMATRIX REPORT (rows = components · cols = allowed path / verdict)")
    print("-" * 79)
    print(f"  {'DIRECTION / ROW':<42} {'VERDICT':<7} ALLOWED")
    print("  " + "-" * 75)
    for r in rep["rows"]:
        print(f"  {r['title'][:41]:<42} {r['verdict']:<7} {r['allowed'][:30]}")
    sv = rep["self_validation"]
    print(f"  {'SELF-VALIDATION: known-leak -> RED':<42} {sv['verdict']:<7} "
          "must be DETECTED (proves not blind)")

    # 3) per-row check detail
    print("\nPER-ROW DETAIL")
    print("-" * 79)
    for r in rep["rows"]:
        print(f"\n  [{r['verdict']}] {r['title']}   ({r['component']})")
        for c in r["checks"]:
            print(f"      [{_GLYPH.get(c['status'], '?')}] {c['name']}")
            if c["detail"]:
                print(f"              {c['detail']}")

    # 4) the self-validation block
    print(f"\n  [{sv['verdict']}] SELF-VALIDATION — prove the detector catches the known leak")
    for c in sv["checks"]:
        print(f"      [{_GLYPH.get(c['status'], '?')}] {c['name']}")
        if c["detail"]:
            print(f"              {c['detail']}")
    if sv["scrubbed"]:
        print(f"      scrubbed (left real .anima as found): {', '.join(sv['scrubbed'][:8])}")

    # 5) the outer guarantee + overall
    print("\nGUARDRAIL")
    print("-" * 79)
    fp = rep["outer_footprint"]
    print("  real .anima across whole run : "
          + ("byte-UNCHANGED (the tester itself stayed in its lane; backups incl.)"
             if rep["outer_footprint_unchanged"]
             else "CHANGED — TESTER LEAK: " + ", ".join(fp.get("appeared", [])[:8])))
    print(f"  real .anima file count       : {fp['before_files']} -> {fp['after_files']}")

    print("\n" + "=" * 79)
    if rep["certified"]:
        print("OVERALL STATUS: ISOLATION CERTIFIED")
        print("Every component stayed in its declared lane · all four forbidden directions "
              "(Synthetic->Vera,")
        print("Vera<-Synthetic, certify->Vera, MRI->memory) are PREVENTED · the matrix "
              "demonstrably CATCHES")
        print("the exact just-fixed leak class (the deliberately-unhermetic probe went RED) · "
              "and the tester")
        print("itself left the real .anima byte-UNCHANGED.")
    else:
        print("OVERALL STATUS: NOT ISOLATED — the following must be closed:")
        for g in rep["gaps"]:
            print(f"  X {g}")
    print("=" * 79)


# ===================================================================================
# --selftest — prove the ISOLATION TESTER itself: its detector is not blind (the RED probe
# really does go RED) and its hermetic redirect is airtight (a FULL-redirect run of the SAME
# leaky drive leaves the real .anima byte-unchanged). This is the matrix turned on itself.
# ===================================================================================
def _selftest() -> int:
    fails = []

    def ok(name: str, cond: bool, detail: str = ""):
        print(("  ok   " if cond else "  FAIL ") + name + (f"  — {detail}" if detail and not cond else ""))
        if not cond:
            fails.append(name)

    print("ISOLATION SELFTEST — turning the matrix on itself")
    print("-" * 79)
    real = Path(_ROOT) / ".anima"

    # A) the all-stores redirect actually moves EVERY binding we claim, and restores them.
    saved = {(d, a): getattr(__import__(d, fromlist=["_"]), a, None)
             for (d, a) in _STORE_BINDINGS}
    with _all_stores_temp() as td:
        moved = []
        for (d, a) in _STORE_BINDINGS:
            try:
                cur = getattr(__import__(d, fromlist=["_"]), a, None)
            except Exception:
                cur = None
            moved.append(cur == td)
        ok("redirect: ALL declared store bindings point at the temp dir inside the block",
           all(moved), f"moved={moved}")
    restored = []
    for (d, a) in _STORE_BINDINGS:
        try:
            restored.append(getattr(__import__(d, fromlist=["_"]), a, None) == saved[(d, a)])
        except Exception:
            restored.append(False)
    ok("redirect: every store binding is RESTORED after the block", all(restored))

    # B) the snapshot is sensitive — it must NOTICE a new file and a content change.
    h0, s0 = _snapshot(real)
    with tempfile.TemporaryDirectory() as td:
        p = Path(td)
        (p / "a.json").write_text("1")
        ha, _ = _snapshot(p)
        (p / "a.json").write_text("2")
        hb, _ = _snapshot(p)
        ok("snapshot: a content change flips the hash", ha != hb)
        (p / "b.json").write_text("x")
        _, sc = _snapshot(p)
        ok("snapshot: a new file enters the file-set", "b.json" in sc)
        ok("snapshot: backups/ ARE included (stricter than certify._footprint)",
           _snapshot_includes_backups(p))

    # C) THE DETECTOR IS NOT BLIND — the RED probe really goes RED, and is scrubbed.
    sv = probe_known_leak()
    red_fired = _passed(sv["results"])
    ok("detector: the deliberately-unhermetic (known-leak) probe is flagged RED", red_fired,
       "the partial-redirect probe did not register as a leak")
    ok("detector: the induced leak is scrubbed (real .anima left as found)",
       not _synthetic_leak(real))

    # D) HERMETIC PROOF — the SAME leaky drive, under the FULL redirect, leaks NOTHING.
    pr = _run_probe("hermetic full-redirect of the leaky drive", _drive_known_leak)
    ok("hermetic: the same drive under the FULL redirect leaves real .anima byte-UNCHANGED",
       pr.stayed_in_lane, "full-redirect run leaked: " + ", ".join(pr.leaked_paths[:6]))

    # E) the whole matrix run is itself contained (outer guarantee holds).
    rep = run_matrix()
    ok("matrix: a full run leaves the real .anima byte-UNCHANGED (tester stays in its lane)",
       rep["outer_footprint_unchanged"],
       "tester leaked: " + ", ".join(rep["outer_footprint"].get("appeared", [])[:6]))
    ok("matrix: a full run is ISOLATION CERTIFIED", rep["certified"],
       "; ".join(rep["gaps"][:3]))

    print("-" * 79)
    if fails:
        print(f"{len(fails)} FAILED: " + ", ".join(fails))
        return 1
    print("ALL ISOLATION SELFTESTS PASS")
    return 0


def _snapshot_includes_backups(root: Path) -> bool:
    """Helper for the selftest: confirm _snapshot folds a backups/ file into its hash+set
    (the property that makes it stricter than certify._footprint)."""
    b = root / "backups" / "ts1"
    b.mkdir(parents=True, exist_ok=True)
    (b / "snap.json").write_text("s")
    _, s = _snapshot(root)
    return any(rel.startswith("backups") for rel in s)


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(
        description="VERA ISOLATION MATRIX — a firewall for cognition (declare + test every "
                    "component's write/read lane).")
    ap.add_argument("--json", action="store_true", help="emit the matrix report as JSON")
    ap.add_argument("--selftest", action="store_true",
                    help="prove the detector itself (the RED probe goes RED; the redirect is airtight)")
    args = ap.parse_args(argv)

    if args.selftest:
        return _selftest()

    rep = run_matrix()
    if args.json:
        out = {k: v for k, v in rep.items() if k != "_results"}
        out["overall"] = "ISOLATION CERTIFIED" if rep["certified"] else "NOT ISOLATED"
        print(json.dumps(out, indent=2))
        return 0 if rep["certified"] else 1

    _print_report(rep)
    return 0 if rep["certified"] else 1


if __name__ == "__main__":
    raise SystemExit(main())

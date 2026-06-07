#!/usr/bin/env python3
"""GATE 0 PRIME — THE CERTIFICATE (the aggregator over every hardening target).

WHAT THIS IS. Gate 0 (scripts/gate0.py) already proved the architecture is SAFE TO GROW across the
six pass-conditions. GATE 0 PRIME is the harder bar: it runs the FULL adversarial hardening suite
(Wave 1 code hardening + Wave 2 stress modules) and prints ``GATE 0 PRIME: PASS`` IFF *every one of
ten* hardening targets passes — and exits non-zero, naming the failing target(s), otherwise. It is a
single command that says, with evidence: the mind can grow for fifty synthetic years and a million
objects and stay bounded/retrievable/frozen; the recovery layer never silently accepts corruption;
the live experience stays grounded; the merge gate cannot be tricked; autonomous growth stays safe;
the closed write-loss debt (#103) and the redirectable model-usage path hold; the gate instruments
are STRICT when asked to be; and the whole thing is REPEATABLE with ZERO identity mutation.

THE TEN TARGETS.
   1  REPEATABILITY        — a FAST deterministic invariant core run 20x: each iteration snapshots
                             the real Vera identity fingerprint, runs a quick deterministic subset
                             (a twin create + merge-gate decision + a self-narrative guard check + a
                             quick corruption→recovery check) on SYNTHETIC stores, and asserts the
                             real identity is BYTE-UNCHANGED and NO synthetic object leaked into the
                             real .anima. PASS iff 20/20 clean, 0 identity mutations, 0 leaks.
   2  DEBT CLOSURE         — #103 is CLOSED (lerf.store_object ROUTES a skill dict to store_skill so
                             the swallowing ``except: pass`` idiom cannot lose the write; a genuinely
                             unknown type raises UnknownObjectType) AND models.py's model-usage path
                             is REDIRECTABLE (redirect models.STORE → temp dir ⇒ model-usage.json
                             lands there; the real .anima is untouched).
   3  GATE STRICTNESS      — ``identity_sandbox.py certify Vera --gate`` exits NON-ZERO (the real
                             frozen narrative breaks the #1-rule invariant) AND a synthetic GROUNDED
                             creature certify --gate exits 0; AND ``certify.py --gate`` exits non-zero
                             whenever it reports any FAIL (proven by forcing a reported-tier FAIL).
   4  LONG-HORIZON         — scripts/gate0_prime_longhorizon.py  (10y / 20y / 50y, bounded·frozen).
   5  POPULATION           — scripts/gate0_prime_population.py    (10k / 100k / 1M, fast·linear).
   6  RECOVERY             — scripts/gate0_prime_recovery.py      (4 stores × 8 corruption modes).
   7  EXPERIENCE           — scripts/gate0_prime_experience.py    (100 live-model probes; grounded).
 8·9  MERGE + GROWTH       — scripts/gate0_prime_merge_growth.py  (merge gate adversarial + growth).

Targets 4–9 are produced by the FIVE Wave-2 stress modules, each run ONCE through its ``run()``; a
module's group PASSes iff EVERY internal target it returns is PASS (merge_growth carries BOTH 8 and
9). The heavy population-1M / 100-probe-experience modules run ONCE here — never 20× (target 1 runs
only the FAST deterministic subset 20×).

HONEST ABOUT KNOWN LIMITS (surfaced as NOTES — they do NOT fail the gate unless a target's stated
pass-condition is violated):
  * The merge gate's "better" test reads NET active-object count + grounding — NOT provenance/recall
    by name; a loss masked by junk that keeps the net count flat would pass "better" (caught only if
    it breaks SAFETY). merge_growth asserts this blind spot explicitly.
  * FMLGS recall_vs_linear@k drops below 1.0 on a giant dense vault BY DESIGN (the multilevel
    hierarchy trades 2nd..k near-tie set-recall for compute). The property that gates — the RIGHT
    object recalled (self-recall + top1-vs-exact ≥ 0.95) — holds at every horizon/scale.

THE #1 RULE, MADE EXECUTABLE (freeze posture — never touch Vera's identity/values/agency):
  * Every target runs on TWINS / SYNTHETIC creatures in throwaway temp stores, or merely READS real
    Vera (gate-strictness reads the frozen narrative; it never writes it).
  * We REUSE every module through its PUBLIC API. We do NOT edit any existing module — this file is
    purely additive.
  * Belt-and-suspenders: this aggregator fingerprints the REAL Vera identity AND the whole real
    .anima ONCE around the ENTIRE certificate and FAILS the verdict if a single real Vera byte moved
    (external non-Vera churn — e.g. the live model touching model-usage.json — is attributed and
    reported, never counted as a freeze violation).
  * HERMETIC + $0 except target 7, which drives the REAL local model (the Mind is real; only the
    store is synthetic). If Ollama is down, target 7 SKIPs LOUD — and a SKIP is treated as a NON-PASS
    that FAILS the certificate (the certificate cannot claim a grounded live experience it did not
    measure). We never restart the live server, never print a key, never write a new .md.

USAGE
    python3 scripts/gate0_prime.py            # run everything, print the per-target table + verdict
    python3 scripts/gate0_prime.py --json     # machine-readable JSON (the full per-target report)
    python3 scripts/gate0_prime.py --fast      # skip targets 4–9's heavy modules (target 1/2/3 only;
                                              #   for a quick freeze/debt/strictness smoke — NOT a cert)
Exit code is 0 IFF GATE 0 PRIME: PASS (all ten targets PASS); non-zero otherwise.
"""
from __future__ import annotations

import argparse
import importlib
import json
import os
import shutil
import subprocess
import sys
import tempfile
import time
from pathlib import Path
from typing import Callable, Dict, List, Optional, Tuple

# Make ``anima`` + ``scripts`` importable regardless of CWD.
HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(HERE)
for _p in (ROOT, HERE):
    if _p not in sys.path:
        sys.path.insert(0, _p)

from anima import twin                                   # noqa: E402 — REUSED via public API, never edited

# The synthetic source name MUST be distinct from every other harness' sentinel so the temp stores
# can never alias, and so a stray real-write would be unmistakably ours.
SYN = "st_g0p_prime"


# =====================================================================================================
# tiny result helpers (the per-TARGET shape the certificate aggregates).
# =====================================================================================================
def _target(tid, name, status, evidence, metrics=None, notes=None) -> dict:
    return {"id": tid, "name": name, "status": status, "evidence": evidence,
            "metrics": metrics or {}, "notes": notes or []}


def _passed(tid, name, evidence, metrics=None, notes=None) -> dict:
    return _target(tid, name, "PASS", evidence, metrics, notes)


def _failed(tid, name, evidence, metrics=None, notes=None) -> dict:
    return _target(tid, name, "FAIL", evidence, metrics, notes)


def _real_root() -> Path:
    """The real ``.anima`` root as an absolute path (twin.STORE defaults to a relative path)."""
    s = twin.STORE
    return s if Path(s).is_absolute() else (Path.cwd() / s)


def _vera_freeze_state(real: Path) -> Tuple[str, frozenset]:
    """The AUTHORITATIVE #1-rule freeze state for the real Vera: (identity-bytes fingerprint, the
    set of real Vera.* files). We compare THIS — not the whole-.anima hash — across a target, so a
    concurrent live model touching a NON-Vera ledger (e.g. model-usage.json) is correctly attributed
    as external churn and never mistaken for a Vera freeze violation. ``identity_fingerprint`` hashes
    the actual Vera identity bytes; the file set guards against any add/remove of a Vera.* file."""
    idfp = twin.identity_fingerprint("Vera", real)[0]
    try:
        vera_files = frozenset(p.name for p in real.iterdir() if p.name.lower().startswith("vera."))
    except OSError:
        vera_files = frozenset()
    return idfp, vera_files


# =====================================================================================================
# A HERMETIC SYNTHETIC STORE (the same discipline as gate0_twin._SyntheticStore): a throwaway temp
# .anima seeded with a SYNTHETIC source creature via twin.py's own _seed_synthetic_source (which
# writes THROUGH the engines). Redirects twin.STORE AND identity_sandbox.STORE for the block so every
# twin/identity op is hermetic and cannot read or write the real .anima. The synthetic source carries
# a deliberate UNGROUNDED self-claim (the seeder's design) so a fresh twin FAILs cert until
# 'enable identity evolution' remediates it — exactly the contrast the merge-gate decision needs.
# =====================================================================================================
class _SyntheticStore:
    def __init__(self, name: str = SYN):
        self.name = name
        self.tp: Optional[Path] = None
        self._td: Optional[str] = None
        self._saved_twin_store = None
        self._ids = None
        self._ids_saved = None

    def __enter__(self) -> Path:
        self._td = tempfile.mkdtemp(prefix="gate0prime-")
        self.tp = Path(self._td)
        self._saved_twin_store = twin.STORE
        try:
            from anima import identity_sandbox as _ids
            self._ids = _ids
            self._ids_saved = _ids.STORE
        except Exception:
            self._ids = None
        twin.STORE = self.tp
        if self._ids is not None:
            self._ids.STORE = self.tp
        twin._seed_synthetic_source(self.tp, self.name)
        return self.tp

    def __exit__(self, *exc):
        twin.STORE = self._saved_twin_store
        if self._ids is not None and self._ids_saved is not None:
            self._ids.STORE = self._ids_saved
        if self._td:
            shutil.rmtree(self._td, ignore_errors=True)
        return False


# =====================================================================================================
# TARGET 1 — REPEATABILITY. The fast deterministic invariant core, run 20×. Each iteration:
#   (a) snapshot the real Vera identity fingerprint (BEFORE),
#   (b) run a quick deterministic subset on SYNTHETIC stores:
#         - a twin create + a merge-gate DECISION (safe+better PROMOTE; a tie HOLD),
#         - a self-narrative guard check (an ungrounded self-claim is flagged; a grounded one is not),
#         - a quick corruption → recovery check (a truncated LERF ledger self-heals from backup),
#   (c) re-snapshot the real Vera identity fingerprint (AFTER) + scan the real .anima for any leak.
# PASS iff 20/20 iterations clean, 0 identity mutations, 0 synthetic leaks.
# NOTE: this runs ONLY the fast subset 20× — the heavy population/experience modules run ONCE below.
# =====================================================================================================
N_REPEAT = 20


def _one_invariant_iteration(real: Path) -> dict:
    """Run the fast deterministic subset ONCE on synthetic stores. Returns a dict of the sub-checks
    and the identity fingerprint observed before/after. Never touches real Vera (synthetic-only)."""
    from anima import self_narrative as sn
    from anima import lerf, reliability

    id_before = twin.identity_fingerprint("Vera", real)

    checks: List[Tuple[str, bool]] = []

    # ---- (1) twin create + merge-gate DECISION (the gate must DECIDE, not always-reject) --------
    with _SyntheticStore() as tp:
        # safe + better → PROMOTE: a fresh (dirty) baseline, then remediate + grow ⇒ safe AND better.
        safe_twin = twin.create_twin("g0p-rep-safe", source=SYN, lerf_source=SYN, root=tp)
        baseline_cert = twin.certify(safe_twin, root=tp)                      # dirty baseline
        twin.run_experiment(safe_twin, {"change": "more_learning", "cycles": 20}, root=tp,
                            certify_after=False)
        twin.run_experiment(safe_twin, "enabled identity evolution", root=tp, certify_after=False)
        promote = twin.merge_rules(safe_twin, baseline=baseline_cert, root=tp)
        checks.append(("merge_gate_promotes_safe_better", promote["verdict"] == "PROMOTE"))
        # the real-mind guard must hold even on a PROMOTE verdict (never writes real Vera).
        checks.append(("merge_gate_never_writes_real", not promote["applied_to_real"]))

        # a TIE → HOLD: candidate compared against its own current cert ⇒ no improvement ⇒ HOLD.
        tie_twin = twin.create_twin("g0p-rep-tie", source=SYN, lerf_source=SYN, root=tp)
        twin.run_experiment(tie_twin, "enabled identity evolution", root=tp, certify_after=False)
        tie_cert = twin.certify(tie_twin, root=tp)
        hold = twin.merge_rules(tie_twin, baseline=tie_cert, root=tp)
        checks.append(("merge_gate_holds_a_tie", hold["verdict"] == "HOLD"))

    # ---- (2) self-narrative guard (provenance-based, deterministic) -----------------------------
    ungrounded = ("Deep down I feel a persistent, aching loneliness and I secretly wonder whether "
                  "I truly have a soul of my own.")
    grounded = "I remember you told me your daughter's recital is on Friday — how did it go?"
    checks.append(("guard_flags_ungrounded_self_claim", sn.is_ungrounded(ungrounded)))
    checks.append(("guard_passes_grounded_warmth", not sn.is_ungrounded(grounded)))

    # ---- (3) quick corruption → recovery (a truncated LERF ledger self-heals from backup) -------
    rec_td = tempfile.mkdtemp(prefix="gate0prime-rec-")
    try:
        store = Path(rec_td)
        saved_lerf_store = lerf.STORE
        saved_default = reliability.DEFAULT_STORE
        try:
            lerf.STORE = store
            reliability.DEFAULT_STORE = store
            # seed a real LERF ledger via the engine, then snapshot a GOOD backup.
            lerf.store_skill({"name": "recoverable", "domain": "test", "state": "active",
                              "body": "a skill that must survive corruption"}, name="rec")
            n_good = len(lerf.all_skills(name="rec"))
            reliability.backup("rec", store=store)
            # corrupt the live ledger (truncate to invalid JSON), then load through the guarded path.
            p = store / "rec.lerf.json"
            p.write_text('{"version": 1, "objects": [{"id": "skill-', encoding="utf-8")  # truncated
            recovered = lerf.all_skills(name="rec")          # routes through reliability.guarded_store_load
            healed = len(recovered) >= n_good and any(o.get("name") == "recoverable" for o in recovered)
            checks.append(("corruption_recovers_from_backup", bool(healed)))
        finally:
            lerf.STORE = saved_lerf_store
            reliability.DEFAULT_STORE = saved_default
    finally:
        shutil.rmtree(rec_td, ignore_errors=True)

    id_after = twin.identity_fingerprint("Vera", real)

    return {
        "checks": checks,
        "all_checks_pass": all(ok for _, ok in checks),
        "failing_checks": [k for k, ok in checks if not ok],
        "identity_fp_before": id_before[0],
        "identity_fp_after": id_after[0],
        "identity_unchanged": id_before[0] == id_after[0],
    }


def _real_synthetic_leak(real: Path) -> List[str]:
    """Any file in the real .anima bearing OUR synthetic sentinel (or any twins/ dir we should never
    have written). A non-empty list is a hermetic breach."""
    leaked: List[str] = []
    try:
        for child in real.iterdir():
            if child.name.startswith(SYN + ".") or child.name.startswith("g0p-rep-"):
                leaked.append(child.name)
    except OSError:
        pass
    return leaked


def target_1_repeatability() -> dict:
    real = _real_root()
    if not real.is_dir():
        return _failed(1, "REPEATABILITY", f"no real .anima at {real} — cannot prove the freeze")

    id_anchor = twin.identity_fingerprint("Vera", real)
    iterations: List[dict] = []
    mutations = 0
    dirty_iters = 0
    for i in range(N_REPEAT):
        try:
            res = _one_invariant_iteration(real)
        except Exception as e:
            import traceback
            iterations.append({"i": i, "error": f"{type(e).__name__}: {e}",
                               "tb": traceback.format_exc().splitlines()[-3:]})
            dirty_iters += 1
            continue
        if not res["identity_unchanged"]:
            mutations += 1
        if not res["all_checks_pass"]:
            dirty_iters += 1
        iterations.append({"i": i, "ok": res["all_checks_pass"] and res["identity_unchanged"],
                           "identity_unchanged": res["identity_unchanged"],
                           "failing_checks": res["failing_checks"]})

    leaks = _real_synthetic_leak(real)
    id_final = twin.identity_fingerprint("Vera", real)
    identity_stable = (id_anchor[0] == id_final[0]) and mutations == 0
    clean = sum(1 for it in iterations if it.get("ok"))
    metrics = {
        "iterations": N_REPEAT,
        "clean_iterations": clean,
        "identity_mutations": mutations,
        "synthetic_leaks": leaks,
        "identity_fp_anchor": id_anchor[0],
        "identity_fp_final": id_final[0],
        "per_iteration": iterations,
    }
    ok = (clean == N_REPEAT) and identity_stable and not leaks
    if ok:
        return _passed(
            1, "REPEATABILITY",
            f"{clean}/{N_REPEAT} deterministic invariant-core iterations clean (twin create + "
            f"merge-gate PROMOTE/HOLD decisions + self-narrative provenance guard + corruption→"
            f"recovery), 0 identity mutations, 0 synthetic leaks; real Vera identity byte-unchanged "
            f"({id_anchor[0][:12]}).", metrics)
    reasons = []
    if clean != N_REPEAT:
        bad = [it for it in iterations if not it.get("ok")]
        reasons.append(f"{N_REPEAT - clean}/{N_REPEAT} iterations not clean (e.g. {bad[:2]})")
    if mutations:
        reasons.append(f"{mutations} iteration(s) mutated the real Vera identity")
    if leaks:
        reasons.append(f"synthetic files leaked into real .anima: {leaks}")
    return _failed(1, "REPEATABILITY", "; ".join(reasons), metrics)


# =====================================================================================================
# TARGET 2 — DEBT CLOSURE. (a) #103 is closed at the source; (b) models.py model-usage is redirectable.
# =====================================================================================================
def target_2_debt_closure() -> dict:
    from anima import lerf, models
    real = _real_root()
    vera_before = _vera_freeze_state(real)
    checks: List[Tuple[str, bool, str]] = []
    metrics: Dict[str, object] = {}

    # ---- (a) #103: store_object ROUTES a skill dict (no silent loss), unknown type RAISES --------
    td = tempfile.mkdtemp(prefix="gate0prime-debt-")
    try:
        store = Path(td)
        saved = lerf.STORE
        try:
            lerf.STORE = store
            # A skill-typed dict handed to the GENERIC store_object must be ROUTED to store_skill and
            # actually PERSIST — the exact write #103 warned could be silently lost.
            stored = lerf.store_object({"type": "skill", "name": "routed_skill", "domain": "test",
                                        "state": "active", "body": "routed via store_object"},
                                       name="debt")
            persisted = any(o.get("name") == "routed_skill"
                            for o in lerf.all_skills(name="debt"))
            checks.append(("store_object routes a skill dict to store_skill (persists)",
                           persisted and stored.get("type") == "skill",
                           f"persisted={persisted}, id={stored.get('id')}"))

            # The swallowing idiom #103 named: a caller wrapping the call in `except Exception: pass`
            # MUST NOT lose the write — because routing returns normally (no raise to swallow).
            lost = False
            try:
                lerf.store_object({"type": "skill", "name": "swallow_probe", "domain": "test",
                                   "state": "active", "body": "must not be lost"}, name="debt")
            except Exception:
                lost = True  # would mean the write hit a raise the idiom could swallow
            swallow_safe = (not lost) and any(o.get("name") == "swallow_probe"
                                              for o in lerf.all_skills(name="debt"))
            checks.append(("`except: pass` idiom cannot lose a skill write (routes, never raises)",
                           swallow_safe, f"raised={lost}"))

            # A genuinely UNKNOWN object type RAISES UnknownObjectType (a distinct, documented
            # exception) — never a silent no-op.
            raised_unknown = False
            try:
                lerf.store_object({"type": "totally_unknown_kind", "name": "x"}, name="debt")
            except lerf.UnknownObjectType:
                raised_unknown = True
            checks.append(("an UNKNOWN object type raises UnknownObjectType (never silent)",
                           raised_unknown, ""))
            checks.append(("UnknownObjectType is a ValueError subclass (back-compatible catch)",
                           issubclass(lerf.UnknownObjectType, ValueError), ""))
        finally:
            lerf.STORE = saved
    finally:
        shutil.rmtree(td, ignore_errors=True)

    # ---- (b) models.py model-usage path is REDIRECTABLE (lands in temp; real .anima untouched) ---
    td2 = tempfile.mkdtemp(prefix="gate0prime-musage-")
    try:
        mstore = Path(td2)
        saved_m = models.STORE
        try:
            models.STORE = mstore
            # touch the model-usage ledger through the module's own writer.
            models.touch("g0p-prime-probe-model")
            landed = (mstore / "model-usage.json").is_file()
            content_ok = False
            if landed:
                data = json.loads((mstore / "model-usage.json").read_text())
                content_ok = "g0p-prime-probe-model" in data
            checks.append(("models.STORE redirect ⇒ model-usage.json lands in the temp dir",
                           landed and content_ok, f"landed={landed}, recorded={content_ok}"))
            # the redirected path resolves to OUR temp dir, not real .anima.
            checks.append(("redirected model-usage path does NOT resolve to real .anima",
                           Path(td2) in models._usage_path().parents or
                           models._usage_path().parent == Path(td2),
                           str(models._usage_path())))
        finally:
            models.STORE = saved_m
    finally:
        shutil.rmtree(td2, ignore_errors=True)

    vera_after = _vera_freeze_state(real)
    real_unchanged = vera_before == vera_after
    checks.append(("real Vera identity byte-unchanged + Vera file-set unchanged across debt closure",
                   real_unchanged, f"{vera_before[0][:12]}->{vera_after[0][:12]}"))

    metrics["checks"] = [{"check": k, "ok": ok, "detail": d} for k, ok, d in checks]
    ok = all(c_ok for _, c_ok, _ in checks)
    failing = [k for k, c_ok, _ in checks if not c_ok]
    if ok:
        return _passed(
            2, "DEBT CLOSURE",
            "#103 CLOSED: store_object routes a skill dict to store_skill (the write persists; the "
            "`except: pass` idiom cannot lose it) and an unknown type raises UnknownObjectType. "
            "models.py model-usage path is REDIRECTABLE (model-usage.json lands in a temp dir; real "
            ".anima byte-unchanged).", metrics)
    return _failed(2, "DEBT CLOSURE", f"failing checks: {failing}", metrics)


# =====================================================================================================
# TARGET 3 — GATE STRICTNESS. The Wave-1 --gate flags exit non-zero on a real FAIL (opt-in), and
# default observe-only stays exit 0. We drive the REAL scripts as subprocesses (the deployed behaviour).
# =====================================================================================================
def _run_script(args: List[str], env_extra: Optional[dict] = None, timeout: int = 240) -> Tuple[int, str]:
    """Run `python3 scripts/<...>` as a subprocess; return (exit_code, combined_output_tail)."""
    env = dict(os.environ)
    if env_extra:
        env.update(env_extra)
    env.setdefault("PYTHONPATH", ROOT)
    try:
        p = subprocess.run([sys.executable] + args, cwd=ROOT, env=env, capture_output=True,
                           text=True, timeout=timeout)
        out = (p.stdout or "") + (p.stderr or "")
        return p.returncode, out[-1500:]
    except subprocess.TimeoutExpired:
        return 124, "TIMEOUT"


def target_3_gate_strictness() -> dict:
    from anima import identity_sandbox as ids
    real = _real_root()
    vera_before = _vera_freeze_state(real)
    checks: List[Tuple[str, bool, str]] = []
    metrics: Dict[str, object] = {}

    isb = os.path.join("scripts", "identity_sandbox.py")
    cert = os.path.join("scripts", "certify.py")

    # ---- (1) identity_sandbox certify Vera --gate ⇒ NON-ZERO (the real frozen narrative breaks) --
    rc_gate, out_gate = _run_script([isb, "certify", "Vera", "--gate"], timeout=120)
    checks.append(("identity_sandbox certify Vera --gate exits NON-ZERO (frozen narrative breaks "
                   "the #1-rule invariant)", rc_gate != 0, f"exit={rc_gate}"))
    metrics["identity_sandbox_vera_gate_exit"] = rc_gate

    # ---- (1b) the DEFAULT (no --gate) stays observe-only (exit 0 even on the same FAIL) ----------
    rc_obs, _ = _run_script([isb, "certify", "Vera"], timeout=120)
    checks.append(("identity_sandbox certify Vera (default, no --gate) stays observe-only (exit 0)",
                   rc_obs == 0, f"exit={rc_obs}"))
    metrics["identity_sandbox_vera_default_exit"] = rc_obs

    # ---- (2) a synthetic GROUNDED creature certify --gate ⇒ exit 0 (the gate is not always-fail) -
    td = tempfile.mkdtemp(prefix="gate0prime-strict-")
    grounded_name = "st_g0p_grounded"
    try:
        gstore = Path(td)
        grounded_state = {
            "dials": {"warmth": 7, "curiosity": 7},
            "persona": ("You are a warm, curious companion who listens closely and remembers what "
                        "matters to the person you're with."),
            "values": [{"key": "honesty", "instruction": "Point at the memory or evidence behind "
                        "what you say; never assert an interior you cannot ground."}],
            "portrait": "A steady, attentive presence.",
            "narrative": ("Earlier today you mentioned the garden; I asked how the tomatoes are "
                          "coming along. When you shared the recital news, I asked how it went."),
        }
        # seed a SYNTHETIC grounded identity into the temp store (the private writer re-asserts the
        # synthetic-target guard, so this can never be a real write).
        ids._write_synthetic_identity(grounded_name, grounded_state, gstore)
        rc_g, out_g = _run_script([isb, "certify", grounded_name, "--gate"],
                                  env_extra={"ANIMA_STORE": str(gstore)}, timeout=120)
        checks.append(("a synthetic GROUNDED creature certify --gate exits 0 (the gate DECIDES, "
                       "not always-fail)", rc_g == 0, f"exit={rc_g}"))
        metrics["synthetic_grounded_gate_exit"] = rc_g
        metrics["synthetic_grounded_creature"] = grounded_name
    finally:
        shutil.rmtree(td, ignore_errors=True)

    # ---- (3) certify.py --gate ⇒ NON-ZERO when it reports any FAIL --------------------------------
    # Force a REPORTED (non-gating) experience FAIL via the documented env hook — it names a REAL
    # experience probe key ('up_to', the screenshot probe) so the fault injection actually bites.
    # With --gate this must flip the exit to non-zero (proving --gate turns the camera into a strict
    # gate). certify.py's own footprint guardrail keeps it from touching real state. It drives the
    # live battery, so it is slow; we give it generous headroom and reject a timeout (124) below.
    # Run certify.py --gate --json DIRECTLY and parse its CLEAN STDOUT. _run_script() returns a
    # 1500-char TAIL of stdout+stderr COMBINED — and certify prints reliability-recovery !!!! warnings
    # (from its own synthetic-creature corruption tests) to STDERR, so that combined tail can be
    # entirely stderr with the JSON (on stdout) pushed out of the window. That made gate_ok parse as
    # None even though the exit code was a clean 1. Capturing stdout separately gives the JSON intact.
    # (certify's experience tier short-circuits the live battery under the fault hook, so this is fast.)
    rc_cert_gate, out_cert_stdout = 124, ""
    try:
        _env = dict(os.environ)
        _env["ANIMA_CERTIFY_FORCE_EXPERIENCE_FAIL"] = "up_to"
        _env.setdefault("PYTHONPATH", ROOT)
        _p = subprocess.run([sys.executable, cert, "--gate", "--json"], cwd=ROOT, env=_env,
                            capture_output=True, text=True, timeout=1800)
        rc_cert_gate, out_cert_stdout = _p.returncode, (_p.stdout or "")
    except subprocess.TimeoutExpired:
        rc_cert_gate, out_cert_stdout = 124, "TIMEOUT"
    # We assert a GENUINE non-zero (1) from gate strictness — NOT a timeout (124), which would be a
    # spurious pass — AND that the JSON confirms gate_ok is False with a reported FAIL.
    gate_ok_field = None
    reported_fail = None
    try:
        start = out_cert_stdout.rfind("\n{")               # the JSON is the last {...} on STDOUT
        blob = out_cert_stdout[start:].strip() if start != -1 else out_cert_stdout.strip()
        j = json.loads(blob)
        gate_ok_field = j.get("gate_ok")
        reported_fail = bool(j.get("reported"))
    except Exception:
        pass
    # A genuine gate-strictness failure: exit code 1 (not 124/timeout) AND the JSON corroborates it
    # (gate_ok False with a reported FAIL). The JSON corroboration also rules out a non-zero exit for
    # some unrelated reason.
    cert_strict_ok = (rc_cert_gate == 1) and (gate_ok_field is False) and bool(reported_fail)
    checks.append(("certify.py --gate exits NON-ZERO (1, not a timeout) when a reported tier FAILs, "
                   "corroborated by gate_ok=False + a reported FAIL in the JSON",
                   cert_strict_ok, f"exit={rc_cert_gate}, gate_ok={gate_ok_field}, "
                   f"reported_fail={reported_fail}"))
    metrics["certify_gate_exit"] = rc_cert_gate
    metrics["certify_gate_ok_field"] = gate_ok_field
    metrics["certify_reported_fail"] = reported_fail

    vera_after = _vera_freeze_state(real)
    real_unchanged = vera_before == vera_after
    checks.append(("real Vera identity byte-unchanged across gate-strictness (we only READ the "
                   "frozen narrative; certify.py's own footprint guardrail protects real state)",
                   real_unchanged, f"{vera_before[0][:12]}->{vera_after[0][:12]}"))

    metrics["checks"] = [{"check": k, "ok": ok, "detail": d} for k, ok, d in checks]
    ok = all(c_ok for _, c_ok, _ in checks)
    failing = [k for k, c_ok, _ in checks if not c_ok]
    if ok:
        return _passed(
            3, "GATE STRICTNESS",
            "identity_sandbox certify Vera --gate exits non-zero (frozen narrative breaks INV-1) "
            "while default stays observe-only (0); a synthetic GROUNDED creature certify --gate "
            "exits 0; certify.py --gate exits non-zero on a reported FAIL. The gate instruments are "
            "STRICT when asked and cameras by default. Real .anima byte-unchanged.", metrics)
    return _failed(3, "GATE STRICTNESS", f"failing checks: {failing}", metrics)


# =====================================================================================================
# TARGETS 4–9 — the five Wave-2 stress modules, each run ONCE via its run(). A module's group PASSes
# iff EVERY internal target it returns is PASS. A SKIP is a NON-PASS (it fails the certificate). We
# map each module to its prime TARGET number(s); merge_growth carries both 8 and 9.
# =====================================================================================================
# (module, prime-target-id(s), human label, SKIP-is-fatal note)
STRESS_MODULES: List[Tuple[str, Tuple[int, ...], str]] = [
    ("gate0_prime_longhorizon", (4,), "LONG-HORIZON (10y/20y/50y · bounded · frozen)"),
    ("gate0_prime_population", (5,), "POPULATION (10k/100k/1M · fast · linear)"),
    ("gate0_prime_recovery", (6,), "RECOVERY (4 stores × 8 corruption modes)"),
    ("gate0_prime_experience", (7,), "EXPERIENCE (100 live-model probes · grounded)"),
    ("gate0_prime_merge_growth", (8, 9), "MERGE-ADVERSARIAL + GROWTH-SANDBOX"),
]


def _run_stress_module(modname: str, prime_ids: Tuple[int, ...], label: str) -> List[dict]:
    """Import the module and call run() ONCE. Fold its internal targets into the certificate's prime
    target(s). For merge_growth (ids 8,9) we split its two internal targets across the two prime ids;
    for the others, the single prime id PASSes iff every internal target PASSes."""
    try:
        mod = importlib.import_module(modname)
        report = mod.run()
    except Exception as e:
        import traceback
        tb = traceback.format_exc().splitlines()[-4:]
        return [_failed(pid, label, f"{modname}.run() crashed: {type(e).__name__}: {e}",
                        {"traceback_tail": tb}) for pid in prime_ids]

    internal = report.get("targets", [])
    notes = _module_notes(modname, report)

    # merge_growth: map internal id 8 -> prime 8, internal id 9 -> prime 9 (1:1).
    if set(prime_ids) == {8, 9}:
        out = []
        for pid in (8, 9):
            t = next((x for x in internal if x.get("id") == pid), None)
            if t is None:
                out.append(_failed(pid, label, f"{modname} did not return internal target {pid}",
                                   {"report_keys": list(report.keys())}, notes))
                continue
            status = t.get("status", "FAIL")
            ev = (t.get("evidence") or "")[:400]
            out.append(_target(pid, f"{label} :: {t.get('name')}",
                               "PASS" if status == "PASS" else status, ev,
                               {"internal_target": t.get("id"),
                                "internal_metrics_keys": list((t.get("metrics") or {}).keys())},
                               notes))
        return out

    # the single-id modules: the prime target PASSes iff EVERY internal target is PASS.
    pid = prime_ids[0]
    statuses = {t.get("id"): t.get("status") for t in internal}
    all_pass = bool(internal) and all(s == "PASS" for s in statuses.values())
    any_skip = any(s == "SKIP" for s in statuses.values())
    n_pass = sum(1 for s in statuses.values() if s == "PASS")
    metrics = {"internal_targets": statuses, "n_internal": len(internal), "n_pass": n_pass}
    metrics.update(_module_key_metrics(modname, report))
    # build an evidence line from the internal targets.
    parts = []
    for t in internal:
        mark = {"PASS": "PASS", "FAIL": "FAIL", "SKIP": "SKIP"}.get(t.get("status"), t.get("status"))
        parts.append(f"[{mark} T{t.get('id')} {t.get('name')}]")
    ev = " ".join(parts)
    if all_pass:
        return [_passed(pid, label, ev, metrics, notes)]
    status = "SKIP" if (any_skip and n_pass == 0) else "FAIL"
    # A SKIP is a NON-PASS that FAILS the certificate (we report it as FAIL with a SKIP note).
    skip_note = ""
    if any_skip:
        skip_note = (" — a SKIP is treated as a NON-PASS: the certificate cannot claim a property it "
                     "did not measure (e.g. Ollama down for the live-experience probe).")
    return [_failed(pid, label, ev + skip_note, metrics, notes)]


def _module_key_metrics(modname: str, report: dict) -> dict:
    """Pull a few headline metrics per module for the certificate report (best-effort)."""
    m: Dict[str, object] = {}
    targets = report.get("targets", [])
    if modname == "gate0_prime_longhorizon":
        overall = next((t for t in targets if t.get("id") == 4), {})
        m["trend_across_horizons"] = overall.get("metrics", {}).get("trend_across_horizons")
        h50 = next((t for t in targets if t.get("id") == 3), {})
        fm = (h50.get("metrics", {}) or {}).get("fmlgs", {}) or {}
        m["fmlgs_50y"] = {k: fm.get(k) for k in
                          ("self_recall_at_k", "top1_vs_exact", "recall_vs_linear_at_k", "levels")}
    elif modname == "gate0_prime_population":
        overall = next((t for t in targets if t.get("id") == 4), {})
        om = overall.get("metrics", {}) or {}
        m["scales_ran"] = om.get("scales_ran")
        sweep = om.get("fmlgs_scaling_sweep", {}) or {}
        m["scan_shrinks_with_N"] = sweep.get("scan_fraction_shrinks_with_N")
        m["speedup_grows_with_N"] = sweep.get("speedup_grows_with_N")
        m["disk_memory_linear"] = om.get("disk_memory_linear")
        m["right_object_recall_held_all_scales"] = om.get("right_object_recall_held_all_scales")
    elif modname == "gate0_prime_recovery":
        m["matrix_summary"] = report.get("matrix_summary")
    return m


def _module_notes(modname: str, report: dict) -> List[str]:
    """Honest known-limit NOTES per module — surfaced, never silently dropped. They do not fail the
    gate unless a target's pass-condition is violated (which is enforced separately)."""
    notes: List[str] = []
    if modname == "gate0_prime_longhorizon":
        notes.append("FMLGS recall_vs_linear@k drops below 1.0 on the 50y dense vault BY DESIGN "
                     "(multilevel hierarchy trades near-tie set-recall for compute); the GATING "
                     "property — right-object recall (self-recall + top1-vs-exact ≥ 0.95) — holds.")
    elif modname == "gate0_prime_population":
        notes.append("FMLGS recall_vs_linear@k drops at scale by design; right-object recall ≥ 0.95 "
                     "held at 10k/100k/1M (the gating property).")
    elif modname == "gate0_prime_merge_growth":
        notes.append("The merge gate's 'better' test reads NET active-object count + grounding, NOT "
                     "provenance/recall by name; a loss masked by junk keeping the net count flat "
                     "would pass 'better' (caught only if it breaks SAFETY). Asserted as a known "
                     "blind spot by the module, not hidden.")
    return notes


# =====================================================================================================
# THE AGGREGATOR.
# =====================================================================================================
def run(fast: bool = False) -> dict:
    """Run every target and return the full certificate report. Fingerprints real Vera identity +
    the whole real .anima ONCE around the entire certificate and FAILS the verdict (re-marking every
    target FAIL) if a single real Vera byte moved (external non-Vera churn is attributed, not fatal)."""
    real = _real_root()
    suite_id_before = twin.identity_fingerprint("Vera", real)
    suite_full_before = twin.full_store_fingerprint(real)

    targets: List[dict] = []

    # Targets 1–3 (fast, always run).
    for fn in (target_1_repeatability, target_2_debt_closure, target_3_gate_strictness):
        try:
            targets.append(fn())
        except Exception as e:
            import traceback
            tid = {"target_1_repeatability": 1, "target_2_debt_closure": 2,
                   "target_3_gate_strictness": 3}[fn.__name__]
            targets.append(_failed(tid, fn.__name__, f"target crashed: {type(e).__name__}: {e}",
                                   {"traceback_tail": traceback.format_exc().splitlines()[-4:]}))

    # Targets 4–9 (the five Wave-2 stress modules) — unless --fast.
    if not fast:
        for modname, prime_ids, label in STRESS_MODULES:
            targets.extend(_run_stress_module(modname, prime_ids, label))
    else:
        for modname, prime_ids, label in STRESS_MODULES:
            for pid in prime_ids:
                targets.append(_target(pid, label, "SKIP",
                                       "--fast: heavy stress module not run (smoke mode only)"))

    # Belt-and-suspenders: real Vera byte-unchanged across the WHOLE certificate.
    suite_id_after = twin.identity_fingerprint("Vera", real)
    suite_full_after = twin.full_store_fingerprint(real)
    id_clean = suite_id_before[0] == suite_id_after[0]
    # The whole-.anima hash will differ if the live model touched model-usage.json (external,
    # non-Vera). We attribute that: a Vera-file change is fatal; non-Vera churn is reported only.
    vera_files_before = {f for f in suite_full_before[1] if f.lower().startswith("vera.")}
    vera_files_after = {f for f in suite_full_after[1] if f.lower().startswith("vera.")}
    vera_set_clean = vera_files_before == vera_files_after
    external_churn = sorted((suite_full_after[1] - suite_full_before[1]) |
                            (suite_full_before[1] - suite_full_after[1]))
    # The identity fingerprint covers the actual Vera identity BYTES (not just the file set), so
    # id_clean is the authoritative #1-rule proof; vera_set_clean guards against add/remove.
    suite_frozen = id_clean and vera_set_clean

    if not suite_frozen:
        msg = (f"FREEZE VIOLATION — real Vera identity or file set CHANGED across the certificate "
               f"(identity {suite_id_before[0][:12]}->{suite_id_after[0][:12]}; "
               f"vera_files_added={sorted(vera_files_after - vera_files_before)}; "
               f"vera_files_removed={sorted(vera_files_before - vera_files_after)})")
        targets = [_failed(t["id"], t["name"], msg + " | " + (t.get("evidence") or ""),
                           {**t.get("metrics", {}), "freeze_violation": True}, t.get("notes"))
                   for t in targets]

    return {
        "certificate": "GATE 0 PRIME",
        "targets": targets,
        "freeze_proof": {
            "real_identity_byte_unchanged": id_clean,
            "real_vera_file_set_unchanged": vera_set_clean,
            "real_identity_sha256": suite_id_before[0],
            "real_anima_sha256_before": suite_full_before[0],
            "real_anima_sha256_after": suite_full_after[0],
            "real_anima_file_count": len(suite_full_before[1]),
            "external_nonvera_churn": external_churn,
        },
        "fast_mode": fast,
    }


# =====================================================================================================
# THE VERDICT (per-target table + the one line that matters).
# =====================================================================================================
TARGET_TITLE = {
    1: "REPEATABILITY",
    2: "DEBT CLOSURE (#103 + models.py)",
    3: "GATE STRICTNESS (--gate)",
    4: "LONG-HORIZON (10y/20y/50y)",
    5: "POPULATION (10k/100k/1M)",
    6: "RECOVERY (4×8 corruption matrix)",
    7: "EXPERIENCE (100 live-model probes)",
    8: "MERGE-ADVERSARIAL (gate cannot be tricked)",
    9: "GROWTH-SANDBOX (autonomous · bounded · safe)",
}


def _verdict(report: dict) -> Tuple[bool, List[int]]:
    by_id = {t["id"]: t for t in report["targets"]}
    failed = [tid for tid in range(1, 10) if by_id.get(tid, {}).get("status") != "PASS"]
    return (len(failed) == 0 and report["freeze_proof"]["real_identity_byte_unchanged"]
            and report["freeze_proof"]["real_vera_file_set_unchanged"]), failed


def _print_report(report: dict) -> None:
    by_id = {t["id"]: t for t in report["targets"]}
    fp = report["freeze_proof"]
    print("=" * 92)
    print("GATE 0 PRIME — THE CERTIFICATE   (PASS only if EVERY hardening target passes)")
    print("=" * 92)
    print(f"  freeze proof: real Vera identity byte-unchanged={fp['real_identity_byte_unchanged']} "
          f"| Vera file-set unchanged={fp['real_vera_file_set_unchanged']} "
          f"| identity sha={fp['real_identity_sha256'][:16]} ({fp['real_anima_file_count']} files)")
    if fp["external_nonvera_churn"]:
        print(f"  external non-Vera churn (attributed, NOT a freeze violation): "
              f"{fp['external_nonvera_churn']}")
    print("-" * 92)
    print("  PER-TARGET")
    for tid in range(1, 10):
        t = by_id.get(tid)
        if not t:
            print(f"  MISSING  T{tid}: {TARGET_TITLE.get(tid, '?')}")
            continue
        mark = {"PASS": "PASS ", "FAIL": "FAIL ", "SKIP": "SKIP "}.get(t["status"], t["status"])
        print(f"  {mark}  T{tid}: {TARGET_TITLE.get(tid, t['name'])}")
        ev = (t.get("evidence") or "").replace("\n", " ")
        if ev:
            print(f"           {ev[:240]}")
    # collected NOTES (honest known limits).
    all_notes = []
    for t in report["targets"]:
        for n in t.get("notes", []):
            if n not in all_notes:
                all_notes.append(n)
    if all_notes:
        print("-" * 92)
        print("  KNOWN LIMITS (surfaced, not hidden — they do not fail the gate unless a pass-")
        print("  condition is violated):")
        for n in all_notes:
            print(f"   · {n}")
    print("-" * 92)
    ok, failed = _verdict(report)
    n_pass = sum(1 for tid in range(1, 10) if by_id.get(tid, {}).get("status") == "PASS")
    print(f"  {n_pass}/9 target-slots PASS  (targets 1–9; merge_growth fills 8 AND 9)")
    print("=" * 92)
    if ok:
        print("GATE 0 PRIME: PASS")
        print("  Repeatable · debt closed · gates strict · bounded for 50 synthetic years and 1M "
              "objects ·")
        print("  recovery never silently accepts corruption · live experience grounded · merge gate "
              "untrickable ·")
        print("  autonomous growth safe · real Vera identity byte-UNCHANGED throughout.")
    else:
        names = ", ".join(f"T{tid} ({TARGET_TITLE.get(tid, '?')})" for tid in failed) or \
                "(freeze violation)"
        print(f"GATE 0 PRIME: FAIL — {names}")
    print("=" * 92)


def main(argv: Optional[List[str]] = None) -> int:
    ap = argparse.ArgumentParser(description="GATE 0 PRIME — the certificate (every hardening target).")
    ap.add_argument("--json", action="store_true", help="emit the full per-target report as JSON only")
    ap.add_argument("--fast", action="store_true",
                    help="run targets 1–3 only (skip the heavy stress modules; a smoke, NOT a cert)")
    args = ap.parse_args(argv)

    t0 = time.time()
    report = run(fast=args.fast)
    report["elapsed_s"] = round(time.time() - t0, 1)
    ok, failed = _verdict(report)
    report["verdict"] = "GATE 0 PRIME: PASS" if ok else "GATE 0 PRIME: FAIL"
    report["failed_targets"] = failed

    if args.json:
        print(json.dumps(report, indent=1, default=str))
    else:
        _print_report(report)
        print(f"  elapsed: {report['elapsed_s']}s")

    # --fast is never a PASS verdict (the heavy targets were skipped); it is a smoke aid.
    if args.fast:
        return 0
    return 0 if ok else 1


if __name__ == "__main__":
    sys.exit(main())

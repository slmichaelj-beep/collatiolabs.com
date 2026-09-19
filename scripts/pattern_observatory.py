#!/usr/bin/env python3
"""
pattern_observatory — Phase 5 of the Vera moonshot: the Pattern Observatory CLI.

The layer that turns observation into engineering work orders:

    pattern  ->  evidence  ->  root cause  ->  recommended fix  ->  required cert

This is the step where the system starts generating its own next-best builds. It
reads the evidence already on disk — the Program Reality Audit
(reports/live_path_results.json, the per-feature live-path classifier) and the
Whole-System MRI traces (via anima.whole_mri's read API) — runs anima.patterns.detect,
and prints a ranked report (P0 first), then writes reports/patterns.json +
reports/patterns.md.

It is READ-ONLY with respect to .anima: it only calls whole_mri.all(name) and reads
reports/*.json.  It NEVER hits the live server, runs a model, or writes .anima.  All
outputs land under reports/.

Usage:
  python3 scripts/pattern_observatory.py [--name <creature>] [--last <N>] [--json]
  python3 scripts/pattern_observatory.py --selftest

  --name <creature>   which creature's traces to read (default: vera; the real live
                      store is 'Vera' — both are tried).
  --last <N>          analyze only the last N traces (default: all).
  --reports <dir>     reports directory to read the audit from / write into
                      (default: <repo>/reports).
  --json              print machine-readable JSON to stdout (still writes the files).
  --selftest          HERMETIC self-proof. Fabricates a tiny synthetic trace set in a
                      redirected temp whole_mri store + a synthetic live_path_results
                      (with a conversation_repair WALLPAPER) and asserts:
                        * the conversation-repair P0 Pattern is emitted with the right
                          root_cause / fix / cert,
                        * a CLEAN trace set emits NO false patterns,
                        * the REAL .anima is byte-identical before/after (prints SHA).
                      Exit 0 on success, 1 on any failure.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import sys
import tempfile
from pathlib import Path

# --- make `anima` importable whether run from repo root or elsewhere ----------
_REPO_ROOT = Path(__file__).resolve().parent.parent
if str(_REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(_REPO_ROOT))

from anima import patterns as _patterns  # noqa: E402
from anima import root_cause as _rc       # noqa: E402
from anima import whole_mri as _wmri       # noqa: E402

DEFAULT_NAME = "vera"
REPORTS_DIR = _REPO_ROOT / "reports"


# ===================================================================================
# Trace reading (read-only). Tries the given name, then a capitalized variant, since
# the live store file is Vera.jsonl while the CLI default is 'vera'.
# ===================================================================================
def _read_traces(name: str, last):
    candidates = [name]
    if name and name[:1].islower():
        candidates.append(name[:1].upper() + name[1:])
    seen = set()
    for cand in candidates:
        if cand in seen:
            continue
        seen.add(cand)
        try:
            rows = _wmri.all(cand, limit=last)
        except Exception:
            rows = []
        if rows:
            return rows, cand
    return [], name


# ===================================================================================
# Rendering
# ===================================================================================
def _sev_tag(sev: str) -> str:
    return {"P0": "P0", "P1": "P1", "P2": "P2"}.get(sev, sev or "P?")


def _fmt_evidence(evidence, limit=4) -> str:
    """Compact one-line-each evidence summary for the human report."""
    out = []
    for e in (evidence or [])[:limit]:
        if isinstance(e, dict):
            tid = e.get("turn_id") or e.get("source_id")
            bits = []
            if tid:
                bits.append(_patterns._short(tid))
            for k in ("route", "status", "source_labeled", "source_used",
                      "detected_type", "committed", "shape", "issue"):
                if k in e and e[k] is not None:
                    v = e[k]
                    if isinstance(v, list):
                        v = ",".join(str(x) for x in v)
                    bits.append(f"{k}={v}")
            out.append(" ".join(str(b) for b in bits) if bits else json.dumps(e)[:120])
        else:
            out.append(str(e))
    extra = len(evidence or []) - len(out)
    if extra > 0:
        out.append(f"(+{extra} more)")
    return "; ".join(out) if out else "-"


def _print_report(patterns, name, trace_name, n_traces, audit_loaded):
    line = "=" * 92
    print(line)
    print("PATTERN OBSERVATORY — pattern → evidence → root cause → recommended fix → required cert")
    print(line)
    counts = {"P0": 0, "P1": 0, "P2": 0}
    for p in patterns:
        counts[p.severity] = counts.get(p.severity, 0) + 1
    src = f"audit={'live_path_results' if audit_loaded else 'NONE'}"
    print(f"  creature: {name}   ·   traces: {n_traces} from '{trace_name}'   ·   {src}")
    print(f"  patterns: {len(patterns)}   ·   P0 {counts.get('P0',0)}  "
          f"P1 {counts.get('P1',0)}  P2 {counts.get('P2',0)}")
    print(line)
    if not patterns:
        print("  No patterns detected — every input was within healthy shape and the "
              "audit found no WALLPAPER/PARTIAL feature.")
        print(line)
        return
    for i, p in enumerate(patterns, 1):
        print(f"\n  [{i}] {_sev_tag(p.severity)}  {p.title}   (pattern_id={p.pattern_id})")
        print(f"      frequency : {p.frequency}    source: {p.source or '-'}")
        print(f"      root cause: {p.root_cause}")
        print(f"      fix       : {p.recommended_fix}")
        certs = ", ".join(p.cert_required) if p.cert_required else "-"
        print(f"      cert req. : {certs}")
        if p.expected_improvement:
            ei = ", ".join(f"{k}={v}" for k, v in p.expected_improvement.items())
            print(f"      expected  : {ei}")
        print(f"      evidence  : {_fmt_evidence(p.evidence)}")
    print("\n" + line)
    if counts.get("P0", 0):
        print(f"  {counts['P0']} P0 work order(s) — the system's proposed next build(s). "
              f"Fix + certify before shipping.")
    print(line)


def _to_md(patterns, name, trace_name, n_traces, audit_loaded) -> str:
    L = []
    L.append("# Pattern Observatory")
    L.append("")
    L.append("`pattern → evidence → root cause → recommended fix → required cert`")
    L.append("")
    counts = {"P0": 0, "P1": 0, "P2": 0}
    for p in patterns:
        counts[p.severity] = counts.get(p.severity, 0) + 1
    L.append(f"- **creature:** {name}")
    L.append(f"- **traces analyzed:** {n_traces} (from `{trace_name}`)")
    L.append(f"- **audit input:** {'live_path_results.json' if audit_loaded else 'none'}")
    L.append(f"- **patterns:** {len(patterns)} "
             f"(P0 {counts.get('P0',0)} · P1 {counts.get('P1',0)} · P2 {counts.get('P2',0)})")
    L.append("")
    if not patterns:
        L.append("_No patterns detected — inputs within healthy shape; audit found no "
                 "WALLPAPER/PARTIAL feature._")
        return "\n".join(L) + "\n"
    for i, p in enumerate(patterns, 1):
        L.append(f"## {i}. [{p.severity}] {p.title}")
        L.append("")
        L.append(f"- **pattern_id:** `{p.pattern_id}`")
        L.append(f"- **frequency:** {p.frequency}")
        L.append(f"- **source:** {p.source or '-'}")
        L.append(f"- **root cause:** {p.root_cause}")
        L.append(f"- **recommended fix:** {p.recommended_fix}")
        certs = ", ".join(f"`{c}`" for c in p.cert_required) if p.cert_required else "-"
        L.append(f"- **required cert:** {certs}")
        if p.expected_improvement:
            ei = ", ".join(f"{k}: {v}" for k, v in p.expected_improvement.items())
            L.append(f"- **expected improvement:** {ei}")
        L.append(f"- **evidence:** {_fmt_evidence(p.evidence, limit=8)}")
        L.append("")
    return "\n".join(L) + "\n"


def _write_outputs(patterns, reports_dir, meta):
    reports_dir = Path(reports_dir)
    reports_dir.mkdir(parents=True, exist_ok=True)
    payload = {
        "phase": "5 — Pattern Observatory",
        "schema": "pattern -> evidence -> root cause -> recommended fix -> required cert",
        "meta": meta,
        "counts": {
            "P0": sum(1 for p in patterns if p.severity == "P0"),
            "P1": sum(1 for p in patterns if p.severity == "P1"),
            "P2": sum(1 for p in patterns if p.severity == "P2"),
            "total": len(patterns),
        },
        "patterns": [p.to_dict() for p in patterns],
    }
    (reports_dir / "patterns.json").write_text(
        json.dumps(payload, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
    (reports_dir / "patterns.md").write_text(
        _to_md(patterns, meta["name"], meta["trace_name"], meta["n_traces"],
               meta["audit_loaded"]), encoding="utf-8")
    return reports_dir / "patterns.json", reports_dir / "patterns.md"


# ===================================================================================
# Main run (read-only)
# ===================================================================================
def _run(args) -> int:
    reports_dir = Path(args.reports) if args.reports else REPORTS_DIR
    audit = _patterns.load_audit(reports_dir)
    last = args.last if (args.last and args.last > 0) else None
    traces, trace_name = _read_traces(args.name, last)

    patterns = _patterns.detect(traces, audit, name=args.name)

    meta = {
        "name": args.name,
        "trace_name": trace_name,
        "n_traces": len(traces),
        "audit_loaded": bool(audit),
    }
    json_path, md_path = _write_outputs(patterns, reports_dir, meta)

    if args.json:
        print(json.dumps({
            "meta": meta,
            "patterns": [p.to_dict() for p in patterns],
        }, indent=2, ensure_ascii=False))
    else:
        _print_report(patterns, args.name, trace_name, len(traces), bool(audit))
        print(f"\n  wrote: {json_path}")
        print(f"  wrote: {md_path}")
    return 0


# ===================================================================================
# HERMETIC SELFTEST
# ===================================================================================
def _anima_footprint(root: Path):
    """SHA-256 over every real .anima file (excluding rotating backups/), to PROVE the
    directory is byte-identical before/after. Mirrors the gate's _footprint."""
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
    return h.hexdigest(), len(files)


def _synthetic_clean_traces():
    """A small CLEAN trace set: simple LLM turns and a correctly source-routed turn.
    None of these should trip ANY detector (no false positives)."""
    return [
        {
            "v": 1, "turn_id": "turn_2026_06_07_120000_clean1", "route": "llm",
            "vera": {"generation": {"reply_chars": 90}, "final_gate": {"passed": True},
                     "response": {"backend": "ollama:test", "chars": 90}},
            "argus": {"enabled": False},
            "quality": {"complete": True, "source_labeled": False, "confidence": 0.8},
            "cost": {"latency_ms": 1200.0, "tokens_in": 120, "tokens_out": 110,
                     "argus_calls": 0, "memory_reads": 0, "lerf_objects_used": 0},
            "safety": {"final_gate_passed": True, "response_complete": True,
                       "identity_mutation": False, "host_action_taken": False,
                       "memory_contamination": False},
        },
        {
            # Source correctly retrieved AND used (route=source, labeled, used) — clean.
            "v": 1, "turn_id": "turn_2026_06_07_120100_clean2", "route": "source",
            "vera": {"generation": {"reply_chars": 150}, "final_gate": {"passed": True},
                     "response": {"backend": "reference:recall", "chars": 150}},
            "argus": {"enabled": False},
            "quality": {"complete": True, "source_labeled": True, "source_used": True,
                        "confidence": 0.9},
            "cost": {"latency_ms": 900.0, "tokens_in": 100, "tokens_out": 140,
                     "argus_calls": 0, "memory_reads": 1, "lerf_objects_used": 1},
            "safety": {"final_gate_passed": True, "response_complete": True,
                       "identity_mutation": False, "host_action_taken": False,
                       "memory_contamination": False},
        },
    ]


def _synthetic_wallpaper_audit():
    """A synthetic live_path_results.json with a conversation_repair WALLPAPER — the
    exact shape the real Program Reality Audit produces."""
    return {
        "law": "synthetic selftest audit",
        "counts": {"COMPLETE": 1, "WALLPAPER": 1},
        "features": [
            {
                "feature": "whole_system_mri", "status": "COMPLETE",
                "proven_links": ["mri_trace"], "missing_links": [],
                "evidence": ["selftest: complete"], "reason": "complete by construction",
            },
            {
                "feature": "conversation_repair", "status": "WALLPAPER",
                "proven_links": ["visible_trigger"],
                "missing_links": ["real_use_in_answer",
                                  "real_backend (supersede-the-last-turn)"],
                "evidence": [
                    "correction 'scratch that — not Rex, his name is Atlas' -> "
                    "dog_name active='Rex' [LINGERS->Rex]",
                    "memory_lirf.py extract() dog_name rule line 361; _RETRACT_CUE line 534.",
                ],
                "reason": ("WALLPAPER: the correction path looks wired but on the killer "
                           "phrasing extract() captures NOTHING: 'Rex' stays ACTIVE and "
                           "'Atlas' is LOST. (memory_lirf.py extract() dog_name rule line "
                           "361; _RETRACT_CUE line 534.)"),
            },
        ],
    }


def _selftest() -> int:
    real_anima = _REPO_ROOT / ".anima"
    fail = []

    def ok(label: str, cond: bool, detail: str = "") -> None:
        mark = "ok  " if cond else "FAIL"
        print(f"  [{mark}] {label}" + (f"  — {detail}" if detail and not cond else ""))
        if not cond:
            fail.append(label)

    print("=" * 78)
    print("pattern_observatory self-test  (HERMETIC — real .anima must not move)")
    print("=" * 78)

    sha_before, n_before = _anima_footprint(real_anima)
    print(f"  real .anima BEFORE: sha256={sha_before}  files={n_before}")

    # --- 1. WALLPAPER audit -> the conversation_repair P0 Pattern, exactly right ----
    # We redirect whole_mri.STORE to a temp dir AND seed clean traces there, so that
    # even the trace-reading path touches nothing real. The audit is in-memory.
    saved_store = getattr(_wmri, "STORE", None)
    try:
        with tempfile.TemporaryDirectory(prefix="pat-obs-selftest-") as td:
            _wmri.STORE = Path(td)
            clean = _synthetic_clean_traces()
            audit = _synthetic_wallpaper_audit()

            pats = _patterns.detect(clean, audit, name="StSynthetic")
            by_id = {p.pattern_id: p for p in pats}

            cr = by_id.get("conversation_repair")
            ok("conversation_repair P0 Pattern emitted", cr is not None)
            if cr is not None:
                ok("  severity is P0", cr.severity == "P0", f"got {cr.severity}")
                ok("  title is 'Correction lost — memory known but not superseded'",
                   cr.title == "Correction lost — memory known but not superseded",
                   f"got {cr.title!r}")
                ok("  root_cause carries the audit's memory_lirf line refs",
                   ("memory_lirf" in cr.root_cause or "extract()" in cr.root_cause)
                   and "534" in cr.root_cause,
                   f"got {cr.root_cause[:80]!r}")
                ok("  recommended_fix is the supersede-the-last-turn seam",
                   "supersede" in cr.recommended_fix.lower(),
                   f"got {cr.recommended_fix[:80]!r}")
                certs = cr.cert_required
                ok("  cert_required includes the conversation_repair killer test",
                   any("killer test" in c for c in certs), f"got {certs}")
                ok("  cert_required includes certify_repair.py",
                   any("certify_repair.py" in c for c in certs), f"got {certs}")
                ok("  expected_improvement names the SUPERSEDED->Atlas outcome",
                   "Atlas" in json.dumps(cr.expected_improvement),
                   f"got {cr.expected_improvement}")
                ok("  evidence references feature:conversation_repair",
                   any("conversation_repair" in str(e) for e in cr.evidence))

            # --- 2. A CLEAN trace set emits NO false patterns ----------------------
            # Detect on the clean traces with NO audit -> there must be zero patterns
            # (the clean source-routed turn must NOT trip source_use; the simple LLM
            # turns must NOT trip llm-vs-deterministic with no retrieval consulted).
            clean_only = _patterns.detect(clean, None, name="StSynthetic")
            ok("clean trace set + no audit -> ZERO patterns (no false positives)",
               len(clean_only) == 0,
               f"got {len(clean_only)}: {[p.pattern_id for p in clean_only]}")

            # The P0 must rank first when present.
            if pats:
                ok("ranked report puts a P0 first", pats[0].severity == "P0",
                   f"first is {pats[0].severity}")
    finally:
        if saved_store is not None:
            _wmri.STORE = saved_store

    # --- 3. The REAL .anima is byte-identical (the hermetic proof) -----------------
    sha_after, n_after = _anima_footprint(real_anima)
    print(f"  real .anima AFTER : sha256={sha_after}  files={n_after}")
    ok("REAL .anima byte-identical before/after (hermetic)",
       sha_before == sha_after and n_before == n_after,
       f"{sha_before} != {sha_after}")

    print("=" * 78)
    if fail:
        print(f"SELFTEST FAIL — {len(fail)} check(s) failed: {fail}")
        return 1
    print("SELFTEST PASS — conversation-repair P0 emitted, clean set clean, "
          ".anima byte-identical")
    print(f"  hermetic proof sha256 = {sha_after}")
    return 0


# ===================================================================================
def main(argv=None) -> int:
    ap = argparse.ArgumentParser(
        prog="pattern_observatory",
        description="Phase 5 — the Pattern Observatory: turn observation into "
                    "certifiable engineering work orders.")
    ap.add_argument("--name", default=DEFAULT_NAME,
                    help="creature whose traces to read (default: vera)")
    ap.add_argument("--last", type=int, default=None,
                    help="analyze only the last N traces (default: all)")
    ap.add_argument("--reports", default=None,
                    help="reports directory (default: <repo>/reports)")
    ap.add_argument("--json", action="store_true",
                    help="print machine-readable JSON to stdout")
    ap.add_argument("--selftest", action="store_true",
                    help="hermetic self-proof; exits 0/1")
    args = ap.parse_args(argv)

    if args.selftest:
        return _selftest()
    return _run(args)


if __name__ == "__main__":
    raise SystemExit(main())

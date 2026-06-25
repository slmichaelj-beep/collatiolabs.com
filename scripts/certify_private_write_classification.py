#!/usr/bin/env python3
"""certify_private_write_classification — every production direct writer is classified.

This is the static guardrail for W03. It does not pretend that every direct write is bad:
reports, cert fixtures, temp audio, installers, and user-chosen exports are real product
surfaces. But a private local companion cannot allow mystery persistence. Any new direct
writer in anima/ must either move to secure_store/util crypto helpers or land here with an
explicit classification and reason.

Exit 0 == all direct writes are classified; known pending privacy surfaces are named.
"""
from __future__ import annotations

import ast
import collections
import sys
import time
from dataclasses import dataclass
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
ANIMA = ROOT / "anima"
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))


@dataclass(frozen=True)
class WriteSite:
    path: str
    function: str
    kind: str
    line: int
    source: str


class _Visitor(ast.NodeVisitor):
    def __init__(self, path: Path, lines: list[str]):
        self.path = path
        self.lines = lines
        self.stack: list[str] = []
        self.sites: list[WriteSite] = []

    def visit_FunctionDef(self, node: ast.FunctionDef) -> None:
        self.stack.append(node.name)
        self.generic_visit(node)
        self.stack.pop()

    visit_AsyncFunctionDef = visit_FunctionDef

    def _name(self, node: ast.AST) -> str:
        if isinstance(node, ast.Name):
            return node.id
        if isinstance(node, ast.Attribute):
            parent = self._name(node.value)
            return (parent + "." if parent else "") + node.attr
        return ""

    def _str(self, node: ast.AST) -> str:
        return node.value if isinstance(node, ast.Constant) and isinstance(node.value, str) else ""

    def _mode(self, node: ast.Call, *, attr_open: bool) -> str:
        vals = []
        # builtins/wave.open(path, mode); Path.open(mode)
        if attr_open:
            vals.extend(self._str(a) for a in node.args[:2])
        elif len(node.args) >= 2:
            vals.append(self._str(node.args[1]))
        for kw in node.keywords:
            if kw.arg == "mode":
                vals.append(self._str(kw.value))
        return next((v for v in vals if any(c in v for c in "wax+")), "")

    def visit_Call(self, node: ast.Call) -> None:
        name = self._name(node.func)
        kind = ""
        if name.endswith(".write_text"):
            kind = "write_text"
        elif name.endswith(".write_bytes"):
            kind = "write_bytes"
        elif name == "os.open":
            kind = "os_open"
        elif name.endswith(".mkstemp") or name.endswith(".NamedTemporaryFile"):
            kind = "tempfile"
        elif name.endswith(".dump"):
            kind = "dump"
        elif name == "open" or name.endswith(".open"):
            mode = self._mode(node, attr_open=(name != "open"))
            if mode:
                kind = "open:" + mode
        if kind:
            rel = self.path.relative_to(ROOT).as_posix()
            fn = self.stack[-1] if self.stack else "<module>"
            src = self.lines[node.lineno - 1].strip()
            self.sites.append(WriteSite(rel, fn, kind, node.lineno, src))
        self.generic_visit(node)


def _scan() -> list[WriteSite]:
    out: list[WriteSite] = []
    for path in sorted(ANIMA.rglob("*.py")):
        text = path.read_text(encoding="utf-8")
        tree = ast.parse(text, filename=str(path))
        v = _Visitor(path, text.splitlines())
        v.visit(tree)
        out.extend(v.sites)
    return out


def _classify(s: WriteSite) -> tuple[str, str]:
    """Return (classification, reason). Empty classification means the cert must fail."""
    p, f, src = s.path, s.function, s.source

    if p in {"anima/secure_store.py", "anima/util.py", "anima/crypto.py"}:
        return ("crypto_substrate", "the shared encrypted/atomic persistence substrate itself")
    if p in {"anima/world_state.py", "anima/world_model.py"} and f in {"save_json", "load_json"}:
        return ("isolation_fallback", "standalone fallback; package runtime imports util.save_json/load_json")

    if f.startswith("_selftest") or f in {"_ingest_synthetic", "_seed_stalled",
                                          "_seed_synthetic_source", "_valid_creature"}:
        return ("test_fixture", "synthetic cert/selftest fixture, not live product persistence")
    if p in {"anima/rover/soak.py"}:
        return ("test_fixture", "rover soak creates/corrupts synthetic fixture state")
    if p == "anima/intake_queue.py" and f == "_ingest_synthetic":
        return ("test_fixture", "synthetic intake corpus")

    if p == "anima/server.py" and f in {"_transcribe", "_tts", "_warm"}:
        return ("private_temp_audio", "short-lived temp audio bridge, deleted after use where applicable")
    if p == "anima/server.py" and f == "__enter__":
        return ("private_temp_materialization", "short-lived decrypted parser handoff for sealed intake staging")
    if p == "anima/call_loop.py":
        return ("private_temp_audio", "short-lived call-loop audio temp files")

    if p == "anima/portrait.py" and f == "log_turn":
        return ("crypto_aware_legacy", "manual crypto.maybe_encrypt per JSONL line")
    if p == "anima/portrait.py" and f == "clear_log":
        return ("crypto_aware_archive", "appends already sealed chat-log bytes before clearing the working log")

    if p == "anima/reliability.py" and f == "backup":
        return ("backup_manifest", "self-describing backup metadata; copied private files stay byte-identical")
    if p == "anima/reliability.py" and f == "restore":
        return ("restore_tempfile", "same-directory temp path for atomic restore")
    if p == "anima/vault_backup.py" and f == "_write_owner_only":
        return ("encrypted_backup_bundle", "owner-only encrypted bundle write / confirmed restore after hash and path validation")
    if p == "anima/vault_keys.py" and f == "_write_owner_only_text":
        return ("vault_key_rotation", "owner-only rewrite of already-encrypted vault files during key rotation")
    if p == "anima/nightly.py":
        return ("installer_config", "macOS launchd plist, not Vera private memory")

    if p in {"anima/identity.py", "anima/portable.py", "anima/platform.py", "anima/forge.py"}:
        return ("PENDING_plaintext_export", "user-chosen portable/export/training artifact needs encrypted export option")

    report_prefixes = (
        "anima/verification/",
        "anima/host/",
        "anima/commercial/",
    )
    report_files = {
        "anima/improvement_engine.py",
        "anima/system_shape.py",
        "anima/twin_dashboard.py",
    }
    if p.startswith(report_prefixes) or p in report_files:
        return ("public_report", "generated reports/cert artifacts, not private creature memory")

    if p == "anima/observation_harness/bundle.py":
        return ("PENDING_diagnostic_bundle_export", "diagnostic bundle can hold observations; needs encrypted export option")

    if p == "anima/intake_audio.py":
        return ("test_fixture", "synthetic invalid audio fixture")
    if p == "anima/intake_worker.py" and f == "_selftest":
        return ("test_fixture", "synthetic worker document")

    return ("", "")


def main() -> int:
    t0 = time.perf_counter()
    sites = _scan()
    rows = []
    unclassified = []
    pending = []
    counts = collections.Counter()
    for s in sites:
        cls, reason = _classify(s)
        if not cls:
            unclassified.append(s)
            continue
        counts[cls] += 1
        rows.append((s, cls, reason))
        if cls.startswith("PENDING_"):
            pending.append((s, cls, reason))

    print("PRIVATE WRITE CLASSIFICATION — direct writers are inventoried and classified")
    print("=" * 88)
    print(f"  scanned sites: {len(sites)}")
    for cls, n in sorted(counts.items()):
        print(f"  {cls:34s} {n}")

    if pending:
        print("\nKNOWN PENDING PRIVACY SURFACES (classified, not forgotten):")
        for s, cls, reason in pending:
            print(f"  - {cls}: {s.path}:{s.line} {s.function} — {reason}")

    if unclassified:
        print("\nUNCLASSIFIED DIRECT WRITES:")
        for s in unclassified:
            print(f"  - {s.path}:{s.line} {s.function} {s.kind}: {s.source}")

    fails = []
    if unclassified:
        fails.append("unclassified direct write sites exist")

    green = not fails
    try:
        from anima.verification.cert_result import emit
        observed = ["scripts/certify_private_write_classification.py"]
        observed.extend(str(p.relative_to(ROOT)) for p in sorted(ANIMA.rglob("*.py")))
        emit("certify_private_write_classification", "green" if green else "red",
             files_observed=observed,
             evidence_paths=["reports/cert_results/certify_private_write_classification.json"],
             failures=fails,
             warnings=[f"{len(pending)} pending privacy write surfaces are classified"]
             if pending else [],
             next_action=("Build encrypted export/package options"
                          if pending else ""),
             duration_sec=time.perf_counter() - t0)
    except Exception as e:
        print("  (emit failed: %r)" % e)

    print("\nPRIVATE-WRITE-CLASSIFICATION CERT: " + ("CERTIFIED" if green else f"FAIL ({len(fails)})"))
    return 0 if green else 1


if __name__ == "__main__":
    raise SystemExit(main())

#!/usr/bin/env python3
"""certify_exception_safety_taxonomy - broad exceptions are visible and safety-domained.

This cert does not pretend the repo has no broad exception handlers. It proves the current
truthful posture:

  A. every broad handler in anima/ is inventoried and assigned a fail-policy domain;
  B. corrupt Truth/Observation lines surface as conflict records, not silent drops;
  C. consent persistence failures fail closed/loud instead of reporting success;
  D. malformed approval expiry cannot silently extend authority;
  E. zero-egress and malformed passkey auth degrade to visible denials.

Exit 0 == CERTIFIED.
"""
from __future__ import annotations

import ast
import json
import os
import subprocess
import sys
import tempfile
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

REPORT = ROOT / "reports" / "exception_safety_taxonomy.json"

DOMAIN_POLICIES = {
    "privacy_security_auth": "fail closed, return a visible denial, or emit a high-risk event",
    "governance_money_external_action": "fail closed and record a blocked action/verdict",
    "egress_cloud_network": "deny egress or return a visible error; never silently call out",
    "durable_truth_memory": "raise or surface corruption/conflict as data",
    "surface_runtime_visibility": "visible degradation only; no safety decision may depend on it",
    "optional_runtime_analysis": "best-effort is allowed only outside authority/privacy/money gates",
}


def _git(*args: str) -> str:
    try:
        return subprocess.run(["git", *args], cwd=str(ROOT), capture_output=True,
                              text=True, timeout=10).stdout.strip()
    except Exception:
        return ""


def _broad_type(node: ast.ExceptHandler) -> str:
    if node.type is None:
        return "bare"
    if isinstance(node.type, ast.Name) and node.type.id in ("Exception", "BaseException"):
        return node.type.id
    if isinstance(node.type, ast.Tuple):
        names = [x.id for x in node.type.elts if isinstance(x, ast.Name)]
        if any(x in ("Exception", "BaseException") for x in names):
            return "tuple:" + ",".join(names)
    return ""


def _domain(path: str) -> str:
    p = path.replace("\\", "/")
    if any(x in p for x in ("passkey", "consent", "privacy", "permission", "secure_store",
                            "crypto", "vault", "auth", "incident")):
        return "privacy_security_auth"
    if any(x in p for x in ("company_operator", "marketplaces", "foundry", "revenue",
                            "commercial", "sales", "budget", "approval", "action_ledger")):
        return "governance_money_external_action"
    if any(x in p for x in ("webget", "cloud", "egress", "mail", "browser", "host_apps")):
        return "egress_cloud_network"
    if any(x in p for x in ("truth", "observation", "memory", "whole_mri", "intake",
                            "ledger", "rollback")):
        return "durable_truth_memory"
    if any(x in p for x in ("server", "rover", "dashboard", "surface", "telemetry",
                            "metrics", "ui_", "route")):
        return "surface_runtime_visibility"
    return "optional_runtime_analysis"


def _scan_broad_handlers() -> dict:
    handlers = []
    by_domain = {k: 0 for k in DOMAIN_POLICIES}
    by_file: dict[str, int] = {}
    for path in sorted((ROOT / "anima").rglob("*.py")):
        rel = path.relative_to(ROOT).as_posix()
        try:
            src = path.read_text(encoding="utf-8")
            tree = ast.parse(src)
        except Exception as e:
            handlers.append({"file": rel, "line": 0, "type": "parse_error",
                             "domain": _domain(rel), "policy": DOMAIN_POLICIES[_domain(rel)],
                             "error": e.__class__.__name__})
            continue
        for node in ast.walk(tree):
            if not isinstance(node, ast.ExceptHandler):
                continue
            broad = _broad_type(node)
            if not broad:
                continue
            domain = _domain(rel)
            by_domain[domain] += 1
            by_file[rel] = by_file.get(rel, 0) + 1
            body_kinds = [type(x).__name__ for x in node.body[:4]]
            handlers.append({"file": rel, "line": int(getattr(node, "lineno", 0)),
                             "type": broad, "domain": domain,
                             "policy": DOMAIN_POLICIES[domain],
                             "body_kinds": body_kinds})
    return {"total": len(handlers), "by_domain": by_domain,
            "top_files": sorted(by_file.items(), key=lambda x: (-x[1], x[0]))[:25],
            "handlers": handlers}


oks: list[str] = []
fails: list[str] = []


def ck(label: str, cond: bool):
    (oks if cond else fails).append(label)
    print(("  ok   " if cond else "  XX   ") + label)


def _write_corrupt_jsonl(path: Path) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text('{"ok": true}\n{this is not json}\n', encoding="utf-8")


def _behavior_checks() -> list[dict]:
    evidence = []
    with tempfile.TemporaryDirectory(prefix="vera-exception-safety-") as td:
        st = Path(td)
        name = "ExceptionSafetyCert"

        from anima.truth import ledger as truth_ledger
        from anima.observation import store as observation_store
        from anima.consent import policy as consent_policy
        from anima.consent import schema as consent_schema
        from anima.company_operator import approvals, authority
        from anima import passkey, webget

        _write_corrupt_jsonl(truth_ledger.path_for(name, st))
        truth_rows = truth_ledger.load(name, store=st)
        truth_corrupt = any(x.get("_corrupt") and x.get("active_status") == "conflict"
                            for x in truth_rows)
        ck("1. corrupt Truth Ledger lines surface as conflict records", truth_corrupt)
        evidence.append({"check": "truth_corrupt_line_visible", "ok": truth_corrupt})

        _write_corrupt_jsonl(observation_store.path_for(name, st))
        obs_rows = observation_store.load(name, store=st)
        obs_corrupt = any(x.get("_corrupt") and x.get("status") == "conflict"
                          and x.get("kind") == "observation_corrupt" for x in obs_rows)
        ck("2. corrupt Observation lines surface as conflict records", obs_corrupt)
        evidence.append({"check": "observation_corrupt_line_visible", "ok": obs_corrupt})

        old_store = consent_policy.STORE
        old_save_json = consent_policy.secure_store.save_json
        consent_policy.STORE = st

        def boom(*_args, **_kwargs):
            raise OSError("simulated consent store failure")

        try:
            consent_policy.secure_store.save_json = boom
            denied = consent_policy.set_consent(name, "memory_write", "health", "granted")
        finally:
            consent_policy.secure_store.save_json = old_save_json
            consent_policy.STORE = old_store
        consent_failed_closed = (
            denied.get("ok") is False
            and "persisted" in denied.get("error", "")
            and consent_policy.status(name, "memory_write", "health")
            == consent_schema.default_status("memory_write", "health")
        )
        ck("3. consent save failure returns a visible failure and leaves safe default",
           consent_failed_closed)
        evidence.append({"check": "consent_persist_failure_fail_closed",
                         "ok": consent_failed_closed})

        authority.set_level(name, 4, store=st)
        ap = approvals.create(name, "Invalid expiry approval", "send",
                              expires_at="not-a-date", store=st)["approval"]
        approvals.decide(name, ap["approval_id"], "approved", store=st)
        verdict = approvals.validate_for_action(name, ap["approval_id"], "send_message", store=st)
        expiry_closed = verdict.get("ok") is False and "expiry invalid" in verdict.get("reason", "")
        ck("4. malformed approval expiry fails closed instead of becoming no-expiry",
           expiry_closed)
        evidence.append({"check": "approval_invalid_expiry_fail_closed", "ok": expiry_closed})

        old_zero = os.environ.get("ANIMA_ZERO_EGRESS")
        os.environ["ANIMA_ZERO_EGRESS"] = "1"
        try:
            blocked = webget.fetch("https://example.com", ["example.com"], name=name)
        finally:
            if old_zero is None:
                os.environ.pop("ANIMA_ZERO_EGRESS", None)
            else:
                os.environ["ANIMA_ZERO_EGRESS"] = old_zero
        zero_blocks = blocked.get("ok") is False and "zero-egress" in blocked.get("error", "")
        ck("5. zero-egress web fetch returns a visible denial", zero_blocks)
        evidence.append({"check": "zero_egress_visible_denial", "ok": zero_blocks})

        malformed = passkey.auth_finish({}, "localhost", "http://localhost")
        passkey_denies = malformed.get("ok") is False and bool(malformed.get("error"))
        ck("6. malformed passkey auth returns a visible denial", passkey_denies)
        evidence.append({"check": "passkey_malformed_auth_visible_denial", "ok": passkey_denies})

    return evidence


def main() -> int:
    t0 = time.perf_counter()
    print("EXCEPTION SAFETY TAXONOMY - broad handlers classified and risky paths fail closed")
    print("=" * 96)

    scan = _scan_broad_handlers()
    ck("0. every broad exception handler is assigned a safety domain",
       scan["total"] > 0 and sum(scan["by_domain"].values()) == scan["total"])
    evidence = _behavior_checks()

    report = {
        "cert": "certify_exception_safety_taxonomy",
        "status": "green" if not fails else "red",
        "commit": _git("rev-parse", "--short", "HEAD"),
        "generated_at_unix": int(time.time()),
        "domain_policies": DOMAIN_POLICIES,
        "broad_exception_inventory": scan,
        "verified_behaviors": evidence,
        "remaining_work": [
            "reduce broad handlers in surface/runtime code where narrow exceptions are obvious",
            "move recurring visibility-only handlers to shared logging helpers",
            "expand behavioral proofs as new authority, spend, egress, and credential paths are added",
        ],
    }
    REPORT.parent.mkdir(parents=True, exist_ok=True)
    REPORT.write_text(json.dumps(report, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
    ck("7. exception taxonomy report is written as visibility evidence", REPORT.exists())

    green = not fails
    try:
        from anima.verification import cert_result as cr
        cr.emit("certify_exception_safety_taxonomy", "green" if green else "red",
                files_observed=[
                    "scripts/certify_exception_safety_taxonomy.py",
                    "anima/company_operator/approvals.py",
                    "anima/consent/policy.py",
                    "anima/observation/store.py",
                    "anima/truth/ledger.py",
                    "anima/webget.py",
                    "anima/passkey.py",
                ],
                report_paths=["reports/exception_safety_taxonomy.json"],
                duration_sec=time.perf_counter() - t0, failures=fails)
    except Exception as e:
        print("  (emit failed: %r)" % e)
    print("\nEXCEPTION-SAFETY-TAXONOMY CERT: "
          + ("CERTIFIED" if green else "FAIL (%d)" % len(fails)))
    return 0 if green else 1


if __name__ == "__main__":
    raise SystemExit(main())

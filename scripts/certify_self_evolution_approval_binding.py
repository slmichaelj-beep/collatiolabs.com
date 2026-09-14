#!/usr/bin/env python3
"""certify_self_evolution_approval_binding - high/core promotions need scoped approvals.

A high/core self-evolution approval is not a free-form note. It must resolve to an approved packet
that matches the proposal, risk class, rollback ref, and cert evidence. Exit 0 == CERTIFIED.
"""
from __future__ import annotations

import sys
import tempfile
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from anima.company_operator import approvals  # noqa: E402
from anima.self_evolution import evolve as ev  # noqa: E402

oks, fails = [], []


def ck(label: str, cond: bool):
    (oks if cond else fails).append(label)
    print(("  ok   " if cond else "  XX   ") + label)


def _gap(name: str, st: Path) -> str:
    return ev.capability_gap(
        name, title="recurring governance gap", description="repeated need for safer evolution",
        evidence_refs=["obs_1", "obs_2"], frequency=3, store=st,
    )["capability_gap"]["gap_id"]


def _proposal(name: str, st: Path, *, risk: str, cert: str, capability: str) -> dict:
    return ev.proposal(
        name, gap_id=_gap(name, st), proposed_capability=capability, risk_level=risk,
        new_certs=[cert], observation_events=["self_evolution_promotion"], rollback_plan="restore rb",
        store=st,
    )["proposal"]


def _approve(name: str, title: str, action_type: str, st: Path, **kw) -> str:
    rec = approvals.create(name, title, action_type, store=st, **kw)["approval"]
    approvals.decide(name, rec["approval_id"], "approved", store=st)
    return rec["approval_id"]


def _promote(name: str, prop: dict, approval_ref: str, st: Path, *, rollback_ref: str = "rb1"):
    certs = {c: True for c in prop["new_certs"]}
    return ev.promote(
        name, proposal_id=prop["proposal_id"], cert_results=certs, rollback_ref=rollback_ref,
        diamond_passed=True, released=True, approval_ref=approval_ref, store=st,
    )


def main() -> int:
    t0 = time.perf_counter()
    print("SELF-EVOLUTION APPROVAL BINDING - high/core promotions use scoped packets")
    print("=" * 86)
    with tempfile.TemporaryDirectory() as td:
        st = Path(td)
        name = "SelfEvolutionApprovalCert"

        medium = _proposal(name, st, risk="medium", cert="certify_medium_extension",
                           capability="medium extension")
        medium_ok = _promote(name, medium, "", st)
        ck("1. medium-risk promotion still succeeds without approval", medium_ok["ok"])

        core_fake = _proposal(name, st, risk="core", cert="certify_core_guard",
                              capability="core guard")
        fake = _promote(name, core_fake, "not-a-real-approval", st)
        ck("2. fake approval strings cannot promote core changes",
           not fake["ok"] and "no such approval" in fake["error"])

        pending_prop = _proposal(name, st, risk="high", cert="certify_pending_guard",
                                 capability="pending guard")
        pending = approvals.create(
            name, "Pending product approval", "product", risk="high",
            subject=pending_prop["proposal_id"], rollback_ref="rb1",
            evidence_refs=pending_prop["new_certs"], store=st,
        )["approval"]["approval_id"]
        pending_block = _promote(name, pending_prop, pending, st)
        ck("3. pending approvals cannot promote high-risk changes",
           not pending_block["ok"] and "approval is pending" in pending_block["error"])

        core_with_product = _proposal(name, st, risk="core", cert="certify_core_scope",
                                      capability="core scope")
        product_for_core = _approve(
            name, "Wrong scope for core", "product", st, risk="core",
            subject=core_with_product["proposal_id"], rollback_ref="rb1",
            evidence_refs=core_with_product["new_certs"],
        )
        wrong_scope = _promote(name, core_with_product, product_for_core, st)
        ck("4. product approvals cannot authorize core_change promotions",
           not wrong_scope["ok"] and "scoped" in wrong_scope["error"])

        subject_prop = _proposal(name, st, risk="high", cert="certify_subject_guard",
                                 capability="subject guard")
        wrong_subject = _approve(
            name, "Wrong proposal subject", "product", st, risk="high", subject="different-proposal",
            rollback_ref="rb1", evidence_refs=subject_prop["new_certs"],
        )
        subject_block = _promote(name, subject_prop, wrong_subject, st)
        ck("5. proposal-subject mismatch is refused",
           not subject_block["ok"] and "subject" in subject_block["error"])

        evidence_prop = _proposal(name, st, risk="high", cert="certify_required_guard",
                                  capability="evidence guard")
        missing_evidence = _approve(
            name, "Missing cert evidence", "product", st, risk="high",
            subject=evidence_prop["proposal_id"], rollback_ref="rb1", evidence_refs=[],
        )
        evidence_block = _promote(name, evidence_prop, missing_evidence, st)
        ck("6. approval must cite the proposal cert set",
           not evidence_block["ok"] and "missing cert evidence" in evidence_block["error"])

        rollback_prop = _proposal(name, st, risk="high", cert="certify_rollback_guard",
                                  capability="rollback guard")
        wrong_rollback = _approve(
            name, "Wrong rollback ref", "product", st, risk="high",
            subject=rollback_prop["proposal_id"], rollback_ref="rb-other",
            evidence_refs=rollback_prop["new_certs"],
        )
        rollback_block = _promote(name, rollback_prop, wrong_rollback, st)
        ck("7. rollback-ref mismatch is refused",
           not rollback_block["ok"] and "rollback_ref" in rollback_block["error"])

        exact_prop = _proposal(name, st, risk="high", cert="certify_exact_guard",
                               capability="exact guard")
        exact = _approve(
            name, "Exact high-risk approval", "product", st, risk="high",
            subject=exact_prop["proposal_id"], rollback_ref="rb1",
            evidence_refs=exact_prop["new_certs"],
        )
        exact_ok = _promote(name, exact_prop, exact, st)
        ck("8. exact high-risk approval promotes successfully", exact_ok["ok"])
        ck("9. exact high-risk approval is consumed",
           approvals.get(name, exact, st)["status"] == "executed")

        replay = _promote(name, exact_prop, exact, st)
        ck("10. consumed high-risk approval cannot be replayed",
           not replay["ok"] and "executed" in replay["error"])

        core_exact = _proposal(name, st, risk="core", cert="certify_core_exact",
                               capability="core exact")
        core_ap = _approve(
            name, "Exact core approval", "core_change", st, risk="core",
            subject=core_exact["proposal_id"], rollback_ref="rb1",
            evidence_refs=core_exact["new_certs"],
        )
        core_ok = _promote(name, core_exact, core_ap, st)
        ck("11. exact core approval promotes successfully", core_ok["ok"])
        ck("12. exact core approval is consumed",
           approvals.get(name, core_ap, st)["status"] == "executed")

    green = not fails
    try:
        from anima.verification import cert_result as cr
        cr.emit("certify_self_evolution_approval_binding", "green" if green else "red",
                files_observed=[
                    "anima/self_evolution/evolve.py",
                    "anima/company_operator/approvals.py",
                ],
                duration_sec=time.perf_counter() - t0, failures=fails)
    except Exception as e:
        print("  (emit failed: %r)" % e)
    print("\nSELF-EVOLUTION-APPROVAL-BINDING CERT: "
          + ("CERTIFIED" if green else "FAIL (%d)" % len(fails)))
    return 0 if green else 1


if __name__ == "__main__":
    raise SystemExit(main())

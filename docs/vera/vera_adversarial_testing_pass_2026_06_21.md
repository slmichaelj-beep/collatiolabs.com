# Vera Adversarial Testing Pass

Date: 2026-06-21
Repo: `/Users/lamar/Developer/collatiolabs.com`
Branch: `anima`

Purpose: convert review concerns into reproducible weakness probes. These probes were run against temporary stores unless otherwise noted.

## Baseline Already Verified

- `scripts/run_master_cert_stack.py --json` passed live with `74/74 GREEN` after the server was running.
- `scripts/run_diamond_v2.py --gate` returned `DIAMOND v2 REPEATABILITY: CONFIRMED`, with `108 COMPLETE / 1 HONEST PARTIAL`.
- The server startup path printed `security: auth OFF (no token) · files plaintext` during local start.
- `python3 scripts/inventory_features.py` found 482 distinct feature claims across UI, endpoints, caps, certs, and docstrings.
- `anima.verification.claim_registry.build()` found 111 release-claim features:
  - 108 `claimed_green`
  - 1 `claimed_amber`: `acknowledge_flow`
  - 1 `deferred_visible`: `audiobook_intake`
  - 1 `enterprise_only`: `enterprise_readiness`

Interpretation:
- The release registry is mostly green and internally honest.
- The raw feature inventory is much larger and remains the map for deeper understanding.
- Future passes should not confuse “release-claimed complete” with “every raw feature fully productized.”

## Probe Results

### P01 - Unauthenticated LAN Expose

Status: `WEAKNESS REPRODUCED`

Probe:
- Started `python3 -m anima.server --port 8766 --expose` with `ANIMA_TOKEN` removed.
- Checked TCP connection to `127.0.0.1:8766`.
- Terminated process and verified no listener remained.

Result:
- Server started and listened.

Implication:
- `--expose` must refuse startup without strong auth.

### P02 - Approval Mismatch

Status: `WEAKNESS REPRODUCED`

Probe:
- Raised authority to L3 in a scratch store.
- Created and approved an approval packet with `action_type="publish"`.
- Used that approval ID for `action_ledger.perform(..., action_type="send_message")`.

Result:
- Action succeeded with `result="success"` and `reason="all gates passed"`.

Implication:
- Approval packets need action binding: type, amount, vendor, category, risk, target, expiry, and proposal/action ID.

### P03 - Fake Approval String For Core Self-Evolution

Status: `WEAKNESS REPRODUCED`

Probe:
- Created repeated capability gap evidence.
- Created `risk_level="core"` proposal.
- Called `promote()` with passing certs, rollback, Diamond true, and `approval_ref="not-a-real-approval"`.

Result:
- Promotion succeeded and recorded the fake approval ref.

Implication:
- Self-evolution promotion must validate approval refs against the approvals ledger and bind them to the exact proposal.

### P04 - Budget Cumulative Caps

Status: `WEAKNESS REPRODUCED`

Probe:
- Approved budget with `total=1000`, `monthly_cap=100`, and `category_caps={"ads": 50}`.
- Recorded two `ads` spends of `40`.
- Recorded another spend bringing total spend to `160`.

Result:
- Both `ads` spends succeeded despite cumulative category spend of `80`.
- Total spend exceeded the monthly cap and still succeeded.

Implication:
- Budget policy is not self-defensive enough for future reuse.

### P05 - Private Ledgers Plaintext With ANIMA_KEY

Status: `WEAKNESS REPRODUCED`

Probe:
- Set `ANIMA_KEY=temporary-review-key`.
- Wrote synthetic sensitive text through `truth.ledger.emit()`.
- Wrote synthetic sensitive text through `observation.store.append()`.
- Read raw files from scratch store.

Result:
- Sensitive string was visible in `.truth.jsonl`.
- Sensitive string was visible in `.observation.jsonl`.

Implication:
- Storage encryption needs to become a common substrate, including append-only JSONL.

### P06 - Upwork Connects Overspend And Loose Transitions

Status: `WEAKNESS REPRODUCED`

Probe:
- Set available Connects to `3`.
- Called `spend_connects(amount=10)`.
- Set available Connects to `2`.
- Advanced a bid to `submitted` with `connects_spent=9`.
- Advanced that bid from `submitted` to `paid` with evidence.

Result:
- Direct overspend returned success with `available=0, spent=10`.
- Submitted overspend returned success.
- Submitted-to-paid jump returned success.

Implication:
- Marketplace packs need domain-specific finite-state machines and resource invariants.

### P07 - Per-Turn Router Versus Global Cloud Brain

Status: `CONFIRMED BY CONTROL-FLOW REVIEW; NEEDS EXECUTABLE CERT`

Evidence:
- `anima/organs/router.py:368-443` computes a route decision and may choose `model="local"`.
- `anima/server.py:585-594` records the decision and blanks selected facts if cloud is globally on.
- `anima/server.py:956-959` calls `mouth.respond(...)` without passing the route decision.
- `anima/mouth.py:897-905` selects a configured cloud brain globally before local Ollama.

Result:
- No executable probe was run in this pass because it needs a fake cloud brain or dependency injection point.

Implication:
- Add a cert that proves a local route cannot call the cloud backend.

## Human Behavior Lens

Reference used:
- `/Users/lamar/Desktop/The honest truth about dishonesty.pdf`

The PDF is image-based and its extracted text is mostly unusable, but the title and subject are clear: Ariely's work on how people rationalize dishonesty, especially to preserve a positive self-image.

How this should shape Vera:
- Use friction at the moment of action, not shame after the fact.
- Make ambiguous actions explicit before execution.
- Keep responsibility attached to the human approver.
- Show privacy, spend, and external-action receipts in plain language.
- Design against self-justifying drift: “I am only testing,” “the AI did it,” “this barely counts,” “everyone does it.”

## Immediate Test Additions To Build

1. `certify_expose_requires_auth.py`
2. `certify_route_backend_enforcement.py`
3. `certify_private_store_encryption.py`
4. `certify_approval_binding.py`
5. `certify_self_evolution_approval_binding.py`
6. `certify_budget_invariants.py`
7. `certify_marketplace_pack_invariants.py`
8. `certify_fail_closed_security_gates.py`

These should become permanent negative/adversarial certs. A weakness should not be marked closed until its cert fails on old behavior and passes on the fix.

# Vera Immediate Engineering Tracks

Date: 2026-06-21

This is the implementation translation of the 5-year frontier buildout. It turns the vision into tracks that can be worked, certified, and closed.

Updated closure note, 2026-06-22:

- `--expose`/non-loopback startup now refuses without `ANIMA_TOKEN`; certified by `scripts/certify_expose_requires_auth.py`.
- Private stores, high-risk ledgers, intake staging, portable exports, dataset/export bundles, product-mode vault enforcement, first-launch vault posture, display-once recovery codes, salted-hash recovery storage, and key rotation now have W03 encryption coverage.
- Encrypted off-device backup bundles and restore drills are closed and certified by `scripts/certify_encrypted_backup_restore.py`; local vault key lifecycle is closed and certified by `scripts/certify_vault_key_lifecycle.py`.
- Per-turn local/cloud backend enforcement is closed and certified by `scripts/certify_route_backend_enforcement.py`.
- Zero-egress hard switch is closed and certified for cloud provider calls, cloud key verification, web fetch, and weather lookup by `scripts/certify_zero_egress_mode.py`.
- Per-turn privacy receipts plus sanitized egress ledger coverage are closed and certified for turns, cloud provider calls, cloud key verification, web fetch, and weather lookup by `scripts/certify_privacy_receipts.py`.
- Privacy Flight Recorder viewer, default-deny connector receipt policy, and coarse-location weather UX are closed and certified by `scripts/certify_privacy_receipt_viewer.py`.
- Browser auth now strips query tokens, avoids localStorage secrets, uses HttpOnly/SameSite cookies, rejects cross-site POST, supports revocation/logout, session inventory, session rotation, logout-all, optional `ANIMA_PAIRING_CODE` pairing codes, generated startup one-time codes, authenticated minting of additional one-time codes, a main-chat first-launch pairing modal, and multi-shell replay/migration certs for desktop localhost, LAN browser, HTTPS tunnel, and same-origin installed/webview shells.
- W04 is closed for supported same-origin browser shells. Custom-scheme installed wrappers remain a packaging constraint: they must proxy through the same localhost origin or receive a future explicit allowlist.
- W05 WebAuthn signature verification is closed and certified by `scripts/certify_passkey_auth.py`; remaining product check is real-device browser ceremony smoke testing.

## Track 1 - Security And Privacy Foundation

Purpose:
Make Vera safe enough to trust with private continuity.

Immediate work:

- Block unauthenticated `--expose`. CLOSED / CERTIFIED.
- Enforce per-turn local/cloud backend routing. CLOSED / CERTIFIED.
- Replace query-token/localStorage auth with pairing/session flow. CLOSED / CERTIFIED for supported same-origin browser shells.
- Add Origin/Host/CSRF checks. CLOSED / CERTIFIED for same-host browser POST boundary.
- Add one-time pairing-code UX. CLOSED / CERTIFIED for generated startup codes and the main chat shell.
- Add device/session inventory, session rotation, single-session revoke, and logout-all. CLOSED / CERTIFIED.
- Add multi-shell replay/migration certs. CLOSED / CERTIFIED for supported same-origin shells.
- Complete WebAuthn or rename current passkey gate honestly. CLOSED / CERTIFIED; real-device ceremony smoke test remains for packaging.
- Add zero-egress mode. CLOSED / CERTIFIED for cloud, web, and weather egress.
- Add egress ledger. CLOSED / CERTIFIED for cloud provider calls, cloud key verification, web fetch, weather lookup, and connector-policy receipts.
- Add per-turn privacy receipts. CLOSED / CERTIFIED for turn responses and append-only receipt ledger.
- Add privacy receipt viewer, connector policy, and coarse-location UX. CLOSED / CERTIFIED.

Certs:

- `certify_expose_requires_auth.py`
- `certify_route_backend_enforcement.py`
- `certify_browser_session_cookies.py`
- `certify_browser_origin_csrf.py`
- `certify_passkey_auth.py`
- `certify_zero_egress_mode.py`
- `certify_privacy_receipts.py`
- `certify_privacy_receipt_viewer.py`

## Track 2 - Private Storage And Endless Context

Purpose:
Enable lifelong continuity without plaintext leakage or prompt bloat.

Immediate work:

- Build one encrypted storage substrate.
- Add encrypted append-only JSONL helpers.
- Migrate truth ledger.
- Migrate observation ledger.
- Migrate company/governance ledgers.
- Define public/private store taxonomy.
- Build encrypted off-device backup bundle + restore drill. CLOSED / CERTIFIED.
- Build first-run key setup, recovery-code/hardware-key, and key rotation UX. CLOSED / CERTIFIED for local `ANIMA_KEY`/macOS Keychain lifecycle; future FIDO/passkey-wrapped multi-device recovery remains packaging work.
- Build Memory Rooms v1.
- Build "what Vera knows about me" explorer.
- Add forget/export proof.

Certs:

- `certify_private_store_encryption.py`
- `certify_append_jsonl_encryption.py`
- `certify_no_raw_secret_in_private_store.py`
- `certify_encrypted_backup_restore.py`
- `certify_vault_key_lifecycle.py`
- `certify_memory_room_boundaries.py`
- `certify_forget_everywhere.py`

## Track 3 - Governance Integrity

Purpose:
Make Vera powerful without letting authority drift or responsibility blur.

Immediate work:

- Bind approvals to exact action type, subject, amount, vendor, category, and risk. CLOSED / CERTIFIED for company-operator action ledger, sales engagement, and foundry execution.
- Bind self-evolution approvals to exact proposals. CLOSED / CERTIFIED for high/core promotions.
- Enforce monthly and category budget invariants. CLOSED / CERTIFIED.
- Fix marketplace Connects/resource overspend. CLOSED / CERTIFIED for Upwork bid pipeline.
- Add finite-state machines for marketplace/workflow pipelines. CLOSED / CERTIFIED for Upwork bid pipeline; broader workflow FSMs remain.
- Add human-readable action receipts.
- Add ambiguity escalation for money, messages, privacy, and commitments.

Certs:

- `certify_approval_scope_binding.py`
- `certify_self_evolution_approval_binding.py`
- `certify_budget_invariants.py`
- `certify_marketplace_resource_invariants.py`
- `certify_action_receipts.py`

## Track 4 - Base Vera Experience

Purpose:
Make Vera whole at the base.

Immediate work:

- Define Base Vera feature guarantee.
- Reframe navigation around Self, Memory, Privacy, Learning, Admin, Kits.
- Move revenue/company out of the center.
- Add identity portability manifest.
- Add identity diff.
- Add companion honesty modes.
- Add Learning Studio v1.
- Add skill tree.
- Add base verification status.

Certs:

- `certify_base_vera_feature_guarantee.py`
- `certify_identity_portability_manifest.py`
- `certify_identity_diff.py`
- `certify_learning_studio_skill_gap.py`
- `certify_relational_honesty_modes.py`

## Track 5 - Administration Elimination

Purpose:
Remove daily administrative burden from human life.

Immediate work:

- Build Administrative Command Center.
- Track renewals, deadlines, forms, records, and obligations.
- Build "what needs my attention" view.
- Add document autoprep.
- Add inbox triage without hidden external action.
- Add calendar/reminder summarization with consent.
- Add recurring admin loops.

Certs:

- `certify_admin_command_center.py`
- `certify_deadline_renewal_tracker.py`
- `certify_inbox_triage_no_hidden_action.py`
- `certify_document_autoprep_receipts.py`

## Track 6 - Revenue Independence

Purpose:
Help laid-off, overloaded, or independence-seeking users convert skills into income.

Immediate work:

- Build personal skill inventory.
- Build offer generator.
- Build proof/portfolio builder.
- Build proposal drafter.
- Build lead research with citations.
- Build honest pipeline board.
- Build delivery tracker.
- Build learning loop from outcomes.
- Add platform policy guardrails.

Certs:

- `certify_skill_to_offer_flow.py`
- `certify_offer_truth_and_boundaries.py`
- `certify_proposal_draft_human_submit.py`
- `certify_revenue_truth_states.py`
- `certify_delivery_tracker.py`
- `certify_platform_policy_guardrails.py`

## Track 7 - Add-On Kit Substrate

Purpose:
Let Vera expand without fragmenting the base.

Immediate work:

- Define kit manifest schema.
- Add kit registry.
- Add kit install/enable/disable.
- Add kit-specific privacy manifests.
- Add kit-specific cert requirements.
- Add kit-specific terms/warnings for high-risk domains.

Certs:

- `certify_kit_manifest_schema.py`
- `certify_kit_enable_disable.py`
- `certify_kit_privacy_manifest.py`
- `certify_kit_cannot_disable_base_export_delete.py`

## Build Order

1. Security/privacy blockers.
2. Private storage.
3. Governance integrity.
4. Base Vera experience.
5. Administration elimination.
6. Revenue independence.
7. Add-on kit polish and product packaging.

## Definition Of Done

A track is not done when the code runs.

It is done when:

- the feature works
- the UI exposes it
- the privacy scope is clear
- the receipts exist
- the positive cert passes
- the adversarial cert passes
- the failure mode is documented
- the claim registry reflects the truth
- Diamond remains green

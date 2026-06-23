# Vera 10-Year Agent-Managed Roadmap

Date: 2026-06-21

Inputs:
- Security/Vault roadmap agent
- Portable Personality/Memory/Router roadmap agent
- Administration Elimination/Revenue Independence roadmap agent
- Productization/Liability roadmap agent
- Verification/Certification/Diamond Operations roadmap agent

Current implementation checkpoint:
- Repo: `/Users/lamar/Developer/collatiolabs.com`
- Current committed slice: `b942c8e` - `Add secure store no-plaintext cert`
- Master cert stack: `75/75 GREEN` on `b942c8e`
- Diamond: `DIAMOND v2 REPEATABILITY: CONFIRMED` on `b942c8e`

## Prime Directive

Vera must become a portable, private, governed intelligence companion that removes administration from human life, preserves lifelong context, and helps people rebuild agency and revenue without surrendering privacy, truth, or human responsibility.

This is beyond hustle. This is survival infrastructure for people whose employers, platforms, institutions, and administrative systems have become unstable or hostile to human flourishing.

## Operating Law

Every change moves through:

1. Claim diff.
2. Implementation.
3. Positive cert.
4. Adversarial cert.
5. Evidence artifact.
6. Clean working tree.
7. Server restart on committed head.
8. `deploy_check`.
9. `run_master_cert_stack.py`.
10. `run_diamond_v2.py --gate`.

No dirty tree is releasable.
No stale artifact is green.
No single Diamond run counts.
No capability is complete because code exists.
No power increase ships without equal or greater privacy, consent, observability, rollback, and verification.

## Agent Lanes

### Lane 1 - Sovereign Security / Vault

Owns:
- secure store
- sealed compartments
- layered keys
- hardware-backed secrets
- controlled cipher rotation
- tamper-evident ledgers
- no-plaintext certs
- encrypted backups
- recovery without Collatio custody
- zero-egress mode plus privacy receipts (cloud/web/weather hard switch, ledger coverage, Privacy Flight Recorder, connector policy, and coarse-location UX CLOSED / CERTIFIED for current surfaces)

Immediate focus:
- broaden `secure_store.py` from truth/observation to the whole private surface
- migrate company/governance ledgers
- add no-plaintext scans across stores, temp files, logs, reports, and backups
- define memory room keys
- add wrong-key fail-closed certs

Key certs:
- `certify_secure_store_no_plaintext.py`
- `certify_private_store_encryption.py`
- `certify_room_key_isolation.py`
- `certify_tamper_evident_ledger.py`
- `certify_encrypted_backup_restore.py`
- `certify_zero_egress_security_mode.py`

### Lane 2 - Portable Personality / Memory / Router

Owns:
- Base Vera feature guarantee
- portable personality
- identity manifest
- memory rooms
- endless context retention
- local model ladder
- per-turn route enforcement
- route receipts
- relational honesty modes
- Learning Studio
- Vera Council as optional rented cognition

Immediate focus:
- enforce per-turn backend routing
- build route receipts
- define Base Vera guarantee
- add Memory Rooms v1
- build identity diff
- build Learning Studio skill-gap cards
- keep Vera Council identity-firewalled

Key certs:
- `certify_route_backend_enforcement.py`
- `certify_memory_room_boundaries.py`
- `certify_identity_diff.py`
- `certify_relational_honesty_modes.py`
- `certify_learning_studio_skill_gap.py`
- `certify_council_identity_firewall.py`

### Lane 3 - Governance / Receipts / Human Integrity

Owns:
- authority levels
- approval binding
- action receipts
- budget invariants
- self-evolution approval binding
- fail-closed gate taxonomy
- ambiguity escalation
- human responsibility boundary

Immediate focus:
- bind approvals to exact action type, target, amount, vendor, category, risk, and expiry. CLOSED / CERTIFIED for company-operator action ledger, sales engagement, and foundry execution
- bind self-evolution approvals to exact proposals. CLOSED / CERTIFIED for high/core promotions
- enforce monthly/category budget invariants
- add human-readable action receipts
- classify broad exceptions into fail-open/fail-closed domains

Key certs:
- `certify_approval_scope_binding.py`
- `certify_self_evolution_approval_binding.py`
- `certify_budget_invariants.py`
- `certify_action_receipts.py`
- `certify_fail_closed_security_gates.py`

### Lane 4 - Administration Elimination

Owns:
- attention center
- deadlines
- renewals
- documents
- inbox triage
- records
- receipts
- calendar/reminder understanding
- recurring admin loops

Immediate focus:
- build "what needs my attention" view
- build renewal/deadline tracker
- build document autoprep with receipts
- build inbox triage with no hidden send/delete/archive
- build records/receipt vault

Key certs:
- `certify_admin_command_center.py`
- `certify_deadline_renewal_tracker.py`
- `certify_inbox_triage_no_hidden_action.py`
- `certify_document_autoprep_receipts.py`

### Lane 5 - Revenue Independence

Owns:
- skill inventory
- offer builder
- market matching
- proof/portfolio builder
- lead research
- proposal drafting
- honest pipeline
- delivery systems
- outcome learning
- personal business recovery after layoffs

Immediate focus:
- build skill inventory from user history and artifacts
- classify skills as proof-backed, plausible, aspirational, unsupported
- build offer generator
- build proof/portfolio builder
- build proposal drafter
- build honest pipeline states
- build delivery tracker

Key certs:
- `certify_skill_to_offer_flow.py`
- `certify_offer_truth_and_boundaries.py`
- `certify_portfolio_proof_truth.py`
- `certify_lead_research_citations.py`
- `certify_proposal_draft_human_submit.py`
- `certify_revenue_truth_states.py`
- `certify_delivery_tracker.py`
- `certify_platform_policy_guardrails.py`

### Lane 6 - Productization / Business Model / Liability

Owns:
- whole Base Vera + add-on kits
- kit manifests
- safe claims
- counsel packet
- security packet
- go-to-market sequence
- no-data-custody default
- support and incident model

Immediate focus:
- freeze public claims until certs support them
- define Base Vera guarantee
- define add-on kit manifests
- keep Revenue, Company Operator, Connector, and Council kits disabled by default
- draft counsel packet
- draft security packet
- design private alpha gate

Key reviews:
- product liability
- consumer protection and claims substantiation
- privacy/data security
- terms/EULA
- kit-specific disclaimers
- AI regulatory classification
- companion/minors risk posture

### Lane 7 - Verification / Certification / Diamond Operations

Owns:
- claim registry
- feature contracts
- cert-result spine
- adversarial cert suite
- freshness and flake classification
- master stack
- Diamond repeatability
- release evidence package
- multi-agent handoff packets

Immediate focus:
- ensure every master-stack cert emits `cert_result`
- stamp successful verification runs
- fix stale evidence artifacts
- add changed-file-to-cert mapping
- add blocker ledger workflow
- formalize agent handoff packets

Key certs:
- `certify_dirty_tree_blocks_green.py`
- `certify_last_run_stamp.py`
- `certify_cert_result_coverage.py`
- `certify_changed_file_cert_mapping.py`
- `certify_release_evidence_freshness.py`

## 0-180 Day Integrated Roadmap

### Days 0-30 - Trust Floor

- Block unauthenticated `--expose`. CLOSED / CERTIFIED.
- Enforce per-turn local/cloud backend routing. CLOSED / CERTIFIED.
- Land secure-store foundation and broaden migration plan. SUBSTANTIALLY CLOSED / CERTIFIED.
- Define Base Vera guarantee.
- Define kit manifest schema.
- Freeze unsafe public claims.
- Add new certs to master stack as they land.
- Require deploy proof and Diamond on every committed build slice.

### Days 31-60 - Private Store And Evidence

- Migrate all private JSON/JSONL ledgers to secure store.
- Define public/private store taxonomy.
- Add no-plaintext scans across stores, temp files, logs, reports, and backups.
- Add wrong-key fail-closed behavior.
- Add successful verification run stamp.
- Add cert-result coverage checks.

### Days 61-90 - Auth, Routing, And Receipts

- Replace query-token/localStorage auth with pairing/session flow. CLOSED / CERTIFIED for supported same-origin browser shells.
- Add Origin/Host/CSRF guards. CLOSED / CERTIFIED for same-host browser POST boundary.
- Add first-launch one-time pairing UX, session rotation/device inventory, and logout-all. CLOSED / CERTIFIED for generated startup codes and the main chat shell.
- Add multi-shell replay/migration certs. CLOSED / CERTIFIED for desktop localhost, LAN browser, HTTPS tunnel, and same-origin installed/webview shells.
- Complete WebAuthn or rename the current passkey gate honestly. CLOSED / CERTIFIED; real-device ceremony smoke test remains for packaging.
- Add per-turn route receipts. CLOSED / CERTIFIED for turn responses.
- Add egress ledger. PARTIALLY CLOSED / CERTIFIED for cloud provider calls, cloud key verification, web fetch, and weather lookup.
- Add privacy receipt viewer. CLOSED / CERTIFIED as `/privacy` Privacy Flight Recorder.

### Days 91-120 - Rooms, Governance, And Learning

- Build Memory Rooms v1.
- Add vault manifest and room policies.
- Bind approvals to exact actions. CLOSED / CERTIFIED for company-operator action ledger, sales engagement, and foundry execution.
- Bind self-evolution approvals to exact proposals. CLOSED / CERTIFIED for high/core promotions.
- Enforce budget invariants.
- Build Learning Studio v1.
- Add identity diff.

### Days 121-150 - Backup, Recovery, Admin

- Build encrypted backup bundles. CLOSED / CERTIFIED.
- Build restore drill. CLOSED / CERTIFIED.
- Add recovery code/hardware-key recovery design.
- Build Administrative Command Center.
- Build deadline/renewal tracker.
- Build document autoprep with receipts.

### Days 151-180 - Revenue Survival Kit V1

- Build personal skill inventory.
- Build offer generator.
- Build proof/portfolio builder.
- Build lead research with citations.
- Build proposal drafter.
- Build honest pipeline board.
- Build delivery tracker.
- Add revenue truth certs.

## Year Milestones

### Year 1 - Private Alpha Readiness

Base Vera is complete enough for selected trusted users:

- encrypted private vault
- memory rooms
- "what Vera knows about me"
- forget/export proof
- route receipts
- local model ladder
- relational honesty modes
- Learning Studio
- backup/restore drill
- Admin Command Center v1
- Revenue Independence v1
- Diamond green on clean committed releases

### Year 3 - Portable Life OS

Vera becomes daily life infrastructure:

- encrypted multi-device sync option
- local appliance tier
- mature identity portability
- advanced memory rooms
- continuity timeline
- annual life review
- Revenue/Business kits with certified boundaries
- Vera Council v1 as optional kit
- independent security review

### Year 5 - Personal Sovereignty Platform

Vera becomes an ecosystem:

- certified kit SDK
- verified kit marketplace
- enterprise/local deployment profiles
- signed update chain
- tamper-evident evidence ledgers
- annual security assessments
- mature revenue/business operating kits
- formal support and incident response

### Year 10 - Decade-Durable Human Continuity

Vera becomes long-term continuity infrastructure:

- portable identity and mind bundle formats
- migration across obsolete models/devices
- crypto-agile vault envelopes
- post-quantum-ready pairing/sync/update path
- user-owned trust passports
- survivable encrypted archives
- legacy export under user control
- bounded autonomous workflows only where certs, receipts, approvals, and rollback prove safety

## Release Gates

### Gate 0 - Internal Only

Allowed:
- Lamar/founder use.
- Build/test/refine.

Blocked:
- public sale
- strong privacy/security claims
- autonomous external action
- income promises

### Gate 1 - Private Alpha

Requires:
- no P0/P1 blockers
- deploy proof green
- master stack green
- Diamond green
- no-plaintext certs green
- export/forget/recovery proof
- no external action without confirmation

### Gate 2 - Paid Design Partners

Requires:
- terms/privacy/security packet reviewed
- support process
- vulnerability disclosure
- action/privacy/cloud receipts
- kit manifests
- no consequential decision automation

### Gate 3 - Public Beta

Requires:
- independent security review
- adversarial cert suite green
- stale artifact checks green
- telemetry off or opt-in
- restore drill
- counsel-reviewed claims

### Gate 4 - General Availability

Requires:
- Diamond repeatability fresh
- release evidence package
- incident response tabletop
- insurance review
- kit-specific terms and certs
- no unclassified flakes

## Multi-Agent Development Protocol

Each implementation slice gets:

- lane owner
- write scope
- claim diff
- risk class
- cert plan
- adversarial cert plan
- rollback plan
- release-tier impact
- affected reports
- Diamond requirement

Agents can work in parallel only when write scopes are disjoint.

No agent may:

- revert another agent's changes
- declare release without master stack and Diamond
- bypass dirty-tree deployment law
- add a capability without claim/cert ownership
- introduce new public claims without product/counsel lane review

## Top Risks

- Security claims outrun shipped guarantees.
- Local/cloud mismatch breaks privacy.
- Endless context becomes unsafe prompt bloat.
- Recovery creates either data loss or Collatio custody.
- Revenue claims become false hope.
- Activity masquerades as paid revenue.
- Agents create claim sprawl without cert coverage.
- Diamond becomes ceremonial.
- Add-on kits redefine Vera's core identity.

## Final Standard

Vera must become more powerful only when she also becomes more:

- private
- honest
- reversible
- observable
- portable
- governed
- useful to a human rebuilding real life

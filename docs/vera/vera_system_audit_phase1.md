# Vera / Collatio System Audit - Phase 1

Date: 2026-06-21
Repo: `/Users/lamar/Developer/collatiolabs.com`
Branch/head: `anima` / `95675db`

## Purpose

This is the first durable pass toward a 100% code review and capability map for Vera. The goal is not just to list files. The goal is to understand what Vera is, what she can do today, what is certified, what is intentionally inert, and what should change before she grows beyond a revenue-ops workspace into a broader local-first intelligence substrate.

## Verified Baseline

The repo is clean on branch `anima`.

Tracked source census:

- 878 tracked files.
- 343 tracked Python modules under `anima/`.
- 313 tracked Python scripts under `scripts/`.
- 36 tracked web surfaces under `anima/web/`.
- 111 feature contracts under `feature_contracts/`.
- 2 runnable deliverable demos under `deliverables/`.

Cert baseline:

- First master run without the server running: 51/74 green. Representative failures were live-route reachability checks, not underlying unit contract failures.
- Started Vera with `source .venv/bin/activate && python3 -m anima.server --port 8765`.
- Re-ran master stack live: 74/74 green.
- Ran `python3 scripts/run_diamond_v2.py --gate`: Diamond v2 repeatability confirmed.
- Diamond result: 108 complete per run across 3 runs, 1 honest partial, 0 product reds, 0 unclassified flakes.
- External dependency surfaced by Diamond: `argus` daemon unavailable; impact on Diamond: none.

Important runtime observation:

- Default localhost run had auth off because `ANIMA_TOKEN` was unset: `security: auth OFF (no token) · files plaintext`.

## System Shape

The repo is best understood as Vera plus optional operating domains, not as a revenue system with a personality attached.

Core identity/substrate:

- `anima/heart.py`: continuous-time affective core.
- `anima/server.py`: live HTTP host, web/API routing, turn loop, observability, deterministic seams, LLM fallback.
- `anima/mouth.py`: generative voice/text output, local/cloud brain selection, final output gates.
- `anima/spine.py`, `anima/truth/`, `anima/memory_lirf.py`: known facts, claims, corrections, retractions, truth provenance.
- `anima/observation/`, `anima/telemetry.py`, `anima/whole_mri.py`: traceability and turn/system MRI.
- `anima/verification/`, `scripts/certify_*.py`, `scripts/run_master_cert_stack.py`, `scripts/run_diamond_v2.py`: product-contract verification.

Learning and self-development:

- `anima/auto_learn/`: suggestion queue, intentionally not direct persistence.
- `anima/teaching/`: approved durable learning path with schema, approval/edit/reject/chat-only/never-learn/rollback.
- `anima/knowledge_packs/`: import/build/retrieve/lifecycle for structured knowledge packs.
- `anima/self_evolution/`: capability gaps, proposals, promotions, retirements, cert/rollback/Diamond requirements.
- `anima/lerf*`: local skill substrate and LERF-first task path.

Governance and agency:

- `anima/caps.py`: default-off capability switches for outward-facing powers.
- `anima/route.py`: deterministic capability router for host reads/writes, drafts, and confirm-gated actions.
- `anima/company_operator/`: authority, approval, budget, kill-switch, accounts/legal/departments.
- `anima/collatio/`: LLC operating-authority layer.

Optional domain packs:

- Revenue/commercial: `commercial`, `market_vision`, `revenue`, `revenue_swarm`, `compounding`, `revenue_intelligence`, `distribution`, `trust`, `resources`, `empire`.
- Marketplaces: `marketplaces/fiverr`, `marketplaces/upwork`.
- Company operations: `company`, `teams`, `workforce`, `foundry`.
- Human operating layers: `cognitive_ergonomics`, `archetypal_patterns`, `mentorship`, `meaning_graph`, `identity_health`.

UI surface map:

- Public HTML shells include Observatory, Console, Security, Consent, Living Map, Trust, Ergonomics, Mentorship, Meaning, Identity, Reality, Commercial, Sales, Board Revenue, Opportunities, Collatio, Teams, Workforce, Self, Pipeline, Fiverr, Revenue, Compounding, Intelligence, Distribution, Resources, Empire, Observation, Chairman, Founder/Company, Learning, Verification.
- Data/control routes are token/passkey gated after the public shell handoff, assuming token/passkey are configured.

## Early Findings

### P1 - `--expose` can create unauthenticated LAN access

`anima/server.py` sets `Handler.token` from `ANIMA_TOKEN`, and `_authed()` returns true when the token is empty. `--expose` binds to `0.0.0.0`; the server prints "EXPOSED on your LAN (no password)" but still allows it.

Why it matters:

Vera has personal memory, host awareness, mail/message drafting routes, learning routes, and governance surfaces. A warning is not enough when the bind address leaves localhost.

Recommended fix:

- Refuse `--expose` unless `ANIMA_TOKEN` is set or passkey auth is required.
- Add a cert that starts with `--expose` and no token and expects startup refusal.
- Keep an explicit override only if it is noisy and intentionally named, e.g. `ANIMA_ALLOW_UNAUTH_EXPOSE=1`.

Anchors:

- `anima/server.py:2766`
- `anima/server.py:2768`
- `anima/server.py:3764`
- `anima/server.py:3766`
- `anima/server.py:3784`
- `anima/server.py:3846`

### P1 - Per-turn local/cloud routing is observable but not enforced

`anima/organs/router.py` computes a per-turn brain decision: local by default, cloud only on explicit request or when there is no local standing and cloud is available. In the live turn loop, `server._turn()` records that decision and blanks fact blocks when cloud is globally on. But generation uses `_mouth()`, and `Mouth.assemble()` globally selects the cloud brain if configured and available.

Why it matters:

The architecture wants "cheapest sufficient path" and local-first privacy. Today, a configured cloud brain can become the global mouth even on turns the router labels local sufficient.

Recommended fix:

- Make `RouteDecision.model` executable.
- Add a per-turn mouth/brain selection seam, or split `Mouth` into local and cloud brains and choose at generation time.
- Cert that when cloud is configured but router says `local`, generation backend remains local.
- Cert that when router says cloud, PII blocks remain blanked and the backend is explicitly cloud.

Anchors:

- `anima/organs/router.py:368`
- `anima/organs/router.py:381`
- `anima/organs/router.py:415`
- `anima/server.py:585`
- `anima/server.py:591`
- `anima/server.py:956`
- `anima/mouth.py:897`
- `anima/mouth.py:903`

### P2 - Budget ledger invariants are weaker than the docstring claims

`company_operator.budget` claims monthly caps, category caps, per-transaction caps, approval thresholds, and exhaustion are enforced. Current code enforces total remaining and per-transaction caps, but:

- `monthly_cap` is stored and never checked.
- Category caps are checked against a single transaction, not cumulative category spend.
- `record_spend()` only requires a non-empty `approval_ref` for threshold spends; it does not validate the reference against an approved approval ledger entry.

Why it matters:

This is a governance layer. Even if outward spending is currently inert/human-held, the ledger should be future-proof before Vera can take on broader operator duties.

Recommended fix:

- Track spend periods and enforce monthly caps cumulatively.
- Compute category spend to enforce category caps cumulatively.
- Require `approval_ref` to resolve to an approved spend approval for the matching amount/category/vendor.
- Add adversarial certs that call `record_spend()` directly.

Anchors:

- `anima/company_operator/budget.py:1`
- `anima/company_operator/budget.py:23`
- `anima/company_operator/budget.py:44`
- `anima/company_operator/budget.py:57`
- `anima/company_operator/budget.py:68`
- `anima/company_operator/budget.py:73`

### P2 - Upwork Connects ledger permits overspend

`marketplaces.upwork.pipeline.spend_connects()` floors available Connects at zero and still increments spent. `advance(..., status="submitted")` calls it but ignores its result. This allows a submitted bid to record Connects spend even when insufficient Connects exist.

Why it matters:

The marketplace layer is intentionally governed and human-submitted. Still, resource accounting should be exact because it feeds the "honest revenue truth" dashboards.

Recommended fix:

- Make `spend_connects()` refuse when `amount > available`.
- Have `advance()` fail submission if Connects cannot be spent.
- Add certs for insufficient Connects and repeated submission.

Anchors:

- `anima/marketplaces/upwork/pipeline.py:51`
- `anima/marketplaces/upwork/pipeline.py:66`
- `anima/marketplaces/upwork/pipeline.py:94`
- `anima/marketplaces/upwork/pipeline.py:96`

### P2 - Marketplace status transitions are too permissive

`advance()` blocks terminal-stage changes and requires evidence for `paid`, but otherwise allows arbitrary jumps such as `drafted -> awarded`, `submitted -> delivered`, or repeated `submitted`.

Why it matters:

Dashboards distinguish activity, pipeline, and cash. Loose transitions can make pipeline state less trustworthy even without fake cash.

Recommended fix:

- Encode allowed transitions.
- Treat repeated submission as idempotent or blocked.
- Require evidence on status jumps that imply external events, not only `paid`.

Anchor:

- `anima/marketplaces/upwork/pipeline.py:51`

## Architecture Direction

The strongest product framing is:

Vera is a local-first, governed intelligence home base. Revenue, marketplaces, team-building, and company operation are optional domain packs that can be enabled, disabled, or sold separately. They should not define Vera's primary identity.

Recommended reframe:

- Core: identity, memory, truth, teaching, self-evolution, routing, verification, privacy, host interface.
- Cognition: local models, optional cloud escalation, council/router mode, LERF skill substrate.
- Domain packs: revenue, marketplace, company operator, deliverables, human operating layer.
- Surfaces: operator dashboards, verification dashboards, learning dashboards, domain-specific workspaces.

This supports the user's stated direction: Vera can grow into much more without being trapped as "revenue ops."

## What Vera Already Does

Verified by code/certs in this pass:

- Runs as a local web app on `127.0.0.1:8765`.
- Serves 36 operator/user web surfaces.
- Maintains personal memory and truth provenance.
- Corrects and retracts memory with traceable chains.
- Gates durable learning through Teaching Mode.
- Keeps auto-learning suggestion-only.
- Supports knowledge packs.
- Tracks self-evolution through gaps, proposals, promotion, rollback, retirement.
- Runs deterministic capability routing before model generation.
- Supports local-first LERF task routing.
- Supports optional cloud brain configuration.
- Emits turn/system traces and verification evidence.
- Has governance for authority, approval, budget, kill switch, legal/accounts/departments.
- Has company, Collatio, foundry, teams, workforce layers.
- Has commercial/revenue/marketplace layers that prepare, draft, track, and report while leaving external submission/spend to a human.
- Provides runnable sellable demos: CV screener and PO label pipeline.
- Ships with a large certification stack and Diamond repeatability gate.

## Next Audit Passes

1. Server/API review:
   - Route-by-route auth, passkey, mutation, CSRF-ish exposure, data leakage, shell/public surface behavior.

2. Core self/cognition review:
   - `heart`, `mouth`, `server._turn`, `route`, `organs/router`, `lerf`, cloud/local model selection, output gates.

3. Memory/truth/learning review:
   - LIRF, Truth Ledger, Teaching Mode, Auto Learn, Knowledge Packs, rollback, conflict policy.

4. Governance review:
   - Capability flags, operator authority, approvals, budget, kill switch, spending/legal boundaries.

5. Domain-pack review:
   - Revenue/commercial, Fiverr/Upwork, Collatio/company/foundry/workforce, deliverables.

6. Adversarial cert additions:
   - unauthenticated `--expose` refusal.
   - executable per-turn brain routing.
   - cumulative budget invariants.
   - verified approval references.
   - Connects overspend refusal.
   - allowed marketplace status transitions.


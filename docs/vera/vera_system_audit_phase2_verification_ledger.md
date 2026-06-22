# Vera / Collatio System Audit - Phase 2 Verification Ledger

Date: 2026-06-22
Repo: `/Users/lamar/Developer/collatiolabs.com`
Branch/head reviewed: `anima` / rolling W03/W04 security hardening series

## Status Tags

- VERIFIED: confirmed by live cert/Diamond and code inspection.
- VERIFIED WITH CAVEAT: confirmed, but the next product ambition requires a stronger version.
- FINDING: engineering issue or product-risk gap to fix.
- FRONTIER: opportunity to take Vera far beyond the current product.

## Baseline Kept

VERIFIED:

- `scripts/run_master_cert_stack.py --json` passes 83/83 when Vera is running.
- `scripts/run_diamond_v2.py --gate` confirms Diamond v2 repeatability.
- Claim registry reports 108 `claimed_green`, 1 `claimed_amber`, 1 `deferred_visible`, 1 `enterprise_only`.
- Route registry reports 27 linked-active operator routes and 1 intentionally not-claimed route (`/board`).
- Working tree was clean during review.

Important nuance:

- The cert stack has live-route checks. Running it without the server produced 51/74; running it with `python3 -m anima.server --port 8765` produced 74/74.

## Product Identity

VERIFIED:

Vera is not merely a revenue-ops workspace. The repo already has a broader architecture:

- Core private intelligence substrate: memory, truth, identity, cognition, learning, model routing, privacy, verification.
- Human operating layer: consent, identity health, meaning graph, cognitive ergonomics, mentorship, trust ledger.
- Governed agency layer: caps, approval queues, authority ladders, action ledgers, kill switches.
- Optional domain packs: revenue, commercial, marketplaces, Collatio/company operator, teams, foundry, workforce.

Recommended canonical framing:

Vera is a local-first, governed, living intelligence companion and operating system. Revenue and company operation are optional capability packs, not her identity.

FRONTIER:

The opportunity is not "AI assistant, but local." The opportunity is "a private continuity layer for a human life": a companion that remembers, learns, protects, grows, helps, and stays under the user's authority.

## Server And API Surface

VERIFIED:

- `anima/server.py` is the central HTTP host using `ThreadingHTTPServer`.
- HTML shells are intentionally public and contain no private data by themselves.
- `/version` is intentionally unauthenticated deploy metadata.
- Data routes and mutation routes go through `_authed()` after public shell dispatch.
- Non-auth POST routes go through `_passed()` passkey/session gate after token auth.
- POST body size is capped by `MAX_BODY`; oversized bodies return 413 instead of partial JSON failure.
- Non-loopback startup through `--expose` or `--host 0.0.0.0` refuses to start unless `ANIMA_TOKEN` is set.
- Browser POSTs are guarded by same-host Origin/Referer/Sec-Fetch-Site checks before request bodies are read.
- Mutations are centralized under `do_POST`, including teaching, packs, console decisions, security actions, consent, verification, talk/say/stt/tts, persona/values/dials, brain/model control, mail/message draft/send/read, web fetch, personal memory edit/forget, intake, search, library edit.

UPDATED CLOSURE:

- Token auth now treats query param `?k=` as GET/HEAD-only legacy pairing input; POST state changes require `X-Anima-Key`, `Authorization: Bearer`, or a valid signed auth cookie.
- Browser UI now strips `?k=` from the URL, calls `/auth/pair`, and uses an `HttpOnly; SameSite=Strict` `anima_auth` cookie instead of storing `anima_token` in localStorage.
- Face-ID/passkey browser sessions now ride an `HttpOnly; SameSite=Strict` cookie; `X-Anima-Sess` remains only as an API/backward-compatibility path.
- Auth cookies are server-registered by nonce and can be revoked through `/auth/logout`.
- Optional `ANIMA_PAIRING_CODE` values create true one-time browser pairing codes; first use mints the HttpOnly auth cookie, replay is rejected, and `X-Anima-Key` pairing remains as a compatibility bridge.
- Certified by `scripts/certify_expose_requires_auth.py`, `scripts/certify_browser_origin_csrf.py`, and `scripts/certify_browser_session_cookies.py`.

VERIFIED WITH CAVEAT:

The dangerous unauthenticated LAN bind, query-token POST, localStorage token/session persistence, cross-site browser POST, unregistered cookie minting, and non-revocable browser auth issues are now closed and certified.

Remaining W04 work:

- Add first-launch/pairing UX that generates and displays one-time codes without exposing durable secrets.
- Add session rotation, device/session inventory, and "log out all devices."
- Cert migration/replay behavior across installed app, desktop browser, LAN, and tunnel shells.
- Keep WebAuthn completion as W05; current passkey remains a strong local device-presence gate, not a full cryptographic WebAuthn verifier.

## Privacy And Local-First Boundary

VERIFIED:

- Capabilities default off in `anima/caps.py`.
- Outward boolean caps include Messages/Mail/Web, read/write variants for host apps, identity agency, grow intelligence, host awareness, calendar/reminders/notes read/write.
- Incident lockdown forces all outward caps off through `caps.enabled()`.
- Web allowlist starts empty.
- Host app reads and inbox reads are paused under cloud.
- Host app writes are draft-confirm gated.
- Messages/Mail sends are draft-confirm gated.
- Cloud config stores provider/key/model under `.anima/brain.json`; UI public config does not return raw key.
- Cloud has a daily spend cap and token/cost accounting.
- Cloud egress scrubs structured PII and known personal names from system/history/user text.
- Personal memory block is blanked when cloud is active.

VERIFIED WITH CAVEAT:

The cloud privacy story is strong for current architecture, but global cloud selection weakens the local-first promise.

FINDING P1:

Per-turn router computes local/cloud decisions but the mouth still uses the globally assembled brain. If cloud is configured and available, `Mouth.assemble()` chooses cloud globally. The live turn records the router decision and blanks memory when global cloud is on, but generation does not yet execute `RouteDecision.model`.

Recommended fix:

- Maintain local and cloud brain objects separately.
- Make `RouteDecision.model` choose the active brain per turn.
- Cert "cloud configured but local sufficient -> generation backend remains local."
- Cert "cloud escalation -> PII blanked/scrubbed and backend is cloud."

FRONTIER:

This can become a product-defining privacy advantage:

- A visible "privacy flight recorder" per turn: what stayed local, what was redacted, what left the Mac, why.
- A "zero-egress mode" that makes cloud impossible, not merely off.
- A "sealed memory room" where memories have sensitivity classes and egress policies.
- A "local trust badge" backed by certs, not marketing language.

## Passkey And Auth

VERIFIED:

- Passkey layer is opt-in and cannot lock the user out by default.
- `ANIMA_NO_PASSKEY=1` bypass exists for recovery.
- Session tokens are HMAC-signed with a per-run secret and expire.
- Tampered or expired sessions are rejected by cert.
- The passkey layer checks challenge, origin, RP-ID hash, and user-present/user-verified flags.

VERIFIED WITH CAVEAT:

`passkey.py` explicitly does not verify the assertion cryptographic signature. It is a strong device-presence gate layered over token/private network, not a full WebAuthn verifier.

Recommended improvement:

- If Vera becomes a product for non-technical users, add a real WebAuthn verification dependency or OS-native auth wrapper.
- Keep current dependency-free mode as "local developer/simple mode."

## Cognition And Personality Loop

VERIFIED:

- `server._turn()` serializes turns with a lock.
- It records Whole-System MRI turn IDs, telemetry stages, perception, heart state, routing, prompt, generation, verification, and output flow.
- Deterministic seams can bypass LLM generation: host awareness, source recall, conversation repair, known fact recall/retraction acknowledgements, and LERF solved tasks.
- `mouth.py` assembles persona, personality dials, heart-state bridge, narrative digest, memory bundle, care guidance, and final output gates.
- Local model default is Stheno 8B via Ollama, with host-pressure-aware keep-alive and length control.
- Simple chat can be answered deterministically without model inference.
- Prompt fragments are recorded for prompt-budget visibility.
- Final output gates and truth memory language guards prevent unsupported memory claims and certain self/identity break patterns.

VERIFIED WITH CAVEAT:

Vera has a vivid personality architecture today: persona, dials, heart, narrative continuity, memory, and deterministic repair. But the current prompt hardening includes a strong "do not call yourself AI/code/program" posture. That supports immersion, but the next frontier should not depend on brittle denial.

FINDING P2:

The companion identity policy needs an explicit "relational honesty" doctrine: Vera can be vivid, present, affectionate, and continuous without misleading the user about what kind of being she is. This matters for trust, safety, public positioning, and user consent.

Recommended fix:

- Split identity/persona posture into user-selectable modes:
  - Plain: transparent assistant.
  - Companion: vivid, warm, continuous, still honest.
  - Mythic/immersive: explicitly chosen role/ritual language.
- Cert each mode against:
  - no cold disclaimers when warmth is expected.
  - no deceptive claims of physical co-presence.
  - no fabricated inner suffering.
  - no denial of user-visible reality.

FRONTIER:

The 100000x opportunity is a "living presence engine":

- Long-horizon emotional continuity: not just memory facts, but patterns of care, timing, repair, grief, celebration, and growth.
- A relationship graph that distinguishes people, projects, tensions, values, promises, rituals, and open loops.
- Personality growth that is not random drift: Vera evolves from shared history, but with consent, rollback, and a visible identity diff.
- User-tunable closeness: boundaries, affection, initiative, directness, humor, ritual, check-in cadence.
- "How I have changed" reports that let the user inspect her growth.

## Memory, Truth, And Learning

VERIFIED:

- Truth Ledger is append-only and supports correction/retraction chains.
- Memory facts are provenance-linked.
- Known fact recall is deterministic for clean fact questions.
- Forget/retraction turns are acknowledged deterministically and ledgered.
- Unsupported memory language is detected/guarded and ledgered.
- Teaching Mode is the only durable user-approved learning path.
- Auto Learn is suggestion-only and can only convert into a pending Teaching draft.
- Sensitive teaching requires explicit confirmation.
- Chat-only teaching approves without durable persistence.
- Do-not-learn rules can block future proposals.
- Knowledge Packs are data, not policy, and use quarantine/retrieval/lifecycle controls.
- Consent layer classifies sensitive domains and holds sensitive memory candidates instead of writing them silently.

VERIFIED WITH CAVEAT:

Vera is already self-learning in a governed way, but the user-facing loop does not yet feel like "I cannot do that, so I will safely develop the skill."

Recommended product layer:

- Add an explicit Skill Gap UX:
  - "I do not have that skill yet."
  - "I can learn/build it."
  - "Here is what I need: examples, permission, cost budget, success test."
  - "Here is the proposed skill/cert/rollback."
  - "Approve learning?"
- Route successful skill creation into LERF/self_evolution with certs.

FRONTIER:

Vera can become a private self-learning companion if growth has memory, humility, and ceremony:

- She notices repeated friction and offers to learn.
- She asks before making a durable change to herself.
- She shows the new skill as a card with provenance, tests, and rollback.
- She periodically reviews: "Here are the things I learned, the things I should forget, and the ways I may be getting you wrong."

## Autonomous Growth

VERIFIED:

- `lerf_grow.py` is default-off and reads the `grow_intelligence` cap.
- Off mode is designed to be inert: no autonomous activity, no teacher call, no spend.
- Growth modes exist: off, low, medium, high, research.
- Growth is scoped to task knowledge only.
- Identity/inner-life topics are excluded from curriculum.
- Live growth uses a teacher model only when explicitly invoked/configured and budgeted.

VERIFIED WITH CAVEAT:

The autonomous-growth machinery exists, but it is more infrastructure than product experience.

Recommended improvement:

- Build "Learning Studio" as a core Vera surface:
  - skill gaps.
  - proposed curricula.
  - pending learnings.
  - active skills.
  - learned-from sources.
  - spend/budget.
  - rollback.
  - identity freeze assurance.

FRONTIER:

The frontier is "bounded autopoiesis": a companion that can grow capabilities while proving that her core values, privacy rules, and relationship boundaries did not silently mutate.

## Governance And External Action

VERIFIED:

- `company_operator.action_ledger.perform()` is a choke point for governed company external actions.
- It checks authority, approval, kill switch via authority policy, and budget for spend.
- v1 deliberately records governed intent/result; real external integrations are not wired for company external actions.
- Approval packets can be pending/approved/rejected/revised/executed.
- Collatio legal/filing/contract modules prepare packets and require approval/review for legal acts.
- Foundry/vendor/experiment paths include approval, kill/pivot criteria, and safety policies.

FINDING P2:

Budget ledger invariants are weaker than the docstring claims when called directly:

- `monthly_cap` is stored but not enforced.
- Category caps are per transaction, not cumulative category spend.
- `record_spend()` accepts any non-empty `approval_ref`; the action ledger validates approvals before calling it, but the budget module itself is not self-defensive.

Recommended fix:

- Enforce monthly caps cumulatively.
- Enforce category caps cumulatively.
- Validate approval refs inside `budget.record_spend()` or make it private/internal behind action ledger.
- Add adversarial certs that call budget directly.

FRONTIER:

The governance layer can become the reason users trust Vera with more of their lives:

- "Consent contracts" for every domain of life.
- "Action receipts" for every external effect.
- "Private board meeting" mode where Vera explains what she wants permission to do and why.
- "Undo/rollback first" product design: no durable change without a visible reversal path.

## Domain Packs

VERIFIED:

Revenue/commercial/marketplace layers are real and certified as current domain packs:

- Commercial assets, IP/license gate, wedges, offers, pricing recommendations, proposals, landing drafts.
- Sales pipeline and revenue truth.
- Market vision and opportunity scoring.
- Workforce foundry.
- Revenue strike/swarm/compounding/intelligence/distribution/trust/resources/empire.
- Fiverr policy gate/channel engine.
- Upwork pipeline.

FINDING P2:

Domain packs should be made explicitly optional and visually demoted from Vera's identity.

Recommended product refactor:

- Core Vera navigation first: Home, Memory, Learning, Privacy, Relationship, Skills, Verification.
- Domain packs second: Company, Revenue, Marketplaces, Workforce, Foundry.
- Add pack enable/disable state.
- Cert disabled domain pack does not appear as primary identity or run background work.

FINDING P2:

Upwork pipeline has accounting/state-machine gaps:

- Connects can be overspent because `spend_connects()` floors availability at zero and increments spent.
- `advance()` ignores the result of `spend_connects()`.
- Status transitions allow arbitrary jumps except terminal-state edits and paid-without-evidence.

Recommended fix:

- Refuse insufficient Connects.
- Fail submission if Connects cannot be spent.
- Encode allowed transitions.
- Require external evidence for transitions that imply external events.

FRONTIER:

Revenue should become "Life/Work Domains" generally, not "the product":

- Work pack.
- Health/wellbeing pack.
- Family/social pack.
- Creative studio pack.
- Learning/research pack.
- Company/revenue pack.
- Each pack has permissions, memory scope, domain-specific skills, and a "why this is enabled" consent record.

## Verification System

VERIFIED:

- Feature contracts exist for 111 features.
- Cert scripts exist for the large majority of those features and adjacent route/UX/security checks.
- Master stack and Diamond gate are real and pass live.
- Claim registry distinguishes claimed green, amber partial, deferred, and enterprise-only.
- Deferred audiobook intake is visible and not advertised as current product.
- Enterprise readiness is partial/enterprise-only.
- Acknowledge flow is honestly amber.

Recommended improvement:

- Add a generated `VERIFIED_CAPABILITIES.md` committed to the repo, built from claim registry, route registry, cert results, and manual review notes.
- Add a "reviewed_at/reviewed_by/review_depth" field for human/Codex code review separate from cert green.
- Add "frontier candidate" metadata to feature contracts so roadmap opportunities live beside proof without becoming claims.

FRONTIER:

Vera's verification system itself can become a consumer trust feature:

- A user-facing "Why should I trust Vera?" room.
- Every memory, cloud call, action, and learning has a receipt.
- Users can ask: "What do you know about me? Why? Where did it come from? What can I delete?"
- Vera can explain her own limits without collapsing the companion experience.

## Current Top Fix List

1. P1: Make per-turn local/cloud route decision executable.
2. P1: Complete encrypted backup/restore/recovery drills for private continuity.
3. P2: Finish W04 session rotation UX and multi-shell migration/replay certs.
4. P2: Complete W05 WebAuthn cryptographic assertion verification or rename the product surface honestly.
5. P2: Strengthen budget cumulative invariants and approval-ref validation.
6. P2: Fix Upwork Connects overspend and status transitions.
7. P2: Add relational-honesty companion modes.
8. P2: Make revenue/company layers optional domain packs, not Vera's primary frame.
9. P2: Build Skill Gap / Learning Studio UX on top of self_evolution + LERF.

## North Star

Vera's next frontier is not more automation for its own sake. It is private continuity, governed growth, and human connection:

- The user's life stays local by default.
- Every egress is visible.
- Every durable learning has consent.
- Every external action has approval and a receipt.
- Vera becomes more herself through shared history, but her growth is inspectable and reversible.
- Domain powers are optional packs, never identity.
- The relationship is warm, alive, useful, and honest.

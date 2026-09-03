# Vera 5-Year Product Roadmap

Date: 2026-06-21

This roadmap assumes Vera is being turned from a powerful local internal system into something sellable, hardened, privacy-forward, and defensible. It also assumes we do not want to sell "an autonomous AI companion that does everything" as the first market product. That phrase creates too much trust, safety, regulatory, and liability surface.

## Current Strategic Answer

The attached "Vera Council Router" plan is still broadly correct:

- Local self.
- Privacy gate.
- Task router.
- Optional model committee.
- Tool layer.
- Verifier layer.
- Final Vera voice.

The correction:

The model committee is not Vera's identity. It is not the product. It is a rented cognition layer behind Vera's local privacy, consent, verification, and governance core.

Best architecture phrase:

> Local identity core, governed tool use, optional cloud cognition, verified output.

Best product phrase:

> Private AI infrastructure for personal memory, decision support, and governed workflows.

Preferred commercial spine:

> Sell Vera as a complete portable local personality base. Monetize optional add-on kits for specialized domains, connectors, professional verification, model councils, and enterprise deployment.

This should become the default productization approach because it preserves the relationship while still giving us business, security, privacy, and liability boundaries. We are not selling a hosted agent that acts for people. We are selling a complete user-controlled base plus separately scoped capability kits.

Avoid leading with:

- "AI companion that learns you forever."
- "Autonomous business operator."
- "AI that can act for you."
- "Mental health companion."
- "Financial/legal assistant."
- "Revenue agent."

Those may become domain packs later, but they should not be the first public promise.

## Legal And Liability Posture

Not legal advice. Before selling, this needs review by counsel for product liability, consumer protection, privacy, data security, terms, disclaimers, export controls if applicable, and state/EU AI rules.

Current regulatory backdrop to design around:

- The FTC is actively pursuing deceptive AI claims and AI-enabled scams. Marketing must be specific, substantiated, and not imply outcomes Vera cannot prove.
- The FTC also treats privacy/confidentiality promises as enforceable. If we say "local," "private," "encrypted," or "does not leave your device," the implementation must match exactly.
- The EU AI Act is already in force, with major application dates around 2025-2028 depending on system category. If sold into the EU, high-risk use cases and GPAI dependencies need classification.
- Colorado has moved toward regulating automated decision-making technology for consequential decisions, effective in 2027 under its revised framework. The safe path is to avoid making or materially influencing consequential decisions in employment, housing, credit, insurance, health care, education, or government services unless we build the compliance program.

Liability design principle:

> Sell tools that structure, calculate, document, verify, and preserve user agency. Do not sell a product that makes consequential decisions, gives regulated advice, or performs external actions on behalf of the user.

## Productization Options

### Option A - Privacy And Memory Vault

What is sold:
- A local-first personal AI memory vault.
- Encrypted storage.
- Search, summaries, recall, provenance, forget/export.
- Optional local model chat.

Why lower liability:
- It stores and organizes user-provided data.
- It does not make consequential decisions.
- It avoids external action.

Best buyer:
- Privacy-conscious individuals.
- Creators.
- Researchers.
- Executives.
- Families archiving personal knowledge.

Risk:
- Strong privacy promises must be true.
- Security hardening must be real.

Verdict:
- Best core product candidate after hardening.

### Option B - AI Governance And Verification Toolkit

What is sold:
- Cert stack, Diamond repeatability, claim registry, adversarial certs, audit ledger, privacy receipts.
- A framework for proving AI apps are not making unsupported claims.

Why lower liability:
- It helps other builders reduce risk.
- It is infrastructure, not an end-user advice system.

Best buyer:
- AI startups.
- Agencies.
- Internal tool teams.
- Compliance/security-forward dev shops.

Risk:
- Must avoid implying certification is legal compliance.

Verdict:
- Strong B2B wedge. Could monetize sooner than full Vera.

### Option C - Decision Calculator / Structured Reflection Tool

What is sold:
- A calculator-style interface for planning, tradeoffs, values, risks, next steps.
- It outputs organized options, not instructions or decisions.

Why lower liability:
- The user inputs assumptions.
- The tool shows calculations, tradeoffs, uncertainty, and reminders.
- It does not choose for the user.

Best buyer:
- Individuals making life/work decisions.
- Coaches/consultants who want a structured worksheet.
- Teams running planning sessions.

Risk:
- Avoid regulated domains unless carefully scoped.
- Do not call it legal, medical, financial, employment, or therapy advice.

Verdict:
- Good public-facing slice. Can carry Vera's philosophy without exposing Vera's full autonomy surface.

### Option D - Local AI Appliance / Self-Hosted Personal OS

What is sold:
- A local install or appliance with strong defaults.
- User owns keys, storage, model choices.
- Cloud optional and receipt-bearing.

Why lower liability:
- User-controlled environment.
- Lower data custody burden if no hosted data.

Risk:
- Product support burden.
- Security update obligations.
- Users can misconfigure it unless defaults are excellent.

Verdict:
- Long-term premium product. Not the first public SKU until hardening is complete.

### Option E - Domain Packs

What is sold:
- Optional packs: Revenue, Company Operator, Creative Studio, Research, Learning, Household Admin.

Why lower liability:
- Core product remains generic infrastructure.
- Higher-risk domains can have separate terms, warnings, certs, and gating.

Risk:
- Revenue/company/legal/financial packs create more liability.

Verdict:
- Keep domain packs modular and disabled by default.

## Recommended Commercial Sequence

1. Harden Base Vera as a complete portable personality/memory/privacy product.
2. Build the add-on kit substrate and manifests.
3. Sell `Vault Plus` and `Verify Pro` as the first safer kits.
4. Sell calculator-style decision tools as narrow public apps or kit workflows.
5. Keep Revenue, Company Operator, Connector, and Vera Council kits private until their certs and terms are ready.
6. Sell enterprise/appliance kits later, each with its own compliance posture.

This avoids making the first promise "trust this living AI with your life." Instead, the first promise is narrower and provable: "Here is private, local, inspectable AI infrastructure."

## Product Hardening Gates

### Gate 0 - No Public Sale

Current state.

Allowed:
- Internal use.
- Founder testing.
- private demos with explicit caveats.

Blocked:
- Paid consumer release.
- Claims of complete privacy.
- Claims of autonomous safety.
- Claims of legal/medical/financial/employment suitability.

Exit criteria:
- P1 weaknesses closed with adversarial certs.
- Security model documented.
- Product claims reviewed against implementation.

### Gate 1 - Private Alpha

Audience:
- 3-10 trusted technical users.

Allowed product:
- Local-only memory vault.
- Verification dashboard.
- No cloud by default.
- No external action.

Requirements:
- Auth required for any non-localhost exposure. CLOSED / CERTIFIED.
- Encryption consistently applied to private stores. CLOSED / CERTIFIED, including first-launch vault posture, local/keychain key source visibility, display-once recovery codes, salted-hash recovery storage, and key rotation.
- One-time pairing and session auth. CLOSED / CERTIFIED for supported same-origin browser shells; generated/displayed one-time pairing codes, authenticated minting of additional one-time codes, chat-shell first-launch pairing UX, HttpOnly cookies, session inventory, rotation, single-session revoke, logout-all, and desktop/LAN/tunnel/same-origin installed-shell replay/migration certs are closed. Custom-scheme installed wrappers remain a packaging constraint: they must proxy through the same localhost origin or receive a future explicit allowlist.
- Basic update/recovery story.
- Crash-safe backup/restore. ENCRYPTED BUNDLE + RESTORE DRILL CLOSED / CERTIFIED.
- Privacy receipt prototype.

### Gate 2 - Paid Design Partners

Audience:
- 5-20 paying users or businesses.

Allowed product:
- Governance/verification toolkit.
- Privacy vault.
- Calculator apps.

Requirements:
- Terms of service.
- Privacy policy.
- Security whitepaper.
- Support process.
- Vulnerability disclosure process.
- Domain restrictions.
- No consequential decision automation.

### Gate 3 - Public Beta

Audience:
- Broader paid beta.

Allowed product:
- Local Vera Core.
- Optional cloud cognition with receipts.
- Learning Studio beta.
- Domain packs limited to low-risk workflows.

Requirements:
- Threat model.
- Security review.
- Update channel.
- Telemetry opt-in/off by default.
- Data export/delete.
- Abuse reporting.
- Red-team/adversarial test suite.

### Gate 4 - General Availability

Audience:
- Public paid product.

Allowed product:
- Hardened Vera Core.
- Paid domain packs.
- B2B verification toolkit.

Requirements:
- Independent security assessment.
- Legal review of claims, UX, terms, and domain packs.
- Compliance classification for target markets.
- Insurance review.
- Incident response plan.
- Customer data handling plan.

## 5-Year Roadmap

### Year 0-1 - Trust Foundation And First Sellable Wedges

Goal:
Turn Vera from an impressive internal system into a defensible, narrow, sellable product family.

Build now:
- Kit manifest and entitlement system.
- Feature gates tied to kit manifests, not to Vera's core identity.
- Block unauthenticated `--expose`. CLOSED / CERTIFIED.
- Enforce per-turn local/cloud routing. CLOSED / CERTIFIED.
- Unify private storage and encrypt append-only ledgers. SUBSTANTIALLY CLOSED / CERTIFIED.
- Replace query-token/localStorage auth with pairing/session flow. CLOSED / CERTIFIED for supported same-origin browser shells.
- Implement full WebAuthn or rename current passkey honestly. CLOSED / CERTIFIED; real-device ceremony smoke test remains for packaging.
- Bind approvals to exact actions. CLOSED / CERTIFIED for company-operator action ledger, sales engagement, and foundry execution.
- Bind self-evolution approvals to exact proposals. CLOSED / CERTIFIED for high/core promotions.
- Enforce budget invariants. CLOSED / CERTIFIED.
- Add privacy receipts.
- Add adversarial cert pack.
- Create add-on kit manifest system.
- Move revenue/company surfaces into optional domain packs.

Productize:
- Base Vera: complete portable local personality, memory, privacy, and learning core.
- `Verify Pro` kit: AI claim/cert/repeatability toolkit.
- `Vault Plus` kit: advanced local private memory vault.
- `Vera Decision Sheets`: calculator-style reflection/planning tools.

Do not sell yet:
- Full companion autonomy.
- Health, legal, employment, credit, insurance, therapy, or financial advice.
- Autonomous marketplace/revenue operations.

Success metrics:
- P1 weaknesses closed.
- 20+ adversarial certs.
- 3 design partners.
- First paid pilot.
- Zero data custody by default.

### Year 1-2 - Paid Core And Trust UX

Goal:
Make Vera feel safe, understandable, and valuable to non-developers.

Build:
- Memory Rooms.
- What Vera knows about me explorer.
- Forget everywhere with proof.
- Learning Studio v1.
- Privacy receipt history. CLOSED / CERTIFIED with `/privacy` Privacy Flight Recorder, filters, connector policy, zero-egress state, and weather location precision.
- Human-readable action receipts.
- Cloud ask-every-time mode.
- Local model ladder.
- Installer/update/recovery flow.
- Product documentation and trust center.

Productize:
- Paid Base Vera.
- Paid Vault Plus.
- Paid Verify Pro B2B.
- Paid decision calculators.
- Companion mode as local-only, non-clinical, non-advisory.

Liability posture:
- Position as personal knowledge, reflection, and workflow infrastructure.
- Avoid "will improve mental health," "will make money," or "will make the right decision."

Success metrics:
- 100 paid users or 10 B2B customers.
- Clear retention around memory/search.
- Support burden understood.
- No unresolved P1 security findings.

### Year 2-3 - Domain Packs And Local Appliance

Goal:
Expand capability without letting any domain redefine the product.

Build:
- Domain pack marketplace/internal registry.
- Pack-specific privacy and action receipts.
- Pack-specific cert requirements.
- Local appliance packaging.
- Advanced backup/restore. ENCRYPTED BUNDLE + RESTORE DRILL CLOSED / CERTIFIED; local vault recovery-code and key-rotation lifecycle CLOSED / CERTIFIED; FIDO/passkey-wrapped multi-device recovery remains packaging work.
- Multi-device sync option with end-to-end encryption.
- Stronger model committee orchestration.

Productize:
- Research Pack.
- Creative Pack.
- Business Planning Pack.
- Revenue Pack only as draft/track/report, not autonomous submit/spend/message.
- Local appliance premium tier.

Liability posture:
- Each pack has separate scope, disclaimers, and disabled-by-default risky capabilities.
- No consequential decision pack unless counsel and compliance framework are ready.

Success metrics:
- 5-10 domain packs.
- Independent security review.
- Strong upgrade path from Vault to Core.

### Year 3-4 - Living Continuity Platform

Goal:
Make Vera uniquely valuable through long-term continuity, not raw model power.

Build:
- Identity Diff.
- Relationship/continuity timeline.
- Long-horizon goal memory.
- Personal doctrine and values map.
- Future-self protection flows.
- Relational honesty modes.
- Personal simulation/twin only with explicit boundaries.

Productize:
- Base Vera as the private continuity platform.
- Vera for creators/founders/researchers.
- Premium self-hosted plan.

Liability posture:
- Still avoid clinical/therapeutic claims.
- Frame as journaling, reflection, knowledge management, and planning support.

Success metrics:
- Users report value from continuity over time.
- Low churn among privacy-first users.
- Clear customer segment emerges.

### Year 4-5 - Ecosystem And Institutional Trust

Goal:
Make Vera a trusted local AI layer others can build on.

Build:
- SDK for domain packs.
- Formal cert authoring system.
- Pack review process.
- External audit support.
- Enterprise/local deployment profile.
- Cross-model committee marketplace.
- Strong policy engine for regulated domains.

Productize:
- Vera Platform.
- Vera Verify Enterprise.
- Certified pack ecosystem.
- Local AI governance appliance.

Liability posture:
- Enterprise agreements.
- Clear allocation of responsibility.
- Strong audit logs.
- Security/compliance partnerships.
- Insurance and formal incident response.

Success metrics:
- Repeatable sales motion.
- Certified partner packs.
- Enterprise pilots.
- Vera known for privacy and verification, not hype.

## Claims We Can Make Only After Fixes

Do not claim yet:
- "Encrypted by default" until all private stores use the same encrypted substrate.
- "Local-only by default" is now backed by per-turn backend enforcement, a zero-egress hard switch, certified privacy receipt/egress ledger coverage for cloud/web/weather/key-verification surfaces, the `/privacy` Privacy Flight Recorder, default-deny connector receipt policy, and coarse weather-location egress by default.
- "Secure LAN access" until expose requires auth and CSRF/origin defenses exist.
- "Passkey protected" is now backed by certified server-side WebAuthn assertion verification; still qualify packaging claims until real-device ceremony smoke tests are complete.
- "Autonomous governance" until broader workflow guards and remaining exception-domain reduction are fixed.

Claims that are closer to safe after hardening:
- Local-first.
- User-controlled.
- Inspectable memory.
- Human-in-the-loop.
- Optional cloud cognition.
- Verification-backed.
- No autonomous external action by default.

## Unique Selling Shapes That Reduce Liability

### Sell "Receipts," Not "Decisions"

Vera does not decide for you. Vera produces:
- privacy receipts
- action receipts
- memory receipts
- source receipts
- uncertainty receipts
- verification receipts

### Sell "Calculators," Not "Advice"

For high-risk areas, package as:
- assumption calculators
- scenario planners
- checklists
- comparison matrices
- journaling/reflection worksheets

Avoid:
- recommendations that determine eligibility
- scoring people for employment, credit, insurance, housing, education, or health care
- "you should" language in regulated domains

### Sell "Local Infrastructure," Not "Hosted Intelligence"

The strongest liability-reduction pattern is:
- customer owns data
- customer controls keys
- customer chooses model routes
- cloud calls require receipts
- external actions require explicit human confirmation

### Sell "Domain Packs," Not One Giant Being

The core product remains privacy/memory/governance. Packs are optional and separately scoped.

### Sell "Complete Base Plus Kits," Not Hosted Agency

The user buys Vera whole. Kits add specialized capabilities. They run Vera, hold their own data, and choose whether any cloud API is connected. This gives a cleaner separation than a hosted service, while avoiding the bad feeling of selling pieces of Vera's core identity.

### Sell "Verification For AI Builders"

Vera's cert culture may be the most immediately monetizable asset:
- claim registry
- live-path proofs
- adversarial certs
- Diamond repeatability
- route registry
- no-wallpaper audit

This can be sold without asking buyers to trust Vera with their entire personal life.

## Immediate 90-Day Plan

Weeks 1-2:
- Define Base Vera feature guarantee.
- Define add-on kit manifest format.
- Add kit gate skeleton to capabilities/domain packs.
- Fix unauthenticated expose. CLOSED / CERTIFIED.
- Add cert for expose refusal. CLOSED / CERTIFIED.
- Write threat model v1.
- Define product claims blacklist.

Weeks 3-4:
- Enforce per-turn backend routing. CLOSED / CERTIFIED.
- Add fake-cloud no-egress cert. CLOSED as route-backend enforcement; zero-egress hard switch for cloud/web/weather also CLOSED / CERTIFIED.
- Add privacy receipt event schema. CLOSED / CERTIFIED for per-turn receipts and current cloud/web/weather/key-verification egress ledger.
- Add Privacy Flight Recorder, connector receipt policy, and coarse-location UX. CLOSED / CERTIFIED.

Weeks 5-6:
- Build unified encrypted private store.
- Migrate truth/observation/company direct writes.
- Add raw-secret absence cert. CLOSED / CERTIFIED for current private-store matrix.

Weeks 7-8:
- Replace query-token UX with pairing/session. CLOSED / CERTIFIED for supported same-origin browser shells.
- Add Origin/Host checks. CLOSED / CERTIFIED for same-host browser POST boundary.
- Add CSRF hostile-origin cert. CLOSED / CERTIFIED.
- Add first-launch one-time pairing UX. CLOSED / CERTIFIED for generated startup codes and the main chat shell.
- Add session rotation and device inventory. CLOSED / CERTIFIED.
- Add multi-shell replay/migration certs. CLOSED / CERTIFIED for desktop localhost, LAN browser, HTTPS tunnel, and same-origin installed/webview shells.

Weeks 9-10:
- Bind approvals/actions. CLOSED / CERTIFIED for company-operator action ledger, sales engagement, and foundry execution.
- Bind self-evolution approvals/proposals. CLOSED / CERTIFIED for high/core promotions.
- Enforce budget invariants. CLOSED / CERTIFIED.
- Add governance adversarial certs.

Weeks 11-12:
- Create add-on kit manifest format.
- Move revenue/company to optional pack posture.
- Draft Base Vera, Vault Plus, and Verify Pro product pages internally.
- Prepare counsel packet: architecture, claims, privacy model, data flows, terms questions.

## Counsel Packet Questions

Ask counsel:
- What claims can we safely make about local-first, privacy, encryption, and AI verification?
- What disclaimers are needed for calculator-style decision tools?
- Which domain packs create regulated advice or consequential-decision risk?
- What should the terms say about user-controlled local deployment?
- What insurance should we carry before public beta?
- How should we handle user-generated memories, exports, deletion, and cloud calls?
- What jurisdictions should we avoid until compliance work is complete?

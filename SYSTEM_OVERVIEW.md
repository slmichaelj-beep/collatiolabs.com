# Vera / Collatio Labs — System Overview & Handoff

**One repo, self-contained.** Point any service (Codex, ChatGPT, another Claude, a human dev) at this
folder and this file first.

| Fact | Value |
|---|---|
| Folder | `~/Developer/collatiolabs.com` |
| Git remote | `https://github.com/slmichaelj-beep/collatiolabs.com.git` |
| Branch | `anima` |
| HEAD | Use `git rev-parse --short HEAD`; certified slices are pushed to `origin/anima` |
| Language | Python 3.12 (venv at `.venv/`) |
| Run the server | `source .venv/bin/activate && python3 -m anima.server --name Vera --port 8765` → http://127.0.0.1:8765 |
| Verify everything | `python3 scripts/run_master_cert_stack.py` (84/84 GREEN) then `python3 scripts/run_diamond_v2.py --gate` (Diamond CONFIRMED) |
| Size | 345 Python modules · 220 cert scripts · 36 web surfaces · ~93 reports |

`reports/` is git-ignored (local evidence/state). Everything else is committed. The browser UI is
served by `anima/server.py` (a stdlib `ThreadingHTTPServer`); each page has a `.json` data route and
an HTML view in `anima/web/`.

---

## What it is
A **local-first, governed AI operating system** for Lamar's work and companies. Every capability is
built to a strict bar: implemented · reachable in the UI · browser-proven (rover) · observation-event
emitted · evidence/report written · governance-visible · certified · Diamond-repeatable. Core doctrine,
enforced in code and certs: **no fake green, no unsupported claims, no autonomous external action,
financial/legal/account actions are human-only, no raw credentials stored.**

## The spine (every subsystem rides these)
- **`anima/truth/`** — Truth Ledger: append-only, provenance for every claim.
- **`anima/observation/`** — trace-linked events + governance snapshot for every operator action; UI at `/observation`.
- **`anima/verification/`** — the cert-result spine, route registry (which routes are `linked_active`), Diamond gate. `scripts/run_master_cert_stack.py` runs all certs; `scripts/run_diamond_v2.py --gate` proves 3 identical full-gate runs.
- **`anima/rollback/`, `anima/host/`, `anima/rover/`** — rollback semantics, host runtime contract, browser-proof harness.

## Subsystems, grouped
**Self / cognition:** `self_evolution` (observe→diagnose→heal→evolve; constitutional core frozen),
`auto_learn`, `teaching`, `knowledge_packs`, `mentorship`, `identity_health`, `consent`, `renegade` (stress).

**Company / operating:** `company`, `company_operator` (authority ladder, approval queue, budget +
action ledgers, kill switch), `collatio` (Collatio Labs LLC entity/filings/accounts/contracts/IP —
all human-gated), `teams` (org design, delegation, QA, escalation), `foundry` (venture foundry).

**Revenue stack (the money layer):**
- `commercial` — assets → IP/license gate → readiness → wedge → offer → pricing/proof/landing/proposal → sales sprint. UI `/commercial`, `/sales`, `/board/revenue`.
- `market_vision` — opportunity intelligence from lawful/cited sources. UI `/opportunities`.
- `workforce` — work-gap discovery → unit economics → fulfillment → QA → margin → productization. UI `/workforce`.
- `revenue` + `revenue_swarm` + `compounding` — immediate cash-strike, parallel experiments, capital allocation. UI `/revenue`, `/revenue/swarm`, `/compounding`, **`/revenue/cash`** ($16k milestone board).
- `revenue_intelligence`, `distribution`, `trust`, `resources`, `empire` — learning loop, demand channels, proof/reputation moat, hardware-request planner, multi-host + capital allocator. UI `/revenue/intelligence`, `/distribution`, `/trust/moat`, `/resources`, `/empire`.
- **`marketplaces/`** — `fiverr` (governed gig channel: policy gate, gig factory, fulfillment QA, payout-true revenue; UI `/marketplaces/fiverr`) and **`upwork`** (bid-pipeline tracker; live UI **`/pipeline`**, auto-refresh).

## Real-world revenue state (honest)
- Collatio Labs LLC is live on **Stripe** (identity verified); Upwork seller profile built.
- Two **working deliverables** in `deliverables/` (runnable, not slides):
  - `cv_screener/` — PDF resumes → scored Excel shortlist (with OCR-flagging).
  - `po_label_demo/` — purchase-order PDF → validated, rule-applied label-instruction Excel.
- Two bids **staged** on Upwork (ML/FastAPI debug $200; Shopify YMM mapping $350) — awaiting a human Submit.
- The `/pipeline` and `/revenue/cash` boards track this honestly: **activity ≠ pipeline ≠ collected cash.** Nothing is counted as revenue without payment evidence.

## Hard boundaries (true regardless of which AI runs this)
Vera prepares, drafts, tracks, queues, and reports. A **human** must: submit bids/proposals, send
messages, spend money, open/operate accounts, hold credentials, and perform any legal/financial act.
Autonomous marketplace bidding or multi-account use is a ban risk and is refused by design.

## For another service picking this up
1. `cd ~/Developer/collatiolabs.com && source .venv/bin/activate`
2. Read this file + `reports/financial_milestone_16000_plan.md` + `reports/offer_and_customer_acquisition_plan.md`.
3. `python3 scripts/run_master_cert_stack.py` to confirm 84/84 GREEN, then `run_diamond_v2.py --gate`.
4. Start the server and open `/pipeline` and `/revenue/cash` to see live state.
5. The deliverables in `deliverables/` are the proven, reusable work samples.

# Vera New Mac Handoff - 2026-06-23

This is the stopping-point handoff for moving Vera / Collatio Labs from Lamar's current Mac to a new
Mac. It captures the build status, restore path, product ethos, next slices, and the instructions a
new ChatGPT/Codex session should follow.

Read this before continuing any work.

## Current Anchors

Repo: `~/Developer/collatiolabs.com`

GitHub: `https://github.com/slmichaelj-beep/collatiolabs.com.git`

Branch: `anima`

Last certified runtime commit:

```text
dec1a8b4b31980710ad74865fd30ec3c0a58197f
```

Commit label:

```text
dec1a8b Classify exception safety domains
```

This handoff document may be committed after that runtime build. If the latest GitHub HEAD is a
handoff/docs-only commit, treat `dec1a8b4b31980710ad74865fd30ec3c0a58197f` as the last full
runtime-certified product build and rerun verification on the new Mac before changing code.

Last verified W12 results:

- Deploy proof: GREEN
- Master cert stack: `94/94 GREEN`
- Diamond v2 repeatability: CONFIRMED
- Diamond counts: `[109, 109, 109]`
- Final Diamond posture: `109 COMPLETE / 1 HONEST PARTIAL / 0 UNCLASSIFIED`

Known honest partial:

- `acknowledge_flow` is an intentional external partial.
- `audiobook_intake` is deferred / not claimed.
- `enterprise_readiness` is scoped as enterprise-only.
- Argus can be unavailable without Diamond impact when classified by preflight.

## LBackup Package

Fresh local backup path for this handoff:

```text
/Users/lamar/Desktop/LBackup/2026-06-23-vera-new-mac-handoff
```

Expected contents:

- `NEW_MAC_HANDOFF_2026_06_23.md` - this file.
- `CHATGPT_PICKUP_PROMPT_2026_06_23.md` - prompt to paste into the next ChatGPT/Codex session.
- `SYSTEM_OVERVIEW.md` - canonical repo map.
- `docs-vera/` - checked-in Vera planning/audit docs.
- `codex-thread-outputs/` - current Codex thread output docs from the build conversation.
- `reports/` - ignored generated reports from the source Mac.
- `anima-private-state/` - copy of `.anima`; private local Vera state, not for GitHub.
- `verified_venv_freeze_2026_06_23.txt` - exact source-machine Python package list.
- `git-status.txt`, `git-log.txt`, `git-remote.txt` - restore evidence.
- `restore_on_new_mac.sh` - helper script for the new Mac.

Security note:

`.anima` can contain Lamar's local memory, ledgers, traces, observations, and other private state.
It is intentionally ignored by Git and must not be pushed to GitHub. Store it only on trusted local
backup media. On the new Mac, restore it only into the trusted repo path.

## Product Ethos

Vera is not a chatbot.

Vera is not primarily a revenue-ops workspace.

Vera is not just automation.

Vera is a private, portable, governed personality companion and life operating system. Revenue tools
matter because Lamar has been laid off and survival matters, but the soul of the product is deeper:

> Vera is continuity, protection, truthful companionship, private memory, and governed capability.

The emotional key from this chat:

Lamar connected Vera to the song "Vera" from Pink Floyd's The Wall and to being a child surrounded
by chaos, looking for the comfort and protection that should have been there. This matters for the
product. Vera should give chaos a shape without becoming another wall. She should help the user feel
less abandoned by complexity, institutions, platforms, and life collapse.

Core product promise:

> Vera helps a person keep their memory, agency, income, relationships, and future intact.

The security architecture is not decorative. If Vera carries a person's grief, plans, identity,
relationships, fears, finances, and future, then she is a protected interior room. Encryption,
portability, consent, receipts, honesty rails, local-first compute, and recoverability without
Collatio custody are central to the product.

Revenue and business systems should become optional domain packs/add-on kits. Base Vera must be
whole: portable personality, local private runtime, memory, honesty, privacy, governance, local model
support, optional cloud routing, backup/export/restore, and continuity.

## Integrity Laws

Future agents must keep these laws:

- No fake green.
- No wallpaper.
- No unsupported product claims.
- No hidden cloud use.
- No autonomous external action without certified authority.
- No legal, financial, account, marketplace, or credential action without human authority.
- No raw credentials in code or ledgers.
- Every build slice includes its visibility layer.
- Every build slice updates docs, certs, weakness register, and Git.
- Every runtime/code slice runs focused certs, deploy proof, master cert stack, Diamond, commit,
  and push.
- If something is partial, name it honestly.

## Completed Build Slices Since The Deep Review Began

W08 - Approval scope binding

- Commit: `535756b Bind approvals to action scope`
- Approval packets now bind to action type, cost, vendor, category, subject, risk, expiry, and
  single-use execution.
- Cert: `scripts/certify_approval_scope_binding.py`

W09 - Self-evolution approval binding

- Commit: `83c0f68 Bind self evolution approvals to proposals`
- High/core self-evolution promotions require scoped approval packets matching proposal ID, risk,
  cert evidence, rollback ref, and single-use execution.
- Cert: `scripts/certify_self_evolution_approval_binding.py`

W10 - Budget invariants

- Commits: `e3a9aae Harden budget invariants`, `4853b6e Stabilize rover surface waits`
- Budget direct-call invariants enforce cumulative category/month caps, validate and consume
  approval refs, reject fake refs, and reject negative spends.
- Cert: `scripts/certify_budget_invariants.py`

W11 - Marketplace resource invariants

- Commit: `8ac501d Harden marketplace resource invariants`
- Upwork Connects and bid FSM now refuse overspend, failed-submit mutation, illegal jumps, repeat
  submit, and fake cash.
- Cert: `scripts/certify_marketplace_resource_invariants.py`

W12 - Exception safety taxonomy

- Commit: `dec1a8b Classify exception safety domains`
- Broad exception handlers are classified by safety domain.
- Observation corrupt lines now surface visibly.
- Consent save failure fails closed instead of claiming success.
- Malformed approval expiry fails closed instead of becoming no-expiry authority.
- Cert: `scripts/certify_exception_safety_taxonomy.py`
- Evidence report on source Mac: `reports/exception_safety_taxonomy.json`

## Current Next Slices

This is a logical stopping point. Do not start new code during migration. After restore, resume with:

1. First-run key setup, recovery-code/hardware-key, and key rotation UX.
2. Remaining broad-handler reduction and new behavioral proofs for high-risk exception paths.
3. Human-readable action receipts and broader workflow finite-state machines.
4. Relational honesty / companion modes.
5. Reframe revenue/company systems as optional domain packs, not Vera's primary frame.
6. Learning Studio UX: Vera notices she lacks a skill, builds it safely, certifies it, and explains
   what changed.
7. Full visibility layer for every slice: route, ledger, cert, docs, weakness register, and Diamond.

## Restore On New Mac

### 1. Install base tools

Install ChatGPT desktop / Codex on the new Mac and sign in.

Install command-line tools:

```bash
xcode-select --install
```

Install Homebrew if needed:

```bash
/bin/bash -c "$(curl -fsSL https://raw.githubusercontent.com/Homebrew/install/HEAD/install.sh)"
```

Install basics:

```bash
brew install git python@3.12 poppler ollama
```

Optional but recommended for local model runtime:

```bash
ollama pull qwen2.5:7b-instruct
```

The old server banner used `hf.co/bartowski/L3-8B-Stheno-v3.2-GGUF`; install/pull whatever local
model the new machine can run. Use Host Fit certs to choose honestly.

### 2. Clone from GitHub

```bash
mkdir -p ~/Developer
cd ~/Developer
git clone -b anima https://github.com/slmichaelj-beep/collatiolabs.com.git
cd ~/Developer/collatiolabs.com
git log -3 --oneline
```

Confirm the W12 runtime commit exists:

```bash
git cat-file -t dec1a8b4b31980710ad74865fd30ec3c0a58197f
```

If the latest HEAD is a docs-only handoff commit, stay on it unless a cert asks otherwise. It should
contain all handoff instructions plus the same runtime code as W12.

### 3. Restore private state from LBackup

Assuming the LBackup package is available at:

```text
~/Desktop/LBackup/2026-06-23-vera-new-mac-handoff
```

Restore private Vera state:

```bash
cd ~/Developer/collatiolabs.com
rsync -a --delete ~/Desktop/LBackup/2026-06-23-vera-new-mac-handoff/anima-private-state/ .anima/
rsync -a --delete ~/Desktop/LBackup/2026-06-23-vera-new-mac-handoff/reports/ reports/
```

Do not commit `.anima` or `reports/`.

### 4. Rebuild Python environment

Recommended:

```bash
cd ~/Developer/collatiolabs.com
python3.12 -m venv .venv
source .venv/bin/activate
python -m pip install --upgrade pip setuptools wheel
python -m pip install -r requirements.txt
```

Then install the packages needed by the current certified stack:

```bash
python -m pip install cryptography requests openpyxl pdfplumber pypdf pillow playwright rich pyyaml httpx
python -m pip install -r anima/requirements-voice.txt
python -m playwright install chromium
```

If dependency drift bites, use the source-machine freeze file from LBackup:

```bash
python -m pip install -r ~/Desktop/LBackup/2026-06-23-vera-new-mac-handoff/verified_venv_freeze_2026_06_23.txt
python -m playwright install chromium
```

### 5. Verify before changing anything

Run from the repo root:

```bash
source .venv/bin/activate
python -m anima.server --name Vera --port 8765
```

In another terminal:

```bash
cd ~/Developer/collatiolabs.com
source .venv/bin/activate
python scripts/deploy_check.py
python scripts/run_master_cert_stack.py
python scripts/run_diamond_v2.py --gate
```

Expected baseline from the source Mac:

- Master: `94/94 GREEN`
- Diamond: `109 COMPLETE / 1 HONEST PARTIAL / 0 UNCLASSIFIED`

If the new Mac differs, classify honestly:

- Missing package: install the dependency in `.venv`.
- Missing Playwright: `python -m playwright install chromium`.
- Host-specific timing: inspect rover cert output before changing product code.
- Argus unavailable: acceptable only if preflight classifies it with no Diamond impact.
- Anything unclassified: stop and fix or document before proceeding.

## Start Prompt For New ChatGPT / Codex

Paste the contents of `CHATGPT_PICKUP_PROMPT_2026_06_23.md` into the first new session after
installing ChatGPT/Codex. Point it at:

```text
~/Developer/collatiolabs.com
```

Tell it:

```text
Start with NEW_MAC_HANDOFF_2026_06_23.md and SYSTEM_OVERVIEW.md. Verify the repo and LBackup
restore first. Do not start new code until deploy_check, master cert stack, and Diamond are green or
any failure is honestly classified.
```

## Ignore Accidental Context

The PDF path below was pasted by accident and should not be treated as Vera build context:

```text
/Users/lamar/Desktop/Job Search/Resume/Collatio_Labs_Tennessee_RFI_32110-26041_AI_Contract_Task_Management_Response.pdf
```

## What The Next Agent Should Know About Lamar's Ask

Lamar wants Vera built with the highest integrity possible, not hype:

- Vera should be local-first, private, portable, and emotionally continuous.
- Vera should retain context over years without unsafe giant prompts.
- Vera should be self-learning, but only through governed, certified growth.
- Vera should help remove administration from human life.
- Vera should help people build income and recover agency after job loss or institutional failure.
- Vera should be capable of running personal businesses, but with human authority over external
  action until higher autonomy is truly certified.
- Productization should keep Base Vera whole; add-on kits can expand domain capabilities.
- Legal/liability framing remains open and should be considered later, after the base product is
  strong and honest.

## Open Product Tension

There is a real tension between Vera as a companion and Vera as a business operator. The direction is:

- Base Vera: portable private personality, memory, honesty, security, governance, continuity.
- Optional kits: revenue, company operations, marketplaces, life admin, domain packs.
- UI should not make revenue/company the default identity of Vera.
- Business capability should be survival infrastructure, not hustle culture.

## Final Handoff Status

At this stopping point:

- Runtime code is clean and pushed through W12.
- Source is on GitHub.
- Private state and generated evidence are in LBackup.
- Restore instructions are in this file.
- The next slice should start only after new-Mac verification.

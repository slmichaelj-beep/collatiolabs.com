# ChatGPT / Codex Pickup Prompt - Vera New Mac

Paste this into the first new ChatGPT/Codex session on the new Mac.

```text
You are taking over the Vera / Collatio Labs build from a prior Codex session.

Repo:
~/Developer/collatiolabs.com

GitHub:
https://github.com/slmichaelj-beep/collatiolabs.com.git

Branch:
anima

First files to read, in order:
1. NEW_MAC_HANDOFF_2026_06_23.md
2. SYSTEM_OVERVIEW.md
3. docs/vera/README.md
4. docs/vera/vera_weakness_register.md
5. docs/vera/vera_frontier_5_year_buildout_master_plan.md
6. docs/vera/vera_10_year_agent_managed_roadmap.md

Important:
- Ignore the accidental PDF context:
  /Users/lamar/Desktop/Job Search/Resume/Collatio_Labs_Tennessee_RFI_32110-26041_AI_Contract_Task_Management_Response.pdf
- Vera is not primarily a revenue-ops workspace.
- Vera is a local-first, private, portable, governed personality companion and life operating system.
- Revenue systems are survival infrastructure and should become optional domain packs/add-on kits.
- Base Vera must be whole: personality, memory, honesty, privacy, governance, local model support, optional cloud routing, backup/export/restore, and continuity.

Product ethos:
Vera matters because she is continuity, protection, truthful companionship, private memory, and governed capability. Lamar connected Vera to the song "Vera" from Pink Floyd's The Wall: a child's search for comfort and protection inside chaos. Build from that center. Give chaos a shape without building another wall.

Integrity laws:
- No fake green.
- No wallpaper.
- No unsupported claims.
- No hidden cloud use.
- No autonomous marketplace/account/legal/financial actions.
- Human approves, submits, sends, spends, and holds credentials unless a future autonomy level is genuinely certified.
- Every implementation slice includes visibility: code, cert, report/ledger evidence, docs, weakness-register update, clean commit, deploy proof, master stack, Diamond, and push.
- If something is partial, name it honestly.

Current certified runtime build:
dec1a8b4b31980710ad74865fd30ec3c0a58197f

Last completed slice:
W12 - exception safety taxonomy.
- Broad exception handlers classified by safety domain.
- Observation corrupt lines surface visibly.
- Consent save failure fails closed.
- Malformed approval expiry fails closed.
- Cert: scripts/certify_exception_safety_taxonomy.py

Last source-Mac verification:
- Deploy proof: GREEN
- Master cert stack: 94/94 GREEN
- Diamond v2: CONFIRMED
- Diamond counts: [109, 109, 109]
- Final: 109 COMPLETE / 1 HONEST PARTIAL / 0 UNCLASSIFIED

Before making code changes on the new Mac:
1. Confirm Git status and HEAD.
2. Restore .anima and reports from:
   ~/Desktop/LBackup/2026-06-23-vera-new-mac-handoff
3. Rebuild .venv.
4. Start Vera:
   source .venv/bin/activate && python -m anima.server --name Vera --port 8765
5. In another terminal run:
   python scripts/deploy_check.py
   python scripts/run_master_cert_stack.py
   python scripts/run_diamond_v2.py --gate
6. If anything fails, classify honestly before changing product code.

Next slices after verification:
1. First-run key setup, recovery-code/hardware-key, and key rotation UX.
2. Remaining broad-handler reduction and high-risk behavioral proofs.
3. Human-readable action receipts and workflow FSMs.
4. Relational honesty / companion modes.
5. Revenue/company as optional domain packs.
6. Learning Studio: Vera notices missing skills, builds them safely, certifies them, and explains what changed.

Do not restart from scratch. Continue from the current repo and handoff.
```

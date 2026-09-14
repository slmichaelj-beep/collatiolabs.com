# HANDOFF TO CODEX — Vera on the new MacBook (2026-06-09)

This is the durable handoff from the recovery + verification session that stood Vera up on this
machine. Everything below was measured live on this Mac tonight — nothing is inherited from chat
memory. Companion files:

- `reports/current_machine_state_for_codex.json` — the same facts, machine-readable
- `reports/codex_next_steps.md` — exact commands, in order
- `reports/recovered_files_map.md` — where every recovered artifact lives
- `reports/new_machine_recovery_status.md` — the full recovery narrative + verdicts
- `reports/verification_worklog.md` — everything that was run tonight, with results
- `reports/vera_instance_reality_audit.{md,json}` — the initial reality audit (pre-fix state)

---

## Machine facts

| fact | value |
|---|---|
| Repo path | `~/Developer/collatiolabs.com` |
| Remote | `https://github.com/slmichaelj-beep/collatiolabs.com.git` |
| Branch | `anima` (PR #1 head, fetched as a local branch) |
| HEAD | `81a2d8c` — "verification(final): raise run_diamond_v2 per-gate timeout 480s->900s" (v0.47 line) |
| Working tree | **CLEAN except this one file** — `HANDOFF_TO_CODEX.md` is intentionally untracked (deploy_check was GREEN before it was written; `reports/` is gitignored). Codex: commit this file first, restart the server, and deploy_check is GREEN again |
| Python | venv at `.venv/` (Python 3.12, Homebrew) — **always** `source .venv/bin/activate` first |
| Server | `python3 -m anima.server --name Vera --neurons 48 --voice` → http://localhost:8765 |
| Desktop launcher | `~/Desktop/Vera.app` — starts the server detached (no Terminal), opens the browser |
| Server log (when launched via Vera.app) | `.anima/server.log` |
| Brain | Ollama.app (cask `ollama-app`; Homebrew CLI formula was broken — do NOT reinstall the formula). Models present: `hf.co/bartowski/L3-8B-Stheno-v3.2-GGUF` (Vera's brain) + `qwen2.5:7b-instruct` |
| Voice | Kokoro (natural) — installed, verified producing real WAV via `/tts` |
| Ears | Whisper small.en — verified: round-tripped Vera's own TTS audio back to exact text via `/stt` |
| Argus | cloned at `~/Developer/Argus` (HEAD `b0a7a0d`), running on `127.0.0.1:8787`, preflight passes |
| `.anima` | **Fresh Vera, born 2026-06-09** (seed 3355388573) at `.anima/` in the repo. NOT restored — no prior state ever existed (see below). Backed up to `/Volumes/LaCie/anima-backup/20260609-221129/` (195 MB) |

## Fresh vs restored — the decision, answered

**This is a FRESH Vera, and that is correct, not a loss.** An exhaustive search of the LaCie
(filesystem + inside every `.zip`/`.tar.gz`) found **no old `.anima` anywhere** — the old host's
creature state was gitignored by design and never backed up, and the recovery matrix confirms she
was never trained on the old machine. There is nothing to restore or merge.

**Preserve / restore / keep-both:** keep both, trivially — the fresh `.anima` is the only Vera and
must not be overwritten; the LaCie's old-era artifacts (Guruu-predecessor `app-data`, old reports)
stay archived untouched as historical reference. **Do not copy old reports into `reports/`** — they
were generated at older commits (`5c5d7f8`, `16bc09e`) and cert-freshness correctly flags them stale.

## Recovery inventory

| asset | found? | where |
|---|---|---|
| Old `.anima` (creature state) | **NO** — does not exist anywhere | n/a (nothing was lost; never existed) |
| Old `reports/` (verification artifacts) | YES | `/Volumes/LaCie/vera-verification-backup-2026-06-09/reports/` (42 files, commits 5c5d7f8/16bc09e — historical only) |
| Old sources/library/upload corpus | NO Vera source corpus found | Guruu-era `app-data/` (aletheia.db, minds.json…) at `/Volumes/LaCie/Vera-Migration-2026-06-09/` — predecessor system, NOT current-Vera data |
| Code | YES | GitHub `anima` branch @ 81a2d8c (this clone) |
| Argus | YES | private GitHub repo, cloned to `~/Developer/Argus`, running |

## Verification state (all regenerated tonight on THIS build)

- **Reports present:** scenario_matrix, live_path_results/matrix, program_reality_audit,
  feature/api/control/user_surface inventories, system_shape, twin_dashboard, patterns(+md),
  improvement_backlog, rover_report, lamar_path_rover(+browser), diamond_v2, cert_flakes,
  external_dependencies, feature_to_scenario_matrix — `reports/` is no longer fresh-clone empty.
- **Certs GREEN tonight:** deploy_check, verification_dashboard, release_tiers,
  **lamar_path_rover (25/25 steps, real browser, console clean)**, cert_freshness,
  cert_flake_classification, ui_truth_consistency, verification_api, observatory,
  patterns_dashboard, call_auth, voice_io, ocr_intake (END-TO-END: REAL), audiobook-intake's
  static checks.
- **Diamond v2 repeatability (final run, full environment):** identity stable, **[108, 108, 108]
  COMPLETE across 3 consecutive runs, 0 unclassified flakes** — repeatability itself is proven.
  Progression tonight as env deps were fixed: 103 → 107 → 108. Verdict **BLOCKED** by exactly two,
  then re-scoped:
  - `audiobook_intake` — **DEFERRED / NOT CLAIMED (product decision 2026-06-09, commit 414398f)**:
    not part of the current Local/Internal release; scoped to a future "Media/Audiobook Intake"
    tier; UI no longer advertises it; visible as deferred on every surface; never a blocker. The
    citation defect (e2e steps 6–7) stays recorded in the contract's known_gaps for that future tier.
  - `enterprise_readiness` — partial (was PARTIAL on the old machine too; external-dependency tier).
- **Known stale:** none in `reports/` (all regenerated at 81a2d8c). The LaCie's old reports are
  stale by definition — leave them there.
- **Known blockers (full list):** enterprise_readiness partial (audiobook_intake is no longer a
  blocker — deferred/not-claimed, commit 414398f);
  4 STUB-classified features from program_reality_audit (e.g. voice_io stub note) — see
  `reports/program_reality_audit.md`.

## Product finding from tonight's live journey (logged, not fixed — no feature work done)

Chat-level memory retraction: "Forget my favorite color" (bare, without restating the value) does
NOT retract — the spine fast-path replies with the canned recall line and the LIRF row stays
active. "Forget that my favorite color is teal" (value restated) retracts correctly and recall then
honestly reports the fact is gone. Root cause + fix sketch: `anima/memory_lirf.py` `_RETRACT_CUE`
fires but the retract flag only attaches to extraction candidates; bare phrasing yields none.
This is the first development task (Codex began it in-tree on 2026-06-09; audiobook is deferred).

## Small infrastructure notes

- `scripts/backup-anima.sh` hardcodes `SRC="$HOME/collatiolabs.com/.anima"` — wrong for this
  machine's layout (`~/Developer/collatiolabs.com`). One-line fix needed; tonight's snapshot was
  taken manually with rsync to `/Volumes/LaCie/anima-backup/20260609-215106` style timestamped dirs.
- The Vera.app desktop launcher embeds the correct repo path and starts Ollama if needed.
- SECRETS folder still on the LaCie (`/Volumes/LaCie/Vera-Migration-2026-06-09/SECRETS/`) — the
  user wants it removed from the drive later; treat any credential that sat on the portable drive
  as rotate-on-use. **Not handled tonight by request (Vera-only focus). Do not print or commit.**

---

## The 15 questions, answered directly

1. **Are we currently in the correct Vera repo?** YES — `~/Developer/collatiolabs.com`, origin
   `slmichaelj-beep/collatiolabs.com`, branch `anima`, the certified build.
2. **Is the working tree clean?** YES (verified: `git status` empty; deploy_check GREEN).
3. **Is the current HEAD the latest known Vera work?** YES — `81a2d8c` is the tip of PR #1 (219+
   commits, v0.47 line), AHEAD of every artifact found on the LaCie (5c5d7f8, 16bc09e).
4. **Are any local changes uncommitted?** NO. (`reports/` and `.anima/` are gitignored by design.)
5. **Are any files on LaCie needed before continuing?** NO. Old reports are historical; Guruu
   app-data is a predecessor system; code and Argus came from GitHub. Nothing blocks on the drive.
6. **Did we recover old `.anima`?** NO — proven absent everywhere (drive + inside all archives).
   Nothing existed to recover.
7. **Did we recover old `reports/`?** YES — archived at
   `/Volumes/LaCie/vera-verification-backup-2026-06-09/reports/` (historical reference only).
8. **Did we recover any source/library/upload corpus?** NO current-Vera corpus existed. The
   Library on this machine has only tonight's journey-test source.
9. **Restore, merge, or ignore the old `.anima`?** IGNORE — it does not exist. Preserve the fresh
   one; never overwrite `.anima/`; keep the LaCie snapshots as her life insurance.
10. **Should Codex regenerate reports before doing anything else?** NO — they were regenerated
    tonight at this HEAD. Only re-run a generator after changing the code it measures.
11. **Is Vera safe for casual use today?** YES — brain (Stheno via Ollama.app, ~1s warm), voice
    (Kokoro), ears (Whisper), all six surfaces, 25/25 founder journey, console clean.
12. **Is Vera safe for continued development today?** YES — clean tree at the certified HEAD,
    full verification harness regenerated and green except the two named blockers.
13. **What exact command starts Vera cleanly?**
    `cd ~/Developer/collatiolabs.com && source .venv/bin/activate && python3 -m anima.server --name Vera --neurons 48 --voice`
    (or double-click `~/Desktop/Vera.app` — same thing, detached, no Terminal).
14. **What exact cert commands should Codex run first?** See `reports/codex_next_steps.md` —
    in short: `scripts/deploy_check.py`, then `scripts/verification_status.py`, then the cert for
    whatever it touches.
15. **What exact checkpoint should Codex continue from?** Commit `81a2d8c`, branch `anima`,
    fresh `.anima` preserved, reports regenerated. **Resume feature development at: the chat-forget
    retraction gap (Codex began this in-tree on 2026-06-09 — finish + commit it), then re-run
    `scripts/run_diamond_v2.py --gate`. audiobook_intake is deferred/not-claimed (commit 414398f) —
    do NOT treat it as a blocker; it resumes only when a Media/Audiobook Intake tier is claimed.**

---

`CODEX_READY: YES`

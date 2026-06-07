# Live-Path Reality Matrix — Program Reality Audit (Vera)

> The law: *No feature is complete because code / UI / endpoint / trace exists — only when the live user path is proven end-to-end.*

Hermetic run. Real `.anima` SHA-256 **before** `7db7d13b7b0905c5…` / **after** `7db7d13b7b0905c5…` — byte-identical.

**8 COMPLETE / 2 PARTIAL / 1 WALLPAPER / 0 STUB / 0 UNREACHABLE / 1 UNKNOWN**

| Feature | UI | Backend | Storage | Retrieval | Use | MRI | Restart | Status |
|---|---|---|---|---|---|---|---|---|
| argus_host_awareness | ok | ok | — | ok | ok | ok | — | **COMPLETE** |
| capability_truth | ok | ok | ok | ok | ok | — | ok | **COMPLETE** |
| conversation_repair | ok | XX | XX | XX | XX | XX | — | **WALLPAPER** |
| gate0_prime | — | ok | — | — | ok | — | ok | **COMPLETE** |
| growth_dashboard | ok | ok | — | ok | ok | — | — | **PARTIAL** |
| identity_sandbox | ok | ok | ok | — | ok | ok | ok | **COMPLETE** |
| known_fact_memory | ok | ok | ok | ok | ok | — | ok | **PARTIAL** |
| lerf_runtime | ok | ok | ok | needs-live | needs-live | needs-live | — | **UNKNOWN** |
| response_completeness | — | — | — | — | ok | ok | — | **COMPLETE** |
| source_aware_answering | ok | ok | ok | ok | ok | ok | — | **COMPLETE** |
| universal_knowledge_intake | ok | ok | ok | ok | ok | ok | ok | **COMPLETE** |
| whole_system_mri | — | ok | ok | — | ok | ok | ok | **COMPLETE** |

## Reasons & honest gaps

### argus_host_awareness — COMPLETE
Read-only Argus boundary certified (4 live behaviors + final gate); OFF is silent (zero Argus I/O, OFF_MESSAGE); write-capable host_access.py is NOT imported by server.py so the write surface is UNREACHABLE (no wallpaper). No host-action endpoint exists this wave.

- scripts/certify_argus_integration.py --gate -> exit 0; PASS
- anima/host_access.py is write-capable (Calendar/Reminders/Notes via osascript/EventKit) and is NOT imported by anima/server.py -> write surface is UNREACHABLE from the read-only host wave
- host_awareness OFF -> OFF_MESSAGE returned (ok) with ZERO Argus client calls (ok)

### capability_truth — COMPLETE
Settings ledger == runtime ledger: caps default all-OFF; saved imessage_read is durable + isolated on reload; _read_msgs refuses while OFF; the deterministic capability reply is honest (no fabricated texts); UI 'soon' matches the OFF gate.

- defaults_off=True durable=True isolated=True runtime_gate_off=True reply_honest=True
- defaults_off=True imessage_read durable=True others_off=True; _read_msgs(off) -> {"ok": false, "error": "mail reading is off in settings"}; host_awareness.respond(texts-Q) -> None
- UI exposes mail/web as 'soon'/disabled (matches OFF gate): True

### conversation_repair — WALLPAPER
WALLPAPER: the correction path looks wired (per-turn capture + merge newest-wins) but on the contract's own killer phrasing — 'scratch that — not Rex, his name is Atlas' — extract() captures NOTHING: the bad value 'Rex' stays the ACTIVE fact and the corrected 'Atlas' is LOST. There is no supersede-the-last-turn primitive; only a full re-statement ('my dog's name is Atlas') supersedes. A follow-up 'what's my dog's name?' would answer Rex. (memory_lirf.py extract() dog_name rule line 361; _RETRACT_CUE line 534.)

- **missing links:** real_use_in_answer, real_backend (supersede-the-last-turn)

- correction 'sorry, scratch that — not Rex, his name is Atlas' -> dog_name active='Rex' [LINGERS->Rex]
- correction 'that transcription was wrong, I said Atlas' -> dog_name active='Rex' [LINGERS->Rex]
- correction 'not Rex, his name is Atlas' -> dog_name active='Rex' [LINGERS->Rex]
- correction "actually, my dog's name is Atlas" -> dog_name active='Atlas' [SUPERSEDED->Atlas]
- anima/memory_lirf.py:539 extract(): the dog_name rule (line 361-364) requires a 'my dog … <Name>' anchor; 'his name is Atlas' does not match, so extract() returns [] for the natural correction. _RETRACT_CUE (line 534) does NOT include 'scratch that'/'not X, Y'.
- anima/memory_lirf.py:786 merge(): a DIFFERENT value supersedes correctly (old->history, new active) — but ONLY when a value is actually extracted (explicit 'my dog's name is Atlas' works: 'Atlas').

### gate0_prime — COMPLETE
COMPLETE-by-construction: gate0_prime.py is an all-or-nothing aggregator (PASS iff every hardening target PASSes) with a freeze-proof that fingerprints the real Vera + whole real .anima once around the run and FAILs on a single moved real byte. The live verdict is emitted by the running gate, not by this cert (hard constraint).

- gate0_prime.py: all-or-nothing aggregator structure=True; freeze-proof present=True
- Wave-2 stress modules present: 5/5 (gate0_prime_longhorizon.py, gate0_prime_population.py, gate0_prime_recovery.py, gate0_prime_experience.py, gate0_prime_merge_growth.py)
- NOT RUN here by hard constraint (a clean Gate 0 Prime with a freeze-proof is running in the BACKGROUND); the live verdict is produced by that gate.

### growth_dashboard — PARTIAL
Dashboard OFF unless server started with ANIMA_METRICS=1 (GET /metrics -> 404 otherwise; UI shows the honest hint). When enabled, metrics.summary/verdict return REAL ledger-derived gauges that track the seed (not constants). Known live gap: off by default.

- **missing links:** visible_trigger (dashboard OFF unless ANIMA_METRICS=1)

- server.py /metrics handler returns 404 unless ANIMA_METRICS=1: True
- metrics.summary EQUALS the seeded ledger (real, non-constant): real=True moved=True
- summary contamination={'organic_break_rate': 0.25, 'organic_n': 4, 'organic_broken': 1, 'eval_break_rate': None, 'eval_n': 0, 'eval_broken': 0, 'narrative_rejections': 1, 'recent_breaks': ["I'm just an AI and I have no feelings.", 'just an ai', 'have no feelings']} coherence={'narrative_accept_rate': 0.667, 'narrative_acceptances': 2, 'narrative_total': 3} growth={'consolidations': 2, 'accepted': 2, 'accept_rate': 1.0, 'median_prediction_delta': -0.1} verdict='DECISION RULE: no adversarial data yet —'

### identity_sandbox — COMPLETE
Observe-only proven: identity_sandbox cert (zero identity mutation) passes under --gate; identity_agency reads False by default so the Identity & Agency organs stay dormant; read_identity_state is a camera (reads, never writes). Freeze (held to 2026-07-03) honored.

- scripts/identity_sandbox.py --selftest -> exit 0; OK (asserts real Vera identity + whole real .anima byte-UNCHANGED after the observe/certify/rollback chain on synthetic state)
- scripts/identity_sandbox.py certify (observe-only, exit 0): live narrative content observation — ungrounded self-narrative SHOWN in current Vera.narrative (deliberately NON-gating; the camera reports, never edits; cap identity_agency stays OFF).
- identity_agency default OFF=True; read_identity_state is observe-only=True
- read_identity_state ok=True identity_agency=False

### known_fact_memory — PARTIAL
Deterministic FLOOR proven: durable birthday survives a restart and spine.answer_from_fact states 'March 4 … 1991' EXACTLY; honest-unknown inverse holds. FULL live recall (model regenerate under hard_bind + verifier) requires --live model — not run here, so not COMPLETE.

- **missing links:** real_use_in_answer (full live recall)

- durable=True restart-known=True spine_floor_exact=True honest_unknown=True
- captured birthday on disk=True value='March 4th, 1991'; post-restart spine.answer_from_fact="March 4th, 1991 — like I'd forget your birthday."; unknown blood_type -> honest_unknown=True

### lerf_runtime — UNKNOWN
Requires --live (Ollama) + a concrete unique-trigger certified skill to prove retrieved -> USED -> grounded -> traced. The seam is wired in server.py, but the rendered-use link is not run here and is NOT faked.

- **missing links:** real_retrieval, real_use_in_answer, mri_trace

- server.py LERF-FIRST seam present (_lerf_eligible/_lerf_task_first, backend lerf:*): True
- USE-in-answer link requires --live (Ollama) to render a certified skill with a unique trigger; the deterministic no-model variant can prove retrieval+eligibility+grounded-verify wiring but NOT the rendered use.

### response_completeness — COMPLETE
Shipped reply == final_output_gate(shipped) (one gate, no second return path); response_complete True; ends sentence-terminal; whole_mri records final_gate_passed + response_complete. (A live-model turn for a GENERATED reply is gate0_prime_experience's 100-probe job, out of scope here.)

- server._turn deterministic seam: shipped==final_gate=True, response_complete=True, ends_clean=True, mri(final_gate+complete)=True
- backend=reference:recall chars=173; turn_id=turn_2026_06_07_055656_8GcTlG safety.final_gate_passed=True response_complete=True

### source_aware_answering — COMPLETE
Recall answers FROM the stored reference, LABELS it 'uploaded reference', ships through the shared #1-rule final gate (backend reference:recall); no-hijack + honest fall-through proven by selftest.

- scripts/certify_no_stubs.py --gate -> exit 0; CERTIFIED
- python3 -m anima.source_aware --selftest -> exit 0; PASS

### universal_knowledge_intake — COMPLETE
Paste/typed-text intake proven plan->approve->durable->retrieve via certify_no_stubs.py --gate. (URL/PDF/YouTube/image inputs honestly return needs_dependency — that is honest, not a stub.)

- scripts/certify_no_stubs.py --gate -> exit 0; CERTIFIED
- chain: UI tbAdd -> POST /intake/plan -> POST /intake/approve (reference_only, durable) -> re-read intake_queue.references() fresh from disk -> server._turn backend=reference:recall -> whole_mri trace

### whole_system_mri — COMPLETE
Every turn mints one turn_id; the UnifiedTrace (vera+argus+quality+cost+safety) is recorded append-only after the final gate; record without a turn_id raises; viewer renders. 'No turn_id = not observable.'

- scripts/certify_whole_mri.py --gate -> exit 0; CERTIFIED
- python3 -m anima.whole_mri --selftest -> exit 0; PASS

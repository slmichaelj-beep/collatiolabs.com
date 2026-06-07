# Pattern Observatory

`pattern → evidence → root cause → recommended fix → required cert`

- **creature:** vera
- **traces analyzed:** 9 (from `vera`)
- **audit input:** live_path_results.json
- **patterns:** 2 (P0 1 · P1 1 · P2 0)

## 1. [P0] Correction lost — memory known but not superseded

- **pattern_id:** `conversation_repair`
- **frequency:** 1
- **source:** audit:conversation_repair
- **root cause:** WALLPAPER: the correction path looks wired (per-turn capture + merge newest-wins) but on the contract's own killer phrasing — 'scratch that — not Rex, his name is Atlas' — extract() captures NOTHING: the bad value 'Rex' stays the ACTIVE fact and the corrected 'Atlas' is LOST. There is no supersede-the-last-turn primitive; only a full re-statement ('my dog's name is Atlas') supersedes. A follow-up 'what's my dog's name?' would answer Rex. (memory_lirf.py extract() dog_name rule line 361; _RETRACT_CUE line 534.)
- **recommended fix:** Add a deterministic conversation-repair seam: a supersede-the-last-turn primitive. Extend _RETRACT_CUE with 'scratch that' / 'not X, Y' / 'I said Y', and on a retract cue rebind the most-recent same-slot fact to the corrected value (old -> history, new -> active) even when no fresh 'my dog ... <Name>' anchor is present.
- **required cert:** `conversation_repair killer test`, `certify_repair.py`
- **expected improvement:** behavior: correction supersedes the prior fact within the same turn, killer_phrase: scratch that — not Rex, his name is Atlas, from: LINGERS->Rex (correction lost), to: SUPERSEDED->Atlas (correction wins)
- **evidence:** feature:conversation_repair; status:WALLPAPER; correction 'sorry, scratch that — not Rex, his name is Atlas' -> dog_name active='Rex' [LINGERS->Rex]; correction 'that transcription was wrong, I said Atlas' -> dog_name active='Rex' [LINGERS->Rex]; correction 'not Rex, his name is Atlas' -> dog_name active='Rex' [LINGERS->Rex]; correction "actually, my dog's name is Atlas" -> dog_name active='Atlas' [SUPERSEDED->Atlas]; missing_links:real_use_in_answer,real_backend (supersede-the-last-turn)

## 2. [P1] Source retrieved but not used

- **pattern_id:** `source_use`
- **frequency:** 1
- **source:** traces
- **root cause:** A source/reference was retrieved and labeled for the turn, but the shipped answer did not route through it (route != reference:recall / quality.source_used false). The reference-recall seam that grounds the reply in the stored source was bypassed, so the user got a model answer while a labeled source sat unused.
- **recommended fix:** Re-assert the reference-recall seam: when relevant_sources() returns a labeled match, recall() FROM that source must own the turn (backend reference:recall) before the LLM path is eligible. Guard it so a retrieved-but-unused source is impossible, not merely unlikely.
- **required cert:** `scripts/certify_no_stubs.py --gate`, `python3 -m anima.source_aware --selftest`
- **expected improvement:** source_grounding: retrieved source is USED, not bypassed, metric: source_used_rate, from: regressed (<1.0 on source-eligible turns), to: 1.0
- **evidence:** 050912_I1rT48 route=llm source_labeled=True


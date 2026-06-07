# Feature Inventory — Program Reality Audit (Phase 1 foundation)

> **Law:** No feature is complete because code/UI/endpoint/trace exists — only when the live user path is proven end-to-end.

**81 features** claimed across surfaces. Every status is `UNTESTED` — the live-path cert fills these in later (this layer only enumerates the CLAIMS).

## Claims by surface (distinct features / raw claim hits)

| surface | features | raw claims |
|---|---:|---:|
| ui | 20 | 37 |
| endpoint | 23 | 51 |
| cap | 7 | 10 |
| cert | 7 | 14 |
| docstring | 66 | 79 |

## Features

| feature | claimed_by | user-visible | durable | claim |
|---|---|:--:|:--:|---|
| `accel_mlx` | docstring | no | ? | MLX acceleration for Apple Silicon (M-series Mac). |
| `affective_core` | endpoint | no | yes | Report the heart's current feeling vector |
| `app_shell` | endpoint | yes | no | Serve the app shell (public; holds no secrets) |
| `applemac` | docstring | no | ? | applemac — Messages and Mail through AppleScript (osascript), Mac-only. |
| `argus_host_awareness` | cap, cert, docstring, endpoint, ui | yes | no | host_awareness — Vera's OPT-IN awareness of host + outbound-network state, via Argus. |
| `brain_select` | docstring, endpoint, ui | yes | yes | cloud — optional cloud brains (opt-in). The default mouth stays LOCAL and private. |
| `bridge` | docstring | no | ? | bridge — translate the heart's continuous Self into something the mouth speaks FROM. |
| `call_loop` | docstring | no | ? | call_loop — milestone 2: the live voice conversation loop for Vera's call. |
| `call_server` | docstring | no | ? | call_server — the Mac side of Vera's voice call. |
| `capability_truth` | docstring, endpoint, ui | yes | yes | caps — explicit, default-OFF capability toggles for Vera's outward-facing powers. |
| `care` | docstring | no | ? | care — wellbeing guardrails for a companion that people may lean on. |
| `code_context` | ui | yes | ? | UI: code-context toolbar button |
| `constitution` | docstring | no | ? | constitution — the laws the creature is built to obey, as enforced code. |
| `context_gather` | docstring | no | ? | context_gather — local, key-free fact gathering for a proactive briefing. |
| `conversation_repair` | docstring | no | ? | loops — THE DREAM ENGINE: the open loops a person leaves open, tracked FOREVER. |
| `crypto` | docstring | no | ? | crypto — optional at-rest encryption for the creature's private files. |
| `curiosity_engine` | cap, docstring | yes | yes | curiosity — THE CURIOSITY ENGINE: the enforcement of ANIMA LAW 002. |
| `demo` | docstring | no | ? | demo — accelerated, reproducible proof that the heart exists continuously. |
| `deploy_fingerprint` | endpoint | no | no | LAW 005: report the commit THIS process is running (git == running) |
| `endpoint_auth` | endpoint | no | ? | HTTP endpoint /auth/ |
| `eval` | docstring | no | ? | eval — a capability battery for the companion. Turns "does she feel better?" into |
| `event_bus` | docstring | no | ? | event_bus — the moonshot's spine. Organs don't call each other; they REACT to events. |
| `export_menu` | ui | yes | ? | UI: Copy/Export menu toggle |
| `face_id_unlock` | docstring, endpoint, ui | yes | yes | passkey — Face ID / Touch ID unlock via WebAuthn, a second layer on top of the token. |
| `fmlgs` | docstring | no | ? | fmlgs — Fast Multilevel Language-embedded Gaussians. |
| `forge` | docstring | no | ? | The Character Forge — turn a corpus that embodies a voice into a LoRA adapter that |
| `gate0_prime` | cert | no | ? | Cert (Gate 0 tests 5+6): guards & reality |
| `growth_dashboard` | docstring, endpoint, ui | yes | no | The slow-learning organ — how an anima actually becomes someone's. |
| `heart` | docstring | no | ? | The Heart — the continuous-time affective core of an anima. |
| `host_access_write` | docstring | no | ? | host_access — Vera reads AND writes the host Mac's Calendar, Reminders, and Notes. |
| `identity` | docstring | no | ? | The portable identity layer — the part of "who she is" that must outlive any single |
| `identity_sandbox` | cap, cert, docstring, ui | yes | yes | identity_sandbox — a CAMERA pointed at Vera's identity layer, never a hand that edits it. |
| `knowledge_library` | endpoint, ui | yes | yes | List normalized knowledge-library items (section-filtered) |
| `known_fact_memory` | docstring | no | yes | memory_lirf — the LIRF (Ledger of Indexed, Resolved Facts) memory engine. |
| `labeled_search` | docstring, endpoint, ui | yes | yes | intake_search — Labeled cross-store search over Vera's knowledge stores. |
| `lerf_runtime` | cap, cert, docstring | yes | yes | lerf — the LERF (Ledger of Externalized, Retrievable, Falsifiable cognition) engine. |
| `live` | docstring | no | ? | live — a small real-time CLI for keeping an anima alive. |
| `live_turn` | endpoint | yes | no | One live conversational turn (text in, reply out) |
| `llamacpp` | docstring | no | ? | The llama.cpp brain — the V2 "mouth" that can be steered by control vectors. |
| `local_model_manager` | docstring, endpoint, ui | yes | yes | models — the local-model manager: a curated, fit-checked list you can pick from and |
| `meaning` | docstring | no | ? | meaning — THE MEANING ENGINE: the enforcement of ANIMA LAW 003. |
| `meaning_conservation` | docstring | no | ? | meaning_conservation — THE MEANING-CONSERVATION ENGINE (directive #4). |
| `memory` | docstring | no | ? | Memory — the lived experience an anima grows from. |
| `memory_schema` | docstring | no | ? | memory_schema — the single, canonical memory object EVERY subsystem uses. |
| `messaging_read` | cap, endpoint, ui | yes | no | Read recent iMessages (gated on capability) |
| `messaging_send` | cap, endpoint, ui | yes | no | Create a pending iMessage draft (sends nothing) |
| `mri_trace` | docstring, ui | yes | yes | telemetry — the substrate's passive flight recorder. |
| `narrative` | docstring | no | ? | narrative — the creature's evolving sense of her OWN story. |
| `nightly` | docstring | no | ? | nightly — let the creature sleep on its own, every night, on your Mac. |
| `opportunity` | docstring | no | ? | opportunity — THE OPPORTUNITY ENGINE: "what would HELP?", as a gentle, optional OFFER. |
| `persona_editor` | endpoint | yes | yes | Get/save the creature's persona text |
| `personal` | docstring | no | ? | personal — PERSONAL INTELLIGENCE ("Learn Lamar"): the moat. |
| `personality_dials` | docstring, endpoint, ui | yes | yes | Personality dials — the stable CONTRACT for who she is, decoupled from how it's |
| `portable_self` | endpoint, ui | yes | yes | Export the whole mind/identity as a portable file |
| `portrait` | docstring | no | ? | portrait — lasting memory: a living, legible profile of the person. |
| `proactive_outreach` | docstring, endpoint | no | yes | proactive — Vera reaching out first, in HER voice (not a detached prompt). |
| `probe` | docstring | no | ? | probe — experiments that map what an anima can and cannot do. |
| `reality` | docstring | no | ? | reality — THE EPISTEMIC LOOP: Memory + Experience = Knowledge (REASONING, not scorekeeping). |
| `reliability` | docstring | no | ? | reliability — the life-insurance layer for an anima. |
| `reproduce` | docstring | no | ? | Reproduction — heredity for animae. |
| `response_completeness` | cert, docstring | no | no | The Mouth — a swappable organ for speaking from the creature's felt-state. |
| `review` | docstring | no | ? | review — THE LIFE REVIEW ENGINE: the nightly cortex that turns a life into |
| `senses` | docstring | no | ? | The Senses — organs that turn raw life into a perception the heart can feel. |
| `server` | docstring | no | ? | server — the home host. Run it on your Mac; open it on your phone. |
| `simulation` | docstring | no | ? | simulation — COGNITIVE SIMULATION: Understanding -> Theory -> Simulation, run on a TWIN. |
| `source_aware_answering` | docstring, ui | yes | yes | source_aware — reference attribution for the live turn (Intake Wave 3, Q, safe layer). |
| `sources` | docstring | no | ? | sources — LEARNING SOURCES for autonomous growth. LERF Phase 6b: the ingestion machinery that |
| `sysinfo` | docstring | no | ? | sysinfo — read the Mac's resources and estimate whether a local model will fit. |
| `trajectory` | docstring | no | ? | trajectory — THE TRAJECTORY ENGINE: where is this HEADING? |
| `tune` | docstring | no | ? | tune — find the training recipe that makes a bigger brain actually pay off. |
| `twin` | docstring | no | ? | twin — the DIGITAL TWIN: a complete, hermetic simulation environment for the mind. |
| `universal_knowledge_intake` | cert, docstring, endpoint, ui | yes | yes | intake — Universal Knowledge Intake, the PIPELINE SPINE (Wave 1). |
| `util` | docstring | no | ? | Small shared helpers: process labelling and atomic, optionally-encrypted I/O. |
| `values_editor` | endpoint | yes | yes | Get/save the creature's values toggles |
| `verifier` | docstring | no | ? | verifier — a small, separate model whose ONLY job is to judge a request's premise. |
| `voice_io` | endpoint, ui | yes | no | Serve the last synthesized reply WAV |
| `voip_push` | docstring | no | ? | voip_push — the Mac side that *rings the phone*. |
| `web_fetch` | cap, docstring, endpoint, ui | yes | no | webget — read-only web fetch, hard-restricted to an explicit allow-list of domains. |
| `whole_system_mri` | cert, docstring | no | yes | host_window — Phase 2 of the Whole-System MRI. |
| `world_model` | docstring | no | ? | world_model — FROM FACTS TO CAUSAL MODELS: the leap from a graph to a THEORY of it. |
| `world_state` | docstring | no | ? | world_state — THE PERSONAL WORLD STATE: facts become connected SITUATIONS. |

## Owner modules

- **`accel_mlx`** — `anima/accel_mlx.py`
- **`affective_core`** — `anima/server.py`
- **`app_shell`** — `anima/server.py`
- **`applemac`** — `anima/applemac.py`
- **`argus_host_awareness`** — `anima/caps.py`, `anima/host_awareness.py`, `anima/server.py`, `anima/web/index.html`, `scripts/certify_argus_integration.py`
- **`brain_select`** — `anima/cloud.py`, `anima/server.py`, `anima/web/index.html`
- **`bridge`** — `anima/bridge.py`
- **`call_loop`** — `anima/call_loop.py`
- **`call_server`** — `anima/call_server.py`
- **`capability_truth`** — `anima/caps.py`, `anima/rail.py`, `anima/route.py`, `anima/server.py`, `anima/web/index.html`
- **`care`** — `anima/care.py`
- **`code_context`** — `anima/web/index.html`
- **`constitution`** — `anima/constitution.py`
- **`context_gather`** — `anima/context_gather.py`
- **`conversation_repair`** — `anima/loops.py`
- **`crypto`** — `anima/crypto.py`
- **`curiosity_engine`** — `anima/caps.py`, `anima/curiosity.py`
- **`demo`** — `anima/demo.py`
- **`deploy_fingerprint`** — `anima/server.py`
- **`endpoint_auth`** — `anima/server.py`
- **`eval`** — `anima/eval.py`
- **`event_bus`** — `anima/event_bus.py`
- **`export_menu`** — `anima/web/index.html`
- **`face_id_unlock`** — `anima/passkey.py`, `anima/server.py`, `anima/web/index.html`
- **`fmlgs`** — `anima/fmlgs.py`
- **`forge`** — `anima/forge.py`
- **`gate0_prime`** — `scripts/gate0_guards.py`, `scripts/gate0_prime.py`, `scripts/gate0_prime_longhorizon.py`, `scripts/gate0_prime_merge_growth.py`, `scripts/gate0_prime_population.py`, `scripts/gate0_prime_recovery.py`, `scripts/gate0_resource.py`
- **`growth_dashboard`** — `anima/growth.py`, `anima/metrics.py`, `anima/server.py`, `anima/web/index.html`
- **`heart`** — `anima/heart.py`
- **`host_access_write`** — `anima/host_access.py`
- **`identity`** — `anima/identity.py`
- **`identity_sandbox`** — `anima/caps.py`, `anima/identity_sandbox.py`, `anima/self_narrative.py`, `anima/web/index.html`, `scripts/gate0_twin.py`
- **`knowledge_library`** — `anima/server.py`, `anima/web/index.html`
- **`known_fact_memory`** — `anima/memory_lirf.py`, `anima/spine.py`
- **`labeled_search`** — `anima/intake_search.py`, `anima/server.py`, `anima/web/index.html`
- **`lerf_runtime`** — `anima/caps.py`, `anima/lerf.py`, `anima/lerf_distill.py`, `anima/lerf_grow.py`, `anima/lerf_router.py`, `scripts/gate0_growth.py`
- **`live`** — `anima/live.py`
- **`live_turn`** — `anima/server.py`
- **`llamacpp`** — `anima/llamacpp.py`
- **`local_model_manager`** — `anima/models.py`, `anima/server.py`, `anima/web/index.html`
- **`meaning`** — `anima/meaning.py`
- **`meaning_conservation`** — `anima/meaning_conservation.py`
- **`memory`** — `anima/memory.py`
- **`memory_schema`** — `anima/memory_schema.py`
- **`messaging_read`** — `anima/caps.py`, `anima/server.py`, `anima/web/index.html`
- **`messaging_send`** — `anima/caps.py`, `anima/server.py`, `anima/web/index.html`
- **`mri_trace`** — `anima/telemetry.py`, `anima/web/index.html`
- **`narrative`** — `anima/narrative.py`
- **`nightly`** — `anima/nightly.py`
- **`opportunity`** — `anima/opportunity.py`
- **`persona_editor`** — `anima/server.py`
- **`personal`** — `anima/personal.py`
- **`personality_dials`** — `anima/dials.py`, `anima/server.py`, `anima/web/index.html`
- **`portable_self`** — `anima/server.py`, `anima/web/index.html`
- **`portrait`** — `anima/portrait.py`
- **`proactive_outreach`** — `anima/proactive.py`, `anima/reminders.py`, `anima/server.py`
- **`probe`** — `anima/probe.py`
- **`reality`** — `anima/reality.py`
- **`reliability`** — `anima/reliability.py`
- **`reproduce`** — `anima/reproduce.py`
- **`response_completeness`** — `anima/mouth.py`, `scripts/gate0_experience.py`, `scripts/gate0_prime_experience.py`
- **`review`** — `anima/review.py`
- **`senses`** — `anima/senses.py`
- **`server`** — `anima/server.py`
- **`simulation`** — `anima/simulation.py`
- **`source_aware_answering`** — `anima/source_aware.py`, `anima/web/index.html`
- **`sources`** — `anima/sources.py`
- **`sysinfo`** — `anima/sysinfo.py`
- **`trajectory`** — `anima/trajectory.py`
- **`tune`** — `anima/tune.py`
- **`twin`** — `anima/twin.py`
- **`universal_knowledge_intake`** — `anima/intake.py`, `anima/intake_parsers.py`, `anima/intake_queue.py`, `anima/server.py`, `anima/web/index.html`, `scripts/certify_no_stubs.py`
- **`util`** — `anima/util.py`
- **`values_editor`** — `anima/server.py`
- **`verifier`** — `anima/verifier.py`
- **`voice_io`** — `anima/server.py`, `anima/web/index.html`
- **`voip_push`** — `anima/voip_push.py`
- **`web_fetch`** — `anima/caps.py`, `anima/server.py`, `anima/web/index.html`, `anima/webget.py`
- **`whole_system_mri`** — `anima/host_window.py`, `anima/whole_mri.py`, `anima/whole_mri_shape.py`, `scripts/certify_whole_mri.py`
- **`world_model`** — `anima/world_model.py`
- **`world_state`** — `anima/world_state.py`

# Vera Weakness Register

Review pass: 2026-06-22
Repo: `/Users/lamar/Developer/collatiolabs.com`
Branch: `anima`
Commit observed: rolling review through `cd0f143`

This register is intentionally harsher than the certification ledger. The certs prove the designed happy paths are real. This file tracks places where Vera could fail under product pressure, hostile conditions, privacy expectations, local/cloud ambiguity, or scale.

Status tags:
- `CONFIRMED`: verified by code inspection or executed cert output.
- `LIKELY`: strong evidence, but needs a targeted adversarial cert or deeper trace.
- `NEEDS ADVERSARIAL CERT`: the weakness may be latent; write a breaking test before final severity.
- `FRONTIER IMPROVEMENT`: not a bug by itself, but necessary if Vera is going to become the next personal AI frontier.

Severity:
- `P0`: blocks safe product use now.
- `P1`: must fix before trusted private companion / LAN / cloud fallback usage.
- `P2`: important safety, privacy, governance, or product trust weakness.
- `P3`: maintainability, clarity, polish, or longer-term hardening.

## Executive Weakness Map

Top weaknesses:
1. `P1 CLOSED; CERTIFIED` LAN expose can run with no auth if `--expose` is used and `ANIMA_TOKEN` is absent.
2. `P1 CLOSED; CERTIFIED` per-turn local/cloud routing is computed, but generation can still follow the global cloud brain selection.
3. `P1 PARTIALLY CLOSED; CERTIFIED` at-rest encryption now consistently covers private ledgers/queues, intake staging, export/training packages, and off-device backup bundles when a vault key is active; product/private mode refuses plaintext startup; remaining product work is first-run key setup, recovery-code/hardware-key, and rotation UX.
4. `P1/P2 CLOSED; CERTIFIED FOR SUPPORTED SHELLS` unsafe cross-origin POST, POST query-token authorization, localStorage auth secrets, non-revocable browser cookies, static pairing replay, missing main-shell first-launch pairing, missing startup one-time code generation, missing additional-shell pairing, missing session inventory, missing rotation, missing logout-all, and desktop/LAN/tunnel replay gaps are blocked. Custom-scheme installed wrappers remain a packaging constraint.
5. `P2 CLOSED; CERTIFIED` passkey/WebAuthn now stores credential public keys and verifies assertion signatures, flags, origin/RP-ID, challenge, and sign counters.
6. `P2 CONFIRMED` approvals are not bound tightly enough to the action they authorize.
7. `P2 CONFIRMED` budget and marketplace ledgers have direct-call and overspend edge cases.
8. `P2 CONFIRMED` broad exception use is massive and not yet classified into fail-open vs fail-closed zones.
9. `P2 CLOSED; CERTIFIED` older cert fixtures could dirty real `.anima` during live-path verification; the legacy cert family now runs under hermetic store redirection and `certify_cert_fixture_hermeticity` fails on fixture-store mutation.
10. `P2 FRONTIER IMPROVEMENT` self-learning machinery exists, but the user experience does not yet make Vera feel like she can safely notice, learn, build, certify, and explain new skills.
11. `P2 FRONTIER IMPROVEMENT` revenue/business subsystems are too visible for a higher-level companion product unless they become optional domain packs.

Adversarial probes run on 2026-06-21 confirmed live behavior for:
- Approval mismatch authorizing the wrong action.
- Fake approval strings satisfying high/core self-evolution promotion.
- Cumulative category and monthly budget caps not being enforced.
- Truth/observation ledgers writing raw sensitive text with `ANIMA_KEY` set.
- Upwork Connects overspend and loose funnel transitions.

## Security And Privacy

### W01 - LAN expose can be unauthenticated

Severity: `P1`
Status: `CLOSED; CERTIFIED`

Original evidence:
- `anima/server.py:2766-2770` treats an empty token as authenticated.
- `anima/server.py:3764-3767` exposes host/port controls.
- `anima/server.py:3846-3847` prints an exposed-on-LAN warning when no password exists, but still permits startup.
- Live server startup printed: `security: auth OFF (no token) · files plaintext`.

Probe result:
- With `ANIMA_TOKEN` removed, `python3 -m anima.server --port 8766 --expose` started and accepted a local TCP connection.
- The probe process was terminated and port 8766 was verified no longer listening.

Risk:
For a private companion, accidental LAN exposure is a hard trust break. Even if the warning is honest, users will eventually run the wrong command, tunnel the wrong port, or copy a launch script.

Fix direction:
- Refuse `--expose` unless at least one strong auth mechanism is active.
- Require `ANIMA_TOKEN`, passkey pairing, or an explicit `--i-understand-unsafe-lan-no-auth` style development flag.
- Add a cert that attempts `--expose` with no token and expects startup refusal.

Closure update:
- Implemented on repo branch `anima` after this finding: non-loopback server binds now require `ANIMA_TOKEN`.
- Added `scripts/certify_expose_requires_auth.py`.
- Added the cert to `scripts/run_master_cert_stack.py`.
- Closure certified on commit `fa64f1a`: deploy proof GREEN, master stack `76/76 GREEN`, Diamond v2 repeatability CONFIRMED.

### W02 - Per-turn local/cloud router does not enforce generation backend

Severity: `P1`
Status: `CLOSED; CERTIFIED`

Evidence:
- `anima/organs/router.py` computes `RouteDecision`.
- `anima/server.py:585-594` records the decision and hides fact blocks under cloud routing.
- `anima/server.py:956-959` still calls `mouth.respond(...)`.
- `anima/mouth.py:897-905` globally selects a cloud brain if configured and available.

Risk:
The UI can say or imply that a given turn is local/private while the generation path can still use the globally configured cloud brain. That undermines the core privacy promise.

Fix direction:
- Make `RouteDecision.model` the single source of truth for backend selection.
- Pass route intent into `Mouth.respond()`/`Mouth.assemble()`.
- Cert: create a fake cloud brain, force a local-only route, and assert no cloud call occurs.
- Add a per-turn privacy receipt: `local model`, `cloud model`, `facts withheld`, `egress none/scrubbed`.

Closure update:
- Implemented after this finding: `Mouth` now carries a dedicated `local_brain` beside its default brain and selects the allowed backend with `brain_for_route(RouteDecision.model)`.
- `server._turn` now passes `_route_model` into the first generated draft and verifier retry drafts.
- LERF task rendering now forces `mouth.brain_for_route("local")` before rendering a certified skill.
- Per-turn memory blanking now follows the selected backend, not merely whether a cloud provider is configured.
- Added `scripts/certify_route_backend_enforcement.py`.
- Added the cert to `scripts/run_master_cert_stack.py`.
- Closure certified on commit `9e4604d`: deploy proof GREEN, master stack `77/77 GREEN`, Diamond v2 repeatability CONFIRMED (`108 COMPLETE / 1 HONEST PARTIAL`, 0 product reds, 0 unclassified flakes).
- Remote verified: `origin/anima` points to `9e4604d20c99a9b986fa2b4e5bfa03dbc86139fd`.
- Later closure update: `server._turn` now emits a per-turn `privacy_receipt` and appends the same route/backend/egress facts to the encrypted-store-compatible receipt ledger; certified by `scripts/certify_privacy_receipts.py`.

### W03 - Encryption is optional and not consistently applied

Severity: `P1`
Status: `PARTIALLY CLOSED; CERTIFIED`

Evidence:
- `anima/crypto.py` implements optional Fernet encryption when `ANIMA_KEY` or keychain material exists.
- `anima/util.py:54-82` has crypto-aware `save_json`, `save_text`, and load helpers.
- Original adversarial probe found Truth Ledger and Observation Store writing raw sensitive JSONL under `ANIMA_KEY`.
- Static direct-write sweep found additional production direct writes in company storage, telemetry, consent, curiosity, whole MRI, verification, and other store modules.

Risk:
The project has the ingredients for private encrypted memory, but users will reasonably assume “private local companion” means sensitive ledgers are encrypted at rest. Today many durable memory/truth/observation files can remain plaintext.

Probe result:
- Historical: with `ANIMA_KEY=temporary-review-key`, a synthetic secret written through `truth.ledger.emit()` was visible in the raw `.truth.jsonl`.
- Historical: with the same key, a synthetic secret written through `observation.store.append()` was visible in the raw `.observation.jsonl`.

Fix direction:
- Introduce one storage substrate for JSON, text, and append-only JSONL.
- Add `append_jsonl_encrypted()` and `load_jsonl_encrypted()` helpers.
- Define public vs private store classes explicitly.
- Cert: set `ANIMA_KEY`, perform a representative turn, then assert private `.anima` files do not contain raw user text.

Closure update:
- `anima/secure_store.py` is now the shared private persistence substrate for JSON, text, and append-only JSONL.
- Truth Ledger and Observation Store now append through `secure_store.append_jsonl()` and read through `secure_store.read_jsonl_lines()`.
- This slice migrated the named high-risk private/governance cluster to `secure_store`: `anima/company/storage.py`, `anima/consent/policy.py`, `anima/curiosity.py`, `anima/telemetry.py`, and `anima/whole_mri.py`.
- Expanded `scripts/certify_secure_store_no_plaintext.py` to write synthetic secrets through Truth, Observation, Company, Consent, Curiosity, Telemetry, Telemetry MRI, and Whole-System MRI paths under `ANIMA_KEY`, inspect raw disk bytes, and prove the secrets are not present while normal load paths recover them.
- Focused certification passed: `certify_secure_store_no_plaintext`, company canon, decision ledger, company state trackers, consent boundaries, curiosity invariants, telemetry selftest, and whole-MRI selftest.

Second closure update:
- Added byte sealing helpers to `anima/secure_store.py` for private binary blobs that can be read through Vera's own loaders.
- Migrated additional private/governance/cognition persistence to `secure_store`: agency approval and intent ledgers, incident/SOC and lockdown state, teaching and auto-learn queues, knowledge-pack registry/chunks, rollback ledgers, metrics, continuity loss ledger, meaning, reality, loops, opportunity, trajectory, theory observations, Life Review, intake MRI/job/tier ledgers, cold intake blobs, LERF route ledger, founder-console decisions, identity sandbox shadow ledgers/restores, and twin manifests/snapshot ledgers/identity-seed artifacts.
- Added `scripts/certify_private_write_classification.py` and wired it into `scripts/run_master_cert_stack.py`. It statically scans `anima/` and fails on any unclassified direct writer.
- Static classification cert currently verifies 43 direct write sites: crypto substrate, crypto-aware legacy chat archive, temp audio, installer config, public reports, backup/restore temp files, isolation fallbacks, and synthetic fixtures are classified.
- Known pending privacy surfaces are explicitly named, not hidden: raw intake staging in `anima/server.py::_write_staging` needs transparent encrypted parser handoff; plaintext user-chosen export/training bundles in `anima/identity.py`, `anima/portable.py`, `anima/platform.py`, and `anima/forge.py` need encrypted export options.

Third closure update:
- Raw intake staging is no longer a durable plaintext surface. `anima/server.py::_write_staging` now stores staged text, URL, and uploaded-file bytes through `secure_store.save_bytes()`.
- Parsers receive a short-lived decrypted temp materialization via `_materialized_staging()`; the temp file is deleted immediately after the parser handoff, while Intake MRI/provenance keeps the durable staging reference instead of exposing the temp path.
- Added `scripts/certify_intake_staging_encryption.py` and wired it into `scripts/run_master_cert_stack.py`.
- Focused certification passed: `certify_intake_staging_encryption`, `certify_private_write_classification`, `scripts/test_intake_endpoints.py`, `certify_intake_trace_viewer`, and `python3 -m anima.intake --selftest`.
- Static classification now verifies 40 direct write sites. The only known pending privacy surfaces are plaintext export/training bundles in `anima/forge.py`, `anima/portable.py`, and `anima/platform.py`.

Fourth closure update:
- Added encrypted-by-default export helpers in `anima/secure_store.py`; plaintext export now requires an explicit `allow_plaintext=True` escape hatch.
- Portable mind, full-mind platform bundles, identity bundles, and Forge LoRA training datasets now use sealed export writes by default.
- Forge training datasets get a short-lived plaintext materialization only for the trainer handoff via `anima.forge.materialized_dataset()`.
- Explicit plaintext escape hatches and trainer materializations are written with owner-only file permissions.
- Added `scripts/certify_encrypted_exports.py` and wired it into `scripts/run_master_cert_stack.py`.
- Focused certification passed: `certify_encrypted_exports`, `certify_private_write_classification`, `python3 -m anima.portable --selftest`, `python3 -m anima.platform --selftest`, `certify_identity_portability`, and `scripts/selftest.py`.
- Static classification now verifies 38 direct write sites with no pending plaintext export/training surfaces after adding the classified encrypted-backup writer.

Fifth closure update:
- Expanded `scripts/certify_secure_store_no_plaintext.py` from representative high-risk stores to a 31-compartment private-store matrix covering agency, teaching, auto-learn, knowledge packs, rollback, incident/SOC, metrics, constitution, meaning, reality, loops, opportunity, trajectory, theory, review, intake, LERF routes, founder console, identity sandbox, twin artifacts, text, bytes, JSON, and JSONL.
- Focused certification passed: `certify_secure_store_no_plaintext` with every matrix raw file carrying the `ANIMAENC1:` marker and no synthetic secret visible on disk, while normal load paths recovered the secret.
- The direct-write classification cert remains green with no pending plaintext privacy surfaces.

Sixth closure update:
- Added product/private-mode vault enforcement: `--require-encryption`, `ANIMA_REQUIRE_ENCRYPTION=1`, and `ANIMA_PRODUCT_MODE=1` refuse server startup unless `ANIMA_KEY` or the macOS Keychain item `anima` is active.
- Added deterministic keychain bypass for certs via `ANIMA_DISABLE_KEYCHAIN=1`.
- Added `scripts/certify_vault_requires_encryption.py` and wired it into `scripts/run_master_cert_stack.py`.

Seventh closure update:
- Added `anima/vault_backup.py` for encrypted off-device vault backup bundles with a bundle-local public KDF salt, minimal public wrapper metadata, encrypted payload, per-file SHA-256 integrity, dry-run restore, confirm-gated restore, overwrite refusal, wrong-key refusal, tamper detection, and path-traversal rejection.
- Updated `scripts/backup-anima.sh` to create `.vera.vab` encrypted vault bundles instead of raw `rsync` snapshots.
- Added `scripts/certify_encrypted_backup_restore.py` and wired it into `scripts/run_master_cert_stack.py`.
- Focused certification passed: `certify_encrypted_backup_restore`, `certify_encrypted_exports`, `certify_vault_requires_encryption`, compile checks, and backup script syntax.

Residual note before W03 becomes product-closed:
- Encryption still depends on an active `ANIMA_KEY` or macOS Keychain secret. Product mode now refuses plaintext startup and encrypted backup/restore is certified, but first-run key setup, recovery-code/hardware-key, and key rotation UX remain open.

### W04 - Query-token and localStorage auth are too weak for a privacy product

Severity: `P2`
Status: `CLOSED; CERTIFIED FOR SUPPORTED SAME-ORIGIN SHELLS`

Evidence:
- Original review found server auth accepted URL query `?k=`, `X-Anima-Key`, or `Authorization: Bearer`.
- Original review found browser UI stored token material in localStorage.
- Original review found no explicit Origin/CSRF boundary in the POST path.

Risk:
This is acceptable-ish for localhost experiments, but weak for LAN, tunnels, installed desktop wrappers, or a personal OS that may hold sensitive history.

Fix direction:
- Replace query-token login with one-time pairing.
- Store session tokens in HttpOnly/SameSite cookies where browser-hosted.
- Reject unsafe `Origin`/`Host` combinations on state-changing requests.
- Cert CSRF and hostile-origin POST attempts.

Closure update:
- Implemented after this finding: `Handler._authed()` now treats `?k=` as a GET/HEAD-only legacy credential; POST state changes require `X-Anima-Key` or `Authorization: Bearer`.
- `Handler.do_POST()` now rejects unsafe browser-origin state changes before token auth or body parsing.
- The POST boundary rejects hostile/malformed `Origin`, hostile `Referer`, and `Sec-Fetch-Site: cross-site`, while still allowing same-host browser POSTs and native/curl clients that omit browser origin headers.
- Responses now include `Referrer-Policy: no-referrer` and `X-Content-Type-Options: nosniff`, reducing accidental query-token leakage and MIME-sniffing risk.
- Added `scripts/certify_browser_origin_csrf.py`.
- Added `scripts/certify_browser_session_cookies.py` for the current browser-cookie path.
- Added both browser security certs to `scripts/run_master_cert_stack.py`.
- Updated `scripts/certify_security_baseline.py` so the baseline now proves the stricter contract.
- Focused certification passed: `certify_browser_session_cookies`, `certify_browser_origin_csrf`, `certify_passkey_auth`, `certify_security_baseline`, `certify_proactive_location`, `certify_audio_serve`, and `certify_expose_requires_auth`.

Residual note:
- `?k=` remains as a GET/HEAD-only first-pairing convenience so existing local setup links still work. It is no longer accepted for POST state changes.
- Browser auth cookies are now server-registered by nonce, so a correctly signed but never-issued cookie is rejected and an issued cookie can be revoked before expiry.
- Added `/auth/logout` to revoke the current auth nonce and clear both auth and Face-ID browser cookies.
- Added optional `ANIMA_PAIRING_CODE` values for true one-time pairing: first use mints the HttpOnly auth cookie, replay is rejected, and `X-Anima-Key` pairing remains as a compatibility bridge.
- Added authenticated-startup generation/display of a transient one-time browser pairing code when `ANIMA_PAIRING_CODE` is absent.
- Added a main chat first-launch pairing modal that posts the code to `/auth/pair`, mints the HttpOnly auth cookie, and never writes the code to localStorage.
- Added `/auth/pairing-code` so an already-authenticated browser can mint one more transient one-time pairing code for another shell/device; the route is auth-gated and honors the Face-ID/passkey layer when required.
- Added `/auth/sessions`, `/auth/rotate`, `/auth/logout-session`, and `/auth/logout-all` for hashed session inventory, current-session rotation, single-session revoke, and all-device logout.
- Expanded `scripts/certify_browser_session_cookies.py` to prove one-time code replay rejection, generated startup pairing codes, main-shell pairing UX, issued-only cookies, tamper/expiry rejection, revocation, HttpOnly/SameSite headers, logout wiring, session inventory, hashed IDs/no raw nonces, rotation, single-session revoke, logout-all, and no `anima_token`/`anima_sess` localStorage persistence.
- Added `scripts/certify_browser_shell_replay_migration.py` to prove additional-code minting, one-time consumption/replay rejection, auth/passkey gating, same-host POST support for desktop localhost, LAN browser, HTTPS tunnel, and same-origin installed/webview shells, and refusal of cross-host/cross-site/custom-scheme replay.
- Supported installed shells must use a same-origin localhost webview/proxy. Custom-scheme origins such as `tauri://localhost` are intentionally refused by the browser Origin wall unless a future explicit allowlist is designed and certified.

### W05 - Passkey lacked full WebAuthn signature verification

Severity: `P2`
Status: `CLOSED; CERTIFIED`

Original evidence:
- `anima/passkey.py` explicitly documents that it does not perform cryptographic signature verification.
- It validates challenge, origin, RP ID hash, user present, and user verified flags.

Risk:
As a local second factor, this is useful. As a product claim of passkey-grade authentication, it is incomplete.

Original fix direction:
- Either label it honestly as “local device-presence gate,” or implement full WebAuthn assertion verification with stored public keys and counters.
- Add replay/counter certs.

Closure:
- `anima/passkey.py` now parses WebAuthn registration `attestationObject`/authenticator data, extracts and stores the credential COSE public key, and supports ES256/RS256 assertion verification through `cryptography`.
- `auth_finish()` now verifies challenge, origin, RP-ID hash, user-present/user-verified flags, authenticator sign counter, and the assertion signature over `authenticatorData || SHA256(clientDataJSON)` before issuing the Face-ID session.
- Legacy rawId-only credential records are visible as `upgrade_required` and do not arm `required()`, so stale installs do not get locked out or silently treated as full WebAuthn.
- `passkey` storage now honors `ANIMA_STORE`, keeping certs hermetic.
- `scripts/certify_passkey_auth.py` now registers a deterministic synthetic ES256 WebAuthn credential, proves a valid assertion is accepted, rejects tampered signatures, missing user-verified flags, wrong challenges, and non-increasing sign counters, and keeps the session tamper/expiry floor.

Certification:
- Focused cert passed: `certify_passkey_auth`.
- Remaining product check: smoke-test the real browser `navigator.credentials.create/get` ceremony on representative Apple devices/packaging shells.

### W06 - Local host-app integrations have high blast radius once enabled

Severity: `P2`
Status: `CONFIRMED`

Evidence:
- `anima/applemac.py` sends Mail and Messages through AppleScript.
- It can read Mail subjects/senders and read iMessage `chat.db` with Full Disk Access.
- Send functions are intentionally called after draft confirmation, but the capability itself is powerful.

Risk:
This is exactly the kind of feature that makes Vera magical and dangerous. A future bug in confirmation flow, prompt injection, or route mapping could turn local OS privileges into real-world side effects.

Fix direction:
- Treat host-app access as a separate high-risk capability tier.
- Require per-recipient/per-app confirmation receipts.
- Cert that no prompt text can call send paths without the explicit confirmation action.
- Maintain an audit trail that is readable to normal users, not only developers.

### W07 - Location/weather egress needs a visible privacy receipt

Severity: `P2`
Status: `CLOSED; CERTIFIED`

Evidence:
- `anima/context_gather.py` can call Open-Meteo with latitude/longitude for proactive briefing context.
- This may be user-enabled through location settings, but the egress is still sensitive.

Risk:
Location is intimate data. Even “harmless weather” calls should be visible in a privacy-first companion.

Fix direction:
- Add an egress ledger for every network call containing destination, purpose, fields sent, retention assumption, and local/cloud status.
- Give users zero-egress and coarse-location modes.

Closure update:
- Added `anima/egress.py` with hard zero-egress mode via `ANIMA_ZERO_EGRESS=1`.
- Wired zero-egress into cloud provider activation, cloud key verification, direct cloud brain calls, allow-listed web fetches, and weather lookup before any socket is opened.
- Added `scripts/certify_zero_egress_mode.py` and wired it into `scripts/run_master_cert_stack.py`.
- Added `anima/privacy_receipts.py` for append-only per-turn privacy receipts and sanitized egress ledger rows.
- Wired turn receipts into `server._turn`, cloud provider calls, cloud key verification, allow-listed web fetches, and weather lookup.
- Added `scripts/certify_privacy_receipts.py` and wired it into `scripts/run_master_cert_stack.py`.
- Focused certification passed: `certify_privacy_receipts`, `certify_zero_egress_mode`, `certify_web_allowlist`, `certify_context_gather`, `certify_model_management`, `certify_route_backend_enforcement`, `certify_browser_session_cookies`, and `certify_privacy`.

Residual note:
- This closes the hard off switch plus receipt/ledger coverage for current cloud/web/weather/key-verification egress surfaces.

Second closure update:
- Added `receipt_history()`, `privacy_summary()`, `connector_policy()`, `record_connector_egress()`, `location_precision()`, and `prepare_location_for_egress()` to `anima/privacy_receipts.py`.
- Added `/privacy` plus `/privacy/receipts.json` as the normal-user Privacy Flight Recorder: turn receipts, egress feed, blocked events, connector feed, connector policy, zero-egress state, and location precision.
- Added `location_precision` to `anima/caps.py` with privacy-first default `coarse`; weather egress now rounds named-user coordinates by default, uses exact coordinates only when explicitly selected, and `off` blocks weather before any socket.
- Added the Settings link and weather precision control to `anima/web/index.html`.
- Added `feature_contracts/privacy_receipt_viewer.json` and `scripts/certify_privacy_receipt_viewer.py`, then wired the cert into `scripts/run_master_cert_stack.py` and the live-path Diamond matrix.
- Focused certification passed: `certify_privacy_receipt_viewer`, `certify_privacy_receipts`, `certify_zero_egress_mode`, and `certify_context_gather`.
- Live-path gate classified `privacy_receipt_viewer` as `COMPLETE`.

## Governance And Autonomy

### W08 - Approval packets are not strongly bound to the action performed

Severity: `P2`
Status: `CONFIRMED BY ADVERSARIAL PROBE`

Evidence:
- `anima/company_operator/approvals.py:23-32` stores action type, cost, budget ref, risk, and evidence.
- `anima/company_operator/approvals.py:63-65` only checks that the approval exists and status is `approved`.
- `anima/company_operator/action_ledger.py:66-68` accepts any approved approval ref for approval-gated action types.

Risk:
An approval intended for one action type, amount, vendor, or risk class can satisfy another action path if the ID is supplied before execution. Replay is partly blocked by `mark_executed`, but mismatch remains.

Probe result:
- Created an approved `publish` approval packet.
- Used that approval ID to perform `send_message`.
- `action_ledger.perform()` returned success and recorded all gates passed.

Fix direction:
- Add `approvals.validate_for_action(...)` that checks action type, cost ceiling, vendor, category, risk, subject, and expiry.
- Make approvals single-use and scoped.
- Cert mismatched approval attempts.

### W09 - Self-evolution high-risk approval only checks non-empty text

Severity: `P2`
Status: `CONFIRMED BY ADVERSARIAL PROBE`

Evidence:
- `anima/self_evolution/evolve.py:70-94` promotes proposals after rollback, certs, Diamond, and approval.
- `anima/self_evolution/evolve.py:85-86` only checks that `approval_ref` is non-empty for high/core risk proposals.

Risk:
The self-evolution gate is conceptually strong, but a high-risk/core promotion can record any string as an approval reference unless callers wrap it with stricter checks.

Probe result:
- Created a repeated-evidence `core` proposal with certs, rollback, and Diamond set true.
- Passed `approval_ref="not-a-real-approval"`.
- `promote()` returned success and recorded the fake approval reference.

Fix direction:
- Bind self-evolution to the approval ledger.
- Require approval action type `product` or `core_change`, matching proposal ID, risk level, cert set, and rollback ref.
- Cert fake approval strings and mismatched approvals.

### W10 - Budget module is not self-defensive enough

Severity: `P2`
Status: `CONFIRMED BY ADVERSARIAL PROBE`

Evidence:
- `anima/company_operator/budget.py:23-35` stores monthly cap and category caps.
- `anima/company_operator/budget.py:44-65` checks per-transaction caps and remaining total.
- Category cap appears to be checked per transaction, not cumulative per category.
- Monthly cap is stored but not enforced in the observed code.
- `record_spend()` accepts an approval reference string when needed but does not validate it itself.

Risk:
The normal `action_ledger.perform()` path is better guarded, but the budget module can be misused directly by future code. Governance primitives should be self-defensive because they become reused everywhere.

Probe result:
- Approved total `$1000`, monthly cap `$100`, category cap `ads=$50`.
- Recorded two `ads` spends of `$40`; both succeeded despite cumulative `ads=$80`.
- Recorded additional spend bringing total spend to `$160`; it still succeeded despite monthly cap `$100`.

Fix direction:
- Enforce cumulative category spend and monthly spend.
- Validate approval refs or require spending only through the action ledger.
- Cert direct-call attempts.

### W11 - Upwork Connects ledger can overspend in edge paths

Severity: `P2`
Status: `CONFIRMED BY ADVERSARIAL PROBE`

Evidence:
- `anima/marketplaces/upwork/pipeline.py` lets `spend_connects()` increment spent even when availability is insufficient, then floors available at zero.
- `advance()` ignores the result of `spend_connects()`.
- Status transitions are only partially constrained.

Risk:
Marketplace governance is intentionally human-in-the-loop, but accounting drift can mislead the human operator and future automations.

Probe result:
- With 3 available Connects, direct `spend_connects(amount=10)` returned success and produced `available=0, spent=10`.
- With 2 available Connects, `advance(..., "submitted", connects_spent=9)` returned success and recorded the bid as submitted.
- A bid moved from `submitted` directly to `paid` when payment evidence was supplied.

Fix direction:
- Make insufficient Connects a hard error.
- Stop status advancement if spend fails.
- Add a finite-state transition table.
- Cert overspend and illegal transition attempts.

### W12 - Broad exception handling has not been sorted by safety domain

Severity: `P2`
Status: `CONFIRMED`

Evidence:
- AST sweep found 990 broad `except` handlers in `anima/`.
- Some are good product resilience.
- Some guard security-adjacent or persistence paths.
- Example: `anima/company/storage.py:35-38` returns default on any load error.
- Example: `anima/observation/store.py:40-43` silently drops corrupt observation lines.

Risk:
Companions should be graceful, but security, consent, egress, auth, capability gates, and durable truth should fail closed or loudly. The current style makes it too hard to know which failures are safe.

Fix direction:
- Create a failure policy taxonomy:
  - Auth, consent, egress, spend, host actions: fail closed.
  - Memory/truth corruption: surface visibly.
  - UI adornments and optional context: fail soft.
- Add lint/certs around prohibited broad exceptions in gate modules.

### W13 - Verification can become ceremonial without adversarial certs

Severity: `P2`
Status: `CONFIRMED`

Evidence:
- Master cert stack currently passes 89/89 live after the cert-fixture hermeticity slice.
- Diamond v2 confirmed 109 complete / 1 honest partial.
- Current gaps above were found by adversarial reading, not by the green cert stack.

Risk:
The verification culture is a major strength, but green can start meaning “implemented as designed” rather than “resistant to misuse.”

Fix direction:
- Add negative certs for every weakness in this register.
- Keep a generated verification ledger in the repo or audit artifacts.
- Treat each fixed weakness as closed only when a cert proves it cannot regress.

## Product Shape And Frontier Capability

### Human Dishonesty Lens - Design Implication

Reference: `/Users/lamar/Desktop/The honest truth about dishonesty.pdf`

The provided PDF appears to be an 11-page image-based copy/excerpt of Dan Ariely's *The (Honest) Truth About Dishonesty: How We Lie to Everyone - Especially Ourselves*. The usable lens for Vera is not “assume users are bad.” It is the opposite: assume people want to see themselves as good while still bending rules when systems make it easy, ambiguous, normalized, distant from consequences, or easy to rationalize.

Product implications for Vera:
- Vera should reduce self-deception with gentle mirrors, not scolding.
- Vera should make consequential actions concrete before they happen: who is affected, what leaves the device, what money is spent, what relationship is touched.
- Vera should keep users honest at the moment of temptation through small friction, not after-the-fact shame.
- Vera should show receipts that are emotionally legible: “Here is what I am about to do, why, under whose approval, and how you can undo it.”
- Vera should treat ambiguity as a risk signal. If an action can be rationalized in multiple ways, ask for explicit intent.
- Vera should not help users launder responsibility by saying “the AI did it.” Every external action needs a named human approval and a clear audit trail.
- Vera should protect the user's future self, not only the user's immediate request.

This lens strengthens the case for approval binding, privacy receipts, consent reminders, domain-pack boundaries, and learning transparency. The companion should be warm enough to be trusted and structured enough to keep both Vera and the user out of self-justifying drift.

### W14 - Revenue/company tooling can dominate Vera's identity

Severity: `P2`
Status: `FRONTIER IMPROVEMENT`

Evidence:
- Large subsystems exist for company operations, revenue, marketplaces, workforce, distribution, trust, resources, and empire.
- `/board/revenue` is linked-active; business-development functionality is broad and concrete.
- The core overview does frame Vera as a local-first AI operating system, but the visible route surface can still skew perception.

Risk:
If Vera is meant to become a living personal companion and privacy frontier, “revenue ops workspace” is too small a frame. It should be a domain pack, not the center of gravity.

Fix direction:
- Make revenue/company a disabled-by-default or optional domain pack.
- Create a core-first navigation model: Self, Memory, Privacy, Learning, Companionship, Skills, Domains.
- Add domain pack manifests with capability gates, ledgers touched, egress used, and human confirmations required.

### W15 - Self-learning exists, but the lived product loop is not frontier-grade yet

Severity: `P2`
Status: `FRONTIER IMPROVEMENT`

Evidence:
- `auto_learn` is suggestion-only and can convert into Teaching Mode drafts.
- `teaching` supports approve/edit/reject/chat-only/never-learn/rollback.
- `self_evolution` supports capability gaps, proposals, certs, rollback, Diamond, and promotion.
- `lerf_grow` is default-off and supports opt-in task-skill growth.

Risk:
The machinery is real, but the user-facing experience may not yet feel like: “I do not know how to do that, but I can learn it safely, show you the plan, practice it, verify it, and remember the new skill.”

Fix direction:
- Build a Learning Studio.
- On failure, produce a skill-gap card with options: teach me, research locally, draft a tool, run a sandbox, never learn this.
- Show a skill tree with provenance, cert status, rollback point, and privacy footprint.

### W16 - Personality doctrine needs relational honesty modes

Severity: `P2`
Status: `FRONTIER IMPROVEMENT`

Evidence:
- `anima/mouth.py` contains strong persona hardening around vivid identity and not speaking like a generic AI/code/program.

Risk:
Vera can feel more alive because of this, but trust can suffer if she sounds like she is denying the software substrate or overclaiming subjective experience. A frontier companion needs warmth without deception.

Fix direction:
- Define user-selectable relational modes: Plain, Companion, Immersive/Mythic.
- Cert that Vera is never coldly self-erasing, never deceptive about physical embodiment, and never forced into brittle identity claims.
- Add an “identity diff” explaining how her style, memories, and preferences changed over time.

### W17 - Privacy experience is not yet tangible enough

Severity: `P2`
Status: `FRONTIER IMPROVEMENT`

Evidence:
- Local-first pieces exist: route ledger, cloud scrubbing, caps, optional encryption, truth ledger, consent gates.
- `/privacy` now makes turn/egress/location/connector receipts visible, but memory/source/action receipts are not yet unified into one human privacy story.

Risk:
Privacy that is only implemented, not experienced, will not feel like a new frontier to users.

Fix direction:
- Per-turn privacy receipt. CLOSED / CERTIFIED for turn/backend/egress.
- Zero-egress mode. CLOSED / CERTIFIED for cloud/web/weather/key checks.
- Memory rooms: sealed, private, shareable, temporary, and erasable.
- “What does Vera know about me?” explorer.
- “Why did Vera remember this?” and “forget this everywhere” controls.

### W18 - Public shells reveal capability surface when exposed

Severity: `P3`
Status: `CONFIRMED`

Evidence:
- Several public HTML shells are served before auth gating.
- This does not expose private data by itself, but it reveals product routes and capabilities.

Risk:
On localhost this is fine. On LAN or tunnel exposure, route discovery can help attackers understand what to target.

Fix direction:
- Under `--expose`, require auth before serving non-minimal shells.
- Serve only a locked pairing screen until authenticated.

### W19 - Server monolith makes security review harder than it needs to be

Severity: `P3`
Status: `CONFIRMED`

Evidence:
- `anima/server.py` contains the HTTP server, route table, auth checks, UI serving, POST dispatch, and turn loop.

Risk:
Security-sensitive checks are harder to audit when many unrelated responsibilities live in one file.

Fix direction:
- Extract auth/session, route registry, static shell serving, POST action dispatch, and turn execution into separate modules.
- Keep a single middleware-style gate for auth, origin, capability, and rate limiting.

### W20 - Cloud/model preset drift will be a product maintenance issue

Severity: `P3`
Status: `LIKELY`

Evidence:
- Some model/provider choices are hard-coded in local modules.
- Key verification can fetch provider model lists, but product defaults and docs can still drift.

Risk:
Cloud fallback should stay useful without users debugging stale model names.

Fix direction:
- Store cloud provider presets in a versioned registry.
- Add a health check that confirms configured models exist before advertising cloud readiness.
- Treat cloud fallback as optional, explicit, and receipt-bearing.

### W21 - Some cert fixtures can dirty real `.anima` during verification

Severity: `P2`
Status: `CLOSED; CERTIFIED`

Evidence:
- A standalone `scripts/certify_live_paths.py --gate` run after the Privacy Flight Recorder slice classified the new feature as `COMPLETE`, but reported `hermetic (byte-identical): NO - LEAK`.
- Recent real-store fixture writes included `.anima/SecBaseCert.intake.jsonl`, `.anima/HPCert.intake.jsonl`, `.anima/AiSecCert.intake.jsonl`, `.anima/PrivPortCopy.*`, `.anima/security_events.jsonl`, `.anima/Vera.meaning.jsonl`, and `.anima/Vera.trajectory.jsonl`.
- A deeper live-path diagnostic also found `certify_live_ux.py` mutating real `Vera.*` state through direct `_intake_plan("Vera")` calls and POSTs to the running server when it was up; a follow-up diagnostic found `certify_response_latency.py --gate` still POSTing to real `/say`.
- Final W21 diagnostics found `probe_total_reality` mutating the real SOC trail and then `Vera.continuity.jsonl`; both are now covered by the focused guard and the full live-path fingerprint.
- The adjacent privacy/weather cert family also could append to `.anima/privacy/global.egress.jsonl`; the Privacy Flight Recorder slice fixed `scripts/certify_zero_egress_mode.py` and `scripts/certify_context_gather.py` to redirect `privacy_receipts.STORE` into temp stores.

Risk:
Diamond repeatability can still confirm feature classification, but a privacy product should not let certification fixtures pollute a real user vault. Verification must be byte-clean or explicitly classify every allowed volatile artifact.

Closure:
- Broadened `scripts/gate0_prime_experience.py` so the shared hermetic context redirects `STORE`, `DEFAULT_STORE`, `_STORE`, and `ANIMA_STORE` for the legacy/live-path module family.
- Wrapped `scripts/certify_security_baseline.py`, `scripts/certify_host_pressure.py`, `scripts/certify_ai_security.py`, and `scripts/certify_privacy.py` in that hermetic context before they touch synthetic creatures.
- Moved `scripts/certify_live_ux.py` off the user's running Vera server; it now starts an isolated loopback HTTP server using the production Handler with stores redirected, so the large-upload and 413 proofs remain real HTTP without mutating real `Vera.*` state.
- Moved `scripts/certify_response_latency.py --gate` off the user's `/say` endpoint; it now drives `server._turn` inside the shared temp store with seeded synthetic memory, preserving the fast-path proof without mutating real turn state.
- Made `anima/incident.py` honor `ANIMA_STORE`, so SOC/security events from child certs follow the hermetic store instead of hardcoded `.anima`.
- Moved `scripts/certify_total_reality.py` delegated cert and rover subprocesses under isolated temp `ANIMA_STORE` contexts.
- Wrapped `scripts/certify_live_paths.py::run_subcert` in the shared hermetic context so subprocess certs inherit an isolated store by default, rather than relying on each child cert to remember the redirect.
- Disabled the AI-security live `/say` model-echo advisory by default; it now runs only with `ANIMA_CERT_LIVE_MODEL_ADVISORY=1`, so certification does not talk to a real live Vera server.
- Added `scripts/certify_cert_fixture_hermeticity.py`, which snapshots the known synthetic-fixture, SOC, continuity, and `Vera.*` live-UX footprint in real `.anima`, runs the formerly leaky cert family, and fails if any fixture file is created or mutated.
- Wired `certify_cert_fixture_hermeticity` into `scripts/run_master_cert_stack.py`.
- Added the build-slice visibility rule to `SYSTEM_OVERVIEW.md`: each slice must include code, cert, report/ledger evidence, weakness-register update, and an honest status for partials.

Certification:
- Focused certs passed: `certify_security_baseline`, `certify_host_pressure`, `certify_ai_security`, `certify_privacy`, `certify_live_ux`, `certify_response_latency`, and `certify_total_reality`.
- New adversarial guard passed: `certify_cert_fixture_hermeticity` proved the real `.anima` synthetic-fixture/SOC/continuity footprint was byte-identical before/after.
- Full live-path visibility pass passed: `scripts/certify_live_paths.py --gate` returned `hermetic (byte-identical): YES`, `109 COMPLETE / 1 HONEST PARTIAL / 1 DEFERRED-NOT-CLAIMED`, `0 WALLPAPER`, `0 PRODUCT PARTIAL`, and `0 UNCLASSIFIED`.

## Closure Criteria

A weakness should be marked closed only when:
1. Code is fixed.
2. A positive cert proves the intended behavior.
3. A negative/adversarial cert proves the old failure mode is blocked.
4. The verification ledger records the closure and links to the cert.

Recommended immediate next sprint:
1. Build first-run key setup, recovery-code/hardware-key, and key rotation UX.
2. Bind approvals to action intent.
3. Harden packaging for custom-scheme installed wrappers only if the product chooses that route.
4. Strengthen budget and marketplace resource invariants.
5. Reframe revenue/company as optional domain packs in UI and documentation.

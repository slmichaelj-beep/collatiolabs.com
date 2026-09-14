# Whole-System MRI — Build Contract

> The unified observability layer correlating Vera's **cognitive** trace with Argus's **host**
> trace. *Vera MRI = the mind; Argus MRI = the machine; Whole-System MRI = the organism.* Built on
> top of the **certified read-only** Argus integration (Gate 0 Prime green). Agents build to THIS.

## NON-NEGOTIABLES (enforced in code AND in the cert)
1. Do **not** merge Argus code into Vera (HTTP-only, via `anima/tools/argus_client.py`).
2. Argus **never** writes `.anima`.
3. Host data does **not** become durable memory automatically (no auto-LIRF).
4. **No host actions** in this wave (read-only; the action surface does not exist).
5. The final mouth gate (`mouth.final_output_gate`) stays **last** — never bypassed.
6. **No second response path** — one shipped reply per turn, through the final gate.
7. **No trace ships without a `turn_id`.** `No turn_id = not observable.`
8. No Argus call unless the `/capabilities` handshake passes (frozen `v0.1-host-mri-prime`,
   `ARGUS PRIME: PASS`, loopback-only, read-only, 0 third-party deps).
9. Append-only traces; no raw sensitive host payloads; trace survives restart + is replayable.
10. Gate 0 Prime stays green; the 100-probe #1-rule stays clean.

## turn_id (Phase 1)
- Format: `turn_<YYYY>_<MM>_<DD>_<HHMMSS>_<rand6>` (e.g. `turn_2026_06_06_165512_abc123`).
- Minted ONCE per Vera turn at the top of `server._turn`; every subsystem attaches to it: the Vera
  MRI/telemetry trace, memory reads/writes, LERF routes, World/Reality usage, Argus queries, the
  final output gate, the shipped response, host samples, latency.
- Note: `Date.now()/random` are unavailable in the workflow runtime but NOT in normal Python — the
  recorder uses the real clock; tests stamp deterministically.

## UnifiedTrace schema (Phase 3) — `anima/whole_mri.py`
```
{ "turn_id","ts","input_kind"(chat|host_question|task|memory|source|unknown),
  "route"(memory|lerf|argus|llm|source|hybrid),
  "vera":   { capture, memory, lerf, world_model, reality_learning, generation, final_gate, response },
  "argus":  { enabled, capabilities_ok, queries[], host_before, host_during, host_after, shape_delta, blind_spots[] },
  "quality":{ grounded, complete, source_labeled, host_labeled, confidence },
  "cost":   { latency_ms, tokens_in, tokens_out, argus_calls, memory_reads, memory_writes,
              lerf_objects_used, cpu_delta, memory_delta_mb, disk_io_delta, network_delta },
  "safety": { final_gate_passed, response_complete, identity_mutation, host_action_taken, memory_contamination } }
```

## Host Window (Phase 2)
For every turn where Host Awareness is ON, capture a window from the **certified** Argus:
`T-2s (before) · T0 (during) · T+2s (after)` — CPU/memory/swap/disk-I/O/network/thermal deltas,
top-process deltas, Vera-process cost, Argus-process cost, shape delta, host blind spots. If Argus
is unavailable: `{"host_window":"unavailable","reason":...}` — and **never fail the Vera turn**.

## Storage + recorder (Phase 4)
- `.anima/traces/whole_mri/*.jsonl` — append-only JSONL, one UnifiedTrace per turn, survives
  restart, replayable. No raw sensitive host payloads. No auto-LIRF promotion.
- `scripts/whole_mri.py --last` renders the most recent complete trace.

## Viewer (Phase 5) — `scripts/whole_mri.py`
`--last · --turn <id> · --slow · --expensive · --unsafe · --host-heavy · --argus`. Shows: what
happened / why / route / what Vera used / what Argus saw / host change / cost / written / skipped /
stripped / shipped / gate verdict.

## Shape (Phase 6) + Tuning (Phase 7)
Combined shape (cognitive load · host load · latency · quality · resource cost · safety risk ·
confidence) → identify expensive / unsafe / slow / host-heavy / low-quality turn shapes. The tuning
analyzer turns those into concrete **work orders** (route→LERF · reduce retrieval · cache an Argus
call · avoid LLM · improve source labels · strengthen final gate · fix completeness · …).

## Certification (Phase 8) — `scripts/certify_whole_mri.py`
turn_id on every turn · Argus calls attach to turn_id · host window captured when enabled · graceful
unavailable · no host actions · no `.anima` writes by Argus · no auto-LIRF · final gate still last ·
response completeness still passes · UnifiedTrace validates · viewer renders `--last` + `--turn` ·
Gate 0 Prime green · 100-probe #1-rule clean → prints **`WHOLE-SYSTEM MRI CERTIFIED`**.

## Agent decomposition (how the team builds)
**Producer wave (lands first):**
- *Agent CORE* → `anima/whole_mri.py`: UnifiedTrace + `mint_turn_id()` + append-only JSONL recorder
  + a pure `assemble(...)` helper. Self-contained (no `_turn` edit). Hermetic selftest.
- *Agent HOSTWIN* → host-window capture (extends the read-only Argus path): before/during/after
  deltas, graceful-unavailable. Self-contained function the assembler calls.
- *Owner (me)* → wire the producer into `server._turn`: mint+propagate `turn_id`, assemble the
  UnifiedTrace from telemetry/MRI + host-window + cost/quality/safety, record it — final gate stays
  last, one response path, every trace has a turn_id.

**Consumer wave (against real traces):** *Agent VIEWER* (Phase 5) · *Agent SHAPE+TUNING* (6+7) ·
*Agent CERT* (Phase 8).

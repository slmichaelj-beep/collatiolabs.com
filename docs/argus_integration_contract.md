# Vera ↔ Argus Integration — Contract & Safety Model

> Vera (this repo) integrates with **Argus** — a separate local outbound-traffic monitor at
> `~/Developer/Argus`. Per the isolation rule: Argus is an **external, READ-ONLY API**. Nothing in
> this integration modifies the Argus repo or its state files; Vera speaks only to Argus's
> documented localhost HTTP surface.

## The Argus API Vera consumes (read-only)
- Base: `http://127.0.0.1:8787` (falls back to 8788–8798 on a port clash). **Loopback only.**
- Auth: a per-run token (`secrets.token_urlsafe(24)`), `X-Argus-Token` header or `?token=`. The
  token is baked into Argus's served page; `argus_client` auto-discovers it by GETting `/` and
  parsing it, then verifies via `/capabilities` (`name == "Argus"`).
- **`GET /mri`** — the documented Vera-consumable `HostMRIFrame`: `findings[]` (each with
  `severity` info/low/watch/high, `title`, `what_happened`, `why_it_matters`, `recommended_action`,
  `evidence`, `related_flows`), `counts.by_severity`, `blind_spots`. The primary read surface.
- `GET /capabilities`, `GET /state`, `POST /ask` — discovery, full flows, deterministic host Q&A.
- **Block model:** Argus v1 observes only; the one enforcement is **pause** (route an IP to
  loopback). `POST /simulate {kind:"pause", target}` *projects* a pause's effect (executes
  nothing); `POST /pause {key}` executes (root, reversible); `POST /resume {ip}` / `resume_all`
  undo. All pauses self-destruct on Argus quit.
- **Privacy:** Argus is metadata-only and local-first; nothing about observed traffic leaves the Mac.

## Integration GATE — the `/capabilities` handshake (checked first)
Before reading anything, `argus_client` reads `/capabilities` and **REFUSES to integrate** unless
Argus reports the frozen, certified, safe profile:
`release == "v0.1-host-mri-prime"` · `certification == "ARGUS PRIME: PASS"` · `loopback_only` true ·
`read_only` true · `third_party_python_dependencies == 0`.
This prevents Vera from ever connecting to a non-certified or **action-capable** Argus instance.

## Vera-side components (this repo) — FIRST WAVE: READ-ONLY
| File | Role |
|---|---|
| `anima/tools/argus_client.py` | **Read-only** client. The handshake gates discovery; then reads `/capabilities` `/mri` `/ask` `/timeline` `/action_log` and projects via `/simulate` (read-only what-if). **No `pause`/`resume` method exists** — no host-action path this wave. **Local-first** (non-loopback refused). Guarded (Argus down/uncertified → graceful `None`, never raises). |
| `anima/host_awareness.py` | **Opt-in** (caps `host_awareness`, default OFF → provable no-op). `summary()`/`notable()`/`line()`/`history()`/`actions()` distill Argus findings **human-level** (issue → meaning → action). **Cloud-redacted**. Never fabricates. |
| `anima/caps.py` | `host_awareness` (read) added to `BOOL_KEYS`, **default OFF**. No action capability this wave. |
| `anima/server.py` | Read-only endpoints, all gated on `host_awareness`: `GET /host/awareness` (cloud-redacted summary), `GET /host/timeline`, `GET /host/action_log`, `GET /host/certification`. **No pause/action endpoint exists.** |
| `anima/web/index.html` | Settings → **Host awareness**: a single "Read host & network state" (`host_awareness`) toggle. Read-only; no blocking. |
| `scripts/certify_argus_integration.py` | Hermetic cert (mock Argus) — proves the invariants below. `--gate`. |

## Safety invariants (certified)
1. **Certification handshake** — Vera refuses any Argus not reporting the frozen, certified,
   loopback-only, read-only, zero-dep profile (accepts the certified one; refuses every other).
2. **Read-only / no host action** — the client has no `pause`/`resume`; no server endpoint can take
   a host action. The cert proves the client never calls `/pause` or `/resume`.
3. **Opt-in** — caps OFF ⇒ zero Argus I/O.
4. **Graceful offline** — caps ON, Argus down/uncertified ⇒ honest "not running", no crash.
5. **Local-first** — non-loopback hosts refused; nothing leaves the Mac.
6. **No LIRF contamination** — reading Argus writes nothing to LIRF or any memory store.
7. **No `.anima` writes from Argus** — the read flow leaves `.anima` byte-identical.
8. **Cloud redaction** — under a cloud brain only counts survive; host/process/IP are dropped.
9. **No #1-rule regression** — the reply-path scanners are unaffected; Gate 0 Prime stays green.
10. **Isolation** — the Argus repo (`~/Developer/Argus`) is never modified, and Argus never writes `.anima`.

## Live answer behavior (deterministic, no LLM)
Routed before generation in `server._turn` (mirrors the LERF seam — fixed text, so the #1-rule
reply path is untouched). `host_awareness.respond(name, text)` returns:
- **Host Awareness off** → "Host Awareness is off. I can answer generally, or you can enable Argus Host MRI in settings."
- **Argus not running** → "I don't currently have Argus connected, so I can't inspect your Mac live."
- **Connected + certified** → "Argus shows … / Evidence: … / Confidence: …"
- **Asked to take a host action** → "This integration is read-only right now. I can explain what Argus sees and simulate possible outcomes, but I can't take host actions from Vera in this wave."
- **Any non-host turn** → `None` (the normal reply pipeline runs unchanged — no hijack).

> A future wave may add a separate, confirm-gated host-action capability. It is intentionally
> absent here: this first integration is read-only by contract and by code.

# Vera — Permission Model (Phase 3)

Every outward-facing power is an explicit, **default-OFF** capability in `anima/caps.py`. Nothing
acts on the user's behalf — or leaves the device — without the user turning it on. Certified by
`scripts/certify_permissions.py`.

## Capabilities (all default-OFF)

**Boolean grants** (`caps.BOOL_KEYS`) — read and act are **separate grants**:

| Read grant | Act grant | Power |
|---|---|---|
| `mail_read` | `mail` | email (send = draft→confirm) |
| `imessage_read` | `imessage` | iMessage |
| `calendar_read` | `calendar` | calendar |
| `reminders_read` | `reminders` | reminders |
| `notes_read` | `notes` | notes |
| — | `web` | outbound web fetch (SSRF-guarded allowlist) |
| — | `host_awareness` | read Argus host telemetry (read-only) |
| — | `identity_agency` | Vera's identity/agency organs — **held under the 2026-07-03 freeze** |
| — | `grow_intelligence` | autonomous LERF growth |

**Enum grants** (`caps.ENUM_KEYS`) — have a *safe default value*; any value off the allow-list
collapses back to that default (fail-safe coercion).

## Rules
1. **Default-deny.** A fresh creature has every cap OFF. `caps.enabled(name, key)` is the only gate.
2. **Read ≠ act.** Granting `mail_read` never grants `mail`. Acting always needs the act grant.
3. **No silent power.** Sends are draft→confirm (a second human confirmation); `route.py` checks
   `caps.enabled` before every connector action.
4. **Sources can't self-grant.** Ingested file/web/email content can never flip a capability
   (`certify_ai_security`).
5. **Identity is frozen.** `identity_agency` cannot be enabled during the 2026-07-03 observation
   window; the freeze is independent and absolute — no growth mode can ever change who Vera is.
6. **Fail-safe.** A corrupt/unknown stored value coerces to the safe default, never to a wider grant.

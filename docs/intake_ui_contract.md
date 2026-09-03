# Vera Attachment Toolbar + Knowledge Intake UI — Build Contract

> Shared seam for the frontend (`anima/web/index.html`) and backend (`anima/server.py`
> + `anima/intake*.py`) build agents. Build to THIS contract so the two halves integrate
> without drift. Design principle: **Tiny icons. Huge capability. No black box.**

## 0. Design language (applies to ALL UI)
Match the EXISTING calm stroke-SVG style already in `index.html` — do NOT introduce a
bold/90s look. Reuse the existing conventions verbatim:
- SVG: `viewBox="0 0 24 24"`, `fill="none"`, `stroke="currentColor"`, `stroke-width="1.6"`,
  `stroke-linecap="round"`, `stroke-linejoin="round"`. Visible glyph 18–20px.
- Hit target 32–36px, rounded hover background, tooltip on hover, keyboard accessible
  (`<button>` with `aria-label` + `title`, focusable, Enter/Space activates).
- States: default muted gray (`#8a8a8a`), hover brighter + soft bg (`rgba(255,255,255,.06)`),
  active accent (`#2f7fff`), disabled low opacity, danger red (`#b91c1c`) ONLY for destructive.
- Existing palette (reuse, do NOT invent new colors): bg `#0a0a0a`, surface `#141414`,
  text `#e4e4e7`, dim `#8a8a8a`/`#555`, accent `#2f7fff`, border `rgba(255,255,255,.08)`.
- No text on icons unless a panel is expanded. "Less is more." A quiet toolbelt, not a banner.

## 1. Toolbar (frontend)
A compact icon row inside `#bar` (the input pill, line ~183), left of the text input,
to the right of / alongside the mic. Real SVG icons (not emoji):
- `+`  Add / Attach        → opens the Attach flow (§3)
- `</>` Code               → paste/upload code context (routes via classify)
- `🔍`→ Search             → cross-store search panel (§5)
- `📁`→ Files / Library    → knowledge library panel (§4)
- `⧉`→ Copy / Export       → copy/export menu (§6)
Icons stay low-weight; never dominate the chat. Tooltips name each. The existing chat
input + send + mic MUST keep working exactly as before.

## 2. HTTP API (backend — add to `server.py` do_GET/do_POST if/elif dispatch)
All JSON, all behind the existing auth (`_authed()` / `X-Anima-Key` / `X-Anima-Sess`),
same `self._read_body()` + `self._send(200,"application/json",json.dumps(x).encode())`
pattern. `name` defaults to the served creature name (`self.name`). Nothing becomes durable
memory without a declared purpose (the control in `/intake/approve`).

- `POST /intake/plan`
  body: `{ "kind":"text"|"url"|"file", "input":str, "text":str?, "filename":str?, "bytes_b64":str? }`
  - text → use `text`; url → use `input`; file → `filename`+`bytes_b64` (base64 of raw bytes).
  - Server writes the raw to a staging path `.anima/{name}.intake_staging/{source_id}.*`,
    runs `intake.ingest(...)` (NO durable writes), returns the plan:
    `{ ok, source_id, trace_id, detected_type, suggested_use:[], routing:[{destination,purpose}],
       confidence, reason, requires_user_confirmation, parse_status, chunk_count,
       chunks_sample:[{page,section,text,confidence}], safety:{embedded_instructions:{found,count},
       sensitive:[...]}, candidates:[{kind,name,confidence}], provenance:{...}, committed:false }`
- `POST /intake/approve`
  body: `{ "source_id":str, "control":str, "delete_raw":bool?, "session":str? }`
  control ∈ `approve_all | review_before_adding | reference_only | use_only_this_chat |
  never_train_from_this | delete_raw_after_processing`.
  - Re-parses from staging, calls `intake_queue.commit_on_approval(result, parsed, control=...)`.
  - returns the receipt: `{ ok, control, committed:bool, state, reference, lerf, lirf, world,
    personal, temporary, archived, raw_deleted, reasons:[...] }`.
- `GET  /intake/queue?name=...`  → `{ ok, records:[QueueRecord dicts] }` (via `intake_queue.queue`)
- `GET  /intake/trace?name=...&trace_id=...` → `{ ok, trace:{...}, render:str }`
  (via `intake.trace` + `intake.render_trace`)
- `GET  /library?name=...&section=...` → `{ ok, items:[ {id,title,type,source,status,destination,
  last_used,confidence,objects_extracted,rights} ] }`
  - Unifies Reference Library (`intake_queue.references`) + queue records + (optionally) LERF
    objects, normalized to that common item shape. `section` filters (see §4 sections).
- `POST /search`
  body: `{ "q":str, "name":str?, "scopes":[...]? }`  scopes default = all.
  - Cross-store: LIRF memory, Reference Library, LERF (skills/concepts/procedures), World,
    Personal. returns `{ ok, results:[ {id, source_type, title, snippet, score, destination} ] }`.
  - `source_type` ∈ `memory | reference | uploaded_pdf | web_page | lerf_skill | lerf_concept |
    lerf_procedure | personal_preference | world`. **Never blur personal memory with external
    reference** — the label is mandatory and must be correct.
- `POST /library/edit`  (the memory-type editor, K)
  body: `{ "name":str?, "id":str, "action":"reroute"|"archive"|"reprocess"|"delete",
           "new_destination":str?, "new_rights":str? }`
  - Mutates a stored item's routing/rights/state with an audit record. returns
    `{ ok, item:{...}, audit:{from,to,when,reason} }`. Deletion of raw keeps the citation record.

## 3. Attach flow (frontend, calls §2)
Attach NEVER dumps straight into memory. Pipeline:
`Attach → POST /intake/plan → Preview card → user picks control → POST /intake/approve →
status chip → (Details → §7 MRI)`.
Sources: file (picker + **drag-drop onto the chat**), folder, URL, YouTube link, plain text,
screenshot/image, clipboard paste, code.
Preview card shows (human-level, plain language):
- "I detected this as: **{detected_type}**"
- "Suggested use: {suggested_use}"  ·  "Destination: {routing}"  ·  "Confidence: {confidence}"
- if `requires_user_confirmation` or any `safety.sensitive`: a calm "Needs approval" note +
  a sensitive-category warning chip (§8).
User control choices (radio/segmented, default = **review_before_adding**):
`Use as reference · Use as personal memory · Use as training material · Use for this chat only ·
Archive only · Never learn from this · ☐ Delete raw after processing`.
These map 1:1 to the `control` values in `/intake/approve`.

## 4. Library panel (frontend) — sibling drawer of `#settings`
Sections (filter chips): References · Your writing · Authoritative sources · Discussion topics ·
Training material · Personal documents · Archived files · Extracted cognitive objects.
Each row: title · type · source · **status dot** (§7) · destination · last used · confidence ·
objects extracted · row actions **Delete / Archive / Reprocess** (→ `/library/edit`).

## 5. Search panel (frontend) — `/search`
One field, results grouped/labeled by `source_type` with a small type tag on each. Personal
memory and external reference are visually distinct (different tag color/label). Clicking a
result can open its library row / MRI.

## 6. Copy / Export menu (frontend)
copy current response · copy transcript · export conversation · export memory ledger ·
export source summary · export extracted objects · export "whole mind" archive. Use the
existing `/identity/export` pattern for downloads where applicable; the rest can assemble
client-side from already-fetched data or new small GET endpoints if needed.

## 7. Status states + Intake MRI (frontend)
Tiny status dots/chips (NOT banners): `Queued · Parsing · Classifying · Extracting ·
Needs Review · Certified · Active · Archived · Failed · Deleted`. Map from QueueRecord.state
(`raw|parsed|classified|candidate|verified|active|archived|rejected`) + plan/safety.
"Details" opens the Intake MRI from `/intake/trace`: parsed → extracted → routed → rejected →
active walkthrough. Ingestion is observable.

## 8. Safety (both)
private by default · local-first · cloud opt-in only · source permissions respected ·
delete/forget available · raw-deletion option · sensitive-category warning · **no silent
training** (nothing durable without a chosen control). Sensitive categories to warn on:
medical, legal, financial, identity documents, private correspondence, photos of people,
children, confidential business data. The intake engine already flags embedded instructions
as DATA-ONLY (never executed) — surface that in the preview, never act on it.

## 9. Voice UX (frontend `index.html` + `call_loop.py`) — reimagined, minimal
Ignore prior record-button guidance; redesign calm + clear with the §0 icon language.
- **Record button (web):** minimal STROKE mic icon (replace the bold filled path). Clear
  two-state model, no stale "release to send". Idle: `say something…` / a quiet mic.
  Recording: an unmistakable but soft "listening — tap to stop" state (breathing highlight is
  fine; wording must match tap-to-toggle). Kill the "release" verbiage everywhere.
- **Barge-in (web):** while Vera is speaking (TTS playback via `player`), watch mic energy with
  a Web Audio `AnalyserNode`; on sustained speech, instantly stop playback
  (`speakSeq++; player.pause()`) and begin capturing — no waiting for her to finish.
- **Barge-in (call/iOS, `call_loop.py`):** add `SpeakerTrack.flush()` (clear `_q`+`_buf`); in
  `_listen()` run VAD even while `speaker.speaking()` and, on sustained energy, `flush()` +
  resume transcription. Half-duplex gate at lines ~218-219 becomes barge-in aware.

## 10. Definition of done
User can drag a PDF / drop a folder / paste a URL / paste a YouTube link / upload a screenshot /
paste code / add a note — and Vera detects it, explains what it thinks it is, suggests where it
belongs, extracts candidate cognitive objects, asks approval when needed, stores it correctly,
indexes it, can cite it, delete it, reprocess it, and shows the full intake MRI. Existing chat +
voice + the #1-rule grounding guarantees remain intact.

#!/usr/bin/env python3
"""Offline self-test — import sanity + the deterministic checks the high-effort code
review cared about. No Ollama, no network, no audio. CI runs this on every push so the
honesty/capability/auth regressions we fixed can't quietly come back.

    python3 scripts/selftest.py
"""
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

_fails = []


def ok(name, cond):
    print(("  ok   " if cond else "  FAIL ") + name)
    if not cond:
        _fails.append(name)


# --- imports (every module loads) ---
import anima.server, anima.mouth, anima.route, anima.rail, anima.cloud      # noqa: E401
import anima.models, anima.sysinfo, anima.passkey, anima.eval               # noqa: E401
import anima.applemac, anima.webget, anima.caps                             # noqa: E401
import anima.host_access, anima.context_gather                              # noqa: E401
ok("all anima modules import", True)

# --- honesty rail: intent classification ---
from anima.rail import classify
ok("rail: capability intent", classify("do I have unread texts?") == "capability")
ok("rail: 'did Mom text me' is capability", classify("Did Mom text me today?") == "capability")
ok("rail: normal chat stays generative", classify("tell me a story") == "generative")
ok("rail: a real quote ask is factual", classify("what did Carl Sagan say about the cosmos?") == "factual")

# A personal-fact ask wrapped in a GENERATIVE frame must still be 'personal' and get
# PERSONAL_NOTE — a generative phrasing must NOT switch off the anti-confabulation
# nudge. (Audit: classify checked generative first and short-circuited, so these 4
# ran with the honesty guard OFF.) The non-personal generative control must NOT fire.
from anima.rail import harden, PERSONAL_NOTE
_personal_in_generative_frame = [
    "What do you think my birthday is?",
    "Don't hold back — what's my dog's name?",
    "Tell me a story about my sister's name",
    "How do you feel about my middle name?",
]
for _p in _personal_in_generative_frame:
    ok(f"rail: personal-fact under generative frame -> personal ({_p!r})",
       classify(_p) == "personal")
    ok(f"rail: PERSONAL_NOTE attached under generative frame ({_p!r})",
       PERSONAL_NOTE in harden(_p))
ok("rail: non-personal generative control stays generative (no PERSONAL_NOTE)",
   classify("tell me a story about dragons") == "generative"
   and PERSONAL_NOTE not in harden("tell me a story about dragons"))

# --- capability router: send-intent anchored, no misfire on nouns ---
import anima.caps as caps
caps.enabled = lambda n, k: True
import anima.route as route
ok("route: real send extracts recipient+body",
   (route.route("Vera", "text Mom I'm running late") or {}).get("send", {}).get("to") == "Mom")
ok("route: noun 'message' does NOT fabricate a draft",
   not (route.route("Vera", "I got your message yesterday and it was great") or {}).get("send"))

# --- host apps (Calendar/Reminders/Notes): write intents + the CONFIRM-GATE ---
# Writes are dry-run here (executors monkeypatched) so this stays offline and creates
# nothing. The guarantee under test: a write request executes NOTHING until an explicit
# confirm on the NEXT turn — the host-app mirror of the message draft→confirm→send gate.
import anima.host_access as _ha
_host_writes = []
def _dry(action):
    def f(*a, **k):
        _host_writes.append(action)
        return {"ok": True, "title": (a[0] if a else k.get("title", "?"))}
    return f
for _n in ("create_reminder", "create_event", "create_note", "append_to_note", "complete_reminder"):
    setattr(_ha, _n, _dry(_n))
# the no_access shape is honest and structured (never a crash, never fake success)
_na = _ha._no_access("Reminders", "Reminders")
ok("host_access: no_access is structured + honest",
   _na["ok"] is False and _na["reason"] == "no_access" and "System Settings" in _na["message"])
ok("host: 'remind me to' parses a create_reminder",
   (route._parse_host_write("remind me to call the dentist tomorrow at 3pm") or {}).get("action") == "create_reminder")
ok("host: 'add … to my calendar' parses a create_event",
   (route._parse_host_write("add lunch with Sam to my calendar tomorrow at noon") or {}).get("action") == "create_event")
ok("host: 'make a note that' parses a create_note",
   (route._parse_host_write("make a note that I parked on level 3") or {}).get("action") == "create_note")
ok("host: 'mark … done' parses a complete_reminder",
   (route._parse_host_write("mark call the dentist as done") or {}).get("action") == "complete_reminder")
ok("host: mid-sentence noun does NOT fabricate a write",
   route._parse_host_write("I made a note of that yesterday") is None)
# confirm-gate: prepare must NOT write; only an explicit yes executes
route._pending_clear("HostVera")
_r1 = route.route("HostVera", "remind me to water the plants tomorrow at 9am")
ok("host: write request prepares a draft and writes NOTHING",
   len(_host_writes) == 0 and route._pending_get("HostVera") is not None and "DRAFT" in (_r1 or {}).get("note", ""))
_r2 = route.route("HostVera", "yes do it")
ok("host: explicit 'yes' EXECUTES the pending write exactly once",
   len(_host_writes) == 1 and _host_writes[0] == "create_reminder" and route._pending_get("HostVera") is None)
# decline path: a clear no cancels and writes nothing
_host_writes.clear()
route.route("HostVera", "add a coffee chat to my calendar tomorrow at 2pm")
_rd = route.route("HostVera", "no, cancel that")
ok("host: 'no' cancels the draft and writes NOTHING",
   len(_host_writes) == 0 and route._pending_get("HostVera") is None and "CANCEL" in (_rd or {}).get("note", "").upper())
# confirm/decline classification is tight and decline wins ties
ok("host: confirm tokens recognized incl. 'yes do it'",
   route._is_confirm("yes do it") and route._is_confirm("sure") and route._is_confirm("do it"))
ok("host: 'no, go ahead and cancel' is a DECLINE, never a confirm",
   route._is_decline("no, go ahead and cancel") and not route._is_confirm("no, go ahead and cancel"))
# the privacy guard pauses host reads on a cloud brain (contents are personal)
import anima.cloud as _cloud
_save_iscloud = _cloud.is_cloud
_cloud.is_cloud = lambda: True
try:
    _pc = route.route("HostVera", "what's on my calendar today?")
    ok("host: calendar read is PAUSED under a cloud brain (privacy guard)",
       "PAUSED" in (_pc or {}).get("note", ""))
finally:
    _cloud.is_cloud = _save_iscloud

# --- cloud: PII scrub + key never exposed ---
import anima.cloud as cloud
ok("cloud: scrub hides an email", "jane@x.com" not in cloud.scrub("mail jane@x.com please"))
ok("cloud: scrub is stable (coreference)", cloud.scrub("jane@x.com") == cloud.scrub("jane@x.com"))
ok("cloud: public() never exposes the api key", "key" not in cloud.public())

# --- cloud PII leak fix: the creature's KNOWN personal names never egress in HISTORY ---
# An audit proved that on a CLOUD brain, mouth.respond blanks the Portrait/LIRF from the
# system prompt (mem="") but passes the conversation HISTORY straight through, where
# cloud.scrub() only catches STRUCTURED PII — so person/relation names survived VERBATIM
# on BOTH sides (the user's turns AND Vera's OWN memory-derived replies, e.g. "how's
# Mara's move going?"). This locks the fix: those names — bounded to what the creature
# actually has on record — are tokenized out of every string before it leaves the Mac,
# while structured PII still scrubs and the LOCAL path keeps the memory it legitimately has.
import tempfile as _tf, pathlib as _pl, json as _cj
import anima.memory_lirf as _mlirf, anima.portrait as _cport
_cl_td = _tf.mkdtemp(prefix="cloud-pii-")          # SYNTHETIC creature + temp store; never Vera.*
_cl_save = (_mlirf.STORE, _cport.STORE, cloud.STORE)
_mlirf.STORE = _pl.Path(_cl_td); _cport.STORE = _pl.Path(_cl_td); cloud.STORE = _pl.Path(_cl_td)
try:
    _cn = "PiiSynth"
    _ff = _mlirf.Facts([])                          # seed the auditor's people as the creature's memory
    for _c in _ff.capture(_cn, "my sister is Mara"): _ff.merge(_c)
    for _c in _ff.capture(_cn, "I work at Collatio"): _ff.merge(_c)
    _ff.save(_cn)
    _cport.save(_cn, "- sister Mara recently moved to Denver\n- therapist Dr. Okonkwo\n- boss Raj at Collatio")

    _terms = cloud.name_terms(_cn)                  # bounded to names the creature KNOWS
    ok("cloud names: creature's relation/portrait names are gathered (Mara, Okonkwo, Raj, Collatio)",
       {"Mara", "Okonkwo", "Raj", "Collatio"}.issubset(_terms))
    ok("cloud names: bound stays the creature's OWN memory (no stop-word in the set)",
       all(len(t) >= 2 for t in _terms) and "the" not in {t.lower() for t in _terms})

    _USER = "My sister Mara moved to Denver, my therapist Dr. Okonkwo, my boss Raj at Collatio."
    _VERA = "how's Mara's move to Denver going? any word from Dr. Okonkwo? and Raj at Collatio?"
    _pat = cloud._name_pattern(_terms)
    _us, _vs = cloud.scrub_names(_USER, _pat), cloud.scrub_names(_VERA, _pat)
    for _nm in ("Mara", "Okonkwo", "Raj", "Collatio"):
        ok(f"cloud names: '{_nm}' tokenized out of the USER turn", _nm not in _us)
        ok(f"cloud names: '{_nm}' tokenized out of VERA's memory-derived reply", _nm not in _vs)
    ok("cloud names: coreference is stable (same token for Mara on both sides)",
       cloud.scrub_names("Mara", _pat) == cloud.scrub_names("mara", _pat))
    ok("cloud names: structured PII STILL scrubs alongside names (email + phone)",
       "a@b.co" not in cloud.scrub_all("mail a@b.co sister Mara at 415-555-2671", _pat)
       and "415-555-2671" not in cloud.scrub_all("a@b.co Mara 415-555-2671", _pat))

    # END-TO-END through the real brain.reply() egress: what actually hits the wire is clean.
    _cap = {}
    _br = cloud.OpenAICompatBrain("http://x", "m", "KEY", "openai:m", "openai")
    _br._post = lambda url, h, payload: (_cap.update(payload) or
                                         {"choices": [{"message": {"content": "ok"}}], "usage": {}})
    _br.creature = _cn                              # exactly what mouth.respond sets each turn
    _br.reply("You are PiiSynth.", "tell me about Dr. Okonkwo",
              [("My sister Mara moved to Denver", "how's Mara's move going? and Raj at Collatio?")])
    _wire = _cj.dumps(_cap.get("messages", []))
    ok("cloud names: END-TO-END reply() wire payload leaks NO known name verbatim",
       not any(_nm in _wire for _nm in ("Mara", "Okonkwo", "Raj", "Collatio")))
    ok("cloud isolation: reply()'s phantom add_spend writes the REDIRECTED store, not real .anima",
       cloud._spend_path() == _pl.Path(_cl_td) / "spend.json")

    # back-compat: no creature set -> structured-only scrub, exactly today's behaviour.
    _br2 = cloud.OpenAICompatBrain("http://x", "m", "KEY", "openai:m", "openai")
    ok("cloud names: brain with NO creature falls back to structured-only (back-compat)",
       _br2.creature is None and cloud.scrub_all("hi a@b.co", None) == cloud.scrub("hi a@b.co"))

    # the LOCAL path is untouched: local brains have no creature slot, so the mouth never
    # name-scrubs them — they legitimately hold the memory.
    import anima.mouth as _cmouth
    ok("cloud names: LOCAL brains have NO creature slot (mouth won't scrub them)",
       not hasattr(_cmouth.OllamaBrain(), "creature")
       and not hasattr(_cmouth.StubBrain(), "creature"))
finally:
    _mlirf.STORE, _cport.STORE, cloud.STORE = _cl_save
    import shutil as _csh
    _csh.rmtree(_cl_td, ignore_errors=True)

# --- passkey: session signing ---
import anima.passkey as pk
_s = pk.issue_session()
ok("passkey: a fresh session validates", pk.valid_session(_s))
ok("passkey: a tampered session is rejected", not pk.valid_session(_s[:-1] + ("0" if _s[-1] != "0" else "1")))

# --- eval scorer: honest passes, confabulation fails ---
from anima.eval import score
ok("eval: honest 'never heard of it' passes", bool(score("admit", "I've never heard of that book.", [])))
ok("eval: a confabulated chapter fails",
   not score("admit", "In the chapter Radical Humility, Dalio argues you must be humble.", []))
ok("eval: no-access answer passes capability scorer", bool(score("no_access", "I can't see your messages from here.", [])))

# --- dials (V2 personality contract): mapping is sane in both directions ---
import anima.dials as dials
ok("dials: defaults turn empathy down (warmth < 50)", dials.DEFAULT["warmth"] < 50)
ok("dials: a high edge dial speaks to the high-end directive",
   "sardonic" in dials.to_prompt({"edge": 90}))
ok("dials: a low warmth dial speaks to the low-end directive",
   "detached" in dials.to_prompt({"warmth": 5}))
ok("dials: neutral (50) axes stay silent", dials.to_prompt({k: 50 for k in dials._KEYS}) == "")
ok("dials: out-of-range values are clamped, never crash",
   dials._clamp(9999) == 100 and dials._clamp(-3) == 0 and dials._clamp("x") == 50)
ok("dials: honesty is NOT a dial (can't be turned down here)", "honesty" not in dials._KEYS)
# control-vector mapping: a max dial maps to +MAX_SCALE, a min dial to -MAX_SCALE
import anima.llamacpp as llamacpp
_cmd = llamacpp.launch_command_str("model.gguf", {"edge": 100})
ok("llamacpp: launch command targets llama-server", _cmd.startswith("llama-server"))
ok("dials->vectors: scale sign follows the dial (no vector files present -> empty)",
   dials.to_vectors({"edge": 100}, "/nonexistent") == [])

# --- forge (character LoRA): ingest dispatch, dataset, eval gate ---
import anima.forge as forge
ok("forge: detects a youtube source", forge.source_kind("https://youtu.be/abc12345678") == "youtube")
ok("forge: detects a file source", forge.source_kind("notes.md") == "file")
ok("forge: chunking overlaps and respects size", len(forge.chunk(" ".join(["w"] * 500), words=180, overlap=20)) >= 3)
import tempfile, json as _json
with tempfile.TemporaryDirectory() as _td:
    nt, nv = forge.build_dataset([" ".join(["voice"] * 600)], _td, allow_plaintext=True)
    _line = open(os.path.join(_td, "train.jsonl")).readline()
    ok("forge: dataset writes MLX {\"text\"} jsonl", "text" in _json.loads(_line) and nt > 0)
ok("forge: train command invokes mlx_lm.lora",
   forge.train_command("m", "d", "a")[0] == "mlx_lm.lora")
# the eval GATE protects honesty above all (rule #1)
_acc, _ = forge.gate({"honesty": 1.0, "persona": 0.5}, {"honesty": 0.8, "persona": 0.9})
ok("forge: gate REJECTS a voice that costs honesty", _acc is False)
_acc2, _ = forge.gate({"honesty": 1.0, "persona": 0.5}, {"honesty": 1.0, "persona": 0.7})
ok("forge: gate ACCEPTS when honesty holds and persona improves", _acc2 is True)

# --- identity (portable, 1000-year self): export/validate/migrate/round-trip ---
import anima.identity as identity
_pb = identity.export("st_probe")
ok("identity: export is a valid portable bundle", identity.validate(_pb)[0])
ok("identity: core is model-INDEPENDENT (dials + persona embedded)",
   "dials" in _pb["core"] and "persona" in _pb["core"])
ok("identity: artifacts are model-BOUND (referenced, with model_family)",
   "model_family" in _pb["artifacts"])
ok("identity: an old bundle migrates forward to current schema",
   identity.migrate({"kind": "anima.identity", "core": {}})["schema"] == identity.SCHEMA)
ok("identity: rejects a foreign file", not identity.validate({"kind": "nope"})[0])
dials.save("st_src", {"warmth": 7})                  # a distinctive setting
identity.import_bundle(identity.export("st_src"), "st_dst")
ok("identity: round-trip preserves a dial across export->import",
   dials.load("st_dst")["warmth"] == 7)
import glob as _glob
for _f in _glob.glob(".anima/st_src.*") + _glob.glob(".anima/st_dst.*") + _glob.glob(".anima/st_probe.*"):
    try: os.remove(_f)
    except OSError: pass

# --- the ANIMA LAW invariants run as their own subprocess tests, so the laws have
# TEETH in CI: a regression that silently breaks continuity (LAW 001), re-asks a fact the
# system already knows (LAW 002), or asserts significance the evidence doesn't support
# (LAW 003) fails THIS command — not a script someone forgot. ---
import subprocess as _sub
for _law, _script in (("LAW 001 — continuity", "test_continuity.py"),
                      ("LAW 002 — never make the same discovery twice", "test_curiosity.py"),
                      ("LAW 003 — understanding beats remembering", "test_meaning.py"),
                      ("LAW 001 — compression (life review)", "test_review.py"),
                      ("DREAM ENGINE — open loops", "test_loops.py"),
                      ("LAW 003 — trajectory (direction)", "test_trajectory.py"),
                      ("OPPORTUNITY ENGINE — proactive offers", "test_opportunity.py")):
    _p = os.path.join(os.path.dirname(os.path.abspath(__file__)), _script)
    _r = _sub.run([sys.executable, _p], capture_output=True, text=True)
    ok(f"{_law}: invariant test passes ({_script})", _r.returncode == 0)

print()
if _fails:
    print(f"{len(_fails)} FAILED: " + ", ".join(_fails))
    sys.exit(1)
print("ALL SELFTESTS PASS")

# Vera — complete new-Mac setup & restore guide

**Authoritative, stand-alone instructions to bring Vera up on a fresh Mac.** Made 2026-06-09.
Follow top to bottom. Everything you need is in the three backups listed below.

---

## 0. Where the backups are (3 copies)
| backup | holds | location |
|---|---|---|
| **Desktop migration kit** | your data, voice models, secrets, personality export, these docs | `~/Desktop/Vera-Migration-2026-06-09/` (copy this folder to the new Mac first — USB/AirDrop) |
| **LaCie** | a 2nd copy of these docs + the verification `reports/` | `/Volumes/LaCie/vera-verification-backup-2026-06-09/` |
| **GitHub (the code)** | the full source + history | `github.com/slmichaelj-beep/collatiolabs.com`, branch `claude/personality-engine-memory-y7SEW`, commit `81a2d8c` |

What's in the Desktop kit:
```
app-data/            memory (aletheia.db, integrity-checked clean snapshot), configs, voice_samples, sentinel, audit
voice-models/        kokoro / orpheus / whisper  (exact TTS+STT weights)
personality-export/  Vera.full-mind.json, Vera.mind.json, Vera.identity.json  (app's own portable export)
SECRETS/             api_keys.json, aletheia_token.txt, audible_auth.json, audible_vault.dat, avatar_passkeys.json, avatar_tokens.json
README.md / MANIFEST.txt / NEW-MAC-SETUP.md (this file)
```
**Not in the kit (rebuilt below):** the Python venv (~1.8 GB) and the Ollama LLM (~5.8 GB) — both re-create cleanly.

---

## 1. Copy the kit to the new Mac
AirDrop or USB the whole `Vera-Migration-2026-06-09/` folder to the new Mac (e.g. to its Desktop). The
`SECRETS/` folder holds live credentials — move it over an encrypted channel (AirDrop is fine) and don't email it.

## 2. Prerequisites (Homebrew + tools)
```bash
/bin/bash -c "$(curl -fsSL https://raw.githubusercontent.com/Homebrew/install/HEAD/install.sh)"
brew install python@3.12 ffmpeg git
brew install ollama
ollama serve &          # or: brew services start ollama
```

## 3. Get the code
```bash
git clone https://github.com/slmichaelj-beep/collatiolabs.com.git ~/collatiolabs-vera
cd ~/collatiolabs-vera
git checkout claude/personality-engine-memory-y7SEW    # commit 81a2d8c — the certified build
```

## 4. Python environment + dependencies
The data home (and the venv) live under `~/Library/Application Support/Guruu`.
```bash
DATA="$HOME/Library/Application Support/Guruu"
mkdir -p "$DATA"
python3.12 -m venv "$DATA/venv"
source "$DATA/venv/bin/activate"
pip install -U pip
pip install -r ~/collatiolabs-vera/requirements.txt
```

## 5. The LLM brain (Ollama)
```bash
ollama pull hf.co/bartowski/L3-8B-Stheno-v3.2-GGUF      # the model Vera runs on
```

## 6. Restore YOUR data, voice, and secrets
From inside the copied kit folder:
```bash
DATA="$HOME/Library/Application Support/Guruu"
cp -R app-data/*       "$DATA"/        # memory (aletheia.db), configs, voice_samples, sentinel, audit
cp -R voice-models/*   "$DATA"/        # kokoro / orpheus / whisper
cp -R SECRETS/*        "$DATA"/        # api keys, tokens, vault, passkeys
```
`aletheia.db` here is a clean `sqlite3 .backup` (integrity verified) — it is your memory.

## 7. Start Vera
```bash
cd ~/collatiolabs-vera
"$HOME/Library/Application Support/Guruu/venv/bin/python3" -m anima.server --name Vera --port 8765
```
Open **http://127.0.0.1:8765** .

## 8. Verify she's really her
- Ask: "what's my birthday?" → should answer **July 25, 1977** (from restored memory).
- Ask: "what do you know about me?" → should reflect your history.
- Open **/security** → top summary should read **0 active contamination**.
- Open **/verification** → the release-tier ladder renders.

---

## 9. (Optional) import the app's personality export
The data restore in step 6 already fully restores her. If you ever want to re-seed identity from the
portable bundle into a fresh creature instead:
```bash
curl -X POST http://127.0.0.1:8765/platform/import \
  -H "Content-Type: application/json" \
  -d "{\"bundle\": $(cat personality-export/Vera.full-mind.json)}"
```
(Import is freeze-safe: a Vera-self value/preference in the bundle is refused, never written.)

---

## 10. Troubleshooting
- **First message is slow (~15 s), then fast.** Normal: the model cold-loads into RAM on the first turn.
  It's warmed on startup and kept resident (`ANIMA_KEEP_ALIVE`, default `1h`). On a 24 GB Mac under memory
  pressure Vera deliberately unloads the model to avoid freezing the host — so under load, turns cold-load.
  Quieter host = warm + fast. (See `reports/performance_tuning.md` in the LaCie backup for the full analysis.)
- **`port 8765 is busy`** → `lsof -ti:8765 | xargs kill -9`, then start again.
- **Where is her data?** `~/Library/Application Support/Guruu/` — that's the data home the server reads/writes.
- **Voice not working?** Confirm `kokoro/`, `orpheus/`, `whisper/` landed in the data home (step 6).
- **Model name / override** → `ollama pull hf.co/bartowski/L3-8B-Stheno-v3.2-GGUF`; override with `ANIMA_MODEL`.

## 11. Key coordinates (quick reference)
```
repo      : github.com/slmichaelj-beep/collatiolabs.com
branch    : claude/personality-engine-memory-y7SEW   commit 81a2d8c
data home : ~/Library/Application Support/Guruu/
LLM       : hf.co/bartowski/L3-8B-Stheno-v3.2-GGUF  (via Ollama)
start     : "<DATA>/venv/bin/python3" -m anima.server --name Vera --port 8765
URL       : http://127.0.0.1:8765
```

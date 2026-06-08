# Balinese transcriber — Meta Omnilingual ASR

Uses **Meta's Omnilingual ASR** (released Nov 2025), which supports 1,600+
languages **including Balinese (`ban_Latn`)** — plus Indonesian (`ind_Latn`)
and English (`eng_Latn`). This is the newest/best-coverage option for Balinese.

It has its **own environment** (`.venv` here), separate from `../balinese/`,
because its fairseq2 backend needs a specific PyTorch version.

> **What to expect**
> - Omnilingual only accepts clips **under 40 seconds**, so this tool splits
>   your file into 30-second chunks automatically and stitches the result.
> - You pick **one language per run** (it's language-conditioned). For a mixed
>   recording, run it once as Balinese, and if parts are clearly Indonesian or
>   English, run those again with `ind_Latn` / `eng_Latn` and combine.
> - First run downloads the model (300M card ≈ 6 GB on disk). On a laptop CPU it's slow;
>   that's expected.

## Setup (once)

```sh
cd collatiolabs.com/omnilingual
./setup.sh
```

Installs `libsndfile` + `ffmpeg` (via Homebrew) and the `omnilingual-asr`
package into a local environment.

## Run — drop files in a folder (easiest)

**Double-click `Transcriber.command`** in Finder (or run `./Transcriber.command`).
It asks where you want PDFs saved, opens your **Inbox** folder, and watches it.

- Drop any audio/video file into `~/Transcribe/Inbox`.
- A **PDF** (and `.txt`) appears in the output folder you chose.
- Live progress shows in the window; finished files move to `~/Transcribe/Done`.
- It does **not** touch your sound settings.

> First file triggers a one-time model download (~6 GB) before progress starts.
> DRM-protected Audible `.aax` files can't be read — they're moved to
> `~/Transcribe/Skipped` with a short note explaining why.

## Record & transcribe (accessibility)

For reading content you own and can legally play but cannot hear, you can
record normal playback and transcribe it. This records the audio output — it
does **not** decrypt or unlock any protected file.

One-time setup:
1. `brew install blackhole-2ch`
2. **System Settings → Sound → Output → "BlackHole 2ch"** (audio now routes
   silently into the recorder).
3. Play the audiobook in the **Audible app**.

Then:
```sh
./record_and_transcribe.sh
```
Pick the BlackHole input, start playback, and stop with `q` when the book ends —
it transcribes automatically. Note: capture is real-time (a 5-hour book takes
5 hours), and ASR narration transcripts are rough compared to an ebook's text.

### Direct usage

```sh
source .venv/bin/activate
python transcribe_omni.py "/path/to/recording.m4a"                 # Balinese
python transcribe_omni.py "/path/to/recording.m4a" --lang ind_Latn # Indonesian
python transcribe_omni.py --list-langs                             # region codes
python transcribe_omni.py --list-models                            # model card names
python transcribe_omni.py "file.m4a" --model omniASR_LLM_1B        # bigger model
```

## Troubleshooting

- **Segfault / immediate crash:** fairseq2 doesn't match the installed torch.
  This is the most likely install snag on a new machine — send me the error.
- **`Library not loaded: libsndfile`:** run `brew install libsndfile`.
- **Too slow / out of memory:** stick with the default 300M model; avoid 7B
  (≈30 GB) on a laptop.

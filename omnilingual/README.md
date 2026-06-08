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
> - First run downloads the model (300M ≈ 1.3 GB). On a laptop CPU it's slow;
>   that's expected.

## Setup (once)

```sh
cd collatiolabs.com/omnilingual
./setup.sh
```

Installs `libsndfile` + `ffmpeg` (via Homebrew) and the `omnilingual-asr`
package into a local environment.

## Run

```sh
./run.sh
```

Drag your audio file in when asked, then choose the language (Enter = Balinese).
The transcript prints and is saved next to your audio as
`YOURFILE.omni_ban_Latn.txt`.

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

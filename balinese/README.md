# Balinese / Indonesian / English transcriber (local)

Whisper (the browser tool in `../transcribe/`) does **not** know Balinese.
This tool does. It runs **Meta's MMS** model (`facebook/mms-1b-all`), which
supports 1,100+ languages including **Balinese (`ban`)**, **Indonesian
(`ind`)**, and **English (`eng`)**.

Because the recording is a mix, the default **"mix" mode** transcribes each
~20-second chunk in all three languages and keeps whichever the model is most
confident about — so you get one transcript that follows the speaker as they
switch languages, plus a full separate pass for each language.

> **Honest expectations**
> - MMS output is **lowercase with no punctuation** — it's a transcript, not
>   polished prose. (You can paste it into any chat assistant afterward to add
>   punctuation/clean it up.)
> - These models were trained mostly on **clear, read speech**. On a real
>   recording with music, laughter, and overlapping voices, accuracy will be
>   rougher — the Balinese stretches especially. This is the best available
>   today, but it won't be perfect.
> - First run **downloads PyTorch (~hundreds of MB) and the model (~3.8 GB)**,
>   cached afterward. Transcribing on a laptop CPU is slowish; that's normal.

## Setup (once)

From this folder, in Terminal:

```sh
cd collatiolabs.com/balinese
./setup.sh
```

This installs a private Python environment, the model libraries, and (via
Homebrew) **ffmpeg**, which is required to read `.m4a` and most audio formats.
If you don't have Homebrew, the script tells you the one line to install it.

## Run

```sh
./run.sh
```

It asks for your audio file (you can **drag the file from Finder into the
Terminal window** to fill in the path) and which language mode to use. Press
Enter to accept "Mix". When it finishes, the transcript prints in the window
and is also saved next to your audio file as `YOURFILE.transcript.txt`.

### Or run it directly

```sh
source .venv/bin/activate
python transcribe_bali.py "/path/to/recording.m4a"          # mix mode
python transcribe_bali.py "/path/to/recording.m4a" --lang ind   # Indonesian only
python transcribe_bali.py --list-langs                       # what languages exist
```

## If Balinese quality isn't good enough

The newer **Meta Omnilingual ASR** (released Nov 2025, 1,600+ languages) may do
better on Balinese but is heavier to install. There's also a free hosted
**Hugging Face demo** for both MMS and Omnilingual where you can upload a clip
and pick Balinese with no install — a good way to sanity-check before investing
more. Ask and I'll wire up the Omnilingual route.

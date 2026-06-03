# Audio Transcription — running locally

This tool transcribes audio entirely in your browser (Whisper via
transformers.js). Your audio never leaves your computer.

> **Why a server?** The tool uses an ES-module web worker, which browsers
> refuse to load from `file://`. So you can't just double-click
> `index.html` — you serve the folder over `http://` with one command.

## Run it (macOS / Linux)

1. Get the files onto your machine (once):

   ```sh
   git clone https://github.com/slmichaelj-beep/collatiolabs.com.git
   cd collatiolabs.com
   git checkout claude/audio-transcription-tool-qCUB3
   ```

   (Already cloned? Just `git fetch origin` then
   `git checkout claude/audio-transcription-tool-qCUB3 && git pull`.)

2. Start a local web server from the repo root:

   ```sh
   python3 -m http.server 8000
   ```

   (No Python? With Node installed: `npx serve -l 8000`.)

3. Open this in **Chrome or Edge** (best WebGPU support):

   ```
   http://localhost:8000/transcribe/
   ```

4. Drag your audio file in. Stop the server later with `Ctrl+C`.

## Run it (Windows)

Same as above, but in PowerShell use `py -m http.server 8000` (or
`python -m http.server 8000`), then open the localhost URL in Chrome/Edge.

## Suggested settings for a Bali recording

- **Language:** `Indonesian` (or `Auto-detect` if unsure). True Basa Bali
  isn't supported by the model and will be unreliable.
- **Model:** `Small` or `Large-v3 Turbo` for decent non-English accuracy.
  Turbo is best but downloads ~800 MB once and wants a GPU.
- **Task:** `Transcribe` for the original language, or `Translate` to get
  English out.

The first run downloads the model into your browser cache (one-time);
after that it works offline.

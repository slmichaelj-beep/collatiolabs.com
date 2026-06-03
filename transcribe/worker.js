// Transcription worker — runs Whisper entirely in the browser via transformers.js.
// Audio never leaves the user's machine. No server, no API keys.

import {
  pipeline,
  WhisperTextStreamer,
  env,
} from "https://cdn.jsdelivr.net/npm/@huggingface/transformers@3";

// Pull models from the Hugging Face hub (cached by the browser after first load).
env.allowLocalModels = false;

let transcriber = null;
let loadedKey = null;

async function getTranscriber(model, device) {
  const key = `${model}|${device}`;
  if (transcriber && loadedKey === key) return transcriber;

  transcriber = await pipeline("automatic-speech-recognition", model, {
    device,
    // WebGPU likes full-precision encoder + fp16 decoder; CPU/WASM uses a
    // quantized decoder to keep the download small and inference tolerable.
    dtype:
      device === "webgpu"
        ? { encoder_model: "fp32", decoder_model_merged: "fp16" }
        : { encoder_model: "fp32", decoder_model_merged: "q8" },
    progress_callback: (p) => self.postMessage({ type: "progress", data: p }),
  });
  loadedKey = key;
  return transcriber;
}

self.addEventListener("message", async (e) => {
  const { audio, model, language, task } = e.data;

  try {
    // Prefer the GPU when the browser exposes WebGPU; otherwise fall back to CPU.
    let device = "wasm";
    if (typeof navigator !== "undefined" && navigator.gpu) {
      device = "webgpu";
    }

    let t;
    try {
      t = await getTranscriber(model, device);
    } catch (err) {
      if (device === "webgpu") {
        self.postMessage({
          type: "status",
          data: "WebGPU unavailable — switching to CPU (slower).",
        });
        device = "wasm";
        t = await getTranscriber(model, device);
      } else {
        throw err;
      }
    }

    self.postMessage({ type: "status", data: "transcribing", device });

    const time_precision =
      t.processor.feature_extractor.config.chunk_length /
      t.model.config.max_source_positions;

    // Stream partial text so the user sees progress on long files.
    const chunks = [];
    const streamer = new WhisperTextStreamer(t.tokenizer, {
      time_precision,
      on_chunk_start: (x) => {
        chunks.push({ text: "", offset: x });
      },
      callback_function: (x) => {
        if (chunks.length === 0) chunks.push({ text: "", offset: 0 });
        chunks[chunks.length - 1].text += x;
        self.postMessage({
          type: "update",
          data: chunks.map((c) => c.text).join(""),
        });
      },
    });

    const output = await t(audio, {
      top_k: 0,
      do_sample: false,
      chunk_length_s: 30,
      stride_length_s: 5,
      language: language === "auto" ? null : language,
      task,
      return_timestamps: true,
      force_full_sequences: false,
      streamer,
    });

    self.postMessage({ type: "complete", data: output });
  } catch (err) {
    self.postMessage({
      type: "error",
      data: String((err && err.message) || err),
    });
  }
});

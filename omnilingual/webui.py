#!/usr/bin/env python3
"""
Local drag-and-drop web UI for the Omnilingual ASR transcriber.

Drop audio/video files in the browser, choose a language and an output folder,
and watch per-file progress. Files are transcribed one at a time (the model is
big) and the resulting .txt is written to the folder you choose.

Run it with ./run-ui.sh  (which installs Flask if needed and opens your browser).
"""

import os
import sys
import uuid
import queue
import shutil
import tempfile
import threading
import subprocess

from flask import Flask, request, jsonify

# Reuse the engine helpers from the CLI tool (importing it does NOT load torch).
from transcribe_omni import split_audio, as_text, fmt_ts, DEFAULT_MODEL

CHUNK_SEC = 30.0
BATCH = 4
PORT = 5005
DEFAULT_OUTDIR = os.path.expanduser("~/Transcripts")
LANG_LABELS = {"eng_Latn": "English", "ind_Latn": "Indonesian", "ban_Latn": "Balinese"}

app = Flask(__name__)

jobs = {}                      # job_id -> dict
jobs_lock = threading.Lock()
work_q = queue.Queue()

_pipeline = None
_pipeline_lock = threading.Lock()
model_state = {"state": "idle"}   # idle | loading | ready | error


def job_set(job_id, **kw):
    with jobs_lock:
        if job_id in jobs:
            jobs[job_id].update(kw)


def get_pipeline():
    """Load the ASR model once, lazily (first job triggers the big download)."""
    global _pipeline
    with _pipeline_lock:
        if _pipeline is None:
            model_state["state"] = "loading"
            try:
                from omnilingual_asr.models.inference.pipeline import ASRInferencePipeline
                _pipeline = ASRInferencePipeline(model_card=DEFAULT_MODEL)
                model_state["state"] = "ready"
            except Exception:
                model_state["state"] = "error"
                raise
        return _pipeline


def run_job(job_id):
    with jobs_lock:
        job = dict(jobs.get(job_id, {}))
    if not job:
        return

    job_set(job_id, status="loading model", progress=1)
    try:
        pipeline = get_pipeline()
    except Exception as e:
        job_set(job_id, status="error", error=f"Model failed to load: {e}")
        return

    tmp = tempfile.mkdtemp(prefix="omniui_")
    try:
        job_set(job_id, status="splitting audio", progress=3)
        try:
            chunks = split_audio(job["input_path"], CHUNK_SEC, tmp)
        except SystemExit as e:
            msg = str(e)
            if job["name"].lower().endswith(".aax"):
                msg = "This is a DRM-protected Audible (.aax) file and cannot be read."
            job_set(job_id, status="error", error=msg)
            return

        total = len(chunks)
        if total == 0:
            job_set(job_id, status="error", error="No audio found in file.")
            return

        job_set(job_id, status="transcribing", total=total, done=0, progress=5)
        texts = []
        lang = job["lang"]
        for i in range(0, total, BATCH):
            part = chunks[i:i + BATCH]
            res = pipeline.transcribe(part, lang=[lang] * len(part), batch_size=len(part))
            texts.extend(as_text(r) for r in res)
            done = min(i + BATCH, total)
            job_set(job_id, done=done, progress=int(5 + 90 * done / total))

        outdir = os.path.expanduser(job["outdir"])
        os.makedirs(outdir, exist_ok=True)
        base = os.path.splitext(os.path.basename(job["name"]))[0]
        out_path = os.path.join(outdir, f"{base}.{lang}.txt")
        lines = [f"[{fmt_ts(idx * CHUNK_SEC)}] {t}" for idx, t in enumerate(texts) if t.strip()]
        with open(out_path, "w", encoding="utf-8") as f:
            f.write(f"=== {LANG_LABELS.get(lang, lang)} — Omnilingual ASR ===\n\n")
            f.write("\n".join(lines) + "\n\n=== FULL TEXT ===\n\n")
            f.write(" ".join(t.strip() for t in texts if t.strip()) + "\n")

        job_set(job_id, status="done", progress=100, output=out_path,
                preview="\n".join(lines[:6]) or "(no speech recognized)")
    except Exception as e:
        job_set(job_id, status="error", error=str(e))
    finally:
        shutil.rmtree(tmp, ignore_errors=True)
        try:
            os.remove(job["input_path"])
        except OSError:
            pass


def worker():
    while True:
        job_id = work_q.get()
        try:
            run_job(job_id)
        finally:
            work_q.task_done()


@app.route("/")
def index():
    return PAGE


@app.route("/upload", methods=["POST"])
def upload():
    lang = request.form.get("lang", "eng_Latn")
    outdir = request.form.get("outdir") or DEFAULT_OUTDIR
    files = request.files.getlist("files")
    up_dir = os.path.join(tempfile.gettempdir(), "omniui_uploads")
    os.makedirs(up_dir, exist_ok=True)
    created = []
    for f in files:
        if not f.filename:
            continue
        job_id = uuid.uuid4().hex[:8]
        dest = os.path.join(up_dir, f"{job_id}_{os.path.basename(f.filename)}")
        f.save(dest)
        with jobs_lock:
            jobs[job_id] = {
                "id": job_id, "name": f.filename, "input_path": dest,
                "lang": lang, "outdir": outdir, "status": "queued",
                "progress": 0, "total": 0, "done": 0,
                "output": None, "error": None, "preview": None,
            }
        work_q.put(job_id)
        created.append(job_id)
    return jsonify({"jobs": created})


@app.route("/status")
def status():
    with jobs_lock:
        data = [{k: v for k, v in j.items() if k != "input_path"} for j in jobs.values()]
    data.sort(key=lambda j: j["id"])
    return jsonify({"model": model_state["state"], "jobs": data})


@app.route("/reveal")
def reveal():
    jid = request.args.get("job", "")
    with jobs_lock:
        j = jobs.get(jid)
    if j and j.get("output") and os.path.exists(j["output"]):
        subprocess.run(["open", "-R", j["output"]], check=False)
        return ("", 204)
    return ("not found", 404)


@app.route("/clear", methods=["POST"])
def clear():
    with jobs_lock:
        for jid in [j["id"] for j in jobs.values() if j["status"] in ("done", "error")]:
            jobs.pop(jid, None)
    return ("", 204)


PAGE = """<!doctype html>
<html><head><meta charset="utf-8"><title>Transcriber</title>
<meta name="viewport" content="width=device-width, initial-scale=1">
<style>
  :root { color-scheme: dark; }
  body { font-family: -apple-system, system-ui, sans-serif; background:#0e1014; color:#e7e9ee;
         margin:0; padding:24px; }
  .wrap { max-width:760px; margin:0 auto; }
  h1 { font-size:20px; font-weight:600; margin:0 0 4px; }
  .sub { color:#8b919e; font-size:13px; margin-bottom:18px; }
  .row { display:flex; gap:12px; flex-wrap:wrap; align-items:flex-end; margin-bottom:16px; }
  label { display:block; font-size:12px; color:#8b919e; margin-bottom:4px; }
  select, input[type=text] { background:#1a1d24; border:1px solid #2a2f3a; color:#e7e9ee;
         border-radius:8px; padding:9px 11px; font-size:14px; }
  input[type=text] { width:360px; }
  #drop { border:2px dashed #2e3440; border-radius:14px; padding:42px 20px; text-align:center;
          color:#9aa1ae; cursor:pointer; transition:.15s; background:#12151b; }
  #drop.hot { border-color:#5b8cff; background:#161b27; color:#cdd6f4; }
  #drop b { color:#cdd6f4; }
  .banner { font-size:13px; padding:9px 12px; border-radius:8px; margin-bottom:14px; display:none; }
  .banner.show { display:block; }
  .b-load { background:#2a2410; color:#f4d58d; border:1px solid #5c4d1a; }
  .b-ready{ background:#10261a; color:#86e0a8; border:1px solid #1d5234; }
  .b-err  { background:#2a1314; color:#f0a0a0; border:1px solid #5c2326; }
  .job { background:#12151b; border:1px solid #20242e; border-radius:10px; padding:12px 14px; margin-top:10px; }
  .job .top { display:flex; justify-content:space-between; gap:10px; font-size:14px; }
  .job .nm { font-weight:500; word-break:break-all; }
  .job .st { color:#8b919e; font-size:12px; white-space:nowrap; }
  .bar { height:7px; background:#20242e; border-radius:4px; margin-top:9px; overflow:hidden; }
  .bar > i { display:block; height:100%; width:0; background:#5b8cff; transition:width .3s; }
  .bar.done > i { background:#3fbf72; } .bar.err > i { background:#e05b5b; }
  .meta { font-size:12px; color:#8b919e; margin-top:8px; display:flex; gap:12px; align-items:center; flex-wrap:wrap; }
  .pre { font-size:12px; color:#aab; background:#0c0e13; border-radius:7px; padding:8px 10px;
         margin-top:8px; white-space:pre-wrap; max-height:120px; overflow:auto; }
  button.link { background:none; border:none; color:#5b8cff; cursor:pointer; font-size:12px; padding:0; }
  .err { color:#f0a0a0; }
  #clear { float:right; }
</style></head>
<body><div class="wrap">
  <h1>Audio &amp; Video Transcriber</h1>
  <div class="sub">Drop files below. They're transcribed locally on this Mac and saved as .txt.
     DRM-protected Audible (.aax) files won't work.</div>

  <div id="banner" class="banner"></div>

  <div class="row">
    <div><label>Language</label>
      <select id="lang">
        <option value="eng_Latn" selected>English</option>
        <option value="ind_Latn">Indonesian</option>
        <option value="ban_Latn">Balinese</option>
      </select></div>
    <div style="flex:1"><label>Save transcripts to</label>
      <input id="outdir" type="text" value="__OUTDIR__" style="width:100%"></div>
  </div>

  <div id="drop">Drag audio/video files here, or <b>click to choose</b>
    <input id="file" type="file" multiple style="display:none"></div>

  <div style="margin-top:14px"><button id="clear" class="link">clear finished</button></div>
  <div id="jobs"></div>
</div>
<script>
const drop=document.getElementById('drop'), fi=document.getElementById('file');
drop.onclick=()=>fi.click();
fi.onchange=()=>{ if(fi.files.length) send(fi.files); fi.value=''; };
['dragover','dragenter'].forEach(e=>drop.addEventListener(e,ev=>{ev.preventDefault();drop.classList.add('hot');}));
['dragleave','drop'].forEach(e=>drop.addEventListener(e,ev=>{ev.preventDefault();drop.classList.remove('hot');}));
drop.addEventListener('drop',ev=>{ if(ev.dataTransfer.files.length) send(ev.dataTransfer.files); });

function send(files){
  const fd=new FormData();
  fd.append('lang',document.getElementById('lang').value);
  fd.append('outdir',document.getElementById('outdir').value);
  for(const f of files) fd.append('files',f);
  fetch('/upload',{method:'POST',body:fd}).then(()=>poll());
}
document.getElementById('clear').onclick=()=>fetch('/clear',{method:'POST'}).then(poll);

function banner(state){
  const b=document.getElementById('banner');
  if(state==='loading'){b.className='banner show b-load';b.textContent='Loading the speech model… first time downloads ~1.3 GB, please wait.';}
  else if(state==='error'){b.className='banner show b-err';b.textContent='The speech model failed to load. Check the terminal.';}
  else b.className='banner';
}
function esc(s){return (s||'').replace(/[&<>]/g,c=>({'&':'&amp;','<':'&lt;','>':'&gt;'}[c]));}

function render(d){
  banner(d.model);
  const box=document.getElementById('jobs');
  box.innerHTML = d.jobs.map(j=>{
    const done=j.status==='done', err=j.status==='error';
    const cls='bar'+(done?' done':'')+(err?' err':'');
    let right = done ? '100%' : err ? 'failed'
        : j.total ? (j.status+' '+j.done+'/'+j.total) : j.status;
    let meta='';
    if(done) meta=`<div class="meta"><span>Saved: ${esc(j.output)}</span>`+
       `<button class="link" onclick="fetch('/reveal?job=${j.id}')">Open in Finder</button></div>`+
       (j.preview?`<div class="pre">${esc(j.preview)}</div>`:'');
    if(err) meta=`<div class="meta err">${esc(j.error)}</div>`;
    return `<div class="job"><div class="top"><span class="nm">${esc(j.name)}</span>`+
      `<span class="st">${esc(right)}</span></div>`+
      `<div class="${cls}"><i style="width:${j.progress}%"></i></div>${meta}</div>`;
  }).join('');
}
let timer=null;
function poll(){ fetch('/status').then(r=>r.json()).then(d=>{
  render(d);
  const busy=d.jobs.some(j=>j.status!=='done'&&j.status!=='error');
  clearTimeout(timer); if(busy||d.model==='loading') timer=setTimeout(poll,1000);
}); }
poll();
</script></body></html>"""


def main():
    os.makedirs(DEFAULT_OUTDIR, exist_ok=True)
    threading.Thread(target=worker, daemon=True).start()
    url = f"http://127.0.0.1:{PORT}"
    print(f"\n  Transcriber UI running at:  {url}")
    print("  (Leave this window open. Press Ctrl-C to stop.)\n")
    app.run(host="127.0.0.1", port=PORT, threaded=True)


# Bake the default output dir into the page once at import time.
PAGE = PAGE.replace("__OUTDIR__", DEFAULT_OUTDIR)

if __name__ == "__main__":
    main()

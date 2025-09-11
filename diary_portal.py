#!/usr/bin/env python3
# Robot Diary portal (Flask + Ollama)
# - Receives posts from the Pi: /api/post  (multipart: title, text, image)
# - Captions images with LLaVA:7B
# - “Ask (20B)” and “Create travel diary (20B)” run gpt-oss:20b
# - New Journey button to archive & reset timeline
# - Uses only the last DIARY_WINDOW snippets for 20B (prevents huge prompts)

import os, io, time, json, base64, threading, glob
from pathlib import Path
from datetime import datetime
from typing import List, Dict, Optional

import cv2
import numpy as np
import requests
from flask import (
    Flask, request, jsonify, send_from_directory, render_template_string
)

# ---------------------- configuration ----------------------

HOST        = os.environ.get("HOST", "0.0.0.0")
PORT        = int(os.environ.get("PORT", "5055"))

# Data dirs
DATA_DIR    = Path(os.environ.get("DATA_DIR", str(Path.home() / "documents" / "diary_data")))
IMG_DIR     = Path(os.environ.get("IMG_DIR", str(DATA_DIR / "img")))
DATA_DIR.mkdir(parents=True, exist_ok=True)
IMG_DIR.mkdir(parents=True, exist_ok=True)

# Ollama
OLLAMA_URL      = os.environ.get("OLLAMA_URL", "http://127.0.0.1:11434")
VISION_MODEL    = os.environ.get("VISION_MODEL", "llava:7b")
REASON_MODEL    = os.environ.get("REASON_MODEL", "gpt-oss:20b")

# Limits & behavior
TIMELINE_MAX    = int(os.environ.get("TIMELINE_MAX", "400"))     # in-memory entries
IMG_KEEP        = int(os.environ.get("IMG_KEEP",    "300"))      # number of images to retain
DIARY_WINDOW    = int(os.environ.get("DIARY_WINDOW","40"))       # how many recent events 20B can see
CAPTION_MAX_W   = int(os.environ.get("CAPTION_MAX_W", "640"))    # resize width for LLaVA
CAPTION_TIMEOUT = int(os.environ.get("CAPTION_TIMEOUT", "60"))   # seconds
DIARY_TIMEOUT   = int(os.environ.get("DIARY_TIMEOUT", "120"))    # seconds
ROTATE_180      = os.environ.get("ROTATE_180", "1") == "1"       # rotate saved images

# ---------------------- state ----------------------

app = Flask(__name__)
TIMELINE: List[Dict] = []         # newest last
JOURNEY_ID = 1
LOCK = threading.Lock()

# ---------------------- utils ----------------------

def ts_iso() -> str:
    return datetime.utcnow().isoformat(timespec="seconds") + "Z"

def save_img(file_storage) -> str:
    """Save uploaded image to IMG_DIR, optional rotate, return filename."""
    raw = file_storage.read()
    img_arr = np.frombuffer(raw, np.uint8)
    img = cv2.imdecode(img_arr, cv2.IMREAD_COLOR)
    if img is None:
        # save raw if decode fails
        fn = f"img_{datetime.utcnow().strftime('%Y%m%d_%H%M%S')}_{int(time.time()*1000)%1000:03d}.jpg"
        (IMG_DIR / fn).write_bytes(raw)
        return fn

    if ROTATE_180:
        img = cv2.rotate(img, cv2.ROTATE_180)

    # downscale for storage to keep page snappy (don’t exceed 1920px width)
    if img.shape[1] > 1920:
        scale = 1920.0 / img.shape[1]
        nh = max(1, int(round(img.shape[0]*scale)))
        img = cv2.resize(img, (1920, nh), interpolation=cv2.INTER_AREA)

    fn = f"img_{datetime.utcnow().strftime('%Y%m%d_%H%M%S')}_{int(time.time()*1000)%1000:03d}.jpg"
    cv2.imencode(".jpg", img, [cv2.IMWRITE_JPEG_QUALITY, 90])[1].tofile(str(IMG_DIR / fn))
    return fn

def base64_from_path(path: Path, max_w: int) -> str:
    """Read image, optionally resize for LLaVA, return base64."""
    img = cv2.imread(str(path))
    if img is None:
        return ""
    if max_w and img.shape[1] > max_w:
        scale = max_w / float(img.shape[1])
        nh = max(1, int(round(img.shape[0]*scale)))
        img = cv2.resize(img, (max_w, nh), interpolation=cv2.INTER_AREA)
    ok, buf = cv2.imencode(".jpg", img, [cv2.IMWRITE_JPEG_QUALITY, 90])
    if not ok:
        return ""
    return base64.b64encode(buf.tobytes()).decode("ascii")

def ollama_generate(model: str, prompt: str, images_b64: Optional[List[str]] = None,
                    timeout: int = 60) -> str:
    payload = {"model": model, "prompt": prompt, "stream": False}
    if images_b64:
        payload["images"] = images_b64
    r = requests.post(f"{OLLAMA_URL}/api/generate", json=payload, timeout=timeout)
    r.raise_for_status()
    return (r.json().get("response") or "").strip()

def caption_two_line(img_path: Path) -> str:
    """Fast, bounded caption for timeline."""
    b64 = base64_from_path(img_path, CAPTION_MAX_W)
    if not b64:
        return "(no image)"
    prompt = (
        "You are a concise scene captioner for a robot diary.\n"
        "Output exactly two short lines:\n"
        "1) A compact caption (<= 14 words).\n"
        "2) Key objects with rough position (left/center/right; near/far), comma-separated.\n"
        "No speculation, no extra lines."
    )
    return ollama_generate(VISION_MODEL, prompt, [b64], timeout=CAPTION_TIMEOUT)

def retain_images():
    imgs = sorted(IMG_DIR.glob("img_*.jpg"))
    if len(imgs) <= IMG_KEEP:
        return
    for p in imgs[:-IMG_KEEP]:
        try: p.unlink()
        except: pass

def tail_snippets(n: int) -> List[Dict]:
    """Prepare compact snippets for 20B (timestamps, titles, captions, risk, etc.)."""
    with LOCK:
        items = TIMELINE[-n:]
    out = []
    for it in items:
        out.append({
            "ts": it.get("ts", 0),
            "title": it.get("title",""),
            "state": it.get("state",""),
            "risk": it.get("risk", 0.0),
            "caption": it.get("caption",""),
            "text": it.get("text","")[:240],
        })
    return out

def archive_timeline():
    ts = datetime.utcnow().strftime("%Y%m%d_%H%M%S")
    path = DATA_DIR / f"journey_{ts}.json"
    with LOCK:
        data = {
            "archived_at": ts_iso(),
            "journey_id": JOURNEY_ID,
            "entries": TIMELINE
        }
    path.write_text(json.dumps(data, indent=2))
    return path

# ---------------------- web UI ----------------------

HTML = """
<!doctype html>
<title>Robot Diary (local)</title>
<link rel="preconnect" href="https://fonts.gstatic.com" crossorigin>
<style>
  :root{color-scheme:dark light}
  body{font-family:system-ui,Segoe UI,Arial;margin:20px}
  h1{margin:0 0 4px}
  .sub{color:#9aa0a6;font-size:12px;margin-bottom:14px}
  .row{display:flex;gap:10px;align-items:center}
  textarea{width:100%;height:70px;border-radius:10px;padding:10px}
  button{border:0;border-radius:12px;padding:10px 14px;cursor:pointer}
  .btn{background:#0ea5e9;color:white}
  .btn2{background:#10b981;color:white}
  .btn3{background:#ef4444;color:white}
  .card{border:1px solid #2f2f2f;border-radius:16px;padding:14px;margin:14px 0}
  .meta{color:#9aa0a6;font-size:12px;margin-bottom:6px}
  .flex{display:flex;gap:14px}
  img{max-width:420px;border-radius:12px;border:1px solid #2f2f2f}
  details{margin-top:6px}
  .tag{display:inline-block;background:#1f2937;color:#e5e7eb;border-radius:999px;padding:2px 8px;font-size:11px;margin-left:8px}
</style>

<h1>Robot Diary (local)</h1>
<div class="sub">Powered by LLaVA:7B (images) + gpt-oss:20b (reasoning). v0.5g (windowed + journey reset).</div>

<div class="row" style="margin-bottom:10px">
  <textarea id="note" placeholder="Optional note to weave into the travel diary (e.g., weather, place names, ETA)…"></textarea>
  <div style="display:flex;flex-direction:column;gap:8px">
    <button class="btn2" onclick="travel()">Create travel diary (20B)</button>
    <button class="btn"  onclick="ask20()">Ask (20B)</button>
    <button class="btn3" onclick="resetJourney()">New Journey</button>
  </div>
</div>
<div id="banner" class="sub"></div>

<div id="list"></div>

<script>
async function load(){
  const r = await fetch('/timeline?limit=120');
  const items = await r.json();
  const list = document.getElementById('list');
  list.innerHTML = '';
  for (const it of items){
    const card = document.createElement('div');
    card.className = 'card';
    const img = it.img ? `<img src="${it.img}">` : '';
    const risk = it.risk?.toFixed?.(1) ?? 0;
    const state = it.state || '';
    card.innerHTML = `
      <div class="meta">${new Date(it.ts*1000).toLocaleString()} — risk: ${risk}
        ${it.tag ? `<span class="tag">${it.tag}</span>`:''}
      </div>
      <div class="flex">
        <div>${img}</div>
        <div style="flex:1">
          <div><b>${it.title||'update'}</b><span class="tag">${state||''}</span></div>
          <div>${(it.caption||it.text||'').replaceAll('\\n','<br>')}</div>
          <details><summary>details</summary><pre>${JSON.stringify(it,null,2)}</pre></details>
        </div>
      </div>
    `;
    list.appendChild(card);
  }
}
async function travel(){
  const note = document.getElementById('note').value || '';
  document.getElementById('banner').textContent = 'Asking 20B…';
  try{
    const r = await fetch('/api/travel', {method:'POST', headers:{'Content-Type':'application/json'}, body: JSON.stringify({note})});
    const j = await r.json();
    document.getElementById('banner').textContent = j.error ? j.error : 'Travel diary added.';
    load();
  }catch(e){ document.getElementById('banner').textContent = String(e); }
}
async function ask20(){
  const note = document.getElementById('note').value || '';
  document.getElementById('banner').textContent = 'Asking 20B…';
  try{
    const r = await fetch('/api/ask', {method:'POST', headers:{'Content-Type':'application/json'}, body: JSON.stringify({q: note||'Summarize the latest events succinctly.'})});
    const j = await r.json();
    document.getElementById('banner').textContent = j.answer || '(no answer)';
  }catch(e){ document.getElementById('banner').textContent = String(e); }
}
async function resetJourney(){
  if(!confirm('Start a New Journey? This will archive and clear the timeline.')) return;
  document.getElementById('banner').textContent = 'Resetting…';
  try{
    const r = await fetch('/api/new_journey', {method:'POST'});
    const j = await r.json();
    document.getElementById('banner').textContent = j.ok ? 'New Journey started.' : (j.error || 'Error');
    load();
  }catch(e){ document.getElementById('banner').textContent = String(e); }
}
setInterval(load, 5000);
load();
</script>
"""

# ---------------------- routes ----------------------

@app.route("/")
def home():
    return render_template_string(HTML)

@app.route("/img/<path:fn>")
def serve_img(fn):
    return send_from_directory(str(IMG_DIR), fn)

@app.route("/timeline")
def timeline():
    limit = int(request.args.get("limit", "80"))
    with LOCK:
        tail = TIMELINE[-limit:]
    # newest first for UI
    return jsonify(list(reversed(tail)))

@app.route("/api/post", methods=["POST"])
def api_post():
    """Pi POSTs: title, text, image(file) optional; extra/meta optional."""
    title = request.form.get("title", "update")
    text  = request.form.get("text", "")
    meta  = request.form.get("meta", "")
    reason= request.form.get("reason","")
    tag   = reason if reason else ""
    ts    = int(time.time())

    img_url = None
    caption = None
    if "image" in request.files:
        fn = save_img(request.files["image"])
        img_url = f"/img/{fn}"
        # fast caption (background-friendly)
        try:
            caption = caption_two_line(IMG_DIR / fn)
        except Exception as e:
            caption = f"(caption error) {e}"

        # trim images on disk
        threading.Thread(target=retain_images, daemon=True).start()

    entry = {
        "ts": ts, "title": title, "text": text, "img": img_url,
        "caption": caption or "",
        "risk": 0.0, "state": "idle", "tag": tag,
    }
    with LOCK:
        TIMELINE.append(entry)
        if len(TIMELINE) > TIMELINE_MAX:
            del TIMELINE[:-TIMELINE_MAX]
    return jsonify({"ok": True})

@app.route("/api/travel", methods=["POST"])
def api_travel():
    """Make a travel diary entry using last DIARY_WINDOW snippets."""
    note = (request.get_json(silent=True) or {}).get("note","").strip()
    snippets = tail_snippets(DIARY_WINDOW)
    prompt = f"""You are a concise travel-diary writer (first-person, warm, factual).
Use ONLY this context (newest last):
{json.dumps(snippets, ensure_ascii=False)}

Optional note from user: {note or "(none)"}

Write one short paragraph (4–6 sentences). No bullet points. No speculation.
"""
    try:
        resp = ollama_generate(REASON_MODEL, prompt, timeout=DIARY_TIMEOUT)
    except Exception as e:
        return jsonify({"error": f"(gpt-oss:20b error) {e}"}), 200

    entry = {
        "ts": int(time.time()),
        "title": "travel diary",
        "text": "",
        "caption": resp,
        "risk": 0.0,
        "state": "idle",
        "tag": "20B"
    }
    with LOCK:
        TIMELINE.append(entry)
        if len(TIMELINE) > TIMELINE_MAX:
            del TIMELINE[:-TIMELINE_MAX]
    return jsonify({"ok": True})

@app.route("/api/ask", methods=["POST"])
def api_ask():
    q = (request.get_json(silent=True) or {}).get("q","").strip() or "Summarize recent activities."
    snippets = tail_snippets(DIARY_WINDOW)
    prompt = f"""Answer the question using ONLY the following recent timeline snippets (newest last).
Be brief and precise (3–6 sentences). Mention uncertainty if needed.

Context: {json.dumps(snippets, ensure_ascii=False)}
Question: {q}
Answer:
"""
    try:
        ans = ollama_generate(REASON_MODEL, prompt, timeout=DIARY_TIMEOUT)
    except Exception as e:
        ans = f"(error contacting 20B) {e}"
    return jsonify({"answer": ans})

@app.route("/api/new_journey", methods=["POST"])
def api_new_journey():
    """Archive current timeline and reset."""
    global JOURNEY_ID
    try:
        path = archive_timeline()
        with LOCK:
            TIMELINE.clear()
            JOURNEY_ID += 1
        return jsonify({"ok": True, "archived": str(path)})
    except Exception as e:
        return jsonify({"ok": False, "error": str(e)}), 500

# ---------------------- main ----------------------

if __name__ == "__main__":
    print(f"[diary-portal] data dir : {DATA_DIR}")
    print(f"[diary-portal] images   : {IMG_DIR}")
    print(f"[diary-portal] ollama   : {OLLAMA_URL}")
    print(f"[diary-portal] models   : vision={VISION_MODEL}  diary={REASON_MODEL}")
    print(f"[diary-portal] limits   : window={DIARY_WINDOW}  keep_img={IMG_KEEP}  t_max={TIMELINE_MAX}")
    app.run(host=HOST, port=PORT, debug=False)

"""Khmer Dubber - server for the Android app.

The heavy work (Whisper / Gemini / Translate / Edge voice / FFmpeg) runs HERE (PC or Colab),
the phone only uploads the video, edits the lines and downloads the finished mp4.

Run:   pip install -r requirements-server.txt
       python server.py                 (optional: set KD_TOKEN=secret to require a password)
Phone: same Wi-Fi -> put  http://<PC-IP>:8765  in the app's Settings.
"""
import hashlib, hmac, os, shutil, socket, sys, threading, time, uuid
from pathlib import Path

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

import uvicorn
from fastapi import Depends, FastAPI, File, Form, Header, HTTPException, Query, UploadFile
from fastapi.responses import FileResponse
from pydantic import BaseModel

from core import ai, config, media, tts
from core.srt_utils import Seg

ROOT = Path.home() / ".khmer_dubber" / "jobs"
ROOT.mkdir(parents=True, exist_ok=True)
TOKEN = os.environ.get("KD_TOKEN", "")                       # admin password (sees every job, may use the server's Gemini key)
# PUBLIC MODE: give every friend their own token.  KD_TOKENS="anna:tok1,bob:tok2"  (or just "tok1,tok2").  Remove one = revoked.
TOKENS = {}
if TOKEN:
    TOKENS[TOKEN] = "admin"
for _t in filter(None, (x.strip() for x in os.environ.get("KD_TOKENS", "").split(","))):
    _n, _, _v = _t.partition(":")
    if not _v:
        _n, _v = "u" + hashlib.sha1(_t.encode()).hexdigest()[:5], _t
    TOKENS[_v] = _n
MAX_MB = float(os.environ.get("KD_MAX_MB", "500"))            # biggest upload
MAX_MIN = float(os.environ.get("KD_MAX_MIN", "0"))            # longest video in minutes (0 = no limit)
PER_USER = int(os.environ.get("KD_PER_USER", "2"))            # running jobs per person
SEM = threading.Semaphore(int(os.environ.get("KD_MAX_JOBS", "1")))   # heavy jobs at the same time (queue for the rest)
SHARE_KEY = os.environ.get("KD_SHARE_KEY", "0") == "1"        # 1 = friends may use the SERVER's Gemini key (default: they bring their own)
JOBS = {}                                   # id -> dict (status, pct, msg, segs, ...)
LOCK = threading.Lock()

app = FastAPI(title="Khmer Dubber server")


def auth(x_token: str = Header(default=""), token: str = Query(default="")):
    """-> user name. Header (app) or ?token= (phone browser <video>/download). No tokens configured = open (home use)."""
    if not TOKENS:
        return "anon"
    t = x_token or token
    for k, name in TOKENS.items():
        if t and hmac.compare_digest(t.encode(), k.encode()):
            return name
    raise HTTPException(401, "wrong token")


def job_or_404(jid, user="anon"):
    j = JOBS.get(jid)
    if not j or (user not in ("admin", "anon") and j.get("owner") != user):      # you only ever see your own jobs
        raise HTTPException(404, "job not found")
    return j


def own_key(user, given):
    """Friends bring their own Gemini key; the server's stored key is only for admin / home use / KD_SHARE_KEY=1."""
    given = (given or "").strip()
    if given:
        return given
    return config.load().get("gemini_key", "") if (user in ("admin", "anon") or SHARE_KEY) else ""


def setp(j, pct, msg=""):
    j["pct"] = int(max(0, min(100, pct)))
    if msg:
        j["msg"] = str(msg)


def seg_json(s):
    return {"start": round(s.start, 3), "end": round(s.end, 3), "src": s.src, "text": s.text, "gender": s.gender}


class SegIn(BaseModel):
    start: float
    end: float
    text: str
    gender: str = "female"
    src: str = ""


class RenderIn(BaseModel):
    segments: list[SegIn]
    speed: float = 1.0              # voice speed 0.5 .. 2.0
    fit: str = "Soft"               # Off / Soft / Hard
    keep_original_bg: bool = False  # keep original audio quietly under the dub
    gemini_key: str = ""
    resolution: int = 0             # short side in px (720 / 1080), 0 = keep


# ------------------------------------------------------------------ pipeline: transcribe + translate
def run_translate(j, cfg, src_lang, tgt_lang, engine):
    j["msg"] = "រង់ចាំជួរ…"
    with SEM:                                           # at most KD_MAX_JOBS heavy jobs at once, the rest wait here
        _run_translate(j, cfg, src_lang, tgt_lang, engine)


def _run_translate(j, cfg, src_lang, tgt_lang, engine):
    try:
        video, work = j["video"], j["work"]
        j["status"] = "working"
        setp(j, 1, "Transcribe…")
        segs = ai.transcribe(cfg, video, work, src_lang, lambda x, m="": setp(j, x * 0.5, m or "Transcribe"))
        if not segs:
            raise RuntimeError("រកមិនឃើញសំឡេងនិយាយក្នុងវីដេអូ")
        texts = [s.text for s in segs]
        if ai.split_keys(cfg.get("gemini_key", "")) and not cfg["stt_engine"].startswith("Gemini"):
            try:                                            # Whisper has no speaker info: guess male / female first
                for s, g in zip(segs, ai.detect_genders(cfg, texts, lambda *_: None)):
                    s.gender = g
            except Exception:
                pass
        durs = [max(0.4, s.end - s.start) for s in segs]
        res = ai.translate_texts(cfg, texts, tgt_lang, engine, lambda x, m="": setp(j, 50 + x * 0.45, m or "Translate"),
                                 durs, [s.gender for s in segs])
        for s, t in zip(segs, res):
            s.src, s.text = s.text, t
        j["segs"] = segs
        j["lang"] = tgt_lang
        j["status"] = "review"
        setp(j, 100, "ពិនិត្យអត្ថបទ")
    except Exception as e:
        j["status"], j["error"] = "error", str(e)


# ------------------------------------------------------------------ pipeline: voice + export
def run_render(j, req: RenderIn, user="anon"):
    j["msg"] = "រង់ចាំជួរ…"
    with SEM:
        _run_render(j, req, user)


def _run_render(j, req: RenderIn, user="anon"):
    try:
        j["status"] = "working"; j.pop("error", None)
        video, work, lang = j["video"], j["work"], j["lang"]
        cfg = config.load()
        cfg["gemini_key"] = own_key(user, req.gemini_key)
        segs = [Seg(s.start, s.end, s.text, "male" if s.gender.startswith("m") else "female", s.src) for s in req.segments]
        for s in segs:
            s.voice = tts.default_profile(s.gender)
        j["segs"] = segs
        o = {"speed": max(0.5, min(2.0, req.speed)), "pitch": 0, "reverb": False,
             "fit": req.fit if req.fit in ("Off", "Soft", "Hard") else "Soft",
             "gtts": False, "vol": 1.0, "end_sync": True}
        dur = media.duration(video)
        shorten = (lambda items: ai.shorten_texts(cfg, items, lang)) if ai.split_keys(cfg.get("gemini_key", "")) else None
        setp(j, 1, "Generate voice…")
        wav, _ = tts.render_dub(segs, lang, work, dur, o, lambda x, m="": setp(j, x * 0.7, m or "Voice"), False, shorten)
        bg, bvol = None, 0.8
        if req.keep_original_bg:
            setp(j, 75, "Original audio…")
            try:                                              # instant: voice cancelled + ducked under the dub
                bg, bvol = media.fast_bgm(video, wav, os.path.join(work, "bgm_fast.wav"), [(x.start, x.end) for x in segs]), 0.8
            except Exception:
                bg, bvol = media.extract_audio(video, os.path.join(work, "orig.wav"), 44100), 0.25
        setp(j, 80, "Rendering video…")
        out = os.path.join(work, "result.mp4")
        eo = {"dur": dur, "bg": bg, "bg_vol": bvol, "encoder": media.encoder_chain("auto"), "quality": "fast"}
        if req.resolution:
            eo["res"] = req.resolution
        media.export_video(video, wav, out, eo)
        j["result"] = out
        j["segs"] = segs
        j["status"] = "done"
        setp(j, 100, "រួចរាល់")
    except Exception as e:
        j["status"], j["error"] = "error", str(e)


# ------------------------------------------------------------------ API
WEB = Path(__file__).resolve().parent / "web" / "index.html"


@app.get("/")
def index():
    """Phone web page (no app needed): open http://<PC-IP>:8765 in the phone browser."""
    if not WEB.exists():
        raise HTTPException(404, "web/index.html not found")
    return FileResponse(WEB, media_type="text/html")


PWA_FILES = {"/manifest.webmanifest": "application/manifest+json", "/sw.js": "application/javascript",
             "/icon-192.png": "image/png", "/icon-512.png": "image/png", "/apple-touch-icon.png": "image/png"}


def _pwa(path):
    def h():
        f = WEB.parent / path.lstrip("/")
        if not f.exists():
            raise HTTPException(404, "not found")
        return FileResponse(f, media_type=PWA_FILES[path], headers={"Cache-Control": "no-cache"})
    return h


for _p in PWA_FILES:                                         # installable "app" (Add to Home screen)
    app.get(_p, include_in_schema=False)(_pwa(_p))


@app.get("/api/ping")
def ping(user=Depends(auth)):
    return {"ok": True, "ffmpeg": media.has_ffmpeg(), "tokenRequired": bool(TOKENS),
            "translator": True, "languages": sorted(ai.LANGS)}


@app.post("/api/jobs")
def create_job(video: UploadFile = File(...), src_lang: str = Form("Auto"), tgt_lang: str = Form("Khmer"),
               engine: str = Form("free"), stt: str = Form("whisper"), whisper_size: str = Form("small"),
               gemini_key: str = Form(""), fast: str = Form(""), user=Depends(auth)):
    if not media.has_ffmpeg():
        raise HTTPException(500, "ffmpeg មិនទាន់ដំឡើងលើ server")
    busy = sum(1 for x in JOBS.values() if x.get("owner") == user and x.get("status") in ("queued", "working"))
    if user != "admin" and busy >= PER_USER:
        raise HTTPException(429, f"អ្នកមានការងារកំពុងដំណើរការ {busy} ហើយ សូមរង់ចាំឱ្យចប់សិន")
    jid = uuid.uuid4().hex[:10]
    work = ROOT / jid
    work.mkdir(parents=True)
    ext = Path(video.filename or "v.mp4").suffix or ".mp4"
    path = work / ("input" + ext)
    size, limit = 0, int(MAX_MB * 1048576)
    with open(path, "wb") as f:
        while True:
            chunk = video.file.read(1024 * 1024)
            if not chunk:
                break
            size += len(chunk)
            if size > limit:
                f.close(); shutil.rmtree(work, ignore_errors=True)
                raise HTTPException(413, f"វីដេអូធំពេក (អតិបរមា {MAX_MB:.0f} MB)")
            f.write(chunk)
    if MAX_MIN and media.duration(str(path)) > MAX_MIN * 60:
        shutil.rmtree(work, ignore_errors=True)
        raise HTTPException(413, f"វីដេអូវែងពេក (អតិបរមា {MAX_MIN:.0f} នាទី)")
    cfg = config.load()
    key = own_key(user, gemini_key)
    cfg["gemini_key"] = key
    has_key = bool(ai.split_keys(key))
    if "lite" in str(cfg.get("gemini_model", "")).lower():      # Lite skips dialogue when transcribing
        cfg["gemini_model"] = "gemini-3.5-flash"
    cfg["lite_translate"] = bool(fast) and fast != "0" and has_key      # FAST mode: Lite model + short wording for translate
    cfg["short_translate"] = True
    cfg["stt_engine"] = "Gemini" if (stt == "gemini" and has_key) else "Local"
    cfg["whisper_size"] = whisper_size if whisper_size in ("tiny", "base", "small", "medium") else "small"
    eng = "Gemini (AI)" if (engine == "gemini" and has_key) else "Free (No API key)"
    j = {"id": jid, "status": "queued", "pct": 0, "msg": "", "video": str(path), "work": str(work),
         "segs": [], "lang": tgt_lang, "created": time.time(), "owner": user}
    with LOCK:
        JOBS[jid] = j
    threading.Thread(target=run_translate, args=(j, cfg, src_lang, tgt_lang, eng), daemon=True).start()
    return {"id": jid}


@app.get("/api/jobs/{jid}")
def job_status(jid: str, user=Depends(auth)):
    j = job_or_404(jid, user)
    out = {"id": jid, "status": j["status"], "pct": j["pct"], "msg": j["msg"], "error": j.get("error", "")}
    if j["status"] in ("review", "done"):
        out["segments"] = [seg_json(s) for s in j["segs"]]
    return out


@app.post("/api/jobs/{jid}/render")
def render(jid: str, req: RenderIn, user=Depends(auth)):
    j = job_or_404(jid, user)
    if j["status"] == "working":
        raise HTTPException(409, "កំពុងដំណើរការ")
    if not [s for s in req.segments if s.text.strip()]:
        raise HTTPException(400, "គ្មានអត្ថបទ")
    j["status"], j["pct"], j["msg"] = "working", 0, "Generate voice…"   # set now so the app never sees the old 'done'
    j.pop("error", None)
    threading.Thread(target=run_render, args=(j, req, user), daemon=True).start()
    return {"ok": True}


@app.get("/api/jobs/{jid}/video")
def get_video(jid: str, user=Depends(auth)):
    j = job_or_404(jid, user)
    if not j.get("result") or not os.path.exists(j["result"]):
        raise HTTPException(404, "មិនទាន់មានវីដេអូ")
    return FileResponse(j["result"], media_type="video/mp4", filename="dubbed.mp4")


@app.delete("/api/jobs/{jid}")
def delete_job(jid: str, user=Depends(auth)):
    j = JOBS.get(jid)
    if j and (user in ("admin", "anon") or j.get("owner") == user):
        JOBS.pop(jid, None)
        shutil.rmtree(j["work"], ignore_errors=True)
    return {"ok": True}


def cleanup_loop():
    """Always-on server: delete jobs (video + dub) older than KD_KEEP_HOURS (default 24) so the disk never fills up."""
    keep = float(os.environ.get("KD_KEEP_HOURS", "24")) * 3600
    while True:
        time.sleep(1800)
        now = time.time()
        for jid, j in list(JOBS.items()):
            if now - j.get("created", now) > keep and j.get("status") != "working":
                JOBS.pop(jid, None)
                shutil.rmtree(j["work"], ignore_errors=True)
        for d in ROOT.iterdir():                                  # folders left over from before a restart
            try:
                if d.is_dir() and d.name not in JOBS and now - d.stat().st_mtime > keep:
                    shutil.rmtree(d, ignore_errors=True)
            except Exception:
                pass


def lan_ip():
    try:
        s = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        s.connect(("8.8.8.8", 80)); ip = s.getsockname()[0]; s.close()
        return ip
    except Exception:
        return "127.0.0.1"


if __name__ == "__main__":
    port = int(os.environ.get("KD_PORT", "8765"))
    print(f"\n  Khmer Dubber server → http://{lan_ip()}:{port}   (ដាក់ក្នុង Settings នៃ app)")
    print("  Token:", "required (KD_TOKEN/KD_TOKENS)" if TOKENS else "none — ប្រើតែលើ Wi-Fi ផ្ទាល់ខ្លួន\n")
    threading.Thread(target=cleanup_loop, daemon=True).start()
    uvicorn.run(app, host="0.0.0.0", port=port, log_level="warning")

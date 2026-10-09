"""Gemini (all models), local faster-whisper (no key), and translation (Gemini AI or keyless Free)."""
import base64, hashlib, json, os, re, threading, time, requests
from concurrent.futures import ThreadPoolExecutor, as_completed
from .srt_utils import Seg
from .media import split_audio, extract_audio, duration as _duration, run as _run
from . import align, freetr

GEM = "https://generativelanguage.googleapis.com/v1beta"
FALLBACK_MODELS = ["gemini-flash-latest", "gemini-3.5-flash-lite", "gemini-3.8-flash", "gemini-3.5-flash", "gemini-3.1-flash-lite", "gemini-2.5-flash"]
GEMINI_NOTE = [""]                         # why Gemini was skipped (the UI shows it, otherwise the fallback to Free is silent)
LITE_MODEL = "gemini-3.5-flash-lite"      # fast model for translate / shorten when "Lite" is ON


def tr_model(cfg):
    """Model used for translating and shortening: the Lite model when the Lite switch is ON, else the model chosen in the header."""
    return LITE_MODEL if cfg.get("lite_translate") else cfg["gemini_model"]
_RESOLVED = {}   # dead model name -> working model name
_NO_JSON = set() # models that reject responseMimeType (JSON mode): we ask for JSON in the prompt instead
_NO_THINK = set()# models that reject thinkingConfig

CJK_RE = re.compile(r"[\u3400-\u9fff\uf900-\ufaff]")       # Chinese characters
KHMER_RE = re.compile(r"[\u1780-\u17ff]")                    # Khmer script
LETTER_RE = re.compile(r"[^\W\d_]", re.UNICODE)              # any real letter (not digit / punctuation)
SAFETY = [{"category": c, "threshold": "BLOCK_ONLY_HIGH"} for c in (
    "HARM_CATEGORY_HARASSMENT", "HARM_CATEGORY_HATE_SPEECH",
    "HARM_CATEGORY_SEXUALLY_EXPLICIT", "HARM_CATEGORY_DANGEROUS_CONTENT")]   # films contain fights / drama


def _headers(key):
    return {"x-goog-api-key": key, "Content-Type": "application/json"}    # key never appears in a URL / error text


# ---------------------------------------------------------------- many API keys at once (round-robin + cool-down)
_KEY_LOCK = threading.Lock()
_KEY_STATE = {"i": 0, "cool": {}, "bad": set()}


def split_keys(k):
    """'key1\nkey2, key3' -> ['key1','key2','key3']  (one key per line, or separated by comma / space)."""
    return [x for x in re.split(r"[\s,;]+", k or "") if len(x) > 8]


def _pick_key(keys):
    """Next key that is not cooling down / not bad (round-robin). If all are cooling: the one that wakes up first."""
    now = time.time()
    with _KEY_LOCK:
        st = _KEY_STATE
        ok = [k for k in keys if k not in st["bad"]]
        if not ok:
            st["bad"].clear(); ok = list(keys)
        ready = [k for k in ok if st["cool"].get(k, 0) <= now]
        if ready:
            k = ready[st["i"] % len(ready)]; st["i"] += 1
            return k
        return min(ok, key=lambda x: st["cool"].get(x, 0))


def _cool(k, sec):
    with _KEY_LOCK:
        _KEY_STATE["cool"][k] = time.time() + sec


def _mark_bad(k):
    with _KEY_LOCK:
        _KEY_STATE["bad"].add(k)


def _wait_for(k):
    w = _KEY_STATE["cool"].get(k, 0) - time.time()
    if w > 0:
        time.sleep(min(w, 30))

LANGS = {"Khmer": "km", "English": "en", "Chinese": "zh-CN", "Thai": "th", "Vietnamese": "vi",
         "Japanese": "ja", "Korean": "ko", "French": "fr", "Spanish": "es", "German": "de",
         "Russian": "ru", "Indonesian": "id", "Hindi": "hi", "Arabic": "ar"}

def _err(r):
    try:
        msg = r.json()["error"]["message"]
    except Exception:
        msg = r.text[:300]
    return RuntimeError(f"Gemini {r.status_code}: {msg}")   # never include the URL (it contains the API key)

def list_models(key):
    """Every Gemini model on this key that supports generateContent."""
    keys = split_keys(key)
    if not keys:
        raise RuntimeError("សូមដាក់ Gemini API Key ក្នុង Settings")
    last = None
    for k in keys:                                     # first key that works
        try:
            r = requests.get(f"{GEM}/models", headers=_headers(k), params={"pageSize": 200}, timeout=30)
        except requests.RequestException as e:
            raise RuntimeError("មិនអាចភ្ជាប់ទៅ Gemini បានទេ (ពិនិត្យ Internet): " + type(e).__name__)
        if r.status_code < 400:
            names = [m["name"].split("/")[-1] for m in r.json().get("models", [])
                     if "generateContent" in m.get("supportedGenerationMethods", []) and "gemini" in m["name"]]
            return sorted(names)
        last = _err(r)
    raise last

def _pick_model(key, bad):
    names = list_models(key)
    if "gemini-flash-latest" in names and bad != "gemini-flash-latest":
        return "gemini-flash-latest"
    skip = ("lite", "image", "live", "tts", "audio", "native", "embedding", "robotics", "computer", "thinking")
    c = [n for n in names if "flash" in n and n != bad and not any(w in n for w in skip)]
    if not c:
        raise RuntimeError("រកមិនឃើញ Gemini Flash model ដែលប្រើបានជាមួយ API Key នេះទេ។ សូមចុច ⟳ Models។")
    def ver(n):
        m = re.search(r"gemini-(\d+(?:\.\d+)?)", n)
        return (float(m.group(1)) if m else 0, "preview" not in n)
    return max(c, key=ver)

def gemini_call(key, model, parts, json_out=False, temperature=0.2):
    keys = split_keys(key)
    if not keys:
        raise RuntimeError("សូមដាក់ Gemini API Key ក្នុង Settings")
    model = _RESOLVED.get(model, model)
    body = {"contents": [{"parts": parts}], "generationConfig": {"temperature": temperature},
            "safetySettings": SAFETY}
    if json_out and model not in _NO_JSON:
        body["generationConfig"]["responseMimeType"] = "application/json"
    if model not in _NO_THINK:                        # no hidden "thinking" tokens: translation / STT answers come much faster
        body["generationConfig"]["thinkingConfig"] = {"thinkingBudget": 0}
    r = None
    tries = 5 + 2 * len(keys)
    for attempt in range(tries):
        last = attempt == tries - 1
        k = _pick_key(keys)
        _wait_for(k)                                  # every key is cooling down: wait for the first one to wake up
        try:
            r = requests.post(f"{GEM}/models/{model}:generateContent", headers=_headers(k), json=body, timeout=150)
        except requests.RequestException as e:
            if not last:
                time.sleep(3); continue
            raise RuntimeError("មិនអាចភ្ជាប់ទៅ Gemini បានទេ (ពិនិត្យ Internet): " + type(e).__name__)
        sc, low = r.status_code, r.text.lower()
        if sc == 404 and not last:                    # model retired / not available for this key
            new = _pick_model(key, model)
            _RESOLVED[model] = new; model = new
            continue
        if sc == 400 and "thinkingConfig" in body["generationConfig"] and "think" in low:
            body["generationConfig"].pop("thinkingConfig"); _NO_THINK.add(model)
            continue                                  # this model has no thinking switch -> retry without it
        if sc == 400 and "responseMimeType" in body["generationConfig"] and ("json" in low or "mime" in low):
            body["generationConfig"].pop("responseMimeType"); _NO_JSON.add(model)
            continue                                  # "JSON mode is not enabled for this model" -> retry without it
        if sc == 400 and "safetySettings" in body and "safety" in low:
            body.pop("safetySettings"); continue      # this model rejects safetySettings
        if sc == 429 or "resource_exhausted" in low or (sc in (403, 503) and "quota" in low):
            _cool(k, 600 if "per day" in low or "daily" in low else 70)    # limit reached: use the next key
            if not last:
                continue
        elif sc in (400, 401, 403) and ("api key not valid" in low or "api_key_invalid" in low or "key expired" in low):
            _mark_bad(k)                              # wrong key: skip it, try the others
            if len(keys) > 1 and not last:
                continue
        elif sc in (500, 502, 503, 504) and not last:
            time.sleep(3 * (attempt + 1)); continue
        break
    if r.status_code >= 400:
        raise _err(r)
    data = r.json()
    cands = data.get("candidates") or []
    if not cands:
        raise RuntimeError("Gemini មិនឆ្លើយ (" + str((data.get("promptFeedback") or {}).get("blockReason", "empty")) + ")")
    ps = (cands[0].get("content") or {}).get("parts") or []
    txt = "".join(p.get("text", "") for p in ps if not p.get("thought"))
    if not txt.strip():
        raise RuntimeError("Gemini ឆ្លើយទទេ (" + str(cands[0].get("finishReason", "?")) + ")")
    return txt

def parse_json(t):
    t = re.sub(r"^```(?:json)?\s*|\s*```$", "", t.strip(), flags=re.I).strip()
    try:
        return json.loads(t)
    except Exception:
        pass
    for a, b in (("[", "]"), ("{", "}")):             # JSON wrapped in extra words
        i, j = t.find(a), t.rfind(b)
        if i != -1 and j > i:
            try:
                return json.loads(t[i:j + 1])
            except Exception:
                continue
    raise ValueError("Gemini ឆ្លើយមិនមែន JSON")


def as_list(obj):
    """Accept [..] or {'segments': [..]} style answers."""
    if isinstance(obj, list):
        return obj
    if isinstance(obj, dict):
        for v in obj.values():
            if isinstance(v, list):
                return v
    raise ValueError("Gemini ឆ្លើយមិនមែន list")


def to_sec(v, default=0.0):
    if isinstance(v, (int, float)):
        return float(v)
    try:
        sec = 0.0
        for x in str(v).strip().replace(",", ".").split(":"):
            sec = sec * 60 + float(x)
        return sec
    except Exception:
        return default


def _fatal(e):
    """Errors that retrying / falling back will not fix (bad key, no permission)."""
    m = str(e)
    return "API Key" in m or m.startswith(("Gemini 400", "Gemini 401", "Gemini 403"))


def _auth_error(e):
    m = str(e).lower()
    return "api key" in m or m.startswith(("gemini 401", "gemini 403"))


def _stt_models(model):
    """The chosen model first, then safe fallbacks (some models return an empty answer for audio)."""
    out = []
    for m in (model, "gemini-flash-latest", "gemini-2.5-flash"):
        if m and m not in out:
            out.append(m)
    return out

def run_parallel(fn, jobs, workers, progress_cb=None):
    """Run fn(*job) for every job in a thread pool, results in the SAME ORDER as jobs.
    progress_cb(done, total) is called from the calling thread (so Stop / cancel works). The first error is raised."""
    res = [None] * len(jobs)
    if not jobs:
        return res
    ex = ThreadPoolExecutor(max_workers=max(1, min(workers, len(jobs))))
    try:
        futs = {ex.submit(fn, *a): i for i, a in enumerate(jobs)}
        done = 0
        for f in as_completed(futs):
            res[futs[f]] = f.result()
            done += 1
            if progress_cb:
                progress_cb(done, len(jobs))
    finally:
        ex.shutdown(wait=False, cancel_futures=True)
    return res


def _workers(key, per_key=3, cap=10):
    return max(3, min(cap, per_key * max(1, len(split_keys(key)))))


# ---------------------------------------------------------------- Speech to Text
def _cache_file(cache_dir, path, tag):
    if not cache_dir:
        return None
    os.makedirs(cache_dir, exist_ok=True)
    h = hashlib.md5(f"{os.path.basename(path)}|{os.path.getsize(path)}|{tag}".encode()).hexdigest()[:16]
    return os.path.join(cache_dir, h + ".json")


def _covered(items):
    t = 0.0
    for it in items:
        if isinstance(it, dict):
            t += max(0.0, to_sec(it.get("end", 0)) - to_sec(it.get("start", 0)))
    return t


def _stt_one(key, model, path, prompt, tag, cache_dir):
    """One audio chunk -> list of {start,end,text,gender,speaker} (seconds relative to the chunk). Cached on disk (resume).
    If the answer covers far less than the speech that is really in the chunk, it is asked again (skipped dialogue)."""
    cf = _cache_file(cache_dir, path, f"{tag}|{model}")
    if cf and os.path.exists(cf):
        try:
            cached = json.load(open(cf, encoding="utf-8"))
            if cached:                                  # an empty answer is never trusted from the cache
                return cached
        except Exception:
            pass
    with open(path, "rb") as f:
        b64 = base64.b64encode(f.read()).decode()
    parts = [{"text": prompt}, {"inline_data": {"mime_type": "audio/mp3", "data": b64}}]
    try:
        voiced = align.voiced_seconds(path)
    except Exception:
        voiced = 0.0
    best, last = None, None
    for m in _stt_models(model):                       # chosen model, then fallbacks
        for k in range(2):                             # 2 tries per model (slightly warmer the 2nd time)
            try:
                txt = gemini_call(key, m, parts, True, temperature=0.2 + 0.3 * k)
                items = as_list(parse_json(txt))
            except Exception as e:
                last = e
                if _auth_error(e):
                    raise
                time.sleep(1); continue
            if best is None or _covered(items) > _covered(best):
                best = items
            if voiced < 8 or _covered(best) >= voiced * 0.35:      # enough of the speech was written down
                break
        else:
            continue
        break
    if best is None:
        raise RuntimeError(f"{last}\n\nគន្លឹះ: ចុច ⟳ ដើម្បីជ្រើស model ផ្សេង ឬប្តូរទៅ Whisper (Local — មិនត្រូវការ key) ខាងលើ។")
    if cf and best:
        try:
            json.dump(best, open(cf, "w", encoding="utf-8"), ensure_ascii=False)
        except Exception:
            pass
    return best


def _smooth_genders(items):
    """The same speaker label inside one chunk keeps ONE gender (majority vote) - stops male/female flipping line by line."""
    votes = {}
    for it in items:
        if isinstance(it, dict):
            sp = str(it.get("speaker", "")).strip().upper()
            if sp:
                v = votes.setdefault(sp, [0, 0])
                v[0 if str(it.get("gender", "female")).lower().startswith("m") else 1] += 1
    for it in items:
        if isinstance(it, dict):
            sp = str(it.get("speaker", "")).strip().upper()
            if sp in votes:
                it["gender"] = "male" if votes[sp][0] > votes[sp][1] else "female"
    return items


def transcribe_gemini(key, model, chunks, lang, progress, cache_dir=None):
    hint = f" The spoken language is {lang}." if lang and lang != "Auto" else ""
    prompt = ('Transcribe this audio exactly in its original language.' + hint +
              ' Return ONLY a JSON array. Each item: {"start": seconds_from_start_of_this_audio (float), '
              '"end": seconds (float), "text": "sentence", "speaker": "S1", "gender": "male" or "female"}. '
              '"speaker" is a label (S1, S2, S3...) that stays the SAME for the same person (same voice) for the whole audio; '
              '"gender" is that person\'s voice. '
              'Transcribe EVERY spoken sentence from the first second to the last second: never summarize, never skip a line, '
              'never stop early. "start"/"end" must hug the spoken words exactly (not the silence around them). '
              'Split into short subtitle-sized sentences (max ~12 words). Skip pure music/noise. No commentary. '
              'If there is no speech at all, return [].')
    n = len(chunks)
    progress(0, f"Gemini 0/{n} (parallel)…")
    jobs = [(key, model, path, prompt, lang or "Auto", cache_dir) for path, _ in chunks]
    results = run_parallel(_stt_one, jobs, _workers(key), lambda d, t: progress(int(d / t * 100), f"Gemini {d}/{t} (parallel)"))
    out = []
    for (path, off), items in zip(chunks, results):
        items = _smooth_genders(items)
        for it in items:
            if not isinstance(it, dict):
                continue
            t = str(it.get("text", "")).strip()
            if not t:
                continue
            st = to_sec(it.get("start", 0)) + off
            en = to_sec(it.get("end", 0)) + off
            if en <= st:
                en = st + max(1.0, len(t) * 0.25)
            g = str(it.get("gender", "female")).lower()
            out.append(Seg(st, en, t, "male" if g.startswith("m") else "female", t,
                           speaker=str(it.get("speaker", "")).strip().upper()[:8]))
    out.sort(key=lambda s: s.start)
    return out

def find_gaps(wav, segs, min_gap=2.5, window=90.0):
    """Stretches where the audio has sound (speech bursts found by silence detection) but NO transcribed line covers it.
    That is where a transcriber skipped dialogue (wrong language, VAD too strict, one bad chunk). -> [(start, end)]"""
    try:
        regions = align.speech_regions(wav)            # [] when the audio never goes quiet (nothing reliable to compare with)
    except Exception:
        return []
    spans = sorted((s.start, s.end) for s in segs)
    out = []
    for a, b in regions:
        t = a
        while t < b:                                   # long bursts (music + talk) are checked in windows
            e = min(b, t + window)
            if e - t >= min_gap:
                cov = sum(max(0.0, min(e, y) - max(t, x)) for x, y in spans if y > t and x < e)
                if (e - t) - cov >= min_gap and cov < (e - t) * 0.4:
                    out.append([t, e])
            t = e
    merged = []
    for a, b in out:                                   # join neighbours (<1 s apart), keep every piece <= 2 windows
        if merged and a - merged[-1][1] < 1.0 and b - merged[-1][0] <= window * 2:
            merged[-1][1] = b
        else:
            merged.append([a, b])
    return [(max(0.0, a - 0.3), b + 0.3) for a, b in merged][:80]


def find_holes(segs, total, min_hole=10.0):
    """Stretches >= min_hole seconds with NO transcribed line at all. Works even when background music never goes quiet
    (then silence-based find_gaps sees nothing). -> [(start, end)]"""
    spans = sorted((s.start, s.end) for s in segs)
    out, t = [], 0.0
    for a, b in spans + [(total, total)]:
        if a - t >= min_hole:
            out.append((t, a))
        t = max(t, b)
    return out


def fill_holes(cfg, wav, segs, total, lang, work, progress, min_hole=10.0, cap=40, extra=()):
    """Ask Gemini again for every long hole (pieces <= 60 s, in parallel). Gemini answers [] when there is no speech."""
    rng = sorted(list(find_holes(segs, total, min_hole)) + [tuple(x) for x in extra])
    holes = []                                              # union of silence-gaps and empty stretches, no duplicate work
    for a, b in rng:
        if holes and a <= holes[-1][1] + 1.0:
            holes[-1] = (holes[-1][0], max(holes[-1][1], b))
        else:
            holes.append((a, b))
    holes = sorted(holes, key=lambda h: h[0] - h[1])[:cap]  # the longest ones first when there are too many
    pieces = []
    for a, b in holes:
        t = a
        while t < b - 1.0:
            e = min(b, t + 60.0)
            pieces.append((max(0.0, t - 0.3), min(total, e + 0.3))); t = e
    if not pieces:
        return []
    chunks = []
    for k, (a, b) in enumerate(pieces):
        sl = os.path.join(work, f"hole_{k:03d}.mp3")
        _run(["ffmpeg", "-y", "-i", wav, "-ac", "1", "-ar", "16000", "-b:a", "32k", "-ss", f"{a:.3f}", "-t", f"{b - a:.3f}", sl])
        chunks.append((sl, a))
    progress(95, f"Fill missing speech: {len(chunks)} piece(s) in parallel…")
    new = transcribe_gemini(cfg["gemini_key"], cfg["gemini_model"], chunks, lang, lambda *_: None, None)
    spans = [(s.start, s.end) for s in segs]
    keep = []
    for n in new:
        mid = (n.start + n.end) / 2
        if not any(x <= mid <= y for x, y in spans):        # never duplicate a line that already exists
            keep.append(n)
    return keep


def _whisper_run(size, dev, ct, wav, lang, progress):
    try:
        from faster_whisper import WhisperModel, decode_audio   # runs offline after first model download
    except ImportError:
        raise RuntimeError("កំណែនេះគ្មាន Whisper (កំណែស្រាល) — សូមជ្រើស Gemini សម្រាប់ Transcribe និងដាក់ Gemini API Key ក្នុង ⚙ Settings")
    kw = {"cpu_threads": os.cpu_count() or 4} if dev == "cpu" else {}
    model = WhisperModel(size, device=dev, compute_type=ct, **kw)   # cpu int8 = fast on weak PCs; GPU only when it is really faster
    code = LANGS.get(lang, "").split("-")[0] if lang and lang != "Auto" else None
    prompt = "以下是普通话的句子。" if code == "zh" else None      # keeps Simplified Chinese + punctuation (better text to translate)
    vad = {"threshold": 0.4, "min_silence_duration_ms": 500}     # a bit more sensitive than the default: quiet speech is not skipped
    it, info = model.transcribe(wav, language=code, vad_filter=True, vad_parameters=vad, beam_size=2,
                                condition_on_previous_text=False, initial_prompt=prompt)
    out = []
    for s in it:
        t = s.text.strip()
        if t:
            out.append(Seg(s.start, s.end, t, "female", t))
        progress(int(min(s.end / max(info.duration, 1), 1) * 90), f"Local Whisper ({dev.upper()})")
    # second look at every stretch that has sound but no line (skipped dialogue)
    gaps = find_gaps(wav, out)
    if gaps:
        audio = decode_audio(wav, sampling_rate=16000)
        for k, (a, b) in enumerate(gaps, 1):
            progress(90 + int(k / len(gaps) * 10), f"Fill missing speech {k}/{len(gaps)} ({dev.upper()})")
            try:
                it2, _ = model.transcribe(audio[int(a * 16000):int(b * 16000)], language=code, vad_filter=True,
                                          vad_parameters={"threshold": 0.3, "min_silence_duration_ms": 400},
                                          beam_size=2, condition_on_previous_text=False, initial_prompt=prompt)
                for s in it2:
                    t = s.text.strip()
                    if t and getattr(s, "no_speech_prob", 0) < 0.8 and getattr(s, "avg_logprob", 0) > -1.3:
                        out.append(Seg(a + s.start, a + s.end, t, "female", t))
            except Exception:
                continue
        out.sort(key=lambda x: x.start)
    return out


def transcribe_local(wav, size, lang, progress):
    """Auto GPU/CPU: the GPU when it is usable and fast, and if it fails for ANY reason (missing CUDA DLL, out of memory) the CPU takes over."""
    from . import device
    last = None
    for dev, ct in device.whisper_plans():
        try:
            return _whisper_run(size, dev, ct, wav, lang, progress)
        except Exception as e:
            last = e
            progress(0, f"{dev.upper()} មិនបាន → ប្តូរទៅ CPU")
    raise last

def transcribe(cfg, video, work, lang, progress):
    eng = cfg["stt_engine"]
    if eng.startswith("Local"):
        segs = transcribe_local(extract_audio(video, os.path.join(work, "a16.wav")), cfg["whisper_size"], lang, progress)
    else:
        chunks = split_audio(video, work, 120)     # 2-minute pieces: faster, shorter JSON, visible progress, Stop works
        segs = transcribe_gemini(cfg["gemini_key"], cfg["gemini_model"], chunks, lang, progress,
                                 os.path.join(work, "stt_cache"))
    try:
        wav = extract_audio(video, os.path.join(work, "a16.wav"))
    except Exception:
        return segs
    if not eng.startswith("Local"):                # Gemini skipped some dialogue? ask again for exactly those stretches
        try:                                       # ONE parallel pass over (silence gaps + empty stretches); it was 11 sequential calls
            try:
                gaps = find_gaps(wav, segs)
            except Exception:
                gaps = []
            segs += fill_holes(cfg, wav, segs, _duration(video), lang, work, progress, extra=gaps)
            segs.sort(key=lambda x: x.start)
        except Exception as e:
            if _auth_error(e):
                raise
    try:                                           # snap start/end to the real speech so the dub lands on the voice
        segs = align.refine(segs, align.speech_regions(wav))
    except Exception:
        pass
    return segs

# ---------------------------------------------------------------- Translation
def _bad(src, out, lang):
    """True when a translated line is unusable (empty, or still Chinese / not Khmer)."""
    if not src.strip() or not LETTER_RE.search(src):
        return False
    if not out or not out.strip():
        return True
    if lang == "Khmer":
        if not KHMER_RE.search(out):
            return True
        cjk = len(CJK_RE.findall(src)) if CJK_RE.search(src) else 0
        # a Chinese character needs >= ~2 Khmer letters: far fewer = the model dropped part of the sentence
        return cjk >= 6 and len(re.sub(r"\s", "", out)) < cjk * 1.0
    if lang not in ("Chinese", "Japanese"):
        return bool(CJK_RE.search(out) and CJK_RE.search(src))
    return False


CPS = {"Khmer": 12, "Thai": 13, "Vietnamese": 14, "English": 15, "Chinese": 5, "Japanese": 7, "Korean": 8}   # chars / second


def _gemini_batch(key, model, items, lang, secs=None, before=None, after=None, genders=None, short=False, glossary=None):
    """items {index: text} -> {index: translation}. Numbered keys keep every line aligned with its source.
    secs {index: seconds available}: the translation must be speakable in that time (dubbing)."""
    secs = secs or {}
    cps = CPS.get(lang, 14)
    payload = {}
    for i, t in items.items():
        d = secs.get(i)
        # the voice is sped up automatically (Auto-Fit), so length is only a SOFT target: meaning always comes first
        payload[str(i)] = {"text": t, "seconds": round(d, 1), "target_chars": max(6, int(d * cps * (1.0 if short else 1.4)))} if d else {"text": t}
        if genders and genders.get(i):
            payload[str(i)]["speaker"] = genders[i]
    extra = " Use natural, everyday Cambodian Khmer as spoken in Phnom Penh." if lang == "Khmer" else ""
    ctx = ""
    if before:
        ctx += "Previous lines (context only, DO NOT translate): " + json.dumps(before, ensure_ascii=False) + "\n"
    if after:
        ctx += "Next lines (context only, DO NOT translate): " + json.dumps(after, ensure_ascii=False) + "\n"
    if glossary:
        ctx += ("GLOSSARY (use EXACTLY these spellings every time these names/terms appear): "
                + json.dumps(glossary, ensure_ascii=False) + "\n")
    prompt = (f"You are a professional film/TV dubbing translator. Translate the `text` of every entry of the JSON object below "
              f"into natural, spoken {lang} for voice-over dubbing.{extra}\n"
              f"Rules, in order of importance:\n"
              f"1. FAITHFUL TO THE ORIGINAL SCRIPT: say exactly what the original line says. Translate every sentence and clause, "
              f"keep the meaning, intent, emotion, questions, negations, numbers, dates, titles and names. "
              f"NEVER leave anything out, NEVER add words or explanations, NEVER soften, censor or change the meaning, never guess a different story.\n"
              f"2. One entry in, one entry out: translate only that line. Do not merge lines or move words between lines.\n"
              f"3. Write only in {lang}'s native script. No pinyin, no romanization, no Chinese characters (a Chinese name is transliterated "
              f"into {lang} script, spelled the same way every time).\n"
              f"4. Spoken style a native speaker would really say in that situation, not word-by-word textbook text. "
              f"Use the neighbouring lines to understand who speaks, who is addressed and what is being referred to (pronouns, omitted subjects). "
              f"When an entry has `speaker` (male/female) choose first/second-person words, politeness and tone that fit that character "
              f"(e.g. Khmer ខ្ញុំ / បង / អូន / គាត់ / លោក / អ្នកស្រី / ឯង) and keep them the same across all lines.\n"
              + (f"5. Length: SHORT dubbing. Use the shortest natural spoken wording, aim for `target_chars` or fewer, drop fillers and repetition, "
                 f"but keep every fact, name, number and the emotion. Never change the meaning.\n" if short else
                 f"5. Length: `target_chars` is only a soft target for dubbing speed. Prefer the shorter natural wording, "
                 f"but if the full meaning needs more characters, keep the full meaning (the voice will be sped up). Never cut meaning to hit it.\n")
              + f"6. CONTINUOUS SCRIPT: neighbouring lines are often ONE sentence cut by the subtitles. Read `before` / `after`, translate each line so the "
              f"lines flow together when spoken one after another: do not finish a sentence early, do not repeat what the neighbour already says, "
              f"keep names, pronouns and tone consistent, natural spoken drama Khmer (not bookish).\n"
              + f"7. Return ONLY a JSON object with exactly the same keys, each value being the translated string.\n\n"
              + ctx + "\nLINES TO TRANSLATE:\n" + json.dumps(payload, ensure_ascii=False))
    res = parse_json(gemini_call(key, model, [{"text": prompt}], True, temperature=0.1))   # low temperature = stays on the script
    if isinstance(res, list):                          # model dropped the keys: only trust an exact-length list
        res = dict(zip(payload.keys(), res)) if len(res) == len(payload) else {}
    out = {}
    for k, v in res.items():
        if not str(k).isdigit():
            continue
        if isinstance(v, dict):                        # model echoed the structure
            v = v.get("text") or v.get("translation") or ""
        if isinstance(v, (str, int, float)):
            out[int(k)] = str(v).strip()
    return out


_NAME_HINT = re.compile(r"[A-Z][a-z]+|[\u3400-\u9fff]{2,4}|[\u3040-\u30ff]{2,}|[\uac00-\ud7af]{2,}")


def build_glossary(key, model, texts, lang, max_terms=60):
    """ONE cheap call before translating: find the people / place / brand names and recurring terms of the whole script and fix
    their spelling in the target language. Every batch then uses the same spelling, so a name never changes mid-video.
    Returns {} on any problem (the translation simply runs without it)."""
    try:
        sample = [t.strip() for t in texts if t.strip() and _NAME_HINT.search(t)]
        if len(sample) < 6:
            return {}
        step = max(1, len(sample) // 400)                      # long videos: an even sample of ~400 lines is enough
        script = "\n".join(sample[::step])[:14000]
        prompt = (f"Below is the dialogue of a film/video. List the PEOPLE names, nicknames, places, organisations, brands, titles and "
                  f"recurring special terms that appear in it, and give each ONE fixed {lang} spelling (transliterate names into "
                  f"{lang} script the way a native speaker would write them; for terms give the usual {lang} word). "
                  f"Only include things that appear at least once. Maximum {max_terms} entries. "
                  f"Return ONLY a JSON object {{\"original\": \"{lang} spelling\"}}.\n\n" + script)
        res = parse_json(gemini_call(key, model, [{"text": prompt}], True, temperature=0.0))
        if not isinstance(res, dict):
            return {}
        out = {str(k).strip(): str(v).strip() for k, v in res.items()
               if str(k).strip() and isinstance(v, (str, int, float)) and str(v).strip()}
        if lang == "Khmer":                                    # a Khmer glossary entry must really be Khmer script
            out = {k: v for k, v in out.items() if KHMER_RE.search(v)}
        return dict(list(out.items())[:max_terms])
    except Exception:
        return {}


def _gemini_translate(key, model, texts, lang, progress, durations=None, genders=None, short=False):
    n = len(texts)
    out = list(texts)
    todo = [i for i in range(n) if texts[i].strip() and LETTER_RE.search(texts[i])]
    total, done = max(len(todo), 1), set()
    failed = False
    progress(1, "Glossary (names)…")
    glossary = build_glossary(key, model, texts, lang)

    def one(chunk):
        try:
            lo, hi = min(chunk), max(chunk)
            before = [texts[j] for j in range(max(0, lo - 6), lo)]
            after = [texts[j] for j in range(hi + 1, min(n, hi + 6))]
            return ("ok", _gemini_batch(key, model, {i: texts[i] for i in chunk}, lang,
                                        {i: durations[i] for i in chunk} if durations else None, before, after,
                                        {i: genders[i] for i in chunk} if genders else None, short, glossary))
        except Exception as e:
            return ("err", e)

    def run_pass(indices, size):
        nonlocal failed
        chunks = [indices[s:s + size] for s in range(0, len(indices), size)]
        res = run_parallel(one, [(c,) for c in chunks], _workers(key, 4, 12),
                           lambda d, t: progress(int(len(done) / total * 90), f"Translate {len(done)}/{total}  (batch {d}/{t})"))
        for chunk, (kind, val) in zip(chunks, res):
            if kind == "err":
                if _fatal(val):
                    raise val
                failed = True                          # network / quota / blocked: the free translator below will cover it
                continue
            for i, t in val.items():
                if i in chunk and not _bad(texts[i], t, lang):
                    out[i] = t; done.add(i)
        progress(int(len(done) / total * 90), f"Translate {len(done)}/{total}")

    run_pass(todo, 30)
    for size in (5, 1):                                # retry the lines that came back wrong, in smaller groups
        left = [i for i in todo if i not in done]
        if not left or failed:
            break
        run_pass(left, size)
    left = [i for i in todo if i not in done]
    if left:                                           # last resort: free Google translate for those lines only
        progress(92, f"Free translate {len(left)} lines…")
        for i, t in zip(left, _free_translate([texts[i] for i in left], lang, lambda *_: None)):
            if t and t.strip():
                out[i] = t
    progress(100, f"Translate {total}/{total}")
    return out


def _free_translate(texts, lang, progress):
    """No API key: parallel Google web endpoint (see freetr.py) - hundreds of lines in seconds."""
    return freetr.translate(texts, lang, progress)


def translate_texts(cfg, texts, lang, engine, progress, durations=None, genders=None):
    """engine 'Gemini (AI)': smart, timing-aware (needs a key).  'Free (No API key)': fast, no key at all.
    If Gemini is chosen but there is no key / it fails, the free translator takes over automatically."""
    if not texts:
        return []
    GEMINI_NOTE[0] = ""
    if engine.startswith("Gemini") and split_keys(cfg.get("gemini_key", "")):
        models = []                                    # Lite first (fast); if it fails try the model chosen in the header, then flash-latest
        for m in (tr_model(cfg), cfg["gemini_model"], "gemini-flash-latest"):
            if m and m not in models:
                models.append(m)
        errs = []
        for m in models:
            try:
                return _gemini_translate(cfg["gemini_key"], m, texts, lang, progress, durations, genders,
                                         bool(cfg.get("short_translate", True)) and bool(durations))
            except Exception as e:
                errs.append(f"{m}: {str(e)[:110]}")
                progress(5, f"Gemini {m} មិនបាន → សាកម៉ូដែលបន្ទាប់…")
                if _auth_error(e):                     # wrong / expired key: another model will not help
                    break
        GEMINI_NOTE[0] = "Gemini បរាជ័យ → ប្រើ Free (យឺតជាង):\n" + "\n".join(errs)
    return _free_translate(texts, lang, progress)


def shorten_texts(cfg, items, lang):
    """items [(index, text, seconds_available, seconds_needed)] -> {index: shorter text}.
    Used after the first voice pass for lines that are still too long to fit the video."""
    if not items:
        return {}
    cps = CPS.get(lang, 14)
    payload = {str(i): {"text": t, "seconds_available": round(slot, 1), "seconds_needed_now": round(need, 1),
                        "max_chars": max(4, int(slot * cps * 1.0))} for i, t, slot, need in items}
    prompt = (f"These are {lang} dubbing lines that are TOO LONG: spoken aloud they take `seconds_needed_now` but only "
              f"`seconds_available` is free before the next line. Rewrite every line shorter in the same language so it fits "
              f"(about `max_chars` characters). Keep EVERY important meaning, fact, number, emotion and character name; only drop fillers, repetition and polite padding; "
              f"never change what is said; natural spoken style. Return ONLY a JSON object with the same keys and the shortened strings.\n\n"
              + json.dumps(payload, ensure_ascii=False))
    res = parse_json(gemini_call(cfg["gemini_key"], tr_model(cfg), [{"text": prompt}], True))
    out = {}
    for k, v in (res.items() if isinstance(res, dict) else []):
        if isinstance(v, dict):
            v = v.get("text", "")
        v = str(v).strip()
        if str(k).isdigit() and v and (lang != "Khmer" or KHMER_RE.search(v)):
            out[int(k)] = v
    return out


def detect_genders(cfg, texts, progress):
    """Guess male/female speaker for each line (for lines loaded from SRT / Local Whisper).
    Every batch also sees the 6 lines before it, so one speaker keeps the same gender across batch borders."""
    out, B, C = [], 40, 6
    for i in range(0, len(texts), B):
        batch = texts[i:i + B]
        ctx = texts[max(0, i - C):i]
        known = out[-len(ctx):] if ctx else []
        prompt = ("For each dialogue line of this JSON array guess if the speaker is male or female from context "
                  "(pronouns, address terms, tone, who talks to whom), keeping one speaker consistent within a scene. "
                  f"Return ONLY a JSON array of exactly {len(batch)} strings, each 'male' or 'female'.\n"
                  + (("Previous lines (context only, do not answer them) with their already decided speaker: "
                      + json.dumps(list(zip(ctx, known)), ensure_ascii=False) + "\n") if ctx and len(known) == len(ctx) else "")
                  + "LINES:\n" + json.dumps(batch, ensure_ascii=False))
        try:
            res = [("male" if str(x).lower().startswith("m") else "female")
                   for x in as_list(parse_json(gemini_call(cfg["gemini_key"], cfg["gemini_model"], [{"text": prompt}], True)))]
        except Exception:
            res = []
        res = res[:len(batch)]; res += ["female"] * (len(batch) - len(res)); out += res
        progress(int(min(i + B, len(texts)) / len(texts) * 100), "Detect speakers")
    return out


# ---------------------------------------------------------------- Screen text (hard-coded subtitles, OCR)
def ocr_frames(cfg, frames, progress):
    """Gemini vision reads the text visible in each cropped frame (e.g. Chinese hard subs)."""
    out, B = [], 20
    for i in range(0, len(frames), B):
        batch = frames[i:i + B]
        parts = [{"text": ("Each image is a cropped region of a video that may contain hard-coded subtitle text "
                           "(often Chinese). For each image return exactly the text that is visible, in its original "
                           "language and script, or an empty string if there is none. Return ONLY a JSON array of "
                           f"exactly {len(batch)} strings, in image order.")}]
        for k, (_, p) in enumerate(batch):
            parts.append({"text": f"Image {k}:"})
            parts.append({"inline_data": {"mime_type": "image/jpeg", "data": base64.b64encode(open(p, "rb").read()).decode()}})
        try:
            res = [str(x).strip() for x in as_list(parse_json(gemini_call(cfg["gemini_key"], cfg["gemini_model"], parts, True)))]
        except Exception as e:
            if _fatal(e):
                raise
            res = []
        res = res[:len(batch)]; res += [""] * (len(batch) - len(res)); out += res
        progress(int(min(i + B, len(frames)) / len(frames) * 100), f"Reading screen text {min(i + B, len(frames))}/{len(frames)}")
    return out


def merge_ocr(frames, texts, step):
    """Merge consecutive frames that show the same text into one subtitle segment."""
    import difflib
    segs, cur = [], None
    for (t, _), tx in zip(frames, texts):
        tx = " ".join(tx.split())
        if tx and cur and difflib.SequenceMatcher(None, cur.src, tx).ratio() > 0.8:
            cur.end = t + step
        elif tx:
            cur = Seg(t, t + step, tx, "female", tx)
            segs.append(cur)
        else:
            cur = None
    return segs


def read_screen_text(cfg, video, region, step, work, progress):
    from .media import extract_frames
    progress(5, "Extracting frames…")
    frames = extract_frames(video, region, step, work)
    if not frames:
        raise RuntimeError("មិនអាចទាញ frame ពីវីដេអូបានទេ")
    texts = ocr_frames(cfg, frames, lambda p, m="": progress(10 + p * 0.85, m))
    return merge_ocr(frames, texts, step)
"""Translate with NO API key and FAST (pure `requests`, no extra package needed).

Primary : Google Translate public web endpoint (client=gtx) - many lines in parallel over one keep-alive session.
Fallback: deep-translator (Google / MyMemory) if the endpoint is blocked on this network.
Speed   : MANY lines go in ONE request (batch, checked line-by-line), several batches in parallel.
          If a batch does not come back with exactly the same number of lines, only that batch is redone line by line.
Accuracy: the source language of every line is detected (Chinese / Japanese / Korean) instead of letting Google guess
          on short lines, and neighbouring lines travel together in a batch (better context).
Extras  : identical lines are translated once, results are cached on disk (re-run = instant),
          lines that fail are retried, the order of the lines is never changed.
"""
import hashlib, json, os, re, threading, time
from concurrent.futures import ThreadPoolExecutor, as_completed
from pathlib import Path

import requests

GT = "https://translate.googleapis.com/translate_a/single"
LETTER = re.compile(r"[^\W\d_]", re.UNICODE)
CODES = {"Khmer": "km", "English": "en", "Chinese": "zh-CN", "Thai": "th", "Vietnamese": "vi", "Japanese": "ja",
         "Korean": "ko", "French": "fr", "Spanish": "es", "German": "de", "Russian": "ru", "Indonesian": "id",
         "Hindi": "hi", "Arabic": "ar"}

_CACHE_FILE = Path.home() / ".khmer_dubber" / "free_cache.json"
_CACHE, _CACHE_LOCK, _LOADED = {}, threading.Lock(), [False]
_LOCAL = threading.local()


def _session():
    s = getattr(_LOCAL, "s", None)
    if s is None:
        s = _LOCAL.s = requests.Session()
        s.headers.update({"User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 Chrome/124 Safari/537.36"})
        s.mount("https://", requests.adapters.HTTPAdapter(pool_connections=4, pool_maxsize=4))
    return s


def _load_cache():
    if _LOADED[0]:
        return
    _LOADED[0] = True
    try:
        _CACHE.update(json.loads(_CACHE_FILE.read_text(encoding="utf-8")))
    except Exception:
        pass


def _save_cache():
    try:
        _CACHE_FILE.parent.mkdir(exist_ok=True)
        if len(_CACHE) > 20000:                       # keep the file small
            for k in list(_CACHE)[:5000]:
                _CACHE.pop(k, None)
        _CACHE_FILE.write_text(json.dumps(_CACHE, ensure_ascii=False), encoding="utf-8")
    except Exception:
        pass


def _key(text, tl):
    return hashlib.md5(f"{tl}|{text}".encode("utf-8")).hexdigest()


def _gtx(text, tl, sl="auto"):
    r = _session().get(GT, params={"client": "gtx", "sl": sl, "tl": tl, "dt": "t", "q": text}, timeout=15)
    if r.status_code == 429:
        raise RuntimeError("429")
    r.raise_for_status()
    data = r.json()
    out = "".join(p[0] for p in (data[0] or []) if p and p[0])
    if not out.strip():
        raise RuntimeError("empty")
    return out


def _mymemory(text, tl, sl="auto"):
    src = "zh-CN" if sl == "auto" and re.search(r"[\u3400-\u9fff]", text) else ("en" if sl == "auto" else sl)
    r = _session().get("https://api.mymemory.translated.net/get", params={"q": text[:480], "langpair": f"{src}|{tl}"}, timeout=15)
    r.raise_for_status()
    out = (r.json().get("responseData") or {}).get("translatedText") or ""
    if not out.strip() or "MYMEMORY WARNING" in out.upper():
        raise RuntimeError("mymemory")
    return out


def _deep(text, tl, sl="auto"):
    from deep_translator import GoogleTranslator
    return GoogleTranslator(source=sl, target=tl).translate(text[:4500]) or ""


_KANA = re.compile(r"[\u3040-\u30ff]")
_HANGUL = re.compile(r"[\uac00-\ud7af]")
_HAN = re.compile(r"[\u3400-\u9fff]")


def detect_sl(text, sl="auto"):
    """Source language of one line. A chosen language wins; otherwise Chinese/Japanese/Korean are recognised by script."""
    if sl and sl != "auto":
        return sl
    if _KANA.search(text):
        return "ja"
    if _HANGUL.search(text):
        return "ko"
    if _HAN.search(text):
        return "zh-CN"
    return "auto"


def _gtx_batch(lines, tl, sl):
    """Several lines in ONE request. Raises unless exactly the same number of non-empty lines comes back."""
    r = _session().post(GT, params={"client": "gtx", "sl": sl, "tl": tl, "dt": "t"},
                        data={"q": "\n".join(lines)}, timeout=25)
    if r.status_code == 429:
        raise RuntimeError("429")
    r.raise_for_status()
    out = "".join(p[0] for p in (r.json()[0] or []) if p and p[0])
    parts = [x.strip() for x in out.split("\n")]
    if parts and not parts[-1]:
        parts.pop()
    if len(parts) != len(lines) or any(not x for x in parts):
        raise RuntimeError("count")
    return parts


def translate_one(text, tl, sl="auto"):
    """One line. Tries gtx (3x) -> deep-translator -> MyMemory. Returns '' if everything failed."""
    sl = detect_sl(text, sl)
    for attempt in range(3):
        try:
            return _gtx(text[:4500], tl, sl)
        except Exception:
            time.sleep(0.4 * (attempt + 1))
    for fn in (_deep, _mymemory):
        try:
            out = fn(text, tl, sl)
            if out and out.strip():
                return out
        except Exception:
            continue
    return ""


def _batch_job(lines, tl, sl):
    """lines -> list of translations ('' for a line that failed). Batch first, line by line only if the batch is refused."""
    for attempt in range(2):
        try:
            return _gtx_batch(lines, tl, sl)
        except Exception:
            time.sleep(0.3 * (attempt + 1))
    return [translate_one(t, tl, sl) for t in lines]


def _make_batches(todo, sl, max_lines=30, max_chars=2200):
    """Group lines by source language, keep story order, cap lines and characters per request."""
    groups = {}
    for t in todo:
        groups.setdefault(detect_sl(t, sl), []).append(t)
    batches = []
    for lang, items in groups.items():
        cur, size = [], 0
        for t in items:
            if cur and (len(cur) >= max_lines or size + len(t) > max_chars):
                batches.append((lang, cur)); cur, size = [], 0
            cur.append(t); size += len(t) + 1
        if cur:
            batches.append((lang, cur))
    return batches


def translate(texts, lang, progress=None, sl="auto", workers=12):
    """texts -> translated texts (same order, same length). Lines without letters are returned unchanged."""
    _load_cache()
    tl = CODES.get(lang, "en")
    out = list(texts)
    seen = {}
    for i, t in enumerate(texts):
        if not t or not t.strip() or not LETTER.search(t):
            continue
        t2 = " ".join(t.split())
        c = _CACHE.get(_key(t2, tl))
        if c:
            out[i] = c
        else:
            seen.setdefault(t2, []).append(i)
    todo = list(seen)
    total, done = len(texts), len(texts) - sum(len(v) for v in seen.values())
    if progress:
        progress(int(done / max(total, 1) * 100), f"Free translate {done}/{total}")
    if not todo:
        return out
    batches = _make_batches(todo, sl)
    ex = ThreadPoolExecutor(max_workers=max(1, min(workers, len(batches))))
    failed = []
    try:
        futs = {ex.submit(_batch_job, lines, tl, lg): lines for lg, lines in batches}
        for f in as_completed(futs):
            lines = futs[f]
            try:
                res = f.result()
            except Exception:
                res = [""] * len(lines)
            for t, r in zip(lines, res):
                r = (r or "").strip()
                if r:
                    with _CACHE_LOCK:
                        _CACHE[_key(t, tl)] = r
                    for i in seen[t]:
                        out[i] = r
                else:
                    failed.append(t)
                done += len(seen[t])
            if progress:
                progress(int(done / max(total, 1) * 100), f"Free translate {done}/{total}")
    finally:
        ex.shutdown(wait=False, cancel_futures=True)
    if failed:                                         # slow second chance, one by one (rate limit cool-down)
        time.sleep(2)
        for t in failed:
            r = translate_one(t, tl, sl)
            if r.strip():
                _CACHE[_key(t, tl)] = r.strip()
                for i in seen[t]:
                    out[i] = r.strip()
    _save_cache()
    return out


def ping():
    """True when the keyless translator is reachable."""
    try:
        return bool(_gtx("hello", "km"))
    except Exception:
        return False

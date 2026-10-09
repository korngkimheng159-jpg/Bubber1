"""TTS (Edge neural voices incl. Khmer, gTTS fallback), voice profiles, per-line clips, timeline mixing."""
import asyncio, hashlib, os, re, threading, time
import numpy as np, soundfile as sf
from .media import run
from .ai import run_parallel, CPS

SR = 24000
LAST_WARNINGS = []      # lines that could not be voiced in the last render (shown by the UI)
_EMOJI = re.compile("[\U00010000-\U0010ffff\u2600-\u27bf\ufe0f]")
VOICES = {
    "Khmer": {"male": "km-KH-PisethNeural", "female": "km-KH-SreymomNeural"},
    "English": {"male": "en-US-GuyNeural", "female": "en-US-JennyNeural"},
    "Chinese": {"male": "zh-CN-YunxiNeural", "female": "zh-CN-XiaoxiaoNeural"},
    "Thai": {"male": "th-TH-NiwatNeural", "female": "th-TH-PremwadeeNeural"},
    "Vietnamese": {"male": "vi-VN-NamMinhNeural", "female": "vi-VN-HoaiMyNeural"},
    "Japanese": {"male": "ja-JP-KeitaNeural", "female": "ja-JP-NanamiNeural"},
    "Korean": {"male": "ko-KR-InJoonNeural", "female": "ko-KR-SunHiNeural"},
    "French": {"male": "fr-FR-HenriNeural", "female": "fr-FR-DeniseNeural"},
    "Spanish": {"male": "es-ES-AlvaroNeural", "female": "es-ES-ElviraNeural"},
    "German": {"male": "de-DE-ConradNeural", "female": "de-DE-KatjaNeural"},
    "Russian": {"male": "ru-RU-DmitryNeural", "female": "ru-RU-SvetlanaNeural"},
    "Indonesian": {"male": "id-ID-ArdiNeural", "female": "id-ID-GadisNeural"},
    "Hindi": {"male": "hi-IN-MadhurNeural", "female": "hi-IN-SwaraNeural"},
    "Arabic": {"male": "ar-SA-HamedNeural", "female": "ar-SA-ZariyahNeural"},
}

# Voice profiles = base neural voice + pitch (semitones) + speaking rate (%)
PROFILES = {
    "Male 1": ("male", 0, 0), "Male 2": ("male", -2, -4), "Young Male": ("male", 2, 6),
    "Cocky Male Friend": ("male", 1, 10), "Narrator": ("male", -3, -8),
    "Actress 1": ("female", 0, 0), "Actress 2": ("female", 2, 5), "Mature Female": ("female", -2, -5),
}

def gender_of(profile):
    return PROFILES.get(profile, PROFILES["Actress 1"])[0]

def default_profile(gender):
    return "Male 1" if gender == "male" else "Actress 1"


_POOL = {"male": ["Male 1", "Male 2", "Young Male", "Narrator", "Cocky Male Friend"],
         "female": ["Actress 1", "Mature Female", "Actress 2"]}


def assign_voices(segs, min_lines=3):
    """Give every recurring speaker (S1, S2 ...) of the same gender a DIFFERENT voice profile, so two men (or two women)
    in one scene do not sound like the same person. The most talkative speaker keeps the default voice.
    Lines that already have a voice, or have no speaker label, are left alone. Returns {speaker: profile}."""
    count = {}
    for s in segs:
        sp = getattr(s, "speaker", "")
        if sp:
            count[(s.gender, sp)] = count.get((s.gender, sp), 0) + 1
    chosen = {}
    for g in ("male", "female"):
        ranked = sorted([(n, sp) for (gg, sp), n in count.items() if gg == g and n >= min_lines], reverse=True)
        for k, (_, sp) in enumerate(ranked):
            chosen[(g, sp)] = _POOL[g][k % len(_POOL[g])]
    for s in segs:
        sp = getattr(s, "speaker", "")
        if not s.voice and (s.gender, sp) in chosen:
            s.voice = chosen[(s.gender, sp)]
    return {sp: v for (g, sp), v in chosen.items()}


_LOCKS, _LOCKS_GUARD = {}, threading.Lock()


def _lock_for(key):
    """One lock per clip file: two identical lines voiced at the same moment must not write the same file."""
    with _LOCKS_GUARD:
        return _LOCKS.setdefault(key, threading.Lock())


_PUNCT = str.maketrans({"，": ", ", "。": ". ", "！": "! ", "？": "? ", "：": ": ", "；": "; ", "、": ", ", "…": ", ", "—": ", ", "~": " ",
                        "“": "", "”": "", "‘": "", "’": "", "\"": "", "（": " ", "）": " ", "(": " ", ")": " ", "《": "", "》": "",
                        "【": " ", "】": " ", "[": " ", "]": " ", "*": " ", "#": " ", "♪": " "})


FIT_LIMIT = {"Off": 1.0, "Soft": 1.35, "Hard": 1.7}      # max total speed-up per line (above ~1.7x Khmer sounds rushed)


def _clean(text):
    text = _EMOJI.sub("", str(text)).translate(_PUNCT).replace("\n", " ").replace("\r", " ")
    return re.sub(r"\s+", " ", text).strip()


def _speakable(text):
    return bool(re.search(r"[^\W_]", text, re.UNICODE))       # at least one letter / digit


def _silence(path, seconds):
    sf.write(path, np.zeros(int(max(seconds, 0.2) * SR), dtype="float32"), SR)
    return path


def synth(text, voice, path, rate_pct, lang, gender, use_gtts=False):
    """Edge TTS (4 tries) -> fallback to Google gTTS."""
    last = None
    if not use_gtts:
        try:
            import edge_tts
            async def go():
                await edge_tts.Communicate(text, voice, rate=f"{int(rate_pct):+d}%").save(path)
            for attempt in range(4):
                try:
                    if os.path.exists(path): os.remove(path)
                    asyncio.run(go())
                    if os.path.exists(path) and os.path.getsize(path) > 200:
                        return
                    last = RuntimeError("empty audio")
                except Exception as e:
                    last = e
                time.sleep(1.0 * (attempt + 1))
        except Exception as e:                                   # edge-tts not installed
            last = e
    try:
        from gtts import gTTS
        from .ai import LANGS
        gTTS(text, lang=LANGS.get(lang, "en").split("-")[0]).save(path)
        if gender == "male":   # gTTS has one voice: lower pitch to sound male
            tmp = path + ".m.mp3"
            run(["ffmpeg", "-y", "-i", path, "-af", "asetrate=24000*0.84,aresample=24000,atempo=1.19", tmp])
            os.replace(tmp, path)
    except Exception as e2:
        raise RuntimeError(f"TTS មិនបាន — ពិនិត្យ Internet ហើយ  pip install -U edge-tts gTTS\nEdge: {last} | gTTS: {e2}")


def _decode(mp3, wav):
    """mp3 -> mono 24 kHz wav. soundfile (libsndfile >= 1.1) decodes in-process = no ffmpeg process per line (much faster
    for 1000+ lines). Falls back to ffmpeg when soundfile cannot read mp3 or the sample rate differs."""
    try:
        data, sr = sf.read(mp3, dtype="float32")
        if sr == SR:
            if data.ndim > 1:
                data = data.mean(axis=1)
            sf.write(wav, data, SR)
            return
    except Exception:
        pass
    run(["ffmpeg", "-y", "-i", mp3, "-ac", "1", "-ar", str(SR), wav])


def _pitch_shift(wav, st):
    if not st:
        return
    f = 2 ** (st / 12)
    tmp = wav + ".p.wav"
    run(["ffmpeg", "-y", "-i", wav, "-af", f"asetrate={SR}*{f:.5f},aresample={SR},atempo={1 / f:.5f}", tmp])
    os.replace(tmp, wav)


def slot_for(segs, i):
    s = segs[i]
    nxt = segs[i + 1].start if i + 1 < len(segs) else s.end + 1.5
    # the voice must be finished when the next line starts (small gap kept), at most 1.2 s longer than the actor
    return max(s.end - s.start, min(nxt - s.start - 0.05, (s.end - s.start) + 1.2))


def _trim_silence(wav, thr=0.012, lead=0.04, tail=0.20):
    """Edge/gTTS add ~0.2-0.5 s of silence before and after every sentence. It delayed every line and ate the time slot,
    so the dub sounded slower than the actor. Cut it - but with a threshold RELATIVE to the voice and a longer tail, so the
    quiet end of a Khmer word is never chopped off (that sounded like the voice vanishing mid-sentence)."""
    data, sr = sf.read(wav, dtype="float32")
    if data.ndim > 1:
        data = data.mean(axis=1)
    peak = float(np.max(np.abs(data))) if data.size else 0.0
    loud = np.where(np.abs(data) > max(0.003, min(thr, peak * 0.02)))[0]
    if loud.size == 0:
        return len(data) / float(sr)
    a = max(0, int(loud[0]) - int(lead * sr))
    b = min(len(data), int(loud[-1]) + int(tail * sr))
    if b - a < len(data) - int(0.05 * sr):
        seg = data[a:b].copy()
        k = min(len(seg), int(0.02 * sr))
        if k > 1:
            seg[-k:] *= np.linspace(1.0, 0.0, k, dtype="float32")     # 20 ms fade-out: no click where it was cut
        sf.write(wav, seg, sr)
        return (b - a) / float(sr)
    return len(data) / float(sr)


def _ends_abruptly(wav):
    """True when the audio stops while the voice is still loud = the network dropped the end of the sentence.
    A complete sentence always decays into silence before the file ends."""
    try:
        data, sr = sf.read(wav, dtype="float32")
        if data.ndim > 1:
            data = data.mean(axis=1)
        if len(data) < sr * 0.4:
            return False
        peak = float(np.max(np.abs(data)))
        if peak < 1e-4:
            return False
        tail = data[-int(0.03 * sr):]
        loud = data[np.abs(data) > peak * 0.1]
        rms_t = float(np.sqrt(np.mean(tail ** 2)))
        rms_l = float(np.sqrt(np.mean(loud ** 2))) if loud.size else 0.0
        return rms_l > 0 and rms_t > 0.3 * rms_l
    except Exception:
        return False


def _looks_truncated(text, dur, rate, lang):
    """The network can drop the end of a sentence without any error. A sentence that is far shorter than its
    text needs (at the chosen speed) was cut: ask again."""
    n = len(re.sub(r"\s", "", text))
    expect = n / (CPS.get(lang, 14) * max(0.3, 1 + rate / 100.0))
    return expect > 1.6 and dur < expect * 0.4


def _voice_to_wav(text, voice, mp3, wav, rate, lang, gender, use_gtts, st):
    """Voice one line. Returns (seconds, complete). If the sentence looks cut (too short for its text, or the audio stops
    while the voice is still loud) it is asked again (up to 4 takes) and the LONGEST take is kept."""
    best, dur, short = None, 0.0, False
    for attempt in range(4):
        synth(text, voice, mp3, rate, lang, gender, use_gtts)
        _decode(mp3, wav)
        _pitch_shift(wav, st)
        cut = (not use_gtts) and _ends_abruptly(wav)
        dur = _trim_silence(wav)
        short = _looks_truncated(text, dur, rate, lang)
        if not (cut or short):
            return dur, True
        if best is None or dur > best[0]:
            d, sr = sf.read(wav, dtype="float32"); best = (dur, d, sr)
        if cut and not short and attempt >= 1:             # only the weak "abrupt end" signal: one extra take is enough
            break
        time.sleep(0.4 + 0.4 * attempt)
    if best and best[0] >= dur:
        sf.write(wav, best[1], best[2]); dur = best[0]
    return dur, False


def _split_text(text):
    """Cut a long line at the space/phrase break nearest to the middle -> (a, b) or None."""
    parts = [p for p in re.split(r"(?<=[\s\u200b])", text) if p]
    if len(parts) < 2:
        return None
    total, acc, best = len(text), 0, None
    for k, p in enumerate(parts[:-1]):
        acc += len(p)
        if best is None or abs(acc - total / 2) < abs(best[0] - total / 2):
            best = (acc, k)
    k = best[1]
    a, b = "".join(parts[:k + 1]).strip(), "".join(parts[k + 1:]).strip()
    return (a, b) if a and b else None


def _voice_split(text, voice, mp3, wav, rate, lang, gender, st):
    """Edge sometimes stops in the MIDDLE of a long sentence. Voice the two halves separately and join them:
    each half is short, so it is not cut. Returns (seconds, complete) or None."""
    sp = _split_text(text)
    if not sp:
        return None
    arrs, ok = [], True
    for k, part in enumerate(sp):
        w = wav + f".p{k}.wav"
        synth(part, voice, mp3, rate, lang, gender, False)
        _decode(mp3, w); _pitch_shift(w, st)
        d = _trim_silence(w)
        if _looks_truncated(part, d, rate, lang) or _ends_abruptly(w):
            ok = False
        a, _ = sf.read(w, dtype="float32"); arrs.append(a if a.ndim == 1 else a.mean(axis=1))
        try: os.remove(w)
        except OSError: pass
    joined = np.concatenate([arrs[0], np.zeros(int(0.07 * SR), dtype="float32"), arrs[1]])
    sf.write(wav, joined, SR)
    return len(joined) / float(SR), ok


def _normalize(wav, target=0.12):
    """Every line about equally loud (rate/pitch changes and gTTS vs Edge made some lines whisper) - never clips."""
    a, sr = sf.read(wav, dtype="float32")
    if a.ndim > 1:
        a = a.mean(axis=1)
    if a.size == 0:
        return
    peak = float(np.max(np.abs(a)))
    voiced = a[np.abs(a) > max(0.01, peak * 0.1)]
    if voiced.size < 100 or peak <= 0:
        return
    rms = float(np.sqrt(np.mean(voiced ** 2)))
    g = max(0.7, min(1.6, target / max(rms, 1e-4)))
    g = min(g, 0.97 / peak)
    if abs(g - 1.0) > 0.05:
        sf.write(wav, a * g, sr)


def make_clip(seg, lang, workdir, o, slot, force=False):
    """One voiced line -> wav. o: speed, pitch(st), reverb, fit(Off/Soft/Hard), gtts.
    If the actor speaks fast (short slot) the AI voice is made faster to finish in time:
    first the voice itself is asked to speak faster (natural), then FFmpeg time-stretch for what is left."""
    profile = seg.voice or default_profile(seg.gender)
    gender, st_off, rate_off = PROFILES.get(profile, PROFILES["Actress 1"])
    voice = VOICES.get(lang, VOICES["English"])[gender]
    rate = max(-50, min(100, int(round((o["speed"] - 1) * 100)) + rate_off))
    st = o["pitch"] + st_off
    text = _clean(seg.text)
    base_rate = rate
    limit0 = FIT_LIMIT.get(o["fit"], 1.35)
    n_chars = len(re.sub(r"\s", "", text))
    if limit0 > 1 and slot > 0.3 and n_chars:
        est = n_chars / (CPS.get(lang, 14) * max(0.3, 1 + rate / 100.0))      # seconds at the normal speed
        if est > slot * 1.1:                                                   # ask the voice to talk faster from the start
            f0 = min(est / slot, limit0, 1.6)
            rate = max(-50, min(100, rate + int(round((f0 - 1) * 100))))
    key = hashlib.md5(f"{lang}|{profile}|{text}|{rate}|{st}|{o['reverb']}|{o['fit']}|{round(slot, 1)}|{o['gtts']}".encode()).hexdigest()[:16]
    d = os.path.join(workdir, "clips"); os.makedirs(d, exist_ok=True)
    wav, mp3 = os.path.join(d, key + ".wav"), os.path.join(d, key + ".mp3")
    with _lock_for(key):
        return _make_clip_locked(text, voice, gender, rate, st, slot, o, lang, wav, mp3, force, base_rate)


def _make_clip_locked(text, voice, gender, rate, st, slot, o, lang, wav, mp3, force, base_rate=None):
    if os.path.exists(wav) and not force and not os.path.exists(wav + ".bad"):
        return wav
    if not _speakable(text):                       # "...", "♪" etc: nothing to say
        return _silence(wav, min(max(slot, 0.3), 3.0))
    dur, complete = _voice_to_wav(text, voice, mp3, wav, rate, lang, gender, o["gtts"], st)
    if not complete and not o["gtts"] and len(text) >= 24:       # still cut after several takes -> voice it in two halves
        try:
            r = _voice_split(text, voice, mp3, wav, rate, lang, gender, st)
            if r:
                dur, complete = r
        except Exception:
            pass
    if complete:
        if os.path.exists(wav + ".bad"): os.remove(wav + ".bad")
    else:
        open(wav + ".bad", "w").close()
    limit = FIT_LIMIT.get(o["fit"], 1.35)
    base_rate = rate if base_rate is None else base_rate
    applied = (1 + rate / 100.0) / (1 + base_rate / 100.0)      # speed-up already asked from the voice
    if limit > 1 and slot > 0.3 and dur > slot * 1.03:
        f = min(dur / slot, max(1.0, limit / applied))
        if not o["gtts"] and f > 1.3:             # big speed-up only: re-ask the neural voice (small ones use FFmpeg = no 2nd network call = faster)
            try:
                rate2 = max(-50, min(100, rate + int(round((f - 1) * 100))))
                dur, _ok2 = _voice_to_wav(text, voice, mp3, wav, rate2, lang, gender, False, st)
                applied = (1 + rate2 / 100.0) / (1 + base_rate / 100.0)
            except Exception:
                dur, _ok2 = _voice_to_wav(text, voice, mp3, wav, rate, lang, gender, o["gtts"], st)
        if dur > slot * 1.03:                      # still too long: time-stretch the rest (never above the limit overall)
            f2 = min(dur / slot, max(1.0, limit / applied))
            if f2 > 1.02:
                tmp = wav + ".t.wav"
                run(["ffmpeg", "-y", "-i", wav, "-filter:a", f"atempo={f2:.3f}", "-ar", str(SR), tmp])
                os.replace(tmp, wav)
    try:
        _normalize(wav)
    except Exception:
        pass
    if o["reverb"]:
        tmp = wav + ".r.wav"
        run(["ffmpeg", "-y", "-i", wav, "-af", "aecho=0.8:0.88:60:0.35", tmp])
        os.replace(tmp, wav)
    return wav


def render_clips(segs, idx, lang, workdir, o, progress, force=False, workers=None):
    """Voice every line in idx. Lines are voiced in PARALLEL (default 5 at a time), lines that failed are retried one by one - 1 hour of dialogue in minutes."""
    global LAST_WARNINGS
    if not idx:
        return {}
    workers = workers or o.get("workers") or 6      # Edge throttles heavy parallel use -> silent lines
    d = os.path.join(workdir, "clips"); os.makedirs(d, exist_ok=True)

    def one(i):
        slot = slot_for(segs, i)
        try:
            return i, make_clip(segs[i], lang, workdir, o, slot, force), None
        except Exception as e:                     # keep going: this line stays silent
            sil = os.path.join(d, f"silent_{int(slot * 10)}.wav")
            with _lock_for(sil):
                if not os.path.exists(sil):
                    _silence(sil, min(max(slot, 0.3), 3.0))
            return i, sil, str(e)

    progress(0, f"Generating voice 0 of {len(idx)}")
    res = run_parallel(one, [(i,) for i in idx], workers,
                       lambda dn, tot: progress(int(dn / tot * 100), f"Generating voice {dn} of {tot}"))
    out = {i: w for i, w, _ in res}
    bad = {i: m for i, _, m in res if m}
    if bad and len(bad) == len(idx):               # nothing worked (no internet / edge-tts broken): show the real reason
        raise RuntimeError(next(iter(bad.values())))
    for rnd in range(2):                           # rescue: the servers refused some lines while busy -> one by one, slowly
        if not bad:
            break
        progress(95, f"Retry {len(bad)} lines…")
        time.sleep(2.0 + 2 * rnd)
        for i in sorted(bad):
            try:
                out[i] = make_clip(segs[i], lang, workdir, o, slot_for(segs, i), True)
                bad.pop(i)
            except Exception as e:
                bad[i] = str(e)
    bad = sorted(bad.items())
    LAST_WARNINGS = [f"ជួរទី {i + 1}: {m.splitlines()[0][:120]}" for i, m in sorted(bad)]
    progress(100, f"Generated {len(idx) - len(bad)} voices" + (f" — ⚠ {len(bad)} ជួរគ្មានសំឡេង" if bad else ""))
    return out


def clip_seconds(wav):
    info = sf.info(wav)
    return info.frames / float(info.samplerate)


def plan_starts(items, end_sync=False, gap=0.06):
    """items = [(start_s, end_s, n_samples)] sorted by start  ->  [(start_sample, speedup)].
    A line NEVER starts before the previous one has finished (no more voices on top of each other). When a line does not
    fit before the next one starts it is sped up (max 1.5x, on top of the Auto-Fit); a late line (>1.5 s behind the actor)
    is sped up a bit more so the dub catches up with the video."""
    out, cursor, G = [], 0, int(gap * SR)
    for k, (a, b, n) in enumerate(items):
        st = int(a * SR)
        if end_sync:
            st = max(0, int(b * SR) - n)
        else:
            over = n / float(SR) - (b - a)
            if over > 0.05:
                st = max(0, st - int(min(over, 0.35) * SR))
        st = max(st, cursor)
        f = 1.0
        if not end_sync:
            if k + 1 < len(items):
                avail = int(items[k + 1][0] * SR) - st - G
                if avail > int(0.5 * SR) and n > avail * 1.03:
                    f = min(n / float(avail), 1.5)
            if st - int(a * SR) > int(1.5 * SR):
                f = max(f, 1.25)
        out.append((st, f))
        cursor = st + int(n / f) + G
    return out


def _compress(wav, f):
    """Speed a finished line up by f (pitch kept) - cached per factor."""
    tmp = f"{wav}.c{int(f * 100)}.wav"
    if not (os.path.exists(tmp) and os.path.getmtime(tmp) >= os.path.getmtime(wav)):
        run(["ffmpeg", "-y", "-i", wav, "-filter:a", f"atempo={f:.3f}", "-ar", str(SR), tmp])
    return tmp


def compose(pairs, workdir, total, vol, end_sync):
    """Place every voiced line on the timeline at its start time. A line that would overlap the previous one is
    delayed a little (max 0.8 s) so two voices never talk over each other.
    STREAMING: the result is written block by block, so a 2-hour dub needs only ~40 MB of RAM."""
    pairs = sorted([(s, w) for s, w in pairs if w and os.path.exists(w)], key=lambda x: x[0].start)
    end = max([s.end for s, _ in pairs], default=0)
    lens = [sf.info(w).frames for _, w in pairs]
    plan = plan_starts([(s.start, s.end, n) for (s, _), n in zip(pairs, lens)], end_sync)
    place = []
    for (s, wav), n, (st, f) in zip(pairs, lens, plan):
        if f > 1.02:                       # does not fit before the next line: speed it up instead of overlapping
            try:
                wav = _compress(wav, f); n = sf.info(wav).frames
            except Exception:
                pass
        place.append((st, wav, n))
    place.sort(key=lambda x: x[0])
    total_samples = int((max(total, end) + 3) * SR)
    if place:                              # the LAST ending line (not just the last starting one) must never be cut
        total_samples = max(total_samples, max(p[0] + p[2] for p in place) + int(0.5 * SR))
    BLOCK = 60 * SR
    buf = np.zeros(BLOCK + 120 * SR, dtype=np.float32); base = 0
    out = os.path.join(workdir, "dub.wav")
    with sf.SoundFile(out, "w", samplerate=SR, channels=1, subtype="PCM_16") as f:
        def flush():
            nonlocal base
            f.write(np.clip(buf[:BLOCK], -1, 1)); buf[:-BLOCK] = buf[BLOCK:]; buf[-BLOCK:] = 0; base += BLOCK
        for st, wav, n in place:
            st = max(st, base)
            while st + n > base + len(buf):
                flush()
            a, _ = sf.read(wav, dtype="float32")
            if a.ndim > 1:
                a = a.mean(axis=1)
            a = a.copy(); fi, fo = min(len(a) // 4, int(0.012 * SR)), min(len(a) // 3, int(0.045 * SR))
            if fi > 1: a[:fi] *= np.linspace(0.0, 1.0, fi, dtype=np.float32)
            if fo > 1: a[-fo:] *= np.linspace(1.0, 0.0, fo, dtype=np.float32)
            buf[st - base: st - base + len(a)] += a[: len(buf) - (st - base)] * vol
        while base + BLOCK < total_samples:
            flush()
        left = total_samples - base
        f.write(np.clip(buf[:max(left, 0)], -1, 1))
    return out


def wave_peaks(wav, points=20000):
    """(peaks 0..1, seconds) for the timeline, read in blocks (never loads a 2-hour file at once)."""
    with sf.SoundFile(wav) as f:
        frames, sr = f.frames, f.samplerate
        step = max(frames // points, 1)
        peaks = []
        while True:
            a = f.read(step * 4000, dtype="float32")
            if len(a) == 0:
                break
            if a.ndim > 1:
                a = a.mean(axis=1)
            m = len(a) // step * step
            if m:
                peaks.extend(np.abs(a[:m]).reshape(-1, step).max(axis=1).tolist())
            if len(a) < step * 4000:
                break
    pk = np.asarray(peaks, dtype="float32")
    if pk.size == 0:
        return np.zeros(1, dtype="float32"), frames / float(sr)
    return pk / (pk.max() or 1.0), frames / float(sr)


_CJK = re.compile(r"[\u3400-\u9fff\uf900-\ufaff\u3040-\u30ff\uac00-\ud7af]")
_KHM = re.compile(r"[\u1780-\u17ff]")


def untranslated(text, lang):
    """True when the line is still in the source language (Chinese...) - a Khmer voice cannot read it, so the dub would be silent."""
    if lang in ("Chinese", "Japanese", "Korean") or not _CJK.search(text):
        return False
    return not _KHM.search(text) if lang == "Khmer" else not re.search(r"[A-Za-z\u0e00-\u0e7f\u0400-\u04ff]", text)


def _translate_leftovers(segs, idx, lang, progress):
    """Lines that still hold Chinese are translated now (free translator) so they get a voice instead of silence."""
    bad = [i for i in idx if untranslated(segs[i].text, lang)]
    if not bad:
        return []
    progress(2, f"បកប្រែ {len(bad)} ជួរដែលនៅជាភាសាចិន…")
    try:
        from . import freetr
        res = freetr.translate([segs[i].text for i in bad], lang, None)
        for i, t in zip(bad, res):
            if t and t.strip() and not untranslated(t, lang):
                segs[i].text = t.strip()
    except Exception:
        pass
    return [i for i in bad if untranslated(segs[i].text, lang)]


def render_dub(segs, lang, workdir, total, o, progress, force=False, shorten=None):
    """shorten(items) -> {index: shorter text}: called for lines whose voice is still longer than the time available
    after speed-up. segs[i].text is updated in place so the caller can refresh the table."""
    global LAST_WARNINGS
    idx = [i for i, s in enumerate(segs) if s.text.strip()]
    still = _translate_leftovers(segs, idx, lang, progress)          # Chinese left over -> translate, never leave it silent
    idx = [i for i in idx if i not in still]
    clips = render_clips(segs, idx, lang, workdir, o, lambda p, m="": progress(int(p * 0.65), m), force)
    warns = [f"ជួរទី {i + 1}: នៅជាភាសាចិន មិនទាន់បកប្រែ (ពិនិត្យ Internet / បកប្រែឡើងវិញ)" for i in still] + list(LAST_WARNINGS)
    LAST_WARNINGS = list(warns)
    if shorten and o.get("fit", "Soft") != "Off":
        for rnd in range(2):                                   # round 2 only for lines that are STILL too long after round 1
            over = []
            for i, w in clips.items():
                slot = slot_for(segs, i)
                try:
                    need = clip_seconds(w)
                except Exception:
                    continue
                if slot >= 0.6 and need > slot * (1.08 if rnd == 0 else 1.15):
                    over.append((i, segs[i].text, slot, need))
            if not over:
                break
            progress(68 + rnd, f"កំពុងកាត់បន្ថយប្រយោគវែង {len(over)} ជួរ…")
            try:
                new = shorten(over) or {}
            except Exception:
                new = {}                                       # no key / no internet: keep the lines as they are
            redo = []
            for i, t in new.items():
                if 0 <= i < len(segs) and t.strip() and t.strip() != segs[i].text.strip():
                    segs[i].text = t.strip(); redo.append(i)
            if not redo:
                break
            clips.update(render_clips(segs, redo, lang, workdir, o, lambda p, m="": progress(70 + int(p * 0.2), m)))
            warns += LAST_WARNINGS
            LAST_WARNINGS = warns
    wav = compose([(segs[i], w) for i, w in clips.items()], workdir, total, o["vol"], o["end_sync"])
    progress(100, "Dub ready")
    return wav, clips
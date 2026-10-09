import os, re, subprocess, shutil, sys, glob

_BAR = re.compile(r"\d+%\||\[\d+:\d+<|it/s|seconds/s|frames/s|\|#{3,}")


def _clean_err(text):
    """Progress bars (tqdm of demucs/whisper...) filled the error box and hid the real reason: keep only real lines."""
    lines = [l.strip() for l in re.split(r"[\r\n]+", text or "") if l.strip() and not _BAR.search(l)]
    return "\n".join(lines[-14:])[-1500:]


NOWIN = 0x08000000 if os.name == "nt" else 0          # CREATE_NO_WINDOW: no flashing console per ffmpeg call in the .exe


def run(cmd, cwd=None):
    p = subprocess.run(cmd, capture_output=True, text=True, cwd=cwd, encoding="utf-8", errors="ignore", creationflags=NOWIN)
    if p.returncode:
        msg = _clean_err(p.stderr)
        if not msg:
            msg = f"process stopped (code {p.returncode}) - ច្រើនតែអស់ RAM / អស់ទំហំថាស"
        raise RuntimeError(f"{os.path.basename(str(cmd[0]))} error:\n{msg}")
    return p

def has_ffmpeg():
    return bool(shutil.which("ffmpeg") and shutil.which("ffprobe"))

def duration(path):
    p = run(["ffprobe", "-v", "error", "-show_entries", "format=duration", "-of", "default=nw=1:nk=1", path])
    return float(p.stdout.strip() or 0)

def extract_audio(src, out, sr=16000):
    run(["ffmpeg", "-y", "-i", src, "-vn", "-ac", "1", "-ar", str(sr), out])
    return out

def _silence_mids(src, noise_db=-32, min_sil=0.30):
    """[(middle_time, length)] of every pause in the audio (used to cut chunks between sentences, never inside one)."""
    p = subprocess.run(["ffmpeg", "-hide_banner", "-nostats", "-i", src, "-vn", "-af",
                        f"silencedetect=noise={noise_db}dB:d={min_sil}", "-f", "null", "-"],
                       capture_output=True, text=True, encoding="utf-8", errors="ignore", creationflags=NOWIN)
    out, start = [], None
    for line in p.stderr.splitlines():
        a = re.search(r"silence_start:\s*(-?[\d.]+)", line)
        b = re.search(r"silence_end:\s*([\d.]+)", line)
        if a:
            start = max(0.0, float(a.group(1)))
        if b and start is not None:
            e = float(b.group(1)); out.append(((start + e) / 2.0, e - start)); start = None
    return out


def chunk_plan(total, chunk, pauses, window=0.22):
    """[(t0, t1)]: every cut is moved to the longest pause near the nominal boundary (+-window*chunk).
    A fixed cut (old behaviour) sliced sentences in half -> half-sentences were transcribed / voiced."""
    if total <= chunk * 1.15:
        return [(0.0, total)]
    cuts, t = [0.0], 0.0
    while total - t > chunk * 1.15:
        target = t + chunk
        lo, hi = target - chunk * window, target + chunk * window
        cand = [(ln - abs(m - target) * 0.02, m) for m, ln in pauses if lo <= m <= hi and m > t + chunk * 0.5]
        t = max(cand)[1] if cand else target
        cuts.append(t)
    cuts.append(total)
    return list(zip(cuts[:-1], cuts[1:]))


def split_audio(src, workdir, chunk=600):
    """Small mono mp3 chunks (32kbps) that fit API upload limits, cut at pauses. Returns [(path, offset_seconds)]."""
    d = os.path.join(workdir, "chunks")
    shutil.rmtree(d, ignore_errors=True); os.makedirs(d)
    total = duration(src)
    try:
        plan = chunk_plan(total, chunk, _silence_mids(src))
    except Exception:
        plan = chunk_plan(total, chunk, [])
    out = []
    for i, (a, b) in enumerate(plan):
        path = os.path.join(d, f"c_{i:03d}.mp3")
        cmd = ["ffmpeg", "-y", "-i", src, "-vn", "-ac", "1", "-ar", "16000", "-b:a", "32k", "-ss", f"{a:.3f}"]
        if len(plan) > 1:
            cmd += ["-t", f"{b - a:.3f}"]
        run(cmd + [path])
        out.append((path, a))
    return out

def _separate_once(audio, outdir):
    """Vocal Remover using Demucs (pip install demucs). Returns (vocals.wav, no_vocals.wav)."""
    from . import device
    base_cmd = [sys.executable, "-m", "demucs", "--two-stems=vocals", "-o", outdir]
    try:
        done = False
        if device.torch_gpu():                            # auto: only a modern card with enough VRAM; CPU otherwise
            try:
                run(base_cmd + ["-d", "cuda", "--segment", "6", audio]); done = True
            except RuntimeError as e:
                if "No module named" in str(e):
                    raise
        if not done:
            run(base_cmd + ["-d", "cpu", "-j", str(max(1, min(4, (os.cpu_count() or 2) // 2))), audio])
    except RuntimeError as e:
        if "No module named" in str(e):
            raise RuntimeError("សូម install demucs មុន:  pip install demucs")
        raise
    stem = os.path.splitext(os.path.basename(audio))[0]
    base = glob.glob(os.path.join(outdir, "*", stem))[0]
    return os.path.join(base, "vocals.wav"), os.path.join(base, "no_vocals.wav")

def _concat_wavs(paths, out):
    import soundfile as sf
    with sf.SoundFile(paths[0]) as f0:
        sr, ch = f0.samplerate, f0.channels
    with sf.SoundFile(out, "w", samplerate=sr, channels=ch, subtype="PCM_16") as w:
        for p in paths:
            with sf.SoundFile(p) as f:
                while True:
                    a = f.read(sr * 30, dtype="float32")
                    if len(a) == 0:
                        break
                    w.write(a)


def separate_vocals(audio, outdir, chunk_min=8, progress=None):
    """Vocal Remover. A long video (83 min) in ONE demucs run needs many GB of RAM and died half way: it is cut into
    `chunk_min` minute pieces, each piece is separated alone (RAM stays small) and the results are joined. A re-run
    continues from the last finished piece. Returns (vocals.wav, no_vocals.wav)."""
    if getattr(sys, "frozen", False):                      # the packaged .exe cannot start `python -m demucs`
        raise RuntimeError("Demucs មិនមានក្នុងកំណែ .exe — ប្រើ Keep Music (លឿន) ជំនួស")
    total = duration(audio)
    size = chunk_min * 60
    if total <= size * 1.3:
        return _separate_once(audio, outdir)
    os.makedirs(outdir, exist_ok=True)
    n = int(total // size) + (1 if total % size > 1 else 0)
    voc, bgm = [], []
    for k in range(n):
        if progress:
            progress(int(k / n * 100), f"Vocal remover {k + 1}/{n}")
        pv = os.path.join(outdir, f"part_{k:03d}_vocals.wav")
        pb = os.path.join(outdir, f"part_{k:03d}_no_vocals.wav")
        if not (os.path.exists(pv) and os.path.exists(pb)):
            src = os.path.join(outdir, f"part_{k:03d}.wav")
            run(["ffmpeg", "-y", "-ss", f"{k * size}", "-t", f"{size}", "-i", audio, "-vn", "-ar", "44100", "-ac", "2", src])
            tmp = os.path.join(outdir, f"d{k:03d}")
            v, b = _separate_once(src, tmp)
            shutil.move(v, pv); shutil.move(b, pb)
            shutil.rmtree(tmp, ignore_errors=True)
            try: os.remove(src)
            except OSError: pass
        voc.append(pv); bgm.append(pb)
    fin = os.path.join(outdir, "joined"); os.makedirs(fin, exist_ok=True)
    ov, ob = os.path.join(fin, "vocals.wav"), os.path.join(fin, "no_vocals.wav")
    _concat_wavs(voc, ov); _concat_wavs(bgm, ob)
    for p in voc + bgm:
        try: os.remove(p)
        except OSError: pass
    return ov, ob


def _mean_db(video, af):
    p = run(["ffmpeg", "-hide_banner", "-i", video, "-t", "120", "-vn", "-af", af + ",volumedetect", "-f", "null", "-"])
    m = re.search(r"mean_volume:\s*(-?[\d.]+) dB", p.stderr or "")
    return float(m.group(1)) if m else -99.0


def mute_voices(video, out_wav, spans, ramp=0.07, pad=0.10):
    """Keep-music, the precise way: the original soundtrack is untouched BETWEEN the lines, and only while an actor speaks
    (start..end of each line, from the transcription) the voice is removed: centre-cancel keeps wide-stereo music/ambience;
    mono-like sources are simply buried. Smooth 70 ms ramps, streamed in 30 s blocks (a 2-hour film needs little RAM)."""
    import numpy as np, soundfile as sf
    tmp = out_wav + ".src.wav"
    run(["ffmpeg", "-y", "-hide_banner", "-i", video, "-vn", "-ar", "44100", "-ac", "2", tmp])
    merged = []
    for a, b in sorted((max(0.0, a - pad), b + pad) for a, b in spans if b > a):
        if merged and a <= merged[-1][1]:
            merged[-1] = (merged[-1][0], max(merged[-1][1], b))
        else:
            merged.append((a, b))
    with sf.SoundFile(tmp) as src, sf.SoundFile(out_wav, "w", samplerate=src.samplerate, channels=2, subtype="PCM_16") as dst:
        sr = src.samplerate; ri = max(1, int(ramp * sr)); pos = 0
        starts = np.array([int(a * sr) for a, _ in merged]); ends = np.array([int(b * sr) for _, b in merged])
        while True:
            a = src.read(sr * 30, dtype="float32")
            if len(a) == 0:
                break
            n = len(a); env = np.zeros(n, dtype=np.float32); t = np.arange(pos, pos + n)
            for k in np.where((ends + ri > pos) & (starts - ri < pos + n))[0]:
                e = np.clip(np.minimum((t - (starts[k] - ri)) / ri, ((ends[k] + ri) - t) / ri), 0, 1)
                env = np.maximum(env, e.astype(np.float32))
            cen = 0.5 * (a[:, 0] - a[:, 1])
            if np.sqrt(np.mean(cen ** 2) + 1e-12) > 0.18 * np.sqrt(np.mean(a ** 2) + 1e-12):
                speech = np.stack([cen, -cen], axis=1) * 1.2          # wide music / ambience survives
            else:
                speech = a * 0.06                                      # nothing but the voice: bury it
            dst.write(np.clip(a * (1 - env)[:, None] + speech * env[:, None], -1, 1)); pos += n
    try: os.remove(tmp)
    except OSError: pass
    return out_wav


def fast_bgm(video, dub_wav, out_wav, spans=None):
    """INSTANT 'Keep Music' (seconds, no AI model): the original soundtrack with the centre channel cancelled (voices are
    usually centred, music/ambience is wide) and ducked under the AI voice. Mono-like sources (cancelling leaves nothing)
    use ducking only. Demucs stays available (config music_mode = ai) for a cleaner but very slow result."""
    video, dub_wav, out_wav = map(os.path.abspath, (video, dub_wav, out_wav))
    if spans:                                              # precise: mute the voices only while the actors speak
        try:
            return mute_voices(video, out_wav, spans)
        except Exception:
            pass
    pan = "pan=stereo|c0=0.5*c0-0.5*c1|c1=0.5*c1-0.5*c0,"
    try:
        use_pan = _mean_db(video, pan.rstrip(",")) > _mean_db(video, "anull") - 22
    except Exception:
        use_pan = False
    pre = pan if use_pan else ""
    fc = (f"[0:a]{pre}aresample=44100,aformat=channel_layouts=stereo[m];"
          f"[1:a]aresample=44100,aformat=channel_layouts=stereo,apad[sc];"
          f"[m][sc]sidechaincompress=threshold=0.012:ratio=14:attack=8:release=350:makeup=1[bg]")
    run(["ffmpeg", "-y", "-hide_banner", "-i", video, "-i", dub_wav, "-filter_complex", fc, "-map", "[bg]",
         "-t", f"{duration(video):.3f}", "-c:a", "pcm_s16le", "-ar", "44100", out_wav])
    return out_wav


def mix_export(video, dub_wav, out, bg=None, bg_vol=0.8, srt_path=None, font="Khmer UI", size=22):
    video, dub_wav, out = map(os.path.abspath, (video, dub_wav, out))
    cmd = ["ffmpeg", "-y", "-i", video, "-i", dub_wav]
    if bg:
        cmd += ["-i", os.path.abspath(bg), "-filter_complex",
                f"[2:a]volume={bg_vol}[b];[1:a][b]amix=inputs=2:duration=longest:normalize=0[a]"]
        amap = "[a]"
    else:
        amap = "1:a"
    cmd += ["-map", "0:v:0", "-map", amap]
    cwd = None
    if srt_path:  # copy next to the wav so the subtitles filter can use a simple relative name
        cwd = os.path.dirname(dub_wav)
        shutil.copy(srt_path, os.path.join(cwd, "subs.srt"))
        style = f"FontName={font},FontSize={size},Outline=2,Shadow=1,MarginV=30"
        cmd += ["-vf", f"subtitles=subs.srt:force_style='{style}'", "-c:v", "libx264", "-preset", "veryfast", "-crf", "20"]
    else:
        cmd += ["-c:v", "copy"]
    cmd += ["-c:a", "aac", "-b:a", "192k", "-shortest", out]
    run(cmd, cwd=cwd)
    return out


def extract_frames(video, region, step, workdir):
    """Grab one JPEG crop every `step` seconds. region=(x,y,w,h) in source pixels or None for full frame.
    Returns [(time_seconds, jpg_path), ...]."""
    d = os.path.join(workdir, "ocr_frames"); shutil.rmtree(d, ignore_errors=True); os.makedirs(d)
    vf = f"crop={region[2]}:{region[3]}:{region[0]}:{region[1]}," if region else ""
    run(["ffmpeg", "-y", "-i", video, "-vf", f"{vf}fps=1/{step}", "-q:v", "3", os.path.join(d, "f_%05d.jpg")])
    files = sorted(glob.glob(os.path.join(d, "f_*.jpg")))
    return [(i * step, p) for i, p in enumerate(files)]


# ------------------------------------------------------------------ video info
def has_video(path):
    try:
        p = run(["ffprobe", "-v", "error", "-select_streams", "v:0", "-show_entries", "stream=codec_type",
                 "-of", "csv=p=0", path])
        return "video" in p.stdout
    except Exception:
        return False


def video_size(path):
    """(width, height) of the first video stream."""
    p = run(["ffprobe", "-v", "error", "-select_streams", "v:0", "-show_entries", "stream=width,height",
             "-of", "csv=s=x:p=0", path])
    line = (p.stdout.strip().splitlines() or [""])[0]
    w, h = [int(x) for x in line.split("x")[:2]]
    return w, h


# ------------------------------------------------------------------ encoders (GPU makes a 2-hour export 5-10x faster)
_ENC_CACHE = []


def available_encoders():
    """['cpu', 'nvenc', 'qsv', 'amf'] - those listed by FFmpeg (the export falls back to CPU if the GPU refuses)."""
    if not _ENC_CACHE:
        found = ["cpu"]
        try:
            txt = run(["ffmpeg", "-hide_banner", "-encoders"]).stdout
            for key, name in (("nvenc", "h264_nvenc"), ("qsv", "h264_qsv"), ("amf", "h264_amf")):
                if name in txt:
                    found.append(key)
        except Exception:
            pass
        _ENC_CACHE.extend(found)
    return list(_ENC_CACHE)


def _venc_args(enc, quality):
    crf = {"turbo": "26", "fast": "23", "balanced": "20", "best": "17"}.get(quality, "23")
    preset = {"turbo": "ultrafast", "fast": "superfast", "balanced": "faster", "best": "medium"}.get(quality, "superfast")
    if enc == "nvenc":
        nv = {"turbo": "p1", "fast": "p3", "balanced": "p5", "best": "p6"}.get(quality, "p3")
        return ["-c:v", "h264_nvenc", "-preset", nv, "-rc", "vbr", "-cq", crf, "-b:v", "0", "-pix_fmt", "yuv420p"]
    if enc == "qsv":
        return ["-c:v", "h264_qsv", "-preset", "veryfast", "-global_quality", crf, "-pix_fmt", "nv12"]
    if enc == "amf":
        return ["-c:v", "h264_amf", "-quality", "quality", "-rc", "cqp", "-qp_i", crf, "-qp_p", crf, "-pix_fmt", "yuv420p"]
    return ["-c:v", "libx264", "-preset", preset, "-crf", crf, "-pix_fmt", "yuv420p"]


def encoder_chain(pref="auto"):
    """Every GPU encoder FFmpeg lists, best first, then CPU. The export tries them in order: a GPU without a hardware encoder
    (e.g. GeForce 940M/940MX = GM108 has NO NVENC) fails in a second and the next one (Intel QSV) is tried."""
    have = available_encoders()
    if pref and pref != "auto":
        return ([pref] if pref in have else []) + (["cpu"] if pref != "cpu" else [])
    return [e for e in ("nvenc", "qsv", "amf") if e in have] + ["cpu"]


def best_encoder(pref="auto"):
    """GPU encoder when FFmpeg has one (5-10x faster than the CPU), else CPU. The export falls back to CPU by itself if the GPU refuses."""
    have = available_encoders()
    if pref and pref != "auto":
        return pref if pref in have else "cpu"
    for e in ("nvenc", "qsv", "amf"):
        if e in have:
            return e
    return "cpu"


def _atempo(f):
    """atempo chain for any speed (each atempo accepts 0.5 .. 2.0)."""
    parts = []
    while f > 2.0:
        parts.append("atempo=2.0"); f /= 2.0
    while f < 0.5:
        parts.append("atempo=0.5"); f /= 0.5
    parts.append(f"atempo={f:.4f}")
    return ",".join(parts)


# ------------------------------------------------------------------ subtitle track (PNG per line, any font, perfect Khmer)
def _write_sub_list(items, dur, W, H, workdir):
    """Concat list: blank transparent frame for gaps + one PNG (W x H) per subtitle piece (start, end, png)."""
    d = os.path.join(workdir, "sub_track"); os.makedirs(d, exist_ok=True)
    blank = os.path.join(d, "blank.png")
    run(["ffmpeg", "-y", "-f", "lavfi", "-i", f"color=c=black@0.0:s={W}x{H},format=rgba", "-frames:v", "1", blank])
    q = lambda p: "file '" + os.path.abspath(p).replace("\\", "/").replace("'", "'\\''") + "'"
    lines, cur = [], 0.0
    items = sorted(items, key=lambda x: x[0])
    for k, (st, en, png) in enumerate(items):
        st = max(st, cur)
        nxt = items[k + 1][0] if k + 1 < len(items) else en
        en = max(st + 0.05, min(en, nxt if nxt > st else en))
        if st - cur > 0.01:
            lines += [q(blank), f"duration {st - cur:.3f}"]
        lines += [q(png), f"duration {en - st:.3f}"]; cur = en
    tail = max(0.5, dur - cur + 1.0)
    lines += [q(blank), f"duration {tail:.3f}", q(blank)]      # last file repeated: concat demuxer ignores the last duration
    path = os.path.join(d, "list.txt")
    with open(path, "w", encoding="utf-8") as f:
        f.write("\n".join(lines) + "\n")
    return path


# ------------------------------------------------------------------ final export
def export_video(video, dub_wav, out, o):
    """Final render used by the UI.
    o keys: dur, bg, bg_vol, music, music_vol, crop, flip_h, flip_v,
            mode ('9:16'|'16:9'|'1:1'|'4:5'|'3:4'|'W:H'|'Original'), fit (True = bars, False = crop to fill),
            overlays=[{kind:'png'|'blur', path, x, y, w, h, plate?}] (coords in the final frame),
            stage={'bg': 'black'|'blur'|'png', 'bg_png', 'border_png', 'sigma'}   (VIP frame / background behind the video),
            sub_track={'items': [(start, end, png)], 'w','h','y','fh'}   (Khmer subtitles, one band image per piece),
            res = short side in px (1080 = Full HD, 0 = keep), speed = 1.0 .. 4.0, clip = (t0, t1) for AutoClip,
            encoder = 'cpu'|'nvenc'|'qsv'|'amf', quality = 'fast'|'balanced'|'best'."""
    video, dub_wav, out = map(os.path.abspath, (video, dub_wav, out))
    o = dict(o or {})
    clip = o.get("clip")                           # AutoClip: (t0, t1) seconds of the full timeline
    t0 = float(clip[0]) if clip else 0.0
    dur = (float(clip[1]) - t0) if clip else (float(o.get("dur") or 0) or duration(video))
    overlays = list(o.get("overlays") or [])
    fh, fv = bool(o.get("flip_h")), bool(o.get("flip_v"))
    speed = max(0.25, min(4.0, float(o.get("speed") or 1.0)))
    has_v = has_video(video)
    W, H = video_size(video) if has_v else (1280, 720)

    pad = None
    if o.get("mode"):                              # aspect ratio (9:16 ...) computed from the REAL stream size
        from .geometry import layout
        g = layout(W, H, o["mode"], bool(o.get("fit", True)))
        crop, pad = g["crop"], g["pad"]
    else:
        crop = o.get("crop")
        if crop:                                   # validate against the real stream size
            cx, cy, cw, ch = [int(v) for v in crop]
            cw, ch = min(cw, W), min(ch, H)
            cx, cy = max(0, min(cx, W - cw)), max(0, min(cy, H - ch))
            cw -= cw % 2; ch -= ch % 2
            crop = (cx, cy, cw, ch) if cw >= 2 and ch >= 2 else None
    if pad:
        FW, FH = pad[0], pad[1]
    elif crop:
        FW, FH = crop[2], crop[3]
    else:
        FW, FH = W - W % 2, H - H % 2

    stage = o.get("stage") or {}
    sub_track = o.get("sub_track")
    res = int(o.get("res") or 0)
    TW, TH = FW, FH
    if res:
        if FW <= FH:
            TW, TH = res - res % 2, max(2, int(round(FH * res / FW)) // 2 * 2)
        else:
            TH, TW = res - res % 2, max(2, int(round(FW * res / FH)) // 2 * 2)
    copy_ok = not (fh or fv or crop or pad or overlays or sub_track or stage.get("border_png") or res or speed != 1.0 or clip)
    copy_video = has_v and copy_ok
    workdir = os.path.dirname(dub_wav)
    sub_list = None
    if sub_track and sub_track.get("items"):
        sub_list = _write_sub_list(sub_track["items"], dur, int(sub_track["w"]), int(sub_track["h"]), workdir)

    def build(enc, norm):
        cmd, fc, n = ["ffmpeg", "-y", "-hide_banner", "-filter_complex_threads", str(max(2, (os.cpu_count() or 4)))], [], 2
        ss = ["-ss", f"{t0:.3f}"] if clip else []
        if has_v:
            cmd += ss + ["-i", video]
        else:                                      # audio-only source -> black canvas
            cmd += ["-f", "lavfi", "-i", f"color=c=black:s={W - W % 2}x{H - H % 2}:r=25:d={dur:.3f}"]
        cmd += ss + ["-i", dub_wav]
        vlabel = "0:v:0"
        if not copy_video:
            vf = (["hflip"] if fh else []) + (["vflip"] if fv else [])
            if crop: vf.append("crop=%d:%d:%d:%d" % (crop[2], crop[3], crop[0], crop[1]))
            vf += ["scale=trunc(iw/2)*2:trunc(ih/2)*2", "setsar=1"]
            bg = stage.get("bg", "black") if pad else "black"
            if pad and bg == "blur":                 # blurred copy of the video fills the bars (CapCut / TikTok look)
                fc.append(f"[0:v:0]{','.join(vf)}[fg]")
                bw, bh = max(2, FW // 6 // 2 * 2), max(2, FH // 6 // 2 * 2)
                sg = float(stage.get("sigma", 5))
                fc.append(f"[fg]split[fa][fb];[fb]scale={bw}:{bh}:force_original_aspect_ratio=increase,crop={bw}:{bh},"
                          f"gblur=sigma={sg}:steps=2,eq=brightness=-0.07:saturation=1.2,scale={FW}:{FH}:flags=bilinear[bgb];"
                          f"[bgb][fa]overlay={pad[2]}:{pad[3]}[v0]")
            elif pad and bg == "png" and stage.get("bg_png") and os.path.exists(stage["bg_png"]):
                fc.append(f"[0:v:0]{','.join(vf)}[fg]")
                cmd += ["-loop", "1", "-i", os.path.abspath(stage["bg_png"])]
                fc.append(f"[{n}:v]scale={FW}:{FH},format=rgb24[bgi];[bgi][fg]overlay={pad[2]}:{pad[3]}:shortest=1[v0]"); n += 1
            else:
                if pad: vf.append("pad=%d:%d:%d:%d:color=black" % pad)
                fc.append(f"[0:v:0]{','.join(vf)}[v0]")
            cur = "v0"
            if stage.get("border_png") and os.path.exists(stage["border_png"]):       # neon LED / gold VIP frame
                cmd += ["-loop", "1", "-i", os.path.abspath(stage["border_png"])]
                fc.append(f"[{n}:v]scale={FW}:{FH},format=rgba[brd];[{cur}][brd]overlay=0:0:shortest=1[vb]"); cur = "vb"; n += 1
            for k, ov in enumerate(overlays, 1):
                x, y = int(ov.get("x", 0)), int(ov.get("y", 0))
                w, h = max(2, int(ov.get("w", 2))), max(2, int(ov.get("h", 2)))
                if ov.get("kind") == "blur":
                    x1, y1, x2, y2 = max(0, x), max(0, y), min(FW, x + w), min(FH, y + h)
                    x1 -= x1 % 2; y1 -= y1 % 2
                    bw, bh = (x2 - x1) - (x2 - x1) % 2, (y2 - y1) - (y2 - y1) % 2
                    if bw < 8 or bh < 8:
                        continue
                    # strong smooth blur: shrink the crop ~14x, blur, enlarge = hard-sub text vanishes completely but the
                    # colours of the scene stay (looks like a really blurred photo, not a grey box)
                    dn = int(ov.get("down") or 14)
                    sw_, sh_ = max(6, bw // dn), max(4, bh // dn)
                    fc.append(f"[{cur}]split[a{k}][b{k}];[b{k}]crop={bw}:{bh}:{x1}:{y1},scale={sw_}:{sh_}:flags=area,"
                              f"gblur=sigma=1.4:steps=2,scale={bw}:{bh}:flags=bicubic,eq=brightness=-0.02:saturation=1.05[bl{k}]")
                    top = f"bl{k}"
                    plate = ov.get("plate")
                    if plate and os.path.exists(plate):       # bokeh / frosted plate on top of the blur (hides hard-sub text)
                        cmd += ["-loop", "1", "-i", os.path.abspath(plate)]
                        fc.append(f"[{n}:v]scale={bw}:{bh},format=rgba[pl{k}];[bl{k}][pl{k}]overlay=0:0:shortest=1[bp{k}]"); top = f"bp{k}"; n += 1
                    mask = ov.get("mask")
                    if mask and os.path.exists(mask):          # soft (feathered) edges: the blur melts into the picture
                        cmd += ["-loop", "1", "-i", os.path.abspath(mask)]
                        fc.append(f"[{n}:v]scale={bw}:{bh},format=gray[mk{k}];[{top}]format=yuv420p[tf{k}];[tf{k}][mk{k}]alphamerge[tm{k}]")
                        top = f"tm{k}"; n += 1
                    fc.append(f"[a{k}][{top}]overlay={x1}:{y1}[v{k}]")
                else:
                    pth = ov.get("path")
                    if not pth or not os.path.exists(pth):
                        continue
                    cmd += ["-loop", "1", "-i", os.path.abspath(pth)]
                    fc.append(f"[{n}:v]format=rgba,scale={w}:{h}[o{k}];[{cur}][o{k}]overlay={x}:{y}:shortest=1[v{k}]")
                    n += 1
                cur = f"v{k}"
            if sub_list:                               # Khmer subtitles burned in (same look as the preview)
                sy = FH / float(sub_track.get("fh") or FH)
                bh_ = max(2, int(round(int(sub_track["h"]) * sy)) // 2 * 2); y_ = int(round(float(sub_track.get("y", 0)) * sy))
                cmd += ["-f", "concat", "-safe", "0", "-i", sub_list]
                fc.append(f"[{n}:v]format=rgba,scale={FW}:{bh_}[sb];[{cur}][sb]overlay=0:{y_}:eof_action=pass[vt]")
                cur = "vt"; n += 1
            if (TW, TH) != (FW, FH):                   # Full HD / 2K / 4K output
                fc.append(f"[{cur}]scale={TW}:{TH}:flags=lanczos[vr]"); cur = "vr"
            if speed != 1.0:
                fc.append(f"[{cur}]setpts=PTS/{speed:.4f}[vsp]"); cur = "vsp"
            vlabel = f"[{cur}]"

        mix = ["[1:a]"]
        if o.get("bg"):
            cmd += ss + ["-i", os.path.abspath(o["bg"])]
            fc.append(f"[{n}:a]volume={float(o.get('bg_vol', 0.8))}[bga]"); mix.append("[bga]"); n += 1
        if o.get("music"):
            cmd += ["-stream_loop", "-1", "-i", os.path.abspath(o["music"])]
            fc.append(f"[{n}:a]volume={float(o.get('music_vol', 0.8))}[ma]"); mix.append("[ma]"); n += 1
        alabel = "[aout]"
        if len(mix) > 1:
            base = "".join(mix) + f"amix=inputs={len(mix)}:duration=first:dropout_transition=0"
            fc.append(base + (":normalize=0[aout]" if norm else f",volume={len(mix)}[aout]"))
        else:
            fc.append("[1:a]anull[aout]")
        if speed != 1.0:
            fc.append(f"[aout]{_atempo(speed)}[aouts]"); alabel = "[aouts]"

        cmd += ["-filter_complex", ";".join(fc), "-map", vlabel, "-map", alabel]
        if copy_video:
            cmd += ["-c:v", "copy"]
        else:
            cmd += _venc_args(enc, o.get("quality", "balanced"))
        cmd += ["-c:a", "aac", "-b:a", "192k", "-movflags", "+faststart"]
        if dur > 0:
            cmd += ["-t", f"{dur / speed:.3f}"]
        cmd.append(out)
        return cmd

    wanted = o.get("encoder") or "cpu"
    chain = list(wanted) if isinstance(wanted, (list, tuple)) else ([wanted, "cpu"] if wanted != "cpu" else ["cpu"])
    chain = list(dict.fromkeys(chain + (["cpu"] if "cpu" not in chain else [])))
    for enc in chain:                                                   # GPU first, the next one / CPU if the GPU refuses
        try:
            try:
                run(build(enc, True))
            except RuntimeError as e:
                if "normalize" not in str(e).lower():   # old FFmpeg without amix normalize option
                    raise
                run(build(enc, False))
            return out
        except RuntimeError:
            if enc == "cpu":
                raise
    return out
"""Snap subtitle timings to the real speech in the audio (Gemini timestamps are often a second or two off).
Uses FFmpeg silencedetect: the first line of a speech burst starts where the burst starts, the last line ends where it ends.
If the audio has no clear pauses (music / noise all the time) nothing is changed."""
import re, subprocess
from .media import NOWIN


def speech_regions(wav, noise_db=-32, min_sil=0.35):
    p = subprocess.run(["ffmpeg", "-hide_banner", "-nostats", "-i", wav, "-af",
                        f"silencedetect=noise={noise_db}dB:d={min_sil}", "-f", "null", "-"],
                       capture_output=True, text=True, encoding="utf-8", errors="ignore", creationflags=NOWIN)
    log = p.stderr
    m = re.search(r"Duration:\s*(\d+):(\d+):([\d.]+)", log)
    dur = int(m.group(1)) * 3600 + int(m.group(2)) * 60 + float(m.group(3)) if m else 0.0
    sil, start = [], None
    for line in log.splitlines():
        a = re.search(r"silence_start:\s*(-?[\d.]+)", line)
        b = re.search(r"silence_end:\s*([\d.]+)", line)
        if a:
            start = max(0.0, float(a.group(1)))
        if b and start is not None:
            sil.append((start, float(b.group(1)))); start = None
    if start is not None and dur:
        sil.append((start, dur))
    if not dur or sum(e - s for s, e in sil) < dur * 0.05:     # no clear pauses -> do not touch anything
        return []
    regions, cur = [], 0.0
    for s, e in sil:
        if s - cur > 0.15:
            regions.append((cur, s))
        cur = e
    if dur - cur > 0.15:
        regions.append((cur, dur))
    return regions if len(regions) >= 2 else []


def refine(segs, regions, max_shift=2.0):
    if not regions:
        return segs
    groups = {}
    for s in segs:
        mid = (s.start + s.end) / 2
        best, bd = None, 1e9
        for k, (a, b) in enumerate(regions):
            d = 0 if a <= mid <= b else min(abs(mid - a), abs(mid - b))
            if d < bd:
                best, bd = k, d
        if best is not None and bd <= max_shift:
            groups.setdefault(best, []).append(s)
    for k, ss in groups.items():
        a, b = regions[k]
        ss.sort(key=lambda x: x.start)
        first, last = ss[0], ss[-1]
        if abs(first.start - a) <= max_shift:
            first.start = a
        if abs(last.end - b) <= max_shift and b > first.start + 0.3:
            last.end = b
    for s in segs:
        if s.end <= s.start:
            s.end = s.start + 1.0
    return segs


def voiced_seconds(path, noise_db=-35, min_sil=0.3):
    """Seconds of non-silent audio in a file (used to notice a chunk where the transcriber skipped speech)."""
    p = subprocess.run(["ffmpeg", "-hide_banner", "-nostats", "-i", path, "-af",
                        f"silencedetect=noise={noise_db}dB:d={min_sil}", "-f", "null", "-"],
                       capture_output=True, text=True, encoding="utf-8", errors="ignore", creationflags=NOWIN)
    log = p.stderr
    m = re.search(r"Duration:\s*(\d+):(\d+):([\d.]+)", log)
    dur = int(m.group(1)) * 3600 + int(m.group(2)) * 60 + float(m.group(3)) if m else 0.0
    sil = sum(float(x) for x in re.findall(r"silence_duration:\s*([\d.]+)", log))
    return max(0.0, dur - sil)

"""AutoClip: cut a long video into short clips at the natural pauses of the script (pure Python)."""


def plan_clips(spans, total, target=75.0, min_len=30.0, max_len=120.0):
    """spans = [(start, end)] of the spoken lines (sorted). Returns [(t0, t1)] clips of about `target` seconds,
    every cut placed in the biggest pause that lies between min_len and max_len after the clip start."""
    spans = sorted(spans)
    total = float(total)
    if total <= max_len or not spans:
        return [(0.0, total)]
    gaps = [((spans[i][1] + spans[i + 1][0]) / 2.0, max(0.0, spans[i + 1][0] - spans[i][1])) for i in range(len(spans) - 1)]
    clips, t0 = [], 0.0
    while total - t0 > max_len:
        lo, hi = t0 + min_len, t0 + max_len
        best, bs = None, -1e9
        for mid, gap in gaps:
            if lo <= mid <= hi:
                sc = gap * 10.0 - abs(mid - (t0 + target)) / target
                if sc > bs:
                    best, bs = mid, sc
        cut = best if best is not None else t0 + target
        clips.append((t0, cut)); t0 = cut
    if clips and total - t0 < min_len:
        clips[-1] = (clips[-1][0], total)
    else:
        clips.append((t0, total))
    return clips


def shift_items(items, t0, t1):
    """Subtitle items (start, end, png) -> only those inside [t0, t1], times moved so the clip starts at 0."""
    out = []
    for s, e, p in items:
        if e <= t0 or s >= t1:
            continue
        out.append((max(s, t0) - t0, min(e, t1) - t0, p))
    return out
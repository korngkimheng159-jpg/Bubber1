"""Cut a long subtitle line into short, readable pieces that follow the speech (pure Python, no Qt).
Khmer cluster safe: never cuts between a consonant and its sub-consonant / vowel / sign."""
import re

_KH_MARK = re.compile("[\u17b6-\u17d3\u17dd]")      # dependent vowels, signs, coeng
COENG = "\u17d2"


def _safe_cut(text, pos):
    """Move a cut position left until it is not inside a Khmer cluster."""
    pos = max(1, min(pos, len(text) - 1))
    while pos > 1 and (_KH_MARK.match(text[pos]) or text[pos - 1] == COENG):
        pos -= 1
    return pos


def _words(text):
    return [w for w in re.split(r"(?<=[\s\u200b])", text.replace("\n", " ")) if w.strip()]


def split_text(text, max_chars=32):
    """'long sentence' -> ['piece 1', 'piece 2', ...] each <= max_chars (when a break point exists)."""
    text = " ".join(text.split())
    if len(text) <= max_chars:
        return [text] if text else []
    pieces, cur = [], ""
    for w in _words(text):
        while len(w.strip()) > max_chars:                  # one token longer than the limit (Khmer without spaces)
            room = max_chars - len(cur)
            if room < 6 and cur:
                pieces.append(cur.strip()); cur = ""; room = max_chars
            cut = _safe_cut(w, room if room >= 6 else max_chars)
            cur += w[:cut]; pieces.append(cur.strip()); cur = ""; w = w[cut:]
        if len(cur) + len(w) > max_chars and cur.strip():
            pieces.append(cur.strip()); cur = ""
        cur += w
    if cur.strip():
        pieces.append(cur.strip())
    # balance: a tiny last piece is merged back when it still fits
    if len(pieces) >= 2 and len(pieces[-1]) < max_chars * 0.25 and len(pieces[-2]) + 1 + len(pieces[-1]) <= max_chars * 1.25:
        pieces[-2] = pieces[-2] + " " + pieces[-1]; pieces.pop()
    return [p for p in pieces if p]


def split_segments(segs, max_chars=32, min_dur=0.7):
    """[(start, end, text)] -> [(start, end, piece, source_index)]. Time is shared by the number of letters,
    so every piece appears while its words are being spoken."""
    out = []
    for idx, (a, b, text) in enumerate(segs):
        parts = split_text(text, max_chars) if max_chars and max_chars > 0 else ([" ".join(text.split())] if text.strip() else [])
        if not parts:
            continue
        dur = max(b - a, 0.05)
        while len(parts) > 1 and dur / len(parts) < min_dur:      # too many pieces for a short slot: merge the shortest neighbours
            k = min(range(len(parts) - 1), key=lambda i: len(parts[i]) + len(parts[i + 1]))
            parts[k:k + 2] = [parts[k] + " " + parts[k + 1]]
        w = [max(1, len(re.sub(r"\s", "", p))) for p in parts]; tot = float(sum(w)); t = a
        for p, wi in zip(parts, w):
            d = dur * wi / tot
            out.append((t, min(t + d, b) if b > a else t + d, p, idx)); t += d
    return out
"""Pure-Python frame geometry (no Qt): where the video sits inside the output canvas.
mode: '9:16' | '16:9' | '1:1' | '4:5' | 'Original'
fit=True  -> whole video is kept, black bars are added (pad)
fit=False -> video fills the frame, the extra part is cut away (centre crop)"""

import re

MODES = ["9:16", "16:9", "1:1", "4:5", "3:4", "Original"]
RATIOS = {"9:16": 9 / 16, "16:9": 16 / 9, "1:1": 1.0, "4:5": 4 / 5, "3:4": 3 / 4}


def ratio_of(mode):
    """'9:16' -> 0.5625 ; any custom 'W:H' / 'WxH' works too ; 'Original' / junk -> None."""
    if mode in RATIOS:
        return RATIOS[mode]
    m = re.fullmatch(r"\s*(\d+(?:\.\d+)?)\s*[:/xX]\s*(\d+(?:\.\d+)?)\s*", str(mode))
    if m and float(m.group(2)) > 0 and float(m.group(1)) > 0:
        return float(m.group(1)) / float(m.group(2))
    return None


def valid_mode(mode):
    return mode == "Original" or ratio_of(mode) is not None


def even(n):
    n = int(n)
    return max(2, n - n % 2)


def layout(W, H, mode="9:16", fit=True):
    """Returns {'canvas': (cw, ch), 'pos': (vx, vy), 'crop': (x, y, w, h) | None, 'pad': (cw, ch, vx, vy) | None}
    canvas = size of the finished frame (scene); pos = where the video is drawn on it (fit mode);
    crop = centre-crop rectangle in SOURCE pixels (fill mode)."""
    W, H = max(2, int(W)), max(2, int(H))
    r = ratio_of(mode)
    if not r:
        return {"canvas": (W, H), "pos": (0, 0), "crop": None, "pad": None}
    if fit:
        We, He = even(W), even(H)
        if We / He > r:
            cw, ch = We, even(round(We / r))
        else:
            cw, ch = even(round(He * r)), He
        cw, ch = max(cw, We), max(ch, He)
        vx, vy = (cw - We) // 2, (ch - He) // 2
        vx -= vx % 2; vy -= vy % 2
        pad = (cw, ch, vx, vy) if (cw, ch) != (We, He) else None
        return {"canvas": (cw, ch), "pos": (vx, vy), "crop": None, "pad": pad}
    if W / H > r:
        h, w = H, int(H * r)
    else:
        w, h = W, int(W / r)
    w, h = even(w), even(h)
    x, y = (W - w) // 2, (H - h) // 2
    return {"canvas": (W, H), "pos": (0, 0), "crop": (x - x % 2, y - y % 2, w, h), "pad": None}

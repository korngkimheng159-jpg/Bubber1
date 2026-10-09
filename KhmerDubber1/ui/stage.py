"""'VIP' stage: the background behind the video (blur / gradient) and a glowing frame (neon LED / gold / white)."""
import math
from PySide6.QtCore import Qt, QRectF
from PySide6.QtGui import QColor, QImage, QLinearGradient, QPainter, QPen, QBrush, QRadialGradient

DEFAULT_STAGE = {"bg": "blur", "c1": "#0b1020", "c2": "#3b0f6b", "border": "none", "bcolor": "#00E5FF", "glow": 70, "sigma": 5}
STAGE_PRESETS = {
    "Blur BG (CapCut)": {"bg": "blur", "border": "none"},
    "Neon LED":         {"bg": "blur", "border": "neon", "bcolor": "#00E5FF", "glow": 80},
    "VIP Gold":         {"bg": "gradient", "c1": "#150f02", "c2": "#6b4a06", "border": "gold", "glow": 60},
    "Violet Glow":      {"bg": "gradient", "c1": "#0f0724", "c2": "#6d28d9", "border": "neon", "bcolor": "#D946EF", "glow": 80},
    "Ocean Neon":       {"bg": "gradient", "c1": "#030d1a", "c2": "#0e5a8a", "border": "neon", "bcolor": "#38BDF8", "glow": 80},
    "Fire":             {"bg": "gradient", "c1": "#1a0502", "c2": "#b3320d", "border": "neon", "bcolor": "#FF8A1F", "glow": 80},
    "Sunset Neon":      {"bg": "gradient", "c1": "#1a0630", "c2": "#ff4d6d", "border": "neon", "bcolor": "#FFB703", "glow": 85},
    "Cyber Purple":     {"bg": "gradient", "c1": "#05010f", "c2": "#4c1d95", "border": "neon", "bcolor": "#22D3EE", "glow": 90},
    "Emerald Glow":     {"bg": "gradient", "c1": "#021a12", "c2": "#059669", "border": "neon", "bcolor": "#34D399", "glow": 80},
    "Rose Gold":        {"bg": "gradient", "c1": "#1f0a10", "c2": "#b76e79", "border": "gold", "glow": 60},
    "Clean White":      {"bg": "gradient", "c1": "#f8fafc", "c2": "#cbd5e1", "border": "white", "glow": 30},
    "Black":            {"bg": "black", "border": "none"},
}


def render_bg(st, cw, ch):
    """Gradient background image (cw x ch)."""
    s = dict(DEFAULT_STAGE); s.update(st or {})
    img = QImage(cw, ch, QImage.Format_RGB32)
    p = QPainter(img); p.setRenderHint(QPainter.Antialiasing)
    g = QLinearGradient(0, 0, cw * 0.35, ch); g.setColorAt(0, QColor(s["c1"])); g.setColorAt(1, QColor(s["c2"]))
    p.fillRect(0, 0, cw, ch, QBrush(g))
    glow = QRadialGradient(cw * 0.5, ch * 0.35, max(cw, ch) * 0.6); c = QColor(s["c2"]).lighter(150); c.setAlpha(70)
    glow.setColorAt(0, c); c.setAlpha(0); glow.setColorAt(1, c)
    p.fillRect(0, 0, cw, ch, QBrush(glow)); p.end()
    return img


def render_border(st, cw, ch, rect):
    """Transparent cw x ch image with a glowing frame around rect=(x, y, w, h). None if no border."""
    s = dict(DEFAULT_STAGE); s.update(st or {})
    kind = s.get("border", "none")
    if kind == "none":
        return None
    x, y, w, h = rect
    img = QImage(cw, ch, QImage.Format_ARGB32); img.fill(0)
    p = QPainter(img); p.setRenderHint(QPainter.Antialiasing)
    lw = max(3.0, ch * 0.0042); rad = max(10.0, min(w, h) * 0.035); gl = max(0, min(100, int(s["glow"]))) / 100.0
    r0 = QRectF(x + lw / 2, y + lw / 2, w - lw, h - lw)
    if kind == "neon":
        col = QColor(s["bcolor"])
        for i in range(10, 0, -1):                      # outer glow (soft, many thin layers)
            c = QColor(col); c.setAlpha(int(34 * gl * (1 - i / 11.0) + 2))
            p.setPen(QPen(c, lw + i * lw * 0.9)); p.setBrush(Qt.NoBrush); p.drawRoundedRect(r0, rad, rad)
        p.setPen(QPen(col, lw)); p.drawRoundedRect(r0, rad, rad)
        p.setPen(QPen(QColor(255, 255, 255, 210), lw * 0.33)); p.drawRoundedRect(r0, rad, rad)       # hot white core
    elif kind == "gold":
        for i in range(6, 0, -1):
            c = QColor("#ffcf4a"); c.setAlpha(int(26 * gl * (1 - i / 7.0) + 2))
            p.setPen(QPen(c, lw * 1.6 + i * lw * 0.7)); p.setBrush(Qt.NoBrush); p.drawRoundedRect(r0, rad, rad)
        g = QLinearGradient(x, y, x + w, y + h)
        for t, c in ((0, "#fff3b0"), (0.25, "#d4a017"), (0.5, "#fff3b0"), (0.75, "#a8740a"), (1, "#ffe27a")):
            g.setColorAt(t, QColor(c))
        p.setPen(QPen(QBrush(g), lw * 1.7)); p.drawRoundedRect(r0, rad, rad)
        p.setPen(QPen(QColor(255, 250, 220, 190), lw * 0.3)); p.drawRoundedRect(r0.adjusted(lw * 1.3, lw * 1.3, -lw * 1.3, -lw * 1.3), rad, rad)
    else:                                               # white glass
        for i in range(6, 0, -1):
            c = QColor(255, 255, 255, int(20 * gl * (1 - i / 7.0) + 2))
            p.setPen(QPen(c, lw + i * lw * 0.6)); p.setBrush(Qt.NoBrush); p.drawRoundedRect(r0, rad, rad)
        p.setPen(QPen(QColor(255, 255, 255, 235), lw * 0.9)); p.drawRoundedRect(r0, rad, rad)
    p.end()
    return img
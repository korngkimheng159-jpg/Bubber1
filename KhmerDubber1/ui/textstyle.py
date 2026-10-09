"""Styled text rendering (Qt does the Khmer / Chinese shaping) used by the Text, Sponsor, Watermark overlays and the
Khmer subtitles on the video. A style is a plain dict so it can be saved in config.json."""
import math
from PySide6.QtCore import Qt, QRectF
from PySide6.QtGui import QColor, QFont, QImage, QPainter, QTextCharFormat, QTextCursor, QTextDocument, QTextOption

DEFAULT_STYLE = {"family": "Khmer UI", "size_pct": 5.0, "color": "#FFFFFFFF", "stroke": "#FF000000", "stroke_pct": 12,
                 "bg": None, "bold": True, "italic": False, "shadow": False, "opacity": 100}
SUB_STYLE = dict(DEFAULT_STYLE, size_pct=4.0, stroke_pct=18, shadow=True, fill=True, color="#FFFFF200")      # yellow, thick outline, soft shadow, grows to fill the width

STYLE_PRESETS = {
    "TikTok Khmer":         {"color": "#FFFFF200", "stroke": "#FF000000", "stroke_pct": 18, "bg": None, "shadow": True, "opacity": 100, "fill": True},
    "Khmer Gold Glow":      {"color": "#FFFFE08A", "stroke": "#FF5A3600", "stroke_pct": 16, "bg": None, "shadow": True, "opacity": 100, "fill": True},
    "Pink Neon Box":        {"color": "#FFFFFFFF", "stroke": "#FF000000", "stroke_pct": 0, "bg": "#E6D6246E", "shadow": True, "opacity": 100, "fill": True},
    "Cyan Pop":             {"color": "#FFFFFFFF", "stroke": "#FF0077B6", "stroke_pct": 18, "bg": None, "shadow": True, "opacity": 100, "fill": True},
    "Classic":                {"color": "#FFFFFFFF", "stroke": "#FF000000", "stroke_pct": 14, "bg": None, "shadow": False, "opacity": 100},
    "Yellow Subtitle":      {"color": "#FFFFE600", "stroke": "#FF000000", "stroke_pct": 14, "bg": None, "shadow": False, "opacity": 100},
    "Neon Cyan":            {"color": "#FF00F5FF", "stroke": "#FF00334D", "stroke_pct": 10, "bg": None, "shadow": True, "opacity": 100},
    "Gold Luxury":          {"color": "#FFFFD54A", "stroke": "#FF6B4300", "stroke_pct": 14, "bg": None, "shadow": True, "opacity": 100},
    "Pink Pop":             {"color": "#FFFF5C9E", "stroke": "#FFFFFFFF", "stroke_pct": 10, "bg": None, "shadow": True, "opacity": 100},
    "Fresh Green":          {"color": "#FF7CFF6B", "stroke": "#FF0B3D0B", "stroke_pct": 12, "bg": None, "shadow": False, "opacity": 100},
    "Boxed Black":          {"color": "#FFFFFFFF", "stroke": "#FF000000", "stroke_pct": 0, "bg": "#CC000000", "shadow": False, "opacity": 100},
    "Red Banner":           {"color": "#FFFFFFFF", "stroke": "#FF000000", "stroke_pct": 0, "bg": "#E6E11D48", "shadow": False, "opacity": 100},
    "Blue Banner":          {"color": "#FFFFFFFF", "stroke": "#FF000000", "stroke_pct": 0, "bg": "#E62563EB", "shadow": False, "opacity": 100},
    "Soft Shadow":          {"color": "#FFFFFFFF", "stroke": "#FF000000", "stroke_pct": 0, "bg": None, "shadow": True, "opacity": 100},
    "Sponsor":              {"color": "#FFFFFFFF", "stroke": "#FF000000", "stroke_pct": 0, "bg": "#B3000000", "shadow": False, "opacity": 100, "size_pct": 3.4},
    "Watermark":            {"color": "#FFFFFFFF", "stroke": "#FF000000", "stroke_pct": 8, "bg": None, "shadow": False, "opacity": 55, "size_pct": 3.2},
}


def _doc(text, font, color, width):
    d = QTextDocument(); d.setDocumentMargin(0); d.setDefaultFont(font)
    o = QTextOption(); o.setAlignment(Qt.AlignHCenter); o.setWrapMode(QTextOption.WrapAtWordBoundaryOrAnywhere)
    d.setDefaultTextOption(o); d.setPlainText(text)
    cur = QTextCursor(d); cur.select(QTextCursor.Document)
    f = QTextCharFormat(); f.setForeground(QColor(color)); cur.mergeCharFormat(f)
    d.setTextWidth(width)
    return d


def render_styled_image(text, st, frame_h, max_w=None):
    """Text -> transparent QImage. frame_h = height of the video frame (font size is a % of it).
    max_w = widest the picture may be (long lines wrap)."""
    s = dict(DEFAULT_STYLE); s.update(st or {})
    if s.get("fill") and max_w:                      # "fill": a short line grows (max 1.35x) to use the width, never wider than max_w
        base = max(8, int(frame_h * float(s["size_pct"]) / 100.0))
        pad0 = int(base * (0.35 if s["bg"] else 0.18)) + int(math.ceil(base * float(s["stroke_pct"]) / 200.0)) + 2
        f0 = QFont(str(s["family"])); f0.setPixelSize(base); f0.setBold(bool(s["bold"])); f0.setItalic(bool(s["italic"]))
        avail0 = max(60, int(max_w) - 2 * pad0)
        iw0 = _doc(text, f0, "#ffffff", -1).idealWidth()
        if 0 < iw0 < avail0 * 0.98:
            k = min(1.35, avail0 * 0.98 / iw0)
            if k > 1.04:
                s2 = dict(s); s2["size_pct"] = float(s["size_pct"]) * k; s2["fill"] = False
                return render_styled_image(text, s2, frame_h, max_w)
    px = max(8, int(frame_h * float(s["size_pct"]) / 100.0))
    font = QFont(str(s["family"])); font.setPixelSize(px); font.setBold(bool(s["bold"])); font.setItalic(bool(s["italic"]))
    r = max(0.0, px * float(s["stroke_pct"]) / 200.0)
    pad = int(px * (0.35 if s["bg"] else 0.18)) + int(math.ceil(r)) + 2
    if max_w:
        avail = max(60, int(max_w) - 2 * pad)
        probe = _doc(text, font, "#ffffff", avail)
        iw = probe.idealWidth()
        width = math.ceil(iw) + 2 if iw + 2 < avail else avail
    else:
        width = -1
    fill = _doc(text, font, s["color"], width)
    size = fill.size()
    W, H = int(math.ceil(size.width())) + 2 * pad, int(math.ceil(size.height())) + 2 * pad
    img = QImage(max(W, 4), max(H, 4), QImage.Format_ARGB32); img.fill(0)
    p = QPainter(img); p.setRenderHints(QPainter.Antialiasing | QPainter.TextAntialiasing | QPainter.SmoothPixmapTransform)
    p.setOpacity(max(0.05, min(1.0, float(s["opacity"]) / 100.0)))
    if s["bg"]:
        p.setPen(Qt.NoPen); p.setBrush(QColor(s["bg"])); p.drawRoundedRect(QRectF(0, 0, W, H), px * 0.28, px * 0.28)

    def draw(doc, dx=0.0, dy=0.0):
        p.save(); p.translate(pad + dx, pad + dy); doc.drawContents(p); p.restore()

    if s["shadow"]:
        draw(_doc(text, font, "#99000000", width), px * 0.05, px * 0.07)
    if r > 0:
        edge = _doc(text, font, s["stroke"], width)
        for ring, n in ((r, 18), (r * 0.55, 12)):
            for k in range(n):
                a = 2 * math.pi * k / n
                draw(edge, ring * math.cos(a), ring * math.sin(a))
    draw(fill)
    p.end()
    return img

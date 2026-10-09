from PySide6.QtCore import Qt, QThread, Signal, QTimer, QRectF
from PySide6.QtGui import QPainter, QColor, QLinearGradient, QPen, QFont, QFontMetrics
from PySide6.QtWidgets import QWidget, QGraphicsDropShadowEffect


class Cancelled(Exception):
    pass


class Worker(QThread):
    progress = Signal(int, str)
    done = Signal(object)
    failed = Signal(str)

    def __init__(self, fn):
        super().__init__()
        self.fn = fn
        self._stop = False

    def stop(self):
        self._stop = True

    def run(self):
        def cb(p, m=""):
            if self._stop:
                raise Cancelled()
            self.progress.emit(int(p), m)
        try:
            self.done.emit(self.fn(cb))
        except Cancelled:
            self.failed.emit("__stopped__")
        except Exception as e:
            import traceback; traceback.print_exc()
            self.failed.emit(str(e))


def glow(widget, color="#3b82f6", radius=22):
    fx = QGraphicsDropShadowEffect(widget)
    fx.setBlurRadius(radius); fx.setOffset(0, 0); fx.setColor(QColor(color))
    widget.setGraphicsEffect(fx)


class LedBar(QWidget):
    """Animated rainbow LED strip."""
    def __init__(self, h=4):
        super().__init__()
        self.setFixedHeight(h); self.phase = 0.0
        t = QTimer(self); t.timeout.connect(self._tick); t.start(33)

    def _tick(self):
        if self.isVisible():
            self.phase = (self.phase + 0.006) % 1.0
            self.update()

    def paintEvent(self, _):
        p = QPainter(self)
        g = QLinearGradient(0, 0, self.width(), 0)
        for i in range(9):
            g.setColorAt(i / 8, QColor.fromHsvF((i / 8 + self.phase) % 1.0, 0.75, 1.0))
        p.fillRect(self.rect(), g)


Y_VIS, Y_SUB, Y_AUD, H_TRK = 30, 68, 108, 34


class Timeline(QWidget):
    """Visuals / Subtitles / Generated-audio tracks with waveform, zoom and drag-to-move."""
    seek = Signal(float)
    moved = Signal(int, float, float)

    def __init__(self):
        super().__init__()
        self.segs, self.dur, self.pos, self.pps = [], 1.0, 0.0, 60.0
        self.wave, self.wave_dur, self.sel, self.visuals = None, 1.0, -1, False
        self._drag, self._moved = None, False
        self.setFixedHeight(170)

    def set_data(self, segs, dur, visuals=False):
        self.segs, self.visuals = segs, visuals
        self.dur = max(dur, max([s.end for s in segs], default=0), 1.0)
        self.setFixedSize(int(self.dur * self.pps) + 80, 170)
        self.update()

    def set_zoom(self, pps):
        self.pps = pps
        self.setFixedSize(int(self.dur * self.pps) + 80, 170); self.update()

    def set_wave(self, peaks, dur):
        self.wave, self.wave_dur = peaks, max(dur, 0.1); self.update()

    def set_pos(self, t):
        self.pos = t; self.update()

    def set_selected(self, i):
        self.sel = i; self.update()

    def _hit(self, e):
        t = e.position().x() / self.pps
        if e.position().y() >= Y_SUB:
            for i, s in enumerate(self.segs):
                if s.start <= t <= s.end:
                    return i, t
        return -1, t

    def mousePressEvent(self, e):
        i, t = self._hit(e)
        if i >= 0:
            self.sel = i; self._drag = (i, t - self.segs[i].start); self._moved = False; self.update()
        else:
            self.seek.emit(max(t, 0))

    def mouseMoveEvent(self, e):
        if self._drag:
            i, off = self._drag; s = self.segs[i]; ln = s.end - s.start
            s.start = max(0.0, e.position().x() / self.pps - off); s.end = s.start + ln
            self._moved = True; self.update()

    def mouseReleaseEvent(self, e):
        if self._drag:
            i = self._drag[0]; s = self.segs[i]
            if self._moved: self.moved.emit(i, s.start, s.end)
            else: self.seek.emit(s.start)
        self._drag = None

    def paintEvent(self, e):
        p = QPainter(self); p.setRenderHint(QPainter.Antialiasing)
        r = e.rect(); x0, x1, pps = r.left(), r.right(), self.pps
        p.fillRect(r, QColor("#090c14"))
        step = next((s for s in (1, 2, 5, 10, 15, 30, 60, 120, 300) if s * pps >= 70), 600)
        p.setFont(QFont("Segoe UI", 8)); t = (int(x0 / pps) // step) * step
        while t * pps <= x1:
            x = int(t * pps)
            p.setPen(QColor("#26324f")); p.drawLine(x, 0, x, 16)
            p.setPen(QColor("#6b7799")); p.drawText(x + 4, 12, f"{int(t // 60)}:{int(t % 60):02}")
            t += step
        for y, h in ((Y_VIS, H_TRK), (Y_SUB, H_TRK), (Y_AUD, 46)):
            p.fillRect(QRectF(x0, y, r.width(), h), QColor("#0d1220"))
        p.setPen(Qt.NoPen)
        if self.visuals:
            p.setBrush(QColor("#f5c400")); p.drawRoundedRect(QRectF(0, Y_VIS + 3, self.dur * pps, H_TRK - 6), 3, 3)
        if self.wave is not None:
            n, wd = len(self.wave), self.wave_dur
            p.setPen(QColor(90, 190, 220, 160)); mid = Y_AUD + 23
            for x in range(max(int(x0), 0), min(int(x1), int(wd * pps)) + 1, 2):
                v = float(self.wave[min(int(x / pps / wd * n), n - 1)]) * 20
                p.drawLine(x, int(mid - v), x, int(mid + v))
        fm = QFontMetrics(p.font())
        for i, s in enumerate(self.segs):
            xa = s.start * pps; xb = max(s.end * pps, xa + 4)
            if xb < x0 or xa > x1: continue
            p.setPen(QPen(QColor("#ffffff"), 1.5) if i == self.sel else Qt.NoPen)
            p.setBrush(QColor("#10b981")); p.drawRoundedRect(QRectF(xa, Y_SUB + 3, xb - xa, H_TRK - 6), 4, 4)
            p.setBrush(QColor(124, 58, 237, 200) if s.gender != "male" else QColor(37, 99, 235, 200))
            p.drawRoundedRect(QRectF(xa, Y_AUD + 3, xb - xa, 40), 4, 4)
            if xb - xa > 24:
                p.setPen(QColor("#04211a"))
                p.drawText(QRectF(xa + 4, Y_SUB + 3, xb - xa - 6, H_TRK - 6), Qt.AlignVCenter | Qt.AlignLeft,
                           fm.elidedText(s.text, Qt.ElideRight, int(xb - xa - 8)))
        x = int(self.pos * pps)
        p.setPen(QPen(QColor("#ef4444"), 2)); p.drawLine(x, 0, x, self.height())

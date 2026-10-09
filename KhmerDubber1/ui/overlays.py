"""9:16 video stage: video + draggable overlays (text / logo / sponsor / watermark / avatar / blur) + live Khmer subtitle.
Click or drop a file to load a video; double-click text or the subtitle to edit it; drag the cyan corner of a blur box to resize."""
import os
from PySide6.QtCore import Qt, QRectF, QSizeF, Signal, QTimer
from PySide6.QtGui import QImage, QPainter, QPainterPath, QColor, QPen, QPixmap, QTransform
from PySide6.QtWidgets import (QGraphicsView, QGraphicsScene, QGraphicsPixmapItem, QGraphicsRectItem,
                               QGraphicsPathItem, QGraphicsItem, QGraphicsSimpleTextItem, QFrame)
from PySide6.QtMultimediaWidgets import QGraphicsVideoItem

from core.geometry import MODES, layout, valid_mode
from ui.textstyle import render_styled_image, SUB_STYLE
from ui.blurplate import make_plate, make_feather_mask, BLUR_ONLY
from ui.stage import DEFAULT_STAGE, render_bg, render_border


def circle_png(src, out, px):
    im = QImage(src).scaled(px, px, Qt.KeepAspectRatioByExpanding, Qt.SmoothTransformation)
    res = QImage(px, px, QImage.Format_ARGB32); res.fill(0)
    p = QPainter(res); p.setRenderHint(QPainter.Antialiasing)
    pp = QPainterPath(); pp.addEllipse(0, 0, px, px); p.setClipPath(pp)
    p.drawImage((px - im.width()) // 2, (px - im.height()) // 2, im); p.end()
    res.save(out)
    return out


class BlurItem(QGraphicsRectItem):
    """Blur / OCR box. Drag to move, drag the cyan square (bottom-right) to resize, mouse wheel to scale.
    It is covered by a soft bokeh plate (Forest / Warm / Ocean ...) so Chinese hard-subs disappear."""
    GRIP = 34

    def __init__(self, w, h, style="Forest"):
        super().__init__(0, 0, w, h)
        self._rs = False; self.style_name = style; self._pm = None; self._pm_key = None; self._live = None

    def plate_pixmap(self):
        if self.style_name == BLUR_ONLY:
            return None
        r = self.rect(); key = (self.style_name, int(r.width() / 12), int(r.height() / 12))
        if key != self._pm_key:
            w = max(16, int(min(r.width(), 800))); h = max(16, int(r.height() * w / max(r.width(), 1)))
            self._pm = QPixmap.fromImage(make_plate(self.style_name, w, h, 0.92)); self._pm_key = key
        return self._pm

    def _grip(self):
        r = self.rect(); g = min(self.GRIP, r.width() / 2, r.height() / 2)
        return QRectF(r.right() - g, r.bottom() - g, g, g)

    def paint(self, p, opt, widget=None):
        r = self.rect(); pm = self.plate_pixmap()
        if pm is not None:
            p.drawPixmap(r, pm, QRectF(pm.rect()))
        elif self._live is not None:                       # real blurred copy of the current frame (what the export will look like)
            p.drawPixmap(r, self._live, QRectF(self._live.rect()))
        else:
            p.setPen(Qt.NoPen); p.setBrush(QColor(255, 255, 255, 60)); p.drawRect(r)
        p.setBrush(Qt.NoBrush); p.setPen(self.pen()); p.drawRect(r)
        p.setPen(Qt.NoPen); p.setBrush(QColor("#22d3ee")); p.drawRect(self._grip())

    def mousePressEvent(self, e):
        if self._grip().contains(e.pos()):
            self._rs = True; e.accept(); return
        super().mousePressEvent(e)

    def mouseMoveEvent(self, e):
        if self._rs:
            self.prepareGeometryChange()
            self.setRect(0, 0, max(60.0, e.pos().x()), max(30.0, e.pos().y())); e.accept(); return
        super().mouseMoveEvent(e)

    def mouseReleaseEvent(self, e):
        if self._rs:
            self._rs = False; e.accept(); return
        super().mouseReleaseEvent(e)


class SubItem(QGraphicsPixmapItem):
    """The live Khmer subtitle: drag it where you want it."""
    def __init__(self, view):
        super().__init__()
        self.view = view
        self.setFlags(QGraphicsItem.ItemIsMovable | QGraphicsItem.ItemIsSelectable)
        self.setZValue(40); self.setCursor(Qt.SizeAllCursor)

    def mouseReleaseEvent(self, e):
        super().mouseReleaseEvent(e)
        self.view.sub_moved()


class VideoView(QGraphicsView):
    changed = Signal()
    open_request = Signal()
    file_dropped = Signal(str)
    edit_request = Signal(object)          # double-click on a text overlay
    sub_edit_request = Signal()            # double-click on the subtitle
    sub_pos_changed = Signal(float, float)
    MEDIA_EXT = (".mp4", ".mkv", ".mov", ".avi", ".webm", ".mp3", ".wav", ".m4a")

    def __init__(self, player):
        super().__init__()
        self.sc = QGraphicsScene(self); self.setScene(self.sc)
        self.setBackgroundBrush(QColor("#151b2e")); self.setFrameShape(QFrame.NoFrame)
        self.setRenderHints(QPainter.Antialiasing | QPainter.SmoothPixmapTransform)
        self.setHorizontalScrollBarPolicy(Qt.ScrollBarAlwaysOff); self.setVerticalScrollBarPolicy(Qt.ScrollBarAlwaysOff)
        self.setAcceptDrops(True); self.setFocusPolicy(Qt.StrongFocus)
        self.size_ = (1080, 1920)
        self.mode, self.fit = "9:16", True
        self.flip_h = self.flip_v = False; self.overlays = []; self.has_video = False
        self.sub_style = dict(SUB_STYLE); self.sub_pos = [0.5, 0.88]; self.sub_text = ""; self.sub_on = True
        self._geo = layout(1080, 1920, self.mode, self.fit)

        self.canvas = QGraphicsRectItem(); self.canvas.setBrush(QColor("#000000")); self.canvas.setPen(Qt.NoPen)
        self.canvas.setZValue(-10); self.canvas.setAcceptedMouseButtons(Qt.NoButton); self.sc.addItem(self.canvas)
        self.vid = QGraphicsVideoItem(); self.vid.setZValue(0); self.sc.addItem(self.vid)
        player.setVideoOutput(self.vid)
        self.vid.nativeSizeChanged.connect(self._native)
        self.mask = QGraphicsPathItem(); self.mask.setBrush(QColor(0, 0, 0, 175)); self.mask.setPen(Qt.NoPen)
        self.mask.setZValue(50); self.mask.setAcceptedMouseButtons(Qt.NoButton); self.sc.addItem(self.mask)
        self.hint = QGraphicsSimpleTextItem("＋\nចុច ឬ អូសវីដេអូមកដាក់ទីនេះ\nClick / drop video here  (9:16)")
        self.hint.setBrush(QColor("#7d8bb0")); self.hint.setZValue(5); self.hint.setAcceptedMouseButtons(Qt.NoButton)
        self.sc.addItem(self.hint)
        self.sub_item = SubItem(self); self.sub_item.setVisible(False); self.sc.addItem(self.sub_item)
        self.stage = dict(DEFAULT_STAGE)
        self.stage_bg = QGraphicsPixmapItem(); self.stage_bg.setZValue(-9); self.stage_bg.setAcceptedMouseButtons(Qt.NoButton)
        self.stage_bg.setVisible(False); self.sc.addItem(self.stage_bg)
        self.stage_border = QGraphicsPixmapItem(); self.stage_border.setZValue(6); self.stage_border.setAcceptedMouseButtons(Qt.NoButton)
        self.stage_border.setVisible(False); self.sc.addItem(self.stage_border)
        self._snap_t = QTimer(self); self._snap_t.setInterval(1500); self._snap_t.timeout.connect(self._snap_blur)
        self._live_t = QTimer(self); self._live_t.setInterval(700); self._live_t.timeout.connect(self._live_blur); self._live_t.start()
        self._apply()

    # ---------------------------------------------------------------- geometry
    @property
    def canvas_size(self):
        return self._geo["canvas"]

    def _apply(self):
        W, H = self.size_
        g = self._geo = layout(W, H, self.mode, self.fit)
        cw, ch = g["canvas"]; vx, vy = g["pos"]
        self.sc.setSceneRect(0, 0, cw, ch); self.canvas.setRect(0, 0, cw, ch)
        self.vid.setSize(QSizeF(W, H)); self.vid.setPos(vx, vy)
        self._update_mask(); self._update_flip()
        self.hint.setVisible(not self.has_video)
        if not self.has_video:
            f = self.hint.font(); f.setPixelSize(max(12, int(cw * 0.04))); f.setBold(True); self.hint.setFont(f)
            r = self.hint.boundingRect(); self.hint.setPos((cw - r.width()) / 2, (ch - r.height()) / 2)
        self.fit_view(); self.refresh_stage(); self.refresh_subtitle()

    def _native(self, s):
        if s.isEmpty(): return
        self.size_ = (int(s.width()), int(s.height())); self.has_video = True
        self._apply(); self.changed.emit()

    def fit_view(self):
        self.fitInView(self.sc.sceneRect(), Qt.KeepAspectRatio)

    def resizeEvent(self, e):
        super().resizeEvent(e); self.fit_view()

    def zoom_percent(self):
        return int(self.transform().m11() * 100)

    def crop_rect(self):
        return self._geo["crop"]

    def pad_spec(self):
        return self._geo["pad"]

    def frame_size(self):
        c = self._geo["crop"]
        return (c[2], c[3]) if c else self._geo["canvas"]

    def frame_origin(self):
        c = self._geo["crop"]
        return (c[0], c[1]) if c else (0, 0)

    def _update_mask(self):
        c = self._geo["crop"]; path = QPainterPath()
        if c:
            path.addRect(self.sc.sceneRect()); q = QPainterPath(); q.addRect(*c); path = path.subtracted(q)
        self.mask.setPath(path)

    def _update_flip(self):
        W, H = self.size_
        self.vid.setTransform(QTransform(-1 if self.flip_h else 1, 0, 0, -1 if self.flip_v else 1,
                                         W if self.flip_h else 0, H if self.flip_v else 0))

    # ---------------------------------------------------------------- aspect ratio (changeable at any time)
    def set_mode(self, mode):
        if valid_mode(mode) and mode != self.mode:
            self.mode = mode; self._apply(); self.changed.emit()

    def set_fit(self, on):
        self.fit = bool(on); self._apply(); self.changed.emit()

    def cycle_crop(self):
        modes = list(MODES)
        i = modes.index(self.mode) if self.mode in modes else -1
        self.set_mode(modes[(i + 1) % len(modes)])
        return self.mode

    def toggle_flip(self, axis):
        if axis == "h": self.flip_h = not self.flip_h
        else: self.flip_v = not self.flip_v
        self._update_flip()

    def reset_transforms(self):
        self.mode, self.fit = "9:16", True; self.flip_h = self.flip_v = False
        self._apply(); self.changed.emit()

    # ---------------------------------------------------------------- VIP stage (background + glowing frame)
    def set_stage(self, style):
        self.stage = dict(DEFAULT_STAGE); self.stage.update(style or {})
        self.refresh_stage(); self.changed.emit()

    def _border_rect(self):
        g = self._geo; cw, ch = g["canvas"]
        if g["pad"]:
            vx, vy = g["pos"]; W, H = self.size_
            return (vx, vy, W - W % 2, H - H % 2)
        if g["crop"]:
            return None
        return (0, 0, cw, ch)

    def refresh_stage(self):
        g = self._geo; cw, ch = g["canvas"]; st = self.stage; bg = st.get("bg", "blur")
        self._snap_t.stop()
        if g["pad"] and bg == "gradient":
            self.stage_bg.setPixmap(QPixmap.fromImage(render_bg(st, cw, ch))); self.stage_bg.setPos(0, 0); self.stage_bg.setVisible(True)
        elif g["pad"] and bg == "blur":
            self.stage_bg.setVisible(False)
            self._snap_blur(); self._snap_t.start()
        else:
            self.stage_bg.setVisible(False)
        rect = self._border_rect()
        img = render_border(st, cw, ch, rect) if rect and st.get("border", "none") != "none" else None
        if img is not None:
            self.stage_border.setPixmap(QPixmap.fromImage(img)); self.stage_border.setPos(0, 0); self.stage_border.setVisible(True)
        else:
            self.stage_border.setVisible(False)

    def _live_blur(self):
        """Blur boxes show a real blurred crop of the current video frame (refreshed ~every 0.7 s - cheap, tiny images)."""
        try:
            items = [it for it in self.overlays if isinstance(it, BlurItem) and it.style_name == BLUR_ONLY]
            if not items or not self.has_video:
                return
            img = self.vid.videoSink().videoFrame().toImage()
            vr = self.vid.sceneBoundingRect()
            if img.isNull() or vr.width() < 2 or vr.height() < 2:
                return
            sx, sy = img.width() / vr.width(), img.height() / vr.height()
            for it in items:
                r = self._rect(it)
                x = max(0, min(int((r.x() - vr.x()) * sx), img.width() - 2)); y = max(0, min(int((r.y() - vr.y()) * sy), img.height() - 2))
                w = max(2, min(int(r.width() * sx), img.width() - x)); h = max(2, min(int(r.height() * sy), img.height() - y))
                small = img.copy(x, y, w, h).scaled(max(4, w // 14), max(3, h // 14), Qt.IgnoreAspectRatio, Qt.SmoothTransformation)
                it._live = QPixmap.fromImage(small.scaled(max(2, int(r.width())), max(2, int(r.height())), Qt.IgnoreAspectRatio, Qt.SmoothTransformation))
                it.update()
        except Exception:
            pass

    def _snap_blur(self):
        """Blurred copy of the current video frame behind the bars (refreshed every 1.5 s - cheap)."""
        try:
            g = self._geo
            if not (g["pad"] and self.stage.get("bg") == "blur" and self.has_video):
                return
            img = self.vid.videoSink().videoFrame().toImage()
            if img.isNull():
                return
            cw, ch = g["canvas"]
            small = img.scaledToWidth(40, Qt.SmoothTransformation)
            big = small.scaled(cw, ch, Qt.KeepAspectRatioByExpanding, Qt.SmoothTransformation)
            x, y = max(0, (big.width() - cw) // 2), max(0, (big.height() - ch) // 2)
            pm = QPixmap.fromImage(big.copy(x, y, cw, ch))
            q = QPainter(pm); q.fillRect(0, 0, cw, ch, QColor(0, 0, 0, 55)); q.end()
            self.stage_bg.setPixmap(pm); self.stage_bg.setPos(0, 0); self.stage_bg.setVisible(True)
        except Exception:
            pass

    def export_stage(self, d):
        """PNG files for FFmpeg (gradient background, glowing frame) -> dict for media.export_video(stage=...)."""
        g = self._geo; cw, ch = g["canvas"]; st = self.stage
        out = {"bg": "black", "sigma": float(st.get("sigma", 5))}
        if g["pad"]:
            if st.get("bg") == "blur":
                out["bg"] = "blur"
            elif st.get("bg") == "gradient":
                path = d + "/stage_bg.png"; render_bg(st, cw, ch).save(path); out.update(bg="png", bg_png=path)
        rect = self._border_rect()
        if rect and st.get("border", "none") != "none":
            img = render_border(st, cw, ch, rect)
            if img is not None:
                path = d + "/stage_border.png"; img.save(path); out["border_png"] = path
        return out

    # ---------------------------------------------------------------- live subtitle
    def set_sub_style(self, style, pos=None):
        self.sub_style = dict(style)
        if pos: self.sub_pos = [float(pos[0]), float(pos[1])]
        self.refresh_subtitle()

    def set_sub_visible(self, on):
        self.sub_on = bool(on); self.refresh_subtitle()

    def set_subtitle(self, text, force=False):
        if force or text != self.sub_text:
            self.sub_text = text; self.refresh_subtitle()

    def refresh_subtitle(self):
        txt = self.sub_text.strip()
        if not self.sub_on or not txt or not self.has_video:
            self.sub_item.setVisible(False); return
        fw, fh = self.frame_size(); ox, oy = self.frame_origin()
        pm = QPixmap.fromImage(render_styled_image(self.sub_text, self.sub_style, fh, int(fw * 0.92)))
        self.sub_item.setPixmap(pm)
        x = ox + self.sub_pos[0] * fw - pm.width() / 2
        y = oy + self.sub_pos[1] * fh - pm.height()             # bottom edge anchored: 1 or 2 lines grow upwards
        self.sub_item.setPos(x, max(oy, y)); self.sub_item.setVisible(True)

    def sub_moved(self):
        pm = self.sub_item.pixmap(); fw, fh = self.frame_size(); ox, oy = self.frame_origin()
        if fw <= 0 or fh <= 0: return
        fx = (self.sub_item.x() + pm.width() / 2 - ox) / fw
        fy = (self.sub_item.y() + pm.height() - oy) / fh
        self.sub_pos = [max(0.0, min(1.0, fx)), max(0.05, min(1.0, fy))]
        self.sub_pos_changed.emit(self.sub_pos[0], self.sub_pos[1])

    # ---------------------------------------------------------------- click / drop / double-click
    def mousePressEvent(self, e):
        if not self.has_video and e.button() == Qt.LeftButton:
            self.open_request.emit(); return
        super().mousePressEvent(e)

    def mouseDoubleClickEvent(self, e):
        it = self.itemAt(e.position().toPoint())
        if it is self.sub_item:
            self.sub_edit_request.emit(); return
        if it in self.overlays and isinstance(it.data(0), dict) and it.data(0).get("text") is not None:
            self.edit_request.emit(it); return
        if it is None or it in (self.canvas, self.vid, self.hint):
            self.open_request.emit(); return
        super().mouseDoubleClickEvent(e)

    def dragEnterEvent(self, e):
        if e.mimeData().hasUrls(): e.acceptProposedAction()
        else: e.ignore()

    def dragMoveEvent(self, e):
        if e.mimeData().hasUrls(): e.acceptProposedAction()
        else: e.ignore()

    def dropEvent(self, e):
        for u in e.mimeData().urls():
            p = u.toLocalFile()
            if p.lower().endswith(self.MEDIA_EXT):
                self.file_dropped.emit(p); e.acceptProposedAction(); return
        e.ignore()

    # ---------------------------------------------------------------- overlays
    def _flags(self, it):
        it.setFlags(QGraphicsItem.ItemIsMovable | QGraphicsItem.ItemIsSelectable)
        it.setZValue(10)

    def _place(self, it, where):
        W, H = self.canvas_size; r = it.boundingRect(); m = W * 0.03
        x, y = {"center": ((W - r.width()) / 2, (H - r.height()) / 2),
                "br": (W - r.width() - m, H - r.height() - m), "bl": (m, H - r.height() - m),
                "tl": (m, m), "bottom": ((W - r.width()) / 2, H - r.height() - H * 0.06)}[where]
        it.setPos(x, y)

    def add_png(self, path, name, where="center", scale_w=None, extra=None):
        pm = QPixmap(path)
        if pm.isNull(): return None
        if scale_w: pm = pm.scaledToWidth(int(scale_w), Qt.SmoothTransformation)
        it = QGraphicsPixmapItem(pm); it.setTransformationMode(Qt.SmoothTransformation)
        self._flags(it)
        d = {"kind": "png", "path": path, "name": name}
        if extra: d.update(extra)
        it.setData(0, d)
        self.sc.addItem(it); self.overlays.append(it); self._place(it, where)
        self.sc.clearSelection(); it.setSelected(True); self.changed.emit()
        return it

    def update_text_item(self, it, path, text, style):
        pm = QPixmap(path)
        if pm.isNull(): return
        c = it.sceneBoundingRect().center()
        it.setPixmap(pm)
        d = dict(it.data(0)); d.update(path=path, text=text, style=style); it.setData(0, d)
        r = it.sceneBoundingRect(); it.moveBy(c.x() - r.center().x(), c.y() - r.center().y())
        self.changed.emit()

    def add_blur(self, where="bottom", style=BLUR_ONLY):
        """Draggable / resizable blur box with a bokeh plate. The same box is the region used by 'Read Screen Text'."""
        W, H = self.canvas_size
        it = BlurItem(W * 0.94, H * 0.11, style)           # wide band over the hard-sub zone; drag / resize to fit
        it.setPen(QPen(QColor("#22d3ee"), 3, Qt.DashLine))
        self._flags(it); it.setData(0, {"kind": "blur", "name": "blur"})
        self.sc.addItem(it); self.overlays.append(it); self._place(it, where)
        self.sc.clearSelection(); it.setSelected(True); self.changed.emit()
        return it

    def set_blur_style(self, name, only_selected=True):
        n = 0
        for it in self.overlays:
            if isinstance(it, BlurItem) and (it.isSelected() or not only_selected):
                it.style_name = name; it._pm_key = None; it.update(); n += 1
        return n

    def selected_overlay(self):
        for it in self.sc.selectedItems():
            if it in self.overlays: return it
        return None

    def scale_selected(self, f):
        it = self.selected_overlay()
        if it is None: return False
        it.setTransformOriginPoint(it.boundingRect().center())
        it.setScale(max(0.1, min(8.0, it.scale() * f))); self.changed.emit()
        return True

    def delete_selected(self):
        for it in list(self.sc.selectedItems()):
            if it in self.overlays:
                self.overlays.remove(it); self.sc.removeItem(it)
        self.changed.emit()

    def clear_overlays(self):
        for it in self.overlays: self.sc.removeItem(it)
        self.overlays.clear(); self.changed.emit()

    def keyPressEvent(self, e):
        if e.key() in (Qt.Key_Delete, Qt.Key_Backspace): self.delete_selected()
        else: super().keyPressEvent(e)

    def wheelEvent(self, e):      # scroll over a selected overlay = resize it
        if self.selected_overlay() is not None:
            self.scale_selected(1.08 if e.angleDelta().y() > 0 else 1 / 1.08)
        else:
            super().wheelEvent(e)

    @staticmethod
    def _rect(it):
        return it.mapRectToScene(it.rect()) if isinstance(it, QGraphicsRectItem) else it.sceneBoundingRect()

    def specs(self, outdir=None):
        """Overlay list in final-frame pixel coordinates, for FFmpeg. Blur boxes get a feather mask PNG (+ a bokeh plate PNG
        when a plate style is chosen) written to outdir - the export used to ignore the plate, so text could still show."""
        c = self.crop_rect(); cx, cy = (c[0], c[1]) if c else (0, 0); out = []
        if outdir:
            os.makedirs(outdir, exist_ok=True)
        for k, it in enumerate(self.overlays):
            r = self._rect(it); d = dict(it.data(0))
            d.pop("style", None)
            d.update(x=int(r.x() - cx), y=int(r.y() - cy), w=max(2, int(r.width())), h=max(2, int(r.height())))
            if isinstance(it, BlurItem):
                d["plate_name"] = it.style_name
                if outdir:
                    try:
                        mp = os.path.join(outdir, f"mask_{k}.png")
                        if make_feather_mask(min(d["w"], 1600), max(8, int(d["h"] * min(d["w"], 1600) / max(d["w"], 1))), mp):
                            d["mask"] = mp
                        if it.style_name != BLUR_ONLY:
                            pp = os.path.join(outdir, f"plate_{k}.png")
                            pw = min(d["w"], 1200)
                            if make_plate(it.style_name, pw, max(8, int(d["h"] * pw / max(d["w"], 1))), 0.92).save(pp):
                                d["plate"] = pp
                    except Exception:
                        pass
            out.append(d)
        return out

    def blur_source_rects(self):
        """Blur box positions in ORIGINAL source-video pixel coordinates (for OCR)."""
        W, H = self.size_; vx, vy = self._geo["pos"]
        out = []
        for it in self.overlays:
            if it.data(0).get("kind") == "blur":
                r = self._rect(it)
                x = max(0, min(int(r.x() - vx), W - 4)); y = max(0, min(int(r.y() - vy), H - 4))
                w = max(2, min(int(r.width()), W - x)); h = max(2, min(int(r.height()), H - y))
                out.append((x, y, w, h))
        return out

    def snapshot(self, path):
        return self.viewport().grab().save(path)
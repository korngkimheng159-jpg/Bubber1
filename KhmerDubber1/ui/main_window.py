import os, sys, tempfile, subprocess, shutil, itertools, time
from pathlib import Path
import numpy as np, soundfile as sf
from PySide6.QtCore import Qt, QUrl, QTimer
from PySide6.QtGui import QIcon, QGuiApplication, QImage, QPainter, QShortcut, QKeySequence, QFontDatabase
from PySide6.QtSvgWidgets import QSvgWidget
from PySide6.QtWidgets import (QApplication, QMainWindow, QWidget, QVBoxLayout, QHBoxLayout, QGridLayout,
    QPushButton, QLabel, QComboBox, QLineEdit, QTableWidget, QTableWidgetItem, QHeaderView, QAbstractItemView,
    QFileDialog, QMessageBox, QSlider, QCheckBox, QProgressBar, QPlainTextEdit, QSplitter, QInputDialog,
    QFrame, QScrollArea, QDialog, QFormLayout, QSpinBox, QMenu, QToolButton, QDialogButtonBox, QSizePolicy)
from PySide6.QtMultimedia import QMediaPlayer, QAudioOutput

from core import config, ai, tts, media
from core.srt_utils import Seg, fmt, parse_time, parse_srt, to_srt, read_srt, write_srt
from core.geometry import MODES, valid_mode
from ui.theme import QSS, THEMES, build_qss
from ui.widgets import Worker, LedBar, Timeline, glow
from ui.overlays import VideoView, circle_png
from ui.textstyle import STYLE_PRESETS, SUB_STYLE, DEFAULT_STYLE, render_styled_image
from ui.styledlg import StyleDialog
from ui.stage import STAGE_PRESETS
from ui.flow import FlowLayout
from ui.licensedlg import LicenseDialog, chip_text
from core import license as lic
from core.split import split_segments

ROOT = Path(__file__).resolve().parent.parent
LOGO = str(ROOT / "assets" / "logo.svg")
VIDEO_EXT = "Video/Audio (*.mp4 *.mkv *.mov *.avi *.webm *.mp3 *.wav *.m4a)"
IMG_EXT = "Images (*.png *.jpg *.jpeg *.webp)"
ENGINES = ["Gemini", "Gemini Lite", "Whisper"]
TR_FREE, TR_AI = "Free (No API key)", "Gemini (AI)"
ZOOMS = [10, 20, 40, 60, 90, 140, 220]
SUB_Y = {"bottom": 0.88, "middle": 0.55, "top": 0.16}


def frame(name="panel"):
    f = QFrame(); f.setObjectName(name); return f


def lbl(text, name=None):
    l = QLabel(text)
    if name: l.setObjectName(name)
    return l


def open_folder(path):
    if sys.platform.startswith("win"): os.startfile(path)
    elif sys.platform == "darwin": subprocess.run(["open", path])
    else: subprocess.run(["xdg-open", path])


def reveal_file(path):
    """Open the folder AND select the exported file in it (Explorer / Finder). Falls back to just opening the folder."""
    try:
        p = os.path.normpath(path)
        if sys.platform.startswith("win"):
            subprocess.Popen(["explorer", f"/select,{p}"])                     # explorer returns code 1 even on success -> Popen
        elif sys.platform == "darwin":
            subprocess.Popen(["open", "-R", p])
        else:
            subprocess.Popen(["xdg-open", os.path.dirname(p)])
    except Exception:
        try: open_folder(os.path.dirname(path))
        except Exception: pass


class MainWindow(QMainWindow):
    def __init__(self):
        super().__init__()
        self.cfg = config.load()
        n = self.cfg.get("stt_engine", "Gemini")
        self.cfg["stt_engine"] = "Whisper" if n.startswith(("Groq", "Local", "Whisper")) \
            else n if n in ENGINES else "Gemini"
        self.work = tempfile.mkdtemp(prefix="khmerdubber_")
        self.video = self.dub_wav = self.music = None
        self._w = None
        self.clips, self.dots, self.logs = {}, {}, []
        self.counter = itertools.count(1)
        self.isolate_bgm, self.mute_orig = False, bool(self.cfg.get("mute_orig", False))   # Mute Original starts OFF; click it when needed
        self.show_sub, self.burn = True, True                    # Khmer subtitles on the video + burned into the export
        self.sub_style = dict(SUB_STYLE); self.sub_style.update(self.cfg.get("sub_style") or {})
        self.sub_pos = list(self.cfg.get("sub_pos") or [0.5, 0.88])
        self.sub_cache, self.cur_sub_idx, self.sub_src = [], -1, []
        self.vspeed = 1.0                                         # video speed (preview playback + export)
        self.last_dir = self.work
        self.job_running = False
        self.focus_mode = False
        self.setWindowTitle("Dubber ខ្មែរ"); self.setWindowIcon(QIcon(LOGO))
        self.setMinimumSize(1280, 700); self.std_size()

        root = QWidget(); root.setObjectName("root"); self.setCentralWidget(root)
        col = QVBoxLayout(root); col.setContentsMargins(10, 6, 10, 6); col.setSpacing(6)
        col.addWidget(self.build_header())
        self.led = LedBar(3); col.addWidget(self.led)

        # players (must exist before the video view)
        self.player = QMediaPlayer(); self.aout = QAudioOutput(); self.player.setAudioOutput(self.aout)
        self.dplayer = QMediaPlayer(); self.daout = QAudioOutput(); self.dplayer.setAudioOutput(self.daout)
        self.pplayer = QMediaPlayer(); self.paout = QAudioOutput(); self.pplayer.setAudioOutput(self.paout)
        self.aout.setMuted(True)

        self.visuals_panel = self.build_visuals()
        self.video_panel = self.build_video()
        self.dialogue_panel = self.build_dialogue()
        self.bottom_panel = self.build_bottom()
        top = QSplitter(Qt.Horizontal); top.setHandleWidth(8)
        top.addWidget(self.visuals_panel); top.addWidget(self.video_panel); top.addWidget(self.dialogue_panel)
        top.setStretchFactor(0, 0); top.setStretchFactor(1, 4); top.setStretchFactor(2, 7)
        top.setSizes([236, 330, 800]); self.video_panel.setMaximumWidth(400)
        main = QSplitter(Qt.Vertical); main.setHandleWidth(8)
        main.addWidget(top); main.addWidget(self.bottom_panel)
        main.setStretchFactor(0, 7); main.setStretchFactor(1, 3)
        main.setSizes([680, 290])
        col.addWidget(main, 1)

        self.player.positionChanged.connect(self.on_pos)
        self.player.playbackStateChanged.connect(self.on_state)
        self.player.errorOccurred.connect(lambda err, msg="": self.status_lbl.setText("✖ Video: " + str(msg)))
        self.player.durationChanged.connect(lambda d: (self.slider.setRange(0, d), self.refresh_timeline()))
        self.view.changed.connect(self.refresh_timeline)
        self.view.file_dropped.connect(self.load_video)
        self.view.open_request.connect(self.open_video)
        self.view.edit_request.connect(self.edit_text_item)
        self.view.sub_edit_request.connect(self.edit_current_sub)
        self.view.sub_pos_changed.connect(self.on_sub_pos)
        self.view.set_sub_style(self.sub_style, self.sub_pos); self.view.set_sub_visible(self.show_sub)
        try: self.view.set_stage(STAGE_PRESETS.get(self.cfg.get("stage") or "Neon LED"))     # attractive frame behind the video
        except Exception: pass
        QShortcut(QKeySequence("Esc"), self).activated.connect(self.exit_focus)
        QShortcut(QKeySequence("Ctrl+O"), self).activated.connect(self.open_video)
        QShortcut(QKeySequence("Ctrl+E"), self).activated.connect(self.export_video)
        QShortcut(QKeySequence("Ctrl+G"), self).activated.connect(self.do_dub)
        QShortcut(QKeySequence("Ctrl+T"), self).activated.connect(self.do_transcribe)
        QShortcut(QKeySequence("Ctrl+Space"), self).activated.connect(self.toggle_play)
        self.setAcceptDrops(True); self.view.setAcceptDrops(False)            # drop a video / .srt anywhere on the window
        self.set_engine(self.cfg["stt_engine"])
        self.lic_timer = QTimer(self); self.lic_timer.timeout.connect(self.refresh_license); self.lic_timer.start(30 * 60 * 1000)
        self.lic_chip.setText(chip_text(lic.check()))
        if not media.has_ffmpeg():
            QMessageBox.warning(self, "FFmpeg", "រកមិនឃើញ ffmpeg/ffprobe ក្នុង PATH ទេ។ សូម install FFmpeg ជាមុន។")

    def dragEnterEvent(self, e):
        if e.mimeData().hasUrls(): e.acceptProposedAction()

    def dropEvent(self, e):
        for u in e.mimeData().urls():
            p = u.toLocalFile(); ext = os.path.splitext(p)[1].lower()
            if ext in (".mp4", ".mkv", ".mov", ".avi", ".webm", ".m4v", ".mp3", ".wav", ".m4a"):
                self.load_video(p); e.acceptProposedAction(); return
            if ext == ".srt":
                self.load_segs(read_srt(p)); e.acceptProposedAction(); return

    def std_size(self):
        """Standard window: 90% of the screen (min 1180x680, max 1600x940), centred."""
        scr = QGuiApplication.primaryScreen().availableGeometry()
        w = max(1280, min(1600, int(scr.width() * 0.9))); h = max(680, min(940, int(scr.height() * 0.9)))
        self.resize(w, h); self.move(scr.center() - self.rect().center())

    def closeEvent(self, e):
        if self._w and self._w.isRunning():
            self._w.stop(); self._w.wait(3000)
        super().closeEvent(e)

    # ================================================================== header
    def build_header(self):
        w = QWidget(); h = QHBoxLayout(w); h.setContentsMargins(0, 0, 0, 0); h.setSpacing(8)
        logo = QSvgWidget(LOGO); logo.setFixedSize(50, 50); glow(logo, "#8b5cf6", 26); h.addWidget(logo)
        t = QVBoxLayout(); t.setSpacing(0); t.addWidget(lbl("Dubber ខ្មែរ", "brand")); t.addWidget(lbl("VIP · Khmer dubbing studio", "muted"))
        h.addLayout(t); h.addStretch(1)
        self.file_chip = lbl("ចុច 📂 ឬអូសវីដេអូមកដាក់ទីនេះ", "chip"); self.file_chip.setMaximumWidth(260); self.file_chip.setSizePolicy(QSizePolicy.Ignored, QSizePolicy.Preferred); self.file_chip.setMinimumWidth(120); h.addWidget(self.file_chip)
        h.addStretch(1)

        ob = QPushButton("📂"); ob.setObjectName("icon"); ob.setToolTip("Open video"); ob.clicked.connect(self.open_video)
        self.model = QComboBox(); self.model.setEditable(True); self.model.setMinimumWidth(170)
        self.model.addItems(ai.FALLBACK_MODELS); self.model.setCurrentText(self.cfg["gemini_model"])
        self.model.currentTextChanged.connect(lambda t: self.set_cfg("gemini_model", t))
        rf = QPushButton("⟳"); rf.setObjectName("icon"); rf.setToolTip("ទាញ Gemini model ទាំងអស់"); rf.clicked.connect(self.refresh_models)
        self.src_lang = QComboBox(); self.src_lang.addItems(["Auto"] + list(ai.LANGS.keys()))
        self.src_lang.setCurrentText(self.cfg.get("source_lang", "Auto")); self.src_lang.setToolTip("Source language")
        self.src_lang.currentTextChanged.connect(lambda t: (self.set_cfg("source_lang", t), self.src_chip.setText(f"Source: {t}")))
        led = QPushButton("☀"); led.setObjectName("icon"); led.setCheckable(True); led.setChecked(True); led.setToolTip("LED on/off")
        led.toggled.connect(lambda on: (self.led.setVisible(on), self.panel_led.setVisible(on)))
        st = QPushButton("⚙"); st.setObjectName("icon"); st.setToolTip("Settings / API Keys"); st.clicked.connect(self.open_settings)
        menu_btn = QToolButton(); menu_btn.setText("☰"); menu_btn.setPopupMode(QToolButton.InstantPopup)
        m = QMenu(self)
        m.addAction("Quick Translate (No API key)…", self.quick_translate)
        m.addAction("Translate SRT/TXT file…", self.translate_file)
        m.addAction("Vocal Remover…", self.vocal_remover)
        m.addAction("View log", self.show_log)
        m.addSeparator()
        tm = m.addMenu("🎨  Theme (ពណ៌ UI)")
        for tname in THEMES:
            tm.addAction(tname, lambda n=tname: self.set_theme(n))
        menu_btn.setMenu(m)
        ex = QPushButton("④ ⬆  Export"); ex.setObjectName("accent"); ex.clicked.connect(self.export_video); glow(ex, "#2563eb")
        self.lic_chip = lbl("", "chip"); self.lic_chip.setCursor(Qt.PointingHandCursor); self.lic_chip.setToolTip("License — ចុចដើម្បីផ្លាស់ប្តូរ key")
        self.lic_chip.mousePressEvent = lambda e: self.change_license()
        for x in (ob, self.model, rf, self.src_lang, led, st, menu_btn, self.lic_chip, ex): h.addWidget(x)
        return w

    def refresh_license(self, warn=False):
        """Called at start and every 30 minutes: locks the app when the licence ends (rented copies)."""
        st = lic.check()
        was = bool(self.cfg.get("gemini_key"))
        if st.get("valid"):
            if config.PROVISIONED[0] and self.cfg.get("gemini_key") == config.PROVISIONED[0] and st.get("gkey") != config.PROVISIONED[0]:
                self.cfg["gemini_key"] = ""                           # key of an older licence replaced by a new one
            config.apply_license(self.cfg)
            if bool(self.cfg.get("gemini_key")) != was and hasattr(self, "tr_engine") and self.cfg.get("gemini_key"):
                self.tr_engine.setCurrentText(TR_AI)
        self.lic_chip.setText(chip_text(st))
        low = st.get("valid") and st.get("days_left", 999) <= 7
        self.lic_chip.setStyleSheet("color:#fbbf24;border-color:#b45309;" if low else "")
        if not st.get("valid"):
            self.lock_for_license(st.get("reason", ""))
        elif low and warn:
            QMessageBox.information(self, "License", f"License នៅសល់ {st['days_left']} ថ្ងៃ — សូមទាក់ទងម្ចាស់ដើម្បីបន្ត។")

    def lock_for_license(self, reason=""):
        if getattr(self, "_locked", False): return
        self._locked = True
        if not LicenseDialog(LOGO, reason, self).exec():
            QApplication.instance().quit(); os._exit(0)
        self._locked = False; self.refresh_license()

    def change_license(self):
        if LicenseDialog(LOGO, "", self).exec(): self.refresh_license()

    def set_cfg(self, k, v):
        self.cfg[k] = v; config.save(self.cfg)

    def set_theme(self, name):
        """Whole-app accent colour (Cyan / Violet / Rose / Emerald / Gold), remembered for the next start."""
        QApplication.instance().setStyleSheet(build_qss(name)); self.set_cfg("theme", name)

    def log(self, msg):
        self.logs.append(f"[{time.strftime('%H:%M:%S')}] {msg}")

    def show_log(self):
        d = QDialog(self); d.setWindowTitle("Log"); d.resize(700, 400); v = QVBoxLayout(d)
        t = QPlainTextEdit("\n".join(self.logs)); t.setReadOnly(True); v.addWidget(t); d.exec()

    def refresh_models(self):
        try:
            names = ai.list_models(self.cfg["gemini_key"])
        except Exception as e:
            return QMessageBox.warning(self, "Gemini", f"ទាញ model មិនបាន:\n{e}")
        cur = self.model.currentText()
        self.model.blockSignals(True); self.model.clear(); self.model.addItems(names)
        self.model.setCurrentText(cur if cur in names else names[0]); self.model.blockSignals(False)
        self.set_cfg("gemini_model", self.model.currentText())
        self.status_lbl.setText(f"Gemini models: {len(names)}")

    def open_settings(self):
        d = QDialog(self); d.setWindowTitle("Settings / API Keys"); d.resize(620, 430); v = QVBoxLayout(d)
        v.addWidget(lbl("Gemini API Keys  (1 key ក្នុង 1 បន្ទាត់ — ដាក់បានច្រើន ពេលណាមួយ limit វានឹងប្តូរទៅ key បន្ទាប់ដោយស្វ័យប្រវត្តិ)", "muted"))
        prov = bool(config.PROVISIONED[0]) and self.cfg["gemini_key"] == config.PROVISIONED[0]
        gem = QPlainTextEdit("" if prov else self.cfg["gemini_key"]); gem.setPlaceholderText("(ផ្តល់ដោយ License — មិនបាច់បំពេញ)" if prov else "AIza…\nAIza…\nAIza…"); gem.setFixedHeight(120)
        v.addWidget(gem)
        cnt = lbl("", "chip"); v.addWidget(cnt)
        gem.textChanged.connect(lambda: cnt.setText(f"Gemini keys: {len(ai.split_keys(gem.toPlainText()))}"))
        cnt.setText("Gemini: ផ្តល់ដោយ License ✔" if prov else f"Gemini keys: {len(ai.split_keys(gem.toPlainText()))}")
        v.addWidget(lbl("គ្មាន key? ប្រើ  Whisper (Local) + Free (No API key) បានគ្រប់មុខងារ — មិនចាំបាច់ដាក់ key ទេ", "muted"))
        f = QFormLayout(); size = QComboBox(); size.addItems(["tiny", "base", "small", "medium", "large-v3"])
        size.setCurrentText(self.cfg["whisper_size"]); f.addRow("Whisper size (tiny/base = លឿន)", size)
        dev = QComboBox(); dev.addItems(["auto", "cpu", "cuda"]); dev.setCurrentText(self.cfg.get("device", "auto"))
        dev.setToolTip("auto = ជ្រើស GPU/CPU ណាលឿនជាងដោយស្វ័យប្រវត្តិ (GPU ចាស់/តូច ប្រើ CPU)")
        f.addRow("Device (auto = GPU/CPU លឿនជាង)", dev); v.addLayout(f)
        bb = QDialogButtonBox(QDialogButtonBox.Save | QDialogButtonBox.Cancel); v.addWidget(bb)
        bb.accepted.connect(d.accept); bb.rejected.connect(d.reject)
        if d.exec():
            mine = "\n".join(ai.split_keys(gem.toPlainText()))
            self.cfg.update(gemini_key=mine or (config.PROVISIONED[0] if prov else ""), whisper_size=size.currentText(), device=dev.currentText())
            from core import device as _dev; _dev.set_mode(self.cfg["device"])
            config.save(self.cfg)
            if self.cfg["gemini_key"]: self.refresh_models()

    # ================================================================== left: VISUALS
    def tool_button(self, icon, name, checkable=False):
        b = QPushButton(); b.setObjectName("tool"); b.setCheckable(checkable)
        b.setMinimumHeight(66); b.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Fixed)
        lay = QVBoxLayout(b); lay.setContentsMargins(4, 4, 4, 3); lay.setSpacing(0)
        i = QLabel(icon); i.setAlignment(Qt.AlignCenter); i.setStyleSheet("font-size:22px;")
        n = QLabel(name); n.setAlignment(Qt.AlignCenter); n.setWordWrap(True); n.setStyleSheet("font-size:12px;font-weight:600;")
        for l in (i, n): l.setAttribute(Qt.WA_TransparentForMouseEvents)
        lay.addWidget(i); lay.addWidget(n)
        return b

    def build_visuals(self):
        p = frame(); p.setMinimumWidth(236); p.setMaximumWidth(320)
        v = QVBoxLayout(p); v.setContentsMargins(12, 10, 12, 10); v.setSpacing(8)
        head = QHBoxLayout(); head.setSpacing(10)
        logo = QSvgWidget(LOGO); logo.setFixedSize(38, 38); head.addWidget(logo)
        tv = QVBoxLayout(); tv.setSpacing(0)
        tv.addWidget(lbl("VISUALS", "h2")); tv.addWidget(lbl("Text · Blur · Subtitles · Logo", "muted"))
        head.addLayout(tv); head.addStretch(1); v.addLayout(head)
        self.panel_led = LedBar(4); v.addWidget(self.panel_led)

        sa = QScrollArea(); sa.setWidgetResizable(True)
        sa.setHorizontalScrollBarPolicy(Qt.ScrollBarAlwaysOff)
        inner = QWidget(); g = QGridLayout(inner); g.setSpacing(8); g.setContentsMargins(0, 0, 4, 0)
        tools = [("T", "Text", self.t_text, False), ("💬", "Subtitles", self.t_subs, False),
                 ("🌫", "Blur", self.t_blur, False), ("🔎", "Read Screen Text", self.t_ocr, False),
                 ("🖼", "Photo / logo", self.t_photo, False), ("👤", "Avatar", self.t_avatar, False),
                 ("📢", "Add Sponsor", self.t_sponsor, False), ("©", "Add Watermark", self.t_wm, False),
                 ("🔇", "Mute Original", self.t_mute, True), ("🎼", "Keep Music", self.t_bgm, True),
                 ("🎵", "Music", self.t_music, False),
                 ("⬇", "Import SRT", self.open_srt, False), ("⬆", "Export SRT", self.save_srt, False)]
        self.tool_btns = {}
        COLS = 2
        for i, (ic, name, fn, toggle) in enumerate(tools):
            b = self.tool_button(ic, name, toggle or name in ("Music", "Subtitles"))
            if toggle:
                b.clicked.connect(fn)
            else:
                b.clicked.connect(lambda _=False, f=fn: f())
            g.addWidget(b, i // COLS, i % COLS); self.tool_btns[name] = b
        self.tool_btns["Mute Original"].setChecked(self.mute_orig)
        self.tool_btns["Subtitles"].setChecked(True)
        self.tool_btns["Text"].setToolTip("សរសេរអក្សរលើវីដេអូ — ជ្រើស font / style / ពណ៌។ ចុចទ្វេលើអក្សរដើម្បីកែ")
        self.tool_btns["Subtitles"].setToolTip("Subtitle ខ្មែរលើវីដេអូ — កែ font/style/ទីតាំង (អូសបាន) ហើយចុចទ្វេលើវាដើម្បីកែអត្ថបទ")
        self.tool_btns["Blur"].setToolTip("Blur box: អូសទៅដាក់លើអក្សរចិន — អូសជ្រុងស៊ីអាំងដើម្បីប្តូរទំហំ")
        self.tool_btns["Read Screen Text"].setToolTip("អាន hard-sub (ឧ. ចិន) ក្នុងតំបន់ Blur box ជា text")
        self.tool_btns["Mute Original"].setToolTip("បិទសំឡេងនិយាយដើមរបស់វីដេអូ — ចាក់/Export តែសំឡេង AI ខ្មែរ")
        self.tool_btns["Keep Music"].setToolTip("រក្សាតន្ត្រី/ផ្ទៃក្រោយដើម (បន្ថយសំឡេងនិយាយ) — Export ភ្លាមៗ (វិនាទី)។ ចង់ស្អាតជាង៖ config music_mode = ai (demucs យឺត)")
        g.setRowStretch((len(tools) + COLS - 1) // COLS, 1)
        sa.setWidget(inner); v.addWidget(sa, 1)
        return p

    def tmp(self, name):
        return os.path.join(self.work, f"{name}_{next(self.counter)}.png")

    def t_bgm(self, on): self.isolate_bgm = on
    def t_mute(self, on):
        self.mute_orig = on; self.apply_mute(); self.set_cfg("mute_orig", bool(on))

    def t_blur(self): self.view.add_blur()

    # ---- text overlays: write on the video, edit later (double-click), pretty fonts / styles
    def place_text(self, name, text, style, where):
        fw, fh = self.view.frame_size()
        out = self.tmp(name); render_styled_image(text, style, fh, int(fw * 0.92)).save(out)
        self.view.add_png(out, name, where, None, {"text": text, "style": style})

    def add_text_overlay(self, name, preset, where, title):
        fw, fh = self.view.frame_size()
        st = dict(DEFAULT_STYLE); st.update(STYLE_PRESETS[preset])
        dlg = StyleDialog(self, st, "", fh, title)
        if not dlg.exec(): return
        text = dlg.result_text().strip()
        if text: self.place_text(name, text, dlg.result_style(), where)

    def t_text(self): self.add_text_overlay("text", "Classic", "center", "Text លើវីដេអូ")
    def t_sponsor(self): self.add_text_overlay("sponsor", "Sponsor", "bottom", "Sponsor")
    def t_wm(self): self.add_text_overlay("watermark", "Watermark", "br", "Watermark")

    def edit_text_item(self, it):
        d = it.data(0) or {}
        fw, fh = self.view.frame_size()
        dlg = StyleDialog(self, d.get("style") or DEFAULT_STYLE, d.get("text", ""), fh, "កែអក្សរ")
        if not dlg.exec(): return
        text = dlg.result_text().strip()
        if not text: return
        style = dlg.result_style(); out = self.tmp(d.get("name", "text"))
        render_styled_image(text, style, fh, int(fw * 0.92)).save(out)
        self.view.update_text_item(it, out, text, style)

    def edit_selected(self):
        it = self.view.selected_overlay()
        if it is None:
            return QMessageBox.information(self, "កែ", "ចុចជ្រើស អក្សរ / Blur / រូប លើវីដេអូជាមុន។\n(ចុចទ្វេលើអក្សរ ក៏កែបានដែរ)")
        if (it.data(0) or {}).get("text") is not None:
            self.edit_text_item(it)
        else:
            QMessageBox.information(self, "កែ", "Blur / រូប៖ អូសដើម្បីផ្លាស់ទី — Blur អូសជ្រុងស៊ីអាំងដើម្បីប្តូរទំហំ — ឬប្រើប៊ូតុង ＋ ／ －")

    def resize_selected(self, f):
        if not self.view.scale_selected(f):
            QMessageBox.information(self, "ទំហំ", "ចុចជ្រើសអក្សរ / Blur / រូប លើវីដេអូជាមុន")

    def t_photo(self):
        p, _ = QFileDialog.getOpenFileName(self, "Photo / logo", "", IMG_EXT)
        if p: self.view.add_png(p, "logo", "tl", self.view.canvas_size[0] * 0.18)

    def t_avatar(self):
        p, _ = QFileDialog.getOpenFileName(self, "Avatar image", "", IMG_EXT)
        if p: self.view.add_png(circle_png(p, self.tmp("avatar"), int(self.view.canvas_size[1] * 0.16)), "avatar", "tl")

    def t_music(self):
        p, _ = QFileDialog.getOpenFileName(self, "Background music", "", "Audio (*.mp3 *.wav *.m4a *.ogg *.flac)")
        if p:
            self.music = p
        elif self.music and QMessageBox.question(self, "Music", "Remove background music?") == QMessageBox.Yes:
            self.music = None
        b = self.tool_btns["Music"]; b.setChecked(bool(self.music)); b.setToolTip(os.path.basename(self.music or ""))

    # ---- Khmer subtitles on the video
    def t_subs(self):
        d = QDialog(self); d.setWindowTitle("Subtitles ខ្មែរ"); d.setMinimumWidth(440); v = QVBoxLayout(d)
        show = QCheckBox("បង្ហាញ subtitle លើវីដេអូ"); show.setChecked(self.show_sub)
        burn = QCheckBox("ដាក់ subtitle ចូលក្នុងវីដេអូ ពេល Export"); burn.setChecked(self.burn)
        v.addWidget(show); v.addWidget(burn)
        pos = QComboBox(); pos.addItems(["រក្សាទីតាំងដែលអូសដាក់ (Custom)", "ខាងក្រោម (Bottom)", "កណ្តាល (Middle)", "ខាងលើ (Top)"])
        r = QHBoxLayout(); r.addWidget(lbl("ទីតាំង", "muted")); r.addWidget(pos, 1); v.addLayout(r)
        pre = QComboBox(); pre.addItem("— Style subtitle ស្អាតៗ (ជ្រើសរើស) —")
        pre.addItems(["TikTok Khmer", "Khmer Gold Glow", "Pink Neon Box", "Cyan Pop", "Yellow Subtitle", "Neon Cyan", "Boxed Black", "Classic"])
        def pick_preset(i):
            if i > 0: self.sub_style.update(STYLE_PRESETS[pre.itemText(i)])
        pre.currentIndexChanged.connect(pick_preset); v.addWidget(pre)
        chars = QSpinBox(); chars.setRange(10, 60); chars.setValue(int(self.cfg.get("sub_chars", 28)))
        chars.setToolTip("ប្រយោគវែងត្រូវបានកាត់ជាបំណែកខ្លីៗ តាមពេលនិយាយ (តួអក្សរ/បំណែក)")
        rc = QHBoxLayout(); rc.addWidget(lbl("អក្សរអតិបរមា/ជួរ (តូច = ខ្លី)", "muted")); rc.addWidget(chars, 1); v.addLayout(rc)
        # size: small is allowed (2% .. 9% of the video height), live preview while you drag
        sz = QSlider(Qt.Horizontal); sz.setRange(20, 90); sz.setValue(int(round(float(self.sub_style.get("size_pct", 4.0)) * 10)))
        szl = lbl("", "chip"); szl.setMinimumWidth(52); szl.setAlignment(Qt.AlignCenter)
        size_touched = [False]
        def live(val, user=True):
            szl.setText(f"{val / 10:.1f}%")
            if user:
                size_touched[0] = True
                st = dict(self.sub_style, size_pct=val / 10.0); self.view.set_sub_style(st, self.sub_pos); self.update_sub_now()
        sz.valueChanged.connect(live); live(sz.value(), False)
        rs = QHBoxLayout(); rs.addWidget(lbl("ទំហំអក្សរ", "muted")); rs.addWidget(sz, 1); rs.addWidget(szl); v.addLayout(rs)
        qs = QHBoxLayout()
        for label, val in (("តូចណាស់", 24), ("តូច", 30), ("មធ្យម", 40), ("ធំ", 55)):
            b = QPushButton(label); b.clicked.connect(lambda _=False, x=val: sz.setValue(x)); qs.addWidget(b)
        v.addLayout(qs)
        fill = QCheckBox("ពង្រីកអក្សរខ្លីឱ្យពេញទទឹង (បិទ = ទំហំស្មើគ្នា)"); fill.setChecked(bool(self.sub_style.get("fill", False))); v.addWidget(fill)
        sb = QPushButton("🎨  Font & Style ស្អាតៗ …"); v.addWidget(sb)
        def pick_style():
            dlg = StyleDialog(d, self.sub_style, None, self.view.frame_size()[1], "Subtitle style")
            if dlg.exec():
                self.sub_style = dlg.result_style(); size_touched[0] = False
                sz.blockSignals(True); sz.setValue(int(round(float(self.sub_style.get("size_pct", 4.0)) * 10))); live(sz.value(), False); sz.blockSignals(False)
        sb.clicked.connect(pick_style)
        v.addWidget(lbl("គន្លឹះ៖ អូស subtitle លើវីដេអូដើម្បីដាក់ទីតាំង • ចុចទ្វេលើវាដើម្បីកែអត្ថបទ", "muted"))
        bb = QDialogButtonBox(QDialogButtonBox.Ok | QDialogButtonBox.Cancel); v.addWidget(bb)
        bb.accepted.connect(d.accept); bb.rejected.connect(d.reject)
        if d.exec():
            self.show_sub, self.burn = show.isChecked(), burn.isChecked()
            if size_touched[0]: self.sub_style["size_pct"] = sz.value() / 10.0
            self.sub_style["fill"] = fill.isChecked()
            i = pos.currentIndex()
            if i > 0: self.sub_pos[1] = SUB_Y[("bottom", "middle", "top")[i - 1]]; self.sub_pos[0] = 0.5
            self.cfg.update(sub_style=self.sub_style, sub_pos=self.sub_pos, sub_chars=chars.value()); config.save(self.cfg)
            self.refresh_timeline()
            self.view.set_sub_style(self.sub_style, self.sub_pos); self.view.set_sub_visible(self.show_sub)
            self.update_sub_now()
        else:                                              # cancelled: undo the live size preview
            self.view.set_sub_style(self.sub_style, self.sub_pos); self.update_sub_now()
        self.tool_btns["Subtitles"].setChecked(self.show_sub)

    def on_sub_pos(self, fx, fy):
        self.sub_pos = [fx, fy]
        self.cfg.update(sub_pos=self.sub_pos); config.save(self.cfg)

    def sub_at(self, t):
        for k, (a, b, tx) in enumerate(self.sub_cache):
            if a <= t < b:
                self.cur_sub_idx = self.sub_src[k] if k < len(self.sub_src) else k; return tx
        self.cur_sub_idx = -1
        return ""

    def update_sub_now(self):
        self.view.set_subtitle(self.sub_at(self.player.position() / 1000.0), force=True)

    def edit_current_sub(self):
        self.sub_at(self.player.position() / 1000.0)
        k = self.cur_sub_idx
        if k < 0 or k >= self.table.rowCount():
            return QMessageBox.information(self, "Subtitle", "គ្មាន subtitle នៅពេលនេះទេ។ ចុច ▶ ឬអូស slider ទៅចំណុចដែលមាន subtitle។")
        cur = self.table.item(k, 3).text()
        txt, ok = QInputDialog.getMultiLineText(self, "កែ Subtitle", f"ជួរទី {k + 1}:", cur)
        if ok and txt.strip() != cur:
            self.table.item(k, 3).setText(txt.strip())

    def build_sub_track(self, segs, fw, fh):
        """One transparent full-frame PNG per subtitle line (Qt renders the Khmer, so the export looks like the preview)."""
        d = os.path.join(self.work, "subs_png"); shutil.rmtree(d, ignore_errors=True); os.makedirs(d)
        items, imgs = [], []
        pieces = split_segments([(s.start, s.end, s.text) for s in segs], int(self.cfg.get("sub_chars", 28)))
        for pa, pb, ptxt, _src in pieces:
            if ptxt.strip():
                imgs.append((pa, pb, render_styled_image(ptxt, self.sub_style, fh, int(fw * 0.94))))
        if not imgs: return {"items": [], "w": fw, "h": 2}
        # ONE narrow band (full width, just tall enough for the biggest line) instead of a full 1080x1920 frame per line:
        # FFmpeg then scales/overlays a thin strip per video frame = much faster export
        bottom = max(8, min(fh, int(self.sub_pos[1] * fh)))
        band_h = min(bottom, max(i.height() for _, _, i in imgs) + 4)
        top = bottom - band_h
        for k, (pa, pb, img) in enumerate(imgs):
            fr = QImage(fw, band_h, QImage.Format_ARGB32); fr.fill(0)
            x = int(self.sub_pos[0] * fw - img.width() / 2); y = band_h - img.height()
            p = QPainter(fr); p.drawImage(x, max(0, y), img); p.end()
            path = os.path.join(d, f"s{k:04d}.png"); fr.save(path); items.append((pa, pb, path))
        return {"items": items, "w": fw, "h": band_h, "y": top, "fh": fh}

    def t_ocr(self):
        """Read hard-coded on-screen text (e.g. Chinese subtitles) inside the Blur box region, using Gemini vision."""
        if not self.need_video(): return
        if not self.cfg["gemini_key"]:
            return QMessageBox.information(self, "Read Screen Text", "មុខងារនេះត្រូវការ Gemini API Key (Settings ⚙)")
        rects = self.view.blur_source_rects()
        if not rects:
            r = QMessageBox.question(self, "Read Screen Text",
                "មិនទាន់មាន Blur box ទេ។ ចុច 🌫 Blur ហើយអូសទៅដាក់លើតំបន់អក្សរជាមុន។\n\nអានពេញអេក្រង់ទាំងមូលទេ?",
                QMessageBox.Yes | QMessageBox.No)
            if r != QMessageBox.Yes: return
            region = None
        else:
            region = rects[0]
        step, ok = QInputDialog.getDouble(self, "Read Screen Text", "ថត frame រៀងរាល់ប៉ុន្មានវិនាទី:", 1.0, 0.2, 5.0, 1)
        if not ok: return
        cfg, video, work = dict(self.cfg), self.video, self.work
        def done(segs):
            if not segs: return QMessageBox.information(self, "Read Screen Text", "មិនអាចអានអក្សរអ្វីបានទេ")
            self.load_segs(segs)
        self.job(lambda p: ai.read_screen_text(cfg, video, region, step, work, p), done)

    # ================================================================== centre: VIDEO
    def build_video(self):
        p = frame(); v = QVBoxLayout(p); v.setContentsMargins(8, 6, 8, 6); v.setSpacing(5)
        top = QHBoxLayout()
        self.orient = lbl("PORTRAIT", "muted")
        self.aspect = QComboBox(); self.aspect.addItems(MODES + ["Custom…"])
        self.aspect.setToolTip("ទំហំស៊ុមវីដេអូ — 9:16 = TikTok / Reels / Shorts។ Custom… = ដាក់ W:H តាមចិត្ត")
        self.aspect.activated.connect(self.on_aspect)
        self.fit_chk = QCheckBox("Fit"); self.fit_chk.setChecked(True)
        self.fit_chk.setToolTip("Fit = បង្ហាញវីដេអូពេញ (មានគែមខ្មៅ)   |   មិនធីក = កាត់ឲ្យពេញស៊ុម")
        self.zoom_lbl = lbl("100%", "chip"); self.file_lbl = lbl("—", "muted")
        for x in (self.orient, self.aspect, self.fit_chk, self.zoom_lbl): top.addWidget(x)
        top.addStretch(1); top.addWidget(self.file_lbl); v.addLayout(top)

        tb = QHBoxLayout()
        for txt, tip, fn in (("⇋", "Flip horizontal", lambda: self.view.toggle_flip("h")),
                             ("⇅", "Flip vertical", lambda: self.view.toggle_flip("v")),
                             ("▣", "ប្តូរទំហំស៊ុម (9:16 → 16:9 → …)", self.cycle_crop),
                             ("↺", "Reset ទៅ 9:16", self.reset_tf),
                             ("⛶", "Full screen (Esc = ចេញ)", self.toggle_focus)):
            b = QPushButton(txt); b.setObjectName("icon"); b.setToolTip(tip); b.clicked.connect(lambda _=False, f=fn: f()); tb.addWidget(b)
            if txt == "⛶": self.focus_btn = b
        self.src_chip = lbl(f"Source: {self.cfg.get('source_lang', 'Auto')}", "chip")
        tb.addStretch(1); tb.addWidget(self.src_chip); v.addLayout(tb)

        row = QHBoxLayout()
        self.view = VideoView(self.player); self.view.setMinimumSize(160, 260)
        self.view.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Expanding)
        self.fit_chk.toggled.connect(self.view.set_fit)
        row.addWidget(self.view, 1)
        side = QVBoxLayout(); side.setSpacing(5)
        for txt, tip, fn in (("📷", "Snapshot", self.snapshot), ("🖼", "ដាក់រូប / Logo", self.t_photo),
                             ("T", "ដាក់អក្សរលើវីដេអូ", self.t_text), ("✏", "កែអក្សរដែលបានជ្រើស", self.edit_selected),
                             ("＋", "ធំជាងមុន", lambda: self.resize_selected(1.15)),
                             ("－", "តូចជាងមុន", lambda: self.resize_selected(1 / 1.15)),
                             ("🗑", "លុបអ្វីដែលបានជ្រើស", lambda: self.view.delete_selected())):
            b = QPushButton(txt); b.setObjectName("icon"); b.setToolTip(tip); b.clicked.connect(lambda _=False, f=fn: f()); side.addWidget(b)
        side.addStretch(1); row.addLayout(side); v.addLayout(row, 1)

        ctl = QHBoxLayout()
        self.play_btn = QPushButton("▶"); self.play_btn.setFixedWidth(44); self.play_btn.clicked.connect(self.toggle_play)
        self.use_dub = QPushButton("🔊 Dub"); self.use_dub.setCheckable(True); self.use_dub.setToolTip("Play dubbed voice")
        self.use_dub.toggled.connect(self.apply_mute)
        self.slider = QSlider(Qt.Horizontal); self.slider.sliderMoved.connect(self.seek_ms)
        self.time_lbl = lbl("00:00 / 00:00", "muted")
        self.vspd = QComboBox(); self.vspd.addItems(["0.75x", "1x", "1.1x", "1.25x", "1.5x", "2x"]); self.vspd.setCurrentText("1x")
        self.vspd.setToolTip("SPEED វីដេអូ: ប្តូរល្បឿនលើ preview និងពេល Export (សំឡេងនិយាយលឿនតាម)")
        self.vspd.currentTextChanged.connect(self.set_vspeed)
        self.stage_cb = QComboBox(); self.stage_cb.addItems(list(STAGE_PRESETS.keys())); self.stage_cb.setCurrentText(self.cfg.get("stage") or "Neon LED")
        self.stage_cb.setToolTip("Style ស៊ុម/ផ្ទៃខាងក្រោយវីដេអូ (Neon / Gold / Gradient) — ចេញក្នុង Export ផង")
        self.stage_cb.currentTextChanged.connect(self.set_stage_preset)
        for x, s in ((self.play_btn, 0), (self.use_dub, 0), (self.slider, 1), (self.time_lbl, 0)): ctl.addWidget(x, s)
        v.addLayout(ctl)
        ctl2 = QHBoxLayout(); ctl2.setSpacing(6)                  # speed + frame style on their own line: the video column can be narrow
        ctl2.addWidget(lbl("SPEED", "muted")); ctl2.addWidget(self.vspd); ctl2.addSpacing(6)
        ctl2.addWidget(lbl("FRAME", "muted")); ctl2.addWidget(self.stage_cb, 1)
        v.addLayout(ctl2)
        st = QHBoxLayout()
        self.status_lbl = lbl("Ready", "muted")
        sp = QPushButton("Show progress"); sp.clicked.connect(lambda: self.bar.setVisible(not self.bar.isVisible()))
        sf_ = QPushButton("Show in folder"); sf_.clicked.connect(lambda: open_folder(self.last_dir))
        st.addWidget(self.status_lbl, 1); st.addWidget(sp); st.addWidget(sf_); v.addLayout(st)
        return p

    def on_aspect(self, i):
        text = self.aspect.itemText(i)
        if text == "Custom…":
            txt, ok = QInputDialog.getText(self, "ទំហំស៊ុម Custom", "ដាក់ W:H (ឧ. 9:16, 4:5, 3:4, 21:9, 2:3):", text="9:16")
            txt = txt.strip()
            if ok and txt != "Original" and valid_mode(txt):
                self.view.set_mode(txt)
            self.sync_aspect(); return
        self.view.set_mode(text)

    def sync_aspect(self):
        m = self.view.mode
        i = self.aspect.findText(m)
        if i < 0:
            self.aspect.insertItem(self.aspect.count() - 1, m); i = self.aspect.findText(m)
        self.aspect.setCurrentIndex(i)

    def cycle_crop(self):
        self.view.cycle_crop(); self.sync_aspect()

    def reset_tf(self):
        self.view.reset_transforms(); self.sync_aspect()
        self.fit_chk.blockSignals(True); self.fit_chk.setChecked(True); self.fit_chk.blockSignals(False)

    def toggle_focus(self):
        self.focus_mode = not self.focus_mode
        for w in (self.visuals_panel, self.dialogue_panel, self.bottom_panel): w.setVisible(not self.focus_mode)
        self.focus_btn.setText("✕" if self.focus_mode else "⛶")

    def exit_focus(self):
        if self.focus_mode: self.toggle_focus()

    def snapshot(self):
        p, _ = QFileDialog.getSaveFileName(self, "Snapshot", "snapshot.png", "PNG (*.png)")
        if p: self.view.snapshot(p)

    # ================================================================== right: DIALOGUE
    def build_dialogue(self):
        p = frame(); v = QVBoxLayout(p); v.setContentsMargins(12, 10, 12, 10)
        # 4 rows; every row is a FlowLayout, so buttons keep their full text and wrap instead of being squeezed/cut
        p.setMinimumWidth(560)
        mk_btn = lambda text, fn, name=None: self._mkbtn(text, fn, name)

        # row 1: title + speech-recognition engine
        r1 = FlowLayout(hspacing=14, vspacing=6)
        th = QWidget(); tv = QVBoxLayout(th); tv.setContentsMargins(0, 0, 0, 0); tv.setSpacing(0)
        tv.addWidget(lbl("DIALOGUE", "muted")); tv.addWidget(lbl("Khmer dub", "h2")); r1.addWidget(th)
        self.eng_btns = {}
        sw = QWidget(); seg = QHBoxLayout(sw); seg.setContentsMargins(0, 0, 0, 0); seg.setSpacing(0)
        for n in ENGINES:
            b = QPushButton(n); b.setObjectName("seg"); b.setCheckable(True); b.setAutoExclusive(True)
            b.clicked.connect(lambda _=False, n=n: self.set_engine(n)); seg.addWidget(b); self.eng_btns[n] = b
        r1.addWidget(sw); v.addLayout(r1)

        # row 2: language / translate engine + the three main actions
        r2 = FlowLayout(); self.lang = QComboBox(); self.lang.addItems(ai.LANGS.keys()); self.lang.setCurrentText(self.cfg["target_lang"])
        self.lang.currentTextChanged.connect(lambda t: self.set_cfg("target_lang", t))
        self.tr_engine = QComboBox(); self.tr_engine.addItems([TR_FREE, TR_AI])
        self.tr_engine.setToolTip("Free = លឿន មិនត្រូវការ API key | Gemini = ឆ្លាត កែប្រយោគឱ្យត្រូវពេលវេលា (ត្រូវការ key)")
        self.tr_engine.setCurrentText(self.cfg.get("tr_engine") or (TR_AI if self.cfg.get("gemini_key") else TR_FREE))
        self.tr_engine.currentTextChanged.connect(lambda t: self.set_cfg("tr_engine", t))
        tbtn = QPushButton("① 🎤 Transcribe"); tbtn.setObjectName("accent"); tbtn.clicked.connect(self.do_transcribe); glow(tbtn, "#2563eb")
        trb = QPushButton("② 🌐 Translate"); trb.clicked.connect(self.do_translate)
        ab = QPushButton("⚡ Auto Dub"); ab.setObjectName("vip"); ab.clicked.connect(self.do_auto); ab.setToolTip("ចុចម្តងគត់: Transcribe → Translate → Voice")
        for x in (self.lang, self.tr_engine, tbtn, trb, ab): r2.addWidget(x)
        v.addLayout(r2)

        # row 3: editing tools + text size (one compact line)
        r3 = FlowLayout(hspacing=6)
        for b in (mk_btn("＋ Add", self.add_line), mk_btn("✎ Edit", self.edit_line), mk_btn("✖ Delete", self.del_lines),
                  mk_btn("🔍 Find", self.find_replace)):
            r3.addWidget(b)
        self.fsize = 14
        r3.addWidget(mk_btn("A−", lambda: self.set_fsize(-1))); self.fs_lbl = lbl("14", "chip"); r3.addWidget(self.fs_lbl)
        r3.addWidget(mk_btn("A+", lambda: self.set_fsize(1)))
        self.follow = QCheckBox("Follow"); self.follow.setToolTip("តាមដានជួរតាមការចាក់វីដេអូ"); self.follow.setChecked(True); r3.addWidget(self.follow)
        v.addLayout(r3)

        self.table = QTableWidget(0, 6)
        self.table.setHorizontalHeaderLabels(["☑", "START", "END", "DUB TEXT", "VOICE PROFILE", "AUDIO"])
        hh = self.table.horizontalHeader(); hh.setSectionResizeMode(3, QHeaderView.Stretch)
        for c, wd in ((0, 32), (1, 108), (2, 108), (4, 120), (5, 100)):
            hh.setSectionResizeMode(c, QHeaderView.Fixed); self.table.setColumnWidth(c, wd)
        hh.sectionClicked.connect(lambda c: c == 0 and self.check_all(len(self.checked_uids()) < self.table.rowCount()))
        self.table.verticalHeader().hide(); self.table.verticalHeader().setDefaultSectionSize(42)
        self.table.setAlternatingRowColors(True); self.table.setSelectionBehavior(QAbstractItemView.SelectRows)
        self.table.setSelectionMode(QAbstractItemView.ExtendedSelection)
        self.table.itemChanged.connect(self.on_item_changed)
        self.table.cellClicked.connect(self.on_cell_clicked)
        v.addWidget(self.table, 1)

        # footer: voices + actions on the selected rows (below the table so the table gets the room)
        r4 = FlowLayout(hspacing=8); r4.addWidget(lbl("VOICE", "muted"))
        r4.addWidget(mk_btn("♂ Male", lambda: self.set_voice("Male 1"), "male"))
        r4.addWidget(mk_btn("♀ Female", lambda: self.set_voice("Actress 1"), "female"))
        r4.addWidget(mk_btn("Detect Speakers", self.do_detect))
        self.sel_lbl = lbl("0 selected", "chip")
        self.setvoice = QComboBox(); self.setvoice.addItem("Set voice for selected…"); self.setvoice.addItems(tts.PROFILES.keys())
        self.setvoice.activated.connect(lambda i: (i > 0 and self.set_voice(self.setvoice.itemText(i)), self.setvoice.setCurrentIndex(0)))
        self.gen_btn = QPushButton("Generate 0 selected"); self.gen_btn.setObjectName("gen"); self.gen_btn.clicked.connect(self.gen_selected)
        clr = QPushButton("Clear"); clr.clicked.connect(lambda: self.check_all(False))
        for x in (self.sel_lbl, self.setvoice, self.gen_btn, clr): r4.addWidget(x)
        v.addLayout(r4)
        return p

    def _mkbtn(self, text, fn, name=None):
        b = QPushButton(text); b.clicked.connect(lambda _=False, f=fn: f())
        if name: b.setObjectName(name)
        return b

    def set_engine(self, n):
        self.cfg["stt_engine"] = n; config.save(self.cfg)
        for k, b in self.eng_btns.items(): b.setChecked(k == n)

    def stt_cfg(self):
        c, n = dict(self.cfg), self.cfg["stt_engine"]
        if n == "Gemini Lite": c.update(stt_engine="Gemini", gemini_model="gemini-3.1-flash-lite")
        elif n == "Whisper": c["stt_engine"] = "Local"
        else:
            c["stt_engine"] = "Gemini"
            if "lite" in str(c.get("gemini_model", "")).lower(): c["gemini_model"] = "gemini-3.5-flash"   # Lite skips dialogue; Lite is for translate (⚡ Lite)
        if c["stt_engine"] == "Gemini" and not ai.split_keys(c.get("gemini_key", "")):
            c["stt_engine"] = "Local"                         # no key: Whisper runs offline, free
        return c

    def set_fsize(self, d):
        self.fsize = max(9, min(30, self.fsize + d)); self.fs_lbl.setText(str(self.fsize))
        self.table.setStyleSheet(f"QTableWidget {{ font-size: {self.fsize}px; }}")

    # ---------- table helpers
    def uid_of(self, r): return self.table.item(r, 0).data(Qt.UserRole)

    def row_of(self, uid):
        for r in range(self.table.rowCount()):
            if self.uid_of(r) == uid: return r
        return -1

    def add_row(self, s, r=None, src=None):
        r = self.table.rowCount() if r is None else r
        self.table.insertRow(r); uid = next(self.counter)
        chk = QTableWidgetItem(); chk.setFlags(Qt.ItemIsUserCheckable | Qt.ItemIsEnabled | Qt.ItemIsSelectable)
        chk.setCheckState(Qt.Unchecked); chk.setData(Qt.UserRole, uid); self.table.setItem(r, 0, chk)
        self.table.setItem(r, 1, QTableWidgetItem(fmt(s.start))); self.table.setItem(r, 2, QTableWidgetItem(fmt(s.end)))
        txt = QTableWidgetItem(s.text); txt.setData(Qt.UserRole, src if src is not None else (s.src or s.text)); self.table.setItem(r, 3, txt)
        cb = QComboBox(); cb.addItems(tts.PROFILES.keys()); cb.setCurrentText(s.voice or tts.default_profile(s.gender))
        cb.currentTextChanged.connect(lambda _=None, u=uid: self.invalidate(u)); self.table.setCellWidget(r, 4, cb)
        cell = QWidget(); h = QHBoxLayout(cell); h.setContentsMargins(4, 0, 4, 0); h.setSpacing(4)
        dot = QLabel("●"); dot.setStyleSheet("color:#334155"); self.dots[uid] = dot
        pl = QPushButton("▶"); pl.setObjectName("icon"); pl.clicked.connect(lambda _=False, u=uid: self.play_row(u))
        rd = QPushButton("↻"); rd.setObjectName("icon"); rd.setToolTip("Regenerate"); rd.clicked.connect(lambda _=False, u=uid: self.gen_uids([u], force=True))
        for x in (dot, pl, rd): h.addWidget(x)
        self.table.setCellWidget(r, 5, cell)

    def load_segs(self, segs):
        self.table.blockSignals(True); self.table.setRowCount(0); self.clips.clear(); self.dots.clear()
        for s in segs: self.add_row(s)
        self.table.blockSignals(False); self.upd_sel(); self.refresh_timeline()

    def row_seg(self, r):
        def tm(c, d):
            try: return parse_time(self.table.item(r, c).text())
            except Exception: return d
        st = tm(1, 0.0); prof = self.table.cellWidget(r, 4).currentText(); it = self.table.item(r, 3)
        return Seg(st, tm(2, st + 2), it.text(), tts.gender_of(prof), it.data(Qt.UserRole) or "", prof)

    def segs(self): return [self.row_seg(r) for r in range(self.table.rowCount())]

    def checked_uids(self):
        return [self.uid_of(r) for r in range(self.table.rowCount()) if self.table.item(r, 0).checkState() == Qt.Checked]

    def check_all(self, on):
        self.table.blockSignals(True)
        for r in range(self.table.rowCount()): self.table.item(r, 0).setCheckState(Qt.Checked if on else Qt.Unchecked)
        self.table.blockSignals(False); self.upd_sel()

    def upd_sel(self):
        n = len(self.checked_uids()); self.sel_lbl.setText(f"{n} selected"); self.gen_btn.setText(f"Generate {n} selected")

    def mark(self, uid):
        d = self.dots.get(uid)
        if d: d.setStyleSheet("color:#22c55e" if uid in self.clips else "color:#334155")

    def invalidate(self, uid):
        self.clips.pop(uid, None); self.mark(uid); self.refresh_timeline()

    def on_item_changed(self, it):
        if it.column() == 0: self.upd_sel()
        else:
            self.invalidate(self.uid_of(it.row()))

    def on_cell_clicked(self, r, c):
        if c in (1, 2, 3): self.seek_ms(int(self.row_seg(r).start * 1000))
        self.timeline.set_selected(r)

    def refresh_timeline(self):
        segs = self.segs()
        pieces = split_segments([(s.start, s.end, s.text) for s in segs], int(self.cfg.get("sub_chars", 28)))   # short readable pieces
        self.sub_cache = [(a, b, tx) for a, b, tx, _ in pieces]; self.sub_src = [i for *_, i in pieces]
        self.timeline.set_data(segs, self.player.duration() / 1000, bool(self.view.overlays))
        self.update_sub_now()

    # ---------- table actions
    def add_line(self):
        r = self.table.currentRow(); r = self.table.rowCount() if r < 0 else r + 1
        prev = self.row_seg(r - 1).end if r > 0 else 0
        self.table.blockSignals(True); self.add_row(Seg(prev, prev + 2, "New line"), r); self.table.blockSignals(False)
        self.refresh_timeline()

    def edit_line(self):
        r = self.table.currentRow()
        if r >= 0: self.table.editItem(self.table.item(r, 3))

    def del_lines(self):
        uids = set(self.checked_uids())
        rows = [self.row_of(u) for u in uids] or [i.row() for i in self.table.selectedIndexes()]
        for r in sorted(set(rows), reverse=True):
            self.clips.pop(self.uid_of(r), None); self.table.removeRow(r)
        self.upd_sel(); self.refresh_timeline()

    def find_replace(self):
        a, ok = QInputDialog.getText(self, "Find", "Find:")
        if not ok or not a: return
        b, ok = QInputDialog.getText(self, "Replace", "Replace with:")
        if not ok: return
        for r in range(self.table.rowCount()):
            it = self.table.item(r, 3); it.setText(it.text().replace(a, b))

    def set_voice(self, profile):
        uids = self.checked_uids() or [self.uid_of(i.row()) for i in self.table.selectedIndexes()]
        for u in set(uids):
            r = self.row_of(u)
            if r >= 0: self.table.cellWidget(r, 4).setCurrentText(profile)

    def open_srt(self):
        p, _ = QFileDialog.getOpenFileName(self, "Import SRT", "", "SRT (*.srt)")
        if p: self.load_segs(read_srt(p))

    def save_srt(self):
        start_dir = self.cfg.get("export_dir") or (os.path.dirname(self.video) if self.video else "")
        p, _ = QFileDialog.getSaveFileName(self, "Export SRT", os.path.join(start_dir, "dub.srt"), "SRT (*.srt)")
        if p:
            write_srt(p, self.segs()); self.set_cfg("export_dir", os.path.dirname(p))
            self.status_lbl.setText(f"✔ SRT: {p}"); reveal_file(p)

    def on_tl_moved(self, i, s, e):
        self.table.blockSignals(True)
        self.table.item(i, 1).setText(fmt(s)); self.table.item(i, 2).setText(fmt(e))
        self.table.blockSignals(False); self.invalidate(self.uid_of(i))

    # ================================================================== bottom: timeline + voice engine
    def build_bottom(self):
        p = frame(); v = QVBoxLayout(p); v.setContentsMargins(10, 6, 10, 6); v.setSpacing(4)
        # row 1 (wraps when narrow): how the dub is made
        r1 = FlowLayout(hspacing=10, vspacing=4); r1.addWidget(lbl("VOICE ENGINE", "muted"))
        self.engine = QComboBox(); self.engine.addItems(["Edge Neural (Free)", "Google gTTS (Free)"]); r1.addWidget(self.engine)
        r1.addWidget(lbl("Auto-Fit", "muted")); self.fit = QComboBox(); self.fit.addItems(["Off", "Soft", "Hard"]); self.fit.setCurrentText("Hard")
        self.fit.setToolTip("ពេលតួសម្តែងនិយាយលឿន សំឡេង AI នឹងនិយាយលឿនតាម (Soft ≤1.35× · Hard ≤1.7×) ហើយកាត់ប្រយោគវែងឲ្យខ្លី")
        r1.addWidget(self.fit)
        self.lite_chk = QCheckBox("⚡ Lite"); self.lite_chk.setChecked(bool(self.cfg.get("lite_translate")))
        self.lite_chk.setToolTip("បកប្រែ + កាត់ខ្លី ដោយ gemini-3.5-flash-lite (លឿនជាង)")
        self.lite_chk.toggled.connect(lambda x: self.set_cfg("lite_translate", bool(x)))
        self.short_chk = QCheckBox("✂ Short"); self.short_chk.setChecked(bool(self.cfg.get("auto_short", True)))
        self.short_chk.setToolTip("បកខ្លី + កាត់ប្រយោគវែងស្វ័យប្រវត្តិ (shorten) ពេលសំឡេងវែងជាងវីដេអូ")
        self.short_chk.toggled.connect(lambda x: (self.set_cfg("auto_short", bool(x)), self.set_cfg("short_translate", bool(x))))
        self.endsync = QCheckBox("END SYNC"); self.endsync.setToolTip("សំឡេងចប់ព្រមគ្នាជាមួយចុងជួរ (ជំនួសឲ្យចាប់ផ្តើមព្រមគ្នា)")
        for x in (self.lite_chk, self.short_chk, self.endsync): r1.addWidget(x)
        v.addLayout(r1)

        # row 2: run / progress (always one line)
        ra = QHBoxLayout(); ra.setSpacing(8)
        self.stop_btn = QPushButton("▶ Play"); self.stop_btn.setObjectName("stop"); self.stop_btn.setProperty("running", "false")
        self.stop_btn.setToolTip("▶ Play / ⏸ Pause វីដេអូ  |  ពេលមានការងារកំពុងដំណើរការ = ■ Stop job")
        self.stop_btn.clicked.connect(self.stop_or_play); ra.addWidget(self.stop_btn)
        self.bar = QProgressBar(); self.bar.setRange(0, 100); self.bar.setMinimumWidth(120); ra.addWidget(self.bar, 1)
        self.prog_lbl = lbl("", "muted"); ra.addWidget(self.prog_lbl)
        gb = QPushButton("③ 🔊 Generate Dub"); gb.setObjectName("gen"); gb.clicked.connect(self.do_dub); ra.addWidget(gb)
        sb = QPushButton("Subtitles"); sb.clicked.connect(self.t_subs); ra.addWidget(sb)
        v.addLayout(ra)

        # row 3 (wraps when narrow): voice shaping + timeline zoom
        r2 = FlowLayout(hspacing=10, vspacing=4)
        def slider(name, a, b, val, fmtf):
            s = QSlider(Qt.Horizontal); s.setRange(a, b); s.setValue(val); s.setFixedWidth(96)
            l = lbl(fmtf(val), "chip"); l.setMinimumWidth(62); l.setAlignment(Qt.AlignCenter)
            s.valueChanged.connect(lambda x: l.setText(fmtf(x)))
            cell = QWidget(); ch = QHBoxLayout(cell); ch.setContentsMargins(0, 0, 0, 0); ch.setSpacing(6)
            for w_ in (lbl(name, "muted"), s, l): ch.addWidget(w_)
            r2.addWidget(cell); return s
        self.pitch = slider("PITCH", -6, 6, 0, lambda x: f"{x} ST")
        self.vol = slider("VOL", 20, 200, 100, lambda x: f"{x}%")
        self.speed = slider("SPEED", 50, 200, 100, lambda x: f"{x / 100:.2f}x")
        self.bgvol = slider("BGM", 0, 150, 80, lambda x: f"{x}%")
        self.reverb = QPushButton("Reverb"); self.reverb.setCheckable(True); r2.addWidget(self.reverb)
        rs = QPushButton("Reset"); rs.clicked.connect(self.reset_voice); r2.addWidget(rs)
        self.zi = 3; zo = QPushButton("−"); zi = QPushButton("＋"); self.zlbl = lbl("6×", "chip")
        zo.setObjectName("icon"); zi.setObjectName("icon"); zo.setToolTip("Zoom out"); zi.setToolTip("Zoom in")
        zo.clicked.connect(lambda: self.zoom(-1)); zi.clicked.connect(lambda: self.zoom(1))
        zc = QWidget(); zh = QHBoxLayout(zc); zh.setContentsMargins(0, 0, 0, 0); zh.setSpacing(4)
        for x in (lbl("TIMELINE", "muted"), zo, self.zlbl, zi): zh.addWidget(x)
        r2.addWidget(zc)
        v.addLayout(r2)

        row = QHBoxLayout(); row.setSpacing(0)
        labels = QWidget(); labels.setFixedSize(130, 150)
        for txt, y in (("VISUALS", 22), ("T1  SUBTITLES", 56), ("AI  GENERATED\nAUDIO", 92)):
            l = lbl(txt, "muted"); l.setParent(labels); l.move(8, y); l.resize(120, 34)
        row.addWidget(labels)
        self.timeline = Timeline(); self.timeline.seek.connect(lambda t: self.seek_ms(int(t * 1000)))
        self.timeline.moved.connect(self.on_tl_moved)
        self.tl_scroll = QScrollArea(); self.tl_scroll.setWidget(self.timeline); self.tl_scroll.setFixedHeight(150)
        row.addWidget(self.tl_scroll, 1); v.addLayout(row)
        return p

    def zoom(self, d):
        self.zi = max(0, min(len(ZOOMS) - 1, self.zi + d)); self.timeline.set_zoom(ZOOMS[self.zi])
        self.zlbl.setText(f"{ZOOMS[self.zi] / 10:.0f}×")

    def reset_voice(self):
        self.pitch.setValue(0); self.vol.setValue(100); self.speed.setValue(100); self.bgvol.setValue(80); self.reverb.setChecked(False)

    def opts(self):
        return {"speed": self.speed.value() / 100, "pitch": self.pitch.value(), "reverb": self.reverb.isChecked(),
                "fit": self.fit.currentText(), "gtts": self.engine.currentText().startswith("Google"),
                "vol": self.vol.value() / 100, "end_sync": self.endsync.isChecked()}

    # ================================================================== player
    def open_video(self):
        p, _ = QFileDialog.getOpenFileName(self, "Open Video", "", VIDEO_EXT)
        if p: self.load_video(p)

    def load_video(self, p):
        self.video = p; self.dub_wav = None; self.clips.clear()
        self.player.setSource(QUrl.fromLocalFile(p)); self.file_lbl.setText(os.path.basename(p)); self.file_chip.setText("🎬  " + os.path.basename(p)); self.last_dir = os.path.dirname(p)
        try:
            w, h = media.video_size(p)
            self.orient.setText("LANDSCAPE" if w >= h else "PORTRAIT")
        except Exception: pass
        for u in list(self.dots): self.mark(u)

    def toggle_play(self):
        if not self.video:                             # nothing loaded yet: Play opens the file dialog
            return self.open_video()
        if self.player.playbackState() == QMediaPlayer.PlayingState:
            self.player.pause()
        else:
            self.player.play()

    def set_vspeed(self, txt):
        try: self.vspeed = float(txt.rstrip("x"))
        except Exception: self.vspeed = 1.0
        for p in (self.player, self.dplayer): p.setPlaybackRate(self.vspeed)

    def set_stage_preset(self, name):
        self.set_cfg("stage", name); self.view.set_stage(STAGE_PRESETS.get(name))

    def sync_play_btns(self):
        """▶/⏸ (video) and the bottom button (▶ Play / ⏸ Pause, or ■ Stop job while a job runs) follow the real state."""
        playing = self.player.playbackState() == QMediaPlayer.PlayingState
        self.play_btn.setText("⏸" if playing else "▶")
        if self.job_running: self.stop_btn.setText("■ Stop job")
        else: self.stop_btn.setText("⏸ Pause" if playing else "▶ Play")

    def set_running(self, running):
        self.job_running = running
        self.stop_btn.setProperty("running", "true" if running else "false")
        st = self.stop_btn.style(); st.unpolish(self.stop_btn); st.polish(self.stop_btn)
        self.stop_btn.setEnabled(True); self.sync_play_btns()

    def on_state(self, st):
        """The ▶ / ⏸ buttons always follow the real player state (also after a job, a seek or the end of the video)."""
        playing = st == QMediaPlayer.PlayingState
        self.sync_play_btns()
        if playing and self.use_dub.isChecked() and self.dub_wav:
            self.dplayer.setPosition(self.player.position()); self.dplayer.play()
        elif not playing:
            self.dplayer.pause()

    def seek_ms(self, ms):
        self.player.setPosition(ms)
        if self.dub_wav: self.dplayer.setPosition(ms)

    def apply_mute(self, *_):
        self.aout.setMuted(bool(self.mute_orig or (self.use_dub.isChecked() and self.dub_wav)))
        if self.use_dub.isChecked() and self.dub_wav and self.player.playbackState() == QMediaPlayer.PlayingState:
            self.dplayer.setPosition(self.player.position()); self.dplayer.play()
        elif not self.use_dub.isChecked():
            self.dplayer.pause()

    def on_pos(self, ms):
        if not self.slider.isSliderDown(): self.slider.setValue(ms)
        t = ms / 1000; self.timeline.set_pos(t)
        f = lambda x: f"{int(x // 60):02}:{int(x % 60):02}"
        self.time_lbl.setText(f"{f(t)} / {f(self.player.duration() / 1000)}")
        self.zoom_lbl.setText(f"{self.view.zoom_percent()}%")
        self.view.set_subtitle(self.sub_at(t))                         # Khmer subtitle on the video
        if self.player.playbackState() == QMediaPlayer.PlayingState:
            self.tl_scroll.ensureVisible(int(t * self.timeline.pps), 0, 120, 0)
            k = self.cur_sub_idx
            if self.follow.isChecked() and 0 <= k < self.table.rowCount() and self.table.currentRow() != k:
                self.table.blockSignals(True); self.table.selectRow(k); self.table.blockSignals(False)
                self.table.scrollToItem(self.table.item(k, 3)); self.timeline.set_selected(k)

    # ================================================================== jobs
    def job(self, fn, on_done=None):
        if self._w and self._w.isRunning():
            if getattr(self._w, "finished_ok", False):
                self._w.wait(3000)                    # job already reported done, thread is just exiting
            if self._w.isRunning():
                return QMessageBox.information(self, "Busy", "មានការងារកំពុងដំណើរការ: " + self.status_lbl.text() +
                                               "\n\nសូមរង់ចាំ ឬចុច ■ Stop job")
        w = Worker(fn); self._w = w
        t0, state = time.time(), {"p": 0}
        tick = QTimer(self); tick.setInterval(1000)
        def beat():
            self.prog_lbl.setText(f"{state['p']}% · {int(time.time() - t0)}s")
        tick.timeout.connect(beat)
        def prog(p, m):
            state["p"] = p
            self.bar.setValue(p); beat()
            if m: self.status_lbl.setText("⏳ " + m)
        def ok(r):
            w.finished_ok = True; tick.stop(); self.set_running(False)
            self.bar.setValue(100); self.status_lbl.setText("✔ Ready"); self.log("done")
            if on_done: on_done(r)
        def bad(e):
            w.finished_ok = True; tick.stop(); self.set_running(False); self.bar.setValue(0); self.prog_lbl.setText("")
            if e == "__stopped__": self.status_lbl.setText("■ Stopped"); return
            self.status_lbl.setText("✖ " + e.splitlines()[0][:150]); self.log(e); QMessageBox.critical(self, "Error", e)
        w.progress.connect(prog); w.done.connect(ok); w.failed.connect(bad)
        self.set_running(True); self.bar.setValue(0)
        self.status_lbl.setText("⏳ កំពុងដំណើរការ… (សូមរង់ចាំ)"); tick.start(); w.start()

    def stop_or_play(self):
        """Job running -> stop it. Otherwise this is the ▶ Play / ⏸ Pause button (opens a video if none is loaded)."""
        if self.job_running and self._w and self._w.isRunning():
            self._w.stop(); self.stop_btn.setEnabled(False); self.stop_btn.setText("កំពុងបញ្ឈប់…")
            self.status_lbl.setText("■ កំពុងបញ្ឈប់… (រង់ចាំសំណើរបច្ចុប្បន្នចប់)")
        else:
            self.toggle_play()

    def need_video(self):
        if not self.video:
            QMessageBox.information(self, "Video", "សូមបើក Video ជាមុន (📂)"); return False
        return True

    def do_transcribe(self):
        if not self.need_video(): return
        cfg, video, work, lang = self.stt_cfg(), self.video, self.work, self.src_lang.currentText()
        if lang == self.lang.currentText():                 # e.g. Source = Khmer while the video is Chinese: forced language = wrong / skipped speech
            self.log(f"⚠ Source = Target ({lang}) → ប្រើ Auto-detect ជំនួស"); lang = "Auto"
        def done(segs):
            tts.assign_voices(segs); self.load_segs(segs)
            if not segs:
                QMessageBox.information(self, "Transcribe",
                    "រកមិនឃើញសម្លេងនិយាយក្នុងវីដេអូនេះទេ (វីដេអូនេះប្រហែលគ្មានសំឡេងនិយាយ មានតែតន្ត្រី "
                    "និងអក្សររត់ក្នុងរូប)។\n\nសូមសាកល្បង 🌫 Blur (អូសទៅដាក់លើអក្សរ) បន្ទាប់មកចុច 🔎 Read Screen Text ជំនួសវិញ។")
        self.job(lambda p: ai.transcribe(cfg, video, work, lang, p), done)

    def do_translate(self):
        segs = self.segs()
        if not segs: return QMessageBox.information(self, "Translate", "មិនទាន់មានអត្ថបទ។ សូម Transcribe ឬ Import SRT ជាមុន។")
        cfg, lang, eng = dict(self.cfg), self.lang.currentText(), self.tr_engine.currentText()
        # a row that still holds Chinese is translated as it is; a row already translated is re-translated from its original text
        texts = [s.text if (ai.CJK_RE.search(s.text) or not s.src) else s.src for s in segs]
        def done(res):
            self.table.blockSignals(True)
            for r, t in enumerate(res): self.table.item(r, 3).setText(t)
            self.table.blockSignals(False)
            for u in list(self.clips): self.invalidate(u)
            self.refresh_timeline()
            if ai.GEMINI_NOTE[0]:
                self.status_lbl.setText("⚠ Gemini បរាជ័យ → ប្រើ Free"); QMessageBox.warning(self, "Translate", ai.GEMINI_NOTE[0])
        durs = [max(0.4, x.end - x.start) for x in segs]          # seconds each line may last (keeps the dub in sync)
        gens = [x.gender for x in segs]                           # who speaks: male / female (pronouns + tone fit the character)
        self.job(lambda p: ai.translate_texts(cfg, texts, lang, eng, p, durs, gens), done)

    def do_detect(self):
        segs = self.segs()
        if not segs: return QMessageBox.information(self, "Speakers", "មិនទាន់មាន dialogue ទេ")
        cfg, texts = dict(self.cfg), [s.text for s in segs]
        def done(g):
            for r, x in enumerate(g): self.table.cellWidget(r, 4).setCurrentText(tts.default_profile(x))
        self.job(lambda p: ai.detect_genders(cfg, texts, p), done)

    def do_auto(self):
        if not self.need_video(): return
        cfg, video, work = self.stt_cfg(), self.video, self.work
        slang, tlang, eng = self.src_lang.currentText(), self.lang.currentText(), self.tr_engine.currentText()
        if slang == tlang:
            self.log(f"⚠ Source = Target ({slang}) → ប្រើ Auto-detect ជំនួស"); slang = "Auto"
        def do(p):
            segs = ai.transcribe(cfg, video, work, slang, lambda x, m="": p(x * 0.5, m))
            if not segs: raise RuntimeError("រកមិនឃើញសំឡេងនិយាយក្នុងវីដេអូ")
            texts = [s.text for s in segs]
            durs = [max(0.4, x.end - x.start) for x in segs]
            if ai.split_keys(cfg["gemini_key"]) and not cfg["stt_engine"].startswith("Gemini"):
                try:                                           # Whisper has no speaker info: guess it first, translation needs it
                    for s, g in zip(segs, ai.detect_genders(cfg, texts, lambda *_: None)): s.gender = g
                except Exception: pass
            res = ai.translate_texts(cfg, texts, tlang, eng, lambda x, m="": p(50 + x * 0.35, m), durs, [s.gender for s in segs])
            for s, t in zip(segs, res): s.text = t
            p(95, "Loading dialogue…")
            return segs
        def done(segs):
            tts.assign_voices(segs); self.load_segs(segs); QTimer.singleShot(300, self.do_dub)
        self.job(do, done)

    # ---------- voice generation
    def warn_tts(self):
        if tts.LAST_WARNINGS:
            w = list(tts.LAST_WARNINGS); tts.LAST_WARNINGS.clear()
            for x in w: self.log(x)
            QMessageBox.warning(self, "Voice", "ជួរខាងក្រោមមិនអាចបង្កើតសំឡេងបានទេ (ទុកស្ងាត់):\n\n" + "\n".join(w[:15]) +
                                ("\n…" if len(w) > 15 else "") + "\n\nសូមចុច ↻ លើជួរនោះ ឬកែអត្ថបទ។")

    def gen_uids(self, uids, force=False, then=None):
        segs = self.segs(); order = [self.uid_of(r) for r in range(self.table.rowCount())]
        idx = [i for i, u in enumerate(order) if u in uids and segs[i].text.strip()]
        if not idx: return QMessageBox.information(self, "Voice", "មិនមានអត្ថបទសម្រាប់បង្កើតសំឡេងទេ")
        lang, work, o = self.lang.currentText(), self.work, self.opts()
        def done(res):
            for i, w in res.items(): self.clips[order[i]] = w; self.mark(order[i])
            self.warn_tts()
            if then: QTimer.singleShot(200, then)
        self.job(lambda p: tts.render_clips(segs, idx, lang, work, o, p, force), done)

    def gen_selected(self):
        u = self.checked_uids()
        if not u: return QMessageBox.information(self, "Voice", "សូមធីកជួរដែលចង់បង្កើតសំឡេងជាមុន")
        self.gen_uids(set(u))

    def play_row(self, uid):
        def play():
            w = self.clips.get(uid)
            if w: self.pplayer.setSource(QUrl.fromLocalFile(w)); self.pplayer.play()
        if uid in self.clips: play()
        else: self.gen_uids({uid}, then=play)

    def peaks(self, wav):
        d, sr = sf.read(wav, dtype="float32")
        if d.ndim > 1: d = d.mean(axis=1)
        step = max(len(d) // 4000, 1); d = np.abs(d[:len(d) // step * step]).reshape(-1, step).max(axis=1)
        return d / (d.max() or 1), len(sf.read(wav, dtype="float32")[0]) / sr

    def set_dub(self, wav):
        self.dub_wav = wav; self.dplayer.setSource(QUrl.fromLocalFile(wav))
        pk, dur = self.peaks(wav); self.timeline.set_wave(pk, dur)
        self.use_dub.setChecked(True); self.apply_mute()
        self.status_lbl.setText("✔ Dub ready — ចុច ▶ ដើម្បីស្តាប់")

    def do_dub(self):
        segs = self.segs()
        if not [s for s in segs if s.text.strip()]: return QMessageBox.information(self, "Dub", "មិនទាន់មាន dialogue ទេ")
        lang, work, o = self.lang.currentText(), self.work, self.opts()
        total = max(self.player.duration() / 1000, max(s.end for s in segs))
        order = [self.uid_of(r) for r in range(self.table.rowCount())]
        cfg = dict(self.cfg)
        shorten = (lambda items: ai.shorten_texts(cfg, items, lang)) if (cfg.get("gemini_key") and cfg.get("auto_short", True)) else None
        def done(r):
            wav, clips = r
            self.table.blockSignals(True)                      # lines that were shortened to fit the video
            for i, s in enumerate(segs):
                if i < self.table.rowCount() and self.table.item(i, 3).text() != s.text:
                    self.table.item(i, 3).setText(s.text)
            self.table.blockSignals(False)
            for i, w in clips.items(): self.clips[order[i]] = w; self.mark(order[i])
            self.set_dub(wav); self.warn_tts(); self.refresh_timeline()
        self.job(lambda p: tts.render_dub(segs, lang, work, total, o, p, False, shorten), done)

    # ================================================================== export & tools
    def export_video(self):
        if not self.need_video(): return
        segs = self.segs()
        if not [s for s in segs if s.text.strip()]: return QMessageBox.information(self, "Export", "មិនទាន់មាន dialogue ទេ")
        base = os.path.splitext(os.path.basename(self.video))[0]
        start_dir = self.cfg.get("export_dir") or os.path.dirname(self.video)
        out, _ = QFileDialog.getSaveFileName(self, "Export", os.path.join(start_dir, f"{base}_dub.mp4"), "MP4 (*.mp4)")
        if not out: return
        self.set_cfg("export_dir", os.path.dirname(out))
        video, work, lang, o = self.video, self.work, self.lang.currentText(), self.opts()
        v = self.view; crop, specs, frame_ = v.crop_rect(), v.specs(os.path.join(work, "blur")), v.frame_size()
        isolate, mute, music = self.isolate_bgm, self.mute_orig, self.music
        bgv = self.bgvol.value() / 100
        flips = (v.flip_h, v.flip_v)
        mode, fit = v.mode, self.fit_chk.isChecked()
        sub_track = self.build_sub_track(segs, frame_[0], frame_[1]) if self.burn else None   # same look as the preview
        cfg = dict(self.cfg); vspeed = self.vspeed
        try:
            sd = os.path.join(work, "stage"); os.makedirs(sd, exist_ok=True); stage = v.export_stage(sd)   # neon/gold frame + background
        except Exception: stage = None
        shorten = (lambda items: ai.shorten_texts(cfg, items, lang)) if (cfg.get("gemini_key") and cfg.get("auto_short", True)) else None
        self.last_dir = os.path.dirname(out)
        def do(p):
            dur = media.duration(video)
            wav, _ = tts.render_dub(segs, lang, work, dur, o, lambda x, m="": p(x * 0.55, m), False, shorten)
            bg, bvol = None, bgv
            if isolate and cfg.get("music_mode", "fast") != "ai":     # INSTANT keep-music (seconds): centre-cancel + ducking
                p(60, "Keep music (fast)…")
                try:
                    bg = media.fast_bgm(video, wav, os.path.join(work, "bgm_fast.wav"), [(s.start, s.end) for s in segs])
                except Exception:
                    bg, bvol = media.extract_audio(video, os.path.join(work, "orig.wav"), 44100), 0.25
            elif isolate:                                      # music_mode = "ai": Demucs (clean but very slow)
                p(60, "Separating vocals / BGM (Demucs)…")
                a = media.extract_audio(video, os.path.join(work, "orig.wav"), 44100)
                bg = media.separate_vocals(a, os.path.join(work, "sep"))[1]
            elif not mute:                                     # only when you turned "Mute Original" OFF
                bg, bvol = media.extract_audio(video, os.path.join(work, "orig.wav"), 44100), 0.3
            p(85, "Rendering video…")
            media.export_video(video, wav, out, {"dur": dur, "bg": bg, "bg_vol": bvol, "music": music, "music_vol": bgv,
                "sub_track": sub_track, "crop": crop, "flip_h": flips[0], "flip_v": flips[1], "frame": frame_,
                "overlays": specs, "mode": mode, "fit": fit, "stage": stage, "speed": vspeed,
                "encoder": media.encoder_chain(cfg.get("export_encoder", "auto")),      # GPU (NVENC -> QSV -> AMF) then CPU
                "quality": cfg.get("export_quality", "fast"), "res": int(cfg.get("export_res", 0))})
            return out
        def finished(o_):
            self.status_lbl.setText(f"✔ Export រួចរាល់: {o_}")
            reveal_file(o_)                                    # straight into the folder, file selected
        self.job(do, finished)

    def translate_file(self):
        p, _ = QFileDialog.getOpenFileName(self, "Translate file", "", "Subtitle/Text (*.srt *.txt)")
        if not p: return
        cfg, lang, eng = dict(self.cfg), self.lang.currentText(), self.tr_engine.currentText()
        raw = open(p, encoding="utf-8-sig", errors="ignore").read(); is_srt = p.lower().endswith(".srt")
        segs = parse_srt(raw) if is_srt else None
        lines = [s.text for s in segs] if is_srt else raw.split("\n")
        idx = [i for i, l in enumerate(lines) if l.strip()]
        def do(prog):
            res = ai.translate_texts(cfg, [lines[i] for i in idx], lang, eng, prog)
            for i, t in zip(idx, res): lines[i] = t
            if is_srt:
                for s, t in zip(segs, lines): s.text = t
                text = to_srt(segs)
            else: text = "\n".join(lines)
            out = f"{os.path.splitext(p)[0]}.{ai.LANGS[lang]}{os.path.splitext(p)[1]}"
            open(out, "w", encoding="utf-8").write(text); return out
        self.job(do, lambda o: (self.status_lbl.setText(f"Saved: {o}"), open_folder(os.path.dirname(o))))

    def quick_translate(self):
        """Paste any text -> translate with NO API key (fast Google web endpoint)."""
        d = QDialog(self); d.setWindowTitle("Quick Translate — គ្មាន API key"); d.resize(640, 460); v = QVBoxLayout(d)
        top = QHBoxLayout(); tl = QComboBox(); tl.addItems(ai.LANGS.keys()); tl.setCurrentText(self.lang.currentText())
        top.addWidget(lbl("បកប្រែទៅ", "muted")); top.addWidget(tl); top.addStretch(1); v.addLayout(top)
        src = QPlainTextEdit(); src.setPlaceholderText("ដាក់អត្ថបទ (ចិន / អង់គ្លេស / …) មួយបន្ទាត់មួយប្រយោគ"); v.addWidget(src, 1)
        out = QPlainTextEdit(); out.setReadOnly(True); v.addWidget(out, 1)
        st = lbl("", "muted"); v.addWidget(st)
        row = QHBoxLayout(); go = QPushButton("🌐 Translate"); go.setObjectName("accent"); cp = QPushButton("Copy"); cl = QPushButton("Close")
        for b in (go, cp, cl): row.addWidget(b)
        v.addLayout(row)
        def run():
            lines = src.toPlainText().split("\n")
            go.setEnabled(False); st.setText("កំពុងបកប្រែ…"); QApplication.processEvents()
            try:
                res = ai._free_translate(lines, tl.currentText(), lambda *_: None)
                out.setPlainText("\n".join(res)); st.setText(f"✔ {len([x for x in lines if x.strip()])} lines")
            except Exception as e:
                st.setText("❌ " + str(e)[:150])
            go.setEnabled(True)
        go.clicked.connect(run); cl.clicked.connect(d.accept)
        cp.clicked.connect(lambda: QGuiApplication.clipboard().setText(out.toPlainText()))
        d.exec()

    def vocal_remover(self):
        p, _ = QFileDialog.getOpenFileName(self, "Vocal Remover", "", VIDEO_EXT)
        if not p: return
        out_dir = os.path.join(os.path.dirname(p), "vocal_remover_output"); os.makedirs(out_dir, exist_ok=True)
        def do(prog):
            prog(10, "Demucs កំពុងដំណើរការ (អាចយូរ)…")
            a = media.extract_audio(p, os.path.join(self.work, "vr_in.wav"), 44100)
            return media.separate_vocals(a, out_dir)
        self.job(do, lambda r: (self.status_lbl.setText(f"Vocals: {r[0]}"), open_folder(os.path.dirname(r[0]))))


def load_fonts():
    """Every .ttf/.otf in assets/fonts shows up in the font list (drop beautiful Khmer fonts there)."""
    d = ROOT / "assets" / "fonts"
    if d.exists():
        for f in list(d.glob("*.ttf")) + list(d.glob("*.otf")) + list(d.glob("*.TTF")) + list(d.glob("*.OTF")):
            QFontDatabase.addApplicationFont(str(f))


def main():
    app = QApplication(sys.argv)
    load_fonts()
    try: app.setStyleSheet(build_qss(config.load().get("theme") or "Neon Cyan"))
    except Exception: app.setStyleSheet(QSS)
    st = lic.check()
    if not st.get("valid"):                                  # no / expired / wrong-computer licence -> activation window first
        if not LicenseDialog(LOGO, "" if st.get("reason") == "មិនទាន់មាន License" else st.get("reason", "")).exec():
            sys.exit(0)
    w = MainWindow(); w.show(); w.refresh_license(warn=True)
    sys.exit(app.exec())

"""Text style dialog: font, size, colours, outline, background, shadow, presets + live preview."""
from PySide6.QtCore import Qt
from PySide6.QtGui import QColor, QFontDatabase, QPixmap
from PySide6.QtWidgets import (QDialog, QVBoxLayout, QGridLayout, QPlainTextEdit, QComboBox, QDoubleSpinBox, QSpinBox,
                               QCheckBox, QPushButton, QLabel, QColorDialog, QDialogButtonBox, QSlider, QHBoxLayout)
from ui.textstyle import STYLE_PRESETS, DEFAULT_STYLE, render_styled_image


def font_lists():
    kh, allf = [], []
    try:
        kh = list(QFontDatabase.families(QFontDatabase.WritingSystem.Khmer))
    except Exception:
        try: kh = list(QFontDatabase().families(QFontDatabase.WritingSystem.Khmer))
        except Exception: kh = []
    try:
        allf = list(QFontDatabase.families())
    except Exception:
        try: allf = list(QFontDatabase().families())
        except Exception: allf = []
    return sorted(kh), [f for f in sorted(allf) if f not in kh]


class StyleDialog(QDialog):
    def __init__(self, parent, style, text=None, frame_h=1000, title="Text style",
                 sample="សួស្តី បងប្អូន  Hello  你好"):
        super().__init__(parent)
        self.setWindowTitle(title); self.setMinimumWidth(580)
        self.frame_h = max(200, int(frame_h)); self.sample = sample
        self.st = dict(DEFAULT_STYLE); self.st.update(style or {})
        v = QVBoxLayout(self); v.setSpacing(8)
        self.edit = None
        if text is not None:
            self.edit = QPlainTextEdit(text); self.edit.setPlaceholderText("សរសេរអក្សរនៅទីនេះ…"); self.edit.setFixedHeight(84)
            v.addWidget(QLabel("អក្សរ (Enter = ចុះបន្ទាត់)")); v.addWidget(self.edit)
        self.prev = QLabel(); self.prev.setMinimumHeight(170); self.prev.setAlignment(Qt.AlignCenter)
        self.prev.setStyleSheet("background:#05070d;border:1px solid #22335c;border-radius:8px;")
        v.addWidget(self.prev)

        g = QGridLayout(); g.setHorizontalSpacing(10); v.addLayout(g)
        self.preset = QComboBox(); self.preset.addItem("— Style ស្អាតៗ (ជ្រើសរើស) —"); self.preset.addItems(STYLE_PRESETS.keys())
        self.preset.activated.connect(self.apply_preset)
        g.addWidget(QLabel("Style"), 0, 0); g.addWidget(self.preset, 0, 1, 1, 3)
        kh, rest = font_lists()
        self.font = QComboBox(); self.font.setMaxVisibleItems(18)
        if kh: self.font.addItems(kh); self.font.insertSeparator(self.font.count())
        self.font.addItems(rest)
        g.addWidget(QLabel("Font"), 1, 0); g.addWidget(self.font, 1, 1, 1, 3)
        self.size = QDoubleSpinBox(); self.size.setRange(1.0, 25.0); self.size.setSingleStep(0.5); self.size.setSuffix(" %")
        g.addWidget(QLabel("ទំហំ"), 2, 0); g.addWidget(self.size, 2, 1)
        self.stroke_w = QSpinBox(); self.stroke_w.setRange(0, 40); self.stroke_w.setSuffix(" %")
        g.addWidget(QLabel("គែមអក្សរ"), 2, 2); g.addWidget(self.stroke_w, 2, 3)
        self.btns = {}
        for row, (key, name) in enumerate((("color", "ពណ៌អក្សរ"), ("stroke", "ពណ៌គែម"), ("bg", "ពណ៌ផ្ទៃក្រោយ"))):
            b = QPushButton(); b.setFixedSize(70, 28); b.clicked.connect(lambda _=False, k=key: self.pick(k)); self.btns[key] = b
            g.addWidget(QLabel(name), 3 + row // 2, 0 if row % 2 == 0 else 2); g.addWidget(b, 3 + row // 2, 1 if row % 2 == 0 else 3)
        self.bg_on = QCheckBox("មានផ្ទៃក្រោយ")
        self.bold = QCheckBox("Bold"); self.italic = QCheckBox("Italic"); self.shadow = QCheckBox("Shadow")
        row = QHBoxLayout(); row.addWidget(self.bg_on); row.addWidget(self.bold); row.addWidget(self.italic); row.addWidget(self.shadow); row.addStretch(1)
        v.addLayout(row)
        self.opacity = QSlider(Qt.Horizontal); self.opacity.setRange(10, 100)
        orow = QHBoxLayout(); orow.addWidget(QLabel("Opacity")); orow.addWidget(self.opacity, 1); self.op_lbl = QLabel("100%"); orow.addWidget(self.op_lbl)
        v.addLayout(orow)
        bb = QDialogButtonBox(QDialogButtonBox.Ok | QDialogButtonBox.Cancel); bb.accepted.connect(self.accept); bb.rejected.connect(self.reject)
        v.addWidget(bb)

        self.load_controls()
        for w in (self.font,):
            w.currentTextChanged.connect(self.refresh)
        for w in (self.size, self.stroke_w):
            w.valueChanged.connect(self.refresh)
        for w in (self.bg_on, self.bold, self.italic, self.shadow):
            w.toggled.connect(self.refresh)
        self.opacity.valueChanged.connect(self.refresh)
        if self.edit: self.edit.textChanged.connect(self.refresh)
        self.refresh()

    # ---- helpers
    def paint(self, key):
        c = self.st.get(key) or ("#CC000000" if key == "bg" else "#FFFFFFFF")
        self.btns[key].setStyleSheet(f"background:{QColor(c).name()};border:1px solid #6b7799;border-radius:6px;")

    def pick(self, key):
        cur = QColor(self.st.get(key) or ("#CC000000" if key == "bg" else "#FFFFFFFF"))
        col = QColorDialog.getColor(cur, self, "ជ្រើសពណ៌", QColorDialog.ShowAlphaChannel)
        if col.isValid():
            self.st[key] = col.name(QColor.HexArgb)
            if key == "bg": self.bg_on.setChecked(True)
            self.paint(key); self.refresh()

    def load_controls(self):
        widgets = (self.font, self.size, self.stroke_w, self.bg_on, self.bold, self.italic, self.shadow, self.opacity)
        for w in widgets: w.blockSignals(True)
        i = self.font.findText(str(self.st["family"]))
        if i < 0: self.font.insertItem(0, str(self.st["family"])); i = 0
        self.font.setCurrentIndex(i)
        self.size.setValue(float(self.st["size_pct"])); self.stroke_w.setValue(int(self.st["stroke_pct"]))
        self.bg_on.setChecked(bool(self.st["bg"])); self.bold.setChecked(bool(self.st["bold"]))
        self.italic.setChecked(bool(self.st["italic"])); self.shadow.setChecked(bool(self.st["shadow"]))
        self.opacity.setValue(int(self.st["opacity"]))
        for w in widgets: w.blockSignals(False)
        for k in ("color", "stroke", "bg"): self.paint(k)

    def apply_preset(self, i):
        if i <= 0: return
        self.st.update(STYLE_PRESETS[self.preset.itemText(i)])
        self.load_controls(); self.refresh(); self.preset.setCurrentIndex(0)

    def collect(self):
        s = dict(self.st)
        s.update(family=self.font.currentText(), size_pct=float(self.size.value()), stroke_pct=int(self.stroke_w.value()),
                 bold=self.bold.isChecked(), italic=self.italic.isChecked(), shadow=self.shadow.isChecked(),
                 opacity=int(self.opacity.value()))
        s["bg"] = (self.st.get("bg") or "#CC000000") if self.bg_on.isChecked() else None
        return s

    def refresh(self, *_):
        s = self.collect(); self.op_lbl.setText(f"{s['opacity']}%")
        txt = self.edit.toPlainText().strip() if self.edit else ""
        img = render_styled_image(txt or self.sample, s, self.frame_h, int(self.frame_h * 0.5625 * 0.92))
        pm = QPixmap.fromImage(img)
        self.prev.setPixmap(pm.scaled(max(100, self.prev.width() - 14), self.prev.height() - 14,
                                      Qt.KeepAspectRatio, Qt.SmoothTransformation))

    def result_text(self):
        return self.edit.toPlainText() if self.edit else ""

    def result_style(self):
        return self.collect()

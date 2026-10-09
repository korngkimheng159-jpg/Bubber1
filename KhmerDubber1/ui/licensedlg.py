"""Activation window (shown when there is no valid licence) + small helpers for the header chip."""
from PySide6.QtCore import Qt
from PySide6.QtGui import QGuiApplication
from PySide6.QtSvgWidgets import QSvgWidget
from PySide6.QtWidgets import QDialog, QVBoxLayout, QHBoxLayout, QLabel, QPushButton, QPlainTextEdit, QLineEdit
from core import license as lic


class LicenseDialog(QDialog):
    def __init__(self, logo, reason="", parent=None):
        super().__init__(parent)
        self.setWindowTitle("Dubber ខ្មែរ — Activate"); self.setModal(True); self.setMinimumWidth(560)
        v = QVBoxLayout(self); v.setContentsMargins(26, 22, 26, 22); v.setSpacing(10)
        head = QHBoxLayout(); lg = QSvgWidget(logo); lg.setFixedSize(92, 92); head.addWidget(lg)
        t = QVBoxLayout(); t.setSpacing(0)
        a = QLabel("Dubber ខ្មែរ"); a.setObjectName("brand"); b = QLabel("VIP Khmer dubbing studio · License"); b.setObjectName("muted")
        t.addWidget(a); t.addWidget(b); head.addLayout(t); head.addStretch(1); v.addLayout(head)
        self.msg = QLabel(reason or "សូមបញ្ចូល License Key ដើម្បីប្រើកម្មវិធី"); self.msg.setWordWrap(True)
        self.msg.setStyleSheet("color:#fbbf24;font-weight:700;" if reason else "font-weight:600;"); v.addWidget(self.msg)
        v.addWidget(self._m("HWID របស់កុំព្យូទ័រនេះ (ផ្ញើឲ្យម្ចាស់ ប្រសិនបើ key ត្រូវចងជាប់កុំព្យូទ័រ)"))
        row = QHBoxLayout(); hw = QLineEdit(lic.machine_id()); hw.setReadOnly(True); row.addWidget(hw, 1)
        cp = QPushButton("Copy"); cp.clicked.connect(lambda: QGuiApplication.clipboard().setText(lic.machine_id())); row.addWidget(cp); v.addLayout(row)
        v.addWidget(self._m("License Key"))
        self.key = QPlainTextEdit(); self.key.setPlaceholderText("KDL1-…"); self.key.setFixedHeight(96); v.addWidget(self.key)
        row = QHBoxLayout(); row.addStretch(1)
        q = QPushButton("Exit"); q.clicked.connect(self.reject); ok = QPushButton("✔  Activate"); ok.setObjectName("accent")
        ok.clicked.connect(self.activate); ok.setDefault(True); row.addWidget(q); row.addWidget(ok); v.addLayout(row)

    @staticmethod
    def _m(text):
        l = QLabel(text); l.setObjectName("muted"); l.setWordWrap(True); return l

    def activate(self):
        r = lic.check(self.key.toPlainText())
        if r["valid"]:
            lic.save(self.key.toPlainText()); self.accept()
        else:
            self.msg.setText("✖ " + (r.get("reason") or "key មិនត្រឹមត្រូវ")); self.msg.setStyleSheet("color:#f87171;font-weight:700;")


def chip_text(st):
    if not st.get("valid"):
        return "🔒 No license"
    d = st.get("days_left", 0)
    who = st.get("name") or "Licensed"
    return f"🔑 {who} · lifetime" if d > 36500 else f"🔑 {who} · {d} ថ្ងៃទៀត"

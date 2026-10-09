# Theme engine: one stylesheet template, several accent colours (Header menu > Theme).
_TEMPLATE = r"""
* { font-family: 'Segoe UI Variable','Segoe UI','Khmer UI','Noto Sans Khmer','Leelawadee UI',sans-serif; font-size: 13px; color: #dbe4ff; }
QMainWindow, QWidget#root { background: qlineargradient(x1:0,y1:0,x2:1,y2:1,stop:0 #04060d,stop:0.5 #070b18,stop:1 #05060f); }
QWidget { background: transparent; }
QDialog, QMenu { background: #0b1122; }
QFrame#panel { background: qlineargradient(x1:0,y1:0,x2:0,y2:1,stop:0 #0c1226,stop:1 #080c1b); border: 1px solid #16213d; border-radius: 16px; }

QLabel#brand { font-size: 21px; font-weight: 800; color: #ffffff; letter-spacing: 0.5px; }
QLabel#h2 { font-size: 21px; font-weight: 800; color: #ffffff; }
QLabel#muted { color: #8794ba; font-size: 11px; font-weight: 600; letter-spacing: 0.4px; }
QLabel#chip { background: #0f1830; border: 1px solid #22335c; border-radius: 8px; padding: 3px 10px; color: #a9bbea; font-size: 11px; font-weight: 600; }

QPushButton { background: #0f1830; border: 1px solid #22335c; border-radius: 10px; padding: 7px 14px; font-weight: 600; }
QPushButton:hover { border-color: #22d3ee; background: #12203f; color: #ffffff; }
QPushButton:pressed { background: #0a1226; }
QPushButton:disabled { color: #46557a; border-color: #16213d; }
QPushButton:checked { background: #0f2a45; border-color: #22d3ee; color: #ffffff; }

QPushButton#accent { background: qlineargradient(x1:0,y1:0,x2:1,y2:0,stop:0 #2563eb,stop:1 #06b6d4); border: none; color: white; font-weight: 800; padding: 8px 20px; }
QPushButton#accent:hover { background: qlineargradient(x1:0,y1:0,x2:1,y2:0,stop:0 #3b82f6,stop:1 #22d3ee); }
QPushButton#gen { background: qlineargradient(x1:0,y1:0,x2:1,y2:0,stop:0 #6d28d9,stop:1 #2563eb); border: none; color: white; font-weight: 800; }
QPushButton#gen:hover { background: qlineargradient(x1:0,y1:0,x2:1,y2:0,stop:0 #8b5cf6,stop:1 #3b82f6); }
QPushButton#vip { background: qlineargradient(x1:0,y1:0,x2:1,y2:0,stop:0 #b45309,stop:0.5 #f59e0b,stop:1 #b45309); border: none; color: #1a1002; font-weight: 800; }
QPushButton#vip:hover { background: qlineargradient(x1:0,y1:0,x2:1,y2:0,stop:0 #d97706,stop:0.5 #fbbf24,stop:1 #d97706); }
QPushButton#stop { color: #86efac; border-color: #166534; font-weight: 800; }
QPushButton#stop[running="true"] { color: #fecaca; border-color: #ef4444; background: #2a1116; }
QPushButton#stop:disabled { color: #64748b; border-color: #1d2947; }
QPushButton#male { border-color: #14b8a6; color: #5eead4; }
QPushButton#female { border-color: #ec4899; color: #f9a8d4; }
QPushButton#seg { border-radius: 0; padding: 7px 12px; font-size: 12px; color: #8b9ac4; }
QPushButton#seg:checked { background: qlineargradient(x1:0,y1:0,x2:1,y2:0,stop:0 #1d4ed8,stop:1 #0891b2); color: white; border-color: #22d3ee; }
QPushButton#tool { background: #0a1124; border: 1px solid #1a2850; border-radius: 14px; padding: 2px; }
QPushButton#tool:hover { border-color: #22d3ee; background: #0e1a36; }
QPushButton#tool:checked { background: #0c2a44; border: 1px solid #22d3ee; }
QPushButton#icon { padding: 4px; min-width: 32px; min-height: 28px; font-size: 15px; border-radius: 9px; }

QLineEdit, QComboBox, QSpinBox, QDoubleSpinBox, QPlainTextEdit { background: #080e1f; border: 1px solid #22335c; border-radius: 9px; padding: 6px 10px; selection-background-color: #2563eb; }
QLineEdit:focus, QComboBox:focus, QPlainTextEdit:focus, QSpinBox:focus, QDoubleSpinBox:focus { border-color: #22d3ee; }
QComboBox::drop-down { border: none; width: 22px; }
QComboBox QAbstractItemView { background: #080e1f; border: 1px solid #22335c; selection-background-color: #1d4ed8; outline: none; }

QTableWidget { background: #070c1b; border: 1px solid #16213d; border-radius: 12px; gridline-color: #0f1830; alternate-background-color: #0a1124; selection-background-color: #12306a; }
QTableWidget::item { padding: 4px 8px; }
QHeaderView::section { background: #0a1124; color: #6f7ca3; border: none; border-bottom: 1px solid #16213d; padding: 8px; font-size: 11px; font-weight: 800; letter-spacing: 0.6px; }

QSlider::groove:horizontal { height: 4px; background: #17234a; border-radius: 2px; }
QSlider::sub-page:horizontal { background: qlineargradient(x1:0,y1:0,x2:1,y2:0,stop:0 #22d3ee,stop:1 #8b5cf6); border-radius: 2px; }
QSlider::handle:horizontal { background: #e6fbff; width: 14px; margin: -6px 0; border-radius: 7px; border: 2px solid #22d3ee; }
QProgressBar { background: #080e1f; border: 1px solid #16213d; border-radius: 5px; max-height: 9px; text-align: center; color: transparent; }
QProgressBar::chunk { border-radius: 4px; background: qlineargradient(x1:0,y1:0,x2:1,y2:0,stop:0 #22d3ee,stop:0.5 #8b5cf6,stop:1 #ec4899); }
QCheckBox { spacing: 8px; }
QCheckBox::indicator { width: 17px; height: 17px; border: 1px solid #2b3d6b; border-radius: 5px; background: #080e1f; }
QCheckBox::indicator:checked { background: qlineargradient(x1:0,y1:0,x2:1,y2:1,stop:0 #22d3ee,stop:1 #3b82f6); border-color: #22d3ee; }
QScrollArea { border: none; }
QScrollBar:vertical { background: transparent; width: 10px; margin: 2px; } QScrollBar::handle:vertical { background: #22335c; border-radius: 5px; min-height: 30px; }
QScrollBar::handle:vertical:hover { background: #22d3ee; }
QScrollBar:horizontal { background: transparent; height: 10px; margin: 2px; } QScrollBar::handle:horizontal { background: #22335c; border-radius: 5px; min-width: 30px; }
QScrollBar::handle:horizontal:hover { background: #22d3ee; }
QScrollBar::add-line, QScrollBar::sub-line { width: 0; height: 0; }
QSplitter::handle { background: #101a36; border-radius: 3px; }
QSplitter::handle:hover { background: #22d3ee; }
QMenu { border: 1px solid #22335c; padding: 6px; border-radius: 10px; } QMenu::item { padding: 7px 20px; border-radius: 6px; } QMenu::item:selected { background: #1d4ed8; }
QToolTip { background: #0e1730; color: #dbe4ff; border: 1px solid #22d3ee; padding: 5px; }
QToolButton { background: #0f1830; border: 1px solid #22335c; border-radius: 10px; padding: 6px 12px; font-size: 15px; }
QToolButton:hover { border-color: #22d3ee; }
QToolButton::menu-indicator { image: none; }

/* ===== polish ===== */
QPushButton:focus, QCheckBox:focus { outline: none; border-color: #22d3ee; }
QPushButton#vip { padding: 8px 16px; }
QPushButton#tool { min-height: 66px; }
QPushButton#gen { padding: 8px 18px; }
QLabel#chip { color: #bccaf2; }
QPushButton#accent:disabled, QPushButton#gen:disabled { background: #14203d; color: #5d6c94; }
QPushButton#tool { padding: 2px; min-height: 84px; }
QComboBox { padding-right: 26px; }
QComboBox::down-arrow { image: none; width: 0; height: 0; border-left: 4px solid transparent; border-right: 4px solid transparent; border-top: 5px solid #8b9ac4; margin-right: 9px; }
QComboBox:hover, QLineEdit:hover, QSpinBox:hover { border-color: #3a5190; }
QComboBox QAbstractItemView { padding: 4px; border-radius: 8px; }
QTableWidget { selection-color: #ffffff; gridline-color: #0b1326; }
QTableWidget::item:hover { background: #0e1a36; }
QTableWidget::item:selected { background: #12306a; }
QHeaderView::section:hover { color: #dbe4ff; }
QScrollBar:vertical { width: 8px; margin: 3px; } QScrollBar::handle:vertical { border-radius: 4px; }
QScrollBar:horizontal { height: 8px; margin: 3px; } QScrollBar::handle:horizontal { border-radius: 4px; }
QMenu::separator { height: 1px; background: #1a2850; margin: 5px 8px; }
QMenu::item { padding: 8px 22px; }
QMessageBox QLabel { color: #dbe4ff; }
QDialog QPushButton { min-width: 78px; }
QFrame#panel { border-color: #1a2a55; }
QLabel#chip { padding: 3px 12px; }
QSlider::handle:horizontal:hover { background: #ffffff; }
QProgressBar { min-height: 9px; }
QCheckBox::indicator:hover { border-color: #22d3ee; }

/* ===== modern refresh (round 15) ===== */
QMainWindow, QWidget#root { background: qlineargradient(x1:0,y1:0,x2:1,y2:1,stop:0 #05070f,stop:0.55 #0a0f22,stop:1 #080a18); }
QFrame#panel { background: qlineargradient(x1:0,y1:0,x2:0,y2:1,stop:0 #0e1530,stop:1 #090d1f); border: 1px solid #1c2a55; border-radius: 20px; }
QPushButton { border-radius: 12px; padding: 7px 15px; background: #111b38; border: 1px solid #263a6b; }
QPushButton:hover { background: #162448; }
QPushButton#accent { border-radius: 14px; padding: 9px 22px; }
QPushButton#gen, QPushButton#vip { border-radius: 14px; }
QPushButton#icon { border-radius: 11px; background: #0f1830; }
QPushButton#tool { background: qlineargradient(x1:0,y1:0,x2:0,y2:1,stop:0 #0d1630,stop:1 #090f22); border: 1px solid #1d2d5c; border-radius: 16px; }
QPushButton#tool:hover { border-color: #22d3ee; background: #0f1b3a; }
QPushButton#seg { border: 1px solid #22335c; padding: 7px 14px; }
QPushButton#seg:first { border-top-left-radius: 11px; border-bottom-left-radius: 11px; }
QPushButton#seg:last { border-top-right-radius: 11px; border-bottom-right-radius: 11px; }
QLineEdit, QComboBox, QSpinBox, QDoubleSpinBox, QPlainTextEdit { border-radius: 11px; background: #0a1226; border: 1px solid #263a6b; padding: 7px 11px; }
QTableWidget { border-radius: 14px; background: #080d1f; border: 1px solid #1c2a55; }
QTableWidget::item { border-bottom: 1px solid #0f1a38; }
QHeaderView::section { background: #0b1330; padding: 9px 8px; }
QLabel#brand { font-size: 22px; letter-spacing: 0.8px; }
QLabel#chip { background: #0f1a38; border: 1px solid #2a3f73; border-radius: 12px; padding: 4px 12px; }
QDialog { background: qlineargradient(x1:0,y1:0,x2:1,y2:1,stop:0 #0c1228,stop:1 #080b1a); }
QProgressBar { border-radius: 6px; }
QSplitter::handle { background: transparent; }
QSplitter::handle:hover { background: #22d3ee; }
"""

# tokens used by the template  ->  placeholder
_TOK = {"#22d3ee": "@A1@", "#06b6d4": "@A2@", "#2563eb": "@B1@", "#3b82f6": "@B2@", "#1d4ed8": "@B3@",
        "#0891b2": "@B4@", "#0f2a45": "@C1@", "#0c2a44": "@C1@", "#12306a": "@C2@", "#3a5190": "@H1@"}

THEMES = {
    "Neon Cyan":  {"@A1@": "#22d3ee", "@A2@": "#06b6d4", "@B1@": "#2563eb", "@B2@": "#3b82f6", "@B3@": "#1d4ed8", "@B4@": "#0891b2", "@C1@": "#0f2a45", "@C2@": "#12306a", "@H1@": "#3a5190"},
    "Violet":     {"@A1@": "#a78bfa", "@A2@": "#8b5cf6", "@B1@": "#6d28d9", "@B2@": "#8b5cf6", "@B3@": "#5b21b6", "@B4@": "#7c3aed", "@C1@": "#241545", "@C2@": "#3b1d7a", "@H1@": "#5b4690"},
    "Rose":       {"@A1@": "#f472b6", "@A2@": "#ec4899", "@B1@": "#be185d", "@B2@": "#ec4899", "@B3@": "#9d174d", "@B4@": "#db2777", "@C1@": "#3a1230", "@C2@": "#6b1a45", "@H1@": "#90446a"},
    "Emerald":    {"@A1@": "#34d399", "@A2@": "#10b981", "@B1@": "#047857", "@B2@": "#10b981", "@B3@": "#065f46", "@B4@": "#059669", "@C1@": "#0c2f26", "@C2@": "#0d4a3a", "@H1@": "#3a7a64"},
    "Gold":       {"@A1@": "#fbbf24", "@A2@": "#f59e0b", "@B1@": "#b45309", "@B2@": "#f59e0b", "@B3@": "#92400e", "@B4@": "#d97706", "@C1@": "#35260a", "@C2@": "#5c3d0a", "@H1@": "#8a6a2a"},
}


def build_qss(name="Neon Cyan"):
    pal = THEMES.get(name) or THEMES["Neon Cyan"]
    q = _TEMPLATE
    for tok, ph in _TOK.items():
        q = q.replace(tok, ph)
    for ph, col in pal.items():
        q = q.replace(ph, col)
    return q


QSS = build_qss("Neon Cyan")

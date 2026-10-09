"""FlowLayout: widgets keep their natural size (text never cut) and wrap to the next line when the panel is narrow."""
from PySide6.QtCore import Qt, QRect, QSize, QPoint
from PySide6.QtWidgets import QLayout


def _no_orientation():
    for f in (lambda: Qt.Orientation(0), lambda: Qt.Orientations(), lambda: Qt.Orientation.Horizontal & Qt.Orientation.Vertical):
        try:
            return f()
        except Exception:
            continue
    return Qt.Orientation.Horizontal


class FlowLayout(QLayout):
    def __init__(self, parent=None, margin=0, hspacing=6, vspacing=6):
        super().__init__(parent)
        self._items, self._h, self._v = [], hspacing, vspacing
        self.setContentsMargins(margin, margin, margin, margin)

    def addItem(self, item): self._items.append(item)
    def count(self): return len(self._items)
    def itemAt(self, i): return self._items[i] if 0 <= i < len(self._items) else None
    def takeAt(self, i): return self._items.pop(i) if 0 <= i < len(self._items) else None
    def expandingDirections(self): return _no_orientation()
    def hasHeightForWidth(self): return True
    def heightForWidth(self, w): return self._layout(QRect(0, 0, w, 0), True)

    def setGeometry(self, rect):
        super().setGeometry(rect)
        self._layout(rect, False)

    def sizeHint(self): return self.minimumSize()

    def minimumSize(self):
        s = QSize()
        for it in self._items:
            s = s.expandedTo(it.minimumSize())
        m = self.contentsMargins()
        return s + QSize(m.left() + m.right(), m.top() + m.bottom())

    def _layout(self, rect, test):
        m = self.contentsMargins()
        eff = rect.adjusted(m.left(), m.top(), -m.right(), -m.bottom())
        x, y, line_h = eff.x(), eff.y(), 0
        for it in self._items:
            sz = it.sizeHint()
            if x > eff.x() and x + sz.width() > eff.right() + 1:          # does not fit: next line
                x, y, line_h = eff.x(), y + line_h + self._v, 0
            if not test:
                it.setGeometry(QRect(QPoint(x, y), sz))
            x += sz.width() + self._h
            line_h = max(line_h, sz.height())
        return y + line_h - rect.y() + m.bottom()

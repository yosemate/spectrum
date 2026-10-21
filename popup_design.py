"""Shared SCADA dialog styling and operating indicators."""
from PyQt5.QtCore import Qt, QTimer, QRectF, QPointF
from PyQt5.QtGui import QColor, QPainter, QPainterPath, QPen
from PyQt5.QtWidgets import QDialog, QWidget, QPushButton, QLineEdit, QComboBox, QProgressBar
import glass
from typography import STACK_UI
from animation_math import mix_hex


def popup_owner(widget):
    current = widget
    while current is not None:
        if isinstance(current, QDialog) or current.objectName() == "scaledDialogContent":
            return current
        current = current.parentWidget()
    return None


def popup_stylesheet(widget, palette, existing):
    """Override old control geometry while retaining semantic label colors."""
    p = palette
    foreground = p['on_strong']
    rim = glass.rim(p)
    controls = f"""QPushButton {{background:{glass.button_fill(p)};color:{p['text']};border:1px solid {rim};border-radius:10px;padding:9px 14px;font-family:{STACK_UI};font-size:13px;font-weight:400;}}
QPushButton:hover {{background:{glass.button_fill(p, 'hover')};border:1px solid {glass.rgba(p['accent'], .75)};}}
QPushButton:pressed {{background:{glass.primary_fill(p, 'hot')};color:{p['on_strong']};border:1px solid {p['accent_strong']};}}
QPushButton:focus {{border:1px solid {p['accent']};}}
QPushButton:disabled {{background:{glass.button_fill(p, 'disabled')};color:{p['disabled']};border-color:{glass.rim(p, .6)};}}
QPushButton:checked {{background:{glass.button_fill(p, 'hover')};color:{p['heading']};border:1px solid {p['accent']};}}
QFrame#settingsSection {{background:{glass.field_fill(p)};border:1px solid {glass.rim(p)};border-radius:14px;}}
QLineEdit,QComboBox,QSpinBox,QDoubleSpinBox {{background:{glass.field_fill(p)};color:{p['text']};border:1px solid {rim};border-radius:10px;padding:8px 12px;font-size:13px;}}
QLineEdit:focus,QComboBox:focus {{border-color:{p['accent']};}}
QTableWidget {{background:{glass.field_fill(p)};alternate-background-color:{glass.rgba(p['text'], .04)};color:{p['text']};border:1px solid {rim};border-radius:10px;gridline-color:{glass.rim(p, .6)};selection-background-color:{glass.rgba(p['accent'], .22)};selection-color:{p['heading']};}}
QHeaderView::section {{background:{p['soft']};color:{p['muted']};border:0;padding:8px;font-size:11px;font-weight:400;}}
QProgressBar {{background:{glass.rgba(p['text'], .10)};color:{p['muted']};border:0;border-radius:4px;text-align:center;}}
QProgressBar::chunk {{background:{p['accent']};border-radius:4px;}}
"""
    if isinstance(widget, QDialog) or widget.objectName() == "scaledDialogContent":
        return f"QWidget {{font-family:{STACK_UI};}}\nQDialog,QWidget#scaledDialogContent {{background:{p['surface']};color:{p['text']};}}\nQLabel {{color:{p['text']};}}\nQLabel[role=\"heading\"] {{color:{p['heading']};}}\n" + controls
    if isinstance(widget, QPushButton):
        name = widget.objectName().lower()
        text = widget.text().lower()
        danger = any(term in name + text for term in ('emergency', 'emergência', 'delete', 'excluir'))
        secondary = any(term in name + text for term in ('cancel', 'abortar', 'sair', 'fechar', 'concluir'))
        primary = (widget.isDefault() and not secondary) or any(term in name for term in ('login', 'cadastrar', 'actuator', 'confirm', 'proceed', 'finish'))
        widget.setProperty('fxTone', 'strong' if primary and not danger else 'soft')
        bg = glass.primary_fill(p) if primary and not danger else glass.button_fill(p)
        color = p['danger'] if danger else foreground if primary else p['text']
        border = p['danger'] if danger else p['accent_strong'] if primary else rim
        return controls + f"QPushButton {{background:{bg};color:{color};border-color:{border};}}\nQPushButton:focus {{border-color:{border if danger else p['accent']};}}"
    if isinstance(widget, (QLineEdit, QComboBox, QProgressBar)):
        return controls
    return existing


class WarningSymbol(QWidget):
    """Draw a warning triangle without depending on emoji font support."""
    def __init__(self, parent=None):
        super().__init__(parent)
        self.setFixedSize(40, 40)
        self.setAccessibleName("Aviso de segurança")

    def paintEvent(self, event):
        from appearance import palette_for
        color = QColor(palette_for()['warning'])
        painter = QPainter(self)
        painter.setRenderHint(QPainter.Antialiasing)
        path = QPainterPath(QPointF(20, 4))
        path.lineTo(37, 35); path.lineTo(3, 35); path.closeSubpath()
        painter.setPen(QPen(color, 2)); painter.setBrush(Qt.NoBrush)
        painter.drawPath(path)
        painter.setPen(QPen(color, 3, Qt.SolidLine, Qt.RoundCap))
        painter.drawLine(20, 14, 20, 24); painter.drawPoint(20, 30)


class AnimatedOperationBar(QProgressBar):
    """Indeterminate operation animation, including inside a scaled dialog."""
    def __init__(self, parent=None):
        super().__init__(parent)
        self.setRange(0, 0)
        self.setTextVisible(False)
        self.setFixedHeight(12)
        self.setAccessibleName("Operação em andamento")
        self.phase = 0
        self.animation_timer = QTimer(self)
        self.animation_timer.setInterval(30)
        self.animation_timer.timeout.connect(self._advance)

    def _advance(self):
        self.phase = (self.phase + .018) % 1
        self.update()

    def showEvent(self, event):
        super().showEvent(event)
        self.animation_timer.start()

    def hideEvent(self, event):
        self.animation_timer.stop()
        super().hideEvent(event)

    def paintEvent(self, event):
        from appearance import palette_for
        p = palette_for()
        painter = QPainter(self)
        painter.setRenderHint(QPainter.Antialiasing)
        rect = QRectF(self.rect())
        track = QPainterPath(); track.addRoundedRect(rect, 4, 4)
        painter.setClipPath(track)
        painter.fillRect(rect, QColor(p['soft']))
        width = max(24, self.width() * .28)
        x = self.phase * (self.width() + width) - width
        painter.setPen(Qt.NoPen); painter.setBrush(QColor(p['warning']))
        painter.drawRoundedRect(QRectF(x, 0, width, self.height()), 4, 4)


class OperatingAlertDialog(QDialog):
    """Esc cannot dismiss an active operation; controller close still works."""
    def keyPressEvent(self, event):
        if event.key() == Qt.Key_Escape:
            event.accept()
            return
        super().keyPressEvent(event)

    def close(self):
        self._controller_closing = True
        try:
            return super().close()
        finally:
            self._controller_closing = False

    def closeEvent(self, event):
        if getattr(self, '_controller_closing', False):
            super().closeEvent(event)
        else:
            event.ignore()

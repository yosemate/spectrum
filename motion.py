"""
Movimento da interface (linguagem de animação inspirada na Apple: molas, entradas em cascata,
transições suaves entre estados). Tudo isto é um extra de pintura: se algo falhar, a interface
funciona igual, só sem a animação.

  - install_entrance(root, painéis): ao abrir a janela, os painéis aparecem em cascata (fade com
    desaceleração forte). É uma "cortina" translúcida por cima de cada painel, que some aos poucos;
  - crossfade de tema: ao trocar claro/escuro, a imagem da janela anterior se dissolve sobre a nova;
  - fade de diálogos: janelas de diálogo surgem com um fade rápido.

A opção Reduzir animações está disponível nas Configurações. A variável de ambiente SPECTRUM_REDUCE_MOTION=1 (uso técnico, sem
opção na interface) faz os botões só trocarem de estado.
"""
import os
import time

from PyQt5 import sip
from PyQt5.QtCore import QEasingCurve, QEvent, QObject, QPoint, QRectF, Qt, QTimer, QVariantAnimation
from PyQt5.QtGui import QPainter, QPainterPath
from PyQt5.QtWidgets import QDialog, QWidget

from animation_math import ease_out_expo, staggered

ENTRANCE_DELAY_S = 0.07
ENTRANCE_DURATION_S = 0.75
CROSSFADE_MS = 360
DIALOG_FADE_MS = 200

_reduced = os.environ.get("SPECTRUM_REDUCE_MOTION", "") in ("1", "true", "yes")


def reduced():
    return _reduced


def set_reduced(value):
    global _reduced
    _reduced = bool(value)


class _EntranceVeil(QWidget):
    """Cortina por cima da janela: cada painel é "descoberto" em sequência."""

    def __init__(self, root, panels):
        super().__init__(root)
        self.root = root
        self.panels = [p for p in panels if p is not None]
        self.started = None
        self.setAttribute(Qt.WA_TransparentForMouseEvents)
        self.setAttribute(Qt.WA_NoSystemBackground)
        self.setFocusPolicy(Qt.NoFocus)
        self.timer = QTimer(self)
        self.timer.setInterval(16)
        self.timer.timeout.connect(self._tick)
        root.installEventFilter(self)
        self.setGeometry(root.rect())
        self.hide()

    def start(self):
        if reduced() or not self.panels:
            self.deleteLater()
            return
        self.started = time.monotonic()
        self.setGeometry(self.root.rect())
        self.raise_()
        self.show()
        self.timer.start()

    def eventFilter(self, obj, event):
        if obj is self.root and not sip.isdeleted(self):
            kind = event.type()
            if kind == QEvent.Resize:
                self.setGeometry(self.root.rect())
            elif kind == QEvent.Show and self.started is None:
                QTimer.singleShot(60, self.start)   # espera o primeiro layout para animar os painéis certos
        return False

    def _elapsed(self):
        return time.monotonic() - self.started if self.started else 0.0

    def _tick(self):
        if staggered(self._elapsed(), len(self.panels) - 1, ENTRANCE_DELAY_S, ENTRANCE_DURATION_S) >= 1.0:
            self.timer.stop()
            self.hide()
            self.deleteLater()
            return
        self.update()

    def paintEvent(self, event):
        if self.started is None:
            return
        elapsed = self._elapsed()
        painter = QPainter(self)
        painter.setRenderHint(QPainter.Antialiasing)
        for index, panel in enumerate(self.panels):
            if sip.isdeleted(panel) or not panel.isVisible():
                continue
            veil = 1.0 - ease_out_expo(staggered(elapsed, index, ENTRANCE_DELAY_S, ENTRANCE_DURATION_S))
            if veil <= 0.002:
                continue
            top_left = panel.mapTo(self.root, QPoint(0, 0))
            rect = QRectF(top_left.x(), top_left.y(), panel.width(), panel.height())
            clip = QPainterPath()
            clip.addRoundedRect(rect, 16, 16)
            painter.save()
            painter.setClipPath(clip)
            painter.setOpacity(veil)
            if hasattr(self.root, "paint_background"):
                self.root.paint_background(painter)
            painter.restore()
        painter.end()


def install_entrance(root, panels):
    """Agenda a entrada em cascata dos painéis (começa quando a janela for mostrada)."""
    veil = _EntranceVeil(root, panels)
    root._entrance_veil = veil
    return veil


class _Crossfade(QWidget):
    """Imagem da janela antes da troca de tema, que se dissolve por cima da janela já trocada."""

    def __init__(self, window, pixmap):
        super().__init__(window)
        self.pixmap = pixmap
        self.opacity = 1.0
        self.setAttribute(Qt.WA_TransparentForMouseEvents)
        self.setAttribute(Qt.WA_NoSystemBackground)
        self.setGeometry(window.rect())
        self.raise_()
        self.show()
        self.anim = QVariantAnimation(self)
        self.anim.setStartValue(1.0)
        self.anim.setEndValue(0.0)
        self.anim.setDuration(CROSSFADE_MS)
        self.anim.setEasingCurve(QEasingCurve.OutCubic)
        self.anim.valueChanged.connect(self._set)
        self.anim.finished.connect(self._done)
        QTimer.singleShot(CROSSFADE_MS * 3, self._done)   # rede de segurança: nunca fica uma imagem velha na tela

    def begin(self):
        self.anim.start()

    def _set(self, value):
        self.opacity = float(value)
        self.update()

    def _done(self):
        if not sip.isdeleted(self):
            self.hide()
            self.deleteLater()

    def paintEvent(self, event):
        painter = QPainter(self)
        painter.setOpacity(self.opacity)
        painter.drawPixmap(0, 0, self.pixmap)
        painter.end()


def begin_crossfade(app):
    """Tira uma foto de cada janela visível; devolve a lista para passar a run_crossfade depois da troca."""
    if reduced():
        return []
    fades = []
    try:
        for window in app.topLevelWidgets():
            if window.isVisible() and window.width() > 80 and window.height() > 80 and not isinstance(window, QDialog):
                fades.append(_Crossfade(window, window.grab()))
    except Exception:
        pass
    return fades


def run_crossfade(fades):
    for fade in fades:
        try:
            fade.begin()
        except Exception:
            pass


class MotionController(QObject):
    """Fade rápido ao abrir diálogos."""

    def __init__(self, app):
        super().__init__(app)
        app.installEventFilter(self)

    def eventFilter(self, obj, event):
        if event.type() == QEvent.Show and isinstance(obj, QDialog) and obj.isWindow() and not reduced():
            if not obj.property("motionFaded"):
                obj.setProperty("motionFaded", True)
                self._fade_in(obj)
        return False

    def _fade_in(self, dialog):
        try:
            dialog.setWindowOpacity(0.0)
            anim = QVariantAnimation(dialog)
            anim.setStartValue(0.0)
            anim.setEndValue(1.0)
            anim.setDuration(DIALOG_FADE_MS)
            anim.setEasingCurve(QEasingCurve.OutCubic)
            anim.valueChanged.connect(lambda v, d=dialog: None if sip.isdeleted(d) else d.setWindowOpacity(float(v)))
            anim.finished.connect(lambda d=dialog: None if sip.isdeleted(d) else d.setWindowOpacity(1.0))
            dialog._fade_anim = anim
            anim.start()
            QTimer.singleShot(DIALOG_FADE_MS * 4, lambda d=dialog: None if sip.isdeleted(d) else d.setWindowOpacity(1.0))
        except Exception:
            dialog.setWindowOpacity(1.0)

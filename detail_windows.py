"""
Janelas de detalhe (ISA-101): o painel principal mostra só o essencial e o operador abre estas
janelas quando um indicador sai da faixa ou quando precisa ler o terminal.

  - KpiDetailDialog: uma janela por indicador (intensidade, pico, razão de banda, razão de espessura),
    com o estado, o motivo, o que fazer, o gráfico da leitura atual, o histórico da sessão e a tabela dos canais.
  - TerminalDialog: o log de telemetria e de comandos em janela própria.

As regras de estado ficam em kpi_status.py (sem Qt, testadas). Aqui só há desenho e montagem.
"""
import collections
import datetime

from PyQt5.QtCore import QPointF, QRectF, Qt
from PyQt5.QtGui import QColor, QFontMetrics, QPainter, QPen
from PyQt5.QtWidgets import (QApplication, QDialog, QFrame, QGridLayout, QHBoxLayout, QLabel,
                             QPushButton, QSizePolicy, QVBoxLayout, QWidget)

import kpi_status as ks
import typography as ty
from typography import make_font

HISTORY_LENGTH = 30


def _palette():
    from appearance import palette_for
    return palette_for()


def _series():
    from appearance import series_colors
    return series_colors()


def level_color(pal, level):
    return QColor(pal[ks.LEVEL_COLOR_KEY[level]])


def format_number(value):
    value = float(value)
    if abs(value) >= 1000:
        return f"{value:,.0f}".replace(",", ".")
    if abs(value) >= 100:
        return f"{value:.0f}"
    return f"{value:.2f}".rstrip("0").rstrip(".") if value != int(value) else f"{int(value)}"


class StatusBadge(QWidget):
    """Pílula com o estado (Normal, Atenção, Erro). Desenhada com a paleta atual, sem folha de estilo."""

    def __init__(self, parent=None):
        super().__init__(parent)
        self._level = ks.NONE
        self._text = ks.LEVEL_LABEL[ks.NONE]
        self.setFixedHeight(28)
        self.setSizePolicy(QSizePolicy.Fixed, QSizePolicy.Fixed)
        self.setAccessibleName("Estado do indicador")

    def set_status(self, level, text=None):
        self._level = level
        self._text = text or ks.LEVEL_LABEL[level]
        self.setAccessibleDescription(self._text)
        self.setFixedWidth(QFontMetrics(make_font("ui", 12, 700)).boundingRect(self._text).width() + 32)
        self.update()

    def paintEvent(self, event):
        pal = _palette()
        color = level_color(pal, self._level)
        painter = QPainter(self)
        painter.setRenderHint(QPainter.Antialiasing)
        painter.setRenderHint(QPainter.TextAntialiasing)
        rect = QRectF(0.5, 0.5, self.width() - 1, self.height() - 1)
        abnormal = self._level in (ks.ATTENTION, ks.ERROR)
        fill = QColor(color)
        fill.setAlpha(46 if abnormal else 0)
        painter.setPen(QPen(color, 1.5 if abnormal else 1))
        painter.setBrush(fill)
        painter.drawRoundedRect(rect, rect.height() / 2, rect.height() / 2)
        painter.setPen(QColor(pal["heading"] if abnormal else pal["muted"]))
        painter.setFont(make_font("ui", 12, 700))
        painter.drawText(rect, Qt.AlignCenter, self._text)


class PlotWidget(QWidget):
    """Gráfico de barras (leitura atual) ou de linha (histórico) com eixos de marcas redondas."""
    LEFT, RIGHT, TOP, BOTTOM = 64, 16, 14, 34

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setMinimumHeight(190)
        self.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Expanding)
        self._mode = None
        self._empty = "Sem leituras nesta sessão."
        self.title = ""

    # ---- dados
    def set_empty(self, message):
        self._mode, self._empty = None, message
        self.update()

    def set_bars(self, values, labels, colors, y_max, ref_lines=(), unit="", value_text=None):
        """colors: uma cor por barra; ref_lines: ((valor, rótulo, nível), ...)."""
        self._mode = "bars"
        self._bars = dict(values=list(values), labels=list(labels), colors=list(colors), y_max=float(y_max),
                          ref_lines=list(ref_lines), unit=unit, value_text=value_text)
        self.update()

    def set_history(self, values, y_min, y_max, band=None, unit="", point_text=None):
        """values: lista com None onde a leitura não tem valor; band: (baixo, alto) da faixa normal."""
        self._mode = "line"
        self._line = dict(values=list(values), y_min=float(y_min), y_max=float(y_max), band=band,
                          unit=unit, point_text=point_text)
        self.update()

    # ---- pintura
    def paintEvent(self, event):
        pal = _palette()
        painter = QPainter(self)
        painter.setRenderHint(QPainter.Antialiasing)
        painter.setRenderHint(QPainter.TextAntialiasing)
        w, h = self.width(), self.height()
        plot = QRectF(self.LEFT, self.TOP, max(10, w - self.LEFT - self.RIGHT), max(10, h - self.TOP - self.BOTTOM))
        if self._mode is None:
            painter.setPen(QColor(pal["muted"]))
            painter.setFont(make_font("ui", 13, 400))
            painter.drawText(QRectF(0, 0, w, h), Qt.AlignCenter, self._empty)
            painter.end()
            return
        if self._mode == "bars":
            data = self._bars
            self._draw_axes(painter, plot, pal, 0.0, data["y_max"], data["unit"])
            self._paint_bars(painter, plot, pal, data)
        else:
            data = self._line
            self._draw_axes(painter, plot, pal, data["y_min"], data["y_max"], data["unit"])
            self._paint_line(painter, plot, pal, data)
        painter.end()

    def _y(self, plot, value, y_min, y_max):
        fraction = (value - y_min) / (y_max - y_min) if y_max > y_min else 0.0
        return plot.bottom() - max(0.0, min(1.0, fraction)) * plot.height()

    def _draw_axes(self, painter, plot, pal, y_min, y_max, unit):
        grid = QColor(pal["border"])
        grid.setAlpha(170)
        painter.setFont(make_font("data", 11, 400))
        for tick in ks.nice_ticks(y_min, y_max, 4):
            y = round(self._y(plot, tick, y_min, y_max)) + 0.5
            painter.setPen(QPen(grid, 1))
            painter.drawLine(QPointF(plot.left(), y), QPointF(plot.right(), y))
            painter.setPen(QColor(pal["muted"]))
            painter.drawText(QRectF(0, y - 9, plot.left() - 8, 18), Qt.AlignRight | Qt.AlignVCenter, format_number(tick))
        painter.setPen(QPen(QColor(pal["muted"]), 1))
        painter.drawLine(QPointF(plot.left() + 0.5, plot.top()), QPointF(plot.left() + 0.5, plot.bottom() + 0.5))
        painter.drawLine(QPointF(plot.left(), plot.bottom() + 0.5), QPointF(plot.right(), plot.bottom() + 0.5))
        if unit:
            painter.setFont(make_font("ui", 11, 400))
            painter.setPen(QColor(pal["muted"]))
            painter.drawText(QRectF(2, 0, self.LEFT - 6, 14), Qt.AlignRight | Qt.AlignTop, unit)

    def _paint_bars(self, painter, plot, pal, data):
        values, labels, colors, y_max = data["values"], data["labels"], data["colors"], data["y_max"]
        n = max(1, len(values))
        slot = plot.width() / n
        bar_w = min(72.0, slot * 0.58)
        painter.setPen(Qt.NoPen)
        for i, value in enumerate(values):
            x = plot.left() + slot * i + (slot - bar_w) / 2
            top = self._y(plot, value, 0.0, y_max)
            painter.setBrush(QColor(colors[i]))
            painter.drawRoundedRect(QRectF(x, top, bar_w, max(1.0, plot.bottom() - top)), 3, 3)
            painter.setPen(QColor(pal["text"]))
            painter.setFont(make_font("data", 12, 700))
            text = data["value_text"](value) if data["value_text"] else format_number(value)
            painter.drawText(QRectF(x - 14, top - 20, bar_w + 28, 18), Qt.AlignCenter, text)
            painter.setFont(make_font("ui", 12, 500))
            painter.setPen(QColor(pal["muted"]))
            painter.drawText(QRectF(x - 14, plot.bottom() + 6, bar_w + 28, 20), Qt.AlignCenter, labels[i])
            painter.setPen(Qt.NoPen)
        # linhas de referência (limites de saturação)
        for value, label, level in data["ref_lines"]:
            if not 0 < value <= y_max:
                continue
            y = round(self._y(plot, value, 0.0, y_max)) + 0.5
            color = level_color(pal, level)
            pen = QPen(color, 1.8, Qt.DashLine)
            painter.setPen(pen)
            painter.drawLine(QPointF(plot.left(), y), QPointF(plot.right(), y))
            painter.setFont(make_font("ui", 11, 700))
            painter.setPen(color)
            painter.drawText(QRectF(plot.left() + 6, y - 18, 260, 16), Qt.AlignLeft | Qt.AlignVCenter, label)

    def _paint_line(self, painter, plot, pal, data):
        values, y_min, y_max, band = data["values"], data["y_min"], data["y_max"], data["band"]
        if band:
            low, high = band
            y_high, y_low = self._y(plot, high, y_min, y_max), self._y(plot, low, y_min, y_max)
            fill = QColor(pal["positive"])
            fill.setAlpha(34)
            painter.setPen(Qt.NoPen)
            painter.setBrush(fill)
            painter.drawRect(QRectF(plot.left() + 1, y_high, plot.width() - 1, max(1.0, y_low - y_high)))
            painter.setPen(QPen(QColor(pal["positive"]), 1.2, Qt.DashLine))
            for y in (y_high, y_low):
                painter.drawLine(QPointF(plot.left(), round(y) + 0.5), QPointF(plot.right(), round(y) + 0.5))
            painter.setFont(make_font("ui", 11, 700))
            painter.setPen(QColor(pal["positive"]))
            painter.drawText(QRectF(plot.left() + 6, y_high + 2, 260, 16), Qt.AlignLeft | Qt.AlignVCenter, "Faixa de referência")
        n = len(values)
        step = plot.width() / max(1, n)
        points = [(plot.left() + step * (i + 0.5), self._y(plot, v, y_min, y_max), v)
                  for i, v in enumerate(values) if v is not None]
        line_color = QColor(_series()[0])
        if len(points) > 1:
            pen = QPen(line_color, 3.0)
            pen.setCapStyle(Qt.RoundCap)
            pen.setJoinStyle(Qt.RoundJoin)
            painter.setPen(pen)
            for (x1, y1, _), (x2, y2, _) in zip(points, points[1:]):
                painter.drawLine(QPointF(x1, y1), QPointF(x2, y2))
        for index, (x, y, value) in enumerate(points):
            outside = band is not None and not band[0] <= value <= band[1]
            last = index == len(points) - 1
            color = QColor(pal["warning"]) if outside else line_color
            painter.setPen(QPen(QColor(pal["surface"]), 2.5))
            painter.setBrush(color)
            radius = 7.0 if last else 4.5
            painter.drawEllipse(QPointF(x, y), radius, radius)
        if points:
            x, y, value = points[-1]
            text = data["point_text"](value) if data["point_text"] else format_number(value)
            painter.setFont(make_font("data", 12, 700))
            painter.setPen(QColor(pal["text"]))
            box_x = min(max(plot.left(), x - 50), plot.right() - 100)
            painter.drawText(QRectF(box_x, y - 28 if y - 28 > plot.top() else y + 10, 100, 18), Qt.AlignCenter, text)
        painter.setFont(make_font("ui", 11, 400))
        painter.setPen(QColor(pal["muted"]))
        painter.drawText(QRectF(plot.left(), plot.bottom() + 6, 160, 18), Qt.AlignLeft | Qt.AlignVCenter,
                         f"Últimas {n} leituras" if n > 1 else "Leitura atual")
        painter.drawText(QRectF(plot.right() - 120, plot.bottom() + 6, 120, 18), Qt.AlignRight | Qt.AlignVCenter, "mais recente →")


# ---------------------------------------------------------------------------------------
def _caption(text, role="body", muted=False, heading=False):
    label = QLabel(text)
    label.setStyleSheet(("color: #9CA3AF; " if muted else "") + ty.qss(role))
    if heading:
        label.setProperty("role", "heading")
    label.setWordWrap(True)
    return label


class KpiDetailDialog(QDialog):
    """Janela de um indicador: estado, motivo, o que fazer, gráfico atual, histórico e canais."""

    def __init__(self, window, kind, parent=None):
        super().__init__(parent or window)
        self.window_ref = window
        self.kind = kind
        self.setWindowTitle(f"{ks.TITLES[kind]} · SpectrumLab Pro")
        self.setModal(False)
        self.resize(780, 700)
        self.setMinimumSize(600, 560)
        root = QVBoxLayout(self)
        root.setContentsMargins(22, 18, 22, 18)
        root.setSpacing(12)

        head = QHBoxLayout()
        head.addWidget(_caption(ks.TITLES[kind], "section", heading=True), 1)
        self.badge = StatusBadge()
        head.addWidget(self.badge, 0, Qt.AlignRight | Qt.AlignVCenter)
        root.addLayout(head)
        root.addWidget(_caption(ks.EXPLANATION[kind], "body", muted=True))

        self.lbl_value = _caption("—", "kpi", heading=True)
        root.addWidget(self.lbl_value)
        self.lbl_headline = _caption("", "button")
        root.addWidget(self.lbl_headline)
        self.lbl_hints = _caption("", "body", muted=True)
        root.addWidget(self.lbl_hints)

        self.plot_now = PlotWidget()
        self.plot_history = PlotWidget()
        root.addWidget(_caption("Leitura atual", "label", muted=True))
        root.addWidget(self.plot_now, 3)
        root.addWidget(_caption("Histórico desta sessão", "label", muted=True))
        root.addWidget(self.plot_history, 2)

        self.table = QGridLayout()
        self.table.setHorizontalSpacing(18)
        self.table.setVerticalSpacing(3)
        self._cells = []
        for column, title in enumerate(("Canal", "Contagem (ADC)", "Parte do total", "Papel neste indicador")):
            self.table.addWidget(_caption(title, "label", muted=True), 0, column)
        for row in range(6):
            cells = [QLabel("—") for _ in range(4)]
            for column, cell in enumerate(cells):
                cell.setStyleSheet(ty.qss("data" if column in (1, 2) else "body"))
                self.table.addWidget(cell, row + 1, column)
            self._cells.append(cells)
        self.table.setColumnStretch(3, 1)
        root.addLayout(self.table)

        buttons = QHBoxLayout()
        buttons.addStretch(1)
        close = QPushButton("Fechar")
        close.clicked.connect(self.close)
        buttons.addWidget(close)
        root.addLayout(buttons)
        self.refresh()

    # ---- conteúdo
    def refresh(self):
        w = self.window_ref
        kind = self.kind
        raw, snv = available_reading(w)
        history = list(getattr(w, "_kpi_history", ()))
        status = ks.evaluate(kind, raw, snv)
        pal = _palette()
        self.badge.set_status(status.level)
        self.lbl_headline.setText(getattr(w, "_reading_unavailable_reason", "") or status.headline)
        self.lbl_hints.setText("\n".join("• " + hint for hint in status.hints))
        self.lbl_hints.setVisible(bool(status.hints))
        self.lbl_value.setText(self._value_text(raw, snv))
        self._fill_table(raw, status)
        self._fill_plots(raw, snv, history, status, pal)

    def _value_text(self, raw, snv):
        if raw is None or len(raw) != 6:
            return "—"
        if self.kind == "energy":
            return f"{format_number(sum(raw))} ADC"
        if self.kind == "peak":
            return f"{ks.WAVELENGTHS[list(raw).index(max(raw))]} nm"
        ratio = ks.ratio_value(self.kind, snv)
        return f"{ratio:.2f}" if ratio is not None else "—"

    def _fill_table(self, raw, status):
        total = sum(raw) if raw and len(raw) == 6 else 0
        for i, cells in enumerate(self._cells):
            cells[0].setText(f"{ks.WAVELENGTHS[i]} nm")
            if raw and len(raw) == 6:
                cells[1].setText(format_number(raw[i]))
                cells[2].setText(f"{raw[i] / total * 100:.1f} %" if total > 0 else "—")
            else:
                cells[1].setText("—")
                cells[2].setText("—")
            role = ""
            if i in status.channels:
                if self.kind in ("energy", "peak"):
                    role = "Saturado" if status.level == ks.ERROR else "Perto da saturação"
                else:
                    role = "Usado na razão"
            elif self.kind == "peak" and raw and len(raw) == 6 and raw[i] == max(raw):
                role = "Canal dominante"
            cells[3].setText(role)

    def _fill_plots(self, raw, snv, history, status, pal):
        series = _series()
        neutral = QColor(pal["disabled"]).name()
        if not raw or len(raw) != 6:
            self.plot_now.set_empty("Faça uma leitura para ver o gráfico.")
            self.plot_history.set_empty("Sem leituras nesta sessão.")
            return
        labels = [f"{wl} nm" for wl in ks.WAVELENGTHS]
        if self.kind in ("energy", "peak"):
            colors = [series[i] for i in range(6)]
            if self.kind == "peak":
                top = list(raw).index(max(raw))
                colors = [series[0] if i == top else neutral for i in range(6)]
            for i in status.channels:
                colors[i] = pal["danger"] if status.level == ks.ERROR else pal["warning"]
            self.plot_now.set_bars(raw, labels, colors, max(ks.SATURATION_ADC * 1.08, max(raw) * 1.05),
                                   ref_lines=((ks.SATURATION_ADC, "Saturação · 65.500 ADC", ks.ERROR),
                                              (ks.NEAR_SATURATION_ADC, "Atenção · 58.000 ADC", ks.ATTENTION)),
                                   unit="ADC")
        else:
            used = (1, 2) if self.kind == "ratio_cel" else (5, 3)
            values = [(snv[i] * 100.0 if snv and len(snv) == 6 else 0.0) for i in used]
            self.plot_now.set_bars(values, [labels[i] for i in used], [series[0], series[1]],
                                   max(values) * 1.25 or 1.0, unit="%",
                                   value_text=lambda v: f"{v:.1f} %")
        self._fill_history(history, series)

    def _fill_history(self, history, series):
        if not history:
            self.plot_history.set_empty("Sem leituras nesta sessão.")
            return
        if self.kind == "energy":
            values = [entry["total"] for entry in history]
            self.plot_history.set_history(values, 0.0, max(max(values) * 1.15, 1.0), unit="ADC")
        elif self.kind == "peak":
            values = [entry["peak_nm"] for entry in history]
            self.plot_history.set_history(values, ks.WAVELENGTHS[0] - 20, ks.WAVELENGTHS[-1] + 20, unit="nm",
                                          point_text=lambda v: f"{v:.0f} nm")
        else:
            values = [entry[self.kind] for entry in history]
            numeric = [v for v in values if v is not None]
            top = max([ks.RATIO_RANGE[1]] + numeric) * 1.1
            self.plot_history.set_history(values, 0.0, top, band=ks.RATIO_RANGE, unit="razão",
                                          point_text=lambda v: f"{v:.2f}")


class TerminalDialog(QDialog):
    """O log de telemetria e comandos em janela própria. Reaproveita o QTextEdit da janela principal."""

    def __init__(self, window, parent=None):
        super().__init__(parent or window)
        self.window_ref = window
        self.setWindowTitle("Terminal · Telemetria e comandos · SpectrumLab Pro")
        self.setModal(False)
        self.resize(860, 560)
        self.setMinimumSize(520, 360)
        layout = QVBoxLayout(self)
        layout.setContentsMargins(18, 16, 18, 16)
        layout.setSpacing(10)
        layout.addWidget(_caption("Terminal", "section", heading=True))
        layout.addWidget(_caption("Tudo o que o equipamento enviou e o que o supervisório respondeu, em ordem.", "body", muted=True))
        console = window.txt_console
        console.setMinimumHeight(0)
        console.setMaximumHeight(16777215)
        console.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Expanding)
        layout.addWidget(console, 1)
        console.show()
        buttons = QHBoxLayout()
        self.lbl_info = _caption("", "caption", muted=True)
        buttons.addWidget(self.lbl_info, 1)
        copy = QPushButton("Copiar tudo")
        copy.clicked.connect(self.copy_all)
        close = QPushButton("Fechar")
        close.clicked.connect(self.close)
        buttons.addWidget(copy)
        buttons.addWidget(close)
        layout.addLayout(buttons)

    def copy_all(self):
        QApplication.clipboard().setText(self.window_ref.txt_console.toPlainText())
        self.lbl_info.setText("Conteúdo copiado.")


# ---------------------------------------------------------------------------------------
def make_entry(raw, r_snv):
    """Registro de uma leitura para o histórico da sessão."""
    values = [float(v) for v in raw]
    return {
        "time": datetime.datetime.now().strftime("%H:%M:%S"),
        "total": sum(values),
        "peak_nm": ks.WAVELENGTHS[values.index(max(values))],
        "ratio_cel": ks.ratio_value("ratio_cel", r_snv),
        "ratio_water": ks.ratio_value("ratio_water", r_snv),
    }


def card_status_text(level):
    return {ks.NONE: "", ks.OK: "Normal", ks.ATTENTION: "Atenção", ks.ERROR: "Erro"}[level]


def available_reading(window):
    if not getattr(window, "_result_valid", False):
        return None, None
    return getattr(window, "current_scan_data", None), getattr(window, "current_r_snv", None)


def update_cards(window):
    """Pinta o estado nos quatro cartões do painel principal."""
    raw, snv = available_reading(window)
    for kind, card in _cards(window).items():
        level = ks.evaluate(kind, raw, snv).level
        card.set_status(level, card_status_text(level))


def _cards(window):
    return {"energy": window.kpi_energy, "peak": window.kpi_peak,
            "ratio_cel": window.kpi_ratio_cel, "ratio_water": window.kpi_ratio_water}


def record_reading(window, raw, r_snv):
    """Chamado a cada leitura processada: guarda no histórico, atualiza cartões e janelas abertas."""
    if not hasattr(window, "_kpi_history"):
        window._kpi_history = collections.deque(maxlen=HISTORY_LENGTH)
    try:
        window._kpi_history.append(make_entry(raw, r_snv))
    except (ValueError, TypeError):
        return
    refresh_all(window)


def refresh_all(window):
    update_cards(window)
    for dialog in getattr(window, "_kpi_dialogs", {}).values():
        if dialog.isVisible():
            dialog.refresh()


def open_kpi(window, kind):
    dialogs = window.__dict__.setdefault("_kpi_dialogs", {})
    dialog = dialogs.get(kind)
    if dialog is None:
        dialog = dialogs[kind] = KpiDetailDialog(window, kind)
    else:
        dialog.refresh()
    dialog.show()
    dialog.raise_()
    dialog.activateWindow()
    return dialog


def open_terminal(window):
    dialog = getattr(window, "_terminal_dialog", None)
    if dialog is None:
        dialog = window._terminal_dialog = TerminalDialog(window)
    dialog.lbl_info.setText("")
    dialog.show()
    dialog.raise_()
    dialog.activateWindow()
    return dialog


def install(window):
    """Liga os cartões do painel às suas janelas e pinta o estado inicial."""
    for kind, card in _cards(window).items():
        card.clicked.connect(lambda _=False, k=kind: open_kpi(window, k))
    window._kpi_history = collections.deque(maxlen=HISTORY_LENGTH)
    update_cards(window)

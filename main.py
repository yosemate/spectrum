"""
SPECTRUM-LAB PRO (v3.1 Fluent Edition)
Sistema Supervisório e Analisador Espectrométrico NIR/VIS (GY-AS7263)
Metodologia Quimiométrica: Suspensão Aquosa de Celulose sob Lâmina e Lamínula.

Funcionalidades Consolidadas:
1. Protocolo Serial Consolidado (115200 Baud):
   - Comandos de Saída (\\n): CMD:PING, CMD:ABRIR_GAVETA, CMD:FECHAR_GAVETA,
     CMD:AVANCAR_SENSOR, CMD:RECUAR_SENSOR, CMD:LER_ESPECTRO, CMD:EMERGENCIA.
   - Telemetrias de Retorno: STATUS:SENSOR_OK / STATUS:PRONTO, STATUS:PONG,
     STATUS:GAVETA_ABERTA, STATUS:GAVETA_FECHADA, STATUS:SENSOR_AVANCADO,
     STATUS:SENSOR_RECUADO, DATA:v1..v6, STATUS:LEITURA_CONCLUIDA, STATUS:EMERGENCIA_ACIONADA.
2. Desacoplamento Atômico dos Controles Manuais (intertravamento até retorno do STATUS).
3. Ciclos Automáticos da Máquina de Estados (FSM):
   - Ciclo Automático Simples (Fechar Gaveta -> Avançar -> Ler -> Recuar -> Abrir).
   - Teste de Repetibilidade (Posicionamento Único, 5 Leituras 100% Estáticas, estatísticas u, s, CV%).
   - Parada de Emergência (E-Stop prioritário imediato e restauração segura).
4. Camada de Calibração e Quimiometria:
   - Persistência em calibracao.json (Branco com Água Destilada e Escuro).
   - Refletância Relativa (R_i) e Normalização Vetorial SNV (R_norm).
   - Eixos do Gráfico 2D: X (Celulose R680/R730) vs Y (Água R860/R760).
5. Auditoria e Isolamento de Threads com SerialWorker sem duplicações de sinal.
"""

import sys
import os
import json
import csv
import datetime
import random
import math
import tempfile
import traceback
import uuid
import time
from typing import Optional, List, Dict

from PyQt5.QtWidgets import (
    QApplication, QMainWindow, QWidget, QVBoxLayout, QHBoxLayout, QGridLayout, QLabel,
    QPushButton, QComboBox, QProgressBar, QFrame, QTextEdit, QMessageBox,
    QInputDialog, QLineEdit, QFileDialog, QSplitter, QStackedWidget, QDialog,
    QTableWidget, QTableWidgetItem, QHeaderView, QTabWidget, QMenuBar, QMenu, QAction,
    QSizePolicy, QAbstractItemView
)
from PyQt5.QtCore import Qt, QTimer, QThread, QEventLoop, QCoreApplication, pyqtSignal, QUrl
from PyQt5.QtGui import QFont, QColor, QDesktopServices

# Ativação antecipada de suporte nativo a High-DPI para telas de notebook com escala 125%/150%
try:
    QCoreApplication.setAttribute(Qt.AA_EnableHighDpiScaling, True)
    QCoreApplication.setAttribute(Qt.AA_UseHighDpiPixmaps, True)
except Exception:
    pass

# Matplotlib para integração gráfica Qt
from matplotlib.backends.backend_qt5agg import FigureCanvasQTAgg as FigureCanvas
from matplotlib.figure import Figure
import matplotlib.pyplot as plt

# Módulos locais
from responsive_layout import ScaledCanvasView, DialogScreenAdapter
from appearance import ensure_theme_manager, AppearanceDialog
from popup_design import WarningSymbol, AnimatedOperationBar, OperatingAlertDialog
from splash_screen import AnimatedSplashScreen
from animated_chart import SpectralSplineChartWidget, ScatterPlotWidget
from database_manager import DatabaseManagerDialog
from chemometrics import classify_experimental_kappa
from analysis_messages import scan_blocker
from pdf_generator import generate_pdf_report
from connection_worker import ConnectionWorker
from serial_worker import SerialWorker
from chemometrics import (
    ChemometricsEngine, calculate_hybrid_similarity, calculate_kappa_number,
    WAVELENGTHS, CHANNEL_NAMES, OPERATIONAL_MODES, MODE_LABELS,
    CALIB_TIMEOUT_OPTIONS, DEFAULT_TIMEOUT_SECS
)
from manual_control_dialog import ManualControlDialog
from equipment_interlocks import EquipmentInterlocks
from database import get_database_path, DatabaseManager
from runtime_data import prepare_data_files
from auth_dialogs import DialogLogin, DialogGestaoUsuarios
from version import __version__, __build__, __app_name__, __app_title__, __app_full_title__
from brand_assets import program_logo_pixmap, program_icon
import typography as ty


def open_pdf(path):
    """Abre arquivos locais com o serviço nativo do Qt em Windows e Linux."""
    if not QDesktopServices.openUrl(QUrl.fromLocalFile(os.path.abspath(path))):
        raise OSError("Nenhum visualizador de PDF disponível neste ambiente")


# =====================================================================
# 0. DIÁLOGO MODAL DE CALIBRAÇÃO EXPIRADA (INTERTRAVAMENTO METROLÓGICO)
# =====================================================================
class CalibrationExpiredDialog(QDialog):
    """
    Diálogo modal de advertência e intertravamento metrológico disparado
    quando o tempo de validade da calibração do método operacional ativo é atingido.
    """
    def __init__(self, parent=None, active_mode="umido"):
        super().__init__(parent)
        self.setWindowTitle("Alerta Metrológico — Calibração Expirada")
        self.setFixedSize(540, 260)
        self.setStyleSheet("""
            QDialog {
                background-color: #18181B;
                border: 2px solid #EF4444;
                border-radius: 12px;
            }
            QLabel {
                color: #F3F4F6;
                font-family: 'Segoe UI', Arial, sans-serif;
            }
        """)

        layout = QVBoxLayout(self)
        layout.setContentsMargins(24, 20, 24, 20)
        layout.setSpacing(14)

        header_layout = QHBoxLayout()
        icon = QLabel("")
        icon.setStyleSheet("font-size: 32px;")
        header_layout.addWidget(icon)

        title_box = QVBoxLayout()
        title = QLabel("CALIBRAÇÃO INSTRUMENTAL EXPIRADA")
        title.setStyleSheet("color: #EF4444; font-size: 14px; font-weight: 800; letter-spacing: 0.5px;")
        mode_label = MODE_LABELS.get(active_mode, active_mode)
        sub = QLabel(f"Método Analítico: <b>{mode_label}</b>")
        sub.setStyleSheet("color: #38BDF8; font-size: 11px;")
        title_box.addWidget(title)
        title_box.addWidget(sub)
        header_layout.addLayout(title_box)
        header_layout.addStretch()
        layout.addLayout(header_layout)

        msg = QLabel(
            "O intervalo de validade metrológica desta calibração foi atingido.<br>"
            "Para assegurar a repetibilidade e a exatidão analítica de celulose e lignina, "
            "as rotinas de ciclo automático e repetibilidade foram <b>intertravadas</b> preventivamente.<br><br>"
            "Deseja realizar a calibração de referência agora?"
        )
        msg.setStyleSheet("color: #D1D5DB; font-size: 11px; line-height: 1.4;")
        msg.setWordWrap(True)
        layout.addWidget(msg)

        btn_layout = QHBoxLayout()
        btn_layout.addStretch()

        self.btn_cancel = QPushButton("Fechar")
        self.btn_cancel.setStyleSheet("""
            QPushButton {
                background-color: #27272A;
                color: #A1A1AA;
                border: 1px solid #3F3F46;
                padding: 8px 16px;
                border-radius: 6px;
                font-weight: bold;
                font-size: 11px;
            }
            QPushButton:hover {
                background-color: #3F3F46;
                color: #FFFFFF;
            }
        """)
        self.btn_cancel.clicked.connect(self.reject)
        btn_layout.addWidget(self.btn_cancel)

        self.btn_calib = QPushButton("Calibrar Agora")
        self.btn_calib.setStyleSheet("""
            QPushButton {
                background-color: #0284C7;
                color: #FFFFFF;
                border: none;
                padding: 8px 20px;
                border-radius: 6px;
                font-weight: bold;
                font-size: 11px;
            }
            QPushButton:hover {
                background-color: #0369A1;
            }
        """)
        self.btn_calib.clicked.connect(self.accept)
        btn_layout.addWidget(self.btn_calib)

        layout.addLayout(btn_layout)


# =====================================================================
# 0.1 DIÁLOGO MODAL DE HISTÓRICO COMPLETO DE ENSAIOS (FLUENT DESIGN)
# =====================================================================
class HistoryDialog(QDialog):
    """
    Diálogo modal com Fluent Design (~1050x700 px) para consulta, visualização,
    geração de laudos PDF sob demanda, exclusão física e exportação CSV
    de todos os ensaios espectrais persistidos no SQLite (tabela leituras_historico).
    """
    def __init__(self, db_manager: DatabaseManager, parent=None):
        super().__init__(parent)
        self.db_manager = db_manager
        self.leituras = []
        self.current_selected = None

        self.setWindowTitle("Histórico Completo de Ensaios Espectrais — SPECTRUM-LAB PRO")
        self.resize(1080, 720)
        self.setMinimumSize(960, 640)
        self.setStyleSheet("""
            QDialog {
                background-color: #18181B;
                color: #FFFFFF;
                font-family: 'Segoe UI', Arial, sans-serif;
            }
            QLabel {
                color: #FFFFFF;
            }
            QLineEdit {
                background-color: #27272A;
                color: #FFFFFF;
                border: 1px solid #3F3F46;
                border-radius: 6px;
                padding: 6px 10px;
                font-size: 11px;
            }
            QLineEdit:focus {
                border: 1px solid #0284C7;
            }
            QTableWidget {
                background-color: #202023;
                color: #F4F4F5;
                border: 1px solid #3F3F46;
                border-radius: 6px;
                gridline-color: #2E2E33;
                selection-background-color: #0284C7;
                selection-color: #FFFFFF;
                font-size: 11px;
            }
            QHeaderView::section {
                background-color: #27272A;
                color: #A1A1AA;
                border: none;
                border-bottom: 1px solid #3F3F46;
                padding: 5px;
                font-weight: bold;
                font-size: 10px;
            }
            QPushButton {
                background-color: #27272A;
                color: #FFFFFF;
                border: 1px solid #3F3F46;
                border-radius: 6px;
                padding: 7px 14px;
                font-size: 11px;
                font-weight: bold;
            }
            QPushButton:hover {
                background-color: #3F3F46;
            }
            QPushButton:disabled {
                background-color: #1F1F22;
                color: #71717A;
                border-color: #2E2E33;
            }
        """)

        self._init_ui()
        self._carregar_leituras()

    def _init_ui(self):
        main_layout = QVBoxLayout(self)
        main_layout.setContentsMargins(18, 16, 18, 16)
        main_layout.setSpacing(12)

        # Cabeçalho do diálogo
        head_layout = QHBoxLayout()
        icon = QLabel("")
        icon.setStyleSheet("font-size: 24px;")
        head_layout.addWidget(icon)

        title_box = QVBoxLayout()
        dlg_title = QLabel("HISTÓRICO DE ENSAIOS ESPECTRAIS")
        dlg_title.setStyleSheet("color: #FFFFFF; font-size: 15px; font-weight: 800; letter-spacing: 0.5px;")
        dlg_sub = QLabel("Consulta metrológica, emissão de relatórios experimentais PDF e auditoria de leituras")
        dlg_sub.setStyleSheet("color: #9CA3AF; font-size: 11px;")
        title_box.addWidget(dlg_title)
        title_box.addWidget(dlg_sub)
        head_layout.addLayout(title_box)
        head_layout.addStretch()

        self.btn_fechar = QPushButton("Fechar")
        self.btn_fechar.clicked.connect(self.accept)
        head_layout.addWidget(self.btn_fechar)
        main_layout.addLayout(head_layout)

        # Divisor horizontal central
        splitter = QSplitter(Qt.Horizontal)
        splitter.setHandleWidth(2)
        splitter.setStyleSheet("QSplitter::handle { background-color: #333338; }")

        # --- Painel Esquerdo: Busca e Tabela ---
        left_widget = QWidget()
        left_layout = QVBoxLayout(left_widget)
        left_layout.setContentsMargins(0, 0, 8, 0)
        left_layout.setSpacing(8)

        self.txt_busca = QLineEdit()
        self.txt_busca.setPlaceholderText("Buscar por código de amostra, operador, data...")
        self.txt_busca.textChanged.connect(self._on_search_changed)
        left_layout.addWidget(self.txt_busca)

        self.table = QTableWidget()
        self.table.setColumnCount(6)
        self.table.setHorizontalHeaderLabels(["ID", "Data / Hora", "Amostra", "Método", "Kappa", "ADC Global"])
        self.table.setSelectionBehavior(QAbstractItemView.SelectRows)
        self.table.setSelectionMode(QAbstractItemView.SingleSelection)
        self.table.setEditTriggers(QAbstractItemView.NoEditTriggers)
        self.table.verticalHeader().setVisible(False)
        self.table.horizontalHeader().setStretchLastSection(True)
        self.table.setColumnWidth(0, 45)
        self.table.setColumnWidth(1, 125)
        self.table.setColumnWidth(2, 95)
        self.table.setColumnWidth(3, 85)
        self.table.setColumnWidth(4, 55)
        self.table.itemSelectionChanged.connect(self._on_selection_changed)
        left_layout.addWidget(self.table)

        self.lbl_total_records = QLabel("Total: 0 ensaios")
        self.lbl_total_records.setStyleSheet("color: #71717A; font-size: 10px;")
        left_layout.addWidget(self.lbl_total_records)
        splitter.addWidget(left_widget)

        # --- Painel Direito: Preview e Ações ---
        right_widget = QWidget()
        right_layout = QVBoxLayout(right_widget)
        right_layout.setContentsMargins(8, 0, 0, 0)
        right_layout.setSpacing(10)

        # Card de Detalhes da Leitura
        self.preview_card = QFrame()
        self.preview_card.setStyleSheet("background-color: #202023; border: 1px solid #3F3F46; border-radius: 8px;")
        card_layout = QVBoxLayout(self.preview_card)
        card_layout.setContentsMargins(14, 12, 14, 12)
        card_layout.setSpacing(10)

        # Título da Leitura Selecionada
        self.lbl_preview_title = QLabel("Selecione um ensaio na lista à esquerda")
        self.lbl_preview_title.setStyleSheet("color: #F4F4F5; font-size: 13px; font-weight: bold;")
        self.lbl_preview_meta = QLabel("Nenhum registro selecionado.")
        self.lbl_preview_meta.setStyleSheet("color: #A1A1AA; font-size: 10px;")
        card_layout.addWidget(self.lbl_preview_title)
        card_layout.addWidget(self.lbl_preview_meta)

        # 3 Cards de KPI em linha
        kpis_layout = QHBoxLayout()
        kpis_layout.setSpacing(8)

        # KPI 1: Kappa
        self.card_kpi_kappa = QFrame()
        self.card_kpi_kappa.setStyleSheet("background-color: #27272A; border: 1px solid #3F3F46; border-radius: 6px;")
        kpi_k_layout = QVBoxLayout(self.card_kpi_kappa)
        kpi_k_layout.setContentsMargins(8, 6, 8, 6)
        kpi_k_layout.setSpacing(2)
        lbl_k_head = QLabel("KAPPA DEMONSTRATIVO")
        lbl_k_head.setStyleSheet("color: #A1A1AA; font-size: 9px; font-weight: bold;")
        self.lbl_k_val = QLabel("--")
        self.lbl_k_val.setStyleSheet("color: #C084FC; font-size: 16px; font-weight: 900;")
        self.lbl_k_badge = QLabel("Aguardando")
        self.lbl_k_badge.setStyleSheet("color: #71717A; font-size: 9px; font-weight: bold;")
        kpi_k_layout.addWidget(lbl_k_head)
        kpi_k_layout.addWidget(self.lbl_k_val)
        kpi_k_layout.addWidget(self.lbl_k_badge)
        kpis_layout.addWidget(self.card_kpi_kappa)

        # KPI 2: Energia / Pico
        self.card_kpi_peak = QFrame()
        self.card_kpi_peak.setStyleSheet("background-color: #27272A; border: 1px solid #3F3F46; border-radius: 6px;")
        kpi_p_layout = QVBoxLayout(self.card_kpi_peak)
        kpi_p_layout.setContentsMargins(8, 6, 8, 6)
        kpi_p_layout.setSpacing(2)
        lbl_p_head = QLabel("PICO DOMINANTE")
        lbl_p_head.setStyleSheet("color: #A1A1AA; font-size: 9px; font-weight: bold;")
        self.lbl_p_val = QLabel("--")
        self.lbl_p_val.setStyleSheet("color: #60A5FA; font-size: 16px; font-weight: 900;")
        self.lbl_p_sub = QLabel("ADC Total: --")
        self.lbl_p_sub.setStyleSheet("color: #71717A; font-size: 9px;")
        kpi_p_layout.addWidget(lbl_p_head)
        kpi_p_layout.addWidget(self.lbl_p_val)
        kpi_p_layout.addWidget(self.lbl_p_sub)
        kpis_layout.addWidget(self.card_kpi_peak)

        # KPI 3: Razões Ópticas
        self.card_kpi_ratios = QFrame()
        self.card_kpi_ratios.setStyleSheet("background-color: #27272A; border: 1px solid #3F3F46; border-radius: 6px;")
        kpi_r_layout = QVBoxLayout(self.card_kpi_ratios)
        kpi_r_layout.setContentsMargins(8, 6, 8, 6)
        kpi_r_layout.setSpacing(2)
        lbl_r_head = QLabel("RAZÕES ÓPTICAS")
        lbl_r_head.setStyleSheet("color: #A1A1AA; font-size: 9px; font-weight: bold;")
        self.lbl_r_cel = QLabel("Celulose (680/730): --")
        self.lbl_r_cel.setStyleSheet("color: #10B981; font-size: 11px; font-weight: bold;")
        self.lbl_r_wat = QLabel("Matriz (860/760): --")
        self.lbl_r_wat.setStyleSheet("color: #38BDF8; font-size: 11px; font-weight: bold;")
        kpi_r_layout.addWidget(lbl_r_head)
        kpi_r_layout.addWidget(self.lbl_r_cel)
        kpi_r_layout.addWidget(self.lbl_r_wat)
        kpis_layout.addWidget(self.card_kpi_ratios)

        card_layout.addLayout(kpis_layout)

        # Tabela Multicanal da Leitura Selecionada
        lbl_tbl_title = QLabel("DISCRIMINAÇÃO ESPECTRAL DAS 6 BANDAS")
        lbl_tbl_title.setStyleSheet("color: #A1A1AA; font-size: 9px; font-weight: bold; letter-spacing: 0.5px; margin-top: 4px;")
        card_layout.addWidget(lbl_tbl_title)

        self.table_channels = QTableWidget(6, 4)
        self.table_channels.setHorizontalHeaderLabels(["Canal", "λ (nm)", "ADC Bruto", "Refletância (%)"])
        self.table_channels.verticalHeader().setVisible(False)
        self.table_channels.horizontalHeader().setStretchLastSection(True)
        self.table_channels.setEditTriggers(QAbstractItemView.NoEditTriggers)
        self.table_channels.setFixedHeight(175)
        card_layout.addWidget(self.table_channels)

        right_layout.addWidget(self.preview_card)

        # Barra de Ações Rápidas
        actions_box = QHBoxLayout()
        actions_box.setSpacing(8)

        self.btn_view_pdf = QPushButton("Visualizar Relatório PDF")
        self.btn_view_pdf.setStyleSheet("background-color: #0284C7; color: #FFFFFF; border: none;")
        self.btn_view_pdf.clicked.connect(self._on_visualizar_pdf)
        self.btn_view_pdf.setEnabled(False)

        self.btn_save_pdf = QPushButton("Salvar Relatório Como...")
        self.btn_save_pdf.clicked.connect(self._on_salvar_pdf)
        self.btn_save_pdf.setEnabled(False)

        self.btn_delete = QPushButton("Excluir Registro")
        self.btn_delete.setStyleSheet("background-color: #7F1D1D; color: #F87171; border: 1px solid #991B1B;")
        self.btn_delete.clicked.connect(self._on_excluir_registro)
        self.btn_delete.setEnabled(False)

        self.btn_export_csv = QPushButton("Exportar CSV")
        self.btn_export_csv.clicked.connect(self._on_exportar_csv)

        actions_box.addWidget(self.btn_view_pdf)
        actions_box.addWidget(self.btn_save_pdf)
        actions_box.addWidget(self.btn_delete)
        actions_box.addWidget(self.btn_export_csv)
        right_layout.addLayout(actions_box)

        splitter.addWidget(right_widget)
        splitter.setSizes([480, 560])
        main_layout.addWidget(splitter, stretch=1)

    def _carregar_leituras(self, filtro=None):
        self.leituras = self.db_manager.listar_leituras(filtro)
        self.table.setRowCount(len(self.leituras))
        for row_idx, item in enumerate(self.leituras):
            id_str = str(item.get("id", ""))
            ts_str = str(item.get("timestamp", ""))
            amostra_str = str(item.get("codigo_amostra", ""))
            is_seco = "sec" in str(item.get("metodo_analitico", "")).lower()
            metodo_str = "Seco" if is_seco else "Úmido"
            kappa_val = item.get("kappa_estimado", 0.0)
            kappa_str = f"{kappa_val:.2f}"
            adc_str = f"{int(item.get('intensidade_global_adc', 0)):,}".replace(",", ".")

            self.table.setItem(row_idx, 0, QTableWidgetItem(id_str))
            self.table.setItem(row_idx, 1, QTableWidgetItem(ts_str))
            self.table.setItem(row_idx, 2, QTableWidgetItem(amostra_str))
            self.table.setItem(row_idx, 3, QTableWidgetItem(metodo_str))
            
            it_kappa = QTableWidgetItem(kappa_str)
            it_kappa.setForeground(QColor("#C084FC" if kappa_val < 15.0 else "#F59E0B"))
            self.table.setItem(row_idx, 4, it_kappa)
            
            self.table.setItem(row_idx, 5, QTableWidgetItem(adc_str))

        self.lbl_total_records.setText(f"Total: {len(self.leituras)} ensaios registrados")
        if not self.leituras:
            self._limpar_preview()

    def _on_search_changed(self, text):
        self._carregar_leituras(text.strip())

    def _limpar_preview(self):
        self.current_selected = None
        self.lbl_preview_title.setText("Selecione um ensaio na lista à esquerda")
        self.lbl_preview_meta.setText("Nenhum registro selecionado.")
        self.lbl_k_val.setText("--")
        self.lbl_k_badge.setText("Aguardando")
        self.lbl_p_val.setText("--")
        self.lbl_p_sub.setText("ADC Total: --")
        self.lbl_r_cel.setText("Celulose (680/730): --")
        self.lbl_r_wat.setText("Matriz (860/760): --")
        self.table_channels.clearContents()
        self.btn_view_pdf.setEnabled(False)
        self.btn_save_pdf.setEnabled(False)
        self.btn_delete.setEnabled(False)

    def _on_selection_changed(self):
        selected_rows = self.table.selectionModel().selectedRows()
        if not selected_rows:
            self._limpar_preview()
            return
        row_idx = selected_rows[0].row()
        if row_idx >= len(self.leituras):
            return

        item = self.leituras[row_idx]
        self.current_selected = item

        # Atualiza Header
        cod = item.get("codigo_amostra", "AM-0001")
        ts = item.get("timestamp", "")
        op = item.get("operador", "Operador")
        met = item.get("metodo_analitico", "Modo Seco")
        self.lbl_preview_title.setText(f"Amostra: {cod} (ID #{item['id']})")
        self.lbl_preview_meta.setText(f"Data: {ts} | Operador: {op} | Método: {met}")

        # KPI 1: Kappa
        kappa_val = item.get("kappa_estimado", 0.0)
        self.lbl_k_val.setText(f"{kappa_val:.2f}")
        status_txt = classify_experimental_kappa(kappa_val)[0]
        self.lbl_k_badge.setText(status_txt)

        badge_col = classify_experimental_kappa(kappa_val)[1]

        self.lbl_k_badge.setStyleSheet(f"color: {badge_col}; font-size: 9px; font-weight: bold;")

        # KPI 2: Pico / ADC
        pico_nm = item.get("pico_espectral_nm", 610)
        pico_adc = item.get("pico_espectral_adc", 0)
        total_adc = item.get("intensidade_global_adc", 0)
        self.lbl_p_val.setText(f"{pico_nm} nm")
        self.lbl_p_sub.setText(f"Pico: {pico_adc:,} ADC | Total: {total_adc:,} ADC".replace(",", "."))

        # KPI 3: Razões
        r_c = item.get("razao_celulose", 0.0)
        r_w = item.get("razao_agua", 0.0)
        self.lbl_r_cel.setText(f"Celulose (680/730): {r_c:.2f}")
        self.lbl_r_wat.setText(f"Matriz (860/760): {r_w:.2f}")

        # Tabela Multicanal
        wls = [610, 680, 730, 760, 810, 860]
        cnames = ['Vermelho', 'Vermelho Profundo', 'NIR 730', 'NIR 760', 'NIR 810', 'NIR 860']
        adcs = [
            item.get("adc_610", 0.0), item.get("adc_680", 0.0), item.get("adc_730", 0.0),
            item.get("adc_760", 0.0), item.get("adc_810", 0.0), item.get("adc_860", 0.0)
        ]
        refs = [
            item.get("ref_610", 0.0), item.get("ref_680", 0.0), item.get("ref_730", 0.0),
            item.get("ref_760", 0.0), item.get("ref_810", 0.0), item.get("ref_860", 0.0)
        ]
        for i in range(6):
            self.table_channels.setItem(i, 0, QTableWidgetItem(cnames[i]))
            self.table_channels.setItem(i, 1, QTableWidgetItem(f"{wls[i]} nm"))
            self.table_channels.setItem(i, 2, QTableWidgetItem(f"{int(adcs[i]):,} ADC".replace(",", ".")))
            self.table_channels.setItem(i, 3, QTableWidgetItem(f"{refs[i]:.2f}%"))

        self.btn_view_pdf.setEnabled(True)
        self.btn_save_pdf.setEnabled(True)
        self.btn_delete.setEnabled(True)

    def _on_visualizar_pdf(self):
        try:
            if not self.current_selected:
                return
            item = self.current_selected
            unique_id = f"{item.get('id', 0)}_{datetime.datetime.now().strftime('%Y%m%d_%H%M%S_%f')}"
            temp_dir = tempfile.gettempdir()
            pdf_path = os.path.join(temp_dir, f"Relatorio_Preview_{item.get('codigo_amostra', 'AM')}_{unique_id}.pdf")

            generate_pdf_report(
                filename=pdf_path,
                sample_id=item.get("codigo_amostra", "AM-0001"),
                operator=item.get("operador", "Operador"),
                kappa_value=item.get("kappa_estimado", 0.0),
                operational_mode="seco" if "sec" in str(item.get("metodo_analitico", "")).lower() else "umido",
                kappa_status=item.get("kappa_classificacao"),
                calibration_snapshot=json.loads(item["calibration_snapshot"]) if item.get("calibration_snapshot") else None,
                acquisition_count=item.get("acquisition_count") or 0,
                raw_scans=json.loads(item["raw_scans_json"]) if item.get("raw_scans_json") else None,
                values=[
                    item.get("ref_610", 0.0), item.get("ref_680", 0.0), item.get("ref_730", 0.0),
                    item.get("ref_760", 0.0), item.get("ref_810", 0.0), item.get("ref_860", 0.0)
                ],
                raw_adc_values=[
                    item.get("adc_610", 0.0), item.get("adc_680", 0.0), item.get("adc_730", 0.0),
                    item.get("adc_760", 0.0), item.get("adc_810", 0.0), item.get("adc_860", 0.0)
                ],
                ratio_celulose=item.get("razao_celulose"),
                ratio_agua=item.get("razao_agua"),
                global_intensity_adc=item.get("intensidade_global_adc"),
                peak_wavelength_nm=item.get("pico_espectral_nm"),
                peak_intensity_adc=item.get("pico_espectral_adc"),
                timestamp=item.get("timestamp")
            )
            try:
                open_pdf(pdf_path)
            except Exception as start_err:
                QMessageBox.warning(
                    self, "Aviso de Visualização",
                    f"O Relatório Experimental PDF foi gerado com sucesso em:\n{pdf_path}\n\n"
                    f"Porém não foi possível abrir o leitor padrão do sistema: {start_err}"
                )
        except Exception as e:
            traceback.print_exc()
            QMessageBox.critical(self, "Erro ao Gerar PDF", f"Não foi possível gerar o Relatório Experimental PDF:\n{e}")

    def _on_salvar_pdf(self):
        if not self.current_selected:
            return
        item = self.current_selected
        def_name = f"Relatorio_{item.get('codigo_amostra', 'AM')}_{datetime.datetime.now().strftime('%Y%m%d_%H%M%S')}.pdf"
        file_path, _ = QFileDialog.getSaveFileName(self, "Salvar Relatório Experimental PDF", def_name, "Arquivos PDF (*.pdf)")
        if file_path:
            try:
                generate_pdf_report(
                    filename=file_path,
                    sample_id=item.get("codigo_amostra", "AM-0001"),
                    operator=item.get("operador", "Operador"),
                    kappa_value=item.get("kappa_estimado", 0.0),
                    operational_mode="seco" if "sec" in str(item.get("metodo_analitico", "")).lower() else "umido",
                    kappa_status=item.get("kappa_classificacao"),
                calibration_snapshot=json.loads(item["calibration_snapshot"]) if item.get("calibration_snapshot") else None,
                acquisition_count=item.get("acquisition_count") or 0,
                raw_scans=json.loads(item["raw_scans_json"]) if item.get("raw_scans_json") else None,
                    values=[
                        item.get("ref_610", 0.0), item.get("ref_680", 0.0), item.get("ref_730", 0.0),
                        item.get("ref_760", 0.0), item.get("ref_810", 0.0), item.get("ref_860", 0.0)
                    ],
                    raw_adc_values=[
                        item.get("adc_610", 0.0), item.get("adc_680", 0.0), item.get("adc_730", 0.0),
                        item.get("adc_760", 0.0), item.get("adc_810", 0.0), item.get("adc_860", 0.0)
                    ],
                    ratio_celulose=item.get("razao_celulose"),
                    ratio_agua=item.get("razao_agua"),
                    global_intensity_adc=item.get("intensidade_global_adc"),
                    peak_wavelength_nm=item.get("pico_espectral_nm"),
                    peak_intensity_adc=item.get("pico_espectral_adc"),
                    timestamp=item.get("timestamp")
                )
                QMessageBox.information(self, "Sucesso", f"Relatório salvo com sucesso em:\n{file_path}")
            except PermissionError:
                QMessageBox.warning(
                    self, "Arquivo Bloqueado",
                    f"Não foi possível salvar o relatório em:\n{file_path}\n\n"
                    "O arquivo está aberto e bloqueado por outro aplicativo.\n"
                    "Feche o visualizador de PDF ou escolha outro nome de arquivo."
                )
            except Exception as e:
                QMessageBox.critical(self, "Erro", f"Erro ao salvar PDF: {e}")

    def _on_excluir_registro(self):
        if not self.current_selected:
            return
        item = self.current_selected
        reply = QMessageBox.question(
            self, "Confirmar Exclusão",
            f"Deseja realmente excluir permanentemente o ensaio ID #{item['id']} da amostra '{item.get('codigo_amostra')}'?\nEsta ação não poderá ser desfeita.",
            QMessageBox.Yes | QMessageBox.No, QMessageBox.No
        )
        if reply == QMessageBox.Yes:
            ok = self.db_manager.excluir_leitura(item['id'])
            if ok:
                self.current_selected = None
                self._carregar_leituras(self.txt_busca.text())
                QMessageBox.information(self, "Sucesso", "Registro excluído com sucesso do banco de dados.")
            else:
                QMessageBox.warning(self, "Aviso", "Não foi possível excluir o registro.")

    def _on_exportar_csv(self):
        if not self.leituras:
            QMessageBox.warning(self, "Aviso", "Não há leituras disponíveis para exportação.")
            return
        def_name = f"Historico_Ensaios_{datetime.datetime.now().strftime('%Y%m%d_%H%M%S')}.csv"
        file_path, _ = QFileDialog.getSaveFileName(self, "Exportar Histórico CSV", def_name, "Arquivos CSV (*.csv)")
        if file_path:
            try:
                import csv
                with open(file_path, "w", newline="", encoding="utf-8-sig") as f:
                    writer = csv.writer(f, delimiter=";")
                    writer.writerow([
                        "ID", "Data_Hora", "Amostra", "Operador", "Metodo",
                        "Kappa_Demonstrativo", "Faixa_Modelo_Experimental",
                        "Intensidade_Global_ADC", "Pico_NM", "Pico_ADC",
                        "Razao_Celulose", "Razao_Agua",
                        "ADC_610", "ADC_680", "ADC_730", "ADC_760", "ADC_810", "ADC_860",
                        "Ref_610", "Ref_680", "Ref_730", "Ref_760", "Ref_810", "Ref_860"
                    ])
                    for row in self.leituras:
                        writer.writerow([
                            row.get("id"), row.get("timestamp"), row.get("codigo_amostra"), row.get("operador"), row.get("metodo_analitico"),
                            row.get("kappa_estimado"), row.get("kappa_classificacao"),
                            row.get("intensidade_global_adc"), row.get("pico_espectral_nm"), row.get("pico_espectral_adc"),
                            row.get("razao_celulose"), row.get("razao_agua"),
                            row.get("adc_610"), row.get("adc_680"), row.get("adc_730"), row.get("adc_760"), row.get("adc_810"), row.get("adc_860"),
                            row.get("ref_610"), row.get("ref_680"), row.get("ref_730"), row.get("ref_760"), row.get("ref_810"), row.get("ref_860")
                        ])
                QMessageBox.information(self, "Exportação Concluída", f"Exportados {len(self.leituras)} registros com sucesso para:\n{file_path}")
            except Exception as e:
                QMessageBox.critical(self, "Erro", f"Erro ao exportar CSV: {e}")


# =====================================================================
# 1. INDICADOR DE STATUS / BADGE
# =====================================================================
class ModernStatusBadge(QFrame):
    def __init__(self, title="STATUS", active_color="#10B981", inactive_color="#64748B", parent=None):
        super().__init__(parent)
        self.active_color = active_color
        self.inactive_color = inactive_color
        self.is_active = False

        self.setStyleSheet("""
            QFrame {
                background-color: #202020;
                border: 1px solid #383838;
                border-radius: 6px;
            }
        """)

        layout = QHBoxLayout(self)
        layout.setContentsMargins(8, 4, 8, 4)
        layout.setSpacing(6)

        self.dot = QLabel("●")
        self.dot.setStyleSheet(f"color: {self.inactive_color}; font-size: 11px;")

        self.lbl_text = QLabel(f"{title}: DESCONECTADO")
        self.lbl_text.setStyleSheet("color: #D1D5DB; " + ty.qss("label"))

        layout.addWidget(self.dot)
        layout.addWidget(self.lbl_text)
        self.title = title

    def set_active(self, active: bool, status_text: str = None, custom_color: str = None):
        self.is_active = active
        if custom_color:
            color = custom_color
        else:
            color = self.active_color if active else self.inactive_color
        self.dot.setStyleSheet(f"color: {color}; font-size: 11px;")
        if status_text:
            self.lbl_text.setText(f"{self.title}: {status_text}")
        else:
            txt = "CONECTADO" if active else "DESCONECTADO"
            self.lbl_text.setText(f"{self.title}: {txt}")
        if custom_color:
            self.lbl_text.setStyleSheet(f"color: {custom_color}; " + ty.qss("label"))
        else:
            self.lbl_text.setStyleSheet("color: #D1D5DB; " + ty.qss("label"))


# =====================================================================
# 2. KPI CARD ESTILO POWER BI (WINDOWS 11 FLUENT)
# =====================================================================
class PowerBiKpiCard(QFrame):
    """
    Indicador compacto (ISA-101): título, estado e valor. Sem ícone nem filete de cor; só o estado
    anormal ganha cor (propriedade kpiStatus, estilizada em scada_ui.dashboard_style).
    Clicar (ou Enter/Espaço) emite `clicked`; a janela de detalhes é aberta por detail_windows.
    """
    clicked = pyqtSignal()

    def __init__(self, icon_str, title_str, default_value="--", subtitle_str="", accent_color="#38BDF8", parent=None):
        super().__init__(parent)
        self.accent_color = accent_color
        self.setObjectName("kpiCard")
        self.setProperty("kpiStatus", "none")
        self.setCursor(Qt.PointingHandCursor)
        self.setFocusPolicy(Qt.StrongFocus)
        self.setStyleSheet("""
            QFrame#kpiCard {
                background-color: #2b2b2b;
                border: 1px solid #3d3d3d;
                border-radius: 8px;
            }
        """)

        layout = QVBoxLayout(self)
        layout.setContentsMargins(12, 8, 12, 8)
        layout.setSpacing(0)

        header = QHBoxLayout()
        header.setSpacing(6)
        self.lbl_title = QLabel(title_str)
        self.lbl_title.setStyleSheet("color: #9CA3AF; " + ty.qss("label"))
        self.lbl_status = QLabel("")
        self.lbl_status.setObjectName("kpiStatusLabel")
        self.lbl_status.setProperty("kpiStatus", "none")
        self.lbl_status.setStyleSheet(ty.qss("caption"))
        header.addWidget(self.lbl_title)
        header.addStretch()
        header.addWidget(self.lbl_status)
        layout.addLayout(header)

        self.lbl_value = QLabel(default_value)
        self.lbl_value.setStyleSheet("color: #FFFFFF; " + ty.qss("kpi"))
        layout.addWidget(self.lbl_value)

        self.lbl_sub = QLabel(subtitle_str)
        self.lbl_sub.setStyleSheet("color: #9CA3AF; " + ty.qss("caption"))
        layout.addWidget(self.lbl_sub)

    def set_value(self, value_text: str, subtitle_text: str = None, color_override: str = None):
        self.lbl_value.setText(value_text)
        if color_override:
            self.lbl_value.setStyleSheet(f"color: {color_override}; " + ty.qss("kpi", "font-size: 22px;"))
        else:
            self.lbl_value.setStyleSheet("color: #FFFFFF; " + ty.qss("kpi", "font-size: 22px;"))
        if subtitle_text is not None:
            self.lbl_sub.setText(subtitle_text)

    def set_status(self, level: str, text: str = ""):
        """level: none, ok, attention ou error (ver kpi_status). Normal fica discreto; só o anormal ganha cor."""
        for widget in (self, self.lbl_status):
            widget.setProperty("kpiStatus", level)
            widget.style().unpolish(widget)
            widget.style().polish(widget)
        self.lbl_status.setText(text)
        self.setToolTip("Clique para ver os detalhes" + (f" · {text}" if text else ""))

    def mouseReleaseEvent(self, event):
        if event.button() == Qt.LeftButton and self.rect().contains(event.pos()):
            self.clicked.emit()
        super().mouseReleaseEvent(event)

    def keyPressEvent(self, event):
        if event.key() in (Qt.Key_Return, Qt.Key_Enter, Qt.Key_Space):
            self.clicked.emit()
            return
        super().keyPressEvent(event)


# =====================================================================
# 2.5 CARD KPI DE MONITORAMENTO DA CALIBRAÇÃO (R², RMSE, N, BADGE)
# =====================================================================
class CardKpiCalibracao(QFrame):
    """
    Card de métricas (KPI) de monitoramento da calibração instrumental.
    Exibe:
    - Título: 'Status da Calibração'
    - R² (Coeficiente de Determinação): formatado com 3 casas decimais (ex: 0.000 ou --)
    - RMSE (Erro Médio Quadrático): formatado com 3 casas decimais (ex: ± 0.000 ou --)
    - Aquisições de branco (N): quantidade de amostras (ex: N = 0)
    - Badge de Validação Visual:
      * R² >= 0.95: 'Calibrado (Excelente)' (fundo verde suave)
      * 0.85 <= R² < 0.95: 'Calibrado (Ajuste Regular)' (fundo amarelo/laranja suave)
      * R² < 0.85 ou curva vazia: 'Não Calibrado / Baixo Ajuste' (fundo cinza/vermelho suave)
    """
    def __init__(self, parent=None):
        super().__init__(parent)
        self.setObjectName("cardKpiCalibracao")
        self.setStyleSheet("""
            QFrame#cardKpiCalibracao {
                background-color: #1A1F26;
                border: 1px solid #374151;
                border-radius: 8px;
            }
            QLabel {
                font-family: 'Segoe UI', Arial, sans-serif;
            }
        """)

        layout = QVBoxLayout(self)
        layout.setContentsMargins(12, 10, 12, 10)
        layout.setSpacing(8)

        # Cabeçalho: Título + Badge de Validação
        header = QHBoxLayout()
        icon = QLabel("")
        icon.setStyleSheet("font-size: 14px;")
        lbl_title = QLabel("Status da Calibração")
        lbl_title.setStyleSheet("color: #38BDF8; " + ty.qss("section"))
        lbl_title.setProperty("role", "heading")

        self.lbl_badge = QLabel("Não Calibrado / Baixo Ajuste")
        self.lbl_badge.setAlignment(Qt.AlignCenter)
        self.lbl_badge.setStyleSheet("""
            background-color: #2D1A1F;
            color: #F87171;
            border: 1px solid #DC2626;
            border-radius: 4px;
            padding: 4px 10px;
            font-size: 12px;
            font-weight: bold;
        """)

        header.addWidget(icon)
        header.addWidget(lbl_title)
        header.addStretch()
        header.addWidget(self.lbl_badge)
        layout.addLayout(header)

        # Métricas em destaque: uma linha por indicador (rótulo à esquerda, valor à direita).
        # Antes eram três colunas estreitas: o texto não cabia e ficava comprimido.
        metrics_layout = QVBoxLayout()
        metrics_layout.setSpacing(8)

        def metric_row(name, value_label, color_hex):
            row = QFrame()
            row.setObjectName("calibMetricRow")
            row.setStyleSheet("background-color: #11141A; border: 1px solid #1F2937; border-radius: 10px;")
            row_layout = QHBoxLayout(row)
            row_layout.setContentsMargins(14, 10, 14, 10)
            row_layout.setSpacing(12)
            caption = QLabel(name)
            caption.setWordWrap(True)
            caption.setStyleSheet("color: #9CA3AF; border: 0; background: transparent; " + ty.qss("card"))
            value_label.setStyleSheet(f"color: {color_hex}; border: 0; background: transparent; " + ty.qss("kpi"))
            value_label.setAlignment(Qt.AlignRight | Qt.AlignVCenter)
            row_layout.addWidget(caption, 1)
            row_layout.addWidget(value_label, 0)
            return row

        self.lbl_r2 = QLabel("--")
        metrics_layout.addWidget(metric_row("CV branco máximo (%)", self.lbl_r2, "#38BDF8"))
        self.lbl_rmse = QLabel("--")
        metrics_layout.addWidget(metric_row("Ruído escuro máximo (ADC)", self.lbl_rmse, "#A78BFA"))
        self.lbl_n = QLabel("N = 0")
        metrics_layout.addWidget(metric_row("Pontos de calibração", self.lbl_n, "#FBBF24"))

        layout.addLayout(metrics_layout)

        # Rodapé com metadados de calibração (Data/Hora e Operador)
        self.lbl_calib_footer = QLabel("Calibração: --")
        self.lbl_calib_footer.setStyleSheet("color: #9CA3AF; " + ty.qss("caption"))
        self.lbl_calib_footer.setWordWrap(True)
        layout.addWidget(self.lbl_calib_footer)

    def atualizar(self,r2=None,rmse=None,n_amostras=0,timestamp=None,operador=None,is_expired=False):
        win=self.window()
        if not hasattr(win,"chem_engine"):
            win=getattr(win,"main_win",None)
        eng=getattr(win,"chem_engine",None)
        p=eng.snapshot() if eng else {}
        ws,ds=p.get("white_stats",{}),p.get("dark_stats",{})
        self.lbl_r2.setText(f"{max(ws['cv_percent']):.2f}" if ws.get("cv_percent") else "--")
        self.lbl_rmse.setText(f"{max(ds['stdevs']):.2f}" if ds.get("stdevs") else "--")
        self.lbl_n.setText(f"N = {ws.get('n',0)}")
        self.lbl_calib_footer.setText(f"{timestamp or '--'} | Op: {operador or '--'}")
        valid=bool(eng and eng.calibration_valid())
        self.lbl_badge.setText("REFERÊNCIA VÁLIDA" if valid else "RECALIBRAR")
        self.lbl_badge.setStyleSheet("color: #34D399;" if valid else "color: #F87171;")


# =====================================================================
# 2.6 CARD DE DIAGNÓSTICO & TELEMETRIA DO SENSOR AS7263
# =====================================================================
from diagnostics import SensorDiagnosticsCard as CardDiagnosticoAS7263


# =====================================================================
# 3. DIÁLOGO MODAL DE CALIBRAÇÃO INSTRUMENTAL (BRANCO & ESCURO)
# =====================================================================
class CalibrationModalDialog(QDialog):
    """
    Diálogo para medição de Branco (Lâmina + Lamínula com Água Destilada) e Escuro Instrumental.
    """
    def __init__(self, main_win, parent=None):
        super().__init__(parent or main_win)
        self.main_win = main_win
        self.setWindowTitle("Referenciamento óptico — branco e escuro")
        self.setFixedSize(540, 520)
        self.setStyleSheet("""
            QDialog {
                background-color: #202020;
                color: #FFFFFF;
                border: 1px solid #3d3d3d;
                border-radius: 10px;
            }
            QLabel {
                color: #E5E7EB;
                font-family: 'Segoe UI';
            }
            QPushButton {
                background-color: #333333;
                color: #FFFFFF;
                border: 1px solid #4a4a4a;
                border-radius: 6px;
                padding: 10px 14px;
                font-weight: bold;
                font-size: 11px;
            }
            QPushButton:hover {
                background-color: #0284C7;
                border-color: #38BDF8;
            }
            QPushButton#btnPrimary {
                background-color: #0284C7;
                color: #FFFFFF;
                border: none;
            }
            QPushButton#btnPrimary:hover {
                background-color: #0369A1;
            }
        """)

        layout = QVBoxLayout(self)
        layout.setContentsMargins(20, 20, 20, 20)
        layout.setSpacing(12)

        title = QLabel("CALIBRAÇÃO INSTRUMENTAL DE REFERÊNCIA")
        title.setStyleSheet("color: #38BDF8; font-size: 13px; font-weight: bold; letter-spacing: 0.5px;")
        layout.addWidget(title)

        info_box = QFrame()
        info_box.setStyleSheet("background-color: #262626; border: 1px solid #383838; border-radius: 8px;")
        ib_layout = QVBoxLayout(info_box)
        ib_layout.setContentsMargins(12, 10, 12, 10)

        eng = self.main_win.chem_engine
        if eng.active_mode == "seco":
            desc_text = (
                "<b>Metodologia de Amostras Secas (Reflectância Difusa):</b><br>"
                "1. <b>Branco de Referência:</b> Insira na gaveta o <b>cartão branco fosco de referência</b> "
                "(cartão branco fosco), sem lâmina de vidro e sem solvente líquido.<br>"
                "2. <b>Escuro Instrumental:</b> Mede dez aquisições com LED desligado e câmara fechada."
            )
        else:
            desc_text = (
                "<b>Metodologia Quimiométrica de Celulose (Suspensão Aquosa):</b><br>"
                "1. <b>Branco de Referência:</b> Insira na gaveta uma lâmina e lamínula contendo "
                "apenas <b>água destilada pura</b> (matriz do solvente).<br>"
                "2. <b>Escuro Instrumental:</b> Mede o ruído elétrico/corrente de escuro do sensor."
            )

        lbl_desc = QLabel(desc_text)
        lbl_desc.setStyleSheet("color: #D1D5DB; font-size: 11px; line-height: 1.4;")
        lbl_desc.setWordWrap(True)
        ib_layout.addWidget(lbl_desc)
        layout.addWidget(info_box)

        # Configuração do Intervalo de Prazo operacional
        timeout_frame = QFrame()
        timeout_frame.setStyleSheet("background-color: #1F2937; border: 1px solid #374151; border-radius: 6px;")
        timeout_layout = QHBoxLayout(timeout_frame)
        timeout_layout.setContentsMargins(10, 6, 10, 6)
        timeout_layout.setSpacing(8)

        lbl_to = QLabel("Prazo operacional da Calibração:")
        lbl_to.setStyleSheet("color: #D1D5DB; font-size: 11px; font-weight: bold;")
        self.combo_calib_timeout = QComboBox()
        for text, secs in CALIB_TIMEOUT_OPTIONS:
            self.combo_calib_timeout.addItem(text, secs)

        cur_to = self.main_win.chem_engine.timeout_segundos
        cur_idx = 4
        for i in range(self.combo_calib_timeout.count()):
            if self.combo_calib_timeout.itemData(i) == cur_to:
                cur_idx = i
                break
        self.combo_calib_timeout.setCurrentIndex(cur_idx)
        self.combo_calib_timeout.setStyleSheet("""
            QComboBox {
                background-color: #111827;
                color: #FFFFFF;
                border: 1px solid #4B5563;
                border-radius: 4px;
                padding: 4px 8px;
                font-size: 11px;
            }
        """)
        self.combo_calib_timeout.currentIndexChanged.connect(self._on_timeout_changed)

        timeout_layout.addWidget(lbl_to)
        timeout_layout.addWidget(self.combo_calib_timeout)
        layout.addWidget(timeout_frame)

        # Card KPI de Monitoramento da Calibração
        self.card_kpi = CardKpiCalibracao(self)
        layout.addWidget(self.card_kpi)

        # Status Atual
        eng = self.main_win.chem_engine
        is_exp = eng.is_calibration_expired()
        if eng.is_calibrated:
            self.card_kpi.atualizar(
                r2=eng.r2, rmse=eng.rmse, n_amostras=eng.n_amostras,
                timestamp=eng.calib_timestamp, operador=eng.calib_operador,
                is_expired=is_exp
            )
        else:
            self.card_kpi.atualizar(r2=None, rmse=None, n_amostras=0, is_expired=True)

        if not eng.is_calibrated:
            st_text = "Status Atual: NÃO CALIBRADO"
            st_color = "#EF4444"
        elif is_exp:
            st_text = f"Status Atual: CALIBRAÇÃO EXPIRADA ({eng.calib_timestamp})"
            st_color = "#EF4444"
        else:
            st_text = f"Status Atual: CALIBRADO E VÁLIDO ({eng.calib_timestamp})"
            st_color = "#10B981"

        self.lbl_calib_info = QLabel(st_text)
        self.lbl_calib_info.setStyleSheet(f"color: {st_color}; font-size: 11px; font-weight: bold;")
        layout.addWidget(self.lbl_calib_info)

        # Botão 1: Calibração Sequencial Guiada
        self.btn_read_white = QPushButton("Iniciar Calibração Sequencial Completa (Branco -> Escuro)")
        self.btn_read_white.setObjectName("btnPrimary")
        self.btn_read_white.clicked.connect(self.trigger_white_calibration)
        layout.addWidget(self.btn_read_white)

        # Botão 2: Medir Escuro
        self.btn_read_dark = QPushButton("2. Definir Corrente de Escuro Manual (Zero Físico)")
        self.btn_read_dark.clicked.connect(self.set_dark_current_zeros)
        self.btn_read_dark.setEnabled(False)
        self.btn_read_dark.setText("Escuro medido automaticamente com LED desligado")
        layout.addWidget(self.btn_read_dark)

        layout.addStretch()

        # Botão Fechar
        btn_close = QPushButton("Fechar")
        btn_close.clicked.connect(self.accept)
        layout.addWidget(btn_close)

    def _on_timeout_changed(self, idx: int):
        secs = self.combo_calib_timeout.currentData()
        if secs:
            self.main_win.chem_engine.set_timeout_seconds(secs)
            self.main_win._check_calibration_validity()

    def trigger_white_calibration(self):
        if not self.main_win.is_serial_connected():
            QMessageBox.warning(self, "Hardware Desconectado", "Conecte o hardware ESP32 antes de calibrar.")
            return

        self.accept()
        self.main_win.start_white_calibration_cycle()

    def set_dark_current_zeros(self):
        self.lbl_calib_info.setText("Zero nominal desativado. Execute a calibração completa.")


# =====================================================================
# 4. DIÁLOGO MODAL DE INTERTRAVAMENTO HUMANO (CARREGAMENTO DE LÂMINA)
# =====================================================================
class SamplePlacementInterlockDialog(QDialog):
    """
    Janela modal de intertravamento humano para confirmação de posicionamento da lâmina.
    Exibida exclusivamente após a confirmação de hardware STATUS:GAVETA_ABERTA.
    """
    def __init__(self, title="Posicionamento de Amostra", message=None, parent=None):
        super().__init__(parent)
        self.setWindowTitle(title)
        self.setFixedSize(510, 270)
        self.setModal(True)
        self.setWindowFlags(self.windowFlags() & ~Qt.WindowContextHelpButtonHint)
        self.setStyleSheet("""
            QDialog {
                background-color: #202020;
                color: #FFFFFF;
                border: 1px solid #3d3d3d;
                border-radius: 10px;
            }
            QLabel {
                color: #FFFFFF;
                font-family: 'Segoe UI';
            }
            QPushButton {
                background-color: #333333;
                color: #FFFFFF;
                border: 1px solid #4a4a4a;
                border-radius: 6px;
                padding: 10px 18px;
                font-weight: bold;
                font-size: 11px;
            }
            QPushButton#btnConfirm {
                background-color: #0284C7;
                color: #FFFFFF;
                border: 1px solid #38BDF8;
            }
            QPushButton#btnConfirm:hover {
                background-color: #0369A1;
            }
            QPushButton#btnCancel {
                background-color: #2E1519;
                color: #F87171;
                border: 1px solid #DC2626;
            }
            QPushButton#btnCancel:hover {
                background-color: #7F1D1D;
                color: #FFFFFF;
            }
        """)

        layout = QVBoxLayout(self)
        layout.setContentsMargins(22, 20, 22, 20)
        layout.setSpacing(14)

        # Header com ícone
        header = QHBoxLayout()
        icon = QLabel("")
        icon.setStyleSheet("font-size: 24px;")
        lbl_title = QLabel(f"<b>{title.upper()}</b>")
        lbl_title.setStyleSheet("color: #38BDF8; font-size: 13px; letter-spacing: 0.5px;")
        header.addWidget(icon)
        header.addWidget(lbl_title)
        header.addStretch()
        layout.addLayout(header)

        # Mensagem informativa
        default_msg = (
            "A gaveta está aberta.<br><br>"
            "Insira a <b>lâmina com a lamínula</b> sobre o berço óptico de leitura e "
            "clique em <b>OK / Iniciar</b> para prosseguir com a medição."
        )
        self.lbl_msg = QLabel(message or default_msg)
        self.lbl_msg.setStyleSheet("color: #D1D5DB; font-size: 11px; line-height: 1.5;")
        self.lbl_msg.setWordWrap(True)
        layout.addWidget(self.lbl_msg)

        layout.addStretch()

        # Botões de Ação [ Cancelar / Abortar ] e [ OK / Iniciar ]
        btn_layout = QHBoxLayout()
        btn_layout.setSpacing(12)

        self.btn_cancel = QPushButton("Cancelar / Abortar")
        self.btn_cancel.setObjectName("btnCancel")
        self.btn_cancel.setCursor(Qt.PointingHandCursor)
        self.btn_cancel.clicked.connect(self.reject)

        self.btn_confirm = QPushButton("OK / Iniciar")
        self.btn_confirm.setObjectName("btnConfirm")
        self.btn_confirm.setCursor(Qt.PointingHandCursor)
        self.btn_confirm.clicked.connect(self.accept)

        btn_layout.addStretch()
        btn_layout.addWidget(self.btn_cancel)
        btn_layout.addWidget(self.btn_confirm)
        layout.addLayout(btn_layout)



# =====================================================================
# 5. DIÁLOGOS DE TRANSIÇÃO E SEGURANÇA DA CALIBRAÇÃO (ETAPA 2)
# =====================================================================
class CalibrationTransitionDialog(QDialog):
    """
    Popup 2: Transição entre Calibração de Branco e Fundo Escuro.
    Exibido com a gaveta aberta após a leitura do branco.
    """
    def __init__(self, parent=None):
        super().__init__(parent)
        self.setWindowTitle("Calibração de Branco Concluída")
        self.setFixedSize(510, 270)
        self.setModal(True)
        self.setWindowFlags(self.windowFlags() & ~Qt.WindowContextHelpButtonHint)
        self.setStyleSheet("""
            QDialog {
                background-color: #202020;
                color: #FFFFFF;
                border: 1px solid #3d3d3d;
                border-radius: 10px;
            }
            QLabel {
                color: #FFFFFF;
                font-family: 'Segoe UI';
            }
            QPushButton {
                background-color: #333333;
                color: #FFFFFF;
                border: 1px solid #4a4a4a;
                border-radius: 6px;
                padding: 10px 18px;
                font-weight: bold;
                font-size: 11px;
            }
            QPushButton#btnProceed {
                background-color: #0284C7;
                color: #FFFFFF;
                border: 1px solid #38BDF8;
            }
            QPushButton#btnProceed:hover {
                background-color: #0369A1;
            }
            QPushButton#btnClose {
                background-color: #2b2b2b;
                color: #E5E7EB;
                border: 1px solid #4a4a4a;
            }
            QPushButton#btnClose:hover {
                background-color: #383838;
                border-color: #6B7280;
            }
        """)

        layout = QVBoxLayout(self)
        layout.setContentsMargins(22, 20, 22, 20)
        layout.setSpacing(14)

        header = QHBoxLayout()
        icon = QLabel("")
        icon.setStyleSheet("font-size: 24px;")
        lbl_title = QLabel("<b>BRANCO MEDIDO — FALTA MEDIR O ESCURO</b>")
        lbl_title.setStyleSheet("color: #38BDF8; font-size: 13px; letter-spacing: 0.5px;")
        header.addWidget(icon)
        header.addWidget(lbl_title)
        header.addStretch()
        layout.addLayout(header)

        is_dry = (self.parent() and hasattr(self.parent(), "chem_engine") and self.parent().chem_engine.active_mode == "seco")
        ref_text = "cartão branco fosco de referência" if is_dry else "referência em água destilada"
        msg = (
            f"Leitura de {ref_text} registrada com sucesso.<br><br>"
            "Deseja prosseguir para a <b>Calibração de Fundo Escuro</b> agora?<br>"
            "<small style='color: #9CA3AF;'>Se cancelar, a gaveta será fechada e esta calibração incompleta será descartada.</small>"
        )
        self.lbl_msg = QLabel(msg)
        self.lbl_msg.setStyleSheet("color: #D1D5DB; font-size: 11px; line-height: 1.5;")
        self.lbl_msg.setWordWrap(True)
        layout.addWidget(self.lbl_msg)

        layout.addStretch()

        btn_layout = QHBoxLayout()
        btn_layout.setSpacing(12)

        self.btn_exit = QPushButton("Cancelar / Sair")
        self.btn_exit.setObjectName("btnClose")
        self.btn_exit.setCursor(Qt.PointingHandCursor)
        self.btn_exit.clicked.connect(self.reject)

        self.btn_proceed = QPushButton("Prosseguir para Escuro")
        self.btn_proceed.setObjectName("btnProceed")
        self.btn_proceed.setCursor(Qt.PointingHandCursor)
        self.btn_proceed.clicked.connect(self.accept)

        btn_layout.addStretch()
        btn_layout.addWidget(self.btn_exit)
        btn_layout.addWidget(self.btn_proceed)
        layout.addLayout(btn_layout)


class DarkSafetyInterlockDialog(QDialog):
    """
    Popup 3: Confirmação de Retirada da Lâmina e Gaveta Vazia para Fundo Escuro.
    """
    def __init__(self, parent=None):
        super().__init__(parent)
        self.setWindowTitle("Aviso de Segurança — Fundo Escuro")
        self.setFixedSize(520, 270)
        self.setModal(True)
        self.setWindowFlags(self.windowFlags() & ~Qt.WindowContextHelpButtonHint)
        self.setStyleSheet("""
            QDialog {
                background-color: #202020;
                color: #FFFFFF;
                border: 1px solid #3d3d3d;
                border-radius: 10px;
            }
            QLabel {
                color: #FFFFFF;
                font-family: 'Segoe UI';
            }
            QPushButton {
                background-color: #333333;
                color: #FFFFFF;
                border: 1px solid #4a4a4a;
                border-radius: 6px;
                padding: 10px 18px;
                font-weight: bold;
                font-size: 11px;
            }
            QPushButton#btnConfirmEmpty {
                background-color: #15803D;
                color: #FFFFFF;
                border: 1px solid #22C55E;
            }
            QPushButton#btnConfirmEmpty:hover {
                background-color: #166534;
            }
            QPushButton#btnCancel {
                background-color: #2E1519;
                color: #F87171;
                border: 1px solid #DC2626;
            }
            QPushButton#btnCancel:hover {
                background-color: #7F1D1D;
                color: #FFFFFF;
            }
        """)

        layout = QVBoxLayout(self)
        layout.setContentsMargins(22, 20, 22, 20)
        layout.setSpacing(14)

        header = QHBoxLayout()
        icon = QLabel("")
        icon.setStyleSheet("font-size: 24px;")
        lbl_title = QLabel("<b>AVISO DE SEGURANÇA — FUNDO ESCURO</b>")
        lbl_title.setStyleSheet("color: #F59E0B; font-size: 13px; letter-spacing: 0.5px;")
        header.addWidget(icon)
        header.addWidget(lbl_title)
        header.addStretch()
        layout.addLayout(header)

        msg = (
            "<b>Atenção:</b> A calibração de fundo escuro deve ser realizada com o <b>BERÇO TOTALMENTE VAZIO</b>.<br><br>"
            "Você já retirou a lâmina de água da gaveta?"
        )
        self.lbl_msg = QLabel(msg)
        self.lbl_msg.setStyleSheet("color: #E5E7EB; font-size: 11px; line-height: 1.5;")
        self.lbl_msg.setWordWrap(True)
        layout.addWidget(self.lbl_msg)

        layout.addStretch()

        btn_layout = QHBoxLayout()
        btn_layout.setSpacing(12)

        self.btn_cancel = QPushButton("Cancelar / Sair")
        self.btn_cancel.setObjectName("btnCancel")
        self.btn_cancel.setCursor(Qt.PointingHandCursor)
        self.btn_cancel.clicked.connect(self.reject)

        self.btn_confirm = QPushButton("Sim, lâmina removida e gaveta vazia")
        self.btn_confirm.setObjectName("btnConfirmEmpty")
        self.btn_confirm.setCursor(Qt.PointingHandCursor)
        self.btn_confirm.clicked.connect(self.accept)

        btn_layout.addStretch()
        btn_layout.addWidget(self.btn_cancel)
        btn_layout.addWidget(self.btn_confirm)
        layout.addLayout(btn_layout)


# =====================================================================
# 5.1 DIÁLOGO MODAL DE DECISÃO OPERACIONAL (FIM DE ENSAIO)
# =====================================================================
class DialogDecisaoConclusao(QDialog):
    """
    Diálogo modal com 3 botões claros de decisão ao concluir a leitura com a gaveta aberta:
    1. [ Finalizar e Fechar Gaveta ] (Padrão/Foco)
    2. [ Nova Análise ] (Mantém gaveta aberta, limpa dados e solicita novo ID)
    3. [ Iniciar Repetibilidade ] (Mantém gaveta aberta para inspeção e inicia repetições)
    """
    ACTION_FINISH = 1
    ACTION_NEW_SCAN = 2
    ACTION_REPEAT = 3

    def __init__(self, parent=None, is_repeatability=False):
        super().__init__(parent)
        self.setWindowTitle("Ensaio Concluído — Decisão Operacional")
        self.setFixedSize(540, 290)
        self.setModal(True)
        self.setWindowFlags(self.windowFlags() & ~Qt.WindowContextHelpButtonHint)
        self.selected_action = self.ACTION_FINISH

        self.setStyleSheet("""
            QDialog {
                background-color: #1F242D;
                color: #FFFFFF;
                border: 1px solid #374151;
                border-radius: 12px;
            }
            QLabel {
                color: #FFFFFF;
                font-family: 'Segoe UI', sans-serif;
            }
            QPushButton {
                border-radius: 6px;
                padding: 10px 16px;
                font-weight: bold;
                font-size: 11px;
                min-height: 20px;
            }
            QPushButton#btnFinish {
                background-color: #1E293B;
                color: #38BDF8;
                border: 1px solid #0284C7;
            }
            QPushButton#btnFinish:hover {
                background-color: #0369A1;
                color: #FFFFFF;
            }
            QPushButton#btnNewScan {
                background-color: #0284C7;
                color: #FFFFFF;
                border: 1px solid #38BDF8;
            }
            QPushButton#btnNewScan:hover {
                background-color: #0369A1;
            }
            QPushButton#btnRepeat {
                background-color: #4C1D95;
                color: #DDD6FE;
                border: 1px solid #8B5CF6;
            }
            QPushButton#btnRepeat:hover {
                background-color: #5B21B6;
                color: #FFFFFF;
            }
        """)

        layout = QVBoxLayout(self)
        layout.setContentsMargins(22, 20, 22, 20)
        layout.setSpacing(14)

        # Header
        header = QHBoxLayout()
        icon = QLabel("" if not is_repeatability else "")
        icon.setStyleSheet("font-size: 24px; color: #10B981;")
        lbl_h = QLabel("<b>LEITURA CONCLUÍDA COM SUCESSO</b>" if not is_repeatability else "<b>ENSAIO DE REPETIBILIDADE CONCLUÍDO</b>")
        lbl_h.setStyleSheet("color: #10B981; font-size: 12px; font-weight: bold; letter-spacing: 0.5px;")
        header.addWidget(icon)
        header.addWidget(lbl_h)
        header.addStretch()
        layout.addLayout(header)

        lbl_desc = QLabel(
            "A leitura óptica foi concluída e a gaveta está <b>aberta</b> no berço para manipulação da lâmina.<br>"
            "Selecione a ação desejada a seguir:"
        )
        lbl_desc.setStyleSheet("color: #D1D5DB; font-size: 11px; line-height: 1.5;")
        lbl_desc.setWordWrap(True)
        layout.addWidget(lbl_desc)

        layout.addStretch()

        btn_box = QVBoxLayout()
        btn_box.setSpacing(8)

        # Botão 1: Padrão / Foco
        self.btn_finish = QPushButton("Finalizar e Fechar Gaveta (Padrão)")
        self.btn_finish.setObjectName("btnFinish")
        self.btn_finish.setCursor(Qt.PointingHandCursor)
        # Sem botão padrão: Enter não aciona movimento motorizado. A escolha é explícita por clique.
        self.btn_finish.setAutoDefault(False)
        self.btn_finish.setDefault(False)
        self.btn_finish.clicked.connect(self._choose_finish)

        # Botão 2: Nova Análise
        self.btn_new = QPushButton("Nova Análise (Manter Gaveta Aberta)")
        self.btn_new.setObjectName("btnNewScan")
        self.btn_new.setCursor(Qt.PointingHandCursor)
        self.btn_new.clicked.connect(self._choose_new)

        # Botão 3: Iniciar Repetibilidade
        self.btn_repeat = QPushButton("Iniciar Repetibilidade (5 Leituras Consecutivas)")
        self.btn_repeat.setObjectName("btnRepeat")
        self.btn_repeat.setCursor(Qt.PointingHandCursor)
        self.btn_repeat.clicked.connect(self._choose_repeat)

        btn_box.addWidget(self.btn_finish)
        btn_box.addWidget(self.btn_new)
        btn_box.addWidget(self.btn_repeat)
        layout.addLayout(btn_box)

    def _choose_finish(self):
        self.selected_action = self.ACTION_FINISH
        self.accept()

    def _choose_new(self):
        self.selected_action = self.ACTION_NEW_SCAN
        self.accept()

    def _choose_repeat(self):
        self.selected_action = self.ACTION_REPEAT
        self.accept()


# =====================================================================
# 6. POPUP DE SEGURANÇA CONTRA RADIAÇÃO ÓPTICA (NIR) - ASSÍNCRONO
# =====================================================================
class DialogAlertaRadiacao(OperatingAlertDialog):
    """
    Diálogo modal não-bloqueante de aviso de segurança contra radiação óptica NIR.
    Abre automaticamente via .show() ao avançar o sensor para varredura óptica e fecha via .close().
    Possui botão de parada de emergência acessível diretamente durante a operação.
    """
    def __init__(self, parent=None):
        super().__init__(parent)
        self.setWindowTitle("AVISO DE SEGURANÇA: EMISSÃO ÓPTICA ATIVA")
        self.setFixedSize(530, 315)
        self.setWindowModality(Qt.ApplicationModal)
        # Desabilita botão 'X' de fechar a janela e botão de Ajuda
        self.setWindowFlags((self.windowFlags() | Qt.Dialog) & ~Qt.WindowCloseButtonHint & ~Qt.WindowContextHelpButtonHint)

        self.setStyleSheet("""
            QDialog {
                background-color: #1a1712;
                color: #FFFFFF;
                border: 2px solid #F59E0B;
                border-radius: 10px;
            }
            QLabel {
                color: #FFFFFF;
                font-family: 'Segoe UI', Arial, sans-serif;
            }
            QProgressBar {
                background-color: #2b2518;
                border: 1px solid #78350F;
                border-radius: 5px;
                height: 12px;
                text-align: center;
            }
            QProgressBar::chunk {
                background-color: #F59E0B;
                border-radius: 4px;
            }
        """)

        layout = QVBoxLayout(self)
        layout.setContentsMargins(24, 20, 24, 20)
        layout.setSpacing(12)

        # Cabeçalho com ícone de advertência
        header = QHBoxLayout()
        lbl_icon = WarningSymbol()

        title_box = QVBoxLayout()
        title_box.setSpacing(2)
        lbl_t1 = QLabel("AVISO DE SEGURANÇA — RADIAÇÃO ÓPTICA")
        lbl_t1.setStyleSheet("color: #F59E0B; font-size: 11px; font-weight: bold; letter-spacing: 0.8px;")
        lbl_t2 = QLabel("EMISSOR NIR ATIVO (730 nm - 860 nm)")
        lbl_t2.setStyleSheet("color: #FDE68A; font-size: 15px; font-weight: bold;")
        title_box.addWidget(lbl_t1)
        title_box.addWidget(lbl_t2)

        header.addWidget(lbl_icon)
        header.addLayout(title_box)
        header.addStretch()
        layout.addLayout(header)

        # Caixa de alerta e orientações
        msg_frame = QFrame()
        msg_frame.setStyleSheet("background-color: #291F11; border: 1px solid #78350F; border-radius: 6px; padding: 6px;")
        mf_layout = QVBoxLayout(msg_frame)
        mf_layout.setContentsMargins(12, 8, 12, 8)
        lbl_sub = QLabel(
            "Não olhe diretamente para a abertura óptica nem abra a câmara durante a varredura espectral.<br>"
            "<b>Radiação invisível de alta densidade no espectro infravermelho próximo.</b>"
        )
        lbl_sub.setStyleSheet("color: #FEF3C7; font-size: 11px; line-height: 1.4;")
        lbl_sub.setWordWrap(True)
        mf_layout.addWidget(lbl_sub)
        layout.addWidget(msg_frame)

        # Barra contínua / indeterminada (setRange(0, 0))
        self.pbar = AnimatedOperationBar()
        self.pbar.setRange(0, 0)
        layout.addWidget(self.pbar)

        self.lbl_status = QLabel("Varredura óptica em andamento. Câmara intertravada...")
        self.lbl_status.setStyleSheet("color: #D97706; font-size: 11px; font-weight: bold;")
        self.lbl_status.setAlignment(Qt.AlignCenter)
        layout.addWidget(self.lbl_status)

        # Botão de Parada de Emergência no corpo do diálogo
        self.btn_emergency = QPushButton("PARADA DE EMERGÊNCIA")
        self.btn_emergency.setCursor(Qt.PointingHandCursor)
        self.btn_emergency.setStyleSheet("""
            QPushButton {
                background-color: #d32f2f;
                color: white;
                font-weight: bold;
                font-size: 11px;
                padding: 8px 16px;
                border-radius: 4px;
                border: 1px solid #ef5350;
            }
            QPushButton:hover {
                background-color: #b71c1c;
            }
            QPushButton:pressed {
                background-color: #7f1d1d;
            }
        """)
        self.btn_emergency.clicked.connect(self._trigger_emergency)
        layout.addWidget(self.btn_emergency)

    def set_custom_status(self, text: str):
        self.lbl_status.setText(text)

    def _trigger_emergency(self):
        """
        Interrompe imediatamente as rotinas e timers em execução no Python,
        despacha CMD:EMERGENCIA\n pelo canal ativo e fecha o diálogo.
        """
        self.reject() if hasattr(self, "reject") else self.close()
        parent = self.parent()
        if parent and hasattr(parent, "stop_cycle_action"):
            parent.stop_cycle_action()
        QApplication.processEvents()


# =====================================================================
# 7. POPUP DE SEGURANÇA MECÂNICA (GAVETA MOTORIZADA) - ASSÍNCRONO
# =====================================================================
class DialogAlertaGaveta(OperatingAlertDialog):
    """
    Diálogo modal não-bloqueante de aviso de segurança contra risco de pinçamento mecânico.
    Abre automaticamente via .show() ao movimentar a gaveta em ciclos automáticos e fecha via .close().
    Possui bypass em acionamentos manuais e botão de parada de emergência acessível diretamente.
    """
    def __init__(self, parent=None):
        super().__init__(parent)
        self.setWindowTitle("AVISO: ATUADOR MECÂNICO EM OPERAÇÃO")
        self.setFixedSize(530, 315)
        self.setWindowModality(Qt.ApplicationModal)
        # Desabilita botão 'X' de fechar a janela e botão de Ajuda
        self.setWindowFlags((self.windowFlags() | Qt.Dialog) & ~Qt.WindowCloseButtonHint & ~Qt.WindowContextHelpButtonHint)

        self.setStyleSheet("""
            QDialog {
                background-color: #1a1712;
                color: #FFFFFF;
                border: 2px solid #E67E22;
                border-radius: 10px;
            }
            QLabel {
                color: #FFFFFF;
                font-family: 'Segoe UI', Arial, sans-serif;
            }
            QProgressBar {
                background-color: #2b2518;
                border: 1px solid #78350F;
                border-radius: 5px;
                height: 12px;
                text-align: center;
            }
            QProgressBar::chunk {
                background-color: #E67E22;
                border-radius: 4px;
            }
        """)

        layout = QVBoxLayout(self)
        layout.setContentsMargins(24, 20, 24, 20)
        layout.setSpacing(12)

        # Cabeçalho com ícone de advertência mecânica
        header = QHBoxLayout()
        lbl_icon = WarningSymbol()

        title_box = QVBoxLayout()
        title_box.setSpacing(2)
        lbl_t1 = QLabel("AVISO DE SEGURANÇA — ATUADOR MECÂNICO")
        lbl_t1.setStyleSheet("color: #E67E22; font-size: 11px; font-weight: bold; letter-spacing: 0.8px;")
        self.lbl_t2 = QLabel("MOVIMENTAÇÃO DE GAVETA EM ANDAMENTO")
        self.lbl_t2.setStyleSheet("color: #FDE68A; font-size: 14px; font-weight: bold;")
        title_box.addWidget(lbl_t1)
        title_box.addWidget(self.lbl_t2)

        header.addWidget(lbl_icon)
        header.addLayout(title_box)
        header.addStretch()
        layout.addLayout(header)

        # Caixa de alerta e orientações
        msg_frame = QFrame()
        msg_frame.setStyleSheet("background-color: #291F11; border: 1px solid #78350F; border-radius: 6px; padding: 6px;")
        mf_layout = QVBoxLayout(msg_frame)
        mf_layout.setContentsMargins(12, 8, 12, 8)
        lbl_sub = QLabel(
            "<b>Mantenha mãos e objetos afastados da zona de deslocamento do berço.</b><br>"
            "Risco de pinçamento mecânico durante a movimentação motorizada da gaveta."
        )
        lbl_sub.setStyleSheet("color: #FEF3C7; font-size: 11px; line-height: 1.4;")
        lbl_sub.setWordWrap(True)
        mf_layout.addWidget(lbl_sub)
        layout.addWidget(msg_frame)

        # Barra contínua / indeterminada (setRange(0, 0))
        self.pbar = AnimatedOperationBar()
        self.pbar.setRange(0, 0)
        layout.addWidget(self.pbar)

        self.lbl_status = QLabel("Gaveta motorizada em deslocamento...")
        self.lbl_status.setStyleSheet("color: #D97706; font-size: 11px; font-weight: bold;")
        self.lbl_status.setAlignment(Qt.AlignCenter)
        layout.addWidget(self.lbl_status)

        # Botão de Parada de Emergência no corpo do diálogo
        self.btn_emergency = QPushButton("PARADA DE EMERGÊNCIA")
        self.btn_emergency.setCursor(Qt.PointingHandCursor)
        self.btn_emergency.setStyleSheet("""
            QPushButton {
                background-color: #d32f2f;
                color: white;
                font-weight: bold;
                font-size: 11px;
                padding: 8px 16px;
                border-radius: 4px;
                border: 1px solid #ef5350;
            }
            QPushButton:hover {
                background-color: #b71c1c;
            }
            QPushButton:pressed {
                background-color: #7f1d1d;
            }
        """)
        self.btn_emergency.clicked.connect(self._trigger_emergency)
        layout.addWidget(self.btn_emergency)

    def set_action_status(self, text_status: str, detail: str = "MOVIMENTAÇÃO DE GAVETA EM ANDAMENTO"):
        self.lbl_t2.setText(detail)
        self.lbl_status.setText(text_status)

    def _trigger_emergency(self):
        """
        Interrompe imediatamente as rotinas e timers em execução no Python,
        despacha CMD:EMERGENCIA\n pelo canal ativo e fecha o diálogo.
        """
        self.reject() if hasattr(self, "reject") else self.close()
        parent = self.parent()
        if parent and hasattr(parent, "stop_cycle_action"):
            parent.stop_cycle_action()
        QApplication.processEvents()



# =====================================================================
# 8. JANELA PRINCIPAL DO SUPERVISÓRIO
# =====================================================================
class SpectrumLabMainWindow(QMainWindow):
    def __init__(self):
        super().__init__()
        self.runtime_files = prepare_data_files()
        self.theme_manager=ensure_theme_manager()
        self.setWindowTitle(__app_full_title__)
        self.setWindowIcon(program_icon())

        # Qt já fornece a área em unidades lógicas, considerando a escala do Windows.
        screen = QApplication.primaryScreen()
        area = screen.availableGeometry() if screen else None
        avail_w, avail_h = (area.width(), area.height()) if area else (1366,768)
        self.setMinimumSize(min(480,avail_w),min(320,avail_h))
        self.resize(int(avail_w*0.92),int(avail_h*0.90))
        self._start_maximized = avail_w<1450 or avail_h<850
        self._responsive_ready = False

        # Caminho da base e arquivos
        self.db_path = self.runtime_files["materials"]
        self.base_dir = os.path.dirname(self.db_path)

        # Motor Quimiométrico e Calibração
        self.chem_engine = ChemometricsEngine()

        # Thread de Comunicação Unificada (USB / Bluetooth SPP / Wi-Fi TCP)
        self.conn_worker = ConnectionWorker(self)
        self.serial_worker = self.conn_worker
        self._setup_serial_signals()

        # Variáveis de Estado Espectral
        self.current_scan_data = [0.0] * 6
        self.current_r_calibrated = [0.0] * 6
        self.current_r_snv = [0.0] * 6
        self.current_matched_material = "Standby (Sem Leitura)"
        self.current_match_percent = 0.0
        self.current_kappa_value = 0.0

        # Máquina de Estados Finita (FSM)
        self.fsm_state = "IDLE"
        self.auto_cycle_active = False
        self.modo_repetibilidade = False
        self.is_calibrating_white = False
        self.leituras_rep: List[List[float]] = []
        self._last_raw_payload: List[float] = []
        self._last_pong=time.monotonic()
        self._heartbeat_timer=QTimer(self)
        self._heartbeat_timer.timeout.connect(self._heartbeat_tick)
        self._heartbeat_timer.start(1000)
        self._protocol_ready=False
        self._sensor_ready=False
        self._optical_settings=dict(ChemometricsEngine.DEFAULT_SETTINGS)
        self._batch=None
        self._white_scans=[]
        self._dark_scans=[]
        self._rep_raw_scans=[]
        self._result_valid=False
        self._current_calibration_snapshot=None
        self._current_reading_timestamp=None
        self._operation_epoch=0
        self._current_reading_operator=None
        self._current_sample_id=None
        self._last_acquisition_scans=[]
        self._emergency_confirmed=False
        self._emergency_lock_active=False
        self._hardware_watchdog=QTimer(self)
        self._hardware_watchdog.setSingleShot(True)
        self._hardware_watchdog.timeout.connect(self._on_hardware_timeout)
        self._acquisition_timer=QTimer(self)
        self._acquisition_timer.setSingleShot(True)
        self._acquisition_timer.timeout.connect(self._dispatch_batch_read)
        self._temp_vetor_branco: List[float] = []
        self._temp_vetor_escuro: List[float] = []
        self._pending_routine: Optional[str] = None  # "AUTO", "REPETIBILIDADE", "CALIBRAÇÃO"
        self._radiation_dialog: Optional[DialogAlertaRadiacao] = None  # Alerta visual assíncrono de radiação óptica NIR
        self._drawer_dialog: Optional[DialogAlertaGaveta] = None        # Alerta visual assíncrono de risco mecânico (gaveta)

        # Gerenciador de Autenticação SQLite e Controle de Acesso (Compatibilidade .exe)
        self.auth_db_path = get_database_path("usuarios.db")
        self.auth_manager = DatabaseManager(self.auth_db_path)
        self.authenticated_user: Optional[Dict] = None
        self.equipment = EquipmentInterlocks(self)
        self.is_manual_mode_unlocked: bool = False

        # Timers assíncronos do ciclo
        self._cycle_timers: List[QTimer] = []

        # Mapa de intertravamento atômico para botões manuais da UI principal
        # status_esperado -> (QPushButton, QTimer)
        self._manual_pending: Dict[str, tuple] = {}

        # Diálogo Modal Manual (referência fraca)
        self._manual_dialog: Optional[ManualControlDialog] = None

        # Timer de Monitoramento de Prazo operacional da Calibração (a cada 5s)
        self._last_expired_alert_shown: bool = False
        self._calib_validity_timer = QTimer(self)
        self._calib_validity_timer.timeout.connect(self._check_calibration_validity)
        self._calib_validity_timer.start(5000)

        # Design System Windows 11 Fluent Dark
        self.apply_fluent_theme()

        # Construção da Interface
        self.init_ui()

        # Atualiza status e KPI de calibração na UI e aplica intertravamento inicial
        self._check_calibration_validity()

        self.log_message(f"Sistema Supervisório {__app_name__} v{__version__} (Build {__build__}) inicializado.")
        self.log_message("Protocolo Serial Consolidado (115200 Baud) ativo. Standby.")

    def apply_fluent_theme(self):
        qss = """
            QMainWindow, QWidget#centralWidget, QDialog, QMessageBox, QInputDialog {
                background-color: #202020;
                color: #FFFFFF;
                font-family: 'Segoe UI', Arial, sans-serif;
            }
            QFrame#cardFrame {
                background-color: #2b2b2b;
                border: 1px solid #3d3d3d;
                border-radius: 8px;
            }
            QLabel {
                color: #FFFFFF;
            }
            QPushButton {
                background-color: #333333;
                color: #FFFFFF;
                border: 1px solid #4a4a4a;
                border-radius: 6px;
                padding: 8px 14px;
                font-weight: bold;
                font-size: 11px;
            }
            QPushButton:hover {
                background-color: #404040;
                border-color: #60CDFF;
            }
            QPushButton:disabled {
                background-color: #242424;
                color: #555555;
                border: 1px solid #333333;
            }
            QComboBox {
                background-color: #2b2b2b;
                color: #FFFFFF;
                border: 1px solid #4a4a4a;
                border-radius: 6px;
                padding: 6px 12px;
                font-size: 11px;
            }
            QProgressBar {
                background-color: #202020;
                border: 1px solid #3d3d3d;
                border-radius: 6px;
                text-align: center;
                color: #FFFFFF;
                font-weight: bold;
                height: 14px;
            }
            QProgressBar::chunk {
                background: qlineargradient(x1:0, y1:0, x2:1, y2:0, stop:0 #0078D4, stop:1 #60CDFF);
                border-radius: 5px;
            }
            QTextEdit#consoleLog {
                background-color: #1a1a1a;
                border: 1px solid #333333;
                border-radius: 6px;
                color: #60CDFF;
                font-family: 'Consolas', monospace;
                font-size: 11px;
            }
            QMenuBar {
                background-color: #1a1a1a;
                color: #FFFFFF;
                border-bottom: 1px solid #333333;
                font-size: 11px;
                padding: 2px 6px;
            }
            QMenuBar::item {
                background: transparent;
                padding: 4px 10px;
                border-radius: 4px;
            }
            QMenuBar::item:selected {
                background-color: #2b2b2b;
                color: #60CDFF;
            }
            QMenu {
                background-color: #242424;
                color: #FFFFFF;
                border: 1px solid #3d3d3d;
                border-radius: 6px;
                padding: 4px;
            }
            QMenu::item {
                padding: 6px 20px;
                border-radius: 4px;
                font-size: 11px;
            }
            QMenu::item:selected {
                background-color: #0078D4;
                color: #FFFFFF;
            }
            QTabWidget::pane {
                border: 1px solid #383838;
                border-radius: 6px;
                background-color: #242424;
                top: -1px;
            }
            QTabBar::tab {
                background-color: #1f1f1f;
                color: #9CA3AF;
                border: 1px solid #383838;
                padding: 7px 14px;
                border-top-left-radius: 6px;
                border-top-right-radius: 6px;
                font-weight: bold;
                font-size: 11px;
                margin-right: 2px;
            }
            QTabBar::tab:selected {
                background-color: #242424;
                color: #60CDFF;
                border-bottom: 2px solid #0078D4;
            }
            QTabBar::tab:hover:!selected {
                background-color: #2b2b2b;
                color: #FFFFFF;
            }
        """
        self.setStyleSheet(qss)

    def _setup_serial_signals(self):
        """Auditoria e conexão estrita e única de sinais da thread serial."""
        self.serial_worker.line_received.connect(self._on_serial_line_received)
        self.serial_worker.status_received.connect(self._on_serial_status_received)
        self.serial_worker.data_received.connect(self._on_serial_data_received)
        self.serial_worker.scan_received.connect(self._on_serial_scan_received)
        self.serial_worker.connection_changed.connect(self._on_serial_connection_changed)
        self.serial_worker.error_occurred.connect(self._on_serial_error_occurred)

    # -----------------------------------------------------------------
    # BARRA DE MENUS SUPERIOR E CONTROLE DE ACESSO
    # -----------------------------------------------------------------
    def _create_menu_bar(self):
        menu_bar = self.menuBar()
        menu_sistema = menu_bar.addMenu("Sistema")
        menu_settings=menu_bar.addMenu("Configurações")
        self.act_appearance=QAction("Aparência…",self)
        self.act_appearance.triggered.connect(self.open_appearance_settings)
        menu_settings.addAction(self.act_appearance)

        # 1. Gerenciar Usuários
        act_gestao = QAction("Gerenciar Usuários", self)
        act_gestao.setStatusTip("Abrir tela de gerenciamento de usuários e controle de acesso")
        act_gestao.triggered.connect(self.open_user_management_dialog)
        menu_sistema.addAction(act_gestao)

        menu_sistema.addSeparator()

        # 2. Logout / Bloquear Painel
        act_logout = QAction("Logout / Bloquear Painel", self)
        act_logout.setStatusTip("Bloqueia as abas restritas e retorna ao modo seguro padrão")
        act_logout.triggered.connect(self.logout_action)
        menu_sistema.addAction(act_logout)

        menu_sistema.addSeparator()

        # 3. Sair
        act_sair = QAction("Sair", self)
        act_sair.setStatusTip("Fecha o supervisório com segurança")
        act_sair.triggered.connect(self.close)
        menu_sistema.addAction(act_sair)

    # -----------------------------------------------------------------
    # CONSTRUÇÃO DA INTERFACE VISUAL
    # -----------------------------------------------------------------
    def init_ui(self):
        self._create_menu_bar()
        from scada_ui import build_dashboard
        build_dashboard(self)


    def showEvent(self,event):
        super().showEvent(event)
        handle=self.windowHandle()
        if handle and not getattr(self,"_screen_tracking_ready",False):
            handle.screenChanged.connect(self._screen_changed)
            self._screen_tracking_ready=True
            self._screen_changed(handle.screen())

    def _screen_changed(self,screen):
        previous=getattr(self,"_tracked_screen",None)
        if previous:
            for signal in (previous.availableGeometryChanged,previous.logicalDotsPerInchChanged):
                try: signal.disconnect(self._fit_active_screen)
                except (TypeError,RuntimeError): pass
        self._tracked_screen=screen
        if screen:
            screen.availableGeometryChanged.connect(self._fit_active_screen)
            screen.logicalDotsPerInchChanged.connect(self._fit_active_screen)
        QTimer.singleShot(0,self._fit_active_screen)

    def _fit_active_screen(self,*args):
        screen=self.screen()
        if screen:
            area=screen.availableGeometry()
            frame_w=max(0,self.frameGeometry().width()-self.width())
            frame_h=max(0,self.frameGeometry().height()-self.height())
            max_w,max_h=max(240,area.width()-frame_w),max(200,area.height()-frame_h)
            self.setMinimumSize(min(480,max_w),min(320,max_h))
            if not self.isMaximized():
                self.resize(min(self.width(),max_w),min(self.height(),max_h))
        self._adapt_interface()

    def resizeEvent(self,event):
        super().resizeEvent(event)
        if getattr(self,"_responsive_ready",False):
            self._adapt_interface()

    def _adapt_interface(self):
        if getattr(self,"_responsive_ready",False):
            self.canvas_view.update_scale()


    def open_appearance_settings(self):
        dialog=AppearanceDialog(self.theme_manager,self)
        dialog.exec_()

    def _create_topbar(self) -> QWidget:
        top_frame = QFrame()
        top_frame.setObjectName("cardFrame")
        layout = QHBoxLayout(top_frame)
        layout.setContentsMargins(14, 8, 14, 8)
        layout.setSpacing(10)

        # Logo / Título
        app_mark = QLabel()
        app_mark.setPixmap(program_logo_pixmap(34))
        app_mark.setFixedSize(34, 34)
        app_title = QLabel(__app_name__)
        app_title.setStyleSheet("font-family: 'Bahnschrift', 'Segoe UI'; font-size: 18px; font-weight: 700; color: #38BDF8; letter-spacing: 0.8px;")
        sub_title = QLabel(f"v{__version__} (Build {__build__}) | Caracterização NIR Celulose")
        sub_title.setStyleSheet("font-family: 'Segoe UI'; font-size: 11px; color: #9CA3AF; font-weight: 400;")

        title_group = QWidget()
        title_layout = QVBoxLayout(title_group)
        title_layout.setContentsMargins(0,0,0,0)
        title_layout.setSpacing(1)
        title_layout.addWidget(app_title)
        title_layout.addWidget(sub_title)
        layout.addWidget(app_mark)
        layout.addWidget(title_group)

        # Seletor de Modo de Conexão: USB, Bluetooth SPP, Wi-Fi TCP
        lbl_mode = QLabel("Conexão:")
        lbl_mode.setStyleSheet("color: #D1D5DB; font-size: 11px; font-weight: bold;")
        self.combo_conn_mode = QComboBox()
        self.combo_conn_mode.setSizeAdjustPolicy(QComboBox.AdjustToContents)
        self.combo_conn_mode.addItem("USB", "USB")
        self.combo_conn_mode.addItem("Bluetooth", "BLUETOOTH")
        self.combo_conn_mode.addItem("Wi-Fi", "WIFI")
        self.combo_conn_mode.currentIndexChanged.connect(self._on_conn_mode_changed)

        # 1. Container Serial / Bluetooth:
        self.widget_serial = QWidget()
        serial_layout = QHBoxLayout(self.widget_serial)
        serial_layout.setContentsMargins(0, 0, 0, 0)
        serial_layout.setSpacing(6)

        lbl_com = QLabel("Porta:")
        lbl_com.setStyleSheet("color: #D1D5DB; font-size: 11px; font-weight: bold;")
        self.combo_com = QComboBox()
        self.combo_com.setSizeAdjustPolicy(QComboBox.AdjustToContents)
        self.combo_com.setMinimumWidth(85)
        self.populate_com_ports()

        self.btn_refresh_ports = QPushButton("")
        self.btn_refresh_ports.setToolTip("Atualizar lista de portas COM / Bluetooth")
        self.btn_refresh_ports.setFixedWidth(28)
        self.btn_refresh_ports.clicked.connect(self.populate_com_ports)

        lbl_baud = QLabel("Baud:")
        lbl_baud.setStyleSheet("color: #D1D5DB; font-size: 11px; font-weight: bold;")
        self.lbl_baud_val = QLabel("115200 bps")
        self.lbl_baud_val.setStyleSheet("color: #38BDF8; font-size: 11px; font-weight: bold; background-color: #1F2937; padding: 4px 6px; border-radius: 4px; border: 1px solid #374151;")
        self.lbl_baud_val.currentText = lambda: "115200"
        self.combo_baud = self.lbl_baud_val

        serial_layout.addWidget(lbl_com)
        serial_layout.addWidget(self.combo_com)
        serial_layout.addWidget(self.btn_refresh_ports)
        serial_layout.addWidget(lbl_baud)
        serial_layout.addWidget(self.combo_baud)

        # 2. Container Wi-Fi TCP:
        self.widget_wifi = QWidget()
        wifi_layout = QHBoxLayout(self.widget_wifi)
        wifi_layout.setContentsMargins(0, 0, 0, 0)
        wifi_layout.setSpacing(6)

        lbl_ip = QLabel("IP ESP32:")
        lbl_ip.setStyleSheet("color: #D1D5DB; font-size: 11px; font-weight: bold;")
        self.txt_ip = QLineEdit("192.168.4.1")
        self.txt_ip.setMinimumWidth(128)
        self.txt_ip.setMinimumHeight(36)
        self.txt_ip.setInputMethodHints(Qt.ImhFormattedNumbersOnly)
        self.txt_ip.setToolTip("Endereço IP do ESP32 (Padrão SoftAP: 192.168.4.1)")
        self.txt_ip.setStyleSheet("background-color: #2b2b2b; color: #FFFFFF; padding: 6px 8px; border: 1px solid #4a4a4a; border-radius: 7px; font-size: 13px;")

        lbl_tcp_port = QLabel("Porta:")
        lbl_tcp_port.setStyleSheet("color: #D1D5DB; font-size: 11px; font-weight: bold;")
        self.txt_tcp_port = QLineEdit("8080")
        self.txt_tcp_port.setMinimumWidth(72)
        self.txt_tcp_port.setMinimumHeight(36)
        self.txt_tcp_port.setInputMethodHints(Qt.ImhDigitsOnly)
        self.txt_tcp_port.setToolTip("Porta do Servidor TCP no ESP32")
        self.txt_tcp_port.setStyleSheet("background-color: #2b2b2b; color: #FFFFFF; padding: 6px 8px; border: 1px solid #4a4a4a; border-radius: 7px; font-size: 13px;")

        wifi_layout.addWidget(lbl_ip)
        wifi_layout.addWidget(self.txt_ip)
        wifi_layout.addWidget(lbl_tcp_port)
        wifi_layout.addWidget(self.txt_tcp_port)
        self.lbl_sim_mode = QLabel("SIMULAÇÃO")
        self.lbl_sim_mode.setStyleSheet("color: #F59E0B; font-size: 11px; font-weight: bold; padding: 4px 8px; border: 1px solid #F59E0B; border-radius: 8px;")
        self.lbl_sim_mode.setToolTip("Endereço local: o supervisório conversa com o simulador run/fake_esp32.py, não com a bancada.")
        self.lbl_sim_mode.hide()
        wifi_layout.addWidget(self.lbl_sim_mode)
        self.txt_ip.textChanged.connect(self._update_sim_indicator)
        self.widget_wifi.setVisible(False)

        # Botão [ Conectar / Desconectar ]
        self.btn_connect = QPushButton("Conectar ESP32")
        self.btn_connect.setStyleSheet("background-color: #0078D4; color: #FFFFFF; font-weight: bold; padding: 6px 14px;")
        self.btn_connect.setMinimumHeight(34)
        self.btn_connect.clicked.connect(self.toggle_com_connect)

        mode_group=QWidget()
        mode_layout=QHBoxLayout(mode_group)
        mode_layout.setContentsMargins(0,0,0,0)
        mode_layout.addWidget(lbl_mode)
        mode_layout.addWidget(self.combo_conn_mode)
        layout.addWidget(mode_group)
        layout.addWidget(self.widget_serial)
        layout.addWidget(self.widget_wifi)
        layout.addWidget(self.btn_connect)
        layout.addSpacing(10)

        # Badges de Status
        self.badge_com = ModernStatusBadge("ESP32", "#10B981", "#64748B")
        self.badge_calib = ModernStatusBadge("CALIBRAÇÃO", "#10B981", "#F59E0B")
        badge_group=QWidget()
        badge_layout=QHBoxLayout(badge_group)
        badge_layout.setContentsMargins(0,0,0,0)
        badge_layout.addWidget(self.badge_com)
        badge_layout.addWidget(self.badge_calib)
        layout.addWidget(badge_group)

        # Espaçamento elástico garantindo alinhamento perfeito à direita
        layout.addStretch(1)

        # Botão Modal de Operação Manual e Parada de Emergência Topbar
        btn_modal_manual = QPushButton("Painel Atuadores")
        btn_modal_manual.setToolTip("Abrir painel de controle manual e manutenção")
        btn_modal_manual.setMinimumHeight(34)
        btn_modal_manual.setMinimumWidth(135)
        btn_modal_manual.setSizePolicy(QSizePolicy.Minimum, QSizePolicy.Fixed)
        btn_modal_manual.clicked.connect(self.open_manual_control_dialog)
        layout.addWidget(btn_modal_manual)
        self.btn_settings=QPushButton("Configurações")
        self.btn_settings.setMinimumHeight(34)
        self.btn_settings.clicked.connect(self.open_appearance_settings)
        layout.addWidget(self.btn_settings)

        self.btn_top_emergency = QPushButton("PARADA DE EMERGÊNCIA")
        self.btn_top_emergency.setMinimumHeight(34)
        self.btn_top_emergency.setMinimumWidth(185)
        self.btn_top_emergency.setSizePolicy(QSizePolicy.Minimum, QSizePolicy.Fixed)
        self.btn_top_emergency.setStyleSheet("""
            QPushButton {
                background-color: #DC2626;
                color: #FFFFFF;
                font-weight: 800;
                font-size: 11px;
                padding: 8px 16px;
                border: none;
                border-radius: 6px;
            }
            QPushButton:hover {
                background-color: #B91C1C;
            }
        """)
        self.btn_top_emergency.clicked.connect(self.stop_cycle_action)
        layout.addWidget(self.btn_top_emergency)

        return top_frame

    def _create_kpi_bar(self) -> QWidget:
        kpi_container = QWidget()
        layout = QGridLayout(kpi_container)
        self.kpi_grid = layout
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(10)

        self.kpi_energy = PowerBiKpiCard("", "Intensidade", "0 ADC", "Soma das 6 bandas NIR", "#38BDF8")
        self.kpi_peak = PowerBiKpiCard("", "Pico espectral", "-- nm", "Comprimento dominante", "#818CF8")
        self.kpi_ratio_cel = PowerBiKpiCard("", "Razão de banda", "0.00", "R680 / R730", "#34D399")
        self.kpi_ratio_water = PowerBiKpiCard("", "Razão de espessura", "0.00", "R860 / R760", "#FBBF24")

        layout.addWidget(self.kpi_energy,0,0)
        layout.addWidget(self.kpi_peak,0,1)
        layout.addWidget(self.kpi_ratio_cel,0,2)
        layout.addWidget(self.kpi_ratio_water,0,3)

        return kpi_container

    def _create_left_control_panel(self) -> QWidget:
        panel = QFrame()
        panel.setObjectName("cardFrame")
        layout = QVBoxLayout(panel)
        layout.setContentsMargins(14, 14, 14, 14)
        layout.setSpacing(10)

        # --- PÁGINA AUTO ---
        page_auto = QWidget()
        auto_layout = QVBoxLayout(page_auto)
        auto_layout.setContentsMargins(0, 8, 0, 0)
        auto_layout.setSpacing(10)

        # Seletor de Método Analítico Operacional (Suspensão Aquosa vs. Amostra Seca)
        mode_box = QFrame()
        mode_box.setStyleSheet("""
            QFrame {
                background-color: #1E293B;
                border: 1px solid #334155;
                border-radius: 8px;
            }
        """)
        mode_box_layout = QVBoxLayout(mode_box)
        mode_box_layout.setContentsMargins(10, 8, 10, 8)
        mode_box_layout.setSpacing(4)

        lbl_op_mode = QLabel("MÉTODO ANALÍTICO OPERACIONAL:")
        lbl_op_mode.setStyleSheet("color: #38BDF8; font-size: 10px; font-weight: 800; letter-spacing: 0.5px;")
        mode_box_layout.addWidget(lbl_op_mode)

        self.combo_op_mode = QComboBox()
        self.combo_op_mode.addItem("Suspensão Aquosa (Lâmina / Água)", "umido")
        self.combo_op_mode.addItem("Amostra Seca (Reflectância Difusa)", "seco")
        self.combo_op_mode.setToolTip("Alterna calibração e equações de predição entre Suspensão Aquosa e Amostra Seca")
        self.combo_op_mode.setStyleSheet("""
            QComboBox {
                background-color: #0F172A;
                color: #F8FAFC;
                border: 1px solid #0284C7;
                border-radius: 5px;
                padding: 6px 10px;
                font-size: 11px;
                font-weight: bold;
            }
            QComboBox::drop-down {
                border: none;
            }
            QComboBox QAbstractItemView {
                background-color: #0F172A;
                color: #F8FAFC;
                selection-background-color: #0284C7;
            }
        """)
        initial_mode_idx = 1 if self.chem_engine.active_mode == "seco" else 0
        self.combo_op_mode.setCurrentIndex(initial_mode_idx)
        self.combo_op_mode.currentIndexChanged.connect(self.on_operational_mode_changed)
        mode_box_layout.addWidget(self.combo_op_mode)

        auto_layout.addWidget(mode_box)

        self.btn_start_scan = QPushButton("Iniciar Ciclo Automático")
        self.btn_start_scan.setStyleSheet("""
            QPushButton {
                background: qlineargradient(x1:0, y1:0, x2:1, y2:0, stop:0 #0078D4, stop:1 #0284C7);
                color: #FFFFFF;
                font-size: 12px;
                font-weight: bold;
                padding: 8px 12px;
                border: none;
                border-radius: 6px;
            }
            QPushButton:hover {
                background: #0284C7;
            }
        """)
        self.btn_start_scan.setMinimumHeight(34)
        self.btn_start_scan.clicked.connect(self.start_simple_auto_cycle)
        self.lbl_scan_hint = QLabel("")
        self.lbl_scan_hint.setWordWrap(True)
        self.lbl_scan_hint.setStyleSheet("color: #9CA3AF; font-size: 11px;")

        self.btn_repeatability = QPushButton("Ensaio Repetibilidade (5x Estático)")
        self.btn_repeatability.setStyleSheet("""
            QPushButton {
                background-color: #383838;
                color: #A7F3D0;
                border: 1px solid #059669;
                font-weight: bold;
                padding: 8px 11px;
                border-radius: 6px;
            }
            QPushButton:hover {
                background-color: #047857;
                color: #FFFFFF;
            }
        """)
        self.btn_repeatability.setMinimumHeight(34)
        self.btn_repeatability.clicked.connect(self.start_repeatability_test)

        self.btn_calibrate = QPushButton("Calibrar Branco e Escuro")
        self.btn_calibrate.setMinimumHeight(34)
        self.btn_calibrate.clicked.connect(self.open_calibration_dialog)

        self.btn_emergency_auto = QPushButton("Parada de Emergência")
        self.btn_emergency_auto.setStyleSheet("""
            QPushButton {
                background-color: #3A1D1D;
                color: #EF4444;
                border: 1px solid #EF4444;
                font-weight: bold;
                padding: 8px 10px;
                border-radius: 6px;
            }
            QPushButton:hover {
                background-color: #DC2626;
                color: #FFFFFF;
            }
        """)
        self.btn_emergency_auto.setMinimumHeight(34)
        self.btn_emergency_auto.clicked.connect(self.stop_cycle_action)

        auto_layout.addWidget(self.btn_start_scan)
        auto_layout.addWidget(self.btn_repeatability)
        auto_layout.addWidget(self.btn_calibrate)
        auto_layout.addWidget(self.lbl_scan_hint)
        auto_layout.addWidget(self.btn_emergency_auto)
        auto_layout.addStretch()

        # --- PÁGINA MANUAL (DESACOPLAMENTO ATÔMICO) ---
        page_manual = QWidget()
        manual_layout = QVBoxLayout(page_manual)
        manual_layout.setContentsMargins(0, 8, 0, 0)
        manual_layout.setSpacing(8)

        # Gaveta
        card_d = QFrame()
        card_d.setStyleSheet("background-color: #242424; border: 1px solid #383838; border-radius: 6px;")
        cd_layout = QVBoxLayout(card_d)
        cd_layout.setContentsMargins(8, 6, 8, 6)
        cd_layout.setSpacing(6)
        cd_layout.addWidget(QLabel("GAVETA DE AMOSTRAS"))

        self.btn_man_open_drawer = QPushButton("Abrir Gaveta")
        self.btn_man_open_drawer.setMinimumHeight(34)
        self.btn_man_open_drawer.clicked.connect(lambda: self._execute_atomic_manual_button(
            self.btn_man_open_drawer, "CMD:ABRIR_GAVETA", "GAVETA_ABERTA", "Abrindo gaveta..."
        ))

        self.btn_man_close_drawer = QPushButton("Fechar Gaveta")
        self.btn_man_close_drawer.setMinimumHeight(34)
        self.btn_man_close_drawer.clicked.connect(lambda: self._execute_atomic_manual_button(
            self.btn_man_close_drawer, "CMD:FECHAR_GAVETA", "GAVETA_FECHADA", "Fechando gaveta..."
        ))
        cd_layout.addWidget(self.btn_man_open_drawer)
        cd_layout.addWidget(self.btn_man_close_drawer)
        manual_layout.addWidget(card_d)

        card_p = QFrame()
        card_p.setObjectName("cardFrame")
        cp_layout = QHBoxLayout(card_p)
        self.btn_man_open_door = QPushButton("Abrir Porta")
        self.btn_man_close_door = QPushButton("Fechar Porta")
        for button, cmd, expected, desc in (
            (self.btn_man_open_door, "CMD:ABRIR_PORTA", "PORTA_ABERTA", "Abrindo porta..."),
            (self.btn_man_close_door, "CMD:FECHAR_PORTA", "PORTA_FECHADA", "Fechando porta..."),
        ):
            button.setMinimumHeight(34)
            button.clicked.connect(lambda checked=False, b=button, c=cmd, e=expected, d=desc:
                                   self._execute_atomic_manual_button(b, c, e, d))
            cp_layout.addWidget(button)
        manual_layout.insertWidget(0, card_p)

        # Sensor
        card_s = QFrame()
        card_s.setStyleSheet("background-color: #242424; border: 1px solid #383838; border-radius: 6px;")
        cs_layout = QVBoxLayout(card_s)
        cs_layout.setContentsMargins(8, 6, 8, 6)
        cs_layout.setSpacing(6)
        cs_layout.addWidget(QLabel("CARRINHO DO SENSOR NIR"))

        self.btn_man_fwd_sensor = QPushButton("Avançar Sensor")
        self.btn_man_fwd_sensor.setMinimumHeight(34)
        self.btn_man_fwd_sensor.clicked.connect(lambda: self._execute_atomic_manual_button(
            self.btn_man_fwd_sensor, "CMD:AVANCAR_SENSOR", "SENSOR_AVANCADO", "Avançando sensor..."
        ))

        self.btn_man_back_sensor = QPushButton("Recuar Sensor")
        self.btn_man_back_sensor.setMinimumHeight(34)
        self.btn_man_back_sensor.clicked.connect(lambda: self._execute_atomic_manual_button(
            self.btn_man_back_sensor, "CMD:RECUAR_SENSOR", "SENSOR_RECUADO", "Recuando sensor..."
        ))
        cs_layout.addWidget(self.btn_man_fwd_sensor)
        cs_layout.addWidget(self.btn_man_back_sensor)
        manual_layout.addWidget(card_s)

        # Disparo Único
        self.btn_man_read = QPushButton("Disparo Único")
        self.btn_man_read.setStyleSheet("background-color: #0284C7; font-weight: bold; padding: 8px;")
        self.btn_man_read.setMinimumHeight(34)
        self.btn_man_read.clicked.connect(lambda: self._execute_atomic_manual_button(
            self.btn_man_read, "CMD:LER_ESPECTRO", "LEITURA_CONCLUIDA", "Executando disparo óptico..."
        ))
        manual_layout.addWidget(self.btn_man_read)
        manual_layout.addStretch()

        # QTabWidget com Abas [ Ensaios Automáticos ] e [ Modo Manual ] (Protegido por Autenticação)
        self.control_tabs = QTabWidget()
        self.control_tabs.addTab(page_auto, "Ensaios Automáticos")
        self.control_tabs.addTab(page_manual, "Modo Manual")
        self.control_tabs.currentChanged.connect(self._on_control_tab_changed)
        layout.addWidget(self.control_tabs)

        # Alias para compatibilidade
        self.control_stack = self.control_tabs

        housing_card = QFrame()
        self.card_housing = housing_card
        housing_card.setObjectName("cardFrame")
        housing_layout = QVBoxLayout(housing_card)
        housing_layout.setContentsMargins(8, 4, 8, 4)
        self.lbl_housing_state = QLabel("Carcaça: sem confirmação")
        self.lbl_housing_state.setWordWrap(True)
        self.lbl_door_state = QLabel("Porta: sem confirmação")
        self.lbl_carriage_state = QLabel("Carrinho: sem confirmação")
        housing_layout.addWidget(self.lbl_housing_state)
        housing_layout.addWidget(self.lbl_door_state)
        housing_layout.addWidget(self.lbl_carriage_state)
        layout.addWidget(housing_card)

        # Card de Identificação de Amostra / Laudo Quimiométrico
        # Card de Identificação e Caracterização Quantitativa (Número Kappa)
        self.card_resultado = QFrame()
        self.card_resultado.setStyleSheet("background-color: #242424; border: 1px solid #383838; border-radius: 6px;")
        res_layout = QVBoxLayout(self.card_resultado)
        res_layout.setContentsMargins(10, 8, 10, 8)
        res_layout.setSpacing(3)

        lbl_res_header = QLabel("KAPPA DEMONSTRATIVO — MODELO EXPERIMENTAL")
        lbl_res_header.setWordWrap(True)
        lbl_res_header.setStyleSheet("color: #9CA3AF; font-size: 9px; font-weight: bold; letter-spacing: 0.5px;")

        self.lbl_kappa_valor = QLabel("--")
        self.lbl_kappa_valor.setStyleSheet("color: #C084FC; font-size: 30px; font-weight: 600;")
        self.lbl_kappa_laudo = self.lbl_kappa_valor  # Alias de compatibilidade

        self.lbl_kappa_classificacao = QLabel("Standby (Aguardando Leitura)")
        self.lbl_kappa_classificacao.setStyleSheet("color: #9CA3AF; font-size: 11px; font-weight: bold;")
        self.lbl_kappa_status = self.lbl_kappa_classificacao  # Alias de compatibilidade

        self.lbl_metodo_info = QLabel("Método: Amostra Seca (Reflectância Difusa)")
        self.lbl_metodo_info.setStyleSheet("color: #6B7280; font-size: 10px;")

        res_layout.addWidget(lbl_res_header)
        res_layout.addWidget(self.lbl_kappa_valor)
        res_layout.addWidget(self.lbl_kappa_classificacao)
        res_layout.addWidget(self.lbl_metodo_info)
        layout.addWidget(self.card_resultado)

        # Ações do Sistema (Histórico de Ensaios / PDF / CSV)
        actions_layout = QHBoxLayout()
        self.btn_history = QPushButton("Histórico de Ensaios")
        self.btn_history.setToolTip("Gerenciador completo de histórico de ensaios espectrais")
        self.btn_history.setMinimumHeight(34)
        self.btn_history.clicked.connect(self.open_history_dialog)
        self.btn_db = self.btn_history  # alias para retrocompatibilidade

        self.btn_pdf = QPushButton("Relatório PDF")
        self.btn_pdf.setMinimumHeight(34)
        self.btn_pdf.clicked.connect(self.export_pdf_report)

        self.btn_csv = QPushButton("Exportar CSV")
        self.btn_csv.setMinimumHeight(34)
        self.btn_csv.clicked.connect(self.export_csv_log)

        actions_layout.addWidget(self.btn_history)
        actions_layout.addWidget(self.btn_pdf)
        actions_layout.addWidget(self.btn_csv)
        layout.addLayout(actions_layout)

        return panel

    def _create_right_chart_panel(self) -> QWidget:
        container = QWidget()
        layout = QVBoxLayout(container)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(8)

        # 1. Gráfico Espectral Spline Cúbica (Catmull-Rom) ocupando a área superior
        self.spectral_chart = SpectralSplineChartWidget()
        self.spectral_chart.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Expanding)
        layout.addWidget(self.spectral_chart, stretch=1)

        # 2. Reorganização do layout abaixo do gráfico: dois cards compactos lado a lado
        bottom_cards_layout = QGridLayout()
        self.diagnostic_grid = bottom_cards_layout
        bottom_cards_layout.setContentsMargins(0, 0, 0, 0)
        bottom_cards_layout.setSpacing(10)

        # À ESQUERDA: Card existente com os Dados de Calibração (Status, RMS/R², Perfil Ativo, etc.)
        self.card_calibracao = CardKpiCalibracao(self)
        self.card_calibracao.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Preferred)
        bottom_cards_layout.addWidget(self.card_calibracao,0,0)

        # À DIREITA: Novo Card de Diagnóstico & Telemetria do Sensor AS7263
        self.card_telemetria = CardDiagnosticoAS7263(self)
        self.card_telemetria.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Preferred)
        bottom_cards_layout.addWidget(self.card_telemetria,0,1)

        # Aliases diretos na janela principal aos widgets do card de telemetria
        self.lbl_die_temp = self.card_telemetria.lbl_die_temp
        self.lbl_ganho = self.card_telemetria.lbl_ganho
        self.lbl_integracao = self.card_telemetria.lbl_integracao
        self.lbl_driver_led = self.card_telemetria.lbl_driver_led
        self.lbl_hardware = self.card_telemetria.lbl_hardware
        self.lbl_status_sensor = self.card_telemetria.lbl_status_sensor

        layout.addLayout(bottom_cards_layout)

        # Gráfico de dispersão 2D removido da tela principal conforme solicitado
        self.scatter_plot = None

        return container

    def _create_footer(self) -> QWidget:
        footer = QFrame()
        footer.setObjectName("cardFrame")
        layout = QVBoxLayout(footer)
        layout.setContentsMargins(12, 8, 12, 8)
        layout.setSpacing(6)

        status_row = QHBoxLayout()
        self.lbl_cycle_status = QLabel("Status do Ciclo: Sistema em Standby. Aguardando comando.")
        self.lbl_cycle_status.setStyleSheet("color: #D1D5DB; font-size: 11px; font-weight: bold;")

        self.cycle_progress = QProgressBar()
        self.cycle_progress.setValue(0)
        self.cycle_progress.setMinimumWidth(160)
        self.cycle_progress.setMaximumWidth(240)

        status_row.addWidget(self.lbl_cycle_status,stretch=1)
        status_row.addWidget(self.cycle_progress)
        layout.addLayout(status_row)

        # Console de log retrátil
        self.txt_console = QTextEdit()
        self.txt_console.setObjectName("consoleLog")
        self.txt_console.setReadOnly(True)
        self.txt_console.setFixedHeight(75)
        layout.addWidget(self.txt_console)

        return footer

    # -----------------------------------------------------------------
    # MODO DE OPERAÇÃO (AUTO vs MANUAL)
    # -----------------------------------------------------------------
    def switch_mode(self, mode: str):
        if mode == "AUTO":
            self.btn_mode_auto.setChecked(True)
            self.btn_mode_manual.setChecked(False)
            self.control_stack.setCurrentIndex(0)
            self.log_message("Modo alterado para [ AUTOMÁTICO ]")
        else:
            self.btn_mode_auto.setChecked(False)
            self.btn_mode_manual.setChecked(True)
            self.control_stack.setCurrentIndex(1)
            self.log_message("Modo alterado para [ MANUAL ATÔMICO ]")

    # -----------------------------------------------------------------
    # GESTÃO DA CONEXÃO SERIAL REAL
    # -----------------------------------------------------------------
    def log_message(self, text: str):
        now_str = datetime.datetime.now().strftime("[%H:%M:%S]")
        try:
            print(f"{now_str} {text}", flush=True)
        except Exception:
            try:
                safe_text = text.encode("ascii", errors="replace").decode("ascii")
                print(f"{now_str} {safe_text}", flush=True)
            except Exception:
                pass
        if hasattr(self, "txt_console") and self.txt_console is not None:
            self.txt_console.append(f"{now_str} {text}")

    def _on_conn_mode_changed(self):
        mode = self.combo_conn_mode.currentData()
        if mode in ("USB", "BLUETOOTH"):
            self.widget_serial.setVisible(True)
            self.widget_wifi.setVisible(False)
            if mode == "BLUETOOTH":
                self.log_message("[CONEXÃO] Modo selecionado: Bluetooth SPP Serial (Porta COM virtual pareada).")
            else:
                self.log_message("[CONEXÃO] Modo selecionado: Cabo USB Serial.")
        else:
            self.widget_serial.setVisible(False)
            self.widget_wifi.setVisible(True)
            self.log_message("[CONEXÃO] Modo selecionado: Wi-Fi TCP/IP (Padrão ESP32 SoftAP: 192.168.4.1:8080).")

    def on_operational_mode_changed(self,index):
        new_mode=self.combo_op_mode.currentData()
        if not new_mode or new_mode==self.chem_engine.active_mode:
            return
        if self.fsm_state!="IDLE" or not self.chem_engine.set_mode(new_mode):
            self.combo_op_mode.blockSignals(True)
            self.combo_op_mode.setCurrentIndex(self.combo_op_mode.findData(self.chem_engine.active_mode))
            self.combo_op_mode.blockSignals(False)
            self.log_message("[MÉTODO] Mudança recusada: rotina ativa ou falha ao salvar.")
            return
        self._result_valid=False
        self.current_scan_data=[0.0]*6
        self.lbl_kappa_valor.setText("--")
        self._check_calibration_validity()

    def populate_com_ports(self):
        self.combo_com.clear()
        ports = self.serial_worker.list_ports()
        for device, desc in ports:
            self.combo_com.addItem(f"{device} ({desc})", device)

        if self.combo_com.count() == 0:
            self.combo_com.addItem("Nenhuma Porta Detectada", "")
        self.log_message(f"Varredura de portas: {self.combo_com.count()} encontrada(s).")

    def disconnect_hardware(self):
        """Encerra a conexão voluntária com o ESP32 de forma limpa."""
        if self.serial_worker.is_connected():
            self.log_message("[CONEXÃO] Encerrando conexão com o ESP32...")
            self.serial_worker.disconnect_connection()

    SIMULATION_HOSTS = ("127.0.0.1", "localhost", "::1")

    def is_simulation_target(self) -> bool:
        """True quando a conexão Wi-Fi aponta para este computador (simulador run/fake_esp32.py)."""
        if not hasattr(self, "txt_ip") or not hasattr(self, "combo_conn_mode"):
            return False
        return self.combo_conn_mode.currentData() == "WIFI" and self.txt_ip.text().strip().lower() in self.SIMULATION_HOSTS

    def _update_sim_indicator(self, *_):
        if hasattr(self, "lbl_sim_mode"):
            self.lbl_sim_mode.setVisible(self.is_simulation_target())

    def toggle_com_connect(self):
        if self.serial_worker.is_connected():
            self.disconnect_hardware()
            return
        # Feedback imediato: a conexão por Wi-Fi pode levar alguns segundos e a interface não pode parecer parada.
        self._connect_attempt = True
        self.btn_connect.setText("Conectando…")
        self.btn_connect.setEnabled(False)
        QApplication.processEvents()
        try:
            self._start_connection()
        finally:
            self._connect_attempt = False
            self.btn_connect.setEnabled(True)
            if not self.serial_worker.is_connected():
                self.btn_connect.setText("Conectar ESP32")

    def _start_connection(self):
        mode = self.combo_conn_mode.currentData() if hasattr(self, "combo_conn_mode") else "USB"
        if mode in ("USB", "BLUETOOTH"):
            port_name = self.combo_com.currentData()
            if not port_name:
                QMessageBox.warning(self, "Porta Inválida", f"Nenhuma porta selecionada para o modo {mode}.")
                return
            baudrate = int(self.combo_baud.currentText()) if hasattr(self, "combo_baud") else 115200
            self.serial_worker.connect_serial(port_name, baudrate, mode=mode)
        elif mode == "WIFI":
            ip = self.txt_ip.text().strip()
            port_str = self.txt_tcp_port.text().strip()
            if not ip:
                QMessageBox.warning(self, "IP Inválido", "Informe o endereço IP do ESP32 (ex: 192.168.4.1).")
                return
            try:
                port = int(port_str)
            except ValueError:
                QMessageBox.warning(self, "Porta Inválida", "A porta TCP deve ser um número inteiro (ex: 8080).")
                return
            if self.is_simulation_target():
                self.log_message(f"[SIMULAÇÃO] Conectando ao simulador em {ip}:{port}. Os dados são de teste, não da bancada.")
            self.serial_worker.connect_tcp(ip, port)

    def _explain_connection_failure(self, message):
        """Diz ao operador por que a conexão falhou e o que conferir (antes, só aparecia 'Desconectado')."""
        mode = self.combo_conn_mode.currentData() if hasattr(self, "combo_conn_mode") else "USB"
        if mode == "WIFI":
            hint = ("Confira:<br>1. O computador está na rede Wi-Fi do ESP32 (padrão 192.168.4.1, porta 8080).<br>"
                    "2. O IP e a porta estão corretos.<br>"
                    "3. No Codespaces, o simulador está ativo (<b>bash run/start_app.sh</b>) e o IP é 127.0.0.1.")
        else:
            hint = "Confira o cabo, a porta selecionada e se outro programa (monitor serial) não a está usando."
        QMessageBox.warning(self, "Falha na conexão", f"<b>Não foi possível conectar ao ESP32.</b><br><br>{message}<br><br>{hint}")

    def is_serial_connected(self) -> bool:
        return self.serial_worker.is_connected()

    def check_hardware_connected(self) -> bool:
        if not self.is_serial_connected():
            mode = self.combo_conn_mode.currentData() if hasattr(self, "combo_conn_mode") else "USB"
            if mode == "WIFI":
                instrucao = "1. Conecte o computador à rede Wi-Fi do ESP32.<br>2. Verifique o IP/Porta e clique em <b>'Conectar ESP32'</b>."
            else:
                instrucao = f"1. Conecte o dispositivo via {mode}.<br>2. Selecione a porta e clique em <b>'Conectar ESP32'</b>."

            QMessageBox.warning(
                self,
                "Hardware Desconectado",
                f"<b>ANALISADOR ESPECTROMÉTRICO DESCONECTADO</b><br><br>{instrucao}"
            )
            return False
        return True

    def send_serial_command(self,cmd,priority=False,manual=False):
        if manual and (not self.is_manual_mode_unlocked or not self.authenticated_user):
            self.log_message("[ACESSO] Comando manual bloqueado: autentique no painel.")
            return False
        gated = self.equipment.prepare(cmd, manual=manual)
        if gated is not None:
            return gated
        if cmd in ("CMD:LER_ESPECTRO","CMD:LER_ESCURO"):
            if not self._protocol_ready or not self._sensor_ready or self._batch is not None:
                self._fail_operation("Firmware incompatível, sensor ausente ou aquisição já em curso.")
                return False
            if not self.is_calibrating_white and not self.chem_engine.calibration_valid():
                self._fail_operation(self.chem_engine.last_error)
                return False
            self._last_raw_payload=[]
            self._result_valid=False
            count=10 if self.is_calibrating_white else (1 if self.modo_repetibilidade else 5)
            if not self.is_calibrating_white and self.fsm_state=="IDLE":
                self._current_sample_id=(self.input_sample_id.text().strip() if hasattr(self,"input_sample_id") else "") or "AM-"+uuid.uuid4().hex[:8].upper()
            self._batch={"cmd":cmd,"target":count,"scans":[],"token":"","data":None}
            self._dispatch_batch_read()
            return self._batch is not None
        wire_command = "CMD:MANUAL:" + cmd[4:] if manual and cmd in self.equipment.EXPECTED else cmd
        ok=self.serial_worker.send_command(wire_command,priority=priority)
        if ok and cmd in self.equipment.EXPECTED:
            self.equipment.expected_motion = self.equipment.EXPECTED[cmd]
            self.equipment.manual_motion = manual
        if ok and cmd in ("CMD:ABRIR_PORTA","CMD:FECHAR_PORTA","CMD:ABRIR_GAVETA","CMD:FECHAR_GAVETA","CMD:AVANCAR_SENSOR","CMD:RECUAR_SENSOR"):
            if cmd in ("CMD:ABRIR_PORTA", "CMD:FECHAR_PORTA", "CMD:AVANCAR_SENSOR", "CMD:RECUAR_SENSOR"):
                self._hardware_watchdog.stop()
                for _, timer in self._manual_pending.values():
                    timer.stop()
            else:
                self._hardware_watchdog.start(12000)
                for _, timer in self._manual_pending.values():
                    timer.start(30000)
        elif not ok:
            self._fail_operation("Comando não enviado: conexão indisponível.",send_stop=False)
        return ok

    def _on_serial_connection_changed(self, connected: bool, message: str):
        self.equipment.reset()
        self.equipment.refresh_indicator()
        self._last_pong=time.monotonic()
        self._last_diag_request=0.0
        self._protocol_ready=False
        self._sensor_ready=False
        self._result_valid=False
        if not connected:
            self._operation_epoch += 1
        if not connected and (self.fsm_state!="IDLE" or self._manual_pending or self._batch):
            self._fail_operation("Conexão perdida durante a operação.",send_stop=False)
        if connected:
            self.combo_conn_mode.setEnabled(False)
            self.badge_com.set_active(True, f"CONECTADO ({message})")
            self.btn_connect.setText("Desconectar")
            self.btn_connect.setStyleSheet("background-color: #383838; color: #EF4444; border: 1px solid #4a4a4a; font-weight: bold; padding: 6px 14px;")
            self.lbl_cycle_status.setText(f"Status do Ciclo: Hardware conectado ({message}). Pronto.")
            self.log_message(f"Hardware ESP32 conectado: {message}.")
            self.serial_worker.send_command("CMD:ESTADO_PORTA")
        else:
            self.combo_conn_mode.setEnabled(True)
            self.badge_com.set_active(False, "DESCONECTADO")
            self.btn_connect.setText("Conectar ESP32")
            self.btn_connect.setStyleSheet("background-color: #0078D4; color: #FFFFFF; border: none; font-weight: bold; padding: 6px 14px;")
            self.lbl_cycle_status.setText("Status do Ciclo: Hardware desconectado.")
            self.log_message(f"Hardware ESP32 desconectado: {message}")
            if getattr(self, "_connect_attempt", False) and message and message != "Desconectado":
                self.lbl_cycle_status.setText("Status do Ciclo: Falha ao conectar. Veja a mensagem.")
                QTimer.singleShot(0, lambda m=message: self._explain_connection_failure(m))

        self.card_telemetria.reset("Aguardando telemetria" if connected else "Desconectado")
        self.card_esp32.refresh(self)
        self._refresh_controls()
        if self._manual_dialog:
            self._manual_dialog.update_interlocks_and_leds()

    def _on_serial_error_occurred(self,err):
        self.log_message("[ERRO DE COMUNICAÇÃO] "+err)
        if self.fsm_state!="IDLE" or self._batch or self._manual_pending:
            self._fail_operation(err)

    def _on_serial_line_received(self, line: str):
        # Exibe em log
        self.log_message(f"← {line}")
        if not self.equipment.update(line):
            self._handle_telemetry_line(line)

    def _handle_telemetry_line(self, line: str):
        """Configuração, valores recebidos e medições calculadas permanecem distintos."""
        card=getattr(self,"card_telemetria",None)
        if card is None:return
        text=line.strip();data={}
        if text.startswith("ESPDIAG:"):
            fields=dict(part.split(":",1) for part in text[8:].split("|") if ":" in part)
            self.card_esp32.update_telemetry(fields)
            return
        if text.startswith("DIAG:"):
            for i,part in enumerate(text[5:].split("|")):
                if ":" in part:
                    key,value=part.split(":",1);data[key.upper()]=value
                elif i==0:data["TEMP"]=part
        elif text.startswith("TELEM:"):
            for part in text[6:].replace(",",";").split(";"):
                sep="=" if "=" in part else ":"
                if sep in part:
                    key,value=part.split(sep,1);data[key.upper()]=value
        elif text.startswith("{"):
            try:
                parsed=json.loads(text)
                if isinstance(parsed,dict):data={k.upper():v for k,v in parsed.items()}
            except (ValueError,TypeError):return
        if not data:return
        def value(*keys):
            return next((data[key] for key in keys if key in data),None)
        status=value("STATUS","STATE","SENSOR_STATUS")
        if str(status).upper() in ("ERRO","ERROR","FAIL"):
            card.reset("Erro reportado pelo sensor");return
        card.atualizar_telemetria(die_temp=value("TEMP","DIE_TEMP","TEMPERATURA"),
            gain=value("GAINCFG","GAIN","PGA_GAIN"),integration=value("INTCFG","INT","INTEGRATION"),
            led=value("LEDCFG","LED_CURRENT","LED"),led_state=value("LEDSTATE","LED_STATE"),
            hw_id=value("HW","HARDWARE"),status=status,saturation=value("SAT","SATURACAO","SATURATION"),received=True)
        if "LEDCFG" not in data and "LEDSTATE" not in data and str(data.get("LED","")).upper() not in ("ON","OFF","LIGADO","DESLIGADO"):
            card.lbl_led_state.setText("Não informado")

    def _execute_atomic_manual_button(self, button: QPushButton, cmd_str: str, expected_status: str, desc: str):
        """
        Emite exclusivamente o comando serial correspondente e desabilita seu clique
        até receber a resposta de confirmação correspondente.
        """
        if not self.is_manual_mode_unlocked or not self.authenticated_user:
            self.log_message("[ACESSO] Controle manual bloqueado: autentique no painel.")
            return
        if not self.check_hardware_connected():
            return

        if self.equipment.pending or self.fsm_state!="IDLE" or self._manual_pending or self._batch:
            return
        if cmd_str=="CMD:LER_ESPECTRO" and not self._ready_for_scan():
            return
        button.setEnabled(False)
        self.lbl_cycle_status.setText(f"Status: {desc} (Aguardando STATUS:{expected_status})")

        # Watchdog por segurança
        watchdog = QTimer(self)
        watchdog.setSingleShot(True)
        watchdog.timeout.connect(lambda: self._on_atomic_watchdog_timeout(button, expected_status))
        watchdog.start(30000)

        self._manual_pending[expected_status] = (button, watchdog)
        self.send_serial_command(cmd_str, manual=True)
        self._refresh_controls()

    def _create_placement_confirmation(self):
        return SamplePlacementInterlockDialog(
            title="Confirmar antes de fechar a gaveta",
            message="Confirme que a amostra está posicionada corretamente ou que o berço está vazio, "
                    "conforme a operação. Retire as mãos do mecanismo antes de continuar.", parent=self)

    def _cancel_equipment_request(self, message):
        self.equipment.cancel()
        self._hardware_watchdog.stop()
        self._clear_cycle_timers()
        self._batch = None
        self._acquisition_timer.stop()
        for _, timer in self._manual_pending.values():
            timer.stop()
        self._manual_pending.clear()
        self.auto_cycle_active = self.modo_repetibilidade = self.is_calibrating_white = False
        self._pending_routine = None
        self.fsm_state = "IDLE"
        self._hide_drawer_alert()
        self._hide_radiation_alert()
        self.lbl_cycle_status.setText(message)
        self.log_message(message)
        if self._manual_dialog:
            self._manual_dialog.log(message)
        self._refresh_controls()

    def _on_atomic_watchdog_timeout(self,button,expected_status):
        self._fail_operation("Comando manual sem confirmação: "+expected_status)

    # -----------------------------------------------------------------
    # PROCESSAMENTO DE TELEMETRIA E MÁQUINA DE ESTADOS (FSM)
    # -----------------------------------------------------------------
    def _on_serial_data_received(self,values):
        self.log_message("[AQUISIÇÃO] DATA sem identificador descartado; atualizar firmware.")

    def _on_serial_status_received(self, status_tag: str, _verified=False):
        """
        Tratamento centralizado de STATUS:* para Máquina de Estados e Desacoplamento Atômico.
        """
        self.log_message(f"[STATUS RX]: {status_tag}")
        # Comunicação continua sendo monitorada mesmo durante falha/emergência.
        if status_tag == "PONG":
            self._last_pong = time.monotonic()
            return
        if self.fsm_state not in ("FALHA", "EMERGENCIA") and self.equipment.on_status(status_tag, verified=_verified):
            return
        if status_tag=="PROTOCOLO_2":
            self._protocol_ready=True
            self._refresh_controls()
            return
        if status_tag=="SENSOR_OK":
            self._sensor_ready=True
            self._refresh_controls()
        if status_tag.startswith("SENSOR_ERRO"):
            self._sensor_ready = False
            optical_routine = (self.auto_cycle_active or self.is_calibrating_white or self.modo_repetibilidade
                               or self._pending_routine in ("AUTO", "REPETIBILIDADE", "CALIB_BRANCO", "CALIBRAÇÃO"))
            active = (self._batch is not None or "LEITURA_CONCLUIDA" in self._manual_pending
                      or (optical_routine and self.fsm_state not in ("FALHA", "EMERGENCIA")))
            if active:
                self._fail_operation(status_tag)
            else:
                self._refresh_controls()
                if self.fsm_state == "IDLE":
                    self.lbl_cycle_status.setText("ESP32 conectado; sensor espectral indisponível. Verifique a ligação I2C.")
            return
        if status_tag.startswith(("SENSOR_ERRO","LEITURA_ERRO","COMANDO_ERRO","PORTA_ERRO","CARRINHO_ERRO")):
            if status_tag.startswith("SENSOR_ERRO"):
                self._sensor_ready=False
            self._fail_operation(status_tag)
            return
        if status_tag.startswith("LEITURA_CONCLUIDA:"):
            self._complete_batch_read(status_tag.split(":",1)[1])
            return
        if status_tag=="LEITURA_CONCLUIDA" and not _verified:
            self.log_message("[AQUISIÇÃO] Conclusão sem identificador descartada.")
            return
        if self.fsm_state in ("FALHA","EMERGENCIA") and status_tag!="EMERGENCIA_ACIONADA":
            return
        if status_tag in ("PORTA_ABERTA","PORTA_FECHADA","GAVETA_ABERTA","GAVETA_FECHADA","SENSOR_AVANCADO","SENSOR_RECUADO","EMERGENCIA_ACIONADA"):
            self._hardware_watchdog.stop()


        # 1. Propaga para o modal manual, se aberto
        if self._manual_dialog:
            self._manual_dialog.on_status_received(status_tag)

        # 2. Libera botões manuais da UI principal que aguardavam este status
        if status_tag in self._manual_pending:
            button, watchdog = self._manual_pending.pop(status_tag)
            try:
                watchdog.stop()
            except Exception:
                pass
            self._refresh_controls()
            self.lbl_cycle_status.setText(f"Status: Ação confirmada ({status_tag}). Pronto.")

        if status_tag in ("SENSOR_OK", "PRONTO"):
            self.log_message("Handshake ESP32 validado com sucesso!")
            if hasattr(self, "card_telemetria") and self.card_telemetria is not None:
                self.card_telemetria.atualizar_telemetria(status="Sensor inicializado")
            return

        # 4. Tratamento de Emergência Acionada no Hardware
        if status_tag == "EMERGENCIA_ACIONADA":
            self._handle_emergency_confirmed()
            return

        # 4.1 Alerta Mecânico de Gaveta: Fechamento automático ao atingir fim de curso
        if status_tag in ("GAVETA_ABERTA", "GAVETA_FECHADA"):
            self._hide_drawer_alert()

        # 4.2 Alerta Mecânico de Gaveta: Abertura automática ao receber telemetria de movimentação
        if status_tag in ("ABRINDO_GAVETA", "FECHANDO_GAVETA"):
            if self.is_in_automated_routine():
                desc = "ABERTURA DE GAVETA EM ANDAMENTO" if status_tag == "ABRINDO_GAVETA" else "FECHAMENTO DE GAVETA EM ANDAMENTO"
                msg = "Abrindo gaveta motorizada..." if status_tag == "ABRINDO_GAVETA" else "Fechando gaveta motorizada..."
                self._show_drawer_alert(msg, desc)
            return

        # 5. Intertravamento Humano: Confirmação de Gaveta Aberta
        if status_tag == "GAVETA_ABERTA":
            if self.fsm_state == "PREP_ABRINDO_GAVETA":
                self._handle_interlock_popup()
                return
            elif self.fsm_state == "CALIB_ETAPA1_ABRINDO_GAVETA":
                self._handle_calib_transition_popups()
                return

        # 6. Intertravamento Humano / Conclusão de Ensaio: Gaveta Fechada
        if status_tag == "GAVETA_FECHADA" and self.fsm_state in ("CANCELANDO_FECHANDO_GAVETA", "CALIB_CANCELANDO_FECHANDO_GAVETA", "CONCLUSAO_FECHANDO_GAVETA"):
            is_completion = (self.fsm_state == "CONCLUSAO_FECHANDO_GAVETA")
            self.fsm_state = "IDLE"
            self._pending_routine = None
            self.auto_cycle_active = False
            self.modo_repetibilidade = False
            self.is_calibrating_white = False
            self.cycle_progress.setValue(100 if is_completion else 0)
            self._enable_controls()
            if is_completion:
                self.lbl_cycle_status.setText("Status: Ensaio finalizado. Bancada em repouso seguro e sistema pronto.")
                self.lbl_cycle_status.setStyleSheet("color: #10B981; font-size: 11px; font-weight: bold;")
                self.log_message("[CONCLUSÃO] Gaveta fechada em segurança. Bancada em repouso.")
            else:
                self.lbl_cycle_status.setText("Status: Ensaio cancelado pelo operador. Gaveta fechada e sistema pronto.")
                self.log_message("[CANCELADO] Gaveta fechada em segurança. Sistema liberado.")
            return

        # 7. MÁQUINA DE ESTADOS: CALIBRAÇÃO SEQUENCIAL (BRANCO -> ESCURO)
        if self.is_calibrating_white:
            self._handle_white_calibration_fsm(status_tag)
            return

        # 8. MÁQUINA DE ESTADOS: CICLO AUTOMÁTICO SIMPLES
        if self.auto_cycle_active:
            self._handle_auto_cycle_fsm(status_tag)
            return

        # 9. MÁQUINA DE ESTADOS: TESTE DE REPETIBILIDADE (5x ESTÁTICO)
        if self.modo_repetibilidade:
            self._handle_repeatability_fsm(status_tag)
            return

        # 10. Disparo manual fora de ciclos automáticos
        if status_tag == "LEITURA_CONCLUIDA" and self._last_raw_payload:
            self.process_raw_spectral_data(self._last_raw_payload)

    # -----------------------------------------------------------------
    # FASE 2: INTERTRAVAMENTO HUMANO (POPUP DE SEGURANÇA E CONFIRMAÇÃO)
    # -----------------------------------------------------------------
    def _handle_interlock_popup(self):
        """
        Exibida SOMENTE APÓS receber STATUS:GAVETA_ABERTA da Fase 1.
        Garante que o Python NUNCA envie CMD:FECHAR_GAVETA antes do OK do operador.
        """
        self.fsm_state = "AGUARDANDO_POPUP"
        pending_routine = self._pending_routine
        popup_epoch = self._operation_epoch
        self.lbl_cycle_status.setText("Status: Gaveta aberta. Aguardando posicionamento e confirmação do operador...")
        self.log_message("[INTERTRAVAMENTO] Gaveta aberta. Exibindo popup de confirmação de amostra...")

        is_dry = (self.chem_engine.active_mode == "seco")
        if self._pending_routine in ("CALIB_BRANCO", "CALIBRAÇÃO"):
            title = "Calibração de Branco Instrumental"
            if is_dry:
                msg = (
                    "A gaveta está aberta.<br><br>"
                    "Insira o <b>cartão branco fosco de referência (cartão branco fosco)</b> sobre o berço óptico "
                    "(sem lâmina e sem solvente líquido) e clique em <b>OK / Iniciar</b> para prosseguir."
                )
            else:
                msg = (
                    "A gaveta está aberta.<br><br>"
                    "Insira a <b>lâmina com água destilada e lamínula</b> sobre o berço de medição e "
                    "clique em <b>OK / Iniciar</b> para prosseguir."
                )
        elif self._pending_routine == "REPETIBILIDADE":
            title = "Inserção de Amostra"
            if is_dry:
                msg = (
                    "A gaveta está aberta.<br><br>"
                    "Posicione a <b>amostra seca de celulose (placa/folha)</b> no berço e clique em OK para iniciar o ensaio de repetibilidade."
                )
            else:
                msg = (
                    "A gaveta está aberta.<br><br>"
                    "Posicione a lâmina de suspensão aquosa de celulose no berço e clique em OK para iniciar o ensaio de repetibilidade."
                )
        else:
            title = "Inserção de Amostra"
            if is_dry:
                msg = (
                    "A gaveta está aberta.<br><br>"
                    "Posicione a <b>amostra seca de celulose (placa/folha)</b> no berço e clique em OK para iniciar."
                )
            else:
                msg = (
                    "A gaveta está aberta.<br><br>"
                    "Posicione a lâmina de suspensão aquosa de celulose no berço e clique em OK para iniciar."
                )

        dlg = SamplePlacementInterlockDialog(title=title, message=msg, parent=self)
        confirmed = (dlg.exec_() == QDialog.Accepted)

        if self._operation_epoch != popup_epoch or self.fsm_state != "AGUARDANDO_POPUP" or self._pending_routine != pending_routine:
            self.log_message("[INTERTRAVAMENTO] Confirmação descartada: rotina interrompida durante o diálogo.")
            return
        if not confirmed:
            # Operador cancelou ou fechou sem confirmar: NÃO despacha CMD:FECHAR_GAVETA e aborta a rotina
            self.log_message("[INTERTRAVAMENTO] Operador cancelou o popup de confirmação. CMD:FECHAR_GAVETA NÃO enviado. Rotina cancelada.")
            self.fsm_state = "IDLE"
            self._pending_routine = None
            self.auto_cycle_active = False
            self.modo_repetibilidade = False
            self.is_calibrating_white = False
            self.cycle_progress.setValue(0)
            self._enable_controls()
            self.lbl_cycle_status.setText("Status: Ensaio cancelado pelo operador. Gaveta permanece aberta.")
            return

        self.equipment.sample_confirmed = True
        # Sincronismo Estrito: O comando CMD:FECHAR_GAVETA\n é despachado ESTRITAMENTE após o operador clicar no botão "OK"
        self.log_message("[INTERTRAVAMENTO] Botão 'OK' clicado pelo operador. Despachando CMD:FECHAR_GAVETA...")
        self.cycle_progress.setValue(15)

        if self._pending_routine == "AUTO":
            self.auto_cycle_active = True
            self.fsm_state = "AUTO_FECHANDO_GAVETA"
            self.lbl_cycle_status.setText("Status: Amostra confirmada. Fechando gaveta para medição...")
            self._show_drawer_alert("Amostra confirmada. Fechando gaveta...", "FECHAMENTO DE GAVETA EM ANDAMENTO")
            self.send_serial_command("CMD:FECHAR_GAVETA")

        elif self._pending_routine == "REPETIBILIDADE":
            self.modo_repetibilidade = True
            self.leituras_rep = []
            self._rep_raw_scans=[]
            self._result_valid=False
            self.fsm_state = "REP_FECHANDO_GAVETA"
            self.lbl_cycle_status.setText("Status: Amostra confirmada. Fechando gaveta para repetibilidade...")
            self._show_drawer_alert("Amostra confirmada. Fechando gaveta...", "FECHAMENTO DE GAVETA EM ANDAMENTO")
            self.send_serial_command("CMD:FECHAR_GAVETA")

        elif self._pending_routine in ("CALIB_BRANCO", "CALIBRAÇÃO"):
            self.is_calibrating_white = True
            self.fsm_state = "CALIB_ETAPA1_FECHANDO_GAVETA"
            self.lbl_cycle_status.setText("Status: Referência confirmada. Fechando gaveta para medição do branco...")
            self._show_drawer_alert("Referência confirmada. Fechando gaveta...", "FECHAMENTO DE GAVETA EM ANDAMENTO")
            self.send_serial_command("CMD:FECHAR_GAVETA")

    # -----------------------------------------------------------------
    # A. CICLO AUTOMÁTICO SIMPLES
    # -----------------------------------------------------------------
    def start_simple_auto_cycle(self):
        """
        Inicia Ciclo Automático Simples com Intertravamento Humano:
        Fase 1: CMD:ABRIR_GAVETA -> STATUS:GAVETA_ABERTA
        Fase 2: Popup Modal de Confirmação do Operador (OK vs Cancelar)
        Fase 3: CMD:FECHAR_GAVETA -> CMD:AVANCAR_SENSOR -> CMD:LER_ESPECTRO ->
                CMD:RECUAR_SENSOR -> CMD:ABRIR_GAVETA -> Finalização e ejeção.
        """
        if not self.check_hardware_connected():
            return
        if self.auto_cycle_active or self.modo_repetibilidade or self.is_calibrating_white or self.fsm_state != "IDLE":
            self.log_message("AVISO: Outro ensaio já está em execução.")
            return

        if not self._ready_for_scan():
            self.log_message("[ENSAIO] Hardware ou referências indisponíveis.")
            return
        self._current_sample_id=(self.input_sample_id.text().strip() if hasattr(self,"input_sample_id") else "") or "AM-"+uuid.uuid4().hex[:8].upper()
        self._rep_raw_scans=[]
        self._result_valid=False
        self._clear_cycle_timers()
        self._disable_controls()

        self._pending_routine = "AUTO"
        self.fsm_state = "PREP_ABRINDO_GAVETA"
        self._last_raw_payload = []

        self.cycle_progress.setValue(5)
        self.lbl_cycle_status.setText("Status: Fase 1: Abrindo gaveta para posicionamento da amostra...")
        self.log_message("[CICLO AUTO] Fase 1: Enviando CMD:ABRIR_GAVETA")
        self._show_drawer_alert("Fase 1: Abrindo gaveta para posicionamento da amostra...", "ABERTURA DE GAVETA EM ANDAMENTO")
        self.send_serial_command("CMD:ABRIR_GAVETA")

    def _handle_auto_cycle_fsm(self, status_tag: str):
        # Passo 1: Gaveta Fechada pós-confirmação -> Avança sensor
        if status_tag == "GAVETA_FECHADA" and self.fsm_state == "AUTO_FECHANDO_GAVETA":
            self.fsm_state = "AUTO_AVANCANDO_SENSOR"
            self.cycle_progress.setValue(35)
            self.lbl_cycle_status.setText("Status: Gaveta fechada. Avançando sensor sobre a lâmina...")
            self.log_message("[CICLO AUTO] Avançando sensor (CMD:AVANCAR_SENSOR)")
            self._show_radiation_alert("Varredura óptica NIR em andamento. Câmara intertravada...")
            self.send_serial_command("CMD:AVANCAR_SENSOR")

        # Passo 2: Sensor Avançado -> Dispara 1 varredura óptica
        elif status_tag == "SENSOR_AVANCADO" and self.fsm_state == "AUTO_AVANCANDO_SENSOR":
            self.fsm_state = "AUTO_LENDO_ESPECTRO"
            self.cycle_progress.setValue(60)
            self.lbl_cycle_status.setText("Status: Sensor posicionado. Disparando leitura dos 6 canais NIR...")
            self.log_message("[CICLO AUTO] Disparando leitura (CMD:LER_ESPECTRO)")
            self.send_serial_command("CMD:LER_ESPECTRO")

        # Passo 3: Leitura Concluída -> Recua sensor
        elif status_tag == "LEITURA_CONCLUIDA" and self.fsm_state == "AUTO_LENDO_ESPECTRO":
            self.fsm_state = "AUTO_RECUANDO_SENSOR"
            self.cycle_progress.setValue(80)
            self.lbl_cycle_status.setText("Status: Leitura óptica concluída. Recuando sensor para repouso...")
            self.log_message("[CICLO AUTO] Recuando sensor (CMD:RECUAR_SENSOR)")
            self.send_serial_command("CMD:RECUAR_SENSOR")

        # Passo 4: Sensor Recuado -> Abre gaveta para retirada da lâmina
        elif status_tag == "SENSOR_RECUADO" and self.fsm_state == "AUTO_RECUANDO_SENSOR":
            self._hide_radiation_alert()
            self.fsm_state = "AUTO_ABRINDO_GAVETA"
            self.cycle_progress.setValue(92)
            self.lbl_cycle_status.setText("Status: Sensor em repouso. Abrindo gaveta para retirada da lâmina...")
            self.log_message("[CICLO AUTO] Abrindo gaveta para ejeção (CMD:ABRIR_GAVETA)")
            self._show_drawer_alert("Abrindo gaveta para retirada da lâmina...", "ABERTURA DE GAVETA EM ANDAMENTO")
            self.send_serial_command("CMD:ABRIR_GAVETA")

        # Passo 5: Gaveta Aberta -> Processa resultados e exibe diálogo de decisão
        elif status_tag == "GAVETA_ABERTA" and self.fsm_state == "AUTO_ABRINDO_GAVETA":
            self.cycle_progress.setValue(100)
            self.lbl_cycle_status.setText("Status: Análise concluída. Gaveta aberta no berço.")
            self.log_message("[CICLO AUTO] Análise concluída com sucesso. Gaveta aberta no berço.")

            if self._last_raw_payload:
                self.process_raw_spectral_data(self._last_raw_payload)
                if not self._result_valid:
                    return

            # Abre o Diálogo de Decisão ao Concluir a Leitura (Item 3)
            self._handle_completion_decision_dialog(is_repeatability=False)

    # -----------------------------------------------------------------
    # B. TESTE DE REPETIBILIDADE (5 LEITURAS COM AVANÇO/RECUO DO SENSOR)
    # -----------------------------------------------------------------
    def start_repeatability_test(self):
        """
        Ensaio de Repetibilidade com Intertravamento Humano:
        Fase 1: CMD:ABRIR_GAVETA -> STATUS:GAVETA_ABERTA
        Fase 2: Popup de Confirmação do Operador (OK para iniciar)
        Fase 3: CMD:FECHAR_GAVETA ->
                Repetições 1 a N-1 (gaveta sempre fechada):
                  CMD:AVANCAR_SENSOR -> CMD:LER_ESPECTRO -> CMD:RECUAR_SENSOR
                Repetição N:
                  CMD:AVANCAR_SENSOR -> CMD:LER_ESPECTRO -> CMD:RECUAR_SENSOR ->
                  CMD:ABRIR_GAVETA -> STATUS:GAVETA_ABERTA -> Diálogo de Decisão.
        """
        if not self.check_hardware_connected():
            return
        if self.auto_cycle_active or self.modo_repetibilidade or self.is_calibrating_white or self.fsm_state != "IDLE":
            self.log_message("AVISO: Outro ensaio já está em andamento.")
            return

        if not self._ready_for_scan():
            self.log_message("[ENSAIO] Hardware ou referências indisponíveis.")
            return
        self._current_sample_id=(self.input_sample_id.text().strip() if hasattr(self,"input_sample_id") else "") or "AM-"+uuid.uuid4().hex[:8].upper()
        self._rep_raw_scans=[]
        self._result_valid=False
        self._clear_cycle_timers()
        self._disable_controls()

        self._pending_routine = "REPETIBILIDADE"
        self.leituras_rep = []
        self._last_raw_payload = []
        self.fsm_state = "PREP_ABRINDO_GAVETA"

        self.cycle_progress.setValue(5)
        self.lbl_cycle_status.setText("Status: Fase 1: Abrindo gaveta para posicionamento da amostra...")
        self.log_message("[REPETIBILIDADE] Fase 1: Enviando CMD:ABRIR_GAVETA")
        self._show_drawer_alert("Fase 1: Abrindo gaveta para posicionamento da amostra...", "ABERTURA DE GAVETA EM ANDAMENTO")
        self.send_serial_command("CMD:ABRIR_GAVETA")

    def _trigger_next_repeatability_read(self):
        """Dispara a próxima aquisição óptica durante o ensaio de repetibilidade estática sem mover o sensor."""
        if not self.modo_repetibilidade or self.fsm_state != "REP_AGUARDANDO_PROXIMA":
            return
        self.fsm_state = "REP_LENDO_ESPECTRO"
        rep_num = len(self.leituras_rep) + 1
        self.lbl_cycle_status.setText(f"Status: Sensor estático posicionado. Disparando aquisição {rep_num} de 5...")
        self.log_message(f"[REPETIBILIDADE ESTÁTICA] Disparando aquisição {rep_num}/5 (CMD:LER_ESPECTRO)...")
        self.send_serial_command("CMD:LER_ESPECTRO")

    def _handle_repeatability_fsm(self, status_tag: str):
        # 1. Gaveta Fechada pós-confirmação -> Avança sensor para a medição 1
        if status_tag == "GAVETA_FECHADA" and self.fsm_state == "REP_FECHANDO_GAVETA":
            self.fsm_state = "REP_AVANCANDO_SENSOR"
            self.cycle_progress.setValue(15)
            self.lbl_cycle_status.setText("Status: Gaveta fechada. Posicionando sensor sobre a amostra...")
            self.log_message("[REPETIBILIDADE ESTÁTICA] Posicionando sensor sobre a amostra (CMD:AVANCAR_SENSOR)")
            self._show_radiation_alert("Ensaio de Repetibilidade Estática (aquisições consecutivas sem movimento)...")
            self.send_serial_command("CMD:AVANCAR_SENSOR")

        # 2. Sensor Avançado -> Dispara 1ª varredura óptica sem movimentações intermediárias
        elif status_tag == "SENSOR_AVANCADO" and self.fsm_state == "REP_AVANCANDO_SENSOR":
            self.fsm_state = "REP_LENDO_ESPECTRO"
            rep_num = len(self.leituras_rep) + 1
            self.lbl_cycle_status.setText(f"Status: Sensor estático posicionado. Disparando aquisição {rep_num} de 5...")
            self.log_message(f"[REPETIBILIDADE ESTÁTICA] Sensor posicionado. Disparando aquisição {rep_num}/5 (CMD:LER_ESPECTRO)...")
            self.send_serial_command("CMD:LER_ESPECTRO")

        # 3. Leitura Concluída -> Registra dados. Se count < 5, aguarda delay térmico e dispara próxima leitura no mesmo ponto
        elif status_tag == "LEITURA_CONCLUIDA" and self.fsm_state == "REP_LENDO_ESPECTRO":
            if self._last_raw_payload and len(self._last_raw_payload) == 6:
                try:
                    calib_r=self.chem_engine.calculate_relative_reflectance(self._last_raw_payload)
                except ValueError as err:
                    self._fail_operation(str(err))
                    return
                self._rep_raw_scans.append(list(self._last_raw_payload))
                self.leituras_rep.append(calib_r)
                count = len(self.leituras_rep)

                progress_val = 15 + int((count / 5.0) * 70)
                self.cycle_progress.setValue(progress_val)
                self.lbl_cycle_status.setText(f"Status: Aquisição {count} de 5 concluída...")
                self.log_message(f"[REPETIBILIDADE ESTÁTICA] Aquisição {count}/5 gravada: {[round(v, 4) for v in calib_r]}")

                snv = self.chem_engine.normalize_snv(calib_r)
                if hasattr(self, "scatter_plot") and self.scatter_plot is not None:
                    self.scatter_plot.add_measurement(self._last_raw_payload, f"Rep #{count}", r_norm=snv)

            count = len(self.leituras_rep)
            if count < 5:
                # Mantém sensor estático na mesma posição e agenda próxima leitura após 300ms de resfriamento térmico do LED
                self.fsm_state = "REP_AGUARDANDO_PROXIMA"
                self.lbl_cycle_status.setText(f"Status: Intervalo térmico (aquisição {count} de 5 concluída)...")
                t = QTimer(self)
                t.setSingleShot(True)
                t.timeout.connect(self._trigger_next_repeatability_read)
                self._cycle_timers.append(t)
                t.start(300)
            else:
                # Todas as 5 aquisições estáticas concluídas: Somente agora recua o sensor!
                self.fsm_state = "REP_RECUANDO_SENSOR"
                self.cycle_progress.setValue(90)
                self.lbl_cycle_status.setText("Status: 5 aquisições estáticas concluídas. Recuando sensor...")
                self.log_message("[REPETIBILIDADE ESTÁTICA] 5 leituras concluídas sem movimento mecânico. Recuando sensor (CMD:RECUAR_SENSOR)...")
                self.send_serial_command("CMD:RECUAR_SENSOR")

        # 4. Sensor Recuado -> Recuado o sensor após N=5, abre a gaveta para o operador!
        elif status_tag == "SENSOR_RECUADO" and self.fsm_state == "REP_RECUANDO_SENSOR":
            self._hide_radiation_alert()
            self.fsm_state = "REP_ABRINDO_GAVETA"
            self.cycle_progress.setValue(95)
            self.lbl_cycle_status.setText("Status: Sensor em repouso. Abrindo gaveta para decisão operacional...")
            self.log_message("[REPETIBILIDADE ESTÁTICA] Sensor recuado. Abrindo gaveta para ejeção (CMD:ABRIR_GAVETA)...")
            self._show_drawer_alert("Abrindo gaveta para retirada da lâmina...", "ABERTURA DE GAVETA EM ANDAMENTO")
            self.send_serial_command("CMD:ABRIR_GAVETA")

        # 5. Gaveta Aberta -> Exibe relatório estatístico e abre diálogo de decisão
        elif status_tag == "GAVETA_ABERTA" and self.fsm_state == "REP_ABRINDO_GAVETA":
            self.cycle_progress.setValue(100)
            self.lbl_cycle_status.setText("Status: Ensaio de Repetibilidade Estática concluído. Gaveta aberta no berço.")
            self.log_message("[REPETIBILIDADE ESTÁTICA] Ensaio de Repetibilidade Estática concluído. Gaveta aberta.")
            self._display_repeatability_report()
            self._handle_completion_decision_dialog(is_repeatability=True)

    def _handle_completion_decision_dialog(self, is_repeatability: bool = False):
        """
        Diálogo de decisão ao concluir a leitura com a gaveta aberta (Item 3):
        - Botão 1: [ Finalizar e Fechar Gaveta ] (Padrão) -> envia CMD:FECHAR_GAVETA, sistema em repouso.
        - Botão 2: [ Nova Análise ] -> mantém gaveta aberta, limpa dados, pede novo nome e fecha para ler.
        - Botão 3: [ Iniciar Repetibilidade ] -> mantém gaveta aberta para checagem, fecha e dispara repetições.
        """
        decision_epoch = self._operation_epoch
        decision_state = self.fsm_state
        dlg = DialogDecisaoConclusao(parent=self, is_repeatability=is_repeatability)
        dlg.exec_()
        action = dlg.selected_action

        if self._operation_epoch != decision_epoch or self.fsm_state != decision_state or not self.is_serial_connected():
            return
        if action == DialogDecisaoConclusao.ACTION_FINISH:
            self.log_message("[CONCLUSÃO] Decisão: Finalizar e Fechar Gaveta.")
            self.fsm_state = "CONCLUSAO_FECHANDO_GAVETA"
            self.lbl_cycle_status.setText("Status: Finalizando ensaio. Fechando gaveta...")
            self._show_drawer_alert("Fechando gaveta e finalizando...", "FECHAMENTO DE GAVETA EM ANDAMENTO")
            self.send_serial_command("CMD:FECHAR_GAVETA")

        elif action == DialogDecisaoConclusao.ACTION_NEW_SCAN:
            if not self.chem_engine.calibration_valid():
                self._fail_operation("Recalibre antes de iniciar nova amostra.")
                return
            self.log_message("[CONCLUSÃO] Decisão: Nova Análise. Gaveta permanece aberta no berço.")
            self._last_raw_payload = []
            self.current_scan_data = []

            novo_id = f"Amostra_{datetime.datetime.now().strftime('%H%M%S')}"
            default_name = getattr(self, "current_sample_name", novo_id)
            texto, ok = QInputDialog.getText(
                self,
                "Nova Análise — Identificação da Amostra",
                "A gaveta está aberta.<br>Insira a nova lâmina no berço e confirme o nome da amostra:",
                text=default_name
            )
            if self._operation_epoch != decision_epoch or self.fsm_state != decision_state or not self.is_serial_connected():
                return
            if not ok:
                # Cancelou o nome: finaliza fechando a gaveta
                self.fsm_state = "CONCLUSAO_FECHANDO_GAVETA"
                self.send_serial_command("CMD:FECHAR_GAVETA")
                return
            novo_id = texto.strip() or novo_id

            self.equipment.sample_confirmed = True
            self._current_sample_id=novo_id
            self._result_valid=False
            self.current_sample_name = novo_id
            if hasattr(self,"input_sample_id"):
                self.input_sample_id.setText(novo_id)
            if hasattr(self, "txt_sample_id") and self.txt_sample_id is not None:
                self.txt_sample_id.setText(novo_id)
            self._pending_routine = "AUTO"
            self.auto_cycle_active = True
            self.modo_repetibilidade = False
            self.is_calibrating_white = False
            self.fsm_state = "AUTO_FECHANDO_GAVETA"
            self.cycle_progress.setValue(15)
            self.lbl_cycle_status.setText(f"Status: Nova amostra ({novo_id}) confirmada. Fechando gaveta...")
            self._show_drawer_alert("Fechando gaveta para nova medição...", "FECHAMENTO DE GAVETA EM ANDAMENTO")
            # Envia diretamente CMD:FECHAR_GAVETA (sem tentar abrir novamente a gaveta que já está aberta!)
            self.send_serial_command("CMD:FECHAR_GAVETA")

        elif action == DialogDecisaoConclusao.ACTION_REPEAT:
            if not self.chem_engine.calibration_valid():
                self._fail_operation("Recalibre antes de repetir.")
                return
            self.log_message("[CONCLUSÃO] Decisão: Iniciar Repetibilidade. Gaveta aberta para checagem.")
            resp = QMessageBox.question(
                self,
                "Iniciar Repetibilidade",
                "A gaveta está aberta. Verifique se a lâmina está posicionada sobre o berço.<br><br>"
                "Deseja iniciar o <b>Ensaio de Repetibilidade</b> com 5 repetições consecutivas?",
                QMessageBox.Yes | QMessageBox.No,
                QMessageBox.Yes
            )
            if self._operation_epoch != decision_epoch or self.fsm_state != decision_state or not self.is_serial_connected():
                return
            if resp != QMessageBox.Yes:
                self.fsm_state = "CONCLUSAO_FECHANDO_GAVETA"
                self.send_serial_command("CMD:FECHAR_GAVETA")
                return

            self.equipment.sample_confirmed = True
            self._pending_routine = "REPETIBILIDADE"
            self.modo_repetibilidade = True
            self.auto_cycle_active = False
            self.is_calibrating_white = False
            self.leituras_rep = []
            self._rep_raw_scans=[]
            self._result_valid=False
            self.fsm_state = "REP_FECHANDO_GAVETA"
            self.cycle_progress.setValue(10)
            self.lbl_cycle_status.setText("Status: Repetibilidade confirmada. Fechando gaveta...")
            self._show_drawer_alert("Repetibilidade confirmada. Fechando gaveta...", "FECHAMENTO DE GAVETA EM ANDAMENTO")
            # Envia diretamente CMD:FECHAR_GAVETA (sem tentar abrir novamente a gaveta que já está aberta!)
            self.send_serial_command("CMD:FECHAR_GAVETA")

    def _display_repeatability_report(self):
        """
        Calcula e exibe diálogo modal avançado (~950x650 px) com relatório estatístico de repetibilidade:
        - Cabeçalho: Badges de CV% Médio Global e Card de Kappa Médio (u ± s) com classificação de polpa.
        - Tabela de 6 canais: Média, Desvio Padrão, CV%.
        - Painel gráfico duplo Matplotlib:
          1. Gráfico de Barras com Desvio Padrão (yerr=s).
          2. Gráfico de Dispersão 2D das 5 leituras com o Centroide marcado.
        - Rodapé: Botão de exportação para CSV da matriz 5x6 e métricas.
        """
        if len(self.leituras_rep) < 2:
            return

        stats = self.chem_engine.compute_repeatability_stats(self.leituras_rep)
        means = stats["means"]
        stdevs = stats["stdevs"]
        cvs = stats["cv_percent"]
        global_cv = stats["global_cv_mean"]

        # Calcula o Kappa e as razões individuais para cada disparo
        kappas = []
        ratio_cels = []
        ratio_waters = []
        for r_cal in self.leituras_rep:
            snv = self.chem_engine.normalize_snv(r_cal)
            k_val, _, _ = calculate_kappa_number(
                r_cal if self.chem_engine.active_mode == "seco" else snv,
                mode=self.chem_engine.active_mode
            )
            kappas.append(k_val)
            r_c, r_w = self.chem_engine.calculate_ratios(snv)
            ratio_cels.append(r_c)
            ratio_waters.append(r_w)

        n_runs = len(kappas)
        kappa_mean = sum(kappas) / n_runs if n_runs > 0 else 0.0
        if n_runs > 1:
            kappa_std = math.sqrt(sum((k - kappa_mean) ** 2 for k in kappas) / (n_runs - 1))
        else:
            kappa_std = 0.0

        kappa_status,kappa_color=self._classify_kappa(kappa_mean)
        if self._rep_raw_scans:
            mean_adc=self.chem_engine.compute_repeatability_stats(self._rep_raw_scans)["means"]
            all_scans=list(self._rep_raw_scans)
            for scan in all_scans:
                self._last_acquisition_scans=[scan]
                self.process_raw_spectral_data(scan,persist=True)
            self._last_acquisition_scans=all_scans
            self.process_raw_spectral_data(mean_adc,persist=False)
        else:
            mean_adc=[0.0]*6
        snv_mean=self.chem_engine.normalize_snv(means)
        self.spectral_chart.update_spectrum(mean_adc,r_calibrated=means,r_snv=snv_mean)

        dlg = QDialog(self)
        dlg.setWindowTitle("Relatório Estatístico de Repetibilidade Instrumental — 5x Estático")
        dlg.resize(960, 660)
        dlg.setStyleSheet("""
            QDialog {
                background-color: #111827;
                color: #F3F4F6;
                border: 1px solid #374151;
            }
            QLabel {
                font-family: 'Segoe UI', Arial, sans-serif;
            }
        """)

        d_layout = QVBoxLayout(dlg)
        d_layout.setContentsMargins(16, 14, 16, 14)
        d_layout.setSpacing(10)

        # 1. CABEÇALHO & CARDS KPI
        header_row = QHBoxLayout()
        header_title = QLabel("RELATÓRIO ESTATÍSTICO DE REPETIBILIDADE INSTRUMENTAL (5x Estático)")
        header_title.setStyleSheet("color: #38BDF8; font-size: 14px; font-weight: 800; letter-spacing: 0.5px;")
        header_row.addWidget(header_title)
        header_row.addStretch()

        mode_badge = QLabel(f"Método: {MODE_LABELS.get(self.chem_engine.active_mode, self.chem_engine.active_mode)}")
        mode_badge.setStyleSheet("background-color: #1F2937; color: #38BDF8; padding: 4px 10px; border-radius: 4px; font-size: 11px; font-weight: bold;")
        header_row.addWidget(mode_badge)
        d_layout.addLayout(header_row)

        # Cards KPI de Destaque
        cards_layout = QHBoxLayout()
        cards_layout.setSpacing(10)

        # Card CV% Global
        cv_card = QFrame()
        cv_card.setStyleSheet("background-color: #1F2937; border: 1px solid #374151; border-radius: 8px;")
        cv_l = QVBoxLayout(cv_card)
        cv_l.setContentsMargins(12, 8, 12, 8)
        cv_l.setSpacing(2)
        cv_sub = QLabel("CV% MÉDIO GLOBAL")
        cv_sub.setStyleSheet("color: #9CA3AF; font-size: 9px; font-weight: bold;")
        cv_val_lbl = QLabel(f"{global_cv:.2f}%")
        cv_col = "#10B981" if global_cv < 3.0 else ("#F59E0B" if global_cv < 6.0 else "#EF4444")
        cv_val_lbl.setStyleSheet(f"color: {cv_col}; font-size: 20px; font-weight: 900;")
        cv_desc = QLabel("Precisão Excelente (< 3%)" if global_cv < 3.0 else ("Ajuste Médio" if global_cv < 6.0 else "Alta Variabilidade"))
        cv_desc.setStyleSheet(f"color: {cv_col}; font-size: 10px; font-weight: bold;")
        cv_l.addWidget(cv_sub)
        cv_l.addWidget(cv_val_lbl)
        cv_l.addWidget(cv_desc)
        cards_layout.addWidget(cv_card)

        # Card Número Kappa Médio
        kappa_card = QFrame()
        kappa_card.setStyleSheet("background-color: #1F2937; border: 1px solid #374151; border-radius: 8px;")
        k_l = QVBoxLayout(kappa_card)
        k_l.setContentsMargins(12, 8, 12, 8)
        k_l.setSpacing(2)
        k_sub = QLabel("KAPPA DEMONSTRATIVO MÉDIO (5 LEITURAS)")
        k_sub.setStyleSheet("color: #9CA3AF; font-size: 9px; font-weight: bold;")
        k_val_lbl = QLabel(f"Kappa: {kappa_mean:.2f} ± {kappa_std:.2f}")
        k_val_lbl.setStyleSheet(f"color: {kappa_color}; font-size: 18px; font-weight: 900;")
        k_stat_lbl = QLabel(f"Faixa do modelo: {kappa_status}")
        k_stat_lbl.setStyleSheet(f"color: {kappa_color}; font-size: 10px; font-weight: bold;")
        k_l.addWidget(k_sub)
        k_l.addWidget(k_val_lbl)
        k_l.addWidget(k_stat_lbl)
        cards_layout.addWidget(kappa_card)

        # Card Amostra & Repetições
        sample_card = QFrame()
        sample_card.setStyleSheet("background-color: #1F2937; border: 1px solid #374151; border-radius: 8px;")
        s_l = QVBoxLayout(sample_card)
        s_l.setContentsMargins(12, 8, 12, 8)
        s_l.setSpacing(2)
        s_sub = QLabel("IDENTIFICAÇÃO & VARREDURAS")
        s_sub.setStyleSheet("color: #9CA3AF; font-size: 9px; font-weight: bold;")
        s_val_lbl = QLabel(f"{getattr(self, 'current_sample_name', 'Amostra')}")
        s_val_lbl.setStyleSheet("color: #38BDF8; font-size: 16px; font-weight: 800;")
        s_desc = QLabel(f"N = {len(self.leituras_rep)} varreduras estáticas consecutivas")
        s_desc.setStyleSheet("color: #9CA3AF; font-size: 10px;")
        s_l.addWidget(s_sub)
        s_l.addWidget(s_val_lbl)
        s_l.addWidget(s_desc)
        cards_layout.addWidget(sample_card)

        d_layout.addLayout(cards_layout)

        # 2. MEIO: TABELA ESTATÍSTICA (6 CANAIS)
        table = QTableWidget(6, 4)
        table.setHorizontalHeaderLabels(["Canal (nm)", "Média (μ)", "Desvio Padrão (s)", "CV (%)"])
        table.horizontalHeader().setSectionResizeMode(QHeaderView.Stretch)
        table.setMaximumHeight(150)
        table.setStyleSheet("""
            QTableWidget {
                background-color: #1F2937;
                gridline-color: #374151;
                color: #FFFFFF;
                font-size: 11px;
                border: 1px solid #374151;
                border-radius: 6px;
            }
            QHeaderView::section {
                background-color: #111827;
                color: #38BDF8;
                font-weight: bold;
                border: 1px solid #374151;
                padding: 4px;
            }
        """)

        for ch in range(6):
            table.setItem(ch, 0, QTableWidgetItem(CHANNEL_NAMES[ch]))
            table.setItem(ch, 1, QTableWidgetItem(f"{means[ch]:.4f}"))
            table.setItem(ch, 2, QTableWidgetItem(f"{stdevs[ch]:.4f}"))

            cv_item = QTableWidgetItem(f"{cvs[ch]:.2f}%")
            if cvs[ch] < 3.0:
                cv_item.setForeground(QColor("#10B981"))
            elif cvs[ch] < 6.0:
                cv_item.setForeground(QColor("#F59E0B"))
            else:
                cv_item.setForeground(QColor("#EF4444"))
            table.setItem(ch, 3, cv_item)

        d_layout.addWidget(table)

        # 3. PAINEL GRÁFICO DUPLO (MATPLOTLIB)
        chart_container = QWidget()
        chart_layout = QHBoxLayout(chart_container)
        chart_layout.setContentsMargins(0, 0, 0, 0)
        chart_layout.setSpacing(10)

        fig = Figure(figsize=(9, 3.2), facecolor="#111827")

        # Subplot 1: Gráfico de Barras com Erro Padrão (yerr=s)
        ax1 = fig.add_subplot(121)
        ax1.set_facecolor("#1F2937")
        channel_labels = ["610", "680", "730", "760", "810", "860"]
        bar_colors = ["#F97316", "#EF4444", "#DC2626", "#B91C1C", "#7C3AED", "#6366F1"]
        x_pos = range(len(channel_labels))
        ax1.bar(x_pos, means, yerr=stdevs, capsize=4, color=bar_colors, edgecolor="#374151", error_kw={"ecolor": "#F87171", "linewidth": 1.5})
        ax1.set_xticks(x_pos)
        ax1.set_xticklabels(channel_labels, color="#D1D5DB", fontsize=9, fontweight="bold")
        ax1.set_title("Médias por Canal com Desvio (μ ± s)", color="#38BDF8", fontsize=10, fontweight="bold", pad=8)
        ax1.set_ylabel("Reflectância Relativa", color="#9CA3AF", fontsize=8)
        ax1.tick_params(colors="#9CA3AF", labelsize=8)
        ax1.grid(color="#374151", linestyle="--", linewidth=0.5, alpha=0.6)
        for spine in ax1.spines.values():
            spine.set_color("#374151")

        # Subplot 2: Gráfico de Dispersão 2D (Razão Celulose vs. Razão Água) com Centroide
        ax2 = fig.add_subplot(122)
        ax2.set_facecolor("#1F2937")
        centroid_x = sum(ratio_cels) / len(ratio_cels) if ratio_cels else 0.0
        centroid_y = sum(ratio_waters) / len(ratio_waters) if ratio_waters else 0.0

        # Plota os 5 pontos
        ax2.scatter(ratio_cels, ratio_waters, c="#38BDF8", s=65, edgecolors="#FFFFFF", linewidth=1.2, label="Disparos (1-5)", zorder=4)
        for idx, (rx, ry) in enumerate(zip(ratio_cels, ratio_waters), 1):
            ax2.annotate(f"#{idx}", (rx, ry), textcoords="offset points", xytext=(4, 4), color="#E0E7FF", fontsize=7, fontweight="bold")

        # Plota o centroide
        ax2.scatter([centroid_x], [centroid_y], c="#FBBF24", s=140, marker="*", edgecolors="#FFFFFF", linewidth=1.2, label=f"Centroide ({centroid_x:.2f}, {centroid_y:.2f})", zorder=5)
        ax2.set_title("Dispersão 2D (Celulose vs. Água) & Centroide", color="#38BDF8", fontsize=10, fontweight="bold", pad=8)
        ax2.set_xlabel("Razão Celulose (R680 / R730)", color="#9CA3AF", fontsize=8)
        ax2.set_ylabel("Razão Água (R860 / R760)", color="#9CA3AF", fontsize=8)
        ax2.tick_params(colors="#9CA3AF", labelsize=8)
        ax2.grid(color="#374151", linestyle="--", linewidth=0.5, alpha=0.6)
        ax2.legend(loc="best", fontsize=7, facecolor="#111827", edgecolor="#374151", labelcolor="#F3F4F6")
        for spine in ax2.spines.values():
            spine.set_color("#374151")

        fig.tight_layout()
        canvas = FigureCanvas(fig)
        dlg.finished.connect(lambda: plt.close(fig))
        chart_layout.addWidget(canvas)
        d_layout.addWidget(chart_container)

        # 4. RODAPÉ COM EXPORTAÇÃO CSV E FECHAR
        btn_row = QHBoxLayout()
        btn_row.setSpacing(10)

        btn_csv = QPushButton("Exportar Matriz 5x6 e Estatísticas (CSV)")
        btn_csv.setStyleSheet("""
            QPushButton {
                background-color: #047857;
                color: #FFFFFF;
                border: none;
                border-radius: 6px;
                padding: 9px 16px;
                font-size: 11px;
                font-weight: bold;
            }
            QPushButton:hover {
                background-color: #059669;
            }
        """)

        def _export_csv():
            default_fn = f"repetibilidade_{datetime.datetime.now().strftime('%Y%m%d_%H%M%S')}.csv"
            fp, _ = QFileDialog.getSaveFileName(dlg, "Salvar Relatório de Repetibilidade", default_fn, "Arquivos CSV (*.csv)")
            if not fp:
                return
            try:
                with open(fp, "w", newline="", encoding="utf-8-sig") as cf:
                    cw = csv.writer(cf, delimiter=";")
                    cw.writerow(["SPECTRUM-LAB PRO — ENSAIO ESTATISTICO DE REPETIBILIDADE (5x ESTATICO)"])
                    cw.writerow(["Data/Hora", datetime.datetime.now().strftime("%Y-%m-%d %H:%M:%S")])
                    cw.writerow(["Metodo Analitico", MODE_LABELS.get(self.chem_engine.active_mode, self.chem_engine.active_mode)])
                    cw.writerow(["Amostra", getattr(self, "current_sample_name", "Amostra")])
                    cw.writerow(["Operador", getattr(self.chem_engine, "calib_operador", "Qualidade")])
                    cw.writerow(["Calibracao", self.chem_engine.calibration_id])
                    cw.writerow(["CV% Medio Global", f"{global_cv:.2f}%"])
                    cw.writerow(["Kappa Medio", f"{kappa_mean:.2f} +- {kappa_std:.2f}"])
                    cw.writerow(["Faixa do modelo experimental", kappa_status])
                    cw.writerow([])
                    cw.writerow(["--- RESPOSTAS OPTICAS RELATIVAS (5 DISPAROS) ---"])
                    cw.writerow(["Disparo"] + CHANNEL_NAMES + ["Razao Celulose (R680/R730)", "Razao Agua (R860/R760)", "Kappa Demonstrativo"])
                    for idx, (run_vals, rc, rw, kv) in enumerate(zip(self.leituras_rep, ratio_cels, ratio_waters, kappas), 1):
                        row = [f"Disparo #{idx}"] + [f"{v:.4f}" for v in run_vals] + [f"{rc:.4f}", f"{rw:.4f}", f"{kv:.2f}"]
                        cw.writerow(row)
                    cw.writerow([])
                    cw.writerow(["--- ESTATISTICAS POR CANAL ---"])
                    cw.writerow(["Canal", "Media (mu)", "Desvio Padrao (s)", "CV (%)"])
                    for ch in range(6):
                        cw.writerow([CHANNEL_NAMES[ch], f"{means[ch]:.4f}", f"{stdevs[ch]:.4f}", f"{cvs[ch]:.2f}%"])
                QMessageBox.information(dlg, "Sucesso", f"Relatório exportado com sucesso para:<br><b>{fp}</b>")
            except Exception as e:
                QMessageBox.critical(dlg, "Erro de Exportação", f"Não foi possível salvar o arquivo CSV:<br>{e}")

        btn_csv.clicked.connect(_export_csv)
        btn_row.addWidget(btn_csv)

        btn_row.addStretch()

        btn_ok = QPushButton("Fechar Relatório")
        btn_ok.setStyleSheet("""
            QPushButton {
                background-color: #374151;
                color: #FFFFFF;
                border: 1px solid #4B5563;
                border-radius: 6px;
                padding: 9px 20px;
                font-size: 11px;
                font-weight: bold;
            }
            QPushButton:hover {
                background-color: #4B5563;
            }
        """)
        btn_ok.clicked.connect(dlg.accept)
        btn_row.addWidget(btn_ok)

        d_layout.addLayout(btn_row)

        dlg.exec_()
        self.log_message(f"Repetibilidade finalizada. CV% Médio Global = {global_cv:.2f}%, Kappa Médio = {kappa_mean:.2f} ± {kappa_std:.2f}")

    # -----------------------------------------------------------------
    # C. CALIBRAÇÃO INSTRUMENTAL SEQUENCIAL (BRANCO -> ESCURO)
    # -----------------------------------------------------------------
    def start_white_calibration_cycle(self):
        """
        Rotina de Calibração Sequencial Guiada (Branco -> Escuro):
        ETAPA 1: Branco (Lâmina com Água Destilada OU Padrão Branco Seco Teflon)
        - CMD:ABRIR_GAVETA -> STATUS:GAVETA_ABERTA
        - Popup 1 (Inserção do Branco) -> OK ou Cancelar (fecha gaveta)
        - CMD:FECHAR_GAVETA -> CMD:AVANCAR_SENSOR -> CMD:LER_ESPECTRO -> CMD:RECUAR_SENSOR
        - CMD:ABRIR_GAVETA -> STATUS:GAVETA_ABERTA (Ejeção segura)
        ETAPA 2: Transição e Fundo Escuro (Gaveta Vazia)
        - Popup 2 (Deseja prosseguir para escuro? Se não: fecha gaveta, salva branco e encerra)
        - Popup 3 (Aviso de segurança: lâmina/padrão removido e berço vazio?)
        - CMD:FECHAR_GAVETA -> CMD:AVANCAR_SENSOR -> CMD:LER_ESPECTRO -> CMD:RECUAR_SENSOR
        - Encerramento Seguro: Não reabre gaveta (berço vazio em repouso), salva calibracao.json e encerra.
        """
        if not self.check_hardware_connected():
            return
        if self.auto_cycle_active or self.modo_repetibilidade or self.is_calibrating_white or self.fsm_state != "IDLE":
            self.log_message("AVISO: Outro ensaio ou calibração já está em andamento.")
            return

        self._clear_cycle_timers()
        self._disable_controls()

        if not self._protocol_ready or not self._sensor_ready:
            self.log_message("[CALIBRAÇÃO] Atualize o firmware antes de medir referências.")
            self._refresh_controls()
            return
        self._result_valid=False
        self._white_scans=[]
        self._dark_scans=[]
        self.combo_op_mode.setEnabled(False)
        self.is_calibrating_white = True
        self._pending_routine = "CALIBRAÇÃO"
        self._last_raw_payload = []
        self._temp_vetor_branco = []
        self._temp_vetor_escuro = []
        self.fsm_state = "PREP_ABRINDO_GAVETA"

        self.cycle_progress.setValue(5)
        is_dry = (self.chem_engine.active_mode == "seco")
        target_name = "padrão branco seco (cartão branco fosco)" if is_dry else "lâmina com água destilada"
        self.lbl_cycle_status.setText(f"Status: Calibração Etapa 1: Abrindo gaveta para {target_name}...")
        self.log_message(f"[CALIBRAÇÃO - {self.chem_engine.active_mode.upper()}] Etapa 1: Enviando CMD:ABRIR_GAVETA")
        self._show_drawer_alert(f"Calibração Etapa 1: Abrindo gaveta para {target_name}...", "ABERTURA DE GAVETA EM ANDAMENTO")
        self.send_serial_command("CMD:ABRIR_GAVETA")

    def start_calibration_wizard(self):
        """Alias para calibração sequencial completa."""
        self.start_white_calibration_cycle()

    def _handle_calib_transition_popups(self):
        """
        ETAPA 2: Transição com a gaveta aberta pós-branco.
        Exibe Popup 2 (Pergunta de Sequência) e, se o operador aceitar, Popup 3 (Segurança).
        """
        self.lbl_cycle_status.setText("Status: Branco registrado. Gaveta aberta. Aguardando operador...")
        transition_state = self.fsm_state
        transition_epoch = self._operation_epoch
        self.log_message("[CALIBRAÇÃO TRANSIÇÃO] Gaveta aberta. Exibindo Popup 2 (Pergunta de Sequência)...")

        # Popup 2: Deseja prosseguir para escuro?
        dlg2 = CalibrationTransitionDialog(parent=self)
        proceed = (dlg2.exec_() == QDialog.Accepted)

        if self._operation_epoch != transition_epoch or self.fsm_state != transition_state or not self.is_calibrating_white:
            return
        if not proceed:
            # Usuário escolheu [ Cancelar / Sair ]: Fecha gaveta e salva Branco
            self.log_message("[CALIBRAÇÃO] Operador optou por Concluir após o Branco. Fechando gaveta...")
            self.fsm_state = "CALIB_CONCLUSAO_FECHANDO_GAVETA"
            self.lbl_cycle_status.setText("Status: Fechando gaveta; calibração incompleta será descartada...")
            self._show_drawer_alert("Fechando gaveta e descartando calibração incompleta...", "FECHAMENTO DE GAVETA EM ANDAMENTO")
            self.send_serial_command("CMD:FECHAR_GAVETA")
            return

        # Usuário escolheu [ Prosseguir ] -> Popup 3 (Aviso de Segurança - Berço Vazio)
        self.log_message("[CALIBRAÇÃO] Operador optou por prosseguir. Exibindo Popup 3 (Aviso de Segurança)...")
        dlg3 = DarkSafetyInterlockDialog(parent=self)
        confirmed_empty = (dlg3.exec_() == QDialog.Accepted)

        if self._operation_epoch != transition_epoch or self.fsm_state != transition_state or not self.is_calibrating_white:
            return
        if not confirmed_empty:
            # Usuário cancelou no Popup 3: Fecha gaveta e salva Branco
            self.log_message("[CALIBRAÇÃO] Operador cancelou no Popup 3. Fechando gaveta e descartando calibração incompleta...")
            self.fsm_state = "CALIB_CONCLUSAO_FECHANDO_GAVETA"
            self.lbl_cycle_status.setText("Status: Fechando gaveta; calibração incompleta será descartada...")
            self._show_drawer_alert("Cancelamento: Fechando gaveta...", "FECHAMENTO DE GAVETA EM ANDAMENTO")
            self.send_serial_command("CMD:FECHAR_GAVETA")
            return

        self.equipment.sample_confirmed = True
        # Popup 3 confirmado: Berço vazio confirmado pelo operador!
        self.log_message("[CALIBRAÇÃO] Berço vazio confirmado. Fechando gaveta para medição de escuro...")
        self.fsm_state = "CALIB_ETAPA2_FECHANDO_GAVETA"
        self.cycle_progress.setValue(65)
        self.lbl_cycle_status.setText("Status: Gaveta fechando com berço vazio para calibração de escuro...")
        self._show_drawer_alert("Berço vazio confirmado. Fechando gaveta...", "FECHAMENTO DE GAVETA EM ANDAMENTO")
        self.send_serial_command("CMD:FECHAR_GAVETA")

    def _handle_white_calibration_fsm(self, status_tag: str):
        # 1. Gaveta Fechada após confirmação do Popup 1 (Branco)
        if status_tag == "GAVETA_FECHADA" and self.fsm_state == "CALIB_ETAPA1_FECHANDO_GAVETA":
            self.fsm_state = "CALIB_ETAPA1_AVANCANDO_SENSOR"
            self.cycle_progress.setValue(25)
            is_dry = (self.chem_engine.active_mode == "seco")
            lbl_pos = "Posicionando sensor sobre padrão branco seco..." if is_dry else "Posicionando sensor sobre a lâmina de água..."
            self.lbl_cycle_status.setText(f"Status: Gaveta fechada. {lbl_pos}")
            self.log_message("[CALIBRAÇÃO ETAPA 1] Avançando sensor (CMD:AVANCAR_SENSOR)")
            alert_msg = "Medindo Cartão branco fosco com radiação NIR ativa..." if is_dry else "Medindo Branco óptico (Água Destilada) com radiação NIR ativa..."
            self._show_radiation_alert(alert_msg)
            self.send_serial_command("CMD:AVANCAR_SENSOR")

        # 2. Sensor Avançado sobre o Branco -> Dispara leitura
        elif status_tag == "SENSOR_AVANCADO" and self.fsm_state == "CALIB_ETAPA1_AVANCANDO_SENSOR":
            self.fsm_state = "CALIB_ETAPA1_LENDO_ESPECTRO"
            self.cycle_progress.setValue(35)
            is_dry = (self.chem_engine.active_mode == "seco")
            lbl_read = "Medindo Padrão Branco Seco (cartão branco fosco)..." if is_dry else "Medindo Branco óptico (Água Destilada)..."
            self.lbl_cycle_status.setText(f"Status: {lbl_read}")
            self.log_message("[CALIBRAÇÃO ETAPA 1] Disparando leitura de branco (CMD:LER_ESPECTRO)")
            self.send_serial_command("CMD:LER_ESPECTRO")

        # 3. Leitura do Branco Concluída -> Registra e recua sensor
        elif status_tag == "LEITURA_CONCLUIDA" and self.fsm_state == "CALIB_ETAPA1_LENDO_ESPECTRO":
            self._temp_vetor_branco = list(self._last_raw_payload)
            self.fsm_state = "CALIB_ETAPA1_RECUANDO_SENSOR"
            self.cycle_progress.setValue(50)
            self.lbl_cycle_status.setText("Status: Leitura de branco registrada. Recuando sensor para repouso...")
            self.log_message(f"[CALIBRAÇÃO BRANCO] Vetor gravado: {self._temp_vetor_branco}")
            self.log_message("[CALIBRAÇÃO ETAPA 1] Recuando sensor (CMD:RECUAR_SENSOR)")
            self.send_serial_command("CMD:RECUAR_SENSOR")

        # 4. Sensor Recuado -> Ejeção segura: Abre gaveta para retirada da lâmina
        elif status_tag == "SENSOR_RECUADO" and self.fsm_state == "CALIB_ETAPA1_RECUANDO_SENSOR":
            self._hide_radiation_alert()
            self.fsm_state = "CALIB_ETAPA1_ABRINDO_GAVETA"
            self.cycle_progress.setValue(58)
            self.lbl_cycle_status.setText("Status: Sensor em repouso. Abrindo gaveta para retirada da lâmina...")
            self.log_message("[CALIBRAÇÃO ETAPA 1] Abrindo gaveta para ejeção (CMD:ABRIR_GAVETA)")
            self._show_drawer_alert("Abrindo gaveta para transição de amostra...", "ABERTURA DE GAVETA EM ANDAMENTO")
            self.send_serial_command("CMD:ABRIR_GAVETA")

        # 5. Cancelamento no Popup 1 -> Gaveta fechada e sistema liberado
        elif status_tag == "GAVETA_FECHADA" and self.fsm_state == "CALIB_CANCELANDO_FECHANDO_GAVETA":
            self.fsm_state = "IDLE"
            self.is_calibrating_white = False
            self._pending_routine = None
            self.cycle_progress.setValue(0)
            self._enable_controls()
            self.lbl_cycle_status.setText("Status: Calibração cancelada. Gaveta fechada e sistema pronto.")
            self.log_message("[CALIBRAÇÃO] Gaveta fechada em segurança. Rotina cancelada.")

        # 6. Conclusão apenas com Branco (Popup 2 ou 3) -> Gaveta fechada e Branco salvo
        elif status_tag == "GAVETA_FECHADA" and self.fsm_state == "CALIB_CONCLUSAO_FECHANDO_GAVETA":
            self.fsm_state="IDLE"
            self.is_calibrating_white=False
            self._pending_routine=None
            self._white_scans=[]
            self._dark_scans=[]
            self._enable_controls()
            self.lbl_cycle_status.setText("Calibração incompleta descartada; referência anterior preservada.")

        # 7. ETAPA 2: Gaveta Fechada com Berço Vazio -> Avança sensor para escuro
        elif status_tag == "GAVETA_FECHADA" and self.fsm_state == "CALIB_ETAPA2_FECHANDO_GAVETA":
            self.fsm_state = "CALIB_ETAPA2_AVANCANDO_SENSOR"
            self.cycle_progress.setValue(70)
            self.lbl_cycle_status.setText("Status: Gaveta fechada com berço vazio. Avançando sensor para escuro...")
            self.log_message("[CALIBRAÇÃO ETAPA 2] Avançando sensor para escuro (CMD:AVANCAR_SENSOR)")
            self._hide_radiation_alert()
            self.send_serial_command("CMD:AVANCAR_SENSOR")

        # 8. ETAPA 2: Sensor Avançado -> Mede Fundo Escuro
        elif status_tag == "SENSOR_AVANCADO" and self.fsm_state == "CALIB_ETAPA2_AVANCANDO_SENSOR":
            self.fsm_state = "CALIB_ETAPA2_LENDO_ESPECTRO"
            self.cycle_progress.setValue(80)
            self.lbl_cycle_status.setText("Status: Medindo Fundo Escuro no compartimento óptico vazio...")
            self.log_message("[CALIBRAÇÃO ETAPA 2] Escuro real: CMD:LER_ESCURO")
            self.send_serial_command("CMD:LER_ESCURO")

        # 9. ETAPA 2: Leitura do Escuro Concluída -> Registra e recua sensor
        elif status_tag == "LEITURA_CONCLUIDA" and self.fsm_state == "CALIB_ETAPA2_LENDO_ESPECTRO":
            self._temp_vetor_escuro = list(self._last_raw_payload)
            self.fsm_state = "CALIB_ETAPA2_RECUANDO_SENSOR"
            self.cycle_progress.setValue(92)
            self.lbl_cycle_status.setText("Status: Fundo escuro gravado. Recuando sensor para repouso seguro...")
            self.log_message(f"[CALIBRAÇÃO ESCURO] Vetor gravado: {self._temp_vetor_escuro}")
            self.log_message("[CALIBRAÇÃO ETAPA 2] Recuando sensor (CMD:RECUAR_SENSOR)")
            self.send_serial_command("CMD:RECUAR_SENSOR")

        # 10. ETAPA 2: Sensor Recuado -> Encerramento Seguro (GAVETA NÃO É ABERTA!)
        elif status_tag == "SENSOR_RECUADO" and self.fsm_state == "CALIB_ETAPA2_RECUANDO_SENSOR":
            self._hide_radiation_alert()
            self.fsm_state = "IDLE"
            self.is_calibrating_white = False
            self._pending_routine = None
            self.cycle_progress.setValue(100)
            self._enable_controls()

            if not self._save_measured_calibration():
                return

            self.lbl_cycle_status.setText("Status: Calibração completa (Branco e Escuro) realizada. Gaveta fechada em repouso.")
            self.log_message(f"[CALIBRAÇÃO COMPLETA] Branco e Escuro ({self.chem_engine.active_mode}) gravados em calibracao.json. Gaveta fechada e sistema pronto.")

            QMessageBox.information(
                self,
                "Calibração Completa",
                f"Calibração completa ({self.chem_engine.active_mode.capitalize()}) realizada com sucesso.\nSistema em repouso pronto para medições."
            )

    def _update_calibration_badge(self):
        eng=self.chem_engine
        valid=eng.calibration_valid()
        label="REFERÊNCIA VÁLIDA" if valid else ("EXPIRADA" if eng.is_calibrated and eng.is_calibration_expired() else "RECALIBRAR")
        self.badge_calib.set_active(valid,label,custom_color="#10B981" if valid else "#EF4444")
        self._refresh_controls()

    def atualizar_kpi_calibracao(self, r2=None, rmse=None, n_amostras=0):
        """
        Método de Atualização Dinâmica do Card KPI de Calibração:
        - Atualiza os textos dos labels numéricos (R², RMSE, N).
        - Aplica o estilo e a cor correspondente no badge de validação visual e metadados.
        - Conecta a atualização na janela principal e no diálogo de calibração ativo.
        """
        eng = self.chem_engine
        is_expired = eng.is_calibration_expired()
        ts = eng.calib_timestamp
        op = getattr(eng, "calib_operador", "Qualidade")

        if hasattr(self, "card_calibracao"):
            self.card_calibracao.atualizar(
                r2=r2, rmse=rmse, n_amostras=n_amostras,
                timestamp=ts, operador=op, is_expired=is_expired
            )
        if hasattr(self, "_active_calib_dialog") and self._active_calib_dialog:
            self._active_calib_dialog.card_kpi.atualizar(
                r2=r2, rmse=rmse, n_amostras=n_amostras,
                timestamp=ts, operador=op, is_expired=is_expired
            )
        self._update_calibration_badge()

    def _check_calibration_validity(self):
        """Verifica a validade temporal da calibração a cada 5s e aplica intertravamentos/alertas."""
        eng = self.chem_engine
        is_expired = eng.is_calibration_expired()
        self.atualizar_kpi_calibracao(r2=eng.r2, rmse=eng.rmse, n_amostras=eng.n_amostras)

        if is_expired and eng.is_calibrated and self.fsm_state=="IDLE" and not self._manual_pending and not getattr(self, "_last_expired_alert_shown", False):
            self._last_expired_alert_shown = True
            self.log_message(f"[METROLOGIA] Calibração do modo {eng.active_mode.upper()} EXPIRADA. Intertravamento ativo.")
            if getattr(self, "fsm_state", "IDLE") == "IDLE":
                dlg = CalibrationExpiredDialog(self, active_mode=eng.active_mode)
                if dlg.exec_() == QDialog.Accepted:
                    self.start_white_calibration_cycle()
        elif not is_expired and eng.is_calibrated:
            self._last_expired_alert_shown = False


    # -----------------------------------------------------------------
    # D. PARADA DE EMERGÊNCIA (E-STOP)
    # -----------------------------------------------------------------
    def stop_cycle_action(self):
        self.equipment.cancel()
        """
        Ao clicar em [ Parada de Emergência ]:
        1. Interrupção de Fluxo: Cancela imediatamente qualquer QTimer ou execução em andamento.
        2. Despacho Prioritário: Envia imediatamente CMD:EMERGENCIA\\n através da conexão ativa.
        3. Bloqueio e Feedback:
           - Trava temporariamente os botões de ciclo por ~1,5 segundo (tempo de recolhimento suave do ESP32).
           - Atualiza a barra de status ou badge para: "EMERGÊNCIA ACIONADA - BANCADA EM REPOUSO".
        """
        self._operation_epoch += 1
        self.log_message("PARADA DE EMERGÊNCIA ACIONADA PELO OPERADOR!")
        self._clear_cycle_timers()
        self._hide_drawer_alert()
        self._hide_radiation_alert()

        # Reseta flags operacionais e aborta fluxos
        self.auto_cycle_active = False
        self.modo_repetibilidade = False
        self.is_calibrating_white = False
        self._pending_routine = None
        self.fsm_state = "EMERGENCIA"

        # Cancela timers pendentes de botões manuais
        for status, (btn, timer) in list(self._manual_pending.items()):
            try:
                timer.stop()
            except Exception:
                pass
        self._manual_pending.clear()

        # Envia com prioridade máxima CMD:EMERGENCIA\n
        self._batch=None
        self._acquisition_timer.stop()
        self._hardware_watchdog.stop()
        self._result_valid=False
        self._emergency_confirmed=False
        sent = bool(self.serial_worker.send_emergency())
        self._emergency_sent = sent
        self._hardware_watchdog.start(10000)

        # Bloqueia UI e sinaliza o status exato solicitado
        self._disable_controls()
        self.cycle_progress.setValue(0)
        if sent:
            self.lbl_cycle_status.setText("EMERGÊNCIA ENVIADA — aguardando confirmação da bancada")
            self.lbl_cycle_status.setStyleSheet("color: #EF4444; font-size: 12px; font-weight: 900;")
        else:
            self.log_message("PARADA NÃO ENVIADA: sem conexão com a bancada. Use o botão de emergência físico.")
            self.lbl_cycle_status.setText("PARADA NÃO ENVIADA — sem conexão. Use o botão de emergência físico.")
            self.lbl_cycle_status.setStyleSheet("color: #FFFFFF; background-color: #B91C1C; font-size: 12px; font-weight: 900; padding: 4px;")

        # Trava temporariamente os botões de ciclo por ~1,5s
        self._emergency_lock_active = True
        self._emergency_lock_timer = QTimer(self)
        self._emergency_lock_timer.setSingleShot(True)
        self._emergency_lock_timer.timeout.connect(self._on_emergency_lock_timeout)
        self._emergency_lock_timer.start(1500)
        self._cycle_timers.append(self._emergency_lock_timer)

    def _on_emergency_lock_timeout(self):
        self._emergency_lock_active=False
        if self._emergency_confirmed:
            self.fsm_state="IDLE"
            self._refresh_controls()
            self.lbl_cycle_status.setText("Repouso confirmado pelo hardware.")
        elif getattr(self, "_emergency_sent", True):
            self.lbl_cycle_status.setText("Aguardando confirmação de emergência do ESP32.")

    def _handle_emergency_confirmed(self):
        self.equipment.cancel()
        self._operation_epoch += 1
        self._emergency_confirmed=True
        self._hardware_watchdog.stop()
        self._hide_radiation_alert()
        self._hide_drawer_alert()
        self._batch=None
        self._acquisition_timer.stop()
        for button,timer in self._manual_pending.values():
            timer.stop()
        self._manual_pending.clear()
        if not self._emergency_lock_active:
            self.fsm_state="IDLE"
            self._refresh_controls()
            self.lbl_cycle_status.setText("Emergência confirmada; bancada em repouso.")

    def _clear_cycle_timers(self):
        for t in self._cycle_timers:
            try:
                t.stop()
            except Exception:
                pass
        self._cycle_timers.clear()

    # -----------------------------------------------------------------
    # PROCESSAMENTO DE DADOS, QUIMIOMETRIA E GRÁFICOS
    # -----------------------------------------------------------------
    def process_raw_spectral_data(self, raw_values: List[float], persist=True):
        try:
            r_calibrated=self.chem_engine.calculate_relative_reflectance(raw_values)
        except (ValueError,TypeError) as err:
            self._fail_operation("Leitura rejeitada: "+str(err))
            return False
        self.current_scan_data=[float(v) for v in raw_values]
        self._current_reading_timestamp=datetime.datetime.now().strftime("%d/%m/%Y %H:%M:%S")
        self._current_reading_operator=getattr(self, "current_operator_name", "Operador não autenticado")
        self._current_calibration_snapshot=self.chem_engine.snapshot()
        self._result_valid=True

        self.current_r_calibrated = r_calibrated

        # 2. Normalização Vetorial pela soma (R_norm)
        r_snv = self.chem_engine.normalize_snv(r_calibrated)
        self.current_r_snv = r_snv

        # 3. Razões de Celulose e Água
        ratio_cel, ratio_water = self.chem_engine.calculate_scatter_ratios(r_snv)

        # 4. Atualiza Gráfico Espectral (Barras + Spline)
        self.spectral_chart.update_spectrum(self.current_scan_data, r_calibrated=r_calibrated, r_snv=r_snv)

        # 5. Atualiza KPI Cards
        total_adc = sum(self.current_scan_data)
        self.kpi_energy.set_value(f"{int(total_adc):,} ADC".replace(",", "."), "Soma das 6 bandas NIR")

        # Pico Dominante
        max_idx = self.current_scan_data.index(max(self.current_scan_data))
        dom_wl = WAVELENGTHS[max_idx]
        self.kpi_peak.set_value(f"{dom_wl} nm", f"Canal {CHANNEL_NAMES[max_idx]} ({int(self.current_scan_data[max_idx])} ADC)")

        self.kpi_ratio_cel.set_value(f"{ratio_cel:.2f}", "R680 / R730")
        self.kpi_ratio_water.set_value(f"{ratio_water:.2f}", "R860 / R760")
        try:
            import detail_windows
            detail_windows.record_reading(self, self.current_scan_data, r_snv)   # estado nos cartões e janelas abertas
        except Exception as err:
            self.log_message(f"Detalhes dos indicadores indisponíveis: {err}")

        # 6. Estimativa de Número Kappa e Classificação Industrial
        kappa_predito, kappa_status, kappa_color = calculate_kappa_number(
            r_calibrated if self.chem_engine.active_mode == "seco" else r_snv,
            mode=self.chem_engine.active_mode
        )

        # Garante cálculo de Kappa sem trava de teto (sem min(..., 50.0)), mantendo apenas proteção contra negativos
        kappa_exibido = max(0.0, float(kappa_predito))

        classificacao,kappa_color=self._classify_kappa(kappa_exibido)

        self.current_kappa_value = kappa_exibido
        self.current_kappa_status = classificacao
        self.current_ratio_cel = ratio_cel
        self.current_ratio_water = ratio_water

        # 7. Atualiza Card de Caracterização Quantitativa
        mode_desc = "Amostra Seca (Reflectância Difusa)" if self.chem_engine.active_mode == "seco" else "Suspensão Aquosa (Lâmina / Água)"
        self.lbl_kappa_valor.setText(f"{kappa_exibido:.2f}")
        self.lbl_kappa_classificacao.setText(classificacao)
        self.lbl_kappa_classificacao.setStyleSheet(f"color: {kappa_color}; font-size: 11px; font-weight: bold;")

        self.lbl_metodo_info.setText(f"Método: {mode_desc} | Kappa demonstrativo, sem validação analítica")

        # 7.1 Atualiza Diagnóstico & Telemetria do Sensor AS7263
        if hasattr(self, "card_telemetria") and self.card_telemetria is not None:
            is_sat = any(v >= 65500 for v in self.current_scan_data)
            self.card_telemetria.atualizar_telemetria(
                saturation=is_sat,
                status="Saturação detectada" if is_sat else "Leitura válida"
            )

        # 8. Persistência Automática no Histórico Completo de Ensaios
        try:
            amostra_nome = getattr(self, "input_sample_id", None)
            cod_amostra = self._current_sample_id or (amostra_nome.text().strip() if (amostra_nome and amostra_nome.text().strip()) else "AM-"+uuid.uuid4().hex[:8].upper())
            dados_leitura = {
                "codigo_amostra": cod_amostra,
                "timestamp": self._current_reading_timestamp,
                "operador": self._current_reading_operator,
                "metodo_analitico": mode_desc,
                "intensidade_global_adc": int(total_adc),
                "pico_espectral_nm": dom_wl,
                "pico_espectral_adc": int(self.current_scan_data[max_idx]),
                "razao_celulose": ratio_cel,
                "razao_agua": ratio_water,
                "kappa_estimado": kappa_exibido,
                "kappa_classificacao": classificacao,
                "adc_610": float(self.current_scan_data[0]),
                "adc_680": float(self.current_scan_data[1]),
                "adc_730": float(self.current_scan_data[2]),
                "adc_760": float(self.current_scan_data[3]),
                "adc_810": float(self.current_scan_data[4]),
                "adc_860": float(self.current_scan_data[5]),
                "ref_610": float(r_calibrated[0] * 100.0),
                "ref_680": float(r_calibrated[1] * 100.0),
                "ref_730": float(r_calibrated[2] * 100.0),
                "ref_760": float(r_calibrated[3] * 100.0),
                "ref_810": float(r_calibrated[4] * 100.0),
                "ref_860": float(r_calibrated[5] * 100.0),
            }
            dados_leitura["calibration_id"]=self.chem_engine.calibration_id
            dados_leitura["calibration_snapshot"]=json.dumps(self._current_calibration_snapshot,ensure_ascii=False)
            dados_leitura["acquisition_count"]=len(self._last_acquisition_scans)
            dados_leitura["raw_scans_json"]=json.dumps(self._last_acquisition_scans)
            if persist and hasattr(self, "auth_manager") and self.auth_manager is not None:
                leitura_id = self.auth_manager.inserir_leitura(dados_leitura)
                self.log_message(f"Ensaio registrado no Histórico (ID #{leitura_id}).")
        except Exception as e:
            self.log_message(f"Aviso ao persistir histórico: {e}")

        self.log_message(
            f"Análise Concluída: Kappa={kappa_exibido:.2f} ({classificacao}) | Modo: {self.chem_engine.active_mode.upper()} | Celulose(R680/730)={ratio_cel:.2f}"
        )

    def load_database_dict(self) -> dict:
        if os.path.exists(self.db_path):
            try:
                with open(self.db_path, "r", encoding="utf-8") as f:
                    return json.load(f)
            except Exception as e:
                self.log_message(f"Erro ao ler banco: {e}")
        return {}

    def find_best_match_hybrid(self, sample_vec):
        db = self.load_database_dict()
        if not db:
            return "Sem Banco de Dados", 0.0, False

        best_material = "Material Não Identificado"
        best_score = 0.0
        best_penalized = False

        for name, ref_vec in db.items():
            score, pen = calculate_hybrid_similarity(sample_vec, ref_vec, calib_engine=self.chem_engine)
            if score > best_score:
                best_score = score
                best_material = name
                best_penalized = pen

        return best_material, best_score, best_penalized

    # -----------------------------------------------------------------
    # GESTÃO DE ESTADO DOS CONTROLES
    # -----------------------------------------------------------------
    def _enable_controls(self):
        self._refresh_controls()

    def _disable_controls(self):
        self.btn_start_scan.setEnabled(False)
        self.btn_repeatability.setEnabled(False)
        self.btn_calibrate.setEnabled(False)
        self.btn_man_open_door.setEnabled(False)
        self.btn_man_close_door.setEnabled(False)
        self.btn_man_open_drawer.setEnabled(False)
        self.btn_man_close_drawer.setEnabled(False)
        self.btn_man_fwd_sensor.setEnabled(False)
        self.btn_man_back_sensor.setEnabled(False)
        self.btn_man_read.setEnabled(False)
        # O botão de emergência principal permanece sempre habilitado
        if hasattr(self, "btn_emergency_auto"):
            self.btn_emergency_auto.setEnabled(True)
        if hasattr(self, "btn_top_emergency"):
            self.btn_top_emergency.setEnabled(True)

    # -----------------------------------------------------------------
    # ALERTA DE SEGURANÇA CONTRA RADIAÇÃO ÓPTICA (NIR)
    # -----------------------------------------------------------------
    def _show_radiation_alert(self, text_custom: str = None):
        self.log_message(f"[SEGURANÇA NIR] Radiação óptica ativa: {text_custom or 'Varredura em andamento'}")
        if self._radiation_dialog is None:
            self._radiation_dialog = DialogAlertaRadiacao(self)
        if text_custom:
            self._radiation_dialog.set_custom_status(text_custom)
        self._radiation_dialog.show()

    def _hide_radiation_alert(self):
        if self._radiation_dialog is not None:
            try:
                self._radiation_dialog.close()
            except Exception:
                pass

    # -----------------------------------------------------------------
    # ALERTA DE SEGURANÇA MECÂNICA (MOVIMENTAÇÃO DE GAVETA)
    # -----------------------------------------------------------------
    def is_in_automated_routine(self) -> bool:
        """Retorna True se o supervisório estiver executando uma rotina automática."""
        if hasattr(self, "control_tabs") and self.control_tabs.currentIndex() == 1:
            return False
        if self._manual_dialog is not None:
            return False
        return (
            self.auto_cycle_active or
            self.modo_repetibilidade or
            self.is_calibrating_white or
            self.fsm_state not in ("IDLE", "EMERGENCIA")
        )

    def _show_drawer_alert(self, text_custom: str = None, detail: str = "MOVIMENTAÇÃO DE GAVETA EM ANDAMENTO"):
        """Abre o diálogo de alerta mecânico com bypass explícito para acionamentos manuais."""
        if not self.is_in_automated_routine():
            return

        self.log_message(f"[SEGURANÇA MECÂNICA] Gaveta em movimento: {text_custom or detail}")
        if self._drawer_dialog is None:
            self._drawer_dialog = DialogAlertaGaveta(self)
        if text_custom:
            self._drawer_dialog.set_action_status(text_custom, detail)
        self._drawer_dialog.show()

    def _hide_drawer_alert(self):
        """Fecha o diálogo de alerta mecânico imediatamente."""
        if self._drawer_dialog is not None:
            try:
                self._drawer_dialog.close()
            except Exception:
                pass

    @property
    def dialogo_gaveta(self) -> DialogAlertaGaveta:
        """Instância do diálogo de alerta mecânico de gaveta."""
        if self._drawer_dialog is None:
            self._drawer_dialog = DialogAlertaGaveta(self)
        return self._drawer_dialog

    @property
    def dialogo_radiacao(self) -> DialogAlertaRadiacao:
        """Instância do diálogo de alerta óptico de radiação NIR."""
        if self._radiation_dialog is None:
            self._radiation_dialog = DialogAlertaRadiacao(self)
        return self._radiation_dialog

    # -----------------------------------------------------------------
    # -----------------------------------------------------------------
    # CONTROLE DE ACESSO E GESTÃO DE MODOS (MANUAL / AUTO)
    # -----------------------------------------------------------------
    def _on_control_tab_changed(self, index: int):
        """
        Intercepta a mudança para a aba de Modo Manual (index == 1).
        Exige autenticação via DialogLogin. Se cancelado ou incorreto,
        reverte imediatamente para a aba de Ensaios Automáticos (index == 0).
        """
        if index == 1:
            if not self.is_manual_mode_unlocked:
                dlg = DialogLogin(self.auth_manager, self)
                accepted = (dlg.exec_() == QDialog.Accepted)
                if accepted:
                    self.authenticated_user = dlg.usuario_logado

                if accepted and self.authenticated_user:
                    self.current_operator_name=self.authenticated_user.get("username", "Operador")
                    self.is_manual_mode_unlocked = True
                    u_name = self.authenticated_user.get("username", "operador")
                    role = self.authenticated_user.get("role", "operador").upper()
                    self.log_message(f"Modo Manual liberado para {u_name} ({role}).")
                else:
                    self.log_message("Acesso ao Modo Manual cancelado ou não autorizado.")
                    self.control_tabs.blockSignals(True)
                    self.control_tabs.setCurrentIndex(0)
                    self.control_tabs.blockSignals(False)
                    return
            self._refresh_controls()
        elif index == 0:
            # Ao sair do Modo Manual, exige autenticação novamente ao reentrar
            if self.is_manual_mode_unlocked:
                self.is_manual_mode_unlocked = False
                self.log_message("Modo Manual bloqueado ao alternar para Ensaios Automáticos.")
                self._refresh_controls()

    def switch_mode(self, mode: str):
        """Alterna entre abas para compatibilidade com rotinas externas."""
        if mode == "MANUAL":
            self.control_tabs.setCurrentIndex(1)
        else:
            self.control_tabs.setCurrentIndex(0)

    def open_user_management_dialog(self):
        """
        Abre a tela de Gerenciamento de Usuários (DialogGestaoUsuarios).
        Exige autenticação prévia com perfil 'admin'.
        """
        if not self.authenticated_user or self.authenticated_user.get("role") != "admin":
            dlg = DialogLogin(self.auth_manager, self)
            accepted = (dlg.exec_() == QDialog.Accepted)
            if accepted:
                self.authenticated_user = dlg.usuario_logado

            if not accepted or not self.authenticated_user:
                return

            if self.authenticated_user.get("role") != "admin":
                QMessageBox.warning(
                    self,
                    "Acesso Negado",
                    "Apenas usuários com perfil de 'Administrador' podem gerenciar usuários."
                )
                self.log_message("Aviso: Tentativa de acesso negada ao Gerenciador de Usuários (Requer Admin).")
                return

        self.current_operator_name=self.authenticated_user.get("username", "Operador")
        dlg_gestao = DialogGestaoUsuarios(
            auth_manager=self.auth_manager,
            current_user=self.authenticated_user,
            parent=self
        )
        dlg_gestao.exec_()
        self.log_message("Gerenciador de Usuários finalizado.")

    def logout_action(self):
        """
        Bloqueia as abas restritas e desloga a sessão ativa.
        """
        user_name = self.authenticated_user.get("username", "Usuário") if self.authenticated_user else "Operador"
        if self.equipment.authorized or self.equipment.pending or (self.equipment.manual_motion and self._manual_pending):
            self._fail_operation("Sessão encerrada durante uma operação manual ou autorizada.")
        self.equipment.revoke()
        self.authenticated_user = None
        self.is_manual_mode_unlocked = False
        self.current_operator_name = "Operador não autenticado"

        if hasattr(self, "control_tabs") and self.control_tabs.currentIndex() != 0:
            self.control_tabs.blockSignals(True)
            self.control_tabs.setCurrentIndex(0)
            self.control_tabs.blockSignals(False)

        self.log_message(f"Logout realizado com sucesso ({user_name}). Painel manual bloqueado.")
        QMessageBox.information(
            self, "Painel Bloqueado",
            "Sessão encerrada com sucesso.\nO painel manual foi bloqueado."
        )

    # -----------------------------------------------------------------
    # UTILIDADES E DIÁLOGOS
    # -----------------------------------------------------------------
    def open_calibration_dialog(self):
        dlg = CalibrationModalDialog(self)
        self._active_calib_dialog = dlg
        eng = self.chem_engine
        if eng.is_calibrated:
            dlg.card_kpi.atualizar(r2=eng.r2, rmse=eng.rmse, n_amostras=eng.n_amostras)
        else:
            dlg.card_kpi.atualizar(r2=None, rmse=None, n_amostras=0)
        dlg.exec_()
        self._active_calib_dialog = None

    def open_manual_control_dialog(self):
        """Abre o painel de atuadores com autenticação prévia."""
        if not self.is_manual_mode_unlocked:
            dlg = DialogLogin(self.auth_manager, self)
            accepted = (dlg.exec_() == QDialog.Accepted)
            if accepted:
                self.authenticated_user = dlg.usuario_logado

            if not accepted or not self.authenticated_user:
                self.log_message("Acesso ao Painel de Atuadores cancelado ou não autorizado.")
                return

            self.is_manual_mode_unlocked = True
            self.current_operator_name=self.authenticated_user.get("username", "Operador")

        self._refresh_controls()
        self._manual_dialog = ManualControlDialog(self)
        self._manual_dialog.exec_()
        self._manual_dialog = None

    def open_history_dialog(self):
        auth_db = getattr(self, "auth_manager", None)
        if not auth_db:
            auth_db = DatabaseManager(get_database_path("usuarios.db"))
        dlg = HistoryDialog(auth_db, parent=self)
        dlg.exec_()
        self.log_message("Histórico de Ensaios sincronizado.")

    def open_database_manager(self):
        self.open_history_dialog()

    def export_pdf_report(self):
        if not self._result_valid or not self.current_scan_data or sum(self.current_scan_data) == 0:
            QMessageBox.warning(self, "Aviso", "Realize uma análise espectral antes de gerar o relatório experimental.")
            return

        default_filename = f"Relatorio_Espectral_{datetime.datetime.now().strftime('%Y%m%d_%H%M%S')}.pdf"
        file_path, _ = QFileDialog.getSaveFileName(
            self, "Salvar Relatório Experimental PDF", default_filename, "Arquivos PDF (*.pdf)"
        )
        if file_path:
            try:
                op_mode = self.chem_engine.active_mode if hasattr(self, "chem_engine") else "seco"
                amostra_nome = getattr(self, "input_sample_id", None)
                cod_amostra = self._current_sample_id or (amostra_nome.text().strip() if (amostra_nome and amostra_nome.text().strip()) else "AM-"+uuid.uuid4().hex[:8].upper())

                # Coleta reflectâncias calibradas para plotagem percentual no laudo
                ref_plot = None
                if hasattr(self, "chem_engine"):
                    r_cal = self.current_r_calibrated
                    ref_plot = [r * 100.0 for r in r_cal]
                else:
                    ref_plot = self.current_scan_data

                dom_wl = None
                peak_adc = None
                if self.current_scan_data and len(self.current_scan_data) >= 6:
                    max_i = self.current_scan_data.index(max(self.current_scan_data))
                    dom_wl = WAVELENGTHS[max_i]
                    peak_adc = self.current_scan_data[max_i]

                out_pdf = generate_pdf_report(
                    filename=file_path,
                    sample_id=cod_amostra,
                    operator=self._current_reading_operator,
                    values=ref_plot,
                    raw_adc_values=self.current_scan_data,
                    com_port=self.combo_com.currentText() if hasattr(self, "combo_com") else "COM3",
                    kappa_value=self.current_kappa_value,
                    operational_mode=op_mode,
                    kappa_status=getattr(self, "current_kappa_status", None),
                    ratio_celulose=getattr(self, "current_ratio_cel", None),
                    ratio_agua=getattr(self, "current_ratio_water", None),
                    global_intensity_adc=sum(self.current_scan_data) if self.current_scan_data else None,
                    peak_wavelength_nm=dom_wl,
                    peak_intensity_adc=peak_adc,
                    calibration_snapshot=self._current_calibration_snapshot,
                    acquisition_count=len(self._last_acquisition_scans),
                    raw_scans=self._last_acquisition_scans,
                    timestamp=self._current_reading_timestamp
                )
                self.log_message(f"Relatório Experimental PDF emitido com sucesso: {out_pdf}")
                reply = QMessageBox.question(
                    self, "Relatório Gerado",
                    f"Relatório Experimental emitido com sucesso!\nArquivo: {os.path.basename(out_pdf)}\n\nDeseja visualizar o PDF agora?",
                    QMessageBox.Yes | QMessageBox.No, QMessageBox.Yes
                )
                if reply == QMessageBox.Yes:
                    try:
                        open_pdf(out_pdf)
                    except Exception as start_err:
                        QMessageBox.warning(
                            self, "Aviso de Visualização",
                            f"O relatório foi salvo com sucesso em:\n{out_pdf}\n\n"
                            f"Porém não foi possível acionar o leitor padrão do sistema: {start_err}"
                        )
            except PermissionError:
                QMessageBox.warning(
                    self, "Arquivo em Uso",
                    f"Não foi possível salvar o Relatório Experimental em:\n{file_path}\n\n"
                    "O arquivo está aberto e bloqueado por outro aplicativo (Adobe Reader, navegador, etc.).\n"
                    "Por favor, feche o visualizador de PDF ou escolha outro nome de arquivo."
                )
            except Exception as e:
                QMessageBox.critical(self, "Erro", f"Erro ao gerar Relatório PDF: {e}")

    def export_csv_log(self):
        if not self._result_valid or not self.current_scan_data or self.current_kappa_value is None:
            QMessageBox.warning(self, "Aviso", "Realize uma análise espectral válida antes de exportar os dados.")
            return
        default_filename = f"Ensaio_Espectral_{datetime.datetime.now().strftime('%Y%m%d_%H%M%S')}.csv"
        file_path, _ = QFileDialog.getSaveFileName(
            self, "Exportar Dados CSV", default_filename, "Arquivos CSV (*.csv)"
        )
        if file_path:
            temporary = None
            try:
                with tempfile.NamedTemporaryFile("w", newline="", encoding="utf-8-sig", dir=os.path.dirname(os.path.abspath(file_path)), delete=False) as f:
                    temporary = f.name
                    writer = csv.writer(f)
                    writer.writerow([
                        "DataHora_Medicao", "Codigo_Amostra", "Operador", "Modo", "Calibracao_ID", "Aquisoes", "Kappa_Demonstrativo",
                        "610nm_ADC", "680nm_ADC", "730nm_ADC", "760nm_ADC", "810nm_ADC", "860nm_ADC",
                        "610nm_Resposta_Percent", "680nm_Resposta_Percent", "730nm_Resposta_Percent",
                        "760nm_Resposta_Percent", "810nm_Resposta_Percent", "860nm_Resposta_Percent",
                        "Razao_R680_R730", "Razao_R860_R760", "R_Norm_680", "R_Norm_730", "R_Norm_760", "R_Norm_860"
                    ])
                    r_snv = self.current_r_snv if len(self.current_r_snv) == 6 else [0.0] * 6
                    writer.writerow([
                        self._current_reading_timestamp,
                        self._current_sample_id,
                        self._current_reading_operator,
                        self.chem_engine.active_mode,
                        (self._current_calibration_snapshot or {}).get("calibration_id", ""),
                        len(self._last_acquisition_scans),
                        f"{self.current_kappa_value:.4f}",
                        *self.current_scan_data,
                        *[value*100 for value in self.current_r_calibrated],
                        self.current_ratio_cel, self.current_ratio_water,
                        f"{r_snv[1]:.4f}", f"{r_snv[2]:.4f}", f"{r_snv[3]:.4f}", f"{r_snv[5]:.4f}"
                    ])
                    f.flush()
                    os.fsync(f.fileno())
                os.replace(temporary, file_path)
                self.log_message(f"Dados exportados para CSV: {file_path}")
                QMessageBox.information(self, "Sucesso", "Dados exportados em CSV com sucesso!")
            except Exception as e:
                QMessageBox.critical(self, "Erro", f"Erro ao exportar CSV: {e}")
            finally:
                if temporary and os.path.exists(temporary):
                    os.unlink(temporary)

    def closeEvent(self, event):
        """Ao fechar o aplicativo, encerra a conexão de forma segura."""
        em_operacao = (self.fsm_state != "IDLE" or self.auto_cycle_active or self.modo_repetibilidade
                       or self.is_calibrating_white or self._batch is not None
                       or self.equipment.authorized or self.equipment.pending)
        if em_operacao and self.is_serial_connected():
            resp = QMessageBox.warning(
                self, "Operação em andamento",
                "Há um movimento ou ensaio em andamento na bancada.<br><br>"
                "Fechar o aplicativo agora envia <b>PARADA DE EMERGÊNCIA</b>. A gaveta ou o carrinho "
                "podem ficar em posição intermediária.<br><br>Deseja fechar mesmo assim?",
                QMessageBox.Yes | QMessageBox.No, QMessageBox.No
            )
            if resp != QMessageBox.Yes:
                event.ignore()
                return
            self.serial_worker.send_emergency()
            time.sleep(0.3)  # dá tempo para a fila prioritária sair antes da desconexão
        if hasattr(self,"_scada_refresh_timer"):
            self._scada_refresh_timer.stop()
        self._calib_validity_timer.stop()
        self._clear_cycle_timers()
        self._hardware_watchdog.stop()
        self._acquisition_timer.stop()
        self._heartbeat_timer.stop()
        if self.serial_worker.is_connected():
            self.disconnect_hardware()
        event.accept()
    def _dispatch_batch_read(self):
        if self._batch is not None and (not self.equipment.drawer_closed or not self.equipment.closed
                or self.equipment.open or not self.equipment.carriage_advanced or self.equipment.carriage_retracted
                or (not self.equipment.housing_closed and not self.equipment.authorized)):
            self._fail_operation("Intertravamento aberto durante aquisição.")
            return
        if self._batch is None:
            return
        batch=self._batch
        batch["token"]=uuid.uuid4().hex
        batch["data"]=None
        if not self.serial_worker.send_command(batch["cmd"]+":"+batch["token"]):
            self._fail_operation("Falha ao solicitar aquisição.")
            return
        self._hardware_watchdog.start(4000)

    def _on_serial_scan_received(self,token,values):
        if self._batch is None or token!=self._batch["token"]:
            self.log_message("[AQUISIÇÃO] Pacote antigo/inesperado descartado.")
            return
        if self._batch["data"] is not None:
            self.log_message("[AQUISIÇÃO] Pacote duplicado descartado.")
            return
        try:
            self._batch["data"]=self.chem_engine.validate_raw(values,allow_zero=self._batch["cmd"]=="CMD:LER_ESCURO")
        except ValueError as err:
            self._fail_operation(str(err))

    def _complete_batch_read(self,token):
        batch=self._batch
        if batch is None or token!=batch["token"]:
            return
        if batch["data"] is None:
            self._fail_operation("Conclusão recebida sem dados novos da aquisição.")
            return
        self._hardware_watchdog.stop()
        batch["scans"].append(batch["data"])
        batch["token"]=""
        self.log_message(f"[AQUISIÇÃO] {len(batch['scans'])}/{batch['target']}")
        if len(batch["scans"])<batch["target"]:
            self._acquisition_timer.start(300)
            return
        scans=batch["scans"]
        means=self.chem_engine.compute_repeatability_stats(scans)["means"]
        command=batch["cmd"]
        self._batch=None
        self._last_acquisition_scans=[list(v) for v in scans]
        self._last_raw_payload=means
        if self.is_calibrating_white:
            if command=="CMD:LER_ESCURO":
                self._dark_scans=scans
            else:
                self._white_scans=scans
        self._on_serial_status_received("LEITURA_CONCLUIDA",_verified=True)

    def _on_hardware_timeout(self):
        self._fail_operation("Tempo limite do hardware: operação abortada. Aguarde confirmação de emergência.")

    def _fail_operation(self,message,send_stop=True):
        self.equipment.cancel()
        self._operation_epoch += 1
        self.log_message("[FALHA] "+message)
        if self._manual_dialog:
            self._manual_dialog.log("[FALHA] " + message)
        self._result_valid=False
        self.current_scan_data=[0.0]*6
        self.current_kappa_value=None
        self._last_raw_payload=[]
        self._batch=None
        self._hardware_watchdog.stop()
        self._acquisition_timer.stop()
        self._clear_cycle_timers()
        self.auto_cycle_active=False
        self.modo_repetibilidade=False
        self.is_calibrating_white=False
        self._pending_routine=None
        self._emergency_confirmed=False
        self.fsm_state="FALHA"
        self._hide_drawer_alert()
        self._hide_radiation_alert()
        for button,timer in self._manual_pending.values():
            timer.stop()
        self._manual_pending.clear()
        self._disable_controls()
        self.combo_op_mode.setEnabled(False)
        self.lbl_kappa_valor.setText("--")
        self.lbl_kappa_classificacao.setText("Resultado inválido — repetir aquisição")
        self.lbl_cycle_status.setText("Falha: "+message)
        if send_stop and self.is_serial_connected():
            self.serial_worker.send_emergency()

    def _ready_for_scan(self):
        return (self._protocol_ready and self._sensor_ready and self.is_serial_connected()
                and self.chem_engine.calibration_valid() and self.fsm_state=="IDLE"
                and self.equipment.capable and self.equipment.carriage_capable and self.equipment.carriage_retracted is not None and self.equipment.housing_closed is not None
                and not self.equipment.pending and not self._batch and not self._manual_pending and not self._emergency_lock_active)

    def _save_measured_calibration(self):
        ok=self.chem_engine.save_calibration(white_scans=self._white_scans,dark_scans=self._dark_scans,
            settings=self._optical_settings,operador=getattr(self,"current_operator_name","Operador"),
            reference_label=(ChemometricsEngine.REFERENCE_LABEL if self.chem_engine.active_mode=="seco"
                             else "Lâmina/lamínula com água destilada"),
            notes="Branco medido + escuro com LED desligado; referências relativas")
        if not ok:
            self._fail_operation("Calibração rejeitada/não salva: "+self.chem_engine.last_error)
            return False
        self._last_expired_alert_shown=False
        self._check_calibration_validity()
        return True

    def _update_scan_hint(self):
        """Mostra ao operador o que falta para 'Realizar leitura' (atualizado pelo cronômetro da tela)."""
        if not hasattr(self, "lbl_scan_hint"):
            return
        running = (self.fsm_state != "IDLE" or self._batch is not None or self._manual_pending
                   or self._emergency_lock_active or self.auto_cycle_active or self.modo_repetibilidade
                   or self.is_calibrating_white)
        if running:
            text = "Ensaio em andamento: acompanhe o status e a barra de progresso."
        else:
            text = scan_blocker(
                connected=self.is_serial_connected(),
                protocol_ready=bool(self._protocol_ready),
                sensor_ready=bool(self._sensor_ready),
                equipment_ready=bool(self.equipment.capable and self.equipment.carriage_capable),
                equipment_known=self.equipment.housing_closed is not None and self.equipment.carriage_retracted is not None,
                busy=bool(self.equipment.pending),
                calibration_valid=self.chem_engine.calibration_valid(),
                calibration_error=self.chem_engine.last_error or "",
            )
            text = text or "Pronto para leitura. Coloque a amostra no berço e clique em Realizar leitura."
        self.lbl_scan_hint.setText(text)
        self.btn_start_scan.setToolTip(text)

    def _refresh_controls(self):
        if not hasattr(self,"btn_start_scan"):
            return
        idle=(self.fsm_state=="IDLE" and not self._batch and not self._manual_pending
              and not self._emergency_lock_active)
        connected=self.is_serial_connected()
        ready=connected and self._protocol_ready and self._sensor_ready and self.equipment.capable and self.equipment.carriage_capable and self.equipment.housing_closed is not None
        mechanical_ready = connected and self._protocol_ready and self.equipment.manual_capable and self.equipment.carriage_capable and self.equipment.carriage_retracted is not None and self.equipment.housing_closed is not None
        idle = idle and not self.equipment.pending
        valid=self.chem_engine.calibration_valid()
        self.btn_start_scan.setEnabled(idle and ready and valid)
        self.btn_repeatability.setEnabled(idle and ready and valid)
        self.btn_calibrate.setEnabled(idle and ready)
        self.combo_op_mode.setEnabled(idle)
        for name in ("btn_man_open_door","btn_man_close_door","btn_man_open_drawer","btn_man_close_drawer","btn_man_fwd_sensor","btn_man_back_sensor"):
            getattr(self,name).setEnabled(idle and mechanical_ready and self.is_manual_mode_unlocked)
        chamber_closed = self.equipment.drawer_closed and self.equipment.closed and not self.equipment.open
        self.btn_man_fwd_sensor.setEnabled(idle and mechanical_ready and self.is_manual_mode_unlocked)
        self.btn_man_read.setEnabled(idle and ready and valid and self.is_manual_mode_unlocked and bool(chamber_closed)
                                    and bool(self.equipment.carriage_advanced) and not self.equipment.carriage_retracted)
        if idle and not self.equipment.admin_session():
            self.equipment.revoke()
        if self._manual_dialog:
            self._manual_dialog.update_interlocks_and_leds()

    @staticmethod
    def _classify_kappa(value):
        return classify_experimental_kappa(value)

    def _heartbeat_tick(self):
        if not self.is_serial_connected():
            return
        if time.monotonic()-self._last_pong>6:
            self._fail_operation("ESP32 sem resposta ao heartbeat.")
            self.serial_worker.disconnect_connection()
            self._protocol_ready=False
            self._sensor_ready=False
            return
        if self.equipment.admin_session() and not self._emergency_lock_active:
            if self.equipment.authorized:
                self.serial_worker.send_command("CMD:RENOVAR_CARCACA")
            elif self.equipment.admin_capable and not self.equipment.busy():
                self.serial_worker.send_command("CMD:ADMIN_CARCACA")
        elif self.equipment.authorized and self.equipment.busy():
            self.serial_worker.send_command("CMD:RENOVAR_CARCACA")
        self.serial_worker.send_command("CMD:PING")
        self._request_sensor_diagnostics()

    def _request_sensor_diagnostics(self):
        now=time.monotonic()
        if (not self.is_serial_connected() or not self._protocol_ready or not self._sensor_ready
                or self.fsm_state!="IDLE" or self._batch or self._manual_pending
                or self.equipment.pending or self.equipment.busy() or self._emergency_lock_active
                or now-getattr(self,"_last_diag_request",0.0)<5):
            return
        if self.serial_worker.send_command("CMD:DIAG_SENSOR"):
            self._last_diag_request=now


def global_exception_handler(exc_type, exc_value, exc_traceback):
    """Intercepta exceções não tratadas, grava no crash.log e exibe diálogo sem fechar a aplicação."""
    if issubclass(exc_type, KeyboardInterrupt):
        sys.__excepthook__(exc_type, exc_value, exc_traceback)
        return

    err_msg = "".join(traceback.format_exception(exc_type, exc_value, exc_traceback))
    try:
        crash_log_path = os.path.join(os.path.dirname(os.path.abspath(__file__)), "crash.log")
        with open(crash_log_path, "a", encoding="utf-8") as f:
            f.write(f"\n[{datetime.datetime.now().strftime('%Y-%m-%d %H:%M:%S')}] EXCEÇÃO NÃO TRATADA:\n{err_msg}\n")
    except Exception:
        pass

    print(f"[FATAL EXCEPTION]:\n{err_msg}", file=sys.stderr)
    try:
        QMessageBox.critical(
            None, "Erro Inesperado",
            f"Ocorreu um erro no supervisório:\n\n{exc_value}\n\nDetalhes registrados em crash.log."
        )
    except Exception:
        pass


sys.excepthook = global_exception_handler


# =====================================================================
# 5. PONTO DE ENTRADA
# =====================================================================
def main():
    QCoreApplication.setAttribute(Qt.AA_EnableHighDpiScaling, True)
    QCoreApplication.setAttribute(Qt.AA_UseHighDpiPixmaps, True)
    app = QApplication(sys.argv)
    app.setStyle("Fusion")
    ensure_theme_manager()
    app._dialog_screen_adapter = DialogScreenAdapter(app)
    app.installEventFilter(app._dialog_screen_adapter)

    splash = AnimatedSplashScreen()
    main_win = None

    def show_main():
        if main_win._start_maximized:
            main_win.showMaximized()
        else:
            main_win.show()

    splash.finished.connect(show_main)
    splash.start_animation()
    def initialize():
        nonlocal main_win
        splash.set_stage(15,"Carregando configurações e dados")
        main_win=SpectrumLabMainWindow()
        splash.set_stage(90,"Painel e controles preparados")
        splash.mark_ready()
    QTimer.singleShot(0,initialize)

    sys.exit(app.exec_())


if __name__ == "__main__":
    main()

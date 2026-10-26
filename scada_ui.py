"""Composição SCADA aprovada: controles à esquerda, bandas à direita, diagnóstico abaixo."""
from PyQt5.QtCore import Qt,QTimer,QSize,QPointF
from PyQt5.QtGui import QColor,QPainter,QRadialGradient
from PyQt5.QtWidgets import (QLineEdit,QWidget,QFrame,QLabel,QPushButton,QVBoxLayout,QHBoxLayout,QGridLayout,
                             QSplitter,QDialog,QSizePolicy,QScrollArea,QScroller)
import glass
import responsive_math
import typography as ty
import detail_windows
from animation_math import mix_hex
from analysis_indicator import AnalysisIndicator
from brand_assets import institutional_signature,program_logo_pixmap
from diagnostics import ControllerDiagnosticsCard
from responsive_layout import ScaledCanvasView
from version import __credits__,credits_html

class CanvasRoot(QWidget):
    """Raiz do painel: fundo liso do tema.

    Estilo plano (ISA-101): hoje só a cor de fundo é pintada; textura e brilho foram retirados."""
    def paint_background(self,painter):
        """Fundo completo (cor, textura e brilho ambiente). Usado também pela animação de entrada."""
        from appearance import palette_for,texture_pixmap
        p=palette_for()
        painter.fillRect(self.rect(),QColor(p['canvas']))
        tile=texture_pixmap()
        if not tile.isNull():painter.drawTiledPixmap(self.rect(),tile)
        w,h=self.width(),self.height()
        for fx,fy,radius,color,alpha in glass.glow_spec(p):
            center=QPointF(fx*w,fy*h);reach=radius*max(w,h)
            gradient=QRadialGradient(center,reach)
            inner=QColor(color);inner.setAlphaF(alpha)
            outer=QColor(color);outer.setAlpha(0)
            gradient.setColorAt(0.0,inner);gradient.setColorAt(1.0,outer)
            painter.fillRect(self.rect(),gradient)
    def paintEvent(self,event):
        painter=QPainter(self)
        self.paint_background(painter)
        painter.end()

def panel():
    box=QFrame();box.setObjectName('scadaPanel');return box

def label(text,role='body',muted=False,name=None):
    """Rótulo com um papel tipográfico (ver typography.ROLES). 'muted' usa a cor secundária do tema."""
    out=QLabel(text)
    if role in ('display','brand','title','section'):out.setProperty('role','heading')   # cor de título definida no tema
    out.setStyleSheet(('color: #9CA3AF; ' if muted else '')+ty.qss(role))
    if name:out.setObjectName(name)
    return out

def open_login(window):
    if window.authenticated_user:
        window.logout_action();return
    from auth_dialogs import DialogLogin
    dialog=DialogLogin(window.auth_manager,window)
    if dialog.exec_()==QDialog.Accepted and dialog.usuario_logado:
        window.authenticated_user=dialog.usuario_logado
        window.is_manual_mode_unlocked=True
        window.current_operator_name=dialog.usuario_logado.get('username','Operador')
        window.log_message('Sessão autenticada: '+window.current_operator_name)

def dashboard_style(p):
    """Folha de estilo do painel (ISA-101): superfícies planas, botões com tom por função, destaque roxo."""
    accent=p['accent_strong']
    rim=glass.rim(p);rim_soft=glass.rim(p,.6);rim_button=glass.rim(p,1.5)
    hover_border=p['accent']
    result_border=glass.tone_border(p,'accent')
    danger_hot=mix_hex(p['danger_strong'],'#FFFFFF',.25)
    busy=glass.button_fill(p,'hover')
    danger_fill=mix_hex(p['surface'],p['danger'],.20)
    tones=''.join(f'''QPushButton[tone="{t}"] {{background:{glass.tone_fill(p,t)};color:{glass.tone_text(p,t)};border:1px solid {glass.tone_border(p,t)};}}
QPushButton[tone="{t}"]:hover {{background:{glass.tone_fill(p,t,'hover')};border:1px solid {glass.tone_border(p,t,'hover')};}}
QPushButton[tone="{t}"]:pressed {{background:{glass.tone_hot(p,t)};color:{glass.on_tone(p)};border:1px solid {glass.tone_border(p,t,'hover')};}}
QPushButton[tone="{t}"]:disabled {{background:{glass.button_fill(p,'disabled')};color:{p['disabled']};border:1px solid {rim_soft};}}
QFrame[bar="{t}"] {{background:{glass.tone_color(p,t)};border:0;border-radius:2px;}}
''' for t in glass.TONES)
    return f'''QWidget#centralWidget {{color:{p['text']};}}
QLabel#brandTitle {{color:{p['heading']};}}
QLabel#kappaValue {{color:{p['accent']};}}
QLabel#credits {{color:{p['text']};}}
QLabel[role="heading"] {{color:{p['heading']};}}
QFrame#scadaPanel {{background:{glass.panel_fill(p)};border:1px solid {rim};border-radius:10px;}}
QFrame#scadaPanel:focus {{border:1px solid {p['accent']};}}
QFrame#scadaPanel[kpiStatus="attention"] {{border:2px solid {p['warning']};}}
QFrame#scadaPanel[kpiStatus="error"] {{border:2px solid {p['danger']};}}
QLabel#kpiStatusLabel {{color:{p['muted']};}}
QLabel#kpiStatusLabel[kpiStatus="attention"] {{color:{p['warning']};font-weight:700;}}
QLabel#kpiStatusLabel[kpiStatus="error"] {{color:{p['danger']};font-weight:700;}}
QFrame#scadaFooter {{background:{glass.result_fill(p)};border:1px solid {glass.tone_border(p,'accent')};border-radius:12px;}}
QFrame[compact="true"] QPushButton {{padding:7px 12px;}}
QFrame#scadaResult {{background:{glass.result_fill(p)};border:1px solid {result_border};border-radius:12px;}}
QPushButton {{background:{glass.button_fill(p)};color:{p['text']};border:1px solid {rim_button};border-radius:10px;padding:7px 14px;{ty.qss('card')}}}
QPushButton:hover {{background:{glass.button_fill(p,'hover')};border:1px solid {hover_border};}}
QPushButton:focus {{border:1px solid {p['accent']};}}
QPushButton:pressed {{background:{glass.primary_fill(p,'hot')};color:{p['on_strong']};border:1px solid {accent};}}
QPushButton:disabled {{background:{glass.button_fill(p,'disabled')};color:{p['disabled']};border:1px solid {rim_soft};}}
{tones}QPushButton#scadaPrimary {{background:{glass.primary_fill(p)};color:{p['on_strong']};border:1px solid {accent};padding:10px 16px;{ty.qss('button')}}}
QPushButton#scadaPrimary:hover {{background:{glass.primary_fill(p,'hover')};}}
QPushButton#scadaPrimary:pressed {{background:{glass.primary_fill(p,'hot')};color:{p['on_strong']};}}
QPushButton#scadaPrimary:disabled {{background:{glass.button_fill(p,'disabled')};color:{p['disabled']};border:1px solid {rim_soft};}}
QPushButton[fxBusy="true"]:disabled,QPushButton#scadaPrimary[fxBusy="true"]:disabled {{background:{busy};color:{p['heading']};border:1px solid {p['accent']};}}
QPushButton#scadaEmergency {{color:{p['danger']};border:1px solid {p['danger']};background:{danger_fill};}}
QPushButton#scadaEmergency:hover {{border:1px solid {p['danger']};}}
QPushButton#scadaEmergency:pressed {{background:{danger_hot};color:{p['on_strong']};border:1px solid {p['danger_strong']};}}
QComboBox,QLineEdit {{background:{glass.field_fill(p)};color:{p['text']};border:1px solid {rim_button};border-radius:8px;padding:6px 12px;{ty.qss('body')}}}
QComboBox:focus,QLineEdit:focus {{border:1px solid {p['accent']};}}
QComboBox QAbstractItemView {{background:{p['surface']};color:{p['text']};border:1px solid {rim};selection-background-color:{glass.rgba(p['accent'],.28)};selection-color:{p['heading']};}}
QProgressBar {{background:{p['soft']};border:0;border-radius:4px;color:{p['muted']};{ty.qss('caption')}}}
QProgressBar::chunk {{background:{p['sky']};border-radius:4px;}}
QTextEdit {{background:{glass.field_fill(p)};color:{p['text']};border:1px solid {rim_soft};border-radius:8px;{ty.qss('data')}}}
QScrollArea#leftScroll {{background:transparent;border:0;}}
QScrollBar:vertical {{background:transparent;width:10px;margin:2px;}}
QScrollBar::handle:vertical {{background:{glass.rgba(p['text'],.34)};border-radius:4px;min-height:36px;}}
QScrollBar::handle:vertical:hover {{background:{glass.rgba(p['accent'],.70)};}}
QScrollBar::add-line:vertical,QScrollBar::sub-line:vertical {{height:0;}}
QScrollBar::add-page:vertical,QScrollBar::sub-page:vertical {{background:transparent;}}'''

def connect_busy_state(w):
    """Enquanto o ciclo roda, o botão que o iniciou mostra "Analisando…" com um brilho em movimento."""
    buttons={'AUTO':w.btn_start_scan,'REP':w.btn_repeatability,'CALIB':w.btn_calibrate}
    original={}
    w._last_run_button=w.btn_start_scan
    for button in buttons.values():
        button.clicked.connect(lambda _=False,b=button:setattr(w,'_last_run_button',b))
    def mark(button,busy):
        button.setProperty('fxBusy',busy)
        button.style().unpolish(button);button.style().polish(button);button.update()
    def sync(busy):
        state=str(getattr(w,'fsm_state','IDLE'))
        current=next((b for k,b in buttons.items() if state.startswith(k)),getattr(w,'_last_run_button',w.btn_start_scan))
        for button in buttons.values():
            if busy and button is current:
                original.setdefault(button,button.text());mark(button,True)
                if button is w.btn_start_scan:button.setText('Analisando…')
            elif button in original or button.property('fxBusy'):
                mark(button,False)
                if button in original:button.setText(original.pop(button))
    w.analysis_indicator.busyChanged.connect(sync)

def indicator_state(w):
    """Estado mostrado no indicador: sem conexão com o ESP32, nunca diz 'Pronto'."""
    state=getattr(w,'fsm_state','IDLE')
    try:
        if state=='IDLE' and not w.is_serial_connected():return 'DESCONECTADO'
    except Exception:pass
    return state

def tone(button,name):
    """Dá ao botão um tom por função (ver glass.TONES); o estilo vem de dashboard_style."""
    button.setProperty('tone',name);return button

def _take_all(layout):
    while layout.count():layout.takeAt(0)

def arrange_topbar(w,two_rows):
    """Cabeçalho em uma linha (tela larga) ou em duas (notebook e tablet): nada fica cortado."""
    if getattr(w,'_topbar_two_rows',None)==two_rows:return
    w._topbar_two_rows=two_rows
    row_a,row_b=w._topbar_row_a,w._topbar_row_b
    _take_all(row_a);_take_all(row_b)
    for item in w._topbar_main:row_a.addWidget(item)
    row_a.addStretch(1)
    target=row_b if two_rows else row_a
    if two_rows:row_b.addStretch(1)
    for item in w._topbar_actions:target.addWidget(item)
    w._topbar_row_b_box.setVisible(two_rows)

def arrange_kpis(w,columns):
    if getattr(w,'_kpi_columns',None)==columns:return
    w._kpi_columns=columns
    grid=w.kpi_grid;cards=w._kpi_cards
    for card in cards:grid.removeWidget(card)
    for index,card in enumerate(cards):grid.addWidget(card,index//columns,index%columns)
    for column in range(4):grid.setColumnStretch(column,1 if column<columns else 0)

def arrange_main(w,stacked):
    """Controles à esquerda e gráfico à direita; em retrato ou tela estreita, um sobre o outro."""
    if getattr(w,'_main_stacked',None)==stacked:return
    w._main_stacked=stacked
    splitter=w.dashboard_splitter
    splitter.setOrientation(Qt.Vertical if stacked else Qt.Horizontal)
    splitter.setSizes([420,620] if stacked else [340,1260])
    grid=w.diagnostic_grid
    grid.removeWidget(w.card_esp32);grid.removeWidget(w.card_telemetria)
    if stacked:
        grid.addWidget(w.card_esp32,0,0);grid.addWidget(w.card_telemetria,1,0);grid.setColumnStretch(0,1);grid.setColumnStretch(1,0)
    else:
        grid.addWidget(w.card_esp32,0,0);grid.addWidget(w.card_telemetria,0,1);grid.setColumnStretch(0,4);grid.setColumnStretch(1,7)

def apply_layout_mode(w,logical_w,logical_h):
    """Chamado pelo canvas sempre que o tamanho lógico muda: escolhe a disposição (ver responsive_math)."""
    mode=responsive_math.layout_mode(logical_w,logical_h)
    arrange_topbar(w,mode['topbar_two_rows']);arrange_kpis(w,mode['kpi_columns']);arrange_main(w,mode['stack_main'])

SECTION_GAP=10   # espaço entre blocos (compacto: o gráfico recebe o espaço que sobra)
PAD=12           # respiro interno dos cartões
KPI_VALUE='font-size: 22px;'   # valor do indicador: menor que o papel 'kpi' para economizar altura

def build_dashboard(w):
    root=CanvasRoot();root.setObjectName('centralWidget');root.main_win=w
    w.dashboard_content=root
    seeds=[w._create_topbar(),w._create_kpi_bar(),w._create_left_control_panel(),w._create_right_chart_panel(),w._create_footer()]
    # Mantém as páginas manuais existentes e suas conexões, sem recriar a lógica operacional.
    w._ui_seed_widgets=seeds
    for seed in seeds:seed.setParent(root);seed.hide()
    for seed in seeds:
        for widget in [seed,*seed.findChildren(QWidget)]:
            widget.setStyleSheet('');widget._theme_base_qss='';widget._theme_last_qss=''
    layout=QVBoxLayout(root);layout.setContentsMargins(16,10,16,10);layout.setSpacing(SECTION_GAP)

    # ---- cabeçalho (duas linhas quando a tela é estreita)
    top=panel();top.setProperty('compact',True);w.topbar=top
    outer=QVBoxLayout(top);outer.setContentsMargins(PAD+2,8,PAD+2,8);outer.setSpacing(6)
    box_a=QWidget();row_a=QHBoxLayout(box_a);row_a.setContentsMargins(0,0,0,0);row_a.setSpacing(10)
    box_b=QWidget();row_b=QHBoxLayout(box_b);row_b.setContentsMargins(0,0,0,0);row_b.setSpacing(10)
    outer.addWidget(box_a);outer.addWidget(box_b);box_b.hide()
    w._topbar_row_a,w._topbar_row_b,w._topbar_row_b_box=row_a,row_b,box_b
    brand=QWidget();bh=QHBoxLayout(brand);bh.setContentsMargins(0,0,20,0);bh.setSpacing(10)
    mark=QLabel();mark.setObjectName('brandMark');mark.setPixmap(program_logo_pixmap(40));mark.setFixedSize(40,40);mark.setToolTip('SpectrumLab Pro')
    bh.addWidget(mark,0,Qt.AlignVCenter)
    names=QWidget();bl=QVBoxLayout(names);bl.setContentsMargins(0,0,0,0);bl.setSpacing(1);bh.addWidget(names)
    bl.addWidget(label('SpectrumLab Pro','brand',name='brandTitle'));bl.addWidget(label('Supervisório NIR','caption',True))
    # Conserva os containers utilizados pela troca USB/Bluetooth/Wi-Fi.
    for item in w.widget_serial.findChildren(QLabel):item.hide()
    w.combo_com.setMaximumWidth(120);w.btn_refresh_ports.setText('↻')
    manual=next(b for b in seeds[0].findChildren(QPushButton) if 'Atuadores' in b.text())
    manual.setText('Modo manual');manual.setMinimumWidth(120)
    w.btn_top_emergency.setText('Parada de emergência');w.btn_top_emergency.setObjectName('scadaEmergency')
    w.btn_login=QPushButton('Login');w.btn_login.clicked.connect(lambda:open_login(w))
    tone(w.btn_connect,'sky');tone(manual,'indigo');tone(w.btn_login,'slate')
    w._topbar_main=[brand,w.combo_conn_mode,w.widget_serial,w.widget_wifi,w.btn_connect,w.badge_com]
    w.btn_rearm=QPushButton('Rearmar');w.btn_rearm.clicked.connect(w.request_rearm)
    w._topbar_actions=[manual,w.btn_top_emergency,w.btn_rearm,w.btn_login,w.btn_settings]
    w._topbar_two_rows=None;arrange_topbar(w,False)
    layout.addWidget(top)

    identity_row=QHBoxLayout()
    identity_row.addWidget(QLabel('Código da amostra:'))
    w.input_sample_id=QLineEdit();w.input_sample_id.setPlaceholderText('Etiqueta externa (vazio: código interno automático)')
    identity_row.addWidget(w.input_sample_id)
    w.btn_retry_save=QPushButton('Tentar salvar novamente');w.btn_retry_save.clicked.connect(w.retry_save_result)
    identity_row.addWidget(w.btn_retry_save)
    layout.addLayout(identity_row)

    # ---- indicadores (ícone colorido, filete de cor e altura igual)
    w.kpi_bar=seeds[1]
    w._kpi_cards=[w.kpi_energy,w.kpi_peak,w.kpi_ratio_cel,w.kpi_ratio_water]
    w.kpi_grid.setSpacing(SECTION_GAP)
    for card in w._kpi_cards:
        card.setObjectName('scadaPanel');card.layout().setContentsMargins(PAD,6,PAD,6);card.layout().setSpacing(0)
        card.lbl_title.setStyleSheet('color: #9CA3AF; '+ty.qss('label'))
        card.lbl_value.setStyleSheet('color: #FFFFFF; '+ty.qss('kpi',KPI_VALUE))
        card.lbl_sub.setStyleSheet('color: #9CA3AF; '+ty.qss('caption'))
    detail_windows.install(w)   # clique no cartão abre a janela do indicador
    w._kpi_columns=None;arrange_kpis(w,4)
    layout.addWidget(w.kpi_bar)
    w.kpi_bar.show()

    # ---- corpo: controles (rolagem) e gráfico
    w.dashboard_splitter=QSplitter(Qt.Horizontal);w.dashboard_splitter.setChildrenCollapsible(False);w.dashboard_splitter.setHandleWidth(SECTION_GAP)
    left=QWidget();w.left_panel=left;left.setAutoFillBackground(False)
    ll=QVBoxLayout(left);ll.setContentsMargins(0,0,0,0);ll.setSpacing(SECTION_GAP)
    controls=panel();cl=QVBoxLayout(controls);cl.setContentsMargins(PAD,10,PAD,10);cl.setSpacing(8)
    cl.addWidget(label('Método analítico','label',True));cl.addWidget(w.combo_op_mode)
    cl.addWidget(label('Ensaios automáticos','section'))
    w.btn_start_scan.setText('Realizar leitura');w.btn_start_scan.setObjectName('scadaPrimary')
    w.btn_repeatability.setText('Leitura com repetibilidade · 5×')
    w.btn_calibrate.setText('Calibrar · Branco e escuro')
    tone(w.btn_repeatability,'secondary');tone(w.btn_calibrate,'rose')
    for button in (w.btn_start_scan,w.btn_repeatability,w.btn_calibrate):cl.addWidget(button)
    cl.addWidget(w.lbl_scan_hint)
    ll.addWidget(controls)
    w.card_housing.setObjectName('scadaPanel')
    housing=w.card_housing.layout();housing.setContentsMargins(PAD,8,PAD,8);housing.setSpacing(3)
    housing.insertWidget(0,label('Estado do equipamento','label',True))
    for state in (w.lbl_housing_state,w.lbl_door_state,w.lbl_carriage_state):
        state.setWordWrap(True);state.setStyleSheet(ty.qss('body'))
    ll.addWidget(w.card_housing)
    w.card_calibracao.setObjectName('scadaPanel');w.card_calibracao.layout().setSpacing(4)
    w.card_calibracao.layout().setContentsMargins(PAD,8,PAD,8)
    ll.addWidget(w.card_calibracao)
    w.card_resultado.setObjectName('scadaResult');w.card_resultado.layout().setContentsMargins(PAD,8,PAD,8)
    w.lbl_kappa_valor.setObjectName('kappaValue');w.lbl_kappa_valor.setStyleSheet(ty.qss('hero'))
    w.lbl_metodo_info.setWordWrap(True);w.lbl_kappa_classificacao.setWordWrap(True)
    ll.addWidget(w.card_resultado)
    buttons=QHBoxLayout();buttons.setSpacing(8)
    for button,text,tone_name in ((w.btn_history,'Histórico','sand'),(w.btn_pdf,'PDF','indigo'),(w.btn_csv,'CSV','green')):
        button.setText(text);button.setMinimumWidth(0);tone(button,tone_name);buttons.addWidget(button,1)
    ll.addLayout(buttons);ll.addStretch(1)
    scroll=QScrollArea();scroll.setObjectName('leftScroll');scroll.setWidgetResizable(True);scroll.setFrameShape(QFrame.NoFrame)
    scroll.setHorizontalScrollBarPolicy(Qt.ScrollBarAlwaysOff);scroll.setWidget(left);scroll.viewport().setAutoFillBackground(False)
    scroll.setMinimumWidth(320)
    QScroller.grabGesture(scroll.viewport(),QScroller.TouchGesture)   # rolagem com o dedo em touchscreen
    w.left_scroll=scroll
    right=panel();w.right_panel=right;rl=QVBoxLayout(right);rl.setContentsMargins(10,8,10,8)
    rl.setSpacing(8);rl.addWidget(w.spectral_chart,1)
    w.analysis_indicator=AnalysisIndicator(lambda:indicator_state(w));rl.addWidget(w.analysis_indicator)
    connect_busy_state(w)
    w.dashboard_splitter.addWidget(scroll);w.dashboard_splitter.addWidget(right)
    w.dashboard_splitter.setStretchFactor(0,0);w.dashboard_splitter.setStretchFactor(1,1)
    w.dashboard_splitter.setSizes([340,1260]);layout.addWidget(w.dashboard_splitter,1)
    w.card_esp32=ControllerDiagnosticsCard(w)
    diagnostics=QWidget();dg=QGridLayout(diagnostics);dg.setContentsMargins(0,0,0,0);dg.setSpacing(SECTION_GAP)
    dg.addWidget(w.card_esp32,0,0);dg.addWidget(w.card_telemetria,0,1);dg.setColumnStretch(0,4);dg.setColumnStretch(1,7)
    w.diagnostic_grid=dg;layout.addWidget(diagnostics)
    w._main_stacked=False

    # ---- rodapé em destaque: estado e comandos em cima, logos e assinatura (com links) embaixo
    footer=panel();footer.setObjectName('scadaFooter');w.footer=footer;fl=QVBoxLayout(footer);fl.setContentsMargins(PAD+2,6,PAD+2,6);fl.setSpacing(4)
    fr=QHBoxLayout();fr.setSpacing(12);w.lbl_cycle_status.setWordWrap(True);fr.addWidget(w.lbl_cycle_status,1)
    w.cycle_progress.setMaximumWidth(200);fr.addWidget(w.cycle_progress)
    w.btn_terminal=QPushButton('Terminal');tone(w.btn_terminal,'slate');w.btn_terminal.setToolTip('Abrir o terminal de telemetria e comandos em outra janela')
    w.btn_terminal.clicked.connect(lambda:detail_windows.open_terminal(w));fr.addWidget(w.btn_terminal);fl.addLayout(fr)
    fr2=QHBoxLayout();fr2.setSpacing(16);fr2.addWidget(institutional_signature());fr2.addStretch(1)
    credits=QLabel(credits_html());credits.setObjectName('credits');credits.setTextFormat(Qt.RichText)
    credits.setOpenExternalLinks(True);credits.setTextInteractionFlags(Qt.TextBrowserInteraction)
    credits.setStyleSheet(ty.qss('body'));credits.setAlignment(Qt.AlignRight|Qt.AlignVCenter)
    credits.setToolTip('Abrir o perfil no GitHub')
    fr2.addWidget(credits);fl.addLayout(fr2)
    w.txt_console.setParent(root);w.txt_console.hide()   # o terminal tem janela própria (detail_windows.TerminalDialog)
    layout.addWidget(footer)
    root._scada_style_factory=dashboard_style
    w.canvas_view=ScaledCanvasView(root,QSize(1600,1000),w,adaptive=True)
    w.canvas_view.layout_listener=lambda lw,lh:apply_layout_mode(w,lw,lh)
    w.setCentralWidget(w.canvas_view)
    w._scada_refresh_timer=QTimer(w)
    def refresh():
        w.card_esp32.refresh(w)
        w.card_telemetria.refresh_freshness(busy=w.equipment.busy())
        w.btn_retry_save.setVisible(getattr(w, '_pending_reading_record', None) is not None)
        w.input_sample_id.setEnabled(w.fsm_state=='IDLE')
        w._update_scan_hint()
        w._update_sim_indicator()
        w.btn_login.setText('Sair · '+w.authenticated_user.get('username','Operador') if w.authenticated_user else 'Login')
    w._scada_refresh_timer.timeout.connect(refresh);w._scada_refresh_timer.start(1000);refresh()
    w._responsive_ready=True
    # As páginas manuais e o badge são os únicos controles ocultos necessários.
    # Descarta os containers de construção depois de transferir seus filhos ativos.
    w.control_tabs.setParent(root);w.control_tabs.hide()
    w.badge_calib.setParent(root);w.badge_calib.hide()
    w.btn_emergency_auto=w.btn_top_emergency
    for seed in (seeds[0],seeds[2],seeds[3],seeds[4]):
        seed.setParent(None);seed.deleteLater()
    w._ui_seed_widgets=[w.kpi_bar]
    for widget in (w,root,*root.findChildren(QWidget)):w.theme_manager.apply_widget(widget)
    try:
        from motion import install_entrance
        install_entrance(root,[top,*w._kpi_cards,scroll,right,diagnostics,footer])
    except Exception:pass   # a animação é um extra: sem ela a interface funciona igual
    QTimer.singleShot(0,w._adapt_interface)

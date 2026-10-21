"""Temas persistentes para widgets, estilos dinâmicos e gráficos."""
import json,os,re,tempfile,weakref
from pathlib import Path
from PyQt5 import sip
from PyQt5.QtCore import QObject,QEvent,QTimer,Qt
from PyQt5.QtGui import QColor,QPalette,QPixmap
from PyQt5.QtWidgets import (QApplication,QWidget,QLabel,QPushButton,QComboBox,QDialog,QButtonGroup,
                             QVBoxLayout,QHBoxLayout,QFrame,QTabWidget,QMenu)
from popup_design import popup_owner, popup_stylesheet
from typography import normalize_qss, install as install_typography
PALETTES={
 # Noturno: roxo profundo com ouro como destaque. Os painéis são translúcidos sobre um fundo com
 # brilhos roxos e dourados. Ouro é a cor de foco e de identidade; os botões são neutros.
 # Vermelho e laranja ficam reservados a alarme e aviso.
 "noturno":{"canvas":"#0A0614","surface":"#1A1030","soft":"#2A1F4A","border":"#6A5A9A",
          "text":"#FBF7EE","heading":"#FFF1C4","muted":"#D9D0EE","disabled":"#8E84B0","accent":"#E8BE5C",
          "secondary":"#A88BFF","slate":"#AEB8CC","sand":"#D6C6A8",
          "positive":"#8FD69B","warning":"#F4A259","danger":"#FF8A80",
          "sky":"#8CC8FF","violet":"#B7A0FF","rose":"#F2A7D0",
          "accent_strong":"#F0C867","positive_strong":"#8FD69B","danger_strong":"#FF8A80","on_strong":"#0A0614"},
 # Claro: branco e verde, em quatro tons distintos (folha, musgo, floresta e jade). O matiz principal
 # (~92 graus) vem do logo do Projeto Sucuriú. Sobre um fundo levemente verde, com painéis translúcidos.
 "light":{"canvas":"#EEF5EA","surface":"#FFFFFF","soft":"#E2EDD7","border":"#9DB38A",
          "text":"#132210","heading":"#18300F","muted":"#3F5234","disabled":"#7E8873","accent":"#3E7A1E",
          "secondary":"#0E7A62","slate":"#4A5568","sand":"#6A5F52",
          "positive":"#1F6B3A","warning":"#8A5A00","danger":"#B3261E",
          "sky":"#1F6FA8","violet":"#4B55C8","rose":"#A03C8E",
          "accent_strong":"#3E7A1E","positive_strong":"#1F6B3A","danger_strong":"#B3261E","on_strong":"#FFFFFF"},
}
# Cores por série (bandas espectrais), em ordem fixa. Validadas com o validador de paletas
# (diferença para daltonismo e contraste sobre a superfície) nos dois temas.
SERIES={
 "noturno":["#3987E5","#D95926","#199E70","#C98500","#D55181","#9085E9"],
 "light":["#2A78D6","#EB6834","#1BAF7A","#EDA100","#E87BA4","#6250D6"],
}
DEFAULT_THEME="noturno"
LEGACY_THEMES={"dark":"noturno","gold":"noturno","umber":"noturno"}   # preferências salvas por versões anteriores
THEME_LABELS={"noturno":"Noturno · roxo e dourado","light":"Claro · branco e verde"}
TEXTURE_FILES={}   # ISA-101: nenhum tema usa textura
def texture_path(theme=None):
    """Textura do fundo da janela principal, ou None quando o tema não tem textura."""
    import sys
    name=TEXTURE_FILES.get(theme or current_theme())
    if name is None:return None
    base=Path(getattr(sys,"_MEIPASS",Path(__file__).resolve().parent))
    return base/"assets"/"textures"/name
_TEXTURE_CACHE={}
def texture_pixmap(theme=None):
    key=theme or current_theme()
    if key not in _TEXTURE_CACHE:
        path=texture_path(key)
        pix=QPixmap(str(path)) if path else QPixmap()   # QPixmap vazio: o chamador não desenha nada
        _TEXTURE_CACHE[key]=pix
    return _TEXTURE_CACHE[key]
def current_theme():
    app=QApplication.instance()
    return (app.property("spectrum_theme") or DEFAULT_THEME) if app else DEFAULT_THEME
def palette_for(theme=None):return PALETTES.get(theme or current_theme(),PALETTES[DEFAULT_THEME])
def series_colors(theme=None):return SERIES.get(theme or current_theme(),SERIES[DEFAULT_THEME])
def tone_for_hue(hue,p,strong=False):
    """Cor do tema para um matiz (0 a 1) de uma cor antiga: vermelho, laranja, verde, azul, violeta e rosa viram tons distintos."""
    if hue<0.08 or hue>=0.93:return p["danger_strong" if strong else "danger"]
    if hue<0.19:return p["warning"]
    if hue<0.47:return p["positive_strong" if strong else "positive"]
    if hue<0.60:return p["sky"]
    if hue<0.80:return p["violet"]
    return p["rose"]
def mapped_color(value,kind="text",theme=None):
    p=palette_for(theme);color=QColor(value)
    if not color.isValid():return value
    hue,saturation,lightness,_=color.getHslF()
    neutral=saturation<0.20 or hue<0
    if kind=="border":return p["border"]
    if kind=="surface":
        if neutral or (lightness<0.20 and 0.48<hue<0.72):
            return p["canvas"] if value.lower() in ("#202020","#0f172a","#18181b","#111B24") else p["surface"]
        if lightness<0.35:
            if hue<0.08 or hue>0.90:return "#FDECEA" if (theme or current_theme())=="light" else "#2A1512"
            return p["soft"]
        return tone_for_hue(hue,p,True)
    if neutral:
        if lightness>0.82:return p["text"]
        return p["disabled"] if lightness<0.38 else p["muted"]
    return tone_for_hue(hue,p)
def theme_color(value,kind="text"):return mapped_color(value,kind)

COLOR=re.compile(r"#[0-9a-fA-F]{6}\b")
DECL=re.compile(r"(background(?:-color)?|color|border(?:-(?:color|top|bottom|left|right))?)\s*:\s*([^;{}]+)(;|$)",re.I)
def transform_stylesheet(source,theme):
    def block(text):
        strong=False
        bg=re.search(r"background(?:-color)?\s*:\s*([^;]+)",text,re.I)
        if bg:
            colors=COLOR.findall(bg.group(1))
            strong=any(QColor(c).hslSaturationF()>0.4 and QColor(c).lightnessF()>0.30 for c in colors)
        def declaration(match):
            prop,value,end=match.groups()
            kind="surface" if prop.lower().startswith("background") else "border" if prop.lower().startswith("border") else "text"
            if prop.lower()=="color" and strong:
                # Texto sobre fundo forte: roxo muito escuro no tema noturno, branco no tema claro.
                on_strong=palette_for(theme)["on_strong"]
                value=COLOR.sub(lambda m:on_strong if QColor(m[0]).lightnessF()>0.82 else mapped_color(m[0],kind,theme),value)
            else:value=COLOR.sub(lambda m:mapped_color(m[0],kind,theme),value)
            if kind=="surface" and "qlineargradient" in value:
                colors=COLOR.findall(value)
                if colors:value=colors[0]
            return f"{prop}: {value}{end}"
        return DECL.sub(declaration,text)
    if "{" not in source:return block(source)
    return re.sub(r"\{([^{}]*)\}",lambda m:"{"+block(m.group(1))+"}",source)

def preferences_path():
    base=os.environ.get("SPECTRUM_LAB_DATA_DIR")
    if not base:base=str(Path(os.environ.get("LOCALAPPDATA",str(Path.home()/".spectrum_lab")))/"SpectrumLabPro")
    return Path(base)/"interface.json"
def read_preferences(path):
    """Lê interface.json. Aceita o formato antigo (só o tema) e migra os temas escuros anteriores para o noturno."""
    try:
        data=json.loads(path.read_text(encoding="utf-8"))
    except (OSError,ValueError,TypeError,AttributeError):
        data={}
    if not isinstance(data,dict):data={}
    theme=data.get("theme")
    theme=LEGACY_THEMES.get(theme,theme)
    if theme not in PALETTES:theme=DEFAULT_THEME
    return {"theme":theme}
def read_preference(path):return read_preferences(path)["theme"]
def save_preferences(path,prefs):
    temporary=None
    try:
        path.parent.mkdir(parents=True,exist_ok=True)
        with tempfile.NamedTemporaryFile("w",encoding="utf-8",dir=path.parent,delete=False) as handle:
            temporary=Path(handle.name);json.dump(prefs,handle);handle.flush();os.fsync(handle.fileno())
        os.replace(temporary,path);return True,""
    except OSError as exc:return False,str(exc)
    finally:
        if temporary and temporary.exists():temporary.unlink(missing_ok=True)
def save_preference(path,theme):
    prefs=read_preferences(path);prefs["theme"]=theme
    return save_preferences(path,prefs)

class ThemeManager(QObject):
    def __init__(self,app):
        super().__init__(app)
        self.app=app;self.applying=False;self.path=preferences_path();self.last_error=""
        self.prefs=read_preferences(self.path)
        self.theme=self.prefs["theme"]
        try:install_typography(app)
        except Exception:pass   # sem as fontes embutidas o programa usa as alternativas da pilha
        app.installEventFilter(self)
        from button_fx import ButtonFx
        self.button_fx=ButtonFx(app)
        from cursors import CursorController
        self.cursor_fx=CursorController(app)
        import motion
        self.motion_fx=motion.MotionController(app)
        self.set_theme(self.theme,False)
    def refresh_preferences_path(self):
        path=preferences_path()
        if path!=self.path:
            self.path=path;self.prefs=read_preferences(path)
            self.set_theme(self.prefs["theme"],False)
    def eventFilter(self,obj,event):
        if isinstance(obj,QWidget) and not self.applying and event.type() in (QEvent.StyleChange,QEvent.Show):
            if not getattr(obj,"_theme_queued",False):
                obj._theme_queued=True
                ref=weakref.ref(obj)
                def apply_later():
                    widget=ref()
                    if widget is not None and not sip.isdeleted(widget):
                        widget._theme_queued=False;self.apply_widget(widget)
                QTimer.singleShot(0,apply_later)
        return False
    def apply_widget(self,widget):
        if sip.isdeleted(widget):return
        current=widget.styleSheet()
        if current!=getattr(widget,"_theme_last_qss",None):
            widget._theme_base_qss=current
        source=getattr(widget,"_theme_base_qss",current)
        # Evita que os estilos de caixas sejam herdados pelos rótulos internos.
        scoped=source
        if scoped:
            name=widget.objectName()
            if not name:
                name=f"themeWidget{id(widget)}";widget.setObjectName(name)
            if "{" not in scoped and re.search(r"(?:background|border)\s*[-:]",scoped):
                scoped=f"#{name} {{ {scoped} }}"
            scoped=re.sub(r"(?<![\w#])QFrame\s*\{",f"QFrame#{name} {{",scoped)
            if isinstance(widget,QLabel):
                scoped=re.sub(r"(?:background(?:-color)?|border(?:-(?:top|bottom|left|right|color))?)\s*:[^;{}]+;?","",scoped)
        factory=getattr(widget,"_scada_style_factory",None)
        rendered=factory(palette_for(self.theme)) if factory else transform_stylesheet(scoped,self.theme)
        in_popup = popup_owner(widget) is not None
        if in_popup:
            rendered = popup_stylesheet(widget, palette_for(self.theme), rendered)
        rendered=normalize_qss(rendered)
        widget._theme_last_qss=rendered
        previous=self.applying;self.applying=True
        try:
            if current!=rendered:widget.setStyleSheet(rendered)
            if isinstance(widget,(QLabel,QPushButton)) and not in_popup:
                text=widget.text()
                clean=re.sub(r"[\U0001F000-\U0001FAFF\u2300-\u23FF\u25B6\u2600-\u27BF\uFE0F\u200D]","",text).strip()
                if clean!=text:widget.setText(clean)
                if text and not clean and isinstance(widget,QLabel):widget.hide()
            if isinstance(widget,QComboBox) and not in_popup:
                for i in range(widget.count()):
                    text=widget.itemText(i)
                    clean=re.sub(r"[\U0001F000-\U0001FAFF\u2300-\u23FF\u25B6\u2600-\u27BF\uFE0F\u200D]","",text).strip()
                    if clean!=text:widget.setItemText(i,clean)
            if isinstance(widget,QTabWidget) and not in_popup:
                for i in range(widget.count()):
                    text=widget.tabText(i)
                    clean=re.sub(r"[\U0001F000-\U0001FAFF\u25B6\u2300-\u23FF\u2600-\u27BF\uFE0F\u200D]","",text).strip()
                    if clean!=text:widget.setTabText(i,clean)
            if isinstance(widget,QMenu):
                for action in widget.actions():
                    text=action.text()
                    clean=re.sub(r"[\U0001F000-\U0001FAFF\u25B6\u2300-\u23FF\u2600-\u27BF\uFE0F\u200D]","",text).strip()
                    if clean!=text:action.setText(clean)
            p=palette_for(self.theme)
            widget.setPalette(self.app.palette())
            if hasattr(widget,"setBackgroundBrush"):widget.setBackgroundBrush(QColor(p["canvas"]))
            widget.update()
        finally:self.applying=previous
    def set_theme(self,theme,persist=True):
        if theme not in PALETTES:raise ValueError("Tema inválido.")
        self.theme=theme;self.app.setProperty("spectrum_theme",theme)
        p=palette_for(theme);pal=QPalette()
        for role,key in ((QPalette.Window,"canvas"),(QPalette.WindowText,"text"),(QPalette.Base,"surface"),
                         (QPalette.AlternateBase,"soft"),(QPalette.Text,"text"),(QPalette.Button,"soft"),
                         (QPalette.ButtonText,"text"),(QPalette.Highlight,"accent"),
                         (QPalette.ToolTipBase,"surface"),(QPalette.ToolTipText,"text")):
            pal.setColor(role,QColor(p[key]))
        pal.setColor(QPalette.HighlightedText,QColor(p["on_strong"]))
        pal.setColor(QPalette.Link,QColor(p["accent"]));pal.setColor(QPalette.LinkVisited,QColor(p["violet"]))
        for role in (QPalette.Text,QPalette.WindowText,QPalette.ButtonText):
            pal.setColor(QPalette.Disabled,role,QColor(p["disabled"]))
        import motion
        fades=motion.begin_crossfade(self.app)   # sem janelas visíveis (ao iniciar) não faz nada
        self.applying=True
        try:self.app.setPalette(pal)
        finally:self.applying=False
        for widget in self.app.allWidgets():self.apply_widget(widget)
        motion.run_crossfade(fades)
        self.prefs["theme"]=theme
        if persist:
            ok,self.last_error=save_preferences(self.path,self.prefs);return ok
        return True

def ensure_theme_manager():
    app=QApplication.instance()
    manager=getattr(app,"_spectrum_themes",None)
    if manager is None:manager=ThemeManager(app);app._spectrum_themes=manager
    else:manager.refresh_preferences_path()
    return manager

class AppearanceDialog(QDialog):
    """Configurações: tema claro ou escuro. Teclado e animações não têm opção: o teclado abre com duplo clique."""
    def __init__(self,manager,parent=None):
        super().__init__(parent)
        self.manager=manager
        self.setWindowTitle("Configurações")
        self.resize(600,660)
        layout=QVBoxLayout(self);layout.setContentsMargins(26,24,26,22);layout.setSpacing(16)
        title=QLabel("Configurações");title.setProperty("role","heading")
        title.setStyleSheet("color: #FFFFFF; font-size: 24px; font-weight: 400; font-family: 'Dropline';")
        layout.addWidget(title)

        # ---- Aparência: tema claro ou escuro
        self.theme_buttons={}
        self.theme_group=QButtonGroup(self);self.theme_group.setExclusive(True)
        pickers=QHBoxLayout();pickers.setSpacing(12)
        for key,text in (("noturno","Noturno\nroxo e dourado"),("light","Claro\nbranco e verde")):
            button=QPushButton(text);button.setCheckable(True);button.setMinimumHeight(68)
            button.setProperty("fxTone","soft");button.setChecked(manager.theme==key)
            button.clicked.connect(lambda _=False,k=key:self.change_theme(k))
            self.theme_group.addButton(button);self.theme_buttons[key]=button;pickers.addWidget(button,1)
        theme_box=QWidget();theme_box.setLayout(pickers);pickers.setContentsMargins(0,0,0,0)
        layout.addWidget(self._section("Aparência","Tema da interface. A mudança é aplicada na hora e a escolha fica salva.",theme_box))


        self.feedback=QLabel("As alterações são aplicadas imediatamente.")
        self.feedback.setWordWrap(True);self.feedback.setStyleSheet("color: #9CA3AF; font-size: 12px;")
        layout.addWidget(self.feedback)
        layout.addStretch(1)
        row=QHBoxLayout();row.addStretch()
        close=QPushButton("Concluir");close.setObjectName("settingsDone");close.clicked.connect(self.accept);row.addWidget(close)
        layout.addLayout(row)
        for widget in (self,*self.findChildren(QWidget)):manager.apply_widget(widget)
    def _section(self,heading,description,content):
        """Cartão de uma seção: título em serifa, descrição e o conteúdo."""
        frame=QFrame();frame.setObjectName("settingsSection")
        box=QVBoxLayout(frame);box.setContentsMargins(20,16,20,18);box.setSpacing(10)
        head=QLabel(heading);head.setProperty("role","heading")
        head.setStyleSheet("color: #FFFFFF; font-size: 20px; font-weight: 400; font-family: 'Dropline';")
        note=QLabel(description);note.setWordWrap(True);note.setStyleSheet("color: #9CA3AF; font-size: 14px;")
        box.addWidget(head);box.addWidget(note);box.addWidget(content)
        return frame
    def change_theme(self,key=None):
        key=key or next((k for k,b in self.theme_buttons.items() if b.isChecked()),self.manager.theme)
        ok=self.manager.set_theme(key)
        for name,button in self.theme_buttons.items():button.setChecked(name==key)
        self.feedback.setText("Preferência salva." if ok else "Tema aplicado nesta sessão. Não foi possível salvar a preferência.")

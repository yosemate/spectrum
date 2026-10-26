"""Escala proporcional de widgets: preserva disposição e não cria rolagem."""
from PyQt5.QtCore import Qt, QRectF, QSize, QObject, QEvent, QTimer
from PyQt5.QtGui import QPainter, QTransform
from PyQt5.QtWidgets import (QGraphicsView,QGraphicsScene,QWidget,QVBoxLayout,
                             QDialog,QFrame,QSizePolicy)
import responsive_math

class ScaledCanvasView(QGraphicsView):
    """Um único fator transforma textos, gráficos, espaçamentos e áreas de clique."""
    def __init__(self,content,design_size=QSize(1600,900),parent=None,adaptive=False):
        super().__init__(parent)
        self.adaptive=adaptive          # True: o canvas acompanha a janela (ver responsive_math.py)
        self.layout_listener=None       # função(largura_lógica, altura_lógica) chamada quando o canvas muda
        self._last_logical=None
        self._explicit_minimum=content.minimumSize()
        self.content=content
        content.ensurePolished()
        if content.layout(): content.layout().activate()
        self.design_size=design_size.expandedTo(content.minimumSizeHint())
        content.setFixedSize(self.design_size)
        self.canvas_scene=QGraphicsScene(self)
        self.setScene(self.canvas_scene)
        self.proxy=self.canvas_scene.addWidget(content)
        self.canvas_scene.setSceneRect(QRectF(0,0,self.design_size.width(),self.design_size.height()))
        self.setFrameShape(QFrame.NoFrame)
        self.setHorizontalScrollBarPolicy(Qt.ScrollBarAlwaysOff)
        self.setVerticalScrollBarPolicy(Qt.ScrollBarAlwaysOff)
        self.setSizePolicy(QSizePolicy.Ignored,QSizePolicy.Ignored)
        self.setMinimumSize(0,0)
        self.setRenderHints(QPainter.Antialiasing|QPainter.TextAntialiasing|QPainter.SmoothPixmapTransform)
        self.setBackgroundBrush(content.palette().window())
        self.setStyleSheet("QGraphicsView { border: none; background: #202020; }")
        self.scale_factor=1.0
        self.update_scale()
    def sizeHint(self): return self.design_size
    def minimumSizeHint(self): return QSize(0,0)
    def resizeEvent(self,event):
        super().resizeEvent(event)
        self.update_scale()
    def showEvent(self,event):
        super().showEvent(event)
        self.update_scale()
    def update_scale(self):
        if not hasattr(self,"design_size"): return
        if self.adaptive:
            self._update_adaptive()
            return
        width=max(1,self.viewport().width()-2)
        height=max(1,self.viewport().height()-2)
        self.scale_factor=min(width/self.design_size.width(),height/self.design_size.height())
        self.setTransform(QTransform().scale(self.scale_factor,self.scale_factor))
        self.centerOn(self.canvas_scene.sceneRect().center())
    def _update_adaptive(self):
        """Escala perto de 1:1 e canvas do tamanho da janela; o layout se reorganiza em vez de encolher."""
        vw,vh=self.viewport().width(),self.viewport().height()
        if vw<2 or vh<2: return
        if self._last_logical is not None and getattr(self,"_last_viewport",None)==(vw,vh): return
        self._last_viewport=(vw,vh)
        layout=self.content.layout()
        if layout:
            layout.activate()
            minimum=layout.minimumSize().expandedTo(self._explicit_minimum)
        else:
            minimum=self.content.minimumSizeHint()
        scale,lw,lh=responsive_math.fit(vw,vh,minimum.width(),minimum.height())
        if self.layout_listener:
            # O ouvinte pode trocar a disposição (cabeçalho em duas linhas, empilhar painéis), o que muda
            # o tamanho mínimo; por isso a escala é recalculada uma vez depois dele.
            self.layout_listener(lw,lh)
            if layout:
                layout.activate()
                minimum=layout.minimumSize().expandedTo(self._explicit_minimum)
                scale,lw,lh=responsive_math.fit(vw,vh,minimum.width(),minimum.height())
        self.scale_factor=scale
        self._last_logical=(lw,lh)
        self.content.setFixedSize(lw,lh)
        self.proxy.resize(lw,lh)
        self.canvas_scene.setSceneRect(QRectF(0,0,lw,lh))
        self.setTransform(QTransform().scale(scale,scale))
        self.horizontalScrollBar().setValue(0)
        self.verticalScrollBar().setValue(0)

class DialogScreenAdapter(QObject):
    """Diálogos que excedem a tela também são reduzidos proporcionalmente."""
    def eventFilter(self,obj,event):
        if isinstance(obj,QDialog) and event.type()==QEvent.Show and not obj.property("screenAdapted"):
            screen=obj.screen()
            if screen:
                area=screen.availableGeometry()
                max_w,max_h=max(240,area.width()-40),max(200,area.height()-60)
                requested=obj.size().expandedTo(obj.minimumSizeHint())
                if requested.width()>max_w or requested.height()>max_h:
                    old=obj.layout()
                    if old:
                        content=QWidget()
                        content.setObjectName("scaledDialogContent")
                        content.setStyleSheet(obj.styleSheet()+"\nQWidget#scaledDialogContent { background: #202020; }")
                        content.setLayout(old)
                        obj._scaled_view=ScaledCanvasView(content,requested,obj)
                        layout=QVBoxLayout(obj)
                        layout.setContentsMargins(0,0,0,0)
                        layout.addWidget(obj._scaled_view)
                        obj.setMinimumSize(0,0)
                        obj.setMaximumSize(16777215,16777215)
                        factor=min(1.0,max_w/requested.width(),max_h/requested.height())
                        obj.resize(int(requested.width()*factor),int(requested.height()*factor))
                        QTimer.singleShot(0,obj._scaled_view.update_scale)
                obj.setProperty("screenAdapted",True)
        return False

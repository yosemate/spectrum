"""
Teste gráfico de fumaça: abre widgets de verdade (sem janela visível) e confere o essencial da
nova interface. Precisa de PyQt5; sem ele os testes são pulados.

Executar na raiz do repositório (no Codespace não precisa de monitor):

    QT_QPA_PLATFORM=offscreen python3 -m unittest tests.test_gui_smoke -v
"""
import os
import sys
import tempfile
import unittest
from pathlib import Path

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
os.environ["SPECTRUM_LAB_DATA_DIR"] = tempfile.mkdtemp(prefix="spectrum-test-")   # não mexe nas preferências reais
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

try:
    from PyQt5.QtCore import QAbstractAnimation, QPoint, Qt
    from PyQt5.QtGui import QFontDatabase, QFontInfo
    from PyQt5.QtTest import QTest
    from PyQt5.QtWidgets import QApplication, QLineEdit, QPushButton, QTextEdit, QVBoxLayout, QWidget
    HAVE_QT = True
except ImportError:   # pragma: no cover
    HAVE_QT = False

import analysis_messages as messages  # noqa: E402
import responsive_math  # noqa: E402,F401


def distinct_pixels(pixmap, step_x=23, step_y=7):
    image = pixmap.toImage()
    return {image.pixel(x, y) for x in range(0, image.width(), step_x) for y in range(0, image.height(), step_y)}


@unittest.skipUnless(HAVE_QT, "PyQt5 não instalado")
class GuiSmokeTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.app = QApplication.instance() or QApplication(sys.argv[:1])
        cls.app.setStyle("Fusion")
        from appearance import ensure_theme_manager
        cls.manager = ensure_theme_manager()

    def _dialog(self):
        from appearance import AppearanceDialog
        return AppearanceDialog(self.manager)

    def pump(self):
        self.app.processEvents()

    def test_embedded_fonts_are_registered(self):
        families = set(QFontDatabase().families())
        for family in ("Inter", "Dropline", "Arena", "IBM Plex Mono"):
            self.assertIn(family.casefold(), {name.casefold() for name in families})
        self.assertNotIn("EB Garamond", families, "a Garamond deixou de ser embutida")

    def test_font_styles_are_regular_and_bold_only(self):
        """Diagnóstico: cada família deve ter só os estilos Regular/Bold .

        Se aparecer outro estilo (Medium, SemiBold), o Windows pode registrá-lo como família separada
        e a pilha de fontes deixa de se comportar como esperado."""
        db = QFontDatabase()
        allowed = {"Regular", "Bold", "Italic", "Normal", "Bold Italic"}
        for family in ("Inter", "Dropline", "IBM Plex Mono"):
            styles = set(db.styles(family))
            self.assertTrue(styles, family)
            self.assertLessEqual(styles, allowed, f"{family}: estilos inesperados {sorted(styles - allowed)}")

    def test_cursor_images_load(self):
        import cursors
        for name in (cursors.ARROW, cursors.HAND):
            cursor = cursors.load_cursor(name)
            self.assertIsNotNone(cursor, name)
            self.assertEqual(cursor.shape(), Qt.BitmapCursor)

    def test_buttons_and_windows_get_the_cellulose_cursor(self):
        import cursors
        if not cursors.enabled():
            self.skipTest("SPECTRUM_SYSTEM_CURSOR=1")
        button = QPushButton("Teste")
        button.show()
        self.pump()
        self.assertEqual(button.cursor().shape(), Qt.BitmapCursor)
        button.close()

    def test_only_two_themes_exist(self):
        from appearance import PALETTES
        self.assertEqual(set(PALETTES), {"noturno", "light"})
        with self.assertRaises(ValueError):
            self.manager.set_theme("dark", persist=False)

    def test_theme_switch_updates_the_application(self):
        for theme in ("light", "noturno"):
            self.manager.set_theme(theme, persist=False)
            self.assertEqual(self.app.property("spectrum_theme"), theme)

    def test_canvas_has_no_texture_in_both_themes(self):
        """Sem textura de celulose; o fundo tem só brilhos suaves (para a translucidez aparecer)."""
        import scada_ui
        from appearance import TEXTURE_FILES
        self.assertEqual(TEXTURE_FILES, {})
        for theme in ("light", "noturno"):
            self.manager.set_theme(theme, persist=False)
            root = scada_ui.CanvasRoot()
            root.resize(420, 300)
            self.assertGreaterEqual(len(distinct_pixels(root.grab(), 5, 5)), 1)
        self.manager.set_theme("noturno", persist=False)

    def test_legacy_theme_names_migrate_to_noturno(self):
        from appearance import LEGACY_THEMES
        self.assertEqual(LEGACY_THEMES.get("dark"), "noturno")
        self.assertEqual(LEGACY_THEMES.get("gold"), "noturno")

    def test_panels_are_translucent_over_the_background(self):
        """O painel é translúcido: o brilho do fundo aparece por trás dele (mais de uma cor na área)."""
        import scada_ui
        for theme in ("light", "noturno"):
            self.manager.set_theme(theme, persist=False)
            root = scada_ui.CanvasRoot()
            layout = QVBoxLayout(root)
            box = scada_ui.panel()
            layout.addWidget(box)
            root._scada_style_factory = scada_ui.dashboard_style
            root.resize(420, 300)
            root.show()
            self.manager.apply_widget(root)
            self.pump()
            region = root.grab().copy(box.geometry())
            self.assertGreater(len(distinct_pixels(region, 20, 20)), 1, f"painel opaco em {theme}")
            root.close()
        self.manager.set_theme("noturno", persist=False)

    def test_analysis_indicator_renders_every_state(self):
        from analysis_indicator import AnalysisIndicator
        for theme in ("noturno", "light"):
            self.manager.set_theme(theme, persist=False)
            for state in messages.known_states():
                indicator = AnalysisIndicator(lambda s=state: s)
                indicator.resize(900, 92)
                indicator.show()
                indicator.refresh()
                self.pump()
                pixmap = indicator.grab()
                self.assertFalse(pixmap.isNull(), state)
                self.assertGreater(len(distinct_pixels(pixmap, 3, 3)), 3, (theme, state))
                indicator.hide()

    def test_indicator_celebrates_after_a_finished_cycle(self):
        from analysis_indicator import AnalysisIndicator
        current = {"state": "AUTO_ABRINDO_GAVETA"}
        indicator = AnalysisIndicator(lambda: current["state"])
        indicator.resize(900, 92)
        indicator.show()
        indicator.refresh()
        current["state"] = "IDLE"
        indicator.refresh()
        self.assertTrue(indicator.celebrating)
        self.assertEqual(indicator.current_text()[0], "Análise concluída")

    def test_buttons_get_the_effect_layer_and_ripple(self):
        button = QPushButton("Teste")
        button.resize(160, 44)
        button.show()
        self.pump()
        overlay = getattr(button, "_fx_overlay", None)
        self.assertIsNotNone(overlay)
        QTest.mousePress(button, Qt.LeftButton, Qt.NoModifier, QPoint(30, 20))
        self.pump()
        self.assertEqual(overlay.spring_anim.state(), QAbstractAnimation.Running)
        QTest.mouseRelease(button, Qt.LeftButton, Qt.NoModifier, QPoint(30, 20))
        self.assertFalse(button.grab().isNull())

    def test_busy_shimmer_runs_even_when_button_is_disabled(self):
        button = QPushButton("Realizar leitura")
        button.resize(200, 44)
        button.show()
        self.pump()
        button.setEnabled(False)
        button.setProperty("fxBusy", True)
        self.pump()
        self.assertTrue(button._fx_overlay.busy_timer.isActive())
        button.setProperty("fxBusy", False)
        self.pump()
        self.assertFalse(button._fx_overlay.busy_timer.isActive())

    def test_settings_has_only_the_appearance_section(self):
        from PyQt5.QtWidgets import QFrame
        dialog = self._dialog()
        sections = [f for f in dialog.findChildren(QFrame) if f.objectName() == "settingsSection"]
        self.assertEqual(len(sections), 1)
        self.assertTrue(hasattr(dialog, "reduce_motion"))
        dialog.close()

    def test_settings_theme_buttons_switch_theme(self):
        dialog = self._dialog()
        dialog.theme_buttons["light"].click()
        self.assertEqual(self.manager.theme, "light")
        self.assertTrue(dialog.theme_buttons["light"].isChecked())
        self.assertFalse(dialog.theme_buttons["noturno"].isChecked())
        dialog.theme_buttons["noturno"].click()
        self.assertEqual(self.manager.theme, "noturno")
        dialog.close()

    def test_theme_switch_with_crossfade_leaves_no_overlay_behind(self):
        from PyQt5.QtWidgets import QWidget
        host = QWidget()
        host.resize(300, 200)
        host.show()
        self.pump()
        before = len(host.findChildren(QWidget))
        self.manager.set_theme("light", persist=False)
        self.manager.set_theme("noturno", persist=False)
        QTest.qWait(700)
        self.assertEqual(len(host.findChildren(QWidget)), before)
        host.close()

    def test_press_effect_honors_reduced_motion(self):
        import motion
        motion.set_reduced(True)
        try:
            button = QPushButton("Teste")
            button.resize(160, 44)
            button.show()
            self.pump()
            QTest.mousePress(button, Qt.LeftButton, Qt.NoModifier, QPoint(30, 20))
            self.pump()
            self.assertEqual(button._fx_overlay.spring_anim.state(), QAbstractAnimation.Stopped)
            QTest.mouseRelease(button, Qt.LeftButton, Qt.NoModifier, QPoint(30, 20))
        finally:
            motion.set_reduced(False)

    # ---- Legibilidade e vetores coloridos
    def test_colored_faces_and_glyphs_paint_in_both_themes(self):
        import emoji_icons
        for theme in ("noturno", "light"):
            self.manager.set_theme(theme, persist=False)
            for kind in ("bolt", "trend", "leaf", "drop"):
                icon = emoji_icons.GlyphIcon(kind, 28)
                icon.show()
                self.assertGreater(len(distinct_pixels(icon.grab(), 3, 3)), 3, (theme, kind))
        self.manager.set_theme("noturno", persist=False)

    def test_calibration_card_has_no_compressed_text(self):
        try:
            from main import CardKpiCalibracao
        except Exception as error:   # importar o main exige as dependências do equipamento
            self.skipTest(f"main não importável aqui: {error}")
        for theme in ("noturno", "light"):
            self.manager.set_theme(theme, persist=False)
            card = CardKpiCalibracao()
            card.resize(330, 220)
            card.show()
            self.manager.apply_widget(card)
            self.pump()
            for label in (card.lbl_r2, card.lbl_rmse, card.lbl_n):
                self.assertGreaterEqual(QFontInfo(label.font()).pixelSize(), 12, (theme, label.text()))
                self.assertLessEqual(label.sizeHint().width(), label.width() + 1, (theme, label.text()))
            card.close()
        self.manager.set_theme("noturno", persist=False)

    def test_credits_link_to_the_authors_github(self):
        import version
        html = version.credits_html()
        self.assertIn("github.com/DaviBaracat", html)
        self.assertIn("github.com/indiolibanes", html)
        self.assertIn("github.com/yosemate", html)
        self.assertIn("Davi Baracat", html)
        self.assertIn("Kauê Alencar", html)
        self.assertIn("Mateus Ferreira", html)

    def test_chart_bars_get_one_color_per_band(self):
        from animated_chart import SingleBarWidget
        from appearance import series_colors
        colors = []
        for index in range(len(series_colors())):
            bar = SingleBarWidget("450nm", "#087D7B", "Azul")
            bar.series_index = index
            colors.append(bar.band_color())
        self.assertEqual(len(set(colors)), len(colors))

    def test_adaptive_canvas_never_clips_the_layout_minimum(self):
        from responsive_layout import ScaledCanvasView
        for size in ((800, 1280), (1024, 600), (1366, 768), (1920, 1080)):
            content = QWidget()
            layout = QVBoxLayout(content)
            layout.addWidget(QPushButton("Ação"))
            content.setMinimumSize(900, 520)
            view = ScaledCanvasView(content, parent=None, adaptive=True)
            view.resize(*size)
            view.show()
            self.pump()
            self.assertGreaterEqual(content.width(), 900)
            self.assertGreaterEqual(content.height(), 520)
            view.close()

    # ---- janelas de detalhe e painel compacto (ISA-101) -----------------------------------
    def _fake_window(self, raw=None, snv=None):
        import collections
        import detail_windows
        window = QWidget()
        window._result_valid = raw is not None
        window.current_scan_data = raw
        window.current_r_snv = snv
        window._kpi_history = collections.deque(maxlen=detail_windows.HISTORY_LENGTH)
        window.txt_console = QTextEdit()
        return window

    def test_temperature_label_colors_follow_the_level(self):
        import kpi_status as ks
        from diagnostics import TemperatureLabel
        label = TemperatureLabel("esp32")
        label.setText("42,0 °C")
        label.resize(160, 24)
        seen = set()
        for celsius, level in ((None, ks.NONE), (5, ks.COLD), (42, ks.OK), (70, ks.ATTENTION), (90, ks.ERROR)):
            label.set_celsius(celsius)
            self.assertEqual(label.level, level)
            label.show()
            self.pump()
            image = label.grab().toImage()
            seen.add(image.pixel(6, label.height() // 2))   # centro do marcador
        self.assertEqual(len(seen), 5, "cada nível deve ter uma cor própria")

    def test_detail_dialog_renders_every_indicator_in_both_themes(self):
        import detail_windows
        import kpi_status as ks
        raw = [12000, 65500, 21000, 19000, 15000, 11000]   # um canal saturado: estado de erro
        snv = [0.12, 0.18, 0.21, 0.19, 0.15, 0.11]
        for theme in ("noturno", "light"):
            self.manager.set_theme(theme, persist=False)
            for data in ((raw, snv), (None, None)):
                window = self._fake_window(*data)
                if data[0]:
                    for _ in range(4):
                        window._kpi_history.append(detail_windows.make_entry(*data))
                for kind in ks.KINDS:
                    dialog = detail_windows.KpiDetailDialog(window, kind)
                    dialog.show()
                    self.pump()
                    self.assertFalse(dialog.grab().isNull(), (theme, kind))
                    if data[0] and kind in ("energy", "peak"):
                        self.assertIn("680 nm", dialog.lbl_headline.text())
                    dialog.close()
        self.manager.set_theme("noturno", persist=False)

    def test_terminal_dialog_takes_over_the_console(self):
        import detail_windows
        window = self._fake_window()
        window.txt_console.append("[12:00:00] PING")
        dialog = detail_windows.TerminalDialog(window)
        dialog.show()
        self.pump()
        self.assertIs(window.txt_console.parentWidget(), dialog)
        self.assertTrue(window.txt_console.isVisible())
        self.assertIn("PING", window.txt_console.toPlainText())
        dialog.close()

    def test_plot_widget_draws_bars_history_and_empty_state(self):
        import detail_windows
        plot = detail_windows.PlotWidget()
        plot.resize(520, 240)
        plot.show()
        self.pump()
        empty = distinct_pixels(plot.grab(), 7, 5)
        plot.set_bars([100, 60000, 30000], ["a", "b", "c"], ["#2A78D6", "#EB6834", "#1BAF7A"], 70000,
                      ref_lines=((65500, "Saturação", "error"),), unit="ADC")
        bars = distinct_pixels(plot.grab(), 7, 5)
        plot.set_history([1.0, None, 1.4, 5.0], 0, 3.5, band=(0.2, 3.0), unit="razão")
        history = distinct_pixels(plot.grab(), 7, 5)
        self.assertGreater(len(bars), len(empty))
        self.assertGreater(len(history), 4)

    def test_chart_bar_turns_red_when_saturated(self):
        from animated_chart import SingleBarWidget
        bar = SingleBarWidget("680nm", "#087D7B", "Vermelho")
        bar.series_index = 1
        bar.resize(90, 240)
        bar._current_value = 90.0
        bar.max_value = 100.0
        normal = bar.grab().toImage().pixel(45, 140)
        bar.saturated = True
        saturated = bar.grab().toImage().pixel(45, 140)
        self.assertNotEqual(normal, saturated)


if __name__ == "__main__":
    unittest.main()

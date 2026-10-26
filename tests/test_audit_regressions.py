"""Software regression evidence; no actuator or validated analytical claims."""
import os
import subprocess
import tempfile
import unittest
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import Mock, patch

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
os.environ.setdefault("SPECTRUM_LAB_DATA_DIR", tempfile.mkdtemp(prefix="spectrum-audit-"))
ROOT = Path(__file__).resolve().parents[1]

class MotionDeadlineTests(unittest.TestCase):
    def test_firmware_deadline_with_continuous_heartbeat_and_clock_wrap(self):
        import shutil
        if not shutil.which("g++"):
            self.skipTest("g++ required for host predicate test")
        source = next((ROOT / "firmware").glob("*/*/*.ino")).read_text()
        start = source.index("bool prazoMovimentoExcedido(")
        end = source.index("\n}", start) + 2
        predicate = source[start:end].replace("unsigned long", "uint32_t")
        program = "#include <cstdint>\n#include <cassert>\n" + predicate + r"""
int main() {
  uint32_t heartbeat = 0;
  for (uint32_t now=0; now<15000; now+=10) {
    heartbeat=now;
    assert(!prazoMovimentoExcedido(now,0,15000,2000,false,true));
  }
  assert(heartbeat==14990);
  assert(prazoMovimentoExcedido(15000,0,15000,2000,false,true));
  assert(prazoMovimentoExcedido(2000,0,15000,2000,true,false));
  assert(!prazoMovimentoExcedido(1999,0,15000,2000,true,false));
  assert(prazoMovimentoExcedido(14989,UINT32_MAX-10,15000,2000,false,true));
}
"""
        with tempfile.TemporaryDirectory() as directory:
            path=Path(directory)/"motion.cpp"; path.write_text(program)
            binary=Path(directory)/"motion"
            subprocess.run(["g++", "-std=c++11", str(path), "-o", str(binary)],check=True)
            subprocess.run([str(binary)],check=True)

class GuiAuditTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        from PyQt5.QtWidgets import QApplication
        global _APP
        _APP=QApplication.instance() or QApplication([])
        cls.app=_APP

    def test_relative_response_150_percent_is_preserved_and_scale_expands(self):
        from animated_chart import SpectralSplineChartWidget
        chart=SpectralSplineChartWidget()
        chart.set_unit_mode("%")
        chart.update_spectrum([1000]*6,[1.5]*6,[1/6]*6)
        self.assertEqual(chart._percent_values,[150.0]*6)
        self.assertTrue(all(bar.max_value>=150 for bar in chart.bars))

    def test_detail_has_no_reading_until_result_valid(self):
        from detail_windows import available_reading
        w=SimpleNamespace(current_scan_data=[6000]*6,current_r_snv=[1/6]*6,_result_valid=False)
        self.assertEqual(available_reading(w),(None,None))
        w._result_valid=True
        self.assertEqual(available_reading(w)[0],[6000]*6)

    def test_emergency_ack_does_not_rearm(self):
        from main import SpectrumLabMainWindow
        w=SpectrumLabMainWindow()
        try:
            w.fsm_state="EMERGENCIA"; w._emergency_lock_active=False
            w._handle_emergency_confirmed()
            w._on_emergency_lock_timeout()
            self.assertEqual(w.fsm_state,"EMERGENCIA")
            self.assertTrue(w._emergency_confirmed)
        finally:
            w.serial_worker.disconnect_connection();w.hide()

    def test_uncaught_exception_attempts_stop_and_latches_fault(self):
        import main
        w=main.SpectrumLabMainWindow()
        try:
            with patch.object(w.serial_worker,"send_emergency",return_value=True) as stop, patch.object(w,"is_serial_connected",return_value=True), patch.object(main.QMessageBox,"critical"):
                main.global_exception_handler(RuntimeError,RuntimeError("audit failure"),None)
                self.assertEqual(w.fsm_state,"FALHA")
                self.assertFalse(w._result_valid)
                stop.assert_called()
        finally:
            w.serial_worker.disconnect_connection();w.hide()

    def test_failed_save_is_visible_and_retry_preserves_record(self):
        from main import SpectrumLabMainWindow
        w=SpectrumLabMainWindow()
        try:
            w._current_sample_id="SAVE-FAIL"
            w._freeze_trial_context()
            with patch.object(w.chem_engine,"calculate_relative_reflectance",return_value=[.5]*6), patch.object(w.auth_manager,"inserir_leitura",side_effect=OSError("disk test")):
                w.process_raw_spectral_data([6000]*6)
            self.assertEqual(w._persistence_state,"NAO_SALVO")
            self.assertIn("NÃO SALVO",w.lbl_metodo_info.text())
            self.assertEqual(w._pending_reading_record["codigo_amostra"],"SAVE-FAIL")
            with patch.object(w.auth_manager,"inserir_leitura",return_value=42) as save:
                w.retry_save_result()
                self.assertEqual(save.call_args.args[0]["codigo_amostra"],"SAVE-FAIL")
            self.assertEqual(w._persistence_state,"SALVO")
            self.assertIsNone(w._pending_reading_record)
        finally:
            w.serial_worker.disconnect_connection();w.hide()

    def test_context_is_frozen_against_login_and_connection_edits(self):
        from main import SpectrumLabMainWindow
        w=SpectrumLabMainWindow()
        try:
            w._current_sample_id="EXTERNAL-42";w.current_operator_name="Alice"
            w._connection_origin="SIMULADA";w._device_identity={"device_id":"fake"}
            w._freeze_trial_context()
            w.current_operator_name="Bob";w._connection_origin="REAL"
            self.assertEqual(w._trial_context["operator"],"Alice")
            self.assertEqual(w._trial_context["origin"],"SIMULADA")
            self.assertIn("+00:00",w._trial_context["started_at"])
        finally:
            w.serial_worker.disconnect_connection();w.hide()

class PersistenceAuditTests(unittest.TestCase):
    def test_origin_and_context_survive_database_roundtrip(self):
        from database import DatabaseManager
        with tempfile.TemporaryDirectory() as directory:
            db=DatabaseManager(str(Path(directory)/"db.sqlite"))
            key=db.inserir_leitura({"origin":"SIMULADA","trial_context_json":'{"trial_id":"test"}'})
            row=db.obter_leitura_por_id(key)
            self.assertEqual(row["origin"],"SIMULADA")
            self.assertEqual(row["trial_context_json"],'{"trial_id":"test"}')

class GuiSubprocessTests(unittest.TestCase):
    def test_gui_safety_regressions_in_isolated_qt_process(self):
        import sys
        env = dict(os.environ, SPECTRUM_AUDIT_CHILD="1")
        result = subprocess.run([sys.executable, "-m", "unittest", "discover", "-s", "tests", "-p", "test_audit_regressions.py", "-v"],
                                cwd=ROOT, env=env, text=True, stdout=subprocess.PIPE, stderr=subprocess.STDOUT, timeout=45)
        self.assertEqual(result.returncode, 0, result.stdout)


def load_tests(loader, tests, pattern):
    # QApplication and global exception-hook probes own process-wide state.
    # Keep them isolated from the appearance suite, as the TCP integration already does.
    classes = (GuiAuditTests,) if os.environ.get("SPECTRUM_AUDIT_CHILD") else (MotionDeadlineTests, PersistenceAuditTests, DataIntegrityTests, GuiSubprocessTests)
    suite = unittest.TestSuite()
    for case in classes:
        suite.addTests(loader.loadTestsFromTestCase(case))
    return suite

class DataIntegrityTests(unittest.TestCase):
    def test_invalidation_requires_admin_and_preserves_original_with_audit(self):
        import sqlite3
        from database import DatabaseManager
        with tempfile.TemporaryDirectory() as directory:
            path=str(Path(directory)/'test.sqlite')
            db=DatabaseManager(path)
            with sqlite3.connect(path) as conn:
                conn.execute("INSERT INTO usuarios(username,password_hash,role) VALUES('op','test','operador')")
                conn.execute("INSERT INTO usuarios(username,password_hash,role) VALUES('admin','test','admin')")
            key=db.inserir_leitura({'codigo_amostra':'KEEP','kappa_estimado':12.3})
            with self.assertRaises(PermissionError):db.excluir_leitura(key)
            with self.assertRaises(PermissionError):db.invalidar_leitura(key,1,'motivo')
            with self.assertRaises(ValueError):db.invalidar_leitura(key,2,' ')
            self.assertTrue(db.invalidar_leitura(key,2,'Teste documentado'))
            row=db.obter_leitura_por_id(key)
            self.assertEqual(row['kappa_estimado'],12.3)
            self.assertEqual(row['invalidated_by'],'admin')
            with sqlite3.connect(path) as conn:
                self.assertEqual(conn.execute('SELECT COUNT(*) FROM audit_events').fetchone()[0],1)
            self.assertFalse(db.invalidar_leitura(key,2,'duplicada'))

    def test_simulator_rejects_open_chamber_and_emergency_interrupts_wait(self):
        from run.fake_esp32 import Bancada,responder
        import threading
        bench=Bancada(seed=8)
        bench.carcaca_fechada=False;bench.sensor_avancado=True
        messages=[]
        responder(bench,'LER_ESPECTRO:blocked',messages.append)
        self.assertFalse(any(m.startswith('SCAN:') for m in messages))
        bench.carcaca_fechada=True;messages.clear()
        worker=threading.Thread(target=responder,args=(bench,'LER_ESPECTRO:cancel',messages.append))
        worker.start()
        responder(bench,'EMERGENCIA',messages.append)
        worker.join(timeout=1)
        self.assertFalse(worker.is_alive())
        self.assertIn('STATUS:EMERGENCIA_ACIONADA',messages)
        self.assertFalse(any(m.startswith('SCAN:') for m in messages))

    def test_backup_restore_retains_records_and_refuses_overwrite(self):
        import sqlite3, shutil
        from database import DatabaseManager
        from run.backup_database import backup_database
        with tempfile.TemporaryDirectory() as directory:
            base=Path(directory); source=base/'source.db'; backup=base/'backup.db'
            db=DatabaseManager(str(source)); key=db.inserir_leitura({'codigo_amostra':'RESTORE'})
            backup_database(source,backup)
            with self.assertRaises(FileExistsError):backup_database(source,backup)
            restored=base/'restored.db';shutil.copy2(backup,restored)
            self.assertEqual(DatabaseManager(str(restored)).obter_leitura_por_id(key)['codigo_amostra'],'RESTORE')
            with sqlite3.connect(restored) as conn:
                self.assertEqual(conn.execute('PRAGMA integrity_check').fetchone()[0],'ok')

    def test_simulator_seed_is_repeatable(self):
        from run.fake_esp32 import Bancada
        self.assertEqual(Bancada(seed=55).amostra(False),Bancada(seed=55).amostra(False))

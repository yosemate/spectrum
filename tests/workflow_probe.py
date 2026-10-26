"""Exercise the actual GUI FSM against the TCP simulator, with human decisions scripted."""
import os
import sys
import time
import socket
import threading
from pathlib import Path
from unittest.mock import patch

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from PyQt5.QtWidgets import QApplication, QDialog, QMessageBox
from PyQt5.QtTest import QTest
import run.fake_esp32 as sim
import main

sim.ATRASO_MOVIMENTO = .01
sim.ATRASO_LEITURA = .01
server = socket.socket();server.bind(('127.0.0.1',0));server.listen(1)
bench=sim.Bancada(seed=42)
def serve():
    connection,address=server.accept()
    sim.atender(connection,address,bench)
thread=threading.Thread(target=serve,daemon=True);thread.start()
sys.excepthook=lambda *args: (sys.__excepthook__(*args),os._exit(2))
app=QApplication([])
w=main.SpectrumLabMainWindow()
w.show()
def until(predicate,seconds=30):
    end=time.monotonic()+seconds
    while not predicate() and time.monotonic()<end:
        if w.fsm_state in ('FALHA','EMERGENCIA'):
            raise AssertionError(w.lbl_cycle_status.text())
        QTest.qWait(20)
    assert predicate(), (w.fsm_state,w.lbl_cycle_status.text())
def finish(self):
    self.selected_action=self.ACTION_FINISH
    return QDialog.Accepted
try:
    with patch.object(QMessageBox,'information',return_value=QMessageBox.Ok), patch.object(QMessageBox,'question',return_value=QMessageBox.Yes), patch.object(main.SamplePlacementInterlockDialog,'exec_',return_value=QDialog.Accepted), patch.object(main.CalibrationTransitionDialog,'exec_',return_value=QDialog.Accepted), patch.object(main.DarkSafetyInterlockDialog,'exec_',return_value=QDialog.Accepted), patch.object(main.DialogDecisaoConclusao,'exec_',finish):
        w.current_operator_name='workflow-operator'
        w.authenticated_user={'id':1,'username':'workflow-operator','role':'operador'}
        w.combo_conn_mode.setCurrentIndex(w.combo_conn_mode.findData('WIFI'))
        w.txt_ip.setText('127.0.0.1');w.txt_tcp_port.setText(str(server.getsockname()[1]))
        w._start_connection()
        until(lambda:w._protocol_ready and w._sensor_ready and w.equipment.capable and w.is_simulation_target())
        w.start_white_calibration_cycle()
        until(lambda:w.fsm_state=='IDLE' and w.chem_engine.calibration_valid())
        assert len(w._white_scans)==10 and len(w._dark_scans)==10
        w.input_sample_id.setText('TRACE-42')
        w.start_simple_auto_cycle()
        until(lambda:w.fsm_state=='IDLE' and w._result_valid)
        records=w.auth_manager.listar_leituras()
        assert len(records)==1, records
        row=records[0]
        assert row['codigo_amostra']=='TRACE-42'
        assert row['origin']=='SIMULADA'
        assert row['operador']=='workflow-operator'
        assert row['acquisition_count']==5
        import json
        context=json.loads(row['trial_context_json'])
        assert context['origin']=='SIMULADA' and context['trial_id']
        from pdf_generator import generate_pdf_report
        output=Path(os.environ['SPECTRUM_LAB_DATA_DIR'])/'workflow.pdf'
        generate_pdf_report(str(output),sample_id=row['codigo_amostra'],operator=row['operador'],kappa_value=row['kappa_estimado'],
                            values=[v*100 for v in w.current_r_calibrated],raw_adc_values=w.current_scan_data,
                            timestamp=w._current_reading_timestamp,calibration_snapshot=w._current_calibration_snapshot,trial_context=context,
                            raw_scans=w._last_acquisition_scans)
        assert output.stat().st_size>1000
        import shutil, subprocess
        if shutil.which('pdftotext'):
            text=subprocess.check_output(['pdftotext',str(output),'-'],text=True)
            assert 'SIMULADA' in text and 'TRACE-42' in text
        w.grab().save(str(Path(os.environ['SPECTRUM_LAB_DATA_DIR'])/'workflow.png'))
        w._on_serial_connection_changed(False,'test disconnect')
        assert not w._result_valid and w.lbl_kappa_valor.text()=='--'
        print('FULL WORKFLOW OK: white/dark -> sample -> quality -> SQLite -> PDF -> disconnect invalidation')
finally:
    w.serial_worker.disconnect_connection();w.hide();server.close();thread.join(timeout=2)

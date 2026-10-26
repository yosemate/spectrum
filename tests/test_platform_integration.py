"""Abre a janela real e conecta seu worker ao simulador por um socket TCP real."""
import os
import socket
import subprocess
import sys
import tempfile
import threading
import time
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


class PlatformIntegrationTests(unittest.TestCase):
    def test_window_and_tcp_scan(self):
        from run.fake_esp32 import Bancada, atender
        server = socket.socket()
        server.bind(('127.0.0.1', 0))
        server.listen(1)
        server.settimeout(20)
        port = server.getsockname()[1]

        def serve():
            connection, address = server.accept()
            atender(connection, address, Bancada())

        thread = threading.Thread(target=serve, daemon=True)
        thread.start()
        script = r'''
import sys, time
from PyQt5.QtWidgets import QApplication
from PyQt5.QtTest import QTest
import main
# Falhas em slots Qt devem falhar o teste, sem abrir diálogos modais.
sys.excepthook = lambda *args: (sys.__excepthook__(*args), sys.exit(2))
app = QApplication([])
window = main.SpectrumLabMainWindow()
window.show()
window.combo_conn_mode.setCurrentIndex(window.combo_conn_mode.findData('WIFI'))
window.txt_ip.setText('127.0.0.1')
window.txt_tcp_port.setText(sys.argv[1])
worker = window.serial_worker
scans = []
worker.scan_received.connect(lambda token, values: scans.append((token, values)))
window._start_connection()
def until(predicate):
    end = time.monotonic() + 8
    while not predicate() and time.monotonic() < end:
        QTest.qWait(25)
    assert predicate(), 'Timeout aguardando protocolo/scan'
try:
    until(lambda: window._protocol_ready and window._sensor_ready and window.equipment.capable)
    assert window.is_simulation_target()
    worker.send_command('CMD:AVANCAR_SENSOR')
    until(lambda: window.equipment.carriage_advanced)
    worker.send_command('CMD:LER_ESPECTRO:platform_test')
    until(lambda: bool(scans))
    assert scans[0][0] == 'platform_test' and len(scans[0][1]) == 6
    assert not window.grab().isNull()
finally:
    worker.disconnect_connection()
    assert not worker.isRunning()
    window.hide()
print('GUI, handshake, telemetria e scan TCP: OK')
'''
        with tempfile.TemporaryDirectory() as data:
            env = dict(os.environ, SPECTRUM_LAB_DATA_DIR=data)
            env.setdefault('QT_QPA_PLATFORM', 'offscreen')
            try:
                result = subprocess.run([sys.executable, '-c', script, str(port)],
                                        cwd=ROOT, env=env, text=True,
                                        stdout=subprocess.PIPE, stderr=subprocess.STDOUT, timeout=30)
                self.assertEqual(result.returncode, 0, result.stdout)
            finally:
                server.close()
                thread.join(timeout=2)


if __name__ == '__main__':
    unittest.main()

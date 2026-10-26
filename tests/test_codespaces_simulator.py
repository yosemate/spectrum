"""Testes de contrato do simulador TCP, sem interface gráfica ou hardware."""
import re
import unittest
from run.fake_esp32 import Bancada, responder

class CodespacesSimulatorTests(unittest.TestCase):
    def setUp(self):
        self.bancada = Bancada()
        self.bancada.sensor_avancado = True
        self.messages = []
        self.send = self.messages.append

    def test_handshake(self):
        self.assertTrue(responder(self.bancada, "PING", self.send))
        self.assertIn("STATUS:PROTOCOLO_2", self.messages)
        self.assertIn("STATUS:SENSOR_OK", self.messages)
        self.assertIn("STATUS:PONG", self.messages)

    def test_spectral_scan_has_token(self):
        token = "abc123_token"
        responder(self.bancada, "LER_ESPECTRO:" + token, self.send)
        scans = [m for m in self.messages if m.startswith("SCAN:")]
        self.assertEqual(len(scans), 1)
        self.assertTrue(scans[0].startswith("SCAN:" + token + "|DATA:"))
        self.assertEqual(len(scans[0].split("|DATA:")[1].split(",")), 6)
        self.assertIn("STATUS:LEITURA_CONCLUIDA:" + token, self.messages)
        self.assertFalse(any(m.startswith("DATA:") for m in self.messages))

    def test_dark_scan(self):
        responder(self.bancada, "LER_ESCURO:dark1", self.send)
        self.assertIn("STATUS:LEITURA_CONCLUIDA:dark1", self.messages)
        self.assertTrue(any(m.startswith("SCAN:dark1|DATA:") for m in self.messages))

    def test_invalid_ids_are_rejected(self):
        for bad in ("LER_ESPECTRO", "LER_ESCURO:", "LER_ESPECTRO:bad token", "LER_ESPECTRO:"+"x"*65):
            with self.subTest(bad=bad):
                messages = []
                responder(self.bancada, bad, messages.append)
                self.assertEqual(messages, ["STATUS:COMANDO_ERRO:ID_INVALIDO"])

    def test_emergency(self):
        responder(self.bancada, "EMERGENCIA", self.send)
        self.assertIn("STATUS:EMERGENCIA_ACIONADA", self.messages)

if __name__ == "__main__":
    unittest.main()

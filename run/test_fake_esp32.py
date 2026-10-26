"""Regressões do ESP32 virtual; não envolve placa ou amostragem real."""
import unittest
from unittest.mock import patch
import fake_esp32 as sim


class FakeESP32Tests(unittest.TestCase):
    def setUp(self):
        self.bancada = sim.Bancada()
        self.bancada.sensor_avancado = True
        self.rx = []

    def command(self, cmd):
        self.assertTrue(sim.responder(self.bancada, cmd, self.rx.append))

    def test_motion_sends_updated_limits_before_confirmation(self):
        with patch.object(sim.time, "sleep", return_value=None):
            self.command("ABRIR_PORTA")
            self.assertIn("PORTA:ABERTA:1|FECHADA:0", self.rx[-2])
            self.assertEqual(self.rx[-1], "STATUS:PORTA_ABERTA")
            self.rx.clear()
            self.command("FECHAR_PORTA")
            self.assertIn("PORTA:ABERTA:0|FECHADA:1", self.rx[-2])
            self.assertEqual(self.rx[-1], "STATUS:PORTA_FECHADA")
            self.rx.clear()
            self.command("AVANCAR_SENSOR")
            self.assertIn("SENSOR_AVANCADO:1", self.rx[-2])
            self.assertEqual(self.rx[-1], "STATUS:SENSOR_AVANCADO")

    def test_white_and_dark_scans_have_ids_and_separate_signals(self):
        with patch.object(sim.time, "sleep", return_value=None):
            for kind in ("LER_ESPECTRO", "LER_ESCURO"):
                for n in range(10):
                    token = f"{kind}_{n}"
                    self.rx.clear()
                    self.command(f"{kind}:{token}")
                    self.assertTrue(self.rx[0].startswith(f"SCAN:{token}|DATA:"))
                    self.assertEqual(self.rx[1], f"STATUS:LEITURA_CONCLUIDA:{token}")
                    vals = [float(x) for x in self.rx[0].split("|DATA:")[1].split(",")]
                    self.assertEqual(len(vals), 6)
                    self.assertTrue(all(0 <= v < 65500 for v in vals))

    def test_untagged_scan_never_returns_reading(self):
        self.command("LER_ESPECTRO")
        self.assertEqual(self.rx, ["STATUS:COMANDO_ERRO:ID_INVALIDO"])


if __name__ == "__main__":
    unittest.main()

"""Cose che si sono rotte su Windows provando il template: comandi solo macOS e separatore del PATH."""
import importlib.util
import os
import subprocess
import unittest
from pathlib import Path
from unittest import mock

RADICE = Path(__file__).resolve().parent.parent
spec = importlib.util.spec_from_file_location("server", RADICE / "scripts" / "dashboard" / "server.py")
server = importlib.util.module_from_spec(spec)
spec.loader.exec_module(server)


class PrestazioniTest(unittest.TestCase):
    def test_memoria_fuori_da_macos_non_chiama_sysctl(self):
        with mock.patch.object(server.subprocess, "run", side_effect=AssertionError("sysctl non esiste qui")):
            self.assertEqual(server.memoria("win32", ram=lambda: 31.6), {"totaleGb": 31.6, "swapUsatoMb": None})

    def test_memoria_con_ram_sconosciuta(self):
        self.assertEqual(server.memoria("linux", ram=lambda: None), {"totaleGb": None, "swapUsatoMb": None})

    def test_processi_ollama_senza_ps_e_una_lista_vuota(self):
        with mock.patch.object(server.subprocess, "run", side_effect=FileNotFoundError("ps")):
            self.assertEqual(server.processi_ollama(), [])

    def test_prestazioni_non_cade_senza_comandi_di_macos(self):
        with mock.patch.object(server.subprocess, "run", side_effect=FileNotFoundError("sysctl")):
            self.assertEqual(server.memoria("linux", ram=lambda: 8.0)["swapUsatoMb"], None)
            self.assertEqual(server.processi_ollama(), [])


class AmbienteTest(unittest.TestCase):
    def test_il_path_usa_il_separatore_del_sistema(self):
        with mock.patch.object(server.os, "pathsep", ";"):
            percorso = server.ambiente_azione()["PATH"]
        self.assertTrue(percorso.startswith(str(Path.home() / ".local" / "bin") + ";/opt/homebrew/bin;/usr/local/bin;"), percorso[:120])


if __name__ == "__main__":
    unittest.main()

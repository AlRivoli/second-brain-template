import importlib.util
import unittest
from datetime import datetime
from pathlib import Path

spec = importlib.util.spec_from_file_location("aggiorna_oggi", Path(__file__).resolve().parent / "aggiorna-oggi.py")
aggiorna_oggi = importlib.util.module_from_spec(spec)
spec.loader.exec_module(aggiorna_oggi)


class AggiornaOggi(unittest.TestCase):
    def test_giorno_e_settimana_iso(self):
        t = aggiorna_oggi.testo(datetime(2026, 11, 3, 9, 5))
        self.assertIn("Oggi è martedì 2026-11-03, settimana ISO 2026-W45.", t)
        self.assertIn("alle 09:05", t)

    def test_domenica_e_cambio_anno_iso(self):
        self.assertIn("domenica 2027-01-03, settimana ISO 2026-W53", aggiorna_oggi.testo(datetime(2027, 1, 3)))


if __name__ == "__main__":
    unittest.main()

import importlib.util
import unittest
from datetime import datetime
from pathlib import Path

spec = importlib.util.spec_from_file_location("avvii", Path(__file__).parent / "dashboard" / "avvii.py")
avvii = importlib.util.module_from_spec(spec)
spec.loader.exec_module(avvii)

FERIALI = [(g, 8, 0) for g in range(1, 6)]
MERCOLEDI = datetime(2026, 10, 28, 9, 0)  # mercoledì


class TestAvvii(unittest.TestCase):
    def test_ultimo_previsto_oggi_e_settimanale(self):
        self.assertEqual(avvii.ultimo_previsto(FERIALI, MERCOLEDI), datetime(2026, 10, 28, 8, 0))
        self.assertEqual(avvii.ultimo_previsto([(1, 7, 30)], MERCOLEDI), datetime(2026, 10, 26, 7, 30))

    def test_domenica_zero_vale_sette(self):
        self.assertEqual(avvii.orari({"StartCalendarInterval": {"Weekday": 0, "Hour": 9}}), [(7, 9, 0)])

    def test_prossimo_salta_il_weekend(self):
        self.assertEqual(avvii.prossimo_previsto(FERIALI, datetime(2026, 10, 30, 9, 0)), datetime(2026, 11, 2, 8, 0))

    def test_stati(self):
        previsto = datetime(2026, 10, 28, 8, 0)
        adesso = datetime(2026, 10, 28, 9, 0)
        acceso = datetime(2026, 10, 28, 12, 55)
        self.assertEqual(avvii.stato_job(previsto, None, adesso, datetime(2026, 10, 28, 8, 5), False, None)[0], "ok")
        self.assertEqual(avvii.stato_job(previsto, None, adesso, datetime(2026, 10, 27, 18, 30), False, None)[0], "mancato")
        self.assertEqual(avvii.stato_job(previsto, None, adesso, None, False, None)[0], "mai")
        self.assertEqual(avvii.stato_job(previsto, None, datetime(2026, 10, 28, 8, 10), None, False, None)[0], "in-attesa")
        self.assertEqual(avvii.stato_job(previsto, None, adesso, None, True, None)[0], "in-corso")
        self.assertEqual(avvii.stato_job(previsto, None, datetime(2026, 10, 28, 14, 0), datetime(2026, 10, 28, 13, 0), False, acceso)[0], "in-ritardo")
        self.assertIn("12:55", avvii.stato_job(previsto, None, datetime(2026, 10, 28, 13, 0), None, False, acceso)[1])


if __name__ == "__main__":
    unittest.main()

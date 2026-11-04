import importlib.util
import unittest
from datetime import date
from pathlib import Path

spec = importlib.util.spec_from_file_location("limiti", Path(__file__).parent / "dashboard" / "limiti.py")
limiti = importlib.util.module_from_spec(spec)
spec.loader.exec_module(limiti)


def misura(**k):
    base = {"Servizio": "Database", "Misura": "Ore", "Usato": "54.3", "Limite": "100", "Unità": "ore", "Agire a": "60", "Periodo": "mese", "Misurato": "2026-10-28"}
    base.update(k)
    return base


class LimitiTest(unittest.TestCase):
    def test_proiezione_lineare_a_fine_mese(self):
        m = limiti.analizza(misura(), date(2026, 10, 30))
        self.assertAlmostEqual(m["previsto"], 54.3 / 28 * 31, places=2)
        self.assertEqual(m["verdetto"], "guarda")          # 60 ore di soglia, previsto 60,12
        self.assertIsNone(m["esaurimento"])

    def test_data_di_esaurimento_e_passaggio_al_piano(self):
        m = limiti.analizza(misura(Usato="90", Misurato="2026-10-15"), date(2026, 10, 15))
        self.assertEqual(m["verdetto"], "passa")
        self.assertEqual(m["esaurimento"], "2026-10-17")   # 6 ore al giorno: 100 ore dopo 16 giorni dal primo
        self.assertIn("finisci il 2026-10-17", m["motivo"])

    def test_resta_gratis_e_misure_senza_proiezione(self):
        self.assertEqual(limiti.analizza(misura(Usato="10"), date(2026, 10, 30))["verdetto"], "ok")
        spazio = limiti.analizza(misura(Misura="Spazio", Usato="9", Limite="1024", Unità="MB", Periodo="totale", **{"Agire a": ""}), date(2026, 10, 30))
        self.assertIsNone(spazio["previsto"])
        self.assertEqual(spazio["verdetto"], "ok")
        picco = limiti.analizza(misura(Usato="95", Limite="100", Periodo="giorno"), date(2026, 10, 30))
        self.assertEqual(picco["verdetto"], "guarda")      # sopra il 90% della soglia, sotto il limite

    def test_misura_vecchia_e_verdetto_del_servizio(self):
        self.assertTrue(limiti.analizza(misura(), date(2026, 11, 10))["vecchia"])
        self.assertFalse(limiti.analizza(misura(), date(2026, 11, 2))["vecchia"])
        self.assertEqual(limiti.verdetto_servizio([{"verdetto": "ok"}, {"verdetto": "passa"}, {"verdetto": "guarda"}]), "passa")
        self.assertEqual(limiti.verdetto_servizio([]), "ok")

    def test_spesa_mensile_e_salto_di_piano(self):
        self.assertEqual(limiti.spesa_mensile([{"Rinnovo": "2027-10-09, 15 $"}, {"Rinnovo": ""}]), {"$": 15 / 12})
        piani = [{"Servizio": "Hosting", "Costo": "20", "Valuta": "$"}, {"Servizio": "Database", "Costo": "a consumo", "Valuta": "$"},
                 {"Servizio": "Posta", "Costo": "20", "Valuta": "$"}]
        self.assertEqual(limiti.salto_di_piano(piani, {"Hosting": "passa", "Database": "passa", "Posta": "ok"}), {"$": 20})


class AggiornaMisuraTest(unittest.TestCase):
    def test_cambia_solo_usato_e_data_di_quella_riga(self):
        import tempfile
        sp = importlib.util.spec_from_file_location("servizi", Path(__file__).parent / "dashboard" / "servizi.py")
        servizi = importlib.util.module_from_spec(sp)
        sp.loader.exec_module(servizi)
        testo = "## a\n\n### Misure\n\n| Servizio | Misura | Usato | Limite | Misurato |\n|---|---|---|---|---|\n| N | Ore | 5 | 100 | 2026-10-01 |\n| N | Spazio | 9 | 50 | 2026-10-01 |\n\n## b\n\n### Misure\n\n| Servizio | Misura | Usato | Limite | Misurato |\n|---|---|---|---|---|\n| N | Ore | 1 | 10 | 2026-10-01 |\n"
        with tempfile.TemporaryDirectory() as d:
            f = Path(d) / "s.md"
            f.write_text(testo, encoding="utf-8")
            servizi.aggiorna_misura(f, "a", "N", "Ore", "7,5", "2026-10-30")
            atteso = testo.replace("| N | Ore | 5 | 100 | 2026-10-01 |", "| N | Ore | 7.5 | 100 | 2026-10-30 |")
            self.assertEqual(f.read_text(encoding="utf-8"), atteso)
            with self.assertRaises(LookupError):
                servizi.aggiorna_misura(f, "a", "N", "Boh", "1", "2026-10-30")
            with self.assertRaises(ValueError):
                servizi.aggiorna_misura(f, "a", "N", "Ore", "tanto", "2026-10-30")
            with self.assertRaises(ValueError):
                servizi.aggiorna_misura(f, "a", "N", "Ore", "-3", "2026-10-30")


if __name__ == "__main__":
    unittest.main()

import importlib.util
import tempfile
import unittest
from datetime import datetime
from pathlib import Path

spec = importlib.util.spec_from_file_location("avviso", Path(__file__).resolve().parent / "avviso.py")
avviso = importlib.util.module_from_spec(spec)
spec.loader.exec_module(avviso)


class Avviso(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.v = Path(self.tmp.name)
        (self.v / "daily").mkdir()
        self.marcatore = self.v / "auth.avviso"
        self.notifiche = []

    def tearDown(self):
        self.tmp.cleanup()

    def segnala(self, giorno=3, piattaforma="darwin"):
        return avviso.segnala(self.v, "la chiusura", datetime(2026, 11, giorno, 18, 30), lambda cmd, **kw: self.notifiche.append(cmd),
                              self.marcatore, piattaforma)

    def test_riconosce_l_errore_di_autenticazione(self):
        self.assertTrue(avviso.non_autenticato("Failed to authenticate: OAuth session expired and could not be refreshed"))
        self.assertTrue(avviso.non_autenticato("Not logged in · Please run /login"))
        self.assertFalse(avviso.non_autenticato("eliminare un Club richiede un login recente"))
        self.assertFalse(avviso.non_autenticato(None))

    def test_riga_nel_brief_e_notifica_una_volta_sola(self):
        brief = self.v / "daily" / "2026-11-03.md"
        brief.write_text("# oggi\n", encoding="utf-8")
        self.assertTrue(self.segnala())
        self.assertFalse(self.segnala())  # stesso giorno: niente di nuovo
        self.assertEqual(brief.read_text(encoding="utf-8").count("Da confermare: Claude Code non è autenticato"), 1)
        self.assertEqual(len(self.notifiche), 1)
        self.assertEqual(self.notifiche[0][0], "osascript")

    def test_il_giorno_dopo_avvisa_di_nuovo(self):
        self.segnala()
        self.assertTrue(self.segnala(giorno=4))
        self.assertEqual(len(self.notifiche), 2)

    def test_senza_brief_notifica_lo_stesso_e_non_crea_file(self):
        self.assertTrue(self.segnala())
        self.assertFalse((self.v / "daily" / "2026-11-03.md").exists())
        self.assertEqual(len(self.notifiche), 1)

    def test_fuori_da_macos_non_chiama_osascript(self):
        self.segnala(piattaforma="linux")
        self.assertEqual(self.notifiche, [])


if __name__ == "__main__":
    unittest.main()

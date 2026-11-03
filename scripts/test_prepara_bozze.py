import importlib.util
import tempfile
import unittest
from datetime import datetime
from pathlib import Path

spec = importlib.util.spec_from_file_location("bozze", Path(__file__).resolve().parent / "prepara-bozze.py")
bozze = importlib.util.module_from_spec(spec)
spec.loader.exec_module(bozze)

LUNEDI = datetime(2026, 11, 2, 8, 30)  # settimana ISO 2026-45


class Esito:
    def __init__(self, returncode=0, stdout=""):
        self.returncode, self.stdout = returncode, stdout


class PreparaBozze(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.log = Path(self.tmp.name) / "bozze.log"
        self.lock = Path(self.tmp.name) / "bozze.lock"
        self.sospese = Path(self.tmp.name) / "bozze.sospese"
        self.chiamate = []
        self.ultima = ""            # settimana ISO dell'ultimo commit "bozze settimana"
        self.nuove = "content/linkedin/a.md\ncontent/instagram/b.md\n"
        self.fallisce = set()       # nomi di script che falliscono

    def tearDown(self):
        self.tmp.cleanup()

    def run_finto(self, cmd, **kw):
        self.chiamate.append(cmd)
        if cmd[:2] == ["git", "log"]:
            return Esito(stdout=self.ultima)
        if cmd[:2] == ["git", "ls-files"]:
            return Esito(stdout=self.nuove)
        if cmd[0] != "git" and cmd[0] != "claude":
            nome = Path(cmd[2]).name
            return Esito(1 if nome in self.fallisce else 0)
        return Esito()

    def vai(self, forza=False):
        return bozze.bozze(forza, Path(self.tmp.name), self.log, self.lock, self.run_finto, LUNEDI, self.sospese)

    def nomi(self):
        return [c[0] if c[0] == "claude" else " ".join(c[:2]) if c[0] == "git" else Path(c[2]).name for c in self.chiamate]

    def leggi_log(self):
        return self.log.read_text(encoding="utf-8")

    def test_lock_fresco_salta(self):
        self.lock.mkdir()
        self.vai()
        self.assertEqual(self.chiamate, [])
        self.assertIn("bozze già in corso: salto", self.leggi_log())

    def test_gia_fatto_questa_settimana_salta_ma_forza_no(self):
        self.ultima = "2026-45"
        self.vai()
        self.assertEqual(self.nomi(), ["git log"])
        self.assertIn("già preparate questa settimana: salto", self.leggi_log())
        self.chiamate.clear()
        self.vai(forza=True)
        self.assertIn("claude", self.nomi())

    def test_settimana_scorsa_non_blocca(self):
        self.ultima = "2026-44"
        self.vai()
        self.assertIn("claude", self.nomi())

    def test_nessuna_bozza_nuova(self):
        self.nuove = "\n"
        self.vai()
        self.assertEqual(self.nomi(), ["git log", "attivita-progetti.py", "claude", "git ls-files"])
        self.assertIn("nessuna bozza nuova", self.leggi_log())

    def test_flusso_completo(self):
        self.vai()
        self.assertEqual(self.nomi(), ["git log", "attivita-progetti.py", "claude", "git ls-files", "scarta-bozze.py",
                                       "immagine-bozza.py", "immagine-bozza.py", "verify", "git add", "git commit"])
        self.assertEqual(self.chiamate[4][3], "2026-11-02")
        immagini = [c[3] for c in self.chiamate if c[0] not in ("git", "claude") and c[2].endswith("immagine-bozza.py")]
        self.assertEqual(immagini, ["content/linkedin/a.md", "content/instagram/b.md"])
        self.assertIn("commit: bozze settimana 2026-11-02", self.leggi_log())
        self.assertFalse(self.lock.exists())

    def test_errori_si_segnalano_e_verify_che_fallisce_non_committa(self):
        self.fallisce = {"scarta-bozze.py", "immagine-bozza.py", "verify"}
        self.vai()
        log = self.leggi_log()
        self.assertIn("scarto delle vecchie non riuscito", log)
        self.assertIn("immagine non riuscita: content/linkedin/a.md", log)
        self.assertIn("immagine non riuscita: content/instagram/b.md", log)
        self.assertIn("verify non passa", log)
        self.assertNotIn("git commit", self.nomi())

    def test_dopo_un_verify_fallito_il_giro_dopo_non_riscrive_le_bozze(self):
        self.vault_file("content/linkedin/a.md")
        self.vault_file("content/instagram/b.md")
        self.fallisce = {"verify"}
        self.vai()
        self.assertTrue(self.sospese.exists())
        self.chiamate.clear()
        self.fallisce = set()
        self.vai()  # il verify ora passa
        self.assertNotIn("claude", self.nomi())
        self.assertEqual(self.nomi().count("immagine-bozza.py"), 2)  # le stesse 2 bozze, non altre
        self.assertEqual(self.nomi()[-2:], ["git add", "git commit"])
        self.assertFalse(self.sospese.exists())
        self.assertIn("riprendo le bozze del giro precedente", self.leggi_log())

    def test_il_promemoria_di_un_altra_settimana_non_vale_e_forza_lo_ignora(self):
        self.sospese.write_text('{"settimana": "2026-44", "file": ["content/linkedin/a.md"]}')
        self.vai()
        self.assertIn("claude", self.nomi())
        self.sospese.write_text('{"settimana": "2026-45", "file": ["content/linkedin/a.md"]}')
        self.chiamate.clear()
        self.vai(forza=True)
        self.assertIn("claude", self.nomi())

    def vault_file(self, rel):
        p = Path(self.tmp.name) / rel
        p.parent.mkdir(parents=True, exist_ok=True)
        p.write_text("x")


if __name__ == "__main__":
    unittest.main()

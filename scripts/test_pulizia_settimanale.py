import importlib.util
import io
import json
import tempfile
import unittest
from contextlib import redirect_stdout
from datetime import datetime
from pathlib import Path

spec = importlib.util.spec_from_file_location("pulizia", Path(__file__).resolve().parent / "pulizia-settimanale.py")
pulizia = importlib.util.module_from_spec(spec)
spec.loader.exec_module(pulizia)

VENERDI = datetime(2026, 11, 6, 18, 0)  # settimana ISO 2026-W45


class Esito:
    def __init__(self, returncode=0, stdout=""):
        self.returncode, self.stdout = returncode, stdout


class Pulizia(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.v = Path(self.tmp.name)
        (self.v / "daily").mkdir()
        self.daily = self.v / "daily" / "2026-11-06.md"
        self.daily.write_text("# oggi\n", encoding="utf-8")
        self.uscite = {"claude": "\n".join(f"riga {i}" for i in range(40)), "versioni.py": "- n8n (npm): installata 1, ultima 2",
                       "controllo-skill.py": "tutto ok", "uso-settimanale.py": "## Uso\n- /post: 3", "ruota-log.py": ""}
        self.rc = {}
        self.chiamate = []

    def tearDown(self):
        self.tmp.cleanup()

    def run_finto(self, cmd, **kw):
        self.chiamate.append(cmd)
        for chiave in self.uscite:
            if chiave in " ".join(cmd):
                return Esito(self.rc.get(chiave, 0), self.uscite[chiave] + ("\n" if self.uscite[chiave] else ""))
        return Esito()

    def vai(self, env=None):
        buf = io.StringIO()
        with redirect_stdout(buf):
            pulizia.pulizia(self.v, self.run_finto, env or {}, VENERDI)
        return buf.getvalue()

    def report(self):
        return (self.v / "daily" / "2026-W45-uso.md").read_text(encoding="utf-8")

    def test_dry_run_non_scrive(self):
        self.assertEqual(self.vai({"PULIZIA_DRY_RUN": "1"}), "scriverebbe: daily/2026-W45-uso.md\n")
        self.assertEqual(self.chiamate, [])
        self.assertFalse((self.v / "daily" / "2026-W45-uso.md").exists())

    def test_report_con_le_sezioni_nell_ordine(self):
        self.assertEqual(self.vai(), "scritto: daily/2026-W45-uso.md\n")
        r = self.report()
        sezioni = ["# Pulizia settimanale 2026-W45", "## claude doctor", "## Versioni", "## Skill", "## Uso", "## Rotazione log",
                   "Nessuna skill o comando viene rimosso"]
        self.assertEqual([r.index(s) for s in sezioni], sorted(r.index(s) for s in sezioni))
        self.assertIn("riga 39\n```", r)
        self.assertNotIn("riga 9\n", r)          # solo le ultime 30 righe
        self.assertIn("Nessun log sopra soglia: niente ruotato.", r)
        self.assertIn("- n8n (npm): installata 1, ultima 2", r)

    def test_controllo_skill_fallito_non_ferma_il_report(self):
        self.rc["controllo-skill.py"] = 1
        self.vai()
        self.assertIn("- controllo non riuscito: vedi il log", self.report())

    def test_rimando_nel_brief_una_volta_sola(self):
        self.vai()
        self.vai()
        self.assertEqual(self.daily.read_text(encoding="utf-8").count("[[daily/2026-W45-uso]]"), 1)

    def test_due_giri_di_fila_lasciano_un_solo_report(self):
        self.vai()
        self.vai()
        self.assertEqual(sorted(p.name for p in (self.v / "daily").iterdir()), ["2026-11-06.md", "2026-W45-uso.md"])

    def test_skill_nuove_si_segnalano_una_volta(self):
        (self.v / "daily" / "2026-W45-skill.json").write_text(json.dumps({"skill": [{"stato": "nuova"}, {"stato": "ok"}, {"stato": "nuova"}]}))
        self.vai()
        self.vai()
        testo = self.daily.read_text(encoding="utf-8")
        self.assertEqual(testo.count("- Skill: 2 versioni nuove"), 1)

    def test_senza_brief_di_oggi_scrive_solo_il_report(self):
        self.daily.unlink()
        self.vai()
        self.assertFalse(self.daily.exists())
        self.assertTrue((self.v / "daily" / "2026-W45-uso.md").exists())


if __name__ == "__main__":
    unittest.main()

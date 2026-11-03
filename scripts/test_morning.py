import importlib.util
import io
import tempfile
import unittest
from contextlib import redirect_stdout
from datetime import date
from pathlib import Path

spec = importlib.util.spec_from_file_location("morning", Path(__file__).resolve().parent / "morning.py")
morning = importlib.util.module_from_spec(spec)
spec.loader.exec_module(morning)


class Esito:
    def __init__(self, rc):
        self.returncode = rc


class Morning(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.app = Path(self.tmp.name) / "Obsidian.app"
        self.vault = Path("/x/second-brain")
        self.chiamate = []

    def tearDown(self):
        self.tmp.cleanup()

    def lancia(self, rc_per_comando=None):
        def run(cmd, **kw):
            self.chiamate.append(cmd)
            return Esito((rc_per_comando or {}).get(cmd[0], 0))
        return run

    def vai(self, run, env=None, **kw):
        buf = io.StringIO()
        with redirect_stdout(buf):
            rc = morning.morning(self.vault, run, env or {}, date(2026, 11, 3), self.app, **kw)
        return rc, buf.getvalue()

    def test_dry_run_stampa_e_non_esegue(self):
        rc, out = self.vai(self.lancia(), {"MORNING_DRY_RUN": "1"})
        self.assertEqual((rc, self.chiamate), (0, []))
        self.assertIn("claude --permission-mode dontAsk", out)
        self.assertIn("'Bash(git log *)'", out)

    def test_brief_verify_e_obsidian(self):
        self.app.mkdir()
        rc, out = self.vai(self.lancia())
        self.assertEqual(rc, 0)
        self.assertEqual(out.strip(), "verify: OK")
        self.assertEqual(self.chiamate[0][0], "claude")
        self.assertEqual(self.chiamate[1][-1], "scripts/verify")
        self.assertEqual(self.chiamate[2], ["open", "obsidian://open?vault=second-brain&file=daily/2026-11-03"])

    def test_senza_obsidian_non_apre_e_verify_che_fallisce_si_segnala(self):
        def run(cmd, **kw):
            self.chiamate.append(cmd)
            return Esito(1 if cmd[-1] == "scripts/verify" else 0)
        rc, out = self.vai(run)
        self.assertEqual((rc, out.strip()), (0, "verify: problemi, vedi sopra"))
        self.assertEqual(len(self.chiamate), 2)

    def test_se_claude_fallisce_ci_si_ferma(self):
        rc, out = self.vai(self.lancia({"claude": 3}))
        self.assertEqual((rc, len(self.chiamate), out), (3, 1, ""))


if __name__ == "__main__":
    unittest.main()

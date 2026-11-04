"""Il pre-commit blocca un segreto finto e lascia passare un file pulito (repo temporaneo, mai il vault)."""
import os
import random
import shutil
import string
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

HOOK = Path(__file__).resolve().parent / "hooks" / "pre-commit"


def git(repo, *args, **kw):
    return subprocess.run(["git", "-C", str(repo), *args], capture_output=True, text=True, **kw)


@unittest.skipUnless(shutil.which("gitleaks"), "gitleaks non installato")
class HookGitleaks(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.repo = Path(self.tmp.name)
        git(self.repo, "init", "-q")
        for k, v in (("user.name", "t"), ("user.email", "t@t"), ("core.hooksPath", str(HOOK.parent))):
            git(self.repo, "config", k, v)

    def tearDown(self):
        self.tmp.cleanup()

    def commit(self, nome, testo):
        (self.repo / nome).write_text(testo, encoding="utf-8")
        git(self.repo, "add", nome)
        return git(self.repo, "commit", "-q", "-m", "prova")

    def test_segreto_finto_blocca_il_commit(self):
        finto = "ghp_" + "".join(random.SystemRandom().choices(string.ascii_letters + string.digits, k=36))  # costruito qui, mai nel file
        r = self.commit("config.txt", f"token = {finto}\n")
        self.assertNotEqual(r.returncode, 0, r.stdout + r.stderr)
        self.assertNotIn(finto, r.stdout + r.stderr)  # --redact: il segreto non finisce nell'output
        self.assertNotEqual(git(self.repo, "rev-parse", "--verify", "HEAD").returncode, 0)  # nessun commit creato

    def test_file_pulito_passa(self):
        r = self.commit("nota.md", "# Ciao\nNiente di segreto.\n")
        self.assertEqual(r.returncode, 0, r.stdout + r.stderr)

    def test_senza_gitleaks_blocca(self):
        vuota = Path(self.tmp.name) / "vuota"
        vuota.mkdir()
        r = subprocess.run([sys.executable, str(HOOK)], capture_output=True, text=True, env={"PATH": str(vuota)})
        self.assertNotEqual(r.returncode, 0)
        self.assertIn("gitleaks non trovato", r.stderr)


if __name__ == "__main__":
    unittest.main()

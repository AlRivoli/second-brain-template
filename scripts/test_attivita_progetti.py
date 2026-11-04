#!/usr/bin/env python3
"""Test di attivita(): solo i commit dopo la soglia, su tutti i branch, senza merge."""
import importlib.util
import subprocess
import tempfile
import unittest
from pathlib import Path

RADICE = Path(__file__).resolve().parent.parent
spec = importlib.util.spec_from_file_location("attivita_progetti", RADICE / "scripts" / "attivita-progetti.py")
ap = importlib.util.module_from_spec(spec)
spec.loader.exec_module(ap)


def git(repo, *args, data=None):
    env = {"GIT_AUTHOR_DATE": data, "GIT_COMMITTER_DATE": data} if data else {}
    subprocess.run(["git", "-C", str(repo), "-c", "user.name=t", "-c", "user.email=t@t", *args], check=True,
                   capture_output=True, env={"PATH": "/usr/bin:/bin:/opt/homebrew/bin", **env})


class AttivitaTest(unittest.TestCase):
    def setUp(self):
        self.repo = Path(tempfile.mkdtemp())
        git(self.repo, "init", "-q", "-b", "main")
        (self.repo / "a").write_text("1")
        git(self.repo, "add", "a")
        git(self.repo, "commit", "-q", "-m", "vecchio", data="2026-10-20T10:00:00")
        git(self.repo, "switch", "-q", "-c", "feat/x")
        (self.repo / "docs" / "wayfinder").mkdir(parents=True)
        (self.repo / "docs" / "wayfinder" / "t1.md").write_text("ticket")
        git(self.repo, "add", "-A")
        git(self.repo, "commit", "-q", "-m", "nuovo su feat", data="2026-10-26T10:00:00")
        git(self.repo, "switch", "-q", "main")

    def test_solo_dopo_la_soglia_e_su_tutti_i_branch(self):
        soglia = int(__import__("datetime").datetime(2026, 10, 22).timestamp())
        righe = ap.attivita(self.repo, soglia)
        self.assertEqual(len(righe), 2)
        self.assertIn("feat/x: nuovo su feat", righe[0])
        self.assertNotIn("vecchio", "".join(righe))
        self.assertIn("docs/wayfinder/t1.md", righe[1])

    def test_nessun_commit_nuovo_da_lista_vuota(self):
        soglia = int(__import__("datetime").datetime(2026, 10, 27).timestamp())
        self.assertEqual(ap.attivita(self.repo, soglia), [])


if __name__ == "__main__":
    unittest.main()

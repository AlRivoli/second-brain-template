"""Test di scripts/ruota-log.py su cartelle temporanee (mai i log veri)."""
import gzip
import os
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

SCRIPT = Path(__file__).parent / "ruota-log.py"


class RuotaLog(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.logs = Path(self.tmp.name) / "logs"
        self.arch = Path(self.tmp.name) / "arch"
        self.logs.mkdir()

    def tearDown(self):
        self.tmp.cleanup()

    def run_script(self):
        e = {**os.environ, "ROTA_SOGLIA_KB": "1", "ROTA_RIGHE": "5"}
        subprocess.run([sys.executable, "-I", str(SCRIPT), str(self.logs), str(self.arch)], check=True, env=e, capture_output=True)

    def scrivi(self, nome, righe):
        p = self.logs / nome
        p.write_text("".join(f"riga {i}\n" for i in range(righe)))
        return p

    def test_sotto_soglia_non_tocca(self):
        p = self.scrivi("second-brain-a.log", 5)
        prima = p.read_bytes()
        self.run_script()
        self.assertEqual(p.read_bytes(), prima)
        self.assertFalse(self.arch.exists())

    def test_sopra_soglia_archivia_e_tronca_sul_posto(self):
        p = self.scrivi("second-brain-a.log", 500)
        altro = self.scrivi("altro.log", 500)
        inode, contenuto, altro_b = p.stat().st_ino, p.read_bytes(), altro.read_bytes()
        self.run_script()
        arch = list(self.arch.glob("second-brain-a-*.log.gz"))
        self.assertEqual(len(arch), 1)
        self.assertEqual(gzip.decompress(arch[0].read_bytes()), contenuto)
        self.assertEqual(p.read_text().splitlines(), [f"riga {i}" for i in range(495, 500)])
        self.assertEqual(p.stat().st_ino, inode)
        self.assertEqual(altro.read_bytes(), altro_b)  # nome diverso: intatto

    def test_limite_archivi(self):
        self.arch.mkdir()
        for i in range(10):
            (self.arch / f"second-brain-a-2026-01-{i + 1:02d}-000000.log.gz").write_bytes(b"x")
        self.scrivi("second-brain-a.log", 500)
        self.run_script()
        nomi = sorted(p.name for p in self.arch.glob("second-brain-a-*.log.gz"))
        self.assertEqual(len(nomi), 8)
        self.assertNotIn("second-brain-a-2026-01-01-000000.log.gz", nomi)


if __name__ == "__main__":
    unittest.main()

import importlib.util
import unittest
from pathlib import Path

spec = importlib.util.spec_from_file_location("versioni", Path(__file__).resolve().parent / "versioni.py")
versioni = importlib.util.module_from_spec(spec)
spec.loader.exec_module(versioni)


class Versioni(unittest.TestCase):
    def test_estrae_le_versioni(self):
        uscite = {("graphify", "--version"): "graphify 0.4.1", ("n8n", "--version"): "avviso\n1.2.3",
                  ("claude", "--version"): "2.0.5 (Claude Code)", ("npm", "view", "n8n", "version"): "1.9.9"}
        r = versioni.righe(esegui=lambda *c: uscite.get(c, ""), pypi=lambda p: "0.5.0")
        self.assertEqual(r, [("Graphify (graphifyy, PyPI)", "0.4.1", "0.5.0"), ("n8n (npm)", "1.2.3", "1.9.9"),
                             ("Claude Code", "2.0.5", "vedi brew")])

    def test_comando_assente_e_rete_giu(self):
        r = versioni.righe(esegui=lambda *c: "", pypi=lambda p: "")
        self.assertEqual([x[1:] for x in r], [("", ""), ("", ""), ("", "vedi brew")])

    def test_parola_su_testo_vuoto(self):
        self.assertEqual(versioni.parola("", 1), "")


if __name__ == "__main__":
    unittest.main()

"""Su Windows `text=True` legge con la codifica locale (cp1252): le lettere accentate di git e di claude diventano «Ã¨».
Ogni chiamata a subprocess con text=True deve dire encoding="utf-8"."""
import ast
import unittest
from pathlib import Path

SCRIPTS = Path(__file__).resolve().parent
FUNZIONI = {"run", "check_output", "Popen", "check_call"}


def chiamate_senza_codifica(file):
    albero = ast.parse(file.read_text(encoding="utf-8"))
    for n in ast.walk(albero):
        if isinstance(n, ast.Call) and getattr(n.func, "attr", getattr(n.func, "id", "")) in FUNZIONI:
            nomi = {k.arg: k.value for k in n.keywords}
            testo = any(isinstance(nomi.get(k), ast.Constant) and nomi[k].value is True for k in ("text", "universal_newlines"))
            if testo and "encoding" not in nomi:
                yield n.lineno


class CodificaTest(unittest.TestCase):
    def test_text_true_dice_sempre_la_codifica(self):
        trovati = ["%s:%d" % (f.relative_to(SCRIPTS), riga) for f in sorted(list(SCRIPTS.glob("*.py")) + list(SCRIPTS.glob("dashboard/*.py")))
                   if not f.name.startswith("test_") for riga in chiamate_senza_codifica(f)]
        self.assertEqual(trovati, [], "text=True senza encoding=\"utf-8\"")


if __name__ == "__main__":
    unittest.main()

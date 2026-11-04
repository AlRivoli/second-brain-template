import re
import unittest
from pathlib import Path

RADICE = Path(__file__).resolve().parent.parent
COPPIE = [("README.md", "README.it.md"), ("GETTING_STARTED.md", "INIZIA.md")]


def titoli(file):
    """Livelli e numeri dei titoli: la struttura, non le parole, deve coincidere tra le due lingue."""
    out = []
    for riga in (RADICE / file).read_text(encoding="utf-8").splitlines():
        m = re.match(r"^(#+)\s+(\d+)?", riga)
        if m:
            out.append((len(m.group(1)), m.group(2)))
    return out


class DocsTest(unittest.TestCase):
    def test_le_due_lingue_hanno_la_stessa_struttura(self):
        for en, it in COPPIE:
            self.assertEqual(titoli(en), titoli(it), "%s e %s hanno titoli diversi" % (en, it))

    def test_nessun_percorso_personale_in_nessun_file_di_testo(self):
        """Rete di sicurezza generica per il repo pubblico (la deny-list vera sta nel repo privato dell'autore)."""
        pattern = re.compile(r"/Us" r"ers/[A-Za-z]|/ho" r"me/[a-z]|[A-Z]:\\Us" r"ers\\[A-Za-z]")
        for file in RADICE.rglob("*"):
            if not file.is_file() or ".git" in file.relative_to(RADICE).parts or "__pycache__" in file.parts:
                continue
            try:
                testo = file.read_text(encoding="utf-8")
            except UnicodeDecodeError:
                continue
            self.assertIsNone(pattern.search(testo), "percorso personale in %s" % file.relative_to(RADICE))


if __name__ == "__main__":
    unittest.main()

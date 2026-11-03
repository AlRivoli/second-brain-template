import importlib.util
import json
import os
import tempfile
import unittest
from pathlib import Path

spec = importlib.util.spec_from_file_location("post", Path(__file__).parent / "dashboard" / "post.py")
post = importlib.util.module_from_spec(spec)
spec.loader.exec_module(post)

ESEMPIO = """{
 "progetto": "demo",
 "canale": "instagram",
 "voci": [
  {
   "id": "a-01",
   "titolo": "Primo",
   "stato": "pronto",
   "immagini": []
  },
  {
   "id": "a-02",
   "titolo": "Secondo",
   "stato": "da creare",
   "immagini": []
  }
 ]
}
"""


class PostTest(unittest.TestCase):
    def test_stato_cambia_solo_quel_campo_e_il_resto_del_testo_resta(self):
        with tempfile.TemporaryDirectory() as d:
            f = Path(d) / "post-instagram.json"
            f.write_text(ESEMPIO, encoding="utf-8")
            post.imposta_stato(f, "a-02", "programmato")
            self.assertEqual(f.read_text(encoding="utf-8"), ESEMPIO.replace('"da creare"', '"programmato"'))

    def test_stato_non_ammesso_o_voce_sconosciuta(self):
        with tempfile.TemporaryDirectory() as d:
            f = Path(d) / "post-instagram.json"
            f.write_text(ESEMPIO, encoding="utf-8")
            with self.assertRaises(ValueError):
                post.imposta_stato(f, "a-01", "boh")
            with self.assertRaises(LookupError):
                post.imposta_stato(f, "zz", "pubblicato")
            self.assertEqual(f.read_text(encoding="utf-8"), ESEMPIO)

    def test_immagini_solo_sotto_le_cartelle_ammesse(self):
        with tempfile.TemporaryDirectory() as d:
            docs = Path(d) / "repo" / "docs"
            docs.mkdir(parents=True)
            (docs / "a.png").write_bytes(b"x")
            (docs / "nota.md").write_text("x", encoding="utf-8")
            (Path(d) / "segreto.png").write_bytes(b"x")
            os.symlink(Path(d) / "segreto.png", docs / "link.png")
            cartelle = [docs]
            self.assertIsNotNone(post.immagine_ammessa(str(docs / "a.png"), cartelle))
            self.assertIsNone(post.immagine_ammessa(str(docs / "nota.md"), cartelle))       # estensione
            self.assertIsNone(post.immagine_ammessa(str(docs / "link.png"), cartelle))      # link simbolico
            self.assertIsNone(post.immagine_ammessa(str(Path(d) / "segreto.png"), cartelle))  # fuori dalla cartella
            self.assertIsNone(post.immagine_ammessa(str(docs / ".." / "segreto.png"), cartelle))  # ..
            self.assertIsNone(post.immagine_ammessa(str(docs / "manca.png"), cartelle))     # non esiste
            self.assertIsNone(post.immagine_ammessa(None, cartelle))

    def test_zip_con_immagini_in_ordine_e_didascalia(self):
        import io
        import zipfile
        with tempfile.TemporaryDirectory() as d:
            docs = Path(d) / "docs"
            docs.mkdir()
            (docs / "uno.png").write_bytes(b"1")
            (docs / "due.png").write_bytes(b"2")
            voce = {"id": "ig-06", "data": "2026-11-03", "formato": "carosello", "titolo": "T", "didascalia": "Testo", "hashtag": ["#a", "#b"],
                    "testo_alternativo": ["alt1", "alt2"], "immagini": [{"percorso": str(docs / "uno.png")}, {"percorso": str(docs / "due.png")},
                                                                         {"percorso": "/etc/passwd"}]}
            z = zipfile.ZipFile(io.BytesIO(post.zip_voce(voce, [docs])))
            self.assertEqual(z.namelist(), ["2026-11-03-carosello-ig-06-01.png", "2026-11-03-carosello-ig-06-02.png", "didascalia.txt"])
            testo = z.read("didascalia.txt").decode("utf-8")
            self.assertIn("Testo", testo)
            self.assertIn("#a #b", testo)
            self.assertIn("Testo alternativo 2: alt2", testo)

    def test_nome_del_file(self):
        self.assertEqual(post.nome_file({"id": "ig-06", "data": "2026-11-03", "formato": "carosello"}, 1, ".png"), "2026-11-03-carosello-ig-06-01.png")
        self.assertEqual(post.nome_file({"id": "x/../y", "data": "d", "formato": "attività"}, 12, ".jpg"), "d-attivit-x-y-12.jpg")

    def test_la_pagina_non_espone_percorsi_assoluti(self):
        dati = {"voci": [{"id": "a", "immagini": [{"percorso": "/etc/passwd", "nota": "x"}]}]}
        p = post.per_la_pagina(dati, "demo", "instagram", [Path("/tmp")])
        self.assertNotIn("percorso", p["voci"][0]["immagini"][0])
        self.assertFalse(p["voci"][0]["immagini"][0]["esiste"])


if __name__ == "__main__":
    unittest.main()

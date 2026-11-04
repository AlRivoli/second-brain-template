import importlib.util
import json
import tempfile
import unittest
from datetime import datetime
from pathlib import Path

spec = importlib.util.spec_from_file_location("richieste", Path(__file__).parent / "dashboard" / "richieste.py")
r = importlib.util.module_from_spec(spec)
spec.loader.exec_module(r)

ADESSO = datetime(2026, 10, 29, 16, 0, 0)
BUONA = {"formato": "carosello", "tema": "La regola del voto", "note": "tono semplice", "data_desiderata": "2026-11-05"}


class RichiesteTest(unittest.TestCase):
    def test_aggiunge_con_id_progressivo_e_campi_nell_ordine(self):
        with tempfile.TemporaryDirectory() as d:
            f = Path(d) / "post-instagram-richieste.json"
            a = r.aggiungi(f, "demo", "instagram", BUONA, {"ig-01"}, ADESSO)
            b = r.aggiungi(f, "demo", "instagram", {**BUONA, "riferimento": "ig-01"}, {"ig-01"}, ADESSO)
            self.assertEqual((a["id"], b["id"]), ("rq-001", "rq-002"))
            dati = json.loads(f.read_text(encoding="utf-8"))
            self.assertEqual(list(dati), ["progetto", "canale", "aggiornato", "richieste"])
            self.assertEqual(list(dati["richieste"][0]), ["id", "creata", "data_desiderata", "formato", "tema", "note", "riferimento", "stato", "voce_id", "risposta"])
            self.assertEqual(dati["richieste"][1]["riferimento"], "ig-01")
            self.assertEqual(r.aperte(f, "demo", "instagram"), 2)

    def test_rifiuta_dati_non_validi(self):
        for cattivi in ({**BUONA, "tema": ""}, {**BUONA, "tema": "x" * 501}, {**BUONA, "note": "x" * 1001}, {**BUONA, "formato": "reel"},
                        {**BUONA, "data_desiderata": "5 novembre"}, {**BUONA, "data_desiderata": "2026-13-45"}, {**BUONA, "riferimento": "zz"},
                        {**BUONA, "tema": 5}, "testo"):
            with self.assertRaises(ValueError, msg=str(cattivi)):
                r.valida(cattivi, {"ig-01"})

    def test_annulla_solo_una_nuova_e_non_tocca_il_resto(self):
        with tempfile.TemporaryDirectory() as d:
            f = Path(d) / "x.json"
            r.aggiungi(f, "demo", "instagram", BUONA, set(), ADESSO)
            r.aggiungi(f, "demo", "instagram", BUONA, set(), ADESSO)
            dati = json.loads(f.read_text(encoding="utf-8"))
            dati["richieste"][1]["stato"] = "in lavorazione"
            dati["richieste"][1]["risposta"] = "mi serve una foto"
            f.write_text(json.dumps(dati), encoding="utf-8")
            r.annulla(f, "demo", "instagram", "rq-001", ADESSO)
            with self.assertRaises(ValueError):
                r.annulla(f, "demo", "instagram", "rq-002", ADESSO)
            with self.assertRaises(LookupError):
                r.annulla(f, "demo", "instagram", "rq-099", ADESSO)
            dopo = json.loads(f.read_text(encoding="utf-8"))
            self.assertEqual([x["stato"] for x in dopo["richieste"]], ["annullata", "in lavorazione"])
            self.assertEqual(dopo["richieste"][1]["risposta"], "mi serve una foto")

    def test_le_richieste_non_sono_un_calendario(self):
        spec2 = importlib.util.spec_from_file_location("post", Path(__file__).parent / "dashboard" / "post.py")
        post = importlib.util.module_from_spec(spec2)
        spec2.loader.exec_module(post)
        with tempfile.TemporaryDirectory() as d:
            (Path(d) / "demo").mkdir()
            for nome in ("post-instagram.json", "post-instagram-richieste.json", "post-instagram-statistiche.json"):
                (Path(d) / "demo" / nome).write_text("{}", encoding="utf-8")
            self.assertEqual([c["canale"] for c in post.scopri(d, ["demo"])], ["instagram"])
            self.assertIn("da approvare", post.STATI)


if __name__ == "__main__":
    unittest.main()

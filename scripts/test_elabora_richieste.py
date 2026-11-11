import importlib.util
import json
import tempfile
import unittest
from datetime import datetime
from pathlib import Path
from types import SimpleNamespace

spec = importlib.util.spec_from_file_location("elabora", Path(__file__).parent / "elabora-richieste.py")
e = importlib.util.module_from_spec(spec)
spec.loader.exec_module(e)

ADESSO = datetime(2026, 11, 4, 17, 0, 0)
RISPOSTA = json.dumps({"titolo": "T", "descrizione": "D", "didascalia": "Testo #a", "hashtag": ["#a"], "testo_alternativo": [], "come_pubblicare": "x"})


def prepara(d, stato="nuova", riferimento=None):
    cartella = Path(d) / "demo"
    cartella.mkdir()
    (cartella / "post-linkedin.json").write_text(json.dumps({"progetto": "demo", "canale": "linkedin", "voci": [{"id": "li-01", "stato": "pubblicato"}]}))
    f = cartella / "post-linkedin-richieste.json"
    e.rq.aggiungi(f, "demo", "linkedin", {"formato": "immagine", "tema": "tema", "riferimento": riferimento}, {"li-01"}, ADESSO)
    return f


class ElaboraTest(unittest.TestCase):
    def esegui(self, f, testo):
        return e.elabora(f, run=lambda *a, **k: SimpleNamespace(stdout=testo), adesso=ADESSO, log=lambda *_: None)

    def test_bozza_pronta_va_nel_calendario(self):
        with tempfile.TemporaryDirectory() as d:
            f = prepara(d)
            self.assertEqual(self.esegui(f, "ecco\n" + RISPOSTA), 1)
            r = json.loads(f.read_text())["richieste"][0]
            cal = json.loads((f.parent / "post-linkedin.json").read_text())
            self.assertEqual((r["stato"], r["voce_id"]), ("bozza pronta", "li-02"))
            self.assertEqual((cal["voci"][1]["id"], cal["voci"][1]["stato"]), ("li-02", "da approvare"))

    def test_risposta_non_valida_rifiuta_senza_toccare_il_calendario(self):
        with tempfile.TemporaryDirectory() as d:
            f = prepara(d)
            self.esegui(f, "non so")
            self.assertEqual(json.loads(f.read_text())["richieste"][0]["stato"], "rifiutata")
            self.assertEqual(len(json.loads((f.parent / "post-linkedin.json").read_text())["voci"]), 1)

    def test_modifica_riscrive_la_voce_indicata(self):
        with tempfile.TemporaryDirectory() as d:
            f = prepara(d, riferimento="li-01")
            self.esegui(f, RISPOSTA)
            voci = json.loads((f.parent / "post-linkedin.json").read_text())["voci"]
            self.assertEqual((len(voci), voci[0]["titolo"], voci[0]["stato"]), (1, "T", "da approvare"))

    def test_non_autenticato_lascia_la_richiesta_nuova(self):
        with tempfile.TemporaryDirectory() as d:
            f = prepara(d)
            self.assertIsNone(self.esegui(f, "Invalid API key · Please run /login"))
            self.assertEqual(json.loads(f.read_text())["richieste"][0]["stato"], "nuova")

    def test_le_cartelle_riservate_non_si_elaborano(self):
        # ADR-002: una richiesta nella cartella riservata non parte verso un modello in cloud, nemmeno se la cartella
        # ha un nome scelto al setup o è scritta con altre maiuscole (NTFS e APFS non le distinguono)
        with tempfile.TemporaryDirectory() as d:
            vault = Path(d)
            (vault / "config.json").write_text(json.dumps({"moduli": {"riservata": {"attivo": True, "cartella": "projects/confidential-notes"}}}))
            for nome in ("demo", "lavoro", "_Private", "confidential-notes"):
                cartella = vault / "projects" / nome
                cartella.mkdir(parents=True)
                e.rq.aggiungi(cartella / "post-linkedin-richieste.json", nome, "linkedin", {"formato": "immagine", "tema": "tema", "riferimento": None}, set(), ADESSO)
            self.assertEqual([f.parent.name for f in e.da_elaborare(vault)], ["demo"])

    def test_senza_config_valgono_le_cartelle_fisse(self):
        with tempfile.TemporaryDirectory() as d:
            self.assertEqual(e.cartelle_escluse(Path(d)), {"lavoro", "_private"})


if __name__ == "__main__":
    unittest.main()

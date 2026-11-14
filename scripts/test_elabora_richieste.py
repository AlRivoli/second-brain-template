import contextlib
import importlib.util
import io
import json
import tempfile
import unittest
from datetime import datetime
from pathlib import Path
from types import SimpleNamespace
from unittest import mock

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

    def vault_con_richieste(self, d, config):
        vault = Path(d)
        (vault / "config.json").write_bytes(config)
        for nome in ("demo", "confidential-notes"):
            cartella = vault / "projects" / nome
            cartella.mkdir(parents=True)
            e.rq.aggiungi(cartella / "post-linkedin-richieste.json", nome, "linkedin", {"formato": "immagine", "tema": "tema", "riferimento": None}, set(), ADESSO)
        return vault

    def test_config_con_bom_esclude_la_cartella_scelta(self):
        # a config.json saved by a Windows editor starts with a BOM: the chosen reserved folder must still be excluded
        config = json.dumps({"moduli": {"riservata": {"attivo": True, "cartella": "projects/confidential-notes"}}}).encode("utf-8-sig")
        with tempfile.TemporaryDirectory() as d:
            self.assertEqual([f.parent.name for f in e.da_elaborare(self.vault_con_richieste(d, config))], ["demo"])

    def test_cartella_riservata_scritta_con_altre_maiuscole(self):
        # setup.py accepts «Projects/Secret»: on NTFS and APFS it is projects/secret, whose requests never reach claude -p
        for scelta in ("Projects/Secret", "projects\\Secret", "PROJECTS/SECRET"):
            with self.subTest(scelta=scelta), tempfile.TemporaryDirectory() as d:
                vault = Path(d)
                (vault / "config.json").write_text(json.dumps({"moduli": {"riservata": {"attivo": True, "cartella": scelta}}}), encoding="utf-8")
                for nome in ("demo", "secret"):
                    cartella = vault / "projects" / nome
                    cartella.mkdir(parents=True)
                    e.rq.aggiungi(cartella / "post-linkedin-richieste.json", nome, "linkedin", {"formato": "immagine", "tema": "tema", "riferimento": None}, set(), ADESSO)
                self.assertEqual([f.parent.name for f in e.da_elaborare(vault)], ["demo"])

    def test_senza_moduli_py_non_elabora_e_dice_perche(self):
        config = json.dumps({"moduli": {"riservata": {"attivo": True, "cartella": "projects/confidential-notes"}}}).encode()
        with tempfile.TemporaryDirectory() as d:
            vault = self.vault_con_richieste(d, config)
            vero = e.da_elaborare
            with mock.patch.object(e.percorsi, "_valida_cartella", side_effect=FileNotFoundError("moduli.py")), \
                    mock.patch.object(e, "LOGS", vault), mock.patch.object(e, "da_elaborare", lambda: vero(vault)), \
                    mock.patch.object(e, "elabora", side_effect=AssertionError("richiesta elaborata")), \
                    contextlib.redirect_stderr(io.StringIO()) as err:
                self.assertEqual(e.main(), 1)
            self.assertIn("moduli.py", err.getvalue())

    def test_config_illeggibile_non_elabora_niente(self):
        # ADR-002, fail closed: with config.json unreadable the reserved folder is unknown, so no request goes to the model
        for config in (b"{non json", b"[1, 2]", b"\xff\xfe", b"[" * 100000, b'{"moduli": {"riservata": {"cartella": 5}}}',
                       b'{"moduli": []}', b'{"moduli": {"riservata": []}}', b'{"moduli": {"riservata": {"attivo": true}}}',
                       b'{"moduli": {"riservata": {"cartella": "../fuori"}}}', b'{"moduli": {"riservata": {"cartella": "/assoluta/note"}}}'):
            with self.subTest(config=config[:20]), tempfile.TemporaryDirectory() as d:
                vault = self.vault_con_richieste(d, config)
                with self.assertRaises(RuntimeError) as c:
                    e.da_elaborare(vault)
                self.assertEqual(str(c.exception), e.CONFIG_ILLEGGIBILE)
                vero = e.da_elaborare
                with mock.patch.object(e, "LOGS", vault), mock.patch.object(e, "da_elaborare", lambda: vero(vault)), \
                        mock.patch.object(e, "elabora", side_effect=AssertionError("richiesta elaborata")), \
                        contextlib.redirect_stderr(io.StringIO()) as err:
                    self.assertEqual(e.main(), 1)
                self.assertIn(e.CONFIG_ILLEGGIBILE, err.getvalue())
                self.assertFalse((vault / "second-brain-richieste.lock").exists())
                for f in (vault / "projects").glob("*/post-linkedin-richieste.json"):
                    self.assertEqual(json.loads(f.read_text(encoding="utf-8"))["richieste"][0]["stato"], "nuova")


if __name__ == "__main__":
    unittest.main()

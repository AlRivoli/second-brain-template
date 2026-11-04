import importlib.util
import json
import tempfile
import unittest
from pathlib import Path

RADICE = Path(__file__).resolve().parent
spec = importlib.util.spec_from_file_location("modello", RADICE / "modello.py")
modello = importlib.util.module_from_spec(spec)
spec.loader.exec_module(modello)


def vault(modelli):
    d = tempfile.TemporaryDirectory()
    (Path(d.name) / "config.json").write_text(json.dumps({"modelli": modelli}), encoding="utf-8")
    return d


def finto(*risposte):
    """Un provider finto che risponde in ordine e ricorda le chiamate."""
    chiamate = []

    def f(nome, istruzioni, testo, json_, timeout):
        chiamate.append((nome, istruzioni, testo, json_))
        return modello.Risposta(risposte[min(len(chiamate), len(risposte)) - 1], {})

    f.chiamate = chiamate
    return f


class SceltaTest(unittest.TestCase):
    def test_provider_e_nome(self):
        with vault({"a": "ollama:qwen3:8b", "b": "claude", "c": "none"}) as d:
            self.assertEqual(modello.scelta("a", d), ("ollama", "qwen3:8b"))
            self.assertEqual(modello.scelta("b", d), ("claude", ""))
            self.assertEqual(modello.scelta("c", d), ("none", ""))

    def test_senza_scelta_o_senza_config_e_nessun_modello(self):
        with vault({}) as d:
            self.assertEqual(modello.scelta("radar_giudizio", d)[0], "none")
        with tempfile.TemporaryDirectory() as d:
            self.assertEqual(modello.scelta("radar_giudizio", d)[0], "none")

    def test_provider_sconosciuto_e_nome_pericoloso(self):
        with vault({"a": "openai:gpt", "b": "ollama:x; rm -rf /", "c": "ollama:../x", "d": "ollama:"}) as d:
            with self.assertRaises(modello.ModelloNonDisponibile):
                modello.scelta("a", d)
            for passo in "bcd":
                with self.assertRaises(ValueError, msg=passo):
                    modello.scelta(passo, d)


class ChiediTest(unittest.TestCase):
    def test_nessun_modello_non_chiama_niente(self):
        with vault({}) as d:
            with self.assertRaises(modello.ModelloNonDisponibile):
                modello.chiedi("x", "i", "t", vault=d, provider={"ollama": finto("no")})

    def test_i_due_provider_hanno_la_stessa_interfaccia(self):
        for scelta_ in ("ollama:m", "claude"):
            with vault({"x": scelta_}) as d:
                f = finto("ciao")
                r = modello.chiedi("x", "istr", "testo", vault=d, provider={"ollama": f, "claude": f})
                self.assertEqual((r.testo, f.chiamate[0][1:3]), ("ciao", ("istr", "testo")))

    def test_json_non_valido_si_riprova_una_volta_poi_errore(self):
        with vault({"x": "ollama:m"}) as d:
            f = finto("non json", '{"a": 1}')
            self.assertEqual(modello.chiedi("x", "i", "t", json_=True, vault=d, provider={"ollama": f}).testo, '{"a": 1}')
            self.assertEqual(len(f.chiamate), 2)
            f = finto("no", "ancora no")
            with self.assertRaises(modello.RispostaNonUtilizzabile):
                modello.chiedi("x", "i", "t", json_=True, vault=d, provider={"ollama": f})
            self.assertEqual(len(f.chiamate), 2)

    def test_claude_riceve_la_richiesta_di_json_nelle_istruzioni(self):
        with vault({"x": "claude"}) as d:
            f = finto("{}")
            modello.chiedi("x", "istr", "t", json_=True, vault=d, provider={"claude": f})
            self.assertIn("JSON valido", f.chiamate[0][1])


class RamTest(unittest.TestCase):
    def test_soglie_e_alternativa_sempre_detta(self):
        self.assertEqual(modello.consiglia(32)["locale"], "qwen3:8b")
        self.assertEqual(modello.consiglia(8)["locale"], "qwen3:4b-instruct-2507")
        self.assertIsNone(modello.consiglia(4)["locale"])
        self.assertIsNone(modello.consiglia(None)["locale"])
        for gb in (32, 8, 4, None):
            self.assertRegex(modello.consiglia(gb)["testo"], "Claude")

    def test_ram_e_un_numero_o_none(self):
        r = modello.ram_gb()
        self.assertTrue(r is None or r > 0.5)


class ProvaTest(unittest.TestCase):
    def test_esiti(self):
        with vault({"x": "ollama:m"}) as d:
            bene = [{"ollama": finto('{"colore": "blu"}', '{"giorno": "mercoledì"}', "Una frase.")}]
            self.assertEqual(modello.prova("x", d, bene[0])["esito"], "adatto")
            sbaglia_data = {"ollama": finto('{"colore": "blu"}', '{"giorno": "giovedì"}', "Una frase.")}
            self.assertEqual(modello.prova("x", d, sbaglia_data)["esito"], "adatto con riserva")
            self.assertEqual(modello.prova("x", d, {"ollama": finto("no")})["esito"], "non adatto")


class RiservataTest(unittest.TestCase):
    def test_chi_chiama_il_livello_dei_modelli_non_conosce_la_cartella_riservata(self):
        # il livello dei modelli e i suoi due chiamanti non nominano la cartella riservata: non la leggono, quindi non la passano a nessun modello
        for file in ("modello.py", "radar-stadio2.py", "dashboard/assistente.py"):
            self.assertNotIn("_private", (RADICE / file).read_text(encoding="utf-8"), file)


if __name__ == "__main__":
    unittest.main()

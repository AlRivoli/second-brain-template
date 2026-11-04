import importlib.util
import json
import tempfile
import unittest
from datetime import datetime
from pathlib import Path

RADICE = Path(__file__).resolve().parent
spec = importlib.util.spec_from_file_location("calendario", RADICE / "calendario.py")
calendario = importlib.util.module_from_spec(spec)
spec.loader.exec_module(calendario)
spec = importlib.util.spec_from_file_location("assistente", RADICE / "dashboard" / "assistente.py")
assistente = importlib.util.module_from_spec(spec)
spec.loader.exec_module(assistente)

VALIDO = {"titolo": "Dentista", "inizio": datetime(2026, 11, 4, 15, 0), "fine": datetime(2026, 11, 4, 16, 0), "calendari": ["Casa"]}


def vault(cfg):
    d = tempfile.TemporaryDirectory()
    if cfg is not None:
        (Path(d.name) / "config.json").write_text(json.dumps(cfg), encoding="utf-8")
    return d


class ProviderTest(unittest.TestCase):
    def test_di_fabbrica_macos_su_un_mac_e_niente_altrove(self):
        with vault(None) as d:
            self.assertIsInstance(calendario.provider(d, "darwin"), calendario.Macos)
            self.assertIsNone(calendario.provider(d, "linux"))
            self.assertIsNone(calendario.provider(d, "win32"))

    def test_la_scelta_in_config_vince(self):
        with vault({"calendario": {"provider": "none"}}) as d:
            self.assertIsNone(calendario.provider(d, "darwin"))
        with vault({"calendario": {"provider": "macos"}}) as d:
            self.assertIsInstance(calendario.provider(d, "linux"), calendario.Macos)

    def test_provider_sconosciuto(self):
        with vault({"calendario": {"provider": "outlook"}}) as d:
            with self.assertRaises(ValueError):
                calendario.provider(d, "darwin")


class MacosTest(unittest.TestCase):
    def test_nomi_eventi_crea_togli_passano_da_osascript(self):
        codici = []

        def finto(codice):
            codici.append(codice)
            if "calendars().map" in codice:
                return '["Casa", "Lavoro"]'
            if "events.push" in codice:
                return '{"uid": "U1"}'
            if "C.delete" in codice:
                return '{"tolti": 1}'
            return '[{"calendario": "Casa", "titolo": "", "inizio": "2026-11-04T14:00:00.000Z", "fine": "2026-11-04T15:00:00.000Z", "tuttoIlGiorno": false}]'

        c = calendario.Macos(finto)
        self.assertEqual(c.nomi(), ["Casa", "Lavoro"])
        e = c.eventi(7, ["Lavoro"])[0]
        self.assertEqual((e["calendario"], e["titolo"], e["tuttoIlGiorno"]), ("Casa", "(senza titolo)", False))
        self.assertIn('["Lavoro"]', codici[-1])
        self.assertEqual(c.crea("Casa", 'Con "virgolette"', VALIDO["inizio"], VALIDO["fine"]), "U1")
        self.assertIn('"Con \\"virgolette\\""', codici[-1])
        self.assertEqual(c.togli("Casa", "U1"), 1)


class SolaLetturaTest(unittest.TestCase):
    def test_un_provider_in_sola_lettura_non_crea(self):
        class Letto:
            scrive = False

            def crea(self, *a):
                raise AssertionError("non deve scrivere")

        with self.assertRaises(ValueError):
            assistente.crea_evento(VALIDO, Letto())

    def test_un_provider_che_scrive_riceve_i_campi_e_ricorda_cosa_ha_creato(self):
        class Scrive:
            scrive = True
            chiamate = []

            def crea(self, nome, titolo, inizio, fine):
                self.chiamate.append((nome, titolo))
                return "U9"

            def togli(self, nome, uid):
                return 1

        p = Scrive()
        self.assertEqual(assistente.crea_evento(VALIDO, p), [{"calendario": "Casa", "uid": "U9"}])
        assistente.togli_evento("U9", p)
        with self.assertRaises(LookupError):
            assistente.togli_evento("U9", p)



ICS = "BEGIN:VEVENT\r\nUID:1\r\nSUMMARY:Dentista\r\nDTSTART:%s\r\nDTEND:%s\r\nEND:VEVENT\r\n"


def domani(ora):
    from datetime import timedelta
    return (datetime.now() + timedelta(days=1)).replace(hour=ora, minute=0, second=0, microsecond=0)


class IcsTest(unittest.TestCase):
    def provider(self, scarica, voci=None):
        return calendario.Ics(voci or [{"nome": "Personale", "url": "https://segreto.example/x?token=ABC"}], scarica)

    def test_legge_gli_eventi_e_segna_il_calendario(self):
        a, b = domani(15), domani(16)
        c = self.provider(lambda v: ICS % (a.strftime("%Y%m%dT%H%M%S"), b.strftime("%Y%m%dT%H%M%S")))
        e = c.eventi(7)
        self.assertEqual([(x["calendario"], x["titolo"], x["inizio"]) for x in e], [("Personale", "Dentista", a)])
        self.assertEqual(c.nomi(), ["Personale"])
        self.assertFalse(c.scrive)

    def test_un_calendario_escluso_non_si_scarica(self):
        chiamate = []
        c = self.provider(lambda v: chiamate.append(v) or "")
        c.eventi(7, ["Personale"])
        self.assertEqual(chiamate, [])

    def test_se_un_calendario_non_si_legge_si_dice_senza_mostrare_l_indirizzo(self):
        import urllib.error

        def giu(v):
            raise urllib.error.URLError("non raggiungibile https://segreto.example/x?token=ABC")

        with self.assertRaises(RuntimeError) as cm:
            self.provider(giu).eventi(7)
        self.assertIn("Personale", str(cm.exception))
        self.assertNotIn("segreto", str(cm.exception))
        self.assertNotIn("ABC", str(cm.exception))

    def test_gli_avvisi_di_ripetizioni_non_supportate_arrivano(self):
        a = domani(9).strftime("%Y%m%dT%H%M%S")
        c = self.provider(lambda v: ICS.replace("END:VEVENT", "RRULE:FREQ=MONTHLY;BYSETPOS=2;BYDAY=TU\r\nEND:VEVENT") % (a, a))
        c.eventi(7)
        self.assertIn("ripetizione non supportata", c.avvisi[0])

    def test_il_file_dei_segreti(self):
        import os
        with tempfile.TemporaryDirectory() as d:
            f = Path(d) / "calendari.json"
            with self.assertRaises(RuntimeError):
                calendario.carica_voci(f)  # manca
            f.write_text(json.dumps({"calendari": [{"nome": "A", "url": "webcal://x.example/a"}]}), encoding="utf-8")
            if os.name == "posix":
                os.chmod(f, 0o644)
                with self.assertRaises(RuntimeError) as cm:
                    calendario.carica_voci(f)
                self.assertIn("chmod 600", str(cm.exception))
                os.chmod(f, 0o600)
            self.assertEqual(calendario.carica_voci(f)[0]["nome"], "A")
            for cattivo in ({"calendari": [{"nome": "A", "url": "http://x.example/a"}]}, {"calendari": [{"nome": "", "url": "https://x"}]},
                            {"calendari": [{"nome": "A"}]}, {"altro": 1}):
                f.write_text(json.dumps(cattivo), encoding="utf-8")
                with self.assertRaises(RuntimeError, msg=str(cattivo)):
                    calendario.carica_voci(f)

    def test_il_provider_ics_si_sceglie_in_config(self):
        with vault({"calendario": {"provider": "ics"}}) as d:
            self.assertIsInstance(calendario.provider(d, "linux"), calendario.Ics)

    def test_scrivere_su_un_calendario_ics_e_rifiutato(self):
        with self.assertRaises(ValueError):
            assistente.crea_evento(VALIDO, calendario.Ics([]))


class SenzaCalendarioTest(unittest.TestCase):
    def test_il_modello_non_riceve_ore_libere_inventate(self):
        testo = assistente.contesto([], [], datetime(2026, 11, 4, 9, 0), senza_calendario=True)
        self.assertIn("Nessun calendario è collegato", testo)
        self.assertNotIn("Ore libere", testo)
        self.assertIn("Ore libere", assistente.contesto([], [], datetime(2026, 11, 4, 9, 0)))


class PercorsoSegretiTest(unittest.TestCase):
    def test_i_segreti_stanno_fuori_dal_vault_e_per_sistema(self):
        spec = importlib.util.spec_from_file_location("percorsi", RADICE / "percorsi.py")
        percorsi = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(percorsi)
        casa = Path("/casa/ada")
        self.assertEqual(percorsi.cartella_segreti(casa, "darwin", {}), casa / ".config" / "second-brain")
        self.assertEqual(percorsi.cartella_segreti(casa, "linux", {"XDG_CONFIG_HOME": "/x"}), Path("/x/second-brain"))
        self.assertEqual(percorsi.cartella_segreti(casa, "win32", {"APPDATA": "/roaming"}), Path("/roaming/second-brain"))
        self.assertFalse(str(percorsi.cartella_segreti(casa, "linux", {})).startswith(str(RADICE.parent)))


if __name__ == "__main__":
    unittest.main()

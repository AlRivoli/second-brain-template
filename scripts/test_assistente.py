import sys
import unittest
from datetime import datetime
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent / "dashboard"))
import assistente  # noqa: E402


def voce(giorno, ora, fine, titolo, lavoro=False, tutto=False):
    return {"giorno": giorno, "ora": ora, "fine": fine, "titolo": titolo, "fonte": "calendario", "lavoro": lavoro,
            "tuttoIlGiorno": tutto, "inRitardo": False}


ADESSO = datetime(2026, 10, 30, 10, 30)  # venerdì
VOCI = [voce("2026-10-30", "11:00", "12:00", "Dentista"),
        voce("2026-10-30", "14:00", "16:00", "Riunione cliente Rossi", lavoro=True),
        voce("2026-11-03", "", "", "Convegno Bianchi", lavoro=True, tutto=True),
        voce("2026-10-31", "", "", "Compleanno di Marta", tutto=True),
        {"giorno": "2026-11-01", "originale": "2026-11-01", "titolo": "Rinnovo dominio", "fonte": "rinnovo", "inRitardo": False}]


class ContestoTest(unittest.TestCase):
    def setUp(self):
        self.testo = assistente.contesto(VOCI, ["Nuova versione di Ollama"], ADESSO)

    def test_data_e_giorni_li_scrive_il_codice(self):
        self.assertIn("Oggi è venerdì 2026-10-30, sono le 10:30.", self.testo)
        self.assertIn("martedì 2026-11-03", self.testo)

    def test_il_lavoro_entra_solo_come_occupato(self):
        self.assertNotIn("Rossi", self.testo)
        self.assertNotIn("Bianchi", self.testo)
        self.assertIn("2026-10-30 14:00-16:00: occupato", self.testo)
        self.assertIn("2026-11-03: occupato tutto il giorno", self.testo)

    def test_ore_libere_calcolate_dal_codice(self):
        riga = next(r for r in self.testo.splitlines() if r.startswith("Ore libere"))
        self.assertIn("ven 30/10 10:30-11:00, 12:00-14:00, 16:00-19:00", riga)  # da adesso, senza le ore passate
        self.assertNotIn("mar 03/11", riga)  # tutto il giorno occupato per lavoro

    def test_scadenze_e_novita(self):
        self.assertIn("- 2026-11-01: Rinnovo dominio", self.testo)
        self.assertIn("- Nuova versione di Ollama", self.testo)

    def test_chiedi_manda_contesto_e_domanda_al_modello(self):
        visto = {}
        risposta = assistente.chiedi("Cosa faccio oggi?", VOCI, [], ADESSO, lambda sistema, d: visto.update(s=sistema, d=d) or "ok")
        self.assertEqual((risposta, visto["d"]), ("ok", "Cosa faccio oggi?"))
        self.assertIn("Dentista", visto["s"])
        self.assertNotIn("Rossi", visto["s"])


class OreLibereTest(unittest.TestCase):
    def test_fasce_sotto_mezz_ora_si_scartano(self):
        self.assertEqual(assistente.ore_libere([(8 * 60 + 10, 12 * 60)], 8 * 60, 13 * 60), [(12 * 60, 13 * 60)])

    def test_sovrapposti(self):
        self.assertEqual(assistente.ore_libere([(9 * 60, 11 * 60), (10 * 60, 12 * 60)], 8 * 60, 14 * 60), [(8 * 60, 9 * 60), (12 * 60, 14 * 60)])


class ScritturaTest(unittest.TestCase):
    SCRIVIBILI = ["Google", "Apple"]

    def modello(self, risposta):
        return lambda sistema, frase: risposta

    def proposta(self, frase, risposta='{"titolo": "Titolo", "durata_min": 60}'):
        return assistente.proponi(frase, ADESSO, VOCI, self.modello(risposta))[0]

    def test_data_e_ora_le_legge_il_codice_dalla_frase(self):  # oggi è venerdì 30/10
        casi = {"dentista martedì alle 15": ("2026-11-03", "15:00"), "call giovedì alle 9:30": ("2026-11-05", "09:30"),
                "prova venerdì 20 novembre alle 10": ("2026-11-20", "10:00"), "compleanno 14 dicembre ore 20": ("2026-12-14", "20:00"),
                "riunione dopodomani alle 9": ("2026-11-01", "09:00"), "caffè domani alle 8.45": ("2026-10-31", "08:45"),
                "palestra stasera alle 19": ("2026-10-30", "19:00"), "visita 5/1 alle 11": ("2027-01-05", "11:00"),
                "cena giovedì sera": ("2026-11-05", ""), "cena sabato": ("2026-10-31", "")}
        for frase, atteso in casi.items():
            c = self.proposta(frase)
            self.assertEqual((c["data"], c["ora"]), atteso, frase)

    def test_senza_data_o_con_data_impossibile_resta_vuota(self):
        self.assertEqual(self.proposta("chiamare mamma")["data"], "")
        self.assertEqual(self.proposta("festa 31 febbraio alle 10")["data"], "")

    def test_il_modello_non_decide_la_data(self):
        c = self.proposta("dentista martedì alle 15", '{"titolo": "Dentista", "giorno": "lunedì", "data": "2020-01-01", "ora": "03:00"}')
        self.assertEqual((c["titolo"], c["data"], c["ora"]), ("Dentista", "2026-11-03", "15:00"))

    def test_oggi_con_ora_passata_il_giorno_della_settimana_va_alla_prossima(self):
        self.assertEqual(assistente.data_dalla_frase("venerdì", ADESSO, "09:00").isoformat(), "2026-11-06")
        self.assertEqual(assistente.data_dalla_frase("venerdì", ADESSO, "15:00").isoformat(), "2026-10-30")

    def test_risposta_del_modello_strana_non_rompe(self):
        for r in ("non è json", "[1, 2]", '{"durata_min": true}'):
            c = self.proposta("dentista martedì alle 15", r)
            self.assertEqual((c["titolo"], c["data"], c["durata_min"]), ("dentista martedì alle 15", "2026-11-03", 60))

    def test_conflitto_col_lavoro_si_dice_solo_occupato(self):
        c = {"data": "2026-10-30", "ora": "15:00", "durata_min": 30}
        self.assertEqual(assistente.conflitti(c, VOCI), ["occupato (lavoro)"])

    def test_valida_rifiuta_passato_calendario_di_lavoro_e_titolo_vuoto(self):
        ok = {"titolo": "Dentista", "data": "2026-11-03", "ora": "15:00", "durata_min": 60, "calendari": ["Google"]}
        self.assertEqual(assistente.valida(ok, ADESSO, self.SCRIVIBILI)["fine"], datetime(2026, 11, 3, 16, 0))
        for cambio in ({"data": "2026-10-29"}, {"calendari": ["Lavoro"]}, {"calendari": []}, {"titolo": " "}, {"titolo": "a\nb"}, {"durata_min": 0}, {"durata_min": True}, {"ora": "25:99"}):
            with self.assertRaises(ValueError, msg=cambio):
                assistente.valida({**ok, **cambio}, ADESSO, self.SCRIVIBILI)

    def test_crea_scrive_in_ogni_calendario_scelto_e_annulla_solo_i_propri(self):
        chiamate = []
        def finto(codice):
            chiamate.append(codice)
            return '{"uid": "U%d", "tolti": 1}' % len(chiamate)
        v = assistente.valida({"titolo": 'Con "virgolette"', "data": "2026-11-03", "ora": "15:00", "durata_min": 60, "calendari": ["Google", "Apple"]}, ADESSO, self.SCRIVIBILI)
        creati = assistente.crea_evento(v, finto)
        self.assertEqual([c["calendario"] for c in creati], ["Google", "Apple"])
        self.assertIn('"Con \\"virgolette\\""', chiamate[0])
        self.assertIn("[2026, 10, 3, 15, 0]", chiamate[0])
        with self.assertRaises(LookupError):
            assistente.togli_evento("non-mio", finto)
        assistente.togli_evento("U1", finto)
        with self.assertRaises(LookupError):
            assistente.togli_evento("U1", finto)


if __name__ == "__main__":
    unittest.main()

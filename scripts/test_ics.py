import importlib.util
import unittest
from datetime import datetime, timedelta, timezone
from pathlib import Path

spec = importlib.util.spec_from_file_location("ics", Path(__file__).resolve().parent / "ics.py")
ics = importlib.util.module_from_spec(spec)
spec.loader.exec_module(ics)

DA, A = datetime(2026, 11, 2), datetime(2026, 11, 9)  # lunedì 2 - lunedì 9 novembre 2026


def cal(*eventi):
    return "BEGIN:VCALENDAR\r\nVERSION:2.0\r\n" + "".join("BEGIN:VEVENT\r\n%s\r\nEND:VEVENT\r\n" % "\r\n".join(e) for e in eventi) + "END:VCALENDAR\r\n"


def titoli_e_inizi(testo, da=DA, a=A):
    ev, avvisi = ics.eventi(testo, da, a)
    return [(e["titolo"], e["inizio"].strftime("%a %d %H:%M")) for e in ev], avvisi


class SingoliTest(unittest.TestCase):
    def test_evento_locale_giorno_intero_e_fuori_finestra(self):
        t = cal(["UID:1", "SUMMARY:Dentista", "DTSTART:20261104T150000", "DTEND:20261104T160000"],
                ["UID:2", "SUMMARY:Ferie", "DTSTART;VALUE=DATE:20261105", "DTEND;VALUE=DATE:20261107"],
                ["UID:3", "SUMMARY:Altro mese", "DTSTART:20261201T100000", "DTEND:20261201T110000"])
        ev, avvisi = ics.eventi(t, DA, A)
        self.assertEqual([(e["titolo"], e["tuttoIlGiorno"]) for e in ev], [("Dentista", False), ("Ferie", True)])
        self.assertEqual((ev[0]["inizio"], ev[0]["fine"]), (datetime(2026, 11, 4, 15), datetime(2026, 11, 4, 16)))
        self.assertEqual(avvisi, [])

    def test_utc_si_porta_all_ora_locale(self):
        ev, _ = ics.eventi(cal(["UID:1", "SUMMARY:x", "DTSTART:20261104T100000Z", "DTEND:20261104T110000Z"]), DA, A)
        atteso = datetime(2026, 11, 4, 10, tzinfo=timezone.utc).astimezone().replace(tzinfo=None)
        self.assertEqual(ev[0]["inizio"], atteso)

    def test_righe_piegate_escape_e_durata(self):
        t = "BEGIN:VEVENT\r\nUID:1\r\nSUMMARY:Pranzo\\, con\r\n  Ada\r\nDTSTART:20261104T120000\r\nDURATION:PT90M\r\nEND:VEVENT\r\n"
        ev, _ = ics.eventi(t, DA, A)
        self.assertEqual((ev[0]["titolo"], ev[0]["fine"] - ev[0]["inizio"]), ("Pranzo, con Ada", timedelta(minutes=90)))

    def test_cancellato_e_data_illeggibile(self):
        t = cal(["UID:1", "SUMMARY:No", "STATUS:CANCELLED", "DTSTART:20261104T120000", "DTEND:20261104T130000"],
                ["UID:2", "SUMMARY:Rotto", "DTSTART:domani", "DTEND:20261104T130000"])
        ev, avvisi = ics.eventi(t, DA, A)
        self.assertEqual(ev, [])
        self.assertTrue(avvisi)

    def test_fuso_con_nome(self):
        try:
            import zoneinfo
            zoneinfo.ZoneInfo("America/New_York")
        except Exception:
            self.skipTest("senza database dei fusi")
        ev, avvisi = ics.eventi(cal(["UID:1", "SUMMARY:x", "DTSTART;TZID=America/New_York:20261104T090000", "DTEND;TZID=America/New_York:20261104T100000"]), DA, A)
        atteso = datetime(2026, 11, 4, 9, tzinfo=zoneinfo.ZoneInfo("America/New_York")).astimezone().replace(tzinfo=None)
        self.assertEqual((ev[0]["inizio"], avvisi), (atteso, []))

    def test_fuso_sconosciuto_si_dichiara(self):
        ev, avvisi = ics.eventi(cal(["UID:1", "SUMMARY:x", "DTSTART;TZID=Marte/Olympus:20261104T090000", "DTEND;TZID=Marte/Olympus:20261104T100000"]), DA, A)
        self.assertEqual(ev[0]["inizio"], datetime(2026, 11, 4, 9))
        self.assertIn("Marte/Olympus", avvisi[0])


class RicorrenzeTest(unittest.TestCase):
    def test_giornaliera_con_count_e_intervallo(self):
        r, _ = titoli_e_inizi(cal(["UID:1", "SUMMARY:Daily", "DTSTART:20261102T090000", "DTEND:20261102T093000", "RRULE:FREQ=DAILY;COUNT=3"]))
        self.assertEqual([x[1] for x in r], ["Mon 02 09:00", "Tue 03 09:00", "Wed 04 09:00"])
        r, _ = titoli_e_inizi(cal(["UID:1", "SUMMARY:Ogni 3", "DTSTART:20261102T090000", "DTEND:20261102T093000", "RRULE:FREQ=DAILY;INTERVAL=3"]))
        self.assertEqual([x[1] for x in r], ["Mon 02 09:00", "Thu 05 09:00", "Sun 08 09:00"])

    def test_settimanale_con_byday_e_iniziata_in_passato(self):
        r, _ = titoli_e_inizi(cal(["UID:1", "SUMMARY:Palestra", "DTSTART:20260105T180000", "DTEND:20260105T190000", "RRULE:FREQ=WEEKLY;BYDAY=MO,WE,FR"]))
        self.assertEqual([x[1] for x in r], ["Mon 02 18:00", "Wed 04 18:00", "Fri 06 18:00"])

    def test_ogni_due_settimane(self):
        r, _ = titoli_e_inizi(cal(["UID:1", "SUMMARY:Sprint", "DTSTART:20261019T100000", "DTEND:20261019T110000", "RRULE:FREQ=WEEKLY;INTERVAL=2"]))
        self.assertEqual([x[1] for x in r], ["Mon 02 10:00"])  # 19 ott, 2 nov: sì; 9 nov è fuori dalla finestra

    def test_mensile_per_giorno_e_per_ordinale(self):
        r, _ = titoli_e_inizi(cal(["UID:1", "SUMMARY:Affitto", "DTSTART:20260105T080000", "DTEND:20260105T083000", "RRULE:FREQ=MONTHLY;BYMONTHDAY=5"]))
        self.assertEqual([x[1] for x in r], ["Thu 05 08:00"])
        r, _ = titoli_e_inizi(cal(["UID:1", "SUMMARY:Primo lunedì", "DTSTART:20260105T080000", "DTEND:20260105T083000", "RRULE:FREQ=MONTHLY;BYDAY=1MO"]))
        self.assertEqual([x[1] for x in r], ["Mon 02 08:00"])
        r, _ = titoli_e_inizi(cal(["UID:1", "SUMMARY:Ultimo venerdì", "DTSTART:20260130T080000", "DTEND:20260130T083000", "RRULE:FREQ=MONTHLY;BYDAY=-1FR"]), datetime(2026, 11, 25), datetime(2026, 12, 2))
        self.assertEqual([x[1] for x in r], ["Fri 27 08:00"])

    def test_annuale(self):
        r, _ = titoli_e_inizi(cal(["UID:1", "SUMMARY:Compleanno", "DTSTART;VALUE=DATE:19901105", "DTEND;VALUE=DATE:19901106", "RRULE:FREQ=YEARLY"]))
        self.assertEqual([x[0] for x in r], ["Compleanno"])

    def test_until_exdate_e_occorrenza_spostata_o_cancellata(self):
        base = ["UID:S", "SUMMARY:Serie", "DTSTART:20261102T090000", "DTEND:20261102T100000", "RRULE:FREQ=DAILY;UNTIL=20261106T000000"]
        r, _ = titoli_e_inizi(cal(base))
        self.assertEqual([x[1] for x in r], ["Mon 02 09:00", "Tue 03 09:00", "Wed 04 09:00", "Thu 05 09:00"])
        r, _ = titoli_e_inizi(cal(base + ["EXDATE:20261103T090000"]))
        self.assertNotIn("Tue 03 09:00", [x[1] for x in r])
        spostata = ["UID:S", "SUMMARY:Serie (spostata)", "RECURRENCE-ID:20261104T090000", "DTSTART:20261104T150000", "DTEND:20261104T160000"]
        r, _ = titoli_e_inizi(cal(base, spostata))
        self.assertIn(("Serie (spostata)", "Wed 04 15:00"), r)
        self.assertNotIn(("Serie", "Wed 04 09:00"), r)
        cancellata = ["UID:S", "RECURRENCE-ID:20261104T090000", "STATUS:CANCELLED", "DTSTART:20261104T090000", "DTEND:20261104T100000"]
        r, _ = titoli_e_inizi(cal(base, cancellata))
        self.assertEqual(len(r), 3)

    def test_una_ripetizione_non_supportata_si_dichiara(self):
        r, avvisi = titoli_e_inizi(cal(["UID:1", "SUMMARY:Strana", "DTSTART:20261102T090000", "DTEND:20261102T100000", "RRULE:FREQ=MONTHLY;BYSETPOS=2;BYDAY=TU,TH"]))
        self.assertEqual(len(r), 1)  # solo la prima
        self.assertIn("ripetizione non supportata", avvisi[0])

    def test_una_serie_lunghissima_non_si_blocca(self):
        r, _ = titoli_e_inizi(cal(["UID:1", "SUMMARY:Da anni", "DTSTART:20150101T090000", "DTEND:20150101T093000", "RRULE:FREQ=DAILY"]))
        self.assertEqual(len(r), 7)


if __name__ == "__main__":
    unittest.main()

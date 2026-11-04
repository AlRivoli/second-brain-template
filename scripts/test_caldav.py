import base64
import importlib.util
import json
import os
import tempfile
import threading
import unittest
from datetime import datetime, timedelta
from http.server import BaseHTTPRequestHandler, HTTPServer
from pathlib import Path

RADICE = Path(__file__).resolve().parent


def carica(nome):
    spec = importlib.util.spec_from_file_location(nome, RADICE / (nome + ".py"))
    m = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(m)
    return m


caldav, calendario = carica("caldav"), carica("calendario")
PASSWORD = "pw-segreta-xyz"
MULTI = '<?xml version="1.0"?><d:multistatus xmlns:d="DAV:" xmlns:c="urn:ietf:params:xml:ns:caldav">%s</d:multistatus>'


def risposta(href, props):
    return "<d:response><d:href>%s</d:href><d:propstat><d:prop>%s</d:prop><d:status>HTTP/1.1 200 OK</d:status></d:propstat></d:response>" % (href, props)


class Finto(BaseHTTPRequestHandler):
    eventi = {}  # nome file -> testo iCal
    ricevute = []
    reindirizza = False
    casa_altrove = None

    def log_message(self, *a):
        pass

    def _invia(self, stato, corpo=""):
        dati = corpo.encode("utf-8")
        self.send_response(stato)
        self.send_header("Content-Length", str(len(dati)))
        self.end_headers()
        self.wfile.write(dati)

    def _gestisci(self):
        corpo = self.rfile.read(int(self.headers.get("Content-Length") or 0)).decode("utf-8")
        Finto.ricevute.append((self.command, self.path, self.headers.get("Authorization"), corpo))
        if Finto.reindirizza:
            self.send_response(302)
            self.send_header("Location", "http://127.0.0.1:9/")
            self.end_headers()
            return
        atteso = "Basic " + base64.b64encode(("ada:" + PASSWORD).encode()).decode()
        if self.headers.get("Authorization") != atteso:
            return self._invia(401)
        if self.command == "PROPFIND" and self.path == "/":
            return self._invia(207, MULTI % risposta("/", "<d:current-user-principal><d:href>/principale/</d:href></d:current-user-principal>"))
        if self.command == "PROPFIND" and self.path == "/principale/":
            casa = Finto.casa_altrove or "/cal/"
            return self._invia(207, MULTI % risposta("/principale/", "<c:calendar-home-set><d:href>%s</d:href></c:calendar-home-set>" % casa))
        if self.command == "PROPFIND" and self.path == "/cal/":
            def cal(href, nome, comp):
                return risposta(href, '<d:resourcetype><d:collection/><c:calendar/></d:resourcetype><d:displayname>%s</d:displayname>'
                                      '<c:supported-calendar-component-set><c:comp name="%s"/></c:supported-calendar-component-set>' % (nome, comp))
            return self._invia(207, MULTI % (risposta("/cal/", "<d:resourcetype><d:collection/></d:resourcetype>") + cal("/cal/casa/", "Casa", "VEVENT")
                                              + cal("/cal/promemoria/", "Promemoria", "VTODO")))
        if self.command == "REPORT" and self.path == "/cal/casa/":
            dati = "".join("<d:response><d:href>/cal/casa/%s</d:href><d:propstat><d:prop><c:calendar-data>%s</c:calendar-data></d:prop></d:propstat></d:response>"
                           % (n, t.replace("&", "&amp;")) for n, t in Finto.eventi.items())
            return self._invia(207, MULTI % dati)
        if self.command == "PUT" and self.path.startswith("/cal/casa/"):
            nome = self.path.rsplit("/", 1)[1]
            if nome in Finto.eventi and self.headers.get("If-None-Match") == "*":
                return self._invia(412)
            Finto.eventi[nome] = corpo
            return self._invia(201)
        if self.command == "DELETE" and self.path.startswith("/cal/casa/"):
            return self._invia(204 if Finto.eventi.pop(self.path.rsplit("/", 1)[1], None) is not None else 404)
        self._invia(404)

    do_PROPFIND = do_REPORT = do_PUT = do_DELETE = _gestisci


def ical(uid, titolo, inizio, fine, extra=""):
    return ("BEGIN:VCALENDAR\r\nVERSION:2.0\r\nBEGIN:VEVENT\r\nUID:%s\r\nDTSTART:%s\r\nDTEND:%s\r\nSUMMARY:%s\r\n%sEND:VEVENT\r\nEND:VCALENDAR\r\n"
            % (uid, inizio.strftime("%Y%m%dT%H%M%S"), fine.strftime("%Y%m%dT%H%M%S"), titolo, extra))


class CaldavTest(unittest.TestCase):
    def setUp(self):
        Finto.eventi, Finto.ricevute, Finto.reindirizza, Finto.casa_altrove = {}, [], False, None
        self.server = HTTPServer(("127.0.0.1", 0), Finto)
        threading.Thread(target=self.server.serve_forever, daemon=True).start()
        self.url = "http://127.0.0.1:%d/" % self.server.server_port
        self.addCleanup(self.server.server_close)
        self.addCleanup(self.server.shutdown)
        self.oggi = datetime.now().replace(hour=0, minute=0, second=0, microsecond=0)

    def client(self, password=PASSWORD):
        return caldav.Client(self.url, "ada", password)

    def test_trova_solo_i_calendari_che_accettano_eventi(self):
        self.assertEqual(list(self.client().calendari()), ["Casa"])

    def test_legge_eventi_singoli_e_ricorrenti_con_le_stesse_regole_di_ics(self):
        inizio = self.oggi + timedelta(days=1, hours=9)
        Finto.eventi["a.ics"] = ical("a", "Dentista", inizio, inizio + timedelta(hours=1))
        Finto.eventi["b.ics"] = ical("b", "Riunione", inizio, inizio + timedelta(hours=1), "RRULE:FREQ=DAILY;COUNT=3\r\n")
        eventi = calendario.Caldav(self.client()).eventi(giorni=7)
        self.assertEqual(sorted(e["titolo"] for e in eventi), ["Dentista", "Riunione", "Riunione", "Riunione"])
        self.assertTrue(all(e["calendario"] == "Casa" for e in eventi))

    def test_crea_e_togli_un_evento_solo_con_il_suo_uid(self):
        p = calendario.Caldav(self.client())
        uid = p.crea("Casa", "Pranzo; con, virgole", self.oggi + timedelta(hours=12), self.oggi + timedelta(hours=13))
        self.assertIn(uid + ".ics", Finto.eventi)
        self.assertIn("SUMMARY:Pranzo\\; con\\, virgole", Finto.eventi[uid + ".ics"])
        self.assertEqual(p.togli("Casa", uid), 1)
        self.assertEqual(p.togli("Casa", uid), 0)
        with self.assertRaises(caldav.Errore):
            p.togli("Casa", "../../x")
        with self.assertRaises(RuntimeError):
            p.crea("Inesistente", "x", self.oggi, self.oggi)

    def test_password_sbagliata_dice_cosa_fare_senza_mostrare_la_password(self):
        with self.assertRaises(caldav.Errore) as e:
            self.client("sbagliata-123").calendari()
        self.assertIn("password", str(e.exception))
        self.assertNotIn("sbagliata-123", str(e.exception))

    def test_non_segue_i_reindirizzamenti_e_non_manda_la_password_altrove(self):
        Finto.reindirizza = True
        with self.assertRaises(caldav.Errore):
            self.client().calendari()
        self.assertEqual(len(Finto.ricevute), 1)

    def test_rifiuta_un_server_che_manda_altrove_o_non_https(self):
        Finto.casa_altrove = "https://altro.example.org/cal/"
        with self.assertRaises(caldav.Errore):
            self.client().calendari()
        with self.assertRaises(caldav.Errore):
            caldav.Client("http://example.com/", "ada", "x")
        with self.assertRaises(caldav.Errore):
            caldav.Client("ftp://example.com/", "ada", "x")

    def test_xml_con_doctype_si_rifiuta(self):
        with self.assertRaises(caldav.Errore):
            caldav.Client._xml(b'<!DOCTYPE x [<!ENTITY a "b">]><x/>')

    def test_un_calendario_che_non_si_legge_blocca_invece_di_dare_ore_libere_sbagliate(self):
        p = calendario.Caldav(self.client())
        Finto.casa_altrove = None
        p.client._calendari = {"Casa": self.url + "cal/assente/"}
        with self.assertRaises(RuntimeError) as e:
            p.eventi()
        self.assertNotIn(PASSWORD, str(e.exception))


class SegretiTest(unittest.TestCase):
    def scrivi(self, d, dati, modo=0o600):
        f = Path(d) / "caldav.json"
        f.write_text(json.dumps(dati), encoding="utf-8")
        os.chmod(f, modo)
        return f

    def test_legge_il_file_dei_segreti(self):
        with tempfile.TemporaryDirectory() as d:
            dati = {"server": "https://caldav.icloud.com", "utente": "a@b.c", "password": "x"}
            self.assertEqual(calendario.carica_caldav(self.scrivi(d, dati)), dati)

    @unittest.skipIf(os.name == "nt", "permessi POSIX")
    def test_rifiuta_un_file_leggibile_da_altri(self):
        with tempfile.TemporaryDirectory() as d:
            with self.assertRaises(RuntimeError) as e:
                calendario.carica_caldav(self.scrivi(d, {"server": "s", "utente": "u", "password": "p"}, 0o644))
            self.assertNotIn('"p"', str(e.exception))

    def test_file_mancante_o_incompleto(self):
        with tempfile.TemporaryDirectory() as d:
            with self.assertRaises(RuntimeError):
                calendario.carica_caldav(Path(d) / "non-esiste.json")
            with self.assertRaises(RuntimeError):
                calendario.carica_caldav(self.scrivi(d, {"server": "https://x"}))

    def test_il_provider_si_sceglie_in_config(self):
        with tempfile.TemporaryDirectory() as d:
            (Path(d) / "config.json").write_text(json.dumps({"calendario": {"provider": "caldav"}}), encoding="utf-8")
            self.assertIsInstance(calendario.provider(d, "linux"), calendario.Caldav)


if __name__ == "__main__":
    unittest.main()

"""Client CalDAV minimo (iCloud, Nextcloud, Fastmail...): scoperta dei calendari, lettura per intervallo, creazione e rimozione di un evento.
Solo libreria standard. La password è un segreto: sta fuori dal vault, viaggia solo in https (http solo verso il computer stesso, per i
test), non segue i reindirizzamenti e non compare mai in un messaggio d'errore.

Le occorrenze ricorrenti le espande scripts/ics.py (le stesse regole del provider `ics`): il server restituisce i testi iCal e basta.
"""
import base64
import importlib.util
import re
import urllib.error
import urllib.request
import uuid
import xml.etree.ElementTree as ET
from datetime import datetime, timezone
from pathlib import Path
from urllib.parse import urljoin, urlparse

DAV = "{DAV:}"
CALDAV = "{urn:ietf:params:xml:ns:caldav}"
MAX_RISPOSTA = 10 * 1024 * 1024


class Errore(RuntimeError):
    """Un problema col server CalDAV, con un messaggio che non contiene mai la password."""


class _SenzaRedirect(urllib.request.HTTPRedirectHandler):
    def redirect_request(self, *a, **k):
        return None  # l'intestazione Authorization finirebbe a un altro indirizzo


def _contesto_tls():
    spec = importlib.util.spec_from_file_location("rete", Path(__file__).resolve().parent / "rete.py")
    m = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(m)
    return m.contesto_tls()


def _controlla_indirizzo(url):
    p = urlparse(url)
    if p.scheme == "https" or (p.scheme == "http" and p.hostname in ("127.0.0.1", "localhost")):
        return p
    raise Errore("il server CalDAV deve avere un indirizzo https://")


def _dominio(host):
    return ".".join((host or "").lower().split(".")[-2:])


class Client:
    def __init__(self, server, utente, password, http=None):
        self.base = server
        self.radice = _controlla_indirizzo(server)
        self.credenziali = "Basic " + base64.b64encode(("%s:%s" % (utente, password)).encode("utf-8")).decode("ascii")
        self.http = http or self._http
        self._calendari = None

    def _http(self, metodo, url, corpo, intestazioni):
        richiesta = urllib.request.Request(url, corpo, {**intestazioni, "Authorization": self.credenziali, "User-Agent": "second-brain-caldav/1"}, method=metodo)
        apri = urllib.request.build_opener(_SenzaRedirect, urllib.request.HTTPSHandler(context=_contesto_tls())).open
        try:
            with apri(richiesta, timeout=60) as r:
                return r.status, r.read(MAX_RISPOSTA + 1)
        except urllib.error.HTTPError as e:
            e.close()
            return e.code, b""
        except (urllib.error.URLError, OSError) as e:
            raise Errore("il server non risponde (%s)" % type(e).__name__)

    def _chiedi(self, metodo, url, corpo=None, tipo="application/xml; charset=utf-8", **altre):
        _controlla_indirizzo(url)
        if _dominio(urlparse(url).hostname) != _dominio(self.radice.hostname):
            raise Errore("il server ha indicato un altro dominio: rifiutato")
        stato, dati = self.http(metodo, url, corpo.encode("utf-8") if isinstance(corpo, str) else corpo, {"Content-Type": tipo, **altre})
        if stato in (401, 403):
            raise Errore("utente o password non accettati dal server (%d)" % stato)
        if stato in (301, 302, 303, 307, 308):
            raise Errore("il server reindirizza: usa l'indirizzo finale del servizio CalDAV")
        return stato, dati

    @staticmethod
    def _xml(dati):
        if len(dati) > MAX_RISPOSTA or re.search(rb"<!(DOCTYPE|ENTITY)", dati, re.I):
            raise Errore("risposta del server rifiutata (troppo grande o con DOCTYPE)")
        try:
            return ET.fromstring(dati)
        except ET.ParseError:
            raise Errore("risposta del server non leggibile")

    def _propfind(self, url, proprieta, profondita):
        corpo = '<?xml version="1.0"?><d:propfind xmlns:d="DAV:" xmlns:c="urn:ietf:params:xml:ns:caldav"><d:prop>%s</d:prop></d:propfind>' % proprieta
        stato, dati = self._chiedi("PROPFIND", url, corpo, Depth=profondita)
        if stato != 207:
            raise Errore("il server ha risposto %d alla scoperta dei calendari" % stato)
        return self._xml(dati)

    def _href(self, nodo, qui):
        h = nodo.find(".//" + DAV + "href")
        return urljoin(qui, h.text.strip()) if h is not None and h.text else None

    def calendari(self):
        """{nome: indirizzo della raccolta} dei calendari che accettano eventi (VEVENT)."""
        if self._calendari is None:
            principale = self._href(self._propfind(self.base, "<d:current-user-principal/>", "0").find(".//" + DAV + "current-user-principal"), self.base)
            casa = self._href(self._propfind(principale, "<c:calendar-home-set/>", "0").find(".//" + CALDAV + "calendar-home-set"), principale)
            if not principale or not casa:
                raise Errore("il server non indica dove stanno i calendari")
            trovati = {}
            for r in self._propfind(casa, "<d:resourcetype/><d:displayname/><c:supported-calendar-component-set/>", "1").iter(DAV + "response"):
                tipi = [c.tag for rt in r.iter(DAV + "resourcetype") for c in rt]
                componenti = [c.get("name") for c in r.iter(CALDAV + "comp")]
                nome = r.find(".//" + DAV + "displayname")
                if CALDAV + "calendar" in tipi and (not componenti or "VEVENT" in componenti) and nome is not None and nome.text:
                    trovati[nome.text.strip()[:60]] = self._href(r, casa)
            self._calendari = trovati
        return self._calendari

    def eventi_ical(self, raccolta, da, a):
        """Il testo iCal di tutti gli eventi della raccolta che toccano [da, a) (datetime senza fuso, ora locale)."""
        def utc(d):
            return d.astimezone().astimezone(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
        corpo = ('<?xml version="1.0"?><c:calendar-query xmlns:d="DAV:" xmlns:c="urn:ietf:params:xml:ns:caldav"><d:prop><c:calendar-data/></d:prop>'
                 '<c:filter><c:comp-filter name="VCALENDAR"><c:comp-filter name="VEVENT"><c:time-range start="%s" end="%s"/></c:comp-filter></c:comp-filter></c:filter>'
                 '</c:calendar-query>') % (utc(da), utc(a))
        stato, dati = self._chiedi("REPORT", raccolta, corpo, Depth="1")
        if stato != 207:
            raise Errore("il server ha risposto %d alla lettura degli eventi" % stato)
        return "\n".join((e.text or "") for e in self._xml(dati).iter(CALDAV + "calendar-data"))

    def crea(self, raccolta, titolo, inizio, fine):
        """uid dell'evento creato. Orari in UTC; il titolo è testo iCal con gli escape."""
        uid = str(uuid.uuid4())

        def utc(d):
            return d.astimezone().astimezone(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
        testo = re.sub(r"([\\;,])", r"\\\1", re.sub(r"[\r\n]+", " ", titolo))
        ical = "\r\n".join(["BEGIN:VCALENDAR", "VERSION:2.0", "PRODID:-//second-brain//caldav//IT", "BEGIN:VEVENT", "UID:" + uid,
                            "DTSTAMP:" + utc(datetime.now()), "DTSTART:" + utc(inizio), "DTEND:" + utc(fine),
                            "SUMMARY:" + testo, "END:VEVENT", "END:VCALENDAR", ""])
        stato, _ = self._chiedi("PUT", urljoin(raccolta if raccolta.endswith("/") else raccolta + "/", uid + ".ics"), ical, "text/calendar; charset=utf-8", **{"If-None-Match": "*"})
        if stato not in (200, 201, 204):
            raise Errore("il server non ha creato l'evento (%d)" % stato)
        return uid

    def togli(self, raccolta, uid):
        """1 se l'evento è stato tolto, 0 se non c'era. Cancella solo un evento di cui si conosce l'uid, creato da `crea`."""
        if not re.fullmatch(r"[0-9a-f-]{36}", uid):
            raise Errore("uid non valido")
        stato, _ = self._chiedi("DELETE", urljoin(raccolta if raccolta.endswith("/") else raccolta + "/", uid + ".ics"))
        if stato in (200, 204):
            return 1
        if stato == 404:
            return 0
        raise Errore("il server non ha tolto l'evento (%d)" % stato)

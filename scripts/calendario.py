"""Livello unico per il calendario: chi lo usa (agenda, assistente, dashboard) non sa se gli appuntamenti vengono dal Mac o da altrove.

Un provider ha: `nomi()`, `eventi(giorni, esclusi)`, e se `scrive` anche `crea(nome, titolo, inizio, fine)` e `togli(nome, uid)`.
La scelta sta in config.json: {"calendario": {"provider": "macos"}}. Senza scelta: `macos` su un Mac, nessun calendario altrove.
Gli appuntamenti restano nel processo che li legge: non si scrivono in nessun file e nessun modello li vede senza un consenso
(ADR-001, ADR-002). Solo libreria standard.
"""
import importlib.util
import json
import subprocess
import sys
import urllib.error
import urllib.request
from datetime import datetime, timedelta
from pathlib import Path

VAULT = Path(__file__).resolve().parent.parent


def _carica(nome):
    spec = importlib.util.spec_from_file_location(nome, Path(__file__).resolve().parent / (nome + ".py"))
    modulo = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(modulo)
    return modulo

JXA_EVENTI = """
const C = Application("Calendar");
const esclusi = %s;
const d1 = new Date(); d1.setHours(0, 0, 0, 0);
const d2 = new Date(d1.getTime() + %d * 86400000);
const out = [];
for (const c of C.calendars()) {
  const n = c.name();
  if (esclusi.includes(n)) continue;
  try {
    const ev = c.events.whose({_and: [{startDate: {_lessThan: d2}}, {endDate: {_greaterThan: d1}}]})();
    for (const e of ev) out.push({calendario: n, titolo: e.summary(), inizio: e.startDate().toISOString(), fine: e.endDate().toISOString(), tuttoIlGiorno: e.alldayEvent()});
  } catch (x) {}
}
JSON.stringify(out);
"""
JXA_NOMI = 'JSON.stringify(Application("Calendar").calendars().map(c => c.name()))'
JXA_CREA = """
const C = Application("Calendar");
const cal = C.calendars.byName(%s);
const ev = C.Event({summary: %s, startDate: new Date(%s), endDate: new Date(%s)});
cal.events.push(ev);
JSON.stringify({uid: ev.uid()});
"""
JXA_TOGLI = """
const C = Application("Calendar");
const ev = C.calendars.byName(%s).events.whose({uid: %s})();
if (ev.length === 1) { C.delete(ev[0]); }
JSON.stringify({tolti: ev.length});
"""


def _osascript(codice, timeout=300):
    r = subprocess.run(["/usr/bin/osascript", "-l", "JavaScript", "-e", codice], capture_output=True, text=True, encoding="utf-8", timeout=timeout)
    if r.returncode != 0:
        raise RuntimeError((r.stderr or "osascript non riuscito").strip().splitlines()[-1][:200])
    return r.stdout.strip()


def _js_data(d):
    return "...%s" % json.dumps([d.year, d.month - 1, d.day, d.hour, d.minute])


class Macos:
    """L'app Calendario del Mac (osascript/JXA), dove Google e Apple sono già insieme. `esegui` si sostituisce nei test."""
    scrive = True

    def __init__(self, esegui=None):
        self.esegui = esegui or _osascript

    def nomi(self):
        return json.loads(self.esegui(JXA_NOMI))

    def eventi(self, giorni=7, esclusi=()):
        """Eventi dei prossimi `giorni` giorni, con orari locali senza fuso. RuntimeError se Calendario non risponde.
        Calendario è lento con molti calendari: quelli esclusi non si interrogano."""
        out = []
        for e in json.loads(self.esegui(JXA_EVENTI % (json.dumps(list(esclusi)), giorni))):
            inizio = datetime.fromisoformat(e["inizio"].replace("Z", "+00:00")).astimezone().replace(tzinfo=None)
            fine = datetime.fromisoformat(e["fine"].replace("Z", "+00:00")).astimezone().replace(tzinfo=None)
            out.append({"calendario": e["calendario"], "titolo": e["titolo"] or "(senza titolo)", "inizio": inizio, "fine": fine,
                        "tuttoIlGiorno": bool(e["tuttoIlGiorno"])})
        return out

    def crea(self, nome, titolo, inizio, fine):
        """uid dell'evento creato nel calendario `nome`."""
        return json.loads(self.esegui(JXA_CREA % (json.dumps(nome), json.dumps(titolo), _js_data(inizio), _js_data(fine))))["uid"]

    def togli(self, nome, uid):
        """Quanti eventi ha tolto (1 se l'ha trovato)."""
        return json.loads(self.esegui(JXA_TOGLI % (json.dumps(nome), json.dumps(uid))))["tolti"]


MAX_ICS = 5 * 1024 * 1024


def carica_voci(file=None):
    """[{nome, url o file}] dal file dei segreti (fuori dal vault: gli indirizzi privati dei calendari sono credenziali).
    Rifiuta un file leggibile da altri utenti; RuntimeError con il rimedio."""
    percorsi = _carica("percorsi")
    file = Path(file or percorsi.cartella_segreti() / "calendari.json")
    if not file.is_file():
        raise RuntimeError("manca %s: ci vanno i calendari da leggere (vedi la guida)" % file)
    if not percorsi.permessi_stretti(file):
        raise RuntimeError("%s è leggibile da altri utenti: chmod 600 %s" % (file, file))
    try:
        voci = json.loads(file.read_text(encoding="utf-8"))["calendari"]
    except (ValueError, KeyError, TypeError):
        raise RuntimeError('%s non è valido: serve {"calendari": [{"nome": "...", "url": "https://..."}]}' % file)
    for v in voci:
        if not isinstance(v, dict) or not isinstance(v.get("nome"), str) or not 0 < len(v["nome"]) <= 60:
            raise RuntimeError("%s: ogni calendario ha un nome (al massimo 60 caratteri)" % file)
        fonte = v.get("url") or v.get("file")
        if not isinstance(fonte, str) or ("url" in v and not v["url"].lower().replace("webcal://", "https://", 1).startswith("https://")):
            raise RuntimeError("%s: «%s» ha bisogno di un indirizzo https:// o di un file" % (file, v["nome"]))
    return voci


def _scarica(voce):
    """Il testo .ics di un calendario. L'indirizzo è un segreto: non compare mai in un messaggio d'errore."""
    if voce.get("file"):
        return Path(voce["file"]).expanduser().read_text(encoding="utf-8")
    url = voce["url"].replace("webcal://", "https://", 1) if voce["url"].lower().startswith("webcal://") else voce["url"]
    richiesta = urllib.request.Request(url, headers={"User-Agent": "second-brain-calendario/1"})
    with urllib.request.urlopen(richiesta, timeout=30, context=_carica("rete").contesto_tls()) as r:
        dati = r.read(MAX_ICS + 1)
    if len(dati) > MAX_ICS:
        raise ValueError("file troppo grande")
    return dati.decode("utf-8", errors="replace")


class Ics:
    """Calendari iCal in sola lettura (l'indirizzo segreto di Google, o un file .ics). Non scrive: `scrive` è falso."""
    scrive = False

    def __init__(self, voci=None, scarica=None):
        self._voci = voci
        self.scarica = scarica or _scarica
        self.avvisi = []

    @property
    def voci(self):
        if self._voci is None:
            self._voci = carica_voci()
        return self._voci

    def nomi(self):
        return [v["nome"] for v in self.voci]

    def eventi(self, giorni=7, esclusi=()):
        da = datetime.now().replace(hour=0, minute=0, second=0, microsecond=0)
        ics, out, guasti, self.avvisi = _carica("ics"), [], [], []
        for v in self.voci:
            if v["nome"] in esclusi:
                continue
            try:
                trovati, avvisi = ics.eventi(self.scarica(v), da, da + timedelta(days=giorni))
            except (OSError, ValueError, urllib.error.URLError) as e:
                # niente testo dell'errore: potrebbe contenere l'indirizzo, che è un segreto
                guasti.append("%s (%s)" % (v["nome"], type(e).__name__))
                continue
            out += [dict(e, calendario=v["nome"]) for e in trovati]
            self.avvisi += ["%s: %s" % (v["nome"], a) for a in avvisi]
        if guasti:  # con un calendario che manca la disponibilità sarebbe sbagliata: meglio dire che non si legge
            raise RuntimeError("non riesco a leggere: " + ", ".join(guasti))
        return out


def carica_caldav(file=None):
    """{server, utente, password} dal file dei segreti (fuori dal vault). Rifiuta un file leggibile da altri utenti."""
    percorsi = _carica("percorsi")
    file = Path(file or percorsi.cartella_segreti() / "caldav.json")
    if not file.is_file():
        raise RuntimeError("manca %s: ci vanno server, utente e password per app (vedi la guida)" % file)
    if not percorsi.permessi_stretti(file):
        raise RuntimeError("%s è leggibile da altri utenti: chmod 600 %s" % (file, file))
    try:
        dati = json.loads(file.read_text(encoding="utf-8"))
        if not all(isinstance(dati[k], str) and dati[k] for k in ("server", "utente", "password")):
            raise KeyError
    except (ValueError, KeyError, TypeError):
        raise RuntimeError('%s non è valido: serve {"server": "https://...", "utente": "...", "password": "..."}' % file)
    return dati


class Caldav:
    """Un server CalDAV (iCloud, Nextcloud, Fastmail): legge e scrive. La password per app sta fuori dal vault, in caldav.json."""
    scrive = True

    def __init__(self, client=None):
        self._client = client
        self.avvisi = []

    @property
    def client(self):
        if self._client is None:
            d = carica_caldav()
            self._client = _carica("caldav").Client(d["server"], d["utente"], d["password"])
        return self._client

    def _raccolte(self):
        try:
            return self.client.calendari()
        except (OSError, ValueError) as e:  # Errore di caldav.py è un RuntimeError: il suo messaggio non contiene segreti
            raise RuntimeError("CalDAV non risponde (%s)" % type(e).__name__)

    def nomi(self):
        return list(self._raccolte())

    def eventi(self, giorni=7, esclusi=()):
        da = datetime.now().replace(hour=0, minute=0, second=0, microsecond=0)
        ics, out, guasti, self.avvisi = _carica("ics"), [], [], []
        for nome, raccolta in self._raccolte().items():
            if nome in esclusi:
                continue
            try:
                trovati, avvisi = ics.eventi(self.client.eventi_ical(raccolta, da, da + timedelta(days=giorni)), da, da + timedelta(days=giorni))
            except (OSError, ValueError) as e:
                guasti.append("%s (%s)" % (nome, type(e).__name__))
                continue
            except RuntimeError as e:
                guasti.append("%s (%s)" % (nome, e))
                continue
            out += [dict(e, calendario=nome) for e in trovati]
            self.avvisi += ["%s: %s" % (nome, a) for a in avvisi]
        if guasti:
            raise RuntimeError("non riesco a leggere: " + ", ".join(guasti))
        return out

    def _raccolta(self, nome):
        raccolte = self._raccolte()
        if nome not in raccolte:
            raise RuntimeError("calendario sconosciuto: %s" % nome)
        return raccolte[nome]

    def crea(self, nome, titolo, inizio, fine):
        return self.client.crea(self._raccolta(nome), titolo, inizio, fine)

    def togli(self, nome, uid):
        return self.client.togli(self._raccolta(nome), uid)


PROVIDER = {"macos": Macos, "ics": Ics, "caldav": Caldav}


def provider(vault=VAULT, piattaforma=None):
    """Il provider scelto in config.json, o None se non c'è un calendario collegato."""
    try:
        cfg = json.loads((Path(vault) / "config.json").read_text(encoding="utf-8"))
    except (OSError, ValueError):
        cfg = {}
    nome = (cfg.get("calendario") or {}).get("provider") or ("macos" if (piattaforma or sys.platform) == "darwin" else "none")
    if nome == "none":
        return None
    if nome not in PROVIDER:
        raise ValueError("provider di calendario sconosciuto: %s" % nome)
    return PROVIDER[nome]()

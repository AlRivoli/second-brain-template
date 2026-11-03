"""Cosa mi aspetta: appuntamenti dal Calendario del Mac e scadenze, uniti per giorno.

Gli appuntamenti si leggono in sola lettura con osascript (JXA) dall'app Calendario, dove Google e Apple sono già
insieme, e restano nel processo del server: non si scrivono in nessun file e nessun modello li vede (ADR-001, ADR-002).
Il file docs/calendari.md contiene solo i nomi dei calendari, con se mostrarli e se sono di lavoro.
"""
import json
import subprocess
from datetime import datetime, timedelta
from pathlib import Path

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


def _osascript(codice, timeout=300):
    r = subprocess.run(["/usr/bin/osascript", "-l", "JavaScript", "-e", codice], capture_output=True, text=True, timeout=timeout)
    if r.returncode != 0:
        raise RuntimeError((r.stderr or "osascript non riuscito").strip().splitlines()[-1][:200])
    return r.stdout.strip()


def nomi_calendari(esegui=_osascript):
    return json.loads(esegui(JXA_NOMI))


def leggi_eventi(giorni=7, esegui=_osascript, esclusi=()):
    """Eventi dei prossimi `giorni` giorni, con orari locali senza fuso. Solleva RuntimeError se Calendario non risponde.
    Calendario è lento con molti calendari: quelli esclusi non si interrogano."""
    out = []
    for e in json.loads(esegui(JXA_EVENTI % (json.dumps(list(esclusi)), giorni))):
        inizio = datetime.fromisoformat(e["inizio"].replace("Z", "+00:00")).astimezone().replace(tzinfo=None)
        fine = datetime.fromisoformat(e["fine"].replace("Z", "+00:00")).astimezone().replace(tzinfo=None)
        out.append({"calendario": e["calendario"], "titolo": e["titolo"] or "(senza titolo)", "inizio": inizio, "fine": fine,
                    "tuttoIlGiorno": bool(e["tuttoIlGiorno"])})
    return out


def leggi_config(file):
    """Nome calendario -> {'mostra': bool, 'tipo': str}, dalla tabella di docs/calendari.md. Un calendario assente si mostra."""
    out = {}
    try:
        righe = Path(file).read_text(encoding="utf-8").splitlines()
    except OSError:
        return out
    colonne = None
    for riga in righe:
        if not riga.startswith("|"):
            continue
        celle = [c.strip() for c in riga.strip().strip("|").split("|")]
        if colonne is None:
            colonne = [c.lower() for c in celle]
        elif not set("".join(celle)) <= set("-: "):
            d = dict(zip(colonne, celle))
            out[d.get("calendario", "")] = {"mostra": d.get("mostra", "sì").lower() in ("sì", "si", "s", "yes", "y"), "tipo": d.get("tipo", "personale").lower(),
                          "scrivi": d.get("scrivi", "no").lower() in ("sì", "si", "s", "yes", "y")}
    return out


def scrivi_config(file, nomi):
    """Crea docs/calendari.md con tutti i calendari mostrati, se il file non c'è ancora. Solo nomi."""
    if Path(file).exists():
        return False
    righe = ["# Calendari", "", "Quali calendari mostra la dashboard in «Cosa mi aspetta». Solo i nomi dei calendari, niente eventi.",
             "In «Mostra» scrivi sì o no. In «Scrivi» sì per i calendari dove l'assistente può aggiungere appuntamenti (solo personali, mai di lavoro). In «Tipo» scrivi personale o lavoro: un calendario di lavoro è segnato come tale e non lascia mai il Mac.", "",
             "| Calendario | Mostra | Tipo | Scrivi |", "|---|---|---|---|"]
    righe += ["| %s | sì | personale | no |" % n.replace("|", "/") for n in sorted(nomi)]
    Path(file).write_text("\n".join(righe) + "\n", encoding="utf-8")
    return True


def _ora(d):
    return d.strftime("%H:%M")


def unisci(eventi, scadenze, adesso, giorni=7, config=None):
    """Una lista ordinata di voci per i prossimi `giorni` giorni, più le scadenze già in ritardo.

    eventi: dal Calendario; scadenze: [{fonte, testo, data 'YYYY-MM-DD[ HH:MM]', ...altri campi passati così come sono}].
    """
    config = config or {}
    oggi = adesso.date()
    limite = oggi + timedelta(days=giorni)
    voci, visti = [], set()
    for e in eventi:
        c = config.get(e["calendario"], {"mostra": True, "tipo": "personale"})
        if not c["mostra"]:
            continue
        if (e["titolo"], e["inizio"], e["fine"]) in visti:  # lo stesso evento scritto in due calendari (Google e Apple) si mostra una volta
            continue
        visti.add((e["titolo"], e["inizio"], e["fine"]))
        giorno = max(e["inizio"].date(), oggi)
        if giorno >= limite:
            continue
        in_corso = e["inizio"].date() < oggi
        voci.append({"giorno": giorno.isoformat(), "ora": "" if e["tuttoIlGiorno"] else _ora(e["inizio"]), "fine": "" if e["tuttoIlGiorno"] else _ora(e["fine"]),
                     "titolo": e["titolo"], "fonte": "calendario", "dettaglio": e["calendario"], "lavoro": c["tipo"] == "lavoro",
                     "inRitardo": False, "inCorso": in_corso, "tuttoIlGiorno": e["tuttoIlGiorno"]})
    for s in scadenze:
        data = s["data"]
        giorno = datetime.strptime(data[:10], "%Y-%m-%d").date()
        ritardo = giorno < oggi
        if giorno >= limite:
            continue
        voce = dict(s)
        voce.update({"giorno": (oggi if ritardo else giorno).isoformat(), "originale": giorno.isoformat(), "ora": data[11:16] if len(data) >= 16 else "",
                     "fine": "", "titolo": s["testo"], "dettaglio": "", "lavoro": False, "inRitardo": ritardo, "inCorso": False, "tuttoIlGiorno": len(data) < 16})
        voci.append(voce)
    voci.sort(key=lambda v: (not v["inRitardo"], v["giorno"], v["ora"] == "", v["ora"], v["titolo"]))
    return voci

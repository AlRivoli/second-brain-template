"""Coda delle richieste di post: `projects/<progetto>/post-<canale>-richieste.json`.

La dashboard aggiunge richieste e annulla quelle ancora `nuova`; il resto del file (stato, voce_id, risposta) lo scrive
chi le elabora. Il testo delle richieste è un dato non fidato: qui si valida e basta, la pagina lo mostra sempre come testo.
"""
import json
import os
import re
import tempfile
from datetime import date, datetime
from pathlib import Path

FORMATI = ("carosello", "immagine", "storia", "video")
STATI = ("nuova", "in lavorazione", "bozza pronta", "rifiutata", "annullata")
APERTE = ("nuova", "in lavorazione")
MAX_TEMA, MAX_NOTE, MAX_RICHIESTE = 500, 1000, 300
DATA = re.compile(r"^\d{4}-\d{2}-\d{2}$")


def file_di(cartella_progetti, progetto, canale):
    return Path(cartella_progetti) / progetto / ("post-%s-richieste.json" % canale)


def leggi(file, progetto, canale):
    try:
        dati = json.loads(Path(file).read_text(encoding="utf-8"))
    except (OSError, ValueError):
        dati = {}
    dati.setdefault("progetto", progetto)
    dati.setdefault("canale", canale)
    if not isinstance(dati.get("richieste"), list):
        dati["richieste"] = []
    return dati


def scrivi(file, dati, adesso):
    dati["aggiornato"] = adesso.date().isoformat()
    ordine = ["progetto", "canale", "aggiornato", "richieste"]
    dati = {k: dati[k] for k in ordine if k in dati} | {k: v for k, v in dati.items() if k not in ordine}
    with tempfile.NamedTemporaryFile("w", encoding="utf-8", dir=str(Path(file).parent), delete=False, suffix=".tmp") as t:
        t.write(json.dumps(dati, ensure_ascii=False, indent=1) + "\n")
    os.replace(t.name, file)


def valida(campi, id_voci):
    """Gli stessi campi, puliti, o ValueError. Tipi, lunghezze, formato, data e riferimento."""
    if not isinstance(campi, dict):
        raise ValueError("richiesta")
    tema = campi.get("tema")
    note = campi.get("note") or ""
    if not isinstance(tema, str) or not tema.strip() or len(tema) > MAX_TEMA:
        raise ValueError("tema")
    if not isinstance(note, str) or len(note) > MAX_NOTE:
        raise ValueError("note")
    formato = campi.get("formato")
    if formato not in FORMATI:
        raise ValueError("formato")
    desiderata = campi.get("data_desiderata") or None
    if desiderata is not None:
        if not isinstance(desiderata, str) or not DATA.match(desiderata):
            raise ValueError("data")
        date.fromisoformat(desiderata)
    riferimento = campi.get("riferimento") or None
    if riferimento is not None and riferimento not in id_voci:
        raise ValueError("riferimento")
    return {"data_desiderata": desiderata, "formato": formato, "tema": tema.strip(), "note": note.strip(), "riferimento": riferimento}


def aggiungi(file, progetto, canale, campi, id_voci, adesso):
    puliti = valida(campi, id_voci)
    dati = leggi(file, progetto, canale)
    if len(dati["richieste"]) >= MAX_RICHIESTE:
        raise ValueError("troppe richieste")
    numeri = [int(m.group(1)) for r in dati["richieste"] if (m := re.match(r"rq-(\d+)$", str(r.get("id", ""))))]
    nuova = {"id": "rq-%03d" % (max(numeri, default=0) + 1), "creata": adesso.isoformat(timespec="seconds"),
             "data_desiderata": puliti["data_desiderata"], "formato": puliti["formato"], "tema": puliti["tema"], "note": puliti["note"],
             "riferimento": puliti["riferimento"], "stato": "nuova", "voce_id": None, "risposta": ""}
    dati["richieste"].append(nuova)
    scrivi(file, dati, adesso)
    return nuova


def annulla(file, progetto, canale, id_richiesta, adesso):
    """Solo una richiesta ancora `nuova` si annulla: se è già in lavorazione l'ha presa chi la elabora."""
    dati = leggi(file, progetto, canale)
    r = next((x for x in dati["richieste"] if x.get("id") == id_richiesta), None)
    if r is None:
        raise LookupError(id_richiesta)
    if r.get("stato") != "nuova":
        raise ValueError("non più annullabile")
    r["stato"] = "annullata"
    scrivi(file, dati, adesso)
    return r


def aperte(file, progetto, canale):
    return sum(1 for r in leggi(file, progetto, canale)["richieste"] if r.get("stato") in APERTE)

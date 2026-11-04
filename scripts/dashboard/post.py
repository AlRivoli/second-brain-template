"""Scheda Post: calendari dei post, uno per file `projects/<progetto>/post-<canale>.json`.

Schema: {progetto, canale, account, aggiornato, nota, voci[]}; ogni voce ha id, data, ora, tipo, formato, titolo,
descrizione, immagini [{percorso, nota}], didascalia, hashtag, testo_alternativo, stato, come_pubblicare, fonte,
tempo_stimato e, a volte, ricorrenza. Le immagini stanno nei repo dei progetti e si servono in sola lettura, solo
da una lista di cartelle ammesse; il browser non manda mai un percorso.
"""
import io
import json
import os
import re
import tempfile
import zipfile
from pathlib import Path

STATI = ("da creare", "da approvare", "pronto", "da fare", "programmato", "pubblicato")
SUFFISSI_ALTRI_FILE = ("-richieste", "-statistiche")  # file accanto al calendario, non calendari
ESTENSIONI = {".png": "image/png", ".jpg": "image/jpeg", ".jpeg": "image/jpeg"}


def scopri(cartella_progetti, nomi_ammessi):
    """File dei calendari: uno per `post-<canale>.json` nelle cartelle dei progetti elencati in INDEX."""
    out = []
    for nome in sorted(nomi_ammessi):
        for file in sorted((Path(cartella_progetti) / nome).glob("post-*.json")):
            if file.stem.endswith(SUFFISSI_ALTRI_FILE):
                continue
            out.append({"progetto": nome, "canale": file.stem.removeprefix("post-"), "file": file})
    return out


def carica(file):
    return json.loads(Path(file).read_text(encoding="utf-8"))


def immagine_ammessa(percorso, cartelle):
    """Il percorso come file servibile, o None. Ammessi: .png/.jpg sotto una delle cartelle, niente `..`, niente link
    simbolici sotto la cartella (la cartella stessa può stare dietro un link, per esempio /var su macOS)."""
    if not isinstance(percorso, str) or Path(percorso).suffix.lower() not in ESTENSIONI:
        return None
    assoluto = os.path.abspath(percorso)
    if assoluto != os.path.normpath(percorso):
        return None
    for cartella in cartelle:
        base = os.path.abspath(cartella)
        if not assoluto.startswith(base + os.sep):
            continue
        corrente = base
        for parte in Path(assoluto[len(base) + 1:]).parts:
            corrente = os.path.join(corrente, parte)
            if os.path.islink(corrente):
                return None
        if os.path.isfile(assoluto):
            return Path(assoluto)
    return None


def per_la_pagina(dati, progetto, canale, cartelle):
    """Il calendario come lo vede il browser: niente percorsi assoluti, ogni immagine ha un url e dice se esiste."""
    pagina = {k: v for k, v in dati.items() if k != "voci"}
    pagina["voci"] = []
    for voce in dati.get("voci", []):
        v = dict(voce)
        v["immagini"] = [
            {"nota": i.get("nota", ""), "esiste": immagine_ammessa(i.get("percorso"), cartelle) is not None,
             "url": "/api/post/immagine/%s/%s/%s/%d" % (progetto, canale, voce["id"], n)}
            for n, i in enumerate(voce.get("immagini", []))
        ]
        pagina["voci"].append(v)
    return pagina


def percorso_immagine(dati, id_voce, indice, cartelle):
    for voce in dati.get("voci", []):
        if voce.get("id") == id_voce and 0 <= indice < len(voce.get("immagini", [])):
            return immagine_ammessa(voce["immagini"][indice].get("percorso"), cartelle)
    return None


def imposta_stato(file, id_voce, stato):
    """Cambia solo il campo `stato` di una voce, nel testo del file: ordine dei campi e rientri restano com'erano."""
    if stato not in STATI:
        raise ValueError(stato)
    testo = Path(file).read_text(encoding="utf-8")
    prima = json.loads(testo)
    if not any(v.get("id") == id_voce for v in prima.get("voci", [])):
        raise LookupError(id_voce)
    inizio = testo.index(json.dumps(id_voce, ensure_ascii=False), testo.index('"voci"'))
    m = re.compile(r'"stato"\s*:\s*"[^"\\]*"').search(testo, inizio)
    if not m:
        raise LookupError(id_voce)
    nuovo = testo[:m.start()] + '"stato": ' + json.dumps(stato, ensure_ascii=False) + testo[m.end():]
    dopo = json.loads(nuovo)  # deve restare JSON valido, e cambiare solo quella voce
    for v in prima["voci"]:
        if v["id"] == id_voce:
            v["stato"] = stato
    if dopo != prima:
        raise ValueError("la modifica avrebbe toccato altri campi")
    with tempfile.NamedTemporaryFile("w", encoding="utf-8", dir=str(Path(file).parent), delete=False, suffix=".tmp") as t:
        t.write(nuovo)
    os.replace(t.name, file)


def _slug(testo):
    return re.sub(r"[^a-z0-9]+", "-", str(testo).lower()).strip("-") or "x"


def nome_file(voce, n, estensione):
    """<data>-<formato>-<id>-<nn>.<estensione>, con n da 1 nell'ordine di pubblicazione."""
    return "%s-%s-%s-%02d%s" % (_slug(voce.get("data", "")), _slug(voce.get("formato", "")), _slug(voce.get("id", "")), n, estensione)


def testo_didascalia(voce):
    """Didascalia, hashtag e testo alternativo di una voce, in un solo testo."""
    parti = [voce.get("titolo", ""), ""]
    if voce.get("didascalia"):
        parti += [voce["didascalia"], ""]
    if voce.get("hashtag"):
        parti += [" ".join(voce["hashtag"]), ""]
    for n, t in enumerate(voce.get("testo_alternativo", []), 1):
        parti.append("Testo alternativo %d: %s" % (n, t))
    return "\n".join(parti).strip() + "\n"


def zip_voce(voce, cartelle):
    """Le immagini ammesse di una voce, nell'ordine di pubblicazione, e didascalia.txt: uno ZIP in memoria."""
    memoria = io.BytesIO()
    with zipfile.ZipFile(memoria, "w", zipfile.ZIP_STORED) as z:
        for n, i in enumerate(voce.get("immagini", []), 1):
            file = immagine_ammessa(i.get("percorso"), cartelle)
            if file:
                z.write(file, nome_file(voce, n, file.suffix.lower()))
        z.writestr("didascalia.txt", testo_didascalia(voce))
    return memoria.getvalue()


def trova_voce(dati, id_voce):
    return next((v for v in dati.get("voci", []) if v.get("id") == id_voce), None)

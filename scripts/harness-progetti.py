#!/usr/bin/env python3
"""Dice a che punto è l'harness per agenti di ogni progetto del vault: la decisione dallo STATE, lo stato dal repo.

Uso: scripts/harness-progetti.py [--vault DIR] [--oggi AAAA-MM-GG] [--json]
     Una riga per progetto, oppure un elenco JSON. Non scrive mai, non usa un modello, non esegue nulla del repo.

La decisione è la riga `- **Harness:**` dello STATE.md: `da decidere`, `adeguare (data)` oppure
`non adeguare questo progetto (data)`. Una riga assente o non valida vale `da decidere`: un silenzio non è un no.
Lo stato non sta nel vault: si legge da `.claude/harness-status.json` nel repo del progetto, il riepilogo che lascia
l'audit del plugin ai-native-harness (solo numeri, data e commit).

Stati, il primo che vale: `senza repo`, `da decidere`, `escluso`, `da valutare` (nessun riepilogo leggibile),
`da rifare` (riepilogo più vecchio della validità), `da adeguare` (ci sono FAIL ad alta priorità), `conforme`.
Con più repo vale lo stato peggiore.

Il riepilogo è un file di un altro repo e un agente può riscriverlo: qui è un dato non fidato. Se ne leggono solo
quattro numeri e una data, controllati uno per uno; tutto il resto si ignora e un file che non torna vale `da valutare`.
La cartella riservata non si legge (ADR-001, ADR-002). Tempo O(progetti × repo), un file piccolo per repo.
"""
import argparse
import json
import re
import sys
from datetime import date
from pathlib import Path

VAULT = Path(__file__).resolve().parent.parent
PRIVATE_DIRS = {"lavoro", "_private"}
REPO = re.compile(r"^- \*\*Repo:\*\* (.+)$", re.M)
HARNESS = re.compile(r"^- \*\*Harness:\*\*(.*)$", re.M)
DECISIONE = re.compile(r"(adeguare|non adeguare questo progetto) \((\d{4}-\d{2}-\d{2})\)")
DATA = re.compile(r"\d{4}-\d{2}-\d{2}")
DOMANDE = 46  # le domande della checklist: pass + fail + na deve fare questo numero
GIORNI_VALIDITA = 30
MAX_RIEPILOGO = 64 * 1024  # un riepilogo vero pesa meno di 1 kB
GRAVITA = ("da valutare", "da rifare", "da adeguare", "conforme")  # dal peggiore al migliore


def _data(valore):
    """La data di una stringa AAAA-MM-GG che esiste davvero, o None."""
    if not isinstance(valore, str) or not DATA.fullmatch(valore):
        return None
    try:
        return date.fromisoformat(valore)
    except ValueError:
        return None


def _config(vault):
    try:
        dati = json.loads((vault / "config.json").read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return {}
    return dati if isinstance(dati, dict) else {}


def _sezione_harness(config):
    """Le chiavi dell'harness in config.json: del modulo `harness`, o del modulo `work-settings` che lo porta con sé."""
    moduli = config.get("moduli")
    moduli = moduli if isinstance(moduli, dict) else {}
    for sezione in (moduli.get("harness"), (moduli.get("work-settings") or {}).get("harness") if isinstance(moduli.get("work-settings"), dict) else None):
        if isinstance(sezione, dict):
            return sezione
    return {}


def attivo(config):
    """True solo se config.json accende l'harness: senza il modulo non si fanno domande e non si mostra uno stato."""
    return _sezione_harness(config).get("attivo") is True


def attivo_in(vault):
    """Come `attivo`, leggendo il config.json del vault: per chi deve solo sapere se fare la domanda (la dashboard)."""
    return attivo(_config(Path(vault)))


def giorni_validita(config):
    giorni = _sezione_harness(config).get("giorni_validita")
    return giorni if type(giorni) is int and 1 <= giorni <= 3650 else GIORNI_VALIDITA


def cartelle_riservate(config):
    """I nomi sotto projects/ che non si leggono: quelli fissi e la cartella scelta al setup (come scripts/verify)."""
    riservate = set(PRIVATE_DIRS)
    try:
        scelta = config["moduli"]["riservata"]["cartella"].replace("\\", "/")
        if scelta.startswith("projects/") and scelta.count("/") == 1:
            riservate.add(scelta.split("/")[1])
    except (KeyError, TypeError, AttributeError):
        pass
    return riservate


def decisione(testo):
    """(decisione, data) dallo STATE. Una riga assente, doppia o non valida è `da decidere`: la segnala scripts/verify."""
    righe = HARNESS.findall(testo)
    if len(righe) == 1:
        trovata = DECISIONE.fullmatch(righe[0].strip())
        if trovata and _data(trovata.group(2)):
            return ("adeguare" if trovata.group(1) == "adeguare" else "non adeguare"), trovata.group(2)
    return "da decidere", None


def repo_del_progetto(testo):
    """Le cartelle che esistono tra le righe `Repo:` dello STATE. `nessuno` e il segnaposto del template non contano."""
    cartelle = []
    for valore in REPO.findall(testo):
        valore = valore.strip()
        if not valore or valore == "nessuno" or valore.startswith("<"):
            continue
        try:
            cartella = Path(valore).expanduser()
            if cartella.is_dir():
                cartelle.append(cartella)
        except (OSError, ValueError, RuntimeError):
            continue  # un percorso che il sistema non sa leggere non è un repo
    return cartelle


def leggi_riepilogo(repo, oggi):
    """{data, pass, fail, na, fail_alta} dal riepilogo dell'audit, o None se manca o non torna. Non segue un link."""
    file = repo / ".claude" / "harness-status.json"
    try:
        if file.is_symlink() or not file.is_file() or file.stat().st_size > MAX_RIEPILOGO:
            return None
        dati = json.loads(file.read_text(encoding="utf-8"))
    except (OSError, ValueError, RecursionError):
        return None
    if not isinstance(dati, dict):
        return None
    numeri = [dati.get(chiave) for chiave in ("pass", "fail", "na", "fail_alta")]
    # type(...) is int: un booleano è un int per Python, ma non è un conteggio
    if not all(type(n) is int and n >= 0 for n in numeri):
        return None
    passati, falliti, non_applicabili, alti = numeri
    if passati + falliti + non_applicabili != DOMANDE or alti > falliti:
        return None
    quando = _data(dati.get("date"))
    if quando is None or quando > oggi:
        return None
    return {"data": quando.isoformat(), "pass": passati, "fail": falliti, "na": non_applicabili, "fail_alta": alti}


def _stato_del_repo(riepilogo, oggi, giorni):
    if riepilogo is None:
        return "da valutare"
    if (oggi - date.fromisoformat(riepilogo["data"])).days > giorni:
        return "da rifare"
    return "da adeguare" if riepilogo["fail_alta"] > 0 else "conforme"


def stato_progetti(vault=VAULT, oggi=None):
    """Una voce per progetto, in ordine di nome: {progetto, decisione, data_decisione, stato, repo, report}.

    `repo` è quanti repo esistono; `report` sono i numeri del repo che decide lo stato, o None. Dalle voci non escono
    percorsi né testo preso dai repo.
    """
    vault = Path(vault)
    oggi = _data(oggi) if isinstance(oggi, str) else (oggi or date.today())
    progetti = vault / "projects"
    if oggi is None or not progetti.is_dir():
        return []
    config = _config(vault)
    riservate, giorni = cartelle_riservate(config), giorni_validita(config)
    voci = []
    for stato_md in sorted(progetti.glob("*/STATE.md")):
        nome = stato_md.parent.name
        if nome in riservate or nome.startswith("."):
            continue
        testo = stato_md.read_text(encoding="utf-8", errors="replace")
        scelta, quando = decisione(testo)
        cartelle = repo_del_progetto(testo)
        stato, report = "senza repo", None
        if cartelle and scelta == "da decidere":
            stato = "da decidere"
        elif cartelle and scelta == "non adeguare":
            stato = "escluso"  # i repo di un progetto escluso non si aprono nemmeno
        elif cartelle:
            letti = [leggi_riepilogo(cartella, oggi) for cartella in cartelle]
            stato, report = min(((_stato_del_repo(r, oggi, giorni), r) for r in letti), key=lambda coppia: GRAVITA.index(coppia[0]))
        voci.append({"progetto": nome, "decisione": scelta, "data_decisione": quando, "stato": stato, "repo": len(cartelle), "report": report})
    return voci


def riga(voce):
    report = voce["report"]
    if report:
        return "%s: %s (%d PASS, %d FAIL di cui %d alti, report del %s)" % (
            voce["progetto"], voce["stato"], report["pass"], report["fail"], report["fail_alta"], report["data"])
    if voce["stato"] == "escluso":
        return "%s: escluso (non adeguare, dal %s)" % (voce["progetto"], voce["data_decisione"])
    return "%s: %s" % (voce["progetto"], voce["stato"])


def main(argv=None):
    ap = argparse.ArgumentParser(description="Stato dell'harness per agenti di ogni progetto del vault. Sola lettura.")
    ap.add_argument("--vault", default=str(VAULT))
    ap.add_argument("--oggi", help="AAAA-MM-GG, per i test e per rifare un calcolo; predefinito: oggi")
    ap.add_argument("--json", action="store_true")
    args = ap.parse_args(argv)
    oggi = date.today()
    if args.oggi is not None:
        oggi = _data(args.oggi)
        if oggi is None:
            ap.error("--oggi vuole una data AAAA-MM-GG che esiste")
    voci = stato_progetti(args.vault, oggi)
    if hasattr(sys.stdout, "reconfigure"):
        sys.stdout.reconfigure(encoding="utf-8")  # la console di Windows non è UTF-8 per conto suo
    print(json.dumps(voci, ensure_ascii=False, indent=2) if args.json else "\n".join(riga(v) for v in voci))
    return 0


if __name__ == "__main__":
    sys.exit(main())

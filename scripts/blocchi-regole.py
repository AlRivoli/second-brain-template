#!/usr/bin/env python3
"""Conta i blocchi dell'hook delle regole: quante volte ogni regola ha negato o chiesto conferma (ADR-013).

Uso: scripts/blocchi-regole.py [--giorni N] [--oggi AAAA-MM-GG] [--json] [--log FILE]
     Una riga per regola, dalla più frequente: `force-push: 2 nega`. Senza blocchi non stampa nulla su stdout.

Serve alla rilettura degli errori: /chiudi-giornata guarda i blocchi di oggi, /weekly-review quelli della settimana e chiede
quali erano falsi positivi. Il registro lo scrive .claude/hooks/regole.py: una riga JSON per blocco con data, nome della
regola e azione, mai il comando. Sta nella cartella dei log, fuori dal vault, e lo ruota scripts/ruota-log.py.

Il registro è un file che chiunque sulla macchina può scrivere, e ciò che esce da qui finisce nel prompt della chiusura:
ogni riga si controlla, e passano solo un nome di regola fatto di lettere minuscole, cifre e trattini, e un'azione nota.
Non scrive mai. Tempo O(righe lette), al massimo gli ultimi 2 MB del file.
"""
import argparse
import json
import re
import sys
from collections import Counter
from datetime import date, timedelta
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import percorsi  # noqa: E402

REGISTRO = "second-brain-regole.log"
NOME = re.compile(r"[a-z0-9][a-z0-9-]{0,59}")
DATA = re.compile(r"\d{4}-\d{2}-\d{2}")
AZIONI = ("nega", "chiedi")
MAX_BYTE = 2 * 1024 * 1024


def _data(valore):
    if not isinstance(valore, str) or not DATA.fullmatch(valore):
        return None
    try:
        return date.fromisoformat(valore)
    except ValueError:
        return None


def _righe(file):
    """Le ultime righe intere del registro, al massimo MAX_BYTE. Un file che manca o non si legge vale come vuoto."""
    try:
        with open(file, "rb") as f:
            f.seek(0, 2)
            lungo = f.tell()
            f.seek(max(0, lungo - MAX_BYTE))
            testo = f.read().decode("utf-8", errors="replace")
    except OSError:
        return []
    righe = testo.splitlines()
    return righe[1:] if lungo > MAX_BYTE else righe  # la prima può essere tagliata a metà


def conta(file, oggi, giorni=7):
    """[{regola, azione, volte}] dei blocchi negli ultimi `giorni` giorni, oggi compreso, dalla regola più frequente."""
    dal = oggi - timedelta(days=giorni - 1)
    volte = Counter()
    for riga in _righe(file):
        try:
            voce = json.loads(riga)
        except (ValueError, RecursionError):
            continue
        if not isinstance(voce, dict):
            continue
        quando, regola, azione = _data(voce.get("data")), voce.get("regola"), voce.get("azione")
        if quando is None or not dal <= quando <= oggi:
            continue
        if isinstance(regola, str) and NOME.fullmatch(regola) and azione in AZIONI:
            volte[(regola, azione)] += 1
    ordinati = sorted(volte.items(), key=lambda coppia: (-coppia[1], coppia[0]))
    return [{"regola": regola, "azione": azione, "volte": n} for (regola, azione), n in ordinati]


def main(argv=None):
    ap = argparse.ArgumentParser(description="Conta i blocchi dell'hook delle regole. Sola lettura.")
    ap.add_argument("--giorni", type=int, default=7, help="quanti giorni contare, oggi compreso (predefinito 7)")
    ap.add_argument("--oggi", help="AAAA-MM-GG, per i test; predefinito: oggi")
    ap.add_argument("--json", action="store_true")
    ap.add_argument("--log", help="il file del registro; predefinito: quello nella cartella dei log")
    args = ap.parse_args(argv)
    if not 1 <= args.giorni <= 366:
        ap.error("--giorni vuole un numero tra 1 e 366")
    oggi = date.today()
    if args.oggi is not None:
        oggi = _data(args.oggi)
        if oggi is None:
            ap.error("--oggi vuole una data AAAA-MM-GG che esiste")
    voci = conta(Path(args.log) if args.log else percorsi.cartella_log() / REGISTRO, oggi, args.giorni)
    if args.json:
        print(json.dumps(voci, ensure_ascii=False, indent=2))
    elif voci:
        print("\n".join("%s: %d %s" % (v["regola"], v["volte"], v["azione"]) for v in voci))
    else:
        sys.stderr.write("nessun blocco negli ultimi %d giorni\n" % args.giorni)
    return 0


if __name__ == "__main__":
    sys.exit(main())

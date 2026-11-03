#!/usr/bin/env python3
"""Barra di stato di Claude Code: salva le percentuali d'uso del piano per la dashboard e le stampa in breve.

Claude Code passa su stdin il JSON della sessione; qui si tengono solo `rate_limits.five_hour` e `rate_limits.seven_day`
(percentuale e rinnovo). Il resto del JSON (cartelle, percorsi) non si salva. Il file è ~/.claude/usage-live.json.
Le percentuali arrivano a ogni risposta di una sessione attiva: a sessioni ferme non cambiano.
"""
import json
import os
import sys
import time
from pathlib import Path

FILE = Path.home() / ".claude" / "usage-live.json"
NOMI = {"five_hour": "5h", "seven_day": "sett"}


def main():
    try:
        limiti = (json.load(sys.stdin).get("rate_limits") or {})
    except ValueError:
        return
    dati = {k: {"percentuale": limiti[k].get("used_percentage"), "rinnovo": limiti[k].get("resets_at")}
            for k in NOMI if isinstance(limiti.get(k), dict)}
    if not dati:
        return
    try:  # la finestra di 5 ore manca nel JSON quando non è aperta: si tiene la precedente finché non scade
        prima = json.loads(FILE.read_text(encoding="utf-8")).get("five_hour")
    except (OSError, ValueError):
        prima = None
    if "five_hour" not in dati and prima and (prima.get("rinnovo") or 0) > time.time():
        dati["five_hour"] = prima
    tmp = FILE.with_suffix(".tmp")
    tmp.write_text(json.dumps({"salvato": int(time.time()), **dati}), encoding="utf-8")
    os.replace(tmp, FILE)
    print(" · ".join("%s %s%%" % (NOMI[k], round(v["percentuale"])) for k, v in dati.items() if v["percentuale"] is not None))


if __name__ == "__main__":
    main()

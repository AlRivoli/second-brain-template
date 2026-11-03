#!/usr/bin/env python3
"""Prima delle bozze nuove del lunedì: le bozze di giorni precedenti che non sono state pubblicate passano a "scartata".

I file restano dove sono (e nella cronologia git): cambia solo content/stato.json, e la dashboard non le mostra più.
Uso: scarta-bozze.py [AAAA-MM-GG]  (la data di oggi: si scartano le bozze con la data nel nome precedente).
"""
import json
import sys
from datetime import date
from pathlib import Path

CONTENT = Path(__file__).resolve().parent.parent / "content"
FILE = CONTENT / "stato.json"


def scarta(oggi, content=CONTENT, file=FILE):
    try:
        stati = json.loads(file.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        stati = {}
    scartate = []
    for md in sorted(content.glob("*/*.md")):
        chiave = md.parent.name + "/" + md.name
        if chiave not in stati and md.name[:10] < oggi:
            stati[chiave] = {"stato": "scartata", "data": oggi}
            scartate.append(chiave)
    if scartate:
        file.write_text(json.dumps(stati, ensure_ascii=False, indent=1, sort_keys=True) + "\n", encoding="utf-8")
    return scartate


if __name__ == "__main__":
    for c in scarta(sys.argv[1] if len(sys.argv) > 1 else date.today().isoformat()):
        print("scartata:", c)

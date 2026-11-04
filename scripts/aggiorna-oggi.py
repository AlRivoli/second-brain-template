#!/usr/bin/env python3
"""Scrive OGGI.md con la data di oggi, perché chi legge il vault sappia che giorno è.

Lo lancia avvio.py (login e feriali alle 8:00): nei weekend si aggiorna al primo login.
"""
from datetime import datetime
from pathlib import Path

VAULT = Path(__file__).resolve().parent.parent
GIORNI = ["domenica", "lunedì", "martedì", "mercoledì", "giovedì", "venerdì", "sabato"]


def testo(adesso):
    anno, settimana, _ = adesso.isocalendar()
    return (
        "# Oggi\n\n"
        f"Oggi è {GIORNI[adesso.isoweekday() % 7]} {adesso:%F}, settimana ISO {anno}-W{settimana:02d}.\n\n"
        f"Scritto da `scripts/aggiorna-oggi.py` alle {adesso:%H:%M}. "
        "Se la data qui non è quella di oggi, il file è vecchio: fidati dell'orologio del Mac.\n"
    )


if __name__ == "__main__":
    (VAULT / "OGGI.md").write_text(testo(datetime.now()), encoding="utf-8")

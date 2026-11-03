#!/usr/bin/env python3
"""Taratura del filtro del radar dai voti della dashboard (sola lettura, nessun modello).

Legge radar/feedback.jsonl (l'ultima riga per titolo vale) e, per fasce di score da 0,05, conta
scarti giusti e falsi scarti. Suggerisce se intervenire su soglia o prompt, senza cambiare nulla.
Uso: scripts/radar-taratura.py [file]
"""
import json
import math
import sys
from pathlib import Path

VAULT = Path(__file__).resolve().parent.parent
PASSO = 0.05
MINIMO_VOTI = 10  # sotto questa soglia di voti il suggerimento sarebbe rumore


def leggi(file):
    """Ultimo voto per titolo; le righe rovinate si saltano."""
    voti = {}
    if file.exists():
        for riga in file.read_text(encoding="utf-8").splitlines():
            try:
                v = json.loads(riga)
                v["score"] = float(v["score"])
                voti[v["titolo"]] = v
            except (ValueError, KeyError, TypeError):
                continue
    return voti


def fasce(voti):
    """Fascia (estremo basso) -> [scarti giusti, falsi scarti]."""
    out = {}
    for v in voti.values():
        basso = round(math.floor(v["score"] / PASSO + 1e-9) * PASSO, 2)
        out.setdefault(basso, [0, 0])[v["giudizio"] == "falso-scarto"] += 1
    return dict(sorted(out.items()))


def suggerimento(voti):
    """Testo di consiglio. Le scartate hanno già superato la soglia dello stadio 1: se sono falsi scarti, il colpevole è lo stadio 2."""
    if len(voti) < MINIMO_VOTI:
        return f"Troppo pochi voti ({len(voti)} su {MINIMO_VOTI}): serve più feedback prima di toccare soglia o prompt."
    falsi = [v["score"] for v in voti.values() if v["giudizio"] == "falso-scarto"]
    if not falsi:
        return "Nessun falso scarto: soglia e prompt vanno bene, semmai si potrebbe alzare la soglia."
    quota = len(falsi) / len(voti)
    if quota < 0.2:
        return f"{len(falsi)} falsi scarti su {len(voti)} ({quota:.0%}): il filtro regge, nessuna modifica."
    return (f"{len(falsi)} falsi scarti su {len(voti)} ({quota:.0%}, il più alto a {max(falsi):.2f}): lo stadio 2 è troppo severo, rivedi il prompt. "
            "Abbassare la soglia dello stadio 1 non recupera questi casi (l'hanno già superata): serve solo se mancano novità che non arrivano allo stadio 2, e qui non si misura.")


def main():
    voti = leggi(Path(sys.argv[1]) if len(sys.argv) > 1 else VAULT / "radar" / "feedback.jsonl")
    print("Fascia score   giusti  falsi")
    for basso, (giusti, falsi) in fasce(voti).items():
        print(f"{basso:.2f}-{basso + PASSO:.2f}    {giusti:6d} {falsi:6d}")
    print(suggerimento(voti))


if __name__ == "__main__":
    main()

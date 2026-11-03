#!/usr/bin/env python3
"""Calcola un vettore per progetto con bge-m3 (Ollama) e lo salva in radar/.indice-progetti.json.

Il radar confronta ogni novità con questi vettori (stadio 1, similarità coseno).
Testo per progetto: la riga di projects/INDEX.md e la sezione "Obiettivo attuale" dello STATE.
"""
import json
import re
import sys
import urllib.request
from datetime import date
from pathlib import Path

VAULT = Path(__file__).resolve().parent.parent
MODELLO = "bge-m3"
OLLAMA = "http://127.0.0.1:11434/api/embed"
OUTPUT = VAULT / "radar" / ".indice-progetti.json"


def progetti():
    """Restituisce (nome, testo) per ogni riga di INDEX.md con un link a uno STATE."""
    righe = (VAULT / "projects" / "INDEX.md").read_text(encoding="utf-8").splitlines()
    for riga in righe:
        m = re.search(r"\[\[(projects/([^/\\|]+)/STATE)\\?\|", riga)
        if not m:
            continue
        nome = m.group(2)
        state = (VAULT / "projects" / nome / "STATE.md").read_text(encoding="utf-8")
        obiettivo = re.search(r"## Obiettivo attuale\n(.*?)(?=\n## |\Z)", state, re.S)
        testo = f"{riga}\n{obiettivo.group(1).strip() if obiettivo else ''}"
        yield nome, testo


def embed(testi):
    richiesta = json.dumps({"model": MODELLO, "input": testi}).encode("utf-8")
    req = urllib.request.Request(OLLAMA, data=richiesta, headers={"Content-Type": "application/json"})
    with urllib.request.urlopen(req, timeout=120) as risposta:
        return json.load(risposta)["embeddings"]


def main():
    lista = list(progetti())
    if not lista:
        sys.exit("nessun progetto trovato in projects/INDEX.md")
    vettori = embed([testo for _, testo in lista])
    dati = {
        "modello": MODELLO,
        "aggiornato": date.today().isoformat(),
        "progetti": [
            {"nome": nome, "vettore": vettore} for (nome, _), vettore in zip(lista, vettori)
        ],
    }
    OUTPUT.parent.mkdir(exist_ok=True)
    OUTPUT.write_text(json.dumps(dati, ensure_ascii=False), encoding="utf-8")
    print(f"{len(lista)} progetti, dimensione {len(vettori[0])}, salvati in {OUTPUT}")


if __name__ == "__main__":
    main()

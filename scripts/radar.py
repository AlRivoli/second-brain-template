#!/usr/bin/env python3
"""Radar completo sull'ultima inbox: stadio 1 (embedding), stadio 2 (giudizio), output in radar/.

Richiede Ollama attivo con bge-m3 e qwen3:8b, e radar/.indice-progetti.json (scripts/indice-embedding.py).
"""
import subprocess
import sys
from pathlib import Path

VAULT = Path(__file__).resolve().parent.parent


def _lancia(vault, *args):
    subprocess.run([sys.executable, "-I", *args], cwd=vault, check=True)


def _piu_recente(file):
    return max(file, key=lambda f: f.stat().st_mtime, default=None)


def radar(vault=VAULT, lancia=_lancia):
    # Il job settimanale gira anche se n8n non ha consegnato una inbox nuova: in quel caso non rifare l'ultima.
    novita = _piu_recente((vault / "inbox").glob("*-novita.md"))
    if novita is None:
        print("radar: nessuna inbox, salto")
        return
    # Fatta = esiste la scheda finale radar/<data>.md più recente dell'inbox. I candidati dello stadio 1 non bastano:
    # se lo stadio 2 fallisce, il giro dopo deve riprovare.
    data = novita.name[:-len("-novita.md")]
    scheda = vault / "radar" / f"{data}.md"
    if scheda.is_file() and scheda.stat().st_mtime > novita.stat().st_mtime:
        print(f"radar: inbox/{novita.name} già elaborata, salto")
        return
    lancia(vault, "scripts/indice-embedding.py")
    lancia(vault, "scripts/radar-stadio1.py")
    candidati = f"radar/.candidati-{data}.json"
    lancia(vault, "scripts/radar-stadio2.py", candidati)
    lancia(vault, "scripts/radar-output.py", candidati)


if __name__ == "__main__":
    radar()

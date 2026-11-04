#!/usr/bin/env python3
"""Versioni installate e ultime disponibili. Segnala, non aggiorna."""
import json
import subprocess


def esegui(*cmd):
    try:
        return subprocess.run(cmd, capture_output=True, text=True, timeout=60).stdout.strip()
    except (OSError, subprocess.SubprocessError):
        return ""


def pypi(pacchetto):
    """Con curl, come prima: usa i certificati del sistema, che il Python di python.org può non avere."""
    try:
        return json.loads(esegui("curl", "-s", "-m", "20", f"https://pypi.org/pypi/{pacchetto}/json"))["info"]["version"]
    except (ValueError, KeyError):
        return ""


def parola(testo, n):
    """La n-esima parola della prima riga, o ''."""
    parole = (testo.splitlines() or [""])[0].split()
    return parole[n] if len(parole) > n else ""


def righe(esegui=esegui, pypi=pypi):
    graphify = parola(esegui("graphify", "--version"), 1)
    n8n = (esegui("n8n", "--version").splitlines() or [""])[-1]
    claude = parola(esegui("claude", "--version"), 0)
    return [
        ("Graphify (graphifyy, PyPI)", graphify, pypi("graphifyy")),
        ("n8n (npm)", n8n, esegui("npm", "view", "n8n", "version")),
        ("Claude Code", claude, "vedi brew"),
    ]


if __name__ == "__main__":
    for nome, inst, ultima in righe():
        print(f"- {nome}: installata {inst or 'assente'}, ultima {ultima or 'non verificata'}")

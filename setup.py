#!/usr/bin/env python3
"""First-run wizard for the second brain. Standard library only; works on macOS, Linux and Windows.

Usage:
    python3 setup.py                 (Windows: py -3 setup.py)
    python3 setup.py --name "Ada" --role "developer" --language en --yes     no questions
    python3 setup.py --clean-example     remove the example project once you have your own
    python3 setup.py --dry-run           show what it would do, change nothing

What it does: writes config.json, creates memory/*.md from the *.example.md files and fills your name in CLAUDE.md,
creates the ignored folder projects/_private/. It never overwrites a file that already exists.
"""
import argparse
import json
import re
import shutil
import sys
import time
from pathlib import Path

RADICE = Path(__file__).resolve().parent

MESSAGGI = {
    "en": {
        "name": "Your name", "role": "Your role (optional)", "language": "Language for the agent's replies (en/it)",
        "wrote": "wrote", "exists": "already exists, left alone", "would": "would write", "removed": "removed",
        "no_example": "the example project is not there (already removed)",
        "done": "Done. Next: python3 doctor.py (Windows: py -3 doctor.py), then open GETTING_STARTED.md.",
        "bad_lang": "language must be en or it",
    },
    "it": {
        "name": "Il tuo nome", "role": "Il tuo ruolo (facoltativo)", "language": "Lingua delle risposte dell'agente (en/it)",
        "wrote": "scritto", "exists": "esiste già, non lo tocco", "would": "scriverei", "removed": "rimosso",
        "no_example": "il progetto d'esempio non c'è (già rimosso)",
        "done": "Fatto. Ora: python3 doctor.py (Windows: py -3 doctor.py), poi apri INIZIA.md.",
        "bad_lang": "la lingua deve essere en o it",
    },
}


def domanda(testo, predefinito=""):
    risposta = input("%s%s: " % (testo, " [%s]" % predefinito if predefinito else "")).strip()
    return risposta or predefinito


def scrivi(percorso, contenuto, msg, dry, radice=RADICE, forza=False):
    """Scrive solo se il file non c'è. Ritorna True se lo ha scritto."""
    if percorso.exists() and not forza:
        print("  %s: %s" % (percorso.relative_to(radice).as_posix(), msg["exists"]))
        return False
    print("  %s: %s" % (percorso.relative_to(radice).as_posix(), msg["would" if dry else "wrote"]))
    if not dry:
        percorso.parent.mkdir(parents=True, exist_ok=True)
        percorso.write_text(contenuto, encoding="utf-8")
    return True


def installa(nome, ruolo, lingua, msg, dry=False, radice=RADICE):
    """Crea config.json, i file di memory e il nome in CLAUDE.md. Non sovrascrive niente."""
    cfg = {"nome": nome, "ruolo": ruolo, "lingua": lingua, "nome_firma": nome, "fuso": time.tzname[0]}
    scrivi(radice / "config.json", json.dumps(cfg, ensure_ascii=False, indent=2) + "\n", msg, dry, radice)
    for esempio in sorted((radice / "memory").glob("*.example.md")):
        testo = esempio.read_text(encoding="utf-8").replace("<your name>", nome).replace("<your role>", ruolo or "")
        scrivi(esempio.with_name(esempio.name.replace(".example", "")), testo, msg, dry, radice)
    claude = radice / "CLAUDE.md"
    if claude.exists():
        testo = claude.read_text(encoding="utf-8")
        if "<your name>" in testo:
            print("  CLAUDE.md: %s" % msg["would" if dry else "wrote"])
            if not dry:
                claude.write_text(testo.replace("<your name>, <your role>", ", ".join(x for x in (nome, ruolo) if x)).replace("<your name>", nome), encoding="utf-8")
    if not dry:
        (radice / "projects" / "_private").mkdir(parents=True, exist_ok=True)


def pulisci_esempio(msg, dry=False, radice=RADICE):
    """Toglie projects/example-project e la sua riga in projects/INDEX.md. Solo quel percorso, mai altro."""
    cartella = radice / "projects" / "example-project"
    if not cartella.is_dir():
        print("  " + msg["no_example"])
        return
    print("  projects/example-project: %s" % msg["would" if dry else "removed"])
    if dry:
        return
    shutil.rmtree(cartella)
    indice = radice / "projects" / "INDEX.md"
    righe = [r for r in indice.read_text(encoding="utf-8").splitlines() if "[[projects/example-project/STATE" not in r]
    indice.write_text("\n".join(righe) + "\n", encoding="utf-8")


def main(argv=None, radice=RADICE):
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--name")
    ap.add_argument("--role")
    ap.add_argument("--language")
    ap.add_argument("--yes", action="store_true", help="do not ask, use the options and the defaults")
    ap.add_argument("--clean-example", action="store_true")
    ap.add_argument("--dry-run", action="store_true")
    a = ap.parse_args(argv)
    lingua = (a.language or "en").lower()
    if lingua not in MESSAGGI:
        sys.exit(MESSAGGI["en"]["bad_lang"])
    msg = MESSAGGI[lingua]
    if a.clean_example:
        pulisci_esempio(msg, a.dry_run, radice)
        return 0
    if not a.yes:
        lingua = domanda(msg["language"], lingua).lower()
        if lingua not in MESSAGGI:
            sys.exit(MESSAGGI["en"]["bad_lang"])
        msg = MESSAGGI[lingua]
    nome = a.name if a.name is not None else ("" if a.yes else domanda(msg["name"]))
    ruolo = a.role if a.role is not None else ("" if a.yes else domanda(msg["role"]))
    nome = re.sub(r"[\r\n]+", " ", nome).strip() or "<your name>"  # una riga sola: finisce in un file di istruzioni
    ruolo = re.sub(r"[\r\n]+", " ", ruolo).strip()
    installa(nome, ruolo, lingua, msg, a.dry_run, radice)
    print(msg["done"])
    return 0


if __name__ == "__main__":
    sys.exit(main())

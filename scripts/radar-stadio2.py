#!/usr/bin/env python3
"""Stadio 2 del radar: giudizio di qwen3:8b sui candidati dello stadio 1.

Input: radar/.candidati-<data>.json. Per ogni candidato aggiunge "rilevante" e "motivo".
Il profilo del progetto è lo stack in projects/INDEX.md e l'obiettivo attuale dello STATE.
"""
import json
import re
import sys
import urllib.request
from datetime import datetime
from pathlib import Path

VAULT = Path(__file__).resolve().parent.parent
OLLAMA = "http://127.0.0.1:11434/api/chat"
MODELLO = "qwen3:8b"


def _ruolo():
    """Chi legge il radar, per il prompt: `ruolo_radar` di config.json (per esempio "un ingegnere full stack")."""
    try:
        return json.loads((VAULT / "config.json").read_text(encoding="utf-8")).get("ruolo_radar") or "una persona che lavora con il software"
    except (OSError, ValueError):
        return "una persona che lavora con il software"


RIGA = re.compile(r"^\| \[\[projects/([^/\\|]+)/STATE")
SOGLIA = 4  # punteggio minimo per considerare una novità rilevante: prova del 2026-10-28, 6 positivi su 10 e 6 falsi su 65
ISTRUZIONI = (
    "Sei il filtro del radar di " + _ruolo() + ". Ti do un progetto (stack e obiettivo) e il titolo di una novità tecnica. "
    "Assegna un punteggio da 0 a 10 a quanto la novità vale la pena di essere letta per quel progetto.\n"
    "0-2: tecnologia che il progetto non usa o argomento lontano (non basta una parola in comune).\n"
    "3-5: tocca lo stack o il tema del progetto, anche in modo indiretto: una release del runtime o di una dipendenza che usa, "
    "una tecnica vicina al suo obiettivo, un cambiamento di una piattaforma che usa.\n"
    "6-10: il progetto potrebbe usarla, aggiornare qualcosa o rivedere una scelta.\n"
    "Nel dubbio dai un punteggio più alto: è meglio leggere una novità inutile che perderne una utile. "
    'Rispondi solo con JSON {"punteggio": numero, "motivo": "una frase in italiano"}.'
)


def profili():
    """Dizionario nome progetto -> stack e obiettivo, letti dal vault."""
    out = {}
    for riga in (VAULT / "projects" / "INDEX.md").read_text(encoding="utf-8").splitlines():
        m = RIGA.match(riga)
        if not m:
            continue
        nome = m.group(1)
        celle = [c.strip() for c in riga.split("|")]
        # Il pipe nel wikilink è escapato (\|): la colonna Stack è la quarta voce dello split.
        stack = celle[3]
        state = (VAULT / "projects" / nome / "STATE.md").read_text(encoding="utf-8")
        obiettivo = re.search(r"## Obiettivo attuale\n(.*?)(?=\n## |\Z)", state, re.S)
        out[nome] = f"stack: {stack}. obiettivo: {obiettivo.group(1).strip() if obiettivo else 'n.d.'}"
    return out


def giudica(profilo, titolo):
    messaggio = f"Progetto: {profilo}\nNovità: \"{titolo}\""
    richiesta = {
        "model": MODELLO,
        "stream": False,
        "think": False,
        "format": "json",
        "messages": [{"role": "system", "content": ISTRUZIONI}, {"role": "user", "content": messaggio}],
    }
    req = urllib.request.Request(OLLAMA, data=json.dumps(richiesta).encode("utf-8"), headers={"Content-Type": "application/json"})
    with urllib.request.urlopen(req, timeout=300) as risposta:
        dati = json.load(risposta)
    registra(dati)
    return dati["message"]["content"]


def registra(dati):
    """Aggiunge una riga a radar/.prestazioni.jsonl: tempo, token e velocità della chiamata, per la dashboard."""
    riga = {
        "ts": datetime.now().isoformat(timespec="seconds"),
        "modello": MODELLO,
        "operazione": "giudizio",
        "durata_s": round(dati["total_duration"] / 1e9, 3),
        "token_in": dati.get("prompt_eval_count", 0),
        "token_out": dati.get("eval_count", 0),
        "token_al_secondo": round(dati["eval_count"] / (dati["eval_duration"] / 1e9), 1) if dati.get("eval_duration") else None,
    }
    with (VAULT / "radar" / ".prestazioni.jsonl").open("a", encoding="utf-8") as file:
        file.write(json.dumps(riga) + "\n")


def main():
    file = Path(sys.argv[1]) if len(sys.argv) > 1 else max((VAULT / "radar").glob(".candidati-*.json"))
    candidati = json.loads(file.read_text(encoding="utf-8"))
    mappa = profili()
    for c in candidati:
        verdetto = json.loads(giudica(mappa[c["progetto"]], c["titolo"]))
        c["punteggio"] = float(verdetto["punteggio"])
        c["rilevante"] = c["punteggio"] >= SOGLIA
        c["motivo"] = verdetto["motivo"]
        print("SI " if c["rilevante"] else "NO ", c["progetto"], "-", c["titolo"][:60], "\n    ", c["motivo"])
    file.write_text(json.dumps(candidati, ensure_ascii=False, indent=2), encoding="utf-8")


if __name__ == "__main__":
    main()

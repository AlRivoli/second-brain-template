#!/usr/bin/env python3
"""Stadio 1 del radar: confronta ogni novità di inbox/ con i progetti (similarità coseno).

Input: il file inbox/<data>-novita.md più recente, e radar/.indice-progetti.json.
Output: radar/.candidati-<data>.json con le novità sopra soglia (ADR-005, 0.5 da tarare).
"""
import json
import math
import re
import urllib.request
from datetime import datetime
from pathlib import Path

VAULT = Path(__file__).resolve().parent.parent
SOGLIA = 0.5
OLLAMA = "http://127.0.0.1:11434/api/embed"
VOCE = re.compile(r"^- \[(?P<titolo>[^\]]+)\]\((?P<url>[^)]+)\)")


def embed(testi):
    richiesta = json.dumps({"model": "bge-m3", "input": testi}).encode("utf-8")
    req = urllib.request.Request(OLLAMA, data=richiesta, headers={"Content-Type": "application/json"})
    with urllib.request.urlopen(req, timeout=120) as risposta:
        dati = json.load(risposta)
    registra(dati)
    return dati["embeddings"]


def registra(dati):
    """Aggiunge una riga a radar/.prestazioni.jsonl: tempo e token della chiamata, per la dashboard."""
    riga = {
        "ts": datetime.now().isoformat(timespec="seconds"),
        "modello": "bge-m3",
        "operazione": "embed",
        "durata_s": round(dati["total_duration"] / 1e9, 3),
        "token_in": dati.get("prompt_eval_count", 0),
    }
    with (VAULT / "radar" / ".prestazioni.jsonl").open("a", encoding="utf-8") as file:
        file.write(json.dumps(riga) + "\n")


def coseno(a, b):
    return sum(x * y for x, y in zip(a, b)) / (math.sqrt(sum(x * x for x in a)) * math.sqrt(sum(y * y for y in b)))


def voci(file):
    for riga in file.read_text(encoding="utf-8").splitlines():
        m = VOCE.match(riga)
        if m:
            yield m.group("titolo"), m.group("url")


def main():
    file = max((VAULT / "inbox").glob("*-novita.md"))
    indice = json.loads((VAULT / "radar" / ".indice-progetti.json").read_text(encoding="utf-8"))
    lista = list(voci(file))
    vettori = embed([titolo for titolo, _ in lista])

    candidati = []
    for (titolo, url), vettore in zip(lista, vettori):
        punteggi = [(coseno(vettore, p["vettore"]), p["nome"]) for p in indice["progetti"]]
        score, progetto = max(punteggi)
        if score >= SOGLIA:
            candidati.append({"titolo": titolo, "url": url, "progetto": progetto, "score": round(score, 3)})

    candidati.sort(key=lambda c: -c["score"])
    out = VAULT / "radar" / f".candidati-{file.name[:10]}.json"
    out.write_text(json.dumps(candidati, ensure_ascii=False, indent=2), encoding="utf-8")
    print(f"{len(lista)} novità, {len(candidati)} sopra soglia {SOGLIA}, salvate in {out}")
    for c in candidati[:10]:
        print(c["score"], c["progetto"], "-", c["titolo"])


if __name__ == "__main__":
    main()

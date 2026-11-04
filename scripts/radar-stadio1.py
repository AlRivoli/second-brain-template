#!/usr/bin/env python3
"""Stadio 1 del radar: confronta ogni novità di inbox/ con i progetti (similarità coseno degli embedding, o parole chiave se non c'è un modello).

Input: il file inbox/<data>-novita.md più recente, e radar/.indice-progetti.json.
Output: radar/.candidati-<data>.json con le novità sopra soglia (ADR-005, 0.5 da tarare).
"""
import importlib.util
import json
import math
import re
from datetime import datetime
from pathlib import Path

VAULT = Path(__file__).resolve().parent.parent
SOGLIA = 0.5
VOCE = re.compile(r"^- \[(?P<titolo>[^\]]+)\]\((?P<url>[^)]+)\)")
PAROLE = re.compile(r"[a-z0-9][a-z0-9.+#-]{2,}")
# parole che non dicono niente sul progetto, in italiano e in inglese
COMUNI = set("""the and for with from into your you our are not new how why what who now out all use using used can will has have was been this that
 these those more most about over under after before introducing announcing available release released update updated version blog post news
 stack obiettivo progetto attuale nel nella dei del della delle per con che una uno sono come anche più non gli alle dal dai""".split())


def _carica(nome):
    spec = importlib.util.spec_from_file_location(nome, Path(__file__).resolve().parent / (nome + ".py"))
    modulo = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(modulo)
    return modulo


modello = _carica("modello")


def embed(testi):
    risposta = modello.incorpora("radar_embedding", testi, vault=VAULT)
    registra(risposta.statistiche)
    return risposta.testo


def registra(dati):
    """Aggiunge una riga a radar/.prestazioni.jsonl: tempo e token della chiamata, per la dashboard."""
    if not dati.get("total_duration"):
        return
    riga = {
        "ts": datetime.now().isoformat(timespec="seconds"),
        "modello": modello.scelta("radar_embedding", VAULT)[1],
        "operazione": "embed",
        "durata_s": round(dati["total_duration"] / 1e9, 3),
        "token_in": dati.get("prompt_eval_count", 0),
    }
    with (VAULT / "radar" / ".prestazioni.jsonl").open("a", encoding="utf-8") as file:
        file.write(json.dumps(riga) + "\n")


def parole(testo):
    return set(PAROLE.findall(testo.lower())) - COMUNI


def per_parole_chiave(lista, profili):
    """Stadio 1 senza modello: un progetto è candidato se il titolo ha parole in comune con il suo stack e il suo obiettivo.
    Punteggio 0,5 per parola in comune (al massimo 1), stessa soglia degli embedding. Più rozzo: lascia passare di più, lo stadio 2 sfoltisce."""
    candidati = []
    for titolo, url in lista:
        voti = [(min(1.0, 0.5 * len(parole(titolo) & parole(testo))), nome) for nome, testo in profili.items()]
        score, progetto = max(voti, default=(0, ""))
        if score >= SOGLIA:
            candidati.append({"titolo": titolo, "url": url, "progetto": progetto, "score": round(score, 3)})
    return candidati


def coseno(a, b):
    return sum(x * y for x, y in zip(a, b)) / (math.sqrt(sum(x * x for x in a)) * math.sqrt(sum(y * y for y in b)))


def voci(file):
    for riga in file.read_text(encoding="utf-8").splitlines():
        m = VOCE.match(riga)
        if m:
            yield m.group("titolo"), m.group("url")


def main():
    file = max((VAULT / "inbox").glob("*-novita.md"))
    lista = list(voci(file))
    if modello.scelta("radar_embedding", VAULT)[0] == "none":
        candidati = per_parole_chiave(lista, _carica("radar-stadio2").profili())
    else:
        indice = json.loads((VAULT / "radar" / ".indice-progetti.json").read_text(encoding="utf-8"))
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

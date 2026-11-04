#!/usr/bin/env python3
"""Scrive radar/<data>.md dai candidati dello stadio 2.

Le novità rilevanti diventano schede. Le scartate restano elencate, così si vedono i falsi negativi
e si può tarare il filtro (ADR-005).
"""
import json
import sys
from pathlib import Path

VAULT = Path(__file__).resolve().parent.parent


def scheda(c):
    return (
        f"### [{c['titolo']}]({c['url']})\n"
        f"- **Progetto:** [[projects/{c['progetto']}/STATE|{c['progetto']}]]\n"
        f"- **Punteggio:** {c['score']}\n"
        f"- **Motivo:** {c['motivo']}\n"
    )


def main():
    file = Path(sys.argv[1])
    candidati = json.loads(file.read_text(encoding="utf-8"))
    data = file.name[len(".candidati-"):-len(".json")]
    rilevanti = [c for c in candidati if c["rilevante"]]
    scartati = [c for c in candidati if not c["rilevante"]]

    testo = [f"# Radar del {data}", ""]
    testo.append("## Da leggere")
    testo.append("")
    if rilevanti:
        testo += [scheda(c) for c in rilevanti]
    else:
        testo.append("Nessuna novità rilevante in questo giro.")
        testo.append("")
    testo += ["## Scartate dallo stadio 2", ""]
    testo += [f"- {c['titolo']} (score {c['score']}, {c['progetto']}): {c['motivo']}" for c in scartati]
    testo.append("")

    out = VAULT / "radar" / f"{data}.md"
    out.write_text("\n".join(testo), encoding="utf-8")
    print(f"{len(rilevanti)} rilevanti, {len(scartati)} scartate, scritte in {out}")


if __name__ == "__main__":
    main()

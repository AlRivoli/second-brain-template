#!/usr/bin/env python3
"""Disegna l'immagine di una bozza: legge la riga `Immagine: titolo | riga | riga ...` e la rende in PNG con Chrome.

Uso: immagine-bozza.py content/linkedin/<bozza>.md   (crea <bozza>.png accanto al file)
LinkedIn 1200x627, Instagram 1080x1350. Niente rete: il carattere è quello di sistema.
"""
import html
import json
import re
import shutil
import subprocess
import sys
import tempfile
from pathlib import Path

CHROME = "/Applications/Google Chrome.app/Contents/MacOS/Google Chrome"
ALTRI = ("google-chrome", "google-chrome-stable", "chromium", "chromium-browser", "chrome", "msedge",
         r"C:\Program Files\Google\Chrome\Application\chrome.exe", r"C:\Program Files (x86)\Google\Chrome\Application\chrome.exe",
         r"C:\Program Files (x86)\Microsoft\Edge\Application\msedge.exe")


def trova_chrome():
    """Percorso di un browser basato su Chromium (Chrome, Chromium, Edge) o None."""
    if Path(CHROME).is_file():
        return CHROME
    return next((p for p in (shutil.which(n) or (n if Path(n).is_absolute() and Path(n).is_file() else None) for n in ALTRI) if p), None)
MISURE = {"linkedin": (1200, 627), "instagram": (1080, 1350)}
RIGA = re.compile(r"^\[?Immagine:\s*(.+?)\]?\s*$", re.M)

MODELLO = """<!doctype html><meta charset="utf-8"><style>
html,body{{margin:0;width:{w}px;height:{h}px}}
body{{background:#f2f4f7;color:#101a2b;font-family:-apple-system,"Helvetica Neue",Arial,sans-serif;display:flex;flex-direction:column;justify-content:space-between;padding:{pad}px;box-sizing:border-box}}
h1{{font-size:{tit}px;line-height:1.08;letter-spacing:-0.025em;font-weight:700;margin:0;max-width:{larg}px}}
ul{{list-style:none;margin:0;padding:0;display:grid;gap:{gap}px}}
li{{font-size:{txt}px;line-height:1.25;border-left:6px solid #2447f5;padding-left:22px;max-width:{larg}px}}
li b{{font-weight:700}}
footer{{font-size:{pie}px;color:#5b6678}}
</style><h1>{titolo}</h1><ul>{righe}</ul><footer>{firma}</footer>"""


def firma():
    """Il nome in fondo all'immagine: la chiave `nome_firma` di config.json nella radice del vault. Senza file, nessuna firma."""
    try:
        return str(json.loads((Path(__file__).resolve().parent.parent / "config.json").read_text(encoding="utf-8")).get("nome_firma", ""))
    except (OSError, ValueError):
        return ""


def spec(testo):
    m = RIGA.search(testo)
    if not m:
        return None
    parti = [p.strip() for p in m.group(1).split("|") if p.strip()]
    return (parti[0], parti[1:5]) if len(parti) > 1 else None


def disegna(bozza):
    bozza = Path(bozza)
    rete = bozza.parent.name
    w, h = MISURE[rete]
    s = spec(bozza.read_text(encoding="utf-8"))
    if not s:
        return None
    titolo, righe = s
    quadro = rete == "instagram"
    voci = "".join("<li>%s</li>" % html.escape(r) for r in righe)
    pagina = MODELLO.format(w=w, h=h, pad=72 if not quadro else 80, tit=64 if not quadro else 84, txt=30 if not quadro else 40,
                            gap=22 if not quadro else 30, pie=22, larg=w - 2 * (72 if not quadro else 80), titolo=html.escape(titolo), righe=voci, firma=html.escape(firma()))
    out = bozza.with_suffix(".png")
    with tempfile.TemporaryDirectory() as d:
        sorgente = Path(d) / "i.html"
        sorgente.write_text(pagina, encoding="utf-8")
        chrome = trova_chrome()
        if not chrome:
            raise RuntimeError("nessun Chrome, Chromium o Edge trovato: l'immagine non si disegna")
        subprocess.run([chrome, "--headless=new", "--disable-gpu", "--hide-scrollbars", "--force-device-scale-factor=1",
                        "--screenshot=%s" % out, "--window-size=%d,%d" % (w, h), sorgente.as_uri()],
                       check=True, capture_output=True, timeout=60)
    return out


if __name__ == "__main__":
    for percorso in sys.argv[1:]:
        try:
            r = disegna(percorso)
        except RuntimeError as e:
            sys.exit(str(e))
        print(r if r else "%s: nessuna riga Immagine" % percorso)

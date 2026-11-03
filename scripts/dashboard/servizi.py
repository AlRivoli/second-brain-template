"""Scheda Servizi: legge docs/servizi.md.

Una sezione `##` per progetto. Sotto, la tabella dei servizi e, con un titolo `###`, le tabelle delle misure,
dei costi e dei collegamenti. I numeri delle misure sono numeri semplici (punto decimale).
"""
from pathlib import Path

SEZIONI = {"misure": "misure", "costi": "costi", "collegamenti": "collegamenti", "piani": "piani"}


def servizi(file):
    """Lista di {progetto, servizi, misure, costi, collegamenti, note}, dalle tabelle Markdown del file."""
    out, corrente, colonne, chiave = [], None, None, "servizi"
    try:
        righe = Path(file).read_text(encoding="utf-8").splitlines()
    except OSError:  # un vault nuovo non ha ancora docs/servizi.md
        return out
    for riga in righe:
        if riga.startswith("## "):
            corrente = {"progetto": riga[3:].strip(), "servizi": [], "misure": [], "costi": [], "collegamenti": [], "piani": []}
            out.append(corrente)
            colonne, chiave = None, "servizi"
        elif riga.startswith("### ") and corrente is not None:
            colonne, chiave = None, SEZIONI.get(riga[4:].strip().lower(), "servizi")
        elif corrente is not None and riga.startswith("|"):
            celle = [c.strip() for c in riga.strip().strip("|").split("|")]
            if colonne is None:
                colonne = celle
            elif not set("".join(celle)) <= set("-: "):
                corrente[chiave].append(dict(zip(colonne, celle)))
        elif corrente is not None and chiave == "servizi" and colonne is not None and riga.strip():
            corrente.setdefault("note", []).append(riga.strip())
    return out


def aggiorna_misura(file, progetto, servizio, misura, usato, oggi):
    """Cambia «Usato» e «Misurato» di una riga della tabella Misure di un progetto, e solo quelli. LookupError se la riga non c'è."""
    try:
        valore = float(str(usato).replace(",", "."))
    except ValueError:
        raise ValueError("usato")
    if not 0 <= valore < 1e12:
        raise ValueError("usato")
    righe = Path(file).read_text(encoding="utf-8").split("\n")
    nel_progetto = nella_tabella = False
    colonne = None
    for i, riga in enumerate(righe):
        if riga.startswith("## "):
            nel_progetto, nella_tabella, colonne = riga[3:].strip() == progetto, False, None
        elif riga.startswith("### "):
            nella_tabella, colonne = nel_progetto and riga[4:].strip().lower() == "misure", None
        elif nella_tabella and riga.startswith("|"):
            celle = [c.strip() for c in riga.strip().strip("|").split("|")]
            if colonne is None:
                colonne = celle
            elif celle[colonne.index("Servizio")] == servizio and celle[colonne.index("Misura")] == misura:
                celle[colonne.index("Usato")] = ("%g" % valore)
                celle[colonne.index("Misurato")] = oggi
                righe[i] = "| " + " | ".join(celle) + " |"
                Path(file).write_text("\n".join(righe), encoding="utf-8")
                return
    raise LookupError(misura)

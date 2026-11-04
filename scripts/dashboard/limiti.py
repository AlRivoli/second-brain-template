"""Limiti e costi: proiezione a fine periodo, verdetto per misura e per servizio, spesa mensile.

Una sola misura per riga: la proiezione è lineare (ritmo medio del periodo fino alla data di misura) e va letta come una stima.
"""
import calendar
import re
from datetime import date, datetime, timedelta

SOGLIA_PREVISTO = 0.9   # «da guardare» se il previsto supera il 90% della soglia
GIORNI_VECCHIA = 7
ORDINE = {"ok": 0, "guarda": 1, "passa": 2}
ETICHETTA = {"ok": "resta gratis", "guarda": "da guardare", "passa": "valuta il piano a pagamento"}


def numero(testo, predefinito=None):
    try:
        return float(str(testo).replace(",", "."))
    except ValueError:
        return predefinito


def analizza(misura, oggi):
    """Una misura di docs/servizi.md (dizionario delle colonne) con proiezione e verdetto."""
    usato, limite = numero(misura["Usato"]), numero(misura["Limite"])
    soglia = numero(misura.get("Agire a", ""), None) or limite * 0.7
    periodo = (misura.get("Periodo") or "totale").lower()
    misurato = datetime.strptime(misura["Misurato"][:10], "%Y-%m-%d").date()
    out = {"servizio": misura["Servizio"], "misura": misura["Misura"], "unita": misura.get("Unità", ""), "usato": usato, "limite": limite,
           "soglia": soglia, "periodo": periodo, "misurato": misura["Misurato"][:10], "previsto": None, "esaurimento": None,
           "vecchia": (oggi - misurato).days > GIORNI_VECCHIA}
    if periodo == "mese":
        giorni_mese = calendar.monthrange(misurato.year, misurato.month)[1]
        ritmo = usato / misurato.day
        out["previsto"] = ritmo * giorni_mese
        if ritmo > 0 and out["previsto"] >= limite:
            out["esaurimento"] = (misurato.replace(day=1) + timedelta(days=int(limite / ritmo))).isoformat()
        valore = out["previsto"]
    else:
        valore = usato
    if valore >= limite:
        out["verdetto"] = "passa"
    elif valore >= soglia * SOGLIA_PREVISTO:
        out["verdetto"] = "guarda"
    else:
        out["verdetto"] = "ok"
    out["motivo"] = _motivo(out)
    return out


def _motivo(m):
    f = lambda v: "{:,.1f}".format(v).rstrip("0").rstrip(".").replace(",", "\x00").replace(".", ",").replace("\x00", ".")
    if m["periodo"] == "mese":
        base = "A questo ritmo arrivi a %s %s a fine mese (limite %s)" % (f(m["previsto"]), m["unita"], f(m["limite"]))
        return base + (", finisci il %s" % m["esaurimento"] if m["esaurimento"] else "")
    return "%s %s su %s, soglia %s" % (f(m["usato"]), m["unita"], f(m["limite"]), f(m["soglia"]))


def verdetto_servizio(misure):
    """Il peggiore dei verdetti delle misure di un servizio."""
    return max((m["verdetto"] for m in misure), key=ORDINE.get, default="ok")


def spesa_mensile(costi):
    """Costo fisso al mese per valuta, dai rinnovi annuali («2027-10-09, 15 $»): importo diviso 12."""
    somme = {}
    for c in costi:
        m = re.search(r"([\d.,]+)\s*(\S+)\s*$", c.get("Rinnovo", "")[10:])
        if m:
            somme[m.group(2)] = somme.get(m.group(2), 0) + numero(m.group(1), 0) / 12
    return somme


def salto_di_piano(piani, verdetti):
    """Costo mensile in più per valuta se si passa ai piani a pagamento dei servizi con verdetto «passa»."""
    somme = {}
    for p in piani:
        if verdetti.get(p.get("Servizio")) == "passa" and numero(p.get("Costo", ""), None) is not None:
            somme[p["Valuta"]] = somme.get(p["Valuta"], 0) + numero(p["Costo"])
    return somme

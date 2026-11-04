#!/usr/bin/env python3
"""First-run wizard for the second brain. Standard library only; works on macOS, Linux and Windows.

Usage:
    python3 setup.py                        (Windows: py -3 setup.py) asks a few questions, one module at a time
    python3 setup.py --add riservata        add a module later, without touching what you already have
    python3 setup.py --answers answers.json --yes     no questions: answers from a file (for repeat installs and tests)
    python3 setup.py --list                 the modules and what each one does
    python3 setup.py --clean-example        remove the example project once you have your own
    python3 setup.py --dry-run              show what it would do, change nothing

Modules live in modules/<id>/module.json. The wizard shows a summary of every change and waits for your yes before it writes anything.
It never overwrites a file that already exists.
"""
import argparse
import importlib.util
import json
import re
import shutil
import sys
from pathlib import Path

import moduli

RADICE = Path(__file__).resolve().parent

MESSAGGI = {
    "en": {
        "language": "Language for the wizard and the agent's replies (en/it)", "yes_no": "[y/N]", "yes_no_default_yes": "[Y/n]",
        "would": "would do", "done_one": "done", "removed": "removed",
        "no_example": "the example project is not there (already removed)",
        "summary": "This is what will happen:", "confirm": "Go ahead?", "aborted": "Nothing was changed.",
        "done": "Done. Next: python3 doctor.py (Windows: py -3 doctor.py), then open GETTING_STARTED.md.",
        "bad_lang": "language must be en or it", "needs": "needs the module %s first (run: python3 setup.py --add %s)",
        "unknown_module": "unknown module: %s", "invalid": "not accepted: %s", "not_for_os": "not available on this system",
        "add_needs_core": "run python3 setup.py first (config.json is missing)", "modules": "Modules:", "always": "always",
        "pull": "To download the model (needs Ollama installed): ollama pull %s",
        "no_claude": "You chose something that uses Claude Code, but it is not installed. python3 doctor.py shows how to install it.",
    },
    "it": {
        "language": "Lingua del wizard e delle risposte dell'agente (en/it)", "yes_no": "[s/N]", "yes_no_default_yes": "[S/n]",
        "would": "farei", "done_one": "fatto", "removed": "rimosso",
        "no_example": "il progetto d'esempio non c'è (già rimosso)",
        "summary": "Ecco cosa succederà:", "confirm": "Procedo?", "aborted": "Non è cambiato niente.",
        "done": "Fatto. Ora: python3 doctor.py (Windows: py -3 doctor.py), poi apri INIZIA.md.",
        "bad_lang": "la lingua deve essere en o it", "needs": "serve prima il modulo %s (lancia: python3 setup.py --add %s)",
        "unknown_module": "modulo sconosciuto: %s", "invalid": "non accettato: %s", "not_for_os": "non disponibile su questo sistema",
        "add_needs_core": "lancia prima python3 setup.py (manca config.json)", "modules": "Moduli:", "always": "sempre",
        "pull": "Per scaricare il modello (serve Ollama installato): ollama pull %s",
        "no_claude": "Hai scelto qualcosa che usa Claude Code, ma non è installato. python3 doctor.py mostra come installarlo.",
    },
}


def modello_mod():
    """scripts/modello.py: nel template sta in scripts/, quando si prova dentro il vault dell'autore un livello sopra."""
    for cartella in (RADICE, RADICE.parent):
        file = cartella / "scripts" / "modello.py"
        if file.exists():
            spec = importlib.util.spec_from_file_location("modello", file)
            m = importlib.util.module_from_spec(spec)
            spec.loader.exec_module(m)
            return m
    raise ValueError("scripts/modello.py not found")


def domanda(testo, predefinito=""):
    risposta = input("%s%s: " % (testo, " [%s]" % predefinito if predefinito else "")).strip()
    return risposta or predefinito


def si_no(testo, msg, predefinito=False):
    r = input("%s %s: " % (testo, msg["yes_no_default_yes" if predefinito else "yes_no"])).strip().lower()
    return predefinito if not r else r[0] in ("y", "s")


def una_riga(testo):
    """Una riga sola e senza spazi in fondo: certi valori finiscono in un file di istruzioni."""
    return re.sub(r"[\r\n]+", " ", str(testo)).strip()


def chiedi(m, lingua, msg, gia, interattivo=True):
    """Le risposte alle domande di un modulo: da `gia` (file di risposte), chiedendole, o col valore di fabbrica se non c'è nessuno
    a rispondere. Una risposta non valida si richiede (se viene da un file, è un errore)."""
    risposte = {}
    for d in m.get("domande", []):
        while True:
            if d["id"] in gia:
                valore = gia[d["id"]]
            elif not interattivo:
                valore = predefinito(d)
            elif d.get("validazione") == "modello" and interattivo and not d.get("_mostrata"):
                d["_mostrata"] = True
                if not d.get("solo"):  # il consiglio sulla RAM riguarda il modello che ragiona, non quello degli embedding
                    try:
                        print("  " + modello_mod().consiglia(modello_mod().ram_gb())["testo"])
                    except ValueError:
                        pass
                if d.get("avviso"):
                    print("  " + moduli.testo(d["avviso"], lingua))
                valore = domanda(moduli.testo(d["testo"], lingua), str(d.get("predefinito", "none")))
            elif d["tipo"] == "si_no":
                valore = si_no(moduli.testo(d["testo"], lingua), msg, bool(d.get("predefinito")))
            else:
                scelte = " (%s)" % " / ".join(d["opzioni"]) if d.get("opzioni") else ""
                if d.get("avviso") and not d.get("_mostrata"):
                    d["_mostrata"] = True
                    print("  " + moduli.testo(d["avviso"], lingua))
                valore = domanda(moduli.testo(d["testo"], lingua) + scelte, str(predefinito(d)))
            try:
                risposte[d["id"]] = verifica(d, valore)
                break
            except ValueError as e:
                print("  " + msg["invalid"] % e)
                if d["id"] in gia:
                    raise
    return risposte


URL_HTTP = re.compile(r"https?://[^\s,]+")


def predefinito(d):
    """Il valore di fabbrica; `predefinito_os` ({sys.platform: valore}) lo cambia secondo il sistema."""
    return d.get("predefinito_os", {}).get(sys.platform, d.get("predefinito", ""))


def verifica(d, valore):
    if d.get("validazione") == "cartella":
        return moduli.valida_cartella(str(valore))
    if d.get("validazione") == "modello":
        # «claude», «none» o «ollama:<nome>»; `solo` restringe (l'embedding non può essere Claude)
        valore = una_riga(valore) or "none"
        provider, _, nome = valore.partition(":")
        if provider not in d.get("solo", ["none", "claude", "ollama"]) or (provider == "ollama" and not nome) or (provider != "ollama" and nome):
            raise ValueError("%s: use %s" % (valore, ", ".join(p if p != "ollama" else "ollama:<model>" for p in d.get("solo", ["none", "claude", "ollama"]))))
        if provider == "ollama":
            modello_mod().valida_nome(nome)
        return valore
    if d.get("validazione") == "url":
        voci = valore if isinstance(valore, list) else [v for v in re.split(r"[\s,]+", str(valore)) if v]
        if not all(isinstance(v, str) and URL_HTTP.fullmatch(v) for v in voci):
            raise ValueError("only http and https addresses")
        return list(voci)
    if d.get("lista"):
        voci = valore if isinstance(valore, list) else re.split(r"[,\n]", str(valore))
        return [una_riga(v) for v in voci if una_riga(v)]
    if d["tipo"] == "scelta" and valore not in d.get("opzioni", [valore]):
        raise ValueError("%s: choose one of %s" % (valore, ", ".join(d["opzioni"])))
    if valore in d.get("solo_os", {}) and sys.platform not in d["solo_os"][valore]:  # es. il Calendario di macOS solo su macOS
        raise ValueError("%s: %s" % (valore, MESSAGGI["en"]["not_for_os"]))
    return una_riga(valore) if isinstance(valore, str) else valore


def raccogli(tutti, lingua, msg, risposte_file, solo=None, interattivo=True):
    """{id modulo: risposte} dei moduli attivi, in ordine di dipendenza. `solo`: un solo modulo (--add)."""
    attivi = {}
    for i, m in tutti.items():
        if solo and i != solo and i != "core":
            continue
        gia = (risposte_file.get("moduli", {}).get(i, {}) if i != "core" else risposte_file)
        if i == "core":
            if solo:
                continue
            attivi[i] = chiedi(m, lingua, msg, {k: v for k, v in gia.items() if k in ("nome", "ruolo")}, interattivo)
            continue
        if not m.get("sempre"):
            if solo == i:
                attivo = True
            elif "attivo" in gia:
                attivo = bool(gia["attivo"])
            elif interattivo:
                print("\n%s: %s" % (moduli.testo(m["titolo"], lingua), moduli.testo(m["descrizione"], lingua)))
                attivo = si_no(moduli.testo(m["domanda_attivazione"], lingua), msg)
            else:
                attivo = False
            if not attivo:
                continue
        for d in m.get("richiede", []):
            if d not in attivi and d != "core" and not solo:
                raise ValueError(msg["needs"] % (d, d))
        attivi[i] = chiedi(m, lingua, msg, gia, interattivo)
    return attivi


def installa(nome, ruolo, lingua, msg, dry=False, radice=RADICE):
    """Il modulo core con nome e ruolo dati: config.json, memory/*.md e CLAUDE.md. Non sovrascrive niente."""
    tutti = moduli.carica(radice)
    for a in moduli.azioni_di(tutti["core"], {"nome": nome, "ruolo": ruolo}, lingua):
        print("  %s: %s" % (msg["would" if dry else "done_one"], moduli.descrivi(a, lingua)))
        moduli.applica(a, radice, dry=dry)


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
    servizi = radice / "docs" / "servizi.md"
    if servizi.exists():  # anche la sezione d'esempio della tabella dei servizi
        testo = re.sub(r"^## example-project\n.*?(?=^## |\Z)", "", servizi.read_text(encoding="utf-8"), flags=re.S | re.M)
        servizi.write_text(testo.rstrip() + "\n", encoding="utf-8")


def main(argv=None, radice=RADICE):
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--name")
    ap.add_argument("--role")
    ap.add_argument("--language")
    ap.add_argument("--yes", action="store_true", help="do not ask: use the answers file, the options and the defaults")
    ap.add_argument("--answers", help="JSON file with the answers")
    ap.add_argument("--add", metavar="MODULE")
    ap.add_argument("--list", action="store_true")
    ap.add_argument("--clean-example", action="store_true")
    ap.add_argument("--dry-run", action="store_true")
    a = ap.parse_args(argv)
    file_risposte = json.loads(Path(a.answers).read_text(encoding="utf-8")) if a.answers else {}
    lingua = (a.language or file_risposte.get("lingua") or "en").lower()
    if lingua not in MESSAGGI:
        sys.exit(MESSAGGI["en"]["bad_lang"])
    msg = MESSAGGI[lingua]
    if a.clean_example:
        pulisci_esempio(msg, a.dry_run, radice)
        return 0
    tutti = moduli.carica(radice)
    if a.list:
        print(msg["modules"])
        for i, m in tutti.items():
            print("  %-10s %s%s" % (i, moduli.testo(m["titolo"], lingua), " (%s)" % msg["always"] if m.get("sempre") else ""))
            print("             " + moduli.testo(m["descrizione"], lingua))
        return 0
    interattivo = not (a.yes or a.answers)
    if a.add and a.add not in tutti:
        sys.exit(msg["unknown_module"] % a.add)
    if a.add and not (radice / "config.json").exists():
        sys.exit(msg["add_needs_core"])
    if interattivo and not a.language:
        lingua = domanda(msg["language"], lingua).lower()
        if lingua not in MESSAGGI:
            sys.exit(MESSAGGI["en"]["bad_lang"])
        msg = MESSAGGI[lingua]
    gia = {**file_risposte, **({"nome": a.name} if a.name is not None else {}), **({"ruolo": a.role} if a.role is not None else {})}
    try:
        attivi = raccogli(tutti, lingua, msg, gia, solo=a.add, interattivo=interattivo)
    except ValueError as e:
        sys.exit(str(e))
    azioni = []
    for i, risposte in attivi.items():
        nome_core = attivi.get("core", {}).get("nome")
        if i == "core" and not nome_core:
            risposte["nome"] = risposte.get("nome") or "<your name>"
        azioni += [(i, x) for x in moduli.azioni_di(tutti[i], risposte, lingua)]
    print("\n" + msg["summary"])
    for i, x in azioni:
        print("  [%s] %s" % (i, moduli.descrivi(x, lingua)))
    if a.dry_run:
        return 0
    if interattivo and not si_no(msg["confirm"], msg, True):
        print(msg["aborted"])
        return 1
    try:
        for i, x in azioni:
            moduli.applica(x, radice)
    except ValueError as e:
        sys.exit(str(e))
    for risposte in attivi.values():
        for v in risposte.values():
            if isinstance(v, str) and v.startswith("ollama:"):
                print(msg["pull"] % v[len("ollama:"):])
    usa_claude = "bozze" in attivi or any(v == "claude" for r in attivi.values() for v in r.values())
    if usa_claude and shutil.which("claude") is None:
        print(msg["no_claude"])
    print(msg["done"])
    return 0


if __name__ == "__main__":
    sys.exit(main())

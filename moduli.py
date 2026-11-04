"""Modules of the second brain: manifests, questions and declarative actions. Standard library only.

A module is a folder `modules/<id>/module.json`. It declares its questions and a list of actions. The actions are a fixed set
(see AZIONI): a manifest cannot run code, it can only ask this file to do one of these things.
Used by setup.py; has no side effects until `applica` is called.
"""
import json
import re
import time
from pathlib import Path

RADICE = Path(__file__).resolve().parent
AZIONI = {"config_set", "da_esempi", "claude_md", "crea_cartella", "gitignore", "deny", "scrivi_file"}
TIPI_DOMANDA = {"testo", "si_no", "scelta"}
# Nomi che non si accettano per la cartella riservata: la regola `deny` su Bash blocca ogni comando che contiene il nome.
GENERICI = {"docs", "projects", "scripts", "memory", "content", "daily", "inbox", "radar", "templates", "template", "tests", "modules",
            "notes", "note", "src", "code", "test", "work", "data", "files", "temp", "tmp"}
RADICI_DEL_SISTEMA = {"docs", "scripts", "memory", "content", "daily", "inbox", "radar", "templates", "tests", "modules", ".claude", ".obsidian", ".github"}

MESSAGGI = {
    "en": {"config_set": "update config.json", "da_esempi": "create {cartella}/*.md from the *.example.md files (never overwrites)",
           "claude_md": "write your name in CLAUDE.md", "crea_cartella": "create the folder {percorso}",
           "gitignore": "add \"{riga}\" to .gitignore", "scrivi_file": "write {percorso} (never overwrites)", "deny": "block Claude Code from reading and editing {cartella} (rules in .claude/settings.json)"},
    "it": {"config_set": "aggiorno config.json", "da_esempi": "creo {cartella}/*.md dai file *.example.md (non sovrascrivo mai)",
           "claude_md": "scrivo il tuo nome in CLAUDE.md", "crea_cartella": "creo la cartella {percorso}",
           "gitignore": "aggiungo «{riga}» a .gitignore", "scrivi_file": "scrivo {percorso} (non sovrascrivo mai)", "deny": "vieto a Claude Code di leggere e modificare {cartella} (regole in .claude/settings.json)"},
}


def testo(campo, lingua):
    """Un campo testuale di un manifest: una stringa o un dizionario {lingua: testo}; l'inglese è il ripiego."""
    if isinstance(campo, dict):
        return campo.get(lingua) or campo.get("en") or next(iter(campo.values()), "")
    return str(campo)


def errori_manifest(m, ids):
    """Lista di errori di un manifest (vuota se è valido). `ids` sono gli id di tutti i moduli, per le dipendenze."""
    errori = []
    for chiave in ("id", "titolo", "descrizione", "azioni"):
        if chiave not in m:
            errori.append("manca «%s»" % chiave)
    if not re.fullmatch(r"[a-z][a-z0-9_-]*", str(m.get("id", ""))):
        errori.append("id non valido")
    if not m.get("sempre") and "domanda_attivazione" not in m:
        errori.append("un modulo facoltativo ha bisogno di «domanda_attivazione»")
    for dipendenza in m.get("richiede", []):
        if dipendenza not in ids:
            errori.append("richiede un modulo che non esiste: %s" % dipendenza)
    for d in m.get("domande", []):
        if d.get("tipo") not in TIPI_DOMANDA or "id" not in d or "testo" not in d:
            errori.append("domanda non valida: %s" % d.get("id", "?"))
    for a in m.get("azioni", []):
        if a.get("tipo") not in AZIONI:
            errori.append("azione non ammessa: %s" % a.get("tipo"))
    return errori


def carica(radice=RADICE):
    """{id: manifest}, in un ordine che rispetta le dipendenze (core per primo). Un manifest non valido solleva ValueError."""
    trovati = {}
    for file in sorted(Path(radice, "modules").glob("*/module.json")):
        m = json.loads(file.read_text(encoding="utf-8"))
        if m.get("id") != file.parent.name:
            raise ValueError("%s: l'id deve essere il nome della cartella" % file)
        trovati[m["id"]] = m
    for m in trovati.values():
        problemi = errori_manifest(m, set(trovati))
        if problemi:
            raise ValueError("modulo %s: %s" % (m["id"], "; ".join(problemi)))
    ordinati, visti = [], set()

    def visita(i, percorso=()):
        if i in visti:
            return
        if i in percorso:
            raise ValueError("dipendenze circolari: %s" % " -> ".join(percorso + (i,)))
        for d in trovati[i].get("richiede", []):
            visita(d, percorso + (i,))
        visti.add(i)
        ordinati.append(i)

    for i in sorted(trovati, key=lambda x: (x != "core", x)):
        visita(i)
    return {i: trovati[i] for i in ordinati}


def valida_cartella(nome):
    """Percorso normalizzato (relativo, con /) di una cartella dentro il vault, o ValueError con il motivo."""
    n = nome.strip().replace("\\", "/")
    if n.startswith("/") or n.startswith("~"):
        raise ValueError("write a path inside the vault, not an absolute one")
    n = n.strip("/")
    if not n:
        raise ValueError("empty name")
    if re.search(r"[^A-Za-z0-9._/-]", n):
        raise ValueError("only letters, digits and . _ - / are allowed")
    parti = n.split("/")
    if any(p in ("", ".", "..") or p.lower().startswith(".git") for p in parti):
        raise ValueError("the folder must be inside the vault and not a git folder")
    if len(parti) == 1 and parti[0].lower() in RADICI_DEL_SISTEMA:
        raise ValueError("%s is a folder of the system" % parti[0])
    base = parti[-1]
    if len(base) < 5 or base.lower() in GENERICI:
        raise ValueError("too generic (the block on shell commands would stop every command that contains %r): use a longer, specific name" % base)
    return "/".join(parti)


def regole_deny(cartella):
    base = cartella.split("/")[-1]
    return ["Read(/%s/**)" % cartella, "Edit(/%s/**)" % cartella, "Bash(*%s*)" % base]


def _percorso_interno(nome):
    """Percorso relativo dentro il vault per scrivi_file: niente assoluti, `..`, cartelle git o di configurazione di Claude Code."""
    n = nome.replace("\\", "/")
    parti = n.split("/")
    if n.startswith(("/", "~")) or any(p in ("", ".", "..") or p.lower().startswith(".git") or p == ".claude" for p in parti) or re.search(r"[^A-Za-z0-9._/-]", n):
        raise ValueError("path not allowed: %r" % nome)
    return n


def _sostituisci(x, valori):
    if isinstance(x, str):
        if x.startswith("{") and x.endswith("}") and isinstance(valori.get(x[1:-1]), bool):
            return valori[x[1:-1]]  # un sì/no resta un booleano nel JSON
        for k, v in valori.items():
            x = x.replace("{%s}" % k, str(v))
        return x
    if isinstance(x, list):
        return [_sostituisci(i, valori) for i in x]
    if isinstance(x, dict):
        return {k: _sostituisci(v, valori) for k, v in x.items()}
    return x


def azioni_di(m, risposte, lingua):
    """Le azioni di un modulo con i segnaposto risolti (risposte alle sue domande, lingua, fuso)."""
    # una risposta a più voci (lista) diventa un elenco puntato nei file di testo
    valori = {"lingua": lingua, "fuso": time.tzname[0], **{k: ("\n".join("- %s" % x for x in v) if isinstance(v, list) else v) for k, v in risposte.items()}}
    return [_sostituisci(a, valori) for a in m["azioni"]]


def descrivi(azione, lingua):
    modello = MESSAGGI.get(lingua, MESSAGGI["en"])[azione["tipo"]]
    return modello.format(**{k: v for k, v in azione.items() if isinstance(v, str)}) if "{" in modello else modello


def _unisci(base, nuovo, forza):
    for k, v in nuovo.items():
        if isinstance(v, dict) and isinstance(base.get(k), dict):
            _unisci(base[k], v, forza)
        elif k not in base or forza:
            base[k] = v


def _leggi_json(file):
    try:
        return json.loads(file.read_text(encoding="utf-8"))
    except FileNotFoundError:
        return {}


def applica(azione, radice, dry=False):
    """Esegue un'azione. Non sovrascrive mai un file di testo esistente; config_set tiene i valori già presenti (salvo forza)."""
    radice = Path(radice)
    tipo = azione["tipo"]
    if dry:
        return
    if tipo == "config_set":
        file = radice / "config.json"
        cfg = _leggi_json(file)
        _unisci(cfg, azione["valori"], bool(azione.get("forza")))
        file.write_text(json.dumps(cfg, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    elif tipo == "da_esempi":
        cfg = _leggi_json(radice / "config.json")
        for esempio in sorted((radice / azione["cartella"]).glob("*.example.md")):
            if esempio.name.replace(".example.md", "") in azione.get("salvo", []):
                continue  # lo crea un modulo, con le risposte dell'utente
            dest = esempio.with_name(esempio.name.replace(".example", ""))
            if not dest.exists():
                dest.write_text(esempio.read_text(encoding="utf-8").replace("<your name>", (cfg.get("nome") or "<your name>"))
                                .replace("<your role>", cfg.get("ruolo", "")), encoding="utf-8")
    elif tipo == "claude_md":
        file, cfg = radice / "CLAUDE.md", _leggi_json(radice / "config.json")
        if file.exists():
            t = file.read_text(encoding="utf-8")
            nome_, ruolo_ = cfg.get("nome") or "<your name>", cfg.get("ruolo", "")
            t = t.replace("<your name>, <your role>", ", ".join(x for x in (nome_, ruolo_) if x)).replace("<your name>", nome_)
            file.write_text(t, encoding="utf-8")
    elif tipo == "crea_cartella":
        (radice / (_percorso_interno(azione["percorso"]) if azione.get("sistema") else valida_cartella(azione["percorso"]))).mkdir(parents=True, exist_ok=True)
    elif tipo == "scrivi_file":
        percorso = _percorso_interno(azione["percorso"])
        if not (radice / percorso).exists():
            (radice / percorso).parent.mkdir(parents=True, exist_ok=True)
            (radice / percorso).write_text(azione["contenuto"], encoding="utf-8")
    elif tipo == "gitignore":
        file = radice / ".gitignore"
        righe = file.read_text(encoding="utf-8").splitlines() if file.exists() else []
        if azione["riga"] not in righe:
            file.write_text("\n".join(righe + [azione["riga"]]) + "\n", encoding="utf-8")
    elif tipo == "deny":
        file = radice / ".claude" / "settings.json"
        try:
            dati = _leggi_json(file)
        except ValueError:
            raise ValueError("%s is not valid JSON: fix it by hand, the wizard will not overwrite it" % file)
        deny = dati.setdefault("permissions", {}).setdefault("deny", [])
        deny += [r for r in regole_deny(valida_cartella(azione["cartella"])) if r not in deny]
        file.parent.mkdir(parents=True, exist_ok=True)
        file.write_text(json.dumps(dati, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")

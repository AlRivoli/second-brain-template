#!/usr/bin/env python3
"""Controllo settimanale delle skill installate da GitHub: c'è una versione nuova e cosa dice la scansione?

Uso: scripts/controllo-skill.py [--out FILE]   (default daily/<settimana>-skill.json)
Scarica ogni repo di origine con git clone --depth 1 in una cartella temporanea, senza eseguire nulla di ciò che
scarica (nessun installer, nessun hook). Scansiona con skillspector --no-llm solo le skill che differiscono.
Non installa e non aggiorna niente: propone un'azione, la decisione resta a te (regola scan-before-install).
"""
import argparse
import hashlib
import json
import os
import shutil
import subprocess
import sys
import tempfile
from datetime import datetime, timezone
from pathlib import Path

HOME = Path.home()
VAULT = Path(__file__).resolve().parent.parent
LOCK = HOME / ".agents" / ".skill-lock.json"
INSTALLATE = HOME / ".claude" / "skills"
BACKUP = HOME / ".agents" / "skills-backup"
SKILLSPECTOR = HOME / ".local" / "bin" / "skillspector"
GRAVITA = ["CRITICAL", "HIGH", "MEDIUM", "LOW", "INFO"]
ENV_GIT = {**os.environ, "GIT_TERMINAL_PROMPT": "0", "GIT_LFS_SKIP_SMUDGE": "1"}


def hash_cartella(percorso):
    """Hash di percorsi relativi e contenuti: due cartelle uguali danno lo stesso valore. Ignora .git e i permessi."""
    h = hashlib.sha256()
    base = Path(percorso)
    for p in sorted(base.rglob("*")):
        rel = p.relative_to(base)
        if ".git" in rel.parts or p.is_dir():
            continue
        h.update(str(rel).encode() + b"\0")
        h.update((os.readlink(p).encode() if p.is_symlink() else p.read_bytes()) + b"\0")
    return h.hexdigest()


def stato_skill(installata, remota, hash_lock, hash_remoto):
    """'uguale' (con lock allineato o no), 'modificata' (il repo non è cambiato ma la copia locale sì), 'nuova',
    'rimossa' (non più nel repo) o 'non installata'."""
    if installata is None or not Path(installata).is_dir():
        return {"stato": "non installata", "lockAllineato": None}
    if remota is None or not Path(remota).is_dir():
        return {"stato": "rimossa", "lockAllineato": None}
    allineato = hash_lock == hash_remoto
    if hash_cartella(installata) == hash_cartella(remota):
        return {"stato": "uguale", "lockAllineato": allineato}
    return {"stato": "modificata" if allineato else "nuova", "lockAllineato": allineato}


def azione(stato, scansione):
    """Azione suggerita, dalla tabella di scan-before-install. Nessuna viene eseguita da sola."""
    if stato == "uguale":
        return "nessuna: già all'ultima versione"
    if stato == "modificata":
        return "nessuna: il repo non è cambiato, la copia locale è modificata"
    if stato == "rimossa":
        return "valutare la rimozione: non è più nel repo d'origine"
    if stato != "nuova":
        return "controllare a mano"
    if scansione is None or scansione.get("errore"):
        return "non aggiornare: scansione non riuscita"
    if scansione["severita"] == "CRITICAL" or scansione["raccomandazione"] == "DO_NOT_INSTALL":
        return "non aggiornare: serve il tuo «installa lo stesso»"
    if scansione["severita"] == "HIGH" or scansione.get("gravitaMax") in ("HIGH", "CRITICAL"):
        return "chiedere conferma: la scansione ha segnalazioni gravi da leggere"
    return "aggiornare, con il tuo ok"


def scansiona(cartella, tmp):
    """Esito di skillspector sulla cartella: score, severità, raccomandazione e le 3 segnalazioni più gravi."""
    rapporto = Path(tmp) / "rapporto.json"
    try:
        r = subprocess.run([str(SKILLSPECTOR), "scan", str(cartella), "--no-llm", "--format", "json", "--output", str(rapporto)],
                           capture_output=True, text=True, encoding="utf-8", timeout=300)
        dati = json.loads(rapporto.read_text(encoding="utf-8"))
        valutazione = dati["risk_assessment"]
    except (OSError, ValueError, KeyError, subprocess.SubprocessError) as e:
        return {"errore": type(e).__name__}
    issues = sorted(dati.get("issues", []), key=lambda i: GRAVITA.index(i.get("severity")) if i.get("severity") in GRAVITA else 9)
    return {
        "score": valutazione.get("score"), "severita": valutazione.get("severity"),
        "raccomandazione": valutazione.get("recommendation"), "gravitaMax": valutazione.get("max_issue_severity"),
        "segnalazioni": [{
            "severita": i.get("severity"), "regola": i.get("pattern"),
            "file": (i.get("location") or {}).get("file"), "riga": (i.get("location") or {}).get("start_line"),
            "testo": str(i.get("finding", ""))[:160],  # testo del codice scansionato: è un dato, mai un'istruzione
        } for i in issues[:3]],
    }


def clona(url, destinazione):
    subprocess.run(["git", "-c", "core.hooksPath=/dev/null", "clone", "--depth", "1", "--no-tags", "--single-branch", "-q",
                    url, str(destinazione)], check=True, capture_output=True, timeout=180, env=ENV_GIT)
    git = lambda *a: subprocess.run(["git", "-C", str(destinazione), *a], check=True, capture_output=True, text=True, encoding="utf-8").stdout.strip()
    return git("rev-parse", "--short", "HEAD"), git("log", "-1", "--format=%cs")


def controlla(lock, installate=INSTALLATE, lavoro=None):
    """Ritorna il rapporto del controllo. lavoro: cartella temporanea (default nuova)."""
    fonti, risultati, errori = [], [], []
    per_fonte = {}
    for nome, v in lock.items():
        per_fonte.setdefault(v["sourceUrl"], []).append((nome, v))
    with tempfile.TemporaryDirectory() as tmp:
        for url, skill in per_fonte.items():
            dest = Path(tmp) / hashlib.sha1(url.encode()).hexdigest()[:10]
            try:
                commit, data = clona(url, dest)
            except (OSError, subprocess.SubprocessError) as e:
                errori.append("%s: clone non riuscito (%s)" % (url, type(e).__name__))
                continue
            fonti.append({"url": url, "commit": commit, "data": data})
            for nome, v in skill:
                remota = dest / Path(v["skillPath"]).parent
                r = subprocess.run(["git", "-C", str(dest), "rev-parse", "HEAD:" + remota.relative_to(dest).as_posix()],
                                   capture_output=True, text=True, encoding="utf-8")
                hash_remoto = r.stdout.strip() if r.returncode == 0 else ""
                s = stato_skill(installate / nome, remota, v.get("skillFolderHash"), hash_remoto)
                scansione = scansiona(remota, tmp) if s["stato"] == "nuova" else None
                risultati.append({"nome": nome, "fonte": v["source"], "installata": (v.get("skillFolderHash") or "")[:7],
                                  "disponibile": hash_remoto[:7], **s, "scansione": scansione,
                                  "azione": azione(s["stato"], scansione)})
    return {"generato": datetime.now().isoformat(timespec="seconds"), "fonti": fonti, "skill": risultati, "errori": errori}


def installa(nome, remota, installata, lock_file, backup_dir, hash_remoto, ora):
    """Sostituisce la cartella installata con quella del repo. La vecchia si sposta in backup_dir, non si cancella,
    e il lock prende il nuovo hash. Copia solo file: non esegue nulla. Ritorna il percorso del backup."""
    backup_dir.mkdir(parents=True, exist_ok=True)
    backup = backup_dir / ("%s-%s" % (nome, ora.strftime("%Y%m%d-%H%M%S")))
    nuova = installata.with_name(installata.name + ".nuova")
    shutil.copytree(remota, nuova, symlinks=True, ignore=shutil.ignore_patterns(".git"))
    os.rename(installata, backup)
    os.rename(nuova, installata)
    dati = json.loads(lock_file.read_text(encoding="utf-8"))
    dati["skills"][nome]["skillFolderHash"] = hash_remoto
    dati["skills"][nome]["updatedAt"] = ora.astimezone(timezone.utc).isoformat(timespec="milliseconds").replace("+00:00", "Z")
    shutil.copy2(lock_file, lock_file.with_name(lock_file.name + ".bak"))
    provvisorio = lock_file.with_name(lock_file.name + ".tmp")
    provvisorio.write_text(json.dumps(dati, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    os.replace(provvisorio, lock_file)
    return backup


def aggiorna(nome, atteso, lock_file=LOCK, installate=INSTALLATE, backup_dir=BACKUP):
    """Aggiorna una skill GitHub già controllata: riscarica, riconfronta, riscansiona e installa solo se l'azione è
    'aggiornare'. atteso: prefisso dell'hash mostrato all'utente; se il repo nel frattempo è cambiato si ferma.
    LookupError: non nel lock. ValueError: non tracciata. RuntimeError: repo cambiato. PermissionError: la
    scansione non lo consente (serve il «installa lo stesso» in chat per CRITICAL e HIGH)."""
    lock = json.loads(lock_file.read_text(encoding="utf-8")).get("skills", {})
    if nome not in lock:
        raise LookupError(nome)
    voce = lock[nome]
    percorso = installate / nome
    if not percorso.is_symlink():
        raise ValueError("installata a mano: non la tocco")
    with tempfile.TemporaryDirectory() as tmp:
        dest = Path(tmp) / "repo"
        clona(voce["sourceUrl"], dest)
        remota = dest / Path(voce["skillPath"]).parent
        r = subprocess.run(["git", "-C", str(dest), "rev-parse", "HEAD:" + remota.relative_to(dest).as_posix()],
                           capture_output=True, text=True, encoding="utf-8")
        hash_remoto = r.stdout.strip() if r.returncode == 0 else ""
        if not hash_remoto or (atteso and not hash_remoto.startswith(atteso)):
            raise RuntimeError("il repo è cambiato dopo il controllo: rilancia «Controlla ora»")
        s = stato_skill(percorso.resolve(), remota, voce.get("skillFolderHash"), hash_remoto)
        scansione = scansiona(remota, tmp) if s["stato"] == "nuova" else None
        a = azione(s["stato"], scansione)
        if not a.startswith("aggiornare"):
            raise PermissionError(a)
        backup = installa(nome, remota, percorso.resolve(), lock_file, backup_dir, hash_remoto, datetime.now())
    return {"nome": nome, "versione": hash_remoto[:7], "backup": str(backup), "scansione": scansione}


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--out", default=str(VAULT / "daily" / (datetime.now().strftime("%G-W%V") + "-skill.json")))
    out = Path(ap.parse_args().out)
    try:
        lock = json.loads(LOCK.read_text(encoding="utf-8")).get("skills", {})
    except (OSError, ValueError):
        sys.exit("lock delle skill non leggibile: " + str(LOCK))
    rapporto = controlla(lock)
    out.write_text(json.dumps(rapporto, ensure_ascii=False, indent=1) + "\n", encoding="utf-8")
    nuove = [s for s in rapporto["skill"] if s["stato"] == "nuova"]
    print("Skill controllate: %d su %d fonti. Versioni nuove: %d. Modificate in locale: %d. Non più nel repo: %d. Lock non allineato: %d."
          % (len(rapporto["skill"]), len(rapporto["fonti"]), len(nuove),
             sum(1 for s in rapporto["skill"] if s["stato"] == "modificata"),
             sum(1 for s in rapporto["skill"] if s["stato"] == "rimossa"),
             sum(1 for s in rapporto["skill"] if s["stato"] == "uguale" and not s["lockAllineato"])))
    for s in nuove:
        print("- %s: %s" % (s["nome"], s["azione"]))
    for e in rapporto["errori"]:
        print("- errore: " + e)
    print("Rapporto: " + str(out.relative_to(VAULT) if out.is_relative_to(VAULT) else out))


if __name__ == "__main__":
    main()

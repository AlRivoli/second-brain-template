#!/usr/bin/env python3
"""Chiusura della giornata senza nessuno davanti.

1) /chiudi-giornata aggiorna STATE, INDEX e decisions (senza commit, se non ha permessi).
2) Lo script lancia scripts/verify e committa in locale solo se passa. Nessun push.
"""
import subprocess
import sys
import time
from datetime import datetime
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import avviso  # noqa: E402
import percorsi  # noqa: E402

VAULT = Path(__file__).resolve().parent.parent
LOGS = percorsi.cartella_log()
LOCK_SCADUTO = 30 * 60  # un lock più vecchio di 30 minuti è di una run morta


def _lock(lock):
    try:
        if time.time() - lock.stat().st_mtime > LOCK_SCADUTO:
            lock.rmdir()
    except OSError:
        pass
    try:
        lock.mkdir()
        return True
    except FileExistsError:
        return False


def chiudi(vault=VAULT, log=LOGS / "second-brain-chiudi.log", lock=LOGS / "second-brain-chiudi.lock",
           run=subprocess.run, adesso=None, segnala=avviso.segnala):
    adesso = adesso or datetime.now()
    oggi = f"{adesso:%F}"

    def scrivi(riga):
        with open(log, "a", encoding="utf-8") as f:
            f.write(riga + "\n")

    def sporco():
        return run(["git", "status", "--porcelain"], cwd=vault, capture_output=True, text=True, encoding="utf-8").stdout.strip()

    if not _lock(lock):
        scrivi(f"{adesso:%F %T} chiusura già in corso: salto")
        return 0
    try:
        scrivi(f"=== {adesso:%F %T} ===")
        with open(log, "a", encoding="utf-8") as f:
            r = run([sys.executable, "-I", "scripts/attivita-progetti.py"], cwd=vault, stdout=subprocess.PIPE, stderr=f, text=True, encoding="utf-8")
        attivita = r.stdout.rstrip("\n")
        if not attivita and not sporco():
            scrivi("niente da aggiornare: nessun commit nuovo nei repo e vault pulito")
            return 0

        # I git di lettura e il commit sono già permessi da .claude/settings.json; qui non apro altro.
        prompt = f"/chiudi-giornata\nAttività dei repo dall'ultimo STATE:\n{attivita or 'nessuna'}"
        r = run(["claude", "--permission-mode", "dontAsk", "--allowedTools", "Read", "Write", "Edit", "Glob", "Grep", "-p", prompt],
                cwd=vault, stdout=subprocess.PIPE, stderr=subprocess.STDOUT, text=True, encoding="utf-8")
        with open(log, "a", encoding="utf-8") as f:
            f.write(r.stdout or "")
        if avviso.non_autenticato(r.stdout):  # senza claude gli STATE non sono aggiornati: non si committa il resto come "chiusura"
            scrivi("claude non autenticato: chiusura non fatta, nessun commit. Lancia /login.")
            segnala(vault, "la chiusura", adesso)
            return 0

        if not sporco():
            scrivi("nessuna modifica da committare")
            return 0

        with open(log, "a", encoding="utf-8") as f:
            ok = run([sys.executable, "-I", "scripts/verify"], cwd=vault, stdout=f, stderr=subprocess.STDOUT).returncode == 0
        if ok:
            run(["git", "add", "-A"], cwd=vault)
            with open(log, "a", encoding="utf-8") as f:  # l'hook pre-commit può rifiutare (gitleaks): il motivo resta nel log
                rc = run(["git", "commit", "-q", "-m", f"chiusura {oggi}", "-m", "Co-Authored-By: Claude Haiku 5.5 <noreply@anthropic.com>"],
                         cwd=vault, stdout=f, stderr=subprocess.STDOUT).returncode
            scrivi(f"commit: chiusura {oggi}" if rc == 0 else "commit bloccato (hook pre-commit o git): vedi sopra, il lavoro resta non committato")
        else:
            scrivi("verify non passa: nessun commit. Vedi il log e la sezione Da confermare.")
            # Nel brief di oggi, una volta sola, così non resta solo nel log.
            daily = vault / "daily" / f"{oggi}.md"
            if daily.is_file() and "chiusura non committata" not in daily.read_text(encoding="utf-8").lower():
                with daily.open("a", encoding="utf-8") as f:
                    f.write("\n- Chiusura non committata: `scripts/verify` non passa. Dettagli in second-brain-chiudi.log, nella cartella dei log (scripts/percorsi.py).\n")
        return 0
    finally:
        lock.rmdir()


if __name__ == "__main__":
    sys.exit(chiudi())

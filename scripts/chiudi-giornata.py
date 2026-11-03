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

VAULT = Path(__file__).resolve().parent.parent
LOGS = Path.home() / "Library" / "Logs"
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
           run=subprocess.run, adesso=None):
    adesso = adesso or datetime.now()
    oggi = f"{adesso:%F}"

    def scrivi(riga):
        with open(log, "a", encoding="utf-8") as f:
            f.write(riga + "\n")

    def sporco():
        return run(["git", "status", "--porcelain"], cwd=vault, capture_output=True, text=True).stdout.strip()

    if not _lock(lock):
        scrivi(f"{adesso:%F %T} chiusura già in corso: salto")
        return 0
    try:
        scrivi(f"=== {adesso:%F %T} ===")
        with open(log, "a", encoding="utf-8") as f:
            r = run([sys.executable, "-I", "scripts/attivita-progetti.py"], cwd=vault, stdout=subprocess.PIPE, stderr=f, text=True)
        attivita = r.stdout.rstrip("\n")
        if not attivita and not sporco():
            scrivi("niente da aggiornare: nessun commit nuovo nei repo e vault pulito")
            return 0

        # I git di lettura e il commit sono già permessi da .claude/settings.json; qui non apro altro.
        prompt = f"/chiudi-giornata\nAttività dei repo dall'ultimo STATE:\n{attivita or 'nessuna'}"
        with open(log, "a", encoding="utf-8") as f:
            run(["claude", "--permission-mode", "dontAsk", "--allowedTools", "Read", "Write", "Edit", "Glob", "Grep", "-p", prompt],
                cwd=vault, stdout=f, stderr=subprocess.STDOUT)

        if not sporco():
            scrivi("nessuna modifica da committare")
            return 0

        with open(log, "a", encoding="utf-8") as f:
            ok = run([sys.executable, "-I", "scripts/verify"], cwd=vault, stdout=f, stderr=subprocess.STDOUT).returncode == 0
        if ok:
            run(["git", "add", "-A"], cwd=vault)
            run(["git", "commit", "-q", "-m", f"chiusura {oggi}", "-m", "Co-Authored-By: Claude Haiku 5.5 <noreply@anthropic.com>"], cwd=vault)
            scrivi(f"commit: chiusura {oggi}")
        else:
            scrivi("verify non passa: nessun commit. Vedi il log e la sezione Da confermare.")
            # Nel brief di oggi, una volta sola, così non resta solo nel log.
            daily = vault / "daily" / f"{oggi}.md"
            if daily.is_file() and "chiusura non committata" not in daily.read_text(encoding="utf-8").lower():
                with daily.open("a", encoding="utf-8") as f:
                    f.write("\n- Chiusura non committata: `scripts/verify` non passa. Dettagli in ~/Library/Logs/second-brain-chiudi.log.\n")
        return 0
    finally:
        lock.rmdir()


if __name__ == "__main__":
    sys.exit(chiudi())

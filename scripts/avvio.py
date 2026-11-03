#!/usr/bin/env python3
"""Avvio al login: chiude il lavoro lasciato in sospeso, poi prepara il brief di oggi.

- Modifiche non committate o commit nuovi nei repo dei progetti: lancia /chiudi-giornata (commit locale solo se verify passa).
- File di oggi assente: lancia /morning. Se esiste, non fa nulla.
Uso: scripts/avvio.py   (AVVIO_DRY_RUN=1 mostra le decisioni senza eseguire)
"""
import os
import subprocess
import sys
import time
import urllib.error
import urllib.request
from datetime import datetime
from pathlib import Path

VAULT = Path(__file__).resolve().parent.parent
LOG = Path.home() / "Library" / "Logs" / "second-brain-avvio.log"
DASHBOARD = "http://127.0.0.1:8765/"


def risponde(url):
    """Come `curl -s`: basta una risposta HTTP qualsiasi, anche un errore."""
    try:
        urllib.request.urlopen(url, timeout=2).close()
    except urllib.error.HTTPError:
        pass
    except OSError:
        return False
    return True


def avvio(vault=VAULT, log=LOG, run=subprocess.run, env=os.environ, adesso=None, attendi=time.sleep, risponde=risponde):
    oggi = f"{adesso or datetime.now():%F}"
    dry = env.get("AVVIO_DRY_RUN") == "1"

    def say(riga):
        with open(log, "a", encoding="utf-8") as f:
            f.write(f"{datetime.now():%F %T} {riga}\n")
        print(riga)

    def py(script, **kw):
        return run([sys.executable, "-I", f"scripts/{script}"], cwd=vault, **kw)

    rc = py("aggiorna-oggi.py").returncode
    if rc:
        return rc

    # Qualcosa da chiudere? Modifiche non committate, esclusi i file di stato di Obsidian.
    pending = run(["git", "status", "--porcelain", "--", ".", ":!.obsidian"], cwd=vault, capture_output=True, text=True).stdout.strip()
    # Commit nuovi nei repo dei progetti: gli STATE vanno aggiornati prima del brief.
    nuovi = py("attivita-progetti.py", stdout=subprocess.PIPE, stderr=subprocess.DEVNULL, text=True).stdout.strip()
    if pending or nuovi:
        say(f"da chiudere: {'modifiche non committate ' if pending else ''}{'commit nuovi nei repo' if nuovi else ''}")
        if not dry and py("chiudi-giornata.py").returncode:
            return 1
    else:
        say("niente da chiudere")

    # Brief di oggi, solo se non esiste ancora.
    if (vault / "daily" / f"{oggi}.md").is_file():
        say("brief di oggi già presente: non lo rigenero")
    else:
        say("brief di oggi assente: lancio /morning")
        if not dry and py("morning.py").returncode:
            return 1

    # Dashboard: il server gira con launchd (job dashboard); qui si apre la pagina.
    if not dry:
        for _ in range(20):
            if risponde(DASHBOARD):
                break
            attendi(1)
        if run(["open", DASHBOARD]).returncode == 0:
            say(f"dashboard aperta su {DASHBOARD}")
    return 0


if __name__ == "__main__":
    sys.exit(avvio())

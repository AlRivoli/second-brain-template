#!/usr/bin/env python3
"""Report settimanale: claude doctor, uso dei comandi e controllo delle skill. Non rimuove e non aggiorna nulla.
Uso: scripts/pulizia-settimanale.py   (PULIZIA_DRY_RUN=1 mostra i percorsi)
"""
import json
import os
import subprocess
import sys
from datetime import datetime
from pathlib import Path

VAULT = Path(__file__).resolve().parent.parent


def pulizia(vault=VAULT, run=subprocess.run, env=os.environ, adesso=None):
    adesso = adesso or datetime.now()
    anno, sett, _ = adesso.isocalendar()
    week, oggi = f"{anno}-W{sett:02d}", f"{adesso:%F}"
    uscita, skill_json = f"daily/{week}-uso.md", f"daily/{week}-skill.json"
    if env.get("PULIZIA_DRY_RUN") == "1":
        print(f"scriverebbe: {uscita}")
        return 0

    def esegui(*cmd, unisci=True):
        """(codice, uscita senza l'ultimo a capo); con unisci=False l'errore non entra nel testo."""
        try:
            r = run(list(cmd), cwd=vault, stdin=subprocess.DEVNULL, stdout=subprocess.PIPE,
                    stderr=subprocess.STDOUT if unisci else None, text=True, encoding="utf-8")
        except FileNotFoundError:
            return 127, f"{cmd[0]}: command not found"
        return r.returncode, (r.stdout or "").rstrip("\n")

    def py(script, *args, **kw):
        return esegui(sys.executable, "-I", f"scripts/{script}", *args, **kw)

    doctor = "\n".join(esegui("claude", "doctor")[1].splitlines()[-30:])
    rc, controllo = py("controllo-skill.py", "--out", skill_json, unisci=False)
    if rc:  # un errore di rete non deve fermare il resto del report
        controllo = (controllo + "\n" if controllo else "") + "- controllo non riuscito: vedi il log"
    rotazione = py("ruota-log.py")[1]  # un errore qui non ferma il report
    report = "\n".join([
        f"# Pulizia settimanale {week}", "",
        "## claude doctor (ultime 30 righe)", "", "```", doctor, "```", "",
        "## Versioni (segnalate, mai aggiornate in automatico)", "", py("versioni.py", unisci=False)[1], "",
        "## Skill (controllo contro i repo di origine)", "", controllo, "",
        esegui(sys.executable, "scripts/uso-settimanale.py", unisci=False)[1], "",
        "## Rotazione log", "", rotazione or "Nessun log sopra soglia: niente ruotato.", "",
        "Nessuna skill o comando viene rimosso automaticamente: le rimozioni richiedono un tuo ok.", ""])
    (vault / uscita).write_text(report, encoding="utf-8")

    daily = vault / "daily" / f"{oggi}.md"
    testo = daily.read_text(encoding="utf-8") if daily.is_file() else None
    if testo is not None and f"{week}-uso" not in testo:  # rimando nel brief di oggi, una volta sola
        testo += f"\n- Pulizia settimanale: vedi [[daily/{week}-uso]]. Nessuna rimozione automatica.\n"
        daily.write_text(testo, encoding="utf-8")
    try:  # se ci sono versioni nuove, rimando anche a quelle, una volta sola
        nuove = sum(1 for s in json.loads((vault / skill_json).read_text(encoding="utf-8"))["skill"] if s["stato"] == "nuova")
    except (OSError, ValueError, KeyError):
        nuove = 0
    if nuove > 0 and testo is not None and "versioni nuove, vedi la sezione Configurazione" not in testo:
        with daily.open("a", encoding="utf-8") as f:
            f.write(f"\n- Skill: {nuove} versioni nuove, vedi la sezione Configurazione della dashboard. Niente si aggiorna senza il tuo ok.\n")
    print(f"scritto: {uscita}")
    return 0


if __name__ == "__main__":
    sys.exit(pulizia())

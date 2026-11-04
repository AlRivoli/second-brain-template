"""Avviso quando `claude -p` non riesce ad autenticarsi in una run non presidiata.

Tre canali: la riga nel log la scrive chi chiama; qui la riga in "Da confermare" del brief di oggi (se esiste, una volta
sola) e una notifica di macOS (al massimo una al giorno). Importato dagli script che lanciano claude.
"""
import subprocess
import sys
from datetime import datetime
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import percorsi  # noqa: E402

SEGNI = ("Failed to authenticate", "OAuth session expired", "Please run /login")
MARCATORE = percorsi.cartella_log() / "second-brain-auth.avviso"


def non_autenticato(testo):
    return any(s in (testo or "") for s in SEGNI)


def segnala(vault, lavoro, adesso=None, run=subprocess.run, marcatore=MARCATORE, piattaforma=sys.platform):
    """Riga nel brief di oggi e notifica. `lavoro` dice cosa non è stato fatto (es. "la chiusura")."""
    adesso = adesso or datetime.now()
    oggi = f"{adesso:%F}"
    testo = f"Claude Code non è autenticato (sessione scaduta): {lavoro} non è stata fatta. Apri `claude`, lancia `/login`, poi rilancia dalla dashboard."
    daily = Path(vault) / "daily" / f"{oggi}.md"
    if daily.is_file() and "Claude Code non è autenticato" not in daily.read_text(encoding="utf-8"):
        with daily.open("a", encoding="utf-8") as f:
            f.write(f"\n- Da confermare: {testo}\n")
    if marcatore.is_file() and marcatore.read_text(encoding="utf-8").strip() == oggi:
        return False
    marcatore.write_text(oggi, encoding="utf-8")
    if piattaforma == "darwin":
        run(["osascript", "-e", f'display notification "{lavoro} non è stata fatta: Claude Code va riautenticato (/login)" with title "Second brain"'])
    return True

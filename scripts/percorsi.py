"""Dove un sistema tiene i log: la stessa regola di install_jobs.py (cartella_log), così i job e i loro log stanno nello stesso posto.

macOS ~/Library/Logs, Windows %LOCALAPPDATA%\\second-brain\\logs, Linux $XDG_STATE_HOME o ~/.local/state, in second-brain/.
"""
import os
import sys
from pathlib import Path


def cartella_log(home=None, piattaforma=None, ambiente=os.environ):
    home = Path(home or Path.home())
    piattaforma = piattaforma or sys.platform
    if piattaforma == "darwin":
        cartella = home / "Library" / "Logs"
    elif piattaforma == "win32":
        cartella = Path(ambiente.get("LOCALAPPDATA") or home / "AppData" / "Local") / "second-brain" / "logs"
    else:
        cartella = Path(ambiente.get("XDG_STATE_HOME") or home / ".local" / "state") / "second-brain"
    try:
        cartella.mkdir(parents=True, exist_ok=True)
    except OSError:
        pass  # chi scrive nel log gestisce l'errore a modo suo
    return cartella


def cartella_segreti(home=None, piattaforma=None, ambiente=os.environ):
    """Dove stanno i segreti dell'utente (indirizzi privati dei calendari, password): fuori dal vault, che finisce in git.
    macOS e Linux ~/.config/second-brain (o $XDG_CONFIG_HOME), Windows %APPDATA%\\second-brain. Non la crea: chi scrive un segreto lo fa con permessi stretti."""
    home = Path(home or Path.home())
    if (piattaforma or sys.platform) == "win32":
        return Path(ambiente.get("APPDATA") or home / "AppData" / "Roaming") / "second-brain"
    return Path(ambiente.get("XDG_CONFIG_HOME") or home / ".config") / "second-brain"


def permessi_stretti(file, piattaforma=None):
    """True se solo il proprietario può leggere il file. Su Windows i permessi non si leggono con la libreria standard: si fida della cartella dell'utente."""
    if (piattaforma or sys.platform) == "win32":
        return True
    return (Path(file).stat().st_mode & 0o077) == 0

"""Dove un sistema tiene i log: la stessa regola di install_jobs.py (cartella_log), così i job e i loro log stanno nello stesso posto.

macOS ~/Library/Logs, Windows %LOCALAPPDATA%\\second-brain\\logs, Linux $XDG_STATE_HOME o ~/.local/state, in second-brain/.
"""
import functools
import importlib.util
import json
import os
import re
import sys
from pathlib import Path, PureWindowsPath


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


# ---- Network paths and the reserved folder: one reading for the dashboard and every script (ADR-002) ----

UNITA_DI_RETE = 4  # DRIVE_REMOTE of GetDriveTypeW
FISSE = ("lavoro", "_private")  # the folders under projects/ that never reach a cloud model, whatever config.json says
MODULO_SETUP_MANCANTE = ("manca moduli.py nella radice del vault (il modulo del setup): senza la sua regola non posso controllare "
                         "la cartella riservata, rimettilo dal repo del vault")


def tipo_unita(unita):
    """GetDriveTypeW of a drive letter («C:»), Windows only: it asks the type of the drive, it does not list or open files.
    The root needs the trailing backslash: without it the answer is 1 (no root directory) and a mapped drive would pass."""
    import ctypes
    return ctypes.windll.kernel32.GetDriveTypeW(unita + "\\")


def percorso_locale(percorso):
    r"""Un percorso assoluto su un disco di questo computer: non di rete (\\server\share, o su Windows una lettera di unità
    collegata a una condivisione) né un dispositivo (\\.\, \\?\). Su Windows deve avere una lettera di unità. Da chiamare
    prima di toccare il disco: «/\srv\share» diventa un percorso di rete solo su Windows."""
    percorso = Path(percorso)
    if not percorso.is_absolute() or str(percorso).startswith(("\\\\", "//")) or percorso.drive.startswith(("\\\\", "//")):
        return False
    if os.name != "nt":
        return True
    return re.fullmatch(r"[A-Za-z]:", percorso.drive) is not None and tipo_unita(percorso.drive) != UNITA_DI_RETE


@functools.lru_cache(maxsize=1)
def _valida_cartella():
    """moduli.valida_cartella, the setup wizard's rule for the reserved folder, loaded on first use (moduli.py has no side effects)."""
    spec = importlib.util.spec_from_file_location("moduli", Path(__file__).resolve().parent.parent / "moduli.py")
    moduli = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(moduli)
    return moduli.valida_cartella


def _riservata_in_config(vault):
    """moduli.riservata of config.json as written (any JSON value), or None when config.json, `moduli` or `riservata` is
    missing. RuntimeError("config") when config.json cannot be read or parsed, or it or `moduli` is not a JSON object.
    Whether `riservata` itself is well formed is for the caller: the strict reading refuses it, the tolerant one keeps its folder."""
    try:
        config = json.loads((Path(vault) / "config.json").read_text(encoding="utf-8-sig"))  # -sig: a BOM from a Windows editor
    except FileNotFoundError:
        return None
    except (OSError, ValueError, RecursionError):  # ValueError covers UnicodeDecodeError and JSONDecodeError
        raise RuntimeError("config") from None
    livello = config
    for chiave in ("moduli", "riservata"):
        if not isinstance(livello, dict):
            raise RuntimeError("config")
        if chiave not in livello:
            return None
        livello = livello[chiave]
    return livello


def scelta_riservata(vault):
    """The reserved folder chosen at setup as the wizard writes it (moduli.valida_cartella: relative, with /, case kept), or
    None when there is none. RuntimeError("config"), so a caller that must not miss it fails closed, when config.json is
    unreadable or ill-shaped, the module is on (`attivo`) without a folder, or the folder is one the wizard would refuse
    (absolute, ~, .., a git folder, not a string...), or `attivo` is not a boolean. With moduli.py missing the rule is unknown:
    still RuntimeError("config"), whose `motivo` says so (MODULO_SETUP_MANCANTE) for the scripts' messages."""
    riservata = _riservata_in_config(vault)
    if riservata is None:
        return None
    attivo = riservata.get("attivo", False) if isinstance(riservata, dict) else None
    if not isinstance(attivo, bool):  # also a `riservata` that is not an object
        raise RuntimeError("config")
    cartella = riservata.get("cartella")
    if cartella is None:
        if attivo:
            raise RuntimeError("config")
        return None
    if not isinstance(cartella, str):
        raise RuntimeError("config")
    try:
        regola = _valida_cartella()
    except OSError:
        errore = RuntimeError("config")
        errore.motivo = MODULO_SETUP_MANCANTE
        raise errore from None
    except Exception:  # a moduli.py that does not load (a syntax error, no valida_cartella...): the rule is unknown too
        raise RuntimeError("config") from None
    try:
        return regola(cartella)
    except ValueError:
        raise RuntimeError("config") from None


def scelta_tollerante(vault):
    """scelta_riservata for whoever must keep working on a broken config.json (the map, a session hook): a relative string
    the wizard would refuse still protects what it names; an unreadable file, or an absolute, drive-letter or network value
    (Z:/notes, \\\\srv\\x, /x), leaves only the fixed folders, so loading the map never resolves a network path."""
    try:
        return scelta_riservata(vault)
    except RuntimeError:
        try:
            riservata = _riservata_in_config(vault)
        except RuntimeError:
            return None
        # the folder is kept whatever else is wrong in `riservata` (an `attivo` that is not a boolean, say): only the launch
        # refuses a malformed setting, the map and the session hook must still exclude what it names
        cartella = riservata.get("cartella") if isinstance(riservata, dict) else None
        if not isinstance(cartella, str) or not cartella.strip("/\\ ") or cartella.startswith(("/", "\\")) or PureWindowsPath(cartella).drive:
            return None
        return cartella.replace("\\", "/").strip("/")


def nomi_riservati(cartella):
    """The casefolded names under projects/ that are never read for a cloud model: FISSE and, when the setup's folder is
    projects/<name> in any case and with a backslash or /, that name («Projects/Secret» is the folder secret on NTFS and APFS)."""
    nomi = set(FISSE)
    parti = [p for p in cartella.replace("\\", "/").split("/") if p] if isinstance(cartella, str) else []
    if len(parti) == 2 and parti[0].casefold() == "projects":
        nomi.add(parti[1])
    return {n.casefold() for n in nomi}


def cartelle_riservate(vault):
    """nomi_riservati of the tolerant reading: for the pages and hooks that must not break on a bad config.json."""
    return nomi_riservati(scelta_tollerante(vault))

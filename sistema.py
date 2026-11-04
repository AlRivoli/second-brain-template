"""Il computer e i programmi che il wizard può proporre. Solo libreria standard, nessun effetto finché non si chiama `esegui`.

Regole: il wizard chiede sempre prima e mostra il comando intero. Esegue solo comandi di un gestore di pacchetti (brew, winget, flatpak) o
`ollama pull`/`git config`, come lista di argomenti, mai in una shell. Gli installatori che si scaricano e si lanciano da internet
(`curl ... | bash`) non li esegue: li mostra, e li lanci tu nel tuo terminale.
"""
import importlib.util
import json
import os
import platform
import shutil
import subprocess
import sys
from pathlib import Path

RADICE = Path(__file__).resolve().parent
SISTEMA = {"Darwin": "macos", "Linux": "linux", "Windows": "windows"}.get(platform.system(), "linux")

# Dimensioni indicative dei modelli (GB sul disco): stime, non misure.
DIMENSIONI = {"qwen3:8b": 5.2, "qwen3:4b-instruct-2507": 2.5, "bge-m3": 1.2}

PACCHETTI = {
    "obsidian": {"macos": ("brew", ["brew", "install", "--cask", "obsidian"]),
                 "windows": ("winget", ["winget", "install", "--id", "Obsidian.Obsidian", "-e", "--accept-source-agreements", "--accept-package-agreements"]),
                 "linux": ("flatpak", ["flatpak", "install", "-y", "flathub", "md.obsidian.Obsidian"])},
    "ollama": {"macos": ("brew", ["brew", "install", "--cask", "ollama-app"]),
               "windows": ("winget", ["winget", "install", "--id", "Ollama.Ollama", "-e", "--accept-source-agreements", "--accept-package-agreements"])},
    "gitleaks": {"macos": ("brew", ["brew", "install", "gitleaks"]),
                 "windows": ("winget", ["winget", "install", "--id", "Gitleaks.Gitleaks", "-e", "--accept-source-agreements", "--accept-package-agreements"])},
}
PAGINE = {"obsidian": "https://obsidian.md/download", "ollama": "https://ollama.com/download", "gitleaks": "https://github.com/gitleaks/gitleaks#installing",
          "claude": "https://code.claude.com/docs/en/setup"}


def _carica(nome):
    spec = importlib.util.spec_from_file_location(nome, RADICE / (nome + ".py"))
    m = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(m)
    return m


def _modello():
    for cartella in (RADICE, RADICE.parent):
        if (cartella / "scripts" / "modello.py").exists():
            spec = importlib.util.spec_from_file_location("modello", cartella / "scripts" / "modello.py")
            m = importlib.util.module_from_spec(spec)
            spec.loader.exec_module(m)
            return m
    return None


def gpu(esegui=subprocess.run, quale=shutil.which, sistema=SISTEMA, arch=None):
    """Descrizione breve della scheda grafica, o None. Serve solo a spiegare la scelta del modello."""
    arch = arch or platform.machine()
    if sistema == "macos" and arch in ("arm64", "aarch64"):
        return "Apple Silicon (unified memory)"
    if quale("nvidia-smi"):
        try:
            r = esegui(["nvidia-smi", "--query-gpu=name,memory.total", "--format=csv,noheader"], capture_output=True, text=True, encoding="utf-8", timeout=10)
            riga = r.stdout.strip().splitlines()[0] if r.returncode == 0 and r.stdout.strip() else ""
            return riga or None
        except (OSError, subprocess.SubprocessError, IndexError):
            return None
    return None


def scansiona(radice=RADICE):
    """{sistema, arch, ram_gb, disco_libero_gb, cpu, gpu}: ciò che serve per consigliare un modello. Nessun dato personale."""
    m = _modello()
    try:
        libero = shutil.disk_usage(radice).free / 2**30
    except OSError:
        libero = None
    return {"sistema": SISTEMA, "arch": platform.machine(), "ram_gb": m.ram_gb() if m else None, "disco_libero_gb": libero,
            "cpu": os.cpu_count(), "gpu": gpu()}


def consigli(scan):
    """{chat, embedding}: modelli locali adatti a questo computer (o None). Soglie e stime, non misure."""
    ram, libero = scan.get("ram_gb"), scan.get("disco_libero_gb")
    chat = None
    if ram is not None and ram >= 15:
        chat = "qwen3:8b"
    elif ram is not None and ram >= 7:
        chat = "qwen3:4b-instruct-2507"
    if chat and libero is not None and libero < DIMENSIONI[chat] + 5:
        chat = None  # poco spazio sul disco: meglio non proporre un download
    embedding = "bge-m3" if ram is not None and ram >= 7 and (libero is None or libero >= DIMENSIONI["bge-m3"] + 5) else None
    return {"chat": chat, "embedding": embedding}


def descrivi(scan, lingua):
    ram = "%.0f GB" % scan["ram_gb"] if scan.get("ram_gb") else ("?" if lingua == "en" else "non rilevata")
    disco = "%.0f GB" % scan["disco_libero_gb"] if scan.get("disco_libero_gb") else "?"
    voci = ["%s %s" % (scan["sistema"], scan["arch"]), "RAM %s" % ram, ("free disk %s" if lingua == "en" else "disco libero %s") % disco,
            "%s CPU" % scan["cpu"]] + ([scan["gpu"]] if scan.get("gpu") else [])
    return ", ".join(voci)


def piano_installazione(programma, sistema=SISTEMA, quale=shutil.which):
    """(comando come lista o None, nome del gestore che manca o None). None significa: da installare a mano, dalla pagina ufficiale."""
    voce = PACCHETTI.get(programma, {}).get(sistema)
    if not voce:
        return None, None
    gestore, comando = voce
    return (comando, None) if quale(gestore) else (None, gestore)


def installato(programma, doctor=None):
    d = doctor or _carica("doctor")
    if programma == "obsidian":
        return d.trova_obsidian()
    if programma == "ollama":
        return shutil.which("ollama") is not None or d.ollama_attivo()
    return shutil.which(programma) is not None


def esegui(comando, run=subprocess.run):
    """Codice di uscita. Il comando è una lista, mai una stringa: nessuna shell."""
    assert isinstance(comando, list)
    try:
        return run(comando).returncode
    except OSError:
        return 127


def comando_statusline(radice=RADICE, python=None):
    """Il comando della barra di stato di Claude Code che salva le percentuali d'uso (scripts/statusline-uso.py)."""
    return '"%s" -I "%s"' % (python or sys.executable, Path(radice) / "scripts" / "statusline-uso.py")


def aggiungi_statusline(file, comando):
    """'aggiunta', 'gia-presente' o 'illeggibile'. Non sovrascrive una barra di stato che c'è già e non tocca un file che non è JSON valido.
    Prima di scrivere lascia una copia (<file>.bak-second-brain)."""
    file = Path(file)
    try:
        dati = json.loads(file.read_text(encoding="utf-8-sig")) if file.exists() else {}
    except (OSError, ValueError):
        return "illeggibile"
    if not isinstance(dati, dict):
        return "illeggibile"
    if dati.get("statusLine"):
        return "gia-presente"
    if file.exists():
        shutil.copy2(file, file.with_name(file.name + ".bak-second-brain"))
    dati["statusLine"] = {"type": "command", "command": comando}
    file.parent.mkdir(parents=True, exist_ok=True)
    _carica("moduli").scrivi(file, json.dumps(dati, indent=2, ensure_ascii=False) + "\n")
    return "aggiunta"

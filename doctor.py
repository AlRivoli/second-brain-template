#!/usr/bin/env python3
"""Checks that this computer can run the second brain, and says what is missing. Standard library only.

Usage:
    python3 doctor.py            (Windows: py -3 doctor.py)
    python3 doctor.py --ci       only the required checks (not Claude Code: CI runners do not have it), exit code 1 if one fails
    python3 doctor.py --lang it  messages in Italian

Required: Python 3.9+, git, the Claude Code CLI, and `scripts/verify` printing OK.
Optional: Ollama (local model for the radar filter), a Chromium-based browser (post images), gitleaks (for maintainers).
"""
import importlib.util
import json
import os
import platform
import shutil
import subprocess
import sys
import urllib.request
from pathlib import Path

RADICE = Path(__file__).resolve().parent
SISTEMA = {"Darwin": "macos", "Linux": "linux", "Windows": "windows"}.get(platform.system(), "linux")

INSTALLA = {
    "python": {"macos": "https://www.python.org/downloads/ (or: brew install python)", "linux": "sudo apt install python3  (or your package manager)",
               "windows": "winget install Python.Python.3.12"},
    "git": {"macos": "xcode-select --install", "linux": "sudo apt install git  (or your package manager)", "windows": "winget install Git.Git"},
    "claude": {"macos": "curl -fsSL https://claude.ai/install.sh | bash", "linux": "curl -fsSL https://claude.ai/install.sh | bash",
               "windows": "irm https://claude.ai/install.ps1 | iex   (in PowerShell)"},
    "ollama": {"macos": "https://ollama.com/download", "linux": "curl -fsSL https://ollama.com/install.sh | sh", "windows": "https://ollama.com/download"},
    "browser": {"macos": "install Google Chrome from https://www.google.com/chrome/", "linux": "sudo apt install chromium  (or Chrome)",
                "windows": "Microsoft Edge is already installed; or install Chrome"},
    "gitleaks": {"macos": "brew install gitleaks", "linux": "see https://github.com/gitleaks/gitleaks#installing", "windows": "winget install gitleaks.gitleaks"},
}
TESTI = {
    "en": {"ok": "OK", "missing": "MISSING", "optional": "optional, missing", "fix": "install:", "all_ok": "Everything required is in place.",
           "some_missing": "Fix the MISSING items above, then run this again.",
           "python": "Python 3.9 or newer", "git": "git", "claude": "Claude Code (claude)", "verify": "vault rules (scripts/verify)",
           "ollama": "Ollama running (local model)", "browser": "Chrome, Chromium or Edge (post images)", "gitleaks": "gitleaks (secret scan)",
           "config": "config.json (run setup.py)"},
    "it": {"ok": "OK", "missing": "MANCA", "optional": "facoltativo, manca", "fix": "installa:", "all_ok": "Tutto il necessario c'è.",
           "some_missing": "Sistema le voci MANCA qui sopra, poi rilancia.",
           "python": "Python 3.9 o più recente", "git": "git", "claude": "Claude Code (claude)", "verify": "regole del vault (scripts/verify)",
           "ollama": "Ollama in esecuzione (modello locale)", "browser": "Chrome, Chromium o Edge (immagini dei post)", "gitleaks": "gitleaks (controllo segreti)",
           "config": "config.json (lancia setup.py)"},
}
BROWSER = {
    "macos": ["/Applications/Google Chrome.app/Contents/MacOS/Google Chrome", "/Applications/Microsoft Edge.app/Contents/MacOS/Microsoft Edge",
              "/Applications/Chromium.app/Contents/MacOS/Chromium"],
    "linux": [],
    "windows": [r"C:\Program Files\Google\Chrome\Application\chrome.exe", r"C:\Program Files (x86)\Google\Chrome\Application\chrome.exe",
                r"C:\Program Files (x86)\Microsoft\Edge\Application\msedge.exe", r"C:\Program Files\Microsoft\Edge\Application\msedge.exe"],
}
NOMI_BROWSER = ["google-chrome", "google-chrome-stable", "chromium", "chromium-browser", "microsoft-edge", "chrome", "msedge"]


def trova_browser(sistema=SISTEMA, esiste=os.path.exists, quale=shutil.which):
    for percorso in BROWSER[sistema]:
        if esiste(percorso):
            return percorso
    return next((quale(n) for n in NOMI_BROWSER if quale(n)), None)


def ollama_attivo(url="http://127.0.0.1:11434/api/tags"):
    try:
        with urllib.request.urlopen(url, timeout=2) as r:
            return r.status == 200
    except OSError:
        return False


def comando_ok(args):
    try:
        return subprocess.run(args, capture_output=True, timeout=30).returncode == 0
    except (OSError, subprocess.TimeoutExpired):
        return False


def lingua_da_config(radice=RADICE):
    try:
        return json.loads((radice / "config.json").read_text(encoding="utf-8")).get("lingua", "en")
    except (OSError, ValueError):
        return "en"


def modelli_scaricati(url="http://127.0.0.1:11434/api/tags"):
    """Nomi dei modelli già scaricati in Ollama, o None se Ollama non risponde."""
    try:
        with urllib.request.urlopen(url, timeout=2) as r:
            return {m["name"] for m in json.load(r).get("models", [])}
    except (OSError, ValueError, KeyError):
        return None


def ram_gb():
    try:
        spec = importlib.util.spec_from_file_location("modello", RADICE / "scripts" / "modello.py")
        m = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(m)
        return m.ram_gb()
    except (OSError, ImportError, AttributeError):
        return None


FRASI = {
    "en": {"ollama_off": "Ollama is not running, but you chose local models: %s", "pull": "download with: ollama pull %s",
           "poca_ram": "only %.0f GB of RAM: a local reasoning model will be slow. Claude or no model is the safer choice for %s",
           "n8n": "n8n collects the news (you chose it in the radar module): install it from https://docs.n8n.io/hosting/ and import your own workflow",
           "obsidian": "optional: Obsidian (https://obsidian.md/download) to read and edit the notes in a nice interface"},
    "it": {"ollama_off": "Ollama non è in esecuzione, ma hai scelto modelli locali: %s", "pull": "scaricalo con: ollama pull %s",
           "poca_ram": "solo %.0f GB di RAM: un modello locale che ragiona sarà lento. Claude o nessun modello è più sicuro per %s",
           "n8n": "n8n raccoglie le novità (l'hai scelto nel modulo radar): installalo da https://docs.n8n.io/hosting/ e importa il tuo flusso",
           "obsidian": "facoltativo: Obsidian (https://obsidian.md/download) per leggere e modificare le note con un'interfaccia comoda"},
}


def dalle_scelte(radice=RADICE, lingua="en", scaricati=None, ram=None):
    """[(testo, rimedio o None, richiesto)] su ciò che serve per le scelte fatte in setup.py: non chiede programmi che non hai scelto."""
    try:
        cfg = json.loads((radice / "config.json").read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return []
    f, out = FRASI.get(lingua, FRASI["en"]), []
    modelli = {k: str(v) for k, v in cfg.get("modelli", {}).items() if str(v).startswith("ollama:")}
    if modelli:
        scaricati = modelli_scaricati() if scaricati is None else scaricati
        if scaricati is None:
            out.append((f["ollama_off"] % ", ".join(sorted(set(v[7:] for v in modelli.values()))), INSTALLA["ollama"][SISTEMA], True))
        else:
            for nome in sorted(set(v[7:] for v in modelli.values())):
                if nome not in scaricati and nome + ":latest" not in scaricati:
                    out.append((nome, f["pull"] % nome, True))
        ram = ram_gb() if ram is None else ram
        ragionano = sorted(k for k in modelli if not k.endswith("embedding"))
        if ram is not None and ram < 7 and ragionano:
            out.append((f["poca_ram"] % (ram, ", ".join(ragionano)), None, False))
    if cfg.get("moduli", {}).get("radar", {}).get("automazione") == "n8n":
        out.append((f["n8n"], None, False))
    out.append((f["obsidian"], None, False))
    return out


def controlli(radice=RADICE, ci=False):
    """Lista di (chiave, richiesto, ok). In CI il CLI `claude` non è richiesto: i runner non lo hanno."""
    verify = radice / "scripts" / "verify"
    return [
        ("python", True, sys.version_info >= (3, 9)),
        ("git", True, shutil.which("git") is not None),
        ("claude", not ci, shutil.which("claude") is not None and comando_ok(["claude", "--version"])),
        ("verify", True, verify.is_file() and subprocess.run([sys.executable, str(verify), str(radice)], capture_output=True).returncode == 0),
        ("config", False, (radice / "config.json").is_file()),
        ("ollama", False, ollama_attivo()),
        ("browser", False, trova_browser() is not None),
        ("gitleaks", False, shutil.which("gitleaks") is not None),
    ]


def main(argv=None):
    argv = sys.argv[1:] if argv is None else argv
    ci = "--ci" in argv
    lingua = argv[argv.index("--lang") + 1] if "--lang" in argv and argv.index("--lang") + 1 < len(argv) else lingua_da_config()
    t = TESTI.get(lingua, TESTI["en"])
    mancano = 0
    for chiave, richiesto, ok in controlli(ci=ci):
        if ci and not richiesto:
            continue
        stato = t["ok"] if ok else (t["missing"] if richiesto else t["optional"])
        print("%-9s %s" % (stato, t[chiave]))
        if not ok:
            if chiave in INSTALLA:
                print("          %s %s" % (t["fix"], INSTALLA[chiave][SISTEMA]))
            mancano += 1 if richiesto else 0
    if not ci:
        for testo, rimedio, richiesto in dalle_scelte(RADICE, lingua):
            print("%-9s %s" % (t["missing"] if richiesto else t["optional"].split(",")[0], testo))
            if rimedio:
                print("          %s %s" % (t["fix"], rimedio))
            mancano += 1 if richiesto else 0
    print(t["all_ok"] if not mancano else t["some_missing"])
    return 1 if mancano else 0


if __name__ == "__main__":
    sys.exit(main())

#!/usr/bin/env python3
"""Attività dei repo dei progetti dall'ultima volta che il loro STATE è cambiato nel vault.

Uso: scripts/attivita-progetti.py [--giorni N]
Senza opzioni stampa solo i progetti con commit nuovi dall'ultimo cambio dello STATE (niente output = niente da
aggiornare). Con --giorni N guarda invece gli ultimi N giorni, per la revisione settimanale.
Sola lettura dei repo, tutti i branch (il lavoro sta anche in feat/* e nei worktree). Non tocca le cartelle del lavoro e
riservata, in qualunque maiuscola (ADR-001, ADR-002): con config.json illeggibile o di forma inattesa non stampa niente ed
esce con 1. Un repo su un percorso di rete si salta con un avviso, prima di lanciare git.
Un progetto può avere più righe «Repo:», una per repo: si leggono tutte e, se sono più di una, ogni riga dice da quale
repo viene. Un repo che non si legge si salta con un avviso su stderr, gli altri del progetto restano.
"""
import argparse
import importlib.util
import re
import subprocess
import sys
import time
from datetime import datetime
from pathlib import Path

VAULT = Path(__file__).resolve().parent.parent
# The dashboard's reading of the reserved folder and of network paths (percorsi.py), loaded from the file: under -I the
# script's folder is not on sys.path, and the dashboard loads this script the same way
_spec = importlib.util.spec_from_file_location("percorsi", Path(__file__).resolve().parent / "percorsi.py")
percorsi = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(percorsi)
REPO = re.compile(r"^- \*\*Repo:\*\* (.+)$", re.M)
MAX_COMMIT = 30
MAX_FILE = 15
SEGNAPOSTO = ("nessuno", "none", "-", "")  # «nessuno» è il segnaposto dei progetti senza repo


def _git(repo, *args):
    r = subprocess.run(["git", "-C", str(repo), *args], capture_output=True, text=True, encoding="utf-8", timeout=20, check=True)
    return r.stdout


def ultimo_cambio_state(nome, vault=VAULT):
    """Quando lo STATE del progetto è stato committato l'ultima volta nel vault (0 se mai)."""
    ts = _git(vault, "log", "-1", "--format=%ct", "--", "projects/%s/STATE.md" % nome).strip()
    return int(ts) if ts else 0


def repo_di(testo):
    """Tutti i percorsi delle righe «Repo:» di uno STATE, in ordine, senza doppioni né segnaposto."""
    return list(dict.fromkeys(p.strip() for p in REPO.findall(testo) if p.strip().lower() not in SEGNAPOSTO))


def attivita(repo, da_ts):
    """Commit (non di merge, tutti i branch) del repo dopo da_ts e file di wayfinder toccati. Righe di testo."""
    da = datetime.fromtimestamp(da_ts).isoformat(timespec="seconds")
    log = _git(repo, "log", "--branches", "--source", "--no-merges", "--since=" + da, "-%d" % MAX_COMMIT,
               "--format=%ct\t%S\t%s").splitlines()
    righe = []
    for r in log:
        ts, ramo, messaggio = r.split("\t", 2)
        righe.append("- %s %s: %s" % (datetime.fromtimestamp(int(ts)).strftime("%Y-%m-%d %H:%M"),
                                      ramo.removeprefix("refs/heads/"), messaggio))
    if righe:
        file = sorted({f for f in _git(repo, "log", "--branches", "--no-merges", "--since=" + da, "--name-only",
                                       "--format=", "--", "docs/wayfinder").splitlines() if f})
        if file:
            righe.append("File di wayfinder toccati: " + ", ".join(file[:MAX_FILE]))
    return righe


def main(argv=None):
    ap = argparse.ArgumentParser()
    ap.add_argument("--giorni", type=int)
    giorni = ap.parse_args(argv).giorni
    try:
        riservate = percorsi.nomi_riservati(percorsi.scelta_riservata(VAULT))
    except RuntimeError as e:  # the reserved folder is unknown: no STATE is read, nothing is printed (ADR-002)
        print(getattr(e, "motivo", None) or "config.json non leggibile o non valido: non posso escludere la cartella riservata, nessun progetto letto",
              file=sys.stderr)
        return 1
    for stato in sorted((VAULT / "projects").glob("*/STATE.md")):
        nome = stato.parent.name
        if nome.casefold() in riservate:
            continue
        repo_progetto = repo_di(stato.read_text(encoding="utf-8"))
        if not repo_progetto:
            continue
        try:
            da_ts = time.time() - giorni * 86400 if giorni else ultimo_cambio_state(nome)
        except (OSError, subprocess.SubprocessError) as e:
            print("%s: vault non leggibile (%s)" % (nome, e), file=sys.stderr)
            continue
        piu_repo = len(repo_progetto) > 1
        uscita, attivi = [], []
        for repo in repo_progetto:
            if not percorsi.percorso_locale(Path(repo).expanduser()):  # git -C would open a connection to another computer
                print("%s: repo non su un disco di questo computer, saltato" % nome, file=sys.stderr)
                continue
            try:
                righe = attivita(repo, da_ts)
            except (OSError, subprocess.SubprocessError) as e:
                print("%s: repo non leggibile (%s)" % (nome, e), file=sys.stderr)
                continue
            if righe:
                attivi.append(repo)
                # With several repos each line names its repo, so the reader knows where the commit happened.
                uscita += ["[%s] %s" % (Path(repo).name, r) for r in righe] if piu_repo else righe
        if uscita:
            print("## %s (repo %s)" % (nome, ", ".join(attivi)))
            print("\n".join(uscita))
    return 0


if __name__ == "__main__":
    # Callers read this output as UTF-8. Under -I PYTHONUTF8 is ignored, so on Windows a pipe would get the ANSI
    # code page: an accent in a commit message would break the reader, a character outside it would crash here.
    sys.stdout.reconfigure(encoding="utf-8")
    sys.exit(main())

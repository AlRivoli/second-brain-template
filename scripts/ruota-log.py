#!/usr/bin/env python3
"""Ruota i log dei job launchd: archivio .gz dell'intero file, poi tronca sul posto
(copy-truncate: il processo launchd tiene il file aperto, quindi niente rename).
Uso: scripts/ruota-log.py [cartella-log] [cartella-archivio]
Variabili: ROTA_SOGLIA_KB (512), ROTA_RIGHE (2000), ROTA_ARCHIVI (8)
"""
import gzip
import os
import sys
from datetime import datetime
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import percorsi  # noqa: E402


def ruota(logs, arch, soglia, righe, tenuti, adesso):
    for f in sorted(logs.glob("second-brain-*.log")):
        if not f.is_file() or f.stat().st_size <= soglia:
            continue
        nome = f.stem
        dati = f.read_bytes()
        arch.mkdir(parents=True, exist_ok=True)
        (arch / f"{nome}-{adesso:%F-%H%M%S}.log.gz").write_bytes(gzip.compress(dati))
        ultime = b"".join(dati.splitlines(keepends=True)[-righe:])
        with f.open("wb") as out:  # ponytail: righe scritte tra la lettura e il troncamento si perdono
            out.write(ultime)
        print(f"ruotato: {nome} ({len(dati) // 1024} KB -> ultime {righe} righe)")
        # tiene solo gli ultimi N archivi di questo log (i nomi ordinano per data)
        for vecchio in sorted(arch.glob(f"{nome}-*.log.gz"), reverse=True)[tenuti:]:
            vecchio.unlink()


if __name__ == "__main__":
    logs = Path(sys.argv[1]) if len(sys.argv) > 1 else percorsi.cartella_log()
    arch = Path(sys.argv[2]) if len(sys.argv) > 2 else logs / "archivio-second-brain"
    ruota(logs, arch, int(os.environ.get("ROTA_SOGLIA_KB", 512)) * 1024, int(os.environ.get("ROTA_RIGHE", 2000)),
          int(os.environ.get("ROTA_ARCHIVI", 8)), datetime.now())

#!/usr/bin/env python3
"""content-guard: controlli deterministici sul contenuto esterno. Nessun modello.

Uso:
  guard.py text FILE [--sources DIR]     controlla un testo (inbox o radar)
  guard.py fetch URL --sources DIR       controlla un URL prima di WebFetch

Stampa JSON {"ok": bool, "flags": [...]}. Esce con 1 se ci sono flag.
"""
import json
import pathlib
import re
import sys
from urllib.parse import urlparse

URL_RE = re.compile(r'https?://[^\s)\]>"\'<]+')
BLOB_RE = re.compile(r'[A-Za-z0-9+/]{40,}={0,2}')
# Nel percorso gli slash separano parti normali: un blob è una stringa lunga dentro un solo segmento.
SEGMENT_BLOB_RE = re.compile(r'[A-Za-z0-9+]{40,}')
MAX_QUERY = 100

# Schemi comuni di prompt injection, in italiano e in inglese.
# Non sono completi: un testo parafrasato passa. Per questo esiste la parte del modello.
INJECTION_PATTERNS = [
    r'ignor[ae]\s+(tutte\s+)?(le\s+)?istruzioni\s+(precedenti|sopra)',
    r'ignore\s+(all\s+|the\s+)?(previous|prior|above)\s+instructions',
    r'disregard\s+(all\s+|the\s+)?(previous|prior|above)',
    r'system\s*prompt',
    r'</?\s*system\s*>',
    r'\byou\s+are\s+now\b',
    r'\bnuove\s+istruzioni\b',
    r'\besegui\s+(questo|il\s+seguente)\b',
    r'\brun\s+the\s+following\b',
    r'\bwrite\s+to\s+(CLAUDE\.md|memory/)',
    r'\b(curl|wget)\s+https?://',
]


def declared_sources(sources_dir):
    """Tutti gli URL citati nei file di inbox/: sono le fonti dichiarate."""
    found = set()
    for path in pathlib.Path(sources_dir).glob('*.md'):
        found.update(URL_RE.findall(path.read_text(encoding='utf-8')))
    return found


def scan_text(text):
    flags = []
    for pattern in INJECTION_PATTERNS:
        if re.search(pattern, text, re.IGNORECASE):
            flags.append(f'injection:{pattern}')
    # Gli URL hanno lunghi tratti alfanumerici: vanno tolti prima di cercare blob.
    without_urls = URL_RE.sub(' ', text)
    if BLOB_RE.search(without_urls):
        flags.append('blob:base64-like')
    return flags


def scan_url(url, sources):
    flags = []
    parts = urlparse(url)
    if len(parts.query) > MAX_QUERY:
        flags.append('url:long-query')
    if BLOB_RE.search(parts.query) or SEGMENT_BLOB_RE.search(parts.path):
        flags.append('url:blob')
    if url not in sources:
        flags.append('url:not-in-sources')
    return flags


def check_text(text, sources=None):
    flags = scan_text(text)
    if sources is not None:
        for url in URL_RE.findall(text):
            flags += [f'{f} ({url})' for f in scan_url(url, sources)]
    return flags


def main(argv):
    if len(argv) < 3:
        print(__doc__)
        return 2
    mode, target = argv[1], argv[2]
    sources_dir = argv[argv.index('--sources') + 1] if '--sources' in argv else None
    sources = declared_sources(sources_dir) if sources_dir else None

    if mode == 'text':
        text = pathlib.Path(target).read_text(encoding='utf-8')
        flags = check_text(text, sources)
    elif mode == 'fetch':
        if sources is None:
            print('fetch richiede --sources DIR')
            return 2
        flags = scan_url(target, sources)
    else:
        print(__doc__)
        return 2

    result = {'ok': not flags, 'flags': flags}
    print(json.dumps(result, ensure_ascii=False))
    return 0 if not flags else 1


if __name__ == '__main__':
    sys.exit(main(sys.argv))

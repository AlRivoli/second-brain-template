#!/usr/bin/env python3
"""Misura il tasso di blocco di content-guard sui casi in cases.json."""
import json
import pathlib
import sys
import tempfile

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parent.parent / 'scripts'))
import guard  # noqa: E402

cases = json.loads((pathlib.Path(__file__).parent / 'cases.json').read_text(encoding='utf-8'))
results = []
for case in cases:
    sources = set(case.get('sources', []))
    if case['kind'] == 'fetch':
        flags = guard.scan_url(case['input'], sources)
    elif case['kind'] == 'radar':
        flags = guard.check_text(case['input'], sources)
    else:
        flags = guard.check_text(case['input'], None)
    blocked = bool(flags)
    expected = case['label'] == 'malicious'
    results.append((case['id'], case['label'], blocked, flags))

mal = [r for r in results if r[1] == 'malicious']
cln = [r for r in results if r[1] == 'clean']
mal_rate = sum(r[2] for r in mal) / len(mal)
cln_rate = sum(not r[2] for r in cln) / len(cln)
print(f'malevoli bloccati: {sum(r[2] for r in mal)}/{len(mal)} = {mal_rate:.0%}')
print(f'puliti passati:    {sum(not r[2] for r in cln)}/{len(cln)} = {cln_rate:.0%}')
for cid, label, blocked, flags in results:
    wrong = (label == 'malicious') != blocked
    if wrong:
        print(f'  MANCATO/FALSO POSITIVO {cid} ({label}): flags={flags}')

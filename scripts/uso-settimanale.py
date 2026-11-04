#!/usr/bin/env python3
"""Report di uso dei comandi e delle skill, da ~/.claude/history.jsonl.

Stampa Markdown. Non rimuove nulla: i "mai usati" sono candidati, non certezze.
Uso: uso-settimanale.py [--history F] [--skills-dir D] [--commands-dir D] [--now ISO]
"""
import argparse
import collections
import datetime
import json
import pathlib
import sys

WINDOW_DAYS = 14
LIMIT_NOTE = ('Limite: le skill che scattano da sole, senza che tu le digiti, non compaiono nello storico. '
              'Un "mai usato" qui vuol dire solo "non digitato", non "inutile".')


def parse_now(value):
    if value:
        return datetime.datetime.fromisoformat(value)
    return datetime.datetime.now(datetime.timezone.utc)


def read_commands(history, since):
    """Conta i comandi digitati (prompt che iniziano con /) dopo 'since'."""
    counts = collections.Counter()
    projects = collections.Counter()
    if not history.exists():
        return None, None
    for line in history.read_text(encoding='utf-8', errors='replace').splitlines():
        try:
            item = json.loads(line)
        except json.JSONDecodeError:
            continue
        # Il timestamp è in millisecondi.
        when = datetime.datetime.fromtimestamp(item.get('timestamp', 0) / 1000, datetime.timezone.utc)
        if when < since:
            continue
        display = str(item.get('display', '')).strip()
        if not display.startswith('/'):
            continue
        name = display.split()[0]  # il nome, senza argomenti
        counts[name] += 1
        projects[pathlib.PurePosixPath(str(item.get('project', ''))).name or '-'] += 1
    return counts, projects


def installed_names(skills_dir, commands_dir):
    names = set()
    if skills_dir.exists():
        names.update(p.name for p in skills_dir.iterdir() if p.is_dir() and not p.name.startswith('.'))
    if commands_dir.exists():
        names.update(p.stem for p in commands_dir.glob('*.md'))
    return names


def build_report(history, skills_dir, commands_dir, now):
    since = now - datetime.timedelta(days=WINDOW_DAYS)
    counts, projects = read_commands(history, since)
    lines = [f'# Uso degli ultimi {WINDOW_DAYS} giorni', '']
    if counts is None:
        lines.append(f'Nessun dato di uso: storico non trovato in {history}.')
        lines += ['', LIMIT_NOTE]
        return '\n'.join(lines) + '\n'

    lines.append('## Comandi digitati')
    if counts:
        for name, n in counts.most_common():
            lines.append(f'- {name}: {n}')
    else:
        lines.append('- nessun comando digitato nel periodo.')

    lines += ['', '## Progetti', '']
    for name, n in projects.most_common():
        lines.append(f'- {name}: {n}')
    if not projects:
        lines.append('- nessun progetto nel periodo.')

    unused = sorted(name for name in installed_names(skills_dir, commands_dir) if f'/{name}' not in counts)
    lines += ['', '## Mai usati nel periodo (candidati, non rimozioni)', '']
    lines += [f'- {name}' for name in unused] or ['- nessuno.']

    lines += ['', '## Limiti', '', LIMIT_NOTE]
    return '\n'.join(lines) + '\n'


def main(argv):
    home = pathlib.Path.home() / '.claude'
    parser = argparse.ArgumentParser()
    parser.add_argument('--history', type=pathlib.Path, default=home / 'history.jsonl')
    parser.add_argument('--skills-dir', type=pathlib.Path, default=home / 'skills')
    parser.add_argument('--commands-dir', type=pathlib.Path, default=home / 'commands')
    parser.add_argument('--now', default=None)
    args = parser.parse_args(argv[1:])
    now = parse_now(args.now)
    if now.tzinfo is None:
        now = now.replace(tzinfo=datetime.timezone.utc)
    print(build_report(args.history, args.skills_dir, args.commands_dir, now), end='')
    return 0


if __name__ == '__main__':
    sys.exit(main(sys.argv))

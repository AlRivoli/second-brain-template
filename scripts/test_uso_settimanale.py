#!/usr/bin/env python3
"""Test di scripts/uso-settimanale.py su storico e cartelle temporanei."""
import json
import pathlib
import subprocess
import sys
import tempfile
import unittest
from datetime import datetime, timezone

SCRIPT = pathlib.Path(__file__).resolve().parent / 'uso-settimanale.py'
NOW = datetime(2026, 10, 22, 12, 0, tzinfo=timezone.utc)


def ms(days_ago):
    return int((NOW.timestamp() - days_ago * 86400) * 1000)


def entry(display, days_ago, project='/srv/x/progetto'):
    return json.dumps({'display': display, 'timestamp': ms(days_ago), 'project': project})


def run(history, skills, commands):
    result = subprocess.run(
        [sys.executable, str(SCRIPT), '--history', str(history), '--skills-dir', str(skills),
         '--commands-dir', str(commands), '--now', NOW.isoformat()],
        capture_output=True, text=True)
    return result.returncode, result.stdout + result.stderr


class UsoTest(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.root = pathlib.Path(self.tmp.name)
        self.skills = self.root / 'skills'
        self.commands = self.root / 'commands'
        self.skills.mkdir()
        self.commands.mkdir()

    def tearDown(self):
        self.tmp.cleanup()

    def write_history(self, lines):
        path = self.root / 'history.jsonl'
        path.write_text('\n'.join(lines) + '\n', encoding='utf-8')
        return path

    def test_conta_comandi_nella_finestra(self):
        history = self.write_history([
            entry('/morning', 1),
            entry('/morning', 2),
            entry('/morning', 30),          # fuori dalla finestra di 14 giorni
            entry('ciao senza slash', 1),   # non è un comando
        ])
        code, out = run(history, self.skills, self.commands)
        self.assertEqual(code, 0, out)
        self.assertIn('/morning: 2', out)
        self.assertNotIn('ciao', out)

    def test_argomenti_non_contano_nel_nome(self):
        history = self.write_history([entry('/nuovo-progetto prova-uno', 1)])
        code, out = run(history, self.skills, self.commands)
        self.assertIn('/nuovo-progetto: 1', out)

    def test_skill_installata_mai_usata_e_candidato(self):
        (self.skills / 'vecchia-skill').mkdir()
        history = self.write_history([entry('/morning', 1)])
        code, out = run(history, self.skills, self.commands)
        self.assertIn('vecchia-skill', out)
        self.assertIn('Mai usati', out)

    def test_storico_mancante_non_esplode(self):
        code, out = run(self.root / 'nessuno.jsonl', self.skills, self.commands)
        self.assertNotIn('Traceback', out)
        self.assertIn('storico non trovato', out)

    def test_timestamp_in_millisecondi(self):
        history = self.write_history([entry('/morning', 1)])
        code, out = run(history, self.skills, self.commands)
        self.assertIn('/morning: 1', out)

    def test_skill_senza_nome_di_comando_avvisa(self):
        (self.skills / 'skill-con-nome-diverso').mkdir()
        history = self.write_history([])
        code, out = run(history, self.skills, self.commands)
        self.assertIn('limite', out.lower())


if __name__ == '__main__':
    unittest.main()

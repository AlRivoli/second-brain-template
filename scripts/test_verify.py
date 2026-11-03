#!/usr/bin/env python3
"""Test di scripts/verify su vault temporanei."""
import pathlib
import subprocess
import sys
import tempfile
import unittest

VERIFY = pathlib.Path(__file__).resolve().parent / 'verify'

STATE_TEMPLATE = """# {{title}}

## Obiettivo attuale

## Dove sono

## Prossimi 3 passi

## Blocchi aperti

## Link utili
"""

GOOD_STATE = """# progetto-a
- **Repo:** nessuno
- **Aggiornato:** 2026-10-22
## Obiettivo attuale
Test.
## Dove sono
Test.
## Prossimi 3 passi
1. Test.
## Blocchi aperti
- nessuno
## Link utili
- nessuno
"""

GOOD_INDEX = """# Progetti attivi

| Progetto | Stack | Stato | Priorità | Ultimo aggiornamento |
|---|---|---|---|---|
| [[projects/progetto-a/STATE|progetto-a]] | Python | in corso | alta | 2026-10-22 |
"""


def make_vault(root, state=GOOD_STATE, index=GOOD_INDEX, extra=None):
    (root / 'templates').mkdir()
    (root / 'templates' / 'STATE.md').write_text(STATE_TEMPLATE, encoding='utf-8')
    (root / 'projects' / 'progetto-a').mkdir(parents=True)
    (root / 'projects' / 'INDEX.md').write_text(index, encoding='utf-8')
    (root / 'projects' / 'progetto-a' / 'STATE.md').write_text(state, encoding='utf-8')
    for name, text in (extra or {}).items():
        path = root / name
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(text, encoding='utf-8')


def run_verify(root):
    result = subprocess.run([sys.executable, str(VERIFY), str(root)], capture_output=True, text=True)
    return result.returncode, result.stdout + result.stderr


class VerifyTest(unittest.TestCase):
    def test_vault_valido_passa(self):
        with tempfile.TemporaryDirectory() as tmp:
            make_vault(pathlib.Path(tmp))
            code, out = run_verify(tmp)
            self.assertEqual(code, 0, out)

    def test_readme_che_non_cita_un_job_o_un_comando(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = pathlib.Path(tmp)
            make_vault(root)
            (root / 'scripts').mkdir(exist_ok=True)
            (root / 'scripts' / 'jobs.json').write_text('{"bozze": {}}', encoding='utf-8')
            (root / '.claude' / 'commands').mkdir(parents=True)
            (root / '.claude' / 'commands' / 'post.md').write_text('x', encoding='utf-8')
            (root / 'README.md').write_text('# Vault\n', encoding='utf-8')
            code, out = run_verify(tmp)
            self.assertEqual(code, 1)
            self.assertIn('non cita il job launchd bozze', out)
            self.assertIn('non cita il comando /post', out)
            (root / 'README.md').write_text('second-brain.bozze e /post', encoding='utf-8')
            code, out = run_verify(tmp)
            self.assertEqual(code, 0, out)

    def test_vault_vuoto_non_esplode(self):
        with tempfile.TemporaryDirectory() as tmp:
            code, out = run_verify(tmp)
            self.assertEqual(code, 1)
            self.assertIn('INDEX.md', out)
            self.assertNotIn('Traceback', out)

    def test_state_troppo_lungo(self):
        with tempfile.TemporaryDirectory() as tmp:
            make_vault(pathlib.Path(tmp), state=GOOD_STATE + '\n'.join(['riga'] * 20))
            code, out = run_verify(tmp)
            self.assertEqual(code, 1)
            self.assertIn('righe', out)

    def test_riga_index_senza_cartella(self):
        index = GOOD_INDEX + '| [[fantasma]] | Go | ferma | bassa | 2026-10-22 |\n'
        with tempfile.TemporaryDirectory() as tmp:
            make_vault(pathlib.Path(tmp), index=index)
            code, out = run_verify(tmp)
            self.assertEqual(code, 1)
            self.assertIn('fantasma', out)

    def test_cartella_fuori_da_index(self):
        with tempfile.TemporaryDirectory() as tmp:
            make_vault(pathlib.Path(tmp))
            (pathlib.Path(tmp) / 'projects' / 'nuovo').mkdir()
            code, out = run_verify(tmp)
            self.assertEqual(code, 1)
            self.assertIn('nuovo', out)

    def test_data_index_diversa_da_state(self):
        index = GOOD_INDEX.replace('2026-10-22', '2026-10-01')
        with tempfile.TemporaryDirectory() as tmp:
            make_vault(pathlib.Path(tmp), index=index)
            code, out = run_verify(tmp)
            self.assertEqual(code, 1)
            self.assertIn('Aggiornato', out)

    def test_sezione_obbligatoria_mancante(self):
        state = GOOD_STATE.replace('## Blocchi aperti\n- nessuno\n', '')
        with tempfile.TemporaryDirectory() as tmp:
            make_vault(pathlib.Path(tmp), state=state)
            code, out = run_verify(tmp)
            self.assertEqual(code, 1)
            self.assertIn('Blocchi aperti', out)

    def test_wikilink_rotto(self):
        with tempfile.TemporaryDirectory() as tmp:
            make_vault(pathlib.Path(tmp), extra={'daily/2026-10-22.md': 'Vedi [[nota-inesistente]].'})
            code, out = run_verify(tmp)
            self.assertEqual(code, 1)
            self.assertIn('nota-inesistente', out)

    def test_wikilink_con_alias_valido(self):
        with tempfile.TemporaryDirectory() as tmp:
            make_vault(pathlib.Path(tmp), extra={'daily/2026-10-22.md': 'Vedi [[projects/progetto-a/STATE|il progetto]].'})
            code, out = run_verify(tmp)
            self.assertEqual(code, 0, out)

    def test_state_mancante_segnalato(self):
        with tempfile.TemporaryDirectory() as tmp:
            make_vault(pathlib.Path(tmp))
            (pathlib.Path(tmp) / 'projects' / 'nuovo').mkdir()
            (pathlib.Path(tmp) / 'projects' / 'INDEX.md').write_text(
                GOOD_INDEX + '| [[projects/nuovo/STATE|nuovo]] | Go | ferma | bassa | 2026-10-22 |\n', encoding='utf-8')
            code, out = run_verify(tmp)
            self.assertEqual(code, 1)
            self.assertIn('projects/nuovo/STATE.md: manca', out)

    def test_wikilink_in_blocco_di_codice_ignorato(self):
        text = 'Esempio:\n```\n[[nota-di-esempio]]\n```\n'
        with tempfile.TemporaryDirectory() as tmp:
            make_vault(pathlib.Path(tmp), extra={'daily/2026-10-22.md': text})
            code, out = run_verify(tmp)
            self.assertEqual(code, 0, out)

    def test_allegato_esistente_valido(self):
        with tempfile.TemporaryDirectory() as tmp:
            make_vault(pathlib.Path(tmp), extra={'daily/2026-10-22.md': 'Vedi [[foto.png]].', 'inbox/foto.png': 'x'})
            code, out = run_verify(tmp)
            self.assertEqual(code, 0, out)

    def test_maiuscole_non_contano(self):
        with tempfile.TemporaryDirectory() as tmp:
            make_vault(pathlib.Path(tmp), extra={'daily/2026-10-22.md': 'Vedi [[Projects/Progetto-A/STATE]].'})
            code, out = run_verify(tmp)
            self.assertEqual(code, 0, out)

    def test_alias_con_pipe_escapato_in_tabella(self):
        index = GOOD_INDEX.replace('[[projects/progetto-a/STATE|progetto-a]]', '[[projects/progetto-a/STATE\\|progetto-a]]')
        with tempfile.TemporaryDirectory() as tmp:
            make_vault(pathlib.Path(tmp), index=index)
            code, out = run_verify(tmp)
            self.assertEqual(code, 0, out)

    def test_riga_index_senza_data(self):
        index = GOOD_INDEX.replace('| 2026-10-22 |', '|  |')
        with tempfile.TemporaryDirectory() as tmp:
            make_vault(pathlib.Path(tmp), index=index)
            code, out = run_verify(tmp)
            self.assertEqual(code, 1)
            self.assertIn('progetto-a', out)

    def test_file_non_utf8_non_esplode(self):
        with tempfile.TemporaryDirectory() as tmp:
            make_vault(pathlib.Path(tmp))
            (pathlib.Path(tmp) / 'daily').mkdir()
            (pathlib.Path(tmp) / 'daily' / '2026-10-22.md').write_bytes(b'\xff\xfe [[x]]')
            code, out = run_verify(tmp)
            self.assertNotIn('Traceback', out)


if __name__ == '__main__':
    unittest.main()

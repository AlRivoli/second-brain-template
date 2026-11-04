#!/usr/bin/env python3
"""Test del confronto tra skill installata e skill nel repo di origine, senza rete e senza skillspector."""
import importlib.util
import json
import tempfile
from datetime import datetime
import unittest
from pathlib import Path

RADICE = Path(__file__).resolve().parent.parent
spec = importlib.util.spec_from_file_location("controllo_skill", RADICE / "scripts" / "controllo-skill.py")
cs = importlib.util.module_from_spec(spec)
spec.loader.exec_module(cs)


def cartella(**file):
    d = Path(tempfile.mkdtemp())
    for nome, testo in file.items():
        (d / nome).write_text(testo, encoding="utf-8")
    return d


class StatoSkillTest(unittest.TestCase):
    def test_uguale_con_lock_allineato(self):
        s = cs.stato_skill(cartella(a="1"), cartella(a="1"), "h1", "h1")
        self.assertEqual(s, {"stato": "uguale", "lockAllineato": True})

    def test_uguale_ma_lock_obsoleto(self):
        # installata a mano all'ultima versione: nessun aggiornamento, il lock non lo sa
        s = cs.stato_skill(cartella(a="2"), cartella(a="2"), "h1", "h2")
        self.assertEqual(s, {"stato": "uguale", "lockAllineato": False})

    def test_diversa_con_repo_invariato_e_modificata_in_locale(self):
        s = cs.stato_skill(cartella(a="locale"), cartella(a="remota"), "h1", "h1")
        self.assertEqual(s, {"stato": "modificata", "lockAllineato": True})
        self.assertTrue(cs.azione("modificata", None).startswith("nessuna"))

    def test_diversa_e_nuova(self):
        self.assertEqual(cs.stato_skill(cartella(a="1"), cartella(a="2"), "h1", "h2")["stato"], "nuova")

    def test_remota_assente_e_installata_assente(self):
        self.assertEqual(cs.stato_skill(cartella(a="1"), None, "h", "h")["stato"], "rimossa")
        self.assertEqual(cs.stato_skill(None, cartella(a="1"), "h", "h")["stato"], "non installata")

    def test_hash_ignora_git(self):
        a, b = cartella(a="1"), cartella(a="1")
        (b / ".git").mkdir()
        (b / ".git" / "x").write_text("rumore")
        self.assertEqual(cs.hash_cartella(a), cs.hash_cartella(b))


class AzioneTest(unittest.TestCase):
    def test_tabella_di_scan_before_install(self):
        ok = {"severita": "LOW", "raccomandazione": "SAFE"}
        self.assertTrue(cs.azione("nuova", ok).startswith("aggiornare"))
        self.assertTrue(cs.azione("nuova", {"severita": "HIGH", "raccomandazione": "REVIEW"}).startswith("chiedere conferma"))
        self.assertTrue(cs.azione("nuova", {"severita": "MEDIUM", "raccomandazione": "CAUTION", "gravitaMax": "HIGH"}).startswith("chiedere conferma"))
        self.assertIn("installa lo stesso", cs.azione("nuova", {"severita": "CRITICAL", "raccomandazione": "DO_NOT_INSTALL"}))
        self.assertIn("installa lo stesso", cs.azione("nuova", {"severita": "LOW", "raccomandazione": "DO_NOT_INSTALL"}))
        self.assertIn("non riuscita", cs.azione("nuova", {"errore": "OSError"}))
        self.assertIn("non riuscita", cs.azione("nuova", None))
        self.assertTrue(cs.azione("uguale", None).startswith("nessuna"))


class InstallaTest(unittest.TestCase):
    def test_sostituisce_con_backup_e_aggiorna_il_lock(self):
        radice = Path(tempfile.mkdtemp())
        installata = radice / "skills" / "x"
        installata.mkdir(parents=True)
        (installata / "SKILL.md").write_text("vecchia")
        remota = cartella(**{"SKILL.md": "nuova"})
        (remota / ".git").mkdir()
        lock = radice / "lock.json"
        lock.write_text(json.dumps({"version": 3, "skills": {"x": {"skillFolderHash": "h1", "updatedAt": "old", "source": "o/r"}}}))
        backup = cs.installa("x", remota, installata, lock, radice / "bk", "h2", datetime(2026, 10, 27, 18, 0, 0))
        self.assertEqual((installata / "SKILL.md").read_text(), "nuova")
        self.assertFalse((installata / ".git").exists())
        self.assertEqual((backup / "SKILL.md").read_text(), "vecchia")
        self.assertFalse((radice / "skills" / "x.nuova").exists())
        dati = json.loads(lock.read_text())
        self.assertEqual((dati["version"], dati["skills"]["x"]["skillFolderHash"], dati["skills"]["x"]["source"]), (3, "h2", "o/r"))
        self.assertNotEqual(dati["skills"]["x"]["updatedAt"], "old")
        self.assertEqual(json.loads(lock.with_name("lock.json.bak").read_text())["skills"]["x"]["skillFolderHash"], "h1")

    def test_non_tocca_una_skill_installata_a_mano(self):
        radice = Path(tempfile.mkdtemp())
        (radice / "x").mkdir()
        lock = radice / "lock.json"
        lock.write_text(json.dumps({"skills": {"x": {"sourceUrl": "u", "skillPath": "x/SKILL.md"}}}))
        with self.assertRaises(ValueError):
            cs.aggiorna("x", "", lock_file=lock, installate=radice, backup_dir=radice / "bk")
        with self.assertRaises(LookupError):
            cs.aggiorna("assente", "", lock_file=lock, installate=radice, backup_dir=radice / "bk")


if __name__ == "__main__":
    unittest.main()

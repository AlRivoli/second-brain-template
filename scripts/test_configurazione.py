#!/usr/bin/env python3
"""Test dell'inventario: legge nomi e versioni, mai i valori che possono contenere segreti."""
import importlib.util
import json
import tempfile
import unittest
from pathlib import Path

RADICE = Path(__file__).resolve().parent.parent
spec = importlib.util.spec_from_file_location("configurazione", RADICE / "scripts" / "dashboard" / "configurazione.py")
cfg = importlib.util.module_from_spec(spec)
spec.loader.exec_module(cfg)


def scrivi(percorso, dati):
    percorso.parent.mkdir(parents=True, exist_ok=True)
    percorso.write_text(json.dumps(dati) if not isinstance(dati, str) else dati, encoding="utf-8")


class ConfigurazioneTest(unittest.TestCase):
    def setUp(self):
        self.home = Path(tempfile.mkdtemp())
        self.prog = Path(tempfile.mkdtemp())
        scrivi(self.home / ".claude.json", {"mcpServers": {"db": {"command": "x", "env": {"TOKEN": "SEGRETO-1"}}}})
        scrivi(self.home / ".claude" / "settings.json", {"enabledPlugins": {"p@m": True, "q@m": False}, "skillOverrides": {"b": "off"}})
        scrivi(self.home / ".agents" / ".skill-lock.json", {"skills": {"a": {"source": "o/r", "updatedAt": "2026-10-08T10:00:00Z", "skillFolderHash": "abcdef123456"},
                                                                         "m": {"source": "o/r", "skillFolderHash": "ffff"}}})
        base = self.home / ".claude" / "skills"
        (self.home / ".agents" / "skills" / "a").mkdir(parents=True)
        (self.home / ".agents" / "skills" / "b").mkdir(parents=True)
        (base).mkdir(parents=True, exist_ok=True)
        (base / "a").symlink_to(self.home / ".agents" / "skills" / "a")
        (base / "b").symlink_to(self.home / ".agents" / "skills" / "b")
        (base / "m").mkdir()                      # nel lock ma installata a mano: lock obsoleto
        (base / "x").mkdir()                      # fuori dal lock
        inst = self.home / "plugin-p"
        scrivi(inst / ".mcp.json", {"mcpServers": {"web": {"url": "https://x", "headers": {"Authorization": "SEGRETO-2"}}}})
        scrivi(inst / "hooks" / "hooks.json", {"hooks": {"SessionStart": []}})
        (inst / "skills" / "s1").mkdir(parents=True)
        scrivi(self.home / ".claude" / "plugins" / "installed_plugins.json",
               {"plugins": {"p@m": [{"scope": "user", "version": "1.2.3", "installPath": str(inst), "lastUpdated": "2026-10-01T00:00:00Z"}]}})
        scrivi(self.prog / ".mcp.json", {"mcpServers": {"locale": {"command": "y", "env": {"K": "SEGRETO-3"}}}})
        scrivi(self.prog / ".claude" / "settings.json", {"enabledPlugins": {"p@m": True}, "hooks": {"Stop": []}})
        (self.prog / ".claude" / "skills" / "g").mkdir(parents=True)
        scrivi(self.prog / ".claude" / "commands" / "c.md", "x")
        self.out = cfg.raccogli([("prog", self.prog)], None, self.home)

    def test_skill_tracciate_a_mano_e_disattivate(self):
        per = {s["nome"]: s for s in self.out["globale"]["skill"]}
        self.assertEqual((per["a"]["tracciata"], per["a"]["hash"], per["a"]["aggiornata"]), (True, "abcdef1", "2026-10-08"))
        self.assertFalse(per["b"]["attiva"])
        self.assertFalse(per["x"]["tracciata"])
        self.assertTrue(per["m"]["lockObsoleto"])

    def test_plugin_con_hook_mcp_e_skill(self):
        p = self.out["globale"]["plugin"]
        self.assertEqual([(x["nome"], x["versione"], x["attivo"], x["hook"], x["mcp"], x["skill"]) for x in p],
                         [("p", "1.2.3", True, ["SessionStart"], ["web"], ["s1"])])

    def test_progetto(self):
        p = self.out["progetti"][0]
        self.assertEqual((p["skill"], p["comandi"], p["hook"], p["mcp"]), (["g"], ["c"], ["Stop"], ["locale"]))
        self.assertEqual(self.out["globale"]["mcp"], ["db"])

    def test_nessun_segreto_nell_output(self):
        testo = json.dumps(self.out)
        for segreto in ("SEGRETO-1", "SEGRETO-2", "SEGRETO-3", "env", "headers", "Authorization", "https://x"):
            self.assertNotIn(segreto, testo)

    def leggi_settings(self):
        return json.loads((self.home / ".claude" / "settings.json").read_text(encoding="utf-8"))

    def test_disattiva_e_riattiva_una_skill(self):
        cfg.imposta_interruttore("skill", "a", False, self.home)
        self.assertEqual(self.leggi_settings()["skillOverrides"], {"b": "off", "a": "off"})
        cfg.imposta_interruttore("skill", "b", True, self.home)
        s = self.leggi_settings()
        self.assertEqual(s["skillOverrides"], {"a": "off"})
        self.assertEqual(s["enabledPlugins"], {"p@m": True, "q@m": False})  # il resto resta com'era
        self.assertTrue((self.home / ".claude" / "settings.json.bak").exists())

    def test_attiva_e_disattiva_un_plugin(self):
        cfg.imposta_interruttore("plugin", "p@m", False, self.home)
        self.assertFalse(self.leggi_settings()["enabledPlugins"]["p@m"])

    def test_nomi_non_installati_si_rifiutano(self):
        for tipo, nome in (("skill", "inventata"), ("plugin", "x@y"), ("plugin", "p")):
            with self.assertRaises(LookupError):
                cfg.imposta_interruttore(tipo, nome, False, self.home)
        with self.assertRaises(ValueError):
            cfg.imposta_interruttore("hook", "a", False, self.home)

    def test_settings_rotto_non_si_riscrive(self):
        file = self.home / ".claude" / "settings.json"
        file.write_text("{non json", encoding="utf-8")
        with self.assertRaises(ValueError):
            cfg.imposta_interruttore("skill", "a", False, self.home)
        self.assertEqual(file.read_text(encoding="utf-8"), "{non json")

    def test_file_assenti_non_rompono(self):
        vuoto = cfg.raccogli([("x", Path("/nonexistent"))], None, Path(tempfile.mkdtemp()))
        self.assertEqual(vuoto["globale"]["skill"], [])
        self.assertFalse(vuoto["progetti"][0]["esiste"])


if __name__ == "__main__":
    unittest.main()

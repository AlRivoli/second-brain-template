import importlib.util
import json
import shutil
import sys
import tempfile
import unittest
from unittest import mock
from pathlib import Path

RADICE = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(RADICE))
import moduli  # noqa: E402

spec = importlib.util.spec_from_file_location("setup_wizard", RADICE / "setup.py")
setup = importlib.util.module_from_spec(spec)
spec.loader.exec_module(setup)


def vault(d):
    d = Path(d)
    shutil.copytree(RADICE / "modules", d / "modules")
    (d / "memory").mkdir()
    (d / "memory" / "about-me.example.md").write_text("<your name>, <your role>\n", encoding="utf-8")
    (d / "CLAUDE.md").write_text("<your name>, <your role>. Resto.\n", encoding="utf-8")
    (d / ".claude").mkdir()
    (d / ".claude" / "settings.json").write_text(json.dumps({"permissions": {"deny": ["Bash(git push *)"], "allow": ["Edit(/daily/**)"]}}), encoding="utf-8")
    (d / ".gitignore").write_text(".DS_Store\n", encoding="utf-8")
    return d


def lancia(d, risposte, *argv):
    file = Path(d) / "risposte.json"
    file.write_text(json.dumps(risposte), encoding="utf-8")
    return setup.main(["--answers", str(file), *argv], radice=Path(d))


class ManifestTest(unittest.TestCase):
    def test_i_moduli_del_template_sono_validi_e_core_e_il_primo(self):
        tutti = moduli.carica(RADICE)
        self.assertEqual(next(iter(tutti)), "core")
        self.assertIn("riservata", tutti)

    def test_azione_non_ammessa_o_dipendenza_inesistente_si_rifiutano(self):
        base = {"id": "x", "titolo": "x", "descrizione": "x", "sempre": True, "azioni": []}
        self.assertEqual(moduli.errori_manifest(base, {"x"}), [])
        self.assertTrue(moduli.errori_manifest({**base, "azioni": [{"tipo": "esegui", "comando": "rm -rf /"}]}, {"x"}))
        self.assertTrue(moduli.errori_manifest({**base, "richiede": ["fantasma"]}, {"x"}))
        self.assertTrue(moduli.errori_manifest({**base, "sempre": False}, {"x"}))  # facoltativo senza domanda di attivazione

    def test_dipendenze_circolari_e_id_diverso_dalla_cartella(self):
        with tempfile.TemporaryDirectory() as d:
            for nome, richiede in (("a", ["b"]), ("b", ["a"])):
                (Path(d) / "modules" / nome).mkdir(parents=True)
                (Path(d) / "modules" / nome / "module.json").write_text(json.dumps(
                    {"id": nome, "titolo": "t", "descrizione": "d", "sempre": True, "richiede": richiede, "azioni": []}), encoding="utf-8")
            with self.assertRaises(ValueError):
                moduli.carica(d)
            (Path(d) / "modules" / "a" / "module.json").write_text(json.dumps({"id": "altro"}), encoding="utf-8")
            with self.assertRaises(ValueError):
                moduli.carica(d)

    def test_testo_in_due_lingue_con_ripiego_in_inglese(self):
        self.assertEqual(moduli.testo({"en": "a", "it": "b"}, "it"), "b")
        self.assertEqual(moduli.testo({"en": "a"}, "it"), "a")


class CartellaTest(unittest.TestCase):
    def test_nomi_accettati(self):
        self.assertEqual(moduli.valida_cartella("projects/_private"), "projects/_private")
        self.assertEqual(moduli.valida_cartella(" documenti-riservati/ "), "documenti-riservati")
        self.assertEqual(moduli.valida_cartella("note\\clienti-x"), "note/clienti-x")

    def test_nomi_pericolosi_si_rifiutano(self):
        for nome in ("", "..", "../fuori", "/etc/passwd", "a/../../b", "C:\\Windows", "~/x", "docs", "work", "src", "projects/docs", ".git/hooks",
                     ".claude", "scripts", "a*b-cartella", "x{y}zzzz", "uno;due-tre", "nome con spazio"):
            with self.assertRaises(ValueError, msg=repr(nome)):
                moduli.valida_cartella(nome)

    def test_le_regole_deny_sono_tre_e_usano_il_nome(self):
        self.assertEqual(moduli.regole_deny("projects/_private"), ["Read(/projects/_private/**)", "Edit(/projects/_private/**)", "Bash(*_private*)"])


class RiservataTest(unittest.TestCase):
    def test_crea_cartella_gitignore_regole_e_config(self):
        with tempfile.TemporaryDirectory() as t:
            d = vault(t)
            lancia(d, {"nome": "Ada", "lingua": "en", "moduli": {"riservata": {"attivo": True, "cartella": "documenti-protetti"}}})
            self.assertTrue((d / "documenti-protetti").is_dir())
            self.assertIn("documenti-protetti/", (d / ".gitignore").read_text(encoding="utf-8").splitlines())
            deny = json.loads((d / ".claude" / "settings.json").read_text(encoding="utf-8"))["permissions"]
            self.assertIn("Bash(*documenti-protetti*)", deny["deny"])
            self.assertIn("Bash(git push *)", deny["deny"])  # le regole che c'erano restano
            self.assertEqual(deny["allow"], ["Edit(/daily/**)"])
            cfg = json.loads((d / "config.json").read_text(encoding="utf-8"))
            self.assertEqual(cfg["moduli"]["riservata"], {"attivo": True, "cartella": "documenti-protetti"})
            self.assertEqual(cfg["nome"], "Ada")

    def test_rilanciarlo_non_duplica_niente(self):
        with tempfile.TemporaryDirectory() as t:
            d = vault(t)
            r = {"nome": "Ada", "moduli": {"riservata": {"attivo": True}}}
            lancia(d, r)
            lancia(d, r)
            self.assertEqual((d / ".gitignore").read_text(encoding="utf-8").splitlines().count("projects/_private/"), 1)
            deny = json.loads((d / ".claude" / "settings.json").read_text(encoding="utf-8"))["permissions"]["deny"]
            self.assertEqual(len(deny), len(set(deny)))

    def test_senza_il_modulo_non_si_crea_niente(self):
        with tempfile.TemporaryDirectory() as t:
            d = vault(t)
            lancia(d, {"nome": "Ada"})
            self.assertFalse((d / "projects").exists())
            self.assertEqual((d / ".gitignore").read_text(encoding="utf-8"), ".DS_Store\n")

    def test_una_cartella_pericolosa_in_un_file_di_risposte_ferma_tutto_prima_di_scrivere(self):
        with tempfile.TemporaryDirectory() as t:
            d = vault(t)
            with self.assertRaises(SystemExit):
                lancia(d, {"nome": "Ada", "moduli": {"riservata": {"attivo": True, "cartella": "../fuori"}}})
            self.assertFalse((d / "config.json").exists())

    def test_dry_run_non_scrive_niente(self):
        with tempfile.TemporaryDirectory() as t:
            d = vault(t)
            lancia(d, {"nome": "Ada", "moduli": {"riservata": {"attivo": True}}}, "--dry-run")
            self.assertFalse((d / "config.json").exists())
            self.assertFalse((d / "projects").exists())

    def test_un_settings_non_valido_non_si_sovrascrive(self):
        with tempfile.TemporaryDirectory() as t:
            d = vault(t)
            (d / ".claude" / "settings.json").write_text("{ non json", encoding="utf-8")
            with self.assertRaises(SystemExit):
                lancia(d, {"nome": "Ada", "moduli": {"riservata": {"attivo": True}}})
            self.assertEqual((d / ".claude" / "settings.json").read_text(encoding="utf-8"), "{ non json")


class AddTest(unittest.TestCase):
    def test_add_senza_config_chiede_prima_il_setup(self):
        with tempfile.TemporaryDirectory() as t:
            d = vault(t)
            with self.assertRaises(SystemExit):
                setup.main(["--add", "riservata", "--yes"], radice=d)

    def test_add_aggiunge_un_modulo_senza_toccare_il_core(self):
        with tempfile.TemporaryDirectory() as t:
            d = vault(t)
            lancia(d, {"nome": "Ada", "ruolo": "dev"})
            (d / "memory" / "about-me.md").write_text("MIO", encoding="utf-8")
            setup.main(["--add", "riservata", "--yes"], radice=d)
            self.assertTrue((d / "projects" / "_private").is_dir())
            self.assertEqual((d / "memory" / "about-me.md").read_text(encoding="utf-8"), "MIO")
            self.assertEqual(json.loads((d / "config.json").read_text(encoding="utf-8"))["nome"], "Ada")

    def test_modulo_sconosciuto(self):
        with tempfile.TemporaryDirectory() as t:
            with self.assertRaises(SystemExit):
                setup.main(["--add", "fantasma", "--yes"], radice=vault(t))


class ConfigTest(unittest.TestCase):
    def test_config_set_tiene_i_valori_esistenti_salvo_forza(self):
        with tempfile.TemporaryDirectory() as t:
            moduli.applica({"tipo": "config_set", "valori": {"nome": "Ada", "moduli": {"a": {"x": 1}}}}, t)
            moduli.applica({"tipo": "config_set", "valori": {"nome": "Altro", "moduli": {"a": {"x": 2, "y": 3}}}}, t)
            cfg = json.loads((Path(t) / "config.json").read_text(encoding="utf-8"))
            self.assertEqual((cfg["nome"], cfg["moduli"]["a"]), ("Ada", {"x": 1, "y": 3}))
            moduli.applica({"tipo": "config_set", "forza": True, "valori": {"nome": "Altro"}}, t)
            self.assertEqual(json.loads((Path(t) / "config.json").read_text(encoding="utf-8"))["nome"], "Altro")



RADAR = {"attivo": True, "temi": "databases, privacy", "feeds": "https://a.example/rss https://b.example/atom", "automazione": "interno",
         "radar_embedding": "none", "radar_giudizio": "ollama:qwen3:8b"}


class RadarTest(unittest.TestCase):
    def test_scrive_temi_feed_e_scelte_dei_modelli(self):
        with tempfile.TemporaryDirectory() as t:
            d = vault(t)
            lancia(d, {"nome": "Ada", "moduli": {"radar": RADAR}})
            self.assertEqual((d / "memory" / "feeds.md").read_text(encoding="utf-8").splitlines()[-2:], ["- https://a.example/rss", "- https://b.example/atom"])
            self.assertIn("- privacy", (d / "memory" / "radar-topics.md").read_text(encoding="utf-8"))
            cfg = json.loads((d / "config.json").read_text(encoding="utf-8"))
            self.assertEqual(cfg["modelli"], {"radar_embedding": "none", "radar_giudizio": "ollama:qwen3:8b"})
            self.assertEqual(cfg["moduli"]["radar"], {"attivo": True, "automazione": "interno"})
            self.assertTrue((d / "inbox").is_dir() and (d / "radar").is_dir())

    def test_il_core_non_crea_i_temi_da_solo_e_un_file_esistente_non_si_tocca(self):
        with tempfile.TemporaryDirectory() as t:
            d = vault(t)
            (d / "memory" / "radar-topics.example.md").write_text("esempio\n", encoding="utf-8")
            lancia(d, {"nome": "Ada"})
            self.assertFalse((d / "memory" / "radar-topics.md").exists())
            (d / "memory").joinpath("feeds.md").write_text("MIEI", encoding="utf-8")
            setup.main(["--add", "radar", "--yes"], radice=d)  # con i valori di fabbrica
            self.assertEqual((d / "memory" / "feeds.md").read_text(encoding="utf-8"), "MIEI")
            self.assertEqual(json.loads((d / "config.json").read_text(encoding="utf-8"))["modelli"]["radar_giudizio"], "none")

    def test_risposte_non_valide_si_rifiutano_prima_di_scrivere(self):
        for campo, valore in (("radar_embedding", "claude"), ("radar_giudizio", "ollama:x; rm -rf /"), ("radar_giudizio", "openai:gpt"),
                              ("radar_giudizio", "ollama:"), ("feeds", "ftp://a.example/rss"), ("feeds", "file:///etc/passwd"), ("automazione", "zapier")):
            with tempfile.TemporaryDirectory() as t:
                d = vault(t)
                with self.assertRaises(SystemExit, msg="%s=%s" % (campo, valore)):
                    lancia(d, {"nome": "Ada", "moduli": {"radar": {**RADAR, campo: valore}}})
                self.assertFalse((d / "config.json").exists())

    def test_scrivi_file_non_esce_dal_vault(self):
        with tempfile.TemporaryDirectory() as t:
            for percorso in ("../fuori.md", "/etc/x", ".git/hooks/pre-commit", ".claude/settings.json", "a/../../b", "~/x"):
                with self.assertRaises(ValueError, msg=percorso):
                    moduli.applica({"tipo": "scrivi_file", "percorso": percorso, "contenuto": "x"}, t)

    def test_i_job_del_radar_si_registrano_solo_se_il_modulo_e_attivo(self):
        spec = importlib.util.spec_from_file_location("install_jobs", RADICE / "install_jobs.py")
        ij = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(ij)
        jobs = json.loads((RADICE / "scripts" / "jobs.json").read_text(encoding="utf-8"))
        self.assertNotIn("radar", ij.seleziona(jobs, "linux"))
        attivo = {"moduli": {"radar": {"attivo": True, "automazione": "interno"}}}
        self.assertTrue({"radar", "feed"} <= set(ij.seleziona(jobs, "linux", config=attivo)))
        con_n8n = {"moduli": {"radar": {"attivo": True, "automazione": "n8n"}}}
        scelti = set(ij.seleziona(jobs, "linux", config=con_n8n))
        self.assertIn("radar", scelti)
        self.assertNotIn("feed", scelti)  # con n8n il raccoglitore interno non si registra



class AssistenteTest(unittest.TestCase):
    def test_scrive_modello_calendario_e_consenso_come_booleano(self):
        with tempfile.TemporaryDirectory() as t:
            d = vault(t)
            lancia(d, {"nome": "Ada", "moduli": {"assistente": {"attivo": True, "assistente": "claude", "calendario": "ics", "calendario_al_cloud": True}}})
            cfg = json.loads((d / "config.json").read_text(encoding="utf-8"))
            self.assertEqual(cfg["moduli"]["assistente"], {"attivo": True, "calendario_al_cloud": True})
            self.assertEqual(cfg["modelli"]["assistente"], "claude")
            self.assertEqual(cfg["calendario"], {"provider": "ics"})

    def test_di_fabbrica_niente_modello_e_niente_invio_al_cloud(self):
        with tempfile.TemporaryDirectory() as t:
            d = vault(t)
            lancia(d, {"nome": "Ada", "moduli": {"assistente": {"attivo": True}}})
            cfg = json.loads((d / "config.json").read_text(encoding="utf-8"))
            self.assertIs(cfg["moduli"]["assistente"]["calendario_al_cloud"], False)
            self.assertEqual(cfg["modelli"]["assistente"], "none")

    def test_il_calendario_di_macos_si_rifiuta_fuori_da_macos(self):
        with tempfile.TemporaryDirectory() as t:
            d = vault(t)
            risposte = {"nome": "Ada", "moduli": {"assistente": {"attivo": True, "calendario": "macos"}}}
            with mock.patch.object(setup.sys, "platform", "linux"), self.assertRaises(SystemExit):
                lancia(d, risposte)
            with mock.patch.object(setup.sys, "platform", "darwin"):
                lancia(d, risposte)
            self.assertEqual(json.loads((d / "config.json").read_text(encoding="utf-8"))["calendario"]["provider"], "macos")


class WindowsTest(unittest.TestCase):
    """Trovati provando il template su Windows."""

    def test_i_file_si_scrivono_con_a_capo_lf(self):
        """Su Windows write_text li fa CRLF e git li vede cambiati."""
        with tempfile.TemporaryDirectory() as t:
            moduli.scrivi(Path(t) / "x.json", "a\nb\n")
            self.assertEqual((Path(t) / "x.json").read_bytes(), b"a\nb\n")
        for file in ("moduli.py", "setup.py"):
            self.assertNotIn(".write_text(", (RADICE / file).read_text(encoding="utf-8"), "usa moduli.scrivi: a capo LF su ogni sistema")

    def test_il_file_delle_risposte_puo_avere_il_bom(self):
        """PowerShell 5.1 con Out-File -Encoding utf8 scrive sempre il BOM."""
        with tempfile.TemporaryDirectory() as t:
            d = vault(t)
            file = d / "risposte.json"
            file.write_bytes(b"\xef\xbb\xbf" + json.dumps({"nome": "Ada"}).encode("utf-8"))
            setup.main(["--answers", str(file), "--yes"], radice=d)
            self.assertEqual(json.loads((d / "config.json").read_text(encoding="utf-8"))["nome"], "Ada")


class ScaffoldTest(unittest.TestCase):
    def prepara(self, d):
        shutil.copytree(RADICE / "scaffold", d / "scaffold")

    def test_crea_registro_vuoto_profili_e_nessun_dato_personale(self):
        with tempfile.TemporaryDirectory() as t:
            d = vault(t)
            self.prepara(d)
            lancia(d, {"nome": "Ada", "moduli": {"scaffold": {"attivo": True}}})
            for f in ("registro", "ignorati"):
                self.assertTrue((d / "scaffold" / (f + ".md")).is_file())
            for f in ("personal", "lavoro"):
                self.assertTrue((d / "scaffold" / "profili" / (f + ".md")).is_file())
            righe = [r for r in (d / "scaffold" / "registro.md").read_text(encoding="utf-8").splitlines() if r.startswith("|")]
            self.assertEqual(len(righe), 2)  # solo intestazione e separatore
            self.assertEqual(json.loads((d / "config.json").read_text(encoding="utf-8"))["moduli"]["scaffold"], {"attivo": True})

    def test_il_testo_dell_hook_non_viene_scritto_in_home(self):
        testo = (RADICE / "scaffold" / "hook-avvio.example.md").read_text(encoding="utf-8")
        self.assertIn("~/.claude/settings.json", testo)
        self.assertIn("a mano", testo)


class BozzeServiziTest(unittest.TestCase):
    def test_bozze_crea_cartelle_stato_e_scelta_dei_social(self):
        with tempfile.TemporaryDirectory() as t:
            d = vault(t)
            lancia(d, {"nome": "Ada", "moduli": {"bozze": {"attivo": True, "social": "linkedin"}}})
            self.assertTrue((d / "content" / "linkedin").is_dir() and (d / "content" / "instagram").is_dir())
            self.assertEqual(json.loads((d / "content" / "stato.json").read_text(encoding="utf-8")), {})
            self.assertEqual(json.loads((d / "config.json").read_text(encoding="utf-8"))["moduli"]["bozze"], {"attivo": True, "social": "linkedin"})

    def test_social_non_valido_si_rifiuta(self):
        with tempfile.TemporaryDirectory() as t:
            d = vault(t)
            with self.assertRaises(SystemExit):
                lancia(d, {"nome": "Ada", "moduli": {"bozze": {"attivo": True, "social": "tiktok"}}})
            self.assertFalse((d / "config.json").exists())

    def test_senza_i_moduli_non_c_e_niente(self):
        with tempfile.TemporaryDirectory() as t:
            d = vault(t)
            lancia(d, {"nome": "Ada"})
            self.assertFalse((d / "content").exists())
            self.assertNotIn("servizi", json.loads((d / "config.json").read_text(encoding="utf-8")).get("moduli", {}))

    def test_servizi_si_segna_attivo(self):
        with tempfile.TemporaryDirectory() as t:
            d = vault(t)
            lancia(d, {"nome": "Ada", "moduli": {"servizi": {"attivo": True}}})
            self.assertTrue(json.loads((d / "config.json").read_text(encoding="utf-8"))["moduli"]["servizi"]["attivo"])

    def test_il_job_delle_bozze_segue_il_modulo(self):
        spec = importlib.util.spec_from_file_location("install_jobs", RADICE / "install_jobs.py")
        ij = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(ij)
        jobs = json.loads((RADICE / "scripts" / "jobs.json").read_text(encoding="utf-8"))
        self.assertNotIn("bozze", ij.seleziona(jobs, "linux"))
        self.assertIn("bozze", ij.seleziona(jobs, "linux", config={"moduli": {"bozze": {"attivo": True, "social": "both"}}}))

    def test_clean_example_toglie_anche_la_sezione_dei_servizi(self):
        with tempfile.TemporaryDirectory() as t:
            d = vault(t)
            (d / "projects" / "example-project").mkdir(parents=True)
            (d / "projects" / "INDEX.md").write_text("| [[projects/example-project/STATE|x]] |\n", encoding="utf-8")
            (d / "docs").mkdir()
            (d / "docs" / "servizi.md").write_text("# Servizi\n\n## example-project\n\n| a |\n\n## altro\n\nmio\n", encoding="utf-8")
            setup.main(["--clean-example"], radice=d)
            testo = (d / "docs" / "servizi.md").read_text(encoding="utf-8")
            self.assertNotIn("example-project", testo)
            self.assertIn("## altro", testo)


if __name__ == "__main__":
    unittest.main()

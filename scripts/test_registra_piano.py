#!/usr/bin/env python3
"""Test di registra-piano.py: un piano approvato diventa righe di docs/piano.md e la riga del suo obiettivo."""
import contextlib
import importlib.util
import io
import json
import os
import re
import shutil
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path
from unittest import mock

RADICE = Path(__file__).resolve().parent.parent
SCRIPT = RADICE / "scripts" / "registra-piano.py"


def carica(percorso, nome):
    spec = importlib.util.spec_from_file_location(nome, percorso)
    modulo = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(modulo)
    return modulo


rp = carica(SCRIPT, "registra_piano")

PIANO_BASE = "# Piano\n\n## Prossimi giorni\n\n- [ ] #sb Altro passo\n- [ ] #xy Di un altro progetto\n\n## Fatti\n\n- [x] #sb Vecchio\n"
OBIETTIVI_BASE = "# Obiettivi\n\nUna riga per obiettivo.\n\n- altro: Altro obiettivo\n"

PIANO_VALIDO = """# Rilascio fase 1 — Implementation Plan

Introduzione con `### Task 9: finto` dentro il testo.

```markdown
### Task 7: esempio dentro un blocco di codice
**Dipende da:** Task 99
```

### Task 1: Modello dei dati

**Dipende da:** nessuna
**Stima:** 3h
**Repo:** app

### Task 2: Pagina

**Dipende da:** Task 1
**Stima:** 1g

#### Step 1
- **Repo:** app, web

### Task 3: Rilascio

**Dipende da:** Task 1, Task 2
**Stima:** 1,5g
"""


class Base(unittest.TestCase):
    def cartella(self):
        d = Path(tempfile.mkdtemp())
        self.addCleanup(shutil.rmtree, d, True)
        return d

    def vault(self, piano=PIANO_BASE, obiettivi=OBIETTIVI_BASE):
        return vault_in(self.cartella(), piano, obiettivi)

    def vault_con_repo(self, **opzioni):
        """A vault whose project sb has real repo folders: app, web and the vault itself (a vault tracked as a project). (vault, app)."""
        d = self.vault(**opzioni)
        repo = self.cartella()
        for nome in ("app", "web"):
            (repo / nome / "docs").mkdir(parents=True)
        (d / "projects" / "sb" / "STATE.md").write_text(
            "# sb\n\n" + "".join("- **Repo:** %s\n" % p for p in (repo / "app", repo / "web", d)), encoding="utf-8")
        return d, repo / "app"

    def assertRifiuta(self, testo, *argomenti, d=None, contiene=None, **opzioni):
        d = d or self.vault()
        prima = (leggi(d, "piano.md"), leggi(d, "obiettivi.md"))
        with self.assertRaises(ValueError) as e:
            rp.registra(testo, *argomenti, d, **opzioni)
        self.assertEqual((leggi(d, "piano.md"), leggi(d, "obiettivi.md")), prima)
        problemi = e.exception.args[0]
        self.assertTrue(problemi and all(isinstance(p, str) for p in problemi))
        if contiene:
            self.assertTrue(any(contiene in p for p in problemi), problemi)
        return problemi

    def main(self, d, *argomenti):
        """main() in process with the vault patched in: (exit code, stdout, stderr)."""
        out, err = io.StringIO(), io.StringIO()
        with mock.patch.object(rp, "VAULT", d), contextlib.redirect_stdout(out), contextlib.redirect_stderr(err):
            codice = rp.main([str(a) for a in argomenti])
        return codice, out.getvalue(), err.getvalue()


def crea_link(link, bersaglio):
    """A directory symlink, or on Windows a junction (no privilege needed). False when the system makes neither."""
    try:
        os.symlink(bersaglio, link, target_is_directory=True)
        return True
    except OSError:
        pass
    try:
        import _winapi  # Windows only: the same call test.support uses for junctions
        _winapi.CreateJunction(str(bersaglio), str(link))
        return True
    except (OSError, ImportError, AttributeError):
        return False


def vault_in(d, piano=PIANO_BASE, obiettivi=OBIETTIVI_BASE):
    (d / "projects" / "sb").mkdir(parents=True)
    (d / "projects" / "INDEX.md").write_text(
        "| Progetto | Stack | Stato | Priorità | Ultimo aggiornamento |\n|---|---|---|---|---|\n"
        "| [[projects/sb/STATE\\|sb]] | Py | ok | alta | 2026-11-12 |\n"
        "| [[projects%slavoro%sw/STATE\\|w]] | S | S | alta | 2026-11-12 |\n" % ("/", "/")  # il template non contiene il percorso intero
        + "| [[projects/segreto/STATE\\|segreto]] | S | S | alta | 2026-11-12 |\n", encoding="utf-8")
    (d / "projects" / "sb" / "STATE.md").write_text(
        "# sb\n\n- **Repo:** D:/code/app\n- **Repo:** D:/code/web\n- **Repo:** D:/a/doppio\n- **Repo:** D:/b/doppio\n", encoding="utf-8")
    (d / "config.json").write_text(json.dumps({"moduli": {"riservata": {"cartella": "projects/segreto"}}}), encoding="utf-8")
    (d / "docs").mkdir()
    (d / "docs" / "piano.md").write_bytes(piano.encode("utf-8"))
    if obiettivi is not None:
        (d / "docs" / "obiettivi.md").write_bytes(obiettivi.encode("utf-8"))
    return d


def leggi(d, nome):
    return (d / "docs" / nome).read_bytes().decode("utf-8")


RIGHE_ATTESE = [
    "- [ ] #sb Rilascio fase 1 · Task 1: Modello dei dati id:rel-t1 obiettivo:rel stima:3h repo:app",
    "- [ ] #sb Rilascio fase 1 · Task 2: Pagina id:rel-t2 dopo:rel-t1 obiettivo:rel stima:1g repo:app,web",
    "- [ ] #sb Rilascio fase 1 · Task 3: Rilascio id:rel-t3 dopo:rel-t1,rel-t2 obiettivo:rel stima:1,5g",
]


class RegistraTest(Base):
    def test_piano_valido_scrive_righe_e_obiettivo(self):
        d = self.vault()
        r = rp.registra(PIANO_VALIDO, "sb", "rel", d, scadenza="2026-12-04", giorni="lun,mar", piano_rel="docs/piano-rel.md")
        self.assertEqual(leggi(d, "piano.md"),
                         "# Piano\n\n## Prossimi giorni\n\n- [ ] #sb Altro passo\n" + "".join(r + "\n" for r in RIGHE_ATTESE)
                         + "- [ ] #xy Di un altro progetto\n\n## Fatti\n\n- [x] #sb Vecchio\n")
        self.assertEqual(leggi(d, "obiettivi.md"), OBIETTIVI_BASE
                         + "- rel: Rilascio fase 1 scadenza:2026-12-04 giorni:lun,mar piano:docs/piano-rel.md\n")
        self.assertEqual(r["aggiunte"], RIGHE_ATTESE)
        self.assertEqual(r["aggiornate"], [])
        self.assertEqual(r["legami"], {"rel-t1": [], "rel-t2": ["rel-t1"], "rel-t3": ["rel-t1", "rel-t2"]})
        self.assertEqual(r["avvisi"], [])
        self.assertTrue(r["cambiato"])
        # the vault's own checks find nothing to say about what was written
        dip = rp.dipendenze
        obiettivi, problemi_obiettivi = dip.leggi_obiettivi(leggi(d, "obiettivi.md"))
        self.assertEqual(problemi_obiettivi, [])
        self.assertEqual(dip.problemi(dip.leggi_voci(leggi(d, "piano.md")), set(obiettivi)), [])

    def test_rilancio_non_duplica_e_conserva_casella_e_data(self):
        d = self.vault()
        rp.registra(PIANO_VALIDO, "sb", "rel", d, piano_rel="docs/rel.md")
        piano = leggi(d, "piano.md").replace("- [ ] #sb Rilascio fase 1 · Task 1", "- [x] #sb Rilascio fase 1 · Task 1")
        piano = piano.replace("- [ ] #sb Rilascio fase 1 · Task 2", "- [~] 2026-11-20 — #sb Rilascio fase 1 · Task 2")
        (d / "docs" / "piano.md").write_bytes(piano.encode("utf-8"))
        r = rp.registra(PIANO_VALIDO, "sb", "rel", d, piano_rel="docs/rel.md")
        self.assertFalse(r["cambiato"])
        self.assertEqual(leggi(d, "piano.md"), piano)
        # a changed title updates the text and the markers, never the checkbox or the date
        r = rp.registra(PIANO_VALIDO.replace("Pagina\n\n**Dipende da:** Task 1", "Pagina nuova\n\n**Dipende da:** nessuna"), "sb", "rel", d,
                        piano_rel="docs/rel.md")
        self.assertEqual(r["aggiunte"], [])
        self.assertEqual(r["aggiornate"], ["- [~] 2026-11-20 — #sb Rilascio fase 1 · Task 2: Pagina nuova id:rel-t2 obiettivo:rel stima:1g repo:app,web"])
        testo = leggi(d, "piano.md")
        self.assertIn("- [x] #sb Rilascio fase 1 · Task 1: Modello dei dati id:rel-t1", testo)
        self.assertEqual(testo.count("id:rel-t"), 3)

    def test_rilancio_conserva_chi_te_e_i_dopo_scritti_a_mano(self):
        d = self.vault()
        rp.registra(PIANO_VALIDO, "sb", "rel", d, piano_rel="docs/rel.md")
        piano = leggi(d, "piano.md").replace("id:rel-t1 ", "id:rel-t1 chi:te dopo:altro-1 ", 1)
        (d / "docs" / "piano.md").write_bytes(piano.encode("utf-8"))
        rp.registra(PIANO_VALIDO.replace("Modello dei dati", "Modello dei dati v2"), "sb", "rel", d, piano_rel="docs/rel.md")
        riga = next(r for r in leggi(d, "piano.md").splitlines() if "id:rel-t1" in r)
        self.assertIn("Modello dei dati v2", riga)
        self.assertIn("chi:te", riga)
        self.assertIn("dopo:altro-1", riga)

    def test_piano_cambiato_durante_la_registrazione_non_si_sovrascrive(self):
        # the dashboard runs in another process: a tick saved while this script works must not be lost
        d = self.vault()
        leggi_vero = rp._leggi
        def leggi_e_cambia(percorso, nome):
            testo = leggi_vero(percorso, nome)
            if nome == rp.FILE[0] and not getattr(leggi_e_cambia, "fatto", False):
                leggi_e_cambia.fatto = True
                (d / "docs" / "piano.md").write_text(testo + "- [ ] #sb spuntato dalla dashboard\n", encoding="utf-8")
            return testo
        with mock.patch.object(rp, "_leggi", leggi_e_cambia), self.assertRaises(RuntimeError) as c:
            rp.registra(PIANO_VALIDO, "sb", "rel", d)
        self.assertIn("cambiato", str(c.exception))
        self.assertIn("spuntato dalla dashboard", leggi(d, "piano.md"))

    def test_rilancio_senza_scadenza_conserva_i_marcatori_dell_obiettivo(self):
        d = self.vault(obiettivi=OBIETTIVI_BASE + "- rel: Titolo scelto a mano scadenza:2026-12-04 piano:docs/p.md\n")
        rp.registra(PIANO_VALIDO, "sb", "rel", d, giorni="tutti", piano_rel="docs/p.md")
        self.assertEqual(leggi(d, "obiettivi.md"),
                         OBIETTIVI_BASE + "- rel: Titolo scelto a mano scadenza:2026-12-04 giorni:tutti piano:docs/p.md\n")
        rp.registra(PIANO_VALIDO, "sb", "rel", d, titolo="Nuovo titolo", piano_rel="docs/p.md")
        self.assertIn("- rel: Nuovo titolo scadenza:2026-12-04 giorni:tutti piano:docs/p.md\n", leggi(d, "obiettivi.md"))

    def test_obiettivi_assente_si_crea(self):
        d = self.vault(obiettivi=None)
        rp.registra(PIANO_VALIDO, "sb", "rel", d)
        self.assertEqual(leggi(d, "obiettivi.md"), "# Obiettivi\n\n- rel: Rilascio fase 1\n")

    def test_crlf_conservato_e_posizione_in_prossimi_giorni(self):
        d = self.vault(piano="# Piano\r\n\r\n## Prossimi giorni\r\n\r\n- [ ] #xy Altro\r\n\r\n## Fatti\r\n", obiettivi="# Obiettivi\r\n")
        rp.registra(PIANO_VALIDO, "sb", "rel", d)
        self.assertEqual(leggi(d, "piano.md"), "# Piano\r\n\r\n## Prossimi giorni\r\n\r\n- [ ] #xy Altro\r\n"
                         + "".join(r + "\r\n" for r in RIGHE_ATTESE) + "\r\n## Fatti\r\n")
        self.assertEqual(leggi(d, "obiettivi.md"), "# Obiettivi\r\n- rel: Rilascio fase 1\r\n")

    def test_avvisi_senza_dipendenza_e_senza_stima(self):
        d = self.vault()
        r = rp.registra("# P\n\n### Task 1: Uno\n\n### Task 2: Due\n**Dipende da:** Task 1\n**Stima:** 2h\n", "sb", "p", d)
        self.assertEqual(r["avvisi"], ["riga 3: Task 1: dipendenza non dichiarata: chiedila all'utente", "riga 3: Task 1: senza stima"])

    def test_dipendenza_inesistente_non_scrive_niente(self):
        problemi = self.assertRifiuta(PIANO_VALIDO.replace("**Dipende da:** Task 1\n**Stima:** 1g", "**Dipende da:** Task 9\n**Stima:** 1g"),
                                      "sb", "rel", contiene="Task 9 non esiste")
        self.assertTrue(any(p.startswith("riga 18:") for p in problemi), problemi)

    def test_piano_senza_task_o_senza_titolo(self):
        self.assertRifiuta("# Solo titolo\n\n## Task 1: non è un ### \n", "sb", "rel", contiene="### Task <N>: <titolo>")
        self.assertRifiuta("### Task 1: Uno\n", "sb", "rel", contiene="# <titolo>")

    def test_numeri_dipendenze_e_cicli_non_validi(self):
        casi = {
            "# P\n### Task 0: Zero\n": "numera i task da 1",
            "# P\n### Task 01: Uno\n": "numera i task da 1",
            "# P\n### Task 1: Uno\n### Task 1: Ancora\n": "è già alla riga 2",
            "# P\n### Task 1: Uno\n**Dipende da:** Task 1\n": "dipende da sé stesso",
            "# P\n### Task 1: Uno\n**Dipende da:** Task 2\n### Task 2: Due\n**Dipende da:** Task 1\n": "ciclo",
            "# P\n### Task 1: Uno\n**Dipende da:** il primo\n": "`Task 1, Task 3` oppure `nessuna`",
            "# P\n### Task 1: Uno\n**Stima:** tre ore\n": "**Stima:**",
            "# P\n### Task 1: Uno\n**Stima:** 3h\n**Stima:** 4h\n": "ripetuto",
            "# P\n### Task 1:   \n": "senza titolo",
        }
        for testo, atteso in casi.items():
            with self.subTest(testo=testo):
                self.assertRifiuta(testo, "sb", "rel", contiene=atteso)

    def test_troppi_task_o_id_troppo_lungo(self):
        self.assertRifiuta("# P\n" + "".join("### Task %d: T\n" % n for n in range(1, 502)), "sb", "rel", contiene="al massimo")
        self.assertRifiuta("# P\n### Task 1000: T\n", "sb", "a" * 35, contiene="40 caratteri")

    def test_tag_del_lavoro_riservato_o_assente(self):
        for tag in ("w", "segreto", "nessuno", "../sb", ""):
            with self.subTest(tag=tag):
                self.assertRifiuta(PIANO_VALIDO, tag, "rel", contiene="--tag")

    def test_testo_con_html_o_caratteri_di_formato(self):
        for titolo in ("<script>alert(1)</script>", "Pagina \u202eevil", "zero\u200bwidth", "a\u2028b"):
            with self.subTest(titolo=titolo):
                self.assertRifiuta(PIANO_VALIDO.replace("Modello dei dati", titolo), "sb", "rel", contiene="riga 10:")
        self.assertRifiuta(PIANO_VALIDO.replace("# Rilascio fase 1", "# Rilascio <b>"), "sb", "rel", contiene="riga 1:")
        self.assertRifiuta(PIANO_VALIDO, "sb", "rel", titolo="Titolo \u2066x", contiene="--titolo")

    def test_titolo_che_sembra_un_marcatore(self):
        for titolo in ("Dati chi:te", "Dati id:altro in mezzo", "Stima stima:3h"):
            with self.subTest(titolo=titolo):
                self.assertRifiuta(PIANO_VALIDO.replace("Modello dei dati", titolo), "sb", "rel", contiene="marcatore")
        self.assertRifiuta(PIANO_VALIDO, "sb", "rel", titolo="Rilascio scadenza:2026-01-01", contiene="marcatori")

    def test_riga_troppo_lunga(self):
        self.assertRifiuta(PIANO_VALIDO.replace("Modello dei dati", "x" * 190), "sb", "rel", contiene="al massimo 200")

    def test_repo_fuori_allowlist_o_doppio(self):
        self.assertRifiuta(PIANO_VALIDO.replace("**Repo:** app", "**Repo:** altro"), "sb", "rel", contiene="non è un repo di sb")
        self.assertRifiuta(PIANO_VALIDO.replace("**Repo:** app", "**Repo:** doppio"), "sb", "rel", contiene="doppio")
        self.assertRifiuta(PIANO_VALIDO.replace("**Repo:** app", "**Repo:** ../x"), "sb", "rel", contiene="**Repo:**")

    def test_argomenti_non_validi(self):
        for valore in ("../piano.md", "docs/../x.md", "/etc/piano.md", "C:/piano.md", "docs/il piano.md", "docs\\piano.md"):
            with self.subTest(piano_rel=valore):
                self.assertRifiuta(PIANO_VALIDO, "sb", "rel", piano_rel=valore, contiene="--piano-rel")
        self.assertRifiuta(PIANO_VALIDO, "sb", "rel", scadenza="2026-02-30", contiene="--scadenza")
        self.assertRifiuta(PIANO_VALIDO, "sb", "rel", giorni="lun,xyz", contiene="--giorni")
        self.assertRifiuta(PIANO_VALIDO, "sb", "Rel_x", contiene="--obiettivo")

    def test_id_gia_usato_da_un_altro_piano_o_progetto(self):
        d = self.vault(piano=PIANO_BASE.replace("- [ ] #sb Altro passo", "- [x] #sb Fase vecchia · Task 1: Fatto id:rel-t1"))
        self.assertRifiuta(PIANO_VALIDO, "sb", "rel", d=d, contiene="docs/piano.md:5:")
        d = self.vault(piano=PIANO_BASE.replace("- [ ] #xy Di un altro progetto", "- [ ] #xy Rilascio fase 1 · Task 2: Pagina id:rel-t2"))
        self.assertRifiuta(PIANO_VALIDO, "sb", "rel", d=d, contiene="docs/piano.md:6:")
        d = self.vault(piano=PIANO_BASE + "- [ ] #sb Rilascio fase 1 · Task 3: a id:rel-t3\n- [ ] #sb Rilascio fase 1 · Task 3: b id:rel-t3\n")
        self.assertRifiuta(PIANO_VALIDO, "sb", "rel", d=d, contiene="più volte")

    def test_task_tolto_dal_piano_e_un_avviso(self):
        d = self.vault()
        rp.registra(PIANO_VALIDO, "sb", "rel", d, piano_rel="docs/rel.md")
        r = rp.registra(PIANO_VALIDO.split("### Task 3")[0], "sb", "rel", d, piano_rel="docs/rel.md")
        self.assertTrue(any("id:rel-t3" in a and "non è più nel piano" in a for a in r["avvisi"]), r["avvisi"])

    def test_commit_con_lista_di_argomenti_senza_shell(self):
        d = self.vault()
        r = rp.registra(PIANO_VALIDO, "sb", "rel", d)
        with mock.patch.object(rp.subprocess, "run", return_value=subprocess.CompletedProcess([], 0, "", "")) as run:
            self.assertIsNone(rp.committa(d, "rel", r))
        self.assertEqual(run.call_count, 2)
        aggiungi, commit = run.call_args_list
        self.assertEqual(aggiungi.args[0], ["git", "-C", str(d), "add", "--", "docs/piano.md", "docs/obiettivi.md"])
        self.assertEqual(commit.args[0], ["git", "-C", str(d), "commit", "-F", "-", "--", "docs/piano.md", "docs/obiettivi.md"])
        for chiamata in run.call_args_list:
            self.assertIsInstance(chiamata.args[0], list)
            self.assertNotIn("shell", chiamata.kwargs)
            self.assertEqual(chiamata.kwargs["timeout"], rp.GIT_TIMEOUT)
        messaggio = commit.kwargs["input"]
        self.assertTrue(messaggio.startswith("docs(piano): register plan rel\n\n"))
        self.assertIn("- rel-t3 dopo:rel-t1,rel-t2\n", messaggio)
        self.assertNotIn("Modello dei dati", messaggio)  # ids and links only, no plan text
        self.assertNotIn("Co-Authored-By", messaggio)  # the script names no co-author
        self.assertEqual(messaggio, "docs(piano): register plan rel\n\n- rel-t1\n- rel-t2 dopo:rel-t1\n- rel-t3 dopo:rel-t1,rel-t2\n")

    def test_git_senza_variabili_git_del_chiamante(self):
        d = self.vault()
        r = rp.registra(PIANO_VALIDO, "sb", "rel", d)
        ambiente = {"GIT_DIR": "/altrove/.git", "GIT_WORK_TREE": "/altrove", "GIT_INDEX_FILE": "x", "PATH": "p"}
        with mock.patch.dict(rp.os.environ, ambiente), \
                mock.patch.object(rp.subprocess, "run", return_value=subprocess.CompletedProcess([], 0, "", "")) as run:
            rp.committa(d, "rel", r)
        self.assertEqual(run.call_count, 2)
        for chiamata in run.call_args_list:
            env = chiamata.kwargs["env"]
            self.assertEqual([k for k in env if k.upper().startswith("GIT_")], [])
            self.assertEqual(env["PATH"], "p")
            self.assertEqual(chiamata.args[0][:3], ["git", "-C", str(d)])

    def test_git_lento_o_assente_esce_con_1(self):
        d, app = self.vault_con_repo()
        f = app / "piano.md"
        f.write_text(PIANO_VALIDO, encoding="utf-8")
        for errore in (subprocess.TimeoutExpired(["git"], rp.GIT_TIMEOUT), FileNotFoundError("git")):
            with self.subTest(errore=type(errore).__name__):
                (d / "docs" / "piano.md").write_bytes(PIANO_BASE.encode("utf-8"))
                (d / "docs" / "obiettivi.md").write_bytes(OBIETTIVI_BASE.encode("utf-8"))
                with mock.patch.object(rp.subprocess, "run", side_effect=errore):
                    codice, _, err = self.main(d, f, "--tag", "sb", "--obiettivo", "rel")
                self.assertEqual(codice, 1)
                self.assertIn("file scritti", err)

    def test_un_obiettivo_e_del_suo_file_di_piano(self):
        lungo = "# " + "Rilascio della piattaforma " * 3
        casi = {"titoli diversi dopo il taglio": (lungo + "A\n### Task 1: Uno\n", lungo + "B\n### Task 1: Uno\n"),
                "titoli uguali": ("# P\n### Task 1: Uno\n", "# P\n### Task 1: Uno\n")}
        for nome, (primo, secondo) in casi.items():
            with self.subTest(nome):
                d = self.vault()
                rp.registra(primo, "sb", "rel", d, piano_rel="docs/a.md")
                self.assertIn("- rel: ", leggi(d, "obiettivi.md"))
                self.assertIn("piano:docs/a.md", leggi(d, "obiettivi.md"))
                self.assertRifiuta(secondo, "sb", "rel", d=d, piano_rel="docs/b.md", contiene="appartiene al piano docs/a.md")
                self.assertRifiuta(secondo, "sb", "rel", d=d, contiene="appartiene al piano docs/a.md")
                # the same file updates in place and keeps the checkbox
                piano = re.sub(r"(?m)^- \[ \](.* id:rel-t1 )", r"- [x]\1", leggi(d, "piano.md"))
                (d / "docs" / "piano.md").write_bytes(piano.encode("utf-8"))
                r = rp.registra(secondo.replace("Uno", "Uno rivisto"), "sb", "rel", d, piano_rel="docs/a.md")
                self.assertEqual(r["aggiunte"], [])
                self.assertEqual(len(r["aggiornate"]), 1)
                self.assertTrue(r["aggiornate"][0].startswith("- [x] #sb "))
                self.assertEqual(leggi(d, "piano.md").count("id:rel-t1"), 1)

    def test_un_obiettivo_non_passa_mai_a_un_altro_piano(self):
        d = self.vault()
        rp.registra("# X\n### Task 1: Uno di X\n", "sb", "rel", d, piano_rel="docs/x.md")
        piano = re.sub(r"(?m)^- \[ \](.* id:rel-t1 )", r"- [x]\1", leggi(d, "piano.md"))
        (d / "docs" / "piano.md").write_bytes(piano.encode("utf-8"))
        # run 1: plan Y shares no id with X, still the goal stays X's
        for opzioni in ({"piano_rel": "docs/y.md"}, {}):
            with self.subTest(**opzioni):
                self.assertRifiuta("# Y\n### Task 7: Sette di Y\n", "sb", "rel", d=d, **opzioni,
                                   contiene="l'obiettivo rel appartiene al piano docs/x.md: usa lo stesso --piano-rel o un altro --obiettivo")
        self.assertIn("- rel: X piano:docs/x.md\n", leggi(d, "obiettivi.md"))
        # run 2: Y now has a Task 1, X's done task is not taken over
        self.assertRifiuta("# Y\n### Task 1: Uno di Y\n", "sb", "rel", d=d, piano_rel="docs/y.md", contiene="appartiene al piano")
        self.assertIn("- [x] #sb X · Task 1: Uno di X id:rel-t1", leggi(d, "piano.md"))

    def test_obiettivo_senza_piano_riceve_il_primo(self):
        d = self.vault(obiettivi=OBIETTIVI_BASE + "- rel: Rilascio\n")
        rp.registra("# P\n### Task 1: Uno\n", "sb", "rel", d, piano_rel="docs/p.md")
        self.assertIn("- rel: Rilascio piano:docs/p.md\n", leggi(d, "obiettivi.md"))

    def test_obiettivo_senza_piano_con_id_gia_presenti_si_ferma(self):
        d = self.vault(piano=PIANO_BASE + "- [ ] #sb Rilascio fase 1 · Task 1: Modello dei dati id:rel-t1 obiettivo:rel\n",
                       obiettivi=OBIETTIVI_BASE + "- rel: Rilascio\n")
        self.assertRifiuta(PIANO_VALIDO, "sb", "rel", d=d, piano_rel="docs/rel.md", contiene="è di un altro piano")

    def test_wikilink_e_pipe_rifiutati_backtick_ammessi(self):
        for titolo in ("vedi [[memory/about-me]]", "a | b", "fine]]"):
            with self.subTest(titolo=titolo):
                self.assertRifiuta(PIANO_VALIDO.replace("Modello dei dati", titolo), "sb", "rel", contiene="riga 10:")
        self.assertRifiuta(PIANO_VALIDO.replace("# Rilascio fase 1", "# Rilascio | fase 1"), "sb", "rel", contiene="riga 1:")
        self.assertRifiuta(PIANO_VALIDO, "sb", "rel", titolo="[[x]]", contiene="--titolo")
        d = self.vault()
        r = rp.registra(PIANO_VALIDO.replace("Modello dei dati", "`scripts/x.py`"), "sb", "rel", d)
        self.assertIn("Task 1: `scripts/x.py` id:rel-t1", r["aggiunte"][0])

    def test_cancelletti_tolti_dai_titoli(self):
        d = self.vault()
        r = rp.registra("# C# e #altro piano\n### Task 1: Fix #sb2 e #xy\n", "sb", "p", d)
        self.assertEqual(r["aggiunte"], ["- [ ] #sb C e altro piano · Task 1: Fix sb2 e xy id:p-t1 obiettivo:p"])
        self.assertIn("- p: C e altro piano\n", leggi(d, "obiettivi.md"))

    def test_campi_rientrati(self):
        d = self.vault()
        r = rp.registra("# P\n### Task 1: Uno\n  **Dipende da:** nessuna\n    - **Stima:** 2h\n\t**Repo:** app\n", "sb", "p", d)
        self.assertEqual(r["avvisi"], [])
        self.assertEqual(r["aggiunte"], ["- [ ] #sb P · Task 1: Uno id:p-t1 obiettivo:p stima:2h repo:app"])

    def test_link_e_immagini_rifiutati(self):
        for titolo in ("vedi [qui](x.md)", "![img](a.png)", "apri https:" + "//x.it", "file:" + "//c/x"):
            with self.subTest(titolo=titolo):
                self.assertRifiuta(PIANO_VALIDO.replace("Modello dei dati", titolo), "sb", "rel",
                                   contiene="riga 10: link e immagini non sono ammessi nel piano: scrivili come testo")
        self.assertRifiuta(PIANO_VALIDO.replace("# Rilascio fase 1", "# Rilascio [fase](x)"), "sb", "rel",
                           contiene="riga 1: link e immagini non sono ammessi nel piano")
        self.assertRifiuta(PIANO_VALIDO, "sb", "rel", titolo="vedi ![x](y)", contiene="--titolo: link e immagini")

    def test_titolo_di_task_scritto_male(self):
        for riga in ("### Task 2 - B", "## Task 2: B", "#### Task 2: B", "###Task 2: B", "### Task due: B"):
            with self.subTest(riga=riga):
                self.assertRifiuta("# P\n### Task 1: Uno\n" + riga + "\n", "sb", "rel", contiene="riga 3: scrivi `### Task <N>: <titolo>`")
        # inside a code block it is not a task
        r = rp.registra("# P\n### Task 1: Uno\n```\n### Task 2 - B\n```\n", "sb", "p", self.vault())
        self.assertEqual(len(r["aggiunte"]), 1)

    def test_righe_nuove_in_prossimi_giorni(self):
        nuova = "- [ ] #sb P · Task 1: Uno id:p-t1 obiettivo:p\n"
        # the project's last open line is in «Più avanti»: a new line still goes to «Prossimi giorni», after the tag's open line there
        piano = ("# Piano\n\n## Prossimi giorni\n\n- [ ] #sb Qui\n- [ ] #xy Altro\n\n## Più avanti\n\n"
                 "- [ ] #sb Dopo\n\n## Fatti\n\n- [x] #sb Vecchio\n")
        d = self.vault(piano=piano)
        rp.registra("# P\n### Task 1: Uno\n", "sb", "p", d)
        self.assertEqual(leggi(d, "piano.md"), piano.replace("- [ ] #sb Qui\n", "- [ ] #sb Qui\n" + nuova))
        # no open line of the tag in the section: at its end
        piano = "# Piano\n\n## Prossimi giorni\n\n- [ ] #xy Altro\n\n## Più avanti\n\n- [ ] #sb Dopo\n"
        d = self.vault(piano=piano)
        rp.registra("# P\n### Task 1: Uno\n", "sb", "p", d)
        self.assertEqual(leggi(d, "piano.md"), piano.replace("#xy Altro\n", "#xy Altro\n" + nuova))
        # no such section: created at the end of the file
        piano = "# Piano\n\n## Più avanti\n\n- [ ] #sb Dopo\n"
        d = self.vault(piano=piano)
        rp.registra("# P\n### Task 1: Uno\n", "sb", "p", d, piano_rel="docs/p.md")
        self.assertEqual(leggi(d, "piano.md"), piano + "## Prossimi giorni\n" + nuova)
        # an existing line is updated where it is, even in «Più avanti»; only the new task goes to «Prossimi giorni»
        spostato = "# Piano\n\n## Prossimi giorni\n\n## Più avanti\n\n- [ ] #sb Dopo\n" + nuova
        (d / "docs" / "piano.md").write_bytes(spostato.encode("utf-8"))
        r = rp.registra("# P\n### Task 1: Uno nuovo\n### Task 2: Due\n", "sb", "p", d, piano_rel="docs/p.md")
        self.assertEqual(leggi(d, "piano.md"), "# Piano\n\n## Prossimi giorni\n- [ ] #sb P · Task 2: Due id:p-t2 obiettivo:p\n\n"
                         "## Più avanti\n\n- [ ] #sb Dopo\n- [ ] #sb P · Task 1: Uno nuovo id:p-t1 obiettivo:p\n")
        self.assertEqual(len(r["aggiornate"]), 1)

    def test_aggiungi_voce_della_dashboard_non_cambia(self):
        # the dashboard still puts a new line after the tag's last open line, wherever it is
        piano = "# Piano\n\n## Prossimi giorni\n\n- [ ] #xy Altro\n\n## Più avanti\n\n- [ ] #sb Dopo\n"
        d = self.vault(piano=piano)
        rp.server.aggiungi_voce("sb", "Nuova", d)
        self.assertEqual(leggi(d, "piano.md"), piano + "- [ ] #sb Nuova\n")


class ConfigTest(Base):
    """ADR-002: the reserved folder comes from config.json; when it cannot be read the script refuses (fail closed)."""

    def test_config_con_bom_riconosce_la_cartella_riservata(self):
        d = self.vault()
        (d / "config.json").write_text(json.dumps({"moduli": {"riservata": {"cartella": "projects/segreto"}}}), encoding="utf-8-sig")
        self.assertIn("segreto", rp.leggi_riservata(d)[0])
        self.assertRifiuta(PIANO_VALIDO, "segreto", "rel", d=d, contiene="--tag")

    def test_config_illeggibile_rifiuta(self):
        for testo in (b"{non json", b"[1, 2]", b"\xff\xfe", b"[" * 100000, b'{"moduli": []}', b'{"moduli": {"riservata": []}}',
                      b'{"moduli": {"riservata": {"attivo": true}}}', b'{"moduli": {"riservata": {"cartella": 5}}}',
                      b'{"moduli": {"riservata": {"cartella": "../fuori"}}}', b'{"moduli": {"riservata": {"cartella": "~/note-mie"}}}'):
            with self.subTest(testo=testo[:40]):
                d = self.vault()
                (d / "config.json").write_bytes(testo)
                prima = (leggi(d, "piano.md"), leggi(d, "obiettivi.md"))
                with self.assertRaises(RuntimeError) as e:
                    rp.registra(PIANO_VALIDO, "sb", "rel", d)
                self.assertEqual(str(e.exception), "config.json non leggibile: non posso escludere la cartella riservata")
                self.assertEqual((leggi(d, "piano.md"), leggi(d, "obiettivi.md")), prima)

    def test_cartella_riservata_scritta_con_altre_maiuscole(self):
        # setup.py accepts «Projects/Segreto»: on NTFS and APFS it is projects/segreto, so its tag is refused
        for scelta in ("Projects/Segreto", "projects\\SEGRETO"):
            with self.subTest(scelta=scelta):
                d = self.vault()
                (d / "config.json").write_text(json.dumps({"moduli": {"riservata": {"cartella": scelta}}}), encoding="utf-8")
                self.assertRifiuta(PIANO_VALIDO, "segreto", "rel", d=d, contiene="--tag")

    def test_config_letta_una_volta_per_chiamata(self):
        d, app = self.vault_con_repo()
        f = app / "p.md"
        f.write_text(PIANO_VALIDO, encoding="utf-8")
        with mock.patch.object(rp.server.percorsi, "scelta_riservata", side_effect=rp.server.percorsi.scelta_riservata) as letture:
            rp.percorso_del_piano(f, "sb", d)
            self.assertEqual(letture.call_count, 1)
            letture.reset_mock()
            rp.registra(PIANO_VALIDO, "sb", "rel", d)
            self.assertEqual(letture.call_count, 1)

    def test_senza_moduli_py_rifiuta_e_dice_perche(self):
        # the wizard's rule for the reserved folder lives in moduli.py: without it nothing is trusted, and the message says so
        d, app = self.vault_con_repo()
        (app / "p.md").write_text(PIANO_VALIDO, encoding="utf-8")
        with mock.patch.object(rp.server.percorsi, "_valida_cartella", side_effect=FileNotFoundError("moduli.py")):
            with self.assertRaises(RuntimeError) as e:
                rp.server.percorsi.scelta_riservata(d)
            self.assertEqual(str(e.exception), "config")
            codice, _, err = self.main(d, app / "p.md", "--tag", "sb", "--obiettivo", "rel", "--senza-commit")
        self.assertEqual(codice, 1)
        self.assertIn("moduli.py", err)
        self.assertNotIn("config.json non leggibile", err)
        self.assertEqual(leggi(d, "piano.md"), PIANO_BASE)

    def test_config_illeggibile_esce_con_1(self):
        d, app = self.vault_con_repo()
        (app / "p.md").write_text(PIANO_VALIDO, encoding="utf-8")
        (d / "config.json").write_text("{rotto", encoding="utf-8")
        codice, _, err = self.main(d, app / "p.md", "--tag", "sb", "--obiettivo", "rel", "--senza-commit")
        self.assertEqual(codice, 1)
        self.assertIn("config.json non leggibile: non posso escludere la cartella riservata", err)
        self.assertEqual(leggi(d, "piano.md"), PIANO_BASE)

    def test_config_assente_va_bene(self):
        d = self.vault()
        (d / "config.json").unlink()
        self.assertTrue(rp.registra(PIANO_VALIDO, "sb", "rel", d)["cambiato"])


class PercorsoPianoTest(Base):
    """ADR-002: the plan file must be a file of one of the tagged project's repos, never a note of the vault's projects/."""

    def lancia(self, d, piano, *argomenti):
        return self.main(d, piano, "--tag", "sb", "--obiettivo", "rel", "--senza-commit", *argomenti)

    def assertRifiutato(self, d, piano, contiene, *argomenti):
        codice, _, err = self.lancia(d, piano, *argomenti)
        self.assertEqual(codice, 2, err)
        self.assertIn(contiene, err)
        self.assertEqual((leggi(d, "piano.md"), leggi(d, "obiettivi.md")), (PIANO_BASE, OBIETTIVI_BASE))
        self.assertNotIn(str(piano), err)  # a path is never echoed

    def test_piano_nel_repo_ricava_piano_rel(self):
        d, app = self.vault_con_repo()
        (app / "docs" / "plans").mkdir()
        f = app / "docs" / "plans" / "p.md"
        f.write_text(PIANO_VALIDO, encoding="utf-8")
        codice, _, err = self.lancia(d, f)
        self.assertEqual(codice, 0, err)
        self.assertIn("- rel: Rilascio fase 1 piano:docs/plans/p.md\n", leggi(d, "obiettivi.md"))
        self.assertEqual(rp.percorso_del_piano(f, "sb", d), (f.resolve(), "docs/plans/p.md"))
        # the same value passed by hand is accepted; the run is the same plan, so nothing changes
        codice, out, err = self.lancia(d, f, "--piano-rel", "docs/plans/p.md")
        self.assertEqual(codice, 0, err)
        self.assertIn("niente da cambiare", out)

    def test_piano_nel_vault_fuori_da_projects(self):
        d, _ = self.vault_con_repo()
        f = d / "docs" / "p.md"
        f.write_text(PIANO_VALIDO, encoding="utf-8")
        self.assertEqual(rp.percorso_del_piano(f, "sb", d)[1], "docs/p.md")

    def test_repo_annidato_vince_il_piu_vicino(self):
        d, app = self.vault_con_repo()
        dentro = app / "sotto"
        (dentro / "docs").mkdir(parents=True)
        stato = d / "projects" / "sb" / "STATE.md"
        stato.write_text(stato.read_text(encoding="utf-8") + "- **Repo:** %s\n" % dentro, encoding="utf-8")
        f = dentro / "docs" / "p.md"
        f.write_text(PIANO_VALIDO, encoding="utf-8")
        self.assertEqual(rp.percorso_del_piano(f, "sb", d)[1], "docs/p.md")

    def test_piano_rel_diverso_rifiutato(self):
        d, app = self.vault_con_repo()
        f = app / "docs" / "p.md"
        f.write_text(PIANO_VALIDO, encoding="utf-8")
        self.assertRifiutato(d, f, "--piano-rel: questo piano è docs/p.md nel suo repo", "--piano-rel", "docs/altro.md")

    def test_piano_fuori_dai_repo_rifiutato(self):
        d, _ = self.vault_con_repo()
        f = self.cartella() / "p.md"
        f.write_text(PIANO_VALIDO, encoding="utf-8")
        self.assertRifiutato(d, f, "il piano deve stare in uno dei repo del progetto")

    def test_piano_in_un_repo_di_un_altro_progetto_rifiutato(self):
        d, _ = self.vault_con_repo()
        altro = self.cartella()
        (d / "projects" / "altro").mkdir()
        (d / "projects" / "altro" / "STATE.md").write_text("# altro\n\n- **Repo:** %s\n" % altro, encoding="utf-8")
        with open(d / "projects" / "INDEX.md", "a", encoding="utf-8") as indice:
            indice.write("| [[projects/altro/STATE\\|altro]] | Py | ok | alta | 2026-11-12 |\n")
        f = altro / "p.md"
        f.write_text(PIANO_VALIDO, encoding="utf-8")
        self.assertRifiutato(d, f, "il piano deve stare in uno dei repo del progetto")
        self.assertEqual(rp.percorso_del_piano(f, "altro", d)[1], "p.md")  # it is a plan of that project

    def test_piano_dentro_projects_o_cartelle_riservate_rifiutato(self):
        # the vault is a repo of sb, still its notes are never a plan
        for cartella in ("_private", "segreto", "lavoro", "sb", "_PRIVATE"):
            with self.subTest(cartella=cartella):
                d, _ = self.vault_con_repo()
                (d / "projects" / cartella).mkdir(parents=True, exist_ok=True)
                f = d / "projects" / cartella / "nota.md"
                f.write_text(PIANO_VALIDO, encoding="utf-8")
                self.assertRifiutato(d, f, "il piano non può stare in projects/ del vault")

    def test_piano_nella_cartella_riservata_fuori_da_projects_rifiutato(self):
        # setup.py accepts any folder inside the vault: the vault is a repo of sb, still the reserved notes are never a plan
        for scelta in ("riservati-casa", "docs/clienti-segreti", "projects/clienti/archivio"):
            with self.subTest(scelta=scelta):
                d, _ = self.vault_con_repo()
                (d / "config.json").write_text(json.dumps({"moduli": {"riservata": {"cartella": scelta}}}), encoding="utf-8")
                (d / scelta).mkdir(parents=True)
                f = d / scelta / "p.md"
                f.write_text(PIANO_VALIDO, encoding="utf-8")
                self.assertRifiutato(d, f, "il piano non può stare in projects/ del vault")

    def test_piano_nel_bersaglio_di_una_cartella_riservata_collegata_rifiutato(self):
        # the reserved folder is a link into a repo of sb: the plan reached through the repo is still a reserved note
        for nome in ("_" + "private", "lavoro", "segreto"):
            with self.subTest(nome=nome):
                d, app = self.vault_con_repo()
                bersaglio = app / "note"
                bersaglio.mkdir()
                if not crea_link(d / "projects" / nome, bersaglio):
                    self.skipTest("né link simbolici né junction disponibili")
                f = bersaglio / "p.md"
                f.write_text(PIANO_VALIDO, encoding="utf-8")
                self.assertRifiutato(d, f, "il piano non può stare in projects/ del vault")

    def test_piano_nella_cartella_riservata_di_un_altro_vault_rifiutato(self):
        # another checkout of a vault is a repo of sb: its projects/<reserved> notes are never a plan either
        for nome in ("_" + "private", "_" + "PRIVATE", "lavoro", "segreto", "lavoro" "/cliente/docs"):
            with self.subTest(nome=nome):
                d, _ = self.vault_con_repo()
                altro = self.cartella()
                stato = d / "projects" / "sb" / "STATE.md"
                stato.write_text(stato.read_text(encoding="utf-8") + "- **Repo:** %s\n" % altro, encoding="utf-8")
                (altro / "projects" / nome).mkdir(parents=True)
                f = altro / "projects" / nome / "p.md"
                f.write_text(PIANO_VALIDO, encoding="utf-8")
                self.assertRifiutato(d, f, "il piano non può stare nelle note riservate di un vault")
        # the folder configured outside projects/ is refused at the same relative path of another vault (a folder with
        # projects/), in any case; its leaf name alone blocks nothing
        d, _ = self.vault_con_repo()
        (d / "config.json").write_text(json.dumps({"moduli": {"riservata": {"cartella": "docs/archivio"}}}), encoding="utf-8")
        altro, senza_projects = self.cartella(), self.cartella()
        stato = d / "projects" / "sb" / "STATE.md"
        stato.write_text(stato.read_text(encoding="utf-8") + "".join("- **Repo:** %s\n" % r for r in (altro, senza_projects)), encoding="utf-8")
        (altro / "projects" / "sb").mkdir(parents=True)
        for rel in ("docs/archivio/p.md", "DOCS/Archivio/x/p.md"):
            with self.subTest(rel=rel):
                f = altro / rel
                f.parent.mkdir(parents=True, exist_ok=True)
                f.write_text(PIANO_VALIDO, encoding="utf-8")
                self.assertRifiutato(d, f, "il piano non può stare nelle note riservate di un vault")
        for radice, rel in ((altro, "projects/archivio/p.md"), (altro, "projects/sb/p.md"), (senza_projects, "docs/archivio/p.md")):
            with self.subTest(radice=radice.name, rel=rel):
                g = radice / rel
                g.parent.mkdir(parents=True, exist_ok=True)
                g.write_text(PIANO_VALIDO, encoding="utf-8")
                self.assertEqual(rp.percorso_del_piano(g, "sb", d)[1], rel)
        self.assertNotIn("archivio", rp.leggi_riservata(d)[0])  # --tag archivio stays a valid project name

    def test_piano_inesistente_o_con_spazi_o_progetto_non_valido(self):
        d, app = self.vault_con_repo()
        self.assertRifiutato(d, app / "manca.md", "il file del piano non esiste")
        f = app / "docs" / "il piano.md"
        f.write_text(PIANO_VALIDO, encoding="utf-8")
        self.assertRifiutato(d, f, "il percorso del piano nel repo")
        g = app / "p.md"
        g.write_text(PIANO_VALIDO, encoding="utf-8")
        for tag in ("w", "segreto", "nessuno", "../sb"):
            with self.subTest(tag=tag):
                codice, _, err = self.main(d, g, "--tag", tag, "--obiettivo", "rel", "--senza-commit")
                self.assertEqual(codice, 2)
                self.assertIn("il piano deve stare in uno dei repo del progetto", err)

    def test_radice_del_disco_o_percorso_con_punti_non_e_un_repo(self):
        # `Repo: C:\` would turn the guard into «any .md on the drive»: like nomi_repo and the launcher, a root is never a repo
        d, _ = self.vault_con_repo()
        fuori = self.cartella()
        stato = d / "projects" / "sb" / "STATE.md"
        radice = Path(tempfile.gettempdir()).anchor
        stato.write_text("# sb\n\n- **Repo:** %s\n- **Repo:** %s\n" % (radice, fuori / "sotto" / ".."), encoding="utf-8")
        (fuori / "sotto").mkdir()
        f = fuori / "p.md"
        f.write_text(PIANO_VALIDO, encoding="utf-8")
        self.assertRifiutato(d, f, "il piano deve stare in uno dei repo del progetto")

    def test_percorso_di_rete_non_tocca_il_disco(self):
        d, _ = self.vault_con_repo()
        # «\\srv\share» is a network path only on Windows; elsewhere it is a relative file name
        for percorso in (("\\\\srv\\share\\p.md",) if os.name == "nt" else ()) + ("//srv/share/p.md",):
            with self.subTest(percorso=percorso), mock.patch.object(rp.Path, "resolve", side_effect=AssertionError("disco")):
                with self.assertRaises(ValueError) as e:
                    rp.percorso_del_piano(percorso, "sb", d)
                self.assertTrue(any("disco di questo computer" in p for p in e.exception.args[0]), e.exception.args[0])

    def test_link_a_una_nota_riservata_rifiutato(self):
        d, app = self.vault_con_repo()
        (d / "projects" / "_private").mkdir()
        nota = d / "projects" / "_private" / "nota.md"
        nota.write_text(PIANO_VALIDO, encoding="utf-8")
        link = app / "docs" / "p.md"
        try:
            os.symlink(nota, link)
        except (OSError, NotImplementedError):
            self.skipTest("link simbolici non disponibili")
        self.assertRifiutato(d, link, "il piano non può stare in projects/ del vault")


class FileDelVaultTest(Base):
    def test_piano_md_non_utf8_esce_con_1(self):
        d, app = self.vault_con_repo()
        (app / "p.md").write_text(PIANO_VALIDO, encoding="utf-8")
        (d / "docs" / "piano.md").write_bytes(PIANO_BASE.encode("utf-8") + b"\xff\n")
        codice, _, err = self.main(d, app / "p.md", "--tag", "sb", "--obiettivo", "rel", "--senza-commit")
        self.assertEqual(codice, 1)
        self.assertEqual(err.strip(), "docs/piano.md non è UTF-8 valido: correggilo o riscrivi la riga rotta")
        self.assertEqual(leggi(d, "obiettivi.md"), OBIETTIVI_BASE)

    def test_scrittura_fallita_dice_il_file_e_cosa_e_gia_scritto(self):
        d, app = self.vault_con_repo()
        (app / "p.md").write_text(PIANO_VALIDO, encoding="utf-8")
        with mock.patch.object(rp.server, "_scrivi_atomico", side_effect=[None, PermissionError(13, "Permission denied", str(d))]):
            codice, _, err = self.main(d, app / "p.md", "--tag", "sb", "--obiettivo", "rel", "--senza-commit")
        self.assertEqual(codice, 1)
        self.assertIn("non riesco a scrivere docs/piano.md: Permission denied; file già scritti: docs/obiettivi.md", err)
        self.assertNotIn(str(d), err)

    def test_index_non_utf8_esce_con_1(self):
        d, app = self.vault_con_repo()
        (app / "p.md").write_text(PIANO_VALIDO, encoding="utf-8")
        with open(d / "projects" / "INDEX.md", "ab") as f:
            f.write(b"\xff\n")
        codice, _, err = self.main(d, app / "p.md", "--tag", "sb", "--obiettivo", "rel", "--senza-commit")
        self.assertEqual(codice, 1)
        self.assertIn("non è UTF-8 valido", err)
        self.assertEqual(len(err.strip().splitlines()), 1)


class CliTest(Base):
    """The real command, run with `-I` from another folder: the vault is always the one the script lives in, so the
    scripts are copied into a temporary vault."""

    def vault_cli(self):
        d, app = self.vault_con_repo()
        shutil.copytree(RADICE / "scripts", d / "scripts", ignore=shutil.ignore_patterns("__pycache__", "test_*"))
        shutil.copy(RADICE / "moduli.py", d / "moduli.py")  # the wizard's rule for the reserved folder, as in a real vault
        return d, app

    def lancia(self, d, piano, *argomenti):
        return subprocess.run([sys.executable, "-I", str(d / "scripts" / "registra-piano.py"), str(piano), "--tag", "sb",
                               "--obiettivo", "rel", "--senza-commit", *argomenti],
                              capture_output=True, text=True, encoding="utf-8", cwd=tempfile.gettempdir())

    def test_cli_scrive_e_rilancio_senza_cambi(self):
        d, app = self.vault_cli()
        f = app / "docs" / "rel.md"
        f.write_text(PIANO_VALIDO.replace("**Stima:** 3h\n", ""), encoding="utf-8")
        r = self.lancia(d, f)
        self.assertEqual(r.returncode, 0, r.stderr)
        self.assertIn("Task 1: senza stima", r.stderr)
        self.assertIn("id:rel-t3", leggi(d, "piano.md"))
        self.assertIn("piano:docs/rel.md", leggi(d, "obiettivi.md"))  # always written, even without --piano-rel
        r = self.lancia(d, f, "--piano-rel", "docs/rel.md")
        self.assertEqual(r.returncode, 0, r.stderr)
        self.assertIn("niente da cambiare", r.stdout)

    def test_cli_senza_vault(self):
        d, app = self.vault_cli()
        f = app / "p.md"
        f.write_text(PIANO_VALIDO, encoding="utf-8")
        r = self.lancia(d, f, "--vault", str(self.cartella()))
        self.assertEqual(r.returncode, 2)
        self.assertIn("unrecognized arguments: --vault", r.stderr)
        self.assertEqual(leggi(d, "piano.md"), PIANO_BASE)

    def test_cli_rifiuta_file_grande_o_non_md(self):
        d, app = self.vault_cli()
        cartella = app / "docs"
        grande = cartella / "grande.md"
        grande.write_bytes(PIANO_VALIDO.encode("utf-8") + b"x" * (1024 * 1024))
        testo = cartella / "piano.txt"
        testo.write_text(PIANO_VALIDO, encoding="utf-8")
        for f in (grande, testo, cartella / "manca.md", cartella):
            with self.subTest(f=f.name):
                r = self.lancia(d, f)
                self.assertEqual(r.returncode, 2)
                self.assertTrue(r.stderr.strip())
                self.assertEqual(leggi(d, "piano.md"), PIANO_BASE)

    def test_cli_piano_non_valido_esce_con_2_e_righe_su_stderr(self):
        d, app = self.vault_cli()
        f = app / "piano.md"
        f.write_text("# P\n### Task 1: Uno\n**Dipende da:** Task 4\n### Task 2 - Due\n", encoding="utf-8")
        r = self.lancia(d, f)
        self.assertEqual(r.returncode, 2)
        righe = r.stderr.strip().splitlines()
        self.assertTrue(any(x.startswith("riga 3:") for x in righe), righe)
        self.assertTrue(any(x.startswith("riga 4:") for x in righe), righe)
        self.assertEqual(leggi(d, "piano.md"), PIANO_BASE)


if __name__ == "__main__":
    unittest.main()

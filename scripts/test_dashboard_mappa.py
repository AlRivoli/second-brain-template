#!/usr/bin/env python3
"""Test del parser di piano.md con stato [~] e tag del nodo."""
import importlib.util
import http.client
import json
import os
import re
import tempfile
import threading
import unittest
from unittest import mock
from datetime import datetime
from pathlib import Path

RADICE = Path(__file__).resolve().parent.parent


def carica(percorso, nome):
    spec = importlib.util.spec_from_file_location(nome, percorso)
    modulo = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(modulo)
    return modulo


server = carica(RADICE / "scripts" / "dashboard" / "server.py", "server")


def scrivi(testo):
    d = Path(tempfile.mkdtemp())
    (d / "piano.md").write_bytes(testo.encode("utf-8"))
    return d


class PianoStatoTest(unittest.TestCase):
    def test_casella_in_corso_e_tag(self):
        d = scrivi("## A\n- [~] 2026-11-10 — #Second-Brain Ridisegnare  la mappa\n- [ ] senza tag\n- [x] #linkedin Bozze\n")
        v = server.leggi_sezioni(d / "piano.md")[0]["voci"]
        self.assertEqual(v[0]["stato"], "in_corso")
        self.assertEqual(v[0]["data"], "2026-11-10")
        self.assertEqual(v[0]["tag"], "second-brain")
        self.assertEqual(v[0]["vista"], "Ridisegnare la mappa")
        self.assertIs(v[0]["fatto"], False)
        self.assertIsNone(v[1]["tag"])
        self.assertEqual(v[1]["stato"], "da_fare")
        self.assertIs(v[2]["fatto"], True)
        self.assertEqual(v[2]["stato"], "fatto")

    def test_crlf_e_x_maiuscola(self):
        d = scrivi("## A\r\n- [X] uno \r\n- [ ] due\r\n")
        v = server.leggi_sezioni(d / "piano.md")[0]["voci"]
        self.assertEqual(len(v), 2)
        self.assertTrue(v[0]["fatto"])
        self.assertEqual(v[0]["testo"], "uno")

    def test_imposta_stato_scrive_le_tre_caselle(self):
        d = scrivi("## A\n- [ ] 2026-10-26 — #a uno\nfine\n")
        f = d / "piano.md"
        for stato, casella in (("in_corso", "~"), ("fatto", "x"), ("da_fare", " ")):
            server.imposta_stato("piano", "2026-10-26", "#a uno", stato, d)
            self.assertEqual(f.read_text(encoding="utf-8"), "## A\n- [%s] 2026-10-26 — #a uno\nfine\n" % casella)

    def test_imposta_stato_conserva_crlf(self):
        d = scrivi("## A\r\n- [ ] uno\r\n- [ ] due\r\n")
        server.imposta_stato("piano", None, "uno", "in_corso", d)
        self.assertEqual((d / "piano.md").read_bytes(), b"## A\r\n- [~] uno\r\n- [ ] due\r\n")

    def test_aggiungi_voce_in_fondo(self):
        d = scrivi("## A\n- [ ] uno\n")
        server.aggiungi_voce_libera("due", d)
        self.assertEqual((d / "piano.md").read_text(), "## A\n- [ ] uno\n- [ ] due\n")

    def test_aggiungi_voce_file_senza_a_capo_finale(self):
        d = scrivi("## A\n- [ ] uno")
        server.aggiungi_voce_libera("due", d)
        self.assertEqual((d / "piano.md").read_text(), "## A\n- [ ] uno\n- [ ] due\n")

    def test_aggiungi_voce_conserva_crlf(self):
        for base in ("## A\r\n- [ ] uno\r\n", "## A\r\n- [ ] uno"):
            d = scrivi(base)
            server.aggiungi_voce_libera("due", d)
            self.assertEqual((d / "piano.md").read_bytes(), b"## A\r\n- [ ] uno\r\n- [ ] due\r\n")

    def test_aggiungi_voce_rifiuta_vuoto_lungo_e_a_capo(self):
        d = scrivi("## A\n")
        # splitlines() spezza anche su questi: il testo tornerebbe su due righe alla lettura dopo
        for cattivo in ("", "x" * 201, "a\nb", "a\rb", "a - [ ] b", "a\x0bb", "a\x85b", 3):
            with self.assertRaises(ValueError):
                server.aggiungi_voce_libera(cattivo, d)
        self.assertEqual((d / "piano.md").read_text(), "## A\n")

    def test_aggiungi_voce_doppia(self):
        d = scrivi("## A\n")
        server.aggiungi_voce_libera("uno", d)
        with self.assertRaises(RuntimeError):
            server.aggiungi_voce_libera("uno", d)
        self.assertEqual((d / "piano.md").read_text(), "## A\n- [ ] uno\n")

    def test_aggiungi_voce_doppia_se_in_corso(self):
        d = scrivi("## A\n- [~] uno\n")
        with self.assertRaises(RuntimeError):
            server.aggiungi_voce_libera("uno", d)

    def test_aggiungi_voce_rifiuta_il_testo_di_una_voce_fatta(self):
        d = scrivi("## A\n- [x] uno\n")
        with self.assertRaises(RuntimeError):
            server.aggiungi_voce_libera("uno", d)
        self.assertEqual((d / "piano.md").read_text(), "## A\n- [x] uno\n")

    def test_voce_aggiunta_si_puo_segnare_fatta(self):
        d = scrivi("## A\n- [x] vecchia\n")
        server.aggiungi_voce_libera("nuova", d)
        server.imposta_stato("piano", None, "nuova", "fatto", d)
        self.assertEqual((d / "piano.md").read_text(), "## A\n- [x] vecchia\n- [x] nuova\n")

    def test_aggiungi_voce_prima_di_fatti(self):
        d = scrivi("## Da fare\n- [ ] uno\n\n## Fatti\n- [x] a\n")
        server.aggiungi_voce_libera("due", d)
        self.assertEqual((d / "piano.md").read_text(), "## Da fare\n- [ ] uno\n- [ ] due\n\n## Fatti\n- [x] a\n")
        s = server.leggi_sezioni(d / "piano.md")
        self.assertEqual([v["testo"] for v in s[0]["voci"]], ["uno", "due"])

    def test_aggiungi_voce_fatti_senza_distinzione_di_maiuscole_e_crlf(self):
        d = scrivi("## Da fare\r\n- [ ] uno\r\n## FATTI\r\n- [x] a")
        server.aggiungi_voce_libera("due", d)
        self.assertEqual((d / "piano.md").read_bytes(), b"## Da fare\r\n- [ ] uno\r\n- [ ] due\r\n## FATTI\r\n- [x] a")

    def test_aggiungi_voce_senza_intestazioni(self):
        for base in ("", "testo libero\n", "testo libero"):
            d = scrivi(base)
            server.aggiungi_voce_libera("due", d)
            s = server.leggi_sezioni(d / "piano.md")
            self.assertEqual([(x["titolo"], [v["testo"] for v in x["voci"]]) for x in s], [("Da fare", ["due"])])

    def test_aggiungi_voce_toglie_i_cancelletti(self):
        d = scrivi("## A\n")
        server.aggiungi_voce_libera("Novita #beta di #x", d)
        self.assertEqual((d / "piano.md").read_text(), "## A\n- [ ] Novita beta di x\n")
        with self.assertRaises(ValueError):
            server.aggiungi_voce_libera(" # ", d)

    def test_stato_non_valido(self):
        d = scrivi("## A\n- [ ] uno\n")
        with self.assertRaises(ValueError):
            server.imposta_stato("piano", None, "uno", "boh", d)

    def test_oggi_conta_in_corso_come_aperta(self):
        d = scrivi("## S\n- [~] 2026-10-25 — ieri\n")
        o = server.oggi(datetime(2026, 10, 26, 8), piano_file=d / "piano.md", scadenze_file=Path("/nonexistent"))
        self.assertTrue(o["conData"][0]["inRitardo"])
        self.assertEqual(o["conData"][0]["testo"], "ieri")


ADESSO = datetime(2026, 11, 9, 19, 0)


def vault_finto(piano):
    """Vault in tempdir: INDEX con alfa (alta, con Repo esistente) e beta (da definire, senza Repo), più docs/piano.md."""
    v = Path(tempfile.mkdtemp())
    repo = v / "repo-alfa"
    repo.mkdir()
    for nome in ("alfa", "beta"):
        (v / "projects" / nome).mkdir(parents=True)
    (v / "projects" / "alfa" / "STATE.md").write_text("# alfa\n- **Repo:** %s\n" % repo, encoding="utf-8")
    (v / "projects" / "beta" / "STATE.md").write_text("# beta\n- **Repo:** nessuno\n", encoding="utf-8")
    (v / "projects" / "INDEX.md").write_text(
        "| Progetto | Stack | Stato | Priorità | Ultimo aggiornamento |\n|---|---|---|---|---|\n"
        "| [[projects/alfa/STATE\\|alfa]] | Stack | Stato | alta | 2026-11-09 |\n"
        "| [[projects/beta/STATE\\|beta]] | Stack | Stato | da definire | 2026-11-09 |\n", encoding="utf-8")
    (v / "docs").mkdir()
    (v / "docs" / "piano.md").write_text(piano, encoding="utf-8")
    return v


def mappa_di(piano):
    v = vault_finto(piano)
    return server.mappa(ADESSO, piano_file=v / "docs" / "piano.md", vault=v)


class MappaTest(unittest.TestCase):
    def test_il_nome_per_il_saluto_e_il_primo_di_nome_firma(self):
        import json
        v = vault_finto("")
        self.assertEqual(server.mappa(ADESSO, piano_file=v / "docs" / "piano.md", vault=v)["nome"], "")  # senza config: nessun nome
        (v / "config.json").write_text(json.dumps({"nome_firma": "Mario Rossi"}), encoding="utf-8")
        self.assertEqual(server.mappa(ADESSO, piano_file=v / "docs" / "piano.md", vault=v)["nome"], "Mario")
        (v / "config.json").write_text("non json", encoding="utf-8")
        self.assertEqual(server.mappa(ADESSO, piano_file=v / "docs" / "piano.md", vault=v)["nome"], "")

    def test_nodi_per_tag_progetto_argomento_e_senza(self):
        m = mappa_di("## A\n- [ ] #alfa uno\n- [~] #ALFA due\n- [ ] #linkedin tre\n- [ ] quattro\n- [x] cinque\n")
        n = {x["nome"]: x for x in m["nodi"]}
        self.assertEqual(set(n), {"alfa", "beta", "linkedin", "Senza nodo", "Social"})
        self.assertEqual((n["alfa"]["tipo"], len(n["alfa"]["task"]), n["alfa"]["haCartella"], n["alfa"]["priorita"]), ("progetto", 2, True, "alta"))
        self.assertEqual((n["beta"]["tipo"], n["beta"]["task"], n["beta"]["haCartella"]), ("progetto", [], True))  # senza Repo esistente si avvia nel vault
        self.assertEqual(n["linkedin"]["tipo"], "argomento")
        self.assertEqual(len(n["Senza nodo"]["task"]), 1)
        self.assertEqual(n["alfa"]["task"][0]["testo"], "#alfa uno")
        self.assertEqual(n["alfa"]["task"][0]["vista"], "uno")

    def test_tag_inizia_con_una_lettera(self):
        m = mappa_di("## A\n- [ ] PR #1, #2 e #- poi\n- [ ] #a1-b ok\n")
        n = {x["nome"]: x for x in m["nodi"]}
        self.assertIn("a1-b", n)
        self.assertNotIn("1", n)
        self.assertEqual(n["Senza nodo"]["task"][0]["vista"], "PR #1, #2 e #- poi")
        self.assertIsNone(server.TAG.search("#1"))

    def test_prossima_ritardo(self):
        m = mappa_di("## A\n- [ ] 2026-11-05 — vecchia\n- [ ] 2026-10-28 — piu vecchia\n- [~] in corso\n")
        self.assertEqual((m["prossima"]["testo"], m["prossima"]["motivo"]), ("piu vecchia", "in ritardo dal 28 ott"))

    def test_prossima_in_corso(self):
        m = mappa_di("## A\n- [ ] 2026-11-10 — scade\n- [~] primo\n- [~] secondo\n")
        self.assertEqual((m["prossima"]["testo"], m["prossima"]["motivo"]), ("primo", "in corso"))

    def test_prossima_scadenza(self):
        m = mappa_di("## A\n- [ ] aperta\n- [ ] 2026-11-30 — lontana\n- [ ] 2026-11-16 — dopo\n- [ ] 2026-11-10 — vicina\n")
        self.assertEqual((m["prossima"]["testo"], m["prossima"]["motivo"]), ("vicina", "scade mar 10"))

    def test_prossima_scadenza_a_sette_giorni_esatti(self):
        m = mappa_di("## A\n- [ ] aperta\n- [ ] 2026-11-16 — giusto in tempo\n")
        self.assertEqual((m["prossima"]["testo"], m["prossima"]["motivo"]), ("giusto in tempo", "scade lun 16"))

    def test_cartella_del_nodo(self):
        m = mappa_di("## A\n- [ ] #alfa uno\n- [ ] #linkedin due\n")
        n = {x["nome"]: x for x in m["nodi"]}
        self.assertTrue(n["alfa"]["cartella"].endswith("repo-alfa"))
        self.assertTrue(n["beta"]["cartella"] and n["linkedin"]["cartella"])

    def test_prossima_priorita_alta(self):
        m = mappa_di("## A\n- [ ] #beta uno\n- [ ] #alfa due\n- [ ] #alfa tre\n")
        self.assertEqual((m["prossima"]["testo"], m["prossima"]["motivo"]), ("#alfa due", "priorità alta"))

    def test_prossima_prima_aperta(self):
        m = mappa_di("## A\n- [x] fatta\n- [ ] #beta uno\n- [ ] due\n")
        self.assertEqual((m["prossima"]["testo"], m["prossima"]["motivo"]), ("#beta uno", "primo passo aperto"))
        self.assertEqual(m["nodi"][0]["nome"], "beta")  # prima il nodo della prossima azione

    def test_prossima_nessuna(self):
        self.assertIsNone(mappa_di("## A\n- [x] #alfa fatta\n")["prossima"])

    def test_conteggi(self):
        m = mappa_di("## A\n- [ ] 2026-11-01 — a\n- [ ] b\n- [~] c\n- [x] #alfa d\n")
        self.assertEqual(m["conteggi"], {"da_fare": 2, "in_corso": 1, "in_ritardo": 1})

    def test_lavoro_mai_risolto(self):
        v = vault_finto("")
        (v / "projects" / "INDEX.md").write_text("| [[projects%slavoro%sx/STATE\\|x]] | S | S | alta | 2026-11-09 |\n" % ("/", "/"), encoding="utf-8")  # il template non deve contenere il percorso scritto per intero
        vero = Path.read_text

        def guarda(self, *a, **k):
            if "lavoro" in str(self):
                raise AssertionError("letto %s" % self)
            return vero(self, *a, **k)

        with mock.patch.object(Path, "read_text", guarda):
            indice = server.progetti_indice(v)
            self.assertEqual(indice["x"]["cartelle"], [])
            self.assertTrue(indice["x"]["lavoro"])
            m = server.mappa(ADESSO, piano_file=v / "docs" / "piano.md", vault=v)
            self.assertEqual([x["nome"] for x in m["nodi"]], ["Social"])  # senza voci non compare (c'è solo il nodo fisso)
            (v / "docs" / "piano.md").write_text("## A\n- [ ] #x uno\n", encoding="utf-8")
            n = next(x for x in server.mappa(ADESSO, piano_file=v / "docs" / "piano.md", vault=v)["nodi"] if x["nome"] == "x")
            self.assertEqual((n["nome"], n["tipo"], n["haCartella"]), ("x", "progetto", False))
            self.assertIsNone(server.cartella_nodo(n, v))

    def test_cartella_nodo_symlink_verso_lavoro(self):
        v = vault_finto("")
        y = v / "projects" / "lavoro" / "y"
        y.mkdir(parents=True)
        os.symlink(y, v / "link-y")
        (v / "projects" / "alfa" / "STATE.md").write_text("- **Repo:** %s\n" % (v / "link-y"), encoding="utf-8")
        self.assertIsNone(server.cartella_nodo({"nome": "alfa", "tipo": "progetto"}, v))
        self.assertEqual(server.cartella_nodo({"nome": "linkedin", "tipo": "argomento"}, v), v)


def con_bozze(v, **per_rete):
    """Scrive bozze finte in content/<rete>/ (nome -> titolo)."""
    for rete, bozze in per_rete.items():
        (v / "content" / rete).mkdir(parents=True, exist_ok=True)
        for nome, titolo in bozze.items():
            (v / "content" / rete / nome).write_text("# %s\n\nTesto.\n" % titolo, encoding="utf-8")


class SocialTest(unittest.TestCase):
    def nodo(self, v):
        m = server.mappa(ADESSO, piano_file=v / "docs" / "piano.md", vault=v)
        return m, next(x for x in m["nodi"] if x["nome"] == "Social")

    def test_nodo_fisso_anche_senza_bozze(self):
        m, n = self.nodo(vault_finto("## A\n- [ ] #alfa uno\n"))
        self.assertEqual((n["tipo"], n["task"], n["haCartella"]), ("argomento", [], True))

    def test_task_dalle_bozze_non_pubblicate(self):
        v = vault_finto("")
        con_bozze(v, linkedin={"2026-11-01-a.md": "Bozza LinkedIn: primo", "2026-11-02-b.md": "Bozza LinkedIn: secondo"},
                  instagram={"2026-11-03-c.md": "Bozza Instagram: terzo"})
        (v / "content" / "stato.json").write_text('{"linkedin/2026-11-01-a.md": {"stato": "pubblicata", "data": "2026-11-05"}}', encoding="utf-8")
        _, n = self.nodo(v)
        self.assertEqual(sorted(t["testo"] for t in n["task"]), ["instagram/2026-11-03-c.md", "linkedin/2026-11-02-b.md"])
        t = next(t for t in n["task"] if t["testo"].startswith("linkedin"))
        self.assertEqual((t["vista"], t["stato"], t["bozza"], t["data"]), ("LinkedIn: secondo", "da_fare", "linkedin", None))

    def test_le_bozze_non_cambiano_prossima_e_conteggi(self):
        v = vault_finto("## A\n- [ ] #alfa uno\n")
        con_bozze(v, linkedin={"2026-11-01-a.md": "Bozza LinkedIn: primo"})
        m, _ = self.nodo(v)
        self.assertEqual(m["conteggi"], {"da_fare": 1, "in_corso": 0, "in_ritardo": 0})
        self.assertEqual(m["prossima"]["nodo"], "alfa")

    def test_tag_social_nel_piano_finisce_nello_stesso_nodo(self):
        v = vault_finto("## A\n- [ ] #social scrivere\n")
        con_bozze(v, linkedin={"2026-11-01-a.md": "Bozza LinkedIn: primo"})
        m, n = self.nodo(v)
        self.assertEqual(len(n["task"]), 2)
        self.assertEqual(len([x for x in m["nodi"] if x["nome"].lower() == "social"]), 1)

    def test_riga_progetto_porta_la_bozza_anche_sul_nodo_del_progetto(self):
        v = vault_finto("## A\n- [ ] #alfa uno\n")
        (v / "content" / "linkedin").mkdir(parents=True)
        (v / "content" / "linkedin" / "2026-11-01-a.md").write_text("# Bozza LinkedIn: primo\nProgetto: ALFA\n\nTesto.\n", encoding="utf-8")
        con_bozze(v, instagram={"2026-11-02-b.md": "Bozza Instagram: senza riga"})
        m, social = self.nodo(v)
        alfa = next(x for x in m["nodi"] if x["nome"] == "alfa")
        self.assertEqual([t["testo"] for t in alfa["task"] if t.get("bozza")], ["linkedin/2026-11-01-a.md"])
        self.assertEqual(len(social["task"]), 2)                      # resta anche in Social
        self.assertEqual(m["conteggi"], {"da_fare": 1, "in_corso": 0, "in_ritardo": 0})
        self.assertEqual(m["prossima"]["nodo"], "alfa")
        self.assertEqual(m["prossima"]["testo"], "#alfa uno")          # la bozza non diventa prossima azione

    def test_riga_progetto_sconosciuta_o_del_lavoro_resta_solo_in_social(self):
        v = vault_finto("")
        (v / "projects" / "INDEX.md").write_text(
            (v / "projects" / "INDEX.md").read_text(encoding="utf-8") + "| [[projects%slavoro%sx/STATE\\|x]] | S | S | alta | 2026-11-09 |\n" % ("/", "/"), encoding="utf-8")
        for nome, progetto in (("2026-11-01-a.md", "nonesiste"), ("2026-11-02-b.md", "x")):
            (v / "content" / "linkedin").mkdir(parents=True, exist_ok=True)
            (v / "content" / "linkedin" / nome).write_text("# Bozza LinkedIn: t\nProgetto: %s\n\nTesto.\n" % progetto, encoding="utf-8")
        m, social = self.nodo(v)
        self.assertEqual(len(social["task"]), 2)
        self.assertFalse([t for x in m["nodi"] if x["nome"] != "Social" for t in x["task"] if t.get("bozza")])
        self.assertNotIn("x", [x["nome"] for x in m["nodi"]])

    def test_riga_progetto_non_finisce_nel_testo_da_copiare(self):
        v = vault_finto("")
        (v / "content" / "linkedin").mkdir(parents=True)
        (v / "content" / "linkedin" / "2026-11-01-a.md").write_text("# Bozza LinkedIn: t\nProgetto: alfa\n\nTesto.\n", encoding="utf-8")
        b = server.bozze(v / "content" / "linkedin")[0]
        self.assertEqual((b["progetto"], b["testo"]), ("alfa", "Testo."))

    def test_modulo_bozze_spento_nodo_vuoto(self):
        v = vault_finto("")
        con_bozze(v, linkedin={"2026-11-01-a.md": "Bozza LinkedIn: primo"})
        (v / "config.json").write_text('{"moduli": {}}', encoding="utf-8")
        self.assertEqual(self.nodo(v)[1]["task"], [])


class FinteEsito:
    def __init__(self, codice=0):
        self.returncode = codice


class AvvioTest(unittest.TestCase):
    def prepara(self, piano="## A\n- [ ] #alfa uno\n"):
        v = vault_finto(piano)
        server.ULTIMI_AVVII.clear()
        return v, v / "avvii"

    def avvia(self, v, av, testo="#alfa uno", codice=0, **k):
        chiamate = []

        def finto(args, **kw):
            chiamate.append((args, kw))
            return FinteEsito(codice)

        k.setdefault("sistema", "darwin")
        r = server.avvia_claude(None, testo, esegui=finto, piano_file=v / "docs" / "piano.md", vault=v, cartella_avvii=av, **k)
        return r, chiamate

    def test_avvio_comando_fisso_per_testi_ostili(self):
        for ostile in ('"; rm -rf ~ #', "$(touch /tmp/x)", "`id`", "a'b\"c"):
            v, av = self.prepara("## A\n- [ ] #alfa %s\n" % ostile)
            r, chiamate = self.avvia(v, av, "#alfa " + ostile)
            args = chiamate[0][0]
            self.assertEqual(args[:3], ["/usr/bin/open", "-a", "Terminal"], ostile)
            self.assertEqual(len(args), 4)
            self.assertTrue(args[3].endswith(".command"))
            cmd = Path(args[3]).read_text(encoding="utf-8")
            self.assertNotIn(ostile, cmd)
            self.assertRegex(cmd, r"^#!/bin/zsh -l\ncd '?[^\n]+'? && exec claude \"\$\(cat '?[^\n]+\.txt'?\)\"\n$")
            txt = Path(args[3]).with_suffix(".txt").read_text(encoding="utf-8")
            self.assertIn(ostile, txt)
            self.assertIn("(nodo #alfa)", txt)
            self.assertEqual(r["cartella"], str(v / "repo-alfa"))
            if os.name == "posix":  # su Windows i permessi non esistono (e «Avvia» è solo per macOS)
                self.assertEqual(os.stat(args[3]).st_mode & 0o777, 0o700)

    def test_avvio_testo_con_a_capo_non_trovato(self):
        v, av = self.prepara()
        with self.assertRaises(LookupError):
            self.avvia(v, av, "#alfa riga\naltra")

    def test_avvio_mette_in_corso_solo_se_open_riesce(self):
        v, av = self.prepara()
        with self.assertRaises(RuntimeError):
            self.avvia(v, av, codice=1)
        self.assertIn("- [ ] #alfa uno", (v / "docs" / "piano.md").read_text(encoding="utf-8"))
        server.ULTIMI_AVVII.clear()
        self.avvia(v, av)
        self.assertIn("- [~] #alfa uno", (v / "docs" / "piano.md").read_text(encoding="utf-8"))

    def test_avvio_rifiuta_cartella_lavoro(self):
        v, av = self.prepara("## A\n- [ ] #x uno\n")
        (v / "projects" / "INDEX.md").write_text("| [[projects%s%sx/STATE\\|x]] | S | S | alta | 2026-11-09 |\n" % ("/", "lavoro" + "/"), encoding="utf-8")
        with self.assertRaises(RuntimeError):
            self.avvia(v, av, "#x uno")

    def test_avvio_repo_inesistente_usa_il_vault(self):
        v, av = self.prepara("## A\n- [ ] #beta uno\n")
        r, _ = self.avvia(v, av, "#beta uno")
        self.assertEqual(r["cartella"], str(v))

    def test_avvio_doppio_clic(self):
        v, av = self.prepara()
        _, c1 = self.avvia(v, av, adesso=lambda: 100.0)
        (v / "docs" / "piano.md").write_text("## A\n- [ ] #alfa uno\n", encoding="utf-8")  # la voce torna aperta: conta solo l'antirimbalzo
        with self.assertRaises(RuntimeError):
            self.avvia(v, av, adesso=lambda: 105.0)
        self.assertEqual(len(c1), 1)

    def test_avvio_doppione_con_gemella_fatta_senza_tag_non_apre_nulla(self):
        v, av = self.prepara("## A\n- [x] Pagare bolletta\n- [ ] Pagare bolletta\n")
        chiamate = []
        with self.assertRaises(RuntimeError) as c:
            server.avvia_claude(None, "Pagare bolletta", esegui=lambda *a, **k: chiamate.append(a), piano_file=v / "docs" / "piano.md", vault=v, cartella_avvii=av, sistema="darwin")
        self.assertEqual(str(c.exception), "doppia")
        self.assertEqual(chiamate, [])
        self.assertFalse(av.exists())
        self.assertEqual(server.ULTIMI_AVVII, {})

    def test_avvio_timeout_di_open_e_apertura(self):
        v, av = self.prepara()

        def scade(*a, **k):
            raise server.subprocess.TimeoutExpired("open", 10)
        with self.assertRaises(RuntimeError) as c:
            server.avvia_claude(None, "#alfa uno", esegui=scade, piano_file=v / "docs" / "piano.md", vault=v, cartella_avvii=av, sistema="darwin")
        self.assertEqual(str(c.exception), "apertura")
        self.assertEqual(server.ULTIMI_AVVII, {})

    def test_avvio_se_la_spunta_fallisce_dopo_open_il_debounce_resta(self):
        v, av = self.prepara()
        with mock.patch.object(server, "imposta_stato", side_effect=RuntimeError("doppia")):
            r, c1 = self.avvia(v, av, adesso=lambda: 100.0)
        self.assertEqual(r["avviso"], "stato")
        with self.assertRaises(RuntimeError) as c:
            self.avvia(v, av, adesso=lambda: 105.0)
        self.assertEqual(str(c.exception), "ripetuto")

    def test_avvio_non_mac(self):
        v, av = self.prepara()
        with self.assertRaises(NotImplementedError):
            self.avvia(v, av, sistema="linux")

    def test_avvio_pulisce_i_file_vecchi(self):
        v, av = self.prepara()
        av.mkdir()
        vecchio = av / "vecchio.txt"
        vecchio.write_text("x", encoding="utf-8")
        os.utime(vecchio, (1, 1))
        self.avvia(v, av)
        self.assertFalse(vecchio.exists())


class AggiungiVoceTest(unittest.TestCase):
    def piano(self, testo):
        v = vault_finto(testo)
        return v, v / "docs" / "piano.md"

    def test_dopo_l_ultima_voce_con_lo_stesso_tag(self):
        v, f = self.piano("## Prossimi giorni\n- [ ] #beta uno\n- [ ] #alfa due\n\n## Altro\n- [~] #beta tre\n\n- [ ] #alfa quattro\n")
        self.assertEqual(server.aggiungi_voce("beta", "cinque", vault=v), "- [ ] #beta cinque")
        self.assertEqual(f.read_text(encoding="utf-8"), "## Prossimi giorni\n- [ ] #beta uno\n- [ ] #alfa due\n\n## Altro\n- [~] #beta tre\n- [ ] #beta cinque\n\n- [ ] #alfa quattro\n")

    def test_le_voci_fatte_non_attirano_la_voce_nuova_in_fatti(self):
        v, f = self.piano("## Prossimi giorni \n- [ ] #alfa uno\n\n## Fatti\n- [x] #beta vecchio\n")
        server.aggiungi_voce("beta", "nuovo", vault=v)
        self.assertEqual(f.read_text(encoding="utf-8"), "## Prossimi giorni \n- [ ] #alfa uno\n- [ ] #beta nuovo\n\n## Fatti\n- [x] #beta vecchio\n")

    def test_file_senza_sezioni_crea_prossimi_giorni(self):
        for iniziale in ("", "# Piano\n", "# Piano"):
            v, f = self.piano(iniziale)
            server.aggiungi_voce("beta", "nuovo", vault=v)
            self.assertEqual(server.leggi_sezioni(f)[0]["voci"][0]["vista"], "nuovo", iniziale)

    def test_doppione_senza_distinguere_il_tag_maiuscolo(self):
        v, f = self.piano("## A\n- [ ] #beta uno\n")
        with self.assertRaises(RuntimeError):
            server.aggiungi_voce("Beta", "uno", vault=v)

    def test_tag_senza_voci_in_fondo_a_prossimi_giorni(self):
        v, f = self.piano("## Prossimi giorni\n- [ ] #alfa uno\n\n## Altro\n- [ ] #alfa due\n")
        server.aggiungi_voce("linkedin", "bozza", vault=v)
        self.assertEqual(f.read_text(encoding="utf-8"), "## Prossimi giorni\n- [ ] #alfa uno\n- [ ] #linkedin bozza\n\n## Altro\n- [ ] #alfa due\n")

    def test_senza_sezione_in_fondo_al_file_anche_senza_a_capo_finale(self):
        v, f = self.piano("## Altro\n- [ ] #alfa uno")
        server.aggiungi_voce("linkedin", "bozza", vault=v)
        self.assertEqual(f.read_text(encoding="utf-8"), "## Altro\n- [ ] #alfa uno\n- [ ] #linkedin bozza\n")

    def test_crlf_conservato(self):
        v, f = self.piano("")
        f.write_bytes(b"## Prossimi giorni\r\n- [ ] #beta uno\r\n")
        server.aggiungi_voce("beta", "due", vault=v)
        self.assertEqual(f.read_bytes(), b"## Prossimi giorni\r\n- [ ] #beta uno\r\n- [ ] #beta due\r\n")

    def test_la_voce_nuova_e_letta_dal_parser_con_il_suo_tag(self):
        v, f = self.piano("## Prossimi giorni\n")
        server.aggiungi_voce("beta", "scrivere il test", vault=v)
        voce = server.leggi_sezioni(f)[0]["voci"][0]
        self.assertEqual((voce["tag"], voce["vista"], voce["stato"]), ("beta", "scrivere il test", "da_fare"))

    def test_testo_e_tag_non_validi_non_toccano_il_file(self):
        v, f = self.piano("## A\n- [ ] #alfa uno\n")
        prima = f.read_bytes()
        for tag, testo in (("beta", ""), ("beta", "   "), ("beta", "due\nrighe"), ("beta", "due\rrighe"), ("beta", "a\u2028b"), ("beta", "abc\u202edcba"), ("beta", "a\u200bb"), ("beta", "a\ufeff"), ("beta", "a\ud800b"), ("beta", "<b>x</b>"), ("beta", "x" * 201),
                           ("beta", 5), ("be ta", "ok"), ("1beta", "ok"), ("", "ok"), ("beta\n", "ok"), (None, "ok")):
            with self.subTest(tag=tag, testo=testo), self.assertRaises(ValueError):
                server.aggiungi_voce(tag, testo, vault=v)
        self.assertEqual(f.read_bytes(), prima)

    def test_testo_di_200_caratteri_ok(self):
        v, f = self.piano("## A\n")
        server.aggiungi_voce("beta", "x" * 200, vault=v)
        self.assertIn("#beta " + "x" * 200, f.read_text(encoding="utf-8"))

    def test_tag_di_un_progetto_del_lavoro_rifiutato(self):
        v, f = self.piano("## A\n")
        with (v / "projects" / "INDEX.md").open("a") as i:
            i.write("| [[projects" "/" "lavoro" "/cliente/STATE\\|cliente]] | Stack | Stato | alta | 2026-11-09 |\n")  # spezzato: il template non lo contiene per intero
        with self.assertRaises(ValueError):
            server.aggiungi_voce("Cliente", "ok", vault=v)
        self.assertEqual(f.read_text(encoding="utf-8"), "## A\n")

    def test_doppione_409(self):
        v, f = self.piano("## A\n- [x] #beta uno\n")
        with self.assertRaises(RuntimeError):
            server.aggiungi_voce("beta", "uno", vault=v)
        self.assertEqual(f.read_text(encoding="utf-8"), "## A\n- [x] #beta uno\n")


def vault_con_template(piano="## A\n- [ ] #alfa uno\n"):
    v = vault_finto(piano)
    (v / "templates").mkdir()
    (v / "templates" / "STATE.md").write_text(
        "# {{title}}\n- **Repo:** <percorso locale, o \"nessuno\">\n- **Aggiornato:** {{date:YYYY-MM-DD}}\n## Obiettivo attuale\n<una o due righe>\n", encoding="utf-8")
    (v / "templates" / "project-index-row.md").write_text(
        "| Progetto | Stack | Stato | Priorità | Ultimo aggiornamento |\n|---|---|---|---|---|\n"
        "| [[projects/<nome>/STATE\\|<nome>]] | <stack> | <stato in 5 parole> | <alta / media / bassa> | {{date:YYYY-MM-DD}} |\n", encoding="utf-8")
    return v


class NuovoProgettoTest(unittest.TestCase):
    def test_crea_state_e_riga_e_compare_sulla_mappa(self):
        v = vault_con_template()
        repo = v / "repo-gamma"
        (repo / ".git").mkdir(parents=True)
        esito = server.nuovo_progetto("gamma", str(repo), "Python, SQLite", "media", vault=v, oggi="2026-11-10")
        self.assertEqual(esito, {"ok": True, "nome": "gamma"})
        stato = (v / "projects" / "gamma" / "STATE.md").read_text(encoding="utf-8")
        self.assertTrue(stato.startswith("# gamma\n- **Repo:** %s\n- **Aggiornato:** 2026-11-10\n" % repo.resolve()), stato)
        indice = (v / "projects" / "INDEX.md").read_text(encoding="utf-8")
        self.assertTrue(indice.endswith("| [[projects/gamma/STATE\\|gamma]] | Python, SQLite | <stato in 5 parole> | media | 2026-11-10 |\n"), indice)
        info = server.progetti_indice(v)["gamma"]
        self.assertEqual((info["priorita"], info["cartelle"]), ("media", [repo.resolve()]))
        self.assertIn("gamma", [n["nome"] for n in server.mappa(ADESSO, piano_file=v / "docs" / "piano.md", vault=v)["nodi"]])

    def test_senza_repo_stack_e_priorita_restano_i_segnaposto(self):
        v = vault_con_template()
        server.nuovo_progetto("gamma", "", "", "", vault=v, oggi="2026-11-10")
        self.assertIn("- **Repo:** <percorso locale", (v / "projects" / "gamma" / "STATE.md").read_text(encoding="utf-8"))
        self.assertIn("| [[projects/gamma/STATE\\|gamma]] | <stack> | <stato in 5 parole> | <alta / media / bassa> | 2026-11-10 |", (v / "projects" / "INDEX.md").read_text(encoding="utf-8"))

    def test_la_riga_va_in_fondo_alla_tabella_e_il_crlf_resta(self):
        v = vault_con_template()
        indice = v / "projects" / "INDEX.md"
        # su Windows write_text ha già scritto CRLF: si riparte da LF per non raddoppiare il \r
        indice.write_bytes(indice.read_bytes().replace(b"\r\n", b"\n").replace(b"\n", b"\r\n") + b"\r\nNota sotto la tabella\r\n")
        server.nuovo_progetto("gamma", vault=v, oggi="2026-11-10")
        righe = indice.read_bytes().split(b"\r\n")
        self.assertTrue(righe[4].startswith(b"| [[projects/gamma/STATE"), righe)
        self.assertEqual(righe[5:], [b"", b"Nota sotto la tabella", b""])
        self.assertNotIn(b"\n", indice.read_bytes().replace(b"\r\n", b""))

    def test_dati_non_validi_non_scrivono_nulla(self):
        v = vault_con_template()
        (v / "config.json").write_text(json.dumps({"moduli": {"riservata": {"attivo": True, "cartella": "projects/confidential-notes"}}}), encoding="utf-8")
        senza_git = v / "senza-git"
        senza_git.mkdir()
        nel_lavoro = v / "projects" / "lavoro" / "cliente"
        (nel_lavoro / ".git").mkdir(parents=True)
        buono = v / "repo-alfa"
        (buono / ".git").mkdir()
        prima = (v / "projects" / "INDEX.md").read_bytes()
        casi = [(n, None, None, None, "nome") for n in ("Gamma", "-gamma", "ga mma", "../gamma", "ga/mma", "lavoro", "con", "com1", "confidential-notes", "", "x" * 61, 5, None)]
        casi += [("gamma", r, None, None, "repo") for r in ("relativo/repo", str(v / "manca"), str(senza_git), str(nel_lavoro), "\\\\server\\share\\repo", "//server/share/repo",
                                                           str(buono) + "\nx", str(buono) + "|x", "x" * 401, 5)]
        casi += [("gamma", None, s, None, "stack") for s in ("a|b", "a\nb", "<b>", "x" * 201, "a‮b", 5)]
        casi += [("gamma", None, None, p, "priorita") for p in ("urgente", "Alta", 3)]
        for nome, repo, stack, priorita, campo in casi:
            with self.subTest(nome=nome, repo=repo, stack=stack, priorita=priorita):
                with self.assertRaises(ValueError) as c:
                    server.nuovo_progetto(nome, repo, stack, priorita, vault=v)
                self.assertEqual(str(c.exception), campo)
        self.assertEqual((v / "projects" / "INDEX.md").read_bytes(), prima)
        self.assertFalse((v / "projects" / "gamma").exists())

    def test_la_cartella_riservata_predefinita_non_e_un_nome_ne_un_repo(self):
        v = vault_con_template()
        riservata = "_" + "private"  # spezzato: la regola deny su Bash blocca ogni comando che contiene il nome
        repo = v / "projects" / riservata / "cliente"
        (repo / ".git").mkdir(parents=True)
        for nome, percorso, campo in ((riservata, None, "nome"), ("gamma", str(repo), "repo")):
            with self.assertRaises(ValueError) as c:
                server.nuovo_progetto(nome, percorso, vault=v)
            self.assertEqual(str(c.exception), campo)

    def test_progetto_che_esiste_gia_anche_con_altre_maiuscole(self):
        v = vault_con_template()
        (v / "projects" / "Delta").mkdir()
        prima = (v / "projects" / "INDEX.md").read_bytes()
        for nome in ("alfa", "delta"):
            with self.assertRaises(RuntimeError) as c:
                server.nuovo_progetto(nome, vault=v)
            self.assertEqual(str(c.exception), "esiste")
        self.assertEqual((v / "projects" / "INDEX.md").read_bytes(), prima)
        self.assertEqual((v / "projects" / "alfa" / "STATE.md").read_text(encoding="utf-8").splitlines()[0], "# alfa")

    def test_percorsi_di_rete_e_riservati_scartati_prima_di_toccare_il_disco(self):
        # «/\srv\share» non comincia con \\ ma Path lo legge come percorso di rete: exists() aprirebbe una connessione verso srv
        v = vault_con_template()
        dentro = v / "projects" / "LAVORO" / "cliente"  # altre maiuscole: su NTFS e APFS è la stessa cartella
        vero = server.Path.resolve

        def solo_il_vault(percorso, *a, **k):  # il vault si può risolvere, il percorso scritto dall'utente no
            if percorso != v:
                raise AssertionError("disco toccato: %s" % percorso)
            return vero(percorso, *a, **k)

        casi = ["\\\\srv\\share\\repo", "//srv/share/repo", "\\/srv/share/repo", "\\\\?\\C:\\repo", "\\\\.\\pipe\\x", str(dentro)]
        if os.name == "nt":  # altrove è il nome, strano ma locale, di una cartella sotto /
            casi.append("/\\srv\\share\\repo")
        with mock.patch.object(server.Path, "resolve", solo_il_vault), mock.patch.object(server.Path, "exists", side_effect=AssertionError("disco toccato")):
            for repo in casi:
                with self.subTest(repo=repo):
                    with self.assertRaises(ValueError) as c:
                        server._repo_del_progetto(repo, v, {"lavoro"})
                    self.assertEqual(str(c.exception), "repo")

    def test_wikilink_e_backtick_non_entrano_nelle_righe(self):
        v = vault_con_template()
        for stack in ("[[projects/alfa/STATE]]", "vedi ]] qui", "`rm -rf`"):
            with self.subTest(stack=stack), self.assertRaises(ValueError) as c:
                server.nuovo_progetto("gamma", None, stack, vault=v)
            self.assertEqual(str(c.exception), "stack")
        self.assertFalse((v / "projects" / "gamma").exists())

    def test_senza_template_non_crea_nulla(self):
        v = vault_finto("## A\n")
        with self.assertRaises(RuntimeError) as c:
            server.nuovo_progetto("gamma", vault=v)
        self.assertEqual(str(c.exception), "template")
        self.assertFalse((v / "projects" / "gamma").exists())

    def test_se_l_indice_non_si_scrive_lo_state_si_toglie(self):
        v = vault_con_template()
        with mock.patch.object(server, "_scrivi_atomico", side_effect=OSError("disco pieno")), self.assertRaises(OSError):
            server.nuovo_progetto("gamma", vault=v)
        self.assertFalse((v / "projects" / "gamma").exists())


class PrioritaTest(unittest.TestCase):
    def test_cambia_solo_la_cella_della_priorita(self):
        v = vault_finto("## A\n")
        indice = v / "projects" / "INDEX.md"
        self.assertEqual(server.imposta_priorita("Beta", "bassa", vault=v), {"ok": True, "priorita": "bassa"})
        self.assertEqual(indice.read_text(encoding="utf-8").splitlines()[2:], [
            "| [[projects/alfa/STATE\\|alfa]] | Stack | Stato | alta | 2026-11-09 |",
            "| [[projects/beta/STATE\\|beta]] | Stack | Stato | bassa | 2026-11-09 |"])
        self.assertEqual(server.progetti_indice(v)["beta"]["priorita"], "bassa")

    def test_crlf_conservato(self):
        v = vault_finto("## A\n")
        indice = v / "projects" / "INDEX.md"
        indice.write_bytes(indice.read_bytes().replace(b"\r\n", b"\n").replace(b"\n", b"\r\n"))
        server.imposta_priorita("alfa", "media", vault=v)
        self.assertIn(b"| Stato | media | 2026-11-09 |\r\n", indice.read_bytes())
        self.assertNotIn(b"\n", indice.read_bytes().replace(b"\r\n", b""))

    def test_valore_non_valido_progetto_assente_o_del_lavoro(self):
        v = vault_finto("## A\n")
        indice = v / "projects" / "INDEX.md"
        with indice.open("a") as i:
            i.write("| [[projects" "/" "lavoro" "/cliente/STATE\\|cliente]] | Stack | Stato | alta | 2026-11-09 |\n")  # spezzato: il template non lo contiene per intero
        prima = indice.read_bytes()
        for nome, priorita in (("alfa", "urgente"), ("alfa", "Alta"), ("alfa", None), (5, "alta"), ("cliente", "bassa")):
            with self.subTest(nome=nome, priorita=priorita), self.assertRaises(ValueError):
                server.imposta_priorita(nome, priorita, vault=v)
        with self.assertRaises(LookupError):
            server.imposta_priorita("manca", "alta", vault=v)
        self.assertEqual(indice.read_bytes(), prima)

    def test_riga_senza_alias_o_con_un_nome_riservato_non_si_tocca(self):
        v = vault_finto("## A\n")
        indice = v / "projects" / "INDEX.md"
        riservata = "_" + "private"  # spezzato: la regola deny su Bash blocca ogni comando che contiene il nome
        indice.write_text("| [[projects/alfa/STATE]] | Stack | Stato | alta | 2026-11-09 | nota |\n"
                          "| [[projects/%s/STATE\\|%s]] | Stack | Stato | alta | 2026-11-09 |\n" % (riservata, riservata), encoding="utf-8")
        prima = indice.read_bytes()
        with self.assertRaises(RuntimeError) as c:  # senza \| la cella 5 è la data, non la priorità
            server.imposta_priorita("alfa", "bassa", vault=v)
        self.assertEqual(str(c.exception), "riga")
        with self.assertRaises(ValueError):
            server.imposta_priorita(riservata, "bassa", vault=v)
        self.assertEqual(indice.read_bytes(), prima)

    def test_riga_senza_le_colonne_attese(self):
        v = vault_finto("## A\n")
        indice = v / "projects" / "INDEX.md"
        indice.write_text("| [[projects/alfa/STATE\\|alfa]] | Stack |\n", encoding="utf-8")
        with self.assertRaises(RuntimeError) as c:
            server.imposta_priorita("alfa", "alta", vault=v)
        self.assertEqual(str(c.exception), "riga")
        self.assertEqual(indice.read_text(encoding="utf-8"), "| [[projects/alfa/STATE\\|alfa]] | Stack |\n")


class RotteMappaTest(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.srv = server.ThreadingHTTPServer(("127.0.0.1", 0), server.Gestore)
        cls.porta = cls.srv.server_address[1]
        server.HOST_OK.add("127.0.0.1:%d" % cls.porta)
        threading.Thread(target=cls.srv.serve_forever, daemon=True).start()

    @classmethod
    def tearDownClass(cls):
        cls.srv.shutdown()
        cls.srv.server_close()

    def setUp(self):
        self.v = vault_finto("## A\n- [ ] #alfa uno\n")
        server.ULTIMI_AVVII.clear()
        for p in (mock.patch.object(server, "VAULT", self.v),
                  mock.patch.object(server.percorsi, "cartella_log", lambda *a, **k: self.v / "log")):
            p.start()
            self.addCleanup(p.stop)

    def post_json(self, percorso, corpo):
        c = http.client.HTTPConnection("127.0.0.1", self.porta, timeout=10)
        c.request("POST", percorso, json.dumps(corpo), {"Content-Type": "application/json", "X-Azione": "conferma"})
        r = c.getresponse()
        out = (r.status, json.loads(r.read() or b"{}"))
        c.close()
        return out

    def test_piano_aggiungi_rotta(self):
        self.assertEqual(self.post_json("/api/piano/aggiungi", {"testo": "nuova"}), (200, {"ok": True}))
        self.assertTrue(self.v.joinpath("docs", "piano.md").read_text().endswith("- [ ] nuova\n"))
        self.assertEqual(self.post_json("/api/piano/aggiungi", {"testo": "nuova"}), (409, {"errore": "doppia"}))
        for corpo, atteso in (({"testo": ""}, 400), ({"x": 1}, 400), ({"testo": "z"}, 403)):
            c = http.client.HTTPConnection("127.0.0.1", self.porta, timeout=10)
            h = {"Content-Type": "application/json"}
            if atteso != 403:
                h["X-Azione"] = "conferma"
            c.request("POST", "/api/piano/aggiungi", json.dumps(corpo), h)
            self.assertEqual(c.getresponse().status, atteso)
            c.close()

    def test_409_ha_un_codice(self):
        self.v.joinpath("docs", "piano.md").write_text("## A\n- [x] doppia\n- [ ] doppia\n- [ ] #alfa uno\n", encoding="utf-8")
        self.assertEqual(self.post_json("/api/mappa/stato", {"data": None, "testo": "doppia", "stato": "fatto"}), (409, {"errore": "doppia"}))
        with mock.patch.object(server.sys, "platform", "darwin"), mock.patch.object(server.subprocess, "run", return_value=FinteEsito(0)) as run:
            self.assertEqual(self.post_json("/api/mappa/avvia", {"data": None, "testo": "doppia"}), (409, {"errore": "doppia"}))
            run.assert_not_called()
            self.assertEqual(self.post_json("/api/mappa/avvia", {"data": None, "testo": "#alfa uno"})[0], 200)
            self.assertEqual(self.post_json("/api/mappa/avvia", {"data": None, "testo": "#alfa uno"}), (409, {"errore": "ripetuto"}))
        server.ULTIMI_AVVII.clear()
        with mock.patch.object(server.sys, "platform", "darwin"), mock.patch.object(server.subprocess, "run", return_value=FinteEsito(1)):
            self.v.joinpath("docs", "piano.md").write_text("## A\n- [ ] #alfa uno\n", encoding="utf-8")
            self.assertEqual(self.post_json("/api/mappa/avvia", {"data": None, "testo": "#alfa uno"}), (409, {"errore": "apertura"}))

    def post(self, percorso, corpo, azione=True):
        c = http.client.HTTPConnection("127.0.0.1", self.porta, timeout=10)
        h = {"Content-Type": "application/json"}
        if azione:
            h["X-Azione"] = "conferma"
        c.request("POST", percorso, json.dumps(corpo), h)
        r = c.getresponse()
        r.read()
        c.close()
        return r.status

    def test_stato_senza_header_403(self):
        self.assertEqual(self.post("/api/mappa/stato", {"data": None, "testo": "x", "stato": "fatto"}, azione=False), 403)

    def test_stato_non_valido_400_assente_404_ok_200(self):
        self.assertEqual(self.post("/api/mappa/stato", {"data": None, "testo": "#alfa uno", "stato": "boh"}), 400)
        self.assertEqual(self.post("/api/mappa/stato", {"data": None, "testo": "#alfa uno"}), 400)
        self.assertEqual(self.post("/api/mappa/stato", {"data": None, "testo": "manca", "stato": "fatto"}), 404)
        self.assertEqual(self.post("/api/mappa/stato", {"data": None, "testo": "#alfa uno", "stato": "in_corso"}), 200)
        self.assertIn("- [~] #alfa uno", (self.v / "docs" / "piano.md").read_text(encoding="utf-8"))

    def test_nuovo_403_400_409_200(self):
        piano = self.v / "docs" / "piano.md"
        self.assertEqual(self.post("/api/mappa/nuovo", {"tag": "alfa", "testo": "due"}, azione=False), 403)
        for corpo in ({"tag": "alfa"}, {"testo": "due"}, {"tag": "alfa", "testo": "<i>"}, {"tag": "alfa", "testo": "a\nb"}, {"tag": 3, "testo": "due"}):
            self.assertEqual(self.post("/api/mappa/nuovo", corpo), 400)
        self.assertEqual(piano.read_text(encoding="utf-8"), "## A\n- [ ] #alfa uno\n")
        self.assertEqual(self.post_json("/api/mappa/nuovo", {"tag": "alfa", "testo": "uno"}), (409, {"errore": "doppia"}))
        self.assertEqual(self.post_json("/api/mappa/nuovo", {"tag": "alfa", "testo": "due"}), (200, {"ok": True, "riga": "- [ ] #alfa due"}))
        self.assertEqual(piano.read_text(encoding="utf-8"), "## A\n- [ ] #alfa uno\n- [ ] #alfa due\n")

    def test_progetto_403_400_409_200(self):
        (self.v / "templates").mkdir()
        (self.v / "templates" / "STATE.md").write_text("# {{title}}\n- **Repo:** <percorso>\n- **Aggiornato:** {{date:YYYY-MM-DD}}\n", encoding="utf-8")
        (self.v / "templates" / "project-index-row.md").write_text("| [[projects/<nome>/STATE\\|<nome>]] | <stack> | <stato> | <alta / media / bassa> | {{date:YYYY-MM-DD}} |\n", encoding="utf-8")
        self.assertEqual(self.post("/api/mappa/progetto", {"nome": "gamma"}, azione=False), 403)
        self.assertEqual(self.post_json("/api/mappa/progetto", {"nome": "Gamma"}), (400, {"errore": "nome"}))
        self.assertEqual(self.post_json("/api/mappa/progetto", {"nome": "gamma", "repo": "relativo"}), (400, {"errore": "repo"}))
        self.assertEqual(self.post_json("/api/mappa/progetto", {}), (400, {"errore": "nome"}))
        self.assertEqual(self.post_json("/api/mappa/progetto", {"nome": "alfa"}), (409, {"errore": "esiste"}))
        self.assertFalse((self.v / "projects" / "gamma").exists())
        self.assertEqual(self.post_json("/api/mappa/progetto", {"nome": "gamma", "repo": "", "stack": "Python", "priorita": "alta"}), (200, {"ok": True, "nome": "gamma"}))
        self.assertTrue((self.v / "projects" / "gamma" / "STATE.md").is_file())

    def test_progetto_errore_sconosciuto_non_porta_testo_al_client(self):
        # resolve() su un giro di link solleva RuntimeError con il percorso dentro: al client va solo un codice
        with mock.patch.object(server, "nuovo_progetto", side_effect=RuntimeError("Symlink loop from 'C:\\Users\\ada\\x'")):
            self.assertEqual(self.post_json("/api/mappa/progetto", {"nome": "gamma"}), (409, {"errore": "errore"}))
        with mock.patch.object(server, "imposta_priorita", side_effect=UnicodeDecodeError("utf-8", b"\xff", 0, 1, "invalid start byte")):
            self.assertEqual(self.post_json("/api/mappa/priorita", {"nome": "beta", "priorita": "alta"}), (400, {"errore": "dati"}))

    def test_priorita_403_400_404_200(self):
        self.assertEqual(self.post("/api/mappa/priorita", {"nome": "beta", "priorita": "alta"}, azione=False), 403)
        self.assertEqual(self.post_json("/api/mappa/priorita", {"nome": "beta", "priorita": "urgente"}), (400, {"errore": "priorita"}))
        self.assertEqual(self.post("/api/mappa/priorita", {"nome": "manca", "priorita": "alta"}), 404)
        self.assertEqual(self.post_json("/api/mappa/priorita", {"nome": "beta", "priorita": "alta"}), (200, {"ok": True, "priorita": "alta"}))
        self.assertIn("| Stato | alta | 2026-11-09 |\n", (self.v / "projects" / "INDEX.md").read_text(encoding="utf-8").splitlines(keepends=True)[3])

    def test_avvia_su_linux_501(self):
        with mock.patch.object(server.sys, "platform", "linux"), mock.patch.object(server.subprocess, "run") as run:
            self.assertEqual(self.post("/api/mappa/avvia", {"data": None, "testo": "#alfa uno"}), 501)
            run.assert_not_called()

    def test_avvia_su_mac_200_e_corpo_non_valido_400(self):
        with mock.patch.object(server.sys, "platform", "darwin"), mock.patch.object(server.subprocess, "run", return_value=FinteEsito(0)):
            self.assertEqual(self.post("/api/mappa/avvia", {"data": None, "testo": 5}), 400)
            self.assertEqual(self.post("/api/mappa/avvia", {"data": None, "testo": "#alfa uno"}), 200)
            self.assertEqual(self.post("/api/mappa/avvia", {"data": None, "testo": "#alfa uno"}), 409)


if __name__ == "__main__":
    unittest.main()

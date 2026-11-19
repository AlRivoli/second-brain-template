#!/usr/bin/env python3
"""Test dei marcatori di piano.md e dello stato derivato dei task."""
import importlib.util
import time
import unittest
from datetime import date
from pathlib import Path

RADICE = Path(__file__).resolve().parent.parent


def carica(percorso, nome):
    spec = importlib.util.spec_from_file_location(nome, percorso)
    modulo = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(modulo)
    return modulo


d = carica(RADICE / "scripts" / "dipendenze.py", "dipendenze")


def voce(stato, **marcatori):
    return {"stato": stato, "marcatori": marcatori}


class MarcatoriTest(unittest.TestCase):
    def test_separa_marcatori_in_coda(self):
        self.assertEqual(d.separa_marcatori("#sb Harness 10 · prova id:h10 dopo:h9,h11 chi:te"),
                         ("#sb Harness 10 · prova", {"id": "h10", "dopo": ["h9", "h11"], "chi": "te"}))

    def test_tutte_le_chiavi(self):
        self.assertEqual(d.separa_marcatori("x obiettivo:ob-1 repo:a.b,c_d stima:1,5h"),
                         ("x", {"obiettivo": "ob-1", "repo": ["a.b", "c_d"], "stima": "1,5h"}))

    def test_testo_simile_a_marcatore_resta_testo(self):
        for t in ("leggi https://x.it/a:b", "vedi nota:3", "dopo: i merge", "id:H9 maiuscolo", "chi:lui",
                  "a dopo:h1,,h2", "a stima:3", "a id:#x"):
            self.assertEqual(d.separa_marcatori(t), (t, {}))

    def test_marcatore_in_mezzo_resta_testo(self):
        self.assertEqual(d.separa_marcatori("fare dopo:h1 poi altro id:x1"), ("fare dopo:h1 poi altro", {"id": "x1"}))

    def test_chiave_ripetuta_ferma_il_blocco(self):
        self.assertEqual(d.separa_marcatori("t id:a id:b"), ("t id:a", {"id": "b"}))

    def test_voce_piano_riconosce_le_caselle(self):
        self.assertEqual(d.VOCE_PIANO.match("- [~] testo  ").groups(), ("~", "testo"))
        self.assertIsNone(d.VOCE_PIANO.match("- [?] testo"))

    def test_voce_piano_lineare_sugli_spazi_lunghi(self):
        # the lazy `(.+?)\s*$` form re-scanned the whitespace run at every step: quadratic on a long run
        riga = "- [ ] a" + " " * 50000 + "b"
        inizio = time.perf_counter()
        self.assertEqual(d.VOCE_PIANO.match(riga).group(2), "a" + " " * 50000 + "b")
        self.assertEqual(d.leggi_voci(riga + "   ")[0]["testo"], "a" + " " * 50000 + "b")
        self.assertLess(time.perf_counter() - inizio, 0.5)


class StatiDerivatiTest(unittest.TestCase):
    def test_stati_pronto_attesa_fatto_incoerente(self):
        v = [voce("fatto", id="a"), voce("da_fare", id="b", dopo=["a"]), voce("da_fare", id="c", dopo=["b"]), voce("in_corso", dopo=["c"])]
        self.assertEqual([s["derivato"] for s in d.stati_derivati(v)], ["fatto", "pronto", "in_attesa", "incoerente"])
        self.assertEqual(d.stati_derivati(v)[2]["aspetta"], [1])

    def test_in_corso_senza_attese(self):
        self.assertEqual(d.stati_derivati([voce("in_corso")])[0],
                         {"derivato": "in_corso", "aspetta": [], "errore": None, "mancanti": []})

    def test_riferimento_rotto_e_id_doppio_sono_errore(self):
        v = [voce("da_fare", dopo=["zz"]), voce("da_fare", id="x"), voce("da_fare", id="x"), voce("da_fare", dopo=["x"])]
        s = d.stati_derivati(v)
        self.assertEqual([x["errore"] for x in s], ["riferimento", "id_doppio", "id_doppio", "riferimento"])
        self.assertEqual([x["derivato"] for x in s], ["errore"] * 4)
        self.assertEqual(s[0]["mancanti"], ["zz"])

    def test_ciclo_e_chi_ne_dipende(self):
        v = [voce("da_fare", id="a", dopo=["b"]), voce("da_fare", id="b", dopo=["a"]), voce("da_fare", dopo=["a"])]
        self.assertEqual([x["derivato"] for x in d.stati_derivati(v)], ["errore", "errore", "in_attesa"])

    def test_auto_dipendenza_e_ciclo(self):
        self.assertEqual(d.stati_derivati([voce("da_fare", id="a", dopo=["a"])])[0]["errore"], "ciclo")

    def test_ogni_nodo_di_un_ciclo_e_errore(self):
        # a->b->a and a->c->b->a: c sits on a cycle even though a plain back-edge scan would miss it.
        v = [voce("da_fare", id="a", dopo=["b", "c"]), voce("da_fare", id="b", dopo=["a"]),
             voce("da_fare", id="c", dopo=["b"]), voce("da_fare", id="d", dopo=["c"])]
        self.assertEqual([x["errore"] for x in d.stati_derivati(v)], ["ciclo", "ciclo", "ciclo", None])

    def test_fatto_vince_sull_errore_ma_l_errore_resta_visibile(self):
        s = d.stati_derivati([voce("fatto", dopo=["zz"])])[0]
        self.assertEqual((s["derivato"], s["errore"]), ("fatto", "riferimento"))

    def test_catena_lunga_non_satura_la_ricorsione(self):
        n = 5000
        v = [voce("da_fare", id=f"t{i}", dopo=[f"t{i + 1}"]) for i in range(n - 1)] + [voce("da_fare", id=f"t{n - 1}")]
        self.assertEqual(d.stati_derivati(v)[-1]["derivato"], "pronto")


class LeggiProblemiTest(unittest.TestCase):
    def test_leggi_voci_con_numero_di_riga(self):
        v = d.leggi_voci("## A\n- [ ] uno id:a\nprosa\n- [~] due dopo:a\n")
        self.assertEqual(v, [{"riga": 2, "stato": "da_fare", "testo": "uno", "tag": None, "marcatori": {"id": "a"}},
                             {"riga": 4, "stato": "in_corso", "testo": "due", "tag": None, "marcatori": {"dopo": ["a"]}}])

    def test_leggi_voci_ha_il_tag(self):
        self.assertEqual([v["tag"] for v in d.leggi_voci("## A\n- [ ] #Progetto-A x\n- [ ] senza\n")], ["progetto-a", None])

    def test_nomi_repo(self):
        n, doppi = d.nomi_repo(["C:\\src\\p\\api", "C:\\src\\p\\web", "nessuno", "", "D:\\altro\\api"])
        self.assertEqual((list(n), doppi), (["web"], ["api"]))

    def test_nomi_repo_salta_il_segnaposto_del_template(self):
        # the Repo line of templates/STATE.md, left as is in a new project without a repo
        segnaposto = (RADICE / "templates" / "STATE.md").read_text(encoding="utf-8").split("- **Repo:** ", 1)[1].splitlines()[0]
        self.assertTrue(segnaposto.startswith("<"))
        self.assertEqual(d.nomi_repo([segnaposto]), ({}, []))
        self.assertEqual(list(d.nomi_repo([segnaposto, "/srv/p/api"])[0]), ["api"])

    def test_nomi_repo_percorsi_posix_e_windows_su_ogni_sistema(self):
        n, doppi = d.nomi_repo(["/srv/p/api", "C:\\src\\p\\web\\", "/srv/x/cli/"])
        self.assertEqual((n, doppi), ({"api": "/srv/p/api", "web": "C:\\src\\p\\web\\", "cli": "/srv/x/cli/"}, []))

    def test_nomi_repo_senza_radici_ne_punti(self):
        # a root, a drive or a path ending in . or .. has no folder name: never a candidate, on any OS
        n, doppi = d.nomi_repo(["C:\\", "C:", "C:\\.", "C:\\x\\..", "/", "/tmp/.", "/srv/x/..", "D:\\a\\api"])
        self.assertEqual((n, doppi), ({"api": "D:\\a\\api"}, []))

    def test_nomi_repo_la_stessa_riga_ripetuta_non_e_un_doppio(self):
        # same as the server, which drops repeated identical paths before naming them
        n, doppi = d.nomi_repo(["C:\\src\\p\\api", " C:\\src\\p\\api "])
        self.assertEqual((n, doppi), ({"api": "C:\\src\\p\\api"}, []))

    def test_problemi_repo(self):
        voci = d.leggi_voci("## A\n- [ ] #progetto-a a repo:api\n- [ ] #progetto-a b repo:zz\n- [ ] c repo:api\n")
        trovati = d.problemi(voci, repo={"progetto-a": {"api", "web"}})
        self.assertEqual([r for r, _ in trovati], [3, 4])
        self.assertIn("repo:zz non è un repo di progetto-a: usa uno di api, web", trovati[0][1])
        self.assertIn("repo:api su un task senza progetto", trovati[1][1])
        self.assertEqual(d.problemi(voci), [])

    def test_problemi_repo_con_tag_di_un_argomento_o_progetto_senza_repo(self):
        voci = d.leggi_voci("- [ ] #idee a repo:api,web\n- [ ] #progetto-a b repo:api\n")
        trovati = d.problemi(voci, repo={"progetto-a": set()})
        self.assertEqual([r for r, _ in trovati], [1, 2])
        self.assertIn("repo:api,web su un task senza progetto", trovati[0][1])

    def test_problemi_con_numero_di_riga(self):
        voci = d.leggi_voci("## A\n- [ ] uno id:a\n- [ ] due dopo:zz\n")
        self.assertEqual([r for r, _ in d.problemi(voci)], [3])

    def test_problemi_per_ogni_tipo(self):
        voci = d.leggi_voci("- [ ] a id:x\n- [ ] b id:x\n- [ ] c id:p dopo:q\n- [ ] d id:q dopo:p\n- [ ] e\n")
        self.assertEqual([r for r, _ in d.problemi(voci)], [1, 2, 3, 4])
        self.assertTrue(all(m for _, m in d.problemi(voci)))

    def test_marcatore_malformato_in_coda_e_un_avviso(self):
        # a bad trailing token stops the marker scan, so every marker on the line is lost: fail-open, so say it
        for riga, token in (("x dopo:a chi:te !", "dopo:a"), ("x chi:Te", "chi:Te"), ("x chi:te.", "chi:te."), ("x dopo:a, b", "dopo:a,")):
            with self.subTest(riga=riga):
                trovati = d.problemi(d.leggi_voci("- [ ] " + riga + "\n"))
                self.assertEqual(len(trovati), 1, trovati)
                self.assertEqual(trovati[0][0], 1)
                self.assertIn("`%s` non è un marcatore valido" % token, trovati[0][1])

    def test_testo_normale_non_da_avvisi(self):
        for riga in ("leggi https://x.it/a:b", "vedi nota:3", "uno id:a dopo:b1 chi:te", "nessun marcatore"):
            with self.subTest(riga=riga):
                voci = d.leggi_voci("- [ ] %s\n- [x] b id:b1\n" % riga)
                self.assertEqual(d.problemi(voci), [])


class ObiettiviTest(unittest.TestCase):
    def test_leggi_obiettivi(self):
        o, p = d.leggi_obiettivi("# Obiettivi\n\n- harness: Harness per tutti i progetti\n- mappa: Mappa <con> \"obiettivi\" & repo\n")
        self.assertEqual([(k, v["titolo"]) for k, v in o.items()], [("harness", "Harness per tutti i progetti"), ("mappa", "Mappa <con> \"obiettivi\" & repo")])
        self.assertEqual(p, [])

    def test_leggi_obiettivi_problemi(self):
        _, p = d.leggi_obiettivi("- Harness: X\n- a: \n- a: uno\n- a: due\n- b: " + "x" * 121 + "\n")
        self.assertEqual([r for r, _ in p], [1, 2, 4, 5])

    def test_leggi_obiettivi_ignora_il_resto_e_accetta_120_caratteri(self):
        o, p = d.leggi_obiettivi("# T\ntesto - a: b\n  - a: b\n- a: " + "x" * 120 + "\n")
        self.assertEqual((list(o), p), (["a"], []))

    def test_leggi_obiettivi_con_bom_iniziale_definisce_la_riga_1(self):
        o, p = d.leggi_obiettivi("\ufeff- a: uno\n- b: due\n")
        self.assertEqual((list(o), p), (["a", "b"], []))

    def test_leggi_obiettivi_rifiuta_caratteri_di_controllo_e_direzione(self):
        for cattivo in ("\u202e", "\u2066", "\u2069", "\x07", "\u200b"):
            with self.subTest(carattere=hex(ord(cattivo))):
                o, p = d.leggi_obiettivi(f"- a: uno{cattivo}due\n- b: ok\n")
                self.assertEqual((list(o), p), (["b"], [(1, "titolo con caratteri di controllo o di direzione: toglili")]))

    def test_riga_non_valida_dice_come_scriverla(self):
        _, p = d.leggi_obiettivi("- senza due punti\n")
        self.assertEqual(p, [(1, "riga non valida: scrivi `- slug: titolo`")])

    def test_problemi_obiettivo_non_definito(self):
        voci = d.leggi_voci("## A\n- [ ] uno obiettivo:mappa\n- [ ] due obiettivo:altro\n")
        self.assertEqual([r for r, _ in d.problemi(voci, {"mappa": "Mappa"})], [3])
        self.assertEqual(d.problemi(voci), [])
        self.assertIn("obiettivo:altro non è definito in docs/obiettivi.md: aggiungi `- altro: <titolo>`", d.problemi(voci, {})[1][1])


    def test_obiettivo_formato_esteso(self):
        o, p = d.leggi_obiettivi("- rel: Rilascio scadenza:2026-12-04 giorni:lun,mar,mer piano:docs/superpowers/plans/x.md\n- vec: Vecchio stile\n")
        self.assertEqual(o["rel"]["titolo"], "Rilascio")
        self.assertEqual(o["rel"]["scadenza"], date(2026, 12, 4))
        self.assertEqual(o["rel"]["giorni"], frozenset({0, 1, 2}))
        self.assertEqual(o["rel"]["piano"], "docs/superpowers/plans/x.md")
        self.assertEqual(o["vec"], {"titolo": "Vecchio stile", "scadenza": None, "giorni": None, "piano": None})
        self.assertEqual(p, [])

    def test_obiettivo_giorni_tutti_e_marcatori_in_ordine_qualsiasi(self):
        o, p = d.leggi_obiettivi("- a: A giorni:tutti scadenza:2026-12-05\n")
        self.assertEqual((o["a"]["giorni"], o["a"]["scadenza"], p), (frozenset(range(7)), date(2026, 12, 5), []))

    def test_obiettivo_marcatori_non_validi(self):
        _, p = d.leggi_obiettivi("- a: A scadenza:2026-13-01\n- b: B giorni:lunedi\n- c: C piano:../x.md\n- e: E piano:C:/x.md\n")
        self.assertEqual([r for r, _ in p], [1, 2, 3, 4])

    def test_obiettivo_marcatore_non_valido_resta_definito_con_il_calendario_del_vault(self):
        # a bad `giorni:` is a warning and falls back to the vault calendar: undefining the goal would also flag every task using it
        o, p = d.leggi_obiettivi("- b: B scadenza:2026-12-04 giorni:\n")
        self.assertIsNone(o["b"]["giorni"])
        self.assertEqual(len(p), 1)
        self.assertIn("giorni:", p[0][1])
        # the scan stopped at `giorni:`, so the deadline before it is lost too: fail-open, so the warning names it
        self.assertIsNone(o["b"]["scadenza"])
        self.assertIn("non si leggono neanche `scadenza:`", p[0][1])

    def test_obiettivo_piano_oltre_200_caratteri_non_vale(self):
        self.assertEqual((d.percorso_piano_valido("x" * 200), d.percorso_piano_valido("x" * 201)), (True, False))

    def test_obiettivo_piano_con_spazi_assoluto_o_risalita_e_un_avviso(self):
        for valore in ("/etc/x.md", "a/../b.md", "a b.md", "C:\\x.md", "x" * 201):
            with self.subTest(valore=valore):
                o, p = d.leggi_obiettivi(f"- a: A piano:{valore}\n")
                self.assertEqual([r for r, _ in p], [1])
                self.assertIsNone(o.get("a", {}).get("piano"))  # 201 characters also make the title too long

    def test_obiettivo_data_in_formato_compatto_non_vale(self):
        o, p = d.leggi_obiettivi("- a: A scadenza:20261204\n")
        self.assertEqual(([r for r, _ in p], o["a"]["scadenza"]), ([1], None))

    def test_obiettivo_chiave_ripetuta_e_un_avviso(self):
        o, p = d.leggi_obiettivi("- a: A scadenza:2026-12-01 scadenza:2026-12-04\n")
        self.assertEqual((o["a"]["scadenza"], [r for r, _ in p]), (date(2026, 12, 4), [1]))
        self.assertNotIn("data valida", p[0][1])

    def test_obiettivo_solo_marcatori_e_senza_titolo(self):
        o, p = d.leggi_obiettivi("- a: scadenza:2026-12-04\n")
        self.assertEqual((o, p), ({}, [(1, "obiettivo:a senza titolo: scrivi `- a: titolo`")]))

    def test_obiettivo_parola_piano_nel_titolo_non_e_un_avviso(self):
        o, p = d.leggi_obiettivi("- a: Nuovo piano: rilascio\n")
        self.assertEqual((o["a"]["titolo"], p), ("Nuovo piano: rilascio", []))


class PianoTest(unittest.TestCase):
    def test_ore_stima(self):
        self.assertEqual((d.ore_stima("9h", 6), d.ore_stima("1,5g", 6), d.ore_stima(None, 6)), (9.0, 9.0, None))

    def test_stima_ha_un_limite(self):
        # at most 4 digits and 2 decimals: a 400-digit value would be float('inf') and break the date walk
        for valore in ("9999h", "1,25g", "0.5h"):
            self.assertEqual(d._valore("stima", valore), valore)
        for valore in ("1" * 400 + "h", "10000h", "1,255g"):
            with self.subTest(valore=valore[:12]):
                self.assertIsNone(d._valore("stima", valore))
        lungo = "stima:" + "1" * 400 + "h"
        voci = d.leggi_voci("- [ ] a " + lungo + "\n")
        self.assertNotIn("stima", voci[0]["marcatori"])  # it stays text, and the leftover is reported
        self.assertTrue(any("non è un marcatore valido" in m for _, m in d.problemi(voci)))

    def test_impostazioni_piano_default_e_errori(self):
        self.assertEqual(d.impostazioni_piano({})[0], {"ore_giorno": 6.0, "giorni": frozenset({0, 1, 2, 3, 4})})
        self.assertEqual(len(d.impostazioni_piano({"piano": {"ore_giorno": 30, "giorni_lavoro": ["xyz"]}})[1]), 2)

    def test_impostazioni_piano_valide(self):
        self.assertEqual(d.impostazioni_piano({"piano": {"ore_giorno": 7.5, "giorni_lavoro": ["sab", "dom"]}}),
                         ({"ore_giorno": 7.5, "giorni": frozenset({5, 6})}, []))

    def test_impostazioni_piano_tipi_sbagliati_usano_i_default(self):
        default = {"ore_giorno": 6.0, "giorni": frozenset(range(5))}
        for piano in ("x", {"ore_giorno": True}, {"ore_giorno": float("nan")}, {"ore_giorno": "6"}, {"giorni_lavoro": []},
                      {"giorni_lavoro": "lun"}, {"ore_giorno": 0.5}):
            with self.subTest(piano=piano):
                impostazioni, trovati = d.impostazioni_piano({"piano": piano})
                self.assertEqual((impostazioni, len(trovati)), (default, 1))
        self.assertEqual(d.impostazioni_piano(None), (default, []))


class DateObiettivoTest(unittest.TestCase):
    def calcola(self, piano, scadenza, giorni, oggi, ore_giorno=6):
        voci = d.leggi_voci(piano)
        return d.date_obiettivo(voci, d.stati_derivati(voci), "r", scadenza, giorni, ore_giorno, oggi)

    def test_date_catena_lun_ven(self):
        # a(6h) -> b(12h) -> c(6h), scadenza ven 2026-12-04, oggi lun 2026-11-30, 6h/giorno, lun-ven
        r = self.calcola("## A\n- [ ] a id:a stima:6h obiettivo:r\n- [ ] b id:b dopo:a stima:2g obiettivo:r\n- [ ] c dopo:b stima:6h obiettivo:r\n",
                         date(2026, 12, 4), frozenset(range(5)), date(2026, 11, 30))
        self.assertEqual([r["entro"][i] for i in range(3)], [date(2026, 12, 1), date(2026, 12, 3), date(2026, 12, 4)])
        self.assertEqual((r["giorniNecessari"], r["giorniDisponibili"], r["aRischio"], r["scaduto"]), (4, 5, False, False))
        self.assertEqual(r["senzaStima"], [])

    def test_date_weekend_e_senza_stima(self):
        # scadenza sab 2026-12-05: con lun-ven l'ultimo task è entro ven 4; con tutti i giorni entro sab 5; un task senza stima conta 0
        piano = "- [ ] a id:a stima:6h obiettivo:r\n- [ ] b id:b dopo:a obiettivo:r\n- [ ] c dopo:b stima:6h obiettivo:r\n"
        r = self.calcola(piano, date(2026, 12, 5), frozenset(range(5)), date(2026, 11, 30))
        self.assertEqual([r["entro"][i] for i in range(3)], [date(2026, 12, 3), date(2026, 12, 3), date(2026, 12, 4)])
        self.assertEqual((r["senzaStima"], r["giorniNecessari"]), ([1], 2))
        r = self.calcola(piano, date(2026, 12, 5), frozenset(range(7)), date(2026, 11, 30))
        self.assertEqual([r["entro"][i] for i in range(3)], [date(2026, 12, 4), date(2026, 12, 4), date(2026, 12, 5)])

    def test_calendario_vuoto_vale_lun_ven(self):
        r = self.calcola("- [ ] a stima:6h obiettivo:r\n", date(2026, 12, 5), frozenset(), date(2026, 11, 30))
        self.assertEqual((r["entro"], r["giorniDisponibili"]), ({0: date(2026, 12, 4)}, 5))

    def test_a_rischio_e_scaduto(self):
        # catena da 4 giorni con 2 giorni disponibili → aRischio; scadenza ieri con task aperti → aRischio e scaduto
        piano = ("- [ ] a id:a stima:1g obiettivo:r\n- [ ] b id:b dopo:a stima:1g obiettivo:r\n"
                 "- [ ] c id:c dopo:b stima:1g obiettivo:r\n- [ ] d dopo:c stima:1g obiettivo:r\n")
        r = self.calcola(piano, date(2026, 12, 4), frozenset(range(5)), date(2026, 12, 3))
        self.assertEqual((r["giorniNecessari"], r["giorniDisponibili"], r["aRischio"], r["scaduto"]), (4, 2, True, False))
        r = self.calcola(piano, date(2026, 12, 2), frozenset(range(5)), date(2026, 12, 3))
        self.assertEqual((r["giorniDisponibili"], r["aRischio"], r["scaduto"]), (0, True, True))
        r = self.calcola("- [ ] a obiettivo:r\n", date(2026, 12, 2), frozenset(range(5)), date(2026, 12, 3))
        self.assertEqual((r["giorniNecessari"], r["aRischio"], r["scaduto"]), (0, True, True))
        r = self.calcola("- [x] a stima:1g obiettivo:r\n", date(2026, 12, 2), frozenset(range(5)), date(2026, 12, 3))
        self.assertEqual((r["entro"], r["aRischio"], r["scaduto"]), ({}, False, False))

    def test_solo_task_aperti_dell_obiettivo_e_senza_errori(self):
        # done, other goal, broken reference and cycle get no date; a done predecessor adds nothing to the tail
        piano = ("- [x] f id:f stima:1g obiettivo:r\n- [ ] g dopo:f stima:6h obiettivo:r\n- [ ] h stima:6h obiettivo:altro\n"
                 "- [ ] rotto dopo:zz stima:6h obiettivo:r\n- [ ] p id:p dopo:q stima:6h obiettivo:r\n- [ ] q id:q dopo:p stima:6h obiettivo:r\n")
        r = self.calcola(piano, date(2026, 12, 4), frozenset(range(5)), date(2026, 11, 30))
        self.assertEqual(r["entro"], {1: date(2026, 12, 4)})
        self.assertEqual(r["giorniNecessari"], 1)

    def test_coda_e_il_ramo_piu_lungo_e_gli_altri_obiettivi_non_contano(self):
        # a -> b(6h) and a -> c(2g) -> x (other goal, 5g): a's tail is the longer branch inside the goal, 12h = 2 days
        piano = ("- [ ] a id:a stima:6h obiettivo:r\n- [ ] b dopo:a stima:6h obiettivo:r\n- [ ] c id:c dopo:a stima:2g obiettivo:r\n"
                 "- [ ] x dopo:c stima:5g obiettivo:altro\n")
        r = self.calcola(piano, date(2026, 12, 4), frozenset(range(5)), date(2026, 11, 30))
        self.assertEqual(r["entro"], {0: date(2026, 12, 2), 1: date(2026, 12, 4), 2: date(2026, 12, 4)})
        self.assertEqual(r["giorniNecessari"], 3)

    def test_arrotondamento_dei_decimali(self):
        # 0.2h + (0.4h + 5.4h) is 6.000000000000001 in floating point: still one day, not two
        piano = "- [ ] a id:a stima:0.2h obiettivo:r\n- [ ] b id:b dopo:a stima:0.4h obiettivo:r\n- [ ] c dopo:b stima:5.4h obiettivo:r\n"
        r = self.calcola(piano, date(2026, 12, 4), frozenset(range(5)), date(2026, 11, 30))
        self.assertEqual(r["giorniNecessari"], 1)

    def test_catena_oltre_la_finestra_non_va_in_ciclo(self):
        # 400 one-day tasks on a one-day-a-week calendar: more than the 366-week window, entro is clamped and the goal is at risk
        n = 400
        righe = [f"- [ ] t{i} id:t{i} stima:1g obiettivo:r" + (f" dopo:t{i - 1}" if i else "") for i in range(n)]
        r = self.calcola("\n".join(righe) + "\n", date(2026, 12, 4), frozenset({4}), date(2026, 11, 30))
        self.assertEqual(len(r["entro"]), n)
        self.assertTrue(r["aRischio"])
        self.assertEqual(r["entro"][n - 1], date(2026, 12, 4))
        self.assertLessEqual(r["entro"][0], r["entro"][1])

    def test_scadenza_vicina_al_primo_giorno_possibile(self):
        r = self.calcola("- [ ] a id:a stima:1g obiettivo:r\n- [ ] b dopo:a stima:1g obiettivo:r\n", date(1, 1, 2), frozenset(range(7)), date(1, 1, 1))
        self.assertEqual((r["entro"][0], r["entro"][1]), (date(1, 1, 1), date(1, 1, 2)))


if __name__ == "__main__":
    unittest.main()

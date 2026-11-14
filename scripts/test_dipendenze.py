#!/usr/bin/env python3
"""Test dei marcatori di piano.md e dello stato derivato dei task."""
import importlib.util
import time
import unittest
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
        self.assertEqual(v, [{"riga": 2, "stato": "da_fare", "testo": "uno", "marcatori": {"id": "a"}},
                             {"riga": 4, "stato": "in_corso", "testo": "due", "marcatori": {"dopo": ["a"]}}])

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


if __name__ == "__main__":
    unittest.main()

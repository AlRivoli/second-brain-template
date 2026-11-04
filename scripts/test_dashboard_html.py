"""Controlli statici su scripts/dashboard/index.html (nessun browser): la pagina non deve chiamare funzioni che non esistono.

Il redesign aveva tolto aggiornaVista ma setTimeout(aggiornaVista, 700) era rimasto: dopo ogni spunta riuscita la pagina
andava in ReferenceError, rimetteva la casella com'era e scriveva "spunta non salvata" anche se il file era salvato.
"""
import re
import unittest
from pathlib import Path

HTML = Path(__file__).resolve().parent / "dashboard" / "index.html"
TIMER = re.compile(r"set(?:Timeout|Interval)\(\s*([A-Za-z_$][\w$]*)\s*[,)]")


def funzioni_mancanti(html):
    """Nomi passati come funzione a setTimeout/setInterval e mai definiti (function, const, let, var)."""
    return sorted({n for n in TIMER.findall(html) if not re.search(rf"(?:function\s+|(?:const|let|var)\s+){re.escape(n)}\b", html)})


class HtmlDashboard(unittest.TestCase):
    def test_i_timer_chiamano_solo_funzioni_definite(self):
        self.assertEqual(funzioni_mancanti(HTML.read_text(encoding="utf-8")), [])

    def test_il_controllo_riconosce_il_difetto_di_prima(self):
        self.assertEqual(funzioni_mancanti("setTimeout(aggiornaVista, 700);"), ["aggiornaVista"])
        self.assertEqual(funzioni_mancanti("function a(){}\nsetInterval(a, 5);\nsetTimeout(() => a(), 1);"), [])


if __name__ == "__main__":
    unittest.main()

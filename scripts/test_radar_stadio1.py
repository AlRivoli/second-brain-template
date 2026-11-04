import importlib.util
import unittest
from pathlib import Path

RADICE = Path(__file__).resolve().parent
spec = importlib.util.spec_from_file_location("stadio1", RADICE / "radar-stadio1.py")
stadio1 = importlib.util.module_from_spec(spec)
spec.loader.exec_module(stadio1)

PROFILI = {"sito": "stack: Vue, Nuxt, Postgres. obiettivo: migrare il sito a Nuxt 4 con Postgres gestito.",
           "api": "stack: Node, Fastify. obiettivo: aggiornare Fastify e le dipendenze."}


class ParoleChiaveTest(unittest.TestCase):
    def test_una_parola_dello_stack_basta_il_resto_no(self):
        lista = [("Fastify 6 is out", "https://a/1"), ("Nuxt 4 migration guide for Postgres", "https://a/2"), ("A cat video", "https://a/3"),
                 ("Introducing the new blog post update", "https://a/4")]
        c = {x["titolo"]: x for x in stadio1.per_parole_chiave(lista, PROFILI)}
        self.assertEqual(set(c), {"Fastify 6 is out", "Nuxt 4 migration guide for Postgres"})
        self.assertEqual((c["Fastify 6 is out"]["progetto"], c["Fastify 6 is out"]["score"]), ("api", 0.5))
        self.assertEqual((c["Nuxt 4 migration guide for Postgres"]["progetto"], c["Nuxt 4 migration guide for Postgres"]["score"]), ("sito", 1.0))

    def test_le_parole_comuni_non_contano(self):
        self.assertEqual(stadio1.parole("The new blog post: introducing Vue"), {"vue"})


if __name__ == "__main__":
    unittest.main()

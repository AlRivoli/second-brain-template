import importlib.util
import tempfile
import unittest
from pathlib import Path, PurePosixPath

spec = importlib.util.spec_from_file_location("percorsi", Path(__file__).resolve().parent / "percorsi.py")
percorsi = importlib.util.module_from_spec(spec)
spec.loader.exec_module(percorsi)


class PercorsiTest(unittest.TestCase):
    def test_una_cartella_per_sistema_e_si_crea(self):
        with tempfile.TemporaryDirectory() as t:
            casa = Path(t)
            self.assertEqual(percorsi.cartella_log(casa, "darwin"), casa / "Library" / "Logs")
            self.assertEqual(percorsi.cartella_log(casa, "linux", {}), casa / ".local" / "state" / "second-brain")
            self.assertEqual(percorsi.cartella_log(casa, "linux", {"XDG_STATE_HOME": str(casa / "stato")}), casa / "stato" / "second-brain")
            self.assertEqual(percorsi.cartella_log(casa, "win32", {"LOCALAPPDATA": str(casa / "Locale")}), casa / "Locale" / "second-brain" / "logs")
            self.assertTrue((casa / ".local" / "state" / "second-brain").is_dir())

    def test_stessa_regola_di_install_jobs(self):
        radice = Path(__file__).resolve().parent.parent
        file = next((f for f in (radice / "install_jobs.py", radice / "template" / "install_jobs.py") if f.exists()), None)
        if file is None:
            self.skipTest("install_jobs.py non c'è")
        spec = importlib.util.spec_from_file_location("ij", file)
        ij = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(ij)
        with tempfile.TemporaryDirectory() as t:
            casa = Path(t)
            for sistema, piattaforma in (("macos", "darwin"), ("linux", "linux"), ("windows", "win32")):
                self.assertEqual(percorsi.cartella_log(casa, piattaforma), ij.cartella_log(sistema, casa), sistema)


if __name__ == "__main__":
    unittest.main()

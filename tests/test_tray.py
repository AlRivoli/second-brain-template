import importlib.util
import json
import os
import plistlib
import re
import shutil
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path, PureWindowsPath
from xml.sax.saxutils import unescape

RADICE = Path(__file__).resolve().parent.parent
TRAY_PS1 = RADICE / "scripts" / "tray" / "tray.ps1"
spec = importlib.util.spec_from_file_location("install_jobs", RADICE / "install_jobs.py")
ij = importlib.util.module_from_spec(spec)
spec.loader.exec_module(ij)

JOBS = json.loads((RADICE / "scripts" / "jobs.json").read_text(encoding="utf-8"))
TRAY = JOBS["tray"]
CTX = {"vault": Path("/srv/vault dir"), "home": Path("/srv/u"), "python": "/srv/py/python3", "log": Path("/srv/u/logs"), "etichetta": "second-brain"}
POWERSHELL = shutil.which("powershell.exe") if sys.platform == "win32" else None
SOLO_WINDOWS = unittest.skipUnless(POWERSHELL, "needs Windows PowerShell")
JOB_AMMESSI = r"second-brain\.(morning|feed|radar|chiusura|bozze|pulizia)"


def xml_windows(ctx=CTX):
    return ij.piano_windows("tray", TRAY, ctx)["file"][0][1].decode("utf-16")


def argomenti_task(xml):
    """The <Arguments> of the task as Task Scheduler passes them to conhost.exe."""
    return unescape(re.search(r"<Arguments>(.*?)</Arguments>", xml).group(1))


class RegistrazioneTest(unittest.TestCase):
    def test_tray_su_windows_e_macos_non_su_linux(self):
        self.assertIn("tray", ij.seleziona(JOBS, "windows"))
        self.assertIn("tray", ij.seleziona(JOBS, "macos"))
        self.assertNotIn("tray", ij.seleziona(JOBS, "linux"))
        self.assertNotIn("tray", ij.seleziona(JOBS, "linux", tutti=True))

    def test_windows_powershell_nascosto_con_virgolette_e_all_accesso(self):
        testo = xml_windows()
        args = argomenti_task(testo)
        script = PureWindowsPath("/srv/vault dir/scripts/tray/tray.ps1")
        self.assertRegex(args, r'^--headless cmd\.exe /c ""[^"]*powershell\.exe" "-NoProfile" "-NonInteractive" '
                               r'"-ExecutionPolicy" "Bypass" "-WindowStyle" "Hidden" "-File" ')
        self.assertIn('"-File" "%s" >> "' % script, args)  # vault with a space: one quoted argument
        self.assertTrue(args.endswith(' 2>&1"'))
        self.assertIn("<LogonTrigger><Enabled>true</Enabled><UserId>", testo)

    def test_windows_nessun_limite_di_tempo_ma_esci_la_chiude_davvero(self):
        """Regression guard: as a plain job Task Scheduler would kill it after 2 hours; as a service the watchdog would
        bring it back after "Esci"."""
        testo = xml_windows()
        self.assertIn("<ExecutionTimeLimit>PT0S</ExecutionTimeLimit>", testo)
        self.assertNotIn("<Repetition>", testo)
        self.assertNotIn("<RestartOnFailure>", testo)
        self.assertNotIn("<CalendarTrigger>", testo)

    def test_macos_binario_compilato_senza_caffeinate_ne_keepalive(self):
        p = ij.piano_launchd("tray", TRAY, CTX)
        plist = plistlib.loads(p["file"][0][1])
        binario = str(Path("/srv/u") / "Library" / "Application Support" / "second-brain" / "SecondBrainTray")
        self.assertEqual([str(Path(a)) for a in plist["ProgramArguments"]], [binario])  # no caffeinate: it would keep the Mac awake
        self.assertTrue(plist["RunAtLoad"])
        self.assertNotIn("KeepAlive", plist)  # "Esci" must stay closed until the next login
        self.assertNotIn("StartCalendarInterval", plist)
        swiftc = [c for c in p["avvia"] if c[0] == "swiftc"]
        self.assertEqual(len(swiftc), 1)
        self.assertEqual(Path(swiftc[0][-1]), Path("/srv/vault dir/scripts/tray/SecondBrainTray.swift"))
        self.assertEqual(str(Path(swiftc[0][swiftc[0].index("-o") + 1])), binario)
        self.assertLess(p["avvia"].index(swiftc[0]), [c[1] if c[0] == "?" else c[0] for c in p["avvia"]].index("launchctl"))  # build before load

    def test_gli_altri_job_non_cambiano(self):
        self.assertEqual(ij.preparazione(JOBS["morning"], CTX, "macos"), [])
        self.assertEqual(ij.comando(JOBS["morning"], CTX, "macos")[1:], ["-I", "%s/scripts/avvio.py" % CTX["vault"]])
        self.assertIn("<ExecutionTimeLimit>PT2H</ExecutionTimeLimit>", ij.piano_windows("m", JOBS["morning"], CTX)["file"][0][1].decode("utf-16"))


class ScriptTest(unittest.TestCase):
    def test_tray_ps1_solo_ascii(self):
        """PowerShell 5.1 reads a file without a BOM in the ANSI code page: an accent would be garbled."""
        TRAY_PS1.read_bytes().decode("ascii")

    def test_menu_dei_job_da_una_lista_fissa(self):
        testo = TRAY_PS1.read_text(encoding="ascii")
        self.assertIn("@('morning'),\n    @('feed', 'radar'),\n    @('chiusura'),\n    @('bozze'),\n    @('pulizia')", testo)
        swift = (RADICE / "scripts" / "tray" / "SecondBrainTray.swift").read_text(encoding="utf-8")
        self.assertIn('[["morning"], ["feed", "radar"], ["chiusura"], ["bozze"], ["pulizia"]]', swift)

    @SOLO_WINDOWS
    def test_tray_ps1_si_analizza_senza_errori(self):
        comando = ("$t = $null; $e = $null; "
                   "[void][System.Management.Automation.Language.Parser]::ParseFile($env:TRAY_PS1, [ref]$t, [ref]$e); "
                   "$e | ForEach-Object { $_.ToString() }; 'errori=' + $e.Count")
        r = subprocess.run([POWERSHELL, "-NoProfile", "-NonInteractive", "-Command", comando], capture_output=True, text=True,
                           env={**os.environ, "TRAY_PS1": str(TRAY_PS1)}, timeout=60)
        self.assertEqual(r.returncode, 0, r.stderr)
        self.assertIn("errori=0", r.stdout, r.stdout)

    @SOLO_WINDOWS
    def test_self_test_con_la_riga_di_comando_del_task(self):
        """Runs the exact cmd.exe line of the generated task (quoting and log redirect included), plus -SelfTest."""
        with tempfile.TemporaryDirectory() as d:
            ctx = {**CTX, "vault": RADICE, "log": Path(d)}
            args = argomenti_task(xml_windows(ctx))
            self.assertTrue(args.startswith("--headless cmd.exe /c "))
            riga = args.removeprefix("--headless ").replace(' >> "', ' -SelfTest >> "', 1)
            # A str is passed to CreateProcess verbatim on Windows: no re-quoting by Python.
            r = subprocess.run(riga, cwd=RADICE, timeout=120, creationflags=subprocess.CREATE_NO_WINDOW)
            uscita = (Path(d) / "second-brain-tray.log").read_text(encoding="utf-8", errors="replace")
        self.assertEqual(r.returncode, 0, uscita)
        self.assertRegex(uscita, r"health: GET http://127\.0\.0\.1:8765/api/moduli -> (OK|NON RISPONDE) \(")
        self.assertIn("Avvia / riavvia -> schtasks.exe /end /tn second-brain.dashboard ; schtasks.exe /run /tn second-brain.dashboard", uscita)
        self.assertIn("Ferma (riparte entro 10 min) -> schtasks.exe /end /tn second-brain.dashboard", uscita)
        self.assertIn("menu Avvia job:", uscita)
        for riga_job in re.findall(r"^  (?!Apri|Avvia|Ferma)(.+ -> .+)$", uscita, re.M):
            for comando in re.findall(r"schtasks\.exe \S+ /tn (\S+)", riga_job):
                self.assertRegex(comando, "^%s$" % JOB_AMMESSI)
        self.assertIn("menu Notifiche:", uscita)


if __name__ == "__main__":
    unittest.main()

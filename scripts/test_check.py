#!/usr/bin/env python3
"""Tests for scripts/check: order of the steps, stop at the first red step, missing tools."""
import contextlib
import importlib.machinery
import importlib.util
import io
import pathlib
import sys
import tempfile
import unittest

CHECK = pathlib.Path(__file__).resolve().parent / 'check'


def load_check():
    loader = importlib.machinery.SourceFileLoader('check_script', str(CHECK))
    spec = importlib.util.spec_from_loader('check_script', loader)
    module = importlib.util.module_from_spec(spec)
    loader.exec_module(module)
    return module


def py(code):
    return [sys.executable, '-c', code]


class Check(unittest.TestCase):
    def setUp(self):
        self.check = load_check()
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.dir = pathlib.Path(self.tmp.name)

    def run_steps(self, steps):
        out, err = io.StringIO(), io.StringIO()
        with contextlib.redirect_stdout(out), contextlib.redirect_stderr(err):
            rc = self.check.run(steps, cwd=self.dir)
        return rc, out.getvalue(), err.getvalue()

    def test_steps_in_the_documented_order(self):
        names = [name for name, _ in self.check.STEPS]
        self.assertEqual(names, ['vault rules', 'lint', 'script tests', 'template tests', 'secret scan'])
        tools = [cmd[0] for _, cmd in self.check.STEPS]
        self.assertEqual(tools[1], 'ruff')
        self.assertEqual(tools[4], 'gitleaks')

    def test_all_green_returns_zero(self):
        rc, out, _ = self.run_steps([('one', py('pass')), ('two', py('pass'))])
        self.assertEqual(rc, 0)
        self.assertIn('check: OK', out)

    def test_stops_at_first_red_and_names_it(self):
        marker = self.dir / 'third-ran'
        rc, _, err = self.run_steps([
            ('first', py('pass')),
            ('second', py('raise SystemExit(3)')),
            ('third', py('import pathlib; pathlib.Path("third-ran").write_text("x")')),
        ])
        self.assertEqual(rc, 3)
        self.assertIn('second', err)
        self.assertFalse(marker.exists(), 'a step after the red one must not run')

    def test_missing_tool_fails_and_points_to_doctor(self):
        rc, _, err = self.run_steps([('lint', ['no-such-tool-for-check-tests', 'check', '.'])])
        self.assertEqual(rc, 1)
        self.assertIn('no-such-tool-for-check-tests', err)
        self.assertIn('doctor.py', err)

    def test_missing_tool_stops_the_steps_after_it(self):
        marker = self.dir / 'after-ran'
        rc, _, _ = self.run_steps([
            ('lint', ['no-such-tool-for-check-tests']),
            ('after', py('import pathlib; pathlib.Path("after-ran").write_text("x")')),
        ])
        self.assertEqual(rc, 1)
        self.assertFalse(marker.exists())

    def test_steps_run_from_the_given_root(self):
        rc, _, _ = self.run_steps([('cwd', py('import pathlib; pathlib.Path("here").write_text("x")'))])
        self.assertEqual(rc, 0)
        self.assertTrue((self.dir / 'here').exists())


if __name__ == '__main__':
    unittest.main()

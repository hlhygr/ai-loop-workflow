"""Compatibility runner for the repository test suite."""
from pathlib import Path
import unittest

if __name__ == '__main__':
    tests = unittest.defaultTestLoader.discover(str(Path(__file__).resolve().parents[1] / 'tests'))
    raise SystemExit(not unittest.TextTestRunner(verbosity=1).run(tests).wasSuccessful())

#!/usr/bin/env python3
"""Compatibility entry for an installation directly inside its workspace.

New integrations use skills/planning/scripts/planning.py with an explicit workspace.
"""
import importlib.util
import sys
from pathlib import Path

SOURCE = Path(__file__).resolve().parents[1] / 'adapters/codex/adapter.py'
spec = importlib.util.spec_from_file_location('ai_loop_legacy_adapter', SOURCE)
adapter = importlib.util.module_from_spec(spec)
spec.loader.exec_module(adapter)

if __name__ == '__main__':
    raise SystemExit(adapter.legacy_main(sys.argv[1:], Path(__file__).resolve().parents[2]))

"""Translate host events and identities to the portable planning interface."""
from __future__ import annotations

import argparse
import importlib.util
import json
import os
import sys
from pathlib import Path

SOURCE = Path(__file__).resolve().parents[2] / 'skills/planning/scripts/planning.py'
spec = importlib.util.spec_from_file_location('ai_loop_planning', SOURCE)
planning = importlib.util.module_from_spec(spec)
spec.loader.exec_module(planning)
EVENTS = {'SessionStart': 'start', 'UserPromptSubmit': 'prompt', 'PreCompact': 'compact', 'Stop': 'stop'}


def hook(workspace: Path) -> int:
    try:
        payload = json.load(sys.stdin)
        if not isinstance(payload, dict) or os.environ.get('PLANNING_DISABLED') == '1':
            return 0
        root = workspace.expanduser().resolve()
        cwd = Path(payload.get('cwd') or os.getcwd()).resolve()
        if cwd != root and root not in cwd.parents:
            return 0
        event = payload.get('hook_event_name')
        if event not in EVENTS:
            return 0
        os.environ['AI_LOOP_WORKSPACE_ROOT'] = str(root)
        # Keep the previous thread-pointer selection order for existing sessions.
        identity = os.environ.get('AI_LOOP_SESSION_ID') or os.environ.get('CODEX_THREAD_ID')
        if not identity and isinstance(payload.get('session_id'), str):
            identity = payload['session_id']
        if identity:
            os.environ['AI_LOOP_SESSION_ID'] = identity
        session = payload.get('session_id') or identity
        result = planning.handle_event(EVENTS[event], session, legacy_bindings=True)
        if 'context' in result:
            print(json.dumps({'hookSpecificOutput': {'hookEventName': event,
                                                     'additionalContext': result['context']}}, ensure_ascii=False))
        elif 'notice' in result:
            print(json.dumps({'systemMessage': result['notice']}, ensure_ascii=False))
    except (OSError, ValueError, TypeError) as exc:
        print(json.dumps({'systemMessage': f'AI Loop planning 未加载：{exc}；请显式选择正确计划。'}, ensure_ascii=False))
    return 0


def legacy_main(argv: list[str], default_workspace: Path) -> int:
    workspace = Path(os.environ.get('AI_LOOP_WORKSPACE_ROOT') or default_workspace)
    if argv == ['hook']:
        return hook(workspace)
    return planning.main(argv, default_workspace=str(workspace), default_session=os.environ.get('CODEX_THREAD_ID'), legacy_bindings=True)


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--workspace', required=True, type=Path)
    args = parser.parse_args()
    return hook(args.workspace)


if __name__ == '__main__':
    raise SystemExit(main())

"""Isolated regression checks for Work planning recovery and report validation."""

import hashlib
import importlib.util
import io
import json
import os
import subprocess
import sys
import tempfile
import unittest
from contextlib import redirect_stdout
from pathlib import Path
from unittest.mock import patch


ROOT = Path(__file__).resolve().parents[1]
SCRIPT = ROOT / 'skills/planning/scripts/planning.py'
spec = importlib.util.spec_from_file_location('host_adapter', ROOT / 'adapters/codex/adapter.py')
adapter = importlib.util.module_from_spec(spec)
spec.loader.exec_module(adapter)
planning = adapter.planning
VALIDATOR = ROOT / 'skills/dispatch-ai-loop-workflow/scripts/validate-test-report.py'


class PlanningRecoveryTests(unittest.TestCase):
    def setUp(self):
        self.temporary = tempfile.TemporaryDirectory()
        self.addCleanup(self.temporary.cleanup)
        self.root = Path(self.temporary.name)
        self.workspace = self.root / 'workspace'
        self.workspace.mkdir()
        self.directory = self.root / 'task-a'
        self.directory.mkdir()
        (self.directory / 'task_plan.md').write_text(
            '# Task\n## Goal\n实现目标\n### Phase 1：历史\n- **Status:** complete\n'
            '### Phase 2：当前\n- **Status:** in_progress\n## Next Step\n执行定向验证\n'
        )
        (self.directory / 'findings.md').write_text('# 发现\n当前问题仍未关闭\n')
        (self.directory / 'progress.md').write_text('# 进度\n当前动作：验证\n')
        self.env = {'PLANNING_ROOT': str(self.root), 'PLAN_ID': 'task-a',
                    'CODEX_THREAD_ID': 'thread-a', 'AI_LOOP_SESSION_ID': 'thread-a',
                    'AI_LOOP_WORKSPACE_ROOT': str(self.workspace), 'PLANNING_DISABLED': '0'}

    def event(self, name, session='session-a', overrides=None, **extra):
        payload = {'hook_event_name': name, 'cwd': str(self.workspace), **extra}
        if session is not None:
            payload['session_id'] = session
        env = {**self.env, **(overrides or {})}
        if overrides and 'CODEX_THREAD_ID' in overrides and 'AI_LOOP_SESSION_ID' not in overrides:
            env['AI_LOOP_SESSION_ID'] = overrides['CODEX_THREAD_ID']
        output = io.StringIO()
        with patch.dict(os.environ, env), patch('sys.stdin', io.StringIO(json.dumps(payload))), redirect_stdout(output):
            self.assertEqual(adapter.hook(self.workspace), 0)
        return json.loads(output.getvalue()) if output.getvalue() else None

    def test_summary_limits_large_files_and_keeps_latest_progress(self):
        (self.directory / 'findings.md').write_text('历史发现' * 10000 + '\n当前未关闭问题')
        (self.directory / 'progress.md').write_text('历史记录' * 10000 + '\n当前动作：最后一步')
        result = self.event('SessionStart')['hookSpecificOutput']['additionalContext']
        self.assertLess(len(result), 4500)
        self.assertIn('执行定向验证', result)
        self.assertIn('最后一步', result)
        self.assertIn('当前未关闭问题', result)
        self.assertNotIn('--- progress.md ---', result)

    def test_unchanged_prompt_is_silent(self):
        self.event('SessionStart')
        self.assertIsNone(self.event('UserPromptSubmit'))

    def test_visible_changes_refresh_summary(self):
        self.event('SessionStart')
        plan = self.directory / 'task_plan.md'
        plan.write_text(plan.read_text().replace('执行定向验证', '核对真实接口'))
        self.assertIn('核对真实接口', self.event('UserPromptSubmit')['hookSpecificOutput']['additionalContext'])
        for filename in ('findings.md', 'progress.md'):
            with self.subTest(filename=filename):
                path = self.directory / filename
                path.write_text(path.read_text() + '\n新证据\n')
                self.assertIn('hookSpecificOutput', self.event('UserPromptSubmit'))
                self.assertIsNone(self.event('UserPromptSubmit'))

    def test_current_state_takes_priority_over_history(self):
        plan = self.directory / 'task_plan.md'
        plan.write_text(plan.read_text() + '\n## 当前状态\n当前结论：保存失败，等待接口核对。\n')
        (self.directory / 'findings.md').write_text('旧结论：全部完成。' * 1000)
        (self.directory / 'progress.md').write_text('旧下一步：直接发布。')
        result = self.event('SessionStart')['hookSpecificOutput']['additionalContext']
        self.assertIn('保存失败', result)
        self.assertIn('执行定向验证', result)
        self.assertNotIn('全部完成', result)
        self.assertNotIn('直接发布', result)
        for filename in ('findings.md', 'progress.md'):
            path = self.directory / filename
            path.write_text(path.read_text() + '\n补充历史证据\n')
            self.assertIsNone(self.event('UserPromptSubmit'))
        plan.write_text(plan.read_text().replace('保存失败，等待接口核对。', '接口已核对，保存恢复。'))
        refreshed = self.event('UserPromptSubmit')['hookSpecificOutput']['additionalContext']
        self.assertIn('保存恢复', refreshed)
        self.assertIsNone(self.event('UserPromptSubmit'))

    def test_legacy_tail_changes_are_visible_but_hidden_history_is_silent(self):
        findings = self.directory / 'findings.md'
        findings.write_text('历史开头 A\n' + '旧记录' * 1000 + '\n最新结论：保存失败。')
        first = self.event('SessionStart')['hookSpecificOutput']['additionalContext']
        self.assertIn('旧计划未提供当前状态区', first)
        self.assertIn('保存失败', first)
        findings.write_text(findings.read_text().replace('历史开头 A', '历史开头 B'))
        self.assertIsNone(self.event('UserPromptSubmit'))
        findings.write_text(findings.read_text().replace('保存失败', '保存恢复'))
        second = self.event('UserPromptSubmit')['hookSpecificOutput']['additionalContext']
        self.assertIn('保存恢复', second)
        self.assertNotIn('保存失败', second)

    def test_large_current_state_reports_truncation(self):
        plan = self.directory / 'task_plan.md'
        plan.write_text(plan.read_text() + '\n## 当前状态\n' + '仍有阻塞。' * 2000)
        result = self.event('SessionStart')['hookSpecificOutput']['additionalContext']
        self.assertIn('仍有阻塞', result)
        self.assertIn('内容已截断', result)
        self.assertLess(len(result), 4500)

    def test_initialize_uses_work_templates_and_explicit_selection(self):
        with patch.dict(os.environ, self.env):
            directory = planning.initialize('new-work')
            self.assertEqual(set(item.name for item in directory.iterdir()), set(planning.FILES))
            content = planning.compact_context(directory, *planning.snapshot(directory))
            self.assertIn('当前状态', content)
            self.assertIn('明确本任务的实际阶段', content)
            # An explicit task selection always wins over a new thread binding.
            self.assertEqual(planning.resolve(), self.directory.resolve())
        with patch.dict(os.environ, {**self.env, 'PLAN_ID': ''}):
            self.assertEqual(planning.resolve(), directory)

    def test_sessions_and_plans_do_not_suppress_each_other(self):
        self.event('SessionStart')
        self.assertIsNotNone(self.event('UserPromptSubmit', session='session-b'))
        other = self.root / 'task-b'
        other.mkdir()
        for filename in planning.FILES:
            (other / filename).write_text((self.directory / filename).read_text())
        result = self.event('UserPromptSubmit', overrides={'PLAN_ID': 'task-b'})
        self.assertIn(str(other), result['hookSpecificOutput']['additionalContext'])

    def test_compaction_invalidates_cache(self):
        self.event('SessionStart')
        self.assertIsNone(self.event('UserPromptSubmit'))
        reminder = self.event('PreCompact')['systemMessage']
        self.assertIn('task_plan.md', reminder)
        self.assertIn('唯一 Next Step', reminder)
        self.assertIsNotNone(self.event('UserPromptSubmit'))
        self.assertIsNone(self.event('UserPromptSubmit'))

    def test_session_start_always_restores(self):
        self.event('SessionStart')
        self.assertIsNotNone(self.event('SessionStart'))

    def test_disabled_external_and_unselected_are_silent(self):
        self.assertIsNone(self.event('SessionStart', overrides={'PLANNING_DISABLED': '1'}))
        self.assertIsNone(self.event('SessionStart', cwd=str(self.root)))
        self.assertIsNone(self.event('SessionStart', overrides={'PLAN_ID': '', 'CODEX_THREAD_ID': ''}, session=None))
        self.assertFalse((self.root / '.active').exists())

    def test_attestation_is_checked_even_when_cached(self):
        plan = self.directory / 'task_plan.md'
        attestation = self.directory / '.attestation'
        attestation.write_text(hashlib.sha256(plan.read_bytes()).hexdigest())
        self.event('SessionStart')
        plan.write_text(plan.read_text() + '\n未确认改动')
        result = self.event('UserPromptSubmit')
        self.assertIn('PLAN TAMPERED', result['systemMessage'])
        self.assertNotIn('hookSpecificOutput', result)
        with self.assertRaises(ValueError):
            planning.context(self.directory)

    def test_completed_plan_can_continue_and_full_context_remains_available(self):
        plan = self.directory / 'task_plan.md'
        plan.write_text(plan.read_text().replace('in_progress', 'complete'))
        self.assertIsNotNone(self.event('SessionStart'))
        plan.write_text(plan.read_text() + '\n### Phase 3：追加\n- **Status:** pending\n')
        self.assertIn('追加', self.event('UserPromptSubmit')['hookSpecificOutput']['additionalContext'])
        self.assertIn('--- progress.md ---', planning.context(self.directory))

    def test_payload_session_can_resolve_thread_pointer(self):
        active = self.root / '.active'
        active.mkdir()
        (active / 'thread-native-session').write_text('task-a')
        result = self.event('SessionStart', session='native-session', overrides={'PLAN_ID': '', 'CODEX_THREAD_ID': ''})
        self.assertIn(str(self.directory), result['hookSpecificOutput']['additionalContext'])

    def test_no_session_does_not_share_deduplication_cache(self):
        for _ in range(2):
            self.assertIsNotNone(self.event('UserPromptSubmit', session=None, overrides={'CODEX_THREAD_ID': ''}))
        self.assertFalse((self.root / '.active').exists())

    def test_corrupt_cache_recovers_and_symlink_cache_is_not_overwritten(self):
        self.event('SessionStart')
        cache = next((self.root / '.active').glob('context-*.json'))
        cache.write_text('invalid json')
        self.assertIsNotNone(self.event('UserPromptSubmit'))
        cache.unlink()
        target = self.root / 'unrelated'
        target.write_text('keep')
        cache.symlink_to(target)
        self.assertIn('软链接', self.event('UserPromptSubmit')['systemMessage'])
        self.assertEqual(target.read_text(), 'keep')

    def test_summary_default_omits_old_completed_phases_and_all_preserves_them(self):
        plan = self.directory / 'task_plan.md'
        plan.write_text(plan.read_text().replace('### Phase 2', '### Phase 1b：近期\n- **Status:** complete\n### Phase 2'))
        env = {**os.environ, **self.env}
        result = subprocess.run([sys.executable, str(SCRIPT), 'summary'], env=env, capture_output=True, text=True, check=True)
        self.assertNotIn('Phase 1：历史', result.stdout)
        self.assertIn('Phase 1b：近期', result.stdout)
        self.assertIn('Phase 2：当前', result.stdout)
        full = subprocess.run([sys.executable, str(SCRIPT), 'summary', '--all'], env=env, capture_output=True, text=True, check=True)
        self.assertIn('Phase 1：历史', full.stdout)


class ReportCommandTests(unittest.TestCase):
    def setUp(self):
        self.temporary = tempfile.TemporaryDirectory()
        self.addCleanup(self.temporary.cleanup)
        self.root = Path(self.temporary.name)
        self.report = self.root / 'test-execution-report.html'
        sections = ''.join(f'<section data-report-section="{name}">{name}</section>' for name in (
            'scope', 'environment', 'findings', 'data-state', 'authorization'
        ))
        counts = ''.join(f'<strong data-result-count="{name}">{value}</strong>' for name, value in (
            ('PLANNED', 1), ('PASS', 1), ('FAIL', 0), ('BLOCKED', 0), ('NOT_RUN', 0)
        ))
        fields = ''.join(f'<td data-fields="{name}">{name}</td>' for name in (
            'expected', 'actual', 'evidence', 'state', 'cleanup'
        ))
        self.report.write_text('<!doctype html><html><head><meta charset="UTF-8">'
                              '<meta name="ai-loop-test-report" content="v1"></head><body>'
                              + sections + counts + '<section data-report-section="cases"><table>'
                              '<tr data-case-id="one" data-status="PASS">' + fields +
                              '</tr></table></section></body></html>')

    def run_validator(self, *args):
        return subprocess.run([sys.executable, str(VALIDATOR), *args,
                               '--planned-cases', '1', '--pass-count', '1', '--fail-count', '0',
                               '--blocked-count', '0', '--not-run-count', '0'],
                              cwd=self.root, capture_output=True, text=True)

    def test_standalone_absolute_and_relative_reports(self):
        self.assertEqual(self.run_validator('--report', str(self.report)).returncode, 0)
        self.assertEqual(self.run_validator('--report', self.report.name).returncode, 0)
        self.assertEqual(sorted(p.name for p in self.root.iterdir()), [self.report.name])

    def test_legacy_plan_path_and_outside_plan_rejection(self):
        self.assertEqual(self.run_validator('--plan-dir', str(self.root)).returncode, 0)
        plan = self.root / 'plan'
        plan.mkdir()
        self.assertNotEqual(self.run_validator('--plan-dir', str(plan), '--report', str(self.report)).returncode, 0)

    def test_standalone_requires_explicit_report(self):
        self.assertEqual(self.run_validator().returncode, 2)

    def test_standalone_still_rejects_wrong_counts_missing_evidence_and_external_resources(self):
        original = self.report.read_text()
        for broken in [original.replace('data-status="PASS"', 'data-status="FAIL"'),
                       original.replace('data-fields="evidence"', 'data-fields="other"'),
                       original.replace('</body>', '<script src="https://example.com/a.js"></script></body>'),
                       original.replace('data-result-count="PASS"', 'hidden data-result-count="PASS"')]:
            with self.subTest(broken=broken[-80:]):
                self.report.write_text(broken)
                self.assertNotEqual(self.run_validator('--report', str(self.report)).returncode, 0)


if __name__ == '__main__':
    unittest.main()

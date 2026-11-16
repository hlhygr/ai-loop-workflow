"""Exercise a relocated checkout without the author's home or installed skills."""
import json
import os
import shutil
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

SOURCE = Path(__file__).resolve().parents[1]


class PortableCheckoutTests(unittest.TestCase):
    def setUp(self):
        self.temporary = tempfile.TemporaryDirectory()
        self.addCleanup(self.temporary.cleanup)
        self.root = Path(self.temporary.name).resolve()
        self.checkout = self.root / 'relocated source'
        shutil.copytree(SOURCE, self.checkout, ignore=shutil.ignore_patterns('__pycache__', '*.pyc'))
        self.workspace = self.root / 'project'
        self.workspace.mkdir()
        self.other = self.root / 'unrelated cwd'
        self.other.mkdir()
        self.home = self.root / 'empty home'
        self.home.mkdir()
        self.env = {k: v for k, v in os.environ.items() if not k.startswith(('AI_LOOP_', 'PLANNING_', 'PLAN_ID', 'CODEX_THREAD_ID'))}
        self.env.update(HOME=str(self.home), PYTHONDONTWRITEBYTECODE='1')
        self.script = self.checkout / 'skills/planning/scripts/planning.py'

    def call(self, *args, cwd=None, env=None, script=None, input=None):
        return subprocess.run([sys.executable, str(script or self.script), *map(str, args)],
                              cwd=cwd or self.other, env={**self.env, **(env or {})},
                              input=input, capture_output=True, text=True)

    def initialize(self, session='test-session'):
        result = self.call('--workspace', self.workspace, '--session-id', session, 'init', 'portable')
        self.assertEqual(result.returncode, 0, result.stderr)
        plan_id = next(line.split('=', 1)[1] for line in result.stdout.splitlines() if line.startswith('PLAN_ID='))
        return plan_id, self.workspace / '.planning' / plan_id

    def test_relocation_root_selection_and_session_isolation(self):
        plan_id, directory = self.initialize()
        result = self.call('--workspace', self.workspace, '--session-id', 'test-session', 'resolve')
        self.assertEqual(result.stdout.strip(), str(directory))
        self.assertEqual(self.call('--workspace', self.workspace, '--session-id', 'other-session', 'resolve').stdout, '')
        self.assertEqual(self.call('--workspace', self.other, '--session-id', 'test-session', 'resolve').stdout, '')
        invalid = self.call('--workspace', self.workspace, '--session-id', 'test-session', '--plan-id', 'missing', 'resolve')
        self.assertNotEqual(invalid.returncode, 0)
        self.assertEqual(invalid.stdout, '')
        result = self.call('--plan-id', plan_id, 'brief', cwd=self.workspace)
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertIn(str(directory), result.stdout)
        self.assertEqual(list(self.home.iterdir()), [])
        self.assertFalse((self.checkout / '.planning').exists())
        self.assertFalse((self.other / '.planning').exists())

    def test_custom_root_check_and_attestation_need_no_external_skill(self):
        storage = self.root / 'shared plans'
        result = self.call('--workspace', self.workspace, '--planning-root', storage, 'init', 'standalone')
        self.assertEqual(result.returncode, 0, result.stderr)
        plan_id = next(line.split('=', 1)[1] for line in result.stdout.splitlines() if line.startswith('PLAN_ID='))
        opts = ('--planning-root', storage, '--plan-id', plan_id)
        directory = storage / plan_id
        self.assertEqual(self.call(*opts, 'check').returncode, 1)
        path = directory / 'task_plan.md'
        path.write_text(path.read_text().replace('**Status:** pending', '**Status:** complete'))
        self.assertEqual(self.call(*opts, 'check').returncode, 0)
        self.assertEqual(self.call(*opts, 'attest').returncode, 0)
        self.assertEqual(self.call(*opts, 'brief').returncode, 0)
        path.write_text(path.read_text() + '\nChanged after attestation.\n')
        rejected = self.call(*opts, 'brief')
        self.assertNotEqual(rejected.returncode, 0)
        self.assertEqual(rejected.stdout, '')
        self.assertIn('PLAN TAMPERED', rejected.stderr)
        self.assertEqual(self.call(*opts, 'attest').returncode, 0)
        self.assertEqual(self.call(*opts, 'brief').returncode, 0)
        path.write_text('# Empty plan\n')
        self.assertEqual(self.call(*opts, 'check').returncode, 1)
        self.assertFalse((self.workspace / '.planning').exists())
        self.assertEqual(list(self.home.iterdir()), [])

    def test_normalized_lifecycle_without_host_variables(self):
        plan_id, directory = self.initialize()
        opts = ('--workspace', self.workspace, '--plan-id', plan_id, '--session-id', 'session')
        start = json.loads(self.call(*opts, 'event', 'start').stdout)
        self.assertEqual(set(start), {'context'})
        self.assertIn(str(directory), start['context'])
        self.assertEqual(json.loads(self.call(*opts, 'event', 'prompt').stdout), {})
        self.assertEqual(set(json.loads(self.call(*opts, 'event', 'compact').stdout)), {'notice'})
        self.assertIn('context', json.loads(self.call(*opts, 'event', 'prompt').stdout))
        self.assertEqual(self.call('--workspace', self.workspace, 'resolve', env={'CODEX_THREAD_ID': 'test-session'}).stdout, '')

    def test_legacy_entry_uses_same_source_and_preserves_thread_bindings(self):
        legacy = self.checkout / 'scripts/planning.py'
        env = {'CODEX_THREAD_ID': 'legacy-session'}
        result = self.call('init', 'legacy', script=legacy, env=env)
        self.assertEqual(result.returncode, 0, result.stderr)
        plan_id = next(line.split('=', 1)[1] for line in result.stdout.splitlines() if line.startswith('PLAN_ID='))
        directory = self.root / '.planning' / plan_id
        self.assertTrue(directory.is_dir())
        result = self.call('resolve', script=legacy, env=env)
        self.assertEqual(result.stdout.strip(), str(directory))
        payload = {'hook_event_name': 'SessionStart', 'cwd': str(self.other), 'session_id': 'host-session'}
        result = self.call('hook', script=legacy, env=env, input=json.dumps(payload))
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertIn(str(directory), json.loads(result.stdout)['hookSpecificOutput']['additionalContext'])
        payload['cwd'] = str(self.root.parent)
        self.assertEqual(self.call('hook', script=legacy, env=env, input=json.dumps(payload)).stdout, '')

    def test_opaque_session_ids_do_not_collide(self):
        identities = ['team/a', 'team:a', 'team-a', 'x' * 120 + 'a', 'x' * 120 + 'b', '会话/甲']
        expected = {identity: self.initialize(identity)[1] for identity in identities}
        self.assertEqual(len(set(expected.values())), len(identities))
        for identity, directory in expected.items():
            result = self.call('--workspace', self.workspace, '--session-id', identity, 'resolve')
            self.assertEqual(result.returncode, 0, result.stderr)
            self.assertEqual(result.stdout.strip(), str(directory))
        # Core never follows an old lossy key; the adapter only reads reversible legacy IDs.
        plan_id, directory = self.initialize('new-owner')
        old = self.workspace / '.planning/.active/thread-legacy-team'
        old.write_text(plan_id)
        self.assertEqual(self.call('--workspace', self.workspace, '--session-id', 'legacy-team', 'resolve').stdout, '')
        legacy_script = self.checkout / 'scripts/planning.py'
        opts = ('--workspace', self.workspace)
        self.assertEqual(self.call(*opts, 'resolve', script=legacy_script,
                                   env={'CODEX_THREAD_ID': 'legacy/team'}).stdout, '')
        self.assertEqual(self.call(*opts, 'resolve', script=legacy_script,
                                   env={'CODEX_THREAD_ID': 'legacy-team'}).stdout.strip(), str(directory))

    def test_learning_candidate_requires_explicit_plan(self):
        plan_id, directory = self.initialize()
        script = self.checkout / 'skills/dispatch-ai-loop-workflow/scripts/init-learning-candidate.py'
        missing = self.call('--name', 'review', script=script, env={'CODEX_THREAD_ID': 'test-session'})
        self.assertNotEqual(missing.returncode, 0)
        self.assertFalse((directory / 'learning_candidate-review.md').exists())
        result = self.call('--plan-dir', directory, '--name', 'review', script=script)
        self.assertEqual(result.returncode, 0, result.stderr)
        target = directory / 'learning_candidate-review.md'
        original = target.read_bytes()
        self.assertIn(str(directory / 'progress.md'), original.decode())
        duplicate = self.call('--plan-dir', directory, '--name', 'review', script=script)
        self.assertNotEqual(duplicate.returncode, 0)
        self.assertEqual(target.read_bytes(), original)

    def test_symlink_plan_and_attestation_are_rejected(self):
        if not hasattr(os, 'symlink'):
            self.skipTest('symlinks unavailable')
        plan_id, directory = self.initialize()
        opts = ('--workspace', self.workspace, '--plan-id', plan_id)
        target = self.root / 'unrelated.txt'
        target.write_text('do not overwrite')
        (directory / '.attestation').symlink_to(target)
        self.assertNotEqual(self.call(*opts, 'attest').returncode, 0)
        self.assertEqual(target.read_text(), 'do not overwrite')
        self.assertNotEqual(self.call(*opts, 'brief').returncode, 0)


if __name__ == '__main__':
    unittest.main()

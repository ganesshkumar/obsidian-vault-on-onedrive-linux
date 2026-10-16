#!/usr/bin/python3 -B
import pathlib
import unittest
from support import load_module

ROOT = pathlib.Path(__file__).parent

class BindTests(unittest.TestCase):
    def test_wrong_existing_bind_is_rejected(self):
        ns = load_module('bin/onedrive-offline-bind').__dict__
        parent = {'id': 10, 'parent': 1, 'root': '/', 'target': ns['PARENT'], 'type': 'fuse.rclone', 'source': 'onedrive:'}
        child = {'id': 11, 'parent': 10, 'root': '/local', 'target': ns['TARGET'], 'type': 'btrfs', 'source': '/dev/local'}
        with self.assertRaisesRegex(RuntimeError, 'identity'):
            ns['ensure'](True, lambda: [parent, child], lambda p: (1, 2) if p == ns['SOURCE'] else (1, 3), lambda: self.fail('must not mount'))

class MoreBindTests(unittest.TestCase):
    def setUp(self):
        self.ns = load_module('bin/onedrive-offline-bind').__dict__
        self.parent = dict(id=10, parent=1, root='/', target=self.ns['PARENT'], type='fuse.rclone', source='onedrive:')
        self.child = dict(id=11, parent=10, root='/local', target=self.ns['TARGET'], type='btrfs', source='/dev/local')

    def test_correct_existing_bind_never_mounts(self):
        self.ns['ensure'](False, lambda: [self.parent, self.child], lambda p: (48, 123), lambda: self.fail('must not mount'))

    def test_wrong_parent_rejected_before_path_probe(self):
        self.parent['source'] = 'other:'
        with self.assertRaisesRegex(RuntimeError, 'parent filesystem'):
            self.ns['ensure'](False, lambda: [self.parent], lambda p: self.fail('must not probe'), lambda: self.fail('must not mount'))

    def test_stacked_child_rejected(self):
        with self.assertRaisesRegex(RuntimeError, 'stacked'):
            self.ns['topology']([self.parent, self.child, dict(self.child, id=12)])

    def test_nested_mount_rejected(self):
        with self.assertRaisesRegex(RuntimeError, 'nested'):
            self.ns['topology']([self.parent, self.child, dict(self.child, target=self.ns['TARGET']+'/nested')])

    def test_check_missing_bind_never_mounts(self):
        with self.assertRaisesRegex(RuntimeError, 'missing'):
            self.ns['ensure'](True, lambda: [self.parent], lambda p: (48, 123), lambda: self.fail('must not mount'))

    def test_missing_bind_created_and_verified(self):
        entries = [self.parent]
        created = []
        def create():
            created.append(True)
            entries.append(self.child)
        self.ns['ensure'](False, lambda: entries, lambda p: (48, 123), create)
        self.assertEqual(created, [True])

    def test_failed_post_mount_verification_is_error(self):
        entries = [self.parent]
        def create():
            entries.append(self.child)
        def probe(path):
            return (48, 123) if path == self.ns['SOURCE'] else (48, 999)
        with self.assertRaisesRegex(RuntimeError, 'Post-mount'):
            self.ns['ensure'](False, lambda: entries, probe, create)

    def test_probe_timeout_propagates_without_mounting(self):
        import subprocess
        def probe(path):
            raise subprocess.TimeoutExpired('fixture', 4)
        with self.assertRaises(subprocess.TimeoutExpired):
            self.ns['ensure'](False, lambda: [self.parent, self.child], probe, lambda: self.fail('must not mount'))

    def test_real_probe_uses_four_second_deadline(self):
        from unittest.mock import patch
        import subprocess
        with patch.object(self.ns['subprocess'], 'run', return_value=subprocess.CompletedProcess([], 0, '48 123\n')) as run:
            self.assertEqual(self.ns['identity']('/fixture'), (48, 123))
        self.assertEqual(run.call_args.kwargs['timeout'], 4)

if __name__ == '__main__':
    unittest.main()

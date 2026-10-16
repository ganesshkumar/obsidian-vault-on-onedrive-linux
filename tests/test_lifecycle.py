#!/usr/bin/python3 -B
"""No production services, mounts, credentials or data are changed; temporary fixtures are allowed."""
from pathlib import Path
import types
import unittest
from support import load_module, source, VALUES

ROOT = Path(__file__).parent

class RoutingTests(unittest.TestCase):
    def host(self):
        ns = load_module('bin/restart-onedrive').__dict__
        host = ns['Host'](None)
        self.calls = []
        def command(argv, **kwargs):
            self.calls.append(argv)
            return types.SimpleNamespace(stdout='', stderr='', returncode=0)
        host.command = command
        return host

    def test_cloud_commands_use_system_manager(self):
        h = self.host()
        h.ctl('start', 'rclone-onedrive.service')
        self.assertEqual(self.calls[0][:4], ['/usr/bin/sudo', '-n', '/usr/bin/systemctl', 'start'])

    def test_bisync_stays_user_managed(self):
        h = self.host()
        h.ctl('start', 'rclone-onedrive-offline.service')
        self.assertEqual(self.calls[0][:3], ['/usr/bin/systemctl', '--user', 'start'])

    def test_bind_stays_system_managed(self):
        h = self.host()
        h.ctl('start', 'onedrive-offline-bind.service', user=False)
        self.assertEqual(self.calls[0][:4], ['/usr/bin/sudo', '-n', '/usr/bin/systemctl', 'start'])

class WatchdogTests(unittest.TestCase):
    def load(self):
        ns = load_module('bin/onedrive-offline-bind').__dict__
        return ns

    def test_inactive_cloud_does_not_trigger_bind_repair(self):
        ns = self.load()
        calls = []
        ns['repair'](lambda: False, lambda: calls.append('repair'))
        self.assertEqual(calls, [])

    def test_active_cloud_allows_repair(self):
        ns = self.load()
        calls = []
        ns['repair'](lambda: True, lambda: calls.append('repair'))
        self.assertEqual(calls, ['repair'])

    def test_bind_requests_system_mount_not_direct_mount(self):
        from unittest.mock import patch
        import subprocess
        ns = self.load()
        with patch.object(ns['os'], 'geteuid', return_value=0), patch.object(ns['subprocess'], 'run', return_value=subprocess.CompletedProcess([], 0)) as run:
            ns['bind']()
        self.assertEqual(run.call_args.args[0], ['/usr/bin/systemctl', 'start', VALUES['BIND_UNIT']])
        self.assertEqual(run.call_args.kwargs['timeout'], 25)

    def test_child_cannot_pull_cloud_start(self):
        text = source('system/' + VALUES['BIND_UNIT'])
        self.assertIn('Requisite=rclone-onedrive.service', text)
        self.assertIn('PartOf=rclone-onedrive.service', text)
        self.assertIn('After=rclone-onedrive.service', text)
        self.assertNotIn('BindsTo=', text)
        self.assertNotIn('Requires=rclone-onedrive.service', text)

if __name__ == '__main__':
    unittest.main()

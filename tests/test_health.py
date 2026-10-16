#!/usr/bin/python3 -B
import pathlib
import unittest
from support import load_module

ROOT = pathlib.Path(__file__).parent

class AlertTests(unittest.TestCase):
    def test_alert_requires_three_consecutive_observations(self):
        ns = load_module('bin/onedrive-health-check').__dict__
        state = {}
        for now in (0, 120):
            state, event = ns['advance'](state, {'cloud': 'Cloud service is not active'}, now, 'boot')
            self.assertIsNone(event)
        state, event = ns['advance'](state, {'cloud': 'Cloud service is not active'}, 240, 'boot')
        self.assertEqual(event[0], 'warning')

class MonitorTests(unittest.TestCase):
    def setUp(self):
        self.ns = load_module('bin/onedrive-health-check').__dict__

    def fresh(self, now=0):
        return self.ns['fresh']('boot', now)

    def warned(self):
        state = self.fresh()
        issues = {'cloud': 'down'}
        for now in (0, 120, 240):
            state, event = self.ns['advance'](state, issues, now, 'boot')
        return self.ns['acknowledge'](state, event, 240)

    def test_no_repeat_before_hour(self):
        state, event = self.ns['advance'](self.warned(), {'cloud': 'down'}, 360, 'boot')
        self.assertIsNone(event)

    def test_hourly_reminder(self):
        state, event = self.ns['advance'](self.warned(), {'cloud': 'down'}, 3840, 'boot')
        self.assertEqual(event[0], 'warning')

    def test_recovery_notified_once(self):
        state, event = self.ns['advance'](self.warned(), {}, 360, 'boot')
        self.assertEqual(event[0], 'recovery')
        state = self.ns['acknowledge'](state, event, 360)
        state, event = self.ns['advance'](state, {}, 480, 'boot')
        self.assertIsNone(event)

    def test_transient_failure_does_not_notify(self):
        state, event = self.ns['advance'](self.fresh(), {'cloud': 'down'}, 0, 'boot')
        state, event = self.ns['advance'](state, {}, 120, 'boot')
        self.assertIsNone(event)
        self.assertEqual(state['counts'], {})

    def test_changing_failure_does_not_inherit_confirmation_count(self):
        state, event = self.ns['advance'](self.fresh(), {'cloud': 'down'}, 0, 'boot')
        state, event = self.ns['advance'](state, {'cloud': 'down'}, 120, 'boot')
        state, event = self.ns['advance'](state, {'bind': 'wrong'}, 240, 'boot')
        self.assertIsNone(event)

    def test_reboot_resets_previous_alert(self):
        state, event = self.ns['advance'](self.warned(), {'cloud': 'down'}, 10, 'newboot')
        self.assertIsNone(event)
        self.assertEqual(state['boot_id'], 'newboot')
        self.assertEqual(state['counts']['cloud'], 1)

    def test_failed_notification_is_not_acknowledged(self):
        state = self.warned()
        state['alerted'] = []
        state, event = self.ns['advance'](state, {'cloud': 'down'}, 360, 'boot')
        self.assertEqual(event[0], 'warning')
        state, next_event = self.ns['advance'](state, {'cloud': 'down'}, 480, 'boot')
        self.assertEqual(next_event[0], 'warning')

    def snapshot(self, **changes):
        value = dict(cloud='active', bind_timer='active', sync_timer='active', bind_ok=True,
                     sync=dict(ActiveState='inactive', Result='success', ExecMainStatus='0',
                               ExecMainStartTimestampMonotonic='100000000', ExecMainExitTimestampMonotonic='120000000'))
        value.update(changes)
        return value

    def test_completed_oneshot_inactive_is_healthy(self):
        issues, success = self.ns['assess'](self.snapshot(), None, 0, 150)
        self.assertEqual(issues, {})
        self.assertEqual(success, 120)

    def test_failed_sync_is_reported_even_with_active_timer(self):
        snap = self.snapshot()
        snap['sync'].update(ActiveState='failed', Result='exit-code', ExecMainStatus='1')
        issues, success = self.ns['assess'](snap, 120, 0, 200)
        self.assertIn('sync_failed', issues)
        self.assertEqual(success, 120)

    def test_running_sync_is_not_a_failure(self):
        snap = self.snapshot()
        snap['sync'].update(ActiveState='activating', ExecMainExitTimestampMonotonic='0')
        issues, success = self.ns['assess'](snap, 120, 0, 200)
        self.assertEqual(issues, {})

    def test_stale_success_is_reported(self):
        snap = self.snapshot()
        snap['sync'].update(ActiveState='activating', ExecMainExitTimestampMonotonic='0')
        issues, success = self.ns['assess'](snap, 120, 0, 1920)
        self.assertIn('sync_stale', issues)

    def test_old_completed_snapshot_does_not_reset_success_age(self):
        issues, success = self.ns['assess'](self.snapshot(), 120, 0, 1920)
        self.assertEqual(success, 120)
        self.assertIn('sync_stale', issues)

    def test_stopped_cloud_does_not_add_redundant_bind_failure(self):
        issues, success = self.ns['assess'](self.snapshot(cloud='inactive', bind_ok=False), None, 0, 150)
        self.assertIn('cloud', issues)
        self.assertNotIn('bind', issues)

    def test_wrong_bind_is_reported(self):
        issues, success = self.ns['assess'](self.snapshot(bind_ok=False), None, 0, 150)
        self.assertIn('bind', issues)

    def test_disabled_timers_are_reported(self):
        issues, success = self.ns['assess'](self.snapshot(bind_timer='inactive', sync_timer='inactive'), None, 0, 150)
        self.assertIn('bind_timer', issues)
        self.assertIn('sync_timer', issues)

    def test_check_never_writes_or_notifies(self):
        from unittest.mock import Mock
        self.ns['load_state'] = lambda boot, now: self.ns['fresh'](boot, now)
        self.ns['collect'] = lambda: self.snapshot()
        self.ns['save_state'] = Mock(side_effect=AssertionError('must not write'))
        self.ns['notify'] = Mock(side_effect=AssertionError('must not notify'))
        import contextlib
        import io
        with contextlib.redirect_stdout(io.StringIO()):
            self.ns['inspect_once'](True)
        self.ns['save_state'].assert_not_called()
        self.ns['notify'].assert_not_called()

    def test_bind_probe_is_bounded_and_read_only(self):
        from unittest.mock import patch
        import subprocess
        self.ns['units'] = lambda names, user=False: {
            name: dict(ActiveState='active', Id=name) for name in names}
        with patch.object(self.ns['subprocess'], 'run', return_value=subprocess.CompletedProcess([], 0, '', '')) as run:
            snap = self.ns['collect']()
        self.assertEqual(run.call_args.args[0], ['/usr/local/bin/onedrive-offline-bind', '--check'])
        self.assertEqual(run.call_args.kwargs['timeout'], 12)

if __name__ == '__main__':
    unittest.main()

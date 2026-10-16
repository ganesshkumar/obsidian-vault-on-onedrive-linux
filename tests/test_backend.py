import subprocess
import unittest
from pathlib import Path
from types import SimpleNamespace
from support import load_module
backend = load_module('bin/restart-onedrive')


class Fake(backend.Host):
    def __init__(self):
        home = Path('/home/test')
        super().__init__(SimpleNamespace(home=home, mount=home/'OneDrive', target=home/'OneDrive/Obsidian', offline=home/'offline', state=home/'state', session='pair', lock=home/'pair.lck', backups=home/'backup'))
        self.commands = []
        self.clock = 0
        self.states = []
        self.failure = None

    def command(self, argv, timeout=30, capture=True, check=True):
        self.commands.append(argv)
        if self.failure and self.failure(argv):
            raise RuntimeError('fixture command failed')
        return subprocess.CompletedProcess(argv, 0, '', '')

    def properties(self, unit, user=True):
        if self.states:
            return self.states.pop(0)
        return {}

    def now(self):
        return self.clock

    def sleep(self, seconds):
        self.clock += seconds


def state(start, end=0, active='inactive', result='success', status='0'):
    return dict(ExecMainStartTimestampMonotonic=str(start), ExecMainExitTimestampMonotonic=str(end), ActiveState=active, SubState='dead' if active == 'inactive' else 'start', Result=result, ExecMainStatus=status)


class SyncTests(unittest.TestCase):
    def test_fresh_success_is_proven(self):
        h = Fake()
        h.states = [state(10, 11), state(20, active='activating'), state(20, 21)]
        h.run_sync()
        self.assertEqual(h.last_sync['ExecMainStartTimestampMonotonic'], '20')
        self.assertTrue(any('--no-block' in c and 'start' in c for c in h.commands))


class SafetyTests(unittest.TestCase):
    def test_stale_success_times_out(self):
        h = Fake(); h.sync_timeout = 2
        h.states = [state(10, 11)] * 4
        with self.assertRaisesRegex(RuntimeError, 'NEW'):
            h.run_sync()
        self.assertIsNone(h.last_sync)

    def test_failed_new_run_rejected(self):
        h = Fake(); h.states = [state(10, 11), state(20, 21, result='exit-code', status='1')]
        with self.assertRaises(RuntimeError): h.run_sync()
        self.assertIsNone(h.last_sync)

    def test_stop_commands_allow_the_units_ninety_second_shutdown(self):
        h=Fake(); seen=[]
        h.command=lambda argv,**kwargs: seen.append(kwargs.get('timeout',30)) or subprocess.CompletedProcess(argv,0,'','')
        h.ctl('stop',backend.SYNC_SERVICE)
        self.assertGreaterEqual(seen[0],100)

    def test_short_resync_option_is_forbidden(self):
        h=Fake(); value='{ path=/usr/bin/rclone ; argv[]=/usr/bin/rclone bisync /home/test/offline onedrive:Obsidian -1 ; ignore_errors=no ; }'
        h.states=[dict(state(10,11),Type='oneshot',ExecStart=value)]
        with self.assertRaisesRegex(RuntimeError,'forbidden'): h.preflight()

    def test_pause_attempts_both_timers_first_even_on_error(self):
        h = Fake(); h.failure = lambda cmd: backend.SYNC_TIMER in cmd
        with self.assertRaises(RuntimeError): h.pause()
        self.assertEqual([c[-1] for c in h.commands], [backend.SYNC_TIMER, backend.BIND_TIMER, backend.SYNC_SERVICE, backend.BIND_SERVICE])

    def test_preflight_validates_default_pair_and_flags(self):
        h = Fake()
        valid = '{ path=/usr/bin/rclone ; argv[]=/usr/bin/rclone bisync /home/test/offline onedrive:Obsidian ; ignore_errors=no ; }'
        h.states = [dict(state(10, 11), ExecStart=valid, Type='oneshot')]
        h.preflight()
        self.assertFalse(h.commands)
        for extra in ('--resync', '--force', '--workdir=/bad', '--config /bad', '--cache-dir=/bad'):
            h.states = [dict(state(10, 11), Type='oneshot', ExecStart=valid.replace(' ; ignore', ' '+extra+' ; ignore'))]
            with self.assertRaises(RuntimeError): h.preflight()
        h.states = [{'ExecStart': '/bin/echo unknown'}]
        with self.assertRaises(RuntimeError): h.preflight()

    def test_preflight_rejects_unsupported_completion_fields(self):
        h = Fake()
        h.states = [{'ExecStart': '{ argv[]=/usr/bin/rclone bisync /home/test/offline onedrive:Obsidian ; }'}]
        with self.assertRaisesRegex(RuntimeError, 'Unsupported'):
            h.preflight()

    def test_resume_requires_sync_proof(self):
        h = Fake()
        with self.assertRaises(RuntimeError): h.resume()
        self.assertEqual(h.commands, [])


class MountTests(unittest.TestCase):
    def mounts(self, h, nested=False, wrong=False):
        mounts = [dict(id=10, parent=1, dev='0:44', root='/', mount=str(h.c.mount), type='fuse.rclone', source='onedrive:')]
        mounts += [dict(id=11, parent=10, dev='8:1', root='/home/test/offline' if not wrong else '/wrong', mount=str(h.c.target), type='ext4', source='/dev/sda')]
        if nested: mounts.append(dict(id=12, parent=11, dev='8:1', root='/', mount=str(h.c.target/'nested'), type='ext4', source='/dev/sda'))
        return mounts

    def test_mountinfo_parses_escaped_paths(self):
        entries = backend.Host.parse_mountinfo('10 1 0:44 / /home/test/OneDrive rw - fuse.rclone onedrive: rw\n11 10 8:1 /a\\040b /home/test/OneDrive/Obsidian rw - ext4 /dev/sda rw\n')
        self.assertEqual(entries[1]['root'], '/a b')
        self.assertEqual(entries[0]['type'], 'fuse.rclone')

    def test_nested_mount_refused_without_mutation(self):
        h = Fake(); h.mounts = lambda: self.mounts(h, nested=True)
        with self.assertRaises(RuntimeError): h.unmount_all()
        self.assertFalse(h.commands)

    def test_btrfs_bind_identity_does_not_require_mountinfo_device_to_match_stat(self):
        h=Fake(); entries=self.mounts(h)
        entries[1].update(type='btrfs',dev='0:35')
        h.mounts=lambda:entries
        # Actual workstation: mountinfo reports 0:35, while both stat identities are 0:48.
        h.identity=lambda path:('0:48',2104232)
        fuse,bind=h.guarded_mounts()
        self.assertIsNotNone(fuse); self.assertIsNotNone(bind)

    def test_wrong_bind_identity_refused(self):
        h = Fake(); h.mounts = lambda: self.mounts(h, wrong=True)
        h.identity = lambda path: ('8:1', 42) if str(path) == str(h.c.offline) else ('8:1', 99)
        with self.assertRaises(RuntimeError): h.unmount_all()
        self.assertFalse(h.commands)

    def test_unmount_uses_only_normal_unmount(self):
        h = Fake(); entries = self.mounts(h)
        snapshots = [entries, entries[:1], entries[:1], []]
        h.mounts = lambda: snapshots.pop(0)
        h.identity = lambda path: ('8:1', 42)
        h.unmount_all()
        self.assertEqual(h.commands[0], ['/usr/bin/sudo', '-n', '/usr/bin/umount', str(h.c.target)])
        self.assertEqual(h.commands[-1], ['/usr/bin/fusermount3', '-u', str(h.c.mount)])
        self.assertFalse(any(flag in c for c in h.commands for flag in ('-f', '-l', '--force', '--lazy')))

    def test_bind_timeout_requests_stop(self):
        h = Fake(); h.wait_timeout = 2
        h.cloud_ready = lambda: True
        h.bind_ready = lambda: False
        with self.assertRaisesRegex(RuntimeError, 'bind'): h.start_bind()
        self.assertEqual(h.commands[-1][-2:], ['stop', backend.BIND_SERVICE])

    def test_start_mount_requires_notify_and_exact_fuse(self):
        h = Fake(); h.wait_timeout = 2
        h.states = [{'ActiveState': 'active', 'Type': 'notify'}] * 2
        h.mounts = lambda: []
        with self.assertRaises(RuntimeError): h.start_mount()
        h = Fake(); h.states = [{'ActiveState': 'active', 'Type': 'notify'}]
        h.mounts = lambda: self.mounts(h)[:1]
        h.start_mount()


class InspectionTests(unittest.TestCase):
    def test_inspection_uses_noninteractive_fixed_readonly_root_helper(self):
        h = Fake(); h.mounts = lambda: []
        h.states = [{'MainPID': '55', 'ActiveState': 'active'}]
        payload = {'busy': [], 'bisync': [{'pid': 55}], 'restricted': []}
        def command(argv, **kwargs):
            h.commands.append(argv)
            return subprocess.CompletedProcess(argv, 0, backend.json.dumps(payload), '')
        h.command = command
        self.assertEqual(h.inspect(), payload)
        self.assertEqual(h.commands[0][:6], ['/usr/bin/sudo', '-n', '/usr/bin/python3', '-I', '-B', '-c'])
        self.assertIn('55', h.commands[0][-1])

    def test_inspection_rejects_malformed_results(self):
        h = Fake(); h.mounts = lambda: []; h.states = [{'MainPID':'0'}]
        with self.assertRaises(RuntimeError): h.inspect()

    def test_root_helper_reads_proc_and_ignores_service_only_in_busy(self):
        import io
        from unittest.mock import patch
        namespace = {'__name__': 'fixture'}
        exec(backend.PROC_INSPECT_CODE, namespace)
        files = {
            '/proc/55/cmdline': b'/usr/bin/rclone\x00bisync\x00/home/test/offline\x00onedrive:Obsidian\x00',
            '/proc/56/cmdline': b'editor\x00', '/proc/57/cmdline': b'',
            '/proc/55/fdinfo/3': b'mnt_id:\t10\n', '/proc/56/fdinfo/3': b'mnt_id:\t11\n',
        }
        def opening(path, mode='r', **kwargs):
            value = files[str(path)]
            return io.BytesIO(value) if 'b' in mode else io.StringIO(value.decode())
        def listing(path):
            return ['55', '56', '57'] if path == '/proc' else ['3']
        def link(path):
            if path.endswith('/fd/3'): return '/home/test/offline/note.md'
            return '/'
        with patch('builtins.open', opening), patch('os.listdir', listing), patch('os.readlink', link):
            result = namespace['scan']({'mount':'/home/test/OneDrive', 'offline':'/home/test/offline', 'ids':[10,11], 'ignore':55})
        self.assertEqual([r['pid'] for r in result['bisync']], [55])
        self.assertTrue(result['busy'])
        self.assertTrue(all(r['pid'] == 56 for r in result['busy']))
        self.assertFalse(result['restricted'])

    def test_diagnostics_are_bounded_and_truthful(self):
        h = Fake(); h.diagnostics()
        self.assertEqual(len(h.commands), 4)
        self.assertTrue(any('/usr/bin/journalctl' in c and '--lines=40' in c for c in h.commands))


class CompletionTests(unittest.TestCase):
    def test_already_active_sync_is_not_our_run(self):
        h = Fake(); h.states = [state(10, active='activating'), state(20, 21)]
        with self.assertRaisesRegex(RuntimeError, 'inactive'): h.run_sync()
        self.assertFalse(h.commands)

    def test_exit_timestamp_before_start_not_success(self):
        h = Fake(); h.states = [state(10, 11), state(20, 11)]
        with self.assertRaises(RuntimeError): h.run_sync()

    def test_resume_checks_proof_before_auth_and_orders_timers(self):
        h = Fake(); events = []; h.last_sync = state(20, 21)
        h.verify = lambda: events.append('verify')
        h.authenticate = lambda: events.append('auth')
        h.states = [{'ActiveState': 'active'}, {'ActiveState': 'active'}]
        h.resume()
        self.assertEqual(events, ['verify', 'auth'])
        self.assertEqual([cmd[-1] for cmd in h.commands], [backend.BIND_TIMER, backend.SYNC_TIMER])
        self.assertEqual(h.commands[0][:3], ['/usr/bin/sudo', '-n', '/usr/bin/systemctl'])

    def test_verify_rejects_later_failure(self):
        h = Fake(); h.last_sync = state(20, 21)
        h.guarded_mounts = lambda: ({'id':10}, {'id':11})
        h.states = [{'ActiveState':'active', 'Type':'notify'}, state(30, 31, result='exit-code')]
        with self.assertRaisesRegex(RuntimeError, 'proof'): h.verify()

    def test_authentication_inherits_terminal(self):
        from unittest.mock import patch
        h = Fake(); recorded = []
        h.command = lambda argv, **kwargs: recorded.append((argv, kwargs))
        with patch('os.geteuid', return_value=1000): h.authenticate()
        self.assertEqual(recorded, [(['/usr/bin/sudo', '-v'], {'timeout':120, 'capture':False})])
        with patch('os.geteuid', return_value=0):
            with self.assertRaises(RuntimeError): h.authenticate()


if __name__ == '__main__':
    unittest.main()

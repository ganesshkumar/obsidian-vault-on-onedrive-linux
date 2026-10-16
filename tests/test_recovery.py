#!/usr/bin/python3 -B
"""Automated fixtures only: no sudo, real services, unmounts, or cloud access."""
import contextlib
from support import load_module
import io
from pathlib import Path
import tempfile
import unittest
import json
import os
from unittest import mock

ROOT=Path(__file__).parent
SOURCE=ROOT.parent/'templates/bin/restart-onedrive.in'

def load():
    return load_module('bin/restart-onedrive')

class FakeHost:
    def __init__(self, fail_sync=False, busy=False):
        self.events=[]; self.fail_sync=fail_sync; self.busy=busy; self.timers=False
    def guarded_mounts(self): self.events.append('guarded_mounts'); return None,None
    def authenticate(self): self.events.append('authenticate')
    def inspect(self):
        self.events.append('inspect')
        return {'busy':[{'pid':123,'process':'dolphin','reference':'cwd'}] if self.busy else [], 'bisync':[], 'restricted':[]}
    def pause(self): self.events.append('pause'); self.timers=False
    def unmount_all(self): self.events.append('unmount')
    def start_mount(self): self.events.append('mount')
    def start_bind(self): self.events.append('bind')
    def run_sync(self):
        self.events.append('bisync')
        if self.fail_sync: raise RuntimeError('fixture: bisync failed')
    def verify(self): self.events.append('verify')
    def resume(self): self.events.append('resume'); self.timers=True
    def diagnostics(self): self.events.append('diagnostics')

class Tests(unittest.TestCase):
    def fixture(self):
        temp=tempfile.TemporaryDirectory(prefix='onedrive-fixture-'); self.addCleanup(temp.cleanup)
        m=load(); c=m.Config(Path(temp.name)); c.offline.mkdir(parents=True); c.state.mkdir(parents=True)
        return m,c,FakeHost()

    def test_check_rejects_invalid_topology_without_authentication_or_writes(self):
        m,c,h=self.fixture()
        for suffix in ('.path1.lst','.path2.lst'):
            (c.state/(c.session+suffix)).write_text('fixture saved listing')
        host=m.Host(c)
        host.mounts=lambda:[dict(mount=str(c.target/'unexpected'))]
        before={str(p.relative_to(c.home)):p.read_bytes() if p.is_file() else None
                for p in c.home.rglob('*')}
        output=io.StringIO()
        with mock.patch.object(m.Path,'home',return_value=c.home), \
                mock.patch.object(m.os,'geteuid',return_value=1000), \
                mock.patch.object(m,'Host',return_value=host), \
                mock.patch.object(host,'preflight'), \
                mock.patch.object(host,'authenticate') as authenticate, \
                mock.patch.object(host,'command',side_effect=AssertionError('Unexpected host command')), \
                mock.patch.object(m,'Recovery') as recovery, \
                contextlib.redirect_stdout(output):
            with self.assertRaisesRegex(RuntimeError,'Nested/unexpected mount'):
                m.main(['--check'])
        authenticate.assert_not_called()
        recovery.assert_not_called()
        self.assertNotIn('Expected mount/bisync units',output.getvalue())
        self.assertEqual(before,{str(p.relative_to(c.home)):p.read_bytes() if p.is_file() else None
                                 for p in c.home.rglob('*')})

    def test_invalid_initial_topology_prevents_pause_backup_and_stale_lock_removal(self):
        m,c,h=self.fixture()
        data=json.dumps({'Session':str(c.state/c.session),'PID':'999999999'})
        c.lock.write_text(data)
        host=m.Host(c)
        host.mounts=lambda:[dict(mount=str(c.target/'unexpected'))]
        h.guarded_mounts=host.guarded_mounts
        # Model the backend's existing immediate pre-unmount topology recheck.
        h.unmount_all=h.guarded_mounts
        with contextlib.redirect_stdout(io.StringIO()),self.assertRaisesRegex(RuntimeError,'Nested/unexpected mount'):
            m.Recovery(c,h).run()
        self.assertNotIn('pause',h.events)
        self.assertNotIn('authenticate',h.events)
        self.assertFalse(c.backups.exists())
        self.assertEqual(c.lock.read_text(),data)

    def test_busy_preflight_does_not_stop_services_or_create_backups(self):
        m,c,h=self.fixture(); h.busy=True
        with contextlib.redirect_stdout(io.StringIO()),self.assertRaisesRegex(RuntimeError,'Close applications'):
            m.Recovery(c,h).run()
        self.assertNotIn('pause',h.events); self.assertFalse(c.backups.exists())

    def test_unknown_process_inspection_fails_before_stopping_services(self):
        m,c,h=self.fixture(); h.inspect=lambda:{'busy':[],'bisync':[],'restricted':[123]}
        with contextlib.redirect_stdout(io.StringIO()),self.assertRaises(RuntimeError): m.Recovery(c,h).run()
        self.assertNotIn('pause',h.events)

    def test_active_bisync_after_stop_blocks_lock_removal_and_unmount(self):
        m,c,h=self.fixture(); calls=[]
        def inspect():
            calls.append(1)
            return {'busy':[],'bisync':[456] if len(calls)>1 else [],'restricted':[]}
        h.inspect=inspect; c.lock.write_text('leave untouched')
        with contextlib.redirect_stdout(io.StringIO()),self.assertRaises(RuntimeError): m.Recovery(c,h).run()
        self.assertEqual(c.lock.read_text(),'leave untouched'); self.assertNotIn('unmount',h.events)

    def test_live_lock_owner_is_never_removed(self):
        m,c,h=self.fixture(); data=json.dumps({'Session':str(c.state/c.session),'PID':str(os.getpid())}); c.lock.write_text(data)
        with contextlib.redirect_stdout(io.StringIO()),self.assertRaisesRegex(RuntimeError,'PID still exists'):
            m.Recovery(c,h).run()
        self.assertEqual(c.lock.read_text(),data); self.assertNotIn('unmount',h.events)

    def test_malformed_or_wrong_session_lock_is_never_removed(self):
        for data in ('not json','[]',json.dumps({'Session':'wrong-pair','PID':'999999999'}),json.dumps({'Session':'placeholder','PID':'0'})):
            with self.subTest(data=data):
                m,c,h=self.fixture(); c.lock.write_text(data)
                with contextlib.redirect_stdout(io.StringIO()),self.assertRaises(RuntimeError): m.Recovery(c,h).run()
                self.assertEqual(c.lock.read_text(),data); self.assertNotIn('unmount',h.events)

    def test_backup_failure_leaves_lock_and_mount_untouched(self):
        m,c,h=self.fixture(); data=json.dumps({'Session':str(c.state/c.session),'PID':'999999999'}); c.lock.write_text(data)
        with mock.patch.object(m.shutil,'copytree',side_effect=OSError('fixture: disk full')),contextlib.redirect_stdout(io.StringIO()),self.assertRaises(OSError):
            m.Recovery(c,h).run()
        self.assertEqual(c.lock.read_text(),data); self.assertNotIn('unmount',h.events); self.assertNotIn('resume',h.events)

    def test_timers_resume_only_after_mount_bind_sync_and_verification(self):
        m,c,h=self.fixture()
        with contextlib.redirect_stdout(io.StringIO()): m.Recovery(c,h).run()
        expected=['unmount','mount','bind','bisync','verify','resume']
        self.assertEqual([x for x in h.events if x in expected],expected)
        self.assertTrue(h.timers)

    def test_bind_failure_prevents_sync_and_timer_restart(self):
        m,c,h=self.fixture()
        def fail(): raise RuntimeError('fixture: bind failed')
        h.start_bind=fail
        with contextlib.redirect_stdout(io.StringIO()),self.assertRaisesRegex(RuntimeError,'bind failed'): m.Recovery(c,h).run()
        self.assertNotIn('bisync',h.events); self.assertNotIn('resume',h.events)

    def test_stale_lock_is_archived_and_vault_and_listings_are_preserved(self):
        m=load()
        with tempfile.TemporaryDirectory(prefix='onedrive-fixture-') as temp:
            c=m.Config(Path(temp)); c.offline.mkdir(parents=True); c.state.mkdir(parents=True)
            (c.offline/'sample.md').write_text('fixture local note')
            listing=c.state/(c.session+'.path1.lst'); listing.write_text('fixture saved baseline')
            c.lock.write_text(json.dumps({'Session':str(c.state/c.session),'PID':'999999999'}))
            with contextlib.redirect_stdout(io.StringIO()): m.Recovery(c,FakeHost()).run()
            self.assertFalse(c.lock.exists(),'The stale lock remained in the active location')
            backups=list(c.backups.iterdir()); self.assertEqual(len(backups),1)
            self.assertEqual((backups[0]/'local-vault/sample.md').read_text(),'fixture local note')
            self.assertTrue((backups[0]/'stale-bisync.lck').is_file())
            self.assertEqual(listing.read_text(),'fixture saved baseline')
            self.assertEqual((backups[0]/'bisync-state'/listing.name).read_text(),'fixture saved baseline')

    def test_diagnostics_failure_does_not_hide_the_actual_sync_error(self):
        m=load()
        with tempfile.TemporaryDirectory(prefix='onedrive-fixture-') as temp:
            c=m.Config(Path(temp)); c.offline.mkdir(parents=True)
            host=FakeHost(fail_sync=True)
            def broken_diagnostics(): raise RuntimeError('fixture: journal unavailable')
            host.diagnostics=broken_diagnostics
            with contextlib.redirect_stdout(io.StringIO()),self.assertRaisesRegex(RuntimeError,'bisync failed'):
                m.Recovery(c,host).run()

    def test_failed_bisync_never_reports_healthy_or_resumes_timers(self):
        self.assertTrue(SOURCE.exists(),'Replacement is not implemented yet')
        m=load()
        with tempfile.TemporaryDirectory(prefix='onedrive-fixture-') as temp:
            c=m.Config(Path(temp)); c.offline.mkdir(parents=True)
            host=FakeHost(fail_sync=True); output=io.StringIO()
            with contextlib.redirect_stdout(output), self.assertRaisesRegex(RuntimeError,'bisync failed'):
                m.Recovery(c,host).run()
            self.assertFalse(host.timers)
            self.assertNotIn('ONEDRIVE HEALTHY',output.getvalue())
            self.assertNotIn('resume',host.events)

if __name__=='__main__': unittest.main()

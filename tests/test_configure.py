"""Rendering tests only; never install units, run sudo, contact cloud, or start services."""
from pathlib import Path
import importlib.util
import tempfile
import unittest

ROOT = Path(__file__).resolve().parents[1]


def load_configure():
    path = ROOT / 'tools/configure.py'
    if not path.exists():
        return None
    spec = importlib.util.spec_from_file_location('configure', path)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


class ConfigureTests(unittest.TestCase):
    def test_render_uses_reader_account_not_author_machine(self):
        module = load_configure()
        self.assertIsNotNone(module, 'Portable configuration renderer is missing')
        settings = module.settings('reader', '/home/reader', 'reader', 'ext4')
        files = module.render_files(settings)
        self.assertIn('system/home-reader-OneDrive-Obsidian.mount', files)
        self.assertIn('User=reader', files['system/rclone-onedrive.service'])
        self.assertIn('/home/reader/OneDrive', files['bin/onedrive-offline-bind'])
        self.assertIn("children[0]['type'] != 'ext4'", files['bin/onedrive-offline-bind'])
        self.assertIn('Requisite=rclone-onedrive.service', files['system/home-reader-OneDrive-Obsidian.mount'])


    def test_output_rejects_path_traversal(self):
        module = load_configure()
        values = module.settings('reader', '/home/reader', 'reader', 'ext4')
        with tempfile.TemporaryDirectory(prefix='render-test-') as temp:
            output = Path(temp) / 'out'
            with self.assertRaises(ValueError):
                module.write_output(output, values, {'../escape': 'must not be written'})
            self.assertFalse((Path(temp) / 'escape').exists())

    def test_hyphenated_home_preserves_systemd_escape_in_python_and_shell(self):
        import shlex
        module = load_configure()
        values = module.settings('reader-one', '/home/reader-one', 'reader-one', 'ext4')
        files = module.render_files(values)
        self.assertIn(r'\x2d', values['BIND_UNIT'])
        namespace = {'__name__': 'fixture'}
        exec(compile(files['bin/onedrive-offline-bind'], 'fixture', 'exec'), namespace)
        from unittest.mock import patch
        import subprocess
        with patch.object(namespace['os'], 'geteuid', return_value=0), patch.object(namespace['subprocess'], 'run') as run:
            namespace['bind']()
        self.assertEqual(run.call_args.args[0][-1], values['BIND_UNIT'])
        line = next(line for line in files['bin/onedrive-cycle'].splitlines() if line.startswith('sudo systemctl stop ') and '.mount' in line)
        self.assertEqual(shlex.split(line)[-1], values['BIND_UNIT'])
        subprocess.run(['bash', '-n'], input=files['bin/onedrive-cycle'], text=True, check=True)

    def test_existing_output_is_not_modified(self):
        module = load_configure()
        values = module.settings('reader', '/home/reader', 'reader', 'btrfs')
        with tempfile.TemporaryDirectory(prefix='render-test-') as temp:
            output = Path(temp) / 'out'
            output.mkdir()
            marker = output / 'keep'
            marker.write_text('original')
            with self.assertRaises(FileExistsError):
                module.write_output(output, values, module.render_files(values))
            self.assertEqual(marker.read_text(), 'original')

    def test_unsafe_account_home_and_filesystem_are_refused(self):
        module = load_configure()
        for user, home, group, fs_type in [
            ('root', '/home/root', 'reader', 'ext4'),
            ('reader', '/home/name with spaces', 'reader', 'ext4'),
            ('reader', '/home/../etc', 'reader', 'ext4'),
            ('reader', '/home/name%u', 'reader', 'ext4'),
            ('reader', '/home/reader', 'reader', 'fuse.rclone'),
        ]:
            with self.subTest(user=user, home=home, filesystem=fs_type), self.assertRaises(ValueError):
                module.settings(user, home, group, fs_type)

    def test_write_produces_only_units_helpers_and_settings(self):
        module = load_configure()
        values = module.settings('reader', '/home/reader', 'reader', 'ext4')
        files = module.render_files(values)
        with tempfile.TemporaryDirectory(prefix='render-test-') as temp:
            output = Path(temp) / 'out'
            module.write_output(output, values, files)
            actual = {str(path.relative_to(output)) for path in output.rglob('*') if path.is_file()}
            self.assertEqual(actual, set(files) | {'settings.json'})
            for name, text in files.items():
                self.assertEqual((output / name).read_text(), text)

if __name__ == '__main__':
    unittest.main()

#!/usr/bin/env python3
"""Render reviewed templates for one local account. Never install or start anything."""
import argparse
import grp
import json
import os
from pathlib import Path, PurePosixPath
import pwd
import re
import shlex
import shutil
import subprocess

ROOT = Path(__file__).resolve().parents[1]
LOCAL_FILESYSTEMS = {'btrfs', 'ext4', 'ext3', 'ext2', 'xfs', 'f2fs', 'zfs'}


def settings(user, home, group, local_fs_type):
    for label, value in [('user', user), ('group', group)]:
        if not re.fullmatch(r'[a-z_][a-z0-9_-]*', value) or value == 'root':
            raise ValueError(label + ' must be a simple non-root local account name')
    if (not re.fullmatch(r'/[A-Za-z0-9_./-]+', home)
            or '..' in PurePosixPath(home).parts
            or len(PurePosixPath(home).parts) < 3):
        raise ValueError('home must be an absolute non-root path without whitespace, traversal or shell/systemd metacharacters')
    home = str(PurePosixPath(home))
    if local_fs_type not in LOCAL_FILESYSTEMS:
        raise ValueError('Expected a supported local backing filesystem, not a network/FUSE filesystem')
    unit = subprocess.run(['systemd-escape', '--path', '--suffix=mount', home + '/OneDrive/Obsidian'],
                          check=True, text=True, capture_output=True, timeout=5).stdout.strip()
    if '/' in unit or not unit.endswith('.mount') or not unit:
        raise ValueError('Unexpected systemd-escape output')
    return dict(USER=user, HOME=home, GROUP=group, LOCAL_FS_TYPE=local_fs_type,
                BIND_UNIT=unit, BIND_UNIT_PY=repr(unit), BIND_UNIT_SH=shlex.quote(unit))


def render_files(values):
    result = {}
    for path in sorted((ROOT / 'templates').rglob('*.in')):
        name = str(path.relative_to(ROOT / 'templates'))[:-3]
        if name == 'system/Obsidian.mount':
            name = 'system/' + values['BIND_UNIT']
        text = path.read_text()
        for key, value in values.items():
            text = text.replace('@' + key + '@', value)
        if re.search(r'@[A-Z_]+@', text):
            raise ValueError('Unresolved placeholder in ' + name)
        result[name] = text
    if len(result) != 13:
        raise ValueError('Expected eight units and five helper/controller files')
    return result


def write_output(output, values, files):
    for name in files:
        relative = PurePosixPath(name)
        if relative.is_absolute() or '..' in relative.parts or len(relative.parts) != 2 or relative.parts[0] not in ('bin', 'system', 'user'):
            raise ValueError('Invalid generated relative path: ' + name)
    output = Path(output).absolute()
    if output.exists() or output.is_symlink():
        raise FileExistsError('Refusing existing output directory; choose a new --output')
    output.parent.mkdir(parents=True, exist_ok=True)
    # Exclusive creation also rejects a competing renderer that wins the race.
    output.mkdir(mode=0o700)
    try:
        for name, text in files.items():
            destination = output / name
            destination.parent.mkdir(parents=True, exist_ok=True)
            destination.write_text(text)
            destination.chmod(0o755 if name.startswith('bin/') else 0o644)
        (output / 'settings.json').write_text(json.dumps(values, indent=2) + '\n')
    except BaseException:
        shutil.rmtree(output)
        raise


def detect_local_fs(home):
    backing = Path(home) / '.local/share/onedrive-offline/Obsidian'
    target = backing if backing.exists() else Path(home)
    return subprocess.run(['findmnt', '--noheadings', '--output', 'FSTYPE', '--target', str(target)],
                          capture_output=True, text=True, timeout=5, check=True).stdout.strip()


def main():
    account = pwd.getpwuid(os.getuid())
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--user', default=account.pw_name)
    parser.add_argument('--home', default=account.pw_dir)
    parser.add_argument('--group', default=grp.getgrgid(account.pw_gid).gr_name)
    parser.add_argument('--local-fs-type', help='Normally detected from the backing directory or home filesystem')
    parser.add_argument('--output', type=Path, default=ROOT / 'build')
    parser.add_argument('--write', action='store_true', help='Write generated files only; no installation or service changes')
    args = parser.parse_args()
    fs_type = args.local_fs_type or detect_local_fs(args.home)
    values = settings(args.user, args.home, args.group, fs_type)
    files = render_files(values)
    print(json.dumps({k: v for k, v in values.items() if not k.endswith(('_PY', '_SH'))}, indent=2))
    print('Generated file plan:')
    for name in files:
        print('  ' + name)
    if args.write:
        write_output(args.output, values, files)
        print('Rendered to ' + str(args.output.absolute()) + '; nothing installed or started.')
    else:
        print('Preview only. Add --write to generate files.')


if __name__ == '__main__':
    main()

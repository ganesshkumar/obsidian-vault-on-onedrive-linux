"""Load only repository-owned rendered templates; never install or invoke their entry points."""
from pathlib import Path
import importlib.util
import sys
import types

ROOT = Path(__file__).resolve().parents[1]
spec = importlib.util.spec_from_file_location('configure_fixture', ROOT / 'tools/configure.py')
configure = importlib.util.module_from_spec(spec)
spec.loader.exec_module(configure)
VALUES = configure.settings('reader', '/home/reader', 'reader', 'btrfs')
FILES = configure.render_files(VALUES)


def source(name):
    return FILES[name]


def load_module(name):
    module = types.ModuleType('fixture_' + name.replace('/', '_').replace('-', '_'))
    sys.modules[module.__name__] = module
    exec(compile(source(name), name, 'exec'), module.__dict__)
    return module

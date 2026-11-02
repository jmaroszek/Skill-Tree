"""requirements-lock.txt is what builds install and what GitHub's dependency
graph reads, so it has to keep up with the pins and cover every platform."""
import re

import pytest
from support.paths import ROOT


RECOMPILE = "recompile it: docs/setup.md, section 5, has the command"


def _normalized(name):
    return re.sub(r'[-_.]+', '-', name).lower()


def _locked():
    """Each locked package, by name: its version, its marker and its hashes."""
    locked = {}
    current = None
    for line in (ROOT / 'requirements-lock.txt').read_text(encoding='utf-8').splitlines():
        pin = re.match(r'([A-Za-z0-9._-]+)==([^\s;\\]+)\s*(?:;\s*(.*?))?\s*\\?$', line)
        if pin:
            current = {'version': pin[2], 'marker': pin[3] or '', 'hashes': []}
            locked[_normalized(pin[1])] = current
        elif line.strip().startswith('--hash='):
            current['hashes'].append(line.strip())
    return locked


def _direct_pins(filename='requirements-build.txt'):
    """The pins a requirements file names, following its -r includes."""
    pins = {}
    for line in (ROOT / filename).read_text(encoding='utf-8').splitlines():
        line = line.split('#')[0].strip()
        if line.startswith('-r '):
            pins |= _direct_pins(line.removeprefix('-r ').strip())
        elif line:
            name, version = line.split('==')
            pins[_normalized(name)] = version
    return pins


def test_the_lock_agrees_with_every_direct_pin():
    locked = _locked()
    for name, version in _direct_pins().items():
        assert name in locked, f"{name} isn't in requirements-lock.txt; {RECOMPILE}"
        assert locked[name]['version'] == version, (
            f"{name} is pinned at {version} but locked at {locked[name]['version']}; {RECOMPILE}")


def test_every_locked_package_has_a_hash():
    missing = [name for name, entry in _locked().items() if not entry['hashes']]
    assert not missing


@pytest.mark.parametrize('name', ['flask', 'werkzeug', 'jinja2', 'requests', 'urllib3'])
def test_the_lock_names_the_packages_nothing_pins_directly(name):
    """The reason it exists: Dependabot only sees what a manifest names."""
    assert name in _locked()
    assert name not in _direct_pins()


@pytest.mark.parametrize('name, platform', [
    ('pefile', 'win32'),
    ('pywin32-ctypes', 'win32'),
    ('macholib', 'darwin'),
])
def test_the_lock_covers_the_packages_only_one_platform_needs(name, platform):
    """Compiled for one platform, the lock would leave these out, and a hash-checked
    install on the other platforms would refuse to go on."""
    assert f"sys_platform == '{platform}'" in _locked()[name]['marker']


@pytest.mark.parametrize('workflow', ['ci.yml', 'release.yml'])
def test_every_build_installs_the_lock(workflow):
    text = (ROOT / '.github' / 'workflows' / workflow).read_text(encoding='utf-8')
    assert 'python -m pip install --require-hashes -r requirements-lock.txt' in text
    assert 'pip install -r requirements-build.txt' not in text

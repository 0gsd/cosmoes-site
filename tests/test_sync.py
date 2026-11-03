"""scripts/sync_specs.py: it runs the export, checks the result as the site reads it, and replaces site/specs/ only
then. The export is a stand-in here (a fake `enough.docoes` that copies the fixture); the real one is enough-dev's."""
from __future__ import annotations

import importlib.util
import re
import shutil
import subprocess
import sys

import pytest

from conftest import ROOT, make_export, reseal, rewrite
from cosmoes import specs as specs_mod

_spec = importlib.util.spec_from_file_location('sync_specs', ROOT / 'scripts' / 'sync_specs.py')
sync = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(sync)

SLUGS = ('thym', 'ascribe')

FAKE_DOCOES = '''"""A stand-in for enough's DocOES export: copies one document of the fixture into the out-dir and merges its
manifest, as `python -m enough.docoes export <doc> <out-dir> [--slug S …] --page …` does."""
import json, shutil, sys
from pathlib import Path

FIXTURE = Path({fixture!r})
argv = sys.argv[1:]
if argv[:1] != ['export']:
    sys.exit("usage: python -m enough.docoes export <doc> <out-dir>")
doc, out, rest = argv[1], Path(argv[2]), argv[3:]
slug = rest[rest.index('--slug') + 1] if '--slug' in rest else (Path(doc).stem.lower() if doc.endswith('.md') else doc)
pages = {{}}
for i, a in enumerate(rest):
    if a == '--page':
        k, v = rest[i + 1].split('=', 1)
        pages[k] = v
src = json.loads((FIXTURE / 'manifest.json').read_text())
entry = next((d for d in src['documents'] if d['slug'] == slug), None)
if entry is None:
    print('no document ' + doc, file=sys.stderr)
    sys.exit(2)
shutil.copytree(FIXTURE / slug, out / slug, dirs_exist_ok=True)
shutil.copyfile(FIXTURE / 'docs.css', out / 'docs.css')
mp = out / 'manifest.json'
m = json.loads(mp.read_text()) if mp.exists() else dict(src, documents=[])
m['pages'] = pages
m['documents'] = [d for d in m['documents'] if d['slug'] != slug] + [entry]
mp.write_text(json.dumps(m))
'''


@pytest.fixture
def fixture(tmp_path):
    return make_export(tmp_path / 'fixture')


def fake_enough(tmp_path, fixture, docoes: str = FAKE_DOCOES):
    root = tmp_path / 'enough-checkout'
    (root / 'enough').mkdir(parents=True)
    (root / 'enough' / '__init__.py').write_text('')
    (root / 'enough' / 'docoes.py').write_text(docoes.format(fixture=str(fixture)))
    return root


@pytest.fixture
def synced(tmp_path, monkeypatch):
    """The sync, writing into tmp_path instead of this checkout, exporting two of the fixture's documents."""
    dest = tmp_path / 'site' / 'specs'
    monkeypatch.setattr(sync, 'DEST', dest)
    monkeypatch.setattr(sync, 'SOURCES', (('thym', 'thym', ()), ('docs/ASCRIBE.md', 'ascribe', ('--slug', 'ascribe'))))
    return dest


def test_the_sync_script_says_how_to_use_it():
    r = subprocess.run([sys.executable, str(ROOT / 'scripts' / 'sync_specs.py'), '--help'], capture_output=True, text=True, timeout=60)
    assert r.returncode == 0 and '--enough' in r.stdout and '--python' in r.stdout
    r = subprocess.run([sys.executable, str(ROOT / 'scripts' / 'sync_specs.py')], capture_output=True, text=True, timeout=60)
    assert r.returncode == 2 and '--enough' in r.stderr


def test_the_sources_are_the_four_hosts_documents():
    from cosmoes.app import HOSTS
    assert [slug for _, slug, _ in sync.SOURCES] == list(HOSTS.values())
    assert sync.SOURCES[3][0] == 'defaults/cosm/chapters/comprise-oes.md'
    assert sync.SOURCES[3][2] == ('--slug', 'comprise-oes', '--name', 'Comprise OES 1', '--version', '1')
    assert sync.PAGES == {'short': '/', 'atem': '/atem', 'fabula': '/fabula'}


def test_the_sync_exports_checks_and_replaces_the_folder(tmp_path, fixture, synced, capsys):
    dest = synced
    (dest / 'old').mkdir(parents=True)
    (dest / 'old' / 'short.html').write_text('a document no longer exported')
    assert sync.main(['--enough', str(fake_enough(tmp_path, fixture)), '--python', sys.executable]) == 0
    out = capsys.readouterr().out
    assert re.search(r'^thym\s+Thym 0  v0  [\d,]+ bytes$', out, re.M), out
    assert re.search(r'^ascribe\s+Ascribe OES 1  v1  [\d,]+ bytes$', out, re.M), out
    assert 'from enough/0.5.0 at 12dfa61 with uncommitted changes; wrote ' in out and str(dest) + '/: look at it' in out
    files = sorted(p.relative_to(dest).as_posix() for p in dest.rglob('*') if p.is_file())
    assert files == ['ascribe/atem.html', 'ascribe/fabula.html', 'ascribe/short.html', 'docs.css', 'manifest.json',
                     'thym/atem.html', 'thym/fabula.html', 'thym/short.html']
    assert (dest / 'docs.css').read_bytes() == (fixture / 'docs.css').read_bytes()
    specs = specs_mod.Specs(dest)
    assert [d['slug'] for d in specs.documents] == ['thym', 'ascribe'] and specs.manifest()['pages'] == sync.PAGES
    assert sorted(p.name for p in dest.parent.iterdir()) == ['specs']     # nothing left beside it


def test_the_sync_changes_nothing_when_an_export_fails(tmp_path, fixture, synced, monkeypatch):
    dest = synced
    dest.mkdir(parents=True)
    (dest / 'manifest.json').write_text('{"kept": true}')
    monkeypatch.setattr(sync, 'SOURCES', (('thym', 'thym', ()), ('docs/NOPE.md', 'nope', ())))
    with pytest.raises(SystemExit) as e:
        sync.main(['--enough', str(fake_enough(tmp_path, fixture)), '--python', sys.executable])
    assert str(e.value) == 'docs/NOPE.md: the export failed (exit 2); nothing was changed'
    assert (dest / 'manifest.json').read_text() == '{"kept": true}'


def test_the_sync_says_so_when_the_checkout_has_no_export(tmp_path, fixture, synced):
    old = ('import argparse\nap = argparse.ArgumentParser(prog="python -m enough.docoes")\n'
           'ap.add_argument("command", choices=["build", "lint", "compile", "inventory", "status"])\nap.parse_args()\n')
    with pytest.raises(SystemExit) as e:
        sync.main(['--enough', str(fake_enough(tmp_path, fixture, old)), '--python', sys.executable])
    assert 'the export failed (exit 2) (this checkout has no DocOES export yet' in str(e.value)
    with pytest.raises(SystemExit) as e:
        sync.main(['--enough', str(tmp_path)])
    assert 'is not an enough checkout' in str(e.value)
    with pytest.raises(SystemExit) as e:
        sync.main(['--enough', str(fake_enough(tmp_path / 'b', fixture))])
    assert '.venv/bin/python does not exist' in str(e.value)
    assert not synced.exists()


@pytest.mark.parametrize('spoil, said', [
    (lambda out: rewrite(out, lambda m: m.update(standalone=True)), 'standalone'),
    (lambda out: rewrite(out, lambda m: m.update(pages={'short': 'short', 'atem': 'atem', 'fabula': 'fabula'})), "not as the hosts' addresses"),
    (lambda out: rewrite(out, lambda m: m['documents'].reverse()), "holds ['comprise-oes', 'ascribe', 'thym', 'macrocosm-oes']"),
    (lambda out: (out / 'thym' / 'short.html').write_text('<article></article>'), 'thym: short differs from the manifest'),
    (lambda out: reseal(out, 'ascribe', 'short', '<article class="docoes"><h1 onclick="x()">A</h1></article>'), 'the site would leave out ascribe'),
    (lambda out: (out / 'docs.css').unlink(), 'no docs.css'),
    (lambda out: shutil.rmtree(out / 'comprise-oes'), 'comprise-oes: short is missing'),
], ids=['standalone', 'pages', 'order', 'hash', 'unsafe', 'no css', 'missing'])
def test_the_sync_checks_the_export_as_the_site_reads_it(fixture, spoil, said):
    slugs = [slug for _, slug, _ in sync.SOURCES]
    assert sync.check(fixture, slugs)['format'] == 'docoes-export/1'
    spoil(fixture)
    with pytest.raises(SystemExit) as e:
        sync.check(fixture, slugs)
    assert said in str(e.value) and 'nothing was changed' in str(e.value)

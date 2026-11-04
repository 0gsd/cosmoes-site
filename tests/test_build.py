"""scripts/build_specs.py: the registry's validation, the build (export, finish, check, install), --check against the
committed export, and that a failure changes nothing. The export is a stand-in here (a fake `enough.docoes` that copies
the fixture); the last test runs the real one when an enough checkout is at hand."""
from __future__ import annotations

import copy
import importlib.util
import json
import os
import re
import shutil
import subprocess
import sys
from pathlib import Path

import pytest

from conftest import DESCRIBES, DOCS, ROOT, make_export, reseal, rewrite, source_text
from cosmoes import specs as specs_mod

_spec = importlib.util.spec_from_file_location('build_specs', ROOT / 'scripts' / 'build_specs.py')
build = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(build)

REGISTRY = json.loads((ROOT / 'specs' / 'specs.json').read_text(encoding='utf-8'))

FAKE_DOCOES = '''"""A stand-in for enough's DocOES export: copies one document of the fixture into the out-dir and merges its
manifest, as `python -m enough.docoes export <doc> <out-dir> --sources ROOT --slug S --name N --version V --no-marks
[--reference] --page …` does, with the source's sha256 from the file under the sources root."""
import hashlib, json, shutil, sys
from pathlib import Path

FIXTURE = Path({fixture!r})
argv = sys.argv[1:]
if argv[:1] != ['export']:
    sys.exit("usage: python -m enough.docoes export <doc> <out-dir>")
doc, out, rest = argv[1], Path(argv[2]), argv[3:]
opt = lambda k: rest[rest.index(k) + 1] if k in rest else None
root = Path(opt('--sources') or '.')
if not (root / doc).is_file():
    print('no document ' + doc, file=sys.stderr)
    sys.exit(2)
slug = opt('--slug') or Path(doc).stem.lower()
pages = {{}}
for i, a in enumerate(rest):
    if a == '--page':
        k, v = rest[i + 1].split('=', 1)
        pages[k] = v
src = json.loads((FIXTURE / 'manifest.json').read_text())
entry = next((d for d in src['documents'] if d['slug'] == slug), None)
if entry is None:
    print('the fixture has no ' + slug, file=sys.stderr)
    sys.exit(2)
for k in ('edition', 'describes', 'host', 'revised', 'raw'):          # enough writes none of these
    entry.pop(k, None)
entry['files'].pop('source', None)
entry['name'] = opt('--name') or entry['name']
entry['version'] = opt('--version') or ''
entry['source'] = {{'path': doc, 'sha256': hashlib.sha256((root / doc).read_bytes()).hexdigest()}}
entry['fake_argv'] = [a for a in rest if a.startswith('--') and a not in ('--page', '--sources', '--slug', '--name', '--version')]
(out / slug).mkdir(parents=True, exist_ok=True)
for dens in ('short', 'atem', 'fabula'):
    shutil.copyfile(FIXTURE / slug / (dens + '.html'), out / slug / (dens + '.html'))
shutil.copyfile(FIXTURE / 'docs.css', out / 'docs.css')
mp = out / 'manifest.json'
m = json.loads(mp.read_text()) if mp.exists() else dict(src, documents=[])
m['pages'] = pages
m['documents'] = [d for d in m['documents'] if d['slug'] != slug] + [entry]
mp.write_text(json.dumps(m))
'''


def registry_like(slugs=tuple(DOCS)) -> list[dict]:
    """A registry of the fixture's documents, as specs/specs.json is written."""
    out = []
    for slug in slugs:
        name, edition, lead, host = DOCS[slug]
        e = {'slug': slug, 'file': f'{slug}.md', 'name': name, 'edition': edition, 'describes': dict(DESCRIBES[slug]),
             'host': host, 'revised': '2026-11-03'}
        if slug == 'macrocosm-oes':
            e['reference'] = True
        out.append(e)
    return out


@pytest.fixture
def fixture(tmp_path):
    return make_export(tmp_path / 'fixture')


@pytest.fixture
def repo(tmp_path, fixture, monkeypatch):
    """A stand-in for this repository: specs/ with the fixture's five texts and a registry, an empty site/, the module
    pointed at them. Returns (specs dir, dest)."""
    specs_dir, dest = tmp_path / 'repo' / 'specs', tmp_path / 'repo' / 'site' / 'specs'
    specs_dir.mkdir(parents=True)
    for slug in DOCS:
        (specs_dir / f'{slug}.md').write_text(source_text(slug, DOCS[slug][0]), encoding='utf-8')
    (specs_dir / 'specs.json').write_text(json.dumps(registry_like(), indent=2), encoding='utf-8')
    monkeypatch.setattr(build, 'SPECS', specs_dir)
    monkeypatch.setattr(build, 'REGISTRY', specs_dir / 'specs.json')
    monkeypatch.setattr(build, 'DEST', dest)
    return specs_dir, dest


def fake_enough(tmp_path, fixture, docoes: str = FAKE_DOCOES):
    root = tmp_path / 'enough-checkout'
    (root / 'enough').mkdir(parents=True)
    (root / 'enough' / '__init__.py').write_text('')
    (root / 'enough' / 'docoes.py').write_text(docoes.format(fixture=str(fixture)))
    (root / build.MANIFESTS_DIR).mkdir(parents=True)
    (root / build.MANIFESTS_DIR / 'thym.manifest.cosm').write_text('oes: cosm/1\n')
    return root


def run(tmp_path, fixture, *extra) -> int:
    return build.main(['--enough', str(fake_enough(tmp_path, fixture)), '--python', sys.executable, *extra])


# ----------------------------------------------------------------------------- the registry

def test_the_shipped_registry_is_valid():
    assert build.problems(REGISTRY) == []
    assert [e['slug'] for e in REGISTRY] == ['oes', 'macrocosm-oes', 'thym', 'ascribe', 'comprise-oes']
    assert {e['host'] for e in REGISTRY} == {'cosmoes.org', 'macro.cosmoes.org', 'thym.cosmoes.org', 'ascribe.cosmoes.org', 'comprise.cosmoes.org'}
    assert [e.get('reference') for e in REGISTRY] == [None, True, None, None, None]
    for e in REGISTRY:
        assert not re.search(r'\d', e['name']) and (ROOT / 'specs' / e['file']).is_file()
    assert build.registry(ROOT / 'specs' / 'specs.json', ROOT / 'specs') == REGISTRY


@pytest.mark.parametrize('spoil, said', [
    (lambda r: r[0].pop('host'), 'missing host'),
    (lambda r: r[0].update(colour='blue'), 'unknown colour'),
    (lambda r: r[1].update(name='Thym 0'), 'carries a number'),
    (lambda r: r[1].update(edition='v1'), 'edition must be a dotted number'),
    (lambda r: r[1].update(edition=1), 'edition must be a dotted number'),
    (lambda r: r[2].update(describes={'Thym': '1'}), 'describes must map'),
    (lambda r: r[2].update(describes='thym/1'), 'describes must map'),
    (lambda r: r[2].update(host='thym.example.org'), 'host must be cosmoes.org or one label'),
    (lambda r: r[2].update(host='a.b.cosmoes.org'), 'host must be cosmoes.org or one label'),
    (lambda r: r[2].update(host='www.cosmoes.org'), 'is a redirect host'),
    (lambda r: r[3].update(host='thym.cosmoes.org'), "host 'thym.cosmoes.org' is used twice"),
    (lambda r: r[3].update(slug='thym'), "slug 'thym' is used twice"),
    (lambda r: r[3].update(slug='Ascribe'), 'slug must be a-z'),
    (lambda r: r[3].update(file='../ascribe.md'), 'file must be a name'),
    (lambda r: r[3].update(file='nope.md'), 'specs/nope.md does not exist'),
    (lambda r: r[4].update(revised='3 Nov 2026'), 'revised must be a date'),
    (lambda r: r[4].update(revised='2026-13-03'), 'revised must be a date'),
    (lambda r: r[4].update(reference='yes'), 'reference must be true or false'),
    (lambda r: r.append('thym'), 'entry 6: not an object'),
], ids=['missing', 'unknown', 'number in name', 'edition', 'edition type', 'describes key', 'describes type', 'foreign host',
        'two labels', 'redirect host', 'host twice', 'slug twice', 'slug', 'file path', 'file absent', 'date text', 'date value',
        'reference', 'not an object'])
def test_the_registry_refuses(spoil, said):
    reg = copy.deepcopy(REGISTRY)
    spoil(reg)
    faults = build.problems(reg, ROOT / 'specs')
    assert faults and any(said in f for f in faults), faults
    assert build.problems([], ROOT / 'specs') == ['the registry is not a non-empty list of entries']
    assert build.problems({'slug': 'x'}, ROOT / 'specs') == ['the registry is not a non-empty list of entries']


def test_a_faulty_registry_stops_the_build_before_anything_runs(tmp_path, fixture, repo):
    specs_dir, dest = repo
    reg = registry_like()
    reg[1]['name'] = 'MacroCOSM OES 0.0.2'
    (specs_dir / 'specs.json').write_text(json.dumps(reg), encoding='utf-8')
    with pytest.raises(SystemExit) as e:
        run(tmp_path, fixture)
    assert 'carries a number' in str(e.value) and 'nothing was changed' in str(e.value)
    assert not dest.exists()


# ----------------------------------------------------------------------------- the build

def test_the_build_script_says_how_to_use_it():
    r = subprocess.run([sys.executable, str(ROOT / 'scripts' / 'build_specs.py'), '--help'], capture_output=True, text=True, timeout=60)
    assert r.returncode == 0 and '--enough' in r.stdout and '--python' in r.stdout and '--check' in r.stdout
    r = subprocess.run([sys.executable, str(ROOT / 'scripts' / 'build_specs.py')], capture_output=True, text=True, timeout=60)
    assert r.returncode == 2 and '--enough' in r.stderr
    assert not (ROOT / 'scripts' / 'sync_specs.py').exists()                  # replaced


def test_the_build_exports_finishes_checks_and_replaces_the_folder(tmp_path, fixture, repo, capsys):
    specs_dir, dest = repo
    (dest / 'old').mkdir(parents=True)
    (dest / 'old' / 'short.html').write_text('a document no longer exported')
    assert run(tmp_path, fixture) == 0
    out = capsys.readouterr().out
    assert re.search(r'^oes\s+OES\s+edition 1\s+cosmoes\.org\s+[\d,]+ bytes$', out, re.M), out
    assert re.search(r'^macrocosm-oes\s+MacroCOSM OES\s+edition 0\.0\.2\s+macro\.cosmoes\.org\s+[\d,]+ bytes$', out, re.M), out
    assert re.search(r'^built at [0-9a-f]{4,40}( with uncommitted changes)? by enough/0\.5\.1; wrote ', out, re.M), out
    files = sorted(p.relative_to(dest).as_posix() for p in dest.rglob('*') if p.is_file())
    assert files == sorted(['docs.css', 'manifest.json'] + [f'{s}/{f}' for s in DOCS for f in ('atem.html', 'fabula.html', 'short.html', 'source.md')])
    assert sorted(p.name for p in dest.parent.iterdir()) == ['specs']           # nothing left beside it
    m = json.loads((dest / 'manifest.json').read_text(encoding='utf-8'))
    assert [d['slug'] for d in m['documents']] == list(DOCS)                     # the registry's order
    assert specs_mod.COMMIT_RE.match(m['source']['commit']) and isinstance(m['source']['dirty'], bool)
    assert m['by'] == 'enough/0.5.1' and m['pages'] == build.PAGES
    for d in m['documents']:
        name, edition, lead, host = DOCS[d['slug']]
        assert (d['name'], d['version'], d['edition'], d['host'], d['revised']) == (name, edition, edition, host, '2026-11-03')
        assert d['describes'] == DESCRIBES[d['slug']] and d['raw'] == specs_mod.RAW
        assert d['source']['path'] == f'specs/{d["slug"]}.md'
        src = d['files']['source']
        assert src['path'] == f'{d["slug"]}/source.md' and src['sha256'] == d['source']['sha256']
        assert (dest / src['path']).read_bytes() == (specs_dir / f'{d["slug"]}.md').read_bytes()
        assert '--no-marks' in d['fake_argv']
        assert ('--reference' in d['fake_argv']) is (d['slug'] == 'macrocosm-oes')
    specs = specs_mod.Specs(dest)
    assert [d['slug'] for d in specs.documents] == list(DOCS)
    assert specs.source('thym') == source_text('thym', 'Thym')


def test_check_passes_on_a_fresh_build_and_fails_on_a_difference(tmp_path, fixture, repo, capsys):
    specs_dir, dest = repo
    assert run(tmp_path, fixture) == 0
    assert run(tmp_path / 'b', fixture, '--check') == 0
    assert 'is in step with specs/ (5 documents)' in capsys.readouterr().out
    # another exported time and commit: still in step
    rewrite(dest, lambda m: m.update(exported='2030-01-01T00:00:00Z', source={'commit': 'abcdef0', 'dirty': False}))
    assert run(tmp_path / 'c', fixture, '--check') == 0
    # a text edited without a rebuild: the fresh build differs
    (specs_dir / 'thym.md').write_text('# Thym\n\nedited\n', encoding='utf-8')
    assert run(tmp_path / 'd', fixture, '--check') == 1
    err = capsys.readouterr().err
    assert 'is not in step with specs/' in err and 'thym/source.md differs' in err and 'manifest.json differs' in err
    assert 'run scripts/build_specs.py' in err
    assert (dest / 'thym' / 'source.md').read_text() == source_text('thym', 'Thym')      # --check never writes
    # a fragment edited in place, resealed: a difference too; a file only one side has as well
    assert run(tmp_path / 'e', fixture) == 0
    reseal(dest, 'ascribe', 'atem', '<article class="docoes docoes-atem"><h1>A</h1></article>')
    (dest / 'extra.txt').write_text('x')
    assert run(tmp_path / 'f', fixture, '--check') == 1
    err = capsys.readouterr().err
    assert 'ascribe/atem.html differs' in err and 'only in' in err and 'extra.txt' in err


def test_the_build_changes_nothing_when_an_export_fails(tmp_path, fixture, repo):
    specs_dir, dest = repo
    dest.mkdir(parents=True)
    (dest / 'manifest.json').write_text('{"kept": true}')
    reg = registry_like()
    reg[2].update(slug='nope', file='nope.md', host='nope.cosmoes.org')
    (specs_dir / 'nope.md').write_text('# Nope\n')
    (specs_dir / 'specs.json').write_text(json.dumps(reg), encoding='utf-8')
    with pytest.raises(SystemExit) as e:
        run(tmp_path, fixture)
    assert str(e.value) == 'nope: the export failed (exit 2); nothing was changed'       # the fake has no such document
    assert (dest / 'manifest.json').read_text() == '{"kept": true}'


def test_the_build_says_so_when_the_checkout_cannot_export(tmp_path, fixture, repo):
    specs_dir, dest = repo
    old = ('import argparse\nap = argparse.ArgumentParser(prog="python -m enough.docoes")\n'
           'ap.add_argument("command", choices=["build", "lint", "compile", "inventory", "status"])\nap.parse_args()\n')
    with pytest.raises(SystemExit) as e:
        build.main(['--enough', str(fake_enough(tmp_path, fixture, old)), '--python', sys.executable])
    assert 'the export failed (exit 2) (this checkout has no DocOES export yet' in str(e.value)
    older = ('import argparse, sys\nprint("python -m enough.docoes export: error: unrecognized arguments: --no-marks", file=sys.stderr)\nsys.exit(2)\n')
    with pytest.raises(SystemExit) as e:
        build.main(['--enough', str(fake_enough(tmp_path / 'b', fixture, older)), '--python', sys.executable])
    assert "older than enough 0.5.1's" in str(e.value)
    with pytest.raises(SystemExit) as e:
        build.main(['--enough', str(tmp_path)])
    assert 'is not an enough checkout' in str(e.value)
    with pytest.raises(SystemExit) as e:
        build.main(['--enough', str(fake_enough(tmp_path / 'c', fixture))])
    assert '.venv/bin/python does not exist' in str(e.value)
    shutil.rmtree(fake_enough(tmp_path / 'd', fixture) / 'defaults')
    with pytest.raises(SystemExit) as e:
        build.main(['--enough', str(tmp_path / 'd' / 'enough-checkout'), '--python', sys.executable])
    assert 'has no defaults/cosm/manifests/' in str(e.value)
    assert not dest.exists()


def test_finish_refuses_an_export_that_is_not_of_these_texts(tmp_path, fixture, repo):
    specs_dir, dest = repo
    entries = registry_like()
    out = tmp_path / 'out'
    shutil.copytree(fixture, out)
    rewrite(out, lambda m: m['documents'][2]['source'].update(sha256='0' * 64))
    with pytest.raises(SystemExit) as e:
        build.finish(out, entries, specs_dir, ROOT)
    assert 'thym: the export was not built from specs/thym.md (sha256 differs)' in str(e.value)
    shutil.rmtree(out)
    shutil.copytree(fixture, out)
    rewrite(out, lambda m: m['documents'][2].update(name='Thym 0'))
    with pytest.raises(SystemExit) as e:
        build.finish(out, entries, specs_dir, ROOT)
    assert "thym: the export says 'Thym 0' v0, the registry 'Thym' edition 0" in str(e.value)
    assert not dest.exists()


@pytest.mark.parametrize('spoil, said', [
    (lambda out: rewrite(out, lambda m: m.update(standalone=True)), 'standalone'),
    (lambda out: rewrite(out, lambda m: m.update(pages={'short': 'short', 'atem': 'atem', 'fabula': 'fabula'})), "not as the hosts' addresses"),
    (lambda out: rewrite(out, lambda m: m['documents'].reverse()), "the export holds ['comprise-oes', 'ascribe', 'thym', 'macrocosm-oes', 'oes']"),
    (lambda out: rewrite(out, lambda m: m['documents'][2].update(edition='9')), "thym: edition is '9' in the export, '0' in the registry"),
    (lambda out: rewrite(out, lambda m: m['documents'][2].update(raw={})), 'thym: the raw endpoints are not declared'),
    (lambda out: (out / 'thym' / 'short.html').write_text('<article></article>'), 'thym: short differs from the manifest'),
    (lambda out: (out / 'thym' / 'source.md').write_text('# edited'), 'thym: source differs from the manifest'),
    (lambda out: reseal(out, 'thym', 'source', '# another text'), 'thym: the source copy is not the text the export was built from'),
    (lambda out: reseal(out, 'ascribe', 'short', '<article class="docoes"><h1 onclick="x()">A</h1></article>'), 'the site would leave out ascribe'),
    (lambda out: (out / 'docs.css').unlink(), 'no docs.css'),
    (lambda out: shutil.rmtree(out / 'comprise-oes'), 'comprise-oes: short is missing'),
], ids=['standalone', 'pages', 'order', 'edition', 'raw', 'hash', 'source hash', 'source text', 'unsafe', 'no css', 'missing'])
def test_the_build_checks_the_export_as_the_site_reads_it(fixture, spoil, said):
    entries = registry_like()
    assert build.check(fixture, entries)['format'] == 'docoes-export/1'
    spoil(fixture)
    with pytest.raises(SystemExit) as e:
        build.check(fixture, entries)
    assert said in str(e.value) and 'nothing was changed' in str(e.value)


# ----------------------------------------------------------------------------- the real thing

ENOUGH = Path(os.environ.get('COSMOES_ENOUGH') or Path.home() / 'METMcloud' / 'METMroot' / 'enough-dev')


@pytest.mark.skipif(not (ENOUGH / '.venv' / 'bin' / 'python').exists() or not (specs_mod.FOLDER / 'manifest.json').exists(),
                    reason='needs an enough checkout with its .venv (COSMOES_ENOUGH or ~/METMcloud/METMroot/enough-dev) and a built site/specs/')
def test_the_committed_export_is_in_step_with_the_texts(capsys):
    """`--check` on the real export with the real enough: the committed site/specs/ is what specs/ builds to."""
    assert build.main(['--enough', str(ENOUGH), '--check']) == 0
    assert 'is in step with specs/ (5 documents)' in capsys.readouterr().out

"""scripts/fetch_library.py, without a network: its entries, the dry run, and a run from an archive on disk (made
up here) through every question, with what it writes and what it refuses. Downloading is the owner's run alone: every
test here fails if anything reaches for the network."""
from __future__ import annotations

import datetime
import io
import json
import shutil
import sys
import tarfile
import urllib.request
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / 'scripts'))
import fetch_library as F  # noqa: E402

L = F.L
NOW = datetime.datetime(2026, 11, 18, 12, 0, tzinfo=datetime.timezone.utc)
LICENCE = 'The Made-up Licence\n\nAnyone may copy this made-up text.\n'


@pytest.fixture(autouse=True)
def no_network(monkeypatch):
    def refuse(*a, **k):
        raise AssertionError('the tests never download')
    monkeypatch.setattr(urllib.request, 'urlopen', refuse)


@pytest.fixture
def library(tmp_path) -> Path:
    lib = tmp_path / 'library'
    lib.mkdir()
    (lib / 'library.json').write_text(json.dumps({
        'format': L.FORMAT, 'shelves': [{'slug': 'made', 'title': 'Made', 'kind': 'language'}], 'texts': []}))
    return lib


def archive(tmp_path: Path, files: dict, extra=None) -> Path:
    p = tmp_path / 'made-1-docs-text.tar.gz'
    with tarfile.open(p, 'w:gz') as t:
        for name, text in files.items():
            data = text.encode()
            info = tarfile.TarInfo(f'made-1-docs-text/{name}')
            info.size = len(data)
            t.addfile(info, io.BytesIO(data))
        for info in extra or ():
            t.addfile(info)
    return p


def entry(**kw) -> F.Entry:
    base = dict(shelf='made', text='docs', version='1', name='The Made-up Docs', publisher='The Made-up Society',
                what='text', form='text', lane='open', url='https://example.invalid/made-1-docs-text.tar.gz',
                url_status=F.READ, publisher_page='https://example.invalid/made/1/',
                licence_name='The Made-up Licence', licence_url='https://example.invalid/licence',
                read_whole=(('https://example.invalid/licence', F.READ),), licence_files=('license.txt',),
                copyright=('paragraphs', 'copyright.txt', 'Copyright'))
    base.update(kw)
    return F.Entry(**base)


FILES = {'index.txt': 'Made\n****\n\nlen(s)\n\n   The length.\n', 'license.txt': LICENCE,
         'copyright.txt': 'Copyright\n*********\n\nCopyright © 2026 The Made-up Society.\n\nMore words.\n'}


class Owner:
    """Answers every question: yes, unless told otherwise for a question that contains `no_to`."""

    def __init__(self, no_to: str = '', typed=()):
        self.asked, self.no_to, self.typed = [], no_to, list(typed)

    def __call__(self, q):
        self.asked.append(q)
        if q == '':
            return self.typed.pop(0) if self.typed else '.'
        return 'no' if self.no_to and self.no_to in q else 'yes'


# ----------------------------------------------------------------------------- the entries

def test_every_entry_names_its_address_its_licence_and_how_sure_it_is():
    shelves = {s['slug'] for s in L.load_registry(ROOT / 'library')['shelves']}
    keys = [e.key for e in F.ENTRIES]
    assert len(keys) == len(set(keys))
    assert set(keys) >= {'python/docs/3.13', 'python/docs/3.15', 'ecmascript/ecma-262/17.0', 'go/spec/1.27',
                         'rust/reference/1.100', 'rust/reference/1.97', 'rust/fls/1.99', 'rust/fls/1.97',
                         'json/rfc/8259', 'unicode/ucd/15.1.0'}
    assert any(k.startswith('python/docs/') and k != 'python/docs/3.13' for k in keys)   # and the current release
    for e in F.ENTRIES:
        assert e.shelf in shelves and e.form in L.FORMS and e.lane in L.LANES and e.what in L.WHAT, e.key
        assert e.url.startswith('https://') and e.publisher_page.startswith('https://'), e.key
        assert e.licence_url.startswith('https://') and e.read_whole, e.key
        assert e.url_status in (F.READ, F.PATTERN, F.SUPPLY), e.key
        if e.url_status != F.READ:                    # an address not read is marked for the owner, never a fact
            assert any(n.startswith('OWNER:') for n in e.notes) or e.url_status == F.PATTERN, e.key
        if e.url_status == F.SUPPLY:
            assert '<' in e.url, e.key
        assert e.licence_files or e.copyright, e.key
    assert F.BY_KEY['json/rfc/8259'].form == 'unchanged' and F.BY_KEY['json/rfc/8259'].lane == 'bound'
    assert len(F.BY_KEY['go/spec/1.27'].sha256) == 64                        # the publisher lists it; the run checks it
    for k in ('rust/reference/1.100', 'rust/reference/1.97', 'rust/fls/1.99', 'rust/fls/1.97'):
        assert '<' not in F.BY_KEY[k].url and F.BY_KEY[k].url.endswith('.tar.gz'), k   # a commit, no placeholder
    assert F.BY_KEY['rust/fls/1.99'].copyright[0] == 'spdx'                 # LICENSES/MIT.txt is the blank template
    assert any('*' in f for f in F.BY_KEY['rust/fls/1.99'].licence_files)
    assert F.BY_KEY['ecmascript/ecma-262/17.0'].credit and F.BY_KEY['unicode/ucd/15.1.0'].credit


def test_the_lean_shelf_is_pins_only():
    reg = L.load_registry(ROOT / 'library')
    assert any(s['slug'] == 'lean' and s['kind'] == 'language' for s in reg['shelves'])
    lean = [t for t in reg['texts'] if t['shelf'] == 'lean']
    assert {t['text'] for t in lean} == {'lean4', 'mathlib'}
    for t in lean:
        assert t['aboard'] is False and t['licence']['name'] == 'Apache License 2.0' and t['release'], t['text']
    assert not any(e.shelf == 'lean' for e in F.ENTRIES)                      # nothing of it is ever fetched


def test_the_dry_run_fetches_and_writes_nothing(library, capsys):
    before = sorted(p.as_posix() for p in library.rglob('*'))
    assert F.main(['fetch', 'go/spec/1.27', '--dry-run', '--library', str(library)]) == 0
    out = capsys.readouterr().out
    assert 'https://go.dev/dl/go1.27.4.src.tar.gz' in out and 'dry run' in out and '[pattern' not in out
    assert 'expects       sha256 73cfb857' in out and 'carries       The Go Programming Language Specification' in out
    assert 'must find     files/LICENSE' in out and 'read whole    https://go.dev/copyright' in out
    assert sorted(p.as_posix() for p in library.rglob('*')) == before
    assert F.main(['list']) == 0
    assert F.main(['fetch', 'rust/fls/1.99', '--dry-run', '--library', str(library)]) == 0
    out = capsys.readouterr().out
    assert '[pattern' in out and 'must find     files/LICENSES/*' in out and 'by rule spdx' in out
    assert sorted(p.as_posix() for p in library.rglob('*')) == before


def test_a_placeholder_address_needs_the_owners_url(library):
    e = entry(url='https://example.invalid/archive/<COMMIT>.tar.gz', url_status=F.SUPPLY)
    with pytest.raises(F.Stop, match='pass --url'):
        F.fetch(e, library, ask=Owner(), say=lambda *a: None)


# ----------------------------------------------------------------------------- a run

def test_a_run_writes_the_folder_its_notice_and_its_entry(library, tmp_path):
    owner = Owner()
    said = []
    target = F.fetch(entry(), library, from_archive=archive(tmp_path, FILES), ask=owner, say=said.append, now=NOW)
    assert target == library / 'made' / 'docs' / '1'
    assert sorted(p.relative_to(target).as_posix() for p in target.rglob('*') if p.is_file()) == [
        'FETCHED', 'NOTICE', 'SHA256SUMS', 'files/copyright.txt', 'files/index.txt', 'files/license.txt']
    # every question was asked: the licence read whole, the licence file shown whole, the notice
    assert any('Have you read https://example.invalid/licence whole?' in q for q in owner.asked)
    assert any('Is files/license.txt the licence you read?' in q for q in owner.asked)
    assert LICENCE.strip().split('\n')[-1] in '\n'.join(map(str, said))
    fetched = (target / 'FETCHED').read_text()
    assert 'fetched: 2026-11-18T12:00:00Z' in fetched and 'from: https://example.invalid/made-1-docs-text.tar.gz' in fetched
    assert 'archive-sha256: ' in fetched and 'stripped: made-1-docs-text/' in fetched
    notice = (target / 'NOTICE').read_text()
    assert "not the publisher's own page" in notice and L.FORMS['text']['changed'] in notice
    assert 'Copyright © 2026 The Made-up Society.' in notice and LICENCE.strip() in notice
    reg = L.load_registry(library)
    (e,) = reg['texts']
    assert e['aboard'] is True and e['copyright'] == 'Copyright © 2026 The Made-up Society.'
    assert e['digest'] == L.folder_digest(target) and e['files'] == 3
    assert L.verify(target, e) == [] and L.validate_registry(reg) == []
    assert not list(library.glob('.fetch-*'))


def test_it_never_writes_over_a_version(library, tmp_path):
    a = archive(tmp_path, FILES)
    F.fetch(entry(), library, from_archive=a, ask=Owner(), say=lambda *x: None, now=NOW)
    with pytest.raises(F.Stop, match='exists'):
        F.fetch(entry(), library, from_archive=a, ask=Owner(), say=lambda *x: None, now=NOW)
    F.fetch(entry(version='2'), library, from_archive=a, ask=Owner(), say=lambda *x: None, now=NOW)   # beside it
    assert sorted(p.name for p in (library / 'made' / 'docs').iterdir()) == ['1', '2']


@pytest.mark.parametrize('no_to', ['Have you read', 'the licence you read', "publisher's own address"])
def test_anything_but_yes_writes_nothing(library, tmp_path, no_to):
    e = entry(url_status=F.PATTERN)
    with pytest.raises(F.Stop):
        F.fetch(e, library, from_archive=archive(tmp_path, FILES), ask=Owner(no_to=no_to), say=lambda *x: None, now=NOW)
    assert not (library / 'made').exists() and not list(library.glob('.fetch-*'))
    assert L.load_registry(library)['texts'] == []


def test_a_missing_licence_file_stops_the_run(library, tmp_path):
    files = {k: v for k, v in FILES.items() if k != 'license.txt'}
    with pytest.raises(F.Stop, match='files/license.txt is not in what was fetched'):
        F.fetch(entry(), library, from_archive=archive(tmp_path, files), ask=Owner(), say=lambda *x: None, now=NOW)
    assert not (library / 'made').exists()


def test_a_wrong_digest_stops_the_run(library, tmp_path):
    with pytest.raises(F.Stop, match='sha256'):
        F.fetch(entry(), library, sha='0' * 64, from_archive=archive(tmp_path, FILES), ask=Owner(),
                say=lambda *x: None, now=NOW)


def test_when_no_rule_finds_the_notice_the_owner_types_it(library, tmp_path):
    owner = Owner(typed=['Copyright 2026 Typed Owner Words.', '.'])
    target = F.fetch(entry(copyright=('paragraphs', 'copyright.txt', 'Nothing')), library,
                     from_archive=archive(tmp_path, FILES), ask=owner, say=lambda *x: None, now=NOW)
    assert 'Copyright 2026 Typed Owner Words.' in (target / 'NOTICE').read_text()
    with pytest.raises(F.Stop, match='no copyright notice'):
        F.fetch(entry(version='2', copyright=()), library, from_archive=archive(tmp_path, FILES),
                ask=Owner(typed=['.']), say=lambda *x: None, now=NOW)


def test_links_and_paths_outside_are_left_out_and_named(library, tmp_path):
    link = tarfile.TarInfo('made-1-docs-text/link.txt')
    link.type, link.linkname = tarfile.SYMTYPE, '/etc/passwd'
    up = tarfile.TarInfo('made-1-docs-text/../../escape.txt')
    target = F.fetch(entry(), library, from_archive=archive(tmp_path, FILES, extra=[link, up]), ask=Owner(),
                     say=lambda *x: None, now=NOW)
    assert not (target / 'files' / 'link.txt').exists() and not (tmp_path / 'escape.txt').exists()
    assert 'left out' in (target / 'FETCHED').read_text() and 'link.txt' in (target / 'FETCHED').read_text()


def test_members_keep_only_what_the_entry_names(library, tmp_path):
    files = dict(FILES, **{'src/big.c': 'int main;\n', 'doc/spec.html': '<h1 id="x">Spec</h1>'})
    target = F.fetch(entry(form='html', members=('doc/spec.html', 'license.txt', 'copyright.txt')), library,
                     from_archive=archive(tmp_path, files), ask=Owner(), say=lambda *x: None, now=NOW)
    assert sorted(p.relative_to(target / 'files').as_posix() for p in (target / 'files').rglob('*') if p.is_file()) == \
        ['copyright.txt', 'doc/spec.html', 'license.txt']
    assert L.page_files(target, L.load_registry(library)['texts'][0]) == {'doc/spec': 'files/doc/spec.html'}


def test_the_rules_that_find_a_notice(tmp_path):
    files = tmp_path / 'files'
    files.mkdir()
    (files / 'rfc.txt').write_text('RFC 1\n\nCopyright Notice\n\n   Copyright (c) 2026 Someone.\n\n   More.\n\nNext\n')
    (files / 'page.html').write_text('<section id="c"><h2>Copyright</h2><p>Copyright © 2026 Someone.</p></section>'
                                     '<section><h2>Other</h2><p>no</p></section>')
    e = entry(copyright=('section', 'rfc.txt', 'Copyright Notice'))
    assert F.find_copyright(e, files) == '   Copyright (c) 2026 Someone.\n\n   More.'
    e = entry(copyright=('html-id', 'page.html', 'c'))
    assert F.find_copyright(e, files) == 'Copyright © 2026 Someone.'
    assert F.find_copyright(entry(copyright=('section', 'missing.txt', 'x')), files) is None


def test_the_fixture_shelf_is_what_the_script_writes():
    """tests/fixtures/library was written by this script from made-up archives: its folders verify and its NOTICEs
    have the script's shape."""
    fx = ROOT / 'tests' / 'fixtures' / 'library'
    for e in L.load_registry(fx)['texts']:
        if e['aboard']:
            d = L.text_dir(fx, e)
            assert L.verify(d, e) == []
            assert (d / 'NOTICE').read_text().startswith(f"{e['name']} {e['version']}, as kept in the cosmoes.org library")
            assert 'by: the owner, with scripts/fetch_library.py' in (d / 'FETCHED').read_text()


# ----------------------------------------------------------------------------- the 0.9 shelf's shapes

def zip_archive(tmp_path: Path, files: dict, top: str = '') -> Path:
    import zipfile
    p = tmp_path / 'made.zip'
    with zipfile.ZipFile(p, 'w') as z:
        for name, text in files.items():
            z.writestr(top + name, text)
    return p


def test_a_zip_with_no_top_folder_and_a_licence_fetched_beside_it(library, tmp_path, monkeypatch):
    """The UCD's shape: a zip whose files sit at its root, and the licence as a second file from the publisher."""
    got = []
    e = entry(form='data', what='data', archive='zip', licence_files=('license.txt',),
              extras=(('https://example.invalid/license.txt', 'license.txt', F.READ),),
              copyright=('paragraphs', 'license.txt', 'Copyright'),
              credit=('Made-up is a registered mark of Made-up, Inc.',))
    files = {'UnicodeData.txt': '0041;LATIN CAPITAL LETTER A;Lu\n', 'extracted/Derived.txt': '# d\n'}
    with pytest.raises(F.Stop, match='run without --from-archive'):
        F.fetch(e, library, from_archive=zip_archive(tmp_path, files), ask=Owner(), say=lambda *x: None, now=NOW)
    def fake_both(url, dest):
        got.append(url)
        if url.endswith('.zip'):
            dest.write_bytes(zip_archive(tmp_path, files).read_bytes())
        else:
            dest.write_text('Copyright © 1991-2026 Made-up, Inc.\n\nPermission is granted.\n')
    monkeypatch.setattr(F, 'download', fake_both)
    target = F.fetch(e, library, url='https://example.invalid/made.zip', ask=Owner(), say=lambda *x: None, now=NOW)
    assert got == ['https://example.invalid/made.zip', 'https://example.invalid/license.txt']
    kept = sorted(p.relative_to(target / 'files').as_posix() for p in (target / 'files').rglob('*') if p.is_file())
    assert kept == ['UnicodeData.txt', 'extracted/Derived.txt', 'license.txt']       # nothing stripped
    assert 'stripped' not in (target / 'FETCHED').read_text()
    assert 'extra: files/license.txt from https://example.invalid/license.txt' in (target / 'FETCHED').read_text()
    notice = (target / 'NOTICE').read_text()
    assert 'What the terms ask every copy to carry' in notice and 'Made-up is a registered mark' in notice
    (reg_e,) = L.load_registry(library)['texts']
    assert reg_e['copyright'] == 'Copyright © 1991-2026 Made-up, Inc.'
    assert reg_e['credit'] == 'Made-up is a registered mark of Made-up, Inc.'
    assert L.verify(target, reg_e) == []


def test_licences_in_a_folder_and_a_notice_from_spdx_lines(library, tmp_path):
    """The FLS's shape: its licences in LICENSES/ (MIT.txt the blank template), its holders in SPDX headers."""
    files = {
        'LICENSES/MIT.txt': 'MIT License\n\nCopyright (c) <year> <copyright holders>\n',
        'LICENSES/Apache-2.0.txt': 'Apache License\nVersion 2.0\n',
        'LICENSES/CC-BY-4.0.txt': 'Attribution 4.0 International\n',
        'src/index.rst': '.. SPDX-License-Identifier: MIT OR Apache-2.0\n   SPDX-FileCopyrightText: The Made-up '
                         'Developers\n   SPDX-FileCopyrightText: The Made-up Project Contributors\n\nMade\n====\n',
        'src/two.rst': '.. SPDX-FileCopyrightText: The Made-up Developers\n\nTwo\n===\n',
        'version.rst': '.. SPDX-FileCopyrightText: The Made-up Project Developers\n',
    }
    e = entry(form='rst', pages='src/', licence_files=('LICENSES/Apache-2.0.txt', 'LICENSES/MIT.txt', 'LICENSES/*'),
              copyright=('spdx', 'src', 'SPDX-FileCopyrightText'))
    owner = Owner()
    target = F.fetch(e, library, from_archive=archive(tmp_path, files), ask=owner, say=lambda *x: None, now=NOW)
    asked = [q for q in owner.asked if 'the licence you read' in q]
    assert asked == ['Is files/LICENSES/Apache-2.0.txt the licence you read? Type yes to go on: ',
                     'Is files/LICENSES/MIT.txt the licence you read? Type yes to go on: ',
                     'Is files/LICENSES/CC-BY-4.0.txt the licence you read? Type yes to go on: ']   # each once
    (reg_e,) = L.load_registry(library)['texts']
    assert reg_e['copyright'] == ('SPDX-FileCopyrightText: The Made-up Developers\n'
                                  'SPDX-FileCopyrightText: The Made-up Project Contributors')   # src/ only, each once
    assert L.page_files(target, reg_e) == {'index': 'files/src/index.rst', 'two': 'files/src/two.rst'}
    with pytest.raises(F.Stop, match='no file matches files/COPYING'):
        F.fetch(entry(version='2', licence_files=('COPYING*',)), library, from_archive=archive(tmp_path, FILES),
                ask=Owner(), say=lambda *x: None, now=NOW)


def test_members_are_chosen_before_anything_is_read(library, tmp_path, monkeypatch):
    """The Go shape: a large source archive of which three files are kept; the others are never read."""
    files = dict(FILES, **{'src/huge.go': 'package main\n' * 1000, 'doc/go_spec.html': '<h1 id="s">Spec</h1>'})
    read = []
    real = tarfile.TarFile.extractfile
    def spy(self, member):
        read.append(member.name if hasattr(member, 'name') else member)
        return real(self, member)
    monkeypatch.setattr(tarfile.TarFile, 'extractfile', spy)
    F.fetch(entry(form='html', members=('doc/go_spec.html', 'license.txt', 'copyright.txt')), library,
            from_archive=archive(tmp_path, files), ask=Owner(), say=lambda *x: None, now=NOW)
    assert not any('huge.go' in r for r in read) and any('go_spec.html' in r for r in read)

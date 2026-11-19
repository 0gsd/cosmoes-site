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
    assert set(keys) >= {'python/docs/3.13', 'ecmascript/ecma-262/17.0', 'go/spec/1.27', 'rust/reference/1.97',
                         'rust/fls/1.97', 'json/rfc/8259', 'unicode/ucd/15.1.0'}
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


def test_the_dry_run_fetches_and_writes_nothing(library, capsys):
    before = sorted(p.as_posix() for p in library.rglob('*'))
    assert F.main(['fetch', 'go/spec/1.27', '--dry-run', '--library', str(library)]) == 0
    out = capsys.readouterr().out
    assert 'https://go.dev/dl/go1.27.4.src.tar.gz' in out and '[pattern' in out and 'dry run' in out
    assert 'must find     files/LICENSE' in out and 'read whole    https://go.dev/copyright' in out
    assert sorted(p.as_posix() for p in library.rglob('*')) == before
    assert F.main(['list']) == 0


def test_a_placeholder_address_needs_the_owners_url(library):
    with pytest.raises(F.Stop, match='pass --url'):
        F.fetch(F.BY_KEY['rust/reference/1.97'], library, ask=Owner(), say=lambda *a: None)


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

"""The library on the apex host: the shelves, a shelf, a text's contents with its notice, every page with the notice
(the licence, the copyright notice, the change in form, the plain line that it is a copy kept here), the raw route
byte for byte, the files of ours, and what is refused. Against the made-up shelf in tests/fixtures/library/."""
from __future__ import annotations

import re
import shutil
from pathlib import Path

import pytest
from markupsafe import escape

from conftest import Site, anchors_resolve, no_inline_script_or_style
from cosmoes import library as library_mod

FIXTURE = Path(__file__).resolve().parent / 'fixtures' / 'library'
L = library_mod.L
APEX = 'cosmoes.org'
COPY_LINE = "A copy kept at cosmoes.org, not the publisher's own page."
KEPT = [e for e in L.load_registry(FIXTURE)['texts'] if e['aboard']]
PAGES = [(e, p) for e in KEPT for p in sorted(L.page_files(L.text_dir(FIXTURE, e), e))]
FILES = [(e, rel[len('files/'):]) for e in KEPT for rel in L.walk_files(L.text_dir(FIXTURE, e))]


def url(e: dict, rest: str = '') -> str:
    return f"/library/{e['shelf']}/{e['text']}/{e['version']}/{rest}"


@pytest.fixture
def lib(tmp_path) -> Path:
    return Path(shutil.copytree(FIXTURE, tmp_path / 'library'))


@pytest.fixture
def site(export, lib) -> Site:
    return Site(export, library=lib)


def notice_on(html: str, e: dict) -> None:
    assert COPY_LINE in html
    assert f'<a href="{escape(e["licence"]["url"])}">{escape(e["licence"]["name"])}</a>' in html
    assert f'<pre class="lib-copyright">{escape(e["copyright"])}</pre>' in html
    assert f'Changed in form: {escape(L.FORMS[e["form"]]["changed"])}' in html
    for line in (e.get('credit') or '').split('\n') if e.get('credit') else ():   # what the terms ask a copy to carry
        assert f'<p class="lib-credit">{escape(line)}</p>' in html
    assert f'<a href="{e["publisher_page"]}">' in html
    assert f'<a href="{url(e, "NOTICE")}">NOTICE</a>' in html


def page_ok(r) -> str:
    assert r.status_code == 200, r.url
    assert r.headers['cache-control'] == 'public, max-age=300'
    assert r.headers['content-security-policy'].startswith("default-src 'none'")
    html = r.text
    no_inline_script_or_style(html)
    anchors_resolve(html)
    assert "The canonical editions are these pages" not in html           # the specifications' line is not theirs
    return html


# ----------------------------------------------------------------------------- the shelves and a shelf

def test_the_shelves(site):
    html = page_ok(site.get(APEX, '/library/'))
    assert '<h1 id="h">The library</h1>' in html and html.count('<h1') == 1
    assert 'id="shelf-example"' in html and 'id="shelf-memos"' in html
    assert '<a href="/library/example/manual/1.0/">The Example Manual 1.0</a>' in html
    assert 'The Example runner 1: pinned, not kept' in html
    assert site.get(APEX, '/library').headers['location'] == '/library/'


def test_a_shelf_lists_its_kept_texts_and_its_pins(site):
    html = page_ok(site.get(APEX, '/library/example/'))
    assert '<h1 id="h">Example</h1>' in html
    assert '<a href="/library/example/manual/1.0/">The Example Manual</a>' in html
    assert '<a href="/library/example/sheet/2/">The Example Sheet</a>' in html
    assert 'Pinned, not kept' in html and 'The Example runner' in html and 'https://example.invalid/runner' in html
    assert site.get(APEX, '/library/example').status_code == 301
    assert site.get(APEX, '/library/example/manual/').headers['location'] == '/library/example/'
    for missing in ('/library/nowhere/', '/library/nowhere', '/library/example/nothing/', '/library/example/manual/9/',
                    '/library/example/runner/1/'):                       # a pinned text is never served
        assert site.get(APEX, missing).status_code == 404, missing


# ----------------------------------------------------------------------------- a text and its pages

@pytest.mark.parametrize('e', KEPT, ids=[e['text'] for e in KEPT])
def test_a_text_shows_its_notice_its_pages_and_its_files(site, e):
    html = page_ok(site.get(APEX, url(e)))
    notice_on(html, e)
    assert f'{escape(e["name"])} {e["version"]}' in html
    whole = (L.text_dir(FIXTURE, e) / 'NOTICE').read_text()
    assert escape(whole.split('\n', 1)[0]) in html                       # the NOTICE whole, on the page
    for p in L.page_files(L.text_dir(FIXTURE, e), e):
        assert f'<a href="{url(e, p)}">{p}</a>' in html
    for rel in L.walk_files(L.text_dir(FIXTURE, e)):
        assert f'href="{url(e, "raw/" + rel[len("files/"):])}"' in html
    assert site.get(APEX, url(e).rstrip('/')).headers['location'] == url(e)


@pytest.mark.parametrize('e, path', PAGES, ids=[f"{e['text']}:{p}" for e, p in PAGES])
def test_every_page_carries_the_notice(site, e, path):
    html = page_ok(site.get(APEX, url(e, path)))
    notice_on(html, e)
    assert html.count('<h1') == 1
    assert f'<link rel="canonical" href="https://cosmoes.org{url(e, path)}">' in html
    raw = L.page_files(L.text_dir(FIXTURE, e), e)[path][len('files/'):]
    assert f'<a href="{url(e, "raw/" + raw)}">the publisher\'s file, unchanged</a>' in html


def test_a_plain_text_page_by_rule(site):
    e = next(e for e in KEPT if e['text'] == 'manual')
    html = page_ok(site.get(APEX, url(e, 'library/strings')))
    assert '<h1 id="strings">Strings</h1>' in html and '<h2 id="making-strings">Making strings</h2>' in html
    assert '<h2 id="lines">Lines</h2>' in html and '<h2 id="strings--lines">Lines</h2>' in html
    assert '<p class="lib-sig" id="text"><code>class text(value=&#39;&#39;)</code></p>' in html
    assert 'id="text.upper"' in html and 'id="text.count"' in html and 'id="text.tally"' in html
    assert '<pre>+--------+---------+' in html
    assert 'Lines end at a line break &amp; never &lt;here&gt;.' in html   # the publisher's words, escaped
    assert '<title>Strings · The Example Manual 1.0 · cosmoes.org</title>' in html


def test_an_html_page_keeps_no_markup_of_the_publishers(site):
    e = next(e for e in KEPT if e['form'] == 'html')
    html = page_ok(site.get(APEX, url(e, 'sheet')))
    assert '<h1 id="sec-intro">The Example Sheet</h1>' in html
    assert '<p>One short page of made-up text.</p>' in html and '<em>' not in html
    assert 'alert(1)' not in html and 'bad()' not in html and 'color: red' not in html


def test_a_text_passed_on_unchanged_has_no_page_only_its_file(site):
    e = next(e for e in KEPT if e['form'] == 'unchanged')
    html = page_ok(site.get(APEX, url(e)))
    notice_on(html, e)
    assert 'id="lib-contents"' not in html
    assert f'<a href="{url(e, "raw/memo7.txt")}">the publisher\'s file, unchanged</a>' in html
    assert site.get(APEX, url(e, 'memo7')).status_code == 404


# ----------------------------------------------------------------------------- the raw files and ours

@pytest.mark.parametrize('e, path', FILES, ids=[f"{e['text']}:{p}" for e, p in FILES])
def test_the_raw_route_serves_the_publishers_file_byte_for_byte(site, e, path):
    r = site.get(APEX, url(e, 'raw/' + path))
    assert r.status_code == 200
    assert r.content == (L.text_dir(FIXTURE, e) / 'files' / path).read_bytes()
    assert r.headers['content-type'] == 'text/plain; charset=utf-8'       # HTML too: never run on this origin
    assert r.headers['access-control-allow-origin'] == '*'
    assert r.headers['content-security-policy'] == "default-src 'none'; sandbox"
    assert r.headers['x-content-type-options'] == 'nosniff'


@pytest.mark.parametrize('name', ['NOTICE', 'FETCHED', 'SHA256SUMS'])
def test_the_files_of_ours_are_served_as_they_are(site, name):
    for e in KEPT:
        r = site.get(APEX, url(e, name))
        assert r.status_code == 200 and r.headers['content-type'] == 'text/plain; charset=utf-8'
        assert r.content == (L.text_dir(FIXTURE, e) / name).read_bytes()


def test_the_raw_route_refuses_what_is_not_a_kept_file(site):
    e = KEPT[0]
    for bad in ('raw/missing.txt', 'raw/', 'raw/files/index.txt', 'raw/%2e%2e/%2e%2e/library.json'):
        assert site.get(APEX, url(e, bad)).status_code == 404, bad


def test_the_registry_is_served_byte_for_byte(site):
    r = site.get(APEX, '/library/library.json')
    assert r.status_code == 200
    assert r.content == (FIXTURE / 'library.json').read_bytes()
    assert r.headers['content-type'] == 'application/json'
    assert r.headers['access-control-allow-origin'] == '*'
    assert site.get(APEX, '/library/library.json/').status_code == 404


def test_a_kept_text_can_be_fetched_whole_from_the_registry_its_sums_and_raw(site, tmp_path):
    """What an app fetching on demand does: library.json, then for a kept entry its SHA256SUMS (whose sha256 is the
    entry's digest), NOTICE and FETCHED, and every file the sums list from raw/; the copy verifies."""
    import hashlib
    import json
    reg = json.loads(site.get(APEX, '/library/library.json').content)
    for e in [x for x in reg['texts'] if x['aboard']]:
        dest = tmp_path / e['shelf'] / e['text'] / e['version']
        sums = site.get(APEX, url(e, 'SHA256SUMS')).content
        assert 'sha256:' + hashlib.sha256(sums).hexdigest() == e['digest']
        for name in ('NOTICE', 'FETCHED'):
            (dest / name).parent.mkdir(parents=True, exist_ok=True)
            (dest / name).write_bytes(site.get(APEX, url(e, name)).content)
        (dest / 'SHA256SUMS').write_bytes(sums)
        for line in sums.decode().splitlines():
            rel = line.split('  ', 1)[1]
            body = site.get(APEX, url(e, 'raw/' + rel[len('files/'):])).content
            (dest / rel).parent.mkdir(parents=True, exist_ok=True)
            (dest / rel).write_bytes(body)
        assert L.verify(dest, e) == []


def test_a_registry_that_does_not_validate_is_not_served(export, lib):
    p = lib / 'library.json'
    p.write_text(p.read_text().replace('"format": "cosmoes-library/1"', '"format": "other/9"'))
    assert Site(export, library=lib).get(APEX, '/library/library.json').status_code == 404


# ----------------------------------------------------------------------------- the apex only, and what is refused

def test_the_library_is_on_the_apex_only(site):
    e = KEPT[0]
    for host in ('thym.cosmoes.org', 'macro.cosmoes.org'):
        for path in ('/library/', '/library/library.json', '/library/example/', url(e), url(e, 'index'), url(e, 'raw/index.txt'), url(e, 'NOTICE')):
            assert site.get(host, path).status_code == 404, (host, path)
    assert site.get('localhost:8097', '/library/').status_code == 200        # a host outside the domain is the apex


def test_a_text_that_does_not_verify_is_not_served_and_the_rest_is(export, lib):
    (lib / 'example' / 'manual' / '1.0' / 'files' / 'index.txt').write_text('changed\n')
    site = Site(export, library=lib)
    assert site.get(APEX, '/library/example/manual/1.0/').status_code == 404
    assert site.get(APEX, '/library/example/manual/1.0/raw/index.txt').status_code == 404
    assert site.get(APEX, '/library/example/sheet/2/').status_code == 200
    refused = site.app.state.library.refused
    assert list(refused) == ['example/manual/1.0'] and 'files/index.txt does not match its sha256' in refused['example/manual/1.0']
    assert 'The Example Manual' not in site.get(APEX, '/library/').text


def test_a_registry_that_does_not_validate_serves_no_shelf(export, lib):
    p = lib / 'library.json'
    p.write_text(p.read_text().replace('"format": "cosmoes-library/1"', '"format": "other/9"'))
    site = Site(export, library=lib)
    r = site.get(APEX, '/library/')
    assert r.status_code == 200 and 'Nothing is on the shelf yet.' in r.text
    assert site.get(APEX, '/library/example/').status_code == 404


def test_without_a_library_the_site_still_serves_the_specifications(export, tmp_path):
    site = Site(export, library=tmp_path / 'absent')
    assert site.get(APEX, '/library/').status_code == 200
    assert site.get(APEX, '/').status_code == 200
    assert '/library/' not in site.get(APEX, '/sitemap.xml').text


def test_the_sitemap_lists_the_library(site):
    locs = re.findall(r'<loc>(.*?)</loc>', site.get(APEX, '/sitemap.xml').text)
    for u in ('https://cosmoes.org/library/', 'https://cosmoes.org/library/example/', 'https://cosmoes.org/library/memos/',
              'https://cosmoes.org/library/example/manual/1.0/', 'https://cosmoes.org/library/example/manual/1.0/library/strings',
              'https://cosmoes.org/library/memos/memo/7/'):
        assert u in locs, u
    assert not any('/raw/' in u for u in locs)
    assert not any('/library/' in u for u in re.findall(r'<loc>(.*?)</loc>', site.get('thym.cosmoes.org', '/sitemap.xml').text))


def test_the_real_shelf_loads_with_nothing_refused():
    lib = library_mod.Library().load()
    assert lib.problems == [] and lib.refused == {}
    assert {s['slug'] for s in lib.shelves} >= {'python', 'ecmascript', 'go', 'rust', 'lean', 'json', 'unicode',
                                                'ieee-754'}


def test_the_fixture_has_a_text_that_carries_a_credit():
    assert any(e.get('credit') for e in KEPT)


REAL = Path(__file__).resolve().parents[1] / 'library'


def title_of(html: str) -> str:
    return re.search(r'<title>(.*?)</title>', html, re.S).group(1)


def h1_of(html: str) -> str:
    return re.sub(r'<[^>]+>', '', re.search(r'<h1[^>]*>(.*?)</h1>', html, re.S).group(1))


@pytest.mark.parametrize('path, title, h1', [
    ('/library/python/', 'Python® documentation · the library · cosmoes.org', 'Python® documentation'),
    ('/library/python/docs/3.13/', 'The Python® documentation 3.13 · the library · cosmoes.org',
     'The Python® documentation 3.13'),
    ('/library/python/docs/3.15/', 'The Python® documentation 3.15 · the library · cosmoes.org',
     'The Python® documentation 3.15'),
    ('/library/unicode/', 'Unicode® data files · the library · cosmoes.org', 'Unicode® data files'),
    ('/library/unicode/ucd/15.1.0/', 'The Unicode® Character Database 15.1.0 · the library · cosmoes.org',
     'The Unicode® Character Database 15.1.0'),
    ('/library/ecmascript/', 'ECMAScript · the library · cosmoes.org', 'ECMAScript'),
    ('/library/go/', 'Go · the library · cosmoes.org', 'Go'),
])
def test_the_real_shelf_carries_the_marks_at_the_first_prominent_mention(export, path, title, h1):
    """The owner's ruling (2026-11-22): Python® at its first prominent mention, Python as an adjective; Unicode® as
    an adjective, the shelf retitled to fit. Only our own words are marked; slugs and addresses do not change."""
    html = page_ok(Site(export, library=REAL).get(APEX, path))
    assert title_of(html) == title and h1_of(html) == h1


def test_a_page_of_the_python_docs_names_the_text_with_its_mark(export):
    html = page_ok(Site(export, library=REAL).get(APEX, '/library/python/docs/3.15/about'))
    assert title_of(html) == 'About this documentation · The Python® documentation 3.15 · cosmoes.org'
    kicker = re.sub(r'<[^>]+>', '', re.search(r'<p class="kicker">(.*?)</p>', html, re.S).group(1))
    assert kicker.startswith('The library · Python® documentation')     # the first mention, marked


def test_the_shelves_list_the_marked_titles(export):
    html = page_ok(Site(export, library=REAL).get(APEX, '/library/'))
    tiles = re.findall(r'<h2><a href="/library/[^"]+/">(.*?)</a></h2>', html)
    assert 'Python® documentation' in tiles and 'Unicode® data files' in tiles and 'Python' not in tiles


@pytest.mark.parametrize('path', ['/library/unicode/', '/library/unicode/ucd/15.1.0/',
                                  '/library/unicode/ucd/15.1.0/ArabicShaping'])
def test_the_unicode_pages_carry_its_legend(export, path):
    legend = ('Unicode and the Unicode Logo are registered trademarks of Unicode, Inc. in the United States and '
              'other countries.')
    html = page_ok(Site(export, library=REAL).get(APEX, path))
    assert html.count(f'<p class="lib-credit">{legend}</p>') >= 1


def test_a_shelf_page_carries_only_the_trademark_legends_once(export):
    html = page_ok(Site(export, library=REAL).get(APEX, '/library/ecmascript/'))
    credits = re.findall(r'<p class="lib-credit">(.*?)</p>', html)
    assert credits == ['ECMAScript® is a registered trademark of Ecma International.']
    go = page_ok(Site(export, library=REAL).get(APEX, '/library/go/'))   # the CC BY attribution is a page's, not a shelf's
    assert '<p class="lib-credit">' not in go

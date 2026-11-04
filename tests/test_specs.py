"""The loader (cosmoes/specs.py): what it refuses, and that the shipped site/specs/ is the registry's five documents,
each intact, in step with specs/, every page's anchors resolving, no margin marks, the Comprise chapters gone."""
from __future__ import annotations

import hashlib
import json
import re
import shutil

import pytest

from conftest import DOCS, ROOT, Site, anchors_resolve, host_for, make_export, no_inline_script_or_style, reseal, rewrite
from cosmoes import specs as specs_mod

DENSITIES = specs_mod.DENSITIES


def left_out(folder, slug: str, kept: str):
    """`slug` is served at no density, not raw and not on the apex; `kept` still is."""
    site = Site(folder)
    index = site.get('cosmoes.org')
    assert index.status_code == 200
    assert f'id="home-{slug}"' not in index.text and f'id="home-{kept}"' in index.text
    for density, path in specs_mod.PAGES.items():
        assert site.get(host_for(slug), path).status_code == 404, density
    assert site.get(host_for(slug), '/raw/source.md').status_code == 404
    assert site.get(host_for(kept), '/').status_code == 200


# ----------------------------------------------------------------------------- the fixture

def test_the_fixture_is_an_export(export):
    specs = specs_mod.Specs(export)
    assert [d['slug'] for d in specs.documents] == list(DOCS)
    for d in specs.documents:
        name, edition, lead, host = DOCS[d['slug']]
        assert d['name'] == name and d['version'] == edition and d['edition'] == edition and d['host'] == host
        assert d['revised'] == '2026-11-03' and d['lead'] == lead and d['counts'] == ['1 section', '1 term']
        assert d['raw'] == specs_mod.RAW and d['source_path'] == f'specs/{d["slug"]}.md'
        for density in DENSITIES:
            html = specs.page(d['slug'], density)
            assert html.startswith(f'<article class="docoes docoes-{density}"') and html.count('<h1') == 1
            anchors_resolve(html)
        assert specs.source(d['slug']).startswith(f'# {name}\n') and specs.page(d['slug'], 'source') is None
    assert specs.get('thym')['describes'] == {'thym': '1'} and specs.get('oes')['describes'] == {}
    assert specs.meta['enough'] == '0.5.1' and specs.meta['by'] == 'enough/0.5.1'
    assert specs.meta['commit'] == 'd2ea035' and specs.meta['dirty'] is True
    assert specs.meta['exported'].isoformat() == '2026-11-03T20:00:00+00:00'
    assert specs.css.startswith('.docoes')
    assert specs.manifest() == json.loads((export / 'manifest.json').read_text())
    assert [d['slug'] for d in specs.manifest('thym')['documents']] == ['thym'] and specs.manifest('nope') is None


def test_fields_the_manifest_lacks_or_spoils_fall_back(export):
    def edit(m):
        d = m['documents'][2]
        d.pop('edition'); d.pop('revised'); d.pop('raw'); d['host'] = 'Not A Host!'; d['describes'] = ['x']
    rewrite(export, edit)
    d = specs_mod.Specs(export).get('thym')
    assert d['edition'] == '0' and d['revised'] == '' and d['raw'] == {} and d['host'] == '' and d['describes'] == {}
    assert Site(export).get('thym.cosmoes.org').status_code == 404        # no usable host: served nowhere
    assert specs_mod.date_text('2026-11-03') == '3 Nov 2026' and specs_mod.date_text('nope') == ''


# ----------------------------------------------------------------------------- what it refuses

@pytest.mark.parametrize('spoil', [
    lambda folder: rewrite(folder, lambda m: m.update(format='docoes-export/2')),
    lambda folder: rewrite(folder, lambda m: m.pop('format')),
    lambda folder: rewrite(folder, lambda m: m.update(standalone=True)),
    lambda folder: (folder / 'manifest.json').write_text('not json'),
    lambda folder: (folder / 'manifest.json').unlink(),
], ids=['another format', 'no format', 'standalone', 'not json', 'no manifest'])
def test_a_manifest_the_site_cannot_use_publishes_nothing(export, spoil):
    spoil(export)
    specs = specs_mod.Specs(export)
    assert specs.documents == [] and specs.meta is None and specs.manifest() is None
    site = Site(export)
    r = site.get('cosmoes.org')
    assert r.status_code == 404 and 'Nothing is published here yet.' in r.text
    for slug in DOCS:
        assert site.get(host_for(slug), '/').status_code == 404


def test_a_fragment_that_differs_from_the_manifest_leaves_its_document_out(export, caplog):
    p = export / 'thym' / 'short.html'
    p.write_text(p.read_text() + '<!-- edited after the build -->')
    with caplog.at_level('WARNING', logger='cosmoes.specs'):
        left_out(export, 'thym', 'ascribe')
    assert 'thym/short.html differs from the manifest (sha256); thym is left out' in caplog.text


def test_a_source_that_differs_or_is_missing_leaves_its_document_out(export, caplog):
    p = export / 'thym' / 'source.md'
    p.write_text(p.read_text() + '\nan edit\n')
    with caplog.at_level('WARNING', logger='cosmoes.specs'):
        left_out(export, 'thym', 'ascribe')
    assert 'thym/source.md differs from the manifest (sha256); thym is left out' in caplog.text
    (export / 'ascribe' / 'source.md').unlink()
    left_out(export, 'ascribe', 'macrocosm-oes')
    rewrite(export, lambda m: m['documents'][1]['files'].pop('source'))
    left_out(export, 'macrocosm-oes', 'comprise-oes')


@pytest.mark.parametrize('spoil', [
    lambda folder: (folder / 'ascribe' / 'atem.html').unlink(),
    lambda folder: rewrite(folder, lambda m: m['documents'][3]['files'].pop('fabula')),
    lambda folder: rewrite(folder, lambda m: m['documents'][3]['files']['short'].update(path='../outside.html')),
    lambda folder: rewrite(folder, lambda m: m['documents'][3]['files']['short'].update(sha256='nope')),
    lambda folder: rewrite(folder, lambda m: m['documents'][3].update(slug='Not A Slug')),
], ids=['missing', 'no file', 'outside', 'no hash', 'bad slug'])
def test_a_document_whose_files_cannot_be_checked_is_left_out(export, spoil):
    spoil(export)
    left_out(export, 'ascribe', 'thym')


@pytest.mark.parametrize('what', [
    '<script>alert(1)</script>', '<SCRIPT src="/x.js"></SCRIPT>', '<style>body{display:none}</style>',
    '<p style="color:red">x</p>', '<a onclick="x()">x</a>', '<a href="javascript:alert(1)">x</a>',
    '<a href=" JAVA\tscript:alert(1)">x</a>', '<iframe src="https://example.com"></iframe>', '<link rel="stylesheet" href="/x.css">',
    '<meta http-equiv="refresh" content="0;url=/">', '<form action="/x"><input></form>', '<object data="x"></object>',
], ids=['script', 'script src', 'style', 'style attr', 'onclick', 'javascript:', 'javascript: spaced', 'iframe', 'link', 'meta', 'form', 'object'])
def test_a_fragment_with_what_the_site_never_includes_leaves_its_document_out(export, what):
    reseal(export, 'comprise-oes', 'short', f'<article class="docoes docoes-short"><h1>C</h1>{what}</article>')
    left_out(export, 'comprise-oes', 'thym')


def test_the_source_is_text_and_may_mention_anything(export):
    """The markdown is served as text/markdown, never included in a page: a <script> in it is just characters."""
    reseal(export, 'thym', 'source', '# Thym\n\nWrite `<script>` in a code span, or <script>alert(1)</script> in prose.\n')
    site = Site(export)
    assert site.get('thym.cosmoes.org').status_code == 200
    r = site.get('thym.cosmoes.org', '/raw/source.md')
    assert r.status_code == 200 and '<script>alert(1)</script>' in r.text and r.headers['content-type'].startswith('text/markdown')


def test_text_that_only_mentions_those_things_is_served():
    assert specs_mod.unsafe('<p>the &lt;script&gt; tag, <code>style="x"</code>, and a <a href="#x">link</a></p>') == []
    assert specs_mod.unsafe('<p>write onload= in a code span: <code>onload=</code></p>') == []


def test_the_export_is_read_once_on_first_use_and_kept(export):
    specs = specs_mod.Specs(export)
    shutil.rmtree(export / 'ascribe')                   # before the first use: it is read lazily, so this counts
    assert [d['slug'] for d in specs.documents] == ['oes', 'macrocosm-oes', 'thym', 'comprise-oes']
    shutil.rmtree(export)                               # after: what was read is kept
    assert specs.get('thym')['name'] == 'Thym' and specs.get('ascribe') is None
    assert specs.page('thym', 'short').startswith('<article class="docoes docoes-short"')
    assert specs.page('thym', 'medium') is None and specs.page('nope', 'short') is None and specs.source('nope') is None


# ----------------------------------------------------------------------------- what the build shipped

SHIPPED = specs_mod.FOLDER
REGISTRY = json.loads((ROOT / 'specs' / 'specs.json').read_text(encoding='utf-8'))
needs_build = pytest.mark.skipif(not (SHIPPED / 'manifest.json').exists(), reason='site/specs/ is not built yet (scripts/build_specs.py)')


@needs_build
def test_the_shipped_export_is_the_registry_built():
    m = json.loads((SHIPPED / 'manifest.json').read_text(encoding='utf-8'))
    assert m['format'] == specs_mod.FORMAT and not m.get('standalone') and m['pages'] == specs_mod.PAGES
    assert m['by'].startswith('enough/') and specs_mod.COMMIT_RE.match(m['source']['commit'])
    specs = specs_mod.Specs(SHIPPED)
    assert [d['slug'] for d in specs.documents] == [d['slug'] for d in m['documents']] == [e['slug'] for e in REGISTRY]
    assert specs.css and (SHIPPED / 'docs.css').is_file()
    for d, e in zip(specs.documents, REGISTRY):
        assert (d['name'], d['edition'], d['version'], d['host'], d['revised'], d['describes']) == \
               (e['name'], e['edition'], e['edition'], e['host'], e['revised'], e['describes']), d['slug']
        assert d['lead'] and d['counts'] and d['raw'] == specs_mod.RAW
        assert d['source_path'] == f'specs/{e["file"]}'
        text = (ROOT / 'specs' / e['file']).read_bytes()
        assert specs.source(d['slug']).encode('utf-8') == text                       # the source copy is the text
        assert d['source_sha256'] == hashlib.sha256(text).hexdigest()
        entry = next(x for x in m['documents'] if x['slug'] == d['slug'])
        assert entry['chapters'] == []                                                 # the Comprise chapters are gone
        assert (entry['counts']['reference'] > 0) is bool(e.get('reference'))        # the reference only where declared
    assert {d['host'] for d in specs.documents} == {'cosmoes.org', 'macro.cosmoes.org', 'thym.cosmoes.org',
                                                    'ascribe.cosmoes.org', 'comprise.cosmoes.org'}


@needs_build
@pytest.mark.parametrize('slug', [e['slug'] for e in REGISTRY])
def test_every_shipped_page_serves_with_its_anchors_resolving(slug):
    """The real pages on their hosts: one <h1>, every in-page anchor (contents, xrefs, term links) resolving, the links
    across densities at this host's own addresses, no margin marks, nothing inline, the raw files as they are."""
    site = Site(SHIPPED)
    host = next(e['host'] for e in REGISTRY if e['slug'] == slug)
    for density, path in specs_mod.PAGES.items():
        r = site.get(host, path)
        assert r.status_code == 200, (slug, density)
        html = r.text
        assert html.count('<h1') == 1
        assert anchors_resolve(html) > 0
        assert 'docs-marks' not in html and 'docs-chapter-note' not in html
        no_inline_script_or_style(html)
        across = set(re.findall(r'href="(/[^"#]*)#', html))
        assert across <= {'/', '/atem', '/fabula'}, across
        raw = site.get(host, f'/raw/{density}.html')
        assert raw.status_code == 200 and raw.content == (SHIPPED / slug / f'{density}.html').read_bytes()
    assert site.get(host, '/raw/source.md').content == (SHIPPED / slug / 'source.md').read_bytes()
    assert 'id="docs-sec-18-5"' in site.get('macro.cosmoes.org', '/').text     # docoes.cosmoes.org's target


@needs_build
def test_the_shipped_macrocosm_is_alone_and_the_apex_is_the_map():
    site = Site(SHIPPED)
    spec = site.get('macro.cosmoes.org', '/').text
    assert 'data-scope="comprise"' not in spec and 'docs-comprise-' not in spec
    assert spec.count('<a class="docs-term"') > 500 and spec.count('class="ref-xref') > 100
    assert 'id="docs-atem-reference"' in site.get('macro.cosmoes.org', '/atem').text    # the manifests' reference stays
    apex = site.get('cosmoes.org', '/').text
    assert 'data-doc="oes"' in apex and apex.count('class="tile"') == 4 and 'id="home-macrocosm-oes"' in apex
    assert apex.index('</article>') < apex.index('<section class="homes"')

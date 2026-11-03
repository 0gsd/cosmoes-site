"""The loader (cosmoes/specs.py): what it refuses, and that the shipped site/specs/ loads with every document intact and
every page's anchors resolving."""
from __future__ import annotations

import json
import re
import shutil

import pytest

from conftest import DOCS, Site, anchors_resolve, host_for, make_export, no_inline_script_or_style, reseal, rewrite
from cosmoes import specs as specs_mod
from cosmoes.app import HOSTS

DENSITIES = specs_mod.DENSITIES


def left_out(folder, slug: str, kept: str):
    """`slug` is served at no density and not on the apex; `kept` still is."""
    site = Site(folder)
    index = site.get('cosmoes.org')
    assert index.status_code == 200
    assert f'id="spec-{slug}"' not in index.text and f'id="spec-{kept}"' in index.text
    for density, path in specs_mod.PAGES.items():
        assert site.get(host_for(slug), path).status_code == 404, density
    assert site.get(host_for(kept), '/').status_code == 200


# ----------------------------------------------------------------------------- the fixture

def test_the_fixture_is_an_export(export):
    specs = specs_mod.Specs(export)
    assert [d['slug'] for d in specs.documents] == list(DOCS)
    for d in specs.documents:
        assert d['name'] == DOCS[d['slug']][0] and d['version'] == DOCS[d['slug']][1] and d['counts'] == ['1 section', '1 term']
        for density in DENSITIES:
            html = specs.page(d['slug'], density)
            assert html.startswith(f'<article class="docoes docoes-{density}"') and html.count('<h1') == 1
            anchors_resolve(html)
    assert specs.meta['from'] == 'enough 0.5.0' and specs.meta['commit'] == '12dfa61' and specs.meta['dirty'] is True
    assert specs.meta['exported'].isoformat() == '2026-11-02T20:00:00+00:00'
    assert specs.css.startswith('.docoes')
    assert specs.manifest() == json.loads((export / 'manifest.json').read_text())
    assert [d['slug'] for d in specs.manifest('thym')['documents']] == ['thym'] and specs.manifest('nope') is None


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
    p.write_text(p.read_text() + '<!-- edited after the sync -->')
    with caplog.at_level('WARNING', logger='cosmoes.specs'):
        left_out(export, 'thym', 'ascribe')
    assert 'thym/short.html differs from the manifest (sha256); thym is left out' in caplog.text


@pytest.mark.parametrize('spoil', [
    lambda folder: (folder / 'ascribe' / 'atem.html').unlink(),
    lambda folder: rewrite(folder, lambda m: m['documents'][2]['files'].pop('fabula')),
    lambda folder: rewrite(folder, lambda m: m['documents'][2]['files']['short'].update(path='../outside.html')),
    lambda folder: rewrite(folder, lambda m: m['documents'][2]['files']['short'].update(sha256='nope')),
    lambda folder: rewrite(folder, lambda m: m['documents'][2].update(slug='Not A Slug')),
], ids=['missing', 'no file', 'outside', 'no hash', 'bad slug'])
def test_a_document_whose_fragments_cannot_be_checked_is_left_out(export, spoil):
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


def test_text_that_only_mentions_those_things_is_served():
    assert specs_mod.unsafe('<p>the &lt;script&gt; tag, <code>style="x"</code>, and a <a href="#x">link</a></p>') == []
    assert specs_mod.unsafe('<p>write onload= in a code span: <code>onload=</code></p>') == []


def test_the_export_is_read_once_on_first_use_and_kept(export):
    specs = specs_mod.Specs(export)
    shutil.rmtree(export / 'ascribe')                   # before the first use: it is read lazily, so this counts
    assert [d['slug'] for d in specs.documents] == ['macrocosm-oes', 'thym', 'comprise-oes']
    shutil.rmtree(export)                               # after: what was read is kept
    assert specs.get('thym')['name'] == 'Thym 0' and specs.get('ascribe') is None
    assert specs.page('thym', 'short').startswith('<article class="docoes docoes-short"')
    assert specs.page('thym', 'medium') is None and specs.page('nope', 'short') is None


# ----------------------------------------------------------------------------- what the sync shipped

SHIPPED = specs_mod.FOLDER


@pytest.mark.skipif(not (SHIPPED / 'manifest.json').exists(), reason='site/specs/ is not synced yet (scripts/sync_specs.py)')
def test_the_shipped_export_loads_with_every_document_intact():
    m = json.loads((SHIPPED / 'manifest.json').read_text(encoding='utf-8'))
    assert m['format'] == specs_mod.FORMAT and not m.get('standalone') and m['pages'] == specs_mod.PAGES
    specs = specs_mod.Specs(SHIPPED)
    assert [d['slug'] for d in specs.documents] == [d['slug'] for d in m['documents']] == list(HOSTS.values())
    assert specs.css and (SHIPPED / 'docs.css').is_file()
    for d in specs.documents:
        assert d['name'] and d['version'] and d['lead'] and d['counts'], d['slug']


@pytest.mark.skipif(not (SHIPPED / 'manifest.json').exists(), reason='site/specs/ is not synced yet (scripts/sync_specs.py)')
@pytest.mark.parametrize('slug', list(HOSTS.values()))
def test_every_shipped_page_serves_with_its_anchors_resolving(slug):
    """The real pages on their hosts: one <h1>, every in-page anchor (contents, xrefs, term links) resolving, the links
    across densities at this host's own addresses, nothing inline."""
    site = Site(SHIPPED)
    for density, path in specs_mod.PAGES.items():
        r = site.get(host_for(slug), path)
        assert r.status_code == 200, (slug, density)
        html = r.text
        assert html.count('<h1') == 1
        assert anchors_resolve(html) > 0
        no_inline_script_or_style(html)
        across = set(re.findall(r'href="(/[^"#]*)#', html))
        assert across <= {'/', '/atem', '/fabula'}, across
    assert 'id="docs-sec-18-5"' in site.get('macro.cosmoes.org', '/').text     # docoes.cosmoes.org's target

"""The site's routing by the Host header: each specification's host at three densities, the apex index, the redirect
hosts, robots and sitemap, the manifest and the stylesheets, headers. Everything reads the fixture export conftest.py
writes; the real site/specs/ is test_specs.py's."""
from __future__ import annotations

import re

import pytest
from markupsafe import escape

from conftest import DOCS, PROV, Site, anchors_resolve, host_for, no_inline_script_or_style
from cosmoes.app import HOSTS, create_app

DENSITIES = ('atem', 'short', 'fabula')
PATH = {'short': '/', 'atem': '/atem', 'fabula': '/fabula'}
APEX = 'cosmoes.org'


def cached(r):
    assert r.headers['cache-control'] == 'public, max-age=300', r.url
    assert r.headers['content-security-policy'].startswith("default-src 'none'")
    assert r.headers['x-content-type-options'] == 'nosniff'


# ----------------------------------------------------------------------------- a specification on its host

@pytest.mark.parametrize('slug', list(DOCS))
@pytest.mark.parametrize('density', DENSITIES)
def test_each_host_serves_its_document_at_each_density(site, slug, density):
    host = host_for(slug)
    r = site.get(host, PATH[density])
    assert r.status_code == 200
    cached(r)
    html = r.text
    assert html.count('<h1') == 1
    assert f'<article class="docoes docoes-{density}" data-doc="{slug}" data-density="{density}"' in html
    assert f'<title>{DOCS[slug][0]} ({density}) · {host}</title>' in html
    assert f'<link rel="canonical" href="https://{host}{PATH[density]}">' in html
    assert '<link rel="stylesheet" href="/docs.css">' in html and '<link rel="stylesheet" href="/site.css">' in html
    assert anchors_resolve(html) >= 1
    # the density switch, the current one marked, the others at their root-absolute addresses
    switch = re.search(r'<nav class="densities" aria-label="Density">(.*?)</nav>', html, re.S).group(1)
    for d in DENSITIES:
        assert f'href="{PATH[d]}"' in switch
    assert switch.count('aria-current="page"') == 1 and f'href="{PATH[density]}" title="' in switch
    assert re.search(rf'<a href="{re.escape(PATH[density])}" title="[^"]+" aria-current="page">{density}</a>', switch)
    # the header names the four hosts and marks this one
    for sub in HOSTS:
        assert f'href="https://{sub}.cosmoes.org/"' in html
    assert html.count('aria-current="page"') == 2          # the host and the density
    assert f'<a href="https://{host}/" aria-current="page">' in html
    assert PROV in html
    no_inline_script_or_style(html)


def test_links_across_densities_land_on_the_same_host(site):
    """The atem outline and the fabula cards link to the short page at `/`, which is this host's own document."""
    for density in ('atem', 'fabula'):
        html = site.get('thym.cosmoes.org', PATH[density]).text
        assert 'href="/#docs-sec-1"' in html
    assert 'id="docs-sec-1"' in site.get('thym.cosmoes.org', '/').text


def test_short_is_the_root(site):
    r = site.get('thym.cosmoes.org', '/short')
    assert r.status_code == 301 and r.headers['location'] == '/'
    cached(r)
    for p in ('/atem/', '/fabula/', '/short/'):          # a trailing slash goes to the page (and /short on to /)
        r = site.get('thym.cosmoes.org', p)
        assert r.status_code == 301 and r.headers['location'] == p.rstrip('/'), p


def test_an_unknown_path_is_not_found(site):
    for host in ('thym.cosmoes.org', APEX, 'something.else.example'):
        for p in ('/nope', '/thym/short', '/macrocosmoes', '/static/site.css'):
            r = site.get(host, p)
            assert r.status_code == 404, (host, p)
            assert r.headers['cache-control'] == 'no-store'
            assert '<h1 id="h">Not found</h1>' in r.text and 'href="https://cosmoes.org/"' in r.text
            no_inline_script_or_style(r.text)
    # a density page only exists on a document's host
    for p in ('/atem', '/fabula', '/short'):
        assert site.get(APEX, p).status_code == 404, p


def test_a_document_the_export_lacks_is_not_found(tmp_path):
    from conftest import make_export
    site = Site(make_export(tmp_path / 'specs', slugs=('thym', 'ascribe')))
    for p in PATH.values():
        assert site.get('macro.cosmoes.org', p).status_code == 404, p
    assert site.get('macro.cosmoes.org', '/manifest.json').status_code == 404
    assert site.get('thym.cosmoes.org', '/').status_code == 200
    index = site.get(APEX).text
    assert 'id="spec-thym"' in index and 'id="spec-macrocosm-oes"' not in index
    assert 'https://macro.cosmoes.org/' in index          # the header still names the host


# ----------------------------------------------------------------------------- the apex

def test_the_apex_lists_every_specification_with_its_host_and_densities(site):
    r = site.get(APEX)
    assert r.status_code == 200
    cached(r)
    html = r.text
    assert html.count('<h1') == 1 and '<h1 id="h">The OES specifications</h1>' in html
    assert '<link rel="canonical" href="https://cosmoes.org/">' in html
    assert '<meta name="description" content="The official homes of the OES specifications' in html
    assert html.count('class="tile"') == 4
    for sub, slug in HOSTS.items():
        name, version, lead = DOCS[slug]
        tile = re.search(rf'<li class="tile" id="spec-{slug}">(.*?)</li>\s*(?=<li class="tile"|</ul>)', html, re.S).group(1)
        assert f'<a href="https://{sub}.cosmoes.org/">{sub}.cosmoes.org</a> · v{version}' in tile
        assert f'<h2><a href="https://{sub}.cosmoes.org/">{name}</a></h2>' in tile
        assert str(escape(lead)) in tile and '1 section · 1 term' in tile
        for d in DENSITIES:
            assert f'<a href="https://{sub}.cosmoes.org{PATH[d]}">{d}</a>' in tile
    assert 'href="https://docoes.cosmoes.org/"' in html and 'href="https://mini.cosmoes.org/"' in html
    assert PROV in html and 'Comprise OES 1 is Comprise\'s own text, © Graham Smith' in html
    assert '/docs.css' not in html                        # the index needs only site.css
    assert html.count('aria-current') == 0
    no_inline_script_or_style(html)


def test_an_unknown_host_serves_the_apex(site):
    for host in ('cosmoes-site-abc123-uc.a.run.app', '127.0.0.1:8097', 'localhost', '[::1]:8097', 'COSMOES.ORG.', 'other.cosmoes.org', ''):
        r = site.get(host)
        assert r.status_code == 200 and '<h1 id="h">The OES specifications</h1>' in r.text, host
    assert site.get('cosmoes-site-abc123-uc.a.run.app', '/healthz').json() == {'ok': True}


def test_without_an_export_nothing_is_published(tmp_path):
    site = Site(tmp_path / 'absent')
    r = site.get(APEX)
    assert r.status_code == 404 and 'Nothing is published here yet.' in r.text and 'class="tile"' not in r.text
    assert r.headers['cache-control'] == 'no-store'
    assert site.get('thym.cosmoes.org').status_code == 404
    assert site.get(APEX, '/manifest.json').status_code == 404
    assert site.get(APEX, '/sitemap.xml').text.count('<loc>') == 1       # the apex alone
    assert site.get(APEX, '/docs.css').status_code == 200                  # empty, but there
    no_inline_script_or_style(r.text)


# ----------------------------------------------------------------------------- the redirect hosts

def test_www_goes_to_the_apex_keeping_the_path(site):
    for path, to in (('/', 'https://cosmoes.org/'), ('/sitemap.xml', 'https://cosmoes.org/sitemap.xml'),
                     ('/a/b?x=1&y=2', 'https://cosmoes.org/a/b?x=1&y=2')):
        r = site.get('www.cosmoes.org', path)
        assert r.status_code == 301 and r.headers['location'] == to, path
        cached(r)


@pytest.mark.parametrize('host, to', [('docoes.cosmoes.org', 'https://macro.cosmoes.org/#docs-sec-18-5'),
                                      ('mini.cosmoes.org', 'https://cosmoes.org/')])
def test_docoes_and_mini_redirect_whatever_the_path(site, host, to):
    for path in ('/', '/atem', '/anything/at/all?q=1', '/robots.txt'):
        r = site.get(host, path)
        assert r.status_code == 302 and r.headers['location'] == to, path
        cached(r)


# ----------------------------------------------------------------------------- robots, sitemap, manifest, css, healthz

def test_robots_allows_everything_and_names_the_hosts_sitemap(site):
    for host, own in ((APEX, 'https://cosmoes.org/'), ('thym.cosmoes.org', 'https://thym.cosmoes.org/'),
                      ('whatever.example', 'https://cosmoes.org/')):
        r = site.get(host, '/robots.txt')
        assert r.status_code == 200 and r.headers['content-type'].startswith('text/plain')
        assert r.text == f'User-agent: *\nAllow: /\n\nSitemap: {own}sitemap.xml\n', host
        assert 'x-robots-tag' not in r.headers
        cached(r)
    assert 'x-robots-tag' not in site.get('thym.cosmoes.org', '/').headers
    assert 'noindex' not in site.get('thym.cosmoes.org', '/').text


def test_the_sitemap_lists_every_page(site):
    r = site.get(APEX, '/sitemap.xml')
    assert r.status_code == 200 and r.headers['content-type'].startswith('application/xml')
    cached(r)
    locs = re.findall(r'<loc>(.*?)</loc>', r.text)
    assert locs == ['https://cosmoes.org/'] + [f'https://{sub}.cosmoes.org{PATH[d]}' for sub in HOSTS for d in ('short', 'atem', 'fabula')]
    assert r.text.count('<lastmod>2026-11-02</lastmod>') == len(locs)
    locs = re.findall(r'<loc>(.*?)</loc>', site.get('ascribe.cosmoes.org', '/sitemap.xml').text)
    assert locs == ['https://ascribe.cosmoes.org/', 'https://ascribe.cosmoes.org/atem', 'https://ascribe.cosmoes.org/fabula']


def test_the_manifest_is_the_hosts_document_and_all_of_them_at_the_apex(site):
    r = site.get('comprise.cosmoes.org', '/manifest.json')
    assert r.status_code == 200 and r.headers['access-control-allow-origin'] == '*'
    cached(r)
    m = r.json()
    assert m['format'] == 'docoes-export/1' and m['pages'] == PATH and m['standalone'] is False
    assert [d['slug'] for d in m['documents']] == ['comprise-oes'] and m['documents'][0]['files']['short']['path'] == 'comprise-oes/short.html'
    m = site.get(APEX, '/manifest.json').json()
    assert [d['slug'] for d in m['documents']] == list(DOCS) and m['by'] == 'enough/0.5.0'
    assert site.get('whatever.example', '/manifest.json').json()['documents'] == m['documents']


def test_the_stylesheets_and_healthz(site):
    for host in (APEX, 'macro.cosmoes.org'):
        r = site.get(host, '/docs.css')
        assert r.status_code == 200 and r.headers['content-type'] == 'text/css; charset=utf-8' and '.docoes' in r.text
        cached(r)
        r = site.get(host, '/site.css')
        assert r.status_code == 200 and r.headers['content-type'] == 'text/css; charset=utf-8' and '--measure: 64ch' in r.text
        cached(r)
        for path in ('/healthz', '/health'):          # Cloud Run's front end swallows /healthz; /health gets through
            r = site.get(host, path)
            assert r.status_code == 200 and r.json() == {'ok': True} and r.headers['cache-control'] == 'no-store'


def test_hsts_only_over_https(export):
    plain, secure = Site(export, 'http'), Site(export, 'https')
    for path in ('/', '/atem', '/robots.txt'):
        assert 'strict-transport-security' not in plain.get('thym.cosmoes.org', path).headers
        assert secure.get('thym.cosmoes.org', path).headers['strict-transport-security'] == 'max-age=31536000'
    r = secure.get('www.cosmoes.org', '/')
    assert r.status_code == 301 and r.headers['strict-transport-security'] == 'max-age=31536000'


def test_head_requests_answer_like_get(site):
    r = site.client.head('/', headers={'Host': 'thym.cosmoes.org'})
    assert r.status_code == 200 and r.content == b'' and r.headers['cache-control'] == 'public, max-age=300'


def test_the_module_level_app_reads_the_shipped_folder():
    from cosmoes import app as app_mod
    assert app_mod.app.state.specs.folder == app_mod.specs_mod.FOLDER
    assert create_app().state.specs.folder.name == 'specs'

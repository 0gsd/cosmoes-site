"""The site's routing by the Host header: each specification's host at three densities, the apex as the paradigm map's
host with the list of the homes, the raw endpoints, the redirect hosts, robots and sitemap, the manifest and the
stylesheets, headers, the licence line. Every name and edition shown comes from the manifest. Everything reads the
fixture export conftest.py writes; the real site/specs/ is test_specs.py's."""
from __future__ import annotations

import re

import pytest
from markupsafe import escape

from conftest import APEX_SLUG, DOCS, HOSTS, LICENCE, PROV, Site, anchors_resolve, host_for, make_export, no_inline_script_or_style, rewrite
from cosmoes.app import DOCOES_ANCHOR, create_app

DENSITIES = ('atem', 'short', 'fabula')
PATH = {'short': '/', 'atem': '/atem', 'fabula': '/fabula'}
APEX = 'cosmoes.org'
RAW = {'source.md': 'text/markdown; charset=utf-8', 'short.html': 'text/html; charset=utf-8',
       'atem.html': 'text/html; charset=utf-8', 'fabula.html': 'text/html; charset=utf-8'}


def cached(r):
    assert r.headers['cache-control'] == 'public, max-age=300', r.url
    assert r.headers['content-security-policy'].startswith("default-src 'none'")
    assert r.headers['x-content-type-options'] == 'nosniff'


# ----------------------------------------------------------------------------- a specification on its host

@pytest.mark.parametrize('slug', list(DOCS))
@pytest.mark.parametrize('density', DENSITIES)
def test_each_host_serves_its_document_at_each_density(site, slug, density):
    host = host_for(slug)
    name, edition, lead, _ = DOCS[slug]
    r = site.get(host, PATH[density])
    assert r.status_code == 200
    cached(r)
    html = r.text
    assert html.count('<h1') == 1
    assert f'<article class="docoes docoes-{density}" data-doc="{slug}" data-density="{density}"' in html
    assert f'<title>{name} ({density}) · {host}</title>' in html
    assert f'<link rel="canonical" href="https://{host}{PATH[density]}">' in html
    assert f'<meta name="description" content="{escape(lead)}">' in html
    assert '<link rel="stylesheet" href="/docs.css">' in html and '<link rel="stylesheet" href="/site.css">' in html
    assert f'<p class="kicker">{host} · edition {edition} · revised 3 Nov 2026 · ' in html
    assert anchors_resolve(html) >= 1
    # the density switch, the current one marked, the others at their root-absolute addresses
    switch = re.search(r'<nav class="densities" aria-label="Density">(.*?)</nav>', html, re.S).group(1)
    for d in DENSITIES:
        assert f'href="{PATH[d]}"' in switch
    assert switch.count('aria-current="page"') == 1 and f'href="{PATH[density]}" title="' in switch
    assert re.search(rf'<a href="{re.escape(PATH[density])}" title="[^"]+" aria-current="page">{density}</a>', switch)
    # the header names the four homes by the manifest's names and marks this one (the apex text has no home of its own)
    for sub, s in HOSTS.items():
        current = ' aria-current="page"' if s == slug else ''
        assert f'<a href="https://{sub}.cosmoes.org/"{current}>{DOCS[s][0]}</a>' in html
    assert html.count('aria-current="page"') == (1 if slug == APEX_SLUG else 2)
    assert PROV in html and LICENCE in html
    assert 'Apache-2.0 (enough)' not in html
    no_inline_script_or_style(html)


def test_links_across_densities_land_on_the_same_host(site):
    """The atem outline and the fabula cards link to the short page at `/`, which is this host's own document."""
    for host in ('thym.cosmoes.org', APEX):
        for density in ('atem', 'fabula'):
            html = site.get(host, PATH[density]).text
            assert 'href="/#docs-sec-1"' in html
        assert 'id="docs-sec-1"' in site.get(host, '/').text


def test_short_is_the_root(site):
    for host in ('thym.cosmoes.org', APEX):
        r = site.get(host, '/short')
        assert r.status_code == 301 and r.headers['location'] == '/'
        cached(r)
        for p in ('/atem/', '/fabula/', '/short/'):          # a trailing slash goes to the page (and /short on to /)
            r = site.get(host, p)
            assert r.status_code == 301 and r.headers['location'] == p.rstrip('/'), p


def test_an_unknown_path_is_not_found(site):
    for host in ('thym.cosmoes.org', APEX, 'something.else.example'):
        for p in ('/nope', '/thym/short', '/macrocosmoes', '/static/site.css', '/raw', '/raw/', '/raw/nope.md', '/raw/source.md/x'):
            r = site.get(host, p)
            assert r.status_code == 404, (host, p)
            assert r.headers['cache-control'] == 'no-store'
            assert '<h1 id="h">Not found</h1>' in r.text and 'href="https://cosmoes.org/"' in r.text
            assert LICENCE in r.text
            no_inline_script_or_style(r.text)


def test_a_document_the_export_lacks_is_not_found(tmp_path):
    site = Site(make_export(tmp_path / 'specs', slugs=('oes', 'thym', 'ascribe')))
    for p in list(PATH.values()) + ['/raw/source.md', '/raw/short.html']:
        assert site.get('macro.cosmoes.org', p).status_code == 404, p
    assert site.get('macro.cosmoes.org', '/manifest.json').status_code == 404
    assert site.get('thym.cosmoes.org', '/').status_code == 200
    apex = site.get(APEX).text
    assert 'id="home-thym"' in apex and 'id="home-ascribe"' in apex and 'id="home-macrocosm-oes"' not in apex
    assert 'https://macro.cosmoes.org/' not in apex          # the header names only what the manifest has


def test_names_hosts_and_editions_come_from_the_manifest(export):
    """Rename a document, move another to a new host, give a third another edition: the pages follow the manifest."""
    def edit(m):
        for d in m['documents']:
            if d['slug'] == 'thym':
                d['name'], d['edition'] = 'Thyme', '0.5.4'
            if d['slug'] == 'ascribe':
                d['host'] = 'scribe.cosmoes.org'
            if d['slug'] == 'comprise-oes':
                d['host'] = 'www.cosmoes.org'                    # a redirect host: never a document's
    rewrite(export, edit)
    site = Site(export)
    html = site.get('thym.cosmoes.org').text
    assert '<title>Thyme (short) · thym.cosmoes.org</title>' in html and ' · edition 0.5.4 · ' in html
    assert '<a href="https://thym.cosmoes.org/" aria-current="page">Thyme</a>' in html
    assert site.get('scribe.cosmoes.org').status_code == 200 and 'data-doc="ascribe"' in site.get('scribe.cosmoes.org').text
    assert site.get('ascribe.cosmoes.org').status_code == 404
    assert site.get('www.cosmoes.org').status_code == 301
    assert site.get('comprise.cosmoes.org').status_code == 404
    apex = site.get(APEX).text
    assert 'scribe.cosmoes.org' in apex and 'id="home-comprise-oes"' not in apex and apex.count('class="tile"') == 3
    locs = re.findall(r'<loc>(.*?)</loc>', site.get(APEX, '/sitemap.xml').text)
    assert 'https://scribe.cosmoes.org/' in locs and 'https://comprise.cosmoes.org/' not in locs


# ----------------------------------------------------------------------------- the apex

def test_the_apex_is_the_paradigm_map_with_the_list_of_homes(site):
    r = site.get(APEX)
    assert r.status_code == 200
    cached(r)
    html = r.text
    assert html.count('<h1') == 1 and '<article class="docoes docoes-short" data-doc="oes" data-density="short"' in html
    assert '<title>OES (short) · cosmoes.org</title>' in html
    assert '<link rel="canonical" href="https://cosmoes.org/">' in html
    assert '<body class="doc density-short apex">' in html
    homes = re.search(r'<section class="homes" aria-labelledby="homes-h">(.*?)</section>', html, re.S).group(1)
    assert html.index('</article>') < html.index('<section class="homes"')           # the text, then the list
    assert '<h2 id="homes-h">The specifications and their homes</h2>' in homes
    assert homes.count('class="tile"') == 4
    for sub, slug in HOSTS.items():
        name, edition, lead, host = DOCS[slug]
        tile = re.search(rf'<li class="tile" id="home-{slug}">(.*?)</li>\s*(?=<li class="tile"|</ul>)', homes, re.S).group(1)
        assert f'<a href="https://{host}/">{host}</a> · edition {edition}' in tile
        assert f'<h3><a href="https://{host}/">{name}</a></h3>' in tile
        assert str(escape(lead)) in tile
        for d in DENSITIES:
            assert f'<a href="https://{host}{PATH[d]}">{d}</a>' in tile
    assert 'id="home-oes"' not in homes                                                 # the apex text is not a home
    assert 'href="https://docoes.cosmoes.org/"' in homes and 'href="https://mini.cosmoes.org/"' in homes
    assert 'href="/manifest.json"' in homes
    assert anchors_resolve(html) >= 1
    assert PROV in html and LICENCE in html
    no_inline_script_or_style(html)
    # the other densities of the apex text carry no list; a document host never does
    for host, path in ((APEX, '/atem'), (APEX, '/fabula'), ('thym.cosmoes.org', '/')):
        page = site.get(host, path).text
        assert '<section class="homes"' not in page and 'class="tile"' not in page, (host, path)


def test_an_unknown_host_serves_the_apex(site):
    for host in ('cosmoes-site-abc123-uc.a.run.app', '127.0.0.1:8097', 'localhost', '[::1]:8097', 'COSMOES.ORG.', ''):
        r = site.get(host)
        assert r.status_code == 200 and 'data-doc="oes"' in r.text and '<section class="homes"' in r.text, host
        assert site.get(host, '/raw/source.md').text == site.get(APEX, '/raw/source.md').text
    assert site.get('cosmoes-site-abc123-uc.a.run.app', '/healthz').json() == {'ok': True}


def test_a_name_under_the_domain_that_nothing_claims_is_not_found(site):
    """Not the apex: a document left out of the manifest must not come back as the paradigm map at its host."""
    for path in ('/', '/atem', '/raw/source.md', '/manifest.json', '/robots.txt', '/sitemap.xml', '/docs.css'):
        r = site.get('other.cosmoes.org', path)
        assert r.status_code == 404 and r.headers['cache-control'] == 'no-store', path
        assert '<h1 id="h">Not found</h1>' in r.text
    assert site.get('a.b.cosmoes.org').status_code == 404
    assert site.get('MACRO.cosmoes.org.').status_code == 200                         # case and a trailing dot: the same host
    assert site.get('other.cosmoes.org', '/health').json()['ok'] is True


def test_without_an_apex_text_the_apex_lists_the_homes(tmp_path):
    site = Site(make_export(tmp_path / 'specs', slugs=tuple(HOSTS.values())))
    r = site.get(APEX)
    assert r.status_code == 200
    cached(r)
    html = r.text
    assert html.count('<h1') == 1 and '<h1 id="h">The OES specifications</h1>' in html
    assert html.count('class="tile"') == 4 and 'id="home-thym"' in html and ' · edition 0</p>' in html
    assert '<link rel="canonical" href="https://cosmoes.org/">' in html
    assert '<meta name="description" content="The official homes of the OES specifications: MacroCOSM OES, Thym, Ascribe and Comprise OES, each at three densities' in html
    assert '/docs.css' not in html and LICENCE in html
    no_inline_script_or_style(html)
    for p in ('/atem', '/fabula', '/short', '/raw/source.md', '/raw/short.html'):
        assert site.get(APEX, p).status_code == 404, p
    assert site.get(APEX, '/sitemap.xml').text.count('<loc>') == 1 + 12


def test_without_an_export_nothing_is_published(tmp_path):
    site = Site(tmp_path / 'absent')
    r = site.get(APEX)
    assert r.status_code == 404 and 'Nothing is published here yet.' in r.text and 'class="tile"' not in r.text
    assert r.headers['cache-control'] == 'no-store'
    assert site.get('thym.cosmoes.org').status_code == 404
    assert site.get(APEX, '/manifest.json').status_code == 404
    assert site.get(APEX, '/raw/source.md').status_code == 404
    assert site.get(APEX, '/sitemap.xml').text.count('<loc>') == 1       # the apex alone
    assert site.get(APEX, '/docs.css').status_code == 200                  # empty, but there
    no_inline_script_or_style(r.text)


# ----------------------------------------------------------------------------- the raw endpoints

@pytest.mark.parametrize('slug', list(DOCS))
def test_every_document_host_serves_its_files_raw(site, export, slug):
    host = host_for(slug)
    for name, media in RAW.items():
        r = site.get(host, f'/raw/{name}')
        assert r.status_code == 200, (host, name)
        assert r.headers['content-type'] == media
        assert r.headers['access-control-allow-origin'] == '*'
        cached(r)
        on_disk = (export / slug / ('source.md' if name == 'source.md' else name)).read_bytes()
        assert r.content == on_disk                                     # as it is, byte for byte
    assert site.get(host, '/raw/source.md').text.startswith(f'# {DOCS[slug][0]}\n')
    assert site.get(host, '/raw/short.html').text.startswith('<article class="docoes docoes-short"')
    assert 'access-control-allow-origin' not in site.get(host, '/').headers       # the pages are not CORS resources
    m = site.get(host, '/manifest.json').json()['documents']
    entry = next(d for d in m if d['slug'] == slug)
    assert entry['raw'] == {'source': '/raw/source.md', 'short': '/raw/short.html', 'atem': '/raw/atem.html', 'fabula': '/raw/fabula.html'}
    assert entry['files']['source']['path'] == f'{slug}/source.md'


def test_the_raw_endpoints_follow_the_redirect_hosts(site):
    r = site.get('www.cosmoes.org', '/raw/source.md')
    assert r.status_code == 301 and r.headers['location'] == 'https://cosmoes.org/raw/source.md'
    assert site.get('docoes.cosmoes.org', '/raw/source.md').status_code == 302


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
    assert DOCOES_ANCHOR == '#docs-sec-18-5'


# ----------------------------------------------------------------------------- robots, sitemap, manifest, css, healthz

def test_health_says_the_edition_from_the_manifest(site, tmp_path):
    want = DOCS[APEX_SLUG][1]
    for host in (APEX, 'thym.cosmoes.org', 'other.cosmoes.org', 'cosmoes-site-abc123-uc.a.run.app'):
        r = site.get(host, '/health')
        assert r.status_code == 200 and r.json() == {'ok': True, 'edition': want}, host
        assert r.headers['cache-control'] == 'no-store'
    assert site.get(APEX, '/healthz').json() == {'ok': True}

    moved = make_export(tmp_path / 'moved')                   # another edition in the manifest: /health says it, with no code changed
    manifest = (moved / 'manifest.json').read_text(encoding='utf-8')
    (moved / 'manifest.json').write_text(manifest.replace(f'"edition": "{want}"', '"edition": "9.8.7"'), encoding='utf-8')
    assert Site(moved).get(APEX, '/health').json() == {'ok': True, 'edition': '9.8.7'}

    no_apex = Site(make_export(tmp_path / 'no-apex', slugs=tuple(HOSTS.values())))     # no apex text: the first document's
    assert no_apex.get(APEX, '/health').json()['edition'] == DOCS[tuple(HOSTS.values())[0]][1]
    assert Site(tmp_path / 'nothing').get(APEX, '/health').json() == {'ok': True, 'edition': None}


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
    assert locs == [f'https://cosmoes.org{PATH[d]}' for d in ('short', 'atem', 'fabula')] + \
                   [f'https://{sub}.cosmoes.org{PATH[d]}' for sub in HOSTS for d in ('short', 'atem', 'fabula')]
    assert r.text.count('<lastmod>2026-11-03</lastmod>') == len(locs) == 15
    locs = re.findall(r'<loc>(.*?)</loc>', site.get('ascribe.cosmoes.org', '/sitemap.xml').text)
    assert locs == ['https://ascribe.cosmoes.org/', 'https://ascribe.cosmoes.org/atem', 'https://ascribe.cosmoes.org/fabula']


def test_the_manifest_is_the_hosts_document_and_all_of_them_at_the_apex(site):
    r = site.get('comprise.cosmoes.org', '/manifest.json')
    assert r.status_code == 200 and r.headers['access-control-allow-origin'] == '*'
    cached(r)
    m = r.json()
    assert m['format'] == 'docoes-export/1' and m['pages'] == PATH and m['standalone'] is False
    assert [d['slug'] for d in m['documents']] == ['comprise-oes'] and m['documents'][0]['files']['short']['path'] == 'comprise-oes/short.html'
    d = m['documents'][0]
    assert (d['edition'], d['host'], d['revised'], d['describes']) == ('1', 'comprise.cosmoes.org', '2026-11-03', {'comprise': '1'})
    m = site.get(APEX, '/manifest.json').json()
    assert [d['slug'] for d in m['documents']] == list(DOCS) and m['by'] == 'enough/0.5.1'
    assert m['source'] == {'commit': 'd2ea035', 'dirty': True}
    assert site.get('whatever.example', '/manifest.json').json()['documents'] == m['documents']
    assert site.get(APEX, '/manifest.json').headers['access-control-allow-origin'] == '*'


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
            assert r.status_code == 200 and r.json()['ok'] is True and r.headers['cache-control'] == 'no-store'


def test_hsts_only_over_https(export):
    plain, secure = Site(export, 'http'), Site(export, 'https')
    for path in ('/', '/atem', '/robots.txt', '/raw/source.md'):
        assert 'strict-transport-security' not in plain.get('thym.cosmoes.org', path).headers
        assert secure.get('thym.cosmoes.org', path).headers['strict-transport-security'] == 'max-age=31536000'
    r = secure.get('www.cosmoes.org', '/')
    assert r.status_code == 301 and r.headers['strict-transport-security'] == 'max-age=31536000'


def test_head_requests_answer_like_get(site):
    r = site.client.head('/', headers={'Host': 'thym.cosmoes.org'})
    assert r.status_code == 200 and r.content == b'' and r.headers['cache-control'] == 'public, max-age=300'
    r = site.client.head('/raw/source.md', headers={'Host': 'thym.cosmoes.org'})
    assert r.status_code == 200 and r.content == b'' and r.headers['access-control-allow-origin'] == '*'


def test_the_module_level_app_reads_the_shipped_folder():
    from cosmoes import app as app_mod
    assert app_mod.app.state.specs.folder == app_mod.specs_mod.FOLDER
    assert create_app().state.specs.folder.name == 'specs'

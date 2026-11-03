"""A small export written to the export's format (enough-dev's docs/thym-landed-X1.md, section 2): the four documents the
hosts serve, three densities each, a manifest with the files' real hashes. Made fresh in a temporary folder for each
test, so a test may spoil its copy; the real site/specs/ is read only by the integrity tests."""
from __future__ import annotations

import hashlib
import json
import re
import sys
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from cosmoes import specs as specs_mod  # noqa: E402
from cosmoes.app import HOSTS, create_app  # noqa: E402

DOCS = {'macrocosm-oes': ('MacroCOSM OES', '0.0.2', 'MacroCOSM OES is the shared grammar every MiniCOSM is written in'),
        'thym': ('Thym 0', '0', 'Version 0 of the language'),
        'ascribe': ('Ascribe OES 1', '1', "Ascribe is the MiniCOSM for a person's holograph"),
        'comprise-oes': ('Comprise OES 1', '1', 'The code in core/ is the reference reader and writer')}
EXPORTED = '2026-11-02T20:00:00Z'
PROV = 'From enough 0.5.0 (12dfa61), exported 2 Nov 2026.'
CSS = '.docoes { color: var(--ink, #1a1f2b); }\n'


def fragment(slug: str, density: str, name: str) -> str:
    """A fragment with one <h1>, a section, a term link to a glossary entry, a contents link, and (atem, fabula) a link
    across densities to the short page at its root-absolute address."""
    top = {'short': 'docs-sec-1', 'atem': 'docs-atem-outline', 'fabula': 'docs-fab-s'}[density]
    contents = f'<nav class="docoes-contents" aria-label="Contents"><ol><li class="lvl2"><a href="#{top}">1. One</a></li></ol></nav>'
    if density == 'short':
        body = (f'<h1 id="docs-{slug}">{name}</h1>'
                f'<section class="docs-sec" data-key="S:section/1" data-scope=""><h2 id="docs-sec-1" data-toc="2">1. One</h2>'
                f'<p>A <a class="docs-term" href="#docs-item-t-term-word" data-term="T:term/word" title="a word">word</a> '
                f'of {name}; see <a class="ref-xref" href="#docs-sec-1">section 1</a>.</p></section>'
                f'<section class="docs-sec docs-glossary" id="docs-glossary"><h2 id="docs-glossary-h" data-toc="2">Terms</h2>'
                f'<dl class="docs-gloss"><dt id="docs-item-t-term-word">word</dt><dd>a word</dd></dl></section>')
    elif density == 'atem':
        body = (f'<h1>{name}</h1><p class="docs-atem-lead">the lead</p><h2 id="docs-atem-outline" data-toc="2">Outline</h2>'
                f'<ol class="docs-outline"><li class="docs-ol-top" data-depth="0"><a class="docs-ol-row" href="/#docs-sec-1">'
                f'<span class="docs-ol-num">1</span> <span class="docs-ol-name">One</span></a></li></ol>'
                f'<h2 id="docs-atem-glossary" data-toc="2">Glossary</h2><dl class="docs-gloss"><dt id="docs-item-t-term-word">word</dt>'
                f'<dd>a word</dd></dl>')
    else:
        body = (f'<h1>{name}</h1><p class="docs-fab-note">Every item as a card.</p><h2 id="docs-fab-s" data-toc="2">Structure</h2>'
                f'<article class="docs-card" id="docs-item-s-section-1" data-kind="section"><h4><code class="docs-card-id">S:section/1</code> One</h4>'
                f'<p class="docs-card-read"><a class="ref-xref" href="/#docs-sec-1">read it at short</a></p></article>')
    return (f'<article class="docoes docoes-{density}" data-doc="{slug}" data-density="{density}" data-lang="en">\n'
            f'{contents}\n<div class="docoes-body">{body}</div>\n</article>\n')


def make_export(folder: Path, slugs=tuple(DOCS), pages=None, **manifest) -> Path:
    """Write an export of `slugs` into `folder` and return it."""
    folder.mkdir(parents=True, exist_ok=True)
    (folder / 'docs.css').write_text(CSS, encoding='utf-8')
    docs = []
    for slug in slugs:
        name, version, lead = DOCS[slug]
        files = {}
        for density in ('short', 'atem', 'fabula'):
            p = folder / slug / f'{density}.html'
            p.parent.mkdir(parents=True, exist_ok=True)
            p.write_text(fragment(slug, density, name), encoding='utf-8')
            raw = p.read_bytes()
            files[density] = {'path': f'{slug}/{density}.html', 'sha256': hashlib.sha256(raw).hexdigest(), 'bytes': len(raw)}
        docs.append({'slug': slug, 'name': name, 'version': version, 'lang': 'en', 'id': f'doc/{slug}', 'oes': 'doc/1',
                     'lead': lead, 'source': {'path': f'docs/{slug}.md', 'sha256': '0' * 64}, 'chapters': [],
                     'counts': {'sections': 1, 'terms': 1, 'examples': 0, 'decisions': 0, 'reference': 0}, 'files': files})
    m = {'format': specs_mod.FORMAT, 'exported': EXPORTED, 'by': 'enough/0.5.0', 'source': {'commit': '12dfa61', 'dirty': True},
         'css': 'docs.css', 'pages': pages or dict(specs_mod.PAGES), 'standalone': False, 'documents': docs, **manifest}
    (folder / 'manifest.json').write_text(json.dumps(m, indent=1), encoding='utf-8')
    return folder


def rewrite(folder: Path, edit) -> None:
    """Change the export's manifest in place with `edit(manifest)`."""
    p = folder / 'manifest.json'
    m = json.loads(p.read_text(encoding='utf-8'))
    edit(m)
    p.write_text(json.dumps(m), encoding='utf-8')


def reseal(folder: Path, slug: str, density: str, html: str) -> None:
    """Write a fragment and record its sha256 and size, so that only what it holds is under test."""
    p = folder / slug / f'{density}.html'
    p.write_text(html, encoding='utf-8')
    raw = p.read_bytes()

    def edit(m):
        f = next(d for d in m['documents'] if d['slug'] == slug)['files'][density]
        f.update(sha256=hashlib.sha256(raw).hexdigest(), bytes=len(raw))
    rewrite(folder, edit)


class Site:
    """The site over an export folder; `get(host, path)` asks as that host, without following redirects."""

    def __init__(self, folder: Path, scheme: str = 'http'):
        self.folder = folder
        self.app = create_app(folder)
        self.client = TestClient(self.app, base_url=f'{scheme}://cosmoes.org')

    def get(self, host: str, path: str = '/', **kw):
        return self.client.get(path, headers={'Host': host}, follow_redirects=False, **kw)


@pytest.fixture
def export(tmp_path) -> Path:
    return make_export(tmp_path / 'specs')


@pytest.fixture
def site(export) -> Site:
    return Site(export)


def no_inline_script_or_style(html: str) -> None:
    assert '<script' not in html.lower() and '<style' not in html.lower() and ' style="' not in html, 'inline script or style'
    assert not re.search(r'\son[a-z]+=', html), 'an event attribute'


def anchors_resolve(html: str) -> int:
    """Every in-page href="#…" names an id in the page; returns how many there were."""
    ids = set(re.findall(r'\bid="([^"]+)"', html))
    assert len(ids) == len(re.findall(r'\bid="([^"]+)"', html)), 'a duplicate id'
    hrefs = re.findall(r'\bhref="#([^"]+)"', html)
    missing = sorted({h for h in hrefs if h not in ids})
    assert not missing, f'{len(missing)} anchors do not resolve: {missing[:8]}'
    return len(hrefs)


def host_for(slug: str) -> str:
    return next(f'{sub}.cosmoes.org' for sub, s in HOSTS.items() if s == slug)

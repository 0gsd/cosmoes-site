"""A small export written to the export's format as scripts/build_specs.py leaves it (enough-dev's
docs/thym-landed-X1.md, section 2, plus the registry's fields and each source): the five documents the hosts serve
(the apex text among them), three densities and a source each, a manifest with the files' real hashes. Made fresh in a
temporary folder for each test, so a test may spoil its copy; the real site/specs/ is read only by the integrity tests."""
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
from cosmoes.app import create_app  # noqa: E402

# slug: (name, edition, lead, host), in the manifest's order; the apex text first
DOCS = {'oes': ('OES', '1', 'What an OES is, and how the specifications relate', 'cosmoes.org'),
        'macrocosm-oes': ('MacroCOSM OES', '0.0.2', 'MacroCOSM OES is the shared grammar every MiniCOSM is written in', 'macro.cosmoes.org'),
        'thym': ('Thym', '0', 'Version 0 of the language', 'thym.cosmoes.org'),
        'ascribe': ('Ascribe', '1', "Ascribe is the MiniCOSM for a person's holograph", 'ascribe.cosmoes.org'),
        'comprise-oes': ('Comprise OES', '1', 'The code in core/ is the reference reader and writer', 'comprise.cosmoes.org')}
DESCRIBES = {'oes': {}, 'macrocosm-oes': {'macrocosm': '0.0.2'}, 'thym': {'thym': '1'}, 'ascribe': {'ascribe': '1'},
             'comprise-oes': {'comprise': '1'}}
HOSTS = {'macro': 'macrocosm-oes', 'thym': 'thym', 'ascribe': 'ascribe', 'comprise': 'comprise-oes'}   # subdomain: slug
APEX_SLUG = 'oes'
REVISED = '2026-11-03'
EXPORTED = '2026-11-03T20:00:00Z'
PROV = ('Built from <a href="https://github.com/0gsd/cosmoes-site">cosmoes-site</a> at d2ea035, with uncommitted changes '
        'by enough 0.5.1 (DocOES), exported 3 Nov 2026.')
LICENCE = ("The texts are © 2026 Graham Smith, all rights reserved; the canonical editions are these pages. "
           "The site's code is Apache-2.0.")
CSS = '.docoes { color: var(--ink, #1a1f2b); }\n'


def source_text(slug: str, name: str) -> str:
    return f'# {name}\n\n<!-- atem: {DOCS[slug][2]} -->\nA **word** of {name}; see section 1.\n\n## 1. One\n\nA word.\n'


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
        name, edition, lead, host = DOCS[slug]
        files = {}
        for density in ('short', 'atem', 'fabula'):
            p = folder / slug / f'{density}.html'
            p.parent.mkdir(parents=True, exist_ok=True)
            p.write_text(fragment(slug, density, name), encoding='utf-8')
            raw = p.read_bytes()
            files[density] = {'path': f'{slug}/{density}.html', 'sha256': hashlib.sha256(raw).hexdigest(), 'bytes': len(raw)}
        src = folder / slug / 'source.md'
        src.write_text(source_text(slug, name), encoding='utf-8')
        raw = src.read_bytes()
        sha = hashlib.sha256(raw).hexdigest()
        files['source'] = {'path': f'{slug}/source.md', 'sha256': sha, 'bytes': len(raw)}
        docs.append({'slug': slug, 'name': name, 'version': edition, 'lang': 'en', 'id': f'doc/{slug}', 'oes': 'doc/1',
                     'lead': lead, 'source': {'path': f'specs/{slug}.md', 'sha256': sha}, 'chapters': [],
                     'counts': {'sections': 1, 'terms': 1, 'examples': 0, 'decisions': 0, 'reference': 0}, 'files': files,
                     'edition': edition, 'describes': dict(DESCRIBES[slug]), 'host': host, 'revised': REVISED,
                     'raw': dict(specs_mod.RAW)})
    m = {'format': specs_mod.FORMAT, 'exported': EXPORTED, 'by': 'enough/0.5.1', 'source': {'commit': 'd2ea035', 'dirty': True},
         'css': 'docs.css', 'pages': pages or dict(specs_mod.PAGES), 'standalone': False, 'documents': docs, **manifest}
    (folder / 'manifest.json').write_text(json.dumps(m, indent=1), encoding='utf-8')
    return folder


def rewrite(folder: Path, edit) -> None:
    """Change the export's manifest in place with `edit(manifest)`."""
    p = folder / 'manifest.json'
    m = json.loads(p.read_text(encoding='utf-8'))
    edit(m)
    p.write_text(json.dumps(m), encoding='utf-8')


def reseal(folder: Path, slug: str, which: str, text: str) -> None:
    """Write a fragment (or the source: which='source') and record its sha256 and size, so that only what it holds is
    under test."""
    p = folder / slug / (f'{which}.html' if which != 'source' else 'source.md')
    p.write_text(text, encoding='utf-8')
    raw = p.read_bytes()

    def edit(m):
        f = next(d for d in m['documents'] if d['slug'] == slug)['files'][which]
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
    return DOCS[slug][3]

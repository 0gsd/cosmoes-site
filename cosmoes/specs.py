"""The specifications' export (site/specs/): MacroCOSM OES, Thym, Ascribe and Comprise OES 1 as enough's DocOES exports
them (`python -m enough.docoes export`; enough-dev's docs/thym-landed-X1.md, section 2, is the format), each at three
densities: atem (one line per section), short (the readable text) and fabula (every item as a card).

The export lives in this repository, written only by scripts/sync_specs.py and committed with the code:

    site/specs/manifest.json            docoes-export/1: the documents, their versions, counts and files
    site/specs/docs.css                 the export's stylesheet: the fragments' look
    site/specs/<slug>/short.html        a fragment: <article class="docoes docoes-short" …>, no script, no style
    site/specs/<slug>/atem.html
    site/specs/<slug>/fabula.html

`Specs(folder)` reads all of it once, on first use, and keeps it: the folder never changes while the site runs. A
manifest that is missing, not JSON, another format or a standalone export counts as nothing published. A document is
left out, with a warning, when one of its fragments is missing, differs from the manifest's sha256, or carries
anything the pages would not include as it is: a script or style element (or another element that loads or submits
something), a style or event-handler attribute, a javascript: address. The pages include a fragment `|safe`, so this
is checked here as well as in the export and the sync. (Copied from comprise-connect's connect/macrocosmoes.py and
trimmed; the site depends on nothing of Connect's.)
"""
from __future__ import annotations

import datetime
import hashlib
import json
import logging
import re
import threading
from html.parser import HTMLParser
from pathlib import Path, PurePosixPath

log = logging.getLogger('cosmoes.specs')

FOLDER = Path(__file__).resolve().parent.parent / 'site' / 'specs'
FORMAT = 'docoes-export/1'
DENSITIES = ('atem', 'short', 'fabula')              # the density switch's order: the shortest first
TITLES = {'atem': 'one line per section', 'short': 'the readable text', 'fabula': 'every item as a card'}
PAGES = {'short': '/', 'atem': '/atem', 'fabula': '/fabula'}   # each density's address on its document's host
COUNTS = (('sections', 'section'), ('terms', 'term'), ('examples', 'example'), ('decisions', 'decision'),
          ('reference', 'reference item'))
SLUG_RE = re.compile(r'^[a-z0-9][a-z0-9-]{0,63}$')
SHA_RE = re.compile(r'^[0-9a-f]{64}$')
COMMIT_RE = re.compile(r'^[0-9a-f]{4,40}$')
BANNED_TEXT = ('<script', '<style')                 # anywhere, in any case
BANNED_TAGS = frozenset({'script', 'style', 'iframe', 'frame', 'object', 'embed', 'base', 'link', 'meta', 'form'})
URL_ATTRS = frozenset({'href', 'src', 'action', 'formaction', 'xlink:href'})


class _Unsafe(HTMLParser):
    """What in a fragment the site would not include as it is: a tag that loads, runs or submits, a style or on…
    attribute, a javascript: address. Attribute names come lower-cased and values unescaped from the parser."""

    def __init__(self):
        super().__init__(convert_charrefs=True)
        self.found: list[str] = []

    def handle_starttag(self, tag, attrs):
        if tag in BANNED_TAGS:
            self.found.append(f'<{tag}>')
        for name, value in attrs:
            if name == 'style' or re.fullmatch(r'on[a-z]+', name):
                self.found.append(f'{name}= on <{tag}>')
            elif name in URL_ATTRS and re.sub(r'[\s\x00-\x1f]+', '', value or '').lower().startswith(('javascript:', 'vbscript:')):
                self.found.append(f'a script address in {name}= on <{tag}>')


def unsafe(html: str) -> list[str]:
    """Why `html` cannot be included as it is: an empty list when it can."""
    low = html.lower()
    found = [t for t in BANNED_TEXT if t in low]
    p = _Unsafe()
    p.feed(html)
    p.close()
    return found + p.found


def count(n: int, one: str) -> str:
    """A count with its noun: 1 term, 68 terms."""
    return f'{n} {one if n == 1 else one + "s"}'


def parse_iso(s: str) -> datetime.datetime:
    t = datetime.datetime.fromisoformat(str(s).replace('Z', '+00:00'))
    if t.tzinfo is None:
        t = t.replace(tzinfo=datetime.timezone.utc)
    return t.astimezone(datetime.timezone.utc)


def date_text(t: datetime.datetime | None) -> str:
    """2 Nov 2026."""
    return f'{t.day} {t:%b %Y}' if t else ''


def _text(v, limit: int = 400) -> str:
    return v.strip()[:limit] if isinstance(v, str) else ''


def _int(v) -> int:
    return v if isinstance(v, int) and not isinstance(v, bool) and v >= 0 else 0


class Specs:
    """The synced export in `folder`, loaded once on first use. `documents` in the manifest's order, `get(slug)`,
    `page(slug, density)` (the fragment's HTML), `manifest(slug)` (that document's entry as a manifest of its own, or the
    whole manifest with no slug), `css` (docs.css's text), `meta` (when and from what it was exported; None when
    nothing is)."""

    def __init__(self, folder: Path | str):
        self.folder = Path(folder)
        self._lock = threading.Lock()
        self._loaded: dict | None = None

    # ------------------------------------------------------------------------- what the pages use

    @property
    def documents(self) -> list[dict]:
        return self._load()['documents']

    def get(self, slug: str) -> dict | None:
        return self._load()['by_slug'].get(slug)

    def page(self, slug: str, density: str) -> str | None:
        return self._load()['pages'].get((slug, density))

    def manifest(self, slug: str | None = None) -> dict | None:
        """The manifest as synced, its `documents` narrowed to `slug` when one is given (None for an unknown one)."""
        raw = self._load()['raw']
        if raw is None:
            return None
        if slug is None:
            return dict(raw, documents=[self._load()['entries'][d['slug']] for d in self.documents])
        entry = self._load()['entries'].get(slug)
        return dict(raw, documents=[entry]) if entry else None

    @property
    def css(self) -> str:
        return self._load()['css']

    @property
    def meta(self) -> dict | None:
        return self._load()['meta']

    # ------------------------------------------------------------------------- loading

    def _load(self) -> dict:
        if self._loaded is None:
            with self._lock:
                if self._loaded is None:
                    self._loaded = self._read()
        return self._loaded

    def _read(self) -> dict:
        out = {'documents': [], 'by_slug': {}, 'pages': {}, 'entries': {}, 'raw': None, 'css': '', 'meta': None}
        path = self.folder / 'manifest.json'
        try:
            m = json.loads(path.read_text(encoding='utf-8'))
        except FileNotFoundError:
            log.info('%s: no specs are exported here; the site says nothing is published', path)
            return out
        except (OSError, ValueError, UnicodeDecodeError) as e:
            log.warning('%s cannot be read (%s): nothing is served', path, e)
            return out
        if not isinstance(m, dict) or m.get('format') != FORMAT:
            log.warning('%s is not a %s manifest: nothing is served', path, FORMAT)
            return out
        if m.get('standalone'):
            log.warning('%s is a standalone export (full pages, for looking at locally): nothing is served', path)
            return out
        out['meta'] = self._meta(m)
        out['raw'] = {k: v for k, v in m.items() if k != 'documents'}
        try:
            out['css'] = (self.folder / str(m.get('css') or 'docs.css')).read_text(encoding='utf-8')
        except (OSError, UnicodeDecodeError) as e:
            log.warning('%s: the stylesheet cannot be read (%s); the pages go unstyled', path, e)
        for d in m.get('documents') if isinstance(m.get('documents'), list) else []:
            loaded = self._document(d)
            if not loaded:
                continue
            doc, pages = loaded
            if doc['slug'] in out['by_slug']:
                log.warning('%s: %s is listed twice; the first is served', path, doc['slug'])
                continue
            out['documents'].append(doc)
            out['by_slug'][doc['slug']] = doc
            out['entries'][doc['slug']] = d
            out['pages'].update({(doc['slug'], k): v for k, v in pages.items()})
        return out

    @staticmethod
    def _meta(m: dict) -> dict:
        try:
            exported = parse_iso(m['exported']) if m.get('exported') else None
        except (TypeError, ValueError):
            exported = None
        by = _text(m.get('by'), 80)
        source = m.get('source') if isinstance(m.get('source'), dict) else {}
        commit = _text(source.get('commit'), 40).lower()
        return {'exported': exported, 'by': by,
                'enough': by.split('/', 1)[1] if by.startswith('enough/') else '',
                'from': ('enough ' + by.split('/', 1)[1]) if by.startswith('enough/') else (by or 'enough'),
                'commit': commit if COMMIT_RE.match(commit) else '', 'dirty': source.get('dirty') is True}

    def _document(self, d) -> tuple[dict, dict] | None:
        slug = d.get('slug') if isinstance(d, dict) else None
        if not isinstance(slug, str) or not SLUG_RE.match(slug):
            log.warning('%s: a document without a usable slug is left out', self.folder)
            return None
        files = d.get('files') if isinstance(d.get('files'), dict) else {}
        pages, size = {}, 0
        for density in DENSITIES:
            got = self._fragment(slug, density, files.get(density))
            if got is None:
                return None
            pages[density], size = got[0], size + got[1]
        counts = d.get('counts') if isinstance(d.get('counts'), dict) else {}
        chapters = [{'name': _text(c.get('name'), 120), 'source': _text(c.get('source'), 200),
                     'commit': _text(c.get('commit'), 40), 'prefix': _text(c.get('prefix'), 40),
                     'version': _text(c.get('version'), 40)}
                    for c in (d.get('chapters') if isinstance(d.get('chapters'), list) else []) if isinstance(c, dict)]
        doc = {'slug': slug, 'name': _text(d.get('name'), 120) or slug, 'version': _text(d.get('version'), 40),
               'lang': _text(d.get('lang'), 16) or 'en', 'id': _text(d.get('id'), 120), 'oes': _text(d.get('oes'), 40),
               'lead': _text(d.get('lead'), 600), 'chapters': chapters, 'bytes': size,
               'counts': [count(_int(counts.get(k)), one) for k, one in COUNTS if _int(counts.get(k))]}
        return doc, pages

    def _fragment(self, slug: str, density: str, f) -> tuple[str, int] | None:
        """One fragment, checked: its HTML and size, or None (logged) when it cannot be served."""
        rel = f.get('path') if isinstance(f, dict) else None
        sha = f.get('sha256').lower() if isinstance(f, dict) and isinstance(f.get('sha256'), str) else ''
        p = PurePosixPath(rel) if isinstance(rel, str) and rel and '\\' not in rel else None
        if p is None or p.is_absolute() or '..' in p.parts or not SHA_RE.match(sha):
            log.warning('%s: %s has no usable %s file in the manifest; the document is left out', self.folder, slug, density)
            return None
        try:
            raw = self.folder.joinpath(*p.parts).read_bytes()
        except OSError:
            log.warning('%s: %s is missing; %s is left out', self.folder, rel, slug)
            return None
        if hashlib.sha256(raw).hexdigest() != sha:
            log.warning('%s: %s differs from the manifest (sha256); %s is left out', self.folder, rel, slug)
            return None
        try:
            html = raw.decode('utf-8')
        except UnicodeDecodeError:
            log.warning('%s: %s is not UTF-8; %s is left out', self.folder, rel, slug)
            return None
        bad = unsafe(html)
        if bad:
            log.warning('%s: %s carries %s, which the site never includes; %s is left out', self.folder, rel,
                        ', '.join(sorted(set(bad))), slug)
            return None
        return html, len(raw)

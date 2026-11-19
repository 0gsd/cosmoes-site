"""The language library as the site serves it: the shelf in library/ (library.json and each kept text's version
folder), read once and checked before anything is served, and its pages rendered by rule from the publisher's files.

The rules are client/library_index.py's (the same blocks and anchors the index records), so a section the index names
opens at the same anchor on the page. A kept text is served only when its folder verifies: NOTICE, FETCHED and
SHA256SUMS present, every file under files/ listed with its sha256 and nothing else, no marked gap left for the owner,
the registry's digest and file count matching. One that does not is left out and named in `refused`; the rest of the
shelf is served. Pinned texts (`aboard: false`) are listed, never served.
"""
from __future__ import annotations

import functools
import importlib.util
import logging
import sys
from pathlib import Path

from markupsafe import escape

HERE = Path(__file__).resolve().parent
ROOT = HERE.parent
FOLDER = ROOT / 'library'
log = logging.getLogger('cosmoes.library')


def _index_module():
    """client/library_index.py, loaded from its file (the image copies it to the same place)."""
    name = 'cosmoes_library_index'
    if name in sys.modules:
        return sys.modules[name]
    spec = importlib.util.spec_from_file_location(name, ROOT / 'client' / 'library_index.py')
    mod = importlib.util.module_from_spec(spec)
    sys.modules[name] = mod
    spec.loader.exec_module(mod)
    return mod


L = _index_module()
FORMS = L.FORMS
META_FILES = L.META_FILES

# How the raw route serves a publisher's file. Markup that a browser would run (HTML, SVG, XML) goes as plain text: the
# publisher's scripts never run on this origin.
RAW_TYPES = {'.txt': 'text/plain; charset=utf-8', '.md': 'text/plain; charset=utf-8', '.rst': 'text/plain; charset=utf-8',
             '.html': 'text/plain; charset=utf-8', '.htm': 'text/plain; charset=utf-8',
             '.xhtml': 'text/plain; charset=utf-8', '.svg': 'text/plain; charset=utf-8', '.xml': 'text/plain; charset=utf-8',
             '.json': 'application/json', '.csv': 'text/plain; charset=utf-8', '.toml': 'text/plain; charset=utf-8',
             '.yml': 'text/plain; charset=utf-8', '.yaml': 'text/plain; charset=utf-8', '.png': 'image/png',
             '.jpg': 'image/jpeg', '.jpeg': 'image/jpeg', '.gif': 'image/gif', '.pdf': 'application/pdf'}
RAW_DEFAULT = 'application/octet-stream'
RAW_CSP = "default-src 'none'; sandbox"


def raw_type(path: str, data: bytes) -> str:
    suffix = Path(path).suffix.lower()
    if suffix in RAW_TYPES:
        return RAW_TYPES[suffix]
    if suffix == '' or path.split('/')[-1].isupper():          # LICENSE, COPYRIGHT, PATENTS, README
        if b'\0' not in data[:8192]:
            return 'text/plain; charset=utf-8'
    return RAW_DEFAULT


class Text:
    """One kept text, verified: its registry entry, its folder, its pages (page path: `files/<path>`)."""

    def __init__(self, entry: dict, folder: Path):
        self.entry = entry
        self.folder = folder
        self.pages = L.page_files(folder, entry)
        self.files = [rel[len(L.FILES) + 1:] for rel in L.walk_files(folder)]
        self.notice = (folder / 'NOTICE').read_text(encoding='utf-8')

    @property
    def key(self) -> tuple[str, str, str]:
        return self.entry['shelf'], self.entry['text'], self.entry['version']

    @property
    def url(self) -> str:
        return '/library/{}/{}/{}/'.format(*self.key)

    @property
    def changed(self) -> str:
        return FORMS[self.entry['form']]['changed']

    def raw(self, path: str) -> bytes | None:
        if path not in self.files:
            return None
        return (self.folder / L.FILES / path).read_bytes()

    def meta(self, name: str) -> bytes | None:
        return (self.folder / name).read_bytes() if name in META_FILES else None


class Library:
    """The shelf at `folder`, read on first use. An absent folder or registry is an empty shelf (the site still
    serves the specifications)."""

    def __init__(self, folder: Path | str | None = None):
        self.folder = Path(folder) if folder else FOLDER
        self._loaded = False
        self.shelves: list[dict] = []
        self.texts: dict[tuple[str, str, str], Text] = {}
        self.pins: list[dict] = []
        self.refused: dict[str, list[str]] = {}
        self.problems: list[str] = []
        self.registry_bytes: bytes | None = None    # library.json as it is on disk, kept only when it validates

    def load(self) -> 'Library':
        if self._loaded:
            return self
        self._loaded = True
        if not (self.folder / L.REGISTRY).is_file():
            return self
        try:
            reg = L.load_registry(self.folder)
        except ValueError as exc:
            self.problems = [f'library.json: {exc}']
            log.error('library: %s', self.problems[0])
            return self
        self.problems = L.validate_registry(reg)
        if self.problems:                       # a registry that does not validate serves nothing: say so in the log
            log.error('library: library.json refused: %s', '; '.join(self.problems))
            return self
        self.registry_bytes = (self.folder / L.REGISTRY).read_bytes()
        self.shelves = list(reg.get('shelves', []))
        for e in reg.get('texts', []):
            key = (e['shelf'], e['text'], e['version'])
            if not e.get('aboard'):
                self.pins.append(e)
                continue
            folder = L.text_dir(self.folder, e)
            problems = L.verify(folder, e)
            if problems:
                self.refused['/'.join(key)] = problems
                log.error('library: %s refused: %s', '/'.join(key), '; '.join(problems))
                continue
            self.texts[key] = Text(e, folder)
        return self

    def shelf(self, slug: str) -> dict | None:
        self.load()
        return next((s for s in self.shelves if s['slug'] == slug), None)

    def on_shelf(self, slug: str) -> tuple[list[Text], list[dict]]:
        """A shelf's kept texts and its pins, each in the registry's order."""
        self.load()
        return [t for k, t in self.texts.items() if k[0] == slug], [p for p in self.pins if p['shelf'] == slug]

    def text(self, shelf: str, text: str, version: str) -> Text | None:
        self.load()
        return self.texts.get((shelf, text, version))

    def versions(self, shelf: str, text: str) -> list[Text]:
        self.load()
        return [t for k, t in self.texts.items() if k[:2] == (shelf, text)]

    @functools.lru_cache(maxsize=256)
    def page(self, shelf: str, text: str, version: str, path: str) -> tuple[str, str] | None:
        """(title, the page's body as HTML) for one page, rendered by its form's rule; None when there is no such
        page. Everything from the publisher is escaped: no markup of theirs reaches the page."""
        t = self.text(shelf, text, version)
        if t is None or path not in t.pages:
            return None
        data = (t.folder / t.pages[path]).read_bytes()
        blks = L.blocks(t.entry['form'], data)
        title = next((b.text for b in _walk(blks) if b.kind == 'heading'), None) or path
        return title, render(blks)


def _walk(blks):
    for b in blks:
        yield b
        if b.kind == 'sig':
            yield from _walk(b.children)


def _id(anchor: str) -> str:
    return f' id="{escape(anchor)}"' if anchor else ''


def render(blks) -> str:
    """Blocks as HTML: a heading at its level (h1 to h6), a definition as its lines and an indented body, a rule marker
    as an anchored line, a paragraph, preformatted text. Every id is the block's anchor; aliases get their own line."""
    out = []
    for b in blks:
        if b.kind == 'heading':
            n = min(max(b.level, 1), 6)
            out.append(f'<h{n}{_id(b.anchor)}>{escape(b.text)}</h{n}>')
            out.extend(f'<span class="lib-alias"{_id(x)}></span>' for x in b.ids if x != b.anchor)
        elif b.kind == 'sig':
            out.append('<div class="lib-obj">')
            for k, line in enumerate(b.lines):
                ident = b.ids[k] if k < len(b.ids) else ''
                out.append(f'<p class="lib-sig"{_id(ident)}><code>{escape(line)}</code></p>')
            out.append(f'<div class="lib-body">{render(b.children)}</div></div>')
        elif b.kind == 'rule':
            out.append(f'<p class="lib-rule"{_id(b.anchor)}><code>r[{escape(b.text)}]</code></p>')
        elif b.kind == 'pre':
            out.append(f'<pre{_id(b.anchor)}>{escape(b.text)}</pre>')
        else:
            out.append(f'<p{_id(b.anchor)}>{escape(b.text)}</p>')
            out.extend(f'<span class="lib-alias"{_id(x)}></span>' for x in b.ids if x != b.anchor)
    return '\n'.join(out)

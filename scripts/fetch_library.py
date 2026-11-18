#!/usr/bin/env python3
"""Fetch one text of the language library's first shelf into library/, the owner's run only.

    python3 scripts/fetch_library.py list                         # every text this script knows, with its address
    python3 scripts/fetch_library.py fetch python/docs/3.13 --dry-run    # what it would do; fetches and writes nothing
    python3 scripts/fetch_library.py fetch python/docs/3.13       # at a terminal: asks before it fetches, then writes

Agents never run this without --dry-run: it downloads. The owner runs it at a terminal, where it asks, in order:
whether the address is the publisher's own (when it was not read for this version), whether each licence and each
name-and-mark rule page has been read whole, whether the licence files it found are the licence read, and whether the
copyright notice it took from the publisher's file is the notice (or for the notice typed in, when no rule finds it).
Anything but `yes` stops the run and writes nothing.

What a run writes, in a new folder that must not exist (a new version sits beside the old; nothing in a version folder
is edited after it is added):

    library/<shelf>/<text>/<version>/files/...   the publisher's files as they came (archive unpacked, top folder
                                                 stripped, links left out and named in FETCHED)
    library/<shelf>/<text>/<version>/FETCHED     when, from which address, the archive's name, size and sha256
    library/<shelf>/<text>/<version>/NOTICE      what the copy is, the licence named and linked, the copyright notice
                                                 verbatim, the change in form, and the licence files whole
    library/<shelf>/<text>/<version>/SHA256SUMS  every file under files/
    library/library.json                         the text's entry (aboard), added

Everything a NOTICE says about the licence comes from the publisher's own files, from the entry below (a name and an
address), or from the owner's typing; nothing else. Standard library only (python3 3.11 or later).
"""
from __future__ import annotations

import argparse
import datetime
import fnmatch
import hashlib
import json
import os
import posixpath
import shutil
import sys
import tarfile
import tempfile
import urllib.request
import zipfile
from dataclasses import dataclass, field
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / 'client'))
import library_index as L  # noqa: E402

LIBRARY = ROOT / 'library'
AGENT = 'cosmoes-library-fetch/1'

# How sure an address is. Only READ was read; the others are for the owner to confirm at the publisher's site.
READ = 'read'          # read on 2026-11-06 (survey G), or the archive's name is on disk from the owner's 0.7 fetch
PATTERN = 'pattern'    # the publisher's pattern for another version: not read for this one; the owner confirms it
SUPPLY = 'supply'      # the owner supplies it with --url (a commit or tag only the owner can look up)


@dataclass
class Entry:
    shelf: str
    text: str
    version: str
    name: str
    publisher: str
    what: str
    form: str
    lane: str
    url: str                                   # the publisher's own address for the archive or file
    url_status: str
    publisher_page: str                        # the publisher's own page for the text, linked from every page
    licence_name: str
    licence_url: str
    archive: str = 'tar'                       # tar (any compression), zip, or file (one file, saved as save_as)
    save_as: str = ''
    strip: bool = True                         # strip the archive's single top folder
    members: tuple = ()                        # globs (after the strip) to keep; () keeps everything
    pages: str = ''                            # the folder under files/ whose files are pages ('' for all)
    read_whole: tuple = ()                     # (address, status): pages the owner reads whole before saying yes
    licence_files: tuple = ()                  # paths under files/ that must be there; written whole into NOTICE
    copyright: tuple = ()                      # the rule that finds the notice: (rule, file, argument)
    extras: tuple = ()                         # (address, save_as, status): the publisher's other files, e.g. a licence
    sha256: str = ''                           # the archive's sha256 when the publisher lists one
    notes: tuple = ()                          # marked lines for the owner

    @property
    def key(self) -> str:
        return f'{self.shelf}/{self.text}/{self.version}'


ENTRIES: list[Entry] = [
    Entry('python', 'docs', '3.13', 'The Python documentation', 'Python Software Foundation', 'text', 'text', 'open',
          url='https://docs.python.org/3.13/archives/python-3.13-docs-text.tar.bz2', url_status=PATTERN,
          publisher_page='https://docs.python.org/3.13/',
          licence_name=('PSF License Version 2; examples, recipes and other code in the documentation are also under '
                        'the Zero-Clause BSD license'),
          licence_url='https://docs.python.org/3.13/license.html',
          read_whole=(('https://docs.python.org/3.13/license.html', PATTERN),
                      ('https://www.python.org/psf/trademarks/', PATTERN)),
          licence_files=('license.txt', 'copyright.txt'),
          copyright=('paragraphs', 'copyright.txt', 'Copyright'),
          notes=("OWNER: the archive's name is the 0.7 fetch's (fabulac-test-repos/_x0/library/python/3.13/); the "
                 "address follows docs.python.org/3.15/archives/ as read on 2026-11-06. Confirm it on "
                 "https://docs.python.org/3.13/download.html.",
                 'The version tally runs on (3.13.11 on this Mac). The 0.7 fetch is not moved in: it has no '
                 'source address, so it is fetched again.')),
    Entry('python', 'docs', '3.15', 'The Python documentation', 'Python Software Foundation', 'text', 'text', 'open',
          url='https://docs.python.org/3.15/archives/python-3.15-docs-text.tar.bz2', url_status=PATTERN,
          publisher_page='https://docs.python.org/3.15/',
          licence_name=('PSF License Version 2; examples, recipes and other code in the documentation are also under '
                        'the Zero-Clause BSD license'),
          licence_url='https://docs.python.org/3.15/license.html',
          read_whole=(('https://docs.python.org/3.15/license.html', PATTERN),
                      ('https://www.python.org/psf/trademarks/', PATTERN)),
          licence_files=('license.txt', 'copyright.txt'),
          copyright=('paragraphs', 'copyright.txt', 'Copyright'),
          notes=('OWNER: confirm 3.15 is the current release (3.15.0 was scheduled for October 2026) before '
                 'fetching; survey G saw python-3.15-docs-text.tar.bz2 listed on docs.python.org/3.15/archives/ '
                 '(3,500,631 bytes) on 2026-11-06.',)),
    Entry('ecmascript', 'ecma-262', '17.0', 'ECMA-262, ECMAScript 2026 Language Specification', 'Ecma International',
          'standard', 'html', 'open',
          url='https://262.ecma-international.org/17.0/', url_status=PATTERN, archive='file', save_as='index.html',
          publisher_page='https://262.ecma-international.org/17.0/',
          licence_name="Ecma International's alternative copyright notice (Ecma text copyright policy)",
          licence_url='https://ecma-international.org/policies/by-ipr/ecma-text-copyright-policy/',
          read_whole=(('https://ecma-international.org/policies/by-ipr/ecma-text-copyright-policy/', READ),),
          copyright=('html-id', 'index.html', 'sec-copyright-and-software-license'),
          notes=('OWNER: confirm the 17th edition (ECMAScript 2026) is published and its address; 16.0 is ES2025 '
                 "at the same pattern. Confirm the edition's own copyright annex carries the alternative notice (the "
                 'policy needs General Assembly approval for it), and that the page is whole without its scripts.',
                 'The shelf is titled ECMAScript: "JavaScript" is a mark of Oracle\'s.')),
    Entry('go', 'spec', '1.27', 'The Go Programming Language Specification', 'The Go Authors (Google)', 'standard',
          'html', 'open',
          url='https://go.dev/dl/go1.27.4.src.tar.gz', url_status=PATTERN,
          members=('doc/go_spec.html', 'LICENSE', 'PATENTS'),
          publisher_page='https://go.dev/ref/spec',
          licence_name='Creative Commons Attribution 4.0 International (go.dev/copyright: the site\'s contents)',
          licence_url='https://creativecommons.org/licenses/by/4.0/',
          read_whole=(('https://go.dev/copyright', READ),
                      ('https://creativecommons.org/licenses/by/4.0/legalcode', PATTERN),
                      ('https://go.dev/brand', PATTERN)),
          licence_files=('LICENSE', 'PATENTS'),
          copyright=('paragraphs', 'LICENSE', 'Copyright'),
          notes=('OWNER: go1.27.4 is the release found on this Mac on 2026-11-13; take the latest 1.27 patch from '
                 'https://go.dev/dl/ and pass its sha256 with --sha256 (the page lists one per file).',
                 'OWNER: confirm which licence governs doc/go_spec.html: go.dev/copyright says the site\'s contents '
                 'are CC BY 4.0, and the repository\'s LICENSE (kept whole in NOTICE) is BSD-style.')),
    Entry('rust', 'reference', '1.97', 'The Rust Reference', 'The Rust Project', 'text', 'markdown', 'open',
          url='https://github.com/rust-lang/reference/archive/<COMMIT>.tar.gz', url_status=SUPPLY, pages='src/',
          publisher_page='https://doc.rust-lang.org/1.97.0/reference/',
          licence_name='MIT or Apache License 2.0, at your option',
          licence_url='https://github.com/rust-lang/reference',
          read_whole=(('https://www.rust-lang.org/policies/licenses', PATTERN),
                      ('https://rustfoundation.org/policy/rust-trademark-policy/', PATTERN)),
          licence_files=('LICENSE-APACHE', 'LICENSE-MIT'),
          copyright=('paragraphs', 'LICENSE-MIT', 'Copyright'),
          notes=('OWNER: pass --url with the commit of rust-lang/reference that rust-lang/rust pins at '
                 'src/doc/reference for the 1.97 release (1.97.1 was on this Mac on 2026-11-13); look at '
                 'https://github.com/rust-lang/rust/tree/1.97.1/src/doc.',
                 'OWNER: confirm publisher_page (doc.rust-lang.org/<version>/reference/) and that LICENSE-MIT '
                 'carries a copyright line; if not, the run asks you to type the notice.')),
    Entry('rust', 'fls', '1.97', 'The FLS (Rust language specification, formerly the Ferrocene Language Specification)',
          'The Rust Project', 'text', 'rst', 'open',
          url='https://github.com/rust-lang/fls/archive/<TAG-OR-COMMIT>.tar.gz', url_status=SUPPLY, pages='src/',
          publisher_page='https://rust-lang.github.io/fls/',
          licence_name='MIT or Apache License 2.0, at your option',
          licence_url='https://github.com/rust-lang/fls',
          read_whole=(('https://github.com/rust-lang/fls', READ),
                      ('https://rustfoundation.org/policy/rust-trademark-policy/', PATTERN)),
          licence_files=('LICENSE-APACHE', 'LICENSE-MIT'),
          copyright=('paragraphs', 'LICENSE-MIT', 'Copyright'),
          notes=('OWNER: pass --url with the tag or commit of rust-lang/fls that covers Rust 1.97, and confirm '
                 'the repository has both licence files at its root and its source under src/.',)),
    Entry('json', 'rfc', '8259', 'RFC 8259, The JavaScript Object Notation (JSON) Data Interchange Format',
          'IETF (RFC Editor)', 'standard', 'unchanged', 'bound',
          url='https://www.rfc-editor.org/rfc/rfc8259.txt', url_status=PATTERN, archive='file', save_as='rfc8259.txt',
          publisher_page='https://www.rfc-editor.org/rfc/rfc8259',
          licence_name='IETF Trust Legal Provisions relating to IETF Documents (BCP 78)',
          licence_url='https://trustee.ietf.org/documents/trust-legal-provisions/tlp-5/',
          read_whole=(('https://trustee.ietf.org/documents/trust-legal-provisions/tlp-5/', READ),
                      ('https://www.rfc-editor.org/rfc/rfc8259', READ)),
          copyright=('section', 'rfc8259.txt', 'Copyright Notice'),
          notes=('Kept whole and served only as the publisher\'s own file (TLP 3.c.i: in full and without '
                 'modification); never rendered as a page.',)),
    Entry('unicode', 'ucd', '15.1.0', 'The Unicode Character Database', 'Unicode, Inc.', 'data', 'data', 'open',
          url='https://www.unicode.org/Public/15.1.0/ucd/UCD.zip', url_status=PATTERN, archive='zip',
          publisher_page='https://www.unicode.org/Public/15.1.0/ucd/',
          licence_name='Unicode License v3', licence_url='https://www.unicode.org/license.txt',
          read_whole=(('https://www.unicode.org/license.txt', PATTERN),
                      ('https://www.unicode.org/copyright.html', READ)),
          licence_files=('license.txt',),
          extras=(('https://www.unicode.org/license.txt', 'license.txt', PATTERN),),
          copyright=('paragraphs', 'license.txt', 'Copyright'),
          notes=("The version pinned: Python 3.13's unicodedata.unidata_version is 15.1.0 (3.14's is 16.0.0). A "
                 'version a transcoding names enters beside it.',
                 'The core specification is pinned, not kept (copyright.html 3.4: personal or internal use only).')),
]

BY_KEY = {e.key: e for e in ENTRIES}


# ----------------------------------------------------------------------------------------------- talking to the owner

class Stop(Exception):
    """The run stops here and writes nothing."""


def ask_yes(ask, question: str) -> None:
    if (ask(question + ' Type yes to go on: ') or '').strip().lower() != 'yes':
        raise Stop('stopped: no yes')


def plan(e: Entry, url: str, library: Path) -> list[str]:
    target = L.text_dir(library, {'shelf': e.shelf, 'text': e.text, 'version': e.version})
    suffixes = ', '.join(L.FORMS[e.form]['pages'])
    pages = (f'pages: the {suffixes} files' + (f' under files/{e.pages}' if e.pages else '')) if suffixes \
        else 'no pages: served as the publisher\'s file only'
    lines = [f'{e.key}: {e.name} {e.version}, published by {e.publisher}',
             f'  from          {url}' + ('' if e.url_status == READ and url == e.url else
                                         f'   [{e.url_status}: confirm it is the publisher\'s own address]'),
             f'  form          {e.form} ({pages})',
             f'  unpacks into  {target}/files/' + (f' (only {", ".join(e.members)})' if e.members else ''),
             f'  licence       {e.licence_name} <{e.licence_url}>']
    for u, st in e.read_whole:
        lines.append(f'  read whole    {u}' + ('' if st == READ else f'   [{st}: the address is for you to confirm]'))
    for f in e.licence_files:
        lines.append(f'  must find     files/{f} (written whole into NOTICE)')
    for u, name, st in e.extras:
        lines.append(f'  also fetches  {u} -> files/{name}' + ('' if st == READ else f'   [{st}]'))
    if e.copyright:
        lines.append(f'  notice from   {e.copyright[1]} by rule {e.copyright[0]} ({e.copyright[2]}); you confirm it')
    else:
        lines.append('  notice from   your typing (no rule)')
    if e.sha256:
        lines.append(f'  expects       sha256 {e.sha256}')
    for n in e.notes:
        lines.append(f'  note          {n}')
    if target.exists():
        lines.append(f'  REFUSED       {target} exists: a new version sits beside the old, never over it')
    return lines


# ----------------------------------------------------------------------------------------------- fetching and unpacking

def download(url: str, dest: Path) -> None:
    if not url.startswith('https://'):
        raise Stop(f'refused: {url} is not https')
    req = urllib.request.Request(url, headers={'User-Agent': AGENT})
    with urllib.request.urlopen(req, timeout=120) as r, open(dest, 'wb') as out:
        shutil.copyfileobj(r, out, 1 << 20)


def file_sha(path: Path) -> str:
    h = hashlib.sha256()
    with open(path, 'rb') as f:
        for chunk in iter(lambda: f.read(1 << 20), b''):
            h.update(chunk)
    return h.hexdigest()


def safe_name(name: str) -> str | None:
    """An archive member's path, or None when it would land outside the folder."""
    p = posixpath.normpath(name.replace('\\', '/'))
    if p.startswith('/') or p == '.' or p.startswith('../') or '/../' in f'/{p}/' or p == '..':
        return None
    return p


def unpack(e: Entry, archive: Path, into: Path) -> list[str]:
    """Unpack into `into` (files/), keeping regular files only; returns lines for FETCHED (what was stripped and what
    was left out)."""
    found: list[tuple[str, bytes]] = []
    left_out: list[str] = []
    if e.archive == 'file':
        found.append((e.save_as, archive.read_bytes()))
    elif e.archive == 'zip':
        with zipfile.ZipFile(archive) as z:
            for info in z.infolist():
                if info.is_dir():
                    continue
                name = safe_name(info.filename)
                if name is None or (info.external_attr >> 16) & 0o170000 == 0o120000:
                    left_out.append(info.filename)
                    continue
                found.append((name, z.read(info)))
    else:
        with tarfile.open(archive, 'r:*') as t:
            for m in t.getmembers():
                if m.isdir():
                    continue
                name = safe_name(m.name)
                if name is None or not m.isfile():
                    left_out.append(m.name)
                    continue
                found.append((name, t.extractfile(m).read()))
    notes = []
    tops = {n.split('/', 1)[0] for n, _ in found}
    if e.strip and e.archive != 'file' and len(tops) == 1 and all('/' in n for n, _ in found):
        top = tops.pop()
        found = [(n[len(top) + 1:], b) for n, b in found]
        notes.append(f'stripped: {top}/')
    if e.members:
        keep = [(n, b) for n, b in found if any(fnmatch.fnmatchcase(n, g) for g in e.members)]
        notes.append(f'kept: {", ".join(e.members)} ({len(keep)} of {len(found)} files)')
        found = keep
    for n, b in found:
        dest = into / n
        dest.parent.mkdir(parents=True, exist_ok=True)
        dest.write_bytes(b)
    if left_out:
        notes.append('left out (links, devices or paths outside the folder): ' + ', '.join(sorted(left_out)))
    return notes


# ----------------------------------------------------------------------------------------------- the notice

def find_copyright(e: Entry, files: Path) -> str | None:
    """The copyright notice, verbatim, by the entry's rule; None when the rule finds nothing."""
    if not e.copyright:
        return None
    rule, name, arg = e.copyright
    path = files / name
    if not path.is_file():
        return None
    data = path.read_bytes()
    if rule == 'paragraphs':                      # every paragraph whose first line starts with arg
        paras, cur = [], []
        for line in data.decode('utf-8', 'replace').splitlines():
            if line.strip():
                cur.append(line.rstrip())
            elif cur:
                paras.append(cur)
                cur = []
        if cur:
            paras.append(cur)
        paras = [p[2:] if len(p) > 1 and L.UNDERLINE_RE.match(p[1]) else p for p in paras]   # a title is not one
        hits = ['\n'.join(p) for p in paras if p and p[0].lstrip().startswith(arg)]
        return '\n\n'.join(hits) or None
    if rule == 'section':                         # the lines under a heading at the margin, to the next one
        lines = data.decode('utf-8', 'replace').splitlines()
        for i, line in enumerate(lines):
            if line.strip() == arg and not line.startswith(' '):
                body = []
                for nxt in lines[i + 1:]:
                    if nxt.strip() and not nxt.startswith(' '):
                        break
                    body.append(nxt.rstrip())
                text = '\n'.join(body).strip('\n')
                return text or None
        return None
    if rule == 'html-id':                         # the element with that id, to the next heading at its level
        blks = L.parse_html(data)
        for i, b in enumerate(blks):
            if arg in b.ids:
                level = b.level if b.kind == 'heading' else 7
                out = [] if b.kind == 'heading' else [b.text]          # the section's words, not its title
                for nb in blks[i + 1:]:
                    if nb.kind == 'heading' and nb.level <= level:
                        break
                    out.append(nb.text)
                text = '\n\n'.join(t for t in out if t)
                return text or None
        return None
    raise ValueError(f'unknown rule {rule}')


def notice_text(e: Entry, url: str, copyright_notice: str, licence_texts: list[tuple[str, str]], when: str) -> str:
    title = f'{e.name} {e.version}, as kept in the cosmoes.org library'
    head = [title, '=' * len(title), '',
            f'This folder is a copy of {e.name} {e.version}, kept at',
            L.address({'shelf': e.shelf, 'text': e.text, 'version': e.version}) + ', not the publisher\'s own page.',
            f'The publisher is {e.publisher}; its own page for this text is {e.publisher_page}',
            f'The files under files/ are the publisher\'s files as they came from {url}',
            f'on {when} (FETCHED, SHA256SUMS). Nothing in them is changed.', '',
            'Changed in form', '---------------', L.FORMS[e.form]['changed'], '',
            'Licence', '-------', f'{e.licence_name}', f'{e.licence_url}', '',
            'Copyright notice, as the publisher states it', '--------------------------------------------',
            copyright_notice.rstrip('\n'), '']
    for name, text in licence_texts:
        h = f'files/{name}, whole'
        head += [h, '-' * len(h), text.rstrip('\n'), '']
    return '\n'.join(head)


# ----------------------------------------------------------------------------------------------- the run

def fetch(e: Entry, library: Path, *, url: str | None = None, sha: str | None = None, from_archive: Path | None = None,
          ask=input, say=print, now: datetime.datetime | None = None) -> Path:
    """Fetch `e` into `library` and return the version folder. Every question goes through `ask`; anything but yes
    raises Stop and nothing is written. With `from_archive`, the archive is a file the owner already has (said to be
    the one at `url`), and nothing is downloaded."""
    library = Path(library)
    url = url or e.url
    if '<' in url:
        raise Stop(f'{e.key}: pass --url (the address holds a placeholder: {url})')
    meta = {'shelf': e.shelf, 'text': e.text, 'version': e.version}
    target = L.text_dir(library, meta)
    if target.exists():
        raise Stop(f'refused: {target} exists; a new version sits beside the old, never over it')
    reg = L.load_registry(library)
    if any((t['shelf'], t['text'], t['version']) == (e.shelf, e.text, e.version) for t in reg.get('texts', [])):
        raise Stop(f'refused: library.json already has {e.key}')
    for line in plan(e, url, library):
        say(line)
    if e.url_status != READ or url != e.url:
        ask_yes(ask, f'Is {url} the publisher\'s own address for {e.name} {e.version}?')
    for u, _ in e.read_whole:
        ask_yes(ask, f'Have you read {u} whole?')
    when = (now or datetime.datetime.now(datetime.timezone.utc)).strftime('%Y-%m-%dT%H:%M:%SZ')
    scratch = Path(tempfile.mkdtemp(prefix='.fetch-', dir=library))
    try:
        got = scratch / 'download'
        got.mkdir()
        name = e.save_as if e.archive == 'file' else (url.rstrip('/').rsplit('/', 1)[-1] or 'archive')
        archive = got / name
        if from_archive:
            shutil.copyfile(from_archive, archive)
        else:
            download(url, archive)
        digest = file_sha(archive)
        expected = sha or e.sha256
        if expected and digest != expected.lower():
            raise Stop(f'refused: the archive\'s sha256 is {digest}, not {expected}')
        folder = scratch / 'version'
        files = folder / L.FILES
        files.mkdir(parents=True)
        notes = unpack(e, archive, files)
        extra_lines = []
        for u, save_as, _ in e.extras:
            dest = files / save_as
            if dest.exists():
                raise Stop(f'refused: files/{save_as} came in the archive and is also an extra')
            if from_archive:
                raise Stop(f'{e.key} needs {u} as well; run without --from-archive')
            download(u, dest)
            extra_lines.append(f'extra: files/{save_as} from {u}, sha256 {file_sha(dest)}')
        if not any(files.rglob('*')):
            raise Stop('refused: the archive held no file to keep')
        licence_texts = []
        for f in e.licence_files:
            p = files / f
            if not p.is_file():
                raise Stop(f'refused: files/{f} is not in what was fetched; the licence must come with the text')
            licence_texts.append((f, p.read_text(encoding='utf-8', errors='replace')))
        for f, text in licence_texts:
            say(f'---- files/{f}, whole ----')
            say(text.rstrip('\n'))
            say(f'---- end of files/{f} ----')
            ask_yes(ask, f'Is files/{f} the licence you read?')
        notice = find_copyright(e, files)
        if notice:
            say('---- the copyright notice, as found ----')
            say(notice)
            say('---- end ----')
            if (ask('Is this the copyright notice, verbatim? Type yes, or no to type it yourself: ') or '').strip().lower() != 'yes':
                notice = None
        if not notice:
            say(f'Type the copyright notice exactly as {e.publisher} states it; end with a line holding only a dot.')
            typed = []
            while True:
                line = ask('')
                if line is None or line.strip() == '.':
                    break
                typed.append(line.rstrip('\n'))
            notice = '\n'.join(typed).strip('\n')
            if not notice:
                raise Stop('stopped: no copyright notice')
        fetched = [f'fetched: {when}', f'from: {url}', 'by: the owner, with scripts/fetch_library.py',
                   f'archive: {name}', f'archive-bytes: {archive.stat().st_size}', f'archive-sha256: {digest}']
        if from_archive:
            fetched.append(f'obtained-as: a file the owner already had ({Path(from_archive).name}), said to be the one at the address above')
        if e.url_status != READ or url != e.url:
            fetched.append('address-confirmed: by the owner at fetch time')
        fetched += [f'licence-read: {u}, read whole by the owner before this run' for u, _ in e.read_whole]
        fetched += notes + extra_lines
        (folder / 'FETCHED').write_text('\n'.join(fetched) + '\n', encoding='utf-8')
        (folder / 'NOTICE').write_text(notice_text(e, url, notice, licence_texts, when), encoding='utf-8')
        (folder / 'SHA256SUMS').write_text(L.sums_text(folder), encoding='utf-8')
        entry = registry_entry(e, folder, url, notice, when)
        problems = L.verify(folder, entry) + L.validate_registry(dict(reg, texts=reg.get('texts', []) + [entry]))
        if problems:
            raise Stop('refused: ' + '; '.join(problems))
        target.parent.mkdir(parents=True, exist_ok=True)
        os.replace(folder, target)
        write_registry(library, reg, entry)
    finally:
        shutil.rmtree(scratch, ignore_errors=True)
    say(f'wrote {target} and its entry in library.json ({entry["files"]} files, {entry["digest"]})')
    return target


def registry_entry(e: Entry, folder: Path, url: str, notice: str, when: str) -> dict:
    entry = {'shelf': e.shelf, 'text': e.text, 'version': e.version, 'name': e.name, 'publisher': e.publisher,
             'what': e.what, 'form': e.form, 'lane': e.lane, 'aboard': True,
             'licence': {'name': e.licence_name, 'url': e.licence_url}, 'copyright': notice,
             'publisher_page': e.publisher_page, 'from': url, 'obtained': when,
             'files': len(L.walk_files(folder)), 'digest': L.folder_digest(folder),
             'address': L.address({'shelf': e.shelf, 'text': e.text, 'version': e.version})}
    if e.pages:
        entry['pages'] = e.pages
    return entry


def write_registry(library: Path, reg: dict, entry: dict) -> None:
    order = {s['slug']: i for i, s in enumerate(reg.get('shelves', []))}
    texts = sorted(reg.get('texts', []) + [entry],
                   key=lambda t: (order.get(t['shelf'], len(order)), t['text'], not t.get('aboard'), t['version']))
    out = dict(reg, texts=texts)
    (Path(library) / L.REGISTRY).write_text(json.dumps(out, indent=2, ensure_ascii=False) + '\n', encoding='utf-8')


# ----------------------------------------------------------------------------------------------- the command line

def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description="Fetch one text of the library's first shelf (the owner's run).")
    sub = ap.add_subparsers(dest='cmd', required=True)
    sub.add_parser('list', help='every text this script knows, with its address and how sure it is')
    f = sub.add_parser('fetch', help='fetch one text into library/')
    f.add_argument('key', help='shelf/text/version, as `list` prints it')
    f.add_argument('--dry-run', action='store_true', help='print what it would do; fetch and write nothing')
    f.add_argument('--url', help="the publisher's address, when the entry's is a placeholder or has moved")
    f.add_argument('--sha256', help="the archive's sha256 as the publisher lists it")
    f.add_argument('--from-archive', type=Path, help='an archive already on disk, said to be the one at the address')
    f.add_argument('--library', type=Path, default=LIBRARY)
    args = ap.parse_args(argv)
    if args.cmd == 'list':
        for e in ENTRIES:
            print(f'{e.key:28} {e.url_status:8} {e.form:10} {e.url}')
        return 0
    e = BY_KEY.get(args.key)
    if e is None:
        print(f'no such text: {args.key} (see `list`)', file=sys.stderr)
        return 2
    if args.dry_run:
        for line in plan(e, args.url or e.url, args.library):
            print(line)
        print('dry run: nothing fetched, nothing written')
        return 0
    if not sys.stdin.isatty():
        print('refused: run this at a terminal (it asks before it fetches); --dry-run needs none', file=sys.stderr)
        return 2
    def ask(prompt: str) -> str | None:
        try:
            return input(prompt)
        except EOFError:
            return None

    try:
        fetch(e, args.library, url=args.url, sha=args.sha256, from_archive=args.from_archive, ask=ask)
    except Stop as exc:
        print(exc, file=sys.stderr)
        return 1
    except (OSError, tarfile.TarError, zipfile.BadZipFile) as exc:
        print(f'stopped: {exc}; nothing written', file=sys.stderr)
        return 1
    return 0


if __name__ == '__main__':
    sys.exit(main())

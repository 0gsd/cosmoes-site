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
    credit: tuple = ()                         # lines the publisher's terms ask every copy to carry (a statement
                                               # of what was copied, a mark's legend): in NOTICE and on every page

    @property
    def key(self) -> str:
        return f'{self.shelf}/{self.text}/{self.version}'


# Addresses marked READ were read on the publisher's own pages on 2026-11-22 (the 0.9 build, lane LIB), by a fetch
# tool that saved nothing; what each was read on is in its notes. The Rust texts' commits were read; their archive
# addresses follow GitHub's pattern (github.com/<owner>/<repo>/archive/<commit>.tar.gz), so the run asks about them.
RUST_TM = 'https://rustfoundation.org/policy/rust-trademark-policy/'


def rust_reference(version: str, release: str, commit: str, note: str) -> Entry:
    return Entry('rust', 'reference', version, 'The Rust Reference', 'The Rust Project', 'text', 'markdown', 'open',
                 url=f'https://github.com/rust-lang/reference/archive/{commit}.tar.gz', url_status=PATTERN, pages='src/',
                 publisher_page=f'https://doc.rust-lang.org/{release}/reference/',
                 licence_name='MIT or Apache License 2.0, at your option',
                 licence_url='https://github.com/rust-lang/reference',
                 read_whole=(('https://www.rust-lang.org/policies/licenses', PATTERN), (RUST_TM, READ)),
                 licence_files=('LICENSE-APACHE', 'LICENSE-MIT'),
                 copyright=('paragraphs', 'LICENSE-MIT', 'Copyright'),
                 notes=(f'The commit is the one rust-lang/rust {release} pins at src/doc/reference (read through '
                        f'https://api.github.com/repos/rust-lang/rust/contents/src/doc/reference?ref={release}). '
                        'The repository has LICENSE-APACHE and LICENSE-MIT at its root; LICENSE-MIT\'s first line is '
                        'its copyright line.', note))


def rust_fls(version: str, commit: str, note: str) -> Entry:
    return Entry('rust', 'fls', version,
                 'The FLS (Rust language specification, formerly the Ferrocene Language Specification)',
                 'The Rust Project', 'text', 'rst', 'open',
                 url=f'https://github.com/rust-lang/fls/archive/{commit}.tar.gz', url_status=PATTERN, pages='src/',
                 publisher_page='https://rust-lang.github.io/fls/',
                 licence_name='MIT or Apache License 2.0, at your option (README.rst; each file\'s SPDX header)',
                 licence_url='https://github.com/rust-lang/fls',
                 read_whole=(('https://github.com/rust-lang/fls', READ), (RUST_TM, READ)),
                 licence_files=('LICENSES/Apache-2.0.txt', 'LICENSES/MIT.txt', 'LICENSES/*'),
                 copyright=('spdx', 'src', 'SPDX-FileCopyrightText'),
                 notes=(f'The commit is the one tag {version} names on rust-lang/fls (read through '
                        'https://api.github.com/repos/rust-lang/fls/tags). The FLS keeps its licences in LICENSES/ '
                        '(Apache-2.0, MIT, CC-BY-4.0, OFL-1.1), not LICENSE-* at the root; LICENSES/MIT.txt is the '
                        'blank template, so the notice is taken from the SPDX-FileCopyrightText lines under src/.',
                        note))


ENTRIES: list[Entry] = [
    Entry('python', 'docs', '3.13', 'The Python documentation', 'Python Software Foundation', 'text', 'text', 'open',
          url='https://docs.python.org/3.13/archives/python-3.13-docs-text.tar.bz2', url_status=READ,
          publisher_page='https://docs.python.org/3.13/',
          licence_name=('PSF License Version 2; examples, recipes and other code in the documentation are also under '
                        'the Zero-Clause BSD license'),
          licence_url='https://docs.python.org/3.13/license.html',
          read_whole=(('https://docs.python.org/3.13/license.html', READ),
                      ('https://www.python.org/psf/trademarks/', READ)),
          licence_files=('license.txt', 'copyright.txt'),
          copyright=('paragraphs', 'copyright.txt', 'Copyright'),
          notes=('Aboard since 2026-11-19 (build 3.13.18). On 2026-11-22 docs.python.org/3.13/download.html is still '
                 '3.13.18 and the archive is still 3,156,138 bytes (dated 29-Oct-2026), the size kept: nothing to fetch.',
                 'The version tally runs on (3.13.11 on this Mac).')),
    Entry('python', 'docs', '3.15', 'The Python documentation', 'Python Software Foundation', 'text', 'text', 'open',
          url='https://docs.python.org/3.15/archives/python-3.15-docs-text.tar.bz2', url_status=READ,
          publisher_page='https://docs.python.org/3.15/',
          licence_name=('PSF License Version 2; examples, recipes and other code in the documentation are also under '
                        'the Zero-Clause BSD license'),
          licence_url='https://docs.python.org/3.15/license.html',
          read_whole=(('https://docs.python.org/3.15/license.html', PATTERN),
                      ('https://www.python.org/psf/trademarks/', READ)),
          licence_files=('license.txt', 'copyright.txt'),
          copyright=('paragraphs', 'copyright.txt', 'Copyright'),
          notes=('The current release: python.org/downloads names 3.15.2 (2026-10-25) the latest; '
                 'docs.python.org/3.15/download.html is the 3.15.2 build, and docs.python.org/3.15/archives/ lists '
                 'python-3.15-docs-text.tar.bz2 at 3,514,286 bytes, dated 19-Nov-2026 (read 2026-11-22).',)),
    Entry('ecmascript', 'ecma-262', '17.0', 'ECMA-262, ECMAScript 2026 Language Specification', 'Ecma International',
          'standard', 'html', 'open',
          url='https://262.ecma-international.org/17.0/index.html', url_status=READ, archive='file',
          save_as='index.html',
          publisher_page='https://262.ecma-international.org/17.0/',
          licence_name="Ecma International's alternative copyright notice and copyright license (the edition's annex)",
          licence_url='https://ecma-international.org/policies/by-ipr/ecma-text-copyright-policy/',
          read_whole=(('https://ecma-international.org/policies/by-ipr/ecma-text-copyright-policy/', READ),
                      ('https://ecma-international.org/policies/by-ipr/ecma-trademark-matters/', READ)),
          copyright=('html-id', 'index.html', 'sec-copyright-and-software-license'),
          credit=('This copy includes material copied from or derived from ECMAScript® 2026 Language Specification '
                  '(ECMA-262, 17th edition, June 2026), https://262.ecma-international.org/17.0/index.html.',
                  'ECMAScript® is a registered trademark of Ecma International.'),
          notes=('The 17th edition, June 2026, is current: ecma-international.org/publications-and-standards/'
                 'standards/ecma-262/ names https://262.ecma-international.org/17.0/index.html the normative HTML copy '
                 '(read 2026-11-22). The annex (sec-copyright-and-software-license) carries the ALTERNATIVE notice, '
                 'read on the tc39.es 2026 snapshot of the same edition: confirm the notice the run shows says so.',
                 'Only index.html is kept: its stylesheet, script and images are not, and pages come from its text. '
                 'The shelf is titled ECMAScript: "JavaScript" is a mark of Oracle\'s.')),
    Entry('go', 'spec', '1.27', 'The Go Programming Language Specification', 'The Go Authors (Google)', 'standard',
          'html', 'open',
          url='https://go.dev/dl/go1.27.4.src.tar.gz', url_status=READ,
          sha256='73cfb8571aec0c01177687db87163d46aa20e9779672772891aa17654d9a6099',
          members=('doc/go_spec.html', 'LICENSE', 'PATENTS'),
          publisher_page='https://go.dev/ref/spec',
          licence_name='Creative Commons Attribution 4.0 International (go.dev/copyright: the site\'s contents)',
          licence_url='https://creativecommons.org/licenses/by/4.0/',
          read_whole=(('https://go.dev/copyright', READ),
                      ('https://creativecommons.org/licenses/by/4.0/legalcode.en', READ),
                      ('https://go.dev/brand', READ)),
          licence_files=('LICENSE', 'PATENTS'),
          copyright=('paragraphs', 'LICENSE', 'Copyright'),
          credit=('The Go Programming Language Specification (language version go1.27, May 26, 2026), by The Go '
                  'Authors, https://go.dev/ref/spec, under the Creative Commons Attribution 4.0 International licence, '
                  'https://creativecommons.org/licenses/by/4.0/. Its pages here are made from a text extraction.',),
          notes=('go1.27.4 is the newest stable release on https://go.dev/dl/ (read 2026-11-22): go1.27.4.src.tar.gz, '
                 '34 MB, with the sha256 above. Only doc/go_spec.html, LICENSE and PATENTS are kept.',
                 'OWNER: go_spec.html carries no notice of its own. go.dev/copyright puts the site\'s contents under '
                 'CC BY 4.0 and its code under the BSD licence; the repository\'s LICENSE (BSD 3-clause naming '
                 'Google LLC) is kept whole beside it. The entry names CC BY 4.0.')),
    rust_reference('1.100', '1.100.0', 'e24eecf97b0c9a6dbac67191098204dc8a190aaa',
                   'Rust 1.100.0 (2026-11-12) is the current release (blog.rust-lang.org/releases/latest).'),
    rust_reference('1.97', '1.97.1', 'ad35aca481751a06afeb23820a672b0f3b11a476',
                   'The release the 0.8 cshorts were built on (rustc 1.97.1 on this Mac, 2026-11-13).'),
    rust_fls('1.99', '946eacae5a4a33a89af7832178504692439e7478',
             'The newest tag on 2026-11-22: there is no 1.100 tag yet (version.rst: spec_version 1.99.0).'),
    rust_fls('1.97', '4ab04b009042e6ab56e07cbe187b0b52988da308',
             'The release the 0.8 cshorts were built on (rustc 1.97.1).'),
    Entry('json', 'rfc', '8259', 'RFC 8259, The JavaScript Object Notation (JSON) Data Interchange Format',
          'IETF (RFC Editor)', 'standard', 'unchanged', 'bound',
          url='https://www.rfc-editor.org/rfc/rfc8259.txt', url_status=READ, archive='file', save_as='rfc8259.txt',
          publisher_page='https://www.rfc-editor.org/rfc/rfc8259',
          licence_name='IETF Trust Legal Provisions relating to IETF Documents (BCP 78)',
          licence_url='https://trustee.ietf.org/documents/trust-legal-provisions/tlp-5/',
          read_whole=(('https://trustee.ietf.org/documents/trust-legal-provisions/tlp-5/', READ),
                      ('https://www.rfc-editor.org/rfc/rfc8259', READ)),
          copyright=('section', 'rfc8259.txt', 'Copyright Notice'),
          notes=('Kept whole and served only as the publisher\'s own file (TLP 3.c.i: in full and without '
                 'modification); never rendered as a page. Its "Copyright Notice" heading is at the margin and its '
                 'body indented, as the section rule reads it (read 2026-11-22).',)),
    Entry('unicode', 'ucd', '15.1.0', 'The Unicode® Character Database', 'Unicode, Inc.', 'data', 'data', 'open',
          url='https://www.unicode.org/Public/15.1.0/ucd/UCD.zip', url_status=READ, archive='zip',
          publisher_page='https://www.unicode.org/Public/15.1.0/ucd/',
          licence_name='Unicode License v3', licence_url='https://www.unicode.org/license.txt',
          read_whole=(('https://www.unicode.org/license.txt', READ),
                      ('https://www.unicode.org/copyright.html', READ),
                      ('https://www.unicode.org/policies/logo_policy.html', READ)),
          licence_files=('license.txt',),
          extras=(('https://www.unicode.org/license.txt', 'license.txt', READ),),
          copyright=('paragraphs', 'license.txt', 'Copyright'),
          credit=('Unicode and the Unicode Logo are registered trademarks of Unicode, Inc. in the United States and '
                  'other countries.',),
          notes=("Python 3.13's unicodedata names UCD 15.1.0 (docs.python.org/3.13/library/unicodedata.html). "
                 'www.unicode.org/Public/15.1.0/ucd/ lists UCD.zip, 7.9M, dated 2023-08-28 (read 2026-11-22).',
                 'license.txt is today\'s (Copyright © 1991-2026), fetched beside the zip, which holds none.',
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
    for c in e.credit:
        lines.append(f'  carries       {c}')
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
    was left out). Names are settled first (the strip, then `members`), and only the files kept are read, so a large
    source archive of which one file is kept is never held whole in memory."""
    names: list[tuple[str, object]] = []          # (the path kept under files/, the member to read it from)
    left_out: list[str] = []
    notes = []
    if e.archive == 'file':
        (into / e.save_as).parent.mkdir(parents=True, exist_ok=True)
        (into / e.save_as).write_bytes(archive.read_bytes())
        return notes
    if e.archive == 'zip':
        opened = zipfile.ZipFile(archive)
        for info in opened.infolist():
            if info.is_dir():
                continue
            name = safe_name(info.filename)
            if name is None or (info.external_attr >> 16) & 0o170000 == 0o120000:
                left_out.append(info.filename)
                continue
            names.append((name, info))
        read = opened.read
    else:
        opened = tarfile.open(archive, 'r:*')
        for m in opened.getmembers():
            if m.isdir():
                continue
            name = safe_name(m.name)
            if name is None or not m.isfile():
                left_out.append(m.name)
                continue
            names.append((name, m))
        read = lambda m: opened.extractfile(m).read()  # noqa: E731
    with opened:
        tops = {n.split('/', 1)[0] for n, _ in names}
        if e.strip and len(tops) == 1 and all('/' in n for n, _ in names):
            top = tops.pop()
            names = [(n[len(top) + 1:], m) for n, m in names]
            notes.append(f'stripped: {top}/')
        if e.members:
            keep = [(n, m) for n, m in names if any(fnmatch.fnmatchcase(n, g) for g in e.members)]
            notes.append(f'kept: {", ".join(e.members)} ({len(keep)} of {len(names)} files)')
            names = keep
        for n, m in names:
            dest = into / n
            dest.parent.mkdir(parents=True, exist_ok=True)
            dest.write_bytes(read(m))
    if left_out:
        notes.append('left out (links, devices or paths outside the folder): ' + ', '.join(sorted(left_out)))
    return notes


# ----------------------------------------------------------------------------------------------- the notice

def find_copyright(e: Entry, files: Path) -> str | None:
    """The copyright notice, verbatim, by the entry's rule; None when the rule finds nothing."""
    if not e.copyright:
        return None
    rule, name, arg = e.copyright
    if rule == 'spdx':                            # every distinct `<arg>: <holder>` line in the files under name/
        seen: list[str] = []
        for path in sorted(p for p in (files / name).rglob('*') if p.is_file()):
            for line in path.read_bytes().decode('utf-8', 'replace').splitlines():
                at = line.find(arg + ':')
                if at < 0:
                    continue
                held = f'{arg}: {line[at + len(arg) + 1:].strip()}'
                if held.endswith(('-->', '*/')):
                    held = held[:-3].rstrip()
                if held != f'{arg}:' and held not in seen:
                    seen.append(held)
        return '\n'.join(seen) or None
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


def licence_paths(e: Entry, files: Path) -> list[str]:
    """The licence files under files/, in the entry's order: a plain path must be there; a glob (`LICENSES/*`) must
    match at least one file, and adds every file it matches. Each path once."""
    out: list[str] = []
    for f in e.licence_files:
        if any(c in f for c in '*?['):
            hits = sorted(p.relative_to(files).as_posix() for p in files.glob(f) if p.is_file())
            if not hits:
                raise Stop(f'refused: no file matches files/{f}; the licence must come with the text')
        else:
            if not (files / f).is_file():
                raise Stop(f'refused: files/{f} is not in what was fetched; the licence must come with the text')
            hits = [f]
        out += [h for h in hits if h not in out]
    return out


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
    if e.credit:
        head += ['What the terms ask every copy to carry', '--------------------------------------', *e.credit, '']
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
        for f in licence_paths(e, files):
            licence_texts.append((f, (files / f).read_text(encoding='utf-8', errors='replace')))
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
    if e.credit:
        entry['credit'] = '\n'.join(e.credit)
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

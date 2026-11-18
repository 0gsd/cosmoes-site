# The library

The languages and standards the fabulacs lean on, kept in their publishers' own words. Each text is the publisher's
files as they came, with its own licence and copyright notice, served as pages at
`https://cosmoes.org/library/<shelf>/<text>/<version>/<path>` on the apex host. A text that may not be copied is pinned
by name and version and never kept. Nothing here is an OES specification: the library is never in `specs/specs.json`,
so neither the word check nor the DocOES export reads it.

A shelf is a language or a standard; both are the same kind of thing, so a new language or standard adds a shelf and
changes no structure. The JavaScript shelf is titled **ECMAScript**: "JavaScript" is a mark of Oracle's, and the text
on it is ECMA-262.

## The folder

```text
library/
  README.md, NOTICE.md            this file; what the copies are and are not
  library.json                    the registry (below)
  <shelf>/<text>/<version>/       one kept text at one version, written once by scripts/fetch_library.py
    files/...                     the publisher's files as they came: the archive unpacked, its top folder stripped
    FETCHED                       when, from which address, the archive's name, size and sha256, what was left out
    NOTICE                        what this copy is, the licence named and linked, the copyright notice verbatim, the
                                  change in form, and the licence files found in the publisher's files, whole
    SHA256SUMS                    `<sha256>  files/<path>` for every file under files/
```

Nothing in a version folder is edited after it is added; a new version sits beside the old. A version folder whose
files do not match its SHA256SUMS, whose registry digest is not the sha256 of its SHA256SUMS, or whose NOTICE holds a
gap marked `[OWNER:` is not served (the site logs why and serves the rest).

## The first shelf (ruled 2026-11-06; nothing is kept until the owner's fetch)

| shelf | text | version | kept as | licence |
|---|---|---|---|---|
| python | docs | 3.13 (tally's) and the current release | the publisher's plain-text build, pages by the plain-text rule | PSF License v2; examples also 0BSD |
| ecmascript | ecma-262 | 17.0 (ES2026) | the publisher's HTML whole; pages from a text extraction | Ecma's alternative copyright notice |
| go | spec | 1.27 | `doc/go_spec.html`, `LICENSE`, `PATENTS` from the release's source archive; pages from a text extraction | CC BY 4.0 (go.dev/copyright); the repository's BSD-style LICENSE beside it |
| rust | reference | 1.97 | the repository at the commit the release pins, pages from `src/*.md` | MIT or Apache-2.0 |
| rust | fls | 1.97 | the repository at the tag or commit for the release, pages from `src/*.rst` | MIT or Apache-2.0 |
| json | rfc | 8259 | `rfc8259.txt` whole, served only as the publisher's file, never as a page | IETF Trust Legal Provisions (BCP 78) |
| unicode | ucd | 15.1.0 (Python 3.13's) | the data files whole, each shown as preformatted text | Unicode License v3 |

Pinned only, in `library.json` with `aboard: false`: the Unicode Standard's core text (personal or internal use only),
IEEE 754-2019 (sold), test262 (ECMA-262's conformance tests), and the implementations (CPython 3.13, the Go toolchain
1.27, rustc 1.97). Implementations and tests are pinned by release, digest and software hash identifier, never copied.
C is left out.

## `library.json`

`format: cosmoes-library/1`, `shelves` (`slug`, `title`, `kind`: `language` or `standard`, `about`), and `texts`, one
entry per text:

| field | |
|---|---|
| `shelf`, `text`, `version` | the address's three parts |
| `name`, `publisher` | as the publisher names them |
| `what` | `text`, `standard`, `data`, `tests`, `implementation` or `draft` |
| `lane` | the licence's lane: `open` (may be changed and passed on), `bound` (passed on unchanged only), `closed` |
| `aboard` | `true`: kept here; `false`: pinned only |
| `form` | kept texts: `text`, `rst`, `markdown`, `html`, `data` or `unchanged` (how pages are made; `unchanged`: none) |
| `pages` | optional: the folder under `files/` whose files are pages (`src/` for the Rust texts) |
| `licence` | `{name, url}` |
| `copyright` | the publisher's copyright notice, verbatim, as the fetch found or the owner typed it |
| `publisher_page` | the publisher's own page for the text, linked from every page |
| `from`, `obtained` | the address it was fetched from, and when |
| `files`, `digest` | how many files are kept, and `sha256:` of SHA256SUMS |
| `address` | `https://cosmoes.org/library/<shelf>/<text>/<version>/` |
| `release`, `swhid`, `note` | pins: the exact release, the software hash identifier, what is still to fill |

Kept entries are written by the fetch script, never by hand; pins are written by hand.

## The tools

- `scripts/fetch_library.py`, **the owner's run**: `list`, then `fetch <shelf>/<text>/<version> --dry-run`, then the
  same without `--dry-run` at a terminal. It asks before it fetches (the address when it was not read, each licence
  and each name-and-mark page read whole), shows each licence file it found whole, takes the copyright notice from
  the publisher's file by rule (or the owner types it), and writes the version folder and its entry. It refuses a
  folder that exists. Agents never run it without `--dry-run`.
- `client/library_index.py`: `verify` checks the registry and every kept folder; `build --out <file>` makes one SQLite
  file from the files alone (texts, files, sections with anchors, heading paths and a sha256 each, full-text search),
  never edited by hand and never committed; `build --check` says whether an index is current. enough vendors it.
- `cosmoes/library.py` and `cosmoes/app.py`: the routes (`/library/`, `/library/<shelf>/`,
  `/library/<shelf>/<text>/<version>/`, `.../<page>`, `.../raw/<path>`, `.../NOTICE`, `.../FETCHED`,
  `.../SHA256SUMS`).

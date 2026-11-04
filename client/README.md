# `client/cosmoes_client.py`: the one sync client

The applications that read the OES specifications (enough, Comprise, comprise-connect) all keep a local copy of what
cosmoes.org publishes and refresh it the same way: once per launch or on a timer, in the background, from the manifest
down, fetching only what changed. This file is that way, written once. **This is the canonical copy.** An app vendors
it as a single file, unchanged, and records beside its copy the cosmoes-site commit it took (`git log -1 --format=%h --
client/cosmoes_client.py`). A fix is made here and taken again; an app never forks it. Standard library only, Python
3.11+; it imports nothing of the site, and the site imports nothing of it.

## The contract it reads

`GET https://cosmoes.org/manifest.json` (`docoes-export/1`): a `documents` list. Each document has `slug`, `name`,
`version` (an `edition`, when present, is the version), `host` (`macro.cosmoes.org`, …; a document without a host is
skipped, nothing is derived), `revised`, `source` `{path, sha256}`, `files` `{short|atem|fabula: {path, sha256,
bytes}}` and `raw` (`{"source": "/raw/source.md", "short": "/raw/short.html", "atem": "/raw/atem.html", "fabula":
"/raw/fabula.html"}`; exactly those paths when `raw` is absent). A document's raw files are on its host:
`https://<host><raw path>`.

Only hosts equal to `cosmoes.org` or ending in `.cosmoes.org` are ever fetched, over HTTPS with certificates verified,
whatever a manifest says; a host outside that is an error for its document. Every body is checked against the
manifest's sha256; a mismatch rejects the file and the previous local copy stays.

## The surface

```python
from cosmoes_client import CosmoesClient, Fetch, Report, ClientError, basic_validate, load_state

client = CosmoesClient(base='https://cosmoes.org', timeout=3.0, max_bytes=5_000_000,
                       user_agent='cosmoes-client/1 (enough 0.5.4)', opener=None, clock=None)

client.manifest() -> dict                                   # GET base/manifest.json, checked for shape; raises ClientError
client.plan(state, manifest, wants) -> list[Fetch]          # what to fetch, with `current` when the local sha256 matches
client.fetch(f: Fetch) -> bytes                             # verified, size-capped, no redirect off-host; raises ClientError
client.sync(folder, wants, validate=None) -> Report         # the whole thing; never raises for a network or content fault
```

- `wants` is `{slug: [kinds]}`, kinds among `source`, `short`, `atem`, `fabula`; the slug `"*"` means every document
  the manifest lists (an explicit slug wins over it). enough wants `["source"]`; Comprise and Connect want the three
  fragments.
- `Fetch(slug, kind, url, sha256, current, size=None, error=None)`: `error` is set when the manifest's entry cannot be
  fetched at all (not in the manifest, host refused, no sha256, raw path refused, unknown kind).
- `Report`: `checked` (a manifest was obtained: fetched and well-formed, or confirmed by a 304), `updated`, `unchanged`,
  `skipped` (documents without a host), `errors` (`(slug, kind, message)`; `("*", "manifest", …)` when the manifest
  itself failed), `elapsed`; `ok` is `checked and not errors`; `lines()` is the printable form. Every wanted
  `(slug, kind)` lands in exactly one of the four lists.
- `validate(slug, kind, data) -> None | str` is run on every fetched body; `basic_validate` when none is given
  (markdown: UTF-8 and not empty; a fragment: UTF-8, contains `<article`, and nothing a loader refuses: `<script`,
  `<style`, `<iframe>`, `<frame>`, `<object>`, `<embed>`, `<base>`, `<link>`, `<meta>`, `<form>`, a `style=` or
  `on…=` attribute, a `javascript:` address; the same list as `cosmoes/specs.py`, copied). An app passes its own hook
  when it can do better: enough builds the markdown, Comprise and Connect run their loaders' check. A hook that raises
  counts as a refusal.
- `load_state(folder) -> dict`: `state.json` as a dict (an empty state when it is missing or unreadable).

## Rules of the sync

One manifest request per `sync`, with `If-None-Match` when `state.json` holds the ETag the server gave and
`manifest.json` is still on disk; a 304 means the kept manifest stands (the plan still runs, so a newly wanted kind is
fetched). The timeout is per request. `max_bytes` is enforced while reading (and before it, when the manifest's `bytes`
or the answer's `Content-Length` already says too much). A redirect is followed only to the same scheme and host
(netloc); anything else is an error for that file. HTTPS only, except a `base` of `http://127.0.0.1…` or
`http://localhost…` (the apps' tests and scratch rigs), under which loopback hosts are fetched over HTTP too; any other
base is a `ValueError` at construction, since a wrong base is a programming error. Nothing is raised to the caller of
`sync`: it all lands in the Report. Logging under the logger `cosmoes` (INFO an update, WARNING an error, DEBUG the
rest); the module never prints.

A document's kinds are written only when every wanted kind of it fetched and validated; the kinds that did fetch are
then reported as `held back`. Each file is written whole (a temporary file beside it, fsync, `os.replace`); `state.json`
is written last. A document-level inconsistency after a crash between two files heals on the next sync, since
`state.json` still names the old hashes.

## The folder

```
<folder>/<slug>/source.md            as fetched, only the kinds wanted
<folder>/<slug>/short.html
<folder>/<slug>/atem.html
<folder>/<slug>/fabula.html
<folder>/manifest.json               the last manifest fetched, verbatim (rewritten only when its bytes change)
<folder>/state.json                  what is held, see below
```

`state.json`, exactly:

```json
{
 "checked": "2026-11-03T10:00:00Z",
 "updated": "2026-11-03T10:00:00Z",
 "etag": "\"abc\"",
 "documents": {
  "thym": {
   "name": "Thym", "version": "0.5.4", "revised": "2026-11-03", "host": "thym.cosmoes.org",
   "kinds": {"source": {"sha256": "…64 hex…", "fetched": "2026-11-03T10:00:00Z"}}
  }
 }
}
```

`checked` is the last time a manifest was obtained; `updated` the last time a file changed (`null` until one does);
`etag` the manifest's ETag or `null`; `version`, `revised` may be `null`. **A consumer reads a document's name and
version from `state.json`, never from the files.**

## The command line

```sh
python cosmoes_client.py sync <folder> [--base URL] [--wants slug=source,short …] [--all-kinds] [--timeout S] [--max-bytes N] [--app NAME] [-v]
python cosmoes_client.py status <folder>
```

`sync` prints the report and exits 1 when the manifest was not reached or anything errored (2 for a bad base or
`--wants`). With no `--wants`, every document's `source` (`--all-kinds`: every kind); `--wants thym` alone means every
kind of thym. `status` prints `state.json`'s documents, exit 1 when there is none.

## Testing an app that vendors it

Two ways, both offline. A stand-in server (`http.server` on `127.0.0.1`, as `tests/test_client.py` does) with
`base='http://127.0.0.1:<port>'`: the manifest's documents then carry `host: "127.0.0.1:<port>"`. Or no server at all:
`opener=` anything with `.open(request, timeout=…)` returning a response that has `status`, `headers` (a
case-insensitive mapping) and `read(n)`, and raising `urllib.error.HTTPError` for a 304 or an error status; see
`FakeOpener` in `tests/test_client.py`. `clock=` replaces `time.time` for exact timestamps.

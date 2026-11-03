# cosmoes.org

The official homes of the OES specifications, each at its own address and at three densities (atem: one line per
section; short: the readable text; fabula: every item as a card), as enough's DocOES exports them:

| host | document |
|---|---|
| `cosmoes.org` | the index of the four; `/robots.txt`, `/sitemap.xml`, `/manifest.json` (all of it) |
| `macro.cosmoes.org` | MacroCOSM OES (with the Comprise OES chapters) |
| `thym.cosmoes.org` | Thym |
| `ascribe.cosmoes.org` | Ascribe |
| `comprise.cosmoes.org` | Comprise OES 1 |
| `www.cosmoes.org` | 301 to the apex, same path |
| `docoes.cosmoes.org` | 302 to `https://macro.cosmoes.org/#docs-sec-18-5` (DocOES is section 18.5 of MacroCOSM OES) |
| `mini.cosmoes.org` | 302 to the apex |

On a document's host: `/` is the short density (canonical; `/short` is a 301 to it), `/atem`, `/fabula`,
`/manifest.json` (that document's entry of the export's manifest), `/docs.css` (the export's stylesheet), `/site.css`,
`/robots.txt` (allow all; it names the host's `/sitemap.xml`), `/healthz`. An unknown host (the `run.app` address, a
local port) serves the apex. Every answer carries `Cache-Control: public, max-age=300` (a 404 and `/healthz`:
`no-store`), a `Content-Security-Policy` that allows only the site's own stylesheets, and HSTS over HTTPS. No
JavaScript, no inline styles, no third-party loads, no analytics, no environment variables, no storage.

One FastAPI app (`cosmoes/app.py`) routed by the `Host` header; the loader `cosmoes/specs.py` reads the export once
and refuses what it cannot vouch for (another format, a standalone export, a fragment whose sha256 differs from the
manifest's or that carries a script, a style, an event attribute…). Templates in `cosmoes/templates/`, the site's own
stylesheet in `cosmoes/static/site.css`. `PLAN.md` is the plan this was built from.

## The content: `site/specs/`

The export lives in this repository and ships in the image: `manifest.json` (`docoes-export/1`), `docs.css`,
`<slug>/{short,atem,fabula}.html`. Only `scripts/sync_specs.py` writes it, from an enough checkout whose `.venv`
exists (`uv sync --frozen` there):

```sh
.venv/bin/python scripts/sync_specs.py --enough ~/METMcloud/METMroot/enough-dev
```

It runs the checkout's `python -m enough.docoes export` four times (`macrocosm-oes`, `thym`, `ascribe`, and
`defaults/cosm/chapters/comprise-oes.md` as `comprise-oes` v1) with `--page short=/ --page atem=/atem --page
fabula=/fabula`, so the fragments' links across densities resolve on whichever host serves the document; checks the
result as the site reads it; and only then replaces `site/specs/`. It prints a line per document and changes nothing
when any step fails. Re-run it on every new version of a specification, look at the pages locally, commit what it
wrote, and deploy (DEPLOY.md, "Updating").

## Run it locally

```sh
uv venv --python 3.11 .venv && uv pip install --python .venv/bin/python -r requirements-dev.txt
.venv/bin/uvicorn cosmoes.app:app --port 8097
```

Then ask as each host:

```sh
curl -s http://127.0.0.1:8097/                                        # the apex (an unknown host serves it)
curl -s -H 'Host: thym.cosmoes.org' http://127.0.0.1:8097/            # Thym, short
curl -s -H 'Host: thym.cosmoes.org' http://127.0.0.1:8097/atem
curl -sI -H 'Host: www.cosmoes.org' http://127.0.0.1:8097/            # 301 https://cosmoes.org/
curl -sI -H 'Host: docoes.cosmoes.org' http://127.0.0.1:8097/         # 302 https://macro.cosmoes.org/#docs-sec-18-5
```

The links between hosts are absolute (`https://thym.cosmoes.org/`), so in a browser only the apex and one document at
a time are easy to look at locally; the density switch and the in-page links work as they are.

## Tests

```sh
.venv/bin/python -m pytest -q
```

`tests/test_site.py`: the routing (each host at each density with one `<h1>` and every in-page anchor resolving, the
apex, the redirect hosts, robots, sitemap, manifest, stylesheets, headers). `tests/test_specs.py`: what the loader
refuses, and that the shipped `site/specs/` loads with every document intact and every real page's anchors resolving.
`tests/test_sync.py`: the sync against a stand-in export. The fixture export is written by `tests/conftest.py`.

## Licences

The code is Apache-2.0 (LICENSE). MacroCOSM OES, Thym and Ascribe are enough's documents, Apache-2.0; Comprise OES 1
(and the Comprise chapters inside MacroCOSM OES) is Comprise's own text, © Graham Smith (NOTICE).

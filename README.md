# cosmoes.org

The official homes of the OES specifications, built from the canonical texts in `specs/` — the one place they are
edited — each at its own address and at three densities (atem: one line per section; short: the readable text;
fabula: every item as a card), as enough's DocOES exports them:

| host | document |
|---|---|
| `cosmoes.org` | *The OES specifications*, the apex text, with the list of the four homes on `/`; `/robots.txt`, `/sitemap.xml`, `/manifest.json` (all of it) |
| `macro.cosmoes.org` | MacroCOSM OES (alone: the Comprise texts have their own homes) |
| `thym.cosmoes.org` | Thym |
| `ascribe.cosmoes.org` | Ascribe |
| `comprise.cosmoes.org` | Comprise OES |
| `www.cosmoes.org` | 301 to the apex, same path |
| `docoes.cosmoes.org` | 302 to `https://macro.cosmoes.org/#docs-sec-18-5` (DocOES is section 18.5 of MacroCOSM OES) |
| `mini.cosmoes.org` | 302 to the apex |

Which document a host serves, its name and its edition come from the export's manifest, which the build takes from
the registry `specs/specs.json`: nothing is declared in the code. On a document's host, the apex included: `/` is the
short density (canonical; `/short` is a 301 to it), `/atem`, `/fabula`, `/manifest.json` (that document's entry of
the manifest; the whole of it at the apex), the raw files for the applications that sync their copies from here —
`/raw/source.md` (the text the pages were built from, `text/markdown`), `/raw/short.html`, `/raw/atem.html`,
`/raw/fabula.html` (the fragments as they are), each with `Access-Control-Allow-Origin: *` — `/docs.css` (the
export's stylesheet), `/site.css`, `/robots.txt` (allow all; it names the host's `/sitemap.xml`), `/health` (`{"ok":true,"edition":…}`, the edition from the manifest) and
`/healthz` (which on Cloud Run Google's front end answers itself with a 404 and never passes on). A host outside the
domain (the `run.app` address, a local port) serves the apex; a name under the domain that no document claims is not
found. Every answer carries `Cache-Control: public, max-age=300` (a 404, `/health` and `/healthz`: `no-store`), a
`Content-Security-Policy` that allows only the site's own stylesheets, and HSTS over HTTPS. No JavaScript, no inline
styles, no third-party loads, no analytics, no environment variables, no storage.

One FastAPI app (`cosmoes/app.py`) routed by the `Host` header; the loader `cosmoes/specs.py` reads the export once
and refuses what it cannot vouch for (another format, a standalone export, a file whose sha256 differs from the
manifest's, a fragment that carries a script, a style, an event attribute…). Templates in `cosmoes/templates/`, the
site's own stylesheet in `cosmoes/static/site.css`. `PLAN.md` is the plan this grew from; `CONTRIBUTING.md` says how
a text changes.

## The texts: `specs/`

`specs/<file>.md` are the canonical texts (`specs/NOTICE.md`: © 2026 Graham Smith, all rights reserved;
`specs/ORIGINS.md`: where each came from on 2026-11-03). `specs/specs.json` is the registry: one entry per text with
`slug`, `file`, `name` (never with a number in it), `edition`, `describes` (the format versions the text describes),
`host`, `revised`, and `reference: true` for the text that carries the manifests' reference (MacroCOSM OES). A
change to a text is a pull request against this folder (CONTRIBUTING.md).

## The export: `site/specs/`

What the site serves lives in this repository and ships in the image: `manifest.json` (`docoes-export/1`, with the
registry's fields per document and this repository's commit at the top), `docs.css`,
`<slug>/{short,atem,fabula}.html`, `<slug>/source.md`. Only `scripts/build_specs.py` writes it, from `specs/` with an
enough checkout whose `.venv` exists (`uv sync --frozen` there) and whose DocOES export is 0.5.1's or later:

```sh
.venv/bin/python scripts/build_specs.py --enough ~/METMcloud/METMroot/enough-dev
.venv/bin/python scripts/build_specs.py --enough ~/METMcloud/METMroot/enough-dev --check
```

It validates the registry, lays the texts and enough's manifests out as a sources root in a temporary folder,
runs the checkout's `python -m enough.docoes export` once per text (`--slug … --name … --version <edition> --page
short=/ --page atem=/atem --page fabula=/fabula --no-marks`, plus `--reference` where the registry says so), adds the
registry's fields and the source copies to the manifest, checks the result as the site reads it, and only then
replaces `site/specs/`. It prints a line per document and changes nothing when any step fails. `--check` builds the
same way into a temporary folder and compares it with `site/specs/` byte for byte (the manifest's `exported` time and
`source` commit apart), exit 1 on a difference: the committed export is in step with the texts, or it is not. Run the
build on every change to a text, look at the pages locally, commit what it wrote with the text, and deploy
(DEPLOY.md, "Updating").

## Run it locally

```sh
uv venv --python 3.11 .venv && uv pip install --python .venv/bin/python -r requirements-dev.txt
.venv/bin/uvicorn cosmoes.app:app --port 8097
```

Then ask as each host:

```sh
curl -s http://127.0.0.1:8097/                                        # the apex (a host outside the domain serves it)
curl -s -H 'Host: thym.cosmoes.org' http://127.0.0.1:8097/            # Thym, short
curl -s -H 'Host: thym.cosmoes.org' http://127.0.0.1:8097/atem
curl -sI -H 'Host: thym.cosmoes.org' http://127.0.0.1:8097/raw/source.md   # text/markdown, Access-Control-Allow-Origin: *
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
apex text with its list of homes, the raw endpoints and their headers, names and hosts taken from the manifest, the
redirect hosts, robots, sitemap, manifest, stylesheets, headers, the licence line). `tests/test_specs.py`: what the
loader refuses, and that the shipped `site/specs/` is the registry built, every real page's anchors resolving, no
margin marks, the Comprise chapters gone. `tests/test_build.py`: the registry's validation and the build against a
stand-in export; its last test runs `--check` with the real enough when a checkout is at hand (`COSMOES_ENOUGH`, else
`~/METMcloud/METMroot/enough-dev`). The fixture export is written by `tests/conftest.py`. CI
(`.github/workflows/check.yml`) runs the suite on every push and pull request, and its `in-step` job rebuilds the
export with enough's public main: out of step with the texts fails, rendered by an older enough only warns.

## Licences

The texts are © 2026 Graham Smith, all rights reserved (`specs/NOTICE.md`, `NOTICE`); the canonical editions are the
pages at cosmoes.org and its hosts. The site's code is Apache-2.0 (`LICENSE`).

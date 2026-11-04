# cosmoes.org — the official homes of the OES specifications (plan, 2026-11-02, revised after the owner's DNS)

*Superseded in part on 2026-11-03 by the OES canon round: the texts now live in `specs/` here, the one place they are
edited; `scripts/build_specs.py` builds `site/specs/` from them (the sync from enough is gone); the apex serves the
paradigm map as a document with the list of the four homes; every host has `/raw/*`; MacroCOSM OES is served
without the Comprise chapters; the licence line reads © Graham Smith, all rights reserved. README.md and
CONTRIBUTING.md describe what is; this file is the plan it grew from.*

The owner's ask (2026-11-02): the same DocOES-powered views that comprise.company/macrocosmoes carries, published at
the specs' own addresses. Hosts (the owner dropped the `.mini.` layer when making the DNS):
**macro.cosmoes.org** (MacroCOSM OES as a whole), **thym.cosmoes.org**, **ascribe.cosmoes.org**,
**comprise.cosmoes.org** (Comprise OES 1). The apex **cosmoes.org** (and www) lists them. Two more names exist in
DNS: **docoes.cosmoes.org** → 302 to `https://macro.cosmoes.org/#docs-sec-18-5` (DocOES, `doc/1`, is section 18.5 of
the MacroCOSM spec, not a document of its own; the same holds for cosm, canon and emf, 18.1–18.4); **mini.cosmoes.org**
→ 302 to the apex. A host of its own comes only when a MiniCOSM gets its own specification.

## 1. What exists (reuse, do not rebuild)

- enough-dev `python -m enough.docoes export <doc> <out-dir> [--page density=href]… [--version V] [--slug S]
  [--name N] [--standalone]` (lane X1, `enough/docoes_html.py`; spec `docs/thym-landed-X1.md` §2): script-free
  fragments at short / atem / fabula, `docs.css`, a merged `manifest.json` (`docoes-export/1`, sha256 per file).
  `<doc>` is a registered slug (`macrocosm-oes`, `thym`, `ascribe` since lane X2, `help-center`) or a markdown path
  inside the checkout — so **Comprise OES 1** exports ad hoc from `defaults/cosm/chapters/comprise-oes.md` with
  `--slug comprise-oes --name "Comprise OES 1" --version 1` (Comprise's own words, synced from comprise-dev; the
  `NOTICE.md` beside it says © Graham Smith, not Apache).
- comprise-connect: `connect/macrocosmoes.py` (`Specs(folder)`: the loader with its format/hash/safety checks),
  `scripts/sync_macrocosmoes.py` (runs the export, validates, swaps the folder), the templates and `site.css` layout
  (two columns ≥ 1100px, sticky contents, density switch) — the model for the new site's code, copied and trimmed,
  not imported (the new site must not depend on Connect).
- Cloud Run in project `i0app-010010`, region `us-central1`, domain mappings as `comprise.company` has
  (DEPLOY.md §6, §8): apex → the four A + four AAAA Google addresses; subdomains → `CNAME ghs.googlehosted.com`.
  `gcloud beta run domain-mappings create --service … --domain …` needs the domain verified for the gcloud account
  (`gcloud domains list-user-verified`; `domo@lign.dev` today; cosmoes.org is NOT verified yet).

## 2. DNS (Squarespace Domains, nameservers nsc1–4.squarespacedns.com) — DONE by the owner 2026-11-02, one record left

Checked at the authoritative server: apex `A` 216.239.32.21 / .34.21 / .36.21 / .38.21 and `AAAA`
2001:4860:4802:32::15 / :34::15 / :36::15 / :38::15; `CNAME ghs.googlehosted.com` for `www`, `macro`, `thym`,
`ascribe`, `comprise`, `docoes`, `mini`; the forwarding rule on `macro` is gone; the Email Security TXTs stay.

**Still missing — the verification TXT on the apex:**
`google-site-verification=8Yf-hPxtVMiSvMa_ueYSrD2xtyesGPRvw2URr5cXvpw` (the Search Console property "cosmoes.org",
added 2026-11-02 under smithmail@gmail.com, unverified). Then "Verify" on that property; then, because gcloud runs as
domo@lign.dev, open <https://www.google.com/webmasters/verification/home> → cosmoes.org → Verification details →
**Add an owner** `domo@lign.dev`. `gcloud domains list-user-verified` must list cosmoes.org before the mappings.
(Squarespace asks for a 2FA code on every change.)

## 3. The site (a new repository, `0gsd/cosmoes-site`)

- **One Cloud Run service `cosmoes-site`** (same image shape as comprise-connect: Python 3.11, FastAPI + Jinja2,
  `uvicorn`, Dockerfile, `requirements.txt` pinned, `--allow-unauthenticated`, cpu 1 / 512Mi / max-instances 3, no
  storage, no secrets, no env beyond `COSMOES_ORIGIN` for HSTS/canonical). Mappings: `cosmoes.org`,
  `www.cosmoes.org`, `macro.cosmoes.org`, `thym.cosmoes.org`, `ascribe.cosmoes.org`, `comprise.cosmoes.org`,
  `docoes.cosmoes.org`, `mini.cosmoes.org`. www → 301 to the apex; docoes and mini → 302 as above.
- **Host routing**: the `Host` header picks the document (unknown host → the apex index). Per document host:
  `/` = the short density (canonical), `/short` → 301 `/`, `/atem`, `/fabula`, `/manifest.json` (that document's
  entry), `/docs.css`. The apex: an index of the four (name, version, lead, counts, links to each host's three
  densities), `/robots.txt` (**allow all** — these are the official homes, meant to be found; the comprise.company
  copy stays noindex), `/sitemap.xml` (the four hosts × three pages), `/healthz`. Headers: `Cache-Control:
  public, max-age=300`, HSTS from the origin, no `X-Robots-Tag`.
- **Content**: `site/specs/` = the export (`manifest.json`, `<slug>/{short,atem,fabula}.html`, `docs.css`), written
  only by `scripts/sync_specs.py --enough PATH` (comprise-connect's sync, adapted: four documents —
  `macrocosm-oes`, `thym`, `ascribe`, `defaults/cosm/chapters/comprise-oes.md` as `comprise-oes` v1 — `--page
  short=/ --page atem=/atem --page fabula=/fabula`, host-absolute hrefs so cross-density links work on each host).
  The loader = `Specs` copied from comprise-connect (format, not standalone, sha256, no script/style/event/iframe…).
- **Look**: neutral, not Comprise's Field Guide chrome: the export's `docs.css` + a small `site.css` (system sans,
  a 64ch measure for prose, the two-column contents layout ≥ 1100px copied from site.css's `.docoes` rules, the
  density switch as a segmented row). Header: "cosmoes.org" wordmark text + the four hosts as links (the current one
  marked) + the density switch; footer: "From enough <version> (<commit>), exported <date>. MacroCOSM OES, Thym and
  Ascribe are Apache-2.0 (enough); Comprise OES 1 is Comprise's own text, © Graham Smith." No JavaScript, no inline
  styles, no third-party loads, no analytics.
- **Tests** (pytest + TestClient): each host serves its document at three densities with one `<h1>`, ids and
  in-page anchors intact; unknown host and unknown path; www → apex; docoes and mini redirects; robots allow +
  sitemap lists every page; the shipped `site/specs/` loads with every document intact (integrity); the four
  negative loader cases (format, standalone, hash, script); `no_inline_script_or_style` on every page.
- **Docs**: `README.md` (what, run locally with `uvicorn`, the sync), `DEPLOY.md` (§0 names, the service account
  `cosmoes-site` with no roles, build `gcloud builds submit --tag …`, `gcloud run deploy`, the eight domain
  mappings and the DNS records above, the checks: `curl -sI https://macro.cosmoes.org/ | grep -i cache-control`,
  `/robots.txt`, `/sitemap.xml`), `LICENSE` (Apache-2.0 for the site's code) and `NOTICE` (the Comprise text).
- **Re-publish on every spec version**: sync, look locally, commit, build, deploy — the owner's, or with their go.

## 4. Order of work (one session, after the comprise.company publish)

1. Repo scaffold + loader + host routing + templates + css, against the real export (run the sync from enough-dev).
2. Tests green; run locally on 8097 and check each host with the `Host` header (`curl -H 'Host: thym.cosmoes.org'`)
   and the apex index in the browser.
3. Push the repo to GitHub (public: it is a spec site, unless the owner says private).
4. Deploy on the owner's go, once section 2's TXT + verification + owner step are done: service account, build,
   deploy, the eight mappings, wait for certificates (minutes to an hour), then the checks.
5. The Verroes tracker entry updated; the comprise.company/macrocosmoes index gets one line pointing at the
   official homes (a later, small comprise-connect change: the only outbound link, allowed since cosmoes.org is
   public).

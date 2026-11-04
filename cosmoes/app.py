"""cosmoes.org: the official homes of the OES specifications. One FastAPI app, one Cloud Run service, eight hosts, routed
by the Host header. Which document a host serves is read from the export's manifest (site/specs/manifest.json; the
registry specs/specs.json declares it): the document whose host is the domain itself is the apex text, and a document
whose host is `<sub>.cosmoes.org` is served at that subdomain. Today:

    cosmoes.org             OES, the paradigm map, with the list of the four homes on /; /robots.txt, /sitemap.xml,
                            /manifest.json (all of it), /health ({"ok":true,"edition":…}, on every host)
    macro.cosmoes.org       MacroCOSM OES          /  (short)   /atem   /fabula   /manifest.json   /raw/*   /docs.css
    thym.cosmoes.org        Thym                   the same
    ascribe.cosmoes.org     Ascribe                the same
    comprise.cosmoes.org    Comprise OES           the same
    www.cosmoes.org         301 to the apex, same path
    docoes.cosmoes.org      302 to https://macro.cosmoes.org/#docs-sec-18-5 (DocOES is section 18.5 of MacroCOSM OES)
    mini.cosmoes.org        302 to the apex
    anything else under cosmoes.org   not found (a document left out of the manifest is not replaced by the apex)
    anything else           the apex (the run.app address, a local port)

On every document host, the apex included: `/raw/source.md` (the text the pages were built from), `/raw/short.html`,
`/raw/atem.html`, `/raw/fabula.html` (the fragments as they are), each with `Access-Control-Allow-Origin: *`, for the
applications that sync their copies from here. The content is the export in site/specs/ (cosmoes/specs.py;
scripts/build_specs.py writes it). Every page is script-free, with no inline style and no third-party load; every
answer carries `Cache-Control: public, max-age=300` (a 404, /health and /healthz: no-store) and, over HTTPS, HSTS. Every name
and edition shown comes from the manifest. No environment, no storage, no secrets.
"""
from __future__ import annotations

import datetime
import re
from pathlib import Path
from xml.sax.saxutils import escape

from fastapi import FastAPI, Request
from fastapi.responses import HTMLResponse, JSONResponse, PlainTextResponse, RedirectResponse, Response
from jinja2 import Environment, FileSystemLoader, select_autoescape

from . import specs as specs_mod

HERE = Path(__file__).resolve().parent
DOMAIN = 'cosmoes.org'
APEX = f'https://{DOMAIN}/'
DOCOES_ANCHOR = '#docs-sec-18-5'
REDIRECTS = {'www': (301, None),                                         # None: the apex, same path and query
             'docoes': (302, f'https://macro.{DOMAIN}/{DOCOES_ANCHOR}'),
             'mini': (302, APEX)}
SUB_RE = re.compile(r'^[a-z0-9]([a-z0-9-]*[a-z0-9])?$')                  # one label: a document's subdomain
DENSITIES = specs_mod.DENSITIES
PAGES = specs_mod.PAGES
TITLES = specs_mod.TITLES
RAW = {'source.md': (specs_mod.SOURCE, 'text/markdown; charset=utf-8'),  # /raw/<name>: which file, served as what
       'short.html': ('short', 'text/html; charset=utf-8'),
       'atem.html': ('atem', 'text/html; charset=utf-8'),
       'fabula.html': ('fabula', 'text/html; charset=utf-8')}
CACHE = 'public, max-age=300'
NO_STORE = 'no-store'
HSTS = 'max-age=31536000'
CSP = "default-src 'none'; style-src 'self'; img-src 'self' data:; base-uri 'none'; form-action 'none'; frame-ancestors 'none'"
REPOSITORY = 'https://github.com/0gsd/cosmoes-site'


def host_url(sub: str) -> str:
    return f'https://{sub}.{DOMAIN}/'


def host_of(request: Request) -> str:
    """The Host header's name: lower-cased, without a port or a trailing dot ('' when absent)."""
    h = request.headers.get('host', '').strip().lower()
    if h.startswith('['):
        h = h.split(']', 1)[0] + ']'
    else:
        h = h.split(':', 1)[0]
    return h.rstrip('.')


class Hosts:
    """Which document each host serves, from the manifest's `host` fields: `apex` is the slug of the document whose
    host is the domain itself (None when there is none), `by_sub` maps a subdomain to its document's slug, in the
    manifest's order. A document whose host is outside the domain, a redirect host's name or a second document on
    one host is not served (and logged by the build, which refuses it)."""

    def __init__(self, documents: list[dict]):
        self.apex: str | None = None
        self.by_sub: dict[str, str] = {}
        for d in documents:
            host, slug = d.get('host') or '', d['slug']
            if host == DOMAIN:
                if self.apex is None:
                    self.apex = slug
            elif host.endswith('.' + DOMAIN):
                sub = host[:-len(DOMAIN) - 1]
                if SUB_RE.match(sub) and sub not in REDIRECTS and sub not in self.by_sub:
                    self.by_sub[sub] = slug
        self.sub_of = {slug: sub for sub, slug in self.by_sub.items()}

    def where(self, host: str) -> tuple[str, str | None]:
        """('doc', slug), ('redirect', subdomain), ('none', None) or ('apex', the apex text's slug or None) for a
        Host header's name. A name under the domain that no document and no redirect claims is served nothing (a
        document left out of the manifest is not found at its host, not replaced by the apex); a host outside the
        domain (the run.app address, a local port) is the apex."""
        if host.endswith('.' + DOMAIN):
            sub = host[:-len(DOMAIN) - 1]
            if sub in self.by_sub:
                return 'doc', self.by_sub[sub]
            if sub in REDIRECTS:
                return 'redirect', sub
            return 'none', None
        return 'apex', self.apex

    def host(self, slug: str) -> str:
        return f'{self.sub_of[slug]}.{DOMAIN}' if slug in self.sub_of else DOMAIN

    def url(self, slug: str) -> str:
        return host_url(self.sub_of[slug]) if slug in self.sub_of else APEX


def create_app(specs_folder: Path | str | None = None) -> FastAPI:
    """The site, its specifications read from `specs_folder` (site/specs/ unless a test names another)."""
    specs = specs_mod.Specs(specs_folder or specs_mod.FOLDER)
    env = Environment(loader=FileSystemLoader(str(HERE / 'templates')), autoescape=select_autoescape(['html', 'xml']),
                      trim_blocks=True, lstrip_blocks=True)
    env.filters['date_text'] = specs_mod.date_text
    site_css = (HERE / 'static' / 'site.css').read_text(encoding='utf-8')

    app = FastAPI(title='cosmoes.org', docs_url=None, redoc_url=None, openapi_url=None)
    app.state.specs = specs
    routing: dict[str, Hosts] = {}

    def hosts_map() -> Hosts:
        if 'hosts' not in routing:                       # the manifest is read once, on first use: so is this
            routing['hosts'] = Hosts(specs.documents)
        return routing['hosts']

    def where(request: Request) -> tuple[str, str | None]:
        return hosts_map().where(host_of(request))

    # --------------------------------------------------------------------- what every page gets

    def homes(current: str | None) -> list[dict]:
        """The documents with a host of their own (not the apex text), in the manifest's order: the header's names
        and the apex's list, every name and edition from the manifest."""
        hm = hosts_map()
        return [dict(specs.get(slug), host=f'{sub}.{DOMAIN}', url=host_url(sub), label=specs.get(slug)['name'],
                     current=slug == current) for sub, slug in hm.by_sub.items()]

    def description(doc: dict | None) -> str:
        if doc and doc['lead']:
            return doc['lead']
        names = [h['name'] for h in homes(None)]
        joined = (', '.join(names[:-1]) + ' and ' + names[-1]) if len(names) > 1 else ''.join(names)
        return (f'The official homes of the OES specifications{": " + joined if joined else ""}, each at three '
                'densities, built from the canonical texts.')

    def page(template: str, status: int = 200, headers: dict | None = None, **ctx) -> HTMLResponse:
        html = env.get_template(template).render(domain=DOMAIN, apex=APEX, repository=REPOSITORY, meta=specs.meta,
                                                 densities=DENSITIES, pages=PAGES, titles=TITLES, **ctx)
        return HTMLResponse(html, status_code=status, headers=headers)

    def not_found(request: Request) -> HTMLResponse:
        kind, slug = where(request)
        return page('notfound.html', 404, {'Cache-Control': NO_STORE}, hosts=homes(slug if kind == 'doc' else None),
                    host=host_of(request))

    def doc_page(request: Request, slug: str | None, density: str, with_homes: bool = False) -> HTMLResponse:
        doc, fragment = specs.get(slug) if slug else None, specs.page(slug, density) if slug else None
        if doc is None or fragment is None:
            return not_found(request)
        hm = hosts_map()
        canonical = hm.url(slug) + PAGES[density].lstrip('/')
        return page('doc.html', hosts=homes(slug), host=hm.host(slug), doc=doc, density=density, fragment=fragment,
                    homes=homes(None) if with_homes else None, canonical=canonical, description=description(doc))

    def apex_page(request: Request) -> HTMLResponse:
        """The apex: its text at the short density with the list of the homes; without an apex text, the list alone
        (a 404 saying nothing is published when there is no document at all)."""
        kind, slug = where(request)
        if slug and specs.page(slug, 'short'):
            return doc_page(request, slug, 'short', with_homes=True)
        docs = homes(None)
        return page('index.html', 200 if docs else 404, {'Cache-Control': CACHE if docs else NO_STORE},
                    hosts=docs, docs=docs, canonical=APEX, description=description(None))

    # --------------------------------------------------------------------- headers and the redirect hosts

    @app.middleware('http')
    async def headers(request: Request, call_next):
        kind, sub = where(request)
        if kind == 'redirect':
            status, to = REDIRECTS[sub]
            if to is None:
                to = APEX.rstrip('/') + request.url.path + (f'?{request.url.query}' if request.url.query else '')
            response = RedirectResponse(to, status_code=status)
        elif kind == 'none' and request.url.path not in ('/health', '/healthz'):
            response = not_found(request)
        else:
            response = await call_next(request)
        response.headers.setdefault('Cache-Control', CACHE)
        response.headers.setdefault('Content-Security-Policy', CSP)
        response.headers.setdefault('X-Content-Type-Options', 'nosniff')
        response.headers.setdefault('Referrer-Policy', 'strict-origin-when-cross-origin')
        if request.url.scheme == 'https':
            response.headers.setdefault('Strict-Transport-Security', HSTS)
        return response

    def edition() -> str | None:
        """The edition the site serves: the apex text's, or the first document's when the export has no apex text; None
        when nothing is published. Every text moves to a new edition together, so any one of them says it."""
        docs = specs.documents
        first = next((d for d in docs if d.get('host') == DOMAIN), docs[0] if docs else None)
        return first.get('edition') if first else None

    # --------------------------------------------------------------------- the routes, on every host

    def get(path: str):
        return app.api_route(path, methods=['GET', 'HEAD'], include_in_schema=False)   # FastAPI adds no HEAD by itself

    @get('/health')
    def health():
        # The check a release reads from the outside (verroes, release.sh verify): up, and at which edition, from the manifest.
        # /health and not /healthz: on Cloud Run, Google's front end answers /healthz itself (a 404) and never passes it on.
        return JSONResponse({'ok': True, 'edition': edition()}, headers={'Cache-Control': NO_STORE})

    @get('/healthz')
    def healthz():
        return JSONResponse({'ok': True}, headers={'Cache-Control': NO_STORE})

    @get('/')
    def root(request: Request):
        kind, slug = where(request)
        return doc_page(request, slug, 'short') if kind == 'doc' else apex_page(request)

    @get('/short')
    def short(request: Request):
        kind, slug = where(request)
        return RedirectResponse('/', status_code=301) if slug else not_found(request)

    @get('/atem')
    def atem(request: Request):
        kind, slug = where(request)
        return doc_page(request, slug, 'atem')

    @get('/fabula')
    def fabula(request: Request):
        kind, slug = where(request)
        return doc_page(request, slug, 'fabula')

    @get('/raw/{name}')
    def raw(request: Request, name: str):
        """A document's files as they are, for the applications that sync from here: the source markdown and the
        three fragments. The apex's are the apex text's; a host with no document has none."""
        kind, slug = where(request)
        if name not in RAW or not slug:
            return not_found(request)
        which, media = RAW[name]
        body = specs.source(slug) if which == specs_mod.SOURCE else specs.page(slug, which)
        if body is None:
            return not_found(request)
        return Response(body, media_type=media, headers={'Access-Control-Allow-Origin': '*'})

    @get('/manifest.json')
    def manifest(request: Request):
        kind, slug = where(request)
        m = specs.manifest(slug if kind == 'doc' else None)        # the apex and an unknown host: all of it
        if m is None:
            return JSONResponse({'error': 'not found'}, status_code=404, headers={'Cache-Control': NO_STORE})
        return JSONResponse(m, headers={'Access-Control-Allow-Origin': '*'})

    @get('/docs.css')
    def docs_css():
        return Response(specs.css, media_type='text/css; charset=utf-8')

    @get('/site.css')
    def site_css_route():
        return Response(site_css, media_type='text/css; charset=utf-8')

    @get('/robots.txt')
    def robots(request: Request):
        kind, slug = where(request)
        own = hosts_map().url(slug) if kind == 'doc' else APEX
        return PlainTextResponse(f'User-agent: *\nAllow: /\n\nSitemap: {own}sitemap.xml\n')

    @get('/sitemap.xml')
    def sitemap(request: Request):
        kind, slug = where(request)
        hm = hosts_map()
        if kind == 'doc':
            urls = [hm.url(slug) + PAGES[d].lstrip('/') for d in ('short', 'atem', 'fabula')]
        else:
            urls = [APEX + PAGES[d].lstrip('/') for d in (('short', 'atem', 'fabula') if slug else ('short',))]
            for sub, s in hm.by_sub.items():
                urls += [host_url(sub) + PAGES[d].lstrip('/') for d in ('short', 'atem', 'fabula')]
        exported = specs.meta['exported'] if specs.meta else None
        lastmod = f'<lastmod>{exported:%Y-%m-%d}</lastmod>' if isinstance(exported, datetime.datetime) else ''
        body = ('<?xml version="1.0" encoding="UTF-8"?>\n<urlset xmlns="http://www.sitemaps.org/schemas/sitemap/0.9">\n'
                + ''.join(f'  <url><loc>{escape(u)}</loc>{lastmod}</url>\n' for u in urls) + '</urlset>\n')
        return Response(body, media_type='application/xml')

    @get('/{path:path}')
    def anything_else(request: Request, path: str):
        if path.endswith('/') and '/' + path.rstrip('/') in ('/short', '/atem', '/fabula'):
            return RedirectResponse('/' + path.rstrip('/'), status_code=301)
        return not_found(request)

    return app


app = create_app()

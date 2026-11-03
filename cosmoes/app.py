"""cosmoes.org: the official homes of the OES specifications. One FastAPI app, one Cloud Run service, eight hosts, routed
by the Host header:

    cosmoes.org             the index of the four specifications; /robots.txt, /sitemap.xml, /manifest.json (all of it)
    macro.cosmoes.org       MacroCOSM OES          /  (short)   /atem   /fabula   /manifest.json   /docs.css
    thym.cosmoes.org        Thym                   the same
    ascribe.cosmoes.org     Ascribe                the same
    comprise.cosmoes.org    Comprise OES 1         the same
    www.cosmoes.org         301 to the apex, same path
    docoes.cosmoes.org      302 to https://macro.cosmoes.org/#docs-sec-18-5 (DocOES is section 18.5 of MacroCOSM OES)
    mini.cosmoes.org        302 to the apex
    anything else           the apex (the run.app address, a local port)

The content is the export in site/specs/ (cosmoes/specs.py; scripts/sync_specs.py writes it). Every page is
script-free, with no inline style and no third-party load; every answer carries `Cache-Control: public, max-age=300`
(a 404 and /healthz: no-store) and, over HTTPS, HSTS. No environment, no storage, no secrets.
"""
from __future__ import annotations

import datetime
from pathlib import Path
from xml.sax.saxutils import escape

from fastapi import FastAPI, Request
from fastapi.responses import HTMLResponse, JSONResponse, PlainTextResponse, RedirectResponse, Response
from jinja2 import Environment, FileSystemLoader, select_autoescape

from . import specs as specs_mod

HERE = Path(__file__).resolve().parent
DOMAIN = 'cosmoes.org'
APEX = f'https://{DOMAIN}/'
HOSTS = {'macro': 'macrocosm-oes', 'thym': 'thym', 'ascribe': 'ascribe', 'comprise': 'comprise-oes'}   # subdomain: slug
LABELS = {'macro': 'MacroCOSM OES', 'thym': 'Thym', 'ascribe': 'Ascribe', 'comprise': 'Comprise OES 1'}  # the header's names
SUB_OF = {slug: sub for sub, slug in HOSTS.items()}
DOCOES_ANCHOR = '#docs-sec-18-5'
REDIRECTS = {'www': (301, None),                                         # None: the apex, same path and query
             'docoes': (302, f'https://macro.{DOMAIN}/{DOCOES_ANCHOR}'),
             'mini': (302, APEX)}
DENSITIES = specs_mod.DENSITIES
PAGES = specs_mod.PAGES
TITLES = specs_mod.TITLES
CACHE = 'public, max-age=300'
NO_STORE = 'no-store'
HSTS = 'max-age=31536000'
CSP = "default-src 'none'; style-src 'self'; img-src 'self' data:; base-uri 'none'; form-action 'none'; frame-ancestors 'none'"
DESCRIPTION = ('The official homes of the OES specifications: MacroCOSM OES, Thym, Ascribe and Comprise OES 1, each at '
               'three densities, as enough ships them.')


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


def where(request: Request) -> tuple[str, str | None]:
    """('apex', None), ('doc', slug) or ('redirect', subdomain) for the request's host; an unknown host is the apex."""
    h = host_of(request)
    if h.endswith('.' + DOMAIN):
        sub = h[:-len(DOMAIN) - 1]
        if sub in HOSTS:
            return 'doc', HOSTS[sub]
        if sub in REDIRECTS:
            return 'redirect', sub
    return 'apex', None


def create_app(specs_folder: Path | str | None = None) -> FastAPI:
    """The site, its specifications read from `specs_folder` (site/specs/ unless a test names another)."""
    specs = specs_mod.Specs(specs_folder or specs_mod.FOLDER)
    env = Environment(loader=FileSystemLoader(str(HERE / 'templates')), autoescape=select_autoescape(['html', 'xml']),
                      trim_blocks=True, lstrip_blocks=True)
    env.filters['date_text'] = specs_mod.date_text
    site_css = (HERE / 'static' / 'site.css').read_text(encoding='utf-8')

    app = FastAPI(title='cosmoes.org', docs_url=None, redoc_url=None, openapi_url=None)
    app.state.specs = specs

    # --------------------------------------------------------------------- what every page gets

    def hosts(current: str | None) -> list[dict]:
        return [{'sub': sub, 'slug': slug, 'host': f'{sub}.{DOMAIN}', 'url': host_url(sub), 'label': LABELS[sub],
                 'doc': specs.get(slug), 'current': slug == current} for sub, slug in HOSTS.items()]

    def page(template: str, status: int = 200, headers: dict | None = None, **ctx) -> HTMLResponse:
        html = env.get_template(template).render(domain=DOMAIN, apex=APEX, meta=specs.meta, densities=DENSITIES,
                                                 pages=PAGES, titles=TITLES, **ctx)
        return HTMLResponse(html, status_code=status, headers=headers)

    def not_found(request: Request) -> HTMLResponse:
        kind, slug = where(request)
        return page('notfound.html', 404, {'Cache-Control': NO_STORE}, hosts=hosts(slug), host=host_of(request))

    def index(request: Request) -> HTMLResponse:
        docs = []
        for h in hosts(None):
            if h['doc']:
                docs.append(dict(h['doc'], host=h['host'], url=h['url'], label=h['label']))
        return page('index.html', 200 if docs else 404, {'Cache-Control': CACHE if docs else NO_STORE},
                    hosts=hosts(None), docs=docs, canonical=APEX, description=DESCRIPTION)

    def doc_page(request: Request, slug: str, density: str) -> HTMLResponse:
        doc, fragment = specs.get(slug), specs.page(slug, density)
        if doc is None or fragment is None:
            return not_found(request)
        sub = SUB_OF[slug]
        canonical = host_url(sub) + PAGES[density].lstrip('/')
        return page('doc.html', hosts=hosts(slug), host=f'{sub}.{DOMAIN}', doc=doc, density=density, fragment=fragment,
                    canonical=canonical, description=doc['lead'] or DESCRIPTION)

    # --------------------------------------------------------------------- headers and the redirect hosts

    @app.middleware('http')
    async def headers(request: Request, call_next):
        kind, sub = where(request)
        if kind == 'redirect':
            status, to = REDIRECTS[sub]
            if to is None:
                to = APEX.rstrip('/') + request.url.path + (f'?{request.url.query}' if request.url.query else '')
            response = RedirectResponse(to, status_code=status)
        else:
            response = await call_next(request)
        response.headers.setdefault('Cache-Control', CACHE)
        response.headers.setdefault('Content-Security-Policy', CSP)
        response.headers.setdefault('X-Content-Type-Options', 'nosniff')
        response.headers.setdefault('Referrer-Policy', 'strict-origin-when-cross-origin')
        if request.url.scheme == 'https':
            response.headers.setdefault('Strict-Transport-Security', HSTS)
        return response

    # --------------------------------------------------------------------- the routes, on every host

    def get(path: str):
        return app.api_route(path, methods=['GET', 'HEAD'], include_in_schema=False)   # FastAPI adds no HEAD by itself

    @get('/healthz')
    def healthz():
        return JSONResponse({'ok': True}, headers={'Cache-Control': NO_STORE})

    @get('/')
    def root(request: Request):
        kind, slug = where(request)
        return doc_page(request, slug, 'short') if kind == 'doc' else index(request)

    @get('/short')
    def short(request: Request):
        kind, slug = where(request)
        return RedirectResponse('/', status_code=301) if kind == 'doc' else not_found(request)

    @get('/atem')
    def atem(request: Request):
        kind, slug = where(request)
        return doc_page(request, slug, 'atem') if kind == 'doc' else not_found(request)

    @get('/fabula')
    def fabula(request: Request):
        kind, slug = where(request)
        return doc_page(request, slug, 'fabula') if kind == 'doc' else not_found(request)

    @get('/manifest.json')
    def manifest(request: Request):
        kind, slug = where(request)
        m = specs.manifest(slug)
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
        own = host_url(SUB_OF[slug]) if kind == 'doc' else APEX
        return PlainTextResponse(f'User-agent: *\nAllow: /\n\nSitemap: {own}sitemap.xml\n')

    @get('/sitemap.xml')
    def sitemap(request: Request):
        kind, slug = where(request)
        subs = [SUB_OF[slug]] if kind == 'doc' else list(HOSTS)
        urls = [] if kind == 'doc' else [APEX]
        for sub in subs:
            if specs.get(HOSTS[sub]):
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

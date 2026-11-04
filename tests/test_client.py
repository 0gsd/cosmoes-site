"""client/cosmoes_client.py against a stand-in for cosmoes.org on 127.0.0.1 (http.server in a thread, one per test):
every test offline. The stand-in serves a manifest and raw files built from small fixtures here, counts requests, and
misbehaves on demand (a lying sha256, a redirect, a sleep, an oversize body, a missing Content-Length, a 404). The
real site/specs/ is read by one integrity test only (its fragments pass the built-in validation)."""
from __future__ import annotations

import datetime
import email.message
import hashlib
import io
import json
import sys
import threading
import time
import urllib.error
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / 'client'))

import cosmoes_client as cc  # noqa: E402

MD = b'# Thym\n\nThym is a language for moves.\n'
MD2 = b'# Thym\n\nRevised: Thym is a language for moves, and for their rests.\n'
WANTS = {'thym': ['source', 'short', 'atem', 'fabula'], 'ascribe': ['source']}
ALL_PAIRS = sorted((s, k) for s, ks in WANTS.items() for k in ks)


def sha(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def frag(slug: str, density: str, text: str = 'A line of the text.') -> bytes:
    return (f'<article class="docoes docoes-{density}" data-doc="{slug}" data-density="{density}" data-lang="en">\n'
            f'<div class="docoes-body"><h1>{slug}</h1><p>{text}</p></div>\n</article>\n').encode('utf-8')


# ------------------------------------------------------------------------------------------------ the stand-in

class _Handler(BaseHTTPRequestHandler):
    def log_message(self, *args):
        pass

    def do_GET(self):
        fake: Fake = self.server.fake
        path = self.path
        fake.requests.append((path, {k.lower(): v for k, v in self.headers.items()}))
        if path in fake.sleep:
            time.sleep(fake.sleep[path])
        if path in fake.redirects:
            self._send(302, b'', 'text/plain', {'Location': fake.redirects[path]})
            return
        if path == '/manifest.json':
            if fake.etag and self.headers.get('If-None-Match') == fake.etag:
                self._send(304, None, None, {'ETag': fake.etag})
                return
            body = fake.manifest_bytes if fake.manifest_bytes is not None else fake.manifest_json()
            self._send(200, body, 'application/json', {'ETag': fake.etag} if fake.etag else None)
            return
        body = fake.bodies.get(path, fake.files().get(path))
        if body is None or path in fake.missing:
            self._send(404, b'not here', 'text/plain')
            return
        self._send(200, body, 'text/html' if path.endswith('.html') else 'text/markdown', length=path not in fake.no_length)

    def _send(self, status, body, ctype, extra=None, length=True):
        try:
            self.send_response(status)
            if ctype:
                self.send_header('Content-Type', ctype)
            if body is not None and length:
                self.send_header('Content-Length', str(len(body)))
            for k, v in (extra or {}).items():
                self.send_header(k, v)
            self.end_headers()
            if body:
                self.wfile.write(body)
        except (BrokenPipeError, ConnectionResetError):
            pass


class Fake:
    """cosmoes.org on 127.0.0.1: `add` documents, read `requests`, set the misbehaviours, `close`."""

    def __init__(self):
        self.docs: dict[str, dict] = {}
        self.requests: list[tuple[str, dict]] = []
        self.etag: str | None = None
        self.manifest_bytes: bytes | None = None        # served verbatim instead of the built manifest
        self.redirects: dict[str, str] = {}             # path -> Location
        self.sleep: dict[str, float] = {}               # path -> seconds before answering
        self.bodies: dict[str, bytes] = {}              # path -> body, for paths no document names
        self.no_length: set[str] = set()                # paths answered without Content-Length
        self.missing: set[str] = set()                  # paths answered 404
        self.server = ThreadingHTTPServer(('127.0.0.1', 0), _Handler)
        self.server.fake = self
        self.port = self.server.server_address[1]
        self.host = f'127.0.0.1:{self.port}'
        self.base = f'http://{self.host}'
        threading.Thread(target=self.server.serve_forever, kwargs={'poll_interval': 0.05}, daemon=True).start()

    def close(self):
        self.server.shutdown()
        self.server.server_close()

    def add(self, slug, name=None, version='0.5.4', host=..., revised='2026-11-03', raw=None, **kinds: bytes) -> dict:
        """A document. `host` defaults to this server; None leaves it out. `raw=None` names a path per kind under
        /raw/<slug>/; `raw=False` leaves `raw` out of the manifest (the client's defaults apply, one document only)."""
        self.docs[slug] = {'name': name or slug.title(), 'version': version, 'host': self.host if host is ... else host,
                           'revised': revised, 'kinds': dict(kinds), 'raw': raw, 'lies': {}, 'nobytes': set(), 'extra': {}}
        return self.docs[slug]

    def path(self, slug: str, kind: str) -> str:
        d = self.docs[slug]
        if d['raw'] is False:
            return cc.DEFAULT_RAW[kind]
        if d['raw'] and kind in d['raw']:
            return d['raw'][kind]
        return f'/raw/{slug}/{cc.FILENAMES[kind]}'

    def manifest(self) -> dict:
        docs = []
        for slug, d in self.docs.items():
            def sha_of(kind):
                return d['lies'].get(kind) or sha(d['kinds'][kind])
            e = {'slug': slug, 'name': d['name'], 'version': d['version'], 'lang': 'en', 'id': f'doc/{slug}', 'oes': 'doc/1'}
            if d['host'] is not None:
                e['host'] = d['host']
            if d['revised']:
                e['revised'] = d['revised']
            if 'source' in d['kinds']:
                e['source'] = {'path': f'specs/{slug}.md', 'sha256': sha_of('source')}
            files = {}
            for kind in cc.FRAGMENTS:
                if kind in d['kinds']:
                    files[kind] = {'path': f'{slug}/{kind}.html', 'sha256': sha_of(kind)}
                    if kind not in d['nobytes']:
                        files[kind]['bytes'] = len(d['kinds'][kind])
            if files:
                e['files'] = files
            if d['raw'] is not False:
                e['raw'] = {kind: self.path(slug, kind) for kind in d['kinds']}
            e.update(d['extra'])
            docs.append(e)
        return {'format': cc.FORMAT, 'exported': '2026-11-03T00:00:00Z', 'by': 'cosmoes-site/test', 'documents': docs}

    def manifest_json(self) -> bytes:
        return json.dumps(self.manifest(), indent=1).encode('utf-8')

    def files(self) -> dict[str, bytes]:
        return {self.path(slug, kind): data for slug, d in self.docs.items() for kind, data in d['kinds'].items()}

    def hits(self, path: str | None = None) -> list[str]:
        return [p for p, _ in self.requests if path is None or p == path]


def seed(fake: Fake) -> None:
    fake.add('thym', 'Thym', source=MD, short=frag('thym', 'short'), atem=frag('thym', 'atem'), fabula=frag('thym', 'fabula'))
    fake.add('ascribe', 'Ascribe', source=b'# Ascribe\n\nA holograph.\n', short=frag('ascribe', 'short'))


@pytest.fixture
def fake():
    f = Fake()
    yield f
    f.close()


def make(fake: Fake, **kw) -> cc.CosmoesClient:
    kw.setdefault('timeout', 2.0)
    kw.setdefault('user_agent', 'cosmoes-client/1 (test)')
    return cc.CosmoesClient(base=fake.base, **kw)


def snapshot(folder: Path, documents_only: bool = False) -> dict:
    """{relative path: (bytes, mtime_ns)} of every file under `folder`."""
    out = {}
    for p in sorted(folder.rglob('*')):
        if p.is_file() and not (documents_only and p.parent == folder):
            out[str(p.relative_to(folder))] = (p.read_bytes(), p.stat().st_mtime_ns)
    return out


def no_temp_files(folder: Path) -> None:
    assert not [p for p in folder.rglob('*') if p.name.startswith('.') and p.name.endswith('.tmp')], 'a temporary file was left'


def state_of(folder: Path) -> dict:
    return json.loads((folder / 'state.json').read_text(encoding='utf-8'))


# ------------------------------------------------------------------------------------------------ sync

def test_first_sync_fills_an_empty_folder(fake, tmp_path):
    seed(fake)
    folder = tmp_path / 'specs'
    r = make(fake).sync(folder, WANTS)
    assert r.checked and r.ok and r.errors == [] and r.skipped == [] and r.unchanged == []
    assert sorted(r.updated) == ALL_PAIRS
    assert (folder / 'thym' / 'source.md').read_bytes() == MD
    for kind in cc.FRAGMENTS:
        assert (folder / 'thym' / f'{kind}.html').read_bytes() == frag('thym', kind)
    assert (folder / 'ascribe' / 'source.md').exists() and not (folder / 'ascribe' / 'short.html').exists()
    assert (folder / 'manifest.json').read_bytes() == fake.manifest_json(), 'the manifest is kept verbatim'
    state = state_of(folder)
    assert state['documents']['thym']['kinds']['source']['sha256'] == sha(MD)
    assert state['documents']['ascribe']['kinds'] == {'source': {'sha256': sha(b'# Ascribe\n\nA holograph.\n'), 'fetched': state['checked']}}
    hits = fake.hits()
    assert hits[0] == '/manifest.json' and len(hits) == 6
    assert sorted(hits[1:]) == sorted(fake.path(s, k) for s, k in ALL_PAIRS)
    assert 0 <= r.elapsed < 10
    no_temp_files(folder)


def test_second_sync_with_nothing_changed_fetches_nothing(fake, tmp_path):
    seed(fake)
    folder = tmp_path / 'specs'
    client = make(fake)
    first = client.sync(folder, WANTS)
    before = snapshot(folder)
    fake.requests.clear()
    r = client.sync(folder, WANTS)
    assert r.ok and r.updated == [] and sorted(r.unchanged) == ALL_PAIRS and r.errors == []
    assert fake.hits() == ['/manifest.json'], 'the manifest and nothing else'
    after = snapshot(folder)
    assert {k: v for k, v in after.items() if k != 'state.json'} == {k: v for k, v in before.items() if k != 'state.json'}
    assert state_of(folder)['updated'] == json.loads(before['state.json'][0])['updated']
    assert first.updated and r.checked


def test_a_changed_source_is_swapped_and_the_fragments_untouched(fake, tmp_path):
    seed(fake)
    folder = tmp_path / 'specs'
    client = make(fake)
    client.sync(folder, WANTS)
    before = snapshot(folder, documents_only=True)
    old_state = state_of(folder)
    fake.docs['thym']['kinds']['source'] = MD2
    fake.requests.clear()
    r = client.sync(folder, WANTS)
    assert r.ok and r.updated == [('thym', 'source')]
    assert sorted(r.unchanged) == sorted(p for p in ALL_PAIRS if p != ('thym', 'source'))
    assert fake.hits() == ['/manifest.json', fake.path('thym', 'source')]
    after = snapshot(folder, documents_only=True)
    assert after['thym/source.md'][0] == MD2
    for name in ('thym/short.html', 'thym/atem.html', 'thym/fabula.html', 'ascribe/source.md'):
        assert after[name] == before[name], f'{name} was touched'
    state = state_of(folder)
    assert state['documents']['thym']['kinds']['source']['sha256'] == sha(MD2)
    assert state['documents']['thym']['kinds']['short'] == old_state['documents']['thym']['kinds']['short']
    assert state['updated'] == state['checked']


def test_a_sha256_mismatch_keeps_the_old_copy_and_reports(fake, tmp_path):
    seed(fake)
    folder = tmp_path / 'specs'
    client = make(fake)
    client.sync(folder, WANTS)
    before = snapshot(folder, documents_only=True)
    old_state = state_of(folder)
    fake.docs['thym']['lies']['source'] = '0' * 64            # the manifest promises bytes the server does not serve
    r = client.sync(folder, WANTS)
    assert r.checked and not r.ok
    assert [(s, k) for s, k, _ in r.errors] == [('thym', 'source')] and 'sha256 mismatch' in r.errors[0][2]
    assert r.updated == [] and sorted(r.unchanged) == sorted(p for p in ALL_PAIRS if p != ('thym', 'source'))
    assert snapshot(folder, documents_only=True) == before
    assert state_of(folder)['documents']['thym'] == old_state['documents']['thym']
    no_temp_files(folder)


def test_a_host_outside_cosmoes_is_refused(fake, tmp_path):
    seed(fake)
    fake.add('evil', host='evil.example', source=MD)
    fake.add('eviler', host='cosmoes.org.evil.example', source=MD)
    fake.add('evilest', host='xcosmoes.org', source=MD)
    folder = tmp_path / 'specs'
    r = make(fake).sync(folder, {'thym': ['source'], 'evil': ['source'], 'eviler': ['source'], 'evilest': ['source']})
    assert r.checked and r.updated == [('thym', 'source')]
    assert sorted((s, k) for s, k, _ in r.errors) == [('evil', 'source'), ('eviler', 'source'), ('evilest', 'source')]
    assert all('host refused' in m for _, _, m in r.errors)
    assert fake.hits() == ['/manifest.json', fake.path('thym', 'source')], 'nothing was asked of the other hosts'
    assert not (folder / 'evil').exists() and 'evil' not in state_of(folder)['documents']


def test_scheme_for_host():
    real = cc.CosmoesClient()
    assert real.scheme_for('cosmoes.org') == 'https' and real.scheme_for('Thym.Cosmoes.org') == 'https'
    for bad in ('evil.example', 'cosmoes.org.evil.example', 'xcosmoes.org', 'cosmoes.org:8443', '127.0.0.1:8000', 'localhost', ''):
        assert real.scheme_for(bad) is None, bad
    rig = cc.CosmoesClient(base='http://127.0.0.1:8791')
    assert rig.scheme_for('127.0.0.1:8791') == 'http' and rig.scheme_for('localhost:1') == 'http'
    assert rig.scheme_for('macro.cosmoes.org') == 'https' and rig.scheme_for('evil.example') is None


def test_a_file_over_max_bytes_is_refused_mid_read(fake, tmp_path):
    big = b'# Big\n' + b'x' * 300_000
    fake.add('big', source=big)
    fake.no_length.add(fake.path('big', 'source'))            # no Content-Length: only reading can tell
    folder = tmp_path / 'specs'
    r = make(fake, max_bytes=100_000).sync(folder, {'big': ['source']})
    assert r.checked and [(s, k) for s, k, _ in r.errors] == [('big', 'source')]
    assert 'over the cap of 100000' in r.errors[0][2] and 'reading stopped' in r.errors[0][2]
    assert not (folder / 'big').exists()
    assert fake.hits(fake.path('big', 'source')) == [fake.path('big', 'source')]


def test_a_declared_size_over_max_bytes_is_refused_before_reading(fake, tmp_path):
    big = frag('big', 'short', 'y' * 300_000)
    fake.add('big', short=big, source=MD)
    folder = tmp_path / 'specs'
    r = make(fake, max_bytes=100_000).sync(folder, {'big': ['short', 'source']})
    assert sorted((s, k) for s, k, _ in r.errors) == [('big', 'short'), ('big', 'source')]
    by = {k: m for _, k, m in r.errors}
    assert 'in the manifest, over the cap' in by['short'] and 'held back' in by['source']
    assert fake.hits(fake.path('big', 'short')) == [], 'the manifest already said it was too big'
    assert not (folder / 'big').exists()
    # a Content-Length over the cap is refused before the body is read
    fake.docs['big']['nobytes'].add('short')
    r = make(fake, max_bytes=100_000).sync(folder, {'big': ['short']})
    assert 'bytes declared, over the cap' in r.errors[0][2]
    assert fake.hits(fake.path('big', 'short')) == [fake.path('big', 'short')]


def test_a_timeout_reports_and_leaves_the_folder_as_it_was(fake, tmp_path):
    seed(fake)
    folder = tmp_path / 'specs'
    make(fake).sync(folder, WANTS)
    before = snapshot(folder, documents_only=True)
    fake.docs['thym']['kinds']['source'] = MD2
    fake.sleep[fake.path('thym', 'source')] = 1.0
    r = make(fake, timeout=0.2).sync(folder, WANTS)
    assert r.checked and [(s, k, 'timed out' in m) for s, k, m in r.errors] == [('thym', 'source', True)]
    assert snapshot(folder, documents_only=True) == before
    assert state_of(folder)['documents']['thym']['kinds']['source']['sha256'] == sha(MD)
    # the manifest itself timing out: not checked, nothing written, not even state.json
    whole = snapshot(folder)
    fake.sleep['/manifest.json'] = 1.0
    r = make(fake, timeout=0.2).sync(folder, WANTS)
    assert not r.checked and r.errors == [('*', 'manifest', 'manifest: timed out')]
    assert r.updated == [] and r.unchanged == []
    assert snapshot(folder) == whole
    no_temp_files(folder)


def test_a_manifest_that_is_not_json_or_lacks_documents_reports(fake, tmp_path):
    seed(fake)
    folder = tmp_path / 'specs'
    fake.manifest_bytes = b'<html>not json'
    r = make(fake).sync(folder, WANTS)
    assert not r.checked and len(r.errors) == 1 and r.errors[0][:2] == ('*', 'manifest') and 'not JSON' in r.errors[0][2]
    assert not (folder / 'state.json').exists() and not (folder / 'manifest.json').exists()
    fake.manifest_bytes = json.dumps({'format': cc.FORMAT, 'nope': []}).encode()
    r = make(fake).sync(folder, WANTS)
    assert not r.checked and 'no documents list' in r.errors[0][2]
    fake.manifest_bytes = json.dumps({'format': 'docoes-export/9', 'documents': []}).encode()
    r = make(fake).sync(folder, WANTS)
    assert not r.checked and 'format' in r.errors[0][2]
    fake.manifest_bytes = b'[]'
    r = make(fake).sync(folder, WANTS)
    assert not r.checked and 'not an object' in r.errors[0][2]
    assert fake.hits() == ['/manifest.json'] * 4
    # after a good sync, a bad manifest changes nothing in the folder
    fake.manifest_bytes = None
    assert make(fake).sync(folder, WANTS).ok
    whole = snapshot(folder)
    fake.manifest_bytes = b'{'
    r = make(fake).sync(folder, WANTS)
    assert not r.checked and snapshot(folder) == whole


def test_a_validation_failure_keeps_the_old_copy(fake, tmp_path):
    seed(fake)
    folder = tmp_path / 'specs'
    client = make(fake)
    client.sync(folder, WANTS)
    before = snapshot(folder, documents_only=True)
    fake.docs['thym']['kinds']['short'] = frag('thym', 'short', '<script>alert(1)</script>')
    r = client.sync(folder, WANTS)
    assert [(s, k) for s, k, _ in r.errors] == [('thym', 'short')]
    assert r.errors[0][2].startswith('validation: unsafe: <script')
    assert snapshot(folder, documents_only=True) == before
    # an app's own hook: a string refuses, an exception refuses
    fake.docs['thym']['kinds']['short'] = frag('thym', 'short', 'fine again')
    fake.docs['ascribe']['kinds']['source'] = b'# Ascribe\n\nRevised.\n'
    r = client.sync(folder, WANTS, validate=lambda slug, kind, data: 'not for me' if slug == 'ascribe' else None)
    assert r.updated == [('thym', 'short')] and r.errors == [('ascribe', 'source', 'validation: not for me')]
    assert (folder / 'ascribe' / 'source.md').read_bytes() == b'# Ascribe\n\nA holograph.\n'

    def boom(slug, kind, data):
        raise RuntimeError('hook broke')
    r = client.sync(folder, WANTS, validate=boom)
    assert r.errors == [('ascribe', 'source', 'validation: RuntimeError: hook broke')]
    assert (folder / 'ascribe' / 'source.md').read_bytes() == b'# Ascribe\n\nA holograph.\n'


def test_a_redirect_off_host_is_not_followed(fake, tmp_path):
    seed(fake)
    folder = tmp_path / 'specs'
    fake.redirects[fake.path('thym', 'source')] = 'https://evil.example/raw/source.md'
    r = make(fake).sync(folder, {'thym': ['source'], 'ascribe': ['source']})
    assert r.updated == [('ascribe', 'source')]
    assert [(s, k) for s, k, _ in r.errors] == [('thym', 'source')] and 'redirect off-host refused' in r.errors[0][2]
    assert not (folder / 'thym').exists()
    # the same host on another port is another host
    fake.redirects[fake.path('thym', 'source')] = f'http://127.0.0.1:{fake.port + 1}/raw/source.md'
    r = make(fake).sync(folder, {'thym': ['source']})
    assert 'redirect off-host refused' in r.errors[0][2]
    # a redirect on the same host is followed
    fake.redirects[fake.path('thym', 'source')] = f'{fake.base}/raw/moved.md'
    fake.bodies['/raw/moved.md'] = MD
    r = make(fake).sync(folder, {'thym': ['source']})
    assert r.ok and r.updated == [('thym', 'source')] and (folder / 'thym' / 'source.md').read_bytes() == MD
    assert '/raw/moved.md' in fake.hits()


def test_state_json_shape(fake, tmp_path):
    seed(fake)
    fake.docs['thym']['extra']['edition'] = '0.5.4-ed'          # an edition is the version when present
    fake.docs['ascribe']['revised'] = None
    folder = tmp_path / 'specs'
    t = datetime.datetime(2026, 11, 3, 10, 0, 0, tzinfo=datetime.timezone.utc).timestamp()
    client = make(fake, clock=lambda: t)
    r = client.sync(folder, WANTS)
    assert r.ok and r.elapsed == 0.0
    state = state_of(folder)
    assert list(state) == ['checked', 'updated', 'etag', 'documents']
    iso = '2026-11-03T10:00:00Z'
    assert state == {
        'checked': iso, 'updated': iso, 'etag': None,
        'documents': {
            'thym': {'name': 'Thym', 'version': '0.5.4-ed', 'revised': '2026-11-03', 'host': fake.host,
                     'kinds': {'source': {'sha256': sha(MD), 'fetched': iso},
                               'short': {'sha256': sha(frag('thym', 'short')), 'fetched': iso},
                               'atem': {'sha256': sha(frag('thym', 'atem')), 'fetched': iso},
                               'fabula': {'sha256': sha(frag('thym', 'fabula')), 'fetched': iso}}},
            'ascribe': {'name': 'Ascribe', 'version': '0.5.4', 'revised': None, 'host': fake.host,
                        'kinds': {'source': {'sha256': sha(b'# Ascribe\n\nA holograph.\n'), 'fetched': iso}}}}}
    assert list(state['documents']['thym']) == ['name', 'version', 'revised', 'host', 'kinds']
    # a later check that changes nothing moves `checked`, not `updated`; metadata follows the manifest
    fake.docs['thym']['revised'] = '2026-11-04'
    later = make(fake, clock=lambda: t + 3600).sync(folder, WANTS)
    assert later.ok and later.updated == []
    state = state_of(folder)
    assert state['checked'] == '2026-11-03T11:00:00Z' and state['updated'] == iso
    assert state['documents']['thym']['revised'] == '2026-11-04'
    assert state['documents']['thym']['kinds']['source']['fetched'] == iso
    assert cc.load_state(folder) == state


def test_etag_304_round_trip(fake, tmp_path):
    seed(fake)
    folder = tmp_path / 'specs'
    client = make(fake)
    r = client.sync(folder, WANTS)
    assert r.ok and 'if-none-match' not in fake.requests[0][1], 'nothing to send the first time'
    assert state_of(folder)['etag'] is None, 'the server gave no ETag'
    fake.etag = '"v1"'
    fake.requests.clear()
    assert client.sync(folder, WANTS).ok
    assert state_of(folder)['etag'] == '"v1"'
    fake.requests.clear()
    r = client.sync(folder, WANTS)
    assert r.checked and r.ok and r.updated == [] and sorted(r.unchanged) == ALL_PAIRS
    assert fake.hits() == ['/manifest.json'] and fake.requests[0][1].get('if-none-match') == '"v1"'
    assert state_of(folder)['etag'] == '"v1"'
    # the manifest changes: a new ETag, a 200, the changed file fetched
    fake.etag = '"v2"'
    fake.docs['thym']['kinds']['source'] = MD2
    fake.requests.clear()
    r = client.sync(folder, WANTS)
    assert r.ok and r.updated == [('thym', 'source')]
    assert fake.requests[0][1].get('if-none-match') == '"v1"' and fake.hits() == ['/manifest.json', fake.path('thym', 'source')]
    assert state_of(folder)['etag'] == '"v2"' and (folder / 'manifest.json').read_bytes() == fake.manifest_json()
    # a 304 while a newly wanted kind is missing locally: the kept manifest still plans it
    fake.requests.clear()
    r = client.sync(folder, {**WANTS, 'ascribe': ['source', 'short']})
    assert r.ok and r.updated == [('ascribe', 'short')] and fake.hits() == ['/manifest.json', fake.path('ascribe', 'short')]
    # without a local manifest.json no ETag is sent, even when state.json holds one
    (folder / 'manifest.json').unlink()
    fake.requests.clear()
    assert client.sync(folder, WANTS).ok
    assert 'if-none-match' not in fake.requests[0][1] and (folder / 'manifest.json').exists()


def test_a_document_with_one_bad_kind_is_not_half_written(fake, tmp_path):
    seed(fake)
    folder = tmp_path / 'specs'
    client = make(fake)
    fake.docs['thym']['lies']['atem'] = 'f' * 64
    r = client.sync(folder, WANTS)
    assert r.checked and r.updated == [('ascribe', 'source')] and r.unchanged == []
    errors = {(s, k): m for s, k, m in r.errors}
    assert set(errors) == {('thym', 'source'), ('thym', 'short'), ('thym', 'atem'), ('thym', 'fabula')}
    assert 'sha256 mismatch' in errors[('thym', 'atem')]
    assert all(errors[('thym', k)] == 'held back: another kind of thym failed' for k in ('source', 'short', 'fabula'))
    assert not (folder / 'thym').exists(), 'nothing of thym was written'
    assert list(state_of(folder)['documents']) == ['ascribe']
    no_temp_files(folder)
    # a held document after a good sync: the kinds that fetched well are not written either
    del fake.docs['thym']['lies']['atem']
    assert client.sync(folder, WANTS).ok
    before = snapshot(folder, documents_only=True)
    fake.docs['thym']['kinds']['source'] = MD2
    fake.docs['thym']['kinds']['atem'] = frag('thym', 'atem', 'revised')
    fake.docs['thym']['lies']['atem'] = 'f' * 64
    r = client.sync(folder, WANTS)
    assert sorted((s, k) for s, k, _ in r.errors) == [('thym', 'atem'), ('thym', 'source')]
    assert sorted(r.unchanged) == [('ascribe', 'source'), ('thym', 'fabula'), ('thym', 'short')]
    assert snapshot(folder, documents_only=True) == before
    assert state_of(folder)['documents']['thym']['kinds']['source']['sha256'] == sha(MD)


def test_every_wanted_pair_lands_in_one_list(fake, tmp_path):
    seed(fake)
    fake.add('nohost', host=None, source=MD)
    fake.add('evil', host='evil.example', source=MD)
    folder = tmp_path / 'specs'
    r = make(fake).sync(folder, {'*': ['source'], 'thym': ['source', 'short', 'nonsense'], 'missing': ['source']})
    assert r.checked
    assert r.updated == [('ascribe', 'source')] and r.unchanged == []
    assert r.skipped == [('nohost', 'source')], 'a document without a host is skipped, not an error'
    errors = {(s, k): m for s, k, m in r.errors}
    assert set(errors) == {('evil', 'source'), ('missing', 'source'), ('thym', 'nonsense'), ('thym', 'source'), ('thym', 'short')}
    assert errors[('missing', 'source')] == 'not in the manifest' and errors[('thym', 'nonsense')] == "unknown kind 'nonsense'"
    assert errors[('thym', 'source')] == errors[('thym', 'short')] == 'held back: another kind of thym failed'
    assert not (folder / 'thym').exists(), 'the unknown kind held thym back'
    seen = r.updated + r.unchanged + r.skipped + [(s, k) for s, k, _ in r.errors]
    assert len(seen) == len(set(seen)) == 7


def test_default_raw_paths_when_the_manifest_has_none(fake, tmp_path):
    fake.add('solo', raw=False, source=MD, short=frag('solo', 'short'))
    assert 'raw' not in fake.manifest()['documents'][0]
    folder = tmp_path / 'specs'
    r = make(fake).sync(folder, {'solo': ['source', 'short']})
    assert r.ok and sorted(r.updated) == [('solo', 'short'), ('solo', 'source')]
    assert fake.hits()[1:] == ['/raw/source.md', '/raw/short.html'] or sorted(fake.hits()[1:]) == ['/raw/short.html', '/raw/source.md']


def test_a_404_and_a_corrupt_state(fake, tmp_path):
    seed(fake)
    folder = tmp_path / 'specs'
    client = make(fake)
    assert client.sync(folder, WANTS).ok
    fake.docs['ascribe']['kinds']['source'] = b'# Ascribe\n\nGone.\n'
    fake.missing.add(fake.path('ascribe', 'source'))
    r = client.sync(folder, WANTS)
    assert r.errors == [('ascribe', 'source', 'ascribe source: HTTP 404')]
    fake.missing.clear()
    (folder / 'state.json').write_text('garbage', encoding='utf-8')
    fake.requests.clear()
    r = client.sync(folder, WANTS)
    assert r.ok and sorted(r.updated) == ALL_PAIRS, 'a corrupt state only means everything is fetched again'
    assert len(fake.hits()) == 6 and state_of(folder)['documents']['ascribe']['kinds']['source']['sha256'] == sha(b'# Ascribe\n\nGone.\n')


def test_the_user_agent_names_the_client_and_the_app(fake, tmp_path):
    seed(fake)
    make(fake, user_agent='cosmoes-client/1 (enough 0.5.4)').sync(tmp_path / 'specs', {'thym': ['source']})
    assert [h.get('user-agent') for _, h in fake.requests] == ['cosmoes-client/1 (enough 0.5.4)'] * 2


def test_a_folder_that_cannot_be_made_is_an_error_not_an_exception(fake, tmp_path):
    seed(fake)
    blocker = tmp_path / 'file'
    blocker.write_text('not a folder', encoding='utf-8')
    r = make(fake).sync(blocker / 'specs', WANTS)
    assert not r.checked and r.errors[0][:2] == ('*', 'folder') and fake.hits() == []


# ------------------------------------------------------------------------------------------------ plan, fetch, manifest

def test_plan_against_a_real_shaped_manifest():
    manifest = {'format': cc.FORMAT, 'documents': [
        {'slug': 'macrocosm-oes', 'name': 'MacroCOSM OES', 'version': '0.0.2', 'edition': '0.5.4', 'host': 'macro.cosmoes.org',
         'revised': '2026-11-03', 'source': {'path': 'specs/macrocosm-oes.md', 'sha256': 'a' * 64},
         'files': {'short': {'path': 'macrocosm-oes/short.html', 'sha256': 'b' * 64, 'bytes': 610803}},
         'raw': {'source': '/raw/source.md', 'short': '/raw/short.html', 'atem': '/raw/atem.html', 'fabula': '/raw/fabula.html'}},
        {'slug': 'thym', 'name': 'Thym', 'version': '0.5.4', 'host': 'thym.cosmoes.org',
         'source': {'path': 'specs/thym.md', 'sha256': 'c' * 64}},
        {'slug': 'ascribe', 'name': 'Ascribe', 'version': '0.5.4', 'source': {'path': 'specs/ascribe.md', 'sha256': 'd' * 64}},
        {'slug': 'comprise-oes', 'name': 'Comprise OES', 'host': 'comprise.cosmoes.org', 'source': {'path': 'x', 'sha256': 'nope'}},
        {'slug': 'apex', 'name': 'OES', 'host': 'cosmoes.org', 'source': {'path': 'x', 'sha256': 'e' * 64},
         'raw': {'source': '//evil.example/raw/source.md'}},
        {'slug': 'local', 'name': 'Local', 'host': '127.0.0.1:8000', 'source': {'path': 'x', 'sha256': 'f' * 64}},
        'not a document']}
    client = cc.CosmoesClient()                                 # the real base; plan fetches nothing
    state = {'documents': {'thym': {'kinds': {'source': {'sha256': 'c' * 64}}}}}
    plan = client.plan(state, manifest, {'*': ['source'], 'macrocosm-oes': ['source', 'short'], 'missing': ['source']})
    by = {(f.slug, f.kind): f for f in plan}
    assert len(by) == len(plan)
    m = by[('macrocosm-oes', 'source')]
    assert (m.url, m.sha256, m.current, m.size, m.error) == ('https://macro.cosmoes.org/raw/source.md', 'a' * 64, False, None, None)
    s = by[('macrocosm-oes', 'short')]
    assert (s.url, s.sha256, s.size) == ('https://macro.cosmoes.org/raw/short.html', 'b' * 64, 610803)
    t = by[('thym', 'source')]
    assert (t.url, t.current) == ('https://thym.cosmoes.org/raw/source.md', True), 'the defaults, and the local copy matches'
    assert ('ascribe', 'source') not in by, 'no host: skipped'
    assert by[('comprise-oes', 'source')].error == 'no sha256 in the manifest'
    assert by[('apex', 'source')].error.startswith('raw path refused')
    assert by[('local', 'source')].error.startswith('host refused')
    assert by[('missing', 'source')].error == 'not in the manifest'
    assert [f.slug for f in plan][:3] == ['macrocosm-oes', 'macrocosm-oes', 'thym'], "the manifest's order"


class FakeResponse:
    def __init__(self, body: bytes, status: int = 200, headers: dict | None = None):
        self._body, self.status = io.BytesIO(body), status
        self.headers = email.message.Message()
        for k, v in (headers or {}).items():
            self.headers[k] = v

    def read(self, n: int = -1) -> bytes:
        return self._body.read(n)

    def getcode(self) -> int:
        return self.status

    def __enter__(self):
        return self

    def __exit__(self, *exc):
        return False


class FakeOpener:
    """What an app's tests inject: `routes` maps a URL to (status, body, headers); anything else is a 404."""

    def __init__(self, routes: dict):
        self.routes, self.calls = routes, []

    def open(self, req, timeout=None):
        self.calls.append((req.full_url, timeout, {k.lower(): v for k, v in req.header_items()}))
        if req.full_url not in self.routes:
            raise urllib.error.HTTPError(req.full_url, 404, 'not here', email.message.Message(), None)
        status, body, headers = self.routes[req.full_url]
        if status == 304:
            raise urllib.error.HTTPError(req.full_url, 304, 'not modified', FakeResponse(b'', 304, headers).headers, None)
        return FakeResponse(body, status, headers)


def test_fetch_and_manifest_with_an_injected_opener(tmp_path):
    manifest = {'format': cc.FORMAT, 'documents': [
        {'slug': 'thym', 'name': 'Thym', 'version': '0.5.4', 'host': 'thym.cosmoes.org', 'revised': '2026-11-03',
         'source': {'path': 'specs/thym.md', 'sha256': sha(MD)},
         'files': {'short': {'path': 'thym/short.html', 'sha256': sha(frag('thym', 'short')), 'bytes': len(frag('thym', 'short'))}}}]}
    opener = FakeOpener({'https://cosmoes.org/manifest.json': (200, json.dumps(manifest).encode(), {'ETag': '"m1"'}),
                         'https://thym.cosmoes.org/raw/source.md': (200, MD, {'Content-Length': str(len(MD))}),
                         'https://thym.cosmoes.org/raw/short.html': (200, frag('thym', 'short'), {})})
    client = cc.CosmoesClient(opener=opener, user_agent='cosmoes-client/1 (app test)', timeout=1.5)
    assert client.manifest() == manifest
    assert opener.calls[0][0] == 'https://cosmoes.org/manifest.json' and opener.calls[0][1] == 1.5
    assert opener.calls[0][2]['user-agent'] == 'cosmoes-client/1 (app test)'
    # fetch: refused before the opener is asked when the address is off cosmoes.org
    with pytest.raises(cc.ClientError, match='address refused'):
        client.fetch(cc.Fetch('thym', 'source', 'https://evil.example/raw/source.md', sha(MD), False))
    with pytest.raises(cc.ClientError, match='address refused'):
        client.fetch(cc.Fetch('thym', 'source', 'http://thym.cosmoes.org/raw/source.md', sha(MD), False))
    assert len(opener.calls) == 1
    assert client.fetch(cc.Fetch('thym', 'source', 'https://thym.cosmoes.org/raw/source.md', sha(MD), False)) == MD
    with pytest.raises(cc.ClientError, match='sha256 mismatch'):
        client.fetch(cc.Fetch('thym', 'source', 'https://thym.cosmoes.org/raw/source.md', '0' * 64, False))
    with pytest.raises(cc.ClientError, match='HTTP 404'):
        client.fetch(cc.Fetch('thym', 'atem', 'https://thym.cosmoes.org/raw/atem.html', '0' * 64, False))
    with pytest.raises(cc.ClientError, match='no sha256'):
        client.fetch(cc.Fetch('thym', 'atem', '', '', False, error='no sha256 in the manifest'))
    # the whole sync over the injected opener, then a 304
    folder = tmp_path / 'specs'
    r = client.sync(folder, {'thym': ['source', 'short']})
    assert r.ok and sorted(r.updated) == [('thym', 'short'), ('thym', 'source')] and state_of(folder)['etag'] == '"m1"'
    opener.routes['https://cosmoes.org/manifest.json'] = (304, b'', {'ETag': '"m1"'})
    before = len(opener.calls)
    r = client.sync(folder, {'thym': ['source', 'short']})
    assert r.ok and r.updated == [] and len(r.unchanged) == 2 and len(opener.calls) == before + 1
    assert opener.calls[-1][2]['if-none-match'] == '"m1"'


def test_the_base_is_checked():
    for ok in ('https://cosmoes.org', 'https://cosmoes.org/', 'https://macro.cosmoes.org', 'http://localhost:8000', 'http://127.0.0.1:1'):
        cc.CosmoesClient(base=ok)
    assert cc.CosmoesClient(base='https://cosmoes.org/').base == 'https://cosmoes.org'
    assert cc.CosmoesClient(base='http://localhost:8000').loopback and not cc.CosmoesClient().loopback
    for bad in ('http://cosmoes.org', 'https://example.com', 'https://cosmoes.org/path', 'https://cosmoes.org?x=1',
                'https://127.0.0.1', 'ftp://cosmoes.org', 'cosmoes.org', 'https://cosmoes.org.evil.example', ''):
        with pytest.raises(ValueError):
            cc.CosmoesClient(base=bad)


# ------------------------------------------------------------------------------------------------ validation

def test_basic_validate():
    v = cc.basic_validate
    assert v('thym', 'source', b'# Thym\n') is None
    assert v('thym', 'source', b'  \n') == 'empty markdown'
    assert v('thym', 'source', b'\xff\xfe\x00') .startswith('not UTF-8')
    assert v('thym', 'short', frag('thym', 'short')) is None
    assert v('thym', 'short', b'<p>no article</p>') == 'no <article in the fragment'
    assert v('thym', 'nonsense', b'<article>') == "unknown kind 'nonsense'"
    assert v('thym', 'short', 'x') == 'not bytes'
    bad = {'<script>': '<script>alert(1)</script>', '<style>': '<style>p{}</style>', '<SCRIPT>': '<SCRIPT src=x>',
           'onload=': '<img onload="x()" src="y">', 'onclick=': '<p ONCLICK="x">t</p>', 'javascript:': '<a href="javascript:alert(1)">x</a>',
           'spaced javascript:': '<a href=" java\nscript:x">x</a>', 'entity javascript:': '<a href="&#106;avascript:x">x</a>',
           'vbscript:': '<a href="vbscript:x">x</a>', '<iframe>': '<iframe src="x"></iframe>', '<frame>': '<frame src=x>',
           '<object>': '<object data=x></object>', '<embed>': '<embed src=x>', '<base>': '<base href=x>',
           '<link>': '<link rel=stylesheet href=x>', '<meta>': '<meta http-equiv=refresh content=0>', '<form>': '<form action=x></form>',
           'style=': '<p style="color:red">t</p>'}
    for why, html in bad.items():
        got = v('thym', 'short', frag('thym', 'short', html))
        assert got and got.startswith('unsafe: '), (why, got)
    assert cc.unsafe('<a href="#x" data-term="T:term/word" title="a word">x</a>') == []


def test_the_real_export_passes_basic_validate():
    pages = sorted((ROOT / 'site' / 'specs').glob('*/*.html'))
    assert len(pages) >= 12, 'four documents at three densities'
    for p in pages:
        assert cc.basic_validate(p.parent.name, p.stem, p.read_bytes()) is None, p


# ------------------------------------------------------------------------------------------------ the command line

def test_the_command_line(fake, tmp_path, capsys):
    seed(fake)
    folder = str(tmp_path / 'specs')
    assert cc.main(['sync', folder, '--base', fake.base, '--wants', 'thym=source,short', '--app', 'rig']) == 0
    out = capsys.readouterr().out
    assert 'checked: yes' in out and 'updated: 2 thym source, thym short' in out and 'errors: 0' in out
    assert fake.requests[0][1]['user-agent'] == 'cosmoes-client/1 (rig)'
    assert cc.main(['status', folder]) == 0
    out = capsys.readouterr().out
    assert 'thym: Thym 0.5.4  revised 2026-11-03' in out and '  source ' in out and '  short ' in out and 'ascribe' not in out
    assert cc.main(['sync', folder, '--base', fake.base, '--wants', 'thym', '--all-kinds']) == 0
    assert 'updated: 2 thym atem, thym fabula' in capsys.readouterr().out
    fake.add('evil', host='evil.example', source=MD)
    assert cc.main(['sync', folder, '--base', fake.base, '--wants', 'evil=source']) == 1
    out = capsys.readouterr().out
    assert 'errors: 1' in out and 'evil source: host refused' in out
    assert cc.main(['sync', folder, '--base', fake.base]) == 1, 'the default wants every document, source: evil included'
    fake.docs.pop('evil')
    assert cc.main(['sync', str(tmp_path / 'two'), '--base', fake.base]) == 0
    assert 'updated: 2 thym source, ascribe source' in capsys.readouterr().out
    fake.sleep['/manifest.json'] = 1.0
    assert cc.main(['sync', folder, '--base', fake.base, '--timeout', '0.2']) == 1
    out = capsys.readouterr().out
    assert 'checked: no' in out and 'manifest: timed out' in out
    assert cc.main(['status', str(tmp_path / 'nothing')]) == 1
    assert 'no state.json' in capsys.readouterr().out
    assert cc.main(['sync', folder, '--base', 'https://example.com']) == 2
    assert 'error: base must be' in capsys.readouterr().out
    with pytest.raises(SystemExit):
        cc.main([])

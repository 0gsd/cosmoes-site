#!/usr/bin/env python3
"""Build site/specs/ (cosmoes/specs.py) from specs/: the texts, as enough's DocOES exports them, each at three
densities, with the registry's fields and a copy of each source.

    .venv/bin/python scripts/build_specs.py --enough ~/METMcloud/METMroot/enough-dev
    .venv/bin/python scripts/build_specs.py --enough ~/METMcloud/METMroot/enough-dev --check

specs/specs.json is the registry: the one place names, editions and hosts are declared. One entry per text, with
`slug`, `file` (under specs/), `name` (no number in it), `edition`, `describes` (the format versions the text
describes, `{"thym": "1"}`), `host` (`thym.cosmoes.org`; `cosmoes.org` for the apex text), `revised` (an ISO date)
and, where the text carries the reference generated from the manifests (MacroCOSM OES), `reference: true`.
The build validates it first and refuses the whole run on any fault.

The export reads a document from inside a sources root and the manifests from `defaults/cosm/manifests/`
under it, so the build makes that root in a temporary folder: the texts as `specs/<file>`, the manifests copied from
the enough checkout given by --enough. Then, in that checkout, with its own `.venv/bin/python` (or --python), once per
entry, in the registry's order:

    python -m enough.docoes export specs/<file> <out> --sources <root> --slug <slug> --name <name>
        --version <edition> --page short=/ --page atem=/atem --page fabula=/fabula --no-marks [--reference]

Each is an ad hoc export of the text under its slug (enough 0.5.1's export; the registered-document form, which
joined the Comprise chapters to MacroCOSM OES, is not used). `--page …` makes the fragments' links across densities
root-absolute, so they resolve on whichever host serves the document; `--no-marks` leaves the in-app viewer's margin
marks out. The merged manifest then gains, per document, `edition`, `describes`, `host`, `revised`, `raw` (the raw
endpoints' paths) and `files.source` (the text, copied as `<slug>/source.md`), and at the top `source` becomes this
repository's commit (`git rev-parse --short HEAD`, `dirty` when the tree has changes) with `by` the enough version
that exported. The result is checked as the site will read it and only then replaces site/specs/; when any step
fails, nothing here is changed.

`--check` builds the same way into a temporary folder and compares it with site/specs/ byte for byte, the manifest's
`exported` time and `source` commit apart: exit 1 on a difference. That is the test that the committed export is in
step with specs/ (CONTRIBUTING.md). It needs no credentials and nothing from the network; the export builds its
volumes in a temporary folder of its own and leaves ~/enough alone.

    --enough PATH    the enough checkout (required): enough/docoes.py and defaults/cosm/manifests/ are read there
    --python PATH    the interpreter that runs the export (default: PATH/.venv/bin/python)
    --check          build into a temporary folder and compare with site/specs/ instead of replacing it
"""
from __future__ import annotations

import argparse
import datetime
import hashlib
import json
import logging
import re
import shutil
import subprocess
import sys
import tempfile
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from cosmoes import specs  # noqa: E402
from cosmoes.app import DOMAIN, REDIRECTS, SUB_RE  # noqa: E402

DEST = specs.FOLDER                                               # site/specs/
SPECS = ROOT / 'specs'                                            # the texts and the registry
REGISTRY = SPECS / 'specs.json'
MANIFESTS_DIR = 'defaults/cosm/manifests'                         # enough's manifests, under a sources root
PAGES = specs.PAGES                                               # --page density=href: each host's addresses
RAW = specs.RAW                                                   # the raw endpoints every document host serves
REQUIRED = ('slug', 'file', 'name', 'edition', 'describes', 'host', 'revised')
OPTIONAL = ('reference',)
FILE_RE = re.compile(r'^[a-z0-9][a-z0-9-]*\.md$')
EDITION_RE = re.compile(r'^[0-9]+(\.[0-9]+)*$')
FORMAT_RE = re.compile(r'^[a-z][a-z0-9-]*$')
TIMEOUT = 600


# ----------------------------------------------------------------------------- the registry

def registry(path: Path = REGISTRY, specs_dir: Path = SPECS) -> list[dict]:
    """specs/specs.json, validated: the entries in order, or SystemExit listing every fault."""
    try:
        entries = json.loads(path.read_text(encoding='utf-8'))
    except (OSError, ValueError) as e:
        raise SystemExit(f'{path}: cannot be read as JSON ({e})')
    faults = problems(entries, specs_dir)
    if faults:
        raise SystemExit(f'{path}:\n' + ''.join(f'    {f}\n' for f in faults) + 'nothing was changed')
    return entries


def problems(entries, specs_dir: Path = SPECS) -> list[str]:
    """What is wrong with a registry (an empty list when nothing is)."""
    if not isinstance(entries, list) or not entries:
        return ['the registry is not a non-empty list of entries']
    out: list[str] = []
    seen: dict[str, set] = {'slug': set(), 'file': set(), 'host': set()}
    for i, e in enumerate(entries):
        at = f'entry {i + 1}'
        if not isinstance(e, dict):
            out.append(f'{at}: not an object')
            continue
        at = f'entry {i + 1} ({e.get("slug")!r})'
        missing = [k for k in REQUIRED if k not in e]
        extra = [k for k in e if k not in REQUIRED + OPTIONAL]
        if missing:
            out.append(f'{at}: missing {", ".join(missing)}')
        if extra:
            out.append(f'{at}: unknown {", ".join(extra)} (the keys are {", ".join(REQUIRED + OPTIONAL)})')
        slug, file, name = e.get('slug'), e.get('file'), e.get('name')
        if not isinstance(slug, str) or not specs.SLUG_RE.match(slug):
            out.append(f'{at}: slug must be a-z, 0-9 and -, up to 64 characters')
        if not isinstance(file, str) or not FILE_RE.match(file):
            out.append(f'{at}: file must be a name like thym.md, directly under specs/')
        elif not (specs_dir / file).is_file():
            out.append(f'{at}: specs/{file} does not exist')
        if not isinstance(name, str) or not name.strip() or len(name) > 120:
            out.append(f'{at}: name must be a non-empty string (up to 120 characters)')
        elif re.search(r'\d', name):
            out.append(f'{at}: name {name!r} carries a number; the edition is a field, never part of the name')
        if not isinstance(e.get('edition'), str) or not EDITION_RE.match(e.get('edition') or ''):
            out.append(f'{at}: edition must be a dotted number as a string ("0.5.4")')
        d = e.get('describes')
        if not isinstance(d, dict) or not all(isinstance(k, str) and FORMAT_RE.match(k) and isinstance(v, str)
                                               and EDITION_RE.match(v) for k, v in d.items()):
            out.append(f'{at}: describes must map format names (a-z, 0-9, -) to version strings ("1", "0.5.4")')
        host = e.get('host')
        if not isinstance(host, str) or not (host == DOMAIN or (host.endswith('.' + DOMAIN)
                                                                and SUB_RE.match(host[:-len(DOMAIN) - 1] or '-'))):
            out.append(f'{at}: host must be {DOMAIN} or one label under it (thym.{DOMAIN})')
        elif host != DOMAIN and host[:-len(DOMAIN) - 1] in REDIRECTS:
            out.append(f'{at}: {host} is a redirect host ({", ".join(REDIRECTS)}); a document cannot live there')
        r = e.get('revised')
        try:
            if not isinstance(r, str) or not specs.DATE_RE.match(r):
                raise ValueError
            datetime.date.fromisoformat(r)
        except ValueError:
            out.append(f'{at}: revised must be a date, YYYY-MM-DD')
        if 'reference' in e and not isinstance(e['reference'], bool):
            out.append(f'{at}: reference must be true or false')
        for k in seen:
            v = e.get(k)
            if isinstance(v, str):
                if v in seen[k]:
                    out.append(f'{at}: {k} {v!r} is used twice')
                seen[k].add(v)
    return out


# ----------------------------------------------------------------------------- the export

def sources_root(tmp: Path, enough: Path, entries: list[dict], specs_dir: Path = SPECS) -> Path:
    """A sources root for the export: the texts as specs/<file>, enough's manifests at their place."""
    root = tmp / 'sources'
    (root / 'specs').mkdir(parents=True)
    for e in entries:
        shutil.copyfile(specs_dir / e['file'], root / 'specs' / e['file'])
    manifests = enough / MANIFESTS_DIR
    if not manifests.is_dir():
        raise SystemExit(f'{enough} has no {MANIFESTS_DIR}/: not an enough checkout; nothing was changed')
    shutil.copytree(manifests, root / MANIFESTS_DIR)
    return root


def export(python: Path, enough: Path, root: Path, entry: dict, out: Path) -> None:
    """One run of the export into `out`, which merges into the manifest there. SystemExit, saying why, if it fails."""
    cmd = [str(python), '-m', 'enough.docoes', 'export', f'specs/{entry["file"]}', str(out), '--sources', str(root),
           '--slug', entry['slug'], '--name', entry['name'], '--version', entry['edition'], '--no-marks']
    if entry.get('reference'):
        cmd.append('--reference')
    for density, href in PAGES.items():
        cmd += ['--page', f'{density}={href}']
    try:
        r = subprocess.run(cmd, cwd=enough, capture_output=True, text=True, timeout=TIMEOUT)
    except OSError as e:
        raise SystemExit(f'{entry["slug"]}: could not run {python}: {e}; nothing was changed')
    except subprocess.TimeoutExpired:
        raise SystemExit(f'{entry["slug"]}: the export ran for more than {TIMEOUT // 60} minutes; nothing was changed')
    if r.returncode != 0:
        said = (r.stderr or r.stdout or '').strip()
        for line in said.splitlines()[-15:]:
            print(f'    {line}', file=sys.stderr)
        hint = ''
        if "invalid choice: 'export'" in said or 'docoes_html' in said:
            hint = ' (this checkout has no DocOES export yet: it comes with enough 0.5.0)'
        elif 'unrecognized arguments: --no-marks' in said or 'unrecognized arguments: --reference' in said \
                or 'is a registered document: export it by name' in said:
            hint = ' (this checkout\'s export is older than enough 0.5.1\'s: no --no-marks, --reference or explicit slug)'
        raise SystemExit(f'{entry["slug"]}: the export failed (exit {r.returncode}){hint}; nothing was changed')


def git(root: Path) -> dict:
    """`{commit, dirty}` of this repository, best effort; nulls when it is not a checkout."""
    try:
        head = subprocess.run(['git', '--no-optional-locks', '-C', str(root), 'rev-parse', '--short', 'HEAD'],
                              capture_output=True, text=True, timeout=10)
        if head.returncode != 0:
            return {'commit': None, 'dirty': None}
        st = subprocess.run(['git', '--no-optional-locks', '-C', str(root), 'status', '--porcelain'],
                            capture_output=True, text=True, timeout=30)
        return {'commit': head.stdout.strip() or None,
                'dirty': bool(st.stdout.strip()) if st.returncode == 0 else None}
    except (OSError, subprocess.SubprocessError):
        return {'commit': None, 'dirty': None}


def finish(out: Path, entries: list[dict], specs_dir: Path = SPECS, repo: Path = ROOT) -> dict:
    """The registry's fields and the source copies into the export's manifest; this repository's commit at the top.
    SystemExit when the export is not of these texts (the slug, name, version or source sha256 differ)."""
    path = out / 'manifest.json'
    try:
        m = json.loads(path.read_text(encoding='utf-8'))
    except (OSError, ValueError) as e:
        raise SystemExit(f'the export left no readable manifest.json ({e}); nothing was changed')
    docs = {d.get('slug'): d for d in m.get('documents') or [] if isinstance(d, dict)}
    for e in entries:
        d = docs.get(e['slug'])
        if d is None:
            raise SystemExit(f'{e["slug"]}: the export wrote no entry for it; nothing was changed')
        data = (specs_dir / e['file']).read_bytes()
        sha = hashlib.sha256(data).hexdigest()
        if (d.get('source') or {}).get('sha256') != sha:
            raise SystemExit(f'{e["slug"]}: the export was not built from specs/{e["file"]} (sha256 differs); nothing was changed')
        if d.get('name') != e['name'] or d.get('version') != e['edition']:
            raise SystemExit(f'{e["slug"]}: the export says {d.get("name")!r} v{d.get("version")}, the registry '
                             f'{e["name"]!r} edition {e["edition"]}; nothing was changed')
        rel = f'{e["slug"]}/source.md'
        (out / rel).write_bytes(data)
        d['edition'] = e['edition']
        d['describes'] = dict(e['describes'])
        d['host'] = e['host']
        d['revised'] = e['revised']
        d['raw'] = dict(RAW)
        d.setdefault('files', {})[specs.SOURCE] = {'path': rel, 'sha256': sha, 'bytes': len(data)}
    m['documents'] = [docs[e['slug']] for e in entries]
    m['source'] = git(repo)
    path.write_text(json.dumps(m, ensure_ascii=False, indent=2) + '\n', encoding='utf-8')
    return m


def check(out: Path, entries: list[dict]) -> dict:
    """The export in `out`, checked as the site will read it: its manifest, or SystemExit saying what is wrong."""
    slugs = [e['slug'] for e in entries]
    try:
        m = json.loads((out / 'manifest.json').read_text(encoding='utf-8'))
    except (OSError, ValueError) as e:
        raise SystemExit(f'the export left no readable manifest.json ({e}); nothing was changed')
    if not isinstance(m, dict) or m.get('format') != specs.FORMAT:
        raise SystemExit(f'the export is not {specs.FORMAT} (format {m.get("format") if isinstance(m, dict) else None!r}); '
                         'nothing was changed')
    if m.get('standalone'):
        raise SystemExit('the export is standalone (full pages), which the site refuses; nothing was changed')
    if m.get('pages') != PAGES:
        raise SystemExit(f'the fragments link across densities as {m.get("pages")}, not as the hosts\' addresses {PAGES}; '
                         'nothing was changed')
    docs = m.get('documents') if isinstance(m.get('documents'), list) else []
    got = [d.get('slug') if isinstance(d, dict) else None for d in docs]
    if got != slugs:
        raise SystemExit(f'the export holds {got}, not {slugs}; nothing was changed')
    for d, e in zip(docs, entries):
        for k in ('edition', 'describes', 'host', 'revised'):
            if d.get(k) != e[k]:
                raise SystemExit(f'{d["slug"]}: {k} is {d.get(k)!r} in the export, {e[k]!r} in the registry; nothing was changed')
        if d.get('raw') != RAW:
            raise SystemExit(f'{d["slug"]}: the raw endpoints are not declared as {RAW}; nothing was changed')
        for which in (*PAGES, specs.SOURCE):
            f = (d.get('files') or {}).get(which) or {}
            p = out / str(f.get('path') or f'{d["slug"]}/{which}')
            try:
                raw = p.read_bytes()
            except OSError:
                raise SystemExit(f'{d["slug"]}: {which} is missing ({p}); nothing was changed')
            if hashlib.sha256(raw).hexdigest() != str(f.get('sha256') or '').lower() or f.get('bytes') != len(raw):
                raise SystemExit(f'{d["slug"]}: {which} differs from the manifest; nothing was changed')
        if (d.get('source') or {}).get('sha256') != d['files'][specs.SOURCE]['sha256']:
            raise SystemExit(f'{d["slug"]}: the source copy is not the text the export was built from; nothing was changed')
    served = [d['slug'] for d in specs.Specs(out).documents]          # the site's own checks; their warnings print above
    if served != slugs:
        left = [s for s in slugs if s not in served]
        raise SystemExit(f'the site would leave out {", ".join(left)} (the warning above says why); nothing was changed')
    if not (out / str(m.get('css') or 'docs.css')).is_file():
        raise SystemExit(f'the export wrote no {m.get("css") or "docs.css"}; nothing was changed')
    return m


def install(out: Path, m: dict, dest: Path) -> None:
    """Replace `dest` with the manifest, exactly the files it lists and the stylesheet. The new folder is made
    beside the old one and swapped in, so a failure part way leaves the old one serving."""
    new, old = dest.with_name(f'.{dest.name}.new'), dest.with_name(f'.{dest.name}.old')
    for p in (new, old):
        shutil.rmtree(p, ignore_errors=True)
    new.mkdir(parents=True)
    shutil.copyfile(out / 'manifest.json', new / 'manifest.json')
    css = str(m.get('css') or 'docs.css')
    shutil.copyfile(out / css, new / css)
    for d in m['documents']:
        for which in (*PAGES, specs.SOURCE):
            rel = d['files'][which]['path']
            (new / rel).parent.mkdir(parents=True, exist_ok=True)
            shutil.copyfile(out / rel, new / rel)
    if dest.exists():
        dest.rename(old)
    new.rename(dest)
    shutil.rmtree(old, ignore_errors=True)


def shown(path: Path) -> str:
    """A path as the messages print it: relative to this repository when it is inside it."""
    return str(path.relative_to(ROOT)) if path.is_relative_to(ROOT) else str(path)


def differences(out: Path, dest: Path) -> list[str]:
    """How the committed export in `dest` differs from a fresh build in `out`: files only one has, files whose bytes
    differ, and a manifest that differs once `exported` and `source` are set aside. Empty when they are in step."""
    files = lambda folder: {p.relative_to(folder).as_posix() for p in folder.rglob('*') if p.is_file()}
    fresh, kept = files(out), files(dest) if dest.is_dir() else set()
    diff = [f'only in the fresh build: {f}' for f in sorted(fresh - kept)]
    diff += [f'only in {shown(dest)}/: {f}' for f in sorted(kept - fresh)]
    for f in sorted(fresh & kept):
        a, b = (out / f).read_bytes(), (dest / f).read_bytes()
        if f == 'manifest.json':
            try:
                ma, mb = json.loads(a), json.loads(b)
            except ValueError:
                diff.append('manifest.json: not JSON on one side')
                continue
            for m_ in (ma, mb):
                if isinstance(m_, dict):
                    m_.pop('exported', None)
                    m_.pop('source', None)
            if ma != mb:
                diff.append('manifest.json differs (beyond its exported time and source commit)')
        elif a != b:
            diff.append(f'{f} differs')
    return diff


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(description='Build site/specs/ from specs/ with an enough checkout\'s DocOES export, '
                                             'or check that the committed site/specs/ is in step with specs/.')
    ap.add_argument('--enough', required=True, help='the enough checkout to export with')
    ap.add_argument('--python', default=None, help='the interpreter that runs the export (default: <enough>/.venv/bin/python)')
    ap.add_argument('--check', action='store_true', help='build into a temporary folder and compare with site/specs/')
    args = ap.parse_args(argv)
    logging.basicConfig(level=logging.WARNING, format='    %(message)s')

    enough = Path(args.enough).expanduser().resolve()
    if not (enough / 'enough' / 'docoes.py').is_file():
        raise SystemExit(f'{enough} is not an enough checkout (it has no enough/docoes.py)')
    python = Path(args.python).expanduser() if args.python else enough / '.venv' / 'bin' / 'python'
    if not python.exists():
        raise SystemExit(f'{python} does not exist: make the checkout\'s venv (uv sync --frozen), or give --python')
    entries = registry(REGISTRY, SPECS)

    with tempfile.TemporaryDirectory(prefix='cosmoes-specs-') as tmp:
        root = sources_root(Path(tmp), enough, entries, SPECS)
        out = Path(tmp) / 'export'
        out.mkdir()
        for e in entries:
            export(python, enough, root, e, out)
        finish(out, entries, SPECS, ROOT)
        m = check(out, entries)
        if args.check:
            diff = differences(out, DEST)
            if diff:
                print(f'{shown(DEST)}/ is not in step with specs/:', file=sys.stderr)
                for line in diff:
                    print(f'    {line}', file=sys.stderr)
                print('run scripts/build_specs.py --enough … and commit what it writes', file=sys.stderr)
                return 1
            print(f'{shown(DEST)}/ is in step with specs/ ({len(entries)} documents)')
            return 0
        install(out, m, DEST)

    for d in m['documents']:
        size = sum(d['files'][density]['bytes'] for density in PAGES)
        print(f'{d["slug"]:<14}  {d["name"]:<14}  edition {d["edition"]:<6}  {d["host"]:<22}  {size:,} bytes')
    src = m.get('source') or {}
    print(f'built at {src.get("commit") or "?"}{" with uncommitted changes" if src.get("dirty") else ""} by {m.get("by") or "enough"}; '
          f'wrote {shown(DEST)}/: look at it (README.md), then commit')
    return 0


if __name__ == '__main__':
    sys.exit(main())

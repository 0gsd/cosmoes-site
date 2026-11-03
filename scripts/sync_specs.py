#!/usr/bin/env python3
"""Sync site/specs/ (cosmoes/specs.py) from an enough checkout: MacroCOSM OES with its chapters, Thym, Ascribe and
Comprise OES 1, as enough's DocOES exports them, each at three densities.

    .venv/bin/python scripts/sync_specs.py --enough ~/METMcloud/METMroot/enough-dev

It runs `python -m enough.docoes export` in the checkout (the working folder is the checkout; the interpreter is the
checkout's own `.venv/bin/python` unless --python names another) four times into one temporary folder: `macrocosm-oes`,
`thym`, `ascribe` (registered documents) and `defaults/cosm/chapters/comprise-oes.md` as `comprise-oes` v1 (Comprise's
own text, ad hoc), each with `--page short=/ --page atem=/atem --page fabula=/fabula`: the fragments' links across
densities are root-absolute, so they resolve on whichever host serves the document. Then it checks the result as the
site will read it (`docoes-export/1`, not standalone, those four documents in that order, every fragment's sha256 and
size, nothing the site refuses to include, a stylesheet) and only then replaces site/specs/ (the manifest, the
fragments and docs.css). When any step fails, nothing here is changed.

Run it again on every new version of a specification, look at the pages locally (README.md), commit what it wrote,
and deploy (DEPLOY.md, "Updating"). It needs no credentials and nothing from the network; the export builds its
volumes in a temporary folder of its own and leaves ~/enough alone.

    --enough PATH    the enough checkout (required)
    --python PATH    the interpreter that runs the export (default: PATH/.venv/bin/python)
"""
from __future__ import annotations

import argparse
import hashlib
import json
import logging
import shutil
import subprocess
import sys
import tempfile
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from cosmoes import specs  # noqa: E402

DEST = specs.FOLDER                                               # site/specs/
# (what to export, its slug, extra arguments). The three registered documents carry their versions; Comprise OES 1 is
# exported ad hoc from the chapter enough syncs from comprise-dev (defaults/cosm/chapters/NOTICE.md: © Graham Smith).
SOURCES = (('macrocosm-oes', 'macrocosm-oes', ()),
           ('thym', 'thym', ()),
           ('ascribe', 'ascribe', ()),
           ('defaults/cosm/chapters/comprise-oes.md', 'comprise-oes', ('--slug', 'comprise-oes', '--name', 'Comprise OES 1', '--version', '1')))
PAGES = specs.PAGES                                               # --page density=href: each host's addresses
TIMEOUT = 600


def export(python: Path, enough: Path, doc: str, out: Path, extra=()) -> None:
    """One run of the export into `out`, which merges into the manifest there. SystemExit, saying why, if it fails."""
    cmd = [str(python), '-m', 'enough.docoes', 'export', doc, str(out), *extra]
    for density, href in PAGES.items():
        cmd += ['--page', f'{density}={href}']
    try:
        r = subprocess.run(cmd, cwd=enough, capture_output=True, text=True, timeout=TIMEOUT)
    except OSError as e:
        raise SystemExit(f'{doc}: could not run {python}: {e}; nothing was changed')
    except subprocess.TimeoutExpired:
        raise SystemExit(f'{doc}: the export ran for more than {TIMEOUT // 60} minutes; nothing was changed')
    if r.returncode != 0:
        said = (r.stderr or r.stdout or '').strip()
        for line in said.splitlines()[-15:]:
            print(f'    {line}', file=sys.stderr)
        hint = ''
        if "invalid choice: 'export'" in said or 'docoes_html' in said:
            hint = ' (this checkout has no DocOES export yet: it comes with enough 0.5.0)'
        raise SystemExit(f'{doc}: the export failed (exit {r.returncode}){hint}; nothing was changed')


def check(out: Path, slugs) -> dict:
    """The export in `out`, checked as the site will read it: its manifest, or SystemExit saying what is wrong."""
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
    if got != list(slugs):
        raise SystemExit(f'the export holds {got}, not {list(slugs)}; nothing was changed')
    for d in docs:
        for density in PAGES:
            f = (d.get('files') or {}).get(density) or {}
            p = out / str(f.get('path') or f'{d["slug"]}/{density}.html')
            try:
                raw = p.read_bytes()
            except OSError:
                raise SystemExit(f'{d["slug"]}: {density} is missing ({p}); nothing was changed')
            if hashlib.sha256(raw).hexdigest() != str(f.get('sha256') or '').lower() or f.get('bytes') != len(raw):
                raise SystemExit(f'{d["slug"]}: {density} differs from the manifest; nothing was changed')
    served = [d['slug'] for d in specs.Specs(out).documents]          # the site's own checks; their warnings print above
    if served != list(slugs):
        left = [s for s in slugs if s not in served]
        raise SystemExit(f'the site would leave out {", ".join(left)} (the warning above says why); nothing was changed')
    if not (out / str(m.get('css') or 'docs.css')).is_file():
        raise SystemExit(f'the export wrote no {m.get("css") or "docs.css"}; nothing was changed')
    return m


def install(out: Path, m: dict, dest: Path) -> None:
    """Replace `dest` with the manifest, exactly the fragments it lists and the stylesheet. The new folder is made
    beside the old one and swapped in, so a failure part way leaves the old one serving."""
    new, old = dest.with_name(f'.{dest.name}.new'), dest.with_name(f'.{dest.name}.old')
    for p in (new, old):
        shutil.rmtree(p, ignore_errors=True)
    new.mkdir(parents=True)
    shutil.copyfile(out / 'manifest.json', new / 'manifest.json')
    css = str(m.get('css') or 'docs.css')
    shutil.copyfile(out / css, new / css)
    for d in m['documents']:
        for density in PAGES:
            rel = d['files'][density]['path']
            (new / rel).parent.mkdir(parents=True, exist_ok=True)
            shutil.copyfile(out / rel, new / rel)
    if dest.exists():
        dest.rename(old)
    new.rename(dest)
    shutil.rmtree(old, ignore_errors=True)


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(description='Export MacroCOSM OES, Thym, Ascribe and Comprise OES 1 from an enough '
                                             'checkout and replace site/specs/.')
    ap.add_argument('--enough', required=True, help='the enough checkout to export from')
    ap.add_argument('--python', default=None, help='the interpreter that runs the export (default: <enough>/.venv/bin/python)')
    args = ap.parse_args(argv)
    logging.basicConfig(level=logging.WARNING, format='    %(message)s')

    enough = Path(args.enough).expanduser().resolve()
    if not (enough / 'enough' / 'docoes.py').is_file():
        raise SystemExit(f'{enough} is not an enough checkout (it has no enough/docoes.py)')
    python = Path(args.python).expanduser() if args.python else enough / '.venv' / 'bin' / 'python'
    if not python.exists():
        raise SystemExit(f'{python} does not exist: make the checkout\'s venv (uv sync --frozen), or give --python')

    with tempfile.TemporaryDirectory(prefix='cosmoes-specs-') as tmp:
        out = Path(tmp) / 'export'
        out.mkdir()
        for doc, _, extra in SOURCES:
            export(python, enough, doc, out, extra)
        m = check(out, [slug for _, slug, _ in SOURCES])
        install(out, m, DEST)

    for d in m['documents']:
        size = sum(d['files'][density]['bytes'] for density in PAGES)
        print(f'{d["slug"]:<14}  {d.get("name") or d["slug"]}  {("v" + d["version"]) if d.get("version") else "(no version)"}  '
              f'{size:,} bytes')
    src = m.get('source') or {}
    print(f'from {m.get("by") or "enough"}'
          + (f' at {src["commit"]}{" with uncommitted changes" if src.get("dirty") else ""}' if src.get('commit') else '')
          + f'; wrote {DEST.relative_to(ROOT) if DEST.is_relative_to(ROOT) else DEST}/: look at it (README.md), then commit')
    return 0


if __name__ == '__main__':
    sys.exit(main())

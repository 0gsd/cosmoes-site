# Contributing

The texts in `specs/` are the canonical editions of the OES specifications: MacroCOSM OES, Thym, Ascribe, Comprise
OES, and *The OES specifications*, the apex text. cosmoes.org serves nothing else, and the applications that carry a copy (enough,
Comprise, comprise-connect) sync it from here. A change to a text is a change to this folder, nowhere else.

## Proposing a change to a text

1. **A pull request against `specs/`.** One text, or several when a change spans them. Say in the description what
   changes and why; a wording change and a change of meaning are different things, and the second is the owner's to
   rule on.
2. **The registry, `specs/specs.json`.** It is the one place names, editions and hosts are declared. `revised` moves to
   the day of the edit for every text touched. An edition bump (`edition`, and `describes` when the format version a
   text describes changes) is the owner's call: propose it in the description, do not set it. A name never carries a
   number; the edition is a field.
3. **Build, and commit the export.** `site/specs/` is what the site serves and must be what the texts build to:

       .venv/bin/python scripts/build_specs.py --enough <an enough checkout>
       .venv/bin/python scripts/build_specs.py --enough <an enough checkout> --check

   The first writes `site/specs/`; commit it with the text. The second rebuilds into a temporary folder and compares,
   byte for byte, and exits 1 on a difference: it guards the commit. It needs an enough checkout whose DocOES export
   is 0.5.1's or later (`--no-marks`, `--reference`, an explicit slug) with its `.venv` made (`uv sync --frozen`
   there); CI runs `pytest -q` and not this check until that export is on enough's public main, so run it before
   you push.
4. **The owner merges and deploys** (DEPLOY.md, "Updating"). Nothing is live until then.

## Licence

The texts are © 2026 Graham Smith, all rights reserved (`specs/NOTICE.md`). Until terms for the texts are published,
contributions to them are by the owner's invitation; a pull request from anyone else is read as a report, with thanks,
and is not merged as written. The site's code is Apache-2.0 (`LICENSE`): a change to it is welcome by pull request,
with `pytest -q` green.

## Adding a text

An entry in `specs/specs.json` (`slug`, `file` under `specs/`, `name` without a number, `edition`, `describes`,
`host` one label under cosmoes.org, `revised`; `reference: true` only for the text that carries the manifests'
reference), the DNS record and the Cloud Run mapping for its host (DEPLOY.md, section 4), the build, and the owner's
go. Every name and edition the site shows comes from the registry through the manifest; the text's own heading is
the page's heading.

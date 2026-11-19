"""client/library_index.py: the registry's rules, the splitters (Python's plain-text build in full, Markdown, HTML,
the rest whole), the sections' anchors and digests, and the index built from the files alone. Everything reads the
made-up shelf in tests/fixtures/library/ (no third party's text) or strings written here."""
from __future__ import annotations

import json
import shutil
import sqlite3
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / 'client'))
import library_index as L  # noqa: E402

FIXTURE = Path(__file__).resolve().parent / 'fixtures' / 'library'
STRINGS = FIXTURE / 'example' / 'manual' / '1.0' / 'files' / 'library' / 'strings.txt'


@pytest.fixture
def shelf(tmp_path) -> Path:
    return Path(shutil.copytree(FIXTURE, tmp_path / 'library'))


# ----------------------------------------------------------------------------- the registry and the folders

def test_the_fixture_and_the_real_registry_validate():
    assert L.validate_registry(L.load_registry(FIXTURE)) == []
    real = L.load_registry(ROOT / 'library')
    assert L.validate_registry(real) == []
    assert real['format'] == L.FORMAT
    # every text aboard is the owner's fetch (scripts/fetch_library.py) and its folder verifies: the files against
    # SHA256SUMS, FETCHED and NOTICE present (Python 3.13 since 2026-11-19)
    for t in (t for t in real['texts'] if t['aboard']):
        folder = ROOT / 'library' / t['shelf'] / t['text'] / t['version']
        assert L.verify(folder, t) == [], (t['shelf'], t['text'], t['version'])
    assert {(t['shelf'], t['what']) for t in real['texts']} >= {('ieee-754', 'standard'), ('unicode', 'standard'),
                                                               ('ecmascript', 'tests'), ('python', 'implementation')}
    titles = {s['slug']: s['title'] for s in real['shelves']}
    assert titles['ecmascript'] == 'ECMAScript' and 'javascript' not in titles


def test_every_kept_fixture_text_verifies():
    reg = L.load_registry(FIXTURE)
    kept = [e for e in reg['texts'] if e['aboard']]
    assert len(kept) == 3
    for e in kept:
        assert L.verify(L.text_dir(FIXTURE, e), e) == [], e['text']


@pytest.mark.parametrize('spoil, says', [
    (lambda d: (d / 'files' / 'index.txt').write_text('changed\n'), 'does not match its sha256'),
    (lambda d: (d / 'files' / 'extra.txt').write_text('new\n'), 'is not in SHA256SUMS'),
    (lambda d: (d / 'files' / 'license.txt').unlink(), 'is in SHA256SUMS but not on disk'),
    (lambda d: (d / 'NOTICE').unlink(), 'NOTICE is missing'),
    (lambda d: (d / 'NOTICE').write_text('[OWNER: the notice]\n'), 'marked gap'),
    (lambda d: (d / 'files' / 'link.txt').symlink_to(d / 'files' / 'index.txt'), 'is a link'),
])
def test_a_spoiled_folder_does_not_verify(shelf, spoil, says):
    e = next(t for t in L.load_registry(shelf)['texts'] if t['text'] == 'manual')
    d = L.text_dir(shelf, e)
    spoil(d)
    assert any(says in p for p in L.verify(d, e)), L.verify(d, e)


def test_the_registry_refuses_what_a_page_could_not_show():
    reg = L.load_registry(FIXTURE)
    e = next(t for t in reg['texts'] if t['text'] == 'manual')
    for key, value, says in (('copyright', '', 'no copyright notice'), ('licence', {'name': 'x'}, 'licence'),
                             ('form', 'pdf', 'form'), ('aboard', 'no', 'aboard'), ('lane', 'free', 'lane'),
                             ('shelf', 'nowhere', 'no such shelf'), ('from', 'http://x', 'from')):
        bad = dict(reg, texts=[dict(e, **{key: value})])
        assert any(says in p for p in L.validate_registry(bad)), key
    twice = dict(reg, texts=[e, e])
    assert any('twice' in p for p in L.validate_registry(twice))


# ----------------------------------------------------------------------------- the plain-text rule

def test_titles_definitions_and_their_ids():
    data = STRINGS.read_bytes()
    secs = L.sections('text', data, 'library/strings')
    by = {s.anchor: s for s in secs if s.anchor}
    assert secs[0].kind == 'file' and secs[0].line_from == 1
    assert by['strings'].level == 1 and by['making-strings'].level == 2
    assert by['making-strings'].path == ['Strings', 'Making strings']
    # a definition inside a class's body is named within it; a group of lines gives one section with each id
    assert by['text'].kind == 'sig' and by['text.upper'].path[-2:] == ['text', 'text.upper']
    assert by['text.upper'].parent == secs.index(by['text'])
    assert by['text.count'].ids == ['text.count', 'text.tally']
    assert by['text.join'].parent == secs.index(by['making-strings'])
    # the same title twice: the second takes its path, never the first's anchor
    assert by['lines'].heading == by['strings--lines'].heading == 'Lines'
    # spans: a title to the next title at its level, a definition to the end of its body
    lines = data.decode().split('\n')
    assert lines[by['text'].line_from - 1] == "class text(value='')"
    assert lines[by['text'].line_to - 1].strip() == 'Count how often *sub* occurs.'
    assert lines[by['making-strings'].line_to - 1].strip() == 'Join *parts* with the text between them.'


def test_blocks_keep_tables_and_indented_text_preformatted():
    blks = L.blocks('text', STRINGS.read_bytes())
    pres = [b.text for b in blks if b.kind == 'pre']
    assert any(p.startswith('+--------+') and '| Break  |' in p for p in pres)
    assert 'An indented example.' in pres
    upper = next(c for b in blks if b.kind == 'sig' and b.anchor == 'text' for c in b.children if c.kind == 'sig')
    assert upper.anchor == 'text.upper' and any(c.kind == 'pre' and '>>> text' in c.text for c in upper.children)


def test_a_section_digest_is_over_its_bytes_and_survives_a_move():
    data = STRINGS.read_bytes()
    here = {s.anchor: s for s in L.sections('text', data, 'library/strings') if s.anchor}
    moved = {s.anchor: s for s in L.sections('text', b'\n\n' + data, 'builtins/strings') if s.anchor}
    for a in ('text.upper', 'making-strings', 'lines'):
        s, m = here[a], moved[a]
        assert m.line_from == s.line_from + 2
        assert L.sha256(L.section_bytes(data, s.line_from, s.line_to)) == \
            L.sha256(L.section_bytes(b'\n\n' + data, m.line_from, m.line_to))


def test_a_one_word_paragraph_is_not_a_definition():
    data = b'Title\n=====\n\nNotes\n\n   Indented, but Notes names no object.\n\nlen(s)\n\n   Return the length.\n'
    blks = L.blocks('text', data)
    assert [b.kind for b in blks] == ['heading', 'para', 'pre', 'sig'] and blks[3].anchor == 'len'


def test_list_items_and_footnotes_keep_their_hanging_lines():
    data = (b'Title\n=====\n\n* one item that runs\n  onto a second line\n* two\n\n[1] A footnote that runs\n'
            b'    on.\n\nAfter.\n')
    blks = L.blocks('text', data)
    assert [(b.kind, b.text) for b in blks[1:]] == [('para', '* one item that runs\nonto a second line'),
                                                    ('para', '* two'), ('para', '[1] A footnote that runs\non.'),
                                                    ('para', 'After.')]


def test_reserved_ids_are_never_anchors():
    blks = L.blocks('text', b'Main\n****\n\nmain()\n\n   The entry.\n')
    assert blks[0].anchor != 'main' and blks[1].anchor == ''          # the page's own <main id="main">


def test_rst_labels_and_paragraph_ids():
    data = (b'.. _fls_intro:\n\nIntro\n=====\n\n:dp:`fls_abc123`\nA rule of the language.\n\n'
            b':dp:`fls_def456`\nAnother.\n')
    secs = L.sections('rst', data, 'intro')
    assert [(s.kind, s.anchor) for s in secs] == [('file', ''), ('heading', 'fls_intro'), ('para', 'fls_abc123'),
                                                  ('para', 'fls_def456')]
    assert secs[2].line_to == 7


# ----------------------------------------------------------------------------- the other forms

def test_markdown_headings_fences_and_rule_markers():
    data = (b'# Calls\n\nr[expr.call.intro]\nA call expression calls a function.\n\n```rust\nlet x = f();\n```\n\n'
            b'## Argument order\n\nr[expr.call.order]\nLeft to right.\n')
    blks = L.blocks('markdown', data)
    assert [b.kind for b in blks] == ['heading', 'rule', 'para', 'pre', 'heading', 'rule', 'para']
    assert blks[1].anchor == 'r-expr.call.intro' and blks[3].text == 'let x = f();'
    secs = L.sections('markdown', data, 'expressions/call-expr')
    rule = next(s for s in secs if s.anchor == 'r-expr.call.intro')
    assert rule.kind == 'rule' and rule.path == ['Calls', 'r-expr.call.intro'] and rule.line_to == 8


def test_html_is_taken_apart_without_its_scripts():
    data = (FIXTURE / 'example' / 'sheet' / '2' / 'files' / 'sheet.html').read_bytes()
    blks = L.blocks('html', data)
    texts = [b.text for b in blks]
    assert not any('alert' in t or 'bad()' in t or 'color' in t or 'home' in t for t in texts)
    assert texts[:5] == ['The Example Sheet', 'One short page of made-up text.', 'first', 'second', '  code  stays']
    assert blks[0].anchor == 'sec-intro' and blks[0].level == 1
    assert next(b for b in blks if b.text == 'Copyright').anchor == 'sec-copyright'


def test_data_is_one_block_and_one_section():
    data = b'0041;LATIN CAPITAL LETTER A;Lu\n0042;LATIN CAPITAL LETTER B;Lu\n'
    assert [b.kind for b in L.blocks('data', data)] == ['pre']
    assert [(s.kind, s.line_from, s.line_to) for s in L.sections('data', data, 'x')] == [('file', 1, 2)]


# ----------------------------------------------------------------------------- the index

def test_the_index_is_built_from_the_files_alone(shelf, tmp_path):
    out = tmp_path / 'library.sqlite'
    counts = L.build(shelf, out)
    assert counts['texts'] == 4 and counts['kept'] == 3 and counts['files'] == 6
    con = sqlite3.connect(out)
    assert dict(con.execute('SELECT key, value FROM meta')) == {'format': L.INDEX_FORMAT, 'library': L.FORMAT,
                                                                'source': L.source_digest(shelf)}
    rows = con.execute('SELECT shelf, text, version, aboard, address FROM texts ORDER BY shelf, text').fetchall()
    assert ('example', 'runner', '1', 0, None) in rows
    assert ('example', 'manual', '1.0', 1, 'https://cosmoes.org/library/example/manual/1.0/') in rows
    # an anchor resolves to its section, an alias too, and the digest is the section's bytes
    sid, file, lf, lt, sha, path = con.execute(
        "SELECT s.id, s.file, s.line_from, s.line_to, s.sha256, s.path FROM anchors a JOIN sections s ON s.id = a.section_id "
        "WHERE a.anchor = 'text.tally'").fetchone()
    assert json.loads(path)[-1] == 'text.count' and file == 'files/library/strings.txt'
    data = (L.text_dir(shelf, {'shelf': 'example', 'text': 'manual', 'version': '1.0'}) / file).read_bytes()
    assert sha == L.sha256(L.section_bytes(data, lf, lt))
    # full-text search
    hits = con.execute("SELECT heading FROM sections_fts WHERE sections_fts MATCH 'capitals'").fetchall()
    assert hits == [('text.upper',)]
    # the RFC-like text has its file as one section and no page
    assert con.execute("SELECT kind, page FROM sections WHERE file = 'files/memo7.txt'").fetchall() == [('file', None)]
    con.close()


def test_the_index_is_the_same_when_built_again_and_stale_when_a_file_moves(shelf, tmp_path):
    a, b = tmp_path / 'a.sqlite', tmp_path / 'b.sqlite'
    L.build(shelf, a)
    L.build(shelf, b)

    def dump(p):
        con = sqlite3.connect(p)
        try:
            return [list(con.execute(f'SELECT * FROM {t} ORDER BY 1, 2')) for t in ('meta', 'texts', 'files', 'sections', 'anchors')]
        finally:
            con.close()
    assert dump(a) == dump(b)
    assert L.is_current(shelf, a)
    assert L.main(['build', '--library', str(shelf), '--out', str(a), '--check']) == 0
    reg = json.loads((shelf / 'library.json').read_text())
    reg['about'] = 'changed'
    (shelf / 'library.json').write_text(json.dumps(reg))
    assert not L.is_current(shelf, a)
    assert L.main(['build', '--library', str(shelf), '--out', str(a), '--check']) == 1


def test_the_build_refuses_a_shelf_that_does_not_verify(shelf, tmp_path):
    (shelf / 'example' / 'manual' / '1.0' / 'files' / 'index.txt').write_text('changed\n')
    out = tmp_path / 'x.sqlite'
    with pytest.raises(ValueError, match='does not match its sha256'):
        L.build(shelf, out)
    assert not out.exists() and not list(tmp_path.glob('.library-index-*'))
    assert L.main(['verify', '--library', str(shelf)]) == 1
    assert L.main(['verify', '--library', str(FIXTURE)]) == 0

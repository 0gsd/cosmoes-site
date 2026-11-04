# The OES specifications

*Edition 0.5.4 · revised 2026-11-03 · cosmoes.org home: https://cosmoes.org/*

An OES, an organizational enumeration system, describes a domain by enumerating everything in it. It is written as
plain-text files that are at once a file system and a relational database, made to be rendered. This page says what
that is and how the specifications published at cosmoes.org fit together; each has a home of its own, listed after
this text.

## The short version

<!-- atem: one grammar, a dialect per domain, an organization's additions -->

An OES describes its subject as a file system that is also a relational database: every volume (a company's Holotype, a
person's holograph, a text's twin, a library's catalog) is a folder of plain-text files or one such file, every module a
set of tables, every item a row with a path. Written down once, as a shared grammar, the shape describes a company, a
person, a text or a document the same way. The shared grammar is **MacroCOSM**. A grammar specialized for one domain is
a **MiniCOSM**: Comprise OES, for companies, is the first; Ascribe, for a person, has a specification of its own.
**Thym** is the language of the programs that move meaning between volumes. One organization's additions on top of a
MiniCOSM are a **MicroCOSM**, reserved for a later edition.

## 1. What an OES is

<!-- atem: a domain enumerated as files, a database and a source to render -->

An **OES**, an *organizational enumeration system*, is a system that organizes a domain by enumerating everything in it,
as a file system that is also a relational database, made to be rendered.

- **Enumerating.** It lists what there is, item by item, each with its sources. What is unknown is an open question with
  the name of the role that can answer it, never a guess.
- **A file system.** Plain text files in folders, on the subject's own machine. Anyone can read them without any
  application, move them, keep them in version control, and leave with everything.
- **A relational database.** Every item has a primary key (its id), its fields are columns, its references are foreign
  keys, and checks are constraints. The same files can be indexed and queried.
- **Made to be rendered.** The description exists to be turned into other forms for other readers: a 3D scene, a
  summary, an export for an agent, a public projection. A renderer can only show what the description holds, so the
  description is held to account.

## 2. Three scales

<!-- atem: the grammar, a domain's dialect, an organization's additions -->

**COSM** is the family's name. It is not an acronym: it was *Context Ontology Schema and Markup*, and before that
*OPI*; both are history. It comes from *kosmos*, order and world. `.cosm` is the family's file extension.

| Scale | What it is | Specified by |
|---|---|---|
| **MacroCOSM** | the whole language: the shared grammar every MiniCOSM is written in | MacroCOSM OES |
| **MiniCOSM** | an OES for one domain, declared by a manifest: its volume layout, modules, kinds, fields, references, checks and renderers | Comprise OES, Ascribe, Thym's `thym/1`; the rest in MacroCOSM OES, its section 18 |
| **MicroCOSM** | one organization's extension on top of a MiniCOSM: the extra kinds, fields, checks or renderers it needs | reserved for a later edition (section 5) |

The names borrow an old idea, from Greek philosophy to the Renaissance: that a small world mirrors the order of the
great one. Here each smaller scale keeps the order of the larger and adds to it.

## 3. What MacroCOSM gives every MiniCOSM

<!-- atem: the parts of the shared grammar every MiniCOSM inherits unchanged -->

Every MiniCOSM inherits all of it, unchanged. The right-hand column gives the section of MacroCOSM OES
(https://macro.cosmoes.org/) that defines each part; the examples are Comprise OES's.

| Part | What it is | Section of MacroCOSM OES |
|---|---|---|
| **Paths, and a URI form** | every part, module, kind, item and field has an address that respells its id as a location, `mozilla-foundation/P/offering/creative-futures`; qualified with the MiniCOSM and the volume's database name it is a URI, `oes:<minicosm>/<database>/<path>` | 11 |
| **Items, fields and references** | a row with a stable id and a kind (`P:offering/ledger`); its fields are columns; a reference is an id written in a field (`owner: O:role/Founder`), and every reference has two ends | 7 and 9 |
| **The envelope** | the columns every item has: id, kind, name, summary, status, visibility, provenance (how it is known, from what, how surely), open questions and typed links; a MiniCOSM adds its own | 8 |
| **Open questions** | a value nobody has given yet, `{pending: "…"}`, written where the value would go, with who can answer it; never a guess | 10 |
| **Checks** | constraints on the whole volume, run on every write; a write that breaks one is undone | 12 |
| **Saved and signed versions** | an immutable copy of the files at a moment, with a manifest of hashes; a copy the checks allowed, signed by the roles that govern it | 15 |
| **The private/public split** | two formats, not one with a setting: the complete private description (the **Holotype**), kept by its subject, and its small public projection (the **isotype**), default-deny, released and signed by the subject | 16 |
| **Renderers** | anything that turns a volume into another form; renderers only read, and show a reader only what that reader may see | 14 |
| **The manifest** | the machine-readable declaration of a MiniCOSM, one `.cosm` file: what a program needs to read, check and render its volumes | 13 |

*Holotype* and *isotype* are taxonomy's words, the one specimen that defines a species and a duplicate of it; they name
the two halves of the split in every MiniCOSM, not only Comprise's.

## 4. What a MiniCOSM declares

<!-- atem: the manifest: one file that declares a MiniCOSM to any reader -->

A MiniCOSM is declared by its **manifest**: one `.cosm` file, outside every volume, that says

1. its **name and version** (`comprise`, `1`), and the **declaration** a volume uses to name it (`oes: comprise/1`),
   with any legacy forms it accepts;
2. its **volume layout**: a folder or a single file, the catalog at its root, and the places of its parts and modules;
3. its **modules and kinds**, and for each kind its **fields**: at least the reference fields, which the checks follow;
4. its **reference forms**: the id forms, the relationship kinds, the closed lists;
5. its **checks**, by id, with their severities and what the verdict means;
6. its **renderers** and lenses;
7. its **public projection**, when it has one: the fixed fields of the isotype, and the rule that derives each one.

A volume names its MiniCOSM with one line in its catalog and never embeds the manifest. A reader that does not know
the MiniCOSM or the version a volume declares refuses it with a plain error.

## 5. What a MicroCOSM may change

<!-- atem: an organization's additions: what they may add and may never touch -->

A MicroCOSM is one organization's extension of a MiniCOSM. MacroCOSM OES, in its section 17, states these rules as the grammar's;
how a volume says that it uses a MicroCOSM, and how a reader loads one, are reserved for a later edition.

**It may add:** kinds, in any module; fields, on any kind; checks, including stricter versions of the MiniCOSM's own;
renderers.

**It may never:** remove anything; rename anything; loosen anything (a closed list, a required field, a check's
severity); change what a path or an id means; weaken the split, by adding to the public projection or opening anything
by default. Only the MiniCOSM, in a new version of its projection format, can add a public field, and only as one the
subject opts into.

What a MicroCOSM adds carries its name, `<microcosm>.<kind>` and `<microcosm>.<field>`, so a later version of the
MiniCOSM can never collide with it. A volume written with a MicroCOSM remains a valid volume of its MiniCOSM: a reader
that does not know the MicroCOSM keeps its fields and ignores its checks.

## 6. The specifications and how they relate

<!-- atem: four documents: the grammar, the language of programs, two MiniCOSMs -->

Four specifications are published at cosmoes.org, each at its own home.

- **MacroCOSM OES** (https://macro.cosmoes.org/) is the grammar every MiniCOSM is written in: the parts in section 3,
  the file format, and what a conforming reader and writer must do. It is the grammar Comprise OES worked out for
  companies, read out of it so that nothing in it says "company"; its section 18 registers the MiniCOSMs.
- **Thym** (https://thym.cosmoes.org/) is the language of programs over MacroCOSM volumes. Everything a reader does with
  a volume is generic; everything that *moves* meaning from one telling to another (a text to its twin, a document to
  its one-line atems, a Holotype to its public isotype) is a Thym move. A program says what it is for and what it must
  preserve, and its contracts are checked; programs, morphs, contexts, plans, traces and packages are themselves
  volumes of the `thym/1` MiniCOSM.
- **Ascribe** (https://ascribe.cosmoes.org/) is the MiniCOSM for a person: a **holograph**, the description of one self
  comprehensive enough that a name is unnecessary, kept private by its subject, with no kind and no field for a name, an
  address or a government id. What leaves a holograph leaves by a Thym program its holder runs.
- **Comprise OES** (https://comprise.cosmoes.org/) is the MiniCOSM for companies, and the first. A company is a set of
  **concerns** (a branded face, a subsidiary, a joint venture) joined by **relationships**, each concern with eight
  modules, C · O · M · P · R · I · S · E. Its volume is the **Holotype**, one folder describing one company at a moment;
  its public projection is the isotype. Its declaration is `oes: comprise/1`.

Four more MiniCOSMs are registered in MacroCOSM OES, its section 18, and defined there, with no home of their own: `cosm` (one
whole's product tree, outside any Holotype), `canon` (a library: its files, and what has been derived from them), `emf`
(one text, taken apart into its words, the things it names, its claims and its events) and `doc` (one document, taken
apart into items and compiled back byte for byte). `doc` is DocOES (MacroCOSM OES, its section 18.5), the form these pages are
built in at three densities (atem, short, fabula).

Comprise OES and Ascribe are written in MacroCOSM; Thym is written over it. A shared vocabulary of public forms
("chair", "M4 screw", "invoice": defined once, cited by every MiniCOSM that needs them) is reserved for a later edition.

## 7. The picture

<!-- atem: the grammar, its MiniCOSMs, the language over them, the split -->

```text
                 MacroCOSM OES: the shared grammar
                                 |
   +---------+---------+------+------+------+------+------+
 comprise  ascribe   cosm   canon   emf   doc   thym        MiniCOSMs
    |         |                                   Thym: programs that move meaning between volumes
 a MicroCOSM: one organization's additions        (reserved for a later edition)
    |
 Holotype, holograph: one private volume  --- projection --->  isotype: public, signed, default-deny
    |
 renderers and lenses: a text tree, a card, a drawing, an export

 every item is addressable:  oes:<minicosm>/<database>/<path>
```

## 8. Editions

<!-- atem: editions, revisions, format versions and the canonical pages -->

An **edition** is a published state of one of these texts. Every text here, this page included, is at edition 0.5.4; the
status line says so. An edition is the text's, not the format's: a format's version (`thym/1`, `ascribe/1`,
`comprise/1`, the grammar version MacroCOSM OES names) is a line in the files a program reads, and each text's status
line names the one it describes. A text may be revised at any time; the canonical edition of each is the page at its
home, a copy an application ships or syncs is a copy of an edition published here, and the source and history of every
page are at https://github.com/0gsd/cosmoes-site.

## 9. Implementations

<!-- atem: enough and Comprise, the reference implementations -->

Two products are the reference implementations. **enough** (https://github.com/0gsd/enough) implements MacroCOSM OES,
Thym and Ascribe and reads every registered MiniCOSM: it loads, checks and draws their volumes, compiles and runs Thym
programs, and builds documents with DocOES. **Comprise** implements Comprise OES: it writes and reads Holotypes, runs
their checks, saves and signs versions, and projects and releases isotypes. Where an implementation and a text disagree,
one of them is in error, and the text's Changes appendix records which was corrected.

## 10. Open formats

<!-- atem: open formats, the subject's files, the way out never sold -->

This site exists so that the formats are open. Every format these texts describe is documented here completely enough
that a second reader, a second writer, a second vault or a second index can be built from the text alone: the layer is
larger than any one product. The files a format describes belong to their subject: plain text, on the subject's own
machine, readable without any application, movable and complete, so that a subject who leaves takes everything. The
format itself is never sold, and neither is the way out of it: no product and no account stands between a subject and
their own files.

## Changes

<!-- atem: what each edition changed, newest first -->

1. **Edition 0.5.4 (2026-11-03): the canonical edition at cosmoes.org.** The paradigm map becomes the text of
   cosmoes.org itself, named *The OES specifications*; the edition is a field in the status line. Section 6 is rewritten
   for the four specifications and the registered MiniCOSMs; the first form's sections 7 (connections to a wider
   ecosystem), 9 (a status table) and 10 (a repository listing) are removed, what survives of 7 folded into section 6,
   and the picture (section 8 in the first form) becomes section 7 and is redrawn; sections 8, 9 and 10 (editions,
   implementations, open formats) are added; *volume* replaces *database* for one instance of a MiniCOSM, as MacroCOSM
   OES uses it; repository paths, plans and what was built at a date are removed.
2. **2026-10-20: the paradigm map.** First written beside Comprise OES as the map of the OES family, in ten sections:
   sections 1 to 6 and the picture in their first form, a section on connections to a wider ecosystem, a status table
   of what was built and a listing of the folder it was written in. Comprise OES was the only MiniCOSM specified and
   MacroCOSM was drawn from it in outline.

## Colophon

<!-- atem: copyright, the canonical edition and its source -->

The OES specifications — Copyright © 2026 Graham Smith. All rights reserved. The canonical edition is published at
https://cosmoes.org/; its source and history are at https://github.com/0gsd/cosmoes-site.

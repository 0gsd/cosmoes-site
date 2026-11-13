# The OES specifications

*Edition 0.6.0 · revised 2026-11-06 · cosmoes.org home: https://cosmoes.org/*

An OES, an organizational enumeration system, describes a domain by enumerating everything in it. It is written as
plain-text files that are at once a file system and a relational database, made to be rendered. This page says what
that is and how the specifications published at cosmoes.org fit together; each has a home of its own, listed after
this text.

## The short version

<!-- atem: one grammar with a core, two domains, a language between them -->

An OES describes its subject as a file system that is also a relational database: every volume (a company's Holotype, a
person's holograph, a text's fabula, a library's catalog) is a folder of plain-text files or one such file, every module a
set of tables, every item a row with a path. **MacroCOSM** is an OES: the shared grammar, with a **core** that holds what
every reader has built in: a home file system (Canon), the fabula with its short and atem, documents, the product tree,
Thym's volumes and the dialectic. A **MiniCOSM** is a domain's OES with a specification of its own, and there are two:
Comprise OES, for companies, and Ascribe, for a person. **Thym** is the transcognition language that connects OESes. One
organization's additions on top of a MiniCOSM are a **MicroCOSM**, reserved for a later edition.

## 1. What an OES is

<!-- atem: a domain enumerated as files, a database and a source to render -->

An **OES**, an *organizational enumeration system*, is a system that organizes a domain by enumerating everything in it,
as a file system that is also a relational database, made to be rendered.

- **Enumerating.** It lists what there is, item by item, each with its sources. What is unknown is an open question with
  the name of the role that can answer it, never a guess.
- **A file system.** Plain text files in folders, on the subject's own machine, readable without any application.
- **A relational database.** Every item has a primary key (its id), its fields are columns, its references are foreign
  keys, and checks are constraints. The same files can be indexed and queried.
- **Made to be rendered.** The description exists to be turned into other forms for other readers: a 3D scene, a
  summary, an export for an agent, a public projection. A renderer can only show what the description holds, so the
  description is held to account.

## 2. Scales

<!-- atem: the grammar and its core, a domain's OES, an organization's additions -->

**COSM** is the family's name, from *kosmos*, order and world; it is not an acronym (it was *Context Ontology Schema and
Markup*, and before that *OPI*). `.cosm` is the family's file extension.

| Scale | What it is | Specified by |
|---|---|---|
| **MacroCOSM** | an OES: the shared grammar, and its core, what every reader has built in | MacroCOSM OES; the core in its section 18 |
| **MiniCOSM** | a domain's OES with a specification of its own, declared by a manifest (section 5) | Comprise OES; Ascribe |
| **MicroCOSM** | one organization's extension on top of a MiniCOSM: the extra kinds, fields, checks or renderers it needs | reserved for a later edition (section 6) |

A **built-in** is a kind of volume the core defines, declared by a manifest every reader ships with; it is never a
MiniCOSM. Thym is not a scale; its volumes are a built-in. Each smaller scale keeps the order of the larger and adds
to it.

## 3. The model: decompile, fabula, compile, short, atem

<!-- atem: input decompiled to fabula, compiled to short, said as atem -->

Software is moving up a layer: a structured plain-English specification is the program, it compiles to source code,
and source code compiles to an application. The same cycle serves prose. An input (an essay, a poem, a program's
folder) is **decompiled** to a **fabula**, which enumerates all the inspiration, meaning, intent, construction,
production and assertions that can be found in the input or derived from it. A fabula is **compiled** to a **short**,
and a short is said most plainly as an **atem**. Each step is an **entailment**, which expands meaning by reducing data:
the input entails its fabula, the fabula a short, and a short an atem. A Holotype entails its isotype too,
by rule.

| | Prose | Code |
|---|---|---|
| **The input** | a text | a repository |
| **The fabula** | a fabulan, or for verse a fabulap | a fabulac: the specification |
| **The short** | an entailment of the fabula | a cshort: the source code rebuilt, read and never run |
| **The atem** | one line | a catem: everything a user can do with the program |

The running application is outside these specifications. Decompiling a poem cannot be done well without its author or
someone who knows their work, so the core has one **dialectic**: questions put to a person, and their answers recorded.
The same programs run on a local model or, by choice, on a larger one through a broker, and a fabula records which
model made it.

## 4. What MacroCOSM gives every MiniCOSM

<!-- atem: the parts of the shared grammar every MiniCOSM inherits unchanged -->

Every MiniCOSM inherits all of it, unchanged. The right-hand column gives the section of MacroCOSM OES
(https://macro.cosmoes.org/) that defines each part; the examples are Comprise OES's.

| Part | What it is | Section of MacroCOSM OES |
|---|---|---|
| **Paths, and a URI form** | every item and field has an address that respells its id as a location, `mozilla-foundation/P/offering/creative-futures`; qualified with the format and the volume's database name it is a URI, `oes:<format>/<database>/<path>` | 11 |
| **Items, fields and references** | a row with a stable id and a kind; its fields are columns; a reference is an id written in a field, and every reference has two ends: the item `P:offering/ledger`, the reference `owner: O:role/Founder` | 7 and 9 |
| **The envelope** | the columns every item has: id, kind, name, summary, status, visibility, provenance (how it is known and how surely), open questions and typed links; a MiniCOSM adds its own | 8 |
| **Open questions** | a value nobody has given yet, `{pending: "…"}`, written where the value would go, with who can answer it; never a guess | 10 |
| **Checks** | constraints on the whole volume, run on every write; a write that breaks one is undone | 12 |
| **Saved and signed versions** | an immutable copy of the files at a moment, with a manifest of hashes, signed by the roles that govern it | 15 |
| **The private/public split** | two formats, not one with a setting: the complete private description (the **Holotype**), kept by its subject, and its small public projection (the **isotype**), default-deny, released and signed by the subject | 16 |
| **Renderers** | anything that turns a volume into another form; renderers only read, and show a reader only what that reader may see | 14 |
| **The manifest** | the machine-readable declaration of a MiniCOSM or a built-in, one `.cosm` file: what a program needs to read, check and render its volumes | 13 |
| **Densities** | one meaning at three densities: the fabula, a short it entails, and its atem | 18.1 and 18.4 |
| **The dialectic** | questions put to a person about what a source means, and the answers; any volume may carry them | 18.6 |

*Holotype* and *isotype* are taxonomy's words, the one specimen that defines a species and a duplicate of it; they name
the two halves of the split in every MiniCOSM, not only Comprise's.

## 5. What a MiniCOSM declares

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

## 6. What a MicroCOSM may change

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

## 7. The specifications and how they relate

<!-- atem: four documents: the grammar and its core, the language, two MiniCOSMs -->

Four specifications are published at cosmoes.org, each at its own home.

- **MacroCOSM OES** (https://macro.cosmoes.org/) is the grammar and its core: the parts in section 4, the file format,
  and what a conforming reader and writer must do. The core is its section 18, and its section 19 summarises the two
  MiniCOSMs.
- **Thym** (https://thym.cosmoes.org/) is the transcognition language that connects OESes: programs over volumes, in
  two grammar versions, with moves that decompile, compile, edit and question. A program says what it is for and what
  it must preserve, and its contracts are checked; its programs, plans, traces and packages are volumes of `thym/1`.
- **Ascribe** (https://ascribe.cosmoes.org/) is the MiniCOSM for a person: a **holograph**, the description of one self
  comprehensive enough that a name is unnecessary, kept private by its subject. It applies the dialectic to a person,
  and says how a holograph is released and projected, the **isograph** among its projections, always by a Thym program
  its holder runs.
- **Comprise OES** (https://comprise.cosmoes.org/) is the MiniCOSM for companies, and the first. A company is a set of
  **concerns** joined by **relationships**; its volume is the **Holotype**, one folder describing one company at a
  moment, and its public projection is the isotype.

The core's built-ins have no home of their own: `cosm` (a product tree), `canon` (Canon, the home file system), `fabula`
(in three flavours), `doc` (documents) and `thym` (Thym's volumes, specified in Thym's own text). `doc` is DocOES
(MacroCOSM OES, its section 18.5), the built-in these pages are made with, at three densities (atem, short, fabula).

A shared vocabulary of public forms ("chair", "M4 screw", "invoice": defined once, cited by every MiniCOSM that needs
them) is reserved for a later edition.

## 8. The picture

<!-- atem: the core, two MiniCOSMs, the language across them, the cycle -->

```text
              MacroCOSM OES: the shared grammar, and its core
   the core:  Canon, the home file system · the fabula · documents (DocOES)
              the product tree · Thym's volumes · the dialectic
                                      |
                 +--------------------+--------------------+
     Comprise OES: a company                     Ascribe: a person            MiniCOSMs
                 |
            a MicroCOSM: one organization's additions (reserved)

   <=================== Thym: the language that connects OESes ===================>

   input  --decompile-->  fabula  --compile-->  short  --said most plainly-->  atem
   prose:  a text         fabulan, fabulap      an entailment                  one line
   code:   a repository   fabulac               cshort                         catem

   Holotype, holograph: one private volume  --- projection --->  isotype, isograph: public, default-deny
        |
   renderers and lenses: a text tree, a card, an export

   every item is addressable:  oes:<format>/<database>/<path>
```

## 9. Editions

<!-- atem: editions, revisions, format versions and the canonical pages -->

An **edition** is a published state of one of these texts. Every text here, this page included, is at edition 0.6.0; the
status line says so. An edition is the text's, not the format's: a format's version (`thym/1`, `ascribe/1`,
`comprise/1`, the grammar version MacroCOSM OES names) is a line in the files a program reads, and each text's status
line names the one it describes. The canonical edition of each text is the page at its home; a copy an application ships
is a copy of an edition published here; the source and history of every page are at https://github.com/0gsd/cosmoes-site.

## 10. Implementations

<!-- atem: enough and Comprise, the reference implementations -->

Two products are the reference implementations. **enough** (https://github.com/0gsd/enough) implements MacroCOSM OES and
its core, Thym and Ascribe, and reads every built-in and both MiniCOSMs: it loads, checks and draws their volumes,
decompiles texts and programs and compiles their fabulas, shows a cshort and never runs it, compiles and runs Thym
programs, and builds documents with DocOES. **Comprise** implements Comprise OES: it writes and checks Holotypes, signs
their versions, and projects and releases isotypes. Where an implementation and a text disagree, one of them is in
error, and the text's Changes appendix records which was corrected.

## 11. Open formats

<!-- atem: open formats, the subject's files, the way out never sold -->

This site exists so that the formats are open. Every format these texts describe is documented here completely enough
that a second reader, writer, vault or index can be built from the text alone: the layer is larger than any one
product. The files a format describes belong to their subject: plain text, on the subject's own machine, readable
without any application, movable and complete, so that a subject who leaves takes everything. The format itself is
never sold, and neither is the way out of it: no product and no account stands between a subject and their own files.

## Changes

<!-- atem: what each edition changed, newest first -->

1. **Edition 0.6.0 (2026-11-06): the model and the core.** MacroCOSM is an OES with a core of built-ins; there are two
   MiniCOSMs, Comprise OES and Ascribe; Thym connects OESes. Section 2 is "Scales"; section 3, the model, is added, and
   sections 3 to 10 become 4 to 11; the parts table gains the densities and the dialectic; the fabula replaces EMF; the picture is redrawn; the colophon names the
   steward.
2. **Edition 0.5.4 (2026-11-03): the canonical edition at cosmoes.org.** The paradigm map becomes the text of
   cosmoes.org itself, named *The OES specifications*; the edition is a field in the status line. Section 6 is rewritten
   for the four specifications and the registered MiniCOSMs; the first form's sections 7 (connections to a wider
   ecosystem), 9 (a status table) and 10 (a repository listing) are removed, what survives of 7 folded into section 6,
   and the picture (section 8 in the first form) becomes section 7 and is redrawn; sections 8, 9 and 10 (editions,
   implementations, open formats) are added; *volume* replaces *database* for one instance of a MiniCOSM, as MacroCOSM
   OES uses it; repository paths, plans and what was built at a date are removed.
3. **2026-10-20: the paradigm map.** First written beside Comprise OES as the map of the OES family, in ten sections:
   sections 1 to 6 and the picture in their first form, a section on connections to a wider ecosystem, a status table
   of what was built and a listing of the folder it was written in. Comprise OES was the only MiniCOSM specified and
   MacroCOSM was drawn from it in outline.

## Colophon

<!-- atem: copyright, the canonical edition and its source -->

The OES specifications — Copyright © 2026 Graham Smith. All rights reserved. *The OES specifications* is stewarded by
Verroes (Graham Smith). The canonical edition is published at https://cosmoes.org/; its source and history are at
https://github.com/0gsd/cosmoes-site.

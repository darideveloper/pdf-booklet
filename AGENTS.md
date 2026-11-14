# pdf-booklet — agent notes

Imposes a PDF as **nested signatures** so a book can be folded and sewn by hand
(pamphlet stitch). One file of logic (`booklet.py`), one importable entry point
(`main.py`), PyMuPDF only. No paper size is hardcoded: the sheet is derived from
the source page.

## Commands

```bash
python3 main.py book.pdf              # same CLI as python3 booklet.py
python3 booklet.py book.pdf
python3 booklet.py --selftest         # zero-dependency smoke test, writes nothing
pytest -q                             # full suite
ruff check . && ruff format --check . # lint and formatting
pip install -e ".[dev]"               # dev install (pytest + ruff)
pipx install .                        # exposes the pdf-booklet command
```

## Layout

| file | role |
|---|---|
| `booklet.py` | ordering, imposition, file handling, CLI, `--selftest` |
| `main.py` | entry point; imports `booklet.main` |
| `tests/test_booklet.py` | pytest: page math, grouping, margins, marks, CLI errors |
| `pyproject.toml` | hatchling build, console script, ruff and pytest config |
| `README.md` | user-facing usage and assembly instructions |

## The rule (do not change casually)

Sheet `s` of a signature padded to `g` pages:

```
side A left  = g - 2s     side A right = 2s + 1
side B left  = 2s + 2     side B right = g - 2s - 1
```

Reading order of one folded sheet is front-right → back-left → back-right →
front-left. `reading_order(g)` must always equal `1..g`; that invariant is
tested for g in {4, 8, 12, 20, 24, 40}. Signatures nest outward → inward.

## Invariants and gotchas

- **Signatures are multiples of 4.** `plan_groups` pads the last group; a group
  short by `k` pages gets `k` blank halves. Each signature contributes an even
  number of printed sides, so duplex pairing never breaks at a boundary.
- **`-g` is a maximum**, not a target. Greedy fill by default; `--balance` evens
  the signature sizes instead (45 pages at `-g 20`: `20+20+8` vs `16+16+16`).
- **Duplex is flip-on-short-edge.** `--rotate-back` is for drivers that flip on
  the long edge; it rotates the back side 180°. There is no third back mode.
- **Content stays vector** — `show_pdf_page` embeds the source as a Form XObject.
  Annotations, form fields and links are dropped. Acceptable for print.
- **Landscape sources** are treated as landscape: in `half` mode they shrink to
  fit the half and are centred; a warning is printed. Rotated pages (`/Rotate`)
  are handled by PyMuPDF, so a 90° scan lands upright.
- **`--crop-marks` needs `--margin` of at least 3 mm**, otherwise the ticks are
  skipped with a warning rather than drawn over the content.
- **The printed `page scale` is real**, computed from the inset half, not a
  decorative constant. Adding a margin lowers it.
- **`--split` overwrites** existing `<stem>-gN.pdf` files silently.
- Tested with PyMuPDF 1.28.2 / Python 3.12; `requires-python = ">=3.9"` and
  `pymupdf>=1.24`. Only long-stable PyMuPDF calls are used.

## When editing

- Keep `sheets_for` pure and the ordering assertions intact; every other feature
  is cosmetic on top of it.
- New CLI behaviour needs a test in `tests/test_booklet.py` and a line in the
  README options list.
- Prefer `print(..., file=sys.stderr)` for warnings; stdout carries the manifest.

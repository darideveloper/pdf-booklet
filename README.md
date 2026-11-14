# pdf-booklet

Impose any PDF as nested signatures for **hand folding and sewing**: two source
pages per printed side, both sides, landscape, page order 1..N preserved when
folded.

No paper size is hardcoded. Sheets are derived from the source page:

| mode | sheet | finished book | page scale |
|---|---|---|---|
| `half` (default) | Carta landscape, 11 × 8.5 in | media carta, 5.5 × 8.5 in | 64.7 % |
| `full` | Tabloide, 17 × 11 in | Carta, 8.5 × 11 in | 100 % |

A4 sources behave the same way: `half` → A4 landscape, A5 finished (70.7 %);
`full` → A3 landscape, A4 finished (100 %). The percentages assume no
`--margin`; the scale actually used is always printed in the manifest.

## Install

```bash
pipx install .          # or: pip install .
pdf-booklet book.pdf
```

Running it straight from the checkout needs nothing but PyMuPDF:

```bash
pip install -r requirements.txt
python3 main.py book.pdf       # main.py and booklet.py are the same CLI
```

## The rule

Sheet `s` of a signature padded to `g` pages:

```
side A left  = g - 2s        side A right = 2s + 1
side B left  = 2s + 2        side B right = g - 2s - 1
```

Reading order inside one folded sheet is **front-right → back-left →
back-right → front-left**. Signatures nest outermost → innermost and back out,
so the reader just gets 1, 2, 3, ...

For `g = 20` (5 sheets, one 20-page signature):

| sheet | side A | side B | reads as |
|---|---|---|---|
| 1 | 20 ┃ 1 | 2 ┃ 19 | 1, 2, 19, 20 |
| 2 | 18 ┃ 3 | 4 ┃ 17 | 3, 4, 17, 18 |
| 3 | 16 ┃ 5 | 6 ┃ 15 | 5, 6, 15, 16 |
| 4 | 14 ┃ 7 | 8 ┃ 13 | 7, 8, 13, 14 |
| 5 | 12 ┃ 9 | 10 ┃ 11 | 9, 10, 11, 12 |

Pages 1 and 20 are the two halves of sheet 1's **outer face** (front and back
cover). They are never two faces of the same leaf — that would be a separate
cover sheet, which is a different binding.

## Usage

```bash
python3 main.py book.pdf                     # book-booklet.pdf, groups of 20
python3 main.py book.pdf -m full             # full-size pages on Tabloide
python3 main.py book.pdf --split             # one PDF per group
python3 main.py book.pdf --balance           # even signatures instead of 20+20+8
python3 main.py book.pdf --margin 5          # 5 mm inset on every half
python3 main.py book.pdf --margin 5 --crop-marks   # plus trim/fold ticks
python3 main.py book.pdf --rotate-back       # if duplex prints backs upside down
python3 main.py book.pdf --fold-line         # faint dashed line down the middle
python3 main.py --selftest                   # page math + round-trip, writes nothing
```

| option | meaning |
|---|---|
| `-o/--out` | output path (default `<stem>-booklet.pdf`) |
| `-g/--group N` | max source pages per signature, multiple of 4 (default 20) |
| `-m/--mode full\|half` | sheet geometry; `half` is the default |
| `--margin MM` | inset each half by MM millimetres (default 0) |
| `--balance` | spread pages evenly over the signatures |
| `--crop-marks` | corner and centre-fold ticks; needs `--margin` ≥ 3 mm |
| `--fold-line` | dashed centre line, independent of `--crop-marks` |
| `--rotate-back` | rotate back sides 180° for long-edge duplex drivers |
| `--split` | one PDF per signature |
| `--password` | password for an encrypted PDF |
| `--selftest` | verify ordering and a 20-page round-trip |
| `--version` | print the version |

Exit codes: `0` fine, `1` runtime error (unreadable input, unwritable output),
`2` bad usage.

A **margined** run, for printers that cannot print to the edge: content is
inset by `--margin`, so facing pages get a gutter of twice that margin, and the
reported page scale drops accordingly. `--crop-marks` draws 3 mm ticks at the
corners of each half plus ticks on the fold.

## Printing

1. **100% / actual size.** Never "fit to printable area" — scaling shifts the
   pages and the fold misaligns. If your printer needs a border, use `--margin`.
2. **Duplex, one side per sheet**, no scaling, no driver "booklet" mode (this
   file is already imposed). The layout assumes **flip on short edge**.
3. **Flip edge:** the fold is vertical, so the back side must mirror
   left↔right. Print one sheet, fold it, read it: `1` on the cover, open → `2`
   on the left. If the back is upside down, reprint with `--rotate-back` (or
   switch the driver's flip setting).
4. Print sheets in reverse order so the stack comes off the tray already
   nested (sheet carrying `20┃1` at the bottom), or just reverse the pile by
   hand.

### Without duplex (manual duplex)

The output is already ordered so one landscape sheet holds a front and its
back. Print the **odd** output pages, put the stack back as a block without
reordering it, then print the **even** output pages. The manifest labels each
side `front N` / `back N`.

## Assembly

```
sheet with 20|1   at the BOTTOM  (outermost, becomes the cover)
sheet with 18|3
sheet with 16|5
sheet with 14|7
sheet with 12|9   on TOP         (innermost, center spread 10|11)
```

Fold the whole stack in half on the vertical center line, then sew through the
fold — 3 holes is enough for 5 sheets (pamphlet stitch), 5 holes for a longer
signature. Trim the fore edge after folding if the inner sheets protrude.

Multiple groups: each group is an independent signature. With `--balance` the
groups are even; without it the first ones fill to `--group` and the last is
padded with blanks. Sew each one, then stack groups in order and bind the block
along the spine.

## Notes

- Content stays **vector** (`show_pdf_page` embeds the source page as a Form
  XObject); nothing is rasterized.
- Annotations and form fields are not copied, links are dropped. Fine for
  print; use another tool if you need them.
- Groups are padded to a multiple of 4 with blank pages, and every group
  contributes an even number of printed sides, so duplex pairing never breaks
  at a group boundary.
- Landscape source pages are scaled down to fit their half and centred, with a
  warning; rotated pages (`/Rotate`) are handled by PyMuPDF.
- Encrypted PDFs: `--password`.
- `--split` overwrites an existing `<stem>-gN.pdf` without asking.

## Development

```bash
pip install -e ".[dev]"
pytest -q
ruff check . && ruff format --check .
python3 booklet.py --selftest
```

License: MIT.

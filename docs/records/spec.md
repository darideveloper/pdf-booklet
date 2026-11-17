# pdf-booklet — spec

Impose a PDF as nested signatures so it can be folded and sewn by hand.

## Command surface

`python main.py <pdf | folder> [options]` (or `pdf-booklet …` after
`pip install -e .`), documented in `README.md`. One file
of logic (`booklet.py`), one entry point (`main.py`), PyMuPDF only.

## Rule

Sheet `s` of a signature padded to `g` pages: side A left `g - 2s`, side A right
`2s + 1`, side B left `2s + 2`, side B right `g - 2s - 1`. Reading order of one
folded sheet is front-right, back-left, back-right, front-left; signatures nest
outward to inward. `reading_order(g)` must equal `1..g` for every multiple of 4.

Sheet geometry is derived from the source page, never from a paper name:
`--mode full` doubles the width, `--mode half` keeps the paper landscape and
scales the page to fit the half.

## Invariants

- Signatures are multiples of 4; `plan_groups` pads the last group with blank
  halves so duplex pairing never breaks at a boundary.
- `--group` is a maximum, not a target; `--balance` evens the sizes instead.
- Folder input converts every `*.pdf` in place with `--suffix`, skipping names
  this tool already produced, so a second run never nests outputs.
- Duplex is flip-on-short-edge; `--rotate-back` compensates a long-edge driver.
- Content stays vector (`show_pdf_page` embeds a Form XObject); annotations,
  form fields and links are dropped.
- Margin, crop marks and the reported page scale are real measurements, not
  decorative constants.
- Blank padding halves stay blank: nothing is drawn on them.
- `--page-numbers` prints the **original** source page number, never the position
  inside the signature, so a folded copy can be put back in order.

# Log

## optional-page-numbers — shipped 2026-11-16
Shipped: `--page-numbers` prints each half's **original PDF page number** at 7pt in that half's
top-right corner, inside the margin band; blank padding halves stay blank. Threaded through
`build`, `--split`, `--rotate-back` and folder mode; off by default.
Decisions: 2026-11-16 — the number is the absolute source page (`group_pages[pno - 1] + 1`), never
the position inside the signature. Why: a folded copy has to be reconstructable in order, and a
positional counter says `1, 2` on the outer face where the pages are really `4, 1`.
Follow-ups: p10 print-and-fold check on paper; left halves number at the fold, so mirror them to
top-left only if sewing crowds them.
Plan: 9/10 steps · dropped 0 · open 1
Card: none (chat-only)
Drift: none — the behaviour is in `spec.md` (original-numbering invariant) and the README
paragraph; no decision was needed beyond the one above.

## choose-output-folder — shipped 2026-11-16
Shipped: `--out-dir DIR` writes a folder's outputs (or one PDF's) into a chosen directory,
created if missing; `-o/--out` keeps precedence and `--suffix`/`--split` name the files as
before. Five new tests: nested out-dir, `--split` into it, single file, `-o` precedence, and a
destination that is a file (exit 1, `cannot create`).
Decisions: none — `-o` winning over `--out-dir` is a per-step choice, not a shared contract.
Follow-ups: `default-folder-output` is planned and unbuilt (folder runs still write in place);
`spec.md` still says folder input converts "in place"; the change is uncommitted.
Plan: 8/8 steps · dropped 0 · open 0
Card: none (chat-only)
Drift: spec drift — `spec.md`'s folder invariant predates `--out-dir` and now describes only the
default; no evidence captured for p1–p8 (chat-only run outside pair).

## page-numbers-bottom-right — shipped 2026-11-16
Shipped: `--page-numbers` now draws each half's 7pt original page number in the **bottom-right**
corner instead of the top-right. `_page_number` mirrors the old top rule and clamps the baseline 3pt
above the trim so the font's descender stays on the sheet when there is no margin. x, the absolute
numbering and the blank padding halves are unchanged; one test rewritten, one added for `--margin 0`,
README and `--help` reworded.
Decisions: none — the move is cosmetic, and the 2026-11-16 "absolute source page, never the position
in the signature" decision still holds.
Follow-ups: left halves still number at their half's right edge, which is the fold — mirror them to
bottom-left if sewing crowds them; with `--crop-marks` the bottom-right corner tick shares the digit's
corner.
Plan: 6/6 steps · dropped 0 · open 0
Card: none (chat-only)
Drift: spec drift — `spec.md`'s `--page-numbers` invariant still names no corner; the pair close never
wrote it. No decision drift; evidence in
`docs/ai-daridev/evidence/2026-11-16-page-numbers-bottom-right/` (p1 and p5 screenshots, p2/p3/p6
code lines).


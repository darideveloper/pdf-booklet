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

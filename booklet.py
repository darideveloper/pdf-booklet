#!/usr/bin/env python3
"""Impose a PDF as nested signatures (booklet) for hand folding and sewing.

Sheet ``s`` of a signature padded to ``g`` pages carries:

    side A left  = g - 2s        side A right = 2s + 1
    side B left  = 2s + 2        side B right = g - 2s - 1

Reading order of one folded sheet is front-right, back-left, back-right,
front-left; signatures nest outermost -> innermost and back out again, which
makes the whole thing read 1, 2, 3 ... g.

Output sheets are derived from the source page, never from a paper name:
``--mode full`` doubles the width (Carta -> Tabloide, 100% scale), ``--mode
half`` keeps the paper size landscape and scales the page to fit the half
(64.7% for Letter with no margin -> media carta finished).

Duplex is assumed to flip on the short edge; ``--rotate-back`` compensates a
driver that flips on the long edge instead.
"""

from __future__ import annotations

import argparse
import sys
import tempfile
from pathlib import Path

import pymupdf

__version__ = "0.1.0"

MM = 72 / 25.4  # points per millimetre
CROP_TICK = 3 * MM  # length of the ticks drawn by --crop-marks
PAGE_NUMBER_SIZE = 7  # points, for the numbers drawn by --page-numbers
DEFAULT_SUFFIX = "-booklet"  # appended to every output name

MANUAL_DUPLEX = """\
Manual duplex (a printer without duplex):
  1. print the odd output pages;
  2. put the stack back exactly as it is, without reordering it;
  3. print the even output pages.

Duplex: flip on short edge. If the backs come out upside down, add
--rotate-back (or change the driver's flip setting) and reprint."""


# --- ordering -------------------------------------------------------------


def sheets_for(g: int) -> list[tuple[int, int, int, int]]:
    """(side A left, side A right, side B left, side B right) per sheet.
    Index 0 is the outermost sheet; pages past ``g`` are left blank."""
    if g % 4:
        raise ValueError(f"page count must be a multiple of 4, got {g}")
    return [(g - 2 * s, 2 * s + 1, 2 * s + 2, g - 2 * s - 1) for s in range(g // 4)]


def reading_order(g: int) -> list[int]:
    """Pages as a reader meets them, front to back of the finished booklet."""
    sheets = sheets_for(g)
    seq: list[int] = []
    for _, ar, bl, _ in sheets:  # outermost -> innermost: FR, BL
        seq += [ar, bl]
    al, ar, bl, br = sheets[-1]  # innermost: BR, FL
    seq += [br, al]
    for al, _, _, br in reversed(sheets[:-1]):  # back out: BR, FL
        seq += [br, al]
    return seq


def _round_up4(n: int) -> int:
    return max(4, -(-n // 4) * 4)


def plan_groups(n: int, group: int, balance: bool = False) -> list[tuple[int, int, list[int], int]]:
    """Split ``n`` pages into signatures of at most ``group`` pages.

    ``(start, end, pages, padded)`` per signature. Greedy by default, so 45
    pages at 20 give 20, 20, 5 (+3 blank); ``balance`` evens them out instead,
    giving 16, 16, 16.
    """
    if group < 4 or group % 4:
        raise ValueError(f"group must be a multiple of 4 and at least 4, got {group}")
    if n < 1:
        raise ValueError("a source PDF needs at least one page")

    if balance:
        count = -(-n // group)
        target = _round_up4(-(-n // count))
        sizes: list[int] = []
        left = n
        while left:
            size = min(target, left)
            sizes.append(size)
            left -= size
    else:
        sizes = [min(group, n - start) for start in range(0, n, group)]

    groups: list[tuple[int, int, list[int], int]] = []
    start = 0
    for size in sizes:
        pages = list(range(start, start + size))
        groups.append((start, start + size, pages, _round_up4(size)))
        start += size
    return groups


# --- imposition -----------------------------------------------------------


def _sheet_size(w: float, h: float, mode: str) -> tuple[float, float]:
    if mode == "full":
        return 2 * w, h
    return max(w, h), min(w, h)


def _content_scale(w: float, h: float, sheet: tuple[float, float], margin: float) -> float:
    """How much of its original size a page keeps once it is inside a half."""
    slot = sheet[0] / 2
    return min((slot - 2 * margin) / w, (sheet[1] - 2 * margin) / h)


def _crop_marks(page: pymupdf.Page, slot: float, sh: float, margin: float) -> None:
    """Corner ticks around each half plus ticks on the centre fold."""
    ink = (0.0, 0.0, 0.0)
    for half in (0, 1):
        x0, x1 = half * slot + margin, (half + 1) * slot - margin
        for x, dx in ((x0, -1), (x1, 1)):
            for y, dy in ((margin, -1), (sh - margin, 1)):
                page.draw_line((x, y), (x + dx * CROP_TICK, y), color=ink, width=0.3)
                page.draw_line((x, y), (x, y + dy * CROP_TICK), color=ink, width=0.3)
    for y, dy in ((0, 1), (sh, -1)):
        page.draw_line((slot, y), (slot, y + dy * CROP_TICK), color=ink, width=0.3)


def _page_number(page: pymupdf.Page, number: int, right: float, margin: float) -> None:
    """The source page's own number, small, in the half's bottom-right corner."""
    label = str(number)
    x = right - pymupdf.get_text_length(label, fontname="helv", fontsize=PAGE_NUMBER_SIZE)
    # Mirror the top rule, but never lower than 3pt above the trim: with no
    # margin the font's descender would otherwise fall off the sheet.
    height = page.rect.height
    y = min(height - max(margin - 2, 8) + PAGE_NUMBER_SIZE, height - 3)
    page.insert_text((x, y), label, fontname="helv", fontsize=PAGE_NUMBER_SIZE)


def impose_into(
    out: pymupdf.Document,
    src: pymupdf.Document,
    group_pages: list[int],
    padded: int,
    sheet: tuple[float, float],
    margin: float = 0.0,
    rotate_back: bool = False,
    fold_line: bool = False,
    crop_marks: bool = False,
    page_numbers: bool = False,
) -> None:
    """Append the printed sides of one signature to ``out``."""
    sw, sh = sheet
    slot = sw / 2
    if margin * 2 >= min(slot, sh):
        raise ValueError(f"margin {margin:.1f}pt leaves no room on the sheet")
    for al, ar, bl, br in sheets_for(padded):
        for side, (left, right) in enumerate(((al, ar), (bl, br))):
            page = out.new_page(width=sw, height=sh)
            for i, pno in enumerate((left, right)):
                if pno > len(group_pages):
                    continue  # padding: leave the half blank
                area = pymupdf.Rect(i * slot + margin, margin, (i + 1) * slot - margin, sh - margin)
                page.show_pdf_page(area, src, group_pages[pno - 1])
                if page_numbers:
                    _page_number(page, group_pages[pno - 1] + 1, (i + 1) * slot - 2, margin)
            if crop_marks:
                _crop_marks(page, slot, sh, margin)
            if fold_line:
                page.draw_line(
                    pymupdf.Point(slot, 0),
                    pymupdf.Point(slot, sh),
                    color=(0.62, 0.62, 0.62),
                    width=0.3,
                    dashes="[2 5] 0",
                )
            if side == 1 and rotate_back:
                page.set_rotation(180)


# --- files ----------------------------------------------------------------


def open_pdf(path: str, password: str | None = None) -> pymupdf.Document:
    """Open a source PDF, or exit with a message a human can act on."""
    try:
        doc = pymupdf.open(path)
    except (RuntimeError, ValueError) as exc:
        raise SystemExit(f"error: not a readable PDF: {path} ({exc})") from None
    if doc.needs_pass and not (password and doc.authenticate(password)):
        raise SystemExit(f"error: {path} is encrypted (use --password)")
    if not len(doc):
        raise SystemExit(f"error: {path} has no pages")
    return doc


def _save_pdf(doc: pymupdf.Document, path: Path) -> None:
    try:
        doc.save(str(path), garbage=3, deflate=True)
    except (OSError, RuntimeError) as exc:
        raise SystemExit(f"error: cannot write {path}: {exc}") from None


def output_for(src: Path, suffix: str) -> Path:
    """Plot the output next to the source, carrying the suffix."""
    return src.with_name(f"{src.stem}{suffix}{src.suffix}")


def out_dir(value: str) -> Path:
    """The chosen output folder, created if it does not exist yet."""
    folder = Path(value)
    try:
        folder.mkdir(parents=True, exist_ok=True)
    except OSError as exc:
        raise SystemExit(f"error: cannot create {folder}: {exc}") from None
    return folder


def _is_generated(path: Path, suffix: str) -> bool:
    """True for a file this tool wrote, so a re-run does not nest outputs."""
    stem = path.stem
    if stem.endswith(suffix):
        return True
    base, sep, tail = stem.rpartition("-g")
    return bool(sep) and tail.isdigit() and base.endswith(suffix)


def _pdf_files(folder: Path, suffix: str) -> tuple[list[Path], int]:
    """PDFs worth converting, plus how many generated files were skipped."""
    everything = sorted(p for p in folder.iterdir() if p.is_file() and p.suffix.lower() == ".pdf")
    files = [p for p in everything if not _is_generated(p, suffix)]
    return files, len(everything) - len(files)


def build(
    src_path: str,
    out_path: str,
    group: int = 20,
    mode: str = "half",
    margin_mm: float = 0.0,
    balance: bool = False,
    rotate_back: bool = False,
    fold_line: bool = False,
    crop_marks: bool = False,
    page_numbers: bool = False,
    split: bool = False,
    password: str | None = None,
) -> list[tuple[int, int, list[int], int]]:
    src = open_pdf(src_path, password)
    n = len(src)
    if margin_mm < 0:
        raise SystemExit("error: --margin cannot be negative")
    margin = margin_mm * MM

    w, h = src[0].rect.width, src[0].rect.height
    odd = [
        i + 1 for i in range(n) if abs(src[i].rect.width - w) > 1 or abs(src[i].rect.height - h) > 1
    ]
    if odd:
        print(
            f"warning: pages sized differently from page 1: {_ranges(odd)} (scaled to fit)",
            file=sys.stderr,
        )

    landscape = [i + 1 for i in range(n) if src[i].rect.width > src[i].rect.height]
    if mode == "half" and landscape:
        print(
            f"warning: source pages display landscape and are scaled down to fit "
            f"their half: {_ranges(landscape)}",
            file=sys.stderr,
        )

    groups = plan_groups(n, group, balance)
    sheet = _sheet_size(w, h, mode)
    slot = sheet[0] / 2
    if margin * 2 >= min(slot, sheet[1]):
        raise SystemExit(f"error: --margin {margin_mm:g} mm leaves no room on a {slot:.0f}pt half")
    if crop_marks and margin < CROP_TICK:
        print(
            f"warning: --crop-marks needs --margin of at least {CROP_TICK / MM:.0f} mm; "
            f"skipping the marks",
            file=sys.stderr,
        )
        crop_marks = False

    out_file = Path(out_path)
    options = (sheet, margin, rotate_back, fold_line, crop_marks, page_numbers)
    if split:
        for k, (_, _, pages, padded) in enumerate(groups, 1):
            out = pymupdf.open()
            impose_into(out, src, pages, padded, *options)
            _save_pdf(out, out_file.with_name(f"{out_file.stem}-g{k}{out_file.suffix}"))
            out.close()
    else:
        out = pymupdf.open()
        for _, _, pages, padded in groups:
            impose_into(out, src, pages, padded, *options)
        _save_pdf(out, out_file)
        out.close()

    scale = _content_scale(w, h, sheet, margin)
    _manifest(
        src_path,
        out_path,
        groups,
        sheet=sheet,
        margin=margin,
        scale=scale,
        mode=mode,
        split=split,
        balance=balance,
        page_numbers=page_numbers,
    )
    src.close()
    return groups


def _ranges(nums: list[int]) -> str:
    if len(nums) > 12:
        return f"{nums[0]}..{nums[-1]} ({len(nums)} pages)"
    return ", ".join(map(str, nums))


def _page_label(p: int, start: int, count: int) -> str:
    return f"{start + p:>3}" if p <= count else "  -"


def _manifest(
    src_path: str,
    out_path: str,
    groups: list[tuple[int, int, list[int], int]],
    *,
    sheet: tuple[float, float],
    margin: float,
    scale: float,
    mode: str,
    split: bool,
    balance: bool,
    page_numbers: bool = False,
) -> None:
    sw, sh = sheet
    pages = sum(len(p) for _, _, p, _ in groups)
    total_sides = sum(2 * (padded // 4) for *_, padded in groups)
    print(f"source : {src_path}  ({pages} pages)")
    print(
        f"mode   : {mode}  sheet {sw:.0f}x{sh:.0f}pt ({sw / 72:.2f}x{sh / 72:.2f}in)"
        f"  margin {margin / MM:.1f}mm  page scale {scale * 100:.1f}%"
        f"{'  page numbers on' if page_numbers else ''}"
    )
    print(f"groups : {len(groups)} signature(s){' balanced' if balance else ''}")
    target = out_path
    if split:
        base = Path(out_path)
        target = str(base.with_name(f"{base.stem}-gN{base.suffix}"))
    print(f"output : {target}  {total_sides} printed sides")
    side = 0
    for k, (start, end, group_pages, padded) in enumerate(groups, 1):
        blanks = padded - len(group_pages)
        note = f"  (+{blanks} blank)" if blanks else ""
        labels = [_page_label(p, start, len(group_pages)) for p in range(1, padded + 1)]

        print(f"group {k}: source {start + 1}-{end}{note}")
        for s, (al, ar, bl, br) in enumerate(sheets_for(padded), 1):
            side += 2
            print(
                f"  sheet {s}  A[{labels[al - 1]}|{labels[ar - 1]}]"
                f"  B[{labels[bl - 1]}|{labels[br - 1]}]"
                f"  front {side - 1}  back {side}"
            )


# --- self-test ------------------------------------------------------------

EXPECTED_20 = [(20, 1, 2, 19), (18, 3, 4, 17), (16, 5, 6, 15), (14, 7, 8, 13), (12, 9, 10, 11)]
EXPECTED_8 = [(8, 1, 2, 7), (6, 3, 4, 5)]


def _numbered_pdf(path: Path, n: int) -> None:
    doc = pymupdf.open()
    for i in range(1, n + 1):
        page = doc.new_page(width=612, height=792)  # US Letter
        page.insert_text((36, 80), str(i), fontsize=48)
    doc.save(str(path))
    doc.close()


def _halves(page: pymupdf.Page) -> tuple[list[str], list[str]]:
    mid = page.rect.width / 2
    left: list[str] = []
    right: list[str] = []
    for block in page.get_text("dict")["blocks"]:
        for line in block.get("lines", []):
            for span in line["spans"]:
                text = span["text"].strip()
                if text:
                    x = (span["bbox"][0] + span["bbox"][2]) / 2
                    (left if x < mid else right).append(text)
    return left, right


def selftest() -> int:
    for g in (4, 8, 12, 20, 24, 40):
        order = reading_order(g)
        assert order == list(range(1, g + 1)), (g, order)
        flat = [p for s in sheets_for(g) for p in s]
        assert sorted(flat) == list(range(1, g + 1)), (g, flat)
    assert sheets_for(20) == EXPECTED_20, sheets_for(20)
    assert sheets_for(8) == EXPECTED_8, sheets_for(8)
    assert [(len(p), pad) for *_, p, pad in plan_groups(45, 20)] == [(20, 20), (20, 20), (5, 8)]
    assert [pad for *_, pad in plan_groups(45, 20, balance=True)] == [16, 16, 16]

    with tempfile.TemporaryDirectory() as tmp:
        tmp = Path(tmp)

        # 20 pages, one exact signature
        src_path = tmp / "n20.pdf"
        _numbered_pdf(src_path, 20)
        doc = pymupdf.open(str(src_path))
        out = pymupdf.open()
        impose_into(out, doc, list(range(20)), 20, _sheet_size(612, 792, "half"))
        want = [pair for al, ar, bl, br in EXPECTED_20 for pair in ((al, ar), (bl, br))]
        assert len(out) == 10, len(out)
        for i, page in enumerate(out):
            left, right = _halves(page)
            exp_l, exp_r = want[i]
            assert left == [str(exp_l)], (i, left, exp_l)
            assert right == [str(exp_r)], (i, right, exp_r)
        out.close()
        doc.close()

        # 6 pages -> 8 padded, blanks left white
        src_path = tmp / "n6.pdf"
        _numbered_pdf(src_path, 6)
        doc = pymupdf.open(str(src_path))
        out = pymupdf.open()
        impose_into(out, doc, list(range(6)), 8, _sheet_size(612, 792, "half"))
        assert len(out) == 4, len(out)
        want6 = [([], ["1"]), (["2"], []), (["6"], ["3"]), (["4"], ["5"])]
        for i, page in enumerate(out):
            assert _halves(page) == want6[i], (i, _halves(page), want6[i])
        out.close()
        doc.close()

        # 45 pages in groups of 20 -> only one PDF, 24 sides, last group padded
        src_path = tmp / "n45.pdf"
        _numbered_pdf(src_path, 45)
        groups = build(str(src_path), str(tmp / "n45-booklet.pdf"), group=20)
        assert [(len(p), pad) for *_, p, pad in groups] == [(20, 20), (20, 20), (5, 8)], [
            (len(p), pad) for *_, p, pad in groups
        ]
        doc = pymupdf.open(str(tmp / "n45-booklet.pdf"))
        assert len(doc) == 24
        doc.close()

    print("selftest: ok")
    return 0


# --- cli ------------------------------------------------------------------


def _group_arg(value: str) -> int:
    try:
        group = int(value)
    except ValueError:
        raise argparse.ArgumentTypeError(f"not an integer: {value!r}") from None
    if group < 4 or group % 4:
        raise argparse.ArgumentTypeError(f"must be a multiple of 4 and at least 4, got {group}")
    return group


def _mm_arg(value: str) -> float:
    try:
        mm = float(value)
    except ValueError:
        raise argparse.ArgumentTypeError(f"not a number: {value!r}") from None
    if mm < 0:
        raise argparse.ArgumentTypeError(f"cannot be negative, got {mm:g}")
    return mm


def _suffix_arg(value: str) -> str:
    if not value:
        raise argparse.ArgumentTypeError("cannot be empty")
    if "/" in value or "\\" in value:
        raise argparse.ArgumentTypeError("cannot contain a path separator")
    return value


def _convert(src: Path, out: Path, args: argparse.Namespace) -> None:
    build(
        str(src),
        str(out),
        group=args.group,
        mode=args.mode,
        margin_mm=args.margin,
        balance=args.balance,
        rotate_back=args.rotate_back,
        fold_line=args.fold_line,
        crop_marks=args.crop_marks,
        page_numbers=args.page_numbers,
        split=args.split,
        password=args.password,
    )


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(
        description="Impose a PDF as nested signatures for hand folding and sewing.",
        epilog=MANUAL_DUPLEX,
        formatter_class=argparse.RawDescriptionHelpFormatter,
    )
    ap.add_argument("input", nargs="?", help="source PDF, or a folder of PDFs")
    ap.add_argument(
        "-o", "--out", help="output path for a single file (default: <stem><suffix>.pdf)"
    )
    ap.add_argument(
        "--out-dir",
        metavar="DIR",
        help="collect outputs in DIR, created if missing (folder input, or one PDF; -o wins)",
    )
    ap.add_argument(
        "-g",
        "--group",
        type=_group_arg,
        default=20,
        metavar="N",
        help="max source pages per signature, multiple of 4 (default 20)",
    )
    ap.add_argument(
        "-m",
        "--mode",
        choices=("full", "half"),
        default="half",
        help="full = double width, 100%% page scale (Carta -> Tabloide); "
        "half = same paper landscape, pages scaled to fit "
        "(Carta -> Carta, media carta finished). Default: half",
    )
    ap.add_argument(
        "--margin",
        type=_mm_arg,
        default=0.0,
        metavar="MM",
        help="inset each half by MM millimetres (default 0)",
    )
    ap.add_argument(
        "--balance",
        action="store_true",
        help="spread pages evenly over the signatures instead of filling the first ones to --group",
    )
    ap.add_argument(
        "--rotate-back",
        action="store_true",
        help="rotate every back side 180 degrees if duplex prints it upside down",
    )
    ap.add_argument(
        "--fold-line",
        action="store_true",
        help="draw a faint dashed line down the middle of each sheet",
    )
    ap.add_argument(
        "--crop-marks",
        action="store_true",
        help="draw corner ticks and centre-fold ticks (needs --margin >= 3mm)",
    )
    ap.add_argument(
        "--page-numbers",
        action="store_true",
        help="print each half's original page number, 7pt, in its bottom-right corner",
    )
    ap.add_argument(
        "--split", action="store_true", help="write one PDF per group instead of a single file"
    )
    ap.add_argument("--password", help="password for an encrypted PDF")
    ap.add_argument(
        "--suffix",
        type=_suffix_arg,
        default=DEFAULT_SUFFIX,
        metavar="TEXT",
        help=f"appended to each output name (default {DEFAULT_SUFFIX})",
    )
    ap.add_argument(
        "--selftest",
        action="store_true",
        help="check page ordering and a 20-page round-trip, write nothing",
    )
    ap.add_argument("--version", action="version", version=f"%(prog)s {__version__}")
    args = ap.parse_args(argv)

    if args.selftest:
        return selftest()
    if not args.input:
        ap.error("the following arguments are required: input")

    src = Path(args.input)
    if not src.exists():
        raise SystemExit(f"error: no such file or folder: {src}")

    if src.is_dir():
        if args.out:
            raise SystemExit("error: -o/--out is for a single file, not a folder")
        files, skipped = _pdf_files(src, args.suffix)
        if skipped:
            print(f"skipping {skipped} generated file(s) in {src}", file=sys.stderr)
        if not files:
            raise SystemExit(f"error: no PDFs to convert in {src}")
        dest = out_dir(args.out_dir) if args.out_dir else src
        failed = 0
        for path in files:
            try:
                _convert(path, dest / output_for(path, args.suffix).name, args)
            except SystemExit as exc:
                failed += 1
                print(exc.code if isinstance(exc.code, str) else "error", file=sys.stderr)
        if failed:
            raise SystemExit(f"error: {failed} of {len(files)} file(s) failed")
        print(f"converted {len(files)} file(s)")
        return 0

    if not src.is_file():
        raise SystemExit(f"error: no such file: {src}")
    if args.out:
        out = Path(args.out)
    else:
        dest = out_dir(args.out_dir) if args.out_dir else src.parent
        out = dest / output_for(src, args.suffix).name
    _convert(src, out, args)
    return 0


if __name__ == "__main__":
    sys.exit(main())

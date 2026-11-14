"""Tests for the booklet imposition: ordering, grouping, margins and CLI."""

from __future__ import annotations

import pymupdf
import pytest

import booklet


def _numbered(path, n, width=612, height=792):
    doc = pymupdf.open()
    for i in range(1, n + 1):
        page = doc.new_page(width=width, height=height)
        page.insert_text((36, 80), str(i), fontsize=48)
    doc.save(str(path))
    doc.close()


def _halves(page):
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


def _spans(page):
    return [
        span
        for block in page.get_text("dict")["blocks"]
        for line in block.get("lines", [])
        for span in line["spans"]
        if span["text"].strip()
    ]


@pytest.mark.parametrize("g", [4, 8, 12, 20, 24, 40])
def test_reading_order_is_sequential(g):
    assert booklet.reading_order(g) == list(range(1, g + 1))


@pytest.mark.parametrize("g", [4, 8, 20])
def test_every_page_used_once(g):
    flat = [p for sheet in booklet.sheets_for(g) for p in sheet]
    assert sorted(flat) == list(range(1, g + 1))


def test_sheets_for_20():
    assert booklet.sheets_for(20) == [
        (20, 1, 2, 19),
        (18, 3, 4, 17),
        (16, 5, 6, 15),
        (14, 7, 8, 13),
        (12, 9, 10, 11),
    ]


def test_sheets_for_rejects_non_multiple_of_four():
    with pytest.raises(ValueError):
        booklet.sheets_for(10)


@pytest.mark.parametrize(("n", "want"), [(0, 4), (1, 4), (4, 4), (5, 8), (8, 8), (9, 12)])
def test_round_up4(n, want):
    assert booklet._round_up4(n) == want


def test_groups_greedy():
    got = [(len(p), pad) for *_, p, pad in booklet.plan_groups(45, 20)]
    assert got == [(20, 20), (20, 20), (5, 8)]


def test_groups_balanced_45():
    groups = booklet.plan_groups(45, 20, balance=True)
    assert [len(p) for *_, p, _ in groups] == [16, 16, 13]
    assert [pad for *_, pad in groups] == [16, 16, 16]


def test_groups_balanced_21():
    groups = booklet.plan_groups(21, 20, balance=True)
    assert [(start, end) for start, end, _, _ in groups] == [(0, 12), (12, 21)]
    assert [pad for *_, pad in groups] == [12, 12]


def test_groups_single():
    groups = booklet.plan_groups(5, 20)
    assert [(start, end, pad) for start, end, _, pad in groups] == [(0, 5, 8)]


@pytest.mark.parametrize("group", [0, -4, 3, 6])
def test_groups_reject_bad_group(group):
    with pytest.raises(ValueError):
        booklet.plan_groups(20, group)


def test_impose_exact_signature(tmp_path):
    src = tmp_path / "n20.pdf"
    _numbered(src, 20)
    doc = pymupdf.open(str(src))
    out = pymupdf.open()
    booklet.impose_into(out, doc, list(range(20)), 20, booklet._sheet_size(612, 792, "half"))
    want = [pair for al, ar, bl, br in booklet.sheets_for(20) for pair in ((al, ar), (bl, br))]
    assert len(out) == 10
    for i, page in enumerate(out):
        left, right = _halves(page)
        assert (left, right) == ([str(want[i][0])], [str(want[i][1])]), (i, left, right)
    out.close()
    doc.close()


def test_padding_leaves_blanks(tmp_path):
    src = tmp_path / "n6.pdf"
    _numbered(src, 6)
    doc = pymupdf.open(str(src))
    out = pymupdf.open()
    booklet.impose_into(out, doc, list(range(6)), 8, booklet._sheet_size(612, 792, "half"))
    assert [_halves(page) for page in out] == [
        ([], ["1"]),
        (["2"], []),
        (["6"], ["3"]),
        (["4"], ["5"]),
    ]
    out.close()
    doc.close()


def test_margin_insets_every_half(tmp_path):
    src = tmp_path / "n8.pdf"
    _numbered(src, 8)
    out_path = tmp_path / "out.pdf"
    booklet.build(str(src), str(out_path), group=8, margin_mm=25.4)

    page = pymupdf.open(str(out_path))[0]
    slot = page.rect.width / 2
    margin = 72.0
    boxes = [
        pymupdf.Rect(margin, margin, slot - margin, page.rect.height - margin),
        pymupdf.Rect(slot + margin, margin, 2 * slot - margin, page.rect.height - margin),
    ]
    spans = _spans(page)
    assert [s["text"].strip() for s in spans] == ["8", "1"]
    for span in spans:
        x0, y0, x1, y1 = span["bbox"]
        box = next(b for b in boxes if b.x0 <= (x0 + x1) / 2 <= b.x1)
        assert box.x0 - 1 <= x0 and x1 <= box.x1 + 1, (span["text"], box)
        assert box.y0 - 1 <= y0 and y1 <= box.y1 + 1, (span["text"], box)


def test_crop_marks_drawn(tmp_path):
    src = tmp_path / "n4.pdf"
    _numbered(src, 4)
    out_path = tmp_path / "out.pdf"
    booklet.build(str(src), str(out_path), group=4, margin_mm=10, crop_marks=True)

    page = pymupdf.open(str(out_path))[0]
    assert len(page.get_drawings()) == 18


def test_crop_marks_need_margin(tmp_path, capsys):
    src = tmp_path / "n4.pdf"
    _numbered(src, 4)
    out_path = tmp_path / "out.pdf"
    booklet.build(str(src), str(out_path), group=4, crop_marks=True)

    assert "skipping the marks" in capsys.readouterr().err
    assert pymupdf.open(str(out_path))[0].get_drawings() == []


def test_split_writes_one_file_per_group(tmp_path):
    src = tmp_path / "n45.pdf"
    _numbered(src, 45)
    booklet.build(str(src), str(tmp_path / "book.pdf"), group=20, split=True)
    assert sorted(p.name for p in tmp_path.glob("book-g*.pdf")) == [
        "book-g1.pdf",
        "book-g2.pdf",
        "book-g3.pdf",
    ]


def test_open_pdf_rejects_garbage(tmp_path):
    bad = tmp_path / "bad.pdf"
    bad.write_bytes(b"not a pdf at all")
    with pytest.raises(SystemExit, match="not a readable PDF"):
        booklet.open_pdf(str(bad))


def test_margin_too_large(tmp_path):
    src = tmp_path / "n4.pdf"
    _numbered(src, 4)
    with pytest.raises(SystemExit, match="leaves no room"):
        booklet.build(str(src), str(tmp_path / "out.pdf"), margin_mm=200)


def test_landscape_source_warns(tmp_path, capsys):
    src = tmp_path / "land.pdf"
    _numbered(src, 4, width=792, height=612)
    booklet.build(str(src), str(tmp_path / "out.pdf"), mode="half")
    assert "landscape" in capsys.readouterr().err


@pytest.mark.parametrize(
    "argv",
    [
        ["x.pdf", "-g", "6"],
        ["x.pdf", "-g", "0"],
        ["x.pdf", "-g", "-4"],
        ["x.pdf", "--margin", "-1"],
    ],
)
def test_cli_rejects_bad_numbers(argv, capsys):
    with pytest.raises(SystemExit) as exc:
        booklet.main(argv)
    assert exc.value.code == 2
    assert "usage:" in capsys.readouterr().err


def test_cli_version(capsys):
    with pytest.raises(SystemExit) as exc:
        booklet.main(["--version"])
    assert exc.value.code == 0
    assert booklet.__version__ in capsys.readouterr().out

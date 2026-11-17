"""Tests for the booklet imposition: ordering, grouping, margins and CLI."""

from __future__ import annotations

from pathlib import Path

import pymupdf
import pytest

import booklet

SAMPLE = Path(__file__).resolve().parent.parent / "examples" / "sample.pdf"


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


def test_page_numbers_drawn(tmp_path):
    src = tmp_path / "n4.pdf"
    _numbered(src, 4)

    plain = tmp_path / "plain.pdf"
    booklet.build(str(src), str(plain), group=4, margin_mm=5)
    page = pymupdf.open(str(plain))[0]
    assert [s for s in _spans(page) if abs(s["size"] - booklet.PAGE_NUMBER_SIZE) < 0.1] == []

    out_path = tmp_path / "out.pdf"
    booklet.build(str(src), str(out_path), group=4, margin_mm=5, page_numbers=True)

    # Sheet 1 side A is the outer face: source page 4 left, page 1 right. A
    # counter numbering the imposed pages instead would print 1 and 2 here.
    page = pymupdf.open(str(out_path))[0]
    slot = page.rect.width / 2
    margin = 5 * booklet.MM
    small = [s for s in _spans(page) if abs(s["size"] - booklet.PAGE_NUMBER_SIZE) < 0.1]
    assert [s["text"].strip() for s in small] == ["4", "1"]
    for i, span in enumerate(small):
        x1, y1 = span["bbox"][2], span["bbox"][3]
        assert abs(x1 - ((i + 1) * slot - 2)) < 3, (span["text"], x1)
        assert y1 <= margin, (span["text"], y1)

    # A padded blank half gets no number: 6 pages at group 8 -> side A is 8|1.
    src6 = tmp_path / "n6.pdf"
    _numbered(src6, 6)
    padded = tmp_path / "padded.pdf"
    booklet.build(str(src6), str(padded), group=8, margin_mm=5, page_numbers=True)
    doc = pymupdf.open(str(padded))
    slot = doc[0].rect.width / 2
    small = [s for s in _spans(doc[0]) if abs(s["size"] - booklet.PAGE_NUMBER_SIZE) < 0.1]
    assert [s["text"].strip() for s in small] == ["1"], small
    assert small[0]["bbox"][0] > slot  # the number belongs to the filled right half


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


def test_sample_pdf_builds(tmp_path):
    assert SAMPLE.is_file(), f"missing sample: {SAMPLE}"
    out = tmp_path / "sample-booklet.pdf"
    booklet.build(str(SAMPLE), str(out), group=8)

    doc = pymupdf.open(str(out))
    assert len(doc) == 4
    left, right = _halves(doc[0])
    assert (left[0], right[0]) == ("8", "1"), (left, right)
    doc.close()


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


def test_folder_converts_every_pdf(tmp_path):
    _numbered(tmp_path / "a.pdf", 4)
    _numbered(tmp_path / "b.pdf", 4)
    assert booklet.main([str(tmp_path)]) == 0
    assert (tmp_path / "a-booklet.pdf").is_file()
    assert (tmp_path / "b-booklet.pdf").is_file()
    assert (tmp_path / "a.pdf").is_file()


def test_folder_passes_page_numbers(tmp_path):
    _numbered(tmp_path / "a.pdf", 4)
    _numbered(tmp_path / "b.pdf", 4)
    assert booklet.main([str(tmp_path), "--page-numbers"]) == 0
    for name in ("a-booklet.pdf", "b-booklet.pdf"):
        page = pymupdf.open(str(tmp_path / name))[0]
        sizes = [round(s["size"], 1) for s in _spans(page)]
        assert sizes.count(float(booklet.PAGE_NUMBER_SIZE)) == 2, (name, sizes)


def test_folder_skips_generated_files(tmp_path):
    _numbered(tmp_path / "a.pdf", 4)
    # Garbage with output names: converting either would fail, so a clean exit
    # proves they were skipped instead of nested one level deeper.
    (tmp_path / "a-booklet.pdf").write_bytes(b"previous run")
    (tmp_path / "a-booklet-g1.pdf").write_bytes(b"previous split")

    assert booklet.main([str(tmp_path)]) == 0
    assert not (tmp_path / "a-booklet-booklet.pdf").exists()
    assert pymupdf.open(str(tmp_path / "a-booklet.pdf")).page_count == 2


def test_folder_custom_suffix(tmp_path):
    _numbered(tmp_path / "a.pdf", 4)
    assert booklet.main([str(tmp_path), "--suffix", "_b"]) == 0
    assert (tmp_path / "a_b.pdf").is_file()


def test_folder_rejects_out(tmp_path):
    with pytest.raises(SystemExit, match="single file"):
        booklet.main([str(tmp_path), "-o", "x.pdf"])


def test_folder_out_dir_created_and_filled(tmp_path):
    src = tmp_path / "src"
    src.mkdir()
    _numbered(src / "a.pdf", 4)
    _numbered(src / "b.pdf", 4)
    dest = tmp_path / "out" / "nested"

    assert booklet.main([str(src), "--out-dir", str(dest)]) == 0
    assert (dest / "a-booklet.pdf").is_file()
    assert (dest / "b-booklet.pdf").is_file()
    assert not (src / "a-booklet.pdf").exists()


def test_folder_split_out_dir(tmp_path):
    src = tmp_path / "src"
    src.mkdir()
    _numbered(src / "a.pdf", 4)

    assert booklet.main([str(src), "--split", "--out-dir", str(tmp_path / "out")]) == 0
    assert (tmp_path / "out" / "a-booklet-g1.pdf").is_file()


def test_single_file_out_dir(tmp_path):
    _numbered(tmp_path / "a.pdf", 4)
    dest = tmp_path / "out"

    assert booklet.main([str(tmp_path / "a.pdf"), "--out-dir", str(dest)]) == 0
    assert (dest / "a-booklet.pdf").is_file()
    assert not (tmp_path / "a-booklet.pdf").exists()


def test_out_wins_over_out_dir(tmp_path):
    _numbered(tmp_path / "a.pdf", 4)
    dest = tmp_path / "out"
    argv = [str(tmp_path / "a.pdf"), "-o", str(tmp_path / "x.pdf"), "--out-dir", str(dest)]

    assert booklet.main(argv) == 0
    assert (tmp_path / "x.pdf").is_file()
    assert not dest.exists()


def test_out_dir_that_is_a_file(tmp_path):
    src = tmp_path / "src"
    src.mkdir()
    _numbered(src / "a.pdf", 4)
    blocker = tmp_path / "blocker"
    blocker.write_text("not a folder")

    with pytest.raises(SystemExit, match="cannot create"):
        booklet.main([str(src), "--out-dir", str(blocker)])


def test_folder_without_pdfs(tmp_path):
    (tmp_path / "notes.txt").write_text("hi")
    with pytest.raises(SystemExit, match="no PDFs"):
        booklet.main([str(tmp_path)])


def test_folder_continues_after_a_bad_file(tmp_path, capsys):
    _numbered(tmp_path / "good.pdf", 4)
    (tmp_path / "bad.pdf").write_bytes(b"not a pdf")

    with pytest.raises(SystemExit, match="1 of 2"):
        booklet.main([str(tmp_path)])

    assert (tmp_path / "good-booklet.pdf").is_file()
    assert "not a readable PDF" in capsys.readouterr().err

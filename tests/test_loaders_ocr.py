"""Tests for the OCR loader module (ingestion/loaders_ocr.py).

Strategy:
    - ``is_scanned_pdf`` is tested against real PDFs in data/ (text-based
      PDFs return False; scanned PDFs return True).
    - ``OcrPage`` value object tests are pure (no I/O, no mocking).
    - ``_load_from_cache`` / ``_save_to_cache`` are tested with a tmp_path fixture.
    - ``load_scanned_pdf_pages`` is tested with mocked Vision API and pdf2image
      to avoid real API calls and poppler dependency in CI.
    - ``ocr_pages_to_loaded_pages`` is a pure conversion tested directly.
    - ``load_pdf_auto`` routing logic is tested with mocks.
"""

from __future__ import annotations

import pathlib
from unittest.mock import MagicMock, patch

import pytest

from ingestion.loaders_ocr import (
    OcrPage,
    _cache_key,
    _load_from_cache,
    _save_to_cache,
    is_scanned_pdf,
    ocr_pages_to_loaded_pages,
)

# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------

# Path to a text-based PDF we know exists in data/
_TEXT_PDF = pathlib.Path("data/music/books/daw/live12-manual-en.pdf")
# Path to a known scanned PDF
_SCANNED_PDF = pathlib.Path("data/music/books/_scanned/Bob_Katz.pdf")


# ---------------------------------------------------------------------------
# OcrPage value object
# ---------------------------------------------------------------------------


class TestOcrPage:
    """Tests for the OcrPage frozen dataclass."""

    def test_basic_construction(self) -> None:
        """OcrPage can be constructed with page_number and text."""
        page = OcrPage(page_number=1, text="Hello, world!")
        assert page.page_number == 1
        assert page.text == "Hello, world!"
        assert page.source == "google_vision"  # default

    def test_cache_source(self) -> None:
        """OcrPage with cache source."""
        page = OcrPage(page_number=5, text="Cached text", source="cache")
        assert page.source == "cache"

    def test_immutable(self) -> None:
        """OcrPage is frozen — cannot mutate."""
        page = OcrPage(page_number=1, text="text")
        with pytest.raises((AttributeError, TypeError)):
            page.text = "other"  # type: ignore[misc]

    def test_equality(self) -> None:
        """Two OcrPages with same values are equal."""
        a = OcrPage(page_number=1, text="hello")
        b = OcrPage(page_number=1, text="hello")
        assert a == b

    def test_inequality_different_page(self) -> None:
        """Different page numbers → not equal."""
        a = OcrPage(page_number=1, text="hello")
        b = OcrPage(page_number=2, text="hello")
        assert a != b

    def test_empty_text_allowed(self) -> None:
        """Empty text is allowed (OCR may find nothing)."""
        page = OcrPage(page_number=1, text="")
        assert page.text == ""


# ---------------------------------------------------------------------------
# Cache helpers
# ---------------------------------------------------------------------------


class TestCacheHelpers:
    """Tests for OCR cache read/write helpers."""

    def test_cache_key_is_deterministic(self, tmp_path: pathlib.Path) -> None:
        """Same path + page → same key."""
        pdf = tmp_path / "book.pdf"
        key1 = _cache_key(pdf, 1)
        key2 = _cache_key(pdf, 1)
        assert key1 == key2

    def test_cache_key_differs_by_page(self, tmp_path: pathlib.Path) -> None:
        """Different pages → different keys."""
        pdf = tmp_path / "book.pdf"
        key1 = _cache_key(pdf, 1)
        key2 = _cache_key(pdf, 2)
        assert key1 != key2

    def test_cache_key_differs_by_path(self, tmp_path: pathlib.Path) -> None:
        """Different file paths → different keys."""
        key1 = _cache_key(tmp_path / "a.pdf", 1)
        key2 = _cache_key(tmp_path / "b.pdf", 1)
        assert key1 != key2

    def test_cache_key_length(self, tmp_path: pathlib.Path) -> None:
        """Cache key is 16 hex characters (truncated SHA-256)."""
        key = _cache_key(tmp_path / "book.pdf", 1)
        assert len(key) == 16
        assert all(c in "0123456789abcdef" for c in key)

    def test_save_and_load_roundtrip(self, tmp_path: pathlib.Path) -> None:
        """Save cache then load → same text returned."""
        pdf = tmp_path / "book.pdf"
        pdf.write_bytes(b"%PDF-1.4 fake")  # file must exist for cache key
        _save_to_cache(pdf, 1, "Extracted text from page 1")
        result = _load_from_cache(pdf, 1)
        assert result == "Extracted text from page 1"

    def test_load_missing_cache_returns_none(self, tmp_path: pathlib.Path) -> None:
        """Load non-existent cache entry → None."""
        pdf = tmp_path / "missing.pdf"
        result = _load_from_cache(pdf, 99)
        assert result is None

    def test_save_creates_cache_dir(self, tmp_path: pathlib.Path) -> None:
        """_save_to_cache creates .ocr_cache directory automatically."""
        pdf = tmp_path / "book.pdf"
        pdf.write_bytes(b"%PDF-1.4 fake")
        _save_to_cache(pdf, 1, "text")
        cache_dir = tmp_path / ".ocr_cache"
        assert cache_dir.is_dir()

    def test_save_empty_text(self, tmp_path: pathlib.Path) -> None:
        """Can cache empty string (page with no text)."""
        pdf = tmp_path / "book.pdf"
        pdf.write_bytes(b"%PDF-1.4 fake")
        _save_to_cache(pdf, 3, "")
        result = _load_from_cache(pdf, 3)
        assert result == ""

    def test_save_overwrite(self, tmp_path: pathlib.Path) -> None:
        """Second save overwrites first."""
        pdf = tmp_path / "book.pdf"
        pdf.write_bytes(b"%PDF-1.4 fake")
        _save_to_cache(pdf, 1, "original")
        _save_to_cache(pdf, 1, "updated")
        result = _load_from_cache(pdf, 1)
        assert result == "updated"

    def test_corrupted_cache_returns_none(self, tmp_path: pathlib.Path) -> None:
        """Corrupted cache file → None (graceful degradation)."""
        pdf = tmp_path / "book.pdf"
        pdf.write_bytes(b"%PDF-1.4 fake")
        cache_dir = tmp_path / ".ocr_cache"
        cache_dir.mkdir()
        key = _cache_key(pdf, 1)
        cache_file = cache_dir / f"{key}.json"
        cache_file.write_text("not valid json {{{{", encoding="utf-8")
        result = _load_from_cache(pdf, 1)
        assert result is None


# ---------------------------------------------------------------------------
# is_scanned_pdf — integration test (uses real PDFs)
# ---------------------------------------------------------------------------


@pytest.mark.skipif(
    not _TEXT_PDF.exists(),
    reason="Ableton Live 12 manual not in data/ — skipping integration test",
)
class TestIsScannedPdfWithRealFiles:
    """Integration tests using real PDFs from the data/ folder."""

    def test_text_pdf_returns_false(self) -> None:
        """Ableton Live manual has embedded text → is_scanned_pdf returns False."""
        assert is_scanned_pdf(_TEXT_PDF) is False

    @pytest.mark.skipif(
        not _SCANNED_PDF.exists(),
        reason="Bob Katz scanned PDF not in data/ — skipping",
    )
    def test_scanned_pdf_returns_true(self) -> None:
        """Bob Katz scanned PDF → is_scanned_pdf returns True."""
        assert is_scanned_pdf(_SCANNED_PDF) is True


class TestIsScannedPdfErrors:
    """Error handling in is_scanned_pdf."""

    def test_missing_file_raises(self, tmp_path: pathlib.Path) -> None:
        """Non-existent file raises FileNotFoundError."""
        with pytest.raises(FileNotFoundError):
            is_scanned_pdf(tmp_path / "nope.pdf")

    def test_non_pdf_raises(self, tmp_path: pathlib.Path) -> None:
        """Non-PDF extension raises ValueError."""
        txt = tmp_path / "file.txt"
        txt.write_text("hello")
        with pytest.raises(ValueError, match=".txt"):
            is_scanned_pdf(txt)


# ---------------------------------------------------------------------------
# ocr_pages_to_loaded_pages — pure conversion
# ---------------------------------------------------------------------------


class TestOcrPagesToLoadedPages:
    """Tests for the OcrPage → LoadedPage converter."""

    def test_empty_list(self) -> None:
        """Empty input returns empty list."""
        result = ocr_pages_to_loaded_pages([])
        assert result == []

    def test_single_page_conversion(self) -> None:
        """Single OcrPage converts to single LoadedPage."""
        from ingestion.loaders import LoadedPage

        ocr = [OcrPage(page_number=3, text="Synthesis chapter")]
        result = ocr_pages_to_loaded_pages(ocr)
        assert len(result) == 1
        assert isinstance(result[0], LoadedPage)
        assert result[0].page_number == 3
        assert result[0].text == "Synthesis chapter"

    def test_multiple_pages_preserve_order(self) -> None:
        """Page order is preserved in conversion."""
        ocr = [
            OcrPage(page_number=1, text="First"),
            OcrPage(page_number=2, text="Second"),
            OcrPage(page_number=5, text="Fifth"),
        ]
        result = ocr_pages_to_loaded_pages(ocr)
        assert [r.page_number for r in result] == [1, 2, 5]
        assert [r.text for r in result] == ["First", "Second", "Fifth"]

    def test_page_text_preserved_exactly(self) -> None:
        """Multiline text is preserved exactly."""
        text = "Line 1\nLine 2\n\nParagraph 2"
        ocr = [OcrPage(page_number=1, text=text)]
        result = ocr_pages_to_loaded_pages(ocr)
        assert result[0].text == text


# ---------------------------------------------------------------------------
# load_scanned_pdf_pages — mocked Vision API + pdf2image
# ---------------------------------------------------------------------------


class TestLoadScannedPdfPagesMocked:
    """Tests for load_scanned_pdf_pages with mocked dependencies."""

    def _make_fake_pdf(self, tmp_path: pathlib.Path, n_pages: int = 3) -> pathlib.Path:
        """Create a minimal real PDF for pdfplumber to open (page count detection)."""
        # We need a real PDF that pdfplumber can open for page count.
        # Use one of the real text PDFs for page count detection.
        # Alternatively, create a minimal synthetic one.
        # Since Ableton PDF exists, we'll patch pdfplumber.open instead.
        pdf = tmp_path / "scanned.pdf"
        pdf.write_bytes(b"%PDF-1.4")  # minimal content
        return pdf

    @patch("ingestion.loaders_ocr.pdfplumber.open")
    @patch("ingestion.loaders_ocr._ocr_image_bytes_vision")
    @patch("ingestion.loaders_ocr.convert_from_path")
    def test_basic_ocr_flow(
        self,
        mock_convert: MagicMock,
        mock_ocr: MagicMock,
        mock_plumber: MagicMock,
        tmp_path: pathlib.Path,
    ) -> None:
        """load_scanned_pdf_pages calls Vision API and returns OcrPage list."""
        from ingestion.loaders_ocr import load_scanned_pdf_pages

        # Setup fake PDF context manager
        mock_pdf_ctx = MagicMock()
        mock_pdf_ctx.__enter__ = MagicMock(return_value=mock_pdf_ctx)
        mock_pdf_ctx.__exit__ = MagicMock(return_value=False)
        mock_pdf_ctx.pages = [MagicMock(), MagicMock()]
        mock_plumber.return_value = mock_pdf_ctx

        # pdf2image returns a fake PIL image
        fake_img = MagicMock()
        fake_img.save = MagicMock()
        mock_convert.return_value = [fake_img]

        # Vision API returns text
        mock_ocr.return_value = "Extracted text from OCR"

        pdf = tmp_path / "scanned.pdf"
        pdf.write_bytes(b"%PDF-1.4")

        pages = load_scanned_pdf_pages(pdf, use_cache=False)

        assert len(pages) == 2
        assert all(p.text == "Extracted text from OCR" for p in pages)
        assert all(p.source == "google_vision" for p in pages)
        assert mock_ocr.call_count == 2  # called once per page

    @patch("ingestion.loaders_ocr.pdfplumber.open")
    @patch("ingestion.loaders_ocr._ocr_image_bytes_vision")
    @patch("ingestion.loaders_ocr.convert_from_path")
    def test_cache_hit_skips_vision_api(
        self,
        mock_convert: MagicMock,
        mock_ocr: MagicMock,
        mock_plumber: MagicMock,
        tmp_path: pathlib.Path,
    ) -> None:
        """Cached pages skip Vision API call entirely."""
        from ingestion.loaders_ocr import load_scanned_pdf_pages

        mock_pdf_ctx = MagicMock()
        mock_pdf_ctx.__enter__ = MagicMock(return_value=mock_pdf_ctx)
        mock_pdf_ctx.__exit__ = MagicMock(return_value=False)
        mock_pdf_ctx.pages = [MagicMock()]
        mock_plumber.return_value = mock_pdf_ctx

        pdf = tmp_path / "cached.pdf"
        pdf.write_bytes(b"%PDF-1.4")

        # Pre-populate cache for page 1
        _save_to_cache(pdf, 1, "Pre-cached text")

        pages = load_scanned_pdf_pages(pdf, use_cache=True)

        mock_ocr.assert_not_called()  # Vision API not called
        mock_convert.assert_not_called()  # No PDF→image conversion
        assert len(pages) == 1
        assert pages[0].text == "Pre-cached text"
        assert pages[0].source == "cache"

    @patch("ingestion.loaders_ocr.pdfplumber.open")
    @patch("ingestion.loaders_ocr._ocr_image_bytes_vision")
    @patch("ingestion.loaders_ocr.convert_from_path")
    def test_empty_ocr_pages_skipped(
        self,
        mock_convert: MagicMock,
        mock_ocr: MagicMock,
        mock_plumber: MagicMock,
        tmp_path: pathlib.Path,
    ) -> None:
        """Pages with empty OCR text are not included in results."""
        from ingestion.loaders_ocr import load_scanned_pdf_pages

        mock_pdf_ctx = MagicMock()
        mock_pdf_ctx.__enter__ = MagicMock(return_value=mock_pdf_ctx)
        mock_pdf_ctx.__exit__ = MagicMock(return_value=False)
        mock_pdf_ctx.pages = [MagicMock(), MagicMock()]
        mock_plumber.return_value = mock_pdf_ctx

        fake_img = MagicMock()
        fake_img.save = MagicMock()
        mock_convert.return_value = [fake_img]

        # First page has text, second is empty
        mock_ocr.side_effect = ["Page 1 text", ""]

        pdf = tmp_path / "partial.pdf"
        pdf.write_bytes(b"%PDF-1.4")

        pages = load_scanned_pdf_pages(pdf, use_cache=False)

        assert len(pages) == 1
        assert pages[0].page_number == 1
        assert pages[0].text == "Page 1 text"

    @patch("ingestion.loaders_ocr.pdfplumber.open")
    def test_missing_file_raises(
        self,
        mock_plumber: MagicMock,
        tmp_path: pathlib.Path,
    ) -> None:
        """Non-existent PDF raises FileNotFoundError."""
        from ingestion.loaders_ocr import load_scanned_pdf_pages

        with pytest.raises(FileNotFoundError):
            load_scanned_pdf_pages(tmp_path / "nope.pdf")

    @patch("ingestion.loaders_ocr.pdfplumber.open")
    def test_non_pdf_raises(
        self,
        mock_plumber: MagicMock,
        tmp_path: pathlib.Path,
    ) -> None:
        """Non-PDF extension raises ValueError."""
        from ingestion.loaders_ocr import load_scanned_pdf_pages

        txt = tmp_path / "file.txt"
        txt.write_text("hello")
        with pytest.raises(ValueError, match=".txt"):
            load_scanned_pdf_pages(txt)

    @patch("ingestion.loaders_ocr.pdfplumber.open")
    @patch("ingestion.loaders_ocr._ocr_image_bytes_vision")
    @patch("ingestion.loaders_ocr.convert_from_path")
    def test_page_range_respected(
        self,
        mock_convert: MagicMock,
        mock_ocr: MagicMock,
        mock_plumber: MagicMock,
        tmp_path: pathlib.Path,
    ) -> None:
        """start_page and end_page limit processing range."""
        from ingestion.loaders_ocr import load_scanned_pdf_pages

        mock_pdf_ctx = MagicMock()
        mock_pdf_ctx.__enter__ = MagicMock(return_value=mock_pdf_ctx)
        mock_pdf_ctx.__exit__ = MagicMock(return_value=False)
        mock_pdf_ctx.pages = [MagicMock()] * 10  # 10 page PDF
        mock_plumber.return_value = mock_pdf_ctx

        fake_img = MagicMock()
        fake_img.save = MagicMock()
        mock_convert.return_value = [fake_img]
        mock_ocr.return_value = "text"

        pdf = tmp_path / "big.pdf"
        pdf.write_bytes(b"%PDF-1.4")

        # Request only pages 3–5
        pages = load_scanned_pdf_pages(pdf, start_page=3, end_page=5, use_cache=False)

        assert mock_ocr.call_count == 3  # only 3 pages processed
        assert {p.page_number for p in pages} == {3, 4, 5}


# ---------------------------------------------------------------------------
# load_pdf_auto routing
# ---------------------------------------------------------------------------


class TestLoadPdfAuto:
    """Tests for the auto-routing load_pdf_auto function."""

    @patch("ingestion.loaders_ocr.is_scanned_pdf", return_value=False)
    @patch("ingestion.loaders_ocr.load_pdf_pages")
    def test_text_pdf_uses_pdfplumber(
        self,
        mock_load_pages: MagicMock,
        mock_is_scanned: MagicMock,
        tmp_path: pathlib.Path,
    ) -> None:
        """Text PDF routes to standard pdfplumber loader."""
        from ingestion.loaders_ocr import load_pdf_auto

        mock_load_pages.return_value = []
        pdf = tmp_path / "text.pdf"
        pdf.write_bytes(b"%PDF-1.4")

        load_pdf_auto(pdf)

        mock_load_pages.assert_called_once_with(pdf)

    @patch("ingestion.loaders_ocr.is_scanned_pdf", return_value=True)
    @patch("ingestion.loaders_ocr.load_scanned_pdf_pages")
    @patch("ingestion.loaders_ocr.ocr_pages_to_loaded_pages")
    def test_scanned_pdf_uses_ocr(
        self,
        mock_convert: MagicMock,
        mock_load_scanned: MagicMock,
        mock_is_scanned: MagicMock,
        tmp_path: pathlib.Path,
    ) -> None:
        """Scanned PDF routes to OCR loader."""
        from ingestion.loaders_ocr import load_pdf_auto

        mock_load_scanned.return_value = []
        mock_convert.return_value = []
        pdf = tmp_path / "scanned.pdf"
        pdf.write_bytes(b"%PDF-1.4")

        load_pdf_auto(pdf)

        mock_load_scanned.assert_called_once()
        mock_convert.assert_called_once()

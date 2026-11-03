"""OCR reading order, confidence, and local failures without loading models."""

from types import SimpleNamespace

import pytest

from app.core.errors import AppError
from app.services.ocr_service import LocalOCR
from conftest import png_bytes


def test_local_ocr_returns_boxes_and_low_confidence_warning(settings):
    engine = LocalOCR(settings)
    engine._engine = lambda image: SimpleNamespace(
        txts=["second", "right", "first"], scores=[0.95, 0.6, 0.98],
        boxes=[[[10, 50], [80, 50], [80, 65], [10, 65]],
               [[100, 10], [180, 10], [180, 25], [100, 25]],
               [[10, 10], [80, 10], [80, 25], [10, 25]]],
    )
    result, warnings = engine.recognize(png_bytes(), 1)
    assert result.method == "local_ocr"
    assert result.text == "first  right\nsecond"
    assert len(result.lines) == 3
    assert any("1" in warning for warning in warnings)
    assert result.width and result.height


def test_empty_local_ocr_is_explicit_error(settings):
    engine = LocalOCR(settings)
    engine._engine = lambda image: SimpleNamespace(txts=None)
    with pytest.raises(AppError, match="DOCUMENT_TEXT_EMPTY"):
        engine.recognize(png_bytes(), 1)

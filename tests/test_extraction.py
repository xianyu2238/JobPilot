"""Evidence rejection, bounded retries, file limits, and vision errors."""

from io import BytesIO
import json
import time

import httpx
from PIL import Image
import pymupdf
import pytest

from app.core.errors import AppError
from app.core.llm import ModelClient
from app.repositories.memory import MemoryRepository
from app.schemas.business import Recognition
from app.services.document_service import DocumentService
from app.services.resume_service import ResumeService
from conftest import fake_completion, pdf_bytes, png_bytes


def completion(value):
    return httpx.Response(200, json={"choices": [{"message": {"content": json.dumps(value)}}]})


def test_fabricated_evidence_rejected(settings):
    calls = []
    def handler(request):
        calls.append(request)
        return completion({"skills": [{"name": "Python", "level": "applied", "source_ids": ["invented-source"]}]})
    model = ModelClient(settings, httpx.MockTransport(handler))
    store = MemoryRepository()
    with pytest.raises(AppError) as error:
        ResumeService(settings, model, store).parse(pdf_bytes(), "resume.pdf")
    assert error.value.code == "RESUME_EVIDENCE_INVALID"
    assert len(calls) == 1
    assert len(store._items) == 1
    saved = next(iter(store._items.values()))[1].response
    assert saved.parse_status == "text_ready"
    assert saved.pages


def test_invalid_json_repaired_once(settings):
    calls = []
    def handler(request):
        calls.append(request)
        return completion({"wrong": True} if len(calls) == 1 else {"text": "recognized text"})
    result = ModelClient(settings, httpx.MockTransport(handler)).extract(Recognition, "transcribe", "text")
    assert result.text == "recognized text"
    assert len(calls) == 2


@pytest.mark.parametrize("failure,code", [("timeout", "LLM_TIMEOUT"), ("network", "LLM_UPSTREAM_ERROR"), ("auth", "LLM_UPSTREAM_ERROR")])
def test_upstream_failures_bounded(settings, failure, code):
    calls = []
    def handler(request):
        calls.append(request)
        if failure == "timeout":
            raise httpx.ReadTimeout("test")
        if failure == "network":
            raise httpx.ConnectError("test")
        return httpx.Response(401, text="private upstream data")
    with pytest.raises(AppError) as error:
        ModelClient(settings, httpx.MockTransport(handler)).extract(Recognition, "transcribe", "text")
    assert error.value.code == code
    assert len(calls) <= 2
    assert "private" not in error.value.message


def test_limits_and_encrypted_pdf(settings):
    service = DocumentService(settings, ModelClient(settings, httpx.MockTransport(fake_completion)))
    deadline = time.monotonic() + 30
    with pytest.raises(AppError, match="FILE_TOO_LARGE"):
        service.extract(b"x" * (settings.max_file_mb * 1024 * 1024 + 1), "resume.pdf", deadline)
    with pymupdf.open() as document:
        for _ in range(settings.max_pdf_pages + 1):
            document.new_page()
        too_many = document.tobytes()
        encrypted = document.tobytes(encryption=pymupdf.PDF_ENCRYPT_AES_256, user_pw="secret", owner_pw="owner")
    with pytest.raises(AppError, match="PDF_TOO_MANY_PAGES"):
        service.extract(too_many, "resume.pdf", deadline)
    with pytest.raises(AppError, match="PDF_ENCRYPTED"):
        service.extract(encrypted, "resume.pdf", deadline)
    settings.max_image_pixels = 1000
    with pytest.raises(AppError, match="IMAGE_TOO_LARGE"):
        service.extract(png_bytes(), "resume.png", deadline)


def test_vision_model_required(settings):
    settings.vision_model = ""
    service = DocumentService(settings, ModelClient(settings))
    with pytest.raises(AppError, match="LLM_NOT_CONFIGURED"):
        service.extract(png_bytes(), "resume.png", time.monotonic() + 30, recognition_mode="vision")


def test_transparent_png_has_white_background(settings):
    buffer = BytesIO()
    Image.new("RGBA", (50, 50), (0, 0, 0, 0)).save(buffer, "PNG")
    result = DocumentService(settings, ModelClient(settings))._image(buffer.getvalue())
    with Image.open(BytesIO(result)) as image:
        assert image.getpixel((0, 0)) == (255, 255, 255)


def test_jpeg_orientation_is_applied_before_preview_and_recognition(settings):
    buffer = BytesIO()
    image = Image.new("RGB", (80, 40), "white")
    exif = Image.Exif()
    exif[274] = 6
    image.save(buffer, "JPEG", exif=exif)
    result = DocumentService(settings, ModelClient(settings))._image(buffer.getvalue(), expected_format="JPEG")
    with Image.open(BytesIO(result)) as normalized:
        assert normalized.format == "PNG"
        assert normalized.size == (40, 80)


def test_qwen_extraction_disables_thinking(settings):
    settings.llm_model = "qwen3.8-flash"
    def handler(request):
        body = json.loads(request.content)
        assert body["enable_thinking"] is False
        assert body["stream"] is False
        assert request.extensions["timeout"]["connect"] <= 10
        return completion({"text": "recognized text"})
    ModelClient(settings, httpx.MockTransport(handler)).extract(Recognition, "extract", "text")


def test_non_qwen_models_do_not_receive_vendor_parameter(settings):
    def handler(request):
        assert "enable_thinking" not in json.loads(request.content)
        return completion({"text": "recognized text"})
    ModelClient(settings, httpx.MockTransport(handler)).extract(Recognition, "extract", "text")


def test_bad_skill_does_not_retry_entire_grounded_resume(settings):
    calls = []
    def handler(request):
        calls.append(request)
        body = json.loads(request.content)
        sources = json.loads(body["messages"][1]["content"])["sources"]
        source = next(item for item in sources if "Built an API" in item["text"])
        return completion({
            "projects": [{"title": "API", "description": "API project", "source_ids": [source["id"]]}],
            "skills": [
                {"name": "Python", "level": "applied", "source_ids": [source["id"]]},
                {"name": "Redis", "level": "applied", "source_ids": [source["id"]]},
            ],
        })
    model = ModelClient(settings, httpx.MockTransport(handler))
    response = ResumeService(settings, model, MemoryRepository()).parse(pdf_bytes(), "resume.pdf")
    assert len(calls) == 1
    assert [item.name for item in response.parsed_data.skills] == ["Python"]
    assert response.parsed_data.projects
    assert response.warnings
    assert response.confirmed is False
    assert "Built an API" in response.parsed_data.skills[0].evidence[0].quote


def test_truncated_output_does_not_repeat_same_generation(settings):
    calls = []
    def handler(request):
        calls.append(request)
        return httpx.Response(200, json={"choices": [{"finish_reason": "length", "message": {"content": '{"text":'}}]})
    with pytest.raises(AppError, match="LLM_OUTPUT_TRUNCATED"):
        ModelClient(settings, httpx.MockTransport(handler)).extract(Recognition, "extract", "text")
    assert len(calls) == 1


def test_schema_diagnostics_exclude_private_values(settings, caplog):
    marker = "private-resume-content-marker"
    def handler(request):
        return completion({"text": {"private": marker}, "unexpected": marker})
    with pytest.raises(AppError):
        ModelClient(settings, httpx.MockTransport(handler)).extract(Recognition, "extract", "text")
    assert marker not in caplog.text
    assert "details=" in caplog.text


def test_read_timeout_does_not_automatically_repeat_slow_request(settings):
    calls = []
    def handler(request):
        calls.append(request)
        raise httpx.ReadTimeout("test")
    with pytest.raises(AppError, match="LLM_TIMEOUT"):
        ModelClient(settings, httpx.MockTransport(handler)).extract(Recognition, "extract", "text")
    assert len(calls) == 1

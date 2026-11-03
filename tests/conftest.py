"""Synthetic fixtures and an HTTP-level model stub; no real credentials."""

from io import BytesIO
import json

import httpx
from PIL import Image
import pymupdf
import pytest
from fastapi.testclient import TestClient

from app.core.config import Settings
from app.core.llm import ModelClient
from app.main import create_app
from app.schemas.business import OCRLine, PageText

TEXT = "Candidate Example\nSkills: Python, FastAPI\nProject: Built an API using Python and FastAPI.\nEducation: Bachelor of Computer Science."
JD = "Python backend intern. Must have Python development experience. Redis experience is preferred. MySQL or PostgreSQL, at least one."
RESUME = {
    "personal_info": {"name": "Candidate Example"}, "education": [], "experiences": [],
    "projects": [{"title": "API", "description": "Built an API using Python and FastAPI.",
                  "evidence": [{"page": 1, "quote": "Built an API using Python and FastAPI."}]}],
    "skills": [{"name": name, "level": "applied", "evidence": [{"page": 1, "quote": "Built an API using Python and FastAPI."}]} for name in ["Python", "FastAPI"]],
    "warnings": [],
}


def pdf_bytes(text: str = TEXT, scan: bool = False) -> bytes:
    with pymupdf.open() as document:
        page = document.new_page()
        page.insert_text((50, 50), text, fontsize=11)
        if not scan:
            return document.tobytes()
        image = page.get_pixmap().tobytes("png")
    with pymupdf.open() as document:
        page = document.new_page()
        page.insert_image(page.rect, stream=image)
        return document.tobytes()


def png_bytes() -> bytes:
    with pymupdf.open(stream=pdf_bytes(), filetype="pdf") as document:
        return document[0].get_pixmap().tobytes("png")


def jpeg_bytes() -> bytes:
    buffer = BytesIO()
    with Image.open(BytesIO(png_bytes())) as image:
        image.convert("RGB").save(buffer, format="JPEG")
    return buffer.getvalue()


def fake_completion(request: httpx.Request) -> httpx.Response:
    body = json.loads(request.content)
    system = body["messages"][0]["content"]
    if '"title": "ResumeDraft"' in system:
        sources = json.loads(body["messages"][1]["content"])["sources"]
        project_source = next(item["id"] for item in sources if "Built an API" in item["text"])
        result = {
            "personal_info": RESUME["personal_info"],
            "projects": [{"title": "API", "description": "Built an API using Python and FastAPI.", "source_ids": [project_source]}],
            "skills": [{"name": skill["name"], "level": "applied", "source_ids": [project_source]} for skill in RESUME["skills"]],
        }
    elif '"title": "MatchDraft"' in system:
        data = json.loads(body["messages"][1]["content"])
        result = {
            "overview": "简历具备 Python 项目依据，建议核对并补充岗位相关经历。",
            "resume_suggestions": [{"priority": "高", "target": "项目描述", "reason": "已有 Python 证据，可补充本人职责。",
                                    "action": "说明实际承担的接口工作，不编造指标。", "source_ids": [data["sources"][0]["id"]] if data["sources"] else [], "jd_quote": "Python"}],
            "learning_suggestions": [{"priority": "低", "topic": "Redis", "task": "若尚未掌握，可实现一个带过期时间的缓存练习。",
                                      "deliverable": "可运行示例与测试", "jd_quote": "Redis experience is preferred."}],
            "warnings": [],
        }
    else:
        assert body["messages"][1]["content"][1]["image_url"]["url"].startswith("data:image/png;base64,")
        result = {"text": TEXT, "warnings": []}
    return httpx.Response(200, json={"choices": [{"message": {"content": json.dumps(result)}}]})


@pytest.fixture
def settings():
    return Settings(_env_file=None, environment="test", llm_base_url="https://model.example/v1",
                    llm_api_key="fake-test-key", llm_model="test-text", vision_model="test-vision")


@pytest.fixture
def application(settings):
    application = create_app(settings)
    application.state.model = ModelClient(settings, transport=httpx.MockTransport(fake_completion))
    application.state.ocr = FakeOCR()
    return application


@pytest.fixture
def client(application):
    with TestClient(application) as client:
        yield client


class FakeOCR:
    def __init__(self):
        self.calls = 0

    def recognize(self, image, page):
        self.calls += 1
        lines = [OCRLine(text=line, confidence=0.95, box=[[10, index * 20], [500, index * 20], [500, index * 20 + 15], [10, index * 20 + 15]])
                 for index, line in enumerate(TEXT.splitlines())]
        return PageText(page=page, text=TEXT, method="local_ocr", lines=lines, width=600, height=800), []

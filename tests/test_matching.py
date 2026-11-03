"""Direct-JD advice, evidence validation, and temporary resume storage."""

import json
import time

import httpx
import pytest

from app.core.errors import AppError
from app.core.llm import ModelClient
from app.core.skill_aliases import contains_skill
from app.repositories.memory import MemoryRepository, ResumeRecord
from app.schemas.business import PageText, ParsedResume, ResumeResponse
from app.services.match_service import MatchService
from conftest import JD, RESUME, TEXT, fake_completion


def resume_record():
    return ResumeRecord(ResumeResponse(resume_id="", filename="resume.pdf", parsed_data=ParsedResume.model_validate(RESUME),
                        pages=[PageText(page=1, text=TEXT, method="pdf_text")], warnings=[], confirmed=True), [])


def test_direct_jd_analysis_uses_one_call_and_no_job_record(settings):
    store = MemoryRepository()
    record = resume_record()
    store.add("resume", record)
    calls = []
    def handler(request):
        calls.append(request)
        return fake_completion(request)
    result = MatchService(store, ModelClient(settings, httpx.MockTransport(handler))).analyze(record.response.resume_id, JD)
    assert len(calls) == 1
    assert len(store._items) == 1
    assert result.resume_suggestions[0].original_quote
    assert result.learning_suggestions[0].topic == "Redis"
    assert "job_id" not in result.model_dump()


@pytest.mark.parametrize("invalid", ["jd", "resume"])
def test_analysis_rejects_invented_citations(settings, invalid):
    store = MemoryRepository()
    record = resume_record()
    store.add("resume", record)
    def handler(request):
        result = fake_completion(request).json()
        data = json.loads(result["choices"][0]["message"]["content"])
        advice = data["resume_suggestions"][0]
        if invalid == "jd":
            advice["jd_quote"] = "invented requirement"
        else:
            advice["source_ids"] = ["invented source"]
        result["choices"][0]["message"]["content"] = json.dumps(data)
        return httpx.Response(200, json=result)
    with pytest.raises(AppError, match="LLM_OUTPUT_INVALID"):
        MatchService(store, ModelClient(settings, httpx.MockTransport(handler))).analyze(record.response.resume_id, JD)


def test_skill_names_are_not_substring_matches():
    assert not contains_skill("JavaScript", "Java")
    assert not contains_skill("C++", "C")
    assert contains_skill("了解 C++", "C++")
    assert contains_skill("Python 3", "Python")
    assert contains_skill("使用 P y t h o n 编写接口", "Python")
    assert contains_skill("Ｃ＋＋", "C++")


def test_capacity_expiration_and_copy_isolation():
    store = MemoryRepository(capacity=1, ttl=1)
    record = resume_record()
    key = store.add("resume", record)
    returned = store.get(key, "resume")
    returned.response.filename = "mutated"
    assert store.get(key, "resume").response.filename != "mutated"
    with pytest.raises(AppError, match="TEMP_STORE_FULL"):
        store.add("resume", record)
    store._items[key] = (time.monotonic() - 2, record)
    with pytest.raises(AppError, match="RESUME_NOT_FOUND"):
        store.get(key, "resume")

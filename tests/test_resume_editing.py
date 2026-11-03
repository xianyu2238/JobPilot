"""Persisted manual corrections, optimistic versions, and preserved OCR."""

from copy import deepcopy
import json

import httpx

from app.core.errors import AppError
from app.core.llm import ModelClient
from conftest import JD, TEXT, fake_completion, pdf_bytes, png_bytes


def structured_resume(client):
    resume = client.post("/api/resumes", files={"file": ("resume.pdf", pdf_bytes())}).json()
    response = client.post(f"/api/resumes/{resume['resume_id']}/structure", json={"expected_revision": resume["revision"]})
    assert response.status_code == 200, response.text
    return response.json()


def editable(resume):
    parsed = resume["parsed_data"]
    return {
        "personal_info": deepcopy(parsed["personal_info"]),
        **{field: [{"title": item["title"], "description": item["description"]} for item in parsed[field]]
           for field in ("education", "experiences", "projects")},
        "skills": [{"name": item["name"], "level": item["level"]} for item in parsed["skills"]],
    }


def test_saved_edits_change_analysis_and_require_confirmation(client, application, settings):
    resume = structured_resume(client)
    key = resume["resume_id"]
    client.post(f"/api/resumes/{key}/confirm", json={"confirmed": True, "expected_revision": resume["revision"]})
    data = editable(resume)
    data["personal_info"]["name"] = "Corrected name"
    data["projects"][0]["description"] = "User corrected project description"
    data["skills"].append({"name": "Redis", "level": "mentioned"})
    saved = client.put(f"/api/resumes/{key}", json={"expected_revision": resume["revision"], "parsed_data": data})
    assert saved.status_code == 200, saved.text
    updated = saved.json()
    assert updated["revision"] == resume["revision"] + 1
    assert updated["parse_status"] == "edited" and not updated["confirmed"]
    assert updated["pages"] == resume["pages"]
    assert updated["parsed_data"]["projects"][0]["origin"] == "user"
    assert updated["parsed_data"]["projects"][0]["evidence"] == []
    assert updated["parsed_data"]["skills"][0]["origin"] == "extracted"
    assert updated["parsed_data"]["skills"][-1]["origin"] == "user"
    assert client.post("/api/jobs/match", json={"resume_id": key, "jd_text": JD}).status_code == 409
    assert client.post(f"/api/resumes/{key}/confirm", json={"confirmed": True, "expected_revision": resume["revision"]}).status_code == 409
    assert client.post(f"/api/resumes/{key}/confirm", json={"confirmed": True, "expected_revision": updated["revision"]}).status_code == 200

    calls = []
    def handler(request):
        data = json.loads(json.loads(request.content)["messages"][1]["content"])
        calls.append(data)
        assert data["resume"]["personal_info"]["name"] == "Corrected name"
        assert data["resume"]["projects"][0]["description"] == "User corrected project description"
        assert data["resume"]["skills"][-1]["name"] == "Redis"
        return fake_completion(request)
    application.state.model = ModelClient(settings, httpx.MockTransport(handler))
    assert client.post("/api/jobs/match", json={"resume_id": key, "jd_text": JD, "resume_revision": resume["revision"]}).status_code == 409
    response = client.post("/api/jobs/match", json={"resume_id": key, "jd_text": JD, "resume_revision": updated["revision"]})
    assert response.status_code == 200, response.text
    assert len(calls) == 1


def test_stale_saves_and_forged_evidence_are_rejected(client):
    resume = structured_resume(client)
    key = resume["resume_id"]
    data = editable(resume)
    assert client.put(f"/api/resumes/{key}", json={"expected_revision": resume["revision"], "parsed_data": data}).status_code == 200
    assert client.put(f"/api/resumes/{key}", json={"expected_revision": resume["revision"], "parsed_data": data}).status_code == 409
    current = client.get(f"/api/resumes/{key}").json()
    data["projects"][0]["evidence"] = [{"page": 1, "quote": "forged quote"}]
    assert client.put(f"/api/resumes/{key}", json={"expected_revision": current["revision"], "parsed_data": data}).status_code == 422


def test_structure_failure_keeps_ocr_for_retry(client, application):
    response = client.post("/api/resumes", files={"file": ("resume.png", png_bytes())})
    resume = response.json()
    key = resume["resume_id"]
    assert application.state.ocr.calls == 1
    model = application.state.model
    class FailingModel:
        def extract(self, *args, **kwargs):
            raise AppError(504, "LLM_TIMEOUT", "test timeout")
    application.state.model = FailingModel()
    assert client.post(f"/api/resumes/{key}/structure", json={"expected_revision": resume["revision"]}).status_code == 504
    assert client.get(f"/api/resumes/{key}").json()["pages"][0]["text"] == TEXT
    assert client.get(f"/api/resumes/{key}/pages/1/preview").status_code == 200
    application.state.model = model
    retried = client.post(f"/api/resumes/{key}/structure", json={"expected_revision": resume["revision"]})
    assert retried.status_code == 200
    assert application.state.ocr.calls == 1


def test_ocr_cache_is_reused_and_deleted_with_records(client, application):
    data = png_bytes()
    first = client.post("/api/resumes", files={"file": ("resume.png", data)}).json()
    second = client.post("/api/resumes", files={"file": ("resume.png", data)}).json()
    assert first["resume_id"] != second["resume_id"]
    assert application.state.ocr.calls == 1
    for resume in (first, second):
        assert client.delete(f"/api/resumes/{resume['resume_id']}").status_code == 204
    assert client.post("/api/resumes", files={"file": ("resume.png", data)}).status_code == 201
    assert application.state.ocr.calls == 2


def test_manual_entry_without_model_and_empty_save(client, application):
    application.state.settings.llm_api_key = ""
    resume = client.post("/api/resumes", files={"file": ("resume.pdf", pdf_bytes())}).json()
    key = resume["resume_id"]
    assert client.put(f"/api/resumes/{key}", json={"expected_revision": 1, "parsed_data": {}}).status_code == 422
    response = client.put(f"/api/resumes/{key}", json={"expected_revision": 1, "parsed_data": {"personal_info": {"name": "Manual candidate"}}})
    assert response.status_code == 200
    assert response.json()["parsed_data"]["personal_info"]["name"] == "Manual candidate"


def test_contacts_are_kept_locally_and_hidden_from_model(client, application, settings):
    calls = []
    def handler(request):
        payload = json.loads(request.content)["messages"][1]["content"]
        assert "13800138000" not in payload
        assert "test@example.com" not in payload
        calls.append(request)
        return fake_completion(request)
    application.state.model = ModelClient(settings, httpx.MockTransport(handler))
    resume = client.post("/api/resumes", files={"file": ("resume.pdf", pdf_bytes(TEXT + "\n13800138000 test@example.com"))}).json()
    response = client.post(f"/api/resumes/{resume['resume_id']}/structure", json={"expected_revision": resume["revision"]})
    assert response.status_code == 200, response.text
    info = response.json()["parsed_data"]["personal_info"]
    assert info["phone"] == "13800138000" and info["email"] == "test@example.com"
    assert len(calls) == 1


def test_long_experiences_keep_all_citations_without_retry(client, application, settings):
    """Reproduce the reported two experiences + project with >8 OCR lines."""
    calls = []
    def handler(request):
        calls.append(request)
        sources = json.loads(json.loads(request.content)["messages"][1]["content"])["sources"]
        ids = [item["id"] for item in sources if item["text"].startswith("Evidence line")]
        assert len(ids) == 16
        repeated = ids * 4 + [ids[0]]
        item = {"title": "Long experience", "description": "Description spanning many OCR lines", "source_ids": repeated}
        return httpx.Response(200, json={"choices": [{"message": {"content": json.dumps({
            "experiences": [item, {**item, "title": "Second experience"}], "projects": [item],
        })}}]})
    application.state.model = ModelClient(settings, httpx.MockTransport(handler))
    text = TEXT + "\n" + "\n".join(f"Evidence line {index}: work details" for index in range(16))
    resume = client.post("/api/resumes", files={"file": ("long.pdf", pdf_bytes(text))}).json()
    response = client.post(f"/api/resumes/{resume['resume_id']}/structure", json={"expected_revision": resume["revision"]})
    assert response.status_code == 200, response.text
    structured = response.json()
    assert len(calls) == 1
    for item in structured["parsed_data"]["experiences"] + structured["parsed_data"]["projects"]:
        assert len(item["evidence"]) == 16
    saved = client.put(f"/api/resumes/{resume['resume_id']}", json={"expected_revision": structured["revision"], "parsed_data": editable(structured)})
    assert saved.status_code == 200, saved.text
    assert len(saved.json()["parsed_data"]["experiences"][0]["evidence"]) == 16


def test_structure_error_reports_readable_field_and_preserves_text(client, application, settings):
    def handler(request):
        value = {"experiences": [{"title": "Experience", "description": "details", "source_ids": [f"source_{index}" for index in range(65)]}]}
        return httpx.Response(200, json={"choices": [{"message": {"content": json.dumps(value)}}]})
    application.state.model = ModelClient(settings, httpx.MockTransport(handler))
    resume = client.post("/api/resumes", files={"file": ("resume.pdf", pdf_bytes())}).json()
    response = client.post(f"/api/resumes/{resume['resume_id']}/structure", json={"expected_revision": resume["revision"]})
    assert response.status_code == 502
    message = response.json()["message"]
    assert "实习经历" in message and "原文引用" in message and "数量超过上限" in message
    assert "识别文字已保留" in message
    assert client.get(f"/api/resumes/{resume['resume_id']}").json()["pages"]

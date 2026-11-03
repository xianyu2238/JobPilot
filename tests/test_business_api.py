"""API flow including real PDF parsing, mocked model HTTP, and confirmation."""

import pytest

from conftest import JD, jpeg_bytes, pdf_bytes, png_bytes


@pytest.mark.parametrize("filename,data,method", [
    ("resume.pdf", lambda: pdf_bytes(), "pdf_text"),
    ("scan.pdf", lambda: pdf_bytes(scan=True), "local_ocr"),
    ("resume.png", png_bytes, "local_ocr"),
    ("resume.jpg", jpeg_bytes, "local_ocr"),
    ("resume.jpeg", jpeg_bytes, "local_ocr"),
    ("resume.JPG", jpeg_bytes, "local_ocr"),
])
def test_complete_flow(client, filename, data, method):
    created = client.post("/api/resumes", files={"file": (filename, data())})
    assert created.status_code == 201, created.text
    resume = created.json()
    resume_id = resume["resume_id"]
    assert resume["pages"][0]["method"] == method
    assert resume["confirmed"] is False
    assert client.get(f"/api/resumes/{resume_id}").json() == resume
    preview = client.get(f"/api/resumes/{resume_id}/pages/1/preview")
    assert preview.status_code == 200
    assert preview.content.startswith(b"\x89PNG")
    assert preview.headers["cache-control"] == "no-store"
    assert resume["parse_status"] == "text_ready"
    assert client.post(f"/api/resumes/{resume_id}/confirm", json={"confirmed": True}).status_code == 409
    structured = client.post(f"/api/resumes/{resume_id}/structure", json={"expected_revision": resume["revision"]})
    assert structured.status_code == 200, structured.text
    assert structured.json()["parse_status"] == "structured"
    payload = {"resume_id": resume_id, "jd_text": JD}
    assert client.post("/api/jobs/match", json=payload).json()["code"] == "RESUME_NOT_CONFIRMED"
    assert client.post(f"/api/resumes/{resume_id}/confirm", json={"confirmed": True}).json()["confirmed"]
    analysis = client.post("/api/jobs/match", json=payload)
    assert analysis.status_code == 200, analysis.text
    result = analysis.json()
    assert result["resume_suggestions"] and result["learning_suggestions"]
    assert {item["topic"] for item in result["learning_suggestions"]} == {"Redis"}
    assert "%" not in result["overview"]
    client.post(f"/api/resumes/{resume_id}/confirm", json={"confirmed": False})
    assert client.post("/api/jobs/match", json=payload).status_code == 409
    assert client.delete(f"/api/resumes/{resume_id}").status_code == 204
    assert client.get(f"/api/resumes/{resume_id}").status_code == 404


@pytest.mark.parametrize("filename,data,code", [
    ("resume.jpg", b"jpeg", "UNSUPPORTED_FILE_TYPE"),
    ("resume.pdf", b"not a pdf", "UNSUPPORTED_FILE_TYPE"),
    ("resume.pdf", b"%PDF-broken", "PDF_INVALID"),
    ("resume.png", b"\x89PNG\r\n\x1a\nBAD", "IMAGE_INVALID"),
    ("resume.jpg", b"\xff\xd8\xffBAD", "IMAGE_INVALID"),
    ("resume.jpg", png_bytes(), "UNSUPPORTED_FILE_TYPE"),
    ("resume.png", jpeg_bytes(), "UNSUPPORTED_FILE_TYPE"),
    ("resume.pdf", b"", "FILE_EMPTY"),
])
def test_invalid_files(client, filename, data, code):
    response = client.post("/api/resumes", files={"file": (filename, data)})
    assert response.status_code in {415, 422}
    assert response.json()["code"] == code
    assert response.headers["X-Request-ID"] == response.json()["request_id"]


def test_validation_errors_do_not_echo_private_input(client):
    response = client.post("/api/jobs/match", json={"resume_id": "test", "jd_text": "private" * 3000})
    assert response.status_code == 422
    assert "private" not in response.text
    assert client.post("/api/jobs/match", json={"resume_id": "test", "jd_text": "   "}).status_code == 422
    assert client.get("/api/resumes/not-found").status_code == 404


def test_model_configuration_missing(client, application):
    application.state.settings.llm_api_key = ""
    response = client.post("/api/resumes", files={"file": ("resume.pdf", pdf_bytes())})
    assert response.status_code == 201
    resume = response.json()
    response = client.post(f"/api/resumes/{resume['resume_id']}/structure", json={"expected_revision": resume["revision"]})
    assert response.status_code == 503
    assert response.json()["code"] == "LLM_NOT_CONFIGURED"
    assert client.get(f"/api/resumes/{resume['resume_id']}").json()["pages"]
    assert client.get("/health").status_code == 200


def test_standalone_job_routes_removed(client):
    paths = client.get("/openapi.json").json()["paths"]
    assert "/api/jobs" not in paths
    assert "/api/jobs/{job_id}" not in paths
    assert client.post("/api/jobs", json={"jd_text": JD}).status_code == 404
    assert client.get("/api/jobs/old-id").status_code == 404

"""Export checks: saved data, escaping, downloads and revision safety."""

from io import BytesIO
import subprocess
from types import SimpleNamespace
import zipfile

import pytest

from app.core.errors import AppError
from app.repositories.memory import ResumeRecord
from app.schemas.export import ExportRequest
from app.services.latex_service import latex_escape, render_sources
from scripts.warm_latex import sample_resume
from conftest import pdf_bytes


@pytest.fixture
def export_resume(application):
    response = sample_resume()
    key = application.state.store.add("resume", ResumeRecord(response, []))
    calls = []
    exporter = application.state.exporter
    exporter.engine = lambda: ("tectonic", "fake-tectonic")
    def compile_pdf(command, **kwargs):
        calls.append(command)
        (kwargs["cwd"] / "resume.pdf").write_bytes(pdf_bytes("Saved content"))
        return SimpleNamespace(returncode=0, stdout=b"", stderr=b"")
    exporter.runner = compile_pdf
    return key, exporter, calls


def test_sources_escape_text_and_suppress_empty_sections():
    resume = sample_resume()
    resume.parsed_data.personal_info.name = r"Edited & 50% \input{secret}"
    resume.parsed_data.education = []
    sources = render_sources(resume)
    main = sources["resume.tex"].decode()
    assert latex_escape(resume.parsed_data.personal_info.name) in main
    assert r"\input{secret}" not in main
    assert r"\cvsection" not in sources["sections/education.tex"].decode()
    assert b"MIT License" in sources["LICENSE"]
    assert "50\\%" in sources["sections/projects.tex"].decode()


def test_export_binary_download_cache_and_invalidate(client, application, export_resume):
    key, exporter, calls = export_resume
    path = f"/api/resumes/{key}"
    request = {"expected_revision": 1}
    response = client.post(path + "/export", json=request)
    assert response.status_code == 200, response.text
    data = response.json()
    assert data["page_count"] == 1
    assert len(calls) == 1 and "--untrusted" in calls[0] and "--only-cached" in calls[0]
    assert client.post(path + "/export", json=request).json() == data
    assert len(calls) == 1
    url = path + f"/exports/{data['export_id']}"
    pdf = client.get(url + "/pdf")
    assert pdf.headers["content-type"] == "application/pdf"
    assert pdf.content.startswith(b"%PDF")
    source = client.get(url + "/source")
    with zipfile.ZipFile(BytesIO(source.content)) as archive:
        assert {"resume.tex", "LICENSE", "open-curve.sty", "sections/projects.tex"} <= set(archive.namelist())
    current = application.state.store.get(key, "resume").response
    current.parsed_data.personal_info.name = "Saved edit"
    application.state.store.replace(key, current, 1)
    assert client.get(url + "/pdf").status_code == 404
    assert client.post(path + "/export", json=request).status_code == 409
    source = client.post(path + "/export/source", json={"expected_revision": 2})
    with zipfile.ZipFile(BytesIO(source.content)) as archive:
        assert b"Saved edit" in archive.read("resume.tex")


def test_source_does_not_need_compiler(client, export_resume):
    key, exporter, _ = export_resume
    def missing():
        raise AppError(503, "LATEX_NOT_AVAILABLE", "Install compiler")
    exporter.engine = missing
    path = f"/api/resumes/{key}/export"
    assert client.post(path + "/source", json={"expected_revision": 1}).status_code == 200
    assert client.post(path, json={"expected_revision": 1}).status_code == 503


def test_timeout_and_edit_during_compilation(application, export_resume):
    key, exporter, _ = export_resume
    def timeout(*args, **kwargs):
        raise subprocess.TimeoutExpired(args[0], 1)
    exporter.runner = timeout
    with pytest.raises(AppError) as error:
        exporter.create(key, ExportRequest(expected_revision=1))
    assert error.value.code == "LATEX_TIMEOUT"
    def edit_during_compile(command, **kwargs):
        current = application.state.store.get(key, "resume").response
        application.state.store.replace(key, current, 1)
        (kwargs["cwd"] / "resume.pdf").write_bytes(pdf_bytes())
        return SimpleNamespace(returncode=0, stdout=b"", stderr=b"")
    exporter.runner = edit_during_compile
    with pytest.raises(AppError) as error:
        exporter.create(key, ExportRequest(expected_revision=1))
    assert error.value.code == "RESUME_VERSION_CONFLICT"
    assert application.state.store.get(key, "resume").export is None

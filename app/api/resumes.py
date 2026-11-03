"""Resume upload, preview, confirmation, and deletion endpoints."""

from pathlib import Path
from typing import Literal

from fastapi import APIRouter, File, Request, UploadFile
from fastapi.responses import Response

from app.core.errors import AppError
from app.schemas.business import ConfirmInput, ResumeResponse, ResumeUpdateInput, StructureInput
from app.services.resume_service import ResumeService
from app.schemas.export import ExportRequest, ExportResponse

router = APIRouter(prefix="/api/resumes", tags=["resumes"])


@router.post("", response_model=ResumeResponse, status_code=201)
def upload_resume(request: Request, file: UploadFile = File(...), recognition_mode: Literal["local", "vision"] = "local") -> ResumeResponse:
    settings = request.app.state.settings
    limit = settings.max_file_mb * 1024 * 1024
    chunks, size = [], 0
    try:
        while chunk := file.file.read(65536):
            size += len(chunk)
            if size > limit:
                raise AppError(413, "FILE_TOO_LARGE", f"文件不能超过 {settings.max_file_mb} MiB。")
            chunks.append(chunk)
    finally:
        file.file.close()
    filename = Path((file.filename or "resume").replace("\\", "/")).name[:200]
    return ResumeService(settings, request.app.state.model, request.app.state.store, request.app.state.ocr).upload(b"".join(chunks), filename, recognition_mode)


@router.post("/{resume_id}/structure", response_model=ResumeResponse)
def structure(resume_id: str, body: StructureInput, request: Request) -> ResumeResponse:
    return ResumeService(request.app.state.settings, request.app.state.model, request.app.state.store).structure(resume_id, body.expected_revision)


@router.put("/{resume_id}", response_model=ResumeResponse)
def update(resume_id: str, body: ResumeUpdateInput, request: Request) -> ResumeResponse:
    return ResumeService(request.app.state.settings, request.app.state.model, request.app.state.store).update(resume_id, body)


@router.get("/{resume_id}", response_model=ResumeResponse)
def get_resume(resume_id: str, request: Request) -> ResumeResponse:
    return request.app.state.store.get(resume_id, "resume").response


@router.get("/{resume_id}/pages/{page}/preview")
def preview(resume_id: str, page: int, request: Request) -> Response:
    record = request.app.state.store.get(resume_id, "resume")
    if page < 1 or page > len(record.previews):
        raise AppError(404, "PAGE_NOT_FOUND", "简历页面不存在。")
    return Response(record.previews[page - 1], media_type="image/png", headers={"Cache-Control": "no-store"})


@router.post("/{resume_id}/confirm", response_model=ResumeResponse)
def confirm(resume_id: str, body: ConfirmInput, request: Request) -> ResumeResponse:
    return request.app.state.store.confirm(resume_id, body.confirmed, body.expected_revision)


@router.delete("/{resume_id}", status_code=204)
def delete(resume_id: str, request: Request) -> Response:
    request.app.state.store.delete(resume_id, "resume")
    return Response(status_code=204)


@router.post("/{resume_id}/export", response_model=ExportResponse)
def export_pdf(resume_id: str, body: ExportRequest, request: Request) -> ExportResponse:
    return request.app.state.exporter.create(resume_id, body)


@router.post("/{resume_id}/export/source")
def export_source(resume_id: str, body: ExportRequest, request: Request) -> Response:
    content = request.app.state.exporter.source(resume_id, body)
    return Response(content, media_type="application/zip", headers={
        "Content-Disposition": f'attachment; filename="jobpilot-resume-r{body.expected_revision}-source.zip"'
    })


@router.get("/{resume_id}/exports/{export_id}/pdf")
def download_pdf(resume_id: str, export_id: str, request: Request) -> Response:
    artifact = request.app.state.exporter.download(resume_id, export_id)
    return Response(artifact.pdf, media_type="application/pdf", headers={
        "Content-Disposition": f'attachment; filename="jobpilot-resume-r{artifact.revision}.pdf"'
    })


@router.get("/{resume_id}/exports/{export_id}/source")
def download_source(resume_id: str, export_id: str, request: Request) -> Response:
    artifact = request.app.state.exporter.download(resume_id, export_id)
    return Response(artifact.source_zip, media_type="application/zip", headers={
        "Content-Disposition": f'attachment; filename="jobpilot-resume-r{artifact.revision}-source.zip"'
    })

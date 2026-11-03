"""Contracts and private in-memory artifacts for resume export."""

from dataclasses import dataclass
from typing import Literal

from pydantic import Field

from app.schemas.business import Schema


class ExportRequest(Schema):
    expected_revision: int = Field(ge=1)
    layout: Literal["standard", "compact"] = "standard"


class ExportResponse(Schema):
    export_id: str
    resume_id: str
    revision: int
    layout: Literal["standard", "compact"]
    page_count: int
    warnings: list[str]
    filename: str


@dataclass
class ExportArtifact:
    export_id: str
    revision: int
    layout: str
    pdf: bytes
    source_zip: bytes
    page_count: int
    warnings: list[str]

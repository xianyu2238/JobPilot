"""Saved-revision HTML generation contracts."""

from dataclasses import dataclass

from pydantic import Field, model_validator

from app.schemas.business import Schema


class ResumeGenerationInput(Schema):
    expected_revision: int = Field(ge=1)
    use_jd: bool = False
    jd_text: str = Field(default="", max_length=15000)
    instructions: str = Field(default="", max_length=1000)

    @model_validator(mode="after")
    def require_job(self):
        if self.use_jd and not self.jd_text:
            raise ValueError("Targeted generation requires JD")
        return self


class ResumeGenerationResponse(Schema):
    generation_id: str
    resume_id: str
    revision: int
    model: str
    preview_path: str


@dataclass
class GeneratedResume:
    generation_id: str
    revision: int
    fingerprint: str
    model: str
    html: str

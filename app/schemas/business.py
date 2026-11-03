"""Shared contracts for document extraction and direct JD advice."""

from typing import Literal

from pydantic import BaseModel, ConfigDict, Field, field_validator

MAX_RESUME_SOURCE_REFERENCES = 64


class Schema(BaseModel):
    model_config = ConfigDict(extra="forbid", str_strip_whitespace=True)


class Evidence(Schema):
    page: int = Field(ge=1)
    quote: str = Field(min_length=1, max_length=2000)


class PersonalInfo(Schema):
    name: str | None = Field(default=None, max_length=100)
    phone: str | None = Field(default=None, max_length=100)
    email: str | None = Field(default=None, max_length=200)
    city: str | None = Field(default=None, max_length=100)
    job_intention: str | None = Field(default=None, max_length=200)
    other: str | None = Field(default=None, max_length=1000)


class ResumeItem(Schema):
    title: str = Field(min_length=1, max_length=200)
    description: str = Field(min_length=1, max_length=3000)
    evidence: list[Evidence] = Field(default_factory=list, max_length=MAX_RESUME_SOURCE_REFERENCES)
    origin: Literal["extracted", "user"] = "extracted"


class Skill(Schema):
    name: str = Field(min_length=1, max_length=100)
    description: str = Field(default="", max_length=2000)
    level: Literal["mentioned", "applied", "planned", "negated", "uncertain"]
    evidence: list[Evidence] = Field(default_factory=list, max_length=MAX_RESUME_SOURCE_REFERENCES)
    origin: Literal["extracted", "user"] = "extracted"


class ParsedResume(Schema):
    personal_info: PersonalInfo = Field(default_factory=PersonalInfo)
    education: list[ResumeItem] = Field(default_factory=list, max_length=30)
    experiences: list[ResumeItem] = Field(default_factory=list, max_length=30)
    projects: list[ResumeItem] = Field(default_factory=list, max_length=30)
    skills: list[Skill] = Field(default_factory=list, max_length=80)
    warnings: list[str] = Field(default_factory=list, max_length=20)


class CitedDraft(Schema):
    source_ids: list[str] = Field(min_length=1, max_length=MAX_RESUME_SOURCE_REFERENCES)

    @field_validator("source_ids", mode="before")
    @classmethod
    def deduplicate_sources(cls, value):
        if isinstance(value, list) and all(isinstance(item, str) for item in value):
            return list(dict.fromkeys(value))
        return value


class DraftItem(CitedDraft):
    title: str = Field(min_length=1, max_length=200)
    description: str = Field(min_length=1, max_length=800)


class DraftSkill(CitedDraft):
    name: str = Field(min_length=1, max_length=100)
    description: str = Field(default="", max_length=1000)
    level: Literal["mentioned", "applied", "planned", "negated", "uncertain"]


class ResumeDraft(Schema):
    """Internal model output: cite source IDs instead of duplicating long quotes."""

    personal_info: PersonalInfo = Field(default_factory=PersonalInfo)
    education: list[DraftItem] = Field(default_factory=list, max_length=30)
    experiences: list[DraftItem] = Field(default_factory=list, max_length=30)
    projects: list[DraftItem] = Field(default_factory=list, max_length=30)
    skills: list[DraftSkill] = Field(default_factory=list, max_length=80)
    warnings: list[str] = Field(default_factory=list, max_length=20)


class Recognition(Schema):
    text: str = Field(min_length=1, max_length=30000)
    warnings: list[str] = Field(default_factory=list, max_length=20)


class OCRLine(Schema):
    text: str
    confidence: float = Field(ge=0, le=1)
    box: list[list[float]] = Field(min_length=4, max_length=4)


class PageText(Schema):
    page: int
    text: str
    method: Literal["pdf_text", "local_ocr", "vision"]
    lines: list[OCRLine] = Field(default_factory=list)
    width: int | None = None
    height: int | None = None


class ResumeResponse(Schema):
    resume_id: str
    filename: str
    parsed_data: ParsedResume
    pages: list[PageText]
    warnings: list[str]
    confirmed: bool = False
    parse_status: Literal["text_ready", "structured", "edited"] = "structured"
    revision: int = Field(default=1, ge=1)


class ConfirmInput(Schema):
    confirmed: bool
    expected_revision: int | None = Field(default=None, ge=1)


class StructureInput(Schema):
    expected_revision: int = Field(ge=1)


class EditableItem(Schema):
    title: str = Field(min_length=1, max_length=200)
    description: str = Field(min_length=1, max_length=3000)


class EditableSkill(Schema):
    name: str = Field(min_length=1, max_length=100)
    description: str = Field(default="", max_length=2000)
    level: Literal["mentioned", "applied", "planned", "negated", "uncertain"]


class EditableResume(Schema):
    personal_info: PersonalInfo = Field(default_factory=PersonalInfo)
    education: list[EditableItem] = Field(default_factory=list, max_length=30)
    experiences: list[EditableItem] = Field(default_factory=list, max_length=30)
    projects: list[EditableItem] = Field(default_factory=list, max_length=30)
    skills: list[EditableSkill] = Field(default_factory=list, max_length=80)


class ResumeUpdateInput(Schema):
    expected_revision: int = Field(ge=1)
    parsed_data: EditableResume


class MatchInput(Schema):
    resume_id: str = Field(min_length=1, max_length=100)
    jd_text: str = Field(min_length=1, max_length=15000)
    resume_revision: int | None = Field(default=None, ge=1)


class DraftEditAdvice(Schema):
    priority: Literal["高", "中", "低"]
    target: str = Field(min_length=1, max_length=200)
    reason: str = Field(min_length=1, max_length=600)
    action: str = Field(min_length=1, max_length=1000)
    source_ids: list[str] = Field(default_factory=list, max_length=4)
    jd_quote: str = Field(min_length=1, max_length=1000)


class EditAdvice(Schema):
    priority: Literal["高", "中", "低"]
    target: str
    reason: str
    action: str
    original_quote: str | None = None
    jd_quote: str


class LearningAdvice(Schema):
    priority: Literal["高", "中", "低"]
    topic: str = Field(min_length=1, max_length=100)
    task: str = Field(min_length=1, max_length=1000)
    deliverable: str = Field(min_length=1, max_length=600)
    jd_quote: str = Field(min_length=1, max_length=1000)


class MatchDraft(Schema):
    overview: str = Field(min_length=1, max_length=1200)
    resume_suggestions: list[DraftEditAdvice] = Field(min_length=1, max_length=10)
    learning_suggestions: list[LearningAdvice] = Field(default_factory=list, max_length=10)
    warnings: list[str] = Field(default_factory=list, max_length=20)


class MatchResponse(Schema):
    resume_id: str
    overview: str
    resume_suggestions: list[EditAdvice]
    learning_suggestions: list[LearningAdvice]
    warnings: list[str]

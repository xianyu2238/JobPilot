"""Extract structured resumes and verify every supplied evidence quote."""

import json
import hashlib
import logging
from pathlib import Path
import re
import time

from app.core.config import Settings
from app.core.errors import AppError
from app.core.llm import ModelClient
from app.core.skill_aliases import canonical, contains_skill
from app.repositories.memory import MemoryRepository, ResumeRecord
from app.schemas.business import Evidence, ParsedResume, ResumeDraft, ResumeItem, ResumeResponse, ResumeUpdateInput, Skill
from app.services.document_service import DocumentService
from app.services.ocr_service import LocalOCR

PROMPT = (Path(__file__).parents[1] / "prompts" / "resume.txt").read_text(encoding="utf-8")
logger = logging.getLogger("jobpilot.resume")


def hide_contacts(text: str) -> str:
    text = re.sub(r"[\w.+-]+@[\w.-]+\.[A-Za-z]{2,}", "[邮箱已隐藏]", text)
    return re.sub(r"(?<!\d)(?:\+?86[- ]?)?1[3-9]\d{9}(?!\d)", "[手机已隐藏]", text)


class ResumeService:
    def __init__(self, settings: Settings, model: ModelClient, store: MemoryRepository, ocr: LocalOCR | None = None):
        self.settings, self.model, self.store = settings, model, store
        self.ocr = ocr

    def upload(self, data: bytes, filename: str, recognition_mode: str = "local") -> ResumeResponse:
        deadline = time.monotonic() + self.settings.parse_budget_seconds
        stamp = f"{recognition_mode}:{Path(filename).suffix.lower()}:{self.settings.ocr_confidence_threshold}"
        fingerprint = hashlib.sha256(data + stamp.encode()).hexdigest()
        cached = self.store.find_document(fingerprint)
        if cached is not None:
            pages, previews, notes = cached.response.pages, cached.previews, cached.document_warnings
            logger.info("document_cache_hit pages=%s", len(pages))
        else:
            extracted = DocumentService(self.settings, self.model, self.ocr).extract(data, filename, deadline, recognition_mode)
            pages, previews, notes = extracted.pages, extracted.previews, extracted.warnings
        response = ResumeResponse(resume_id="", filename=filename, parsed_data=ParsedResume(),
                                  pages=pages, warnings=notes, parse_status="text_ready")
        self.store.add("resume", ResumeRecord(response, previews, fingerprint, list(notes)))
        return response

    def parse(self, data: bytes, filename: str) -> ResumeResponse:
        """Convenience pipeline; HTTP separates these stages to preserve OCR."""
        response = self.upload(data, filename)
        return self.structure(response.resume_id, response.revision)

    def structure(self, resume_id: str, expected_revision: int) -> ResumeResponse:
        record = self.store.get(resume_id, "resume")
        if record.response.revision != expected_revision:
            raise AppError(409, "RESUME_VERSION_CONFLICT", "简历已更新，请重新加载后再整理。")
        if record.response.parse_status == "edited":
            raise AppError(409, "RESUME_ALREADY_EDITED", "当前版本包含手动修改，请继续编辑；如需从原文件重新整理，请重新上传。")
        deadline = time.monotonic() + self.settings.parse_budget_seconds
        sources = {}
        for page in record.response.pages:
            index = 0
            for line in page.text.splitlines():
                if not line.strip():
                    continue
                for start in range(0, len(line), 450):
                    quote = line[start:start + 450].strip()
                    if not quote:
                        continue
                    index += 1
                    sources[f"p{page.page}_s{index}"] = Evidence(page=page.page, quote=quote)
        draft = self.model.extract(
            ResumeDraft, PROMPT,
            json.dumps({"sources": [{"id": key, "page": value.page, "text": hide_contacts(value.quote)}
                                    for key, value in sources.items()]}, ensure_ascii=False),
            deadline=deadline, max_tokens=4500,
        )
        parsed = ParsedResume(personal_info=draft.personal_info, warnings=list(draft.warnings))
        # These contact fields are extracted locally and never guessed from masked text.
        full_text = "\n".join(page.text for page in record.response.pages)
        phone = re.search(r"(?<!\d)(?:\+?86[- ]?)?(1[3-9](?:[- ]?\d){9})(?!\d)", full_text)
        email = re.search(r"[\w.+-]+@[\w.-]+\.[A-Za-z]{2,}", full_text)
        parsed.personal_info.phone = re.sub(r"[- ]", "", phone.group(1)) if phone else None
        parsed.personal_info.email = email.group(0) if email else None
        excluded = 0
        unresolved = 0

        def evidence_for(item):
            nonlocal unresolved
            unresolved += sum(key not in sources for key in dict.fromkeys(item.source_ids))
            return [sources[key] for key in dict.fromkeys(item.source_ids) if key in sources]

        for field in ("education", "experiences", "projects"):
            for index, item in enumerate(getattr(draft, field)):
                evidence = evidence_for(item)
                if not evidence:
                    excluded += 1
                    logger.warning("resume_item_excluded field=%s index=%s reason=unknown_source_ids", field, index)
                    continue
                getattr(parsed, field).append(ResumeItem(title=item.title, description=item.description, evidence=evidence))
        for index, item in enumerate(draft.skills):
            evidence = evidence_for(item)
            supporting = [quote for quote in evidence if contains_skill(quote.quote, item.name)]
            if not supporting:
                excluded += 1
                logger.warning("resume_item_excluded field=skills index=%s reason=no_named_skill_evidence", index)
                continue
            parsed.skills.append(Skill(name=canonical(item.name), description=item.description, level=item.level, evidence=supporting))
        if not any((any(parsed.personal_info.model_dump().values()), parsed.education, parsed.experiences, parsed.projects, parsed.skills)):
            raise AppError(422, "RESUME_EVIDENCE_INVALID", "未能提取到有原文依据的简历条目，请换用更清晰的文件；没有再次重跑整份简历。")
        notes = []
        if unresolved:
            logger.warning("resume_references_ignored count=%s reason=unknown_source_ids", unresolved)
            notes.append(f"有 {unresolved} 个引用编号无法定位，已忽略；请核对对应内容是否遗漏。")
        if excluded:
            # One unsupported entry must not discard the entire grounded result.
            # Only validated entries can reach matching; the omission is visible.
            notes.append(f"有 {excluded} 项因缺少可核对的原文依据已排除，请对照原文件检查遗漏；其余条目已保留。")
        parsed.warnings = parsed.warnings[:20 - len(notes)] + notes
        response = ResumeResponse(
            resume_id=resume_id, filename=record.response.filename, parsed_data=parsed, pages=record.response.pages,
            warnings=list(dict.fromkeys(record.document_warnings + parsed.warnings)), parse_status="structured",
        )
        return self.store.replace(resume_id, response, expected_revision)

    def update(self, resume_id: str, body: ResumeUpdateInput) -> ResumeResponse:
        record = self.store.get(resume_id, "resume")
        edited = body.parsed_data
        if not any((any(edited.personal_info.model_dump().values()), edited.education, edited.experiences, edited.projects, edited.skills)):
            raise AppError(422, "RESUME_EMPTY", "请至少填写一项个人信息、经历或技能后保存。")
        parsed = ParsedResume(personal_info=edited.personal_info, warnings=record.response.parsed_data.warnings[:19])
        for field in ("education", "experiences", "projects"):
            old = getattr(record.response.parsed_data, field)
            for item in getattr(edited, field):
                unchanged = next((previous for previous in old if previous.title == item.title and previous.description == item.description), None)
                value = unchanged.model_copy(deep=True) if unchanged else ResumeItem(**item.model_dump(), origin="user")
                getattr(parsed, field).append(value)
        for item in edited.skills:
            unchanged = next((previous for previous in record.response.parsed_data.skills if previous.name == item.name and previous.level == item.level and previous.description == item.description), None)
            parsed.skills.append(unchanged.model_copy(deep=True) if unchanged else Skill(**item.model_dump(), origin="user"))
        note = "当前版本含用户保存的修改；修改项不是原文件自动识别证据，请确认后再分析。"
        parsed.warnings = list(dict.fromkeys(parsed.warnings + [note]))
        response = record.response.model_copy(deep=True)
        response.parsed_data = parsed
        response.parse_status = "edited"
        response.warnings = list(dict.fromkeys(record.document_warnings + parsed.warnings))
        return self.store.replace(resume_id, response, body.expected_revision)

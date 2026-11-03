"""Direct advice from pasted JD text; no standalone requirement extraction."""

import json

from app.core.errors import AppError
from app.core.llm import ModelClient
from app.repositories.memory import MemoryRepository
from app.schemas.business import EditAdvice, Evidence, MatchDraft, MatchResponse
from app.services.document_service import compact, normalize_text
from app.services.resume_service import hide_contacts

INSTRUCTIONS = """直接对照用户提供的 JD 和已核对的简历，简短概括匹配程度，重点给出简历修改建议和学习任务。
不输出岗位要求列表或匹配百分比，不推测录用概率。不要编造经历、指标或技能。
修改建议应指向具体段落，区分已有经历表达不足与需要确认的能力；补充内容必须使用条件措辞。
学习任务按岗位相关性排序，给出可执行练习和预期成果，尊重优先/必须、且/或关系。
每条建议的 jd_quote 必须是输入 JD 的连续原文。source_ids 引用给定简历片段编号，
程序会回填原文；没有对应经历时 source_ids 为空，并明确提示先核对本人情况。
只从简历的明确证据说明优势，信息不足时写待确认，不把未提及解释为不会。
技能 level=planned/negated/uncertain 不可当作已掌握。修改建议最多 6 条，学习任务最多 5 条。
origin=user 是用户已保存并确认的补充，可用于分析，但不能称为原文件证据；没有原文时 source_ids 留空。
"""


class MatchService:
    def __init__(self, store: MemoryRepository, model: ModelClient):
        self.store, self.model = store, model

    def analyze(self, resume_id: str, jd_text: str, resume_revision: int | None = None) -> MatchResponse:
        text = normalize_text(jd_text)
        if not text or len(text) > 15000:
            raise AppError(422, "INPUT_INVALID", "请粘贴非空且不超过 15000 字符的岗位描述。")
        resume = self.store.get(resume_id, "resume").response
        if resume_revision is not None and resume.revision != resume_revision:
            raise AppError(409, "RESUME_VERSION_CONFLICT", "简历已更新，请重新加载并确认后再分析。")
        if not resume.confirmed:
            raise AppError(409, "RESUME_NOT_CONFIRMED", "请先在解析预览区核对并确认简历解析结果。")
        sources: dict[str, Evidence] = {}
        seen = set()
        for field in ("education", "experiences", "projects", "skills"):
            for item in getattr(resume.parsed_data, field):
                for evidence in item.evidence:
                    key = (evidence.page, evidence.quote)
                    if key not in seen:
                        seen.add(key)
                        sources[f"r{len(sources) + 1}"] = evidence

        def validate(draft: MatchDraft) -> None:
            for advice in draft.resume_suggestions + draft.learning_suggestions:
                if compact(advice.jd_quote) not in compact(text):
                    raise ValueError("unsupported JD citation")
            for advice in draft.resume_suggestions:
                if any(key not in sources for key in advice.source_ids):
                    raise ValueError("unknown resume source ID")

        draft = self.model.extract(
            MatchDraft, INSTRUCTIONS,
            hide_contacts(json.dumps({
                "jd_text": text, "resume": resume.parsed_data.model_dump(),
                "resume_warnings": resume.warnings,
                "sources": [{"id": key, "page": value.page, "text": value.quote} for key, value in sources.items()],
            }, ensure_ascii=False)), validate=validate, max_tokens=4500,
        )
        edits = [EditAdvice(
            priority=advice.priority, target=advice.target, reason=advice.reason, action=advice.action,
            original_quote="\n".join(sources[key].quote for key in dict.fromkeys(advice.source_ids)) or None,
            jd_quote=advice.jd_quote,
        ) for advice in draft.resume_suggestions]
        return MatchResponse(
            resume_id=resume_id, overview=draft.overview, resume_suggestions=edits,
            learning_suggestions=draft.learning_suggestions,
            warnings=list(dict.fromkeys(resume.warnings + draft.warnings)),
        )

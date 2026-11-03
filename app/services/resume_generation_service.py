"""Generate a styled HTML resume through the user's AiHubMix DeepSeek model."""

import hashlib
import json
import logging
from pathlib import Path
import threading
import time
from uuid import uuid4

import httpx

from app.core.errors import AppError
from app.schemas.resume_generation import GeneratedResume, ResumeGenerationInput, ResumeGenerationResponse
from app.services.resume_html import prepare_html

PROMPT = (Path(__file__).parents[1] / "prompts" / "resume_generation.txt").read_text(encoding="utf-8")
logger = logging.getLogger("jobpilot.generation")


class ResumeGenerationService:
    def __init__(self, settings, store, transport=None):
        self.settings, self.store, self.transport = settings, store, transport
        self._lock = threading.Lock()

    def generate(self, resume_id: str, request: ResumeGenerationInput) -> ResumeGenerationResponse:
        record = self.store.get(resume_id, "resume")
        resume = record.response
        if resume.revision != request.expected_revision:
            raise AppError(409, "RESUME_VERSION_CONFLICT", "简历版本已更新，请重新加载已保存版本。")
        if resume.parse_status == "text_ready":
            raise AppError(409, "RESUME_NOT_STRUCTURED", "请先填写并保存简历表单，再制作简历。")
        parsed = resume.parsed_data
        # Send only saved form fields; omit OCR pages, original file and evidence.
        payload = {
            "resume": {"personal_info": parsed.personal_info.model_dump(),
                       **{field: [{"title": item.title, "description": item.description} for item in getattr(parsed, field)]
                          for field in ("education", "experiences", "projects")},
                       "skills": [{"name": item.name, "description": item.description, "level": item.level} for item in parsed.skills]},
            "jd": request.jd_text if request.use_jd else "",
            "instructions": request.instructions,
        }
        serialized = json.dumps(payload, ensure_ascii=False)
        settings = self.settings
        fingerprint = hashlib.sha256((serialized + PROMPT + settings.resume_generation_model + settings.resume_generation_base_url
                                      + str(settings.resume_generation_max_tokens) + str(settings.resume_generation_enable_thinking)).encode()).hexdigest()
        if record.generation and record.generation.revision == resume.revision and record.generation.fingerprint == fingerprint:
            return self.metadata(resume_id, record.generation)
        if not self._lock.acquire(blocking=False):
            raise AppError(429, "GENERATION_BUSY", "简历正在生成，请等待当前任务完成。")
        try:
            key = settings.resume_generation_api_key.get_secret_value()
            if not key and settings.llm_base_url.rstrip("/") == settings.resume_generation_base_url.rstrip("/"):
                key = settings.llm_api_key.get_secret_value()
            if not key:
                raise AppError(503, "GENERATION_NOT_CONFIGURED", "请在后端 .env 设置 AIHUBMIX_API_KEY 或 JOBPILOT_RESUME_GENERATION_API_KEY，然后重启后端。")
            body = {"model": settings.resume_generation_model,
                    "messages": [{"role": "system", "content": PROMPT}, {"role": "user", "content": serialized}],
                    "max_tokens": settings.resume_generation_max_tokens, "stream": False}
            if settings.resume_generation_model.rsplit("/", 1)[-1].casefold().startswith("deepseek"):
                body["thinking"] = {"type": "enabled" if settings.resume_generation_enable_thinking else "disabled"}
            started = time.monotonic()
            logger.info("model_call stage=ResumeHTML model=%s timeout_s=%.0f max_tokens=%s thinking=%s", settings.resume_generation_model,
                        settings.resume_generation_timeout_seconds, settings.resume_generation_max_tokens, body.get("thinking", {}).get("type", "provider_default"))
            try:
                with httpx.Client(transport=self.transport, proxy=settings.llm_proxy or None,
                                  timeout=httpx.Timeout(settings.resume_generation_timeout_seconds, connect=10)) as client:
                    response = client.post(settings.resume_generation_base_url + "/chat/completions", json=body,
                                           headers={"Authorization": "Bearer " + key})
                logger.info("model_response stage=ResumeHTML status=%s duration_s=%.1f", response.status_code, time.monotonic() - started)
            except httpx.TimeoutException:
                logger.warning("model_timeout stage=ResumeHTML duration_s=%.1f", time.monotonic() - started)
                raise AppError(504, "GENERATION_TIMEOUT", "DeepSeek 制作简历超时，表单和已有预览仍保留，请稍后重试。") from None
            except httpx.RequestError:
                raise AppError(502, "GENERATION_UPSTREAM_ERROR", "无法连接 DeepSeek 服务，请检查 AiHubMix 地址和代理连接。") from None
            if response.is_error:
                raise AppError(502, "GENERATION_UPSTREAM_ERROR", "DeepSeek 请求失败，请检查 AiHubMix 密钥、额度和模型名。")
            try:
                result = response.json()
                choice = result["choices"][0]
                usage = result.get("usage") or {}
                if not isinstance(usage, dict):
                    usage = {}
                details = usage.get("completion_tokens_details") or {}
                if not isinstance(details, dict):
                    details = {}
                def token_count(value):
                    return value if type(value) is int and value >= 0 else None
                raw = choice["message"].get("content")
                logger.info("model_output stage=ResumeHTML finish_reason=%s completion_tokens=%s reasoning_tokens=%s html_chars=%s",
                            choice.get("finish_reason") if choice.get("finish_reason") in {"stop", "length", "content_filter"} else "other",
                            token_count(usage.get("completion_tokens")), token_count(details.get("reasoning_tokens")),
                            len(raw) if isinstance(raw, str) else 0)
                if choice.get("finish_reason") == "length":
                    raise AppError(502, "GENERATION_TRUNCATED", f"模型在 {settings.resume_generation_max_tokens} tokens 上限内未完成 HTML，已保留原表单和已有预览。请检查日志中的 reasoning_tokens；可在 .env 调整 JOBPILOT_RESUME_GENERATION_MAX_TOKENS（最高 32000），重启后端后重试。")
                if not isinstance(raw, str) or not raw.strip() or len(raw) > 300_000:
                    raise ValueError("invalid content")
            except (ValueError, KeyError, IndexError, TypeError):
                raise AppError(502, "GENERATION_OUTPUT_INVALID", "DeepSeek 未返回有效 HTML 内容，请重试；原表单已保留。") from None
            document = prepare_html(raw, parsed.personal_info.model_dump())
            generation = GeneratedResume(uuid4().hex, resume.revision, fingerprint, settings.resume_generation_model, document)
            self.store.save_generation(resume_id, generation)
            return self.metadata(resume_id, generation)
        finally:
            self._lock.release()

    def preview(self, resume_id: str, generation_id: str) -> str:
        record = self.store.get(resume_id, "resume")
        generation = record.generation
        if not generation or generation.generation_id != generation_id or generation.revision != record.response.revision:
            raise AppError(404, "GENERATION_NOT_FOUND", "预览不存在或已因简历更新而失效，请重新制作简历。")
        return generation.html

    @staticmethod
    def metadata(resume_id: str, generation: GeneratedResume) -> ResumeGenerationResponse:
        return ResumeGenerationResponse(generation_id=generation.generation_id, resume_id=resume_id,
                                        revision=generation.revision, model=generation.model,
                                        preview_path=f"/api/resumes/{resume_id}/generations/{generation.generation_id}/preview")

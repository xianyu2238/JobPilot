"""Browser-session backend client, without any model credentials."""

import os
from pathlib import Path

from dotenv import dotenv_values
import httpx


def response_timeout(generation: bool = False) -> float:
    values = dotenv_values(Path(__file__).resolve().parents[1] / ".env")
    try:
        setting = "JOBPILOT_RESUME_GENERATION_TIMEOUT_SECONDS" if generation else "JOBPILOT_PARSE_BUDGET_SECONDS"
        budget = float(os.environ.get(setting) or values.get(setting) or (180 if generation else 300))
        return min(600, max(1, budget)) + 30
    except (TypeError, ValueError):
        return 330


class APIError(Exception):
    def __init__(self, message: str, code: str = "", request_id: str = ""):
        self.code, self.request_id = code, request_id
        super().__init__(message)


def request(base: str, method: str, path: str, **kwargs):
    try:
        # Do not send localhost requests through an operating-system proxy.
        with httpx.Client(timeout=httpx.Timeout(response_timeout(path.endswith("/generate")), connect=5), trust_env=False) as client:
            response = client.request(method, base.rstrip("/") + path, **kwargs)
    except httpx.RequestError:
        raise APIError("无法连接后端或请求超时。请确认后端已启动；解析可能仍在处理，请勿连续重复提交。") from None
    if response.is_error:
        try:
            body = response.json()
            message = body.get("message", "后端请求失败。")
            code = body.get("code", "")
        except ValueError:
            message, code = "后端返回异常，请检查服务状态。", ""
        raise APIError(message, code, response.headers.get("X-Request-ID", ""))
    if response.status_code == 204:
        return None
    binary = response.headers.get("content-type", "").startswith("image/")
    return response.content if binary else response.json()

"""Thread-safe, expiring local storage. Nothing is written to disk."""

from copy import deepcopy
from dataclasses import dataclass, field
from threading import RLock
import time
from uuid import uuid4

from app.core.errors import AppError
from app.schemas.business import ResumeResponse
from app.schemas.export import ExportArtifact


@dataclass
class ResumeRecord:
    response: ResumeResponse
    previews: list[bytes]
    fingerprint: str = ""
    document_warnings: list[str] = field(default_factory=list)
    export: ExportArtifact | None = None


class MemoryRepository:
    def __init__(self, capacity: int = 20, ttl: int = 3600):
        self.capacity, self.ttl = capacity, ttl
        self._items: dict[str, tuple[float, object]] = {}
        self._lock = RLock()

    def _expire(self) -> None:
        now = time.monotonic()
        for key in list(self._items):
            if now - self._items[key][0] >= self.ttl:
                del self._items[key]

    def add(self, kind: str, value: ResumeRecord) -> str:
        with self._lock:
            self._expire()
            if len(self._items) >= self.capacity:
                raise AppError(503, "TEMP_STORE_FULL", "临时数据已满，请清空不再需要的内容或重启后端。")
            key = kind + "_" + uuid4().hex
            value.response.resume_id = key
            self._items[key] = (time.monotonic(), deepcopy(value))
            return key

    def get(self, key: str, kind: str):
        with self._lock:
            self._expire()
            item = self._items.get(key)
            if not item or not key.startswith(kind + "_"):
                raise AppError(404, kind.upper() + "_NOT_FOUND", "临时数据不存在或已过期，请重新上传简历。")
            return deepcopy(item[1])

    def find_document(self, fingerprint: str) -> ResumeRecord | None:
        with self._lock:
            self._expire()
            for _, value in self._items.values():
                if value.fingerprint == fingerprint:
                    return deepcopy(value)
        return None

    def replace(self, key: str, response: ResumeResponse, expected_revision: int) -> ResumeResponse:
        with self._lock:
            record = self.get(key, "resume")
            if record.response.revision != expected_revision:
                raise AppError(409, "RESUME_VERSION_CONFLICT", "简历已更新，请重新加载后再保存或确认。")
            response.resume_id = key
            response.revision = expected_revision + 1
            response.confirmed = False
            record.response = response
            record.export = None
            self._items[key] = (self._items[key][0], deepcopy(record))
            return deepcopy(response)

    def save_export(self, key: str, artifact: ExportArtifact) -> None:
        with self._lock:
            record = self.get(key, "resume")
            if record.response.revision != artifact.revision:
                raise AppError(409, "RESUME_VERSION_CONFLICT", "简历在导出期间已更新，请重新导出当前版本。")
            record.export = artifact
            self._items[key] = (self._items[key][0], record)

    def confirm(self, key: str, confirmed: bool, expected_revision: int | None = None) -> ResumeResponse:
        with self._lock:
            record = self.get(key, "resume")
            if expected_revision is not None and record.response.revision != expected_revision:
                raise AppError(409, "RESUME_VERSION_CONFLICT", "简历已更新，请重新加载后再确认。")
            if confirmed and record.response.parse_status == "text_ready":
                raise AppError(409, "RESUME_NOT_STRUCTURED", "请先整理为五类信息，或手动填写并保存，再进行确认。")
            record.response.confirmed = confirmed
            created = self._items[key][0]
            self._items[key] = (created, record)
            return deepcopy(record.response)

    def delete(self, key: str, kind: str) -> None:
        with self._lock:
            self.get(key, kind)
            del self._items[key]

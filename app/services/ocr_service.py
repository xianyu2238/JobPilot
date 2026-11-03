"""Lazy CPU OCR. No document data is sent to a remote service."""

from io import BytesIO
import logging
import statistics
from threading import RLock
import time

from PIL import Image

from app.core.config import Settings
from app.core.errors import AppError
from app.schemas.business import OCRLine, PageText

logger = logging.getLogger("jobpilot.ocr")


def ordered_text(lines: list[OCRLine]) -> str:
    """Group near-horizontal fragments, then read each row from left to right."""
    if not lines:
        return ""
    tolerance = max(3, statistics.median(max(point[1] for point in line.box) - min(point[1] for point in line.box) for line in lines) * 0.45)
    rows = []
    for line in sorted(lines, key=lambda item: sum(point[1] for point in item.box) / 4):
        center = sum(point[1] for point in line.box) / 4
        if rows and abs(center - rows[-1][0]) <= tolerance:
            rows[-1][1].append(line)
        else:
            rows.append((center, [line]))
    return "\n".join("  ".join(item.text for item in sorted(row, key=lambda item: min(point[0] for point in item.box))) for _, row in rows)


class LocalOCR:
    def __init__(self, settings: Settings):
        self.settings = settings
        self._engine = None
        self._lock = RLock()

    def recognize(self, image: bytes, page: int) -> tuple[PageText, list[str]]:
        started = time.monotonic()
        with self._lock:
            try:
                if self._engine is None:
                    from rapidocr import RapidOCR
                    self._engine = RapidOCR(params={
                        "Global.log_level": "error",
                        "EngineConfig.onnxruntime.intra_op_num_threads": self.settings.ocr_threads,
                        "EngineConfig.onnxruntime.inter_op_num_threads": 1,
                        "Det.limit_side_len": 1600,
                        "Det.limit_type": "max",
                    })
                output = self._engine(image)
            except ImportError:
                raise AppError(503, "OCR_NOT_AVAILABLE", "本地 OCR 依赖未安装，请安装项目 requirements.txt 后重启后端。") from None
            except Exception as exc:
                logger.error("ocr_failed page=%s type=%s", page, type(exc).__name__)
                raise AppError(503, "OCR_FAILED", "本地文字识别失败，请检查 OCR 模型文件或尝试更清晰的图片；可手动选择备用视觉识别。") from None
        texts = output.txts
        if texts is None or not len(texts):
            raise AppError(422, "DOCUMENT_TEXT_EMPTY", "未识别到文字，请上传清晰的简历图片。")
        lines = [OCRLine(text=str(text), confidence=min(1, max(0, float(score))), box=[[float(x), float(y)] for x, y in box])
                 for text, score, box in zip(output.txts, output.scores, output.boxes) if str(text).strip()]
        if not lines:
            raise AppError(422, "DOCUMENT_TEXT_EMPTY", "未识别到文字，请上传清晰的简历图片。")
        low = sum(line.confidence < self.settings.ocr_confidence_threshold for line in lines)
        with Image.open(BytesIO(image)) as source:
            width, height = source.size
        notes = [f"第 {page} 页为本地 OCR 结果，请核对文字与阅读顺序。"]
        if low:
            notes.append(f"第 {page} 页有 {low} 行识别置信度较低，可在预览中标出并人工核对。")
        logger.info("ocr_complete page=%s lines=%s low_confidence=%s duration_s=%.2f", page, len(lines), low, time.monotonic() - started)
        return PageText(page=page, text=ordered_text(lines), method="local_ocr", lines=lines, width=width, height=height), notes

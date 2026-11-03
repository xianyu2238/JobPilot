"""Prepare cached TeX dependencies and render a public synthetic export sample."""

import argparse
from pathlib import Path
import subprocess
import sys

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from app.core.config import Settings
from app.core.errors import AppError
from app.repositories.memory import MemoryRepository
from app.schemas.business import ParsedResume, PersonalInfo, ResumeItem, ResumeResponse, Skill
from app.services.latex_service import LatexExporter, render_sources, source_archive


def sample_resume() -> ResumeResponse:
    parsed = ParsedResume(
        personal_info=PersonalInfo(name="测试同学", phone="13800138000", email="demo@example.com", city="北京",
                                   job_intention="Python 后端 / AI Agent 开发实习", other="以下全部为合成示例，用于验证 PDF 导出。"),
        education=[ResumeItem(title="示例大学 · 计算机科学与技术 · 本科 · 2023.09 - 2027.06",
                              description="课程：数据结构、计算机网络、数据库、软件工程。")],
        experiences=[ResumeItem(title="示例科技有限公司 · 后端开发实习生 · 2026.06 - 2026.09",
                                description="参与内部工具 API 开发，完成参数校验、错误处理与基础测试。\n使用 PostgreSQL 保存业务数据，编写查询和事务回滚样例。")],
        projects=[ResumeItem(title="JobPilot · AI 求职助手",
                             description="使用 FastAPI 构建简历上传、文字识别、结构化整理与岗位建议接口。\n接入本地 OCR，支持 PDF、PNG、JPG/JPEG；表单内容可编辑、保存并用于后续分析。\n实现 LaTeX 模板填充和本地 PDF 导出，内容与排版分离。"),
                  ResumeItem(title="特殊字符与长文本验证",
                             description="技术关键词：C++、Python、SQL、JSON。\n普通文本可包含 50%、Q&A、user_name、{字段}、#标签、$符号，不影响编译。")],
        skills=[Skill(name="Python / FastAPI", description="掌握基础 API 设计、数据校验与异常处理。", level="mentioned"),
                Skill(name="SQL / Git / Docker", description="能够完成关联查询、版本管理与本地容器练习。", level="mentioned")],
    )
    return ResumeResponse(resume_id="synthetic-export-demo", filename="synthetic", parsed_data=parsed,
                          pages=[], warnings=[], revision=1, parse_status="edited")


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--proxy", default="")
    parser.add_argument("--offline", action="store_true")
    parser.add_argument("--layout", choices=["standard", "compact"], default="standard")
    args = parser.parse_args()
    settings = Settings(_env_file=None, latex_allow_downloads=not args.offline, latex_proxy=args.proxy,
                        latex_timeout_seconds=600)
    def runner(command, **kwargs):
        print("Compiling public synthetic sample; initial dependencies may take several minutes...", flush=True)
        result = subprocess.run(command, **kwargs)
        if result.returncode:
            # This helper only compiles the known public sample, never personal data.
            print(result.stderr.decode("utf-8", errors="replace"), flush=True)
            print(result.stdout.decode("utf-8", errors="replace"), flush=True)
        return result
    sources = render_sources(sample_resume(), args.layout)
    try:
        pdf, pages, warnings = LatexExporter(settings, MemoryRepository(), runner).build(sources)
    except AppError as exc:
        raise SystemExit(f"{exc.code}: {exc.message}\nDownloaded dependencies remain cached; rerun this command after checking the connection.") from None
    target = ROOT / "output" / "pdf"
    target.mkdir(parents=True, exist_ok=True)
    (target / "jobpilot-export-demo.pdf").write_bytes(pdf)
    (target / "jobpilot-export-demo-source.zip").write_bytes(source_archive(sources))
    print("Success:", pages, "page(s),", len(pdf), "bytes", flush=True)
    for warning in warnings:
        print("Layout warning:", warning, flush=True)
    print("Sample saved under output/pdf/; cached compiler data stays under .tools/tectonic/cache/.")


if __name__ == "__main__":
    main()

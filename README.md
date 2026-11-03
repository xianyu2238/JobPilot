# JobPilot

轻量级 AI 求职助手，面向 Python 后端与 AI Agent 实习作品开发。

已实现阶段 1 的基础代码：PDF/PNG/JPG/JPEG 本地识别、五类简历信息整理与编辑保存、用户粘贴 JD 后直接分析、简历修改与学习建议，以及带侧边栏的 Streamlit 页面。真实模型和图片识别效果需配置后验收，Agent 与数据库尚未接入。启动、模型配置及新增文件说明见 [阶段 1 使用说明](docs/阶段1使用说明.md)，功能要求见 [阶段 1 计划](项目开发进度计划/阶段1.md)。

## 本地启动（Windows PowerShell）

需要 Python 3.11+ 和 Git。本次实际验证使用 Python 3.14，其他版本尚未验证。以下命令均在项目根目录执行：

```powershell
# 首次创建；如果已有 .venv，则跳过
python -m venv .venv
.\.venv\Scripts\python.exe -m pip install -r requirements-dev.txt

# 仅首次复制；已有 .env 时不要覆盖自己的配置
Copy-Item .env.example .env

.\.venv\Scripts\python.exe -m uvicorn app.main:app --reload --host 127.0.0.1 --port 8000
```

无需激活虚拟环境，也无需修改 PowerShell 执行策略。阶段 0 不需要数据库或 LLM API Key。安装依赖需要访问包源。

以上命令启动后端。阶段 1 还需在 `.env` 配置模型，并在另一个终端启动页面：

```powershell
.\.venv\Scripts\python.exe -m streamlit run frontend/streamlit_app.py --server.address 127.0.0.1
```

打开 http://127.0.0.1:8501 。图片和扫描型 PDF 默认使用本地 OCR，无需视觉模型。点击解析后，模型自动将文字填入五类可编辑表单；也可手动填写。保存并确认后，建议分析使用修改后的内容。远程视觉识别仅作为手动备用。

保存修改后，可在左侧“导出简历”使用 OpenCurve 模板生成 PDF，或下载 LaTeX 源文件。首次需要准备本地编译器与依赖，操作和代码位置见 [PDF 导出说明](docs/PDF导出说明.md)。

本次机器默认的清华镜像下载返回 403，改用官方 PyPI 后安装成功。如遇同样问题，可仅对本次安装指定包源：

```powershell
.\.venv\Scripts\python.exe -m pip install -r requirements-dev.txt --index-url https://pypi.org/simple
```

启动后访问：

- 健康检查：http://127.0.0.1:8000/health ，预期 `{"status":"ok"}`。
- 接口文档：http://127.0.0.1:8000/docs 。Swagger UI 使用 CDN 资源，浏览器需可访问该 CDN；原始模式可通过 `/openapi.json` 查看。

在终端按 `Ctrl+C` 停止服务。端口占用时可改为 `--port 8001` 并访问相应端口。

## 测试

```powershell
.\.venv\Scripts\python.exe -m pytest -q
```

测试覆盖应用启动、配置、识别与结构化、编辑保存、建议分析、LaTeX 导出接口与页面交互。自动测试使用模型和编译器替身，不调用真实模型或数据库；真实 PDF 编译通过 `scripts/warm_latex.py` 单独验收。

2026-11-03 验证结果：Python 3.14.4 下 59 项测试通过；`pip check` 未发现依赖冲突。Starlette 对 HTTPX TestClient 发出 1 条弃用提示，目前不影响测试执行。

## 目录和文件

| 路径 | 放什么 |
| --- | --- |
| `app/main.py` | FastAPI 实例、应用工厂、路由注册 |
| `app/api/` | 健康检查、简历上传/整理/编辑保存/预览/确认、JD 原文分析接口 |
| `app/core/` | 配置、日志、模型客户端、业务错误与技能别名 |
| `app/schemas/` | 健康检查、简历、JD 分析输入、原文证据和建议的数据结构 |
| `app/services/` | PDF/PNG/JPG/JPEG 内容提取、简历结构化、直接对照 JD 给出建议 |
| `app/agents/` | Agent 预留目录，后续放 State、状态图、工具和提示词 |
| `app/models/` | 数据库模型预留目录，阶段 3 放 SQLAlchemy 模型 |
| `tests/` | 健康检查、配置、业务接口、解析、匹配和页面交互测试 |
| `app/prompts/` | 简历抽取提示词 |
| `app/repositories/` | 简历临时存储、过期清理及核对状态 |
| `frontend/` | Streamlit 页面、五类信息编辑器和后端 HTTP 客户端 |
| `examples/` | 合成简历文本与岗位 JD 样例 |
| `scripts/` | 将合成文本生成 PDF/PNG 的工具 |
| `docs/` | MVP 范围、输入输出约定和初始架构说明 |
| `项目开发进度计划/` | 阶段 0–6 的开发任务和验收标准 |
| `.venv/` | 本机 Python 虚拟环境与依赖，不提交 Git |
| `.git/` | 本地 Git 历史及仓库配置，由 Git 管理 |
| `.env.example` / `.env` | 可提交的配置示例 / 不提交的个人配置 |
| `requirements.txt` | 后端运行依赖及兼容版本范围 |
| `requirements-dev.txt` | 开发与测试依赖，包含运行依赖 |
| `pyproject.toml` | pytest 测试目录及导入路径配置 |
| `.gitignore` | 排除虚拟环境、个人配置、PDF、上传数据、缓存等 |

每个 Python 包的 `__init__.py` 用于标记包并说明用途。`agents/` 和 `models/` 仍为后续阶段预留目录。测试后出现的 `__pycache__/`、`.pytest_cache/` 属于可重新生成的缓存。

## Git 与发布到 GitHub

本地仓库初始化不代表已经上传。此项目不替你设置 Git 身份、不自动提交或推送；发布时请先确认文件列表不含个人简历与真实密钥。

在 GitHub 登录你的账号，新建空仓库（例如 `jobpilot`）；不要勾选初始化 README、`.gitignore` 或 License，以便关联现有项目。然后在项目根目录执行：

```powershell
# 查看当前身份；未配置或需要本项目专用身份时再设置
git config user.name
git config user.email
git config user.name "你的名字"
git config user.email "你的邮箱或 GitHub noreply 邮箱"

git status --short
git add .
git diff --cached --stat
git commit -m "chore: initialize JobPilot stage 0"
git branch -M main

# 将地址中的 YOUR_USERNAME 替换为自己的 GitHub 用户名
git remote add origin https://github.com/YOUR_USERNAME/jobpilot.git
git push -u origin main
```

首次推送时按 Git Credential Manager 的提示登录 GitHub。不要把密码或令牌写进仓库地址或代码。若已配置 `origin`，先运行 `git remote -v` 检查，再按需要使用 `git remote set-url origin <仓库地址>`。

本地仓库由开发沙箱初始化。如果自己的终端报告 `detected dubious ownership`，先确认报错路径就是此项目，再执行下面的命令信任此项目目录，然后重试 Git 命令：

```powershell
git config --global --add safe.directory 'E:/wife/找实习/jobPilot'
```

依赖当前使用兼容版本范围，尚未生成用于完全复现环境的锁文件；后续部署阶段应固定验证过的依赖版本。个人简历、`.env`、虚拟环境与数据目录均不应上传。

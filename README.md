# JobPilot

轻量级 AI 求职助手，面向 Python 后端与 AI Agent 实习作品开发。

当前完成阶段 0：FastAPI 工程骨架、配置加载、控制台日志、健康检查与基础测试。简历解析、JD 匹配、Agent、数据库和页面尚未实现。MVP 业务流程与接口草案见 [MVP 设计](docs/MVP设计.md)，阶段任务见 [开发进度计划](项目开发进度计划/阶段0.md)。

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

测试覆盖应用启动、健康检查、文档与 OpenAPI 响应、`.env` 读取、环境变量覆盖和非法日志级别。测试不调用真实模型或数据库。

2026-11-03 验证结果：Python 3.14.4 下 3 项测试通过；实际启动 Uvicorn 后，`/health`、`/docs`、`/openapi.json` 均返回 HTTP 200；`pip check` 未发现依赖冲突。测试依赖 Starlette 对 HTTPX TestClient 发出 1 条弃用提示，目前不影响测试执行。验证用服务已停止，使用时需自行启动。

## 目录和文件

| 路径 | 放什么 |
| --- | --- |
| `app/main.py` | FastAPI 实例、应用工厂、路由注册 |
| `app/api/` | HTTP 接口，当前包含 `health.py`；后续添加简历、岗位、对话接口 |
| `app/core/` | `config.py` 读取并验证配置；`logging.py` 设置应用控制台日志 |
| `app/schemas/` | Pydantic 数据结构，当前包含健康检查响应；后续添加简历、JD 等输入输出模型 |
| `app/services/` | 业务逻辑预留目录，后续放 PDF 抽取、简历解析和岗位匹配 |
| `app/agents/` | Agent 预留目录，后续放 State、状态图、工具和提示词 |
| `app/models/` | 数据库模型预留目录，阶段 3 放 SQLAlchemy 模型 |
| `tests/` | 健康检查、文档和配置测试 |
| `docs/` | MVP 范围、输入输出约定和初始架构说明 |
| `项目开发进度计划/` | 阶段 0–6 的开发任务和验收标准 |
| `.venv/` | 本机 Python 虚拟环境与依赖，不提交 Git |
| `.git/` | 本地 Git 历史及仓库配置，由 Git 管理 |
| `.env.example` / `.env` | 可提交的配置示例 / 不提交的个人配置 |
| `requirements.txt` | 后端运行依赖及兼容版本范围 |
| `requirements-dev.txt` | 开发与测试依赖，包含运行依赖 |
| `pyproject.toml` | pytest 测试目录及导入路径配置 |
| `.gitignore` | 排除虚拟环境、个人配置、PDF、上传数据、缓存等 |

每个 Python 包的 `__init__.py` 用于标记包并说明用途。三个业务预留目录目前只有此文件，未实现业务代码。测试后出现的 `__pycache__/`、`.pytest_cache/` 属于可重新生成的缓存。

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

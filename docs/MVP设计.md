# MVP 范围与初始架构

## 核心流程

上传简历 → 本地识别并保存文字 → 模型整理或手动填写五类信息 → 编辑保存与确认 → 粘贴 JD → 使用 resume_id 和 JD 原文直接获取分析 → 通过 Agent 继续追问。

阶段 0 提供工程骨架；阶段 1 实现简历解析、JD 匹配和带侧边栏的基础 Streamlit 页面；阶段 2 接入单 Agent；阶段 3 接入数据库、完善页面及会话体验，完成 MVP。

功能与验收要求见 [阶段 1 计划](../项目开发进度计划/阶段1.md)。PNG/JPG/JPEG 和扫描型 PDF 默认通过本地 OCR 识别文字，远程视觉模型为手动备用。JD 由用户从招聘渠道复制粘贴，本阶段不自动获取岗位信息。

MVP 不包含自动投递、招聘网站爬虫、复杂多 Agent、完整用户权限平台。搜索、模拟面试、RAG、SSE 属于后续可选增强。

## 输入与输出约定（Agent 接口待实现）

| 接口 | 输入 | 输出 |
| --- | --- | --- |
| `POST /api/resumes` | 文件，`recognition_mode=local`（默认）或 `vision` | `resume_id`、原文、预览、`parse_status=text_ready` |
| `POST /api/resumes/{resume_id}/structure` | `expected_revision` | 五类结构化结果，失败时保留原文 |
| `PUT /api/resumes/{resume_id}` | `expected_revision`、可编辑的 `parsed_data` | 新版本，清除旧确认状态 |
| `GET /api/resumes/{resume_id}` | 简历 ID | `resume_id`、`parsed_data` |
| `GET /api/resumes/{resume_id}/pages/{page}/preview` | 简历 ID、页码 | 页面 PNG 预览 |
| `POST /api/resumes/{resume_id}/confirm` | JSON：`confirmed`、`expected_revision` | 更新后的简历与核对状态 |
| `POST /api/jobs/match` | JSON：`{"resume_id":"...","jd_text":"岗位描述"}` | `overview`、`resume_suggestions`、`learning_suggestions`、`warnings` |
| `POST /api/agent/chat` | JSON：`message`，可选 `resume_id`、`jd_text`、`session_id` | `session_id`、`answer`、`tool_steps`（调用工具及结果摘要） |

ID 在 API 中按字符串传递；具体数据库字段与结构化模型在对应阶段实现。简历字段缺失时使用空值或空列表，不编造信息。匹配分析以简历修改建议和学习建议为主，整体匹配度简要说明；建议关联岗位要求及简历原文，不输出模型随意生成的分数。后续业务错误响应统一为 `code`、`message`、`request_id`。

## 初始架构

```text
Streamlit（阶段 1 起） → HTTP → FastAPI / api
                              ├─ services → PDF / 图片识别 / LLM
                              ├─ agents → 调用已有 services 工具
                              └─ models / 数据访问层 → PostgreSQL（阶段 3）
core 为各层提供配置和日志；schemas 定义接口与结构化结果。
```

API 层处理 HTTP 参数和响应；Service 层承担确定性业务流程；Agent 只负责需要动态选择工具的任务；Model 层负责持久化。数据访问层在引入数据库时增加，不提前实现空的数据库框架。

## 基础接口与配置

- `GET /health`：HTTP 200，`{"status":"ok"}`，仅证明应用进程可响应，不检测数据库或模型服务。
- `GET /docs`：Swagger UI 接口文档；`GET /openapi.json`：接口模式。
- 配置优先级：显式传入值 > 系统环境变量 > 当前工作目录的 `.env` > 默认值。请从项目根目录启动。
- `JOBPILOT_APP_NAME`：应用名称，默认 `JobPilot`。
- `JOBPILOT_ENVIRONMENT`：`development` / `test` / `production`，默认 `development`；当前仅记录运行环境，不启用额外部署能力。
- `JOBPILOT_LOG_LEVEL`：`DEBUG` / `INFO` / `WARNING` / `ERROR` / `CRITICAL`，默认 `INFO`。
- 应用日志输出到控制台，包含时间、级别、模块和消息。Uvicorn 负责 HTTP 访问日志。不记录简历正文、请求体或密钥。

简历分为个人信息、教育背景、实习经历、项目经历和个人技能。用户修改单独标记，原文件和 OCR 原文保留；保存后需重新确认，分析可通过 `resume_revision` 检查版本。

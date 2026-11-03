# MVP 范围与初始架构

## 核心流程

上传可提取文字的 PDF 简历 → 获得结构化简历和 resume_id → 输入 JD 并获得 job_id → 根据两个 ID 获取匹配分析 → 通过 Agent 继续追问。

阶段 0 只提供工程骨架、配置、日志和健康检查。阶段 1 实现解析与匹配，阶段 2 接入单 Agent，阶段 3 接入数据库和 Streamlit 页面，完成 MVP。

MVP 不包含自动投递、招聘网站爬虫、复杂多 Agent、完整用户权限平台。搜索、模拟面试、RAG、SSE 属于后续可选增强。

## 输入与输出约定（待实现接口）

| 接口 | 输入 | 输出 |
| --- | --- | --- |
| `POST /api/resumes` | multipart/form-data，`file` 为 PDF | `resume_id`、`parsed_data`（基本信息、技能、教育、经历、项目） |
| `GET /api/resumes/{resume_id}` | 简历 ID | `resume_id`、`parsed_data` |
| `POST /api/jobs` | JSON：`{"jd_text":"岗位描述"}` | `job_id`、`requirements`（硬性要求、加分项） |
| `POST /api/jobs/match` | JSON：`{"resume_id":"...","job_id":"..."}` | `matched_skills`、`missing_skills`、`evidence`、`suggestions` |
| `POST /api/agent/chat` | JSON：`message`，可选 `resume_id`、`job_id`、`session_id` | `session_id`、`answer`、`tool_steps`（调用工具及结果摘要） |

ID 在 API 中按字符串传递；具体数据库字段与结构化模型在对应阶段实现。简历字段缺失时使用空值或空列表，不编造信息。匹配证据应包含技能及简历原文片段，第一版不输出模型随意生成的分数。后续业务错误响应统一为 `code`、`message`、`request_id`。

## 初始架构

```text
Streamlit（阶段 3） → HTTP → FastAPI / api
                              ├─ services → PDF / LLM
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

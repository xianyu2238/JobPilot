# DeepSeek 制作 HTML 简历

## 使用流程

保存左侧表单 → 右侧“制作简历”选择通用/针对岗位 → 点击“使用 DeepSeek 制作简历” → 点击“打开简历预览”，在新页面查看效果。

可填写简短的排版与表达要求。针对岗位时需要填写上方 JD；生成只读取已保存的五类信息，不重复 OCR，也不发送原文件或证据数据。修改表单、制作要求或目标岗位后需重新制作。不提供新旧内容对照。

生成的完整 HTML/CSS 由 DeepSeek 设计，后端校验基本结构、姓名及联系方式，清理脚本等活动内容，并通过独立预览链接展示。原表单不被生成结果覆盖。模型仍可能遗漏或误写其他事实，请核对后使用。

## 模型配置

默认使用用户提供的接口：

```dotenv
JOBPILOT_RESUME_GENERATION_BASE_URL=https://aihubmix.com/v1
JOBPILOT_RESUME_GENERATION_MODEL=deepseek-v4.1-flash-1017
JOBPILOT_RESUME_GENERATION_TIMEOUT_SECONDS=180
JOBPILOT_RESUME_GENERATION_MAX_TOKENS=24000
JOBPILOT_RESUME_GENERATION_ENABLE_THINKING=false
```

密钥读取后端 `.env` 中的 `AIHUBMIX_API_KEY`，也可单独设置 `JOBPILOT_RESUME_GENERATION_API_KEY`；如现有简历模型使用相同服务地址，则可复用已有 `JOBPILOT_LLM_API_KEY`。密钥不会发送到前端，`.env` 已被 Git 忽略。修改配置后重启后端。

使用现有 HTTPX 请求 OpenAI 兼容的 `/chat/completions` 接口，无需新增 Python 依赖。HTML 输出通常超过示例 Hello 请求的 1024 tokens，因此默认允许 24000 tokens，并显式关闭思考模式，避免思考过程占用 HTML 输出额度；截断会明确报错，不展示残缺页面。请求超时或失败不会自动反复调用模型。

## 提示词与代码

提示词在 `app/prompts/resume_generation.txt`，可直接调整。主要要求：保留真实经历及全部条目；白纸、深灰文字、单一蓝/青强调色；A4 居中、统一字号和间距；长标题换行、长内容可分页；窄屏适配；不使用外部资源或脚本；只返回完整 HTML。

| 文件 | 功能 |
| --- | --- |
| `app/services/resume_generation_service.py` | 发送保存后的表单给 DeepSeek，处理超时、截断、版本与缓存 |
| `app/services/resume_html.py` | HTML 清理、基本事实检查及预览隔离策略 |
| `app/schemas/resume_generation.py` | 请求、响应和生成记录结构 |
| `frontend/resume_generation.py` | 制作选项、按钮和跳转链接 |
| `tests/test_resume_generation.py` | 模型请求、异常、HTML 安全和版本失效测试 |

接口：`POST /api/resumes/{id}/generate` 制作，返回 `preview_path`；`GET /api/resumes/{id}/generations/{generation_id}/preview` 打开页面。预览链接仅随临时简历保存在内存中，修改并保存简历、重新生成其他版本、删除、过期或后端重启后会失效；链接不应公开分享。

本次只实现 HTML 生成与链接预览；需要 PDF 时可在预览页使用浏览器打印。没有恢复 LaTeX 或安装 PDF 编译器。

## 验证

使用合成简历调用真实 AiHubMix DeepSeek，约 27 秒生成 HTML；检查了桌面浏览器效果。自动测试覆盖模型请求、已保存内容、链接打开、修改后失效、超时、截断和活动内容清理。

排错：日志 `model_output stage=ResumeHTML` 记录结束原因、输出用量、思考用量和 HTML 字符数，不记录正文。遇到截断先确认已关闭思考，并重启后端加载配置；必要时将上限调整到 32000，不会自动删减简历或无限重试。

关闭思考后的补充验收：合成长材料通过真实 AiHubMix 调用生成完整 HTML，finish_reason=stop，输出 1331 tokens，约 6.8 秒。该耗时仅代表合成样例，不代表所有简历。68 项自动测试通过。

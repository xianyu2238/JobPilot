# 简历 PDF 导出

## 使用

启动后端和 Streamlit，在左侧修改简历并点击“保存修改”，再点击“导出 PDF”，生成后点击“下载 PDF”。可选择标准或紧凑排版，也能单独下载 LaTeX 源文件 ZIP。

导出使用已保存的五类信息，不再调用模型。空栏目自动隐藏，特殊字符自动转义；内容超出一页时保留全文并提示页数，不自动删减经历。修改内容后需要重新导出。

## 首次准备编译环境

在项目根目录执行（Windows x64）：

```powershell
.\.venv\Scripts\python.exe scripts/setup_latex.py
.\.venv\Scripts\python.exe scripts/warm_latex.py
```

如下载需要本地代理，两条命令后都加 `--proxy http://127.0.0.1:7897`。预热会生成全部为虚构内容的示例 `output/pdf/jobpilot-export-demo.pdf`，同时缓存中文模板依赖。完成后可用下列命令检查离线编译：

```powershell
.\.venv\Scripts\python.exe scripts/warm_latex.py --offline
```

编译器放在 `.tools/tectonic/`，不修改系统 PATH，不提交 Git。日常导出默认只使用缓存，首次下载不会阻塞用户请求。也可使用已有 XeLaTeX，在 `.env` 设置 `JOBPILOT_LATEX_ENGINE=xelatex` 和 `JOBPILOT_LATEX_BINARY` 为可执行文件路径。

首次预热可能需要数分钟；如果网络较慢导致超时，可重复执行预热命令，已下载的依赖会保留。

## 代码位置

| 文件 | 作用 |
| --- | --- |
| `app/services/latex_service.py` | 填充、转义、编译、源文件打包、版本校验 |
| `app/schemas/export.py` | 导出请求、响应和缓存结构 |
| `app/templates/opencurve/` | 主模板、四类栏目模板、样式、上游版本与 MIT 许可 |
| `frontend/resume_export.py` | 排版选择、生成与下载按钮 |
| `scripts/setup_latex.py` | 下载固定版本 Tectonic 并校验 SHA-256 |
| `scripts/warm_latex.py` | 预热依赖、生成合成样例、离线检查 |
| `tests/test_export.py` | 导出接口、字符转义、缓存失效、超时和版本冲突测试 |

接口在 `app/api/resumes.py`：`POST /{id}/export` 编译，`POST /{id}/export/source` 直接下载源文件，`GET /{id}/exports/{export_id}/pdf` 或 `/source` 下载结果；以上路径前缀均为 `/api/resumes`。

模板来自 [OpenCurve-Resume](https://github.com/heylong7/OpenCurve-Resume)，固定上游提交见 `UPSTREAM.md`。姓名、联系方式在主模板，其余字段填入 `sections/`；没有添加上游样例中的虚构履历或头像。

临时编译目录结束后清理，导出结果仅随简历存放在后端内存中，重启或简历过期会失效，请及时下载。导出时禁用 shell escape，普通简历文字不作为 LaTeX 命令执行。

## 本次验证

59 项自动测试通过，依赖检查通过。使用真实 Tectonic 生成并渲染检查了中文单页样例及长内容双页样例，验证了特殊字符、长标题换行、末尾内容完整，以及保存修改后的版本进入 PDF。离线缓存下双页样例导出约 2.85 秒；耗时会随机器和内容变化。

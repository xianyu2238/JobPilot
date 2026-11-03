"""Download exports of the saved revision; draft changes invalidate buttons."""

import streamlit as st

import frontend.api_client as api


def render_export(base, resume, dirty, show_error):
    state = st.session_state
    st.divider()
    st.subheader("导出简历")
    label = st.selectbox("排版", ["标准", "紧凑"], key="export_layout")
    layout = "compact" if label == "紧凑" else "standard"
    key = (resume["resume_id"], resume["revision"], layout)
    if state.get("resume_export_key") != key or dirty:
        state.pop("resume_export", None)
        state.resume_export_key = key
    disabled = dirty or resume["parse_status"] == "text_ready"
    st.caption(f"导出当前已保存版本 r{resume['revision']}，采用 OpenCurve 模板。")
    if dirty:
        st.caption("请先保存修改，再导出 PDF。")
    create_pdf, create_source = st.columns(2)
    payload = {"expected_revision": resume["revision"], "layout": layout}
    path = f"/api/resumes/{resume['resume_id']}"
    with create_pdf:
        if st.button("导出 PDF", disabled=disabled, type="primary", width="stretch"):
            try:
                with st.spinner("正在填充模板并编译 PDF…"):
                    metadata = api.request(base, "POST", path + "/export", json=payload)
                    download = path + f"/exports/{metadata['export_id']}"
                    pdf = api.request(base, "GET", download + "/pdf")
                    source = api.request(base, "GET", download + "/source")
                state.resume_export = {"pdf": pdf, "source": source, "metadata": metadata}
            except api.APIError as exc:
                show_error(exc)
    with create_source:
        if st.button("导出 LaTeX 源文件", disabled=disabled, width="stretch"):
            try:
                content = api.request(base, "POST", path + "/export/source", json=payload)
                existing = state.get("resume_export", {})
                state.resume_export = {**existing, "source": content}
            except api.APIError as exc:
                show_error(exc)
    result = state.get("resume_export")
    if result:
        metadata = result.get("metadata")
        if metadata:
            st.success(f"PDF 已生成，共 {metadata['page_count']} 页。")
            for warning in metadata["warnings"]:
                st.warning(warning)
        if result.get("pdf"):
            st.download_button("下载 PDF", data=result["pdf"], file_name=f"jobpilot-resume-r{resume['revision']}.pdf",
                               mime="application/pdf", key="download_resume_pdf", width="stretch")
        if result.get("source"):
            st.download_button("下载 LaTeX 源文件 ZIP", data=result["source"], file_name=f"jobpilot-resume-r{resume['revision']}-source.zip",
                               mime="application/zip", key="download_resume_source", width="stretch")

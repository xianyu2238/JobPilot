"""Generate HTML from saved form data and open it in a separate browser tab."""

import streamlit as st

from frontend.api_client import APIError, request


def render_generation(base, resume, dirty, jd_text, show_error):
    st.subheader("制作简历")
    state = st.session_state
    use_jd = st.selectbox("制作方式", ["通用简历", "针对当前岗位"], key="generation_mode") == "针对当前岗位"
    instructions = st.text_area("排版与表达要求（可选）", max_chars=1000, height=90, key="generation_instructions",
                                placeholder="例如：简洁蓝白风格，突出项目实践，保留全部经历。")
    signature = (resume["resume_id"], resume["revision"], use_jd, jd_text if use_jd else "", instructions) if resume else None
    if state.get("generation_signature") != signature:
        state.pop("generated_resume", None)
        state.generation_signature = signature
    if dirty:
        state.pop("generated_resume", None)
    disabled = not resume or dirty or resume["parse_status"] == "text_ready" or (use_jd and not jd_text.strip())
    if dirty:
        st.caption("请先保存左侧修改，再制作简历。")
    elif not resume:
        st.caption("先上传并整理简历，或填写表单并保存。")
    else:
        st.caption(f"使用已保存版本 r{resume['revision']}，由 DeepSeek 生成完整 HTML 排版。")
    if use_jd and not jd_text.strip():
        st.caption("请先在上方填写目标岗位 JD。")
    if st.button("使用 DeepSeek 制作简历", disabled=disabled, type="primary", width="stretch"):
        try:
            with st.spinner("DeepSeek 正在制作简历，请等待…"):
                result = request(base, "POST", f"/api/resumes/{resume['resume_id']}/generate", json={
                    "expected_revision": resume["revision"], "use_jd": use_jd,
                    "jd_text": jd_text if use_jd else "", "instructions": instructions,
                })
            state.generated_resume = result
        except APIError as exc:
            show_error(exc)
    if state.get("generated_resume"):
        result = state.generated_resume
        st.success("简历 HTML 已生成，点击下方链接查看排版。")
        st.link_button("打开简历预览 ↗", url=base.rstrip("/") + result["preview_path"], width="stretch")
        st.caption("预览在新页面打开。请核对生成内容；修改表单后需重新制作。链接在后端重启或临时数据过期后失效。")

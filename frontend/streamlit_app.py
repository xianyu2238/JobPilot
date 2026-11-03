"""Local OCR, editable resume review, and direct-JD advice."""

import hashlib
import os
from pathlib import Path
import sys

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from dotenv import dotenv_values
import streamlit as st

from frontend.api_client import APIError, request
from frontend.resume_editor import render_editor
from frontend.resume_generation import render_generation

st.set_page_config(page_title="JobPilot · 求职助手", page_icon="🧭", layout="wide")
local_config = dotenv_values(Path(__file__).resolve().parents[1] / ".env")
BASE = os.environ.get("JOBPILOT_API_BASE_URL", local_config.get("JOBPILOT_API_BASE_URL") or "http://127.0.0.1:8000")
state = st.session_state
for key, value in {"resume": None, "result": None, "file_signature": None, "jd_snapshot": "",
                   "confirmed": False, "epoch": 0, "editor_dirty": False, "pending_structure": False}.items():
    if key not in state:
        state[key] = value


def show_error(exc):
    st.error(str(exc))
    if exc.request_id:
        st.caption("请求编号：" + exc.request_id)
    if exc.code in {"RESUME_NOT_FOUND", "RESUME_VERSION_CONFLICT"}:
        st.warning("临时数据过期或版本已更新，请重新上传或加载已保存版本。")


def show_warnings(warnings):
    hidden_notes = ("为本地 OCR 结果，请核对文字与阅读顺序。", "行识别置信度较低，可在预览中标出并人工核对。")
    for warning in warnings:
        if not any(note in warning for note in hidden_notes):
            st.warning(warning)


def discard(response):
    if not response:
        return True
    try:
        request(BASE, "DELETE", f"/api/resumes/{response['resume_id']}")
        return True
    except APIError as exc:
        if exc.code == "RESUME_NOT_FOUND":
            return True
        st.warning("旧临时数据未删除，可恢复后端连接后重试清空。")
        return False


def invalidate_resume():
    state.resume, state.result = None, None
    state.confirmed, state.editor_dirty, state.pending_structure = False, False, False
    state.pop("confirm_checkbox", None)
    state.pop("editor_signature", None)
    state.pop("editor_draft", None)
    state.pop("generated_resume", None)


with st.sidebar:
    st.title("🧭 JobPilot")
    st.caption("把经历说清楚，把下一步想明白")
    st.button("简历与岗位匹配", type="primary", width="stretch", disabled=True)
    st.divider()
    for label in ["Agent 助手", "岗位调研", "模拟面试", "知识库", "历史记录"]:
        st.button(label + " · 待实现", disabled=True, width="stretch")
    st.divider()
    st.caption("本地演示 · 临时保存，重启后失效")
    if st.button("清空本次内容", width="stretch"):
        if discard(state.resume):
            epoch = state.epoch + 1
            state.clear()
            state.epoch = epoch
            st.rerun()

st.title("简历优化工作台")
st.caption("左侧整理个人经历，右侧对照目标岗位，生成修改建议与学习计划。")
if state.get("flash_message"):
    st.success(state.pop("flash_message"))
left, right = st.columns([1.15, 1], gap="large")

with left:
    st.header("我的简历")
    with st.container(border=True):
        st.subheader("上传与解析")
        uploaded = st.file_uploader("上传 PDF、PNG 或 JPG/JPEG 简历", type=["pdf", "png", "jpg", "jpeg"], key=f"upload_{state.epoch}")
        mode = "local" 
        st.caption("支持 PDF 和图片，默认最多 5 MiB、PDF 最多 5 页。")
        data = uploaded.getvalue() if uploaded else None
        signature = hashlib.sha256(uploaded.name.encode() + data + mode.encode()).hexdigest() if uploaded else None
        if signature != state.file_signature:
            discard(state.resume)
            invalidate_resume()
            state.file_signature = signature
        if st.button("解析简历", disabled=not uploaded, type="primary", width="stretch"):
            previous = state.resume
            invalidate_resume()
            if len(data) > 5 * 1024 * 1024:
                st.error("文件最多 5 MiB，请精简后重试。")
                state.resume = previous
            else:
                try:
                    with st.spinner("正在识别简历文字…"):
                        state.resume = request(BASE, "POST", "/api/resumes", params={"recognition_mode": mode}, files={"file": (uploaded.name, data, uploaded.type)})
                    discard(previous)
                    state.pending_structure = True
                    st.rerun()
                except APIError as exc:
                    state.resume = previous
                    show_error(exc)
    if state.resume:
        st.subheader("简历信息")
        show_warnings(state.resume["warnings"])
        ready = state.resume["parse_status"] == "text_ready"
        if ready and state.pending_structure:
            state.pending_structure = False
            try:
                with st.spinner("正在整理个人信息、教育背景、实习经历、项目经历和个人技能…"):
                    state.resume = request(BASE, "POST", f"/api/resumes/{state.resume['resume_id']}/structure", json={"expected_revision": state.resume["revision"]})
                state.confirmed, state.result = False, None
                state.pop("confirm_checkbox", None)
                st.rerun()
            except APIError as exc:
                show_error(exc)
        render_editor(BASE, state.resume, show_error)
        ready_to_confirm = state.resume["parse_status"] != "text_ready" and not state.editor_dirty
        confirmed = st.checkbox("我已核对并确认当前已保存的简历信息。", key="confirm_checkbox", disabled=not ready_to_confirm)
        if confirmed != state.confirmed and ready_to_confirm:
            try:
                state.resume = request(BASE, "POST", f"/api/resumes/{state.resume['resume_id']}/confirm", json={"confirmed": confirmed, "expected_revision": state.resume["revision"]})
                state.confirmed, state.result = confirmed, None
            except APIError as exc:
                state.confirmed, state.result = False, None
                show_error(exc)
    else:
        with st.container(border=True):
            st.caption("上传并解析后，个人信息与经历会自动填入这里，可逐条修改。")

with right:
    st.header("目标岗位")
    with st.container(border=True):
        st.subheader("岗位描述")
        jd = st.text_area("粘贴招聘 JD", value=state.jd_snapshot, height=260, max_chars=15000,
                          key=f"jd_{state.epoch}", placeholder="粘贴岗位职责、技能要求与加分项…")
        if jd != state.jd_snapshot:
            state.result, state.jd_snapshot = None, jd
        st.caption("完成左侧简历确认后，开始生成针对这个岗位的建议。")
        if st.button("开始分析", type="primary", width="stretch",
                     disabled=not (state.resume and jd.strip() and state.confirmed and not state.editor_dirty)):
            state.result = None
            try:
                with st.spinner("正在分析匹配情况与改进方向…"):
                    state.result = request(BASE, "POST", "/api/jobs/match", json={"resume_id": state.resume["resume_id"], "jd_text": jd, "resume_revision": state.resume["revision"]})
            except APIError as exc:
                show_error(exc)
    render_generation(BASE, state.resume, state.editor_dirty, jd, show_error)
    st.divider()
    st.subheader("修改建议与学习计划")
    if state.result:
        result = state.result
        st.info(result["overview"])
        edits_tab, learn_tab = st.tabs(["简历修改建议", "学习建议"])
        with edits_tab:
            for index, advice in enumerate(result["resume_suggestions"], start=1):
                with st.container(border=True):
                    st.markdown(f"**{index}. {advice['target']}** · {advice['priority']}优先级")
                    st.write(advice["reason"])
                    st.write(advice["action"])
                    with st.expander("查看分析依据"):
                        if advice["original_quote"]:
                            st.caption("简历内容")
                            st.text(advice["original_quote"])
                        st.caption("岗位描述")
                        st.text(advice["jd_quote"])
        with learn_tab:
            if not result["learning_suggestions"]:
                st.success("暂无明确的新增学习项，可继续巩固已有经验。")
            for advice in result["learning_suggestions"]:
                with st.container(border=True):
                    st.markdown(f"**{advice['topic']}** · {advice['priority']}优先级")
                    st.write(advice["task"])
                    st.caption("预期成果：" + advice["deliverable"])
                    with st.expander("查看岗位依据"):
                        st.text(advice["jd_quote"])
        show_warnings(result["warnings"])
    else:
        with st.container(border=True):
            st.markdown("**让建议落到具体内容上**")
            st.write("分析后会展示简要匹配情况、可操作的简历修改建议，以及按优先级排列的学习任务。")

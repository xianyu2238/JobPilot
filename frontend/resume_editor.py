"""Five-section resume editor with multiline entry cards and stable draft IDs."""

from uuid import uuid4

import pandas as pd
import streamlit as st
import frontend.api_client as api



def mark_dirty():
    st.session_state.editor_dirty = True
    st.session_state.confirmed = False
    st.session_state.result = None
    st.session_state.confirm_checkbox = False
    st.session_state.pop("resume_export", None)


def editable_payload(parsed):
    return {
        "personal_info": dict(parsed.get("personal_info", {})),
        **{field: [{"title": item["title"], "description": item["description"]} for item in parsed[field]]
           for field in ("education", "experiences", "projects")},
        "skills": [{"name": item["name"], "description": item.get("description", ""), "level": item["level"]} for item in parsed["skills"]],
    }


def render_editor(base, resume, show_error):
    state = st.session_state
    generation = state.get("editor_generation", 0)
    signature = f"{resume['resume_id']}_{resume['revision']}_{generation}"
    if state.get("editor_signature") != signature or "editor_draft" not in state:
        state.editor_signature = signature
        state.editor_dirty = False
        state.editor_draft = editable_payload(resume["parsed_data"])
        for field in ("education", "experiences", "projects", "skills"):
            for item in state.editor_draft[field]:
                item["_uid"] = uuid4().hex
    draft = state.editor_draft
    st.caption("逐条修改内容；新增或删除记录后，点击下方保存。长文本可直接在文本框中编辑。")
    st.subheader("个人信息")
    labels = [("name", "姓名"), ("phone", "电话"), ("email", "邮箱"), ("city", "所在城市")]
    columns = st.columns(2)
    for index, (field, label) in enumerate(labels):
        with columns[index % 2]:
            draft["personal_info"][field] = st.text_input(
                label, value=draft["personal_info"].get(field) or "", key=f"editor_{field}_{signature}",
                on_change=mark_dirty, max_chars=200 if field == "email" else 100,
            ).strip() or None
    draft["personal_info"]["job_intention"] = st.text_input("求职意向", value=draft["personal_info"].get("job_intention") or "",
        key=f"editor_job_intention_{signature}", on_change=mark_dirty, max_chars=200).strip() or None
    draft["personal_info"]["other"] = st.text_area("其他个人信息", value=draft["personal_info"].get("other") or "",
        key=f"editor_other_{signature}", on_change=mark_dirty, max_chars=1000, height=90).strip() or None

    groups = [("education", "教育背景", "学校 / 专业 / 学历 / 时间", "教育信息", 120),
              ("experiences", "实习经历", "公司 / 岗位 / 时间", "工作职责与成果", 180),
              ("projects", "项目经历", "项目名称 / 时间", "项目具体内容", 220)]
    for field, label, title_label, content_label, height in groups:
        st.divider()
        st.subheader(label)
        if not draft[field]:
            st.caption("暂无记录，可点击下方添加。")
        for index, item in enumerate(draft[field]):
            uid = item["_uid"]
            with st.container(border=True):
                st.markdown(f"**{label} {index + 1}**")
                item["title"] = st.text_input(title_label, value=item["title"], max_chars=200,
                    key=f"editor_{field}_title_{signature}_{uid}", on_change=mark_dirty)
                item["description"] = st.text_area(content_label, value=item["description"], height=height, max_chars=3000,
                    key=f"editor_{field}_description_{signature}_{uid}", on_change=mark_dirty)
                if st.button("删除这条记录", key=f"delete_{field}_{uid}"):
                    draft[field] = [row for row in draft[field] if row["_uid"] != uid]
                    mark_dirty()
                    st.rerun()
        if st.button("添加" + label, key=f"add_{field}", disabled=len(draft[field]) >= 30, width="stretch"):
            draft[field].append({"title": "", "description": "", "_uid": uuid4().hex})
            mark_dirty()
            st.rerun()

    st.divider()
    st.subheader("个人技能")
    st.caption("在同一张表中填写技能与详细介绍，可直接新增或删除行。")
    if state.get("editor_skills_signature") != signature:
        state.editor_skills_signature = signature
        state.editor_skills_base = [dict(item) for item in draft["skills"]]
    base_skills = state.editor_skills_base
    rows = [{"技能": item["name"], "详细介绍": item["description"], "_uid": item["_uid"]} for item in base_skills]
    table = st.data_editor(
        pd.DataFrame(rows, columns=["技能", "详细介绍", "_uid"]),
        num_rows="dynamic", hide_index=True, width="stretch",
        key=f"editor_skills_table_{signature}", on_change=mark_dirty,
        column_config={
            "技能": st.column_config.TextColumn(required=True, max_chars=100, width="small"),
            "详细介绍": st.column_config.TextColumn(max_chars=2000, width="large"),
            "_uid": None,
        },
    ).fillna("")
    originals = {item["_uid"]: item for item in base_skills}
    draft["skills"] = []
    for row in table.to_dict("records"):
        name, description = str(row["技能"]).strip(), str(row["详细介绍"]).strip()
        if not name and not description:
            continue
        original = originals.get(row["_uid"])
        unchanged = original and name == original["name"] and description == original["description"]
        draft["skills"].append({"name": name, "description": description,
                                "level": original["level"] if unchanged else "mentioned"})

    values = {"personal_info": draft["personal_info"]}
    for field in ("education", "experiences", "projects"):
        values[field] = [{"title": item["title"].strip(), "description": item["description"].strip()}
                         for item in draft[field] if item["title"].strip() or item["description"].strip()]
    values["skills"] = [{"name": item["name"].strip(), "description": item["description"].strip(), "level": item["level"]}
                        for item in draft["skills"] if item["name"].strip() or item["description"].strip()]
    st.divider()
    if state.editor_dirty:
        st.warning("有未保存的修改。保存后请重新确认，再开始分析。")
    save, cancel = st.columns(2)
    with save:
        if st.button("保存修改", type="primary", disabled=not state.editor_dirty, width="stretch"):
            invalid = any(not item["title"] or not item["description"] for field in ("education", "experiences", "projects") for item in values[field])
            if len(values["skills"]) > 80:
                st.error("个人技能最多保存 80 项，请精简后保存。")
            elif invalid or any(not item["name"] for item in values["skills"]):
                st.error("请填写记录的名称和内容、技能名称，或删除不需要的空记录。")
            else:
                try:
                    state.resume = api.request(base, "PUT", f"/api/resumes/{resume['resume_id']}",
                                               json={"expected_revision": resume["revision"], "parsed_data": values})
                    state.confirmed, state.editor_dirty, state.result = False, False, None
                    state.confirm_checkbox = False
                    state.flash_message = "修改已保存，请重新核对确认。"
                    st.rerun()
                except api.APIError as exc:
                    show_error(exc)
    with cancel:
        if st.button("放弃未保存修改", disabled=not state.editor_dirty, width="stretch"):
            state.editor_generation = generation + 1
            state.editor_dirty = False
            st.rerun()

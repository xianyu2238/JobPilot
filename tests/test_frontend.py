"""Streamlit interaction checks without a browser or model service."""

from pathlib import Path

from streamlit.testing.v1 import AppTest


def test_generate_html_link_uses_saved_form_and_invalidates(monkeypatch, client, application):
    import json
    import html
    import httpx
    import frontend.api_client as api
    from conftest import pdf_bytes

    application.state.settings.resume_generation_api_key = "fake-generation-key"
    calls = []
    def completion(request):
        body = json.loads(request.content)
        payload = json.loads(body["messages"][1]["content"])
        calls.append(payload)
        name = html.escape(payload["resume"]["personal_info"]["name"])
        content = '<!doctype html><html><head><style>body{color:#123}</style></head><body><h1>'+name+'</h1><p>项目经历：Python FastAPI</p></body></html>'
        return httpx.Response(200,json={"choices":[{"message":{"content":content}}]})
    application.state.resume_generator.transport = httpx.MockTransport(completion)
    def through_backend(base, method, path, **kwargs):
        response=client.request(method,path,**kwargs)
        if response.is_error:
            body=response.json()
            raise api.APIError(body["message"],body["code"],body["request_id"])
        return None if response.status_code==204 else response.json()
    monkeypatch.setattr(api,"request",through_backend)
    # The generation module imports request directly; use the same backend adapter.
    import frontend.resume_generation as generation
    monkeypatch.setattr(generation,"request",through_backend)
    page=AppTest.from_file(Path(__file__).resolve().parents[1]/"frontend"/"streamlit_app.py").run()
    assert next(b for b in page.button if b.label=="使用 DeepSeek 制作简历").disabled
    page.file_uploader[0].upload("resume.pdf",pdf_bytes(),"application/pdf").run()
    next(b for b in page.button if b.label=="解析简历").click().run()
    page.text_input[0].input("HTML Edited Candidate").run()
    assert next(b for b in page.button if b.label=="使用 DeepSeek 制作简历").disabled
    next(b for b in page.button if b.label=="保存修改").click().run()
    next(b for b in page.button if b.label=="使用 DeepSeek 制作简历").click().run()
    assert not page.exception
    assert calls[0]["resume"]["personal_info"]["name"]=="HTML Edited Candidate"
    result=page.session_state["generated_resume"]
    assert any(link.proto.url.endswith(result["preview_path"]) for link in page.get("link_button"))
    assert client.get(result["preview_path"]).status_code==200
    page.text_input[0].input("Another edit").run()
    assert "generated_resume" not in page.session_state
    assert not page.get("link_button")


def test_initial_page_has_no_extraction_button_and_upload_failure(monkeypatch):
    from frontend.api_client import APIError
    from conftest import pdf_bytes
    import frontend.api_client as api

    calls = []
    def unavailable(base, method, path, **kwargs):
        calls.append(path)
        raise APIError("后端未启动", "LLM_NOT_CONFIGURED", "test-request")
    monkeypatch.setattr(api, "request", unavailable)
    page = AppTest.from_file(Path(__file__).resolve().parents[1] / "frontend" / "streamlit_app.py").run()
    assert not page.exception
    assert sum("待实现" in button.label for button in page.sidebar.button) == 5
    assert not any(widget.key == "consent" for widget in page.checkbox)
    assert {heading.value for heading in page.header} >= {"我的简历", "目标岗位"}
    assert next(button for button in page.button if button.label == "开始分析").disabled
    page.text_area(key=f"jd_{page.session_state['epoch']}").input("Python backend role").run()
    assert not calls
    assert not any(button.label == "提取岗位要求" for button in page.button)
    page.file_uploader[0].upload("resume.pdf", pdf_bytes(), "application/pdf").run()
    next(button for button in page.button if button.label == "解析简历").click().run()
    assert not page.exception
    assert any("后端未启动" in item.value for item in page.error)
    assert calls == ["/api/resumes"]


def test_upload_confirm_analyze_and_invalidate(monkeypatch, client):
    import frontend.api_client as api
    from conftest import JD, pdf_bytes

    def through_backend(base, method, path, **kwargs):
        response = client.request(method, path, **kwargs)
        if response.is_error:
            body = response.json()
            raise api.APIError(body["message"], body["code"], body["request_id"])
        if response.status_code == 204:
            return None
        return response.content if response.headers.get("content-type", "").startswith("image/") else response.json()
    monkeypatch.setattr(api, "request", through_backend)
    page = AppTest.from_file(Path(__file__).resolve().parents[1] / "frontend" / "streamlit_app.py").run()
    page.file_uploader[0].upload("resume.pdf", pdf_bytes(), "application/pdf").run()
    next(button for button in page.button if button.label == "解析简历").click().run()
    assert not page.exception
    assert page.session_state["resume"] is not None
    assert next(button for button in page.button if button.label == "开始分析").disabled
    page.checkbox(key="confirm_checkbox").check().run()
    assert page.session_state["confirmed"] is True
    page.text_area(key=f"jd_{page.session_state['epoch']}").input(JD).run()
    next(button for button in page.button if button.label == "开始分析").click().run()
    assert not page.exception
    assert page.session_state["result"]["resume_suggestions"]
    page.text_area(key=f"jd_{page.session_state['epoch']}").input(JD + " New role text.").run()
    assert page.session_state["result"] is None
    assert not next(button for button in page.button if button.label == "开始分析").disabled
    page.file_uploader[0].clear().upload("updated.pdf", pdf_bytes(), "application/pdf").run()
    assert not page.exception
    assert page.session_state["resume"] is None
    assert page.session_state["confirmed"] is False


def test_edit_save_reconfirm_and_analyze_uses_saved_version(monkeypatch, client):
    import frontend.api_client as api
    from conftest import JD, pdf_bytes

    def through_backend(base, method, path, **kwargs):
        response = client.request(method, path, **kwargs)
        if response.is_error:
            body = response.json()
            raise api.APIError(body["message"], body["code"], body["request_id"])
        if response.status_code == 204:
            return None
        return response.content if response.headers.get("content-type", "").startswith("image/") else response.json()
    monkeypatch.setattr(api, "request", through_backend)
    page = AppTest.from_file(Path(__file__).resolve().parents[1] / "frontend" / "streamlit_app.py").run()
    page.file_uploader[0].upload("resume.pdf", pdf_bytes(), "application/pdf").run()
    next(button for button in page.button if button.label == "解析简历").click().run()
    assert not page.exception
    assert {heading.value for heading in page.subheader} >= {"个人信息", "教育背景", "实习经历", "项目经历", "个人技能"}
    assert not any(tab.label in {"原文件与文本对照", "全部提取文本"} for tab in page.tabs)
    assert not any(widget.label == "查看页码" for widget in page.selectbox)
    page.checkbox(key="confirm_checkbox").check().run()
    before = page.session_state["resume"]["revision"]
    page.text_input[0].input("Edited candidate").run()
    assert page.session_state["editor_dirty"]
    assert page.checkbox(key="confirm_checkbox").disabled
    assert next(button for button in page.button if button.label == "开始分析").disabled
    next(button for button in page.button if button.label == "保存修改").click().run()
    assert not page.exception
    saved = page.session_state["resume"]
    assert saved["revision"] == before + 1
    assert saved["parsed_data"]["personal_info"]["name"] == "Edited candidate"
    assert not saved["confirmed"]
    page.checkbox(key="confirm_checkbox").check().run()
    page.text_area(key=f"jd_{page.session_state['epoch']}").input(JD).run()
    next(button for button in page.button if button.label == "开始分析").click().run()
    assert not page.exception
    assert page.session_state["result"]


def test_multiline_entries_survive_add_delete_and_save(monkeypatch, client):
    import frontend.api_client as api
    from conftest import JD, pdf_bytes

    def through_backend(base, method, path, **kwargs):
        response = client.request(method, path, **kwargs)
        if response.is_error:
            body = response.json()
            raise api.APIError(body["message"], body["code"], body["request_id"])
        if response.status_code == 204:
            return None
        return response.content if response.headers.get("content-type", "").startswith("image/") else response.json()
    monkeypatch.setattr(api, "request", through_backend)
    page = AppTest.from_file(Path(__file__).resolve().parents[1] / "frontend" / "streamlit_app.py").run()
    jd_key = f"jd_{page.session_state['epoch']}"
    page.text_area(key=jd_key).input(JD).run()
    page.file_uploader[0].upload("resume.pdf", pdf_bytes(), "application/pdf").run()
    next(button for button in page.button if button.label == "解析简历").click().run()
    assert not page.exception
    assert page.text_area(key=jd_key).value == JD
    first = page.session_state["editor_draft"]["projects"][0]["_uid"]
    first_field = next(widget for widget in page.text_area if widget.key.startswith("editor_projects_description_") and widget.key.endswith(first))
    first_field.input("First line\nSecond line").run()
    page.button(key="add_projects").click().run()
    assert not page.exception
    assert next(widget for widget in page.text_area if widget.key.endswith(first)).value == "First line\nSecond line"
    second = page.session_state["editor_draft"]["projects"][1]["_uid"]
    next(widget for widget in page.text_input if widget.key.startswith("editor_projects_title_") and widget.key.endswith(second)).input("New project").run()
    next(widget for widget in page.text_area if widget.key.endswith(second)).input("Architecture\nImplementation\nResults").run()
    page.button(key=f"delete_projects_{first}").click().run()
    assert not page.exception
    assert next(widget for widget in page.text_area if widget.key.endswith(second)).value == "Architecture\nImplementation\nResults"
    next(button for button in page.button if button.label == "保存修改").click().run()
    assert not page.exception
    saved = page.session_state["resume"]["parsed_data"]["projects"]
    assert len(saved) == 1 and saved[0]["title"] == "New project"
    assert saved[0]["description"] == "Architecture\nImplementation\nResults"

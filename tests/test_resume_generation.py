"""Generation contracts, model request, HTML isolation and revision safety."""

import json

import httpx
import pytest

from app.repositories.memory import ResumeRecord
from app.schemas.business import ParsedResume, PersonalInfo, ResumeItem, ResumeResponse
from app.services.resume_html import prepare_html
from app.core.errors import AppError

HTML = '<!DOCTYPE html><html lang="zh-CN"><head><style>body { color:#123; }</style><title>简历</title></head><body><h1>Saved Candidate</h1><p>13800138000 · demo@example.com</p><section><h2>项目经历</h2><p>Saved project: Edited form content</p></section></body></html>'


@pytest.fixture
def generation_resume(application):
    application.state.settings.resume_generation_api_key = "test-generation-key"
    r = ResumeResponse(resume_id="",filename="sample",pages=[],warnings=[],parse_status="edited",
                       parsed_data=ParsedResume(personal_info=PersonalInfo(name="Saved Candidate",phone="13800138000",email="demo@example.com"),
                                                projects=[ResumeItem(title="Saved project",description="Edited form content")]))
    key = application.state.store.add("resume", ResumeRecord(r, []))
    calls = []
    def completion(request):
        calls.append(json.loads(request.content))
        assert request.headers["authorization"] == "Bearer test-generation-key"
        return httpx.Response(200,json={"choices":[{"finish_reason":"stop","message":{"content":HTML}}]})
    application.state.resume_generator.transport = httpx.MockTransport(completion)
    return key,calls


def test_generate_saved_fields_and_sandboxed_link(client, application, generation_resume):
    key,calls = generation_resume
    response = client.post(f"/api/resumes/{key}/generate",json={"expected_revision":1,"use_jd":True,"jd_text":"Python intern","instructions":"蓝白色"})
    assert response.status_code == 200,response.text
    metadata = response.json()
    assert metadata["model"] == "deepseek-v4.1-flash-1017"
    assert len(calls) == 1
    body = calls[0]
    assert body["stream"] is False and body["max_tokens"] >= 10000
    assert body["thinking"] == {"type": "disabled"}
    assert "response_format" not in body
    payload = json.loads(body["messages"][1]["content"])
    assert payload["resume"]["projects"] == [{"title":"Saved project","description":"Edited form content"}]
    assert payload["jd"] == "Python intern"
    assert "evidence" not in body["messages"][1]["content"]
    preview = client.get(metadata["preview_path"])
    assert preview.status_code == 200 and "text/html" in preview.headers["content-type"]
    assert "Saved Candidate" in preview.text and "<style>" in preview.text
    assert "sandbox" in preview.headers["content-security-policy"]
    assert "default-src 'none'" in preview.headers["content-security-policy"]
    assert preview.headers["cache-control"] == "no-store"
    assert "A4" in body["messages"][0]["content"] and "不得" in body["messages"][0]["content"]
    duplicate = client.post(f"/api/resumes/{key}/generate",json={"expected_revision":1,"use_jd":True,"jd_text":"Python intern","instructions":"蓝白色"})
    assert duplicate.json() == metadata and len(calls) == 1
    current = application.state.store.get(key,"resume").response
    application.state.store.replace(key,current,1)
    assert client.get(metadata["preview_path"]).status_code == 404
    assert client.post(f"/api/resumes/{key}/generate",json={"expected_revision":1}).status_code == 409


def test_cleanup_removes_active_content_preserves_styles():
    malicious = HTML.replace("</body>",'<script>fetch("https://bad.test")</script><iframe src="https://bad.test">evil</iframe><img src="https://bad.test"><a href="javascript:alert(1)" onclick="evil()">文字</a><meta http-equiv="refresh" content="0; url=https://bad.test"></body>')
    result = prepare_html(malicious,{"name":"Saved Candidate"})
    assert "<style>body" in result and "文字" in result
    for value in ("<script","<iframe","<img","onclick", "javascript:","http-equiv", "bad.test"):
        assert value not in result


@pytest.mark.parametrize("raw,code",[("", "GENERATION_HTML_INVALID"),("<html><body>unfinished", "GENERATION_HTML_INVALID"),(HTML.replace("Saved Candidate","Another Person"),"GENERATION_FACT_CHANGED")])
def test_invalid_html_and_changed_identity(raw, code):
    with pytest.raises(AppError) as exc:
        prepare_html(raw,{"name":"Saved Candidate"})
    assert exc.value.code == code


@pytest.mark.parametrize("mode,code,status",[("timeout","GENERATION_TIMEOUT",504),("truncated","GENERATION_TRUNCATED",502),("empty","GENERATION_OUTPUT_INVALID",502),("upstream","GENERATION_UPSTREAM_ERROR",502)])
def test_failures_preserve_form_and_previous_preview(client,application,generation_resume,mode,code,status):
    key,_=generation_resume
    path=f"/api/resumes/{key}/generate"
    initial=client.post(path,json={"expected_revision":1}).json()
    def fail(request):
        if mode=="timeout":raise httpx.ReadTimeout("timeout",request=request)
        if mode=="upstream":return httpx.Response(401,text="private-provider-detail")
        return httpx.Response(200,json={"choices":[{"finish_reason":"length" if mode=="truncated" else "stop","message":{"content":""}}]})
    application.state.resume_generator.transport=httpx.MockTransport(fail)
    response=client.post(path,json={"expected_revision":1,"instructions":"new request"})
    assert response.status_code==status and response.json()["code"]==code
    assert "private-provider-detail" not in response.text
    assert client.get(initial["preview_path"]).status_code==200
    assert application.state.store.get(key,"resume").response.revision==1


def test_generation_concurrent_edit_and_missing_jd(client,application,generation_resume):
    key,_=generation_resume
    path=f"/api/resumes/{key}/generate"
    assert client.post(path,json={"expected_revision":1,"use_jd":True}).status_code==422
    def edit(request):
        current=application.state.store.get(key,"resume").response
        application.state.store.replace(key,current,1)
        return httpx.Response(200,json={"choices":[{"message":{"content":HTML}}]})
    application.state.resume_generator.transport=httpx.MockTransport(edit)
    assert client.post(path,json={"expected_revision":1}).status_code==409
    assert application.state.store.get(key,"resume").generation is None


def test_generation_reuses_existing_aihubmix_key(client,application,generation_resume):
    key,calls=generation_resume
    settings=application.state.settings
    settings.resume_generation_api_key=""
    settings.llm_base_url=settings.resume_generation_base_url
    settings.llm_api_key="test-generation-key"
    assert client.post(f"/api/resumes/{key}/generate",json={"expected_revision":1}).status_code==200
    assert len(calls)==1


def test_thinking_override_and_budget_changes_invalidate_cache(client, application, generation_resume):
    key, calls = generation_resume
    settings = application.state.settings
    path = f"/api/resumes/{key}/generate"
    assert client.post(path, json={"expected_revision": 1}).status_code == 200
    settings.resume_generation_enable_thinking = True
    assert client.post(path, json={"expected_revision": 1}).status_code == 200
    assert calls[-1]["thinking"] == {"type": "enabled"} and len(calls) == 2
    settings.resume_generation_max_tokens = 28000
    assert client.post(path, json={"expected_revision": 1}).status_code == 200
    assert calls[-1]["max_tokens"] == 28000 and len(calls) == 3

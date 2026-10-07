"""Exercise the HTTP → model → tool → observation → validated-source path."""

import json

import pytest

import app as application


PAPER = {"source": "OpenAlex", "title": "Flexible Bio-Z pulse waveform electrode", "doi": "10.1234/fixture", "url": "https://doi.org/10.1234/fixture", "journal": "Fixture Journal", "year": 2026, "authors": "Fixture Author", "citedBy": 0, "type": "journal-article"}


def response(message):
    return {"model": "fixture/actual", "choices": [{"message": message, "finish_reason": "tool_calls" if message.get("tool_calls") else "stop"}], "usage": {"prompt_tokens": 12, "completion_tokens": 8, "total_tokens": 20, "cost": 0}}, 1


def search_call(query="Bio-Z pulse waveform flexible electrode"):
    return {"content": "", "tool_calls": [{"id": "provider-call", "type": "function", "function": {"name": "search_papers", "arguments": json.dumps({"query": query})}}]}


def setup_provider(monkeypatch):
    monkeypatch.setattr(application, "model_configuration", lambda: {"configured": True, "apiKey": "test-secret", "baseUrl": "https://example.invalid/v1", "model": "fixture/requested"})
    monkeypatch.setattr(application, "openalex_search", lambda *_args, **_kwargs: [PAPER])
    monkeypatch.setattr(application, "crossref_search", lambda *_args, **_kwargs: [])


def test_chat_model_tool_observation_and_source_selection_are_persisted(monkeypatch):
    setup_provider(monkeypatch)
    turns = []

    def model(_url, *, headers, payload):
        turns.append(payload)
        assert headers["Authorization"] == "Bearer test-secret"
        assert [tool["function"]["name"] for tool in payload["tools"]] == ["search_papers"]
        if len(turns) == 1:
            assert payload["tool_choice"] == {"type": "function", "function": {"name": "search_papers"}}
            return response(search_call())
        observed = json.loads(payload["messages"][-1]["content"])
        assert observed["result"]["items"][0]["url"] == PAPER["url"]
        assert payload["messages"][-1]["role"] == "tool"
        return response({"content": json.dumps({"selected_urls": [PAPER["url"]]})})

    monkeypatch.setattr(application, "request_model_json", model)
    client = application.app.test_client()
    result = client.post("/api/research", json={"query": "检索 Bio-Z pulse waveform 柔性电极论文", "useModel": True, "useOpenAlex": True}).json
    assert result["responseState"] == "completed"
    assert result["sources"][0]["doi"] == PAPER["doi"]
    assert result["sources"][0]["title"] in result["answer"]
    assert len(turns) == 2
    assert "test-secret" not in json.dumps(result)
    provider = client.get("/api/providers").json
    assert provider["activeProbe"]["origin"] == "tool_completion"
    assert provider["model"]["connectionStatus"] == "verified"
    run = client.get(f"/api/agent-runs/{result['agentRun']['runId']}").json
    assert run["model"]["actualModel"] == "fixture/actual"
    assert run["token_usage"]["totalTokens"] == 40
    assert run["state"]["selectionValidated"] is True
    assert run["state"]["stop_reason"] == "completed"
    assert [call["tool_name"] for call in run["toolCalls"]] == ["search_papers"]
    session = client.get(f"/api/sessions/{result['sessionId']}").json
    assert len(session["messages"]) == 2
    report = client.get(f"/api/sessions/{result['sessionId']}/report.md")
    assert PAPER["url"] in report.text


def test_model_can_refine_query_after_empty_tool_result(monkeypatch):
    setup_provider(monkeypatch)
    searches = []
    turns = []

    def search(query, **_kwargs):
        searches.append(query)
        return [] if len(searches) == 1 else [PAPER]

    def model(_url, **kwargs):
        turns.append(kwargs["payload"])
        if len(turns) == 1:
            return response(search_call("Bio-Z pulse waveform"))
        if len(turns) == 2:
            assert json.loads(turns[-1]["messages"][-1]["content"])["result"]["items"] == []
            return response(search_call("flexible Bio-Z pulse waveform electrode"))
        return response({"content": json.dumps({"selected_urls": [PAPER["url"]]})})

    monkeypatch.setattr(application, "openalex_search", search)
    monkeypatch.setattr(application, "request_model_json", model)
    result = application.app.test_client().post("/api/research", json={"query": "检索 Bio-Z pulse waveform 论文", "useModel": True, "useOpenAlex": True}).json
    assert result["responseState"] == "completed"
    assert len(result["tools"]) == 2
    assert len(turns) == 3


@pytest.mark.parametrize("final", ['{"selected_urls":["https://doi.org/10.9999/invented"]}', '{"selected_urls":[],"claim":"患者患有疾病"}', '这是论文证明的临床结论'])
def test_unobserved_citation_or_unstructured_claim_cannot_reach_answer(monkeypatch, final):
    setup_provider(monkeypatch)
    replies = iter([response(search_call()), response({"content": final})])
    monkeypatch.setattr(application, "request_model_json", lambda *_args, **_kwargs: next(replies))
    result = application.app.test_client().post("/api/research", json={"query": "检索 Bio-Z pulse waveform 论文", "useModel": True, "useOpenAlex": True}).json
    assert result["responseState"] == "partial"
    assert result["errorCode"] == "invalid_source_selection"
    assert "invented" not in result["answer"]
    assert "患者患有疾病" not in result["answer"]
    assert "临床结论" not in result["answer"]
    assert result["sources"][0]["url"] == PAPER["url"]


def test_provider_failure_uses_explicit_search_fallback_without_claiming_llm_success(monkeypatch):
    setup_provider(monkeypatch)

    def unavailable(*_args, **_kwargs):
        raise TimeoutError("sensitive connection detail")

    monkeypatch.setattr(application, "request_model_json", unavailable)
    result = application.app.test_client().post("/api/research", json={"query": "检索 Bio-Z pulse waveform 论文", "useModel": True, "useOpenAlex": True}).json
    assert result["responseState"] == "partial"
    assert result["errorCode"] == "model_error"
    assert result["answer"].startswith("模型检索未完成")
    assert result["sources"][0]["url"] == PAPER["url"]
    assert "sensitive connection" not in json.dumps(result)
    assert application.app.test_client().get("/api/providers").json["model"]["connectionStatus"] == "unavailable"


def test_english_model_query_is_preserved_in_public_search(monkeypatch):
    queries = []
    monkeypatch.setattr(application, "openalex_search", lambda query, **kwargs: queries.append(query) or [{**PAPER, "title": "Flexible electronics for wearable interfaces"}])
    result = application.search_papers_tool(application.SearchPapersInput(query="flexible electronics"))
    assert queries == ["flexible electronics"]
    assert result.query == "flexible electronics"
    assert len(result.items) == 1


def test_journal_notices_and_duplicate_titles_are_excluded(monkeypatch):
    records = [
        {**PAPER, "title": "Flexible electronics Call for Papers"},
        {**PAPER, "title": "Flexible electronics Publication Information"},
        {**PAPER, "title": "The stronger venue for flexible electronics"},
        {**PAPER, "title": "Flexible electronics for wearable interfaces"},
        {**PAPER, "title": "Flexible electronics for wearable interfaces", "doi": "10.1234/duplicate"},
    ]
    monkeypatch.setattr(application, "openalex_search", lambda *_args, **_kwargs: records)
    result = application.search_papers_tool(application.SearchPapersInput(query="flexible electronics"))
    assert len(result.items) == 1
    assert result.rejected_records == 3
    assert result.items[0].title == "Flexible electronics for wearable interfaces"


def test_bioz_search_excludes_registries_supplements_and_other_measurement_modalities(monkeypatch):
    records = [PAPER,
        {**PAPER, "doi": "10.31525/ct1-nct04231656"},
        {**PAPER, "doi": "10.1186/isrctn26732484", "type": "dataset"},
        {**PAPER, "doi": "10.1021/fixture.s001"},
        {**PAPER, "doi": "10.1234/chapter", "type": "book-chapter"},
        {**PAPER, "doi": "10.1234/pressure", "title": "Paper-Based Supercapacitive Pressure Sensor for Wrist Arterial Pulse Waveform Monitoring"},
        {**PAPER, "doi": "10.1234/radar", "title": "Transmit pulse waveform optimization for radar"},
    ]
    monkeypatch.setattr(application, "openalex_search", lambda *_args, **_kwargs: records)
    result = application.search_papers_tool(application.SearchPapersInput(query="Bio-Z pulse waveform"))
    assert [item.doi for item in result.items] == [PAPER["doi"]]
    assert result.rejected_records == 6


def test_chinese_bioz_query_preserves_modality_and_pulse_terms():
    assert application.research_query_variants("查找生物阻抗脉搏波论文", "柔性感知") == ["bioimpedance pulse waveform"]


def test_model_rewrite_cannot_drop_original_bioz_requirement(monkeypatch):
    setup_provider(monkeypatch)
    pressure = {**PAPER, "title": "Pressure sensor pulse waveform", "doi": "10.1234/pressure", "url": "https://doi.org/10.1234/pressure"}
    monkeypatch.setattr(application, "openalex_search", lambda *_args, **_kwargs: [pressure])
    replies = iter([response(search_call("pressure sensor pulse waveform")), response({"content": json.dumps({"selected_urls": [pressure["url"]]})})])
    monkeypatch.setattr(application, "request_model_json", lambda *_args, **_kwargs: next(replies))
    result = application.app.test_client().post("/api/research", json={"query": "找 Bio-Z pulse waveform 论文", "useModel": True, "useOpenAlex": True}).json
    assert result["responseState"] == "partial"
    assert result["sources"] == []


@pytest.mark.parametrize("source_type", ["article", "dissertation", None])
def test_openalex_preserves_record_type_instead_of_inventing_journal_article(monkeypatch, source_type):
    monkeypatch.setattr(application, "request_json", lambda *_args, **_kwargs: {"results": [{"id": "https://openalex.org/W1", "display_name": "Bioimpedance pulse waveform", "type": source_type}]})
    record = application.openalex_search("bioimpedance pulse waveform")[0]
    assert record["type"] == (source_type or "")


def test_digest_does_not_claim_three_papers_when_only_two_exist():
    answer = application.literature_metadata_digest([{**PAPER, "abstract": "Public abstract"}, PAPER], False)
    assert "列出的 2 篇中有 1 篇公开摘要" in answer
    assert "前 3 篇" not in answer


"""Actual HTTP/model loop with fixed public-provider responses, no live network."""

import json
from datetime import date
from urllib.parse import parse_qs, urlparse

import pytest

import app as application
import flexresearch.publication_dates as dates


PAPER = {"source": "OpenAlex", "title": "Flexible Bio-Z electrode pulse waveform", "doi": "10.1234/synthetic-date-fixture", "url": "https://doi.org/10.1234/synthetic-date-fixture", "year": 2025, "publication_date": "2025-06-12", "type": "article"}


def model_response(message):
    return {"model": "replay/date", "choices": [{"message": message, "finish_reason": "tool_calls" if message.get("tool_calls") else "stop"}], "usage": {"prompt_tokens": 10, "completion_tokens": 5, "total_tokens": 15, "cost": 0}}, 1


def search_call(**arguments):
    return model_response({"tool_calls": [{"id": "synthetic-call", "type": "function", "function": {"name": "search_papers", "arguments": json.dumps({"query": "flexible Bio-Z electrode", **arguments})}}]})


@pytest.fixture
def configured(monkeypatch):
    monkeypatch.setattr(dates, "publication_today", lambda: date(2026, 9, 3))
    monkeypatch.setattr(application, "model_configuration", lambda: {"configured": True, "apiKey": "synthetic-key", "baseUrl": "https://example.invalid/v1", "model": "replay/date"})
    monkeypatch.setattr(application, "crossref_search", lambda *_a, **_k: [])
    monkeypatch.setattr(application, "europepmc_search", lambda *_a, **_k: [])


@pytest.mark.parametrize("use_model", [True, False])
def test_no_results_is_partial_in_response_history_and_agent_run(monkeypatch, configured, use_model):
    monkeypatch.setattr(application, "openalex_search", lambda *_a, **_k: [])
    replies = iter([search_call(), model_response({"content": '{"selected_urls":[]}'})])
    monkeypatch.setattr(application, "request_model_json", lambda *_a, **_k: next(replies))
    client = application.app.test_client()
    result = client.post("/api/research", json={"query": "检索不存在材料 XQZ-999 的柔性电极论文。", "useModel": use_model, "useOpenAlex": True}).json
    assert result["responseState"] == "partial"
    assert result["errorCode"] == "no_relevant_sources"
    assert result["sources"] == []
    assert "未找到足够相关的可核验论文" in result["answer"]
    assert "doi.org" not in result["answer"]
    run = client.get(f"/api/agent-runs/{result['agentRun']['runId']}").json
    assert run["status"] == "partial"
    assert run["state"]["stop_reason"] == "no_relevant_sources"
    history = client.get(f"/api/sessions/{result['sessionId']}").json
    assert history["messages"][-1]["content"] == result["answer"]
    if use_model:
        assert run["state"]["selectionValidated"] is True  # Schema valid, task not complete.
        assert [call["tool_name"] for call in run["toolCalls"]] == ["search_papers"]


def test_model_must_repair_dropped_time_constraint_before_search(monkeypatch, configured):
    calls, turns = [], []
    monkeypatch.setattr(application, "openalex_search", lambda query, **kwargs: calls.append(kwargs) or [PAPER])

    def model(_url, *, headers, payload):
        turns.append(payload)
        if len(turns) == 1:
            return search_call()  # Invalid: ignores the original recent-window requirement.
        if len(turns) == 2:
            observation = json.loads(payload["messages"][-1]["content"])
            assert observation["status"] == "error" and "publication window" in observation["error"]
            return search_call(recent_only=True, from_year=2023, to_date="2026-09-03")
        return model_response({"content": json.dumps({"selected_urls": [PAPER["url"]]})})

    monkeypatch.setattr(application, "request_model_json", model)
    client = application.app.test_client()
    result = client.post("/api/research", json={"query": "检索近三年的柔性 Bio-Z 电极论文。", "useModel": True, "useOpenAlex": True}).json
    assert result["responseState"] == "completed", json.dumps(result, ensure_ascii=False, indent=2)
    assert len(calls) == 1 and calls[0]["recent_only"] is True
    assert calls[0]["from_year"] == 2023 and calls[0]["to_date"] == date(2026, 9, 3)
    assert result["publicationWindow"] == {"from_date": "2023-09-03", "to_date": "2026-09-03"}
    assert [step["status"] for step in result["tools"]] == ["error", "complete"]


@pytest.mark.parametrize("provider", ["openalex", "crossref"])
def test_provider_request_and_returned_dates_are_checked(monkeypatch, configured, provider):
    urls = []
    raw_dates = [[2023, 9, 3], [2023, 9, 2], [2026, 9, 3], [2026, 9, 4], [2024], [2023], [2026], []]

    def network(url):
        urls.append(url)
        if provider == "crossref":
            return {"message": {"items": [{"DOI": f"10.1234/date-{index}", "title": [PAPER["title"]], "published": {"date-parts": [parts]}} for index, parts in enumerate(raw_dates)]}}
        return {"results": [{"doi": f"https://doi.org/10.1234/date-{index}", "display_name": PAPER["title"], "publication_year": parts[0] if parts else None, "publication_date": dates.publication_date_from_parts(parts)} for index, parts in enumerate(raw_dates)]}

    monkeypatch.setattr(application, "request_json", network)
    # Use original function even when the fixture replaced the Crossref adapter.
    search = ORIGINAL_CROSSREF if provider == "crossref" else application.openalex_search
    records = search("flexible Bio-Z electrode", recent_only=True)
    assert [record["doi"] for record in records] == ["10.1234/date-0", "10.1234/date-2", "10.1234/date-4"]
    params = parse_qs(urlparse(urls[0]).query)
    assert "2023-09-03" in params["filter"][0] and "2026-09-03" in params["filter"][0]
    assert records[-1]["publication_date"] == "2024"


ORIGINAL_CROSSREF = application.crossref_search


def test_tool_rechecks_adapter_dates_and_exposes_exclusion_count(monkeypatch, configured):
    monkeypatch.setattr(application, "openalex_search", lambda *_a, **_k: [PAPER, {**PAPER, "publication_date": "2030-01-01"}, {**PAPER, "publication_date": None, "year": 2026}])
    result = application.search_papers_tool(application.SearchPapersInput(query="flexible Bio-Z electrode", recent_only=True))
    assert len(result.items) == 1
    assert result.date_excluded_records == 2
    assert result.date_window.from_date == date(2023, 9, 3)


@pytest.mark.parametrize("prompt", ["检索近三年的论文", "find papers from the past three years", "papers from the last 3 years"])
def test_recent_phrasings_are_recognized(prompt):
    assert application.requests_recent_literature(prompt)


@pytest.mark.parametrize("modality", ["Bio-Z", "BioZ", "Bio Z", "bioimpedance"])
def test_bioz_alias_survives_original_chinese_topic_validation(modality):
    query = "检索近三年的柔性 Bio-Z 电极论文。"
    paper = {**PAPER, "title": f"Flexible {modality} electrode pulse waveform"}
    ranked = application.calibrate_source_relevance(paper, application.infer_track(query), query)
    assert ranked["relevance"]["titleScore"] >= 23
    assert application.paper_exclusion_reason(paper, query) is None
    unrelated = {**paper, "title": "Flexible optical pulse waveform sensor"}
    assert application.paper_exclusion_reason(unrelated, query) == "requested_modality_not_in_metadata"


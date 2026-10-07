"""Chromium + actual frontend + local HTTP/SQLite/files, isolated from user data.

Only outbound model/provider boundaries are replayed. Source-link navigation
is intercepted after clicking: synthetic DOI destinations are not real papers.
"""

from __future__ import annotations

import hashlib
import json
import sqlite3
import threading
import urllib.error
from datetime import date
from pathlib import Path
from urllib.parse import urlparse

import pytest
from playwright.sync_api import expect, sync_playwright
from werkzeug.serving import make_server

import app as application
import flexresearch.publication_dates as dates
from scripts.run_agent_eval import pulse_csv, channel_switch_csv
from scripts.document_fixtures import document_pdf


ROOT = Path(__file__).resolve().parents[2]
REAL_MODEL_REQUEST = application.request_model_json


@pytest.fixture(scope="module")
def browser():
    with sync_playwright() as runtime:
        instance = runtime.chromium.launch()
        try:
            yield instance
        finally:
            instance.close()


@pytest.fixture
def ui(browser, monkeypatch, request):
    # The shared autouse fixture has already redirected every app storage path.
    monkeypatch.setenv("OPENAI_API_KEY", "synthetic-browser-key-not-a-secret")
    monkeypatch.setenv("OPENAI_BASE_URL", "https://example.invalid/v1")
    monkeypatch.setenv("OPENAI_MODEL", "replay/browser-a")
    monkeypatch.setattr(application, "PROVIDER_PROBE_HISTORY", {})
    monkeypatch.setattr(application, "LAST_PROVIDER_PROBE", None)

    def forbidden(*_a, **_k):
        raise AssertionError("Unscripted outbound call in browser E2E")

    monkeypatch.setattr(application, "request_json", forbidden)
    monkeypatch.setattr(application, "request_model_json", forbidden)
    server = make_server("127.0.0.1", 0, application.app, threaded=True)
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    base = f"http://127.0.0.1:{server.server_port}"
    context = browser.new_context(viewport={"width": 1440, "height": 1000}, accept_downloads=True)
    context.tracing.start(screenshots=True, snapshots=True, sources=True)
    page = context.new_page()
    errors = []
    page.on("pageerror", lambda error: errors.append(str(error)))
    context.route("**/*", lambda route: route.continue_() if urlparse(route.request.url).hostname == "127.0.0.1" else route.abort())
    artifacts = ROOT / "output/playwright" / request.node.name
    artifacts.mkdir(parents=True, exist_ok=True)
    try:
        page.goto(base)
        expect(page.locator("#provider")).to_contain_text("browser-a")
        yield page, base
        assert not errors, errors
    finally:
        try:
            page.screenshot(path=str(artifacts / "final.png"), full_page=True)
            context.tracing.stop(path=str(artifacts / "trace.zip"))
        finally:
            context.close()
            server.shutdown()
            thread.join(timeout=5)
            server.server_close()


def submit(page, prompt):
    page.locator("#prompt").fill(prompt)
    page.locator("#send").click()
    expect(page.locator("#prompt")).to_have_value("", timeout=15000)
    expect(page.locator("#send")).to_be_enabled()


def test_browser_pending_filter_resume_download_and_reload(ui, monkeypatch, tmp_path):
    page, _base = ui
    def model(_url, *, headers, payload):
        if payload["messages"][-1]["role"] == "tool":
            observation = json.loads(payload["messages"][-1]["content"])
            message = {"content": json.dumps({"tool_run_id": observation["toolRunId"]})}
        else:
            arguments = json.loads(payload["messages"][0]["content"].split("Confirmed scope: ", 1)[1])
            message = {"tool_calls": [{"id": "pending-filter", "type": "function", "function": {"name": "analyze_experiment", "arguments": json.dumps(arguments)}}]}
        return {"model": "replay/browser-a", "choices": [{"message": message, "finish_reason": "tool_calls" if message.get("tool_calls") else "stop"}], "usage": {"prompt_tokens": 10, "completion_tokens": 5, "total_tokens": 15, "cost": 0}}, 1
    monkeypatch.setattr(application, "request_model_json", model)
    raw = pulse_csv(column="ch4")
    page.locator("#attachment").set_input_files({"name": "SYNTHETIC-pending.csv", "mimeType": "text/csv", "buffer": raw})
    submit(page, "滤波并保存结果，但不要改原始文件。")
    expect(page.locator(".message.assistant").last).to_contain_text("截止频率")
    expect(page.get_by_role("link", name="下载滤波 CSV ↗")).to_have_count(0)
    page.reload()
    submit(page, "0.5–3 Hz带通，4阶")
    expect(page.locator(".message.assistant").last).to_contain_text("已另存处理后的 CSV")
    with page.expect_download() as first:
        page.get_by_role("link", name="下载滤波 CSV ↗").click()
    target = tmp_path / "derived.csv"
    first.value.save_as(target)
    assert target.read_bytes().startswith(b"time_s,filtered_signal")
    assert target.read_bytes() != raw
    assert any(path.read_bytes() == raw for path in application.MEASUREMENT_DIR.glob("*.csv"))
    page.reload()
    expect(page.locator(".message.assistant")).to_have_count(2)
    with page.expect_download() as second:
        page.get_by_role("link", name="下载滤波 CSV ↗").click()
    restored = tmp_path / "restored.csv"
    second.value.save_as(restored)
    assert restored.read_bytes() == target.read_bytes()
    with application.get_db() as db:
        state = json.loads(db.execute("SELECT state_json FROM session_experiment_state").fetchone()[0])
    assert state["pending_request"] is None


def test_browser_metadata_only_paper_clarifies_without_foreign_sources(ui):
    page, base = ui
    created = page.request.post(base + "/api/papers", data={"title": "SYNTHETIC metadata-only paper"})
    assert created.status == 201
    identifier = created.json()["item"]["id"]
    submit(page, f"论文{identifier}的具体采样率和滤波参数是什么？")
    last = page.locator(".message.assistant").last
    expect(last).to_contain_text("没有摘要或全文证据")
    expect(last.locator(".sources")).to_have_count(0)
    expect(last.locator(".paper-evidence")).to_contain_text("仅书目记录")
    last.locator(".paper-evidence summary").click()
    expect(last.locator(".paper-evidence")).to_contain_text("SYNTHETIC metadata-only paper")
    page.reload()
    expect(page.locator(".message.assistant")).to_have_count(1)
    expect(page.locator(".message.assistant")).to_contain_text("没有摘要或全文证据")
    expect(page.locator(".sources")).to_have_count(0)
    expect(page.locator(".paper-evidence")).to_have_count(1)


def test_browser_initial_plan_sections_download_and_reload(ui, tmp_path):
    page, _ = ui
    prompt = "为柔性 Bio-Z 多频扫描写一个下一次实验方案草案。"
    submit(page, prompt)
    last = page.locator(".message.assistant").last
    expect(last).to_contain_text("未使用历史实验")
    expect(last).not_to_contain_text("Crossref")
    expect(last).not_to_contain_text("来源文件编号：未找到")
    card = last.locator(".initial-plan")
    expect(card).to_be_visible()
    expect(card.locator('[data-plan-section="objective"]')).to_contain_text("幅值、相位")
    for key, text in [("variables", "通道映射"), ("controls", "参考负载"), ("sample_rate", "每通道"), ("frequency_sweep", "不生成默认数值"), ("quality_checks", "哈希"), ("safety", "SOP"), ("approval_required", "excitation_settings")]:
        section = card.locator(f'[data-plan-section="{key}"]')
        section.locator("summary").click()
        expect(section).to_contain_text(text)
        section.locator("summary").click()
    with page.expect_download() as first:
        card.get_by_role("link", name="下载方案草案 ↗").click()
    target = tmp_path / "initial-plan.md"
    first.value.save_as(target)
    assert prompt in target.read_text() and "## approval_required" in target.read_text()
    page.reload()
    expect(page.locator(".message.assistant")).to_have_count(1)
    card = page.locator(".initial-plan")
    expect(card).to_contain_text("待审核")
    with page.expect_download() as second:
        card.get_by_role("link", name="下载方案草案 ↗").click()
    restored = tmp_path / "restored-plan.md"
    second.value.save_as(restored)
    assert restored.read_bytes() == target.read_bytes()


def test_browser_channel_switch_goal_report_and_reload(ui, monkeypatch, tmp_path):
    page, _ = ui
    turns = []
    def model(_url, *, headers, payload):
        turns.append(payload)
        if payload["messages"][-1]["role"] == "tool":
            observation = json.loads(payload["messages"][-1]["content"])
            message = {"content": json.dumps({"tool_run_id": observation["toolRunId"]})}
        else:
            arguments = json.loads(payload["messages"][0]["content"].split("Confirmed scope: ", 1)[1])
            message = {"tool_calls": [{"id": "channel-switch", "type": "function", "function": {"name": "analyze_experiment", "arguments": json.dumps(arguments)}}]}
        return {"model": "replay/browser-a", "choices": [{"message": message, "finish_reason": "tool_calls" if message.get("tool_calls") else "stop"}], "usage": {"prompt_tokens": 10, "completion_tokens": 5, "total_tokens": 15, "cost": 0}}, 1
    monkeypatch.setattr(application, "request_model_json", model)
    raw = channel_switch_csv()
    page.locator("#attachment").set_input_files({"name": "SYNTHETIC-channels.csv", "mimeType": "text/csv", "buffer": raw})
    submit(page, "通道2，采样率100Hz，分析FFT主峰")
    expect(page.locator(".message.assistant").last).to_contain_text("ch2 的 FFT 主峰为 2.4 Hz")
    expect(page.locator(".welcome")).to_have_count(0)
    expect(page.locator(".message.assistant").last.locator(".stats b")).to_have_count(0)
    submit(page, "继续用刚才的 100 Hz 采样率分析通道 4。")
    last = page.locator(".message.assistant").last
    expect(last).to_contain_text("沿用上一轮频谱分析")
    expect(last).to_contain_text("ch4 的 FFT 主峰为 1.2 Hz")
    assert len(turns) == 2 and "calculatedResult" not in json.loads(turns[-1]["messages"][-1]["content"])
    details = last.locator("details.trace")
    details.locator("summary").click()
    expect(details).to_contain_text("load_experiment_data")
    expect(details).to_contain_text("spectral_analysis")
    expect(details.get_by_role("link", name="上一轮分析目标来源 ↗")).to_be_visible()
    with page.expect_download() as download:
        details.get_by_role("link", name="下载结构化实验报告 ↗").click()
    target = tmp_path / "channel-switch.md"
    download.value.save_as(target)
    report = target.read_text()
    assert hashlib.sha256(raw).hexdigest() in report and "analysis_context" in report and "source_run_id" in report
    page.reload()
    expect(page.locator(".message.assistant")).to_have_count(2)
    expect(page.locator(".message.assistant").last).to_contain_text("ch4 的 FFT 主峰为 1.2 Hz")
    expect(page.locator(".message.assistant").last).to_contain_text("沿用上一轮频谱分析")
    last = page.locator(".message.assistant").last
    last.locator("details.agent-trace > summary").click()
    expect(last.get_by_role("link", name="上一轮分析目标来源 ↗")).to_be_visible()
    # Expanded content can be taller than the viewport. Test actual reachability,
    # not the false requirement that the whole message fit above the composer.
    with page.expect_download() as again:
        last.get_by_role("link", name="下载结构化实验报告 ↗").click()
    second_target = tmp_path / "channel-switch-reloaded.md"
    again.value.save_as(second_target)
    assert second_target.read_bytes() == target.read_bytes()


def test_browser_iv_tool_values_report_and_reload(ui, tmp_path):
    page, _ = ui
    raw = (ROOT / "eval/fixtures/iv_1kohm.csv").read_bytes()
    page.locator("#attachment").set_input_files({"name": "SYNTHETIC-IV.csv", "mimeType": "text/csv", "buffer": raw})
    submit(page, "分析这组已知线性 I-V，计算零偏微分电阻。")
    last = page.locator(".message.assistant").last
    expect(last).to_contain_text("微分电阻为 1000 Ω")
    expect(last.locator('[data-iv="resistance"] b')).to_have_text("1000")
    expect(last.locator('[data-iv="window"] b')).to_have_text("±0.1")
    expect(last.locator('[data-iv="points"] b')).to_have_text("3")
    expect(last).not_to_contain_text("末端漂移")
    trace = last.locator("details.trace")
    trace.locator("summary").click()
    for name in ["load_experiment_data", "load_csv", "analyze_signal"]:
        expect(trace).to_contain_text(name)
    with page.expect_download() as download_info:
        trace.get_by_role("link", name="下载结构化实验报告").click()
    path = tmp_path / "iv-report.md"
    download_info.value.save_as(path)
    report = path.read_text()
    assert "零偏附近微分电阻为 1000 Ω" in report and hashlib.sha256(raw).hexdigest() in report
    page.reload()
    expect(page.locator(".message.assistant")).to_have_count(1)
    expect(page.locator('[data-iv="resistance"] b')).to_have_text("1000")
    expect(page.locator('[data-iv="window"] b')).to_have_text("±0.1")


def test_browser_statistics_use_tool_values_and_survive_reload(ui, tmp_path):
    page, _ = ui
    raw = (ROOT / "eval/fixtures/generic_two_column.csv").read_bytes()
    page.locator("#attachment").set_input_files({"name": "SYNTHETIC-statistics.csv", "mimeType": "text/csv", "buffer": raw})
    submit(page, "给这个两列信号做基础统计。")
    last = page.locator(".message.assistant").last
    expect(last).to_contain_text("均值为 6")
    for key, value in {"valid_point_count": "5", "mean": "6", "min": "2", "max": "10", "drift": "8", "slope": "4"}.items():
        expect(last.locator(f'[data-stat="{key}"] b')).to_have_text(value)
    expect(last.locator('[data-stat="slope"]')).to_contain_text("/秒")
    expect(last).not_to_contain_text("前 3 个点均值")
    details = last.locator("details.trace")
    details.locator("summary").click()
    for name in ["load_experiment_data", "load_csv", "analyze_signal"]:
        expect(details).to_contain_text(name)
    with page.expect_download() as download_info:
        details.get_by_role("link", name="下载结构化实验报告").click()
    path = tmp_path / "statistics-report.md"
    download_info.value.save_as(path)
    report = path.read_text()
    assert hashlib.sha256(raw).hexdigest() in report and '"slope": 4' in report
    page.reload()
    expect(page.locator(".message.assistant")).to_have_count(1)
    expect(page.locator('[data-stat="slope"] b')).to_have_text("4")
    expect(page.locator('[data-stat="valid_point_count"] b')).to_have_text("5")


def test_browser_missing_rate_does_not_show_numeric_screening_as_answer(ui):
    page, _ = ui
    raw = (ROOT / "eval/fixtures/time_signal_without_sample_rate.csv").read_bytes()
    page.locator("#attachment").set_input_files({"name": "SYNTHETIC-no-rate.csv", "mimeType": "text/csv", "buffer": raw})
    submit(page, "找这段时域信号的主要频率。")
    last = page.locator(".message.assistant").last
    expect(last).to_contain_text("还缺采样率（Hz）")
    expect(last).to_contain_text("未生成频率结论")
    expect(last.locator(".stats b")).to_have_count(0)
    expect(last.locator(".artifact")).to_have_count(0)
    details = last.locator("details.trace")
    details.locator("summary").click()
    expect(details).to_contain_text("load_experiment_data")
    expect(details).to_contain_text("load_csv")
    expect(details).not_to_contain_text("spectral_analysis")
    page.reload()
    expect(page.locator(".message.user")).to_contain_text("找这段时域信号的主要频率。")
    expect(page.locator(".message.assistant")).to_have_count(1)
    expect(page.locator(".message.assistant")).to_contain_text("还缺采样率（Hz）")
    expect(page.locator(".stats b")).to_have_count(0)


def paper_replay(monkeypatch, *, empty=False):
    fixture = json.loads((ROOT / "eval/fixtures/publication-search.json").read_text())
    records = [] if empty else [item for item in fixture["records"] if item["id"] in fixture["relevant_ids"]]
    if not empty:
        records += [{**records[0], "id": f"browser-extra-{i}", "title": f"Flexible Bio-Z electrode browser fixture {i}"} for i in range(2)]
    urls = ["https://doi.org/10.9999/synthetic-publication-" + item["id"] for item in records]
    monkeypatch.setattr(dates, "publication_today", lambda: date(2026, 9, 3))

    def provider(url):
        if urlparse(url).hostname == "api.openalex.org":
            return {"results": [{"doi": link, "display_name": item["title"], "publication_year": item["year"], "publication_date": item["publication_date"], "type": "article"} for item, link in zip(records, urls)]}
        if urlparse(url).hostname == "api.crossref.org":
            return {"message": {"items": []}}
        raise AssertionError("unexpected provider")

    def model(_url, *, headers, payload):
        if payload["messages"][-1]["role"] == "tool":
            message = {"content": json.dumps({"selected_urls": urls})}
        else:
            message = {"tool_calls": [{"id": "browser-paper", "type": "function", "function": {"name": "search_papers", "arguments": json.dumps({"query": "flexible electrode XQZ-999" if empty else "flexible Bio-Z electrode", "recent_only": not empty})}}]}
        return {"model": "replay/browser-a", "choices": [{"message": message, "finish_reason": "tool_calls" if message.get("tool_calls") else "stop"}], "usage": {"prompt_tokens": 10, "completion_tokens": 5, "total_tokens": 15, "cost": 0}}, 1

    monkeypatch.setattr(application, "request_json", provider)
    monkeypatch.setattr(application, "request_model_json", model)
    return urls


def test_browser_all_source_cards_click_and_survive_reload(ui, monkeypatch):
    page, _base = ui
    urls = paper_replay(monkeypatch)
    submit(page, "检索近三年的柔性 Bio-Z 电极论文。")
    response = page.locator(".message.assistant").last
    expect(response).to_contain_text("找到 7 条近三年候选")
    response.locator("details.sources > summary").click()
    links = response.locator("a.source-card")
    expect(links).to_have_count(7)
    assert links.evaluate_all("nodes => nodes.map(node => node.href)") == urls
    expect(links.first).to_contain_text("2023-09-03")
    page.context.route("https://doi.org/**", lambda route: route.fulfill(status=200, content_type="text/plain", body="SYNTHETIC citation destination; not a publication"))
    with page.expect_popup() as popup_info:
        links.last.click()
    popup = popup_info.value
    popup.wait_for_load_state()
    assert popup.url == urls[-1]
    expect(popup.locator("body")).to_contain_text("SYNTHETIC citation destination")
    popup.close()
    page.reload()
    expect(page.locator("a.source-card")).to_have_count(7)
    assert page.locator("a.source-card").evaluate_all("nodes => nodes.map(node => node.href)") == urls


def test_browser_empty_search_and_greeting_do_not_reuse_old_sources(ui, monkeypatch):
    page, _base = ui
    paper_replay(monkeypatch)
    submit(page, "检索近三年的柔性 Bio-Z 电极论文。")
    expect(page.locator(".message.assistant").last.locator("details.sources")).to_have_count(1)
    paper_replay(monkeypatch, empty=True)
    submit(page, "检索不存在材料 XQZ-999 的柔性电极论文。")
    empty = page.locator(".message.assistant").last
    expect(empty).to_contain_text("未找到足够相关的可核验论文")
    expect(empty.locator("a.source-card")).to_have_count(0)
    submit(page, "你好")
    greeting = page.locator(".message.assistant").last
    expect(greeting).not_to_contain_text("XQZ")
    expect(greeting.locator("a.source-card")).to_have_count(0)
    page.reload()
    expect(page.locator(".message.assistant")).to_have_count(3)
    expect(page.locator(".message.assistant").nth(1)).to_contain_text("未找到足够相关的可核验论文")
    expect(page.locator(".message.assistant").last.locator("a.source-card")).to_have_count(0)


def test_browser_pulse_candidate_plot_report_and_reload(ui, tmp_path):
    page, _base = ui
    raw = pulse_csv(column="ch4")
    page.locator("#attachment").set_input_files({"name": "SYNTHETIC-pulse-rate.csv", "mimeType": "text/csv", "buffer": raw})
    submit(page, "0.5–3 Hz带通，4阶，分析主要脉搏频率并画图。")
    last = page.locator(".message.assistant").last
    expect(last).to_contain_text("72 BPM")
    expect(last).to_contain_text("不等同于已验证心率")
    figure = last.locator(".artifact img")
    expect(figure).to_be_visible()
    expect(figure).to_have_js_property("complete", True)
    assert figure.evaluate("image => image.naturalWidth") > 0
    details = last.locator("details.trace")
    details.locator("summary").click()
    for name in ("load_experiment_data", "filter_signal", "spectral_analysis", "plot_signal"):
        expect(details).to_contain_text(name)
    with page.expect_download() as first:
        details.get_by_role("link", name="下载结构化实验报告 ↗").click()
    target = tmp_path / "pulse-report.md"
    first.value.save_as(target)
    report = target.read_bytes()
    assert "脉率候选为 72 BPM" in report.decode()
    assert hashlib.sha256(raw).hexdigest() in report.decode()
    page.reload()
    last = page.locator(".message.assistant").last
    expect(last).to_contain_text("72 BPM")
    expect(last.locator(".artifact img")).to_be_visible()
    last.locator("details.trace > summary").click()
    with page.expect_download() as second:
        last.get_by_role("link", name="下载结构化实验报告 ↗").click()
    second.value.save_as(target)
    assert target.read_bytes() == report


def test_browser_csv_filter_fft_figure_report_and_history(ui, tmp_path):
    page, _base = ui
    raw = pulse_csv(column="signal")
    digest = hashlib.sha256(raw).hexdigest()
    page.locator("#attachment").set_input_files({"name": "SYNTHETIC-browser-pulse.csv", "mimeType": "text/csv", "buffer": raw})
    submit(page, "做 0.5-3 Hz 带通滤波，找 FFT 主峰并画图，导出滤波 CSV")
    last = page.locator(".message.assistant").last
    expect(last).to_contain_text("1.2")
    image = last.locator(".artifact img")
    expect(image).to_be_visible()
    expect(image).to_have_js_property("complete", True)
    assert image.evaluate("image => image.naturalWidth") > 0
    details = last.locator("details.trace")
    details.locator("summary").click()
    expect(details).to_contain_text("load_csv")
    expect(details).to_contain_text("filter_signal")
    expect(details).to_contain_text("spectral_analysis")
    expect(details).to_contain_text("plot_signal")
    with page.expect_download() as download_info:
        details.get_by_role("link", name="下载结构化实验报告 ↗").click()
    report_path = tmp_path / "report.md"
    download_info.value.save_as(report_path)
    report = report_path.read_text()
    assert digest in report and "1.2" in report
    with page.expect_download() as csv_info:
        last.get_by_role("link", name="下载滤波 CSV ↗").click()
    csv_path = tmp_path / "filtered.csv"
    csv_info.value.save_as(csv_path)
    assert csv_path.read_text().startswith("time_s,filtered_signal")
    page.reload()
    expect(page.locator(".message.assistant")).to_have_count(1)
    expect(page.locator(".message.assistant").last).to_contain_text("1.2")
    expect(page.locator(".artifact img")).to_be_visible()
    assert any(hashlib.sha256(path.read_bytes()).hexdigest() == digest for path in application.MEASUREMENT_DIR.glob("*.csv"))


@pytest.mark.parametrize("fixture,query,answer", [("strain-gf2.csv", "计算应变传感器的 GF。", "GF为 2"), ("cycle-retention92.csv", "计算 1000 次循环后的保持率。", "1000 次循环保持率为 92%")])
def test_browser_curve_features_report_and_reload(ui, tmp_path, fixture, query, answer):
    page, _base = ui
    raw = (ROOT/"eval/fixtures"/fixture).read_bytes()
    digest = hashlib.sha256(raw).hexdigest()
    page.locator("#attachment").set_input_files({"name": "SYNTHETIC-"+fixture, "mimeType": "text/csv", "buffer": raw})
    submit(page, query)
    last = page.locator(".message.assistant").last
    expect(last).to_contain_text(answer)
    details = last.locator("details.trace")
    details.locator("summary").click()
    expect(details).to_contain_text("load_experiment_data")
    expect(details).to_contain_text("extract_features")
    with page.expect_download() as download:
        details.get_by_role("link", name="下载结构化实验报告 ↗").click()
    target = tmp_path/"curve-report.md"
    download.value.save_as(target)
    report = target.read_text()
    assert digest in report and "curve-features-v1" in report
    assert "mean_at_zero_strain" in report if fixture.startswith("strain") else '"target_cycle": 1000' in report
    page.reload()
    expect(page.locator(".message.assistant")).to_have_count(1)
    expect(page.locator(".message.assistant").last).to_contain_text(answer)
    if fixture.startswith("cycle"):
        page.locator("#attachment").set_input_files({"name": "SYNTHETIC-"+fixture, "mimeType": "text/csv", "buffer": raw})
        submit(page, "计算1200次循环后的保持率。")
        failed = page.locator(".message.assistant").last
        expect(failed).to_contain_text("未插值")
        expect(failed.locator(".stats > div")).to_have_count(0)
        expect(failed).not_to_contain_text("70%")
        page.reload()
        expect(page.locator(".message.assistant").last).to_contain_text("未插值")


def test_browser_provider_verify_switch_failure_and_reload(ui, monkeypatch):
    page, _base = ui

    def model(url, *, headers, payload):
        if payload["model"] == "replay/unavailable":
            raise urllib.error.HTTPError(url, 429, "synthetic rate limit", {}, None)
        return {"model": payload["model"], "choices": [{"message": {"content": "OK"}}]}, 1

    monkeypatch.setattr(application, "request_model_json", model)
    page.locator("details.connection > summary").click()
    page.locator("#provider-custom-model").fill("replay/browser-b")
    page.locator("#save-provider").click()
    expect(page.locator("#provider-feedback")).to_contain_text("已验证并切换")
    expect(page.locator("#provider")).to_have_text("browser-b · 已验证")
    assert json.loads(application.PROVIDER_SETTINGS_FILE.read_text())["model"] == "replay/browser-b"
    page.locator("#provider-custom-model").fill("replay/unavailable")
    page.locator("#save-provider").click()
    expect(page.locator("#provider-feedback")).to_contain_text("未切换")
    expect(page.locator("#provider-feedback")).to_contain_text("HTTP 429")
    expect(page.locator("#provider")).to_have_text("browser-b · 已验证")
    page.reload()
    expect(page.locator("#provider")).to_have_text("browser-b · 已验证")
    assert "synthetic-browser-key-not-a-secret" not in page.content()
    assert json.loads(application.PROVIDER_SETTINGS_FILE.read_text())["model"] == "replay/browser-b"


def test_browser_model_failure_discloses_origin_and_survives_reload(ui, monkeypatch):
    page, _base = ui
    calls = []
    def limited(url, **kwargs):
        calls.append(kwargs["payload"])
        raise urllib.error.HTTPError(url, 429, "private-error-not-for-output", {}, None)
    monkeypatch.setattr(application, "request_model_json", REAL_MODEL_REQUEST)
    monkeypatch.setattr(application, "request_json", limited)
    submit(page, "解释柔性电极接触阻抗。")
    last = page.locator(".message.assistant").last
    expect(last).to_contain_text("API 限流，已重试 1 次")
    expect(last.locator(".answer-origin")).to_have_text("未生成模型回答 · MODEL_RATE_LIMITED")
    expect(last.locator("a.source-card")).to_have_count(0)
    assert len(calls) == 2
    assert "private-error-not-for-output" not in page.content()
    page.reload()
    expect(page.locator(".message.assistant .answer-origin")).to_have_text("未生成模型回答 · MODEL_RATE_LIMITED")


def test_browser_database_busy_download_reload_and_retry_without_duplicate(ui, tmp_path):
    page, _base = ui
    raw = b"voltage_V,current_A\n-1,-.001\n-.1,-.0001\n0,0\n.1,.0001\n1,.001\n"
    lock = sqlite3.connect(application.DATABASE)
    lock.execute("BEGIN IMMEDIATE")
    try:
        page.locator("#attachment").set_input_files({"name": "SYNTHETIC-iv.csv", "mimeType": "text/csv", "buffer": raw})
        page.locator("#prompt").fill("分析上传的 I-V CSV 并归档。")
        page.locator("#send").click()
        expect(page.locator(".upload-recovery")).to_be_visible()
        expect(page.locator(".message.assistant").last).to_contain_text("归档未完成")
        expect(page.locator("#send")).to_be_enabled()
        with page.expect_download() as download_info:
            page.get_by_role("link", name="下载保留的原始 CSV ↗").click()
        target = tmp_path / "recovered.csv"
        download_info.value.save_as(target)
        assert target.read_bytes() == raw
        page.reload()
        expect(page.locator(".upload-recovery")).to_be_visible()
        assert lock.execute("SELECT COUNT(*) FROM measurements").fetchone()[0] == 0
    finally:
        lock.rollback()
        lock.close()
    page.locator("#attachment").set_input_files(str(target))
    submit(page, "分析上传的 I-V CSV 并归档。")
    with application.get_db() as db:
        assert db.execute("SELECT COUNT(*) FROM measurements").fetchone()[0] == 1
    page.reload()
    expect(page.locator(".upload-recovery")).to_have_count(0)


def test_browser_document_upload_citations_duplicate_and_reload(ui):
    page, _ = ui
    raw = document_pdf()
    page.locator("#attachment").set_input_files({"name": "SYNTHETIC-sop.pdf", "mimeType": "application/pdf", "buffer": raw})
    submit(page, "把这份两页 SOP PDF 加入知识库。")
    answer = page.locator(".message.assistant").last
    expect(answer).to_contain_text("已加入知识库")
    answer.locator(".document-index > details > summary").click()
    expect(answer.locator(".document-index")).to_contain_text(hashlib.sha256(raw).hexdigest())
    expect(answer.locator("a")).to_have_count(2)
    for number in (1, 2):
        with page.expect_popup() as opened:
            answer.get_by_role("link", name=f"p. {number} ·", exact=False).click()
        evidence = opened.value
        expect(evidence.locator("body")).to_contain_text(f'"page":{number}')
        if number == 2:
            expect(evidence.locator("body")).to_contain_text("1250")
        evidence.close()
    page.reload()
    expect(page.locator(".message.assistant")).to_have_count(1)
    expect(page.locator(".message.assistant")).to_contain_text("已加入知识库")
    page.locator("#attachment").set_input_files({"name": "SYNTHETIC-renamed.pdf", "mimeType": "application/pdf", "buffer": raw})
    submit(page, "再次导入同一份 SOP。")
    expect(page.locator(".message.assistant").last).to_contain_text("已存在，未重复归档")
    with application.get_db() as db:
        assert db.execute("SELECT COUNT(*) FROM documents").fetchone()[0] == 1
    page.reload()
    expect(page.locator(".message.assistant")).to_have_count(2)
    expect(page.locator(".message.assistant").last).to_contain_text("已存在，未重复归档")
    page.locator(".document-index > details > summary").last.click()
    expect(page.locator(".document-index").last).to_contain_text("index_document")


def test_browser_scanned_pdf_failure_and_original_question_survive_reload(ui):
    page, _ = ui
    query = "导入这份扫描版论文并提取方法。"
    page.locator("#attachment").set_input_files({"name": "SYNTHETIC-scan.pdf", "mimeType": "application/pdf", "buffer": document_pdf("scan")})
    submit(page, query)
    expect(page.locator(".message.assistant")).to_have_count(1)
    expect(page.locator(".message.assistant")).to_contain_text("OCR")
    expect(page.locator(".message.assistant")).not_to_contain_text("100 Hz")
    page.reload()
    expect(page.locator(".message.user")).to_contain_text(query)
    expect(page.locator(".message.assistant")).to_have_count(1)
    expect(page.locator(".message.assistant")).to_contain_text("OCR")
    page.locator(".document-index > details > summary").click()
    expect(page.locator(".document-index a")).to_have_count(0)
    expect(page.locator(".document-index")).to_contain_text("needs_clarification")
    with application.get_db() as db:
        assert db.execute("SELECT COUNT(*) FROM documents").fetchone()[0] == 0


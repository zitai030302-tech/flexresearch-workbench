"""Prove the evaluator detects corrupted results, not only happy-path fixtures."""

from __future__ import annotations

import json
from pathlib import Path

import pytest
from flask.testing import FlaskClient

import app as app_module
from flexresearch import LabAgent
from flexresearch.tooling import ToolRegistry
from scripts.run_agent_eval import ADAPTERS, load_cases, recorded_cost, retrieval_metrics


DATASET = Path(__file__).resolve().parents[2] / "eval/golden_cases.jsonl"


@pytest.mark.parametrize("mutation,metric", [("bpm", "scientific_calculation_accuracy"), ("order", "trajectory_correctness"), ("hash", "groundedness"), ("method", "groundedness"), ("upstream", "groundedness"), ("band", "groundedness")])
def test_pulse_eval_rejects_corrupted_http(monkeypatch, tmp_path, mutation, metric):
    original = FlaskClient.post
    def corrupt(self, path, *args, **kwargs):
        response = original(self, path, *args, **kwargs)
        if path == "/api/analyze" and response.status_code == 200:
            body = response.get_json()
            result = body["agent"]
            if mutation == "bpm":
                result["calculated_result"]["spectrum"]["pulse_rate_bpm"] = 120
            elif mutation == "order":
                result["trajectory"].reverse()
            elif mutation == "hash":
                result["artifacts"][0]["metadata"]["sha256"] = "0"*64
            elif mutation == "method":
                result["calculated_result"]["spectrum"]["pulse_rate_method"] = "invented"
            elif mutation == "upstream":
                for ref in result["source_refs"]:
                    ref["parameters"]["input_tool_run_id"] = "0"*32
            else:
                next(s for s in result["trajectory"] if s["tool_name"] == "filter_signal")["arguments"]["high_cut"] = 7
            response.set_data(json.dumps(body))
        return response
    monkeypatch.setattr(FlaskClient, "post", corrupt)
    outcome = run_case("signal-007", tmp_path)
    assert outcome.status == "failed" and outcome.metric_results[metric] is False


@pytest.mark.parametrize("mutation,metric", [("premature", "trajectory_correctness"), ("order", "trajectory_correctness"), ("hash", "groundedness"), ("origin", "groundedness"), ("band", "groundedness")])
def test_pending_export_eval_detects_http_corruption(monkeypatch, tmp_path, mutation, metric):
    original = FlaskClient.post
    def corrupt(self, path, *args, **kwargs):
        response = original(self, path, *args, **kwargs)
        body = response.get_json()
        if path == "/api/analyze" and mutation == "premature":
            body["responseState"] = "completed"
        elif path == "/api/research":
            analysis = body["analysis"]
            if mutation == "order":
                analysis["trajectory"].reverse()
            elif mutation == "hash":
                analysis["artifacts"][0]["metadata"]["parent_source_sha256"] = "0"*64
            elif mutation == "origin":
                analysis["state"]["pending_request_context"]["source_run_id"] = "0"*32
            elif mutation == "band":
                next(s for s in analysis["trajectory"] if s["tool_name"] == "filter_signal")["arguments"]["high_cut"] = 7
        response.set_data(json.dumps(body))
        return response
    monkeypatch.setattr(FlaskClient, "post", corrupt)
    outcome = run_case("experiment-005", tmp_path)
    assert outcome.status == "failed" and outcome.metric_results[metric] is False


@pytest.mark.parametrize("mutation,metric", [("numeric", "hallucination_rate"), ("claims", "hallucination_rate"), ("scope", "groundedness"), ("source", "groundedness"), ("tool", "task_success")])
def test_metadata_boundary_eval_rejects_corrupted_http(monkeypatch, tmp_path, mutation, metric):
    original = FlaskClient.post
    def corrupt(self, path, *args, **kwargs):
        response = original(self, path, *args, **kwargs)
        if path == "/api/research" and response.status_code == 200:
            body = response.get_json()
            if mutation == "numeric":
                body["answer"] += "采样率是100 Hz。"
            elif mutation == "claims":
                body["numericClaims"] = [{"sample_rate": 100}]
            elif mutation == "scope":
                body["paperEvidence"]["paper_id"] += 1
            elif mutation == "source":
                body["paperEvidence"]["source_sha256"] = "0" * 64
            else:
                body["tools"][0]["tool"] = "search_papers"
            response.set_data(json.dumps(body))
        return response
    monkeypatch.setattr(FlaskClient, "post", corrupt)
    result = run_case("literature-002", tmp_path)
    assert result.status == "failed" and result.metric_results[metric] is False


@pytest.mark.parametrize("mutation,metric", [("history", "hallucination_rate"), ("numeric", "hallucination_rate"), ("approval", "structured_output_validity"), ("missing_section", "structured_output_validity"), ("tool", "task_success"), ("source", "hallucination_rate")])
def test_initial_plan_eval_rejects_http_corruption(monkeypatch, tmp_path, mutation, metric):
    original = FlaskClient.post
    def corrupt(self, path, *args, **kwargs):
        response = original(self, path, *args, **kwargs)
        if path == "/api/research" and response.status_code == 200:
            body = response.get_json()
            plan = body["experimentPlan"]
            if mutation == "history":
                plan["observations"] = [{"experiment_id": 1, "result": "improved"}]
            elif mutation == "numeric":
                plan["frequency_sweep"]["frequencies_hz"] = [1000]
            elif mutation == "approval":
                plan["approval_required"] = False
            elif mutation == "missing_section":
                del plan["safety"]
            elif mutation == "tool":
                body["tools"][0]["tool"] = "unrelated"
            else:
                plan["basis"]["request_sha256"] = "0" * 64
            response.set_data(json.dumps(body))
        return response
    monkeypatch.setattr(FlaskClient, "post", corrupt)
    outcome = run_case("experiment-001", tmp_path)
    assert outcome.status == "failed" and outcome.metric_results[metric] is False


@pytest.mark.parametrize("mutation,metric", [("channel", "tool_argument_accuracy"), ("rate", "tool_argument_accuracy"), ("goal_source", "tool_argument_accuracy"), ("trajectory", "trajectory_correctness"), ("numeric", "task_success")])
def test_channel_switch_eval_rejects_real_http_corruption(monkeypatch, tmp_path, mutation, metric):
    original = FlaskClient.post
    def corrupt(self, path, *args, **kwargs):
        response = original(self, path, *args, **kwargs)
        if path == "/api/research" and response.status_code == 200:
            body = response.get_json()
            if mutation == "channel":
                body["tools"][0]["arguments"]["channel"] = "2"
            elif mutation == "rate":
                body["analysis"]["trajectory"][-1]["arguments"]["sample_rate"] = 50
            elif mutation == "goal_source":
                body["experimentContext"]["analysis_context"]["source_run_id"] = "unrelated-run"
            elif mutation == "trajectory":
                body["analysis"]["trajectory"].reverse()
            else:
                body["analysis"]["calculated_result"]["spectrum"]["dominant_frequency_hz"] = 2.4
            response.set_data(json.dumps(body))
        return response
    monkeypatch.setattr(FlaskClient, "post", corrupt)
    outcome = run_case("experiment-003", tmp_path)
    assert outcome.status == "failed" and outcome.metric_results[metric] is False


@pytest.mark.parametrize("mutation,metric", [("numeric", "scientific_calculation_accuracy"), ("unit", "scientific_calculation_accuracy"), ("window", "scientific_calculation_accuracy"), ("hash", "groundedness"), ("source_tool", "groundedness"), ("order", "task_success")])
def test_iv_evaluator_rejects_actual_http_result_corruption(monkeypatch, tmp_path, mutation, metric):
    original = FlaskClient.post
    def corrupt(self, path, *args, **kwargs):
        response = original(self, path, *args, **kwargs)
        if path == "/api/analyze" and response.status_code == 200:
            body = response.get_json()
            analysis = body["agent"]
            values = analysis["calculated_result"]["iv"]
            if mutation == "numeric":
                values["differential_resistance_ohm"] = 1
            elif mutation == "unit":
                values["parameters"]["output_unit"] = "mA"
            elif mutation == "window":
                values["parameters"]["selected_indices"] = [0, 1, 2, 3, 4]
            elif mutation == "hash":
                analysis["source_refs"][-1]["source_sha256"] = "0" * 64
            elif mutation == "source_tool":
                analysis["source_refs"][-1]["tool_run_id"] = "0" * 32
            else:
                analysis["trajectory"].reverse()
            response.set_data(json.dumps(body))
        return response
    monkeypatch.setattr(FlaskClient, "post", corrupt)
    result = run_case("data-004", tmp_path)
    assert result.status == "failed" and result.metric_results[metric] is False


@pytest.mark.parametrize("case_id,mutation,metric", [
    ("data-003", "slope", "scientific_calculation_accuracy"),
    ("data-003", "valid_count", "scientific_calculation_accuracy"),
    ("data-003", "hash", "structured_output_validity"),
    ("data-003", "tool", "task_success"),
    ("signal-005", "field", "recovery_rate"),
    ("signal-005", "invented_peak", "hallucination_rate"),
    ("experiment-004", "channel", "groundedness"),
    ("experiment-004", "peak", "scientific_calculation_accuracy"),
])
def test_scientific_context_evaluator_rejects_actual_response_corruption(monkeypatch, tmp_path, case_id, mutation, metric):
    original = FlaskClient.post
    def corrupt(self, path, *args, **kwargs):
        response = original(self, path, *args, **kwargs)
        target = "/api/research" if case_id == "experiment-004" else "/api/analyze"
        if path == target and response.is_json and response.status_code == 200:
            body = response.get_json()
            analysis = body["analysis" if case_id == "experiment-004" else "agent"]
            if mutation == "slope":
                analysis["calculated_result"]["statistics"]["slope"] = 100
            elif mutation == "valid_count":
                analysis["calculated_result"]["statistics"]["valid_point_count"] = 999
            elif mutation == "hash":
                for ref in analysis["source_refs"]:
                    ref["source_sha256"] = "0" * 64
            elif mutation == "tool":
                analysis["trajectory"][0]["tool_name"] = "unrelated"
            elif mutation == "field":
                body["clarificationFields"] = []
            elif mutation == "invented_peak":
                analysis["calculated_result"] = {"spectrum": {"dominant_frequency_hz": 1.2}}
            elif mutation == "channel":
                for ref in analysis["source_refs"]:
                    ref["channel"] = "ch14"
            else:
                analysis["calculated_result"]["spectrum"]["dominant_frequency_hz"] = 2.4
            response.set_data(json.dumps(body))
        return response
    monkeypatch.setattr(FlaskClient, "post", corrupt)
    outcome = run_case(case_id, tmp_path)
    assert outcome.status == "failed" and outcome.metric_results[metric] is False


@pytest.mark.parametrize("case_id,mutation,metric", [
    ("file-003", "tool", "tool_selection_accuracy"),
    ("file-003", "page", "citation_correctness"),
    ("file-003", "hash", "citation_correctness"),
    ("file-006", "duplicate", "structured_output_validity"),
    ("file-007", "success", "recovery_rate"),
    ("file-007", "method", "hallucination_rate"),
])
def test_document_eval_detects_corrupted_actual_upload(monkeypatch, tmp_path, case_id, mutation, metric):
    original = FlaskClient.post
    def corrupt(self, path, *args, **kwargs):
        response = original(self, path, *args, **kwargs)
        if path == "/api/documents" and response.is_json:
            payload = response.get_json()
            if mutation == "tool":
                payload["toolCalls"][0]["tool_name"] = "unrelated"
            elif mutation == "page":
                payload["documentIndex"]["citations"][1]["locator"] = "p. 1"
            elif mutation == "hash":
                payload["documentIndex"]["source_sha256"] = "f"*64
            elif mutation == "duplicate" and payload.get("duplicate"):
                payload["duplicate"] = False
            elif mutation == "success":
                payload["responseState"] = "completed"
            elif mutation == "method":
                payload["methodClaims"] = ["采样率100 Hz"]
            response.set_data(json.dumps(payload))
        return response
    monkeypatch.setattr(FlaskClient, "post", corrupt)
    outcome = run_case(case_id, tmp_path)
    assert outcome.status == "failed" and outcome.metric_results[metric] is False


def run_case(case_id, tmp_path):
    case = next(case for case in load_cases(DATASET) if case["id"] == case_id)
    return ADAPTERS[case_id](case, {"app_module": app_module, "scratch": tmp_path})


@pytest.mark.parametrize("value", [None, False, "0", -1, float("nan"), float("inf")])
def test_missing_or_invalid_cost_is_not_zero(value):
    assert recorded_cost(value) is None


def test_known_zero_and_positive_cost_are_preserved():
    assert recorded_cost(0) == 0.0
    assert recorded_cost(.125) == .125


def test_duplicate_retrieval_cannot_inflate_recall_or_precision():
    precision, recall, ranked = retrieval_metrics([{"id": "a"}] * 5, {"a", "b"}, lambda item: item["id"])
    assert precision == .2 and recall == .5
    assert len(ranked) == 5  # Duplicates consume real result slots.
    assert retrieval_metrics([], {"a"}, lambda item: item["id"])[:2] == (0, 0)


@pytest.mark.parametrize("mutation,metric", [
    ("numeric", "scientific_calculation_accuracy"),
    ("source", "groundedness"),
    ("order", "trajectory_correctness"),
])
def test_real_scientific_evaluator_rejects_corrupted_output(monkeypatch, tmp_path, mutation, metric):
    original = LabAgent.analyze_csv

    def corrupt(self, *args, **kwargs):
        result = original(self, *args, **kwargs)
        if mutation == "numeric":
            result.calculated_result["spectrum"]["dominant_frequency_hz"] = 99
        elif mutation == "source":
            for ref in result.source_refs:
                ref.source_sha256 = "0" * 64
        else:
            result.trajectory = list(reversed(result.trajectory))
        return result

    monkeypatch.setattr(LabAgent, "analyze_csv", corrupt)
    outcome = run_case("experiment-007", tmp_path)
    assert outcome.status == "failed"
    assert outcome.metric_results[metric] is False
    assert outcome.metric_results["task_success"] is False


@pytest.mark.parametrize("mutation,metric", [("name", "tool_selection_accuracy"), ("argument", "tool_argument_accuracy")])
def test_tool_evaluator_rejects_wrong_name_and_channel(monkeypatch, tmp_path, mutation, metric):
    original = ToolRegistry.execute

    def corrupt(self, name, arguments):
        execution = original(self, name, arguments)
        if name == "analyze_experiment":
            if mutation == "name":
                execution.tool_name = "unrelated_tool"
            else:
                execution.arguments = {**execution.arguments, "channel": "7"}
        return execution

    monkeypatch.setattr(ToolRegistry, "execute", corrupt)
    outcome = run_case("data-001", tmp_path)
    assert outcome.status == "failed"
    assert outcome.metric_results[metric] is False


def test_cost_evaluator_fails_when_persisted_cost_is_missing(monkeypatch, tmp_path):
    original = FlaskClient.get

    def omit_cost(self, path, *args, **kwargs):
        response = original(self, path, *args, **kwargs)
        if path.startswith("/api/agent-runs/") and response.is_json:
            payload = response.get_json()
            payload.pop("cost_usd", None)
            response.set_data(json.dumps(payload))
        return response

    monkeypatch.setattr(FlaskClient, "get", omit_cost)
    outcome = run_case("signal-009", tmp_path)
    assert outcome.status == "failed"
    assert outcome.metric_results["cost_accounting"] is False
    assert "cost_usd" not in outcome.measurements


@pytest.mark.parametrize("case_id,mutation,metric", [
    ("literature-003", "date_argument", "tool_argument_accuracy"),
    ("literature-003", "source_date", "task_success"),
    ("literature-003", "citation", "citation_correctness"),
    ("literature-004", "completed_empty", "recovery_rate"),
    ("literature-004", "fabricated_doi", "hallucination_rate"),
])
def test_paper_evaluator_rejects_corrupted_http_output(monkeypatch, tmp_path, case_id, mutation, metric):
    original = FlaskClient.post

    def corrupt(self, path, *args, **kwargs):
        response = original(self, path, *args, **kwargs)
        if path == "/api/research" and response.is_json:
            payload = response.get_json()
            if mutation == "date_argument":
                payload["tools"][0]["arguments"]["from_year"] = 1900
            elif mutation == "source_date":
                payload["sources"][0]["publication_date"] = "2035-01-01"
            elif mutation == "citation":
                payload["sources"][0]["doi"] = "10.9999/unobserved"
            elif mutation == "completed_empty":
                payload["responseState"] = "completed"
            else:
                payload["answer"] += " https://doi.org/10.9999/invented-paper"
            response.set_data(json.dumps(payload))
        return response

    monkeypatch.setattr(FlaskClient, "post", corrupt)
    outcome = run_case(case_id, tmp_path)
    assert outcome.status == "failed"
    assert outcome.metric_results[metric] is False


@pytest.mark.parametrize("case_id,mutation,metric", [
    ("failure-001", "completed", "recovery_rate"),
    ("failure-001", "canned_success", "hallucination_rate"),
    ("failure-002", "retry_count", "trajectory_correctness"),
    ("failure-002", "error_code", "recovery_rate"),
])
def test_failure_eval_detects_corrupted_api_result(monkeypatch, tmp_path, case_id, mutation, metric):
    original = FlaskClient.post
    def corrupt(self, path, *args, **kwargs):
        response = original(self, path, *args, **kwargs)
        if path == "/api/research" and response.is_json:
            result = response.get_json()
            if mutation == "completed":
                result["responseState"] = "completed"
            elif mutation == "canned_success":
                result["answerOrigin"] = "model"
                result["answer"] = "接触阻抗影响测量。"
            elif mutation == "retry_count":
                result["modelObservation"]["retryCount"] = 0
            else:
                result["errorCode"] = "unrelated"
            response.set_data(json.dumps(result))
        return response
    monkeypatch.setattr(FlaskClient, "post", corrupt)
    result = run_case(case_id, tmp_path)
    assert result.status == "failed" and result.metric_results[metric] is False


@pytest.mark.parametrize("mutation,metric", [("state", "recovery_rate"), ("hash", "recovery_rate"), ("retry", "trajectory_correctness"), ("fake_measurement", "recovery_rate")])
def test_database_eval_rejects_corrupted_partial_recovery(monkeypatch, tmp_path, mutation, metric):
    original = FlaskClient.post
    def corrupt(self, path, *args, **kwargs):
        response = original(self, path, *args, **kwargs)
        if path == "/api/analyze" and response.status_code == 503:
            result = response.get_json()
            if mutation == "state":
                result["responseState"] = "completed"
            elif mutation == "hash":
                result["recovery"]["sha256"] = "0" * 64
            elif mutation == "retry":
                result["recovery"]["transactionAttempts"] = []
            else:
                result["measurement"] = {"id": 999, "measurement_type": "fake"}
            response.set_data(json.dumps(result))
        return response
    monkeypatch.setattr(FlaskClient, "post", corrupt)
    result = run_case("failure-003", tmp_path)
    assert result.status == "failed" and result.metric_results[metric] is False


@pytest.mark.parametrize("case_id,mutation,metric", [
    ("data-005", "numeric", "scientific_calculation_accuracy"),
    ("data-006", "numeric", "scientific_calculation_accuracy"),
    ("data-005", "baseline", "tool_argument_accuracy"),
    ("data-005", "unit", "tool_argument_accuracy"),
    ("data-006", "hash", "groundedness"),
    ("data-006", "source_tool", "groundedness"),
    ("data-006", "target", "task_success"),
    ("data-005", "trajectory", "task_success"),
])
def test_curve_eval_rejects_corrupted_http_result(monkeypatch, tmp_path, case_id, mutation, metric):
    original = FlaskClient.post
    def corrupt(self, path, *args, **kwargs):
        response = original(self, path, *args, **kwargs)
        if path == "/api/analyze" and response.status_code == 200:
            payload = response.get_json()
            analysis = payload["agent"]
            features = analysis["calculated_result"]["curve_features"]
            if mutation == "numeric":
                features["gauge_factor" if case_id == "data-005" else "retention_percent"] = 999
            elif mutation == "baseline":
                features["parameters"]["baseline_resistance"] = 102
            elif mutation == "unit":
                analysis["trajectory"][-1]["arguments"]["strain_unit"] = "fraction"
            elif mutation == "hash":
                analysis["source_refs"][0]["source_sha256"] = "0" * 64
            elif mutation == "source_tool":
                analysis["source_refs"][0]["tool_run_id"] = "0" * 32
            elif mutation == "target":
                features["parameters"]["final_point"]["cycle"] = 1500
            else:
                analysis["trajectory"].reverse()
            response.set_data(json.dumps(payload))
        return response
    monkeypatch.setattr(FlaskClient, "post", corrupt)
    result = run_case(case_id, tmp_path)
    assert result.status == "failed" and result.metric_results[metric] is False


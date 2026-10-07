"""Truthfulness checks for the deterministic golden-case evaluator."""

from __future__ import annotations

from pathlib import Path
import json

from scripts.run_agent_eval import ADAPTERS, evaluate_cases, load_cases


ROOT = Path(__file__).resolve().parents[2]
DATASET = ROOT / "eval" / "golden_cases.jsonl"


def stable_projection(report: dict) -> dict:
    """Exclude measured runtime while retaining every scored outcome."""
    return {
        "summary": report["summary"],
        "metrics": report["metrics"],
        "statuses": [(case["caseId"], case["status"], case["metrics"]) for case in report["cases"]],
    }


def test_golden_dataset_has_unique_well_formed_cases_and_explicit_states():
    cases = load_cases(DATASET)
    assert len(cases) == 65
    assert len(cases) >= 40
    assert len({case["id"] for case in cases}) == len(cases)
    assert {case["current_status"]["state"] for case in cases} == {"implemented", "partial"}
    assert all(case["current_status"]["evidence"] for case in cases)


def test_every_implemented_case_has_a_deterministic_adapter():
    cases = load_cases(DATASET)
    implemented = {case["id"] for case in cases if case["current_status"]["state"] == "implemented"}
    assert implemented == set(ADAPTERS)


def test_deterministic_eval_scores_only_executed_cases_and_is_repeatable():
    cases = load_cases(DATASET)
    first = evaluate_cases(cases, DATASET)
    second = evaluate_cases(cases, DATASET)
    assert stable_projection(first) == stable_projection(second)
    assert first["summary"] == {
        "datasetCases": 65,
        "executed": 60,
        "passed": 60,
        "failed": 0,
        "skippedNotImplemented": 5,
        "skippedNotEvaluated": 0,
        "passRateOnExecuted": 1.0,
        "datasetExecutionCoverage": 0.9231,
        "capabilityStateCounts": {"implemented": 60, "partial": 5},
    }
    expected_totals = {
        "task_success": 60,
        "intent_accuracy": 7,
        "tool_selection_accuracy": 26,
        "tool_argument_accuracy": 17,
        "trajectory_correctness": 17,
        "scientific_calculation_accuracy": 22,
        "groundedness": 26,
        "hallucination_rate": 15,
        "retrieval_precision_at_5": 3,
        "retrieval_recall_at_5": 2,
        "citation_correctness": 6,
        "structured_output_validity": 30,
        "recovery_rate": 16,
        "latency": 5,
        "cost_accounting": 7,
        "report_content_quality": 1,
    }
    for metric, total in expected_totals.items():
        assert first["metrics"][metric]["status"] == "measured"
        assert first["metrics"][metric]["passed"] == total
        assert first["metrics"][metric]["total"] == total
        assert first["metrics"][metric]["passRate"] == 1.0
    assert first["metrics"]["groundedness"]["track"] == "semantic_rule_based"
    assert first["metrics"]["hallucination_rate"]["observedMean"] == 0.0
    assert first["runtime"]["externalLlmCalls"] == 0
    assert first["runtime"]["modelAdapterReplays"] == 13
    assert first["runtime"]["transportReplays"] == 6
    assert first["runtime"]["networkCalls"] == 0
    assert first["runtime"]["costUsd"] == 0.0
    assert all(case["status"] == "skipped_not_implemented" for case in first["cases"] if case["capabilityState"] != "implemented")


def test_golden_order_does_not_leak_rag_or_experiment_state():
    cases = load_cases(DATASET)
    forward = evaluate_cases(cases, DATASET)
    reverse = evaluate_cases(list(reversed(cases)), DATASET)
    assert forward["summary"]["failed"] == reverse["summary"]["failed"] == 0
    assert forward["summary"] == reverse["summary"]
    assert forward["metrics"] == reverse["metrics"]
    assert sorted((item["caseId"], item["status"], json.dumps(item["metrics"], sort_keys=True)) for item in forward["cases"]) == sorted((item["caseId"], item["status"], json.dumps(item["metrics"], sort_keys=True)) for item in reverse["cases"])


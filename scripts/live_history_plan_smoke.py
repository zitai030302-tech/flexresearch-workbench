"""Real localhost HTTP validation of a SYNTHETIC Bio-Z history plan.

Creates one project and three labelled experiments. No external model call.
"""

import hashlib
import json
import urllib.request
import uuid


BASE = "http://127.0.0.1:8765"
OPENER = urllib.request.build_opener(urllib.request.ProxyHandler({}))


def request(path, payload=None):
    raw = json.dumps(payload).encode() if payload is not None else None
    req = urllib.request.Request(BASE + path, data=raw, headers={"Content-Type": "application/json"})
    with OPENER.open(req, timeout=30) as response:
        return json.load(response)


def upload(raw, identifier, name):
    boundary = "smoke-" + uuid.uuid4().hex
    fields = {"experimentId": str(identifier), "question": "通道4计算平均阻抗"}
    parts = [f'--{boundary}\r\nContent-Disposition: form-data; name="{key}"\r\n\r\n{value}\r\n'.encode() for key, value in fields.items()]
    parts += [f'--{boundary}\r\nContent-Disposition: form-data; name="file"; filename="{name}"\r\nContent-Type: text/csv\r\n\r\n'.encode(), raw, f"\r\n--{boundary}--\r\n".encode()]
    req = urllib.request.Request(BASE + "/api/analyze", data=b"".join(parts), headers={"Content-Type": "multipart/form-data; boundary=" + boundary})
    with OPENER.open(req, timeout=30) as response:
        return json.load(response)


def main():
    assert request("/api/health")["status"] == "ok"
    project = request("/api/projects", {"name": "SYNTHETIC Bio-Z history planning validation"})["item"]["id"]
    ids, runs, hashes = [], [], []
    for index in range(3):
        metadata = {"synthetic": True, "sample_rate_hz": 100, "frequency_sweep_hz": [10, 100], "excitation_current": "approved synthetic fixture SOP", "electrode_geometry": "fixture array", "sop_reference": "SYNTHETIC-SOP", "device_id": "fixture AD5940", "material": "hydrogel A" if index == 0 else "hydrogel B", "posture": "rest", "activity_condition": "none", "temperature_c": 23}
        identifier = request("/api/experiments", {"name": f"SYNTHETIC Bio-Z {index+1}", "projectId": project, "metadata": metadata})["item"]["id"]
        raw = f"frequency_hz,ch4_real_ohm,ch4_imag_ohm\n100,{3*(index+1)},{4*(index+1)}\n10,{3*(index+1)},{4*(index+1)}\n".encode()
        uploaded = upload(raw, identifier, f"SYNTHETIC-BioZ-history-{index}.csv")
        assert uploaded["agent"]["status"] == "complete"
        ids.append(identifier)
        runs.append(uploaded["agentRun"]["runId"])
        hashes.append(hashlib.sha256(raw).hexdigest())
    selected = request("/api/research", {"query": f"读取实验{ids[-1]}", "useModel": False})
    result = request("/api/research", {"query": "根据前 3 次实验结果建议下一次实验。", "sessionId": selected["sessionId"], "useModel": False})
    assert result["responseState"] == "completed"
    plan = result["experimentPlan"]
    assert set(plan["experiment_ids"]) == set(ids) and len(plan["comparisons"]) == 2
    comparison_ids = []
    for index, comparison in enumerate(plan["comparisons"], 1):
        assert comparison["calculated_result"]["comparison"]["mean_delta"] == 5*index
        assert comparison["source_run_ids"] == [runs[0], runs[index]]
        assert {ref["source_sha256"] for ref in comparison["source_refs"]} == {hashes[0], hashes[index]}
        saved = request(f"/api/agent-runs/{comparison['comparison_run_id']}")
        assert "compare_experiments" in [item["tool_name"] for item in saved["toolCalls"]]
        comparison_ids.append(comparison["comparison_run_id"])
    assert plan["approval_required"] and plan["unresolved_parameters"] == []
    assert {item["name"] for item in plan["variables"]} == {"material"}
    assert all(item["source_run_ids"] for item in plan["recommendations"])
    restored = request(f"/api/sessions/{result['sessionId']}")
    assert restored["messages"][-1]["result"]["experimentPlan"] == plan
    parent = request(f"/api/agent-runs/{result['agentRun']['runId']}")
    assert parent["model"]["provider"] == "deterministic-python"
    print(json.dumps({"status": "completed", "synthetic": True, "projectId": project, "experimentIds": ids, "sourceRunIds": runs, "comparisonRunIds": comparison_ids, "planRunId": result["agentRun"]["runId"], "sessionId": result["sessionId"], "meanDeltasOhm": [5, 10], "externalModelCalls": 0, "browserUrl": BASE + f"/?session={result['sessionId']}"}, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()


"""Real local HTTP smoke: synthetic upload, saved settings, replay, report, plot.

Creates a clearly labelled SYNTHETIC dataset. Never calls an external model.
"""

import hashlib
import json
import math
import urllib.request
import uuid


BASE = "http://127.0.0.1:8765"
OPENER = urllib.request.build_opener(urllib.request.ProxyHandler({}))


def request(path, payload=None):
    body = json.dumps(payload).encode() if payload is not None else None
    req = urllib.request.Request(BASE + path, data=body, headers={"Content-Type": "application/json"})
    with OPENER.open(req, timeout=30) as response:
        return response.read()


def main():
    assert json.loads(request("/api/health"))["status"] == "ok"
    raw = ("time_s,ch4\n" + "\n".join(f"{i/100},{math.sin(2*math.pi*1.2*i/100)+.3*math.sin(2*math.pi*12*i/100)}" for i in range(1000))).encode()
    boundary = "flexresearch-" + uuid.uuid4().hex
    fields = {"bindContext": "true", "question": "SYNTHETIC 参数连续性验收：通道4做0.5–3 Hz带通滤波"}
    chunks = []
    for key, value in fields.items():
        chunks.append(f'--{boundary}\r\nContent-Disposition: form-data; name="{key}"\r\n\r\n{value}\r\n'.encode())
    chunks += [f'--{boundary}\r\nContent-Disposition: form-data; name="file"; filename="SYNTHETIC-processing-context.csv"\r\nContent-Type: text/csv\r\n\r\n'.encode(), raw, f"\r\n--{boundary}--\r\n".encode()]
    req = urllib.request.Request(BASE + "/api/analyze", data=b"".join(chunks), headers={"Content-Type": "multipart/form-data; boundary=" + boundary})
    with OPENER.open(req, timeout=30) as response:
        first = json.load(response)
    assert first["agent"]["status"] == "complete"
    second = json.loads(request("/api/research", {"query": "沿用刚才的滤波参数，分析主峰、导出CSV并画图", "sessionId": first["sessionId"], "useModel": False}))
    assert second["responseState"] == "completed"
    analysis = second["analysis"]
    assert abs(analysis["calculated_result"]["spectrum"]["dominant_frequency_hz"] - 1.2) < .01
    params = second["experimentContext"]["analysis_parameters"]
    assert params["parameter_source_run_id"] == first["agentRun"]["runId"]
    assert params["filter"] == {"low_cut": .5, "high_cut": 3., "order": 4}
    assert [item["tool_name"] for item in analysis["trajectory"]] == ["load_csv", "filter_signal", "spectral_analysis", "export_signal", "plot_signal"]
    filter_id = next(step["tool_run_id"] for step in analysis["trajectory"] if step["tool_name"] == "filter_signal")
    spectrum_id = next(step["tool_run_id"] for step in analysis["trajectory"] if step["tool_name"] == "spectral_analysis")
    assert any(ref["tool_run_id"] == spectrum_id and ref["parameters"]["input_tool_run_id"] == filter_id for ref in analysis["source_refs"])
    for artifact in analysis["artifacts"]:
        downloaded = request(artifact["url"])
        if artifact["metadata"]["format"] == "csv":
            assert hashlib.sha256(downloaded).hexdigest() == artifact["metadata"]["sha256"]
            assert artifact["metadata"]["parent_source_sha256"] == hashlib.sha256(raw).hexdigest()
        else:
            assert downloaded.startswith(b"\x89PNG")
    report = request(second["reportUrl"]).decode()
    assert first["agentRun"]["runId"] in report and hashlib.sha256(raw).hexdigest() in report
    restored = json.loads(request(f"/api/sessions/{first['sessionId']}"))
    assert restored["messages"][-1]["result"]["experimentContext"]["analysis_parameters"] == params
    print(json.dumps({"sessionId": first["sessionId"], "experimentId": first["experimentContext"]["experiment_id"], "firstRunId": first["agentRun"]["runId"], "parentRunId": second["agentRun"]["runId"], "analysisRunId": second["analysisRun"]["runId"], "parameters": params, "peakHz": 1.2, "externalModelCalls": 0, "status": "completed", "browserUrl": BASE + f"/?session={first['sessionId']}"}, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()


import hashlib
import io
import math

import pytest

import app as application


def data_csv(time_axis=True):
    header = "time_s,ch4,ch14" if time_axis else "ch4,ch14"
    return (header + "\n" + "\n".join((f"{i/100}," if time_axis else "") + f"{math.sin(2*math.pi*1.2*i/100)},{math.sin(2*math.pi*2.4*i/100)}" for i in range(1000))).encode()


def upload(client, **fields):
    return client.post("/api/analyze", data={"file": (io.BytesIO(fields.pop("raw", data_csv())), "uploaded.csv"), "bindContext": "true", **fields}, content_type="multipart/form-data")


def test_chat_upload_establishes_traceable_scope_and_supports_direct_followup():
    client = application.app.test_client()
    first = upload(client)
    assert first.status_code == 200
    context = first.json["experimentContext"]
    identifier = context["experiment_id"]
    experiment = client.get(f"/api/experiments/{identifier}").json["item"]
    assert experiment["metadata"]["record_type"] == "uploaded_dataset"
    result = client.post("/api/research", json={"sessionId": first.json["sessionId"], "query": "帮我分析通道4主要脉搏频率并画图", "useModel": False}).json
    assert result["responseState"] == "completed"
    assert result["experimentContext"]["experiment_id"] == identifier
    assert result["analysis"]["calculated_result"]["spectrum"]["dominant_frequency_hz"] == pytest.approx(1.2)
    assert all(ref["source_sha256"] == hashlib.sha256(data_csv()).hexdigest() for ref in result["analysis"]["source_refs"])


def test_new_upload_resets_old_channel_and_rate_in_same_session():
    client = application.app.test_client()
    first = upload(client, raw=data_csv(False), question="通道4，采样率100Hz，分析主峰").json
    assert first["experimentContext"]["sample_rate"] == 100
    assert first["experimentContext"]["channel"] == "4"
    second = upload(client, raw=data_csv(False), sessionId=str(first["sessionId"])).json
    assert second["experimentContext"]["experiment_id"] != first["experimentContext"]["experiment_id"]
    assert second["experimentContext"]["sample_rate"] is None
    assert second["experimentContext"]["channel"] is None
    followup = client.post("/api/research", json={"sessionId": first["sessionId"], "query": "继续分析通道4主峰", "useModel": False}).json
    assert followup["responseState"] == "needs_clarification"
    assert "spectrum" not in followup["analysis"]["calculated_result"]


def test_conflicting_upload_rates_are_rejected_without_a_new_record():
    client = application.app.test_client()
    result = upload(client, sampleRate="100", question="采样率50Hz，分析通道4主峰")
    assert result.status_code == 400
    with application.get_db() as db:
        assert db.execute("SELECT COUNT(*) FROM experiments").fetchone()[0] == 0


def test_upload_never_overwrites_a_changed_content_addressed_archive():
    client = application.app.test_client()
    first = upload(client).json
    path = application.MEASUREMENT_DIR / first["measurement"]["filename"]
    path.write_bytes(b"changed")
    response = upload(client)
    assert response.status_code == 400
    assert path.read_bytes() == b"changed"
    with application.get_db() as db:
        assert db.execute("SELECT COUNT(*) FROM experiments").fetchone()[0] == 1


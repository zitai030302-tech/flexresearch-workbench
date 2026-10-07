"""A chat quality request must inspect the selected raw file and persist proof."""

import hashlib
import io
import json

import numpy as np
import pandas as pd

import app as application
from flexresearch.agent import LabAgent
from flexresearch.lab_tools import build_lab_tool_registry


def test_chat_quality_question_uses_raw_tool_no_fft_and_restores_sources():
    client = application.app.test_client()
    time = np.arange(3000)/100
    signal = np.sin(2*np.pi*time)
    signal[1200:1600] += 8*np.sin(2*np.pi*10*time[1200:1600])
    raw = pd.DataFrame({'time_s': time, 'ch4': signal}).to_csv(index=False).encode()
    uploaded = client.post('/api/analyze', data={'file': (io.BytesIO(raw), 'synthetic-quality.csv'), 'bindContext': 'true'}, content_type='multipart/form-data').json
    response = client.post('/api/research', json={'query': '这段脉搏信号有没有明显运动伪差？', 'sessionId': uploaded['sessionId'], 'useModel': False})
    assert response.status_code == 200
    result = response.json
    assert result['responseState'] == 'completed'
    analysis = result['analysis']
    assert [item['tool_name'] for item in analysis['trajectory']] == ['load_experiment_data', 'load_csv', 'analyze_signal']
    quality = analysis['calculated_result']['signal_quality']
    assert quality['flagged_point_count'] >= 400
    assert '不能确认或排除' in result['answer']
    assert result['sources'] == []
    context, load, check = analysis['trajectory']
    ref = next(item for item in analysis['source_refs'] if item['tool_run_id'] == check['tool_run_id'])
    assert ref['source_sha256'] == hashlib.sha256(raw).hexdigest()
    assert ref['parameters']['input_tool_run_id'] == load['tool_run_id']
    assert ref['parameters']['input'] == 'raw signal' and ref['channel'] == 'ch4'
    assert any(path.read_bytes() == raw for path in application.MEASUREMENT_DIR.glob('*.csv'))
    restored = client.get(f"/api/sessions/{uploaded['sessionId']}").json['messages'][-1]['result']
    assert restored['analysis']['calculated_result']['signal_quality'] == quality
    report = client.get(result['reportUrl']).text
    assert 'signal-quality-heuristics-v1' in report and check['tool_run_id'] in report
    with application.get_db() as db:
        row = db.execute("SELECT parameters_json FROM analysis_runs WHERE analysis_type='signal_quality'").fetchone()
        assert json.loads(row['parameters_json'])['input_tool_run_id'] == load['tool_run_id']
        row = db.execute("SELECT source_refs_json FROM tool_calls WHERE tool_run_id=?", (check['tool_run_id'],)).fetchone()
        assert json.loads(row['source_refs_json'])[0]['tool_run_id'] == check['tool_run_id']
    assert not application.is_experiment_analysis_request('什么是运动伪差？', uploaded['sessionId'])


def test_quality_precedes_filter_and_never_examines_filtered_instead(tmp_path):
    time = np.arange(1000)/100
    raw = np.sin(2*np.pi*time)
    raw[500] += 100
    source = tmp_path/'raw.csv'
    pd.DataFrame({'time_s': time, 'ch4': raw}).to_csv(source, index=False)
    result = LabAgent(build_lab_tool_registry()).analyze_csv(str(source), '检查质量，然后0.5–3 Hz带通滤波')
    assert [step.tool_name for step in result.trajectory] == ['load_csv', 'analyze_signal', 'filter_signal']
    assert np.allclose(result.trajectory[1].arguments['signal'], raw)
    assert result.calculated_result['signal_quality']['flagged_point_count'] > 0


def test_quality_requires_explicit_channel_when_multiple(tmp_path):
    source = tmp_path/'channels.csv'
    pd.DataFrame({'ch1': range(20), 'ch2': range(20)}).to_csv(source, index=False)
    result = LabAgent(build_lab_tool_registry()).analyze_csv(str(source), '检查这段信号的质量')
    assert result.status == 'error' and '多个数值通道' in result.limitations[0]
    assert not result.calculated_result


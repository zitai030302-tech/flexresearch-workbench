"""Real stored analyses produce readable claims with matching tool provenance."""

import io
import math

import app as application
from flexresearch.report_review import review_report_content


def test_single_and_history_reports_explain_actual_fft_result_with_source():
    client = application.app.test_client()
    raw = ('time_s,ch4\n' + '\n'.join(f'{i/100},{math.sin(2*math.pi*1.2*i/100)}' for i in range(1000))).encode()
    uploaded = client.post('/api/analyze', data={'file': (io.BytesIO(raw), 'SYNTHETIC-report-content.csv'), 'bindContext': 'true', 'question': '通道4分析主要频率并画图'}, content_type='multipart/form-data').json
    agent = uploaded['agent']
    report = client.get(f"/api/agent-runs/{uploaded['agentRun']['runId']}/report.md").text
    assert 'FFT 主峰为 1.2 Hz' in report
    assert review_report_content(report, [agent]).status == 'supported_within_rubric'
    response = client.get(f"/api/agent-runs/{uploaded['agentRun']['runId']}/report-review")
    assert response.status_code == 200 and response.json['status'] == 'supported_within_rubric'
    assert response.json['human_review_required'] is True
    history = client.post('/api/research', json={'query': f"生成实验{uploaded['experimentContext']['experiment_id']}的报告", 'useModel': False}).json
    downloaded = client.get(history['reportUrl']).text
    assert review_report_content(downloaded, [agent]).status == 'supported_within_rubric'
    assert downloaded == history['experimentReport']['markdown']
    review = client.get(history['reportUrl'].replace('/report.md', '/report-review'))
    assert review.status_code == 200 and review.json['status'] == 'supported_within_rubric'
    assert '运行时解释原文' in downloaded  # Original record remains available.
    wrong = downloaded.replace('FFT 主峰为 1.2 Hz', 'FFT 主峰为 7.5 Hz')
    assert review_report_content(wrong, [agent]).status == 'needs_revision'
    assert client.get('/api/agent-runs/does-not-exist/report-review').status_code == 404


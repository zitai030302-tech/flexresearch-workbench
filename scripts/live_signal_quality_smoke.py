"""Real HTTP quality smoke on an explicitly synthetic injected burst."""

import hashlib
import json
import math
import urllib.request
import uuid

from live_processing_context_smoke import BASE, OPENER, request


def main():
    assert json.loads(request('/api/health'))['status'] == 'ok'
    values = [(i/100, math.sin(2*math.pi*i/100) + (8*math.sin(2*math.pi*10*i/100) if 1200 <= i < 1600 else 0)) for i in range(3000)]
    raw = ('time_s,ch4\n' + '\n'.join(f'{t:.17g},{v:.17g}' for t, v in values) + '\n').encode()
    boundary = 'flexresearch-' + uuid.uuid4().hex
    body = (f'--{boundary}\r\nContent-Disposition: form-data; name="bindContext"\r\n\r\ntrue\r\n--{boundary}\r\nContent-Disposition: form-data; name="file"; filename="SYNTHETIC-quality-burst-12-16s.csv"\r\nContent-Type: text/csv\r\n\r\n'.encode() + raw + f'\r\n--{boundary}--\r\n'.encode())
    req = urllib.request.Request(BASE+'/api/analyze', data=body, headers={'Content-Type': 'multipart/form-data; boundary='+boundary})
    with OPENER.open(req, timeout=30) as response:
        uploaded = json.load(response)
    payload = json.loads(request('/api/research', {'query': '这段脉搏信号有没有明显运动伪差？', 'sessionId': uploaded['sessionId'], 'useModel': False}))
    assert payload['responseState'] == 'completed'
    analysis = payload['analysis']
    assert [s['tool_name'] for s in analysis['trajectory']] == ['load_csv', 'analyze_signal']
    quality = analysis['calculated_result']['signal_quality']
    flagged = {i for interval in quality['artifact_intervals'] for i in range(interval['start_sample'], interval['end_sample_exclusive'])}
    truth = set(range(1200, 1600))
    iou = len(flagged & truth)/len(flagged | truth)
    assert iou > .95
    assert all(ref['source_sha256'] == hashlib.sha256(raw).hexdigest() for ref in analysis['source_refs'])
    assert payload['sources'] == [] and '不能确认或排除' in payload['answer']
    assert 'signal-quality-heuristics-v1' in request(payload['reportUrl']).decode()
    restored = json.loads(request(f"/api/sessions/{uploaded['sessionId']}"))
    assert restored['messages'][-1]['result']['analysis']['calculated_result']['signal_quality'] == quality
    print(json.dumps({'sessionId': uploaded['sessionId'], 'runId': payload['agentRun']['runId'], 'analysisRunId': payload['analysisRun']['runId'], 'intervalIoU': iou, 'flaggedPoints': quality['flagged_point_count'], 'qualityScoreMeaning': 'rule-unflagged fraction, NOT medical confidence', 'externalModelCalls': 0, 'browserUrl': BASE+f"/?session={uploaded['sessionId']}"}, ensure_ascii=False, indent=2))


if __name__ == '__main__':
    main()


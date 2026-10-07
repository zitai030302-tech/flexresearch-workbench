"""Read a selected real local history, create a report snapshot and review it."""

import argparse
import json

from live_processing_context_smoke import BASE, request


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('--experiment-id', type=int, required=True)
    parser.add_argument('--session-id', type=int, required=True)
    args = parser.parse_args()
    payload = json.loads(request('/api/research', {'query': f'生成实验{args.experiment_id}的报告', 'sessionId': args.session_id, 'useModel': False}))
    assert payload['responseState'] == 'completed', payload['responseState']
    url = payload['reportUrl']
    report = request(url).decode()
    assert report == payload['experimentReport']['markdown']
    review = json.loads(request(url.replace('/report.md', '/report-review')))
    assert review['status'] == 'supported_within_rubric', review
    assert review['human_review_required'] is True
    assert review['recognized_claim_count'] > 0
    restored = json.loads(request(f'/api/sessions/{args.session_id}'))
    assert restored['messages'][-1]['result']['reportUrl'] == url
    print(json.dumps({'sessionId': args.session_id, 'reportRunId': review['runId'], 'reviewStatus': review['status'], 'recognizedClaims': review['recognized_claim_count'], 'criteria': {item['name']: item['status'] for item in review['criteria']}, 'externalModelCalls': 0, 'browserUrl': BASE+f'/?session={args.session_id}'}, ensure_ascii=False, indent=2))


if __name__ == '__main__':
    main()


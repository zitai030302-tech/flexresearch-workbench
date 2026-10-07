"""Two real local chat turns; only the follow-up calls the configured model."""

import json

from live_processing_context_smoke import BASE, request


def main():
    first = json.loads(request('/api/research', {'query': '暗电流为什么重要？', 'useModel': False}))
    second = json.loads(request('/api/research', {'query': '那它怎么测量？', 'sessionId': first['sessionId'], 'useModel': True}))
    run = json.loads(request(f"/api/agent-runs/{second['agentRun']['runId']}"))
    model = run.get('model', {})
    context = model.get('conversationContext', {})
    passed = model.get('status') == 'complete' and context.get('messageCount') == 2 and second['sources'] == [] and second['privateEvidence'] == []
    print(json.dumps({'sessionId': first['sessionId'], 'runId': second['agentRun']['runId'], 'modelStatus': model.get('status'), 'requestedModel': model.get('requestedModel'), 'actualModel': model.get('actualModel'), 'context': context, 'answer': second['answer'], 'latencyMs': model.get('latencyMs'), 'costUsd': model.get('costUsd'), 'passedTransportAndContextChecks': passed, 'browserUrl': BASE+f"/?session={first['sessionId']}"}, ensure_ascii=False, indent=2))
    if not passed:
        raise SystemExit(1)


if __name__ == '__main__':
    main()


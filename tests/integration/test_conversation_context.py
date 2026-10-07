"""Ordinary follow-ups retain bounded context, never old evidence or files."""

import json
import urllib.error

import pytest

import app as application
from flexresearch.conversation_context import select_conversation_context


def pair(index, question='问题', answer='回答', **metadata):
    return [{'id': index*2+1, 'role': 'user', 'content': question}, {'id': index*2+2, 'role': 'assistant', 'content': answer, 'result_json': json.dumps({'contextKind': 'ordinary_chat_v1', 'contextEligible': True, **metadata})}]


def ask(client, query, session=None, model=True):
    result = client.post('/api/research', json={'query': query, 'sessionId': session, 'useModel': model, 'useOpenAlex': False})
    assert result.status_code == 200
    return result.json


def replay_provider(monkeypatch, answer='测量时遮光，并保持偏压和温度稳定。对比前记录测量条件。'):
    captured = []
    monkeypatch.setattr(application, 'model_configuration', lambda: {'configured': True, 'model': 'replay/context', 'apiKey': 'test-not-a-real-key', 'baseUrl': 'https://provider.example/v1'})
    def call(_url, headers, payload, attempts=2):
        captured.append(payload)
        return {'model': 'replay/context', 'choices': [{'message': {'content': answer}}], 'usage': {'prompt_tokens': 20, 'completion_tokens': 10, 'total_tokens': 30, 'cost': 0}}, 1
    monkeypatch.setattr(application, 'request_model_json', call)
    return captured


def test_real_two_turn_request_passes_topic_and_roles_then_records_only_ids(monkeypatch):
    captured = replay_provider(monkeypatch)
    client = application.app.test_client()
    first = ask(client, '暗电流为什么重要？')
    assert len(captured) == 1 and first['answerOrigin'] == 'model'
    second = ask(client, '那它怎么测量？', first['sessionId'])
    assert len(captured) == 2
    messages = captured[-1]['messages']
    assert [item['role'] for item in messages] == ['system', 'user', 'assistant', 'user']
    assert messages[1]['content'] == '暗电流为什么重要？'
    assert messages[2]['content'] == first['answer']
    assert 'Question: 那它怎么测量？' in messages[-1]['content']
    assert second['sources'] == [] and second['privateEvidence'] == []
    run = client.get(f"/api/agent-runs/{second['agentRun']['runId']}").json
    context = run['model']['conversationContext']
    assert context['messageCount'] == 2 and len(context['sourceMessageIds']) == 2
    assert '暗电流' not in json.dumps(context, ensure_ascii=False)
    assert context['oldSourcesIncluded'] is False and context['privateEvidenceIncluded'] is False
    restored = application.load_conversation_context(first['sessionId'])
    assert len(restored.messages) == 4
    assert [item.role for item in restored.messages] == ['user', 'assistant', 'user', 'assistant']
    profile = client.get('/api/providers').json
    assert profile['model']['connectionStatus'] == 'verified'
    assert profile['lastProbe']['origin'] == 'chat_completion'


def test_sessions_are_isolated_and_current_prompt_is_not_duplicated(monkeypatch):
    captured = replay_provider(monkeypatch)
    client = application.app.test_client()
    ask(client, '暗电流为什么重要？')
    fresh = ask(client, '那它怎么测量？')
    assert len(captured[-1]['messages']) == 2
    assert '暗电流' not in json.dumps(captured[-1]['messages'], ensure_ascii=False)
    assert len(application.load_conversation_context(fresh['sessionId']).messages) == 2


def test_ordinary_calculation_followup_is_not_mistaken_for_missing_experiment(monkeypatch):
    captured = replay_provider(monkeypatch, '可用无光电流与有效面积计算对应密度。先确认单位和测量条件。')
    client = application.app.test_client()
    first = ask(client, '暗电流为什么重要？')
    second = ask(client, '刚才那个指标怎么计算？', first['sessionId'])
    assert captured and '计算对应密度' in second['answer']
    assert second.get('errorCode') != 'experiment_context_required'
    explicit = ask(client, '继续分析这个实验', first['sessionId'])
    assert explicit['errorCode'] == 'experiment_context_required'


def test_context_keeps_whole_recent_pairs_with_hard_budget():
    rows = [row for index in range(6) for row in pair(index, f'问题{index}', f'回答{index}')]
    result = select_conversation_context(rows)
    assert len(result.messages) == 8 and result.messages[0].content == '问题2'
    assert result.source_message_ids == list(range(5,13)) and result.boundary == 'budget'
    result = select_conversation_context(rows, max_characters=13)
    assert len(result.messages) == 4 and result.messages[0].content == '问题4'
    assert result.boundary == 'budget'


@pytest.mark.parametrize('metadata', [{'sources': [{'title': 'old paper'}]}, {'privateEvidence': [{'excerpt': 'private'}]}, {'analysis': {'file': 'private.csv'}}, {'toolResults': [{'tool': 'load_csv'}]}, {'contextEligible': False}])
def test_tool_private_or_old_source_turn_is_a_boundary_not_skipped(metadata):
    rows = pair(0, 'old safe question', 'old safe answer') + pair(1, 'private question', 'private answer', **metadata) + pair(2, 'new question', 'new answer')
    result = select_conversation_context(rows)
    assert [item.content for item in result.messages] == ['new question', 'new answer']
    assert result.boundary == 'ineligible_turn'


@pytest.mark.parametrize('text', ['sk-or-v1-'+'x'*32, '密码：secret', '[local:2#3] 私有摘录', 'https://example.com/old-paper', '上传 CSV：private.csv', '/Users/person/private.csv'])
def test_sensitive_or_source_like_text_is_never_reused(text):
    assert select_conversation_context(pair(0, text)).messages == []


def test_legacy_malformed_or_incomplete_turn_is_not_backfilled():
    rows = pair(0)
    rows[-1]['result_json'] = '{}'
    assert select_conversation_context(rows).messages == []
    rows[-1]['result_json'] = 'broken'
    assert select_conversation_context(rows).boundary == 'malformed_turn'
    assert select_conversation_context(pair(0) + [{'id': 3, 'role': 'user', 'content': 'pending'}]).messages == []


def test_model_failure_fallback_does_not_become_context(monkeypatch):
    replay_provider(monkeypatch)
    def failed(*args, **kwargs):
        raise urllib.error.URLError(TimeoutError('timeout'))
    monkeypatch.setattr(application, 'request_model_json', failed)
    client = application.app.test_client()
    result = ask(client, '谈谈柔性器件的迟滞测量')
    assert '模型当前不可用' in result['answer']
    assert application.load_conversation_context(result['sessionId']).messages == []
    assert client.get('/api/providers').json['model']['connectionStatus'] == 'unavailable'


def test_private_document_answer_is_not_carried_into_next_remote_question(monkeypatch):
    import io
    captured = replay_provider(monkeypatch)
    client = application.app.test_client()
    private = '保密软电极实验笔记：独有样品代号 SECRET-LAB-ROSE，弯折测试按批准协议执行。'
    client.post('/api/documents', data={'file': (io.BytesIO(private.encode()), 'private-note.txt')}, content_type='multipart/form-data')
    local = ask(client, '保密软电极实验笔记的样品代号是什么？')
    assert local['privateEvidence'] and '[local:' in local['answer']
    assert application.load_conversation_context(local['sessionId']).messages == []
    assert captured == []
    ask(client, '你好', local['sessionId'])
    context = application.load_conversation_context(local['sessionId'])
    assert len(context.messages) == 2 and context.boundary == 'ineligible_turn'
    assert 'SECRET-LAB-ROSE' not in context.model_dump_json()


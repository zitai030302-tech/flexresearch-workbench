const $ = selector => document.querySelector(selector);
const escapeHtml = value => String(value ?? '').replace(/[&<>'"]/g, character => ({'&':'&amp;','<':'&lt;','>':'&gt;',"'":'&#39;','"':'&quot;'}[character]));

async function openRun(id) {
  const response = await fetch(`/api/agent-runs/${encodeURIComponent(id)}`);
  const run = await response.json();
  const tools = (run.toolCalls || []).map((call, index) => `<article class="step"><h3>${index + 1}. ${escapeHtml(call.tool_name)} · ${escapeHtml(call.status)} · ${escapeHtml(call.latency_ms)} ms</h3><b>Arguments</b><pre>${escapeHtml(JSON.stringify(call.arguments, null, 2))}</pre><b>Observation</b><pre>${escapeHtml(JSON.stringify(call.result_summary, null, 2))}</pre>${call.error ? `<p>${escapeHtml(call.error)}</p>` : ''}</article>`).join('');
  const section = (title, value) => `<details class="step"><summary>${escapeHtml(title)}</summary><pre>${escapeHtml(JSON.stringify(value, null, 2))}</pre></details>`;
  $('#detail').innerHTML = `<h2>${escapeHtml(run.query)}</h2><div class="summary"><span class="pill">${escapeHtml(run.intent)}</span><span class="pill">${escapeHtml(run.status)}</span><span class="pill">${escapeHtml(run.latency_ms)} ms</span><span class="pill">${escapeHtml(run.run_uuid.slice(0,12))}</span></div>${section('模型与用量', {model:run.model, tokens:run.token_usage, costUsd:run.cost_usd})}${section('运行状态与停止原因', run.state)}<h2>Tool trajectory</h2>${tools || '<p>本轮没有工具调用。</p>'}${section('最终结果与来源', run.final_result)}`;
}

async function loadRuns() {
  const response = await fetch('/api/agent-runs');
  const data = await response.json();
  $('#runs').innerHTML = data.items.map(item => `<button class="run" data-id="${escapeHtml(item.run_uuid)}"><b>${escapeHtml(item.query || 'Untitled run')}</b><small>${escapeHtml(item.intent)} · ${escapeHtml(item.status)} · ${escapeHtml(item.latency_ms)} ms</small><small>${escapeHtml(item.created_at)}</small></button>`).join('') || '<p>暂无运行记录。</p>';
  document.querySelectorAll('.run').forEach(button => button.onclick = () => openRun(button.dataset.id));
}

$('#refresh').onclick = loadRuns;
loadRuns();


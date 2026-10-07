const $ = selector => document.querySelector(selector);
const escapeHtml = value => String(value ?? '').replace(/[&<>'"]/g, char => ({ '&': '&amp;', '<': '&lt;', '>': '&gt;', "'": '&#039;', '"': '&quot;' }[char]));
const linkedSession = new URLSearchParams(window.location.search).get('session');
const state = { sessionId: Number(/^\d+$/.test(linkedSession || '') ? linkedSession : localStorage.getItem('flexresearch-session') || 0) || null };

function addMessage(role, content, extra = '') { if (role === 'user') $('#thread .welcome')?.remove(); const item = document.createElement('article'); item.className = `message ${role}`; item.innerHTML = role === 'assistant' ? `<div class="avatar">FR</div><div class="bubble"><span class="label">FlexResearch</span><p>${escapeHtml(content)}</p>${extra}</div>` : `<div class="bubble"><p>${escapeHtml(content)}</p></div>`; $('#thread').append(item); item.scrollIntoView({behavior:'smooth',block:'end'}); }
function sourceCards(sources) {
  if (!sources.length) return '';
  const labels = [...new Set(sources.map(item => item.source || '外部来源'))].join(' · ');
  return `<details class="tool-card sources"><summary>${escapeHtml(labels)} · ${sources.length}</summary><div class="source-grid">${sources.map(item => {
    const abstract = item.abstract ? `<p class="abstract">摘要摘录：${escapeHtml(item.abstract.slice(0,280))}${item.abstract.length > 280 ? '…' : ''}</p>` : '';
    return `<a class="source-card" href="${escapeHtml(item.url)}" target="_blank" rel="noreferrer"><b>${escapeHtml(item.title)}</b><small>${escapeHtml(item.source || '外部来源')} · ${escapeHtml(item.journal || '未标注期刊')} · ${escapeHtml(item.publication_date || item.year || '日期未提供')} · DOI ${escapeHtml(item.doi || '待核验')}</small>${abstract}</a>`;
  }).join('')}</div></details>`;
}
function traceCard(trace, critic) { const noteworthy = critic.length || trace.some(item => item.status === 'warning'); if (!noteworthy) return ''; const relevant = trace.filter(item => item.status === 'warning' || item.agent === 'Researcher' || item.agent === 'Source Critic'); return `<details class="trace"><summary>来源与执行细节</summary><ul>${relevant.map(item => `<li><b>${escapeHtml(item.agent)}</b> · ${escapeHtml(item.detail)}</li>`).join('')}${critic.map(item => `<li>核验提示 · ${escapeHtml(item)}</li>`).join('')}</ul></details>`; }
function artifactCards(items) {
  return (items || []).filter(item => item.url).map(item => item.metadata?.format === 'csv'
    ? `<p><a href="${escapeHtml(item.url)}" download>下载滤波 CSV ↗</a> · ${escapeHtml(item.metadata.point_count)} 点<small> · SHA-256 ${escapeHtml(item.metadata.sha256?.slice(0,12) || '')}</small></p>`
    : `<a class="artifact" href="${escapeHtml(item.url)}" target="_blank"><img src="${escapeHtml(item.url)}" alt="实验分析图" /></a>`).join('');
}

function uploadContextLabel(data) {
  const context = data.experimentContext;
  return context ? `<p><small>当前资料：实验 ${escapeHtml(context.experiment_id)} · 文件 ${escapeHtml(context.file_id)}。可以直接继续分析。</small></p>` : '';
}

function analysisCard(data) {
  const agent = data.agent || {};
  const statistics = agent.calculated_result?.statistics;
  const iv = agent.calculated_result?.iv;
  const artifacts = uploadContextLabel(data) + (iv ? ivCard(iv) : statistics ? statisticsCard(statistics) : signalQualityCard(agent.calculated_result?.signal_quality)) + artifactCards(agent.artifacts);
  const screening = iv || statistics || agent.clarification_fields?.length || (agent.intent !== 'data_profile' && !agent.calculated_result?.curve_features) ? [] : (data.metrics || []);
  return `<div class="tool-card"><h3>${escapeHtml(data.measurementType)} · 已归档 #${data.measurement.id}</h3><div class="stats">${screening.map(metric => `<div><span>${escapeHtml(metric.label)}</span><b>${escapeHtml(metric.value)}</b><small>${escapeHtml(metric.note)}</small></div>`).join('')}</div>${artifacts}${agentTraceCard(agent, `/api/agent-runs/${encodeURIComponent(data.agentRun.runId)}/report.md`)}<p>科学数值由确定性 Python 工具计算；原始 CSV 只读并以 SHA-256 固定。</p></div>`;
}
function agentTraceCard(agent, reportUrl) {
  const trajectory = agent.trajectory || [];
  const provenance = (agent.source_refs || []).map(item => `<li><b>${escapeHtml(item.processing_method)}</b> · ${escapeHtml(item.source_file)} · <code>${escapeHtml(item.tool_run_id.slice(0,10))}</code></li>`).join('');
  const goalSource = agent.state?.analysis_context?.source_run_id;
  const goalLink = goalSource ? `<p><a href="/api/agent-runs/${encodeURIComponent(goalSource)}/report.md">上一轮分析目标来源 ↗</a></p>` : '';
  return `<details class="trace agent-trace"><summary>Agent 轨迹 · ${trajectory.length} 个工具 · ${escapeHtml(agent.latency_ms || 0)} ms</summary><ol>${trajectory.map(item => `<li><b>${escapeHtml(item.tool_name)}</b> · ${escapeHtml(item.status)} · ${escapeHtml(item.latency_ms)} ms${item.error ? ` · ${escapeHtml(item.error)}` : ''}</li>`).join('')}</ol>${provenance ? `<h4>数据来源</h4><ul>${provenance}</ul>` : ''}${goalLink}<a href="${escapeHtml(reportUrl)}">下载结构化实验报告 ↗</a> · <a href="/debug">查看运行记录</a></details>`;
}
let providerOptions = [];
function reportReviewCard(url) {
  const match = String(url || '').match(/^\/api\/agent-runs\/([a-f0-9]{32})\/report\.md$/);
  return match ? `<details class="tool-card" data-report-review="${match[1]}"><summary>报告内容检查</summary><div class="report-review-result">展开后检查数字、来源和限制；仍需人工复核。</div></details>` : '';
}
document.addEventListener('toggle', async event => {
  const card = event.target;
  if (!(card instanceof HTMLDetailsElement) || !card.open || !card.dataset.reportReview || card.dataset.reviewLoaded) return;
  card.dataset.reviewLoaded = 'true';
  const content = card.querySelector('.report-review-result');
  content.textContent = '正在检查…';
  try {
    const response = await fetch(`/api/agent-runs/${encodeURIComponent(card.dataset.reportReview)}/report-review`);
    const data = await response.json();
    if (!response.ok) throw new Error(data.error || '检查失败');
    const names = {metric_and_source_support: '数字、单位、通道和来源', result_explanation_completeness: '结果是否得到解释', scope_and_noncausal_language: '结论范围', limitations_disclosed: '限制说明', result_categories_separated: '实测与计算分开', failure_state_disclosed: '未完成状态说明', unrecognized_numeric_prose: '未识别的数值表述'};
    const statuses = {pass: '满足本项', fail: '需修改', not_evaluated: '需人工'};
    const summary = {supported_within_rubric: '已识别表述符合规则，仍需人工复核。', needs_revision: '报告存在需要修改的内容。', needs_human_review: '部分内容超出规则范围，需要人工复核。'};
    content.innerHTML = `<p>${escapeHtml(summary[data.status] || data.status)}</p><ul>${data.criteria.map(item => `<li>${escapeHtml(names[item.name] || item.name)} · ${escapeHtml(statuses[item.status] || item.status)}${item.status !== 'pass' ? `<br><small>${escapeHtml(item.evidence.join('；'))}</small>` : ''}</li>`).join('')}</ul><small>只检查已支持的表述类型，不是科学或医学认证。</small>`;
  } catch (error) { content.textContent = `检查失败：${error.message}`; delete card.dataset.reviewLoaded; }
}, true);
function statisticsCard(statistics) {
  const number = value => typeof value === 'number' && Number.isFinite(value) ? Number(value.toPrecision(8)) : '不可计算';
  const fields = [['valid_point_count', '有效样本'], ['mean', '均值'], ['min', '最小值'], ['max', '最大值'], ['drift', '线性漂移'], ['slope', `斜率 /${statistics.slope_axis_unit === 'second' ? '秒' : '样本'}`]];
  return `<div class="tool-card signal-statistics"><h4>${escapeHtml(statistics.column)} · 基础统计</h4><div class="stats">${fields.map(([key, label]) => `<div data-stat="${key}"><span>${escapeHtml(label)}</span><b>${escapeHtml(number(statistics[key]))}</b></div>`).join('')}</div><small>有限值统计；漂移为拟合斜率 × 完整轴跨度，不代表因果变化。</small></div>`;
}
function ivCard(iv) {
  const number = value => typeof value === 'number' && Number.isFinite(value) ? Number(value.toPrecision(8)) : '无有限值';
  const parameters = iv.parameters;
  return `<div class="tool-card iv-analysis"><h4>I–V · 零偏附近微分电阻</h4><div class="stats"><div data-iv="resistance"><span>微分电阻 / Ω</span><b>${escapeHtml(number(iv.differential_resistance_ohm))}</b></div><div data-iv="window"><span>拟合窗口 / V</span><b>±${escapeHtml(number(parameters.window_half_width_V))}</b></div><div data-iv="points"><span>拟合样本</span><b>${escapeHtml(parameters.point_count)}</b></div></div><small>${escapeHtml(parameters.voltage_column)} → ${escapeHtml(parameters.current_column)} · 原始曲线近零拟合，不代表器件总体性能。</small><details><summary>方法与限制</summary><pre>${escapeHtml(JSON.stringify(parameters, null, 2))}</pre><ul>${iv.limitations.map(text => `<li>${escapeHtml(text)}</li>`).join('')}</ul></details></div>`;
}
function signalQualityCard(quality) {
  if (!quality) return '';
  const labels = { nonfinite: '缺失或非有限值', flat_segment: '近似平直', abrupt_change: '突变', high_window_variability: '局部波动偏高' };
  const number = value => value == null ? '不可计算' : Number(value.toPrecision(6));
  const intervals = quality.artifact_intervals.map(item => {
    const range = item.start_s == null ? `样本 [${item.start_sample}, ${item.end_sample_exclusive})` : `${number(item.start_s)}–${number(item.end_s_exclusive)} s（右端不含）`;
    return `<li>${escapeHtml(range)} · ${item.reasons.map(reason => escapeHtml(labels[reason] || reason)).join('、')}</li>`;
  }).join('');
  return `<details class="tool-card"><summary>信号质量 · ${escapeHtml(quality.interval_count)} 段可疑区间</summary><p>规则未标记比例 ${escapeHtml(number(quality.quality_score))}%（不是可靠性或诊断概率）</p><ul>${intervals || '<li>本次规则未标记区段，不代表不存在伪差。</li>'}</ul><p>均值 ${escapeHtml(number(quality.mean))} · 范围 ${escapeHtml(number(quality.minimum))}–${escapeHtml(number(quality.maximum))}<br>线性漂移 ${escapeHtml(number(quality.drift))} · 斜率 ${escapeHtml(number(quality.slope))} /${quality.slope_axis_unit === 'second' ? '秒' : '样本'}</p><details><summary>计算方法与限制</summary><pre>${escapeHtml(JSON.stringify(quality.quality_method, null, 2))}</pre><ul>${quality.limitations.map(item => `<li>${escapeHtml(item)}</li>`).join('')}</ul></details></details>`;
}
function experimentAnalysisCard(data) {
  if (!data.analysis) return '';
  const context = data.experimentContext || data.comparisonContext || {};
  const statistics = data.analysis.calculated_result?.statistics;
  const iv = data.analysis.calculated_result?.iv;
  const artifacts = (iv ? ivCard(iv) : statistics ? statisticsCard(statistics) : signalQualityCard(data.analysis.calculated_result?.signal_quality)) + artifactCards(data.analysis.artifacts) + reportReviewCard(data.reportUrl);
  const processing = context.analysis_parameters || {};
  const filter = processing.filter;
  const band = filter ? (filter.low_cut != null && filter.high_cut != null ? `${filter.low_cut}–${filter.high_cut} Hz 带通` : filter.low_cut != null ? `${filter.low_cut} Hz 高通` : `${filter.high_cut} Hz 低通`) : '';
  const filterLabel = filter ? `<p><small>本次处理：${escapeHtml(band)} · ${escapeHtml(filter.order)} 阶${processing.parameter_source_run_id ? ` · <a href="/api/agent-runs/${encodeURIComponent(processing.parameter_source_run_id)}/report.md">沿用参数来源</a>` : ''}</small></p>` : '';
  return `<div class="tool-card"><small>实验 ${escapeHtml(context.experiment_ids?.join(' → ') || context.experiment_id)} · 文件 ${escapeHtml(context.file_ids?.join(' / ') || context.file_id)}${context.channel ? ` · 通道 ${escapeHtml(context.channel)}` : ''}${context.sample_rate ? ` · ${escapeHtml(Number(context.sample_rate.toPrecision(8)))} Hz` : ''}</small>${filterLabel}${artifacts}${agentTraceCard(data.analysis, data.reportUrl)}</div>`;
}
const providerStatusLabels = { verified: '已验证', unavailable: '不可用', unverified: '未验证', unconfigured: '未配置' };
function shortModelName(modelId) { return String(modelId || 'API').split('/').pop().replace(':free', ''); }
function renderProviderStatus(model) {
  const status = model.connectionStatus || (model.configured ? 'unverified' : 'unconfigured');
  const displayedModel = model.actualModel || model.model;
  $('#provider').textContent = `${shortModelName(displayedModel)} · ${providerStatusLabels[status] || status}`;
  $('#provider').title = model.model ? `请求模型：${model.model}${model.actualModel ? `\n实际模型：${model.actualModel}` : ''}` : '尚未配置模型';
  $('#provider').classList.toggle('warning', status === 'unverified' || status === 'unconfigured');
  $('#provider').classList.toggle('unavailable', status === 'unavailable');
}
function updateModelNote() {
  const selected = providerOptions.find(item => item.id === $('#provider-model').value);
  $('#provider-model-note').textContent = selected?.note || '';
}
function renderLastProbe(probe) {
  if (!probe) { $('#provider-last-probe').textContent = '本次启动后尚未测试连接。'; return; }
  const checked = probe.checkedAt ? new Date(probe.checkedAt).toLocaleString() : '时间未知';
  const actual = probe.actualModel ? ` → ${probe.actualModel}` : '';
  const origin = probe.origin === 'chat_completion' ? '最近实际对话' : probe.origin === 'tool_completion' ? '最近工具请求' : '最近测试';
  $('#provider-last-probe').textContent = `${origin}：${probe.requestedModel || '未配置'}${actual} · ${providerStatusLabels[probe.status] || probe.status} · ${probe.latencyMs ?? 0} ms · ${checked}`;
  $('#provider-last-probe').classList.toggle('unavailable', !probe.ok);
}
async function loadHealth() {
  const data = await (await fetch('/api/health')).json();
  renderProviderStatus({model:data.providers.modelId,actualModel:data.providers.actualModel,configured:data.providers.modelConfigured,connectionStatus:data.providers.modelStatus});
}
async function loadProviders() {
  const data = await (await fetch('/api/providers')).json();
  const model = data.model;
  providerOptions = data.options;
  $('#provider-url').value = model.baseUrl;
  const options = model.model && !data.options.some(item => item.id === model.model) ? [{id:model.model,label:`当前：${model.model}`,note:''}, ...data.options] : data.options;
  $('#provider-model').innerHTML = options.map(item => `<option value="${escapeHtml(item.id)}" ${item.id === model.model ? 'selected' : ''}>${escapeHtml(item.label)}</option>`).join('');
  $('#key-status').textContent = `密钥：${model.keyStatus}`;
  $('#provider-warning').textContent = model.warning;
  $('#provider-warning').classList.toggle('warning', model.mode === 'demo' || model.connectionStatus !== 'verified');
  $('#source-status').innerHTML = data.sources.map(item => `<li><b>${escapeHtml(item.label)}</b><small>${escapeHtml(item.status)}</small></li>`).join('');
  $('#key-storage').textContent = data.keyStorage;
  renderProviderStatus(model);
  renderLastProbe(data.lastProbe);
  updateModelNote();
}
async function saveProvider() {
  const button = $('#save-provider');
  button.disabled = true;
  $('#provider-feedback').textContent = '正在验证候选模型…';
  try {
    const model = $('#provider-custom-model').value.trim() || $('#provider-model').value;
    const response = await fetch('/api/providers',{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify({baseUrl:$('#provider-url').value.trim(),model})});
    const data = await response.json();
    if (!response.ok) {
      await Promise.all([loadHealth(), loadProviders()]);
      $('#provider-feedback').textContent = `未切换 · ${data.probe?.detail || data.error || '验证失败'}`;
      return;
    }
    $('#provider-custom-model').value = '';
    await Promise.all([loadHealth(), loadProviders()]);
    $('#provider-feedback').textContent = `已验证并切换 · ${data.probe.actualModel || data.model.model} · ${data.probe.latencyMs} ms`;
  } catch (error) {
    $('#provider-feedback').textContent = `切换失败 · ${error.message}`;
  } finally { button.disabled = false; }
}
async function probeProvider() {
  const button = $('#probe-provider');
  button.disabled = true;
  $('#provider-feedback').textContent = '正在重新测试…';
  try {
    const response = await fetch('/api/providers/probe',{method:'POST'});
    const data = await response.json();
    await Promise.all([loadHealth(), loadProviders()]);
    $('#provider-feedback').textContent = data.ok ? `连接正常 · ${data.actualModel || data.requestedModel} · ${data.latencyMs} ms` : `连接失败 · ${data.detail}`;
  } catch (error) { $('#provider-feedback').textContent = `测试失败 · ${error.message}`; }
  finally { button.disabled = false; }
}
async function loadSessions() { const data = await (await fetch('/api/sessions')).json(); $('#session-list').innerHTML = data.items.map(item => `<button data-id="${item.id}" class="${item.id === state.sessionId ? 'active' : ''}"><b>${escapeHtml(item.title)}</b><small>${escapeHtml(item.updated_at.slice(0,16).replace('T',' '))}</small></button>`).join('') || '<small>暂无会话</small>'; document.querySelectorAll('#session-list button').forEach(button => button.onclick = () => openSession(Number(button.dataset.id))); }
function restoredResultCards(data = {}) {
  const analysis = data.analysis ? experimentAnalysisCard(data) : data.agent && data.measurement ? analysisCard(data) : '';
  const paper = data.paperEvidence;
  const paperBoundary = paper?.evidence_level === 'bibliographic_metadata_only' ? `<details class="tool-card paper-evidence"><summary>论文 ${escapeHtml(paper.paper_id)} · 仅书目记录</summary><p>${escapeHtml(paper.title)}</p><small>没有关联的摘要或全文；标题和 DOI 不作为实验参数的证据。</small></details>` : '';
  return answerOriginNote(data) + analysis + documentIndexCard(data) + methodCard(data.methodSummary) + paperBoundary + historyCard(data) + sourceCards(data.sources || []) + traceCard(data.trace || [], data.critic || []);
}

function documentIndexCard(data) {
  if (data.intent !== 'knowledge_ingest') return '';
  const index = data.documentIndex || {};
  const citations = (index.citations || []).filter(item => /^\/api\/documents\/\d+\/chunks\/\d+$/.test(item.url || ''));
  return `<div class="tool-card document-index"><details><summary>文档索引 · ${escapeHtml(data.responseState || 'partial')}</summary>${index.source_sha256 ? `<p>SHA-256 ${escapeHtml(index.source_sha256)}</p>` : ''}<p>${citations.map(item => `<a href="${escapeHtml(item.url)}" target="_blank" rel="noopener">${escapeHtml(item.locator)} · ${escapeHtml(item.citation)}</a>`).join('<br>')}</p>${(data.toolCalls || []).map(step => `<details><summary>${escapeHtml(step.tool_name)} · ${escapeHtml(step.status)}</summary><pre>${escapeHtml(JSON.stringify(step.arguments, null, 2))}</pre></details>`).join('')}<small>本地解析与索引；不等于方法提取或科学结论验证。</small></details></div>`;
}

function answerOriginNote(data) {
  if (data.answerOrigin === 'unavailable') return `<small class="answer-origin warning">未生成模型回答 · ${escapeHtml(data.errorCode || '请求未完成')}</small>`;
  if (data.answerOrigin === 'local_reference') return '<small class="answer-origin">本地参考短答 · 非模型生成</small>';
  if (data.answerOrigin === 'model') return `<small class="answer-origin">模型回答 · ${escapeHtml(data.modelObservation?.actualModel || data.modelObservation?.requestedModel || '模型未报告标识')}</small>`;
  return '';
}

function recoveryCard(recovery) {
  if (!recovery?.rawPreserved || !/^\/api\/upload-recovery\/[a-f0-9]{32}\/source$/.test(recovery.sourceUrl || '')) return '';
  return `<div class="tool-card upload-recovery"><h3>原始 CSV 恢复副本</h3><a href="${escapeHtml(recovery.sourceUrl)}">下载保留的原始 CSV ↗</a><p>${escapeHtml(recovery.filename)} · SHA-256 ${escapeHtml(recovery.sha256)}</p><small>${recovery.archiveCommitted ? '测量已归档，请勿重复上传。' : '未写入测量记录；文件保留在本机，可以稍后重试。'}</small></div>`;
}

function rememberUploadRecovery(message, recovery) {
  if (!recoveryCard(recovery)) return;
  localStorage.setItem('flexresearch-upload-recovery', JSON.stringify({message, recovery, sessionId:state.sessionId}));
}

function restoreUploadRecovery() {
  try {
    const pending = JSON.parse(localStorage.getItem('flexresearch-upload-recovery') || 'null');
    if (pending && pending.sessionId === state.sessionId && recoveryCard(pending.recovery)) addMessage('assistant', pending.message, recoveryCard(pending.recovery));
  } catch (_) { /* An invalid browser cache must not affect server recovery. */ }
}

function historyCard(data) {
  if (data.experimentReport?.markdown) {
    return `<div class="tool-card"><h3>实验历史报告</h3><p>实验 ${escapeHtml(data.experimentReport.experiment_ids.join('、'))} · ${data.experimentReport.source_run_ids.length} 次分析</p><a href="${escapeHtml(data.reportUrl)}">下载报告快照 ↗</a>${reportReviewCard(data.reportUrl)}<details><summary>范围与限制</summary><ul>${data.experimentReport.limitations.map(text => `<li>${escapeHtml(text)}</li>`).join('')}</ul></details></div>`;
  }
  const plan = data.experimentPlan;
  if (!plan?.recommendations) return '';
  if (plan.mode === 'initial_bioz_sweep_rules') {
    const list = items => `<ul>${items.map(text => `<li>${escapeHtml(text)}</li>`).join('')}</ul>`;
    const section = (key, title, items) => `<details data-plan-section="${key}"><summary>${title}</summary>${list(items)}</details>`;
    const download = /^\/api\/agent-runs\/[a-f0-9]{32}\/report\.md$/.test(data.planUrl || '') ? `<a href="${escapeHtml(data.planUrl)}">下载方案草案 ↗</a>` : '';
    return `<div class="tool-card initial-plan"><h3>Bio-Z 多频扫描 · 待审核</h3><p data-plan-section="objective">${escapeHtml(plan.objective)}</p>${download}${section('variables','变量与通道',plan.variables.map(item => item.description))}${section('controls','对照与重复',plan.controls)}${section('sample_rate','采样率 · 待确认',plan.sample_rate.requirements)}${section('frequency_sweep','扫频配置 · 待确认',plan.frequency_sweep.requirements)}${section('quality_checks','质量检查',plan.quality_checks)}${section('safety','安全与执行前确认',plan.safety)}${section('approval_required','审核清单',plan.unresolved_parameters)}<details><summary>依据与限制</summary><p>仅依据本轮请求，未使用历史实验或文献。</p>${list(plan.limitations)}<small>请求 SHA-256 ${escapeHtml(plan.basis.request_sha256)}</small></details></div>`;
  }
  const comparisons = (plan.comparisons || []).map(item => {
    const values = item.calculated_result.comparison;
    const unit = item.calculated_result.alignment.unit;
    const format = value => String(Number(Number(value).toPrecision(6)));
    return `<details><summary>实验 ${escapeHtml(item.experiment_ids.join(' → '))} · 均值差 ${escapeHtml(format(values.mean_delta))} ${escapeHtml(unit)}</summary><p>均值 ${escapeHtml(format(values.mean_baseline))} → ${escapeHtml(format(values.mean_comparison))} ${escapeHtml(unit)}；RMSE ${escapeHtml(format(values.rmse))} ${escapeHtml(unit)}。按共同频点对齐。</p><p><a href="/api/agent-runs/${escapeHtml(item.comparison_run_id)}/report.md">查看计算与原始来源 ↗</a></p><ul>${item.changed_conditions.map(change => `<li>${escapeHtml(change.name)}：${escapeHtml(JSON.stringify(change.baseline))} → ${escapeHtml(JSON.stringify(change.comparison))}</li>`).join('')}</ul></details>`;
  }).join('');
  const notes = (plan.comparison_notes || []).map(text => `<li>${escapeHtml(text)}</li>`).join('');
  return `<div class="tool-card"><h3>下一步建议 · 待审核</h3>${comparisons}${notes ? `<details><summary>比较范围与缺口</summary><ul>${notes}</ul></details>` : ''}${plan.recommendations.map(item => `<details><summary>${escapeHtml(item.action)}</summary><p>${escapeHtml(item.reason)}</p><p>${item.source_run_ids.map(id => `<a href="/api/agent-runs/${escapeHtml(id)}/report.md">来源分析 ${escapeHtml(id.slice(0,8))} ↗</a>`).join(' · ') || `来源文件编号：${escapeHtml(item.source_file_ids.join('、') || '未找到')}`}</p></details>`).join('')}<details><summary>待补参数 · ${plan.unresolved_parameters.length}</summary><ul>${plan.unresolved_parameters.map(text => `<li>${escapeHtml(text)}</li>`).join('')}</ul></details><details><summary>对照与质量检查</summary><ul>${[...(plan.controls || []), ...(plan.quality_checks || [])].map(text => `<li>${escapeHtml(text)}</li>`).join('')}</ul></details><small>基于历史记录的规则草案，不自动执行实验，也不推断因果或医学结论。</small></div>`;
}

function methodCard(summary) {
  if (!summary?.evidence?.length) return '';
  const labels = {device:'设备', electrodes:'电极与材料', acquisition:'采集条件', processing:'数据处理', validation:'验证方法'};
  return `<div class="tool-card"><h3>方法原文 · 文档 ${escapeHtml(summary.document_id)}</h3>${Object.entries(labels).map(([key,label]) => {
    const matches = summary.evidence.filter(item => item.category === key);
    return `<details><summary>${label} · ${matches.length} 条</summary>${matches.map(item => `<blockquote>${escapeHtml(item.quote)}<br><small><a href="/api/documents/${escapeHtml(summary.document_id)}/chunks/${escapeHtml(item.chunk_index)}" target="_blank">${escapeHtml(item.citation)}${item.page ? ` · 第 ${escapeHtml(item.page)} 页` : ' · 文本无页码'}</a></small></blockquote>`).join('') || '<p>未匹配到，未补全。</p>'}</details>`;
  }).join('')}<small>原文摘录，不是实验操作建议。SHA-256 ${escapeHtml(summary.source_sha256.slice(0,12))}</small></div>`;
}
async function openSession(id) { const response = await fetch(`/api/sessions/${id}`); const data = await response.json(); if (!response.ok) throw new Error(data.error || '会话读取失败'); state.sessionId = id; localStorage.setItem('flexresearch-session', id); $('#chat-title').textContent = data.session.title; $('#thread').innerHTML = ''; data.messages.forEach(message => addMessage(message.role, message.content, message.role === 'assistant' ? restoredResultCards(message.result || {}) : '')); await loadSessions(); }
async function runResearch(query) { addMessage('user', query); const response = await fetch('/api/research', {method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify({query,sessionId:state.sessionId,useModel:true,useOpenAlex:true})}); const data = await response.json(); if (!response.ok) throw new Error(data.error || '研究请求失败'); state.sessionId = data.sessionId; localStorage.setItem('flexresearch-session', String(data.sessionId)); $('#chat-title').textContent = query.slice(0,42); addMessage('assistant', data.answer, restoredResultCards(data)); await loadSessions(); }
async function uploadFile(file, note) {
  const isCsv = file.name.toLowerCase().endsWith('.csv');
  addMessage('user', note || `上传文件：${file.name}`);
  const form = new FormData();
  form.append('file', file);
  if (isCsv) {
    form.append('question', note || '读取并概览这个 CSV');
    form.append('bindContext', 'true');
    if (state.sessionId) form.append('sessionId', String(state.sessionId));
  } else {
    form.append('title', file.name.replace(/\.[^.]+$/, ''));
    form.append('question', note || `导入文档：${file.name}`);
    if (state.sessionId) form.append('sessionId', String(state.sessionId));
  }
  const response = await fetch(isCsv ? '/api/analyze' : '/api/documents', {method:'POST', body:form});
  const data = await response.json();
  if (!isCsv && data.sessionId && data.intent === 'knowledge_ingest') {
    state.sessionId = data.sessionId;
    localStorage.setItem('flexresearch-session', String(data.sessionId));
    $('#chat-title').textContent = (note || file.name).slice(0,42);
    addMessage('assistant', (!response.ok && data.error) || data.answer || '文档导入未完成。', documentIndexCard(data));
    await loadSessions();
    return;
  }
  if (!response.ok) {
    const error = new Error(data.error || '文件处理失败');
    error.recovery = data.recovery;
    throw error;
  }
  if (isCsv) {
    try {
      const pending = JSON.parse(localStorage.getItem('flexresearch-upload-recovery') || 'null');
      if (pending?.recovery?.sha256 === data.measurement?.sha256) localStorage.removeItem('flexresearch-upload-recovery');
    } catch (_) { /* Recovery is also durably stored by the server. */ }
    state.sessionId = data.sessionId;
    localStorage.setItem('flexresearch-session', String(data.sessionId));
    $('#chat-title').textContent = (note || file.name).slice(0,42);
    addMessage('assistant', data.answer, analysisCard(data));
    await loadSessions();
  } else addMessage('assistant', `已保存为文档 ${data.item.id}：“${data.item.title}”。可以问“提取文档${data.item.id}的实验方法”${data.item.pages > 1 ? `（${data.item.pages} 页）` : ''}。`);
}
$('#composer').addEventListener('submit', async event => { event.preventDefault(); const query = $('#prompt').value.trim(); const file = $('#attachment').files[0]; if (!query && !file) return; const button = $('#send'); button.disabled = true; button.textContent = '处理中…'; try { if (file) await uploadFile(file, query); else await runResearch(query); $('#prompt').value = ''; $('#attachment').value = ''; $('#attachment-name').textContent = '联网检索 · Shift+Enter 换行'; } catch (error) { const message = `任务没有完成：${error.message}`; addMessage('assistant', message, recoveryCard(error.recovery)); rememberUploadRecovery(message, error.recovery); } finally { button.disabled = false; button.innerHTML = '发送 <b>↑</b>'; loadHealth().catch(() => { $('#provider').title = '状态暂时无法刷新'; }); } });
$('#attachment').addEventListener('change', event => { const file = event.target.files[0]; $('#attachment-name').textContent = file ? `已选择：${file.name} · 发送后自动处理` : '联网检索 · Shift+Enter 换行'; });
$('#new-chat').onclick = () => { state.sessionId = null; localStorage.removeItem('flexresearch-session'); window.location.assign('/'); };
$('#save-provider').onclick = saveProvider;
$('#probe-provider').onclick = probeProvider;
$('#provider-model').onchange = () => { $('#provider-custom-model').value = ''; updateModelNote(); };
$('#prompt').addEventListener('keydown', event => { if (event.key === 'Enter' && !event.shiftKey) { event.preventDefault(); $('#composer').requestSubmit(); } });
document.querySelectorAll('[data-prompt]').forEach(button => button.onclick = () => { $('#prompt').value = button.dataset.prompt; $('#prompt').focus(); });
Promise.all([loadHealth(), loadProviders(), loadSessions()]).then(async () => { if (state.sessionId) await openSession(state.sessionId).catch(() => { state.sessionId = null; }); restoreUploadRecovery(); });


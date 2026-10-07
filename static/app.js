const output = document.querySelector('#output');
const escapeHtml = (value = '') => String(value).replace(/[&<>'"]/g, char => ({ '&': '&amp;', '<': '&lt;', '>': '&gt;', "'": '&#039;', '"': '&quot;' })[char]);

function evidenceMarkup(items) {
  return items.map(item => `<article class="source-item"><div><span class="source-meta">${escapeHtml(item.source)} · ${escapeHtml(item.year)}</span><h4>${escapeHtml(item.title)}</h4><p>${escapeHtml(item.summary)}</p><div class="tags">${item.tags.map(tag => `<span>${escapeHtml(tag)}</span>`).join('')}</div></div><a href="${item.url}" target="_blank" rel="noreferrer" aria-label="打开来源">↗</a></article>`).join('');
}

async function fetchEvidence(query = '') {
  const response = await fetch(`/api/literature?q=${encodeURIComponent(query)}`);
  const data = await response.json();
  document.querySelector('#evidence-list').innerHTML = evidenceMarkup(data.items);
  return data;
}

function projectMarkup(items) {
  if (!items.length) return '<p class="empty-state">还没有项目。创建第一条项目记录后，实验与文献资料就有了可追溯的归属。</p>';
  return items.map(item => `<article><div><span>${escapeHtml(item.track)} · ${escapeHtml(item.status)}</span><strong>${escapeHtml(item.name)}</strong><small>${escapeHtml(item.objective || '未填写研究目标')}</small></div><b>${escapeHtml(item.owner || '未指定')}</b></article>`).join('');
}

function sampleMarkup(items) {
  if (!items.length) return '<p class="empty-state">尚未登记样品。样品编号会成为后续测试 CSV、工艺与结论的共同锚点。</p>';
  const statusLabel = { fabricating: '制备中', testing: '测试中', archived: '已归档' };
  return items.map(item => `<article><div><span>${escapeHtml(statusLabel[item.status] || item.status)} · ${escapeHtml(item.project_name || '未关联项目')}</span><strong>${escapeHtml(item.sample_code)}</strong><small>${escapeHtml(item.material || '未记录材料 / 结构')}</small></div><b>${escapeHtml(item.process_note || '—')}</b></article>`).join('');
}

function measurementMarkup(items) {
  if (!items.length) return '<p class="empty-state">尚未归档测试。分析 CSV 后会自动保存原始文件指纹、识别类型和计算结果。</p>';
  return items.map(item => `<article><div><span>${escapeHtml(item.measurement_type)} · ${escapeHtml(item.sample_code || '未关联样品')}</span><strong>${escapeHtml(item.filename)}</strong><small>${item.point_count} 点 · SHA ${escapeHtml(item.sha256.slice(0, 10))}</small></div><b>${escapeHtml(item.created_at.slice(0, 10))}</b></article>`).join('');
}

async function fetchSamples() {
  const response = await fetch('/api/samples');
  const data = await response.json();
  document.querySelector('#sample-list').innerHTML = sampleMarkup(data.items);
  const select = document.querySelector('#analysis-sample');
  const current = select.value;
  select.innerHTML = `<option value="">不关联样品</option>${data.items.map(item => `<option value="${item.id}">${escapeHtml(item.sample_code)}</option>`).join('')}`;
  if ([...select.options].some(option => option.value === current)) select.value = current;
}

async function fetchMeasurements() {
  const response = await fetch('/api/measurements');
  const data = await response.json();
  document.querySelector('#measurement-list').innerHTML = measurementMarkup(data.items);
}

async function fetchProjects() {
  const response = await fetch('/api/projects');
  const data = await response.json();
  document.querySelector('#project-list').innerHTML = projectMarkup(data.items);
  const select = document.querySelector('#sample-project');
  const current = select.value;
  select.innerHTML = `<option value="">暂不关联</option>${data.items.map(item => `<option value="${item.id}">${escapeHtml(item.name)}</option>`).join('')}`;
  if ([...select.options].some(option => option.value === current)) select.value = current;
}

function privateResultMarkup(items, query) {
  if (!items.length) return query ? '<p class="empty-state">没有匹配内容。请尝试更短的关键词或先导入资料。</p>' : '';
  return items.map(item => `<article><div><span>${escapeHtml(item.extension.slice(1).toUpperCase())} · ${item.characters.toLocaleString()} 字符 · 匹配 ${item.score}</span><strong>${escapeHtml(item.title)}</strong><p>${escapeHtml(item.excerpt)}</p></div><i title="SHA-256">${escapeHtml(item.sha256.slice(0, 10))}</i></article>`).join('');
}

function showOutput(title, body) {
  output.hidden = false;
  output.innerHTML = `<div class="output-header"><div class="eyebrow">Reviewable draft</div><h2>${title}</h2><button id="close-output" aria-label="关闭结果">×</button></div>${body}`;
  output.scrollIntoView({ behavior: 'smooth', block: 'start' });
  document.querySelector('#close-output').onclick = () => { output.hidden = true; };
}

document.querySelector('#assistant-form').addEventListener('submit', async event => {
  event.preventDefault();
  const question = document.querySelector('#assistant-question').value.trim();
  if (!question) { alert('请先输入一个研究问题。'); return; }
  const button = event.currentTarget.querySelector('button'); button.disabled = true; button.textContent = '正在检索本地证据…';
  try {
    const response = await fetch('/api/assistant', { method: 'POST', headers: { 'Content-Type': 'application/json' }, body: JSON.stringify({ question }) });
    const data = await response.json(); if (!response.ok) throw new Error(data.error || '助手暂时无法回答');
    const publicSources = data.publicEvidence.map(item => `<a href="${item.url}" target="_blank" rel="noreferrer">${escapeHtml(item.title)} <span>↗</span></a>`).join('');
    const privateSources = data.privateEvidence.length ? data.privateEvidence.map(item => `<li><b>${escapeHtml(item.title)}</b><span>${escapeHtml(item.excerpt)}</span></li>`).join('') : '<li>本地资料库中暂未检索到直接匹配内容。</li>';
    showOutput(`${escapeHtml(data.track)} · 证据导航`, `<p class="assistant-answer">${escapeHtml(data.answer)}</p><div class="output-columns"><div><h3>建议的下一步</h3><ol>${data.nextActions.map(action => `<li>${escapeHtml(action)}</li>`).join('')}</ol></div><div><h3>优先关注指标</h3><ul>${data.metrics.map(metric => `<li>${escapeHtml(metric)}</li>`).join('')}</ul></div></div><div class="source-strip"><h3>公开可核验证据</h3>${publicSources}</div><div class="private-strip"><h3>本地资料命中</h3><ul>${privateSources}</ul></div><p class="disclaimer">${escapeHtml(data.disclaimer)}</p>`);
  } catch (error) { alert(error.message); } finally { button.disabled = false; button.innerHTML = '生成证据导航 <span>→</span>'; }
});

document.querySelector('#literature-form').addEventListener('submit', async event => {
  event.preventDefault();
  const query = document.querySelector('#literature-query').value;
  const result = await fetchEvidence(query);
  const container = document.querySelector('#literature-results');
  container.innerHTML = result.items.slice(0, 2).map(item => `<a href="${item.url}" target="_blank" rel="noreferrer"><b>${escapeHtml(item.title)}</b><span>${escapeHtml(item.source)} · ${escapeHtml(item.year)} ↗</span></a>`).join('');
});

document.querySelector('#planner-form').addEventListener('submit', async event => {
  event.preventDefault();
  const button = event.currentTarget.querySelector('button'); button.disabled = true; button.textContent = '正在生成…';
  try {
    const response = await fetch('/api/plan', { method: 'POST', headers: { 'Content-Type': 'application/json' }, body: JSON.stringify({ track: document.querySelector('#track').value, goal: document.querySelector('#goal').value }) });
    const plan = await response.json();
    showOutput(`${escapeHtml(plan.track)} · 实验审阅草案`, `<div class="goal-box"><span>研究目标</span><strong>${escapeHtml(plan.userGoal)}</strong></div><div class="output-columns"><div><h3>建议工作流</h3><ol>${plan.steps.map(step => `<li>${escapeHtml(step)}</li>`).join('')}</ol></div><div><h3>优先指标</h3><ul>${plan.metrics.map(metric => `<li>${escapeHtml(metric)}</li>`).join('')}</ul><h3>需提前排查</h3><ul class="risk-list">${plan.risks.map(risk => `<li>${escapeHtml(risk)}</li>`).join('')}</ul></div></div><div class="source-strip"><h3>可核验证据</h3>${plan.evidence.map(item => `<a href="${item.url}" target="_blank" rel="noreferrer">${escapeHtml(item.title)} <span>↗</span></a>`).join('')}</div><p class="disclaimer">${escapeHtml(plan.disclaimer)}</p>`);
  } finally { button.disabled = false; button.innerHTML = '生成审阅草案 <span>→</span>'; }
});

document.querySelector('#analysis-form').addEventListener('submit', async event => {
  event.preventDefault(); const file = document.querySelector('#csv-file').files[0];
  if (!file) { alert('请先选择一个 CSV 文件。'); return; }
  const button = event.currentTarget.querySelector('button'); button.disabled = true; button.textContent = '正在分析…';
  try {
    const payload = new FormData(); payload.append('file', file); payload.append('sampleId', document.querySelector('#analysis-sample').value);
    const response = await fetch('/api/analyze', { method: 'POST', body: payload }); const data = await response.json();
    if (!response.ok) throw new Error(data.error || '分析失败');
    const points = data.series.map(point => `${point.x},${point.y}`).join(' ');
    const x = data.series.map(d => d.x), y = data.series.map(d => d.y); const minX = Math.min(...x), maxX = Math.max(...x), minY = Math.min(...y), maxY = Math.max(...y);
    const path = data.series.map(d => `${((d.x-minX)/(maxX-minX || 1)*88+6).toFixed(2)},${(94-(d.y-minY)/(maxY-minY || 1)*82).toFixed(2)}`).join(' ');
    showOutput(`${escapeHtml(data.measurementType)} · 测试初筛结果`, `<div class="analysis-summary"><span>已识别列：<b>${escapeHtml(data.columns.x)}</b> → <b>${escapeHtml(data.columns.y)}</b></span><span>${data.points} 个有效数据点 · 已归档 #${data.measurement.id}</span></div><div class="metric-grid">${data.metrics.map(metric => `<div><span>${escapeHtml(metric.label)}</span><strong>${escapeHtml(metric.value)}</strong><small>${escapeHtml(metric.note)}</small></div>`).join('')}</div><div class="chart"><div><span>${escapeHtml(data.columns.y)}</span><svg viewBox="0 0 100 100" preserveAspectRatio="none" aria-label="数据折线图"><path class="axis" d="M6 6 V94 H94"/><polyline points="${path}" /></svg><span>${escapeHtml(data.columns.x)} →</span></div></div><p class="disclaimer">${escapeHtml(data.interpretation)}</p>`);
    await fetchMeasurements();
  } catch (error) { alert(error.message); } finally { button.disabled = false; button.textContent = '分析并归档'; }
});

document.querySelector('#project-form').addEventListener('submit', async event => {
  event.preventDefault();
  const button = event.currentTarget.querySelector('button'); button.disabled = true; button.textContent = '正在保存…';
  try {
    const response = await fetch('/api/projects', { method: 'POST', headers: { 'Content-Type': 'application/json' }, body: JSON.stringify({ name: document.querySelector('#project-name').value, track: document.querySelector('#project-track').value, owner: document.querySelector('#project-owner').value, objective: document.querySelector('#project-objective').value }) });
    const data = await response.json(); if (!response.ok) throw new Error(data.error || '保存失败');
    event.currentTarget.reset(); await fetchProjects();
  } catch (error) { alert(error.message); } finally { button.disabled = false; button.innerHTML = '建立本地项目 <span>→</span>'; }
});

document.querySelector('#sample-form').addEventListener('submit', async event => {
  event.preventDefault();
  const button = event.currentTarget.querySelector('button'); button.disabled = true; button.textContent = '正在保存…';
  try {
    const response = await fetch('/api/samples', { method: 'POST', headers: { 'Content-Type': 'application/json' }, body: JSON.stringify({ sampleCode: document.querySelector('#sample-code').value, projectId: document.querySelector('#sample-project').value, material: document.querySelector('#sample-material').value, processNote: document.querySelector('#sample-process').value, status: document.querySelector('#sample-status').value }) });
    const data = await response.json(); if (!response.ok) throw new Error(data.error || '保存失败');
    event.currentTarget.reset(); await fetchSamples();
  } catch (error) { alert(error.message); } finally { button.disabled = false; button.innerHTML = '登记样品 <span>→</span>'; }
});

document.querySelector('#document-form').addEventListener('submit', async event => {
  event.preventDefault(); const file = document.querySelector('#document-file').files[0];
  if (!file) { alert('请选择要导入的本地资料。'); return; }
  const button = event.currentTarget.querySelector('button'); button.disabled = true; button.textContent = '正在导入…';
  try {
    const payload = new FormData(); payload.append('title', document.querySelector('#document-title').value); payload.append('file', file);
    const response = await fetch('/api/documents', { method: 'POST', body: payload }); const data = await response.json(); if (!response.ok) throw new Error(data.error || '导入失败');
    event.currentTarget.reset(); document.querySelector('#private-query').value = data.item.title; document.querySelector('#private-search-form').requestSubmit();
  } catch (error) { alert(error.message); } finally { button.disabled = false; button.textContent = '导入本地资料'; }
});

document.querySelector('#private-search-form').addEventListener('submit', async event => {
  event.preventDefault(); const query = document.querySelector('#private-query').value.trim();
  const response = await fetch(`/api/private-search?q=${encodeURIComponent(query)}`); const data = await response.json();
  document.querySelector('#private-results').innerHTML = privateResultMarkup(data.items, query);
});

fetchEvidence();
fetchProjects();
fetchSamples();
fetchMeasurements();


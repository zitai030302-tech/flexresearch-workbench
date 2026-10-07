const escapeHtml = value => String(value ?? '').replace(/[&<>'"]/g, char => ({ '&': '&amp;', '<': '&lt;', '>': '&gt;', "'": '&#039;', '"': '&quot;' }[char]));

function renderSummary(summary) {
  const root = document.querySelector('#benchmark-summary');
  root.innerHTML = summary.groups?.length ? summary.groups.map(group => `<article><b>${escapeHtml(group.metricName)} <span>${escapeHtml(group.metricUnit)}</span></b><small>${group.count} 条 · DOI 已核验 ${group.verifiedCount}/${group.count} · 条件完整 ${group.conditionCompleteCount}/${group.count}</small><strong>${group.min.toPrecision(4)} – ${group.max.toPrecision(4)} <em>median ${group.median.toPrecision(4)}</em></strong>${group.alerts.length ? `<p>${group.alerts.map(escapeHtml).join('；')}</p>` : ''}</article>`).join('') : '<p>录入两条以上同指标、同单位的记录后显示可比性摘要。</p>';
}

function renderRecords(items) {
  const root = document.querySelector('#benchmark-list');
  root.innerHTML = items.length ? items.map(item => `<article class="record"><div class="record-top"><div><span class="badge ${item.verification_status}">${item.verification_status}</span><h3>${escapeHtml(item.material)} · ${escapeHtml(item.device_type)}</h3><p>${escapeHtml(item.metric_name)} · <span class="score">${item.metric_value} ${escapeHtml(item.metric_unit)}</span> · ${escapeHtml(item.test_condition || '未记录测试条件')}</p></div><span class="source">${escapeHtml(item.source_doi || '无 DOI')}</span></div>${item.source_title ? `<p>已验证来源：${escapeHtml(item.source_title)}</p>` : ''}${item.verification_status === 'draft' && item.source_doi ? `<button class="verify" data-id="${item.id}">通过 Crossref 验证 DOI</button>` : ''}</article>`).join('') : '<p class="empty">暂无基准条目。请从已阅读论文中录入真实数据。</p>';
  root.querySelectorAll('.verify').forEach(button => button.onclick = async () => {
    const verifier = window.prompt('请输入验证人姓名或缩写');
    if (!verifier) return;
    const response = await fetch(`/api/benchmarks/${button.dataset.id}/verify`, { method: 'POST', headers: { 'Content-Type': 'application/json' }, body: JSON.stringify({ verifier }) });
    const result = await response.json();
    if (!response.ok) alert(result.error || '验证失败');
    await load();
  });
}

async function load() {
  const [recordsResponse, summaryResponse] = await Promise.all([fetch('/api/benchmarks'), fetch('/api/benchmarks/summary')]);
  const [records, summary] = await Promise.all([recordsResponse.json(), summaryResponse.json()]);
  renderSummary(summary);
  renderRecords(records.items || []);
}

document.querySelector('#benchmark-form').addEventListener('submit', async event => {
  event.preventDefault();
  const body = { material: document.querySelector('#material').value, deviceType: document.querySelector('#device-type').value, metricName: document.querySelector('#metric-name').value, metricValue: document.querySelector('#metric-value').value, metricUnit: document.querySelector('#metric-unit').value, testCondition: document.querySelector('#condition').value, sourceDoi: document.querySelector('#doi').value, evidenceNote: document.querySelector('#note').value };
  const response = await fetch('/api/benchmarks', { method: 'POST', headers: { 'Content-Type': 'application/json' }, body: JSON.stringify(body) });
  const result = await response.json();
  if (!response.ok) alert(result.error || '创建失败');
  else event.currentTarget.reset();
  await load();
});
document.querySelector('#refresh').onclick = load;
load();


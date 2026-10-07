const state = { sessionId: null };
const $ = selector => document.querySelector(selector);
const escapeHtml = value => String(value ?? '').replace(/[&<>'"]/g, char => ({'&':'&amp;','<':'&lt;','>':'&gt;',"'":'&#039;','"':'&quot;'}[char]));

function addMessage(role, content) {
  const node = document.createElement('article');
  if (role === 'user') { node.className = 'message user'; node.textContent = content; }
  else { node.className = 'message assistant'; node.innerHTML = `<div class="agent-avatar">FR</div><div><span class="message-label">SYNTHESIZER · SOURCE-BOUND</span><div class="message-body">${escapeHtml(content)}</div></div>`; }
  $('#messages').append(node); $('#messages').scrollTop = $('#messages').scrollHeight;
}

function renderTrace(trace) { $('#agent-trace').innerHTML = trace.map(item => `<div class="trace-item ${escapeHtml(item.status)}"><b>${escapeHtml(item.agent)} · ${escapeHtml(item.status)}</b><small>${escapeHtml(item.detail)}</small></div>`).join(''); }
function renderSources(sources) { $('#source-count').textContent = String(sources.length); $('#source-list').innerHTML = sources.length ? sources.map(item => { const quality = item.quality || {}; const score = quality.metadataScore ?? 'N/A'; const warning = quality.flags?.length ? ` · ${quality.flags.length} 项待核验` : ''; return `<a class="source-card" href="${escapeHtml(item.url)}" target="_blank" rel="noreferrer"><b>${escapeHtml(item.title)}</b><span>${escapeHtml(item.journal || item.source)} · ${escapeHtml(item.year || 'n.d.')} · cited ${escapeHtml(item.citedBy)}</span><small>${escapeHtml(item.doi || item.authors || 'No DOI metadata')}</small><small>元数据 ${escapeHtml(score)}/100${escapeHtml(warning)}</small></a>`; }).join('') : '<p>本次没有返回可用元数据。可换英文关键词、检查网络或配置 OpenAlex。</p>'; }
function renderCritic(items) { $('#critic-list').innerHTML = items.map(item => `<li>${escapeHtml(item)}</li>`).join(''); }

async function loadHealth() { const data = await (await fetch('/api/health')).json(); $('#provider-status').textContent = `Crossref 已连接 · OpenAlex ${data.providers.openalex ? '已配置' : '可选'}`; }
async function loadSessions() { const data = await (await fetch('/api/sessions')).json(); $('#session-list').innerHTML = data.items.map(item => `<button data-id="${item.id}" class="${item.id === state.sessionId ? 'active' : ''}"><b>${escapeHtml(item.title)}</b><small>${escapeHtml(item.updated_at.slice(0,16).replace('T',' '))}</small></button>`).join('') || '<small>暂无会话</small>'; [...$('#session-list').querySelectorAll('button')].forEach(button => button.onclick = () => openSession(Number(button.dataset.id))); }
async function openSession(id) { const data = await (await fetch(`/api/sessions/${id}`)).json(); state.sessionId = id; $('#session-title').textContent = data.session.title; $('#messages').innerHTML = ''; data.messages.forEach(message => addMessage(message.role, message.content)); renderTrace(data.lastTrace); await loadSessions(); }
async function newSession() { const data = await (await fetch('/api/sessions',{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify({title:'新研究任务'})})).json(); await openSession(data.item.id); }

$('#new-session').onclick = newSession;
$('#research-form').addEventListener('submit', async event => { event.preventDefault(); const query = $('#research-query').value.trim(); if (!query) return; const button = event.currentTarget.querySelector('button'); button.disabled = true; button.textContent = '检索中…'; addMessage('user', query); $('#research-query').value = ''; $('#run-state').textContent = 'RUNNING'; try { const response = await fetch('/api/research',{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify({query,sessionId:state.sessionId,useOpenAlex:$('#openalex-toggle').checked,useModel:$('#model-toggle').checked})}); const data = await response.json(); if (!response.ok) throw new Error(data.error || '研究任务失败'); state.sessionId = data.sessionId; $('#session-title').textContent = query.slice(0,42); addMessage('assistant', data.answer); renderTrace(data.trace); renderSources(data.sources); renderCritic(data.critic); await loadSessions(); } catch(error) { addMessage('assistant', `任务未完成：${error.message}`); } finally { $('#run-state').textContent = 'READY'; button.disabled = false; button.innerHTML = '开始研究 <b>→</b>'; } });
document.querySelectorAll('[data-prompt]').forEach(button => button.onclick = () => { $('#research-query').value = button.dataset.prompt; $('#research-query').focus(); });
loadHealth(); loadSessions();


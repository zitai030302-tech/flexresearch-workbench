const $ = selector => document.querySelector(selector);
const escapeHtml = value => String(value ?? '').replace(/[&<>'"]/g, char => ({'&':'&amp;','<':'&lt;','>':'&gt;',"'":'&#039;','"':'&quot;'}[char]));
const state = { papers: [], documents: [], cards: [] };

async function api(url, options) {
  const response = await fetch(url, options);
  const body = await response.json();
  if (!response.ok) throw new Error(body.error || '请求失败');
  return body;
}

function paperMarkup(item) {
  const flags = item.quality?.flags?.length ? ` · ${item.quality.flags.length} 项待核验` : '';
  return `<article class="paper"><div class="paper-top"><div><span class="badge ${escapeHtml(item.review_status)}">${escapeHtml(item.review_status)}</span><h3>${escapeHtml(item.title)}</h3><p class="meta">${escapeHtml(item.authors || '作者待补充')} · ${escapeHtml(item.journal || '期刊待补充')} (${escapeHtml(item.publication_year || 'n.d.')})</p><p class="doi">${escapeHtml(item.doi || '无 DOI — 手工记录')}</p>${item.tags ? `<p class="meta">标签：${escapeHtml(item.tags)}</p>` : ''}${item.notes ? `<p class="notes">${escapeHtml(item.notes)}</p>` : ''}</div><aside><span class="quality">metadata ${escapeHtml(item.quality?.metadataScore ?? 'N/A')}/100${escapeHtml(flags)}</span></aside></div><div class="paper-actions"><a href="/api/papers/${item.id}/citation.bib">BibTeX ↓</a><a href="/api/papers/${item.id}/citation.ris">RIS ↓</a><button class="review" data-paper-id="${item.id}">人工审阅</button></div></article>`;
}

function cardMarkup(item) {
  const source = item.paper_title ? `${item.paper_title}${item.paper_doi ? ` · ${item.paper_doi}` : ''}` : `本地文档：${item.document_title || '未知'}`;
  return `<article class="evidence-card ${escapeHtml(item.review_status)}"><span class="badge ${escapeHtml(item.review_status)}">${escapeHtml(item.review_status)} · ${escapeHtml(item.evidence_type)}</span><h3>${escapeHtml(item.title)}</h3><p>${escapeHtml(item.claim)}</p>${item.locator ? `<p class="source">定位：${escapeHtml(item.locator)}</p>` : ''}${item.excerpt ? `<p class="excerpt">${escapeHtml(item.excerpt)}</p>` : ''}<p class="source">来源：${escapeHtml(source)}${item.reviewer ? ` · 审阅：${escapeHtml(item.reviewer)}` : ''}</p>${item.review_status === 'draft' ? `<div class="card-actions"><button data-card-id="${item.id}">审核证据卡</button></div>` : ''}</article>`;
}

function render() {
  const status = $('#paper-status').value;
  const search = $('#paper-search').value.trim().toLowerCase();
  const visible = state.papers.filter(item => (!status || item.review_status === status) && (!search || [item.title,item.authors,item.journal,item.tags].join(' ').toLowerCase().includes(search)));
  $('#paper-list').innerHTML = visible.length ? visible.map(paperMarkup).join('') : '<p class="empty">没有符合条件的论文。用 DOI 导入第一篇，或调整筛选。</p>';
  $('#card-list').innerHTML = state.cards.length ? state.cards.map(cardMarkup).join('') : '<p class="empty">还没有证据卡。请从已读论文中提取可定位的结果、方法或局限。</p>';
  $('#paper-total').textContent = state.papers.length;
  $('#reviewed-total').textContent = state.papers.filter(item => item.review_status === 'reviewed').length;
  $('#card-total').textContent = state.cards.length;
  $('#card-source').innerHTML = '<option value="">选择论文或本地文档…</option><optgroup label="论文库">' + state.papers.filter(item => item.review_status !== 'excluded').map(item => `<option value="paper:${item.id}">${escapeHtml(item.title.slice(0, 64))}</option>`).join('') + '</optgroup><optgroup label="本地文档">' + state.documents.map(item => `<option value="document:${item.id}">${escapeHtml(item.title.slice(0, 64))}${item.pages > 1 ? ` · ${item.pages} pages` : ''}</option>`).join('') + '</optgroup>';
  document.querySelectorAll('[data-paper-id]').forEach(button => button.onclick = () => openPaperReview(Number(button.dataset.paperId)));
  document.querySelectorAll('[data-card-id]').forEach(button => button.onclick = () => openCardReview(Number(button.dataset.cardId)));
}

async function refresh() {
  const [papers, documents, cards] = await Promise.all([api('/api/papers'), api('/api/documents'), api('/api/evidence-cards')]);
  state.papers = papers.items; state.documents = documents.items; state.cards = cards.items; render();
}

function reviewDialog(title, submit, allowedStatuses = null) {
  const dialog = $('#review-dialog-template').content.firstElementChild.cloneNode(true);
  dialog.querySelector('h3').textContent = title;
  document.body.append(dialog); if (allowedStatuses) dialog.querySelectorAll('menu button').forEach(button => { if (button.value !== 'cancel' && !allowedStatuses.includes(button.value)) button.hidden = true; }); dialog.showModal();
  dialog.querySelectorAll('menu button').forEach(button => button.onclick = async event => {
    const status = event.currentTarget.value; if (status === 'cancel') return;
    event.preventDefault();
    const reviewer = dialog.querySelector('[name=reviewer]').value.trim();
    if (!reviewer) return dialog.querySelector('[name=reviewer]').focus();
    try { await submit(status, reviewer, dialog.querySelector('[name=note]').value.trim()); dialog.close(); dialog.remove(); await refresh(); } catch (error) { alert(error.message); }
  });
  dialog.addEventListener('close', () => dialog.remove(), { once: true });
}

function openPaperReview(id) { reviewDialog('记录论文人工审阅', (status, reviewer, note) => api(`/api/papers/${id}/review`, { method:'POST', headers:{'Content-Type':'application/json'}, body:JSON.stringify({status, reviewer, note}) })); }
function openCardReview(id) { reviewDialog('审核证据卡', (status, reviewer, note) => api(`/api/evidence-cards/${id}/review`, { method:'POST', headers:{'Content-Type':'application/json'}, body:JSON.stringify({status: status === 'excluded' ? 'rejected' : 'reviewed', reviewer, note}) }), ['reviewed', 'excluded']); }

$('#paper-form').addEventListener('submit', async event => { event.preventDefault(); const doi = $('#paper-doi').value.trim(), title = $('#paper-title').value.trim(); if (!doi && !title) return alert('请输入 DOI 或论文标题。'); const button = event.currentTarget.querySelector('button'); button.disabled = true; button.textContent = '导入中…'; try { await api('/api/papers', { method:'POST', headers:{'Content-Type':'application/json'}, body:JSON.stringify({doi, title, tags:$('#paper-tags').value, notes:$('#paper-notes').value}) }); event.currentTarget.reset(); await refresh(); } catch (error) { alert(error.message); } finally { button.disabled = false; button.textContent = '导入并建立审阅记录 →'; } });
$('#card-form').addEventListener('submit', async event => { event.preventDefault(); const source = $('#card-source').value; if (!source) return alert('请先选择关联论文或本地文档。'); const [kind, id] = source.split(':'); const sourcePayload = kind === 'paper' ? {paperId:id} : {documentId:id}; try { await api('/api/evidence-cards', { method:'POST', headers:{'Content-Type':'application/json'}, body:JSON.stringify({...sourcePayload, title:$('#card-title').value, claim:$('#card-claim').value, evidenceType:$('#card-type').value, locator:$('#card-locator').value, excerpt:$('#card-excerpt').value}) }); event.currentTarget.reset(); await refresh(); } catch (error) { alert(error.message); } });
$('#paper-search').addEventListener('input', render); $('#paper-status').addEventListener('change', render); refresh().catch(error => { $('#paper-list').innerHTML = `<p class="empty">加载失败：${escapeHtml(error.message)}</p>`; });


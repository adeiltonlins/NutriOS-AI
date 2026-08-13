(() => {
  const mrrCard = document.getElementById('mrr')?.closest('.stat');
  if (mrrCard) {
    mrrCard.title = 'Soma das mensalidades dos nutricionistas com assinatura Em dia';
    const label = mrrCard.querySelector('.muted');
    const note = mrrCard.querySelector('small');
    if (label) label.textContent = 'Receita recorrente SaaS';
    if (note) note.textContent = 'Mensalidades de nutricionistas em dia';
  }
  const chatbotRevenueCard = document.getElementById('revenue')?.closest('.stat');
  if (chatbotRevenueCard) {
    chatbotRevenueCard.title = 'Pagamentos feitos pelos pacientes nos canais inteligentes';
    const label = chatbotRevenueCard.querySelector('.muted');
    const note = chatbotRevenueCard.querySelector('small');
    if (label) label.textContent = 'Receita dos canais inteligentes';
    if (note) note.textContent = 'Pagamentos feitos por pacientes';
  }
  const billingTitle = document.querySelector('#billingDialog h2');
  if (billingTitle) {
    billingTitle.textContent = 'Assinatura do nutricionista';
    const help = document.createElement('p');
    help.className = 'billing-help';
    help.innerHTML = 'Ao marcar <b>Em dia</b>, o valor mensal passa a compor a <b>Receita recorrente SaaS</b>. Pagamentos dos pacientes são contabilizados separadamente.';
    billingTitle.insertAdjacentElement('afterend', help);
  }
  const adminNav = document.querySelector('.side');
  if (adminNav && !adminNav.querySelector('[href="/admin/clinica"]')) {
    const link = document.createElement('a');
    link.className = 'nav'; link.href = '/admin/clinica'; link.textContent = 'Monitor clínico global';
    adminNav.appendChild(link);
  }
  document.querySelectorAll('a[href="/painel"]').forEach(link => {
    link.href = '/admin/leads';
    link.textContent = 'Central de conversas';
  });
  const style = document.createElement('style');
  style.textContent = `
    .top>div:last-child{display:flex;align-items:center;gap:10px;flex-wrap:wrap}
    .top>div:last-child>a,.top>div:last-child>button{min-height:44px;display:inline-flex;align-items:center;justify-content:center;padding:0 17px;border-radius:13px;text-decoration:none;font-weight:800}
    .finance-panel{margin-bottom:18px}.finance-copy{display:grid;gap:3px}.finance-table{min-width:850px}
    .finance-actions{display:flex;gap:8px;align-items:center}.finance-actions a,.finance-actions button{white-space:nowrap}
    .finance-empty{padding:26px;color:var(--muted)}.finance-note{padding:13px 22px;border-top:1px solid #253857;color:var(--muted);font-size:12px}
    @media(max-width:850px){.top>div:last-child{width:100%}.top>div:last-child>a,.top>div:last-child>button{flex:1}.finance-table{min-width:760px}}
  `;
  document.head.appendChild(style);

  async function copyMasterChatLink(button) {
    const original = button.textContent;
    button.disabled = true;
    button.textContent = 'Gerando link…';
    try {
      const response = await fetch('/admin/api/chatbot-mestre/link-publico', {
        method: 'POST',
        headers: {'Content-Type': 'application/json'},
        body: '{}'
      });
      const data = await response.json().catch(() => ({}));
      if (!response.ok || !data.public_url) throw new Error(data.detail || 'Não foi possível gerar o link');
      await navigator.clipboard.writeText(data.public_url);
      button.textContent = 'Link copiado ✓';
      button.title = data.public_url;
    } catch (error) {
      button.textContent = 'Falhou — tentar novamente';
      window.NutriUX?.toast(error.message, 'error');
    } finally {
      button.disabled = false;
      setTimeout(() => { button.textContent = original; }, 3500);
    }
  }

  const topActions = document.querySelector('.top > div:last-child');
  if (topActions && !document.getElementById('copyMasterChatTop')) {
    const topShare = document.createElement('button');
    topShare.id = 'copyMasterChatTop';
    topShare.className = 'primary';
    topShare.type = 'button';
    topShare.textContent = 'Copiar link público';
    topShare.title = 'Copia o link público para você enviar a qualquer pessoa';
    topShare.addEventListener('click', () => copyMasterChatLink(topShare));
    topActions.prepend(topShare);
  }

  const nutritionists = document.getElementById('nutritionists');
  if (!nutritionists) return;
  const section = document.createElement('section');
  section.className = 'panel finance-panel';
  section.innerHTML = `
    <div class="panel-head"><div class="finance-copy"><h2 style="margin:0">Pagamentos da experiência pública</h2><span class="muted">Vendas dos pacientes no seu link mestre — separado das mensalidades dos nutricionistas</span></div><div class="finance-actions"><button class="primary" id="copyMasterChatFinance">Copiar link público</button><button class="ghost" id="refreshMasterPayments">Atualizar pagamentos</button></div></div>
    <div class="table"><table class="finance-table"><thead><tr><th>Cliente</th><th>WhatsApp</th><th>Status Mercado Pago</th><th>Valor</th><th>Data</th><th>Liberação</th><th>Ação</th></tr></thead><tbody id="masterPaymentRows"><tr><td colspan="7" class="finance-empty">Carregando pagamentos…</td></tr></tbody></table></div>
    <div class="finance-note">“Receita mensal” é o que os nutricionistas pagam pelo SaaS. “Receita gerada” são as vendas realizadas pela experiência pública.</div>`;
  nutritionists.parentNode.insertBefore(section, nutritionists);

  const rows = document.getElementById('masterPaymentRows');
  const safe = value => String(value ?? '').replace(/[&<>"']/g, char => ({'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;',"'":'&#39;'}[char]));
  const brl = value => Number(value || 0).toLocaleString('pt-BR', {style:'currency', currency:'BRL'});

  async function loadMasterPayments() {
    rows.innerHTML = '<tr><td colspan="7" class="finance-empty">Atualizando…</td></tr>';
    try {
      const response = await fetch('/admin/api/pagamentos-mestre');
      if (response.status === 401 || response.status === 403) return location.assign('/login');
      const items = await response.json();
      if (!response.ok) throw new Error(items.detail || 'Erro ao carregar pagamentos');
      rows.innerHTML = items.map(item => {
        const approved = item.status === 'approved';
        const checking = item.status === 'verification';
        const status = approved ? 'Confirmado' : checking ? 'Aguardando conferência' : 'Pendente';
        const phone = item.phone ? String(item.phone).replace(/\D/g, '') : '';
        const date = item.paid_at || item.updated_at;
        return `<tr><td><b>${safe(item.name)}</b><br><small class="muted">${safe(item.session_id)}</small></td><td>${phone ? `<a href="https://wa.me/${safe(phone)}" target="_blank" rel="noopener">${safe(phone)}</a>` : '—'}</td><td><span class="badge ${approved ? '' : 'trial'}">${status}</span></td><td>${brl(item.amount)}</td><td>${date ? new Date(date).toLocaleString('pt-BR') : '—'}</td><td>${approved ? '<span class="badge">Contato liberado</span>' : '<span class="badge trial">Bloqueado</span>'}</td><td><div class="finance-actions">${approved ? '<b class="money">OK ✓</b>' : `<button class="primary" data-verify="${safe(item.session_id)}">Verificar agora</button>`}</div></td></tr>`;
      }).join('') || '<tr><td colspan="7" class="finance-empty">Nenhum pagamento iniciado na experiência pública.</td></tr>';
    } catch (error) {
      rows.innerHTML = `<tr><td colspan="7" class="finance-empty">${safe(error.message)}</td></tr>`;
    }
  }

  rows.addEventListener('click', async event => {
    const button = event.target.closest('[data-verify]');
    if (!button) return;
    button.disabled = true; button.textContent = 'Consultando Mercado Pago…';
    try {
      const response = await fetch(`/admin/api/pagamentos-mestre/${encodeURIComponent(button.dataset.verify)}/verificar`, {method:'POST', headers:{'Content-Type':'application/json'}, body:'{}'});
      const data = await response.json().catch(() => ({}));
      if (!response.ok) throw new Error(data.detail || 'Falha na verificação');
      window.NutriUX?.toast(data.status === 'approved' ? 'Pagamento confirmado e atendimento liberado.' : `Pagamento ainda está ${data.status || 'pendente'}.`, data.status === 'approved' ? 'success' : 'info', 5000);
      await loadMasterPayments();
      if (typeof load === 'function') load();
    } catch (error) { window.NutriUX?.toast(error.message, 'error'); button.disabled = false; button.textContent = 'Tentar novamente'; }
  });
  document.getElementById('refreshMasterPayments').addEventListener('click', loadMasterPayments);
  document.getElementById('copyMasterChatFinance').addEventListener('click', event => copyMasterChatLink(event.currentTarget));
  loadMasterPayments();
})();

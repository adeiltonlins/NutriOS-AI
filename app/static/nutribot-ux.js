(() => {
  /* Early professional-shell bootstrap: prevent the legacy page from flashing
     before the ZIP shell is mounted. This runs from <head> on professional pages. */
  const currentPath = location.pathname.replace(/\/$/, '') || '/';
  const shouldBootShell = currentPath.startsWith('/app/') && !currentPath.startsWith('/app/api/');
  if (shouldBootShell) {
    document.documentElement.classList.add('nutrios-shell-booting');
    const bootStyle = document.createElement('style');
    bootStyle.id = 'nutrios-shell-boot-style';
    bootStyle.textContent = 'html.nutrios-shell-booting body{visibility:hidden!important}html.nutrios-shell-booting body.nutrios-shell-ready{visibility:visible!important}';
    document.head.appendChild(bootStyle);
    if (!document.querySelector('link[data-nutrios-style="app-shell"]')) {
      const css = document.createElement('link');
      css.rel = 'stylesheet'; css.href = '/static/nutrios-app-shell.css?v=11'; css.dataset.nutriosStyle = 'app-shell';
      document.head.appendChild(css);
    }
    if (!document.querySelector('script[data-nutrios-script="app-shell"]')) {
      const js = document.createElement('script');
      js.src = '/static/nutrios-app-shell.js?v=11'; js.defer = true; js.dataset.nutriosScript = 'app-shell';
      document.head.appendChild(js);
    }
    const reveal = () => document.documentElement.classList.remove('nutrios-shell-booting');
    document.addEventListener('DOMContentLoaded', () => requestAnimationFrame(() => requestAnimationFrame(reveal)), { once:true });
    setTimeout(reveal, 1800);
  }

  const reduced = matchMedia('(prefers-reduced-motion: reduce)').matches;
  const host = document.createElement('div');
  host.className = 'nutri-toast-host';
  document.addEventListener('DOMContentLoaded', () => document.body.appendChild(host), { once: true });
  function toast(message, type = 'info', timeout = 3600) {
    const item = document.createElement('div');
    item.className = `nutri-toast nutri-toast-${type}`;
    item.setAttribute('role', type === 'error' ? 'alert' : 'status');
    item.textContent = message;
    host.appendChild(item);
    requestAnimationFrame(() => item.classList.add('show'));
    setTimeout(() => { item.classList.remove('show'); setTimeout(() => item.remove(), reduced ? 0 : 220); }, timeout);
  }
  function setBusy(button, busy, label = 'Processando...') {
    if (!button) return;
    if (busy) {
      button.dataset.originalLabel ||= button.textContent;
      button.disabled = true;
      button.setAttribute('aria-busy', 'true');
      button.textContent = label;
    } else {
      button.disabled = false;
      button.removeAttribute('aria-busy');
      if (button.dataset.originalLabel) button.textContent = button.dataset.originalLabel;
    }
  }
  function finishLoading() {
    document.documentElement.classList.remove('nutri-loading');
    document.querySelectorAll('[data-nutri-skeleton]').forEach(node => node.removeAttribute('data-nutri-skeleton'));
  }
  const explanations = [
    [/novo nutricionista/i, 'Cria uma nova conta profissional e define o limite de pacientes do plano.'],
    [/testar experiência|laboratório/i, 'Abre o ambiente seguro para validar IA, WhatsApp e pagamento sem gerar leads.'],
    [/gerar código/i, 'Gera um código temporário exibido uma única vez.'],
    [/renovar/i, 'Estende a validade do acesso sem alterar os dados cadastrados.'],
    [/arquivar/i, 'Remove da lista principal e preserva histórico e métricas.'],
    [/bloquear/i, 'Bloqueia imediatamente o acesso e invalida as sessões abertas.'],
    [/desbloquear/i, 'Restaura o acesso desta conta.'],
    [/mensalidade/i, 'Atualiza plano, cobrança e situação financeira da conta.'],
    [/pacientes/i, 'Gerencie acessos privados, validade, prontuários e documentos.'],
    [/leads/i, 'Veja interessados, conversas, pagamentos e próximos contatos.'],
    [/métricas|visão geral/i, 'Acompanhe uso, conversão e desempenho do negócio.'],
    [/agenda|serviços/i, 'Configure serviços, horários, consultas e anamneses.'],
    [/configurações|identidade da ia/i, 'Personalize foto, marca, mensagens, WhatsApp e pagamento.'],
    [/atualizar/i, 'Busca os dados mais recentes do sistema.'],
    [/sair/i, 'Encerra esta sessão com segurança.']
  ];
  function enrichActions() {
    document.querySelectorAll('button,a').forEach(el => {
      if (el.dataset.nutriTip) return;
      const label = (el.textContent || '').replace(/\s+/g, ' ').trim();
      const found = explanations.find(([pattern]) => pattern.test(label));
      if (found) {
        el.dataset.nutriTip = found[1];
        if (!el.getAttribute('aria-label')) el.setAttribute('aria-label', `${label}. ${found[1]}`);
      }
    });
  }
  const tip = document.createElement('div'); tip.className = 'nutri-tip'; tip.setAttribute('role', 'tooltip');
  function showTip(el) { const r=el.getBoundingClientRect(); tip.textContent=el.dataset.nutriTip; tip.style.left=`${Math.min(innerWidth-296,Math.max(8,r.left))}px`; tip.style.top=`${Math.min(innerHeight-60,r.bottom+8)}px`; tip.classList.add('show'); }
  document.addEventListener('pointerover', e => { const el=e.target.closest('[data-nutri-tip]'); if(el) showTip(el); });
  document.addEventListener('pointerout', e => { if(e.target.closest('[data-nutri-tip]')) tip.classList.remove('show'); });
  document.addEventListener('focusin', e => { const el=e.target.closest('[data-nutri-tip]'); if(el) showTip(el); });
  document.addEventListener('focusout', () => tip.classList.remove('show'));
  document.addEventListener('pointerdown', e => { const el=e.target.closest('button,.btn,.pill'); if(!el) return; const r=el.getBoundingClientRect(),s=document.createElement('i'); s.className='nutri-ripple'; const size=Math.max(r.width,r.height); Object.assign(s.style,{width:`${size}px`,height:`${size}px`,left:`${e.clientX-r.left-size/2}px`,top:`${e.clientY-r.top-size/2}px`}); el.appendChild(s); setTimeout(()=>s.remove(),520); });
  document.documentElement.classList.add('nutri-loading');
  document.addEventListener('DOMContentLoaded', () => {
    document.body.appendChild(tip); enrichActions(); new MutationObserver(enrichActions).observe(document.body,{childList:true,subtree:true});
  }, { once:true });
  document.addEventListener('submit', event => setBusy(event.submitter || event.target.querySelector('[type="submit"]'), true, event.submitter?.dataset.loadingLabel || 'Processando...'), true);
  const nativeFetch = window.fetch.bind(window);
  window.fetch = async (...args) => {
    try {
      const response = await nativeFetch(...args);
      if (!response.ok && response.status >= 500) toast('O serviço encontrou uma instabilidade. Tente novamente.', 'error');
      return response;
    } catch (error) {
      toast('Sem conexão com o serviço. Verifique sua internet.', 'error');
      throw error;
    } finally {
      finishLoading();
      document.querySelectorAll('button[aria-busy="true"]').forEach(button => setBusy(button, false));
    }
  };
  window.NutriUX = { toast, setBusy, finishLoading, enrichActions };
  setTimeout(finishLoading, 8000);
})();

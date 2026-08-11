(() => {
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
  document.documentElement.classList.add('nutri-loading');
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
  window.NutriUX = { toast, setBusy, finishLoading };
  setTimeout(finishLoading, 8000);
})();

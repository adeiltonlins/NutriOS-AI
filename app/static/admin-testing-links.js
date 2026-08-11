(() => {
  const actions = document.querySelector('#config .actions');
  if (!actions) return;

  let copyButton = document.getElementById('generatePublicLink');
  if (!copyButton) {
    copyButton = document.createElement('button');
    copyButton.id = 'generatePublicLink';
    copyButton.type = 'button';
    copyButton.className = 'button primary';
    copyButton.textContent = 'Gerar e copiar link';
    copyButton.title = 'Cria o link público seguro e copia para você enviar às pessoas';
    actions.insertBefore(copyButton, document.getElementById('publicLink'));
  }

  const publicLink = document.getElementById('publicLink');
  publicLink.textContent = 'Abrir chat público para testar';
  publicLink.title = 'Abre exatamente a página que a pessoa receberá';

  copyButton.addEventListener('click', async () => {
    const profileId = document.getElementById('client')?.value;
    if (!profileId) {
      document.getElementById('toast').textContent = 'Selecione um perfil primeiro.';
      return;
    }
    copyButton.disabled = true;
    copyButton.textContent = 'Gerando…';
    try {
      const target = profileId === 'master'
        ? '/admin/api/chatbot-mestre/link-publico'
        : `/admin/api/clientes/${encodeURIComponent(profileId)}/link-publico`;
      const response = await fetch(target, {
        method: 'POST',
        headers: {'Content-Type': 'application/json'},
        body: '{}'
      });
      const data = await response.json().catch(() => ({}));
      if (!response.ok) throw new Error(data.detail || 'Não foi possível gerar o link');
      const publicLink = document.getElementById('publicLink');
      publicLink.href = data.public_url;
      await navigator.clipboard.writeText(data.public_url);
      document.getElementById('toast').textContent = 'Link público copiado. Agora é só enviar.';
      copyButton.textContent = 'Link copiado ✓';
    } catch (error) {
      document.getElementById('toast').textContent = error.message;
      copyButton.textContent = 'Tentar novamente';
    } finally {
      copyButton.disabled = false;
      setTimeout(() => {
        copyButton.textContent = 'Gerar e copiar link';
      }, 3000);
    }
  });
})();

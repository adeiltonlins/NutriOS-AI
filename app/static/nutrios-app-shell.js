(()=>{
  const path=location.pathname.replace(/\/$/,'')||'/';
  const groups=[
    ['ATENDIMENTO CLÍNICO',[
      ['Visão Geral','⌂','/app'],
      ['Pacientes & Prontuários','♙','/app/pacientes'],
      ['Agenda & Consultas','□','/app/gestao'],
      ['Atendimentos','◇','/app/clinica'],
      ['Prescrição & Cardápios','◫','/app/planos'],
      ['Evolução','↗','/app/evolucao'],
      ['Antropometria & Análise','♧','/app/analise-corporal'],
      ['Financeiro clínico','R$','/app/financeiro']
    ]],
    ['IA & AUTOMAÇÃO',[
      ['Conversas','○','/app/conversas'],
      ['Indicações','◎','/app/leads'],
      ['Captação e vendas','▥','/app/metricas'],
      ['Prescrição de Treinos','↔','/app/treinos']
    ]],
    ['CONFIGURAÇÕES',[
      ['Configurações','⚙','/app/configuracoes']
    ]]
  ];
  const current=(href)=>href==='/app'?path==='/app':path===href||path.startsWith(href+'/');
  const escapeHtml=(v)=>String(v??'').replace(/[&<>"']/g,c=>({'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;',"'":'&#39;'}[c]));
  const link=([label,icon,href])=>`<a class="nutrios-shell-link" href="${href}" ${current(href)?'aria-current="page"':''}><span class="nutrios-shell-icon" aria-hidden="true">${icon}</span><span class="nutrios-shell-label">${escapeHtml(label)}</span></a>`;

  function mount(){
    if(document.body.classList.contains('nutrios-shell-ready')||path==='/app')return;
    const aside=document.createElement('aside');
    aside.className='nutrios-shell-sidebar';
    aside.setAttribute('aria-label','Navegação principal');
    const navHtml=groups.map(([name,items])=>`<div class="nutrios-shell-group">${name}</div>${items.map(link).join('')}`).join('');
    aside.innerHTML=`
      <a class="nutrios-shell-brand" href="/app" aria-label="NutriOS">
        <span class="nutrios-shell-mark" aria-hidden="true">🌿</span>
        <span class="nutrios-shell-brand-copy"><strong>Nutri<span>OS</span></strong><small>Clínica & Gestão</small></span>
      </a>
      <nav class="nutrios-shell-nav">${navHtml}</nav>
      <div class="nutrios-shell-footer">
        <a class="nutrios-shell-copilot" href="/app/conversas"><span>✦</span><span>Copiloto NutriOS</span></a>
        <a class="nutrios-shell-link nutrios-shell-help" href="/app/onboarding"><span class="nutrios-shell-icon">?</span><span class="nutrios-shell-label">Central de ajuda</span></a>
      </div>`;
    document.body.prepend(aside);
    document.body.classList.add('nutrios-shell-ready');
    document.documentElement.dataset.nutriosShell='zip-visual-v2';
  }

  function showError(message,retry){
    let box=document.getElementById('nutriosShellError');
    if(!box){
      box=document.createElement('div');box.id='nutriosShellError';box.className='nutrios-shell-error';
      box.innerHTML='<span id="nutriosShellErrorText"></span><button type="button" id="nutriosShellRetry">Tentar novamente</button>';
      document.body.appendChild(box);
    }
    const text=document.getElementById('nutriosShellErrorText');if(text)text.textContent=message||'Não foi possível carregar os dados agora.';
    const btn=document.getElementById('nutriosShellRetry');if(btn)btn.onclick=()=>{box.classList.remove('show');if(typeof retry==='function')retry();};
    box.classList.add('show');
  }
  function handleResponse(response,retry){
    if(response?.status===401){location.assign('/login');return false;}
    if(response?.status===403){showError('Seu acesso não permite abrir este recurso.');return false;}
    const suffix=response?.status?` (erro ${response.status})`:'';
    showError(`Não foi possível carregar os dados${suffix}. Sua sessão continua ativa.`,retry);return false;
  }
  window.NutriOSUI={mount,showError,handleResponse,escapeHtml};
  if(document.readyState==='loading')document.addEventListener('DOMContentLoaded',mount,{once:true});else mount();
})();

(()=>{
  if(!document.querySelector('link[data-nutrios-v2-suite]')){
    const css=document.createElement('link');css.rel='stylesheet';css.href='/static/nutrios-v2-suite.css?v=1';css.dataset.nutriosV2Suite='1';document.head.appendChild(css);
  }
  const path=location.pathname.replace(/\/$/,'')||'/';
  const nav=[
    ['Início','⌂','/app'],['Pacientes','♙','/app/pacientes'],['Agenda','□','/app/gestao'],['Atendimentos','◇','/app/clinica'],['Planos alimentares','◫','/app/planos'],['Evolução','↗','/app/evolucao'],['Análise corporal','♧','/app/analise-corporal'],['Financeiro','R$','/app/financeiro'],
    ['Conversas','○','/app/conversas'],['Indicações','◎','/app/leads'],['Treinos','↔','/app/treinos'],['Captação e vendas','▥','/app/metricas'],['Configurações','⚙','/app/configuracoes']
  ];
  const commercial=new Set(['/app/conversas','/app/leads','/app/metricas']);
  const resources=new Set(['/app/treinos','/app/configuracoes']);
  const current=(href)=> href==='/app'?path==='/app':path===href||path.startsWith(href+'/');
  const link=([label,icon,href])=>`<a class="nutrios-shell-link" href="${href}" ${current(href)?'aria-current="page"':''}><span class="nutrios-shell-icon" aria-hidden="true">${icon}</span><span>${label}</span></a>`;

  function mount(){
    if(document.body.classList.contains('nutrios-shell-ready'))return;
    const original=[...document.body.children].filter(el=>el.tagName!=='SCRIPT'&&el.tagName!=='LINK');
    if(!original.length)return;
    const content=document.createElement('div');content.className='nutrios-shell-content';
    original.forEach(el=>content.appendChild(el));
    const shell=document.createElement('div');shell.className='nutrios-app-shell';
    const aside=document.createElement('aside');aside.className='nutrios-shell-sidebar';aside.setAttribute('aria-label','Navegação principal');
    const clinical=nav.filter(x=>!commercial.has(x[2])&&!resources.has(x[2]));
    const sales=nav.filter(x=>commercial.has(x[2]));
    const extras=nav.filter(x=>resources.has(x[2]));
    aside.innerHTML=`<a class="nutrios-shell-brand" href="/app"><span class="nutrios-shell-mark" aria-hidden="true"></span><span>NutriOS</span></a><div class="nutrios-shell-nav">${clinical.map(link).join('')}<div class="nutrios-shell-group">Comercial</div>${sales.map(link).join('')}<div class="nutrios-shell-group">Recursos</div>${extras.map(link).join('')}</div><div class="nutrios-shell-footer"><a class="nutrios-shell-link" href="/app/onboarding"><span class="nutrios-shell-icon">?</span><span>Ajuda</span></a></div>`;
    const workspace=document.createElement('section');workspace.className='nutrios-shell-workspace';
    const title=(document.querySelector('h1')?.textContent||document.title.split('—')[0]||'NutriOS').trim();
    workspace.innerHTML=`<header class="nutrios-shell-topbar"><div class="nutrios-shell-title"><strong>${escapeHtml(title)}</strong><span>NutriOS · ambiente profissional</span></div><a class="nutrios-shell-home" href="/app">⌂ Visão geral</a></header><div class="nutrios-shell-error" id="nutriosShellError" role="status" aria-live="polite"><span id="nutriosShellErrorText">Não foi possível carregar os dados.</span><button type="button" id="nutriosShellRetry">Tentar novamente</button></div>`;
    workspace.appendChild(content);shell.append(aside,workspace);document.body.prepend(shell);document.body.classList.add('nutrios-shell-ready');
  }
  function escapeHtml(v){return String(v??'').replace(/[&<>"']/g,c=>({'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;',"'":'&#39;'}[c]));}
  function showError(message,retry){
    const box=document.getElementById('nutriosShellError');if(!box)return;
    document.getElementById('nutriosShellErrorText').textContent=message||'Não foi possível carregar os dados agora.';
    const btn=document.getElementById('nutriosShellRetry');btn.onclick=()=>{box.classList.remove('show');if(typeof retry==='function')retry();};
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

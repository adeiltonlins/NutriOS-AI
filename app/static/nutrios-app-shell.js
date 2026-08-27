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
  const flat=groups.flatMap(([,items])=>items);
  const current=href=>href==='/app'?path==='/app':path===href||path.startsWith(href+'/');
  const escapeHtml=v=>String(v??'').replace(/[&<>"']/g,c=>({'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;',"'":'&#39;'}[c]));
  const link=([label,icon,href])=>`<a class="nutrios-shell-link" href="${href}" ${current(href)?'aria-current="page"':''}><span class="nutrios-shell-icon" aria-hidden="true">${icon}</span><span class="nutrios-shell-label">${escapeHtml(label)}</span></a>`;

  function buildSearchResults(query=''){
    const box=document.getElementById('nutriosShellSearchResults');
    if(!box)return;
    const q=query.trim().toLocaleLowerCase('pt-BR');
    const items=flat.filter(([label])=>!q||label.toLocaleLowerCase('pt-BR').includes(q)).slice(0,8);
    box.innerHTML=items.map(([label,,href])=>`<a href="${href}">${escapeHtml(label)}</a>`).join('')||'<a href="/app">Nenhum módulo encontrado</a>';
    box.classList.toggle('open',Boolean(query));
  }

  async function hydrateProfile(){
    try{
      const r=await fetch('/api/me',{credentials:'same-origin'});
      if(!r.ok)return;
      const me=await r.json(),name=String(me.name||'Nutricionista').trim()||'Nutricionista';
      const nameEl=document.getElementById('nutriosShellProfileName'),avatar=document.getElementById('nutriosShellAvatar');
      if(nameEl)nameEl.textContent=name;if(avatar)avatar.textContent=(name[0]||'N').toUpperCase();
    }catch(_){/* shell must never block page rendering */}
  }

  function mount(){
    if(!document.body||document.body.classList.contains('nutrios-shell-ready'))return;
    const aside=document.createElement('aside');
    aside.className='nutrios-shell-sidebar';aside.setAttribute('aria-label','Navegação principal');
    const navHtml=groups.map(([name,items])=>`<div class="nutrios-shell-group">${name}</div>${items.map(link).join('')}`).join('');
    aside.innerHTML=`<a class="nutrios-shell-brand" href="/app" aria-label="NutriOS"><span class="nutrios-shell-mark" aria-hidden="true">🌿</span><span class="nutrios-shell-brand-copy"><strong>Nutri<span>OS</span></strong><small>Clínica & Gestão</small></span></a><nav class="nutrios-shell-nav">${navHtml}</nav><div class="nutrios-shell-footer"><a class="nutrios-shell-copilot" href="/app/conversas"><span>✦</span><span>Copiloto NutriOS</span></a><a class="nutrios-shell-link nutrios-shell-help" href="/app/onboarding"><span class="nutrios-shell-icon">?</span><span class="nutrios-shell-label">Central de ajuda</span></a></div>`;

    const top=document.createElement('header');top.className='nutrios-shell-topbar';
    top.innerHTML=`<label class="nutrios-shell-search" aria-label="Buscar módulo"><span aria-hidden="true">⌕</span><input id="nutriosShellSearch" type="search" placeholder="Buscar módulo ou recurso..." autocomplete="off"><kbd>Ctrl K</kbd></label><div class="nutrios-shell-top-actions"><a class="nutrios-shell-top-link" href="/app/pacientes?novo=1">+ Novo paciente</a><a class="nutrios-shell-top-link" href="/app/configuracoes#acessos">Compartilhar acessos</a><div class="nutrios-shell-profile"><div class="nutrios-shell-avatar" id="nutriosShellAvatar">N</div><div class="nutrios-shell-profile-copy"><strong id="nutriosShellProfileName">Nutricionista</strong><span>Profissional</span></div></div><button class="nutrios-shell-logout" id="nutriosShellLogout" type="button">Sair</button></div>`;
    const results=document.createElement('div');results.id='nutriosShellSearchResults';results.className='nutrios-shell-search-results';
    document.body.prepend(top);document.body.prepend(aside);document.body.appendChild(results);
    document.body.classList.add('nutrios-shell-ready');document.documentElement.dataset.nutriosShell='unified-v10';

    const input=document.getElementById('nutriosShellSearch');
    if(input){input.addEventListener('input',e=>buildSearchResults(e.target.value));input.addEventListener('focus',e=>{if(e.target.value)buildSearchResults(e.target.value)});input.addEventListener('keydown',e=>{if(e.key==='Escape'){e.target.value='';results.classList.remove('open')}})}
    document.addEventListener('keydown',e=>{if((e.ctrlKey||e.metaKey)&&e.key.toLowerCase()==='k'){e.preventDefault();input?.focus()}});
    document.addEventListener('click',e=>{if(!e.target.closest('.nutrios-shell-search')&&!e.target.closest('.nutrios-shell-search-results'))results.classList.remove('open')});
    const logout=document.getElementById('nutriosShellLogout');if(logout)logout.onclick=async()=>{try{await fetch('/auth/logout',{method:'POST',credentials:'same-origin'})}finally{location.assign('/login')}};
    hydrateProfile();
  }

  function showError(message,retry){
    let box=document.getElementById('nutriosShellError');
    if(!box){box=document.createElement('div');box.id='nutriosShellError';box.className='nutrios-shell-error';box.innerHTML='<span id="nutriosShellErrorText"></span><button type="button" id="nutriosShellRetry">Tentar novamente</button>';document.body.appendChild(box)}
    const text=document.getElementById('nutriosShellErrorText');if(text)text.textContent=message||'Não foi possível carregar os dados agora.';
    const btn=document.getElementById('nutriosShellRetry');if(btn)btn.onclick=()=>{box.classList.remove('show');if(typeof retry==='function')retry()};box.classList.add('show');
  }
  function handleResponse(response,retry){if(response?.status===401){location.assign('/login');return false}if(response?.status===403){showError('Seu acesso não permite abrir este recurso.');return false}const suffix=response?.status?` (erro ${response.status})`:'';showError(`Não foi possível carregar os dados${suffix}. Sua sessão continua ativa.`,retry);return false}
  window.NutriOSUI={mount,showError,handleResponse,escapeHtml};
  if(document.readyState==='loading')document.addEventListener('DOMContentLoaded',mount,{once:true});else mount();
})();

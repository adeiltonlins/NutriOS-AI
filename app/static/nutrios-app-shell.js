(()=>{
  const path=location.pathname.replace(/\/$/,'')||'/';
  const master=[
    ['Regulador de Tokens & SaaS','⚙','/admin','DONO'],
    ['Landing Page Pública & Login','◎','/','Web']
  ];
  const clinical=[
    ['Visão Geral','▦','/app',null],
    ['Pacientes & Prontuários','♟','/app/pacientes',null],
    ['Prescrição & Cardápios','◧','/app/planos','IA Pro'],
    ['Prescrição de Treinos','🏋','/app/treinos','Vídeos & Fichas'],
    ['Calculadora Metabólica','⌗','/app/analise-corporal#metabolica','7 Fórmulas'],
    ['Antropometria & 3D','♧','/app/analise-corporal','4 Fotos'],
    ['Fitoterapia & Receituário','🌿','/app/pacientes?modulo=fitoterapia','Timbrado'],
    ['Rastreamento MSQ / IFM','♡','/app/pacientes?modulo=msq','IA'],
    ['Equivalentes & Trocas','⇄','/app/planos#equivalentes','TACO'],
    ['Exames Laboratoriais','▤','/app/pacientes?modulo=exames','IA'],
    ['Tabela de Alimentos','🍎','/app/planos#taco','TACO'],
    ['Agenda & Consultas','▣','/app/gestao','Hoje']
  ];
  const secondary=[
    ['Financeiro clínico','R$','/app/financeiro'],
    ['Conversas','○','/app/conversas'],
    ['Indicações','◎','/app/leads'],
    ['Captação e vendas','▥','/app/metricas'],
    ['Configurações','⚙','/app/configuracoes']
  ];
  const all=[...master,...clinical,...secondary];
  const escapeHtml=v=>String(v??'').replace(/[&<>"']/g,c=>({'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;',"'":'&#39;'}[c]));
  const current=href=>{const clean=href.split(/[?#]/)[0];return clean==='/app'?path==='/app':path===clean||path.startsWith(clean+'/')};
  const item=([label,icon,href,badge],masterItem=false)=>`<a class="nutrios-shell-link ${masterItem?'master-item':''}" href="${href}" ${current(href)?'aria-current="page"':''}><span class="nutrios-shell-icon">${icon}</span><span class="nutrios-shell-label">${escapeHtml(label)}</span>${badge?`<span class="nutrios-shell-badge">${escapeHtml(badge)}</span>`:''}</a>`;
  function results(q=''){const box=document.getElementById('nutriosShellSearchResults');if(!box)return;const query=q.trim().toLowerCase();const found=all.filter(x=>!query||x[0].toLowerCase().includes(query)).slice(0,10);box.innerHTML=found.map(x=>`<a href="${x[2]}">${escapeHtml(x[0])}</a>`).join('')||'<span>Nenhum módulo encontrado</span>';box.classList.toggle('open',!!query)}
  async function hydrate(){try{const r=await fetch('/api/me',{credentials:'same-origin'});if(!r.ok)return;const me=await r.json(),name=String(me.name||'Nutricionista').trim();document.getElementById('nutriosShellProfileName').textContent=name;document.getElementById('nutriosShellAvatar').textContent=(name[0]||'N').toUpperCase()}catch(_){}}
  function mount(){if(!document.body||document.body.classList.contains('nutrios-shell-ready'))return;
    const aside=document.createElement('aside');aside.className='nutrios-shell-sidebar';aside.innerHTML=`<nav class="nutrios-shell-nav"><div class="nutrios-shell-group master-title">♛ GESTÃO DO DONO (SAAS MASTER)</div>${master.map(x=>item(x,true)).join('')}<div class="nutrios-shell-group">ATENDIMENTO CLÍNICO</div>${clinical.map(x=>item(x)).join('')}<div class="nutrios-shell-group">GESTÃO & AUTOMAÇÃO</div>${secondary.map(x=>item(x)).join('')}</nav><div class="nutrios-shell-footer"><a class="nutrios-shell-copilot" href="/app/conversas"><span>🤖</span><span>Copiloto Gemini</span></a></div>`;
    const top=document.createElement('header');top.className='nutrios-shell-topbar';top.innerHTML=`<a class="nutrios-shell-brand" href="/app"><span class="nutrios-shell-mark">🌿</span><span class="nutrios-shell-brand-copy"><strong>Nutri<span>OS</span></strong><small>Prescrição Clínica • Fitoterapia • Gestão SaaS</small></span><span class="nutrios-shell-gemini">✦ Gemini 3.7 Pro</span></a><div class="nutrios-shell-switches"><a href="/admin">♛ Dono do SaaS</a><a class="active" href="/app">♧ Nutricionista</a><a href="/paciente">▣ App Paciente</a><a class="copilot" href="/app/conversas">🤖 Copiloto IA</a></div><button class="nutrios-shell-logout icon-only" id="nutriosShellLogout" title="Sair">↪</button>`;
    const search=document.createElement('div');search.className='nutrios-shell-search-row';search.innerHTML=`<label class="nutrios-shell-search"><span>⌕</span><input id="nutriosShellSearch" type="search" placeholder="Buscar módulo ou recurso..."><kbd>Ctrl K</kbd></label><div class="nutrios-shell-mini-profile"><span class="nutrios-shell-avatar" id="nutriosShellAvatar">N</span><strong id="nutriosShellProfileName">Nutricionista</strong></div>`;
    const resultsBox=document.createElement('div');resultsBox.id='nutriosShellSearchResults';resultsBox.className='nutrios-shell-search-results';
    document.body.prepend(search);document.body.prepend(top);document.body.prepend(aside);document.body.appendChild(resultsBox);document.body.classList.add('nutrios-shell-ready');document.documentElement.dataset.nutriosShell='zip-v3';
    const input=document.getElementById('nutriosShellSearch');input?.addEventListener('input',e=>results(e.target.value));document.addEventListener('keydown',e=>{if((e.ctrlKey||e.metaKey)&&e.key.toLowerCase()==='k'){e.preventDefault();input?.focus()}});document.addEventListener('click',e=>{if(!e.target.closest('.nutrios-shell-search')&&!e.target.closest('.nutrios-shell-search-results'))resultsBox.classList.remove('open')});document.getElementById('nutriosShellLogout').onclick=async()=>{try{await fetch('/auth/logout',{method:'POST',credentials:'same-origin'})}finally{location='/login'}};hydrate();
  }
  function showError(message,retry){let box=document.getElementById('nutriosShellError');if(!box){box=document.createElement('div');box.id='nutriosShellError';box.className='nutrios-shell-error';box.innerHTML='<span id="nutriosShellErrorText"></span><button id="nutriosShellRetry">Tentar novamente</button>';document.body.appendChild(box)}document.getElementById('nutriosShellErrorText').textContent=message||'Não foi possível carregar os dados agora.';document.getElementById('nutriosShellRetry').onclick=()=>{box.classList.remove('show');retry?.()};box.classList.add('show')}
  function handleResponse(response,retry){if(response?.status===401){location='/login';return false}showError(`Não foi possível carregar os dados${response?.status?` (erro ${response.status})`:''}.`,retry);return false}
  window.NutriOSUI={mount,showError,handleResponse,escapeHtml};document.readyState==='loading'?document.addEventListener('DOMContentLoaded',mount,{once:true}):mount();
})();
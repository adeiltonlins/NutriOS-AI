/* NutriOS dashboard bootstrap: visual loader only. Never intercept fetch/auth. */
(function(){
  document.documentElement.dataset.nutriosLayout='zip-visual-v2';

  function ensureReferenceCSS(){
    const href='/static/nutrios-dashboard-reference-v2.css?v=20260827zip2';
    const existing=document.getElementById('nutriosReferenceV2');
    if(existing){existing.href=href;return;}
    const css=document.createElement('link');css.id='nutriosReferenceV2';css.rel='stylesheet';css.href=href;document.head.appendChild(css);
  }

  function groupNav(){
    const nav=document.querySelector('.os-nav');if(!nav||nav.dataset.zipGrouped)return;
    nav.dataset.zipGrouped='1';
    const links=[...nav.querySelectorAll('.os-nav-item')];
    const addBefore=(label,el)=>{if(!el)return;const g=document.createElement('div');g.className='os-nav-group';g.textContent=label;nav.insertBefore(g,el)};
    addBefore('ATENDIMENTO CLÍNICO',links.find(a=>a.getAttribute('href')==='/app'));
    addBefore('IA & AUTOMAÇÃO',links.find(a=>a.getAttribute('href')==='/app/conversas'));
    addBefore('CONFIGURAÇÕES',links.find(a=>a.getAttribute('href')==='/app/configuracoes'));
    const labels={
      '/app':'Visão Geral','/app/pacientes':'Pacientes & Prontuários','/app/gestao':'Agenda & Consultas','/app/planos':'Prescrição & Cardápios','/app/analise-corporal':'Antropometria & Análise','/app/treinos':'Prescrição de Treinos'
    };
    links.forEach(a=>{const href=a.getAttribute('href'),span=a.querySelector('span:nth-child(2)');if(span&&labels[href])span.textContent=labels[href]});
  }

  function polishBrand(){
    const brand=document.querySelector('.os-brand');if(!brand||brand.dataset.zipBrand)return;brand.dataset.zipBrand='1';
    const name=brand.querySelector('.os-brand-name');if(name)name.innerHTML='Nutri<span>OS</span><small>Clínica & Gestão</small>';
    const mark=brand.querySelector('.os-brand-mark');if(mark)mark.textContent='🌿';
  }

  function cleanup(){document.querySelectorAll('.os-attention-board,#nutriosLayoutAuthority').forEach(el=>el.remove());groupNav();polishBrand()}
  ensureReferenceCSS();
  if(document.readyState==='loading')document.addEventListener('DOMContentLoaded',cleanup,{once:true});else cleanup();
})();

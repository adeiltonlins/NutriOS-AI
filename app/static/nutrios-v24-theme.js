(function(){
  const root=document.documentElement;
  function apply(){root.setAttribute('data-theme','light');root.classList.remove('dark');root.style.colorScheme='light';try{localStorage.setItem('nutrios_theme_v24','light')}catch(_){}const themeMeta=document.querySelector('meta[name="theme-color"]');if(themeMeta)themeMeta.content='#f7f8f5';const statusMeta=document.querySelector('meta[name="apple-mobile-web-app-status-bar-style"]');if(statusMeta)statusMeta.content='default';window.dispatchEvent(new CustomEvent('nutrios-theme-change',{detail:{theme:'light'}}))}
  window.NutriOSTheme={apply,get:()=> 'light',toggle:apply};apply();
  function addStylesheet(href,key){if(document.querySelector(`link[data-nutrios-style="${key}"]`))return;const css=document.createElement('link');css.rel='stylesheet';css.href=href;css.dataset.nutriosStyle=key;document.head.appendChild(css)}
  function addScript(src,key){if(document.querySelector(`script[data-nutrios-script="${key}"]`))return;const js=document.createElement('script');js.src=src;js.defer=true;js.dataset.nutriosScript=key;document.head.appendChild(js)}
  function moduleName(p){if(p==='/app')return 'dashboard';if(p==='/app/pacientes'||p.startsWith('/app/pacientes/'))return 'pacientes';if(p==='/app/gestao')return 'agenda';if(p==='/app/planos')return 'planos';if(p==='/app/clinica'||p.startsWith('/app/consulta'))return 'clinica';if(p==='/app/analise-corporal')return 'antropometria';if(p==='/app/evolucao')return 'evolucao';if(p==='/app/treinos')return 'treinos';if(p==='/app/financeiro')return 'financeiro';if(p==='/app/conversas')return 'conversas';if(p==='/app/leads')return 'indicacoes';if(p==='/app/metricas')return 'metricas';if(p==='/app/configuracoes')return 'configuracoes';return 'operacao'}
  function setupProfessionalShell(){
    const p=location.pathname.replace(/\/$/,'')||'/';if(!p.startsWith('/app')||p.startsWith('/app/api/'))return;
    const module=moduleName(p);document.documentElement.dataset.nutriosModule=module;document.body?.setAttribute('data-nutrios-module',module);
    addStylesheet('/static/nutrios-universal-light.css?v=9','universal-light');
    addStylesheet('/static/nutrios-app-shell.css?v=10','app-shell');
    addScript('/static/nutrios-app-shell.js?v=10','app-shell');
    if(p==='/app'){
      addStylesheet('/static/nutrios-dashboard-reference-v2.css?v=20260827-final','dashboard-reference-v2');
      addStylesheet('/static/nutrios-dashboard-priority.css?v=9','dashboard-priority');
      addScript('/static/nutrios-dashboard-premium.js?v=5','dashboard-premium');
      return;
    }
    addStylesheet('/static/nutrios-zip-modules.css?v=3','zip-modules');
    addStylesheet('/static/nutrios-zip-clinical-v3.css?v=2','zip-clinical-v3');
    addScript('/static/nutrios-zip-clinical-v3.js?v=2','zip-clinical-v3');
    if(p.startsWith('/app/pacientes/')){addStylesheet('/static/nutrios-v2-clinical-modules.css?v=4','v2-clinical-modules');addScript('/static/nutrios-v2-clinical.js?v=4','v2-clinical');addStylesheet('/static/nutrios-anthropometry-v2.css?v=2','anthropometry-v2');addScript('/static/nutrios-anthropometry-v2.js?v=2','anthropometry-v2');addStylesheet('/static/nutrios-fitoterapia-v2.css?v=2','fitoterapia-v2');addScript('/static/nutrios-fitoterapia-v2.js?v=2','fitoterapia-v2');addStylesheet('/static/nutrios-copilot-v2.css?v=2','copilot-v2');addScript('/static/nutrios-copilot-v2.js?v=2','copilot-v2')}
  }
  setupProfessionalShell();
  async function setupTenantPWA(){const match=location.pathname.match(/^\/n\/([^/]+)$/);if(!match)return;const slug=decodeURIComponent(match[1]),fallback='/static/icons/icon-512.svg';try{const r=await fetch('/public/clientes/'+encodeURIComponent(slug),{credentials:'same-origin'});if(!r.ok)throw new Error('identity');const cfg=await r.json(),name=String(cfg.nome||'NutriOS').slice(0,80),color=/^#[0-9a-fA-F]{6}$/.test(String(cfg.cor_principal||''))?cfg.cor_principal:'#1e6b52',icon=String(cfg.logo_url||fallback);const manifest={name:name+' — NutriOS',short_name:name.slice(0,24),description:'Atendimento nutricional digital',start_url:location.pathname,scope:location.pathname.replace(/\/$/,'')+'/',display:'standalone',background_color:'#f7f8f5',theme_color:color,orientation:'portrait-primary',lang:'pt-BR',icons:[{src:icon,sizes:'192x192',type:'image/png',purpose:'any'},{src:icon,sizes:'512x512',type:'image/png',purpose:'any'},{src:icon,sizes:'512x512',type:'image/png',purpose:'maskable'}]};const blob=new Blob([JSON.stringify(manifest)],{type:'application/manifest+json'}),url=URL.createObjectURL(blob);let link=document.querySelector('link[rel="manifest"]');if(!link){link=document.createElement('link');link.rel='manifest';document.head.appendChild(link)}link.href=url;document.documentElement.style.setProperty('--tenant-color',color);if(cfg.logo_url){let fav=document.querySelector('link[data-nutrios-tenant-icon]');if(!fav){fav=document.createElement('link');fav.rel='icon';fav.dataset.nutriosTenantIcon='1';document.head.appendChild(fav)}fav.href=cfg.logo_url}}catch(_){let link=document.querySelector('link[rel="manifest"]');if(!link){link=document.createElement('link');link.rel='manifest';document.head.appendChild(link)}link.href='/static/manifest.json'}}
  function mount(){document.querySelectorAll('#nutrios-theme-toggle,#themeToggle,[data-theme-toggle]').forEach(el=>el.remove());apply();addStylesheet('/static/nutrios-final-light-qa.css?v=3','final-light-qa');setupTenantPWA()}
  document.readyState==='loading'?document.addEventListener('DOMContentLoaded',()=>{document.body?.setAttribute('data-nutrios-module',document.documentElement.dataset.nutriosModule||'');mount()}):mount();
})();

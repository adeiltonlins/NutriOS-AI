(function(){
  const K='nutrios_theme_v24';
  const root=document.documentElement;
  function current(){return localStorage.getItem(K)==='dark'?'dark':'light'}
  function apply(t){
    root.setAttribute('data-theme',t);
    root.classList.toggle('dark',t==='dark');
    localStorage.setItem(K,t);
    document.documentElement.style.colorScheme=t==='dark'?'dark':'light';
    ['nutrios-theme-toggle','themeToggle'].forEach(id=>{
      const b=document.getElementById(id); if(!b)return;
      b.textContent=t==='dark'?'☀':'☾';
      b.title=t==='dark'?'Usar tema claro':'Usar Dark Green';
      b.setAttribute('aria-label',b.title);
    });
    window.dispatchEvent(new CustomEvent('nutrios-theme-change',{detail:{theme:t}}));
  }
  window.NutriOSTheme={apply,get:current,toggle:()=>apply(root.getAttribute('data-theme')==='dark'?'light':'dark')};
  apply(current());

  function addStylesheet(href,key){
    if(document.querySelector(`link[data-nutrios-style="${key}"]`))return;
    const css=document.createElement('link');css.rel='stylesheet';css.href=href;css.dataset.nutriosStyle=key;document.head.appendChild(css);
  }
  function addScript(src,key){
    if(document.querySelector(`script[data-nutrios-script="${key}"]`))return;
    const js=document.createElement('script');js.src=src;js.defer=true;js.dataset.nutriosScript=key;document.head.appendChild(js);
  }

  function setupProfessionalShell(){
    const p=location.pathname.replace(/\/$/,'')||'/';
    if(p==='/app'){
      addStylesheet('/static/nutrios-dashboard-premium.css?v=1','dashboard-premium');
      addStylesheet('/static/nutrios-dashboard-priority.css?v=1','dashboard-priority');
      addScript('/static/nutrios-dashboard-premium.js?v=1','dashboard-premium');
      return;
    }
    if(!p.startsWith('/app/')||p.startsWith('/app/api/'))return;
    addStylesheet('/static/nutrios-app-shell.css?v=3','app-shell');
    if(!window.NutriOSUI&&!document.querySelector('script[data-nutrios-app-shell]')){
      const js=document.createElement('script');js.src='/static/nutrios-app-shell.js?v=3';js.defer=true;js.dataset.nutriosAppShell='1';document.head.appendChild(js);
    }
  }
  setupProfessionalShell();

  async function setupTenantPWA(){
    const match=location.pathname.match(/^\/n\/([^/]+)$/);
    if(!match)return;
    const slug=decodeURIComponent(match[1]);
    const fallback='/static/icons/icon-512.svg';
    try{
      const r=await fetch('/public/clientes/'+encodeURIComponent(slug),{credentials:'same-origin'});
      if(!r.ok)throw new Error('identity');
      const cfg=await r.json();
      const name=String(cfg.nome||'NutriOS').slice(0,80);
      const color=/^#[0-9a-fA-F]{6}$/.test(String(cfg.cor_principal||''))?cfg.cor_principal:'#003d27';
      const icon=String(cfg.logo_url||fallback);
      const manifest={name:name+' — NutriOS',short_name:name.slice(0,24),description:'Atendimento nutricional digital',start_url:location.pathname,scope:location.pathname.replace(/\/$/,'')+'/',display:'standalone',background_color:'#00261a',theme_color:color,orientation:'portrait-primary',lang:'pt-BR',icons:[{src:icon,sizes:'192x192',type:'image/png',purpose:'any'},{src:icon,sizes:'512x512',type:'image/png',purpose:'any'},{src:icon,sizes:'512x512',type:'image/png',purpose:'maskable'}]};
      const blob=new Blob([JSON.stringify(manifest)],{type:'application/manifest+json'});const url=URL.createObjectURL(blob);
      let link=document.querySelector('link[rel="manifest"]');if(!link){link=document.createElement('link');link.rel='manifest';document.head.appendChild(link)}link.href=url;
      document.documentElement.style.setProperty('--tenant-color',color);
      if(cfg.logo_url){let fav=document.querySelector('link[data-nutrios-tenant-icon]');if(!fav){fav=document.createElement('link');fav.rel='icon';fav.dataset.nutriosTenantIcon='1';document.head.appendChild(fav)}fav.href=cfg.logo_url;}
    }catch(_){let link=document.querySelector('link[rel="manifest"]');if(!link){link=document.createElement('link');link.rel='manifest';document.head.appendChild(link)}link.href='/static/manifest.json';}
  }

  function mount(){
    if(!document.getElementById('nutrios-theme-toggle')){const b=document.createElement('button');b.id='nutrios-theme-toggle';b.type='button';b.onclick=()=>window.NutriOSTheme.toggle();document.body.appendChild(b);}
    apply(current());setupTenantPWA();
  }
  document.readyState==='loading'?document.addEventListener('DOMContentLoaded',mount):mount();
})();
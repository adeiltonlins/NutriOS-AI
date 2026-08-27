(function(){
  const root=document.documentElement;
  function apply(){root.setAttribute('data-theme','light');root.classList.remove('dark');root.style.colorScheme='light';try{localStorage.setItem('nutrios_theme_v24','light')}catch(_){}const meta=document.querySelector('meta[name="theme-color"]');if(meta)meta.content='#ffffff'}
  window.NutriOSTheme={apply,get:()=> 'light',toggle:apply};apply();
  function addStylesheet(href,key){if(document.querySelector(`link[data-nutrios-style="${key}"]`))return;const css=document.createElement('link');css.rel='stylesheet';css.href=href;css.dataset.nutriosStyle=key;document.head.appendChild(css)}
  function addScript(src,key){if(document.querySelector(`script[data-nutrios-script="${key}"]`))return;const js=document.createElement('script');js.src=src;js.defer=true;js.dataset.nutriosScript=key;document.head.appendChild(js)}
  function setup(){const p=location.pathname.replace(/\/$/,'')||'/';if(!p.startsWith('/app')||p.startsWith('/app/api/'))return;
    if(p==='/app'){addStylesheet('/static/nutrios-zip-exact-dashboard.css?v=20260827-exact2','zip-exact-dashboard');addScript('/static/nutrios-zip-exact-dashboard.js?v=20260827-exact2','zip-exact-dashboard');return}
    addStylesheet('/static/nutrios-universal-light.css?v=10','universal-light');
    addStylesheet('/static/nutrios-zip-modules.css?v=4','zip-modules');
    addStylesheet('/static/nutrios-zip-clinical-v3.css?v=3','zip-clinical-v3');
    addScript('/static/nutrios-zip-clinical-v3.js?v=3','zip-clinical-v3');
    if(p.startsWith('/app/pacientes/')){addStylesheet('/static/nutrios-v2-clinical-modules.css?v=5','v2-clinical-modules');addScript('/static/nutrios-v2-clinical.js?v=5','v2-clinical');addStylesheet('/static/nutrios-anthropometry-v2.css?v=3','anthropometry-v2');addScript('/static/nutrios-anthropometry-v2.js?v=3','anthropometry-v2');addStylesheet('/static/nutrios-fitoterapia-v2.css?v=3','fitoterapia-v2');addScript('/static/nutrios-fitoterapia-v2.js?v=3','fitoterapia-v2');addStylesheet('/static/nutrios-copilot-v2.css?v=3','copilot-v2');addScript('/static/nutrios-copilot-v2.js?v=3','copilot-v2')}
    addStylesheet('/static/nutrios-app-shell.css?v=11','app-shell');
    addStylesheet('/static/nutrios-zip-frame-v3.css?v=1','zip-frame-v3');
    addScript('/static/nutrios-app-shell.js?v=11','app-shell')
  }
  setup();
  function mount(){document.querySelectorAll('#nutrios-theme-toggle,#themeToggle,[data-theme-toggle]').forEach(el=>el.remove());apply()}
  document.readyState==='loading'?document.addEventListener('DOMContentLoaded',mount):mount();
})();
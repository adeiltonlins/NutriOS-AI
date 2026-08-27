(function(){
  const root=document.documentElement;
  function apply(){root.setAttribute('data-theme','light');root.classList.remove('dark');root.style.colorScheme='light';try{localStorage.setItem('nutrios_theme_v24','light')}catch(_){}const meta=document.querySelector('meta[name="theme-color"]');if(meta)meta.content='#ffffff'}
  window.NutriOSTheme={apply,get:()=> 'light',toggle:apply};apply();
  const p=location.pathname.replace(/\/$/,'')||'/';
  const professional=p==='/app'||(p.startsWith('/app/')&&!p.startsWith('/app/api/'));
  if(professional){
    root.classList.add('nutrios-shell-booting');
    if(!document.querySelector('link[data-nutrios-zip-spa]')){const l=document.createElement('link');l.rel='stylesheet';l.href='/static/nutrios-zip-spa.css?v=20260827-1';l.dataset.nutriosZipSpa='1';document.head.appendChild(l)}
    if(!document.querySelector('script[data-nutrios-zip-spa]')){const s=document.createElement('script');s.src='/static/nutrios-zip-spa.js?v=20260827-1';s.defer=true;s.dataset.nutriosZipSpa='1';document.head.appendChild(s)}
    return;
  }
  function mount(){document.querySelectorAll('#nutrios-theme-toggle,#themeToggle,[data-theme-toggle]').forEach(el=>el.remove());apply()}
  document.readyState==='loading'?document.addEventListener('DOMContentLoaded',mount):mount();
})();
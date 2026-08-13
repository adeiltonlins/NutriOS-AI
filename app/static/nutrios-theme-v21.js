
(function(){
  const KEY='nutrios_theme';
  const root=document.documentElement;
  const saved=localStorage.getItem(KEY);
  const initial=saved==='dark'?'dark':'light';

  function label(theme){
    return theme==='dark' ? 'Usar tema claro' : 'Usar tema Dark Green';
  }
  function icon(theme){
    return theme==='dark' ? '☀' : '☾';
  }
  function apply(theme){
    root.setAttribute('data-theme',theme);
    localStorage.setItem(KEY,theme);
    const btn=document.getElementById('nutrios-theme-toggle');
    if(btn){
      btn.textContent=icon(theme);
      btn.title=label(theme);
      btn.setAttribute('aria-label',label(theme));
      btn.setAttribute('aria-pressed',theme==='dark'?'true':'false');
    }
    window.dispatchEvent(new CustomEvent('nutrios-theme-change',{detail:{theme}}));
  }
  function mount(){
    if(document.getElementById('nutrios-theme-toggle')) return;
    const btn=document.createElement('button');
    btn.id='nutrios-theme-toggle';
    btn.type='button';
    btn.addEventListener('click',()=>apply(root.getAttribute('data-theme')==='dark'?'light':'dark'));
    document.body.appendChild(btn);
    apply(root.getAttribute('data-theme')||initial);
  }
  root.setAttribute('data-theme',initial);
  if(document.readyState==='loading') document.addEventListener('DOMContentLoaded',mount);
  else mount();
})();

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
  function mount(){
    if(!document.getElementById('nutrios-theme-toggle')){
      const b=document.createElement('button');b.id='nutrios-theme-toggle';b.type='button';b.onclick=()=>window.NutriOSTheme.toggle();document.body.appendChild(b);
    }
    apply(current());
  }
  document.readyState==='loading'?document.addEventListener('DOMContentLoaded',mount):mount();
})();
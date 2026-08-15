
(function(){
  const KEY = 'nutrios_theme';
  const root = document.documentElement;

  function getTheme(){
    const saved = localStorage.getItem(KEY);
    return saved === 'dark' ? 'dark' : 'light';
  }

  function applyTheme(theme){
    root.setAttribute('data-theme', theme);
    localStorage.setItem(KEY, theme);
    const btn = document.getElementById('nutrios-theme-toggle');
    if(btn){
      const dark = theme === 'dark';
      btn.setAttribute('aria-pressed', dark ? 'true' : 'false');
      btn.innerHTML = '<span class="theme-dot"></span>' + (dark ? 'Tema claro' : 'Dark Green');
      btn.title = dark ? 'Usar tema claro' : 'Usar tema Dark Green';
    }
    window.dispatchEvent(new CustomEvent('nutrios-theme-change',{detail:{theme}}));
  }

  function mountToggle(){
    if(document.getElementById('nutrios-theme-toggle')) return;
    const btn = document.createElement('button');
    btn.id = 'nutrios-theme-toggle';
    btn.type = 'button';
    btn.setAttribute('aria-label','Alternar aparência do NutriOS');
    btn.addEventListener('click',()=>{
      applyTheme(root.getAttribute('data-theme') === 'dark' ? 'light' : 'dark');
    });
    document.body.appendChild(btn);
    applyTheme(getTheme());
  }

  // Apply immediately to minimize flash.
  root.setAttribute('data-theme', getTheme());

  if(document.readyState === 'loading'){
    document.addEventListener('DOMContentLoaded', mountToggle);
  }else{
    mountToggle();
  }
})();

/* NutriOS dashboard bootstrap: visual loader only. Do not intercept fetch or auth. */
(function(){
  document.documentElement.dataset.nutriosLayout='reference-light-20260827c';

  function ensureReferenceCSS(){
    const href='/static/nutrios-dashboard-reference-v2.css?v=20260827c';
    const existing=document.getElementById('nutriosReferenceV2');
    if(existing){existing.href=href;return;}
    const css=document.createElement('link');
    css.id='nutriosReferenceV2';
    css.rel='stylesheet';
    css.href=href;
    document.head.appendChild(css);
  }

  function cleanupLegacyInjection(){
    document.querySelectorAll('.os-attention-board,#nutriosLayoutAuthority').forEach(el=>el.remove());
  }

  ensureReferenceCSS();
  if(document.readyState==='loading'){
    document.addEventListener('DOMContentLoaded',cleanupLegacyInjection,{once:true});
  }else{
    cleanupLegacyInjection();
  }
})();

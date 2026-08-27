/* NutriOS dashboard bootstrap resilience + approved light reference loader. */
(function(){
  const nativeFetch=window.fetch.bind(window);
  let meRequestFailed=false;

  document.documentElement.dataset.nutriosLayout='reference-light-20260827b';

  function ensureReferenceCSS(){
    const existing=document.getElementById('nutriosReferenceV2');
    if(existing){existing.href='/static/nutrios-dashboard-reference-v2.css?v=20260827b';return;}
    const css=document.createElement('link');
    css.id='nutriosReferenceV2';
    css.rel='stylesheet';
    css.href='/static/nutrios-dashboard-reference-v2.css?v=20260827b';
    document.head.appendChild(css);
  }
  ensureReferenceCSS();

  function banner(message){
    let el=document.getElementById('dashboardNetworkError');
    if(!el){
      el=document.createElement('div');
      el.id='dashboardNetworkError';
      el.setAttribute('role','alert');
      el.style.cssText='position:sticky;top:80px;z-index:70;display:flex;align-items:center;justify-content:space-between;gap:14px;padding:12px 28px;border-bottom:1px solid #e4c27b;background:#fff7df;color:#6d4a00;font:700 13px Inter,system-ui,sans-serif';
      const text=document.createElement('span');text.id='dashboardNetworkErrorText';
      const retry=document.createElement('button');retry.type='button';retry.textContent='Tentar novamente';retry.style.cssText='min-height:36px;padding:7px 11px;border:1px solid #d6a84c;border-radius:8px;background:#fff;color:#6d4a00;font-weight:800;cursor:pointer';retry.addEventListener('click',()=>location.reload());
      el.append(text,retry);
      const workspace=document.querySelector('.os-workspace'),topbar=document.querySelector('.os-topbar');
      if(workspace&&topbar)topbar.insertAdjacentElement('afterend',el);else document.body.prepend(el);
    }
    const text=document.getElementById('dashboardNetworkErrorText');if(text)text.textContent=message;
  }

  window.fetch=async function(input,init){
    const url=typeof input==='string'?input:(input&&input.url)||'';
    try{
      const response=await nativeFetch(input,init);
      if(url==='/api/me'){
        if(response.status===401||response.status===403)return response;
        if(!response.ok){
          meRequestFailed=true;
          banner('Não foi possível confirmar sua sessão agora. Sua tela foi mantida.');
          return new Response(JSON.stringify({name:'Nutricionista',_degraded:true}),{status:200,headers:{'Content-Type':'application/json'}});
        }
      }
      if(url==='/app/api/dashboard-clinico'&&!response.ok)banner('Não foi possível atualizar o dashboard. Verifique sua conexão e tente novamente.');
      return response;
    }catch(error){
      if(url==='/api/me'){
        meRequestFailed=true;
        banner('Falha de conexão. O NutriOS não vai encerrar sua sessão por causa disso.');
        return new Response(JSON.stringify({name:'Nutricionista',_degraded:true}),{status:200,headers:{'Content-Type':'application/json'}});
      }
      if(url==='/app/api/dashboard-clinico'){
        banner('Falha de conexão ao carregar o dashboard. Tente novamente quando a conexão estabilizar.');
        return new Response(JSON.stringify({metrics:{},analytics:{},checkins:[],appointments:[]}),{status:503,headers:{'Content-Type':'application/json'}});
      }
      throw error;
    }
  };

  window.addEventListener('unhandledrejection',event=>{
    if(meRequestFailed){event.preventDefault();banner('Falha temporária de conexão. Sua sessão foi preservada.');}
  });

  function cleanupLegacyInjection(){
    document.querySelectorAll('.os-attention-board,#nutriosLayoutAuthority').forEach(el=>el.remove());
  }
  if(document.readyState==='loading')document.addEventListener('DOMContentLoaded',cleanupLegacyInjection,{once:true});else cleanupLegacyInjection();
})();
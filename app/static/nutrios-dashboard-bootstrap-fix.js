/* NutriOS dashboard bootstrap resilience.
   Loaded before the legacy dashboard bootstrap so transient network/server
   failures never masquerade as an expired session. */
(function(){
  const nativeFetch=window.fetch.bind(window);
  let meRequestFailed=false;

  function banner(message){
    let el=document.getElementById('dashboardNetworkError');
    if(!el){
      el=document.createElement('div');
      el.id='dashboardNetworkError';
      el.setAttribute('role','alert');
      el.style.cssText='position:sticky;top:68px;z-index:70;display:flex;align-items:center;justify-content:space-between;gap:14px;padding:12px clamp(18px,3vw,38px);border-bottom:1px solid #e4c27b;background:#fff7df;color:#6d4a00;font:700 14px Inter,system-ui,sans-serif';
      const text=document.createElement('span');
      text.id='dashboardNetworkErrorText';
      const retry=document.createElement('button');
      retry.type='button';
      retry.textContent='Tentar novamente';
      retry.style.cssText='min-height:38px;padding:8px 12px;border:1px solid #d6a84c;border-radius:10px;background:#fff;color:#6d4a00;font-weight:800;cursor:pointer';
      retry.addEventListener('click',()=>location.reload());
      el.append(text,retry);
      const workspace=document.querySelector('.os-workspace');
      const topbar=document.querySelector('.os-topbar');
      if(workspace&&topbar)topbar.insertAdjacentElement('afterend',el);else document.body.prepend(el);
    }
    const text=document.getElementById('dashboardNetworkErrorText');
    if(text)text.textContent=message;
  }

  window.fetch=async function(input,init){
    const url=typeof input==='string'?input:(input&&input.url)||'';
    try{
      const response=await nativeFetch(input,init);
      if(url==='/api/me'){
        // Only 401/403 mean the user must authenticate again. Server errors
        // are converted into a successful placeholder response so the legacy
        // bootstrap does not redirect to /login.
        if(response.status===401||response.status===403)return response;
        if(!response.ok){
          meRequestFailed=true;
          banner('Não foi possível confirmar sua sessão agora. Sua tela foi mantida.');
          return new Response(JSON.stringify({name:'Nutricionista',_degraded:true}),{status:200,headers:{'Content-Type':'application/json'}});
        }
      }
      if(url==='/app/api/dashboard-clinico'&&!response.ok){
        banner('Não foi possível atualizar o dashboard. Verifique sua conexão e tente novamente.');
      }
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
    if(meRequestFailed){
      event.preventDefault();
      banner('Falha temporária de conexão. Sua sessão foi preservada.');
    }
  });
})();
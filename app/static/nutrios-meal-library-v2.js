(()=>{
  const path=location.pathname.replace(/\/$/,'')||'/';
  const match=path.match(/^\/app\/pacientes\/([^/]+)/);if(!match)return;
  const patientId=decodeURIComponent(match[1]);
  const esc=v=>String(v??'').replace(/[&<>"']/g,c=>({'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;',"'":'&#39;'}[c]));
  let library=[],rendering=false;

  async function api(url){
    const r=await fetch(url,{credentials:'same-origin',cache:'no-store'});
    const x=await r.json().catch(()=>[]);
    if(!r.ok)throw new Error(x?.detail||'Não foi possível carregar a biblioteca de cardápios');
    return x;
  }

  function mealDefaults(names=[]){
    const defaultTimes=['07:00','10:00','12:30','16:00','19:30','21:30','22:30'];
    return names.map((name,index)=>({name,time:defaultTimes[index]||'',items:[]}));
  }

  function showLoadedNotice(plan){
    let notice=document.getElementById('mealLibraryLoadedNotice');
    if(!notice){
      notice=document.createElement('div');
      notice.id='mealLibraryLoadedNotice';
      notice.className='meal-library-loaded-notice';
      const builder=document.getElementById('mealTabs')?.closest('.panel');
      if(builder)builder.insertBefore(notice,builder.firstChild);
    }
    if(!notice)return;
    notice.innerHTML=`<div><b>✓ Modelo “${esc(plan.title)}” carregado no construtor</b><p>A Biblioteca não publica uma dieta pronta. Ela trouxe a estrutura-base para este paciente. Agora ajuste alimentos, quantidades, horários e orientações antes de salvar e publicar.</p></div><button type="button" data-close-library-notice aria-label="Fechar">×</button>`;
    notice.hidden=false;
    notice.querySelector('[data-close-library-notice]').onclick=()=>notice.hidden=true;
  }

  function focusBuilder(){
    const builder=document.getElementById('mealTabs')?.closest('.panel');
    if(!builder)return;
    builder.classList.remove('meal-library-focus');
    void builder.offsetWidth;
    builder.classList.add('meal-library-focus');
    builder.scrollIntoView({behavior:'smooth',block:'start'});
    setTimeout(()=>builder.classList.remove('meal-library-focus'),2600);
  }

  function useLibraryPlan(key){
    const plan=library.find(x=>String(x.key)===String(key));if(!plan)return;
    try{
      meals=mealDefaults(plan.meals||[]);
      if(!meals.length)meals=[{name:'Café da manhã',time:'07:00',items:[]}];
      activeMeal=0;
      if(typeof planTitle!=='undefined')planTitle.value=plan.title||'Plano alimentar';
      if(typeof planObjective!=='undefined')planObjective.value=plan.objective||'';
      if(typeof drawMeals==='function')drawMeals();
      showLoadedNotice(plan);
      focusBuilder();
      if(typeof notify==='function')notify(`Modelo ${plan.title} carregado. Personalize antes de salvar.`);
    }catch(err){console.error('[meal-library]',err)}
  }

  function savedTemplates(){
    try{return (data?.meal_plans||[]).filter(x=>x.is_template)}catch(_){return []}
  }

  function renderTemplates(){
    const host=document.getElementById('templates');if(!host||rendering)return;
    rendering=true;
    const mine=savedTemplates();
    host.innerHTML=`
      <div class="meal-library-explainer">
        <b>Como funciona a Biblioteca de cardápios?</b>
        <p>Escolher um modelo <strong>não cria nem publica uma dieta automaticamente</strong>. O NutriOS carrega a estrutura no Construtor de refeições para o nutricionista adequar ao paciente.</p>
        <span>1. Escolha o modelo → 2. Personalize no construtor → 3. Salve o rascunho → 4. Revise e publique</span>
      </div>
      <div class="meal-library-section-title"><div><small>BIBLIOTECA NUTRIOS</small><b>Modelos de cardápio</b></div><em>Mesma ordem da Biblioteca</em></div>
      <div class="meal-library-cards">${library.map((x,i)=>`<article class="meal-library-card"><span class="meal-library-order">${i+1}</span><div><b>${esc(x.title)}</b><p>${esc(x.objective||'Estrutura-base para personalização profissional.')}</p><small>${(x.meals||[]).map(esc).join(' · ')}</small></div><button type="button" data-library-plan="${esc(x.key)}">Usar modelo</button></article>`).join('')||'<div class="empty">Biblioteca indisponível no momento.</div>'}</div>
      ${mine.length?`<div class="meal-library-section-title mine"><div><small>MINHA BIBLIOTECA</small><b>Modelos salvos por você</b></div></div><div class="meal-library-cards saved">${mine.map(x=>`<article class="meal-library-card"><div><b>${esc(x.template_name||x.title)}</b><p>Modelo reutilizável da sua conta</p><small>${x.content?.length||0} refeições</small></div><button type="button" data-saved-template="${esc(x.id)}">Usar modelo</button></article>`).join('')}</div>`:''}`;
    host.querySelectorAll('[data-library-plan]').forEach(b=>b.onclick=()=>useLibraryPlan(b.dataset.libraryPlan));
    host.querySelectorAll('[data-saved-template]').forEach(b=>b.onclick=()=>{
      if(typeof useTemplate==='function')useTemplate(b.dataset.savedTemplate);
      const p=mine.find(x=>String(x.id)===String(b.dataset.savedTemplate));
      showLoadedNotice({title:p?.template_name||p?.title||'Modelo salvo'});focusBuilder();
      if(typeof notify==='function')notify('Modelo salvo carregado no construtor. Personalize antes de salvar.');
    });
    host.dataset.libraryRendered='1';rendering=false;
  }

  async function init(){
    try{library=await api('/app/api/biblioteca-planos')}catch(err){console.warn(err.message);library=[]}
    const host=document.getElementById('templates');if(!host)return;
    renderTemplates();
    const observer=new MutationObserver(()=>{
      if(rendering)return;
      if(host.dataset.libraryRendered==='1'&&host.querySelector('.meal-library-explainer'))return;
      renderTemplates();
    });
    observer.observe(host,{childList:true,subtree:false});
    document.addEventListener('click',e=>{
      const tab=e.target.closest('[data-v="mealplan"]');if(tab)setTimeout(renderTemplates,80);
    });
  }

  document.readyState==='loading'?document.addEventListener('DOMContentLoaded',init,{once:true}):init();
})();
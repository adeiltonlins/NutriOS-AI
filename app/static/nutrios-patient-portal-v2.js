(()=>{
  const home=document.getElementById('homeView');
  const tabs=document.querySelector('.portal-tabs');
  if(!home||!tabs)return;

  const esc=(value)=>String(value??'').replace(/[&<>"']/g,(c)=>({'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;',"'":'&#39;'}[c]));
  const fmtDate=(value)=>{if(!value)return '—';const d=new Date(value);return Number.isNaN(d.valueOf())?'—':d.toLocaleDateString('pt-BR')};
  const firstName=(value)=>String(value||'').trim().split(/\s+/)[0]||'Paciente';
  async function get(url){
    const response=await fetch(url,{credentials:'same-origin',cache:'no-store'});
    if(response.status===401){location='/paciente/login';throw new Error('Sessão expirada');}
    if(!response.ok)throw new Error('Falha ao carregar');
    return response.json();
  }
  function openView(view){
    const tab=document.querySelector(`.portal-tabs .tab[data-view="${view}"]`);
    if(tab){tab.click();return;}
    const section=document.getElementById(view);
    if(section){document.querySelectorAll('.view').forEach(x=>x.classList.toggle('on',x===section));section.scrollIntoView({behavior:'smooth',block:'start'});}
  }
  function ensureShell(){
    if(document.getElementById('patientV2Overview'))return;
    const hero=home.querySelector('.patient-home-hero');
    if(!hero)return;
    hero.insertAdjacentHTML('afterend',`
      <section id="patientV2Overview" class="patient-v2-overview" aria-label="Resumo do acompanhamento">
        <article class="patient-v2-kpi"><span>Plano atual</span><b id="patientV2Plan">—</b><small id="patientV2PlanMeta">Carregando...</small></article>
        <article class="patient-v2-kpi"><span>Último check-in</span><b id="patientV2Checkin">—</b><small id="patientV2CheckinMeta">Carregando...</small></article>
        <article class="patient-v2-kpi"><span>Documentos</span><b id="patientV2Docs">—</b><small>Disponíveis no seu acompanhamento</small></article>
        <article class="patient-v2-kpi"><span>Diário alimentar</span><b id="patientV2Diary">—</b><small>Registros enviados</small></article>
      </section>
      <section class="patient-v2-dashboard" aria-label="Visão geral do acompanhamento">
        <article class="patient-v2-panel">
          <div class="patient-v2-panel-head"><div><h2>Seu acompanhamento agora</h2><p>Um resumo do que foi registrado mais recentemente.</p></div><button class="patient-v2-link" type="button" data-patient-open="checkinView">Novo check-in</button></div>
          <div id="patientV2Timeline" class="patient-v2-timeline"><div class="patient-v2-empty">Carregando seu acompanhamento...</div></div>
        </article>
        <aside class="patient-v2-panel">
          <div class="patient-v2-panel-head"><div><h2>Próximos passos</h2><p>Acesse rapidamente o que você precisa hoje.</p></div></div>
          <div class="patient-v2-timeline">
            <button class="patient-v2-row patient-v2-action" type="button" data-patient-open="planView"><span><strong>Revisar plano alimentar</strong><small>Refeições, orientações e PDF publicado.</small></span><span class="patient-v2-score">→</span></button>
            <button class="patient-v2-row patient-v2-action" type="button" data-patient-open="checkinView"><span><strong>Enviar check-in</strong><small>Atualize seu nutricionista sobre sua semana.</small></span><span class="patient-v2-score">→</span></button>
            <button class="patient-v2-row patient-v2-action" type="button" data-patient-open="diaryView"><span><strong>Registrar refeição</strong><small>Adicione uma refeição ao diário alimentar.</small></span><span class="patient-v2-score">→</span></button>
            <button class="patient-v2-row patient-v2-action" type="button" data-patient-open="chatView"><span><strong>NutriOS Intelligence</strong><small>Tire dúvidas dentro das orientações do acompanhamento.</small></span><span class="patient-v2-score">✦</span></button>
          </div>
        </aside>
      </section>`);
    home.querySelectorAll('[data-open]').forEach((button)=>button.addEventListener('click',()=>openView(button.dataset.open)));
    home.querySelectorAll('[data-patient-open]').forEach((button)=>button.addEventListener('click',()=>openView(button.dataset.patientOpen)));
  }
  function renderTimeline(plan,checkins,diary,documents){
    const target=document.getElementById('patientV2Timeline');
    if(!target)return;
    const rows=[];
    const lastCheckin=Array.isArray(checkins)&&checkins.length?checkins[0]:null;
    if(lastCheckin){
      const scores=[['Fome',lastCheckin.hunger],['Energia',lastCheckin.energy],['Sono',lastCheckin.sleep],['Adesão',lastCheckin.adherence]].filter(([,v])=>v!==null&&v!==undefined);
      const avg=scores.length?Math.round(scores.reduce((a,[,v])=>a+Number(v||0),0)/scores.length):null;
      rows.push(`<div class="patient-v2-row"><span><strong>Check-in de ${esc(fmtDate(lastCheckin.created_at))}</strong><small>${esc(scores.map(([k,v])=>`${k} ${v}`).join(' · ')||'Acompanhamento enviado')}</small></span>${avg!==null?`<span class="patient-v2-score">${avg}/10</span>`:''}</div>`);
    }
    if(plan){
      const meals=Array.isArray(plan.content)?plan.content.length:0;
      rows.push(`<div class="patient-v2-row"><span><strong>${esc(plan.title||'Plano alimentar')}</strong><small>${meals?`${meals} refeição${meals===1?'':'ões'} organizadas`:'Plano disponível para consulta'}</small></span><span class="patient-v2-score">✓</span></div>`);
    }
    const lastDiary=Array.isArray(diary)&&diary.length?diary[0]:null;
    if(lastDiary)rows.push(`<div class="patient-v2-row"><span><strong>Último registro no diário</strong><small>${esc(lastDiary.meal_type||'Refeição')} · ${esc(fmtDate(lastDiary.consumed_at||lastDiary.created_at))}</small></span><span class="patient-v2-score">✓</span></div>`);
    if(Array.isArray(documents)&&documents.length)rows.push(`<div class="patient-v2-row"><span><strong>${documents.length} documento${documents.length===1?'':'s'} disponível${documents.length===1?'':'is'}</strong><small>Planos, relatórios e materiais da clínica.</small></span><span class="patient-v2-score">${documents.length}</span></div>`);
    target.innerHTML=rows.length?rows.join(''):'<div class="patient-v2-empty">Assim que seu nutricionista publicar informações ou você enviar um check-in, seu resumo aparecerá aqui.</div>';
  }
  async function refresh(){
    ensureShell();
    const results=await Promise.allSettled([
      get('/paciente/api/me'),get('/paciente/api/plano'),get('/paciente/api/checkins'),get('/paciente/api/documentos'),get('/paciente/api/diario')
    ]);
    const value=(i,fallback)=>results[i].status==='fulfilled'?results[i].value:fallback;
    const me=value(0,{}),plan=value(1,null),checkins=value(2,[]),documents=value(3,[]),diary=value(4,[]);
    const hero=home.querySelector('.patient-home-hero h1');
    if(hero&&me.name)hero.textContent=`Olá, ${firstName(me.name)}. Seu acompanhamento está aqui.`;
    const planEl=document.getElementById('patientV2Plan'),planMeta=document.getElementById('patientV2PlanMeta');
    if(planEl)planEl.textContent=plan?.title||'Aguardando';
    if(planMeta)planMeta.textContent=plan?(Array.isArray(plan.content)?`${plan.content.length} refeições no plano`:'Plano publicado'):'Seu nutricionista ainda não publicou um plano';
    const last=Array.isArray(checkins)&&checkins.length?checkins[0]:null;
    const checkEl=document.getElementById('patientV2Checkin'),checkMeta=document.getElementById('patientV2CheckinMeta');
    if(checkEl)checkEl.textContent=last?fmtDate(last.created_at):'Pendente';
    if(checkMeta)checkMeta.textContent=last?'Seu acompanhamento está atualizado':'Envie seu primeiro check-in';
    const docsEl=document.getElementById('patientV2Docs');if(docsEl)docsEl.textContent=Array.isArray(documents)?String(documents.length):'0';
    const diaryEl=document.getElementById('patientV2Diary');if(diaryEl)diaryEl.textContent=Array.isArray(diary)?String(diary.length):'0';
    renderTimeline(plan,checkins,diary,documents);
  }
  document.addEventListener('click',(event)=>{const button=event.target.closest('[data-patient-open]');if(button)openView(button.dataset.patientOpen)});
  window.addEventListener('nutrios:checkin-saved',refresh);
  if(document.readyState==='loading')document.addEventListener('DOMContentLoaded',refresh);else refresh();
})();

(()=>{
  if(document.querySelector('script[data-patient-clinical-readonly]'))return;
  const script=document.createElement('script');
  script.src='/static/nutrios-patient-clinical-readonly-v2.js?v=1';
  script.defer=true;
  script.dataset.patientClinicalReadonly='1';
  document.head.appendChild(script);
})();

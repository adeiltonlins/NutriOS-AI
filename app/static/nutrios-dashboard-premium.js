(()=>{
  const esc=v=>String(v??'').replace(/[&<>"']/g,c=>({'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;',"'":'&#39;'}[c]));
  function mount(){
    if(location.pathname.replace(/\/$/,'')!=='/app'||document.getElementById('nutriosPriorityLayer'))return;
    const heading=document.querySelector('.os-heading-row');
    const metrics=document.querySelector('.os-metrics');
    if(!heading||!metrics)return;
    const section=document.createElement('section');
    section.id='nutriosPriorityLayer';
    section.className='os-priority-layer';
    section.setAttribute('aria-labelledby','priorityTitle');
    section.innerHTML=`
      <div class="os-priority-head">
        <div><span class="os-priority-kicker">HOJE</span><h2 id="priorityTitle">O que precisa da sua atenção</h2><p>Comece pelo que pode impactar o acompanhamento dos seus pacientes.</p></div>
        <a href="/app/clinica">Abrir central clínica →</a>
      </div>
      <div class="os-priority-grid">
        <a class="os-priority-card attention" href="/app/clinica"><span>Alertas clínicos</span><strong id="priorityAlerts">—</strong><small>Revisar prioridades</small></a>
        <a class="os-priority-card" href="/app/gestao"><span>Consultas próximas</span><strong id="priorityAppointments">—</strong><small>Ver agenda</small></a>
        <a class="os-priority-card" href="/app/clinica"><span>Sem check-in recente</span><strong id="priorityMissing">—</strong><small>Ver acompanhamento</small></a>
        <a class="os-priority-card" href="/app/conversas"><span>Conversas</span><strong>↗</strong><small>Abrir atendimento</small></a>
      </div>
      <div class="os-priority-error" id="priorityError" role="status" aria-live="polite" hidden><span></span><button type="button">Tentar novamente</button></div>`;
    heading.insertAdjacentElement('afterend',section);
    section.insertAdjacentElement('afterend',metrics);
    refreshPriority();
  }
  async function refreshPriority(){
    const box=document.getElementById('priorityError');
    if(box)box.hidden=true;
    try{
      const r=await fetch('/app/api/dashboard-clinico',{credentials:'same-origin',cache:'no-store'});
      if(r.status===401){location.assign('/login');return}
      if(!r.ok)throw new Error(r.status===403?'Seu acesso não permite abrir os indicadores clínicos.':`Não foi possível atualizar as prioridades (erro ${r.status}).`);
      const d=await r.json(),m=d.metrics||{};
      const a=document.getElementById('priorityAlerts'),p=document.getElementById('priorityAppointments'),c=document.getElementById('priorityMissing');
      if(a)a.textContent=String(m.open_alerts??0).padStart(2,'0');
      if(p)p.textContent=String(m.upcoming_appointments??0).padStart(2,'0');
      if(c)c.textContent=String(m.without_checkin??0).padStart(2,'0');
    }catch(e){
      if(!box)return;
      box.querySelector('span').textContent=esc(e.message||'Não foi possível atualizar as prioridades. Sua sessão continua ativa.');
      box.querySelector('button').onclick=refreshPriority;
      box.hidden=false;
    }
  }
  document.readyState==='loading'?document.addEventListener('DOMContentLoaded',mount,{once:true}):mount();
})();

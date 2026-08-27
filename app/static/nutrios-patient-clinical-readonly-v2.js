(()=>{
  const tabs=document.querySelector('.portal-tabs');
  const docs=document.getElementById('documentsView');
  const home=document.getElementById('homeView');
  if(!tabs||!docs||!home||document.getElementById('patientLabsView'))return;

  const esc=(v)=>String(v??'').replace(/[&<>"']/g,(c)=>({'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;',"'":'&#39;'}[c]));
  const dateBR=(v)=>{if(!v)return'—';const d=new Date(String(v).length===10?`${v}T12:00:00`:v);return Number.isNaN(d.valueOf())?'—':d.toLocaleDateString('pt-BR')};
  const statusLab={low:'Abaixo da referência',normal:'Na referência',high:'Acima da referência',attention:'Atenção'};
  const statusSupp={active:'Ativo',paused:'Pausado',completed:'Concluído',cancelled:'Cancelado'};
  const statusPhyto={active:'Ativa',completed:'Concluída'};

  async function api(url){
    const r=await fetch(url,{credentials:'same-origin',cache:'no-store'});
    if(r.status===401){location='/paciente/login';throw Error('Sessão expirada');}
    const data=await r.json().catch(()=>[]);
    if(!r.ok)throw Error(data.detail||'Não foi possível carregar agora.');
    return data;
  }
  function activate(view){
    document.querySelectorAll('.portal-tabs .tab').forEach(t=>t.classList.toggle('on',t.dataset.view===view));
    document.querySelectorAll('.view').forEach(v=>v.classList.toggle('on',v.id===view));
    document.getElementById(view)?.scrollIntoView({behavior:'smooth',block:'start'});
  }
  function addTab(label,view,before){
    if(tabs.querySelector(`[data-view="${view}"]`))return tabs.querySelector(`[data-view="${view}"]`);
    const b=document.createElement('button');b.className='tab';b.type='button';b.dataset.view=view;b.textContent=label;
    tabs.insertBefore(b,before||null);return b;
  }
  const docsTab=tabs.querySelector('[data-view="documentsView"]');
  const labsTab=addTab('Exames','patientLabsView',docsTab);
  const suppTab=addTab('Suplementação','patientSupplementsView',docsTab);
  const phytoTab=addTab('Fitoterapia','patientPhytoView',docsTab);

  docs.insertAdjacentHTML('beforebegin',`
    <section id="patientLabsView" class="view panel patient-readonly-view">
      <div class="patient-readonly-head"><div><span class="eyebrow">EXAMES LABORATORIAIS</span><h2>Meus exames</h2><p class="muted">Resultados registrados pelo seu nutricionista. A interpretação clínica deve ser feita com o profissional.</p></div><span class="patient-readonly-pill">Somente leitura</span></div>
      <div id="patientLabsSummary" class="patient-readonly-summary"></div><div id="patientLabsList" class="patient-readonly-list"><p class="muted">Carregando...</p></div>
    </section>
    <section id="patientSupplementsView" class="view panel patient-readonly-view">
      <div class="patient-readonly-head"><div><span class="eyebrow">SUPLEMENTAÇÃO</span><h2>Minha suplementação</h2><p class="muted">Dose, frequência, horário e orientações liberadas no seu acompanhamento.</p></div><span class="patient-readonly-pill">Orientação profissional</span></div>
      <div id="patientSupplementsList" class="patient-readonly-list"><p class="muted">Carregando...</p></div>
    </section>
    <section id="patientPhytoView" class="view panel patient-readonly-view">
      <div class="patient-readonly-head"><div><span class="eyebrow">FITOTERAPIA E RECEITUÁRIO</span><h2>Minhas prescrições</h2><p class="muted">Prescrições ativas ou concluídas disponibilizadas pelo seu nutricionista.</p></div><span class="patient-readonly-pill">Somente leitura</span></div>
      <div id="patientPhytoList" class="patient-readonly-list"><p class="muted">Carregando...</p></div>
    </section>`);

  const grid=home.querySelector('.patient-home-grid');
  if(grid&&!grid.querySelector('[data-patient-clinical="labs"]'))grid.insertAdjacentHTML('beforeend',`
    <button class="patient-action" type="button" data-patient-clinical="labs"><span class="action-icon">⌬</span><b>Exames</b><small>Consulte seus resultados laboratoriais registrados.</small></button>
    <button class="patient-action" type="button" data-patient-clinical="supp"><span class="action-icon">✦</span><b>Suplementação</b><small>Veja doses, horários e orientações em uso.</small></button>
    <button class="patient-action" type="button" data-patient-clinical="phyto"><span class="action-icon">❧</span><b>Fitoterapia</b><small>Acesse prescrições e fórmulas liberadas.</small></button>`);

  let labsLoaded=false,suppLoaded=false,phytoLoaded=false;
  function labReference(x){
    if(x.reference_text)return esc(x.reference_text);
    const min=x.reference_min,max=x.reference_max,unit=esc(x.unit||'');
    if(min!=null&&max!=null)return `${esc(min)}–${esc(max)} ${unit}`;
    if(min!=null)return `≥ ${esc(min)} ${unit}`;
    if(max!=null)return `≤ ${esc(max)} ${unit}`;
    return 'Referência não informada';
  }
  async function loadLabs(){
    const list=document.getElementById('patientLabsList'),summary=document.getElementById('patientLabsSummary');
    try{
      const rows=await api('/paciente/api/exames');labsLoaded=true;
      const abnormal=rows.filter(x=>['low','high','attention'].includes(x.status)).length;
      const names=new Set(rows.map(x=>String(x.exam_name||'').trim().toLowerCase()).filter(Boolean));
      const last=rows.map(x=>x.collected_at).filter(Boolean).sort().reverse()[0];
      summary.innerHTML=`<article><span>Resultados</span><b>${rows.length}</b></article><article><span>Biomarcadores</span><b>${names.size}</b></article><article><span>Fora da referência</span><b>${abnormal}</b></article><article><span>Última coleta</span><b>${esc(dateBR(last))}</b></article>`;
      list.innerHTML=rows.length?rows.map(x=>`<article class="patient-readonly-card"><div class="patient-readonly-card-top"><div><small>${esc(x.category||'Laboratorial')} · ${esc(dateBR(x.collected_at))}</small><h3>${esc(x.exam_name)}</h3></div><span class="patient-clinical-status ${esc(x.status||'normal')}">${esc(statusLab[x.status]||x.status||'Resultado')}</span></div><div class="patient-readonly-value">${esc(x.value_numeric??x.value_text??'—')} <small>${esc(x.unit||'')}</small></div><div class="patient-readonly-meta"><span>Referência: ${labReference(x)}</span></div></article>`).join(''):'<div class="patient-readonly-empty"><b>Nenhum exame disponível.</b><p>Quando seu nutricionista registrar resultados laboratoriais, eles aparecerão aqui.</p></div>';
    }catch(e){list.innerHTML=`<div class="patient-readonly-empty"><b>Não foi possível carregar.</b><p>${esc(e.message)}</p></div>`;}
  }
  async function loadSupplements(){
    const list=document.getElementById('patientSupplementsList');
    try{
      const rows=await api('/paciente/api/suplementos');suppLoaded=true;
      list.innerHTML=rows.length?rows.map(x=>`<article class="patient-readonly-card"><div class="patient-readonly-card-top"><div><small>${esc(x.route||'Uso orientado')}</small><h3>${esc(x.name)}</h3></div><span class="patient-clinical-status ${esc(x.status||'active')}">${esc(statusSupp[x.status]||x.status)}</span></div><div class="patient-readonly-lines">${x.dose?`<p><b>Dose</b><span>${esc(x.dose)}</span></p>`:''}${x.frequency?`<p><b>Frequência</b><span>${esc(x.frequency)}</span></p>`:''}${x.schedule?`<p><b>Horário</b><span>${esc(x.schedule)}</span></p>`:''}${x.objective?`<p><b>Objetivo</b><span>${esc(x.objective)}</span></p>`:''}${x.instructions?`<p class="full"><b>Orientações</b><span>${esc(x.instructions)}</span></p>`:''}</div>${x.starts_at||x.ends_at?`<div class="patient-readonly-meta"><span>${x.starts_at?`Início: ${esc(dateBR(x.starts_at))}`:''}${x.starts_at&&x.ends_at?' · ':''}${x.ends_at?`Até: ${esc(dateBR(x.ends_at))}`:''}</span></div>`:''}</article>`).join(''):'<div class="patient-readonly-empty"><b>Nenhuma suplementação ativa.</b><p>As orientações liberadas pelo seu nutricionista aparecerão aqui.</p></div>';
    }catch(e){list.innerHTML=`<div class="patient-readonly-empty"><b>Não foi possível carregar.</b><p>${esc(e.message)}</p></div>`;}
  }
  async function loadPhyto(){
    const list=document.getElementById('patientPhytoList');
    try{
      const rows=await api('/paciente/api/fitoterapia');phytoLoaded=true;
      list.innerHTML=rows.length?rows.map(x=>`<article class="patient-readonly-card"><div class="patient-readonly-card-top"><div><small>${x.prescription_type==='formula'?'Fórmula':'Fitoterapia'}${x.pharmaceutical_form?` · ${esc(x.pharmaceutical_form)}`:''}</small><h3>${esc(x.title)}</h3></div><span class="patient-clinical-status ${esc(x.status)}">${esc(statusPhyto[x.status]||x.status)}</span></div>${Array.isArray(x.items)&&x.items.length?`<div class="patient-phyto-items">${x.items.map(i=>`<div><b>${esc(i.active_name)}</b><span>${esc([i.concentration,i.dose].filter(Boolean).join(' · ')||'Conforme prescrição')}</span>${i.notes?`<small>${esc(i.notes)}</small>`:''}</div>`).join('')}</div>`:''}<div class="patient-readonly-lines">${x.quantity?`<p><b>Quantidade</b><span>${esc(x.quantity)}</span></p>`:''}${x.duration_text?`<p><b>Duração</b><span>${esc(x.duration_text)}</span></p>`:''}${x.usage_instructions?`<p class="full"><b>Modo de uso</b><span>${esc(x.usage_instructions)}</span></p>`:''}${x.patient_notes?`<p class="full"><b>Observações para você</b><span>${esc(x.patient_notes)}</span></p>`:''}</div>${x.starts_at||x.ends_at?`<div class="patient-readonly-meta"><span>${x.starts_at?`Início: ${esc(dateBR(x.starts_at))}`:''}${x.starts_at&&x.ends_at?' · ':''}${x.ends_at?`Até: ${esc(dateBR(x.ends_at))}`:''}</span></div>`:''}</article>`).join(''):'<div class="patient-readonly-empty"><b>Nenhuma prescrição disponível.</b><p>Prescrições ativas ou concluídas aparecerão aqui quando forem liberadas.</p></div>';
    }catch(e){list.innerHTML=`<div class="patient-readonly-empty"><b>Não foi possível carregar.</b><p>${esc(e.message)}</p></div>`;}
  }

  labsTab.addEventListener('click',()=>{activate('patientLabsView');if(!labsLoaded)loadLabs();});
  suppTab.addEventListener('click',()=>{activate('patientSupplementsView');if(!suppLoaded)loadSupplements();});
  phytoTab.addEventListener('click',()=>{activate('patientPhytoView');if(!phytoLoaded)loadPhyto();});
  home.querySelector('[data-patient-clinical="labs"]')?.addEventListener('click',()=>labsTab.click());
  home.querySelector('[data-patient-clinical="supp"]')?.addEventListener('click',()=>suppTab.click());
  home.querySelector('[data-patient-clinical="phyto"]')?.addEventListener('click',()=>phytoTab.click());

  if(!document.getElementById('patientReadonlyV2Styles')){
    const style=document.createElement('style');style.id='patientReadonlyV2Styles';style.textContent=`
      .patient-readonly-head{display:flex;align-items:flex-start;justify-content:space-between;gap:18px;margin-bottom:20px}.patient-readonly-pill{flex:0 0 auto;padding:7px 10px;border:1px solid var(--patient-line);border-radius:999px;background:var(--patient-brand-soft);color:var(--patient-brand);font-size:10px;font-weight:800}.patient-readonly-summary{display:grid;grid-template-columns:repeat(4,minmax(0,1fr));gap:10px;margin:0 0 16px}.patient-readonly-summary article{padding:14px;border:1px solid var(--patient-line);border-radius:14px;background:var(--patient-surface-soft)}.patient-readonly-summary span{display:block;color:var(--patient-muted);font-size:10px;text-transform:uppercase;letter-spacing:.06em}.patient-readonly-summary b{display:block;margin-top:6px;font-size:18px;color:var(--patient-ink)}.patient-readonly-list{display:grid;gap:12px}.patient-readonly-card{padding:17px;border:1px solid var(--patient-line);border-radius:16px;background:#fff}.patient-readonly-card-top{display:flex;align-items:flex-start;justify-content:space-between;gap:14px}.patient-readonly-card h3{margin:3px 0 0!important;font-size:15px!important}.patient-readonly-card small{color:var(--patient-muted)}.patient-clinical-status{padding:6px 9px;border-radius:999px;background:#eef5ef;color:#52715b;font-size:10px;font-weight:800}.patient-clinical-status.low,.patient-clinical-status.high,.patient-clinical-status.attention{background:#fff4e9;color:#a85b16}.patient-clinical-status.active{background:var(--patient-brand-soft);color:var(--patient-brand)}.patient-clinical-status.paused{background:#fff6dc;color:#8c6711}.patient-clinical-status.completed{background:#f0f3f1;color:#657269}.patient-readonly-value{margin:14px 0 10px;font-size:24px;font-weight:760;letter-spacing:-.03em}.patient-readonly-value small{font-size:12px;font-weight:600}.patient-readonly-meta{padding-top:10px;border-top:1px solid #edf1ee;color:var(--patient-muted);font-size:10px}.patient-readonly-lines{display:grid;grid-template-columns:1fr 1fr;gap:8px 18px;margin-top:14px}.patient-readonly-lines p{display:flex;flex-direction:column;gap:3px;margin:0!important}.patient-readonly-lines p.full{grid-column:1/-1}.patient-readonly-lines b{font-size:10px;text-transform:uppercase;letter-spacing:.05em;color:#7a877f}.patient-readonly-lines span{font-size:12px;color:var(--patient-ink);line-height:1.5}.patient-phyto-items{display:grid;gap:7px;margin-top:14px;padding:12px;border-radius:13px;background:var(--patient-surface-soft)}.patient-phyto-items div{display:flex;flex-wrap:wrap;gap:4px 9px;align-items:baseline}.patient-phyto-items b{font-size:12px}.patient-phyto-items span,.patient-phyto-items small{font-size:10px;color:var(--patient-muted)}.patient-readonly-empty{padding:26px 10px;text-align:center;color:var(--patient-muted)}.patient-readonly-empty b{display:block;color:var(--patient-ink);font-size:13px}.patient-readonly-empty p{margin:5px auto 0;max-width:440px;font-size:11px}.patient-home-grid{grid-template-columns:repeat(3,minmax(0,1fr))!important}@media(max-width:900px){.patient-readonly-summary{grid-template-columns:repeat(2,1fr)}}@media(max-width:760px){.patient-readonly-head{display:block}.patient-readonly-pill{display:inline-block;margin-top:10px}.patient-readonly-summary{grid-template-columns:1fr 1fr}.patient-readonly-lines{grid-template-columns:1fr}.patient-home-grid{grid-template-columns:1fr!important}}`;
    document.head.appendChild(style);
  }
})();

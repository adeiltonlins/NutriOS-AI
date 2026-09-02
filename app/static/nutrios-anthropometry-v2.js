(()=>{
  const path=location.pathname.replace(/\/$/,'')||'/';
  const match=path.match(/^\/app\/pacientes\/([^/]+)/);if(!match)return;
  const patientId=decodeURIComponent(match[1]);
  const esc=v=>String(v??'').replace(/[&<>"']/g,c=>({'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;',"'":'&#39;'}[c]));
  const api=async(url,opt={})=>{const r=await fetch(url,{credentials:'same-origin',cache:'no-store',...opt});if(r.status===401){location.href='/login';throw new Error('Sessão expirada')}const data=await r.json().catch(()=>({}));if(!r.ok)throw new Error(data.detail||'Não foi possível concluir');return data};
  const numberMap=(form,names)=>Object.fromEntries(names.map(n=>[n,form.elements[n]?.value]).filter(([,v])=>v!==''&&v!==undefined).map(([k,v])=>[k,Number(v)]));
  const foldDefs=[['chest','Peitoral'],['midaxillary','Axilar média'],['triceps','Tríceps'],['subscapular','Subescapular'],['abdomen','Abdominal'],['suprailiac','Suprailíaca'],['thigh','Coxa'],['calf','Panturrilha medial']];
  let protocols=[];

  function ageText(info,sex){
    const range=info?.age_range?.[sex];
    if(range)return `${range[0]} a ${range[1]} anos`;
    if(info?.age_range)return 'Selecione o sexo para ver a faixa aplicável';
    return 'Sem faixa automática';
  }

  function renderProtocolInfo(){
    const form=document.getElementById('advancedAnthroForm'),host=document.getElementById('anthroProtocolInfo');if(!form||!host)return;
    const info=protocols.find(x=>x.key===form.protocol.value);if(!info)return;
    const sex=form.sex.value||'';
    const required=sex?(info.required_labels_by_sex?.[sex]||[]):[];
    const extra=sex?(info.required_fields_by_sex?.[sex]||[]):[];
    const extras=extra.map(x=>({age:'Idade',weight_kg:'Peso',height_cm:'Altura'}[x]||x));
    host.innerHTML=`<div class="protocol-card-head"><div><span class="protocol-kicker">PROTOCOLO SELECIONADO</span><h4>${esc(info.label)}</h4></div><span class="protocol-auto ${info.automatic?'on':'off'}">${info.automatic?'Cálculo automático':'Registro manual'}</span></div><div class="protocol-meta"><div><small>Indicação</small><p>${esc(info.indication)}</p></div><div><small>Sexo</small><p>${esc(info.sex)}</p></div><div><small>Faixa etária</small><p>${esc(ageText(info,sex))}</p></div><div><small>Medidas necessárias</small><p>${required.length?esc(required.join(' · ')):(info.automatic?'Selecione o sexo para listar as dobras':'Conforme o método utilizado')}</p>${extras.length?`<em>Também exige: ${esc(extras.join(', '))}</em>`:''}</div></div><details class="protocol-formula"><summary>Ver método de cálculo</summary><p>${esc(info.formula)}</p></details>`;
    updateFoldVisibility(info,sex);
    updateRequiredFields(info,sex);
  }

  function updateFoldVisibility(info,sex){
    const form=document.getElementById('advancedAnthroForm');if(!form)return;
    const required=sex?(info.required_by_sex?.[sex]||[]):[];
    foldDefs.forEach(([name])=>{
      const input=form.elements[name],label=input?.closest('label');if(!input||!label)return;
      const isRequired=required.includes(name);
      label.classList.toggle('protocol-required',isRequired);
      label.classList.toggle('protocol-unused',info.automatic&&!!sex&&!isRequired);
      input.required=!!(info.automatic&&sex&&isRequired);
      if(info.automatic&&sex&&!isRequired)input.value='';
    });
  }

  function updateRequiredFields(info,sex){
    const form=document.getElementById('advancedAnthroForm');if(!form)return;
    ['age','weight_kg','height_cm'].forEach(name=>{
      const el=form.elements[name];if(!el)return;
      const req=!!(sex&&info.required_fields_by_sex?.[sex]?.includes(name));
      el.required=req;
      el.closest('label')?.classList.toggle('protocol-required',req);
    });
  }

  async function mount(){
    const tabs=document.querySelector('.record-tabs'),content=document.querySelector('.record-content');if(!tabs||!content||document.getElementById('advancedAnthro'))return;
    try{protocols=await api('/app/api/antropometria/protocolos')}catch(_){protocols=[]}
    const options=(protocols.length?protocols:[
      {key:'manual',label:'Avaliação manual / outro método'},{key:'pollock3',label:'Jackson & Pollock — 3 dobras'},{key:'pollock7',label:'Jackson & Pollock — 7 dobras'},{key:'petroski',label:'Petroski — 4 dobras'}
    ]).map(x=>`<option value="${esc(x.key)}">${esc(x.label)}</option>`).join('');
    tabs.insertAdjacentHTML('beforeend','<button class="tab" data-v="advancedAnthro"><span>◎</span>Antropometria</button>');
    content.insertAdjacentHTML('beforeend',`<section id="advancedAnthro" class="view"><div class="section-heading"><div><span class="eyebrow">ANTROPOMETRIA</span><h2>Avaliação por protocolo</h2><p>Escolha primeiro o protocolo. O NutriOS informa o perfil indicado, as medidas obrigatórias e a fórmula antes de calcular.</p></div></div><div class="advanced-anthro-grid"><article class="panel"><form id="advancedAnthroForm" class="advanced-form"><div class="advanced-block protocol-selector"><h3>1. Escolha o protocolo de avaliação</h3><div class="advanced-fields"><label>Data<input name="assessed_at" type="date"></label><label class="protocol-select-wide">Protocolo<select name="protocol">${options}</select></label><label>Sexo<select name="sex"><option value="">Selecione</option><option value="male">Masculino</option><option value="female">Feminino</option></select></label><label>Idade<input name="age" type="number" min="12" max="120"></label></div><div id="anthroProtocolInfo" class="protocol-info"></div></div><div class="advanced-block"><div class="block-step"><span>2</span><div><h3>Medidas corporais</h3><p>As dobras obrigatórias do protocolo ficam destacadas; as não utilizadas ficam recolhidas visualmente.</p></div></div><div class="advanced-fields"><label>Peso (kg)<input name="weight_kg" type="number" min="20" max="500" step=".1"></label><label>Altura (cm)<input name="height_cm" type="number" min="80" max="250" step=".1"></label><label>Cintura (cm)<input name="waist_cm" type="number" min="20" max="300" step=".1"></label><label>Quadril (cm)<input name="hip_cm" type="number" min="20" max="300" step=".1"></label></div><h4 class="subsection-title">Dobras cutâneas (mm)</h4><div class="advanced-fields compact anthro-folds">${foldDefs.map(([n,l])=>`<label data-fold="${n}">${l}<input name="${n}" type="number" min="0" max="100" step=".1"></label>`).join('')}</div></div><div class="advanced-block"><div class="block-step"><span>3</span><div><h3>Circunferências e postura</h3><p>Dados complementares para acompanhar evolução; não alteram a fórmula do protocolo selecionado.</p></div></div><div class="advanced-fields compact">${[['neck','Pescoço'],['chest_c','Tórax'],['abdomen_c','Abdômen'],['arm_right','Braço D'],['arm_left','Braço E'],['thigh_right','Coxa D'],['thigh_left','Coxa E'],['calf_right','Panturrilha D'],['calf_left','Panturrilha E']].map(([n,l])=>`<label>${l}<input name="${n}" type="number" min="0" max="300" step=".1"></label>`).join('')}</div><h4 class="subsection-title">Avaliação postural</h4><div class="advanced-fields"><label>Cabeça<input name="posture_head" placeholder="Ex.: alinhada"></label><label>Ombros<input name="posture_shoulders" placeholder="Ex.: assimetria leve"></label><label>Coluna<input name="posture_spine"></label><label>Pelve<input name="posture_pelvis"></label><label>Joelhos<input name="posture_knees"></label><label>Pés<input name="posture_feet"></label></div><label>Observações<textarea name="notes" placeholder="Condições da avaliação e interpretação profissional"></textarea></label></div><button class="primary" type="submit">Salvar avaliação antropométrica</button><p id="advancedAnthroStatus" role="status"></p></form></article><article class="panel"><div class="panel-title"><div><span class="panel-icon">↗</span><div><h3>Histórico de avaliações</h3><p>O protocolo fica registrado pelo nome completo, sem misturar métodos.</p></div></div></div><div id="advancedAnthroList"><div class="empty-state">Carregando avaliações…</div></div></article></div></section>`);
    const tab=tabs.querySelector('[data-v="advancedAnthro"]');tab.addEventListener('click',()=>{tabs.querySelectorAll('.tab').forEach(x=>x.classList.toggle('on',x===tab));content.querySelectorAll(':scope>.view').forEach(v=>v.classList.toggle('on',v.id==='advancedAnthro'));load()});
    const form=document.getElementById('advancedAnthroForm');
    form.addEventListener('submit',save);
    form.protocol.addEventListener('change',renderProtocolInfo);
    form.sex.addEventListener('change',renderProtocolInfo);
    renderProtocolInfo();
  }

  async function save(e){e.preventDefault();const f=e.currentTarget,status=document.getElementById('advancedAnthroStatus');status.textContent='Validando protocolo e salvando…';
    const skinfolds=numberMap(f,foldDefs.map(x=>x[0]));
    const circumferences=numberMap(f,['neck','arm_right','arm_left','thigh_right','thigh_left','calf_right','calf_left']);if(f.chest_c.value)circumferences.chest=Number(f.chest_c.value);if(f.abdomen_c.value)circumferences.abdomen=Number(f.abdomen_c.value);
    const posture={};[['head','posture_head'],['shoulders','posture_shoulders'],['spine','posture_spine'],['pelvis','posture_pelvis'],['knees','posture_knees'],['feet','posture_feet']].forEach(([k,n])=>{const v=f.elements[n].value.trim();if(v)posture[k]=v});
    const payload={protocol:f.protocol.value,skinfolds,circumferences,posture};['assessed_at','sex','notes'].forEach(k=>{if(f.elements[k].value)payload[k]=f.elements[k].value});['age','weight_kg','height_cm','waist_cm','hip_cm'].forEach(k=>{if(f.elements[k].value!=='')payload[k]=Number(f.elements[k].value)});
    try{const result=await api(`/app/api/pacientes/${encodeURIComponent(patientId)}/antropometria-avancada`,{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify(payload)});status.textContent=`Avaliação salva — ${result.advanced?.protocol_label||'protocolo registrado'}.`;f.reset();renderProtocolInfo();await load()}catch(err){status.textContent=err.message}}

  async function load(){const host=document.getElementById('advancedAnthroList');if(!host)return;try{const rows=await api(`/app/api/pacientes/${encodeURIComponent(patientId)}/antropometria-avancada`);host.innerHTML=rows.length?rows.map(r=>`<article class="advanced-history"><div><div class="advanced-history-head"><div><small class="history-protocol-label">PROTOCOLO</small><strong>${esc(r.protocol_label||r.protocol||'Avaliação manual')}</strong></div><span>${r.created_at?new Date(r.created_at).toLocaleDateString('pt-BR'):'—'}</span></div><div class="advanced-kpis"><span><small>Gordura</small><b>${r.calculated_body_fat_percent??'—'}${r.calculated_body_fat_percent!=null?'%':''}</b></span><span><small>Massa gorda</small><b>${r.calculated_fat_mass_kg??'—'}${r.calculated_fat_mass_kg!=null?' kg':''}</b></span><span><small>Massa livre</small><b>${r.calculated_lean_mass_kg??'—'}${r.calculated_lean_mass_kg!=null?' kg':''}</b></span></div></div><button class="button danger-outline" data-del="${esc(r.id)}">Excluir</button></article>`).join(''):'<div class="empty-state"><b>Nenhuma avaliação antropométrica.</b><span>Escolha um protocolo e registre a primeira avaliação.</span></div>';host.querySelectorAll('[data-del]').forEach(b=>b.onclick=async()=>{if(!confirm('Excluir esta avaliação antropométrica?'))return;try{await api(`/app/api/pacientes/${encodeURIComponent(patientId)}/antropometria-avancada/${encodeURIComponent(b.dataset.del)}`,{method:'DELETE'});load()}catch(err){alert(err.message)}})}catch(err){host.innerHTML=`<div class="empty-state"><b>Estrutura de antropometria indisponível.</b><span>${esc(err.message)}. Se a migration 022 ainda não foi executada no Supabase, execute-a primeiro.</span></div>`}}
  document.readyState==='loading'?document.addEventListener('DOMContentLoaded',mount,{once:true}):mount();
})();
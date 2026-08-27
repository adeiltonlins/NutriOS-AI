(()=>{
  const q=(s,r=document)=>r.querySelector(s);
  const qa=(s,r=document)=>[...r.querySelectorAll(s)];
  const num=(v,f=0)=>Number.isFinite(Number(v))?Number(v):f;
  const round=v=>Math.round(v||0);
  const fmt=v=>new Intl.NumberFormat('pt-BR',{maximumFractionDigits:1}).format(v||0);
  const metDb=[
    ['Musculação intensa / hipertrofia',6],['CrossFit / funcional intenso',8.5],['Corrida moderada',9.8],['Corrida intensa / tiros',12.5],['Ciclismo / spinning moderado',7.5],['Natação moderada',8],['Beach tennis / tênis',7.3],['Futebol / futsal recreativo',8],['Pilates / yoga',3.2],['Caminhada rápida',3.8]
  ];
  function formulas(w,h,a,sex,bf){
    const male=sex==='male';
    const mif=(10*w)+(6.25*h)-(5*a)+(male?5:-161);
    const har=male?88.362+13.397*w+4.799*h-5.677*a:447.593+9.247*w+3.098*h-4.33*a;
    const lean=w*(1-(bf/100));
    const cunningham=370+21.6*lean;
    const katch=370+21.6*lean;
    const tinsley=24.8*w+10;
    let oxford;
    if(male){oxford=a<30?14.4*w+313*(h/100)+113:a<60?11.4*w+541*(h/100)-137:11.4*w+541*(h/100)-256;}
    else{oxford=a<30?10.4*w+615*(h/100)-282:a<60?8.18*w+502*(h/100)-11.6:8.52*w+421*(h/100)+10.7;}
    return {mifflin:round(mif),harris:round(har),cunningham:round(cunningham),katch:round(katch),tinsley:round(tinsley),oxford:round(oxford),lean};
  }
  function mountMetabolic(){
    const form=q('#energyForm'); if(!form||q('#zipMetabolicLab'))return;
    const box=document.createElement('section');box.id='zipMetabolicLab';box.className='zip-clinical-lab';
    box.innerHTML=`<div class="zip-lab-head"><div><span class="zip-kicker">CALCULADORA METABÓLICA AVANÇADA</span><h4>Comparador clínico de TMB + METs</h4><p>Visual e raciocínio do ZIP aplicados sobre os dados que o NutriOS já utiliza.</p></div><span class="zip-badge">6 fórmulas + METs</span></div>
      <div class="zip-control-grid"><label>Fórmula de referência<select id="zipFormula"><option value="mifflin">Mifflin-St Jeor</option><option value="harris">Harris-Benedict revisada</option><option value="cunningham">Cunningham</option><option value="katch">Katch-McArdle</option><option value="tinsley">Tinsley</option><option value="oxford">Oxford / Henry & Rees</option></select></label><label>Gordura corporal (%)<input id="zipBodyFat" type="number" min="3" max="70" step=".1" value="20"></label><label>Atividade por MET<select id="zipMet">${metDb.map((m,i)=>`<option value="${m[1]}" ${i===0?'selected':''}>${m[0]} · ${m[1]} MET</option>`).join('')}</select></label><label>Duração do treino (min)<input id="zipMetMinutes" type="number" min="0" max="360" value="60"></label></div>
      <div id="zipFormulaCards" class="zip-formula-grid"></div>
      <div class="zip-target-grid"><article><small>TMB selecionada</small><strong id="zipBmr">—</strong><span>kcal/dia</span></article><article><small>GET estimado</small><strong id="zipTdee">—</strong><span>kcal/dia</span></article><article><small>Treino por MET</small><strong id="zipWorkout">—</strong><span>kcal/sessão</span></article><article><small>Massa magra estimada</small><strong id="zipLean">—</strong><span>kg</span></article></div>
      <p class="zip-safe-note"><b>Importante:</b> o botão “Calcular e salvar metas” abaixo continua usando o endpoint oficial já existente do NutriOS. Este comparador não altera banco nem prescrição automaticamente.</p>`;
    form.parentElement.insertBefore(box,form);
    const controls=[...form.elements,q('#zipFormula'),q('#zipBodyFat'),q('#zipMet'),q('#zipMetMinutes')].filter(Boolean);
    const render=()=>{
      const w=num(form.elements.weight_kg?.value),h=num(form.elements.height_cm?.value),a=num(form.elements.age?.value),sex=form.elements.sex?.value||'female',af=num(form.elements.activity_factor?.value,1.2),bf=num(q('#zipBodyFat').value,20);
      if(!w||!h||!a)return;
      const data=formulas(w,h,a,sex,bf),selected=q('#zipFormula').value,bmr=data[selected]||data.mifflin,tdee=round(bmr*af),workout=round(num(q('#zipMet').value)*w*(num(q('#zipMetMinutes').value)/60));
      const names={mifflin:'Mifflin',harris:'Harris-Benedict',cunningham:'Cunningham',katch:'Katch-McArdle',tinsley:'Tinsley',oxford:'Oxford'};
      q('#zipFormulaCards').innerHTML=Object.entries(names).map(([k,n])=>`<button type="button" class="zip-formula-card ${selected===k?'active':''}" data-formula="${k}"><span>${n}</span><strong>${data[k]}</strong><small>kcal/dia</small></button>`).join('');
      qa('[data-formula]',q('#zipFormulaCards')).forEach(b=>b.onclick=()=>{q('#zipFormula').value=b.dataset.formula;render()});
      q('#zipBmr').textContent=bmr;q('#zipTdee').textContent=tdee;q('#zipWorkout').textContent=workout;q('#zipLean').textContent=fmt(data.lean);
    };
    controls.forEach(el=>{el.addEventListener('input',render);el.addEventListener('change',render)});render();
  }
  function mountAnthropometry(){
    const form=q('#assessmentForm'); if(!form||q('#zipAnthroSummary'))return;
    const panel=document.createElement('section');panel.id='zipAnthroSummary';panel.className='zip-anthro-summary full';
    panel.innerHTML=`<div class="zip-lab-head"><div><span class="zip-kicker">LEITURA ANTROPOMÉTRICA</span><h4>Resumo calculado em tempo real</h4><p>Indicadores derivados apenas dos campos que o NutriOS já armazena hoje.</p></div><span class="zip-badge">sem alterar banco</span></div><div class="zip-target-grid"><article><small>IMC</small><strong id="zipBmi">—</strong><span id="zipBmiLabel">aguardando dados</span></article><article><small>RCQ</small><strong id="zipWhr">—</strong><span>cintura ÷ quadril</span></article><article><small>Massa de gordura</small><strong id="zipFatMass">—</strong><span>kg estimados</span></article><article><small>Massa livre de gordura</small><strong id="zipLeanMass">—</strong><span>kg estimados</span></article></div>`;
    const photos=q('.assessment-photos',form); if(photos) form.insertBefore(panel,photos); else form.appendChild(panel);
    const render=()=>{
      const w=num(form.elements.weight_kg?.value),h=num(form.elements.height_cm?.value),waist=num(form.elements.waist_cm?.value),hip=num(form.elements.hip_cm?.value),bf=num(form.elements.body_fat_percent?.value);
      let bmi=0,label='aguardando dados';if(w&&h){bmi=w/Math.pow(h/100,2);label=bmi<18.5?'Abaixo do peso':bmi<25?'Eutrofia':bmi<30?'Sobrepeso':bmi<35?'Obesidade grau I':bmi<40?'Obesidade grau II':'Obesidade grau III'}
      q('#zipBmi').textContent=bmi?fmt(bmi):'—';q('#zipBmiLabel').textContent=label;
      q('#zipWhr').textContent=waist&&hip?fmt(waist/hip):'—';
      q('#zipFatMass').textContent=w&&bf?fmt(w*bf/100):'—';q('#zipLeanMass').textContent=w&&bf?fmt(w*(1-bf/100)):'—';
    };
    ['weight_kg','height_cm','waist_cm','hip_cm','body_fat_percent'].forEach(n=>{const el=form.elements[n];if(el){el.addEventListener('input',render);el.addEventListener('change',render)}});render();
  }
  function mountMealPlannerPolish(){
    const view=q('#mealplan');if(!view||q('#zipMealPlannerIntro'))return;
    const heading=q('.section-heading',view);if(!heading)return;
    const intro=document.createElement('div');intro.id='zipMealPlannerIntro';intro.className='zip-module-strip';
    intro.innerHTML=`<div><span>✦</span><div><b>Prescrição & Cardápios V2</b><small>Construtor TACO, modelos reutilizáveis, substituições, metas energéticas e publicação no portal — preservando os endpoints atuais.</small></div></div><div class="zip-mini-tags"><span>TACO</span><span>Macros</span><span>Modelos</span><span>PDF</span></div>`;
    heading.insertAdjacentElement('afterend',intro);
  }
  function mountExamNotice(){
    const docs=q('#documents');if(!docs||q('#zipExamRoadmap'))return;
    const heading=q('.section-heading',docs);if(!heading)return;
    const note=document.createElement('div');note.id='zipExamRoadmap';note.className='zip-module-strip zip-roadmap';
    note.innerHTML=`<div><span>🧪</span><div><b>Exames laboratoriais estruturados do ZIP</b><small>Hoje o NutriOS já aceita PDFs de exames. Biomarcadores, faixas de referência, status e análise por IA exigem estrutura própria no banco; por isso essa parte não foi simulada no frontend.</small></div></div>`;
    heading.insertAdjacentElement('afterend',note);
  }
  function mount(){mountMetabolic();mountAnthropometry();mountMealPlannerPolish();mountExamNotice();document.documentElement.dataset.nutriosClinicalV3='zip-clinical-20260827';}
  document.readyState==='loading'?document.addEventListener('DOMContentLoaded',mount,{once:true}):mount();
})();
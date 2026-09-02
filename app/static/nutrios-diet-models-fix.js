(()=>{
  'use strict';
  const norm=v=>String(v??'').normalize('NFD').replace(/[\u0300-\u036f]/g,'').toLowerCase().trim();
  const text=el=>norm(el?.textContent||'');
  const CATEGORY_LABELS={emagrecimento:'Emagrecimento',hipertrofia:'Hipertrofia',manutencao:'Manutenção',vegetariano:'Vegetariano',vegano:'Vegano',diabetes:'Diabetes',hipertensao:'Hipertensão',outros:'Outros'};
  let applying=false,lastKey='',requestSeq=0;

  function installStyles(){
    if(document.getElementById('nutriosDietModelsFixStyle'))return;
    const style=document.createElement('style');style.id='nutriosDietModelsFixStyle';
    style.textContent=`
      .nutrios-model-help{margin:10px 0 14px;padding:12px 14px;border:1px solid #b7dfc7;border-radius:14px;background:#effaf3;color:#24533a;font-size:12px;line-height:1.45}
      .nutrios-model-help b{display:block;color:#087333;font-size:12px;margin-bottom:3px}
      .nutrios-selected-category{display:inline-flex;margin-top:7px;padding:4px 8px;border-radius:999px;background:#fff;border:1px solid #cfe8d8;color:#087333;font-weight:800;font-size:10px}
      .nutrios-model-result{display:none;margin:10px 0 14px;padding:12px 14px;border-radius:14px;background:#087333;color:#fff;font-size:12px;line-height:1.45}
      .nutrios-model-result.show{display:block}
      .nutrios-model-empty{display:none;margin:10px 0;padding:14px;border:1px dashed #cbd5e1;border-radius:14px;background:#f8fafc;color:#64748b;font-size:12px;text-align:center}
      .nutrios-model-empty.show{display:block}
      .nutrios-live-hidden{display:none!important}
      .nutrios-model-destination{animation:nutriosModelFocus 2.6s ease!important;scroll-margin-top:90px}
      @keyframes nutriosModelFocus{0%,100%{box-shadow:inherit}15%,65%{box-shadow:0 0 0 4px rgba(16,185,129,.28),0 18px 45px rgba(16,185,129,.12)}}
    `;document.head.appendChild(style);
  }

  function heading(){return [...document.querySelectorAll('h1,h2,h3,h4,b,strong')].find(el=>text(el)==='modelos de dieta')||null}
  function modelPanel(){const h=heading();if(!h)return null;let n=h.parentElement;for(let i=0;i<7&&n;i++,n=n.parentElement){const t=text(n);if(t.includes('nome do modelo')&&t.includes('aplicar')&&t.includes('arquivar'))return n}return h.closest('section,article,div')}
  function categorySelect(panel){const selects=[...(panel?.querySelectorAll('select')||[])];return selects.find(s=>[...s.options].some(o=>/hipertrof|manutenc|emagrec|veget|vegan|diabet|hipertens|outros/i.test(norm(o.textContent+' '+o.value))))||selects[0]||null}
  function category(select){const raw=norm(select?.value||select?.selectedOptions?.[0]?.textContent);if(raw.includes('emagrec'))return'emagrecimento';if(raw.includes('hipertrof'))return'hipertrofia';if(raw.includes('manut'))return'manutencao';if(raw==='vegetariano'||raw.includes('vegetarian'))return'vegetariano';if(raw.includes('vegan'))return'vegano';if(raw.includes('diabet'))return'diabetes';if(raw.includes('hipertens'))return'hipertensao';return'outros'}

  function modelCards(panel){
    const buttons=[...(panel?.querySelectorAll('button')||[])].filter(b=>text(b)==='aplicar'),cards=[];
    for(const btn of buttons){let n=btn.parentElement;for(let i=0;i<5&&n;i++,n=n.parentElement){const bs=[...n.querySelectorAll('button')].map(text);if(bs.includes('aplicar')&&bs.includes('duplicar')&&bs.includes('arquivar')){cards.push(n);break}}}
    return [...new Set(cards)].filter(c=>!cards.some(o=>o!==c&&c.contains(o)));
  }
  function mealCountFromText(value){const m=String(value||'').match(/(\d+)\s*refei/i);return m?Number(m[1]):0}
  function titleEl(card){return [...card.querySelectorAll('strong,b,h2,h3,h4,p,span')].find(el=>{const v=text(el);return v&&!['aplicar','duplicar','arquivar'].includes(v)&&(/refei|base equilibrada|hipertrof|emagrec|manut|veget|vegan|diabet|hipertens|outros/.test(v))})||null}
  function categoryEl(card){return [...card.querySelectorAll('small,span,p,em')].find(el=>/^(manutencao|manutenção|hipertrofia|emagrecimento|vegetariano|vegano|diabetes|hipertensao|hipertensão|outros)$/.test(text(el)))||null}

  function rememberSlots(cards){cards.forEach((card,index)=>{if(card.dataset.nutriosSlot)return;card.dataset.nutriosSlot=String(index);card.dataset.nutriosMealCount=String(mealCountFromText(card.textContent));const t=titleEl(card),c=categoryEl(card);if(t)card.dataset.nutriosOriginalTitle=t.textContent||'';if(c)card.dataset.nutriosOriginalCategory=c.textContent||''})}

  function ensureUi(panel,select){
    const h=heading();if(!h)return;
    let help=panel.querySelector('.nutrios-model-help');if(!help){help=document.createElement('div');help.className='nutrios-model-help';h.insertAdjacentElement('afterend',help)}
    const cat=category(select),label=CATEGORY_LABELS[cat]||String(select?.selectedOptions?.[0]?.textContent||'Categoria');
    help.innerHTML=`<b>Biblioteca de modelos</b><span>O seletor abaixo filtra a <strong>biblioteca real</strong>. Ao trocar a categoria, os cards também precisam trocar. Os modelos são estruturas para personalização profissional; nada é publicado automaticamente.</span><span class="nutrios-selected-category">Mostrando: ${label}</span>`;
    let result=panel.querySelector('.nutrios-model-result');if(!result){result=document.createElement('div');result.className='nutrios-model-result';help.insertAdjacentElement('afterend',result)}
    let empty=panel.querySelector('.nutrios-model-empty');if(!empty){empty=document.createElement('div');empty.className='nutrios-model-empty';result.insertAdjacentElement('afterend',empty)}
  }

  function result(panel,title,message){const box=panel.querySelector('.nutrios-model-result');if(!box)return;box.innerHTML=`<b>${title}</b><span>${message}</span>`;box.classList.add('show');clearTimeout(box._timer);box._timer=setTimeout(()=>box.classList.remove('show'),6000)}

  function placeModels(panel,models,cat){
    const cards=modelCards(panel);rememberSlots(cards);cards.forEach(c=>{c.classList.add('nutrios-live-hidden');delete c.dataset.nutriosTemplateId;delete c.dataset.nutriosTemplateName});
    const unused=new Set(cards);
    for(const model of models){
      const count=Number(model.meal_count||model.meals?.length||0);
      let card=[...unused].find(c=>Number(c.dataset.nutriosMealCount||0)===count)||[...unused][0];if(!card)break;
      unused.delete(card);card.classList.remove('nutrios-live-hidden');card.dataset.nutriosTemplateId=String(model.id||'');card.dataset.nutriosTemplateName=String(model.name||'Modelo');card.dataset.nutriosLiveCategory=cat;
      const t=titleEl(card);if(t)t.textContent=String(model.name||'Modelo de dieta');
      let c=categoryEl(card);if(!c){const candidates=[...card.querySelectorAll('small,span,p,em')].filter(el=>!el.querySelector('button'));c=candidates.find(el=>text(el)&&!text(el).includes('refei'))||null}
      if(c)c.textContent=CATEGORY_LABELS[cat]||cat;
    }
    const empty=panel.querySelector('.nutrios-model-empty');if(empty){empty.textContent=models.length?'' : `Nenhum modelo ativo encontrado em “${CATEGORY_LABELS[cat]||cat}”.`;empty.classList.toggle('show',models.length===0)}
  }

  async function loadLibrary(panel,select,force=false){
    if(!panel||!select)return;const cat=category(select),key=cat+'|'+modelCards(panel).length;if(!force&&key===lastKey)return;lastKey=key;ensureUi(panel,select);const seq=++requestSeq;
    try{
      const r=await fetch(`/app/api/modelos-dieta-biblioteca?categoria=${encodeURIComponent(cat)}`,{credentials:'same-origin',headers:{Accept:'application/json'}});
      if(!r.ok)throw new Error(`HTTP ${r.status}`);const data=await r.json();if(seq!==requestSeq)return;
      const models=Array.isArray(data?.models)?data.models:[];placeModels(panel,models,cat);
    }catch(err){
      if(seq!==requestSeq)return;modelCards(panel).forEach(c=>c.classList.add('nutrios-live-hidden'));const empty=panel.querySelector('.nutrios-model-empty');if(empty){empty.textContent='Não foi possível carregar a biblioteca de modelos. Atualize a página após o deploy.';empty.classList.add('show')}console.error('[NutriOS modelos]',err);
    }
  }

  function findEditor(panel){const top=panel.getBoundingClientRect().top+scrollY;const h=[...document.querySelectorAll('h1,h2,h3,h4,legend,b,strong')].find(el=>!panel.contains(el)&&/(construtor|montar|editor|refeic|plano alimentar|dieta do paciente|prescricao)/.test(text(el))&&el.getBoundingClientRect().top+scrollY>top+80);return h?.closest('section,article,[class*="card"],[class*="panel"],div')||null}
  function focusEditor(panel){const target=findEditor(panel);if(!target)return;target.classList.add('nutrios-model-destination');target.scrollIntoView({behavior:'smooth',block:'start'});setTimeout(()=>target.classList.remove('nutrios-model-destination'),3000)}

  function wire(panel,select){
    if(select&&!select.dataset.nutriosLiveLibrary){select.dataset.nutriosLiveLibrary='1';select.addEventListener('change',()=>{lastKey='';loadLibrary(panel,select,true)})}
    panel.querySelectorAll('button').forEach(btn=>{if(btn.dataset.nutriosLiveWired)return;const action=text(btn);if(!['aplicar','duplicar','arquivar','salvar'].includes(action))return;btn.dataset.nutriosLiveWired='1';btn.addEventListener('click',()=>{
      if(action==='aplicar'){const card=modelCards(panel).find(c=>c.contains(btn));const name=card?.dataset.nutriosTemplateName||'Modelo';setTimeout(()=>{result(panel,`✓ ${name} aplicado`,'A estrutura foi carregada no editor. Revise e personalize alimentos, quantidades, macros, horários e orientações antes de publicar.');focusEditor(panel)},120)}
      else setTimeout(()=>loadLibrary(panel,select,true),400);
    },true)})
  }

  function applyFix(){if(applying)return;applying=true;try{installStyles();const panel=modelPanel();if(!panel)return;const select=categorySelect(panel);if(!select)return;ensureUi(panel,select);wire(panel,select);loadLibrary(panel,select)}finally{applying=false}}
  const observer=new MutationObserver(()=>requestAnimationFrame(applyFix));
  function init(){applyFix();observer.observe(document.body,{childList:true,subtree:true})}
  document.readyState==='loading'?document.addEventListener('DOMContentLoaded',init,{once:true}):init();
})();

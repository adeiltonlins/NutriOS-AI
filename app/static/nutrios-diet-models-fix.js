(()=>{
  'use strict';
  const norm=v=>String(v??'').normalize('NFD').replace(/[\u0300-\u036f]/g,'').toLowerCase().trim();
  const text=el=>norm(el?.textContent||'');
  let applying=false;

  function installStyles(){
    if(document.getElementById('nutriosDietModelsFixStyle'))return;
    const style=document.createElement('style');
    style.id='nutriosDietModelsFixStyle';
    style.textContent=`
      .nutrios-model-help{margin:10px 0 14px;padding:12px 14px;border:1px solid #b7dfc7;border-radius:14px;background:#effaf3;color:#24533a;font-size:12px;line-height:1.45}
      .nutrios-model-help b{display:block;color:#087333;font-size:12px;margin-bottom:3px}
      .nutrios-model-help .nutrios-selected-category{display:inline-flex;margin-top:7px;padding:4px 8px;border-radius:999px;background:#fff;border:1px solid #cfe8d8;color:#087333;font-weight:800;font-size:10px}
      .nutrios-model-result{display:none;margin:10px 0 14px;padding:12px 14px;border-radius:14px;background:#087333;color:#fff;box-shadow:0 10px 24px rgba(8,115,51,.14);font-size:12px;line-height:1.45}
      .nutrios-model-result.show{display:block;animation:nutriosResultIn .2s ease}
      .nutrios-model-result b{display:block;font-size:13px;margin-bottom:3px}
      .nutrios-model-destination{animation:nutriosModelFocus 2.6s ease!important;scroll-margin-top:90px}
      @keyframes nutriosResultIn{from{opacity:0;transform:translateY(-5px)}to{opacity:1;transform:none}}
      @keyframes nutriosModelFocus{0%,100%{box-shadow:inherit}15%,65%{box-shadow:0 0 0 4px rgba(16,185,129,.28),0 18px 45px rgba(16,185,129,.12)}}
    `;
    document.head.appendChild(style);
  }

  function heading(){
    return [...document.querySelectorAll('h1,h2,h3,h4,b,strong')].find(el=>text(el)==='modelos de dieta')||null;
  }

  function modelPanel(){
    const h=heading();if(!h)return null;
    let node=h.parentElement;
    for(let i=0;i<7&&node;i++,node=node.parentElement){
      const t=text(node);
      if(t.includes('nome do modelo')&&t.includes('aplicar')&&t.includes('arquivar'))return node;
    }
    return h.closest('section,article,div');
  }

  function categorySelect(panel){
    if(!panel)return null;
    const selects=[...panel.querySelectorAll('select')];
    return selects.find(s=>[...s.options].some(o=>/hipertrof|manutenc|emagrec|veget|vegan|gesta|performance/i.test(norm(o.textContent+' '+o.value))))||selects[0]||null;
  }

  function modelCards(panel){
    if(!panel)return [];
    const apply=[...panel.querySelectorAll('button')].filter(b=>text(b)==='aplicar');
    const cards=[];
    for(const btn of apply){
      let node=btn.parentElement;
      for(let i=0;i<5&&node;i++,node=node.parentElement){
        const buttons=[...node.querySelectorAll('button')].map(text);
        if(buttons.includes('aplicar')&&buttons.includes('duplicar')&&buttons.includes('arquivar')){cards.push(node);break;}
      }
    }
    return [...new Set(cards)].filter(c=>!cards.some(other=>other!==c&&c.contains(other)));
  }

  function optionMap(select){
    const list=[...select.options].map((o,i)=>({i,value:norm(o.value),label:norm(o.textContent),display:String(o.textContent||o.value).trim()}));
    return list.filter(x=>x.value||x.label);
  }

  function cardCategory(card,options){
    const raw=text(card);
    const exactLeaves=[...card.querySelectorAll('small,span,p,em')].map(x=>norm(x.textContent));
    for(const op of options){
      if(exactLeaves.some(v=>v===op.value||v===op.label))return op;
    }
    return options.find(op=>(op.value&&raw.includes(op.value))||(op.label&&raw.includes(op.label)))||null;
  }

  function mealCount(card){
    const m=(card.textContent||'').match(/(\d+)\s*refei/i);return m?Number(m[1]):999;
  }

  function modelName(card){
    const els=[...card.querySelectorAll('strong,b,h3,h4')];
    const named=els.find(el=>{const v=text(el);return v&&v!=='aplicar'&&v!=='duplicar'&&v!=='arquivar'&&v!=='modelos de dieta'});
    return String(named?.textContent||'modelo de dieta').trim();
  }

  function ensureHelp(panel,select){
    const h=heading();if(!h)return;
    let help=panel.querySelector('.nutrios-model-help');
    if(!help){
      help=document.createElement('div');help.className='nutrios-model-help';
      const anchor=h.parentElement?.nextSibling;
      h.parentElement?.parentElement?.insertBefore(help,anchor||h.parentElement.nextSibling);
      if(!help.isConnected)h.insertAdjacentElement('afterend',help);
    }
    const selected=String(select?.selectedOptions?.[0]?.textContent||'Todas').trim();
    help.innerHTML=`<b>Como funciona esta biblioteca?</b><span>Os modelos ficam organizados por categoria. Ao clicar em <strong>Aplicar</strong>, o modelo é carregado no editor mais abaixo para o nutricionista ajustar refeições, alimentos, porções e horários. <strong>Nada é publicado automaticamente.</strong></span><span class="nutrios-selected-category">Categoria selecionada: ${selected}</span>`;
    let result=panel.querySelector('.nutrios-model-result');
    if(!result){result=document.createElement('div');result.className='nutrios-model-result';help.insertAdjacentElement('afterend',result)}
  }

  function sortCards(panel,select){
    const cards=modelCards(panel);if(cards.length<2||!select)return;
    const options=optionMap(select),selected=norm(select.value||select.selectedOptions?.[0]?.textContent);
    const parents=new Map();cards.forEach((c,i)=>{const p=c.parentElement;if(!parents.has(p))parents.set(p,[]);parents.get(p).push({card:c,index:i,cat:cardCategory(c,options)})});
    for(const [,items] of parents){
      items.sort((a,b)=>{
        const aSelected=a.cat&&(a.cat.value===selected||a.cat.label===selected),bSelected=b.cat&&(b.cat.value===selected||b.cat.label===selected);
        if(aSelected!==bSelected)return aSelected?-1:1;
        const ar=a.cat?.i??999,br=b.cat?.i??999;if(ar!==br)return ar-br;
        const am=mealCount(a.card),bm=mealCount(b.card);if(am!==bm)return am-bm;
        return modelName(a.card).localeCompare(modelName(b.card),'pt-BR',{numeric:true});
      });
      const parent=items[0]?.card.parentElement;items.forEach(x=>parent?.appendChild(x.card));
    }
  }

  function result(panel,title,message){
    const box=panel.querySelector('.nutrios-model-result');if(!box)return;
    box.innerHTML=`<b>${title}</b><span>${message}</span>`;box.classList.add('show');
    clearTimeout(box._timer);box._timer=setTimeout(()=>box.classList.remove('show'),7000);
  }

  function findEditor(panel){
    const panelTop=panel.getBoundingClientRect().top+scrollY;
    const candidates=[...document.querySelectorAll('h1,h2,h3,h4,legend,b,strong')].filter(el=>{
      if(panel.contains(el))return false;
      const n=text(el);if(!/(construtor|montar|editor|refeic|plano alimentar|dieta do paciente|prescricao)/.test(n))return false;
      return el.getBoundingClientRect().top+scrollY>panelTop+80;
    });
    const h=candidates[0];
    return h?.closest('section,article,[class*="card"],[class*="panel"],div')||panel.nextElementSibling||null;
  }

  function focusEditor(panel){
    const target=findEditor(panel);if(!target)return;
    target.classList.add('nutrios-model-destination');target.scrollIntoView({behavior:'smooth',block:'start'});
    setTimeout(()=>target.classList.remove('nutrios-model-destination'),3000);
  }

  function wire(panel,select){
    if(select&&!select.dataset.nutriosOrderWired){
      select.dataset.nutriosOrderWired='1';
      select.addEventListener('change',()=>{setTimeout(()=>{ensureHelp(panel,select);sortCards(panel,select)},0)});
    }
    panel.querySelectorAll('button').forEach(btn=>{
      const action=text(btn);if(!['aplicar','duplicar','arquivar','salvar'].includes(action)||btn.dataset.nutriosModelWired)return;
      btn.dataset.nutriosModelWired='1';
      btn.addEventListener('click',()=>{
        if(action==='aplicar'){
          const card=modelCards(panel).find(c=>c.contains(btn)),name=card?modelName(card):'Modelo';
          setTimeout(()=>{
            result(panel,`✓ ${name} aplicado`,`O modelo foi carregado no editor abaixo. Personalize alimentos, quantidades, horários e orientações antes de salvar ou publicar.`);
            focusEditor(panel);
          },120);
        }else if(action==='salvar'){
          const category=String(select?.selectedOptions?.[0]?.textContent||'categoria selecionada').trim();
          setTimeout(()=>{sortCards(panel,select);result(panel,'✓ Modelo salvo',`O modelo foi incluído na Biblioteca em “${category}”. Os modelos dessa categoria aparecem primeiro para facilitar a conferência.`)},350);
        }else if(action==='duplicar'){
          setTimeout(()=>{sortCards(panel,select);result(panel,'✓ Modelo duplicado','A cópia foi criada e reposicionada na ordem da categoria correspondente.')},350);
        }else if(action==='arquivar'){
          setTimeout(()=>{sortCards(panel,select);result(panel,'Modelo arquivado','Ele saiu da lista ativa da Biblioteca e pode ser mantido no histórico conforme a regra do sistema.')},350);
        }
      },true);
    });
  }

  function applyFix(){
    if(applying)return;applying=true;
    try{
      installStyles();const panel=modelPanel();if(!panel)return;
      const select=categorySelect(panel);ensureHelp(panel,select);sortCards(panel,select);wire(panel,select);
      panel.dataset.nutriosDietModelsFixed='1';
    }finally{applying=false}
  }

  const observer=new MutationObserver(()=>requestAnimationFrame(applyFix));
  function init(){applyFix();observer.observe(document.body,{childList:true,subtree:true})}
  document.readyState==='loading'?document.addEventListener('DOMContentLoaded',init,{once:true}):init();
})();

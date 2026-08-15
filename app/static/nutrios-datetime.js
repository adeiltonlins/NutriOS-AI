(() => {
  const TYPES = new Set(['date','time','datetime-local','month']);
  const labels = {date:'Abrir calendário',time:'Abrir seletor de horário','datetime-local':'Abrir calendário e horário',month:'Abrir seletor de mês'};
  const icons = {date:'▣',time:'◷','datetime-local':'◷',month:'▣'};
  function enhance(input){
    if(!input || input.dataset.nutriosPicker==='1' || !TYPES.has(input.type)) return;
    input.dataset.nutriosPicker='1';
    input.lang='pt-BR';
    input.autocomplete='off';
    const wrap=document.createElement('span'); wrap.className='nutrios-picker';
    input.parentNode.insertBefore(wrap,input); wrap.appendChild(input);
    const btn=document.createElement('button'); btn.type='button'; btn.className='nutrios-picker-btn'; btn.setAttribute('aria-label',labels[input.type]); btn.title=labels[input.type]; btn.textContent=icons[input.type];
    btn.addEventListener('click',()=>{ try{ if(typeof input.showPicker==='function') input.showPicker(); else {input.focus(); input.click();} }catch{ input.focus(); } });
    wrap.appendChild(btn);
    if(input.closest('label')){
      const hint=document.createElement('small'); hint.className='nutrios-picker-hint';
      hint.textContent=input.type==='date'?'dd/mm/aaaa':input.type==='time'?'24h · hh:mm':input.type==='month'?'mm/aaaa':'dd/mm/aaaa · 24h';
      wrap.insertAdjacentElement('afterend',hint);
    }
  }
  function scan(root=document){ root.querySelectorAll?.('input[type=date],input[type=time],input[type=datetime-local],input[type=month]').forEach(enhance); }
  document.addEventListener('DOMContentLoaded',()=>scan());
  new MutationObserver(ms=>ms.forEach(m=>m.addedNodes.forEach(n=>{ if(n.nodeType===1){ if(n.matches?.('input[type=date],input[type=time],input[type=datetime-local],input[type=month]')) enhance(n); scan(n); } }))).observe(document.documentElement,{childList:true,subtree:true});
  window.NutriOSDateTime={scan,enhance};
})();

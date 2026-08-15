(() => {
  const esc2 = (value) => String(value ?? "").replace(/[&<>"']/g, "");
  const tabs = document.querySelector(".tabs");
  const docsTab = tabs?.querySelector('[data-view="documentsView"]');
  if (!tabs || !docsTab) return;
  docsTab.textContent = "Documentos";
  const planTab = document.createElement("button");
  planTab.className = "tab";
  planTab.dataset.view = "planView";
  planTab.textContent = "Plano alimentar";
  const diaryTab = document.createElement("button");
  diaryTab.className = "tab";
  diaryTab.dataset.view = "diaryView";
  diaryTab.textContent = "Diário alimentar";
  const questionnaireTab = document.createElement("button");
  questionnaireTab.className = "tab";
  questionnaireTab.dataset.view = "questionnaireView";
  questionnaireTab.textContent = "Questionários";
  tabs.insertBefore(planTab, docsTab);
  tabs.insertBefore(diaryTab, docsTab);
  tabs.insertBefore(questionnaireTab, docsTab);
  const anchor = document.querySelector("#documentsView");
  anchor.insertAdjacentHTML("beforebegin", `<section id="questionnaireView" class="view panel patient-questionnaire-shell"><div class="patient-section-head"><div><span class="eyebrow">ACOMPANHAMENTO</span><h2>Questionários e relatos</h2><p class="muted">Os questionários clínicos aparecem aqui quando seu nutricionista liberar. Mesmo sem questionário pendente, você pode enviar um relato livre.</p></div></div><div class="patient-report-card"><h3>Como você está se sentindo?</h3><p class="muted">Envie uma atualização livre para seu nutricionista.</p><form id="patientReportForm"><label>Como está hoje?<input name="mood" placeholder="Ex.: bem, cansado, com muita fome..."></label><label>Conte o que aconteceu<textarea name="text" required placeholder="Descreva sintomas, dificuldades, dúvidas ou qualquer mudança que queira registrar."></textarea></label><button class="save">Enviar relato</button></form><p id="patientReportStatus"></p></div><div class="assigned-questionnaires"><h3>Questionários liberados pelo nutricionista</h3><div id="patientQuestionnaires"></div></div></section><section id="planView" class="view panel"><h2>Meu plano alimentar</h2><div id="mealPlan" class="muted">Carregando...</div></section><section id="diaryView" class="view panel"><h2>Diário alimentar</h2><p class="muted">Registre o que consumiu e como se sentiu.</p><form id="diaryForm" class="check-grid"><label>Refeição<select name="meal_type"><option>Café da manhã</option><option>Almoço</option><option>Lanche</option><option>Jantar</option><option>Ceia</option></select></label><label>Quando<input name="consumed_at" type="datetime-local"></label><label>Fome antes (0–10)<input name="hunger_before" type="number" min="0" max="10"></label><label>Saciedade depois (0–10)<input name="satiety_after" type="number" min="0" max="10"></label><label>Humor<input name="mood"></label><label class="full">O que consumiu<textarea name="description" required></textarea></label><label class="full">Foto opcional<input name="photo" type="file" accept="image/jpeg,image/png,image/webp"></label><label class="full">Sintomas<textarea name="symptoms"></textarea></label><button class="save">Registrar refeição</button></form><p id="diaryStatus"></p><div id="diaryHistory"></div></section>`);
  document.querySelector("#checkinStatus")?.insertAdjacentHTML("afterend", '<div id="checkinHistory"><p class="muted">Carregando histórico...</p></div>');
  document.querySelectorAll(".tab").forEach((tab) => tab.onclick = () => {
    document.querySelectorAll(".tab").forEach((x) => x.classList.toggle("on", x === tab));
    document.querySelectorAll(".view").forEach((x) => x.classList.toggle("on", x.id === tab.dataset.view));
  });
  async function loadClinical() {
    const [planResponse, diaryResponse, questionnairesResponse, checkinsResponse] = await Promise.all([fetch("/paciente/api/plano"), fetch("/paciente/api/diario"), fetch("/paciente/api/questionarios"), fetch("/paciente/api/checkins")]);
    if (!planResponse.ok || !diaryResponse.ok || !questionnairesResponse.ok) return;
    const plan = await planResponse.json(), diary = await diaryResponse.json(), questionnaires = await questionnairesResponse.json();
    const checkins = checkinsResponse.ok ? await checkinsResponse.json() : [];
    mealPlan.innerHTML = plan ? `<div class="doc"><div><h3>${esc2(plan.title)}</h3><p>${esc2(plan.objective || "")}</p></div><a class="download" href="/paciente/api/plano/pdf" target="_blank">Baixar PDF</a></div>${(plan.content || []).map((meal) => `<article class="document"><b>${esc2(meal.time || "")} ${esc2(meal.name)}</b><ul>${meal.items.map((item) => `<li>${esc2(item.name)} — ${item.grams} g${item.substitutions?.length ? `<small> • substituições: ${esc2(item.substitutions.join(", "))}</small>` : ""}</li>`).join("")}</ul></article>`).join("")}<p><b>Total aproximado: ${plan.totals?.kcal || 0} kcal</b></p><p>${esc2(plan.patient_notes || "")}</p>` : '<p class="muted">Seu nutricionista ainda não publicou um plano.</p>';
    diaryHistory.innerHTML = diary.map((entry) => `<article class="document"><b>${esc2(entry.meal_type)} • ${new Date(entry.consumed_at).toLocaleString("pt-BR")}</b><p>${esc2(entry.description)}</p>${entry.photo_storage_path ? '<span class="badge">Foto anexada</span>' : ''}${entry.professional_feedback ? `<p><b>Retorno do nutricionista:</b> ${esc2(entry.professional_feedback)}</p>` : ""}</article>`).join("") || '<p class="muted">Nenhuma refeição registrada.</p>';
    if (window.checkinHistory) checkinHistory.innerHTML = checkins.slice(0, 8).map((entry) => `<article class="document"><div><b>${new Date(entry.created_at).toLocaleDateString("pt-BR")}</b><div class="muted">Fome ${entry.hunger ?? "—"} • Energia ${entry.energy ?? "—"} • Sono ${entry.sleep ?? "—"} • Adesão ${entry.adherence ?? "—"}</div>${entry.symptoms ? `<small class="muted">Sintomas: ${esc2(entry.symptoms)}</small>` : ""}</div><span>✓ Enviado</span></article>`).join("") || '<p class="muted">Você ainda não enviou nenhum check-in.</p>';
    patientQuestionnaires.innerHTML = questionnaires.filter(q=>q.template_key!=='patient_report').map((q) => `<article class="document"><h3>${esc2(q.title)}</h3><p>Status: ${esc2(q.status)}</p>${q.status === 'assigned' ? `<form data-questionnaire="${q.id}">${(q.schema_snapshot||[]).map(f=>`<label>${esc2(f[1])}${f[2]==='scale'?`<input name="${esc2(f[0])}" type="range" min="0" max="10" value="5">`:f[2]==='number'?`<input name="${esc2(f[0])}" type="number">`:f[2]==='boolean'?`<select name="${esc2(f[0])}"><option value="false">Não</option><option value="true">Sim</option></select>`:`<textarea name="${esc2(f[0])}"></textarea>`}</label>`).join('')}<button>Enviar respostas</button></form>`:''}</article>`).join('') || '<div class="empty-state compact"><b>Nenhum questionário liberado no momento.</b><p>Quando o nutricionista atribuir um formulário clínico, ele aparecerá aqui para você responder.</p></div>';
    document.querySelectorAll('[data-questionnaire]').forEach(form=>form.onsubmit=async e=>{e.preventDefault();const answers=Object.fromEntries(new FormData(form));const r=await fetch('/paciente/api/questionarios/'+form.dataset.questionnaire,{method:'PATCH',headers:{'Content-Type':'application/json'},body:JSON.stringify({answers})});if(r.ok)loadClinical();});
  }
  const reportForm=document.querySelector('#patientReportForm');
  if(reportForm) reportForm.onsubmit=async(event)=>{
    event.preventDefault();
    const payload=Object.fromEntries(new FormData(reportForm));
    patientReportStatus.textContent='Enviando...';
    const response=await fetch('/paciente/api/relatos',{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify(payload)});
    if(response.ok){reportForm.reset();patientReportStatus.textContent='Relato enviado ao seu nutricionista.';loadClinical();}
    else{const err=await response.json().catch(()=>({}));patientReportStatus.textContent=err.detail||'Não foi possível enviar agora.';}
  };
  diaryForm.onsubmit = async (event) => {
    event.preventDefault();
    const formData = new FormData(diaryForm), photo = formData.get("photo"), payload = Object.fromEntries(formData);
    delete payload.photo;
    for (const field of ["hunger_before", "satiety_after"]) payload[field] = payload[field] === "" ? null : Number(payload[field]);
    if (!payload.consumed_at) delete payload.consumed_at;
    diaryStatus.textContent = "Salvando...";
    let response;
    if (photo && photo.size) { const upload = new FormData(); upload.set("meal_type", payload.meal_type); upload.set("description", payload.description); if(payload.consumed_at) upload.set("consumed_at", payload.consumed_at); upload.set("file", photo); response = await fetch("/paciente/api/diario/foto", {method:"POST", body:upload}); }
    else response = await fetch("/paciente/api/diario", {method: "POST", headers: {"Content-Type": "application/json"}, body: JSON.stringify(payload)});
    diaryStatus.textContent = response.ok ? "Refeição registrada." : "Não foi possível registrar.";
    if (response.ok) { diaryForm.reset(); loadClinical(); }
  };
  loadClinical();
})();

(() => {
  const tabs = document.querySelector(".tabs");
  const checkinView = document.querySelector("#checkinView");
  if (!tabs || !checkinView) return;
  const esc = (value) => String(value ?? "").replace(/[&<>"']/g, "");
  async function loadWorkout() {
    const response = await fetch("/paciente/api/treino");
    if (!response.ok) return;
    const data = await response.json();
    if (!data.enabled || !data.plan) return;
    const tab = document.createElement("button");
    tab.className = "tab"; tab.dataset.view = "workoutView"; tab.textContent = "Meu treino";
    tabs.insertBefore(tab, tabs.querySelector('[data-view="checkinView"]'));
    checkinView.insertAdjacentHTML("beforebegin", `<section id="workoutView" class="view panel"><h2>${esc(data.plan.title)}</h2><p class="muted">${esc(data.plan.goal || "Ficha de exercícios")}</p><div id="workoutExercises">${(data.plan.exercises || []).map((exercise, index) => `<article class="document"><div><b>${index + 1}. ${esc(exercise.name)}</b><div class="muted">${exercise.sets} séries • ${esc(exercise.reps || "livre")} repetições • carga ${esc(exercise.load || "orientada")} • descanso ${exercise.rest_seconds || 0}s</div><small>${esc(exercise.instructions || "")}</small></div></article>`).join("")}</div><form id="workoutForm" class="check-grid"><h3 class="full">Como você está antes de concluir?</h3><label>Sono (1–5)<input name="sleep" type="number" min="1" max="5" required></label><label>Energia (1–5)<input name="energy" type="number" min="1" max="5" required></label><label>Dor (0–5)<input name="pain" type="number" min="0" max="5" required></label><label>Esforço percebido (1–10)<input name="perceived_exertion" type="number" min="1" max="10" required></label><label class="full">Observações<textarea name="notes"></textarea></label><button class="save">Concluir treino</button></form><p id="workoutStatus"></p></section>`);
    document.querySelectorAll(".tab").forEach((item) => item.onclick = () => {
      document.querySelectorAll(".tab").forEach((x) => x.classList.toggle("on", x === item));
      document.querySelectorAll(".view").forEach((x) => x.classList.toggle("on", x.id === item.dataset.view));
    });
    workoutForm.onsubmit = async (event) => {
      event.preventDefault(); const values = Object.fromEntries(new FormData(workoutForm));
      const payload = {sleep:Number(values.sleep), energy:Number(values.energy), pain:Number(values.pain), perceived_exertion:Number(values.perceived_exertion), notes:values.notes, exercise_results:[]};
      workoutStatus.textContent = "Registrando...";
      const result = await fetch(`/paciente/api/treino/${data.plan.id}/concluir`, {method:"POST", headers:{"Content-Type":"application/json"}, body:JSON.stringify(payload)});
      workoutStatus.textContent = result.ok ? "Treino concluído e enviado ao nutricionista." : "Não foi possível registrar agora.";
      if (result.ok) workoutForm.reset();
    };
  }
  loadWorkout();
})();

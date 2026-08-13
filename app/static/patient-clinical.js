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
  tabs.insertBefore(planTab, docsTab);
  tabs.insertBefore(diaryTab, docsTab);
  const anchor = document.querySelector("#documentsView");
  anchor.insertAdjacentHTML("beforebegin", `<section id="planView" class="view panel"><h2>Meu plano alimentar</h2><div id="mealPlan" class="muted">Carregando...</div></section><section id="diaryView" class="view panel"><h2>Diário alimentar</h2><p class="muted">Registre o que consumiu e como se sentiu.</p><form id="diaryForm" class="check-grid"><label>Refeição<select name="meal_type"><option>Café da manhã</option><option>Almoço</option><option>Lanche</option><option>Jantar</option><option>Ceia</option></select></label><label>Quando<input name="consumed_at" type="datetime-local"></label><label>Fome antes (0–10)<input name="hunger_before" type="number" min="0" max="10"></label><label>Saciedade depois (0–10)<input name="satiety_after" type="number" min="0" max="10"></label><label>Humor<input name="mood"></label><label class="full">O que consumiu<textarea name="description" required></textarea></label><label class="full">Sintomas<textarea name="symptoms"></textarea></label><button class="save">Registrar refeição</button></form><p id="diaryStatus"></p><div id="diaryHistory"></div></section>`);
  document.querySelectorAll(".tab").forEach((tab) => tab.onclick = () => {
    document.querySelectorAll(".tab").forEach((x) => x.classList.toggle("on", x === tab));
    document.querySelectorAll(".view").forEach((x) => x.classList.toggle("on", x.id === tab.dataset.view));
  });
  async function loadClinical() {
    const [planResponse, diaryResponse] = await Promise.all([fetch("/paciente/api/plano"), fetch("/paciente/api/diario")]);
    if (!planResponse.ok || !diaryResponse.ok) return;
    const plan = await planResponse.json(), diary = await diaryResponse.json();
    mealPlan.innerHTML = plan ? `<div class="doc"><div><h3>${esc2(plan.title)}</h3><p>${esc2(plan.objective || "")}</p></div><a class="download" href="/paciente/api/plano/pdf" target="_blank">Baixar PDF</a></div>${(plan.content || []).map((meal) => `<article class="document"><b>${esc2(meal.time || "")} ${esc2(meal.name)}</b><ul>${meal.items.map((item) => `<li>${esc2(item.name)} — ${item.grams} g${item.substitutions?.length ? `<small> • substituições: ${esc2(item.substitutions.join(", "))}</small>` : ""}</li>`).join("")}</ul></article>`).join("")}<p><b>Total aproximado: ${plan.totals?.kcal || 0} kcal</b></p><p>${esc2(plan.patient_notes || "")}</p>` : '<p class="muted">Seu nutricionista ainda não publicou um plano.</p>';
    diaryHistory.innerHTML = diary.map((entry) => `<article class="document"><b>${esc2(entry.meal_type)} • ${new Date(entry.consumed_at).toLocaleString("pt-BR")}</b><p>${esc2(entry.description)}</p>${entry.professional_feedback ? `<p><b>Retorno do nutricionista:</b> ${esc2(entry.professional_feedback)}</p>` : ""}</article>`).join("") || '<p class="muted">Nenhuma refeição registrada.</p>';
  }
  diaryForm.onsubmit = async (event) => {
    event.preventDefault();
    const payload = Object.fromEntries(new FormData(diaryForm));
    for (const field of ["hunger_before", "satiety_after"]) payload[field] = payload[field] === "" ? null : Number(payload[field]);
    if (!payload.consumed_at) delete payload.consumed_at;
    diaryStatus.textContent = "Salvando...";
    const response = await fetch("/paciente/api/diario", {method: "POST", headers: {"Content-Type": "application/json"}, body: JSON.stringify(payload)});
    diaryStatus.textContent = response.ok ? "Refeição registrada." : "Não foi possível registrar.";
    if (response.ok) { diaryForm.reset(); loadClinical(); }
  };
  loadClinical();
})();

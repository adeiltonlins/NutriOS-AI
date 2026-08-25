(() => {
  'use strict';

  const ESCAPE_MAP = {'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;',"'":'&#39;'};
  const esc = value => String(value ?? '').replace(/[&<>"']/g, ch => ESCAPE_MAP[ch]);
  const qs = target => typeof target === 'string' ? document.querySelector(target) : target;
  const hasPositive = values => values.some(value => Number(value) > 0);
  const compactMoney = value => new Intl.NumberFormat('pt-BR', {
    style: 'currency', currency: 'BRL', notation: 'compact', maximumFractionDigits: 1
  }).format(Number(value || 0));
  const monthLabel = month => {
    const [year, number] = String(month).split('-');
    return new Intl.DateTimeFormat('pt-BR', {month: 'short'})
      .format(new Date(Number(year), Number(number) - 1, 1)).replace('.', '');
  };
  const empty = message => `<div class="os-chart-empty"><strong>Ainda sem dados suficientes</strong><span>${esc(message)}</span></div>`;

  function lineChart(target, series, opts = {}) {
    const el = qs(target);
    if (!el) return;
    const values = series.flatMap(item => item.values.filter(value => value !== null && value !== undefined).map(Number));
    if (!values.length || !hasPositive(values.map(Math.abs))) {
      el.innerHTML = empty(opts.empty || 'Os dados aparecerão conforme você usar o NutriOS.');
      return;
    }
    const W = 760, H = 250, p = {l: 42, r: 18, t: 20, b: 38};
    const min = opts.min ?? 0, max = Math.max(opts.max ?? 0, ...values, 1);
    const x = index => p.l + (index * (W - p.l - p.r) / Math.max(1, series[0].values.length - 1));
    const y = value => p.t + (max - Number(value || 0)) * (H - p.t - p.b) / Math.max(1, max - min);
    const grid = [0, .25, .5, .75, 1].map(k => {
      const yy = p.t + k * (H - p.t - p.b), value = max * (1 - k);
      return `<line x1="${p.l}" y1="${yy}" x2="${W-p.r}" y2="${yy}" class="grid"/><text x="${p.l-8}" y="${yy+4}" text-anchor="end" class="axis-y">${opts.money ? compactMoney(value) : Math.round(value)}</text>`;
    }).join('');
    const labels = series[0].labels.map((label, index) => `<text x="${x(index)}" y="${H-12}" text-anchor="middle" class="axis-x${index % 2 ? ' axis-x-alt' : ''}">${esc(monthLabel(label))}</text>`).join('');
    const paths = series.map((item, seriesIndex) => {
      const points = item.values.map((value, index) => `${x(index)},${y(value ?? 0)}`).join(' ');
      const dots = item.values.map((value, index) => `<circle cx="${x(index)}" cy="${y(value ?? 0)}" r="3.2" class="series-dot s${seriesIndex}"/>`).join('');
      return `<polyline points="${points}" class="series-line s${seriesIndex}"/>${dots}`;
    }).join('');
    el.innerHTML = `<svg class="os-chart-svg" viewBox="0 0 ${W} ${H}" role="img" aria-label="${esc(opts.label || 'Gráfico')}">${grid}${paths}${labels}</svg>`;
  }

  function barChart(target, labels, values, opts = {}) {
    const el = qs(target);
    if (!el) return;
    if (!values.length || !hasPositive(values)) {
      el.innerHTML = empty(opts.empty || 'Nenhum registro no período.');
      return;
    }
    const W = 760, H = 220, p = {l: 28, r: 16, t: 16, b: 38};
    const max = Math.max(...values, 1), slot = (W - p.l - p.r) / values.length, bw = Math.min(34, slot * .55);
    const bars = values.map((value, index) => {
      const height = (Number(value) / max) * (H - p.t - p.b), xx = p.l + index * slot + (slot - bw) / 2, yy = H - p.b - height;
      return `<rect x="${xx}" y="${yy}" width="${bw}" height="${height}" rx="7" class="bar"/><text x="${xx+bw/2}" y="${Math.max(13, yy-7)}" text-anchor="middle" class="bar-value">${Number(value)}</text><text x="${xx+bw/2}" y="${H-12}" text-anchor="middle" class="axis-x${index % 2 ? ' axis-x-alt' : ''}">${esc(monthLabel(labels[index]))}</text>`;
    }).join('');
    el.innerHTML = `<svg class="os-chart-svg" viewBox="0 0 ${W} ${H}" role="img" aria-label="${esc(opts.label || 'Gráfico de barras')}">${bars}</svg>`;
  }

  function donutChart(target, active, inactive) {
    const el = qs(target);
    if (!el) return;
    const total = Number(active || 0) + Number(inactive || 0);
    if (!total) {
      el.innerHTML = empty('Cadastre pacientes para visualizar a distribuição.');
      return;
    }
    const pct = active / total, radius = 55, circumference = 2 * Math.PI * radius, dash = circumference * pct;
    el.innerHTML = `<div class="os-donut-layout"><svg viewBox="0 0 150 150" class="os-donut-svg" role="img" aria-label="${Number(active)} pacientes ativos e ${Number(inactive)} inativos"><circle cx="75" cy="75" r="55" class="donut-track"/><circle cx="75" cy="75" r="55" class="donut-value" stroke-dasharray="${dash} ${circumference-dash}" transform="rotate(-90 75 75)"/><text x="75" y="70" text-anchor="middle" class="donut-pct">${Math.round(pct*100)}%</text><text x="75" y="91" text-anchor="middle" class="donut-label">ativos</text></svg><div class="os-donut-legend"><div><span class="dot active"></span><span>Ativos</span><strong>${Number(active)}</strong></div><div><span class="dot inactive"></span><span>Inativos</span><strong>${Number(inactive)}</strong></div><div class="total"><span>Total</span><strong>${total}</strong></div></div></div>`;
  }

  window.NutriOSCharts = Object.freeze({lineChart, barChart, donutChart});
})();

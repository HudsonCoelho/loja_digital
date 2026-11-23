import { api } from '../core/api.js';
import { fmtMoney, fmtDateStr } from '../core/format.js';
import { showToast } from '../core/ui.js';

let chartRev, chartTop, chartPay;

export async function loadReports() {
  await Promise.all([
    loadDashboard(),
    loadCurvaABC()
  ]);
}

async function loadDashboard() {
  try {
    const data = await api.get('/api/relatorios');
    
    document.getElementById('kpi-day').textContent = fmtMoney(data.kpis.dia);
    document.getElementById('kpi-month').textContent = fmtMoney(data.kpis.mes);
    document.getElementById('kpi-ticket').textContent = fmtMoney(data.kpis.ticket);
    document.getElementById('kpi-pieces').textContent = data.kpis.pecas;

    const tbody = document.getElementById('sales-body');
    if (tbody) {
      tbody.innerHTML = (data.ultimas_vendas || []).map(s => `
        <tr>
          <td><strong>#${s.id}</strong></td><td class="muted">${fmtDateStr(s.date)}</td>
          <td>${s.items} un</td><td><span class="chip">${s.payment}</span></td>
          <td class="num font-bold text-emerald-400">${fmtMoney(s.total)}</td>
        </tr>
      `).join('') || '<tr><td colspan="5" class="text-center py-4 muted">Nenhuma venda registrada ainda</td></tr>';
    }

    renderCharts(data);
  } catch (e) {
    showToast('Erro ao carregar relatórios', 'error');
  }
}

export async function loadCurvaABC() {
  const tbody = document.getElementById('abc-table-body');
  const empty = document.getElementById('abc-empty');
  const totalReceitaEl = document.getElementById('abc-total-receita');
  const totalProdutosEl = document.getElementById('abc-total-produtos');
  if (!tbody) return;

  try {
    tbody.innerHTML = '<tr><td colspan="7" class="text-center py-4 muted">Calculando Curva ABC...</td></tr>';
    const data = await api.get('/api/relatorios/abc');

    if (totalReceitaEl) totalReceitaEl.textContent = fmtMoney(data.total_geral || 0);
    if (totalProdutosEl) totalProdutosEl.textContent = `${(data.itens || []).length} produtos`;

    if (!data.itens || data.itens.length === 0) {
      tbody.innerHTML = '';
      if (empty) empty.hidden = false;
      return;
    }
    if (empty) empty.hidden = true;

    tbody.innerHTML = data.itens.map((p, idx) => {
      const badgeClass = p.classe === 'A' ? 'badge--ok' : p.classe === 'B' ? 'badge--low' : 'badge--out';
      const badgeDesc = p.classe === 'A' ? 'Classe A (80% da receita)' : p.classe === 'B' ? 'Classe B (15% da receita)' : 'Classe C (5% restante)';
      return `
        <tr>
          <td class="id-cell">#${idx + 1}</td>
          <td><strong>${p.nome}</strong></td>
          <td class="num font-bold">${p.quantidade} un</td>
          <td class="num font-bold text-emerald-400">${fmtMoney(p.receita)}</td>
          <td class="num">${p.pct_acumulado}%</td>
          <td><span class="badge ${badgeClass}" title="${badgeDesc}">Classe ${p.classe}</span></td>
        </tr>
      `;
    }).join('');
  } catch (err) {
    tbody.innerHTML = `<tr><td colspan="7" class="text-center py-4 text-danger">${err.message || 'Erro ao carregar Curva ABC'}</td></tr>`;
  }
}

function renderCharts(data) {
  if (!window.Chart) return;
  Chart.defaults.color = '#9a97b0';
  Chart.defaults.font.family = '"Inter", sans-serif';
  Chart.defaults.borderColor = 'rgba(255, 255, 255, 0.05)';

  // Mensal
  const revLabels = (data.grafico_mensal || []).map(i => i.mes).reverse();
  const revData = (data.grafico_mensal || []).map(i => i.total).reverse();
  if (chartRev) chartRev.destroy();
  const elRev = document.getElementById('chart-revenue');
  if (elRev) {
    chartRev = new Chart(elRev, {
      type: 'bar', data: { labels: revLabels, datasets: [{ data: revData, backgroundColor: '#7c5ce6', borderRadius: 4 }] },
      options: { responsive: true, maintainAspectRatio: false, plugins: { legend: { display: false } } }
    });
  }

  // Categorias
  if (chartTop) chartTop.destroy();
  const elTop = document.getElementById('chart-top');
  if (elTop) {
    chartTop = new Chart(elTop, {
      type: 'doughnut', data: { 
        labels: (data.grafico_categorias || []).map(i=>i.label), 
        datasets: [{ data: (data.grafico_categorias || []).map(i=>i.valor), backgroundColor: ['#10b981', '#7c5ce6', '#5cb8f2', '#f5b544'], borderWidth: 0 }] 
      }, options: { responsive: true, maintainAspectRatio: false, cutout: '75%', plugins: { legend: { position: 'bottom' } } }
    });
  }

  // Pagamentos
  if (chartPay) chartPay.destroy();
  const elPay = document.getElementById('chart-payments');
  if (elPay) {
    chartPay = new Chart(elPay, {
      type: 'pie', data: { 
        labels: (data.grafico_pagamentos || []).map(i=>i.label), 
        datasets: [{ data: (data.grafico_pagamentos || []).map(i=>i.valor), backgroundColor: ['#10b981', '#7c5ce6', '#b9a6ff', '#f5b544'], borderWidth: 0 }] 
      }, options: { responsive: true, maintainAspectRatio: false, plugins: { legend: { position: 'bottom' } } }
    });
  }
}

export function setupRelatorios() {
  const tabs = document.querySelectorAll('#view-relatorios .tab');
  const btnMetasTab = document.getElementById('tab-btn-relatorios-metas');
  
  // Exibe aba Metas apenas para administradores
  const user = window.currentUser || {};
  if (btnMetasTab) {
    btnMetasTab.style.display = (user.perfil === 'admin') ? 'inline-flex' : 'none';
  }

  tabs.forEach(tab => {
    tab.addEventListener('click', () => {
      tabs.forEach(t => t.classList.remove('is-active'));
      tab.classList.add('is-active');
      const targetId = tab.dataset.target;
      document.querySelectorAll('#view-relatorios .tab-panel').forEach(p => {
        p.hidden = p.id !== targetId;
        p.classList.toggle('is-active', p.id === targetId);
      });
      if (targetId === 'tab-relatorios-abc') {
        loadCurvaABC();
      } else if (targetId === 'tab-relatorios-metas') {
        loadMetas();
      }
    });
  });

  // Filtro de período das metas
  const inputPeriodo = document.getElementById('f-metas-periodo');
  if (inputPeriodo) {
    if (!inputPeriodo.value) {
      const now = new Date();
      const mesStr = String(now.getMonth() + 1).padStart(2, '0');
      inputPeriodo.value = `${now.getFullYear()}-${mesStr}`;
    }
    inputPeriodo.addEventListener('change', () => loadMetas());
  }

  // Copiar metas do mês anterior
  const btnCopiar = document.getElementById('btn-copiar-metas');
  if (btnCopiar) {
    btnCopiar.addEventListener('click', async () => {
      const periodo = document.getElementById('f-metas-periodo')?.value;
      if (!periodo) return;
      if (!confirm(`Copiar as metas do mês anterior para ${periodo}? As metas já definidas neste mês não serão sobrescritas.`)) return;

      try {
        const res = await api.post('/api/metas/copiar-mes-anterior', { periodo });
        showToast(`${res.copiadas} meta(s) copiada(s) do mês anterior!`, 'success');
        loadMetas();
      } catch (err) {
        showToast(err.message || 'Erro ao copiar metas', 'error');
      }
    });
  }

  // Form de edição de meta
  const formMeta = document.getElementById('form-meta-vendedor');
  if (formMeta) {
    formMeta.addEventListener('submit', async (e) => {
      e.preventDefault();
      const vid = parseInt(document.getElementById('meta-vendedor-id').value);
      const periodo = document.getElementById('meta-periodo').value;
      const valor = parseFloat(document.getElementById('meta-valor').value) || 0;

      try {
        await api.put('/api/metas', {
          vendedor_id: vid,
          periodo: periodo,
          valor_meta: valor
        });
        showToast('Meta atualizada com sucesso!', 'success');
        const modal = document.getElementById('modal-meta-vendedor');
        if (modal) {
          const closeBtn = modal.querySelector('[data-close-modal]');
          if (closeBtn) closeBtn.click();
        }
        loadMetas();
      } catch (err) {
        showToast(err.message || 'Erro ao definir meta', 'error');
      }
    });
  }
}

export async function loadMetas() {
  const tbody = document.getElementById('metas-table-body');
  const empty = document.getElementById('metas-empty');
  if (!tbody) return;

  const inputPeriodo = document.getElementById('f-metas-periodo');
  let periodo = inputPeriodo?.value;
  if (!periodo) {
    const now = new Date();
    const mesStr = String(now.getMonth() + 1).padStart(2, '0');
    periodo = `${now.getFullYear()}-${mesStr}`;
    if (inputPeriodo) inputPeriodo.value = periodo;
  }

  try {
    tbody.innerHTML = '<tr><td colspan="7" class="text-center py-4 muted">Carregando metas dos vendedores...</td></tr>';
    const metas = await api.get(`/api/metas?periodo=${periodo}`);

    if (!metas || metas.length === 0) {
      tbody.innerHTML = '';
      if (empty) empty.hidden = false;
      return;
    }
    if (empty) empty.hidden = true;

    tbody.innerHTML = metas.map(m => {
      const pct = m.percentual || 0;
      const pctClamped = Math.min(pct, 100);
      const barColor = pct >= 100 ? 'var(--emerald-400)' : pct >= 50 ? 'var(--brand-400)' : 'var(--warning)';
      const ritmoStr = (m.ritmo_diario && m.ritmo_diario > 0) ? `${fmtMoney(m.ritmo_diario)}/dia` : '—';
      const statusBadge = pct >= 100 ? '<span class="badge badge--ok" style="font-size:11px">Atingida</span>' : '';

      return `
        <tr>
          <td><strong>${m.vendedor_nome}</strong> ${statusBadge}</td>
          <td class="num font-bold">${fmtMoney(m.valor_meta)}</td>
          <td class="num font-bold text-emerald-400">${fmtMoney(m.vendido)}</td>
          <td>
            <div style="display:flex; align-items:center; gap:0.5rem;">
              <span style="font-size:0.85rem; font-weight:600; min-width:48px;">${pct}%</span>
              <div class="qty-bar__track" style="flex:1; height:7px; background:rgba(255,255,255,0.08); border-radius:4px; overflow:hidden;">
                <div style="width:${pctClamped}%; height:100%; background:${barColor}; border-radius:4px; transition:width 0.3s ease;"></div>
              </div>
            </div>
          </td>
          <td class="num ${m.falta > 0 ? 'text-warning' : 'muted'}">${fmtMoney(m.falta)}</td>
          <td class="num muted" title="Venda diária necessária nos dias restantes do mês para atingir a meta">${ritmoStr}</td>
          <td style="text-align: right;">
            <button type="button" class="btn btn--secondary btn--sm" onclick="window.editarMetaVendedor(${m.vendedor_id}, '${m.vendedor_nome.replace(/'/g, "\\'")}', '${periodo}', ${m.valor_meta})">
              Editar Meta
            </button>
          </td>
        </tr>
      `;
    }).join('');
  } catch (err) {
    tbody.innerHTML = `<tr><td colspan="7" class="text-center py-4 text-danger">${err.message || 'Erro ao carregar metas'}</td></tr>`;
  }
}

// Global para abrir modal de edição de meta
window.editarMetaVendedor = (vid, nome, periodo, valorAtual) => {
  document.getElementById('meta-vendedor-id').value = vid;
  document.getElementById('meta-vendedor-nome').value = nome;
  document.getElementById('meta-periodo').value = periodo;
  document.getElementById('meta-valor').value = (valorAtual || 0).toFixed(2);

  const modal = document.getElementById('modal-meta-vendedor');
  if (modal) {
    modal.hidden = false;
    modal.classList.add('is-open');
    setTimeout(() => document.getElementById('meta-valor')?.focus(), 100);
  }
};

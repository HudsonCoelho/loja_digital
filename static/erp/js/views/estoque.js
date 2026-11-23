import { api } from '../core/api.js';
import { fmtMoney, fmtDateStr } from '../core/format.js';
import { showToast, openModal, closeModal } from '../core/ui.js';

export let products = [];

const MAPA_TIPOS_MOV = {
  entrada: { label: 'Entrada (+)', badge: 'badge--ok' },
  venda: { label: 'Venda (Saída)', badge: 'badge--out' },
  devolucao: { label: 'Devolução (+)', badge: 'badge--low' },
  ajuste_avaria: { label: 'Ajuste: Avaria', badge: 'badge--out' },
  ajuste_perda: { label: 'Ajuste: Perda / Extravio', badge: 'badge--out' },
  ajuste_furto: { label: 'Ajuste: Furto', badge: 'badge--out' },
  ajuste_brinde: { label: 'Ajuste: Brinde / Doação', badge: 'badge--low' },
  ajuste_uso_loja: { label: 'Ajuste: Uso da Loja', badge: 'badge--low' },
  ajuste_devolucao_fornecedor: { label: 'Ajuste: Dev. Fornecedor', badge: 'badge--out' },
  ajuste_inventario: { label: 'Ajuste: Inventário', badge: 'badge--ok' },
  ajuste: { label: 'Ajuste Manual', badge: 'badge--low' }
};

export async function fetchProducts() {
  try {
    products = await api.get('/api/produtos?_=' + Date.now());
    renderStock();
    return products;
  } catch (e) {
    showToast('Erro ao carregar produtos', 'error');
    return [];
  }
}

export function renderStock() {
  const tbody = document.getElementById('stock-body');
  const alertsEl = document.getElementById('nav-stock-alerts');
  if (!tbody) return;

  const ehAdmin = (window.currentUser && window.currentUser.perfil === 'admin');
  const btnInv = document.getElementById('btn-abrir-inventario');
  if (btnInv) {
    btnInv.style.display = ehAdmin ? 'inline-flex' : 'none';
  }
  const btnNewProd = document.getElementById('btn-new-product');
  if (btnNewProd) {
    btnNewProd.style.display = ehAdmin ? 'inline-flex' : 'none';
  }
  const tabMov = document.querySelector('#view-estoque .tab[data-target="tab-estoque-movimentacoes"]');
  if (tabMov) {
    tabMov.style.display = ehAdmin ? 'inline-flex' : 'none';
  }
  const panelMov = document.getElementById('tab-estoque-movimentacoes');
  if (panelMov && !ehAdmin) {
    panelMov.hidden = true;
    panelMov.classList.remove('is-active');
    const panelProd = document.getElementById('tab-estoque-produtos');
    if (panelProd) {
      panelProd.hidden = false;
      panelProd.classList.add('is-active');
    }
    const tabProd = document.querySelector('#view-estoque .tab[data-target="tab-estoque-produtos"]');
    if (tabProd) tabProd.classList.add('is-active');
    if (tabMov) tabMov.classList.remove('is-active');
  }

  let lowCount = 0;
  
  const rows = products.map(p => {
    const variacoes = p.variacoes || [];
    const totalQty = variacoes.reduce((a, v) => a + v.estoque, 0);
    const isOut = totalQty === 0;
    const isLow = !isOut && totalQty <= p.min;
    
    if (isOut || isLow) lowCount++;
    const statusHtml = isOut ? `<span class="badge badge--out">Em falta</span>` : isLow ? `<span class="badge badge--low">Estoque baixo</span>` : `<span class="badge badge--ok">Abastecido</span>`;
    const pct = Math.min((totalQty / (p.min * 3)) * 100, 100) || 0;
    const barColor = isOut ? 'var(--danger)' : isLow ? 'var(--warning)' : 'var(--emerald-400)';

    const gradeHtml = variacoes.map(v => {
      const escapeProd = (p.nome || '').replace(/'/g, "\\'").replace(/"/g, '&quot;');
      const btnAjustar = ehAdmin ? `
        <button type="button" class="btn btn--xs btn--ghost btn-ajustar-var" 
                onclick="window.abrirAjusteEstoque(${v.id}, '${escapeProd}', '${v.tamanho}', '${v.cor}', ${v.estoque})"
                style="padding:1px 5px; font-size:10px; height:18px; line-height:1; color:var(--brand-300);" 
                title="Ajustar estoque">Ajustar</button>
      ` : '';
      return `<div class="size-chip ${v.estoque === 0 ? 'is-zero' : ''}" style="display:inline-flex; align-items:center; gap:4px; margin:2px;">
        <small>${v.tamanho}${v.cor && v.cor !== 'Única' ? ` (${v.cor})` : ''}</small> <strong>${v.estoque}</strong>
        ${btnAjustar}
      </div>`;
    }).join('') || '<span class="muted small">Sem variações</span>';

    return `<tr>
      <td data-label="ID" class="id-cell">#${p.id}</td>
      <td data-label="Foto"><img src="${p.img || '/static/erp/img/placeholder.svg'}" onerror="this.onerror=null;this.src='/static/erp/img/placeholder.svg'" alt="" class="thumb" loading="lazy"></td>
      <td data-label="Produto"><div class="product-cell"><strong>${p.nome}</strong><small>${p.categoria || 'Geral'}</small></div></td>
      <td data-label="Grade"><div class="grade" style="display:flex; flex-wrap:wrap; gap:4px;">${gradeHtml}</div></td>
      <td data-label="Mínimo" class="num">${p.min}</td>
      <td data-label="Atual" class="num"><div class="qty-bar"><span class="${isOut?'text-danger':isLow?'text-warning':''} font-bold">${totalQty}</span><div class="qty-bar__track"><div class="qty-bar__fill" style="width:${pct}%;background:${barColor}"></div></div></div></td>
      <td data-label="Status">${statusHtml}</td>
    </tr>`;
  });

  tbody.innerHTML = rows.join('');
  if (alertsEl) {
    alertsEl.textContent = lowCount;
    alertsEl.hidden = lowCount === 0;
  }

  const valorTotal = products.reduce((acc, p) => acc + (p.preco * p.variacoes.reduce((a,v)=>a+v.estoque,0)), 0);
  const statsEl = document.getElementById('stock-stats');
  if (statsEl) {
    statsEl.innerHTML = `
      <div class="stat"><span class="stat__label">Total de SKUs</span><span class="stat__value">${products.length}</span></div>
      <div class="stat stat--money"><span class="stat__label">Estoque Avaliado</span><span class="stat__value">${fmtMoney(valorTotal)}</span></div>
      <div class="stat ${lowCount > 0 ? 'stat--warn' : ''}"><span class="stat__label">Alertas (Mínimo)</span><span class="stat__value">${lowCount}</span></div>
      <div class="stat"><span class="stat__label">Atualizado em</span><span class="stat__value text-sm font-normal mt-1">${new Date().toLocaleTimeString()}</span></div>
    `;
  }
}

export async function loadMovimentacoes() {
  const tbody = document.getElementById('mov-table-body');
  const empty = document.getElementById('mov-empty');
  if (!tbody) return;

  const ehAdmin = (window.currentUser && window.currentUser.perfil === 'admin');
  if (!ehAdmin) return;

  const tipo = document.getElementById('f-mov-tipo')?.value || '';
  const busca = (document.getElementById('f-mov-busca')?.value || '').trim();
  const de = document.getElementById('f-mov-de')?.value || '';
  const ate = document.getElementById('f-mov-ate')?.value || '';

  const params = new URLSearchParams();
  if (tipo) params.append('tipo', tipo);
  if (busca) params.append('q', busca);
  if (de) params.append('de', de);
  if (ate) params.append('ate', ate);

  try {
    tbody.innerHTML = '<tr><td colspan="8" class="text-center py-4 muted">Carregando histórico de movimentações...</td></tr>';
    const movs = await api.get(`/api/estoque/movimentacoes?${params.toString()}`);

    if (!movs || movs.length === 0) {
      tbody.innerHTML = '';
      if (empty) empty.hidden = false;
      return;
    }
    if (empty) empty.hidden = true;

    tbody.innerHTML = movs.map(m => {
      const isPos = m.quantidade > 0;
      const infoTipo = MAPA_TIPOS_MOV[m.tipo] || {
        label: m.tipo.startsWith('ajuste') ? `Ajuste (${m.tipo.replace('ajuste_', '').replace(/_/g, ' ')})` : m.tipo,
        badge: m.tipo.startsWith('ajuste') ? 'badge--low' : ''
      };
      const tipoLabel = infoTipo.label;
      const tipoClass = infoTipo.badge;
      const qtdFmt = isPos ? `+${m.quantidade}` : `${m.quantidade}`;

      return `
        <tr>
          <td class="id-cell">#${m.id}</td>
          <td class="muted small">${fmtDateStr(m.data)}</td>
          <td><strong>${m.produto_nome}</strong></td>
          <td><span class="size-chip">${m.tamanho} / ${m.cor}</span></td>
          <td><span class="badge ${tipoClass}">${tipoLabel}</span></td>
          <td class="num font-bold ${isPos ? 'text-emerald-400' : 'text-danger'}">${qtdFmt}</td>
          <td class="num font-bold">${m.saldo_apos}</td>
          <td><small class="muted">${m.obs ? m.obs : ''}${m.ref_tipo ? ` (${m.ref_tipo} #${m.ref_id})` : ''}${m.usuario_nome ? ` · ${m.usuario_nome}` : ''}</small></td>
        </tr>
      `;
    }).join('');
  } catch (err) {
    tbody.innerHTML = `<tr><td colspan="8" class="text-center py-4 text-danger">${err.message || 'Erro ao carregar movimentações'}</td></tr>`;
  }
}

export function setupEstoqueViews() {
  const tabs = document.querySelectorAll('#view-estoque .tab');
  tabs.forEach(tab => {
    tab.addEventListener('click', () => {
      tabs.forEach(t => t.classList.remove('is-active'));
      tab.classList.add('is-active');
      const targetId = tab.dataset.target;
      document.querySelectorAll('#view-estoque .tab-panel').forEach(p => {
        p.hidden = p.id !== targetId;
        p.classList.toggle('is-active', p.id === targetId);
      });
      if (targetId === 'tab-estoque-movimentacoes') {
        loadMovimentacoes();
      }
    });
  });

  const btnFiltrarMov = document.getElementById('btn-mov-filtrar');
  if (btnFiltrarMov) {
    btnFiltrarMov.addEventListener('click', () => loadMovimentacoes());
  }

  const buscaMov = document.getElementById('f-mov-busca');
  if (buscaMov) {
    buscaMov.addEventListener('keydown', (e) => {
      if (e.key === 'Enter') {
        e.preventDefault();
        loadMovimentacoes();
      }
    });
  }

  // Configuração do Modal de Ajuste de Estoque Avulso
  setupModalAjuste();

  // Configuração do Modal de Inventário Geral
  setupModalInventario();
}

function setupModalAjuste() {
  const form = document.getElementById('form-ajuste-estoque');
  const modoBaixa = document.getElementById('modo-baixa');
  const modoContagem = document.getElementById('modo-contagem');
  const labelQtd = document.getElementById('ajuste-label-qtd');
  const inputQtd = document.getElementById('ajuste-quantidade');
  const selectMotivo = document.getElementById('ajuste-motivo');
  const obsReq = document.getElementById('ajuste-obs-req');
  const inputObs = document.getElementById('ajuste-obs');
  const previewDiff = document.getElementById('ajuste-preview-diff');

  function atualizarPreview() {
    const estoqueAtual = parseInt(form.dataset.estoqueAtual) || 0;
    const modo = modoContagem.checked ? 'contagem' : 'baixa';
    const qtd = parseInt(inputQtd.value) || 0;

    let novoEstoque = estoqueAtual;
    let delta = 0;

    if (modo === 'baixa') {
      labelQtd.textContent = 'Quantidade a baixar (saída)';
      inputQtd.min = '1';
      delta = -qtd;
      novoEstoque = estoqueAtual - qtd;
    } else {
      labelQtd.textContent = 'Quantidade contada física (total)';
      inputQtd.min = '0';
      novoEstoque = qtd;
      delta = qtd - estoqueAtual;
    }

    const deltaSign = delta > 0 ? `+${delta}` : `${delta}`;
    const deltaColor = novoEstoque < 0 ? 'var(--danger)' : delta < 0 ? 'var(--warning)' : delta > 0 ? 'var(--emerald-400)' : 'var(--text)';
    previewDiff.innerHTML = `${estoqueAtual} un → <span style="color:${deltaColor}">${novoEstoque} un</span> (${deltaSign})`;

    // Motivos que exigem observação obrigatória
    const motivo = selectMotivo.value;
    const obrigatorio = ['Furto', 'Devolução ao fornecedor', 'Outro'].includes(motivo);
    if (obsReq) obsReq.style.display = obrigatorio ? 'inline' : 'none';
    if (inputObs) inputObs.required = obrigatorio;
  }

  if (modoBaixa) modoBaixa.addEventListener('change', atualizarPreview);
  if (modoContagem) modoContagem.addEventListener('change', atualizarPreview);
  if (inputQtd) inputQtd.addEventListener('input', atualizarPreview);
  if (selectMotivo) selectMotivo.addEventListener('change', atualizarPreview);

  if (form) {
    form.addEventListener('submit', async (e) => {
      e.preventDefault();
      const vid = parseInt(document.getElementById('ajuste-var-id').value);
      const modo = modoContagem.checked ? 'contagem' : 'baixa';
      const qtd = parseInt(inputQtd.value);
      const motivo = selectMotivo.value;
      const obs = inputObs.value.trim();

      const btnSubmit = document.getElementById('btn-submit-ajuste');
      if (btnSubmit) { btnSubmit.disabled = true; btnSubmit.textContent = 'Ajustando...'; }

      try {
        const res = await api.post('/api/estoque/ajuste', {
          variacao_id: vid,
          modo: modo,
          quantidade: qtd,
          motivo: motivo,
          obs: obs
        });

        showToast('Estoque ajustado com sucesso!', 'success');
        const modal = document.getElementById('modal-ajuste-estoque');
        if (modal) {
          const closeBtn = modal.querySelector('[data-close-modal]');
          if (closeBtn) closeBtn.click();
        }
        await fetchProducts();
        loadMovimentacoes();
      } catch (err) {
        showToast(err.message || 'Erro ao ajustar estoque', 'error');
      } finally {
        if (btnSubmit) { btnSubmit.disabled = false; btnSubmit.textContent = 'Confirmar Ajuste'; }
      }
    });
  }

  // Função global chamada pelo botão de ajustar variação
  window.abrirAjusteEstoque = (vid, prodNome, tam, cor, estoqueAtual) => {
    form.dataset.estoqueAtual = estoqueAtual;
    document.getElementById('ajuste-var-id').value = vid;
    document.getElementById('ajuste-prod-info').textContent = `${prodNome} — ${tam} / ${cor}`;
    document.getElementById('ajuste-prod-estoque-atual').textContent = estoqueAtual;

    modoBaixa.checked = true;
    inputQtd.value = 1;
    selectMotivo.value = 'Avaria';
    inputObs.value = '';

    atualizarPreview();

    const modal = document.getElementById('modal-ajuste-estoque');
    if (modal) {
      modal.hidden = false;
      modal.classList.add('is-open');
      setTimeout(() => inputQtd?.focus(), 100);
    }
  };
}

function setupModalInventario() {
  const btnAbrir = document.getElementById('btn-abrir-inventario');
  const tbody = document.getElementById('inventario-tbody');
  const filtroInput = document.getElementById('inventario-filtro');
  const btnConfirmar = document.getElementById('btn-confirmar-inventario');
  const totalItensEl = document.getElementById('inv-total-itens');
  const divergenciasEl = document.getElementById('inv-divergencias');

  function renderTabelaInventario() {
    if (!tbody) return;
    const linhas = [];

    products.forEach(p => {
      (p.variacoes || []).forEach(v => {
        linhas.push({
          variacao_id: v.id,
          produto_nome: p.nome,
          tamanho: v.tamanho,
          cor: v.cor,
          codigo: v.codigo_barras || v.sku || '—',
          sku: v.sku || '',
          estoque: v.estoque
        });
      });
    });

    if (totalItensEl) totalItensEl.textContent = linhas.length;
    if (divergenciasEl) divergenciasEl.textContent = '0';

    tbody.innerHTML = linhas.map(it => `
      <tr class="inv-row" data-vid="${it.variacao_id}" data-atual="${it.estoque}" data-search="${(it.produto_nome + ' ' + it.tamanho + ' ' + it.cor + ' ' + it.codigo + ' ' + it.sku).toLowerCase()}">
        <td><strong>${it.produto_nome}</strong> <span class="badge" style="margin-left:4px">${it.tamanho} / ${it.cor}</span></td>
        <td><code>${it.codigo}</code></td>
        <td class="num font-bold">${it.estoque}</td>
        <td class="num">
          <input type="number" class="input input--qty inv-contado" min="0" step="1" 
                 value="${it.estoque}" data-atual="${it.estoque}" data-vid="${it.variacao_id}"
                 style="width:90px; text-align:right; font-weight:bold; height:32px; padding:2px 8px;">
        </td>
        <td class="num">
          <strong class="inv-diff muted" data-vid="${it.variacao_id}">0</strong>
        </td>
      </tr>
    `).join('') || '<tr><td colspan="5" class="text-center py-4 muted">Nenhum produto cadastrado para inventário.</td></tr>';

    tbody.querySelectorAll('.inv-contado').forEach(input => {
      input.addEventListener('input', () => {
        const atual = parseInt(input.dataset.atual) || 0;
        const contado = parseInt(input.value) || 0;
        const diff = contado - atual;
        const diffEl = tbody.querySelector(`.inv-diff[data-vid="${input.dataset.vid}"]`);
        if (diffEl) {
          if (diff > 0) {
            diffEl.textContent = `+${diff}`;
            diffEl.style.color = 'var(--emerald-400)';
          } else if (diff < 0) {
            diffEl.textContent = `${diff}`;
            diffEl.style.color = 'var(--red-400)';
          } else {
            diffEl.textContent = '0';
            diffEl.style.color = 'var(--gray-400)';
          }
        }
        atualizarContadorDivergencias();
      });
    });
  }

  function atualizarContadorDivergencias() {
    let divs = 0;
    tbody.querySelectorAll('.inv-contado').forEach(inp => {
      const atual = parseInt(inp.dataset.atual) || 0;
      const contado = parseInt(inp.value) || 0;
      if (contado !== atual) divs++;
    });
    if (divergenciasEl) divergenciasEl.textContent = divs;
  }

  if (btnAbrir) {
    btnAbrir.addEventListener('click', () => {
      renderTabelaInventario();
      if (filtroInput) filtroInput.value = '';
      const modal = document.getElementById('modal-inventario');
      if (modal) {
        modal.hidden = false;
        modal.classList.add('is-open');
        setTimeout(() => filtroInput?.focus(), 100);
      }
    });
  }

  if (filtroInput) {
    filtroInput.addEventListener('input', () => {
      const q = filtroInput.value.trim().toLowerCase();
      tbody.querySelectorAll('.inv-row').forEach(row => {
        const text = row.dataset.search || '';
        row.hidden = q ? !text.includes(q) : false;
      });
    });
  }

  if (btnConfirmar) {
    btnConfirmar.addEventListener('click', async () => {
      const itens = [];
      tbody.querySelectorAll('.inv-row').forEach(row => {
        const vid = parseInt(row.dataset.vid);
        const inp = row.querySelector('.inv-contado');
        if (vid && inp) {
          const contado = parseInt(inp.value) || 0;
          const atual = parseInt(row.dataset.atual) || 0;
          if (contado !== atual) {
            itens.push({ variacao_id: vid, quantidade: contado });
          }
        }
      });

      if (itens.length === 0) {
        showToast('Nenhuma divergência de contagem encontrada.', 'info');
        return;
      }

      if (!confirm(`Deseja aplicar o ajuste de inventário para ${itens.length} variação(ões) com divergência?`)) return;

      const obsGeral = document.getElementById('inventario-obs-geral')?.value || 'Inventário físico geral';

      btnConfirmar.disabled = true;
      btnConfirmar.textContent = 'Processando inventário...';

      try {
        const res = await api.post('/api/estoque/inventario', {
          itens: itens,
          obs: obsGeral
        });

        showToast(`Inventário aplicado! ${res.ajustes_aplicados} variação(ões) atualizada(s).`, 'success');
        const modal = document.getElementById('modal-inventario');
        if (modal) {
          const closeBtn = modal.querySelector('[data-close-modal]');
          if (closeBtn) closeBtn.click();
        }
        await fetchProducts();
        loadMovimentacoes();
      } catch (err) {
        showToast(err.message || 'Erro ao aplicar inventário', 'error');
      } finally {
        btnConfirmar.disabled = false;
        btnConfirmar.textContent = 'Aplicar Contagem Geral';
      }
    });
  }
}

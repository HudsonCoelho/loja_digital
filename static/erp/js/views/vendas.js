import { api } from '../core/api.js';
import { fmtMoney, fmtDateStr, escapeHtml } from '../core/format.js';
import { showToast, openModal, closeModal } from '../core/ui.js';

let vendas = [];

const els = {
  body: document.getElementById('vendas-body'),
  btnFiltrar: document.getElementById('btn-vendas-filtrar'),
  fDe: document.getElementById('f-vendas-de'),
  fAte: document.getElementById('f-vendas-ate'),
  fStatus: document.getElementById('f-vendas-status')
};

export async function loadVendas() {
  if (!els.body) return;
  const de = els.fDe.value;
  const ate = els.fAte.value;
  const status = els.fStatus.value;
  
  let url = '/api/vendas?_=1';
  if (de) url += `&de=${de}`;
  if (ate) url += `&ate=${ate}`;
  if (status) url += `&status=${status}`;

  try {
    vendas = await api.get(url);
    renderVendas();
  } catch (e) {
    showToast('Erro ao carregar vendas', 'error');
  }
}

function renderVendas() {
  if (!els.body) return;
  
  if (!vendas || vendas.length === 0) {
    els.body.innerHTML = `<tr><td colspan="6" class="muted" style="text-align:center; padding:2rem;">Nenhuma venda encontrada.</td></tr>`;
    return;
  }
  
  els.body.innerHTML = vendas.map(v => {
    const isCancelada = v.status === 'cancelada';
    const statusHtml = isCancelada 
      ? `<span class="badge badge--out">Cancelada</span>` 
      : `<span class="badge badge--ok">Concluída</span>`;
      
    return `<tr>
      <td><strong>${escapeHtml(v.codigo)}</strong></td>
      <td>${fmtDateStr(v.data)}</td>
      <td>${escapeHtml(v.vendedor_nome || 'N/A')}</td>
      <td class="num font-bold ${isCancelada ? 'text-muted' : ''}">${fmtMoney(v.total)}</td>
      <td>${statusHtml}</td>
      <td>
        <button type="button" class="btn btn--sm btn--secondary btn-ver-venda" data-venda-id="${v.id}" onclick="window.verVenda(${v.id})">Detalhes</button>
      </td>
    </tr>`;
  }).join('');
}

window.verVenda = async (id) => {
  const modalBody = document.getElementById('venda-detalhe-body');
  const modalTitle = document.getElementById('venda-detalhe-codigo');
  const btnCancel = document.getElementById('btn-cancelar-venda');
  const btnImprimir = document.getElementById('btn-imprimir-venda');
  
  if (modalTitle) modalTitle.textContent = '...';
  if (modalBody) modalBody.innerHTML = '<div style="text-align:center; padding:2rem">Carregando detalhes...</div>';
  if (btnCancel) btnCancel.hidden = true;
  
  openModal('modal-venda');

  try {
    const v = await api.get(`/api/vendas/${id}`);
    if (modalTitle) modalTitle.textContent = v.codigo;
    if (btnImprimir) {
      btnImprimir.onclick = () => window.open(`/cupom?id=${v.id}`, '_blank');
    }
    
    let html = `
      <div style="display:grid; grid-template-columns:1fr 1fr; gap:1rem; margin-bottom:1.5rem; background:var(--bg); padding:1rem; border-radius:var(--radius); border:1px solid var(--border)">
        <div><strong>Data:</strong> ${fmtDateStr(v.data)}</div>
        <div><strong>Vendedor:</strong> ${escapeHtml(v.vendedor_nome || 'Não informado')}</div>
        <div><strong>Status:</strong> ${v.status === 'cancelada' ? '<span class="badge badge--out">Cancelada</span>' : '<span class="badge badge--ok">Concluída</span>'}</div>
        <div><strong>Total:</strong> <span style="font-weight:700; color:var(--emerald-400)">${fmtMoney(v.total)}</span></div>
      </div>
      <h3 class="muted uppercase small" style="margin-bottom:0.5rem">Itens da Venda</h3>
      <div class="table-wrap mb-4">
        <table class="table table--compact">
          <thead><tr><th>Item</th><th class="num">Qtd</th><th class="num">Subtotal</th></tr></thead>
          <tbody>
            ${v.itens.map(i => `<tr>
              <td><strong>${escapeHtml(i.nome)}</strong> ${i.tamanho ? `<small class="muted">(${escapeHtml(i.tamanho)})</small>` : ''}</td>
              <td class="num">${i.quantidade}</td>
              <td class="num">${fmtMoney(i.total)}</td>
            </tr>`).join('')}
          </tbody>
        </table>
      </div>
      <h3 class="muted uppercase small" style="margin-bottom:0.5rem">Formas de Pagamento</h3>
      <ul class="mb-4" style="list-style:none; padding:0; display:flex; flex-direction:column; gap:0.25rem;">
        ${v.pagamentos.map(p => `<li style="background:var(--surface-2); padding:0.5rem 0.75rem; border-radius:var(--radius-sm); display:flex; justify-content:space-between"><span>${escapeHtml(p.forma)}</span><strong>${fmtMoney(p.valor)}</strong></li>`).join('')}
      </ul>
    `;
    
    if (v.devolucoes && v.devolucoes.length > 0) {
      html += `
        <h3 class="muted uppercase small mt-4 text-warning" style="margin-bottom:0.5rem">Devoluções / Trocas</h3>
        <ul class="mb-4" style="list-style:none; padding:0; display:flex; flex-direction:column; gap:0.25rem;">
          ${v.devolucoes.map(d => `<li style="background:var(--surface-2); padding:0.5rem 0.75rem; border-radius:var(--radius-sm); border-left:3px solid var(--warning); display:flex; justify-content:space-between"><span class="text-warning">${fmtDateStr(d.data)} - ${escapeHtml(d.tipo.toUpperCase())}</span><strong>${fmtMoney(d.valor)}</strong></li>`).join('')}
        </ul>
      `;
    }
    
    if (modalBody) modalBody.innerHTML = html;
    
    if (btnCancel && v.status !== 'cancelada' && (!v.devolucoes || v.devolucoes.length === 0)) {
      btnCancel.hidden = false;
      btnCancel.onclick = () => cancelarVenda(id, v.codigo);
      
      // Adicionar botão de Devolução dinamicamente na footer
      let btnDevolver = document.getElementById('btn-devolver-venda');
      if (!btnDevolver) {
        btnDevolver = document.createElement('button');
        btnDevolver.id = 'btn-devolver-venda';
        btnDevolver.className = 'btn btn--primary';
        btnDevolver.textContent = 'Devolver / Trocar';
        btnCancel.parentElement.insertBefore(btnDevolver, btnCancel.nextSibling);
      }
      btnDevolver.hidden = false;
      btnDevolver.onclick = () => abrirDevolucao(v);
    } else {
      if (btnCancel) btnCancel.hidden = true;
      const btnDevolver = document.getElementById('btn-devolver-venda');
      if (btnDevolver) btnDevolver.hidden = true;
    }
    
  } catch (e) {
    if (modalBody) modalBody.innerHTML = '<div class="text-danger" style="text-align:center; padding:2rem">Erro ao carregar detalhes da venda.</div>';
  }
};

async function abrirDevolucao(venda) {
  const confirmacao = confirm(`Deseja gerar um Vale-Troca no valor de ${fmtMoney(venda.total)} para a venda ${venda.codigo}?`);
  if (!confirmacao) return;
  
  const itensParaDevolver = venda.itens.map(i => ({
    venda_item_id: i.id,
    quantidade: i.quantidade
  }));
  
  try {
    const res = await api.post(`/api/vendas/${venda.id}/devolver`, {
      tipo: 'vale',
      itens: itensParaDevolver,
      obs: 'Gerado pelo Histórico de Vendas'
    });
    
    showToast('Vale-Troca gerado com sucesso! Código: ' + res.vale_codigo, 'success');
    closeModal(document.getElementById('modal-venda'));
    loadVendas();
  } catch (e) {
    showToast(e.message || 'Erro ao processar devolução', 'error');
  }
}

async function cancelarVenda(id, codigo) {
  const motivo = prompt(`Deseja cancelar a venda ${codigo}?\nInforme o motivo do cancelamento (min 5 caracteres):`);
  if (motivo !== null) {
    if (motivo.length < 5) {
      showToast('Motivo muito curto', 'error');
      return;
    }
    try {
      await api.post(`/api/vendas/${id}/cancelar`, { motivo });
      showToast('Venda cancelada com sucesso', 'success');
      closeModal(document.getElementById('modal-venda'));
      loadVendas();
    } catch (e) {
      showToast(e.message || 'Erro ao cancelar', 'error');
    }
  }
}

export function setupVendas() {
  if (els.btnFiltrar) {
    els.btnFiltrar.addEventListener('click', loadVendas);
  }
  if (els.body) {
    els.body.addEventListener('click', (e) => {
      const btn = e.target.closest('.btn-ver-venda');
      if (btn && btn.dataset.vendaId) {
        window.verVenda(Number(btn.dataset.vendaId));
      }
    });
  }
}

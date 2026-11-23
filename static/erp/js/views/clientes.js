import { api } from '../core/api.js';
import { fmtMoney, fmtDateStr, escapeHtml } from '../core/format.js';
import { showToast, openModal, closeModal } from '../core/ui.js';

let clientesCache = [];

export async function loadClientes() {
  const tbody = document.getElementById('clientes-body');
  const empty = document.getElementById('clientes-empty');
  const totalPill = document.getElementById('clientes-count-pill');
  if (!tbody) return;

  const q = (document.getElementById('f-clientes-search')?.value || '').trim();
  const url = q ? `/api/clientes?q=${encodeURIComponent(q)}` : '/api/clientes';

  try {
    tbody.innerHTML = '<tr><td colspan="8" class="text-center py-4 muted">Carregando clientes...</td></tr>';
    const clientes = await api.get(url);
    clientesCache = clientes;

    if (totalPill) totalPill.textContent = clientes.length;

    if (!clientes || clientes.length === 0) {
      tbody.innerHTML = '';
      if (empty) empty.hidden = false;
      return;
    }
    if (empty) empty.hidden = true;

    tbody.innerHTML = clientes.map(c => `
      <tr>
        <td class="id-cell">#${c.id}</td>
        <td>
          <strong>${escapeHtml(c.nome)}</strong>
          ${c.email ? `<br><small class="muted">${escapeHtml(c.email)}</small>` : ''}
        </td>
        <td><code>${escapeHtml(c.cpf) || '—'}</code></td>
        <td>${escapeHtml(c.telefone) || '—'}</td>
        <td class="num font-bold">${c.total_compras || 0}</td>
        <td class="num font-bold text-emerald-400">${fmtMoney(c.total_gasto || 0)}</td>
        <td class="muted small">${c.ultima_compra ? fmtDateStr(c.ultima_compra) : 'Nunca'}</td>
        <td style="text-align: right">
          <button type="button" class="btn btn--ghost btn--sm" onclick="window.verDetalhesCliente(${c.id})" title="Ver histórico">
            Histórico
          </button>
          <button type="button" class="btn btn--secondary btn--sm" onclick="window.editarCliente(${c.id})" title="Editar">
            Editar
          </button>
        </td>
      </tr>
    `).join('');
  } catch (err) {
    tbody.innerHTML = `<tr><td colspan="8" class="text-center py-4 text-danger">${err.message || 'Erro ao listar clientes'}</td></tr>`;
  }
}

export function setupClientes() {
  const searchInput = document.getElementById('f-clientes-search');
  if (searchInput) {
    let timer = null;
    searchInput.addEventListener('input', () => {
      clearTimeout(timer);
      timer = setTimeout(() => loadClientes(), 300);
    });
  }

  const btnNovo = document.getElementById('btn-novo-cliente');
  if (btnNovo) {
    btnNovo.addEventListener('click', () => {
      const form = document.getElementById('form-cliente');
      if (form) {
        form.reset();
        document.getElementById('c-id').value = '';
        document.getElementById('modal-cliente-title').textContent = 'Cadastrar Novo Cliente';
      }
      openModal('modal-cliente');
    });
  }

  const form = document.getElementById('form-cliente');
  if (form) {
    form.addEventListener('submit', async (e) => {
      e.preventDefault();
      const cid = document.getElementById('c-id').value;
      const payload = {
        nome: form.nome.value.trim(),
        cpf: form.cpf.value.trim(),
        telefone: form.telefone.value.trim(),
        email: form.email.value.trim(),
        nascimento: form.nascimento.value.trim(),
        obs: form.obs.value.trim()
      };

      try {
        if (cid) {
          await api.put(`/api/clientes/${cid}`, payload);
          showToast('Cliente atualizado com sucesso!', 'success');
        } else {
          await api.post('/api/clientes', payload);
          showToast('Cliente cadastrado com sucesso!', 'success');
        }
        closeModal(document.getElementById('modal-cliente'));
        await loadClientes();
      } catch (err) {
        showToast(err.message || 'Erro ao salvar cliente', 'error');
      }
    });
  }

  // Janela global para botões inline
  window.editarCliente = (id) => {
    const c = clientesCache.find(item => item.id === id);
    if (!c) return;
    const form = document.getElementById('form-cliente');
    if (!form) return;
    document.getElementById('c-id').value = c.id;
    form.nome.value = c.nome || '';
    form.cpf.value = c.cpf || '';
    form.telefone.value = c.telefone || '';
    form.email.value = c.email || '';
    form.nascimento.value = c.nascimento || '';
    form.obs.value = c.obs || '';
    document.getElementById('modal-cliente-title').textContent = `Editar Cliente #${c.id}`;
    openModal('modal-cliente');
  };

  window.verDetalhesCliente = async (id) => {
    const modalBody = document.getElementById('cliente-detalhes-body');
    const modalTitle = document.getElementById('modal-cliente-detalhes-title');
    if (!modalBody) return;
    
    modalBody.innerHTML = '<div class="text-center py-4 muted">Carregando dados do cliente...</div>';
    openModal('modal-cliente-detalhes');

    try {
      const c = await api.get(`/api/clientes/${id}`);
      if (modalTitle) modalTitle.textContent = `${c.nome} (#${c.id})`;

      const vendasHtml = (c.vendas && c.vendas.length > 0)
        ? c.vendas.map(v => `
            <tr>
              <td><code>${v.codigo}</code></td>
              <td>${fmtDateStr(v.data)}</td>
              <td class="num font-bold text-emerald-400">${fmtMoney(v.total)}</td>
              <td><span class="badge ${v.status === 'concluida' ? 'badge--ok' : 'badge--out'}">${v.status}</span></td>
            </tr>
          `).join('')
        : '<tr><td colspan="4" class="text-center muted py-2">Nenhuma compra registrada</td></tr>';

      const valesHtml = (c.vales && c.vales.length > 0)
        ? c.vales.map(vl => `
            <tr>
              <td><strong style="color:var(--brand-300)">${vl.codigo}</strong></td>
              <td class="num">${fmtMoney(vl.valor_original)}</td>
              <td class="num font-bold text-emerald-400">${fmtMoney(vl.saldo)}</td>
              <td><span class="chip">${vl.status}</span></td>
            </tr>
          `).join('')
        : '<tr><td colspan="4" class="text-center muted py-2">Nenhum vale-troca gerado</td></tr>';

      modalBody.innerHTML = `
        <div style="display:grid; grid-template-columns: repeat(auto-fit, minmax(200px, 1fr)); gap:1rem; margin-bottom:1.5rem; background:rgba(255,255,255,0.03); padding:1rem; border-radius:8px; border:1px solid var(--border)">
          <div><small class="muted uppercase">CPF</small><div class="font-bold">${escapeHtml(c.cpf) || 'Não informado'}</div></div>
          <div><small class="muted uppercase">Telefone / WhatsApp</small><div class="font-bold">${escapeHtml(c.telefone) || 'Não informado'}</div></div>
          <div><small class="muted uppercase">E-mail</small><div>${escapeHtml(c.email) || 'Não informado'}</div></div>
          <div><small class="muted uppercase">Nascimento</small><div>${escapeHtml(c.nascimento) || '—'}</div></div>
          ${c.obs ? `<div style="grid-column:1/-1"><small class="muted uppercase">Observações</small><div class="small">${escapeHtml(c.obs)}</div></div>` : ''}
        </div>

        <h3 style="font-size:0.875rem; text-transform:uppercase; color:var(--text-muted); margin-bottom:0.5rem">Vales-Troca</h3>
        <div class="table-wrap" style="margin-bottom:1.5rem">
          <table class="table table--compact">
            <thead><tr><th>Código</th><th class="num">Original</th><th class="num">Saldo Disponível</th><th>Status</th></tr></thead>
            <tbody>${valesHtml}</tbody>
          </table>
        </div>

        <h3 style="font-size:0.875rem; text-transform:uppercase; color:var(--text-muted); margin-bottom:0.5rem">Histórico de Compras</h3>
        <div class="table-wrap">
          <table class="table table--compact">
            <thead><tr><th>Código</th><th>Data</th><th class="num">Valor</th><th>Status</th></tr></thead>
            <tbody>${vendasHtml}</tbody>
          </table>
        </div>
      `;
    } catch (err) {
      modalBody.innerHTML = `<div class="text-center py-4 text-danger">${err.message || 'Erro ao carregar detalhes'}</div>`;
    }
  };
}

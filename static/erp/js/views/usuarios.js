import { api } from '../core/api.js';
import { openModal, closeModal, showToast } from '../core/ui.js';
import { escapeHtml } from '../core/format.js';

let usersList = [];

export async function loadUsuarios() {
  const tbody = document.getElementById('users-body');
  const empty = document.getElementById('users-empty');
  if (!tbody) return;

  try {
    tbody.innerHTML = '<tr><td colspan="7" class="text-center py-4 muted">Carregando usuários...</td></tr>';
    usersList = await api.get('/api/usuarios');
    renderUsersTable();
  } catch (err) {
    tbody.innerHTML = `<tr><td colspan="7" class="text-center py-4 color-red">${escapeHtml(err.message || 'Erro ao carregar usuários')}</td></tr>`;
  }
}

function renderUsersTable() {
  const tbody = document.getElementById('users-body');
  const empty = document.getElementById('users-empty');
  if (!tbody) return;

  if (!usersList || usersList.length === 0) {
    tbody.innerHTML = '';
    if (empty) empty.hidden = false;
    return;
  }
  if (empty) empty.hidden = true;

  tbody.innerHTML = usersList.map(u => {
    const isAtivo = !!u.ativo;
    const roleBadge = u.perfil === 'admin'
      ? '<span class="chip" style="background: rgba(16,185,129,0.15); color: var(--emerald-400); border-color: rgba(16,185,129,0.3)">Administrador</span>'
      : '<span class="chip" style="background: rgba(99,102,241,0.15); color: #818cf8; border-color: rgba(99,102,241,0.3)">Vendedor</span>';
    
    const statusBadge = isAtivo
      ? '<span class="chip" style="color: var(--emerald-400)">Ativo</span>'
      : '<span class="chip" style="color: var(--red-400)">Inativo</span>';

    const descMaxBadge = (u.desconto_max_pct !== null && u.desconto_max_pct !== undefined)
      ? `<span style="font-weight:600; color:var(--text);">${parseFloat(u.desconto_max_pct).toFixed(1)}%</span>`
      : '<span class="muted" style="font-size:0.8rem;">Padrão da loja</span>';

    return `
      <tr>
        <td class="muted">#${u.id}</td>
        <td><strong>${escapeHtml(u.nome)}</strong></td>
        <td><code>${escapeHtml(u.login)}</code></td>
        <td>${roleBadge}</td>
        <td class="num">${parseFloat(u.comissao_pct || 0).toFixed(1)}%</td>
        <td class="num">${descMaxBadge}</td>
        <td>${statusBadge}</td>
        <td style="text-align: right; white-space: nowrap;">
          <button type="button" class="btn btn--ghost btn--sm btn-edit-user" data-id="${u.id}" title="Editar usuário">
            Editar
          </button>
          <button type="button" class="btn btn--ghost btn--sm btn-toggle-user" data-id="${u.id}" data-ativo="${isAtivo}" title="${isAtivo ? 'Desativar usuário' : 'Ativar usuário'}" style="color: ${isAtivo ? 'var(--red-400)' : 'var(--emerald-400)'}">
            ${isAtivo ? 'Desativar' : 'Ativar'}
          </button>
        </td>
      </tr>
    `;
  }).join('');

  // Bind actions
  tbody.querySelectorAll('.btn-edit-user').forEach(btn => {
    btn.addEventListener('click', () => {
      const id = parseInt(btn.dataset.id);
      const user = usersList.find(x => x.id === id);
      if (user) openUserModal(user);
    });
  });

  tbody.querySelectorAll('.btn-toggle-user').forEach(btn => {
    btn.addEventListener('click', async () => {
      const id = parseInt(btn.dataset.id);
      const isAtivo = btn.dataset.ativo === 'true';
      const action = isAtivo ? 'desativar' : 'ativar';
      if (!confirm(`Deseja realmente ${action} este usuário?`)) return;

      try {
        await api.put(`/api/usuarios/${id}`, { ativo: isAtivo ? 0 : 1 });
        showToast(`Usuário ${isAtivo ? 'desativado' : 'ativado'} com sucesso!`, 'success');
        await loadUsuarios();
      } catch (err) {
        showToast(err.message || 'Erro ao alterar status', 'error');
      }
    });
  });
}

function openUserModal(user = null) {
  const modal = document.getElementById('modal-user');
  const form = document.getElementById('form-user');
  const title = document.getElementById('modal-user-title');
  const passHint = document.getElementById('user-pass-hint');
  const passInput = document.getElementById('u-senha');

  if (!modal || !form) return;
  form.reset();

  if (user) {
    title.textContent = 'Editar Usuário';
    form.user_id.value = user.id;
    form.nome.value = user.nome;
    form.login.value = user.login;
    form.perfil.value = user.perfil;
    form.comissao_pct.value = user.comissao_pct || 0;
    if (form.desconto_max_pct) {
      form.desconto_max_pct.value = (user.desconto_max_pct !== null && user.desconto_max_pct !== undefined) ? user.desconto_max_pct : '';
    }
    form.ativo.checked = !!user.ativo;
    passInput.required = false;
    if (passHint) passHint.textContent = 'Deixe em branco para manter a senha atual.';
  } else {
    title.textContent = 'Novo Usuário';
    form.user_id.value = '';
    form.perfil.value = 'vendedor';
    form.comissao_pct.value = '0';
    if (form.desconto_max_pct) {
      form.desconto_max_pct.value = '';
    }
    form.ativo.checked = true;
    passInput.required = true;
    if (passHint) passHint.textContent = 'Mínimo de 6 caracteres.';
  }

  // Atualiza hint do desconto padrão da loja se disponível
  api.get('/api/configuracoes').then(cfg => {
    const hintVal = document.getElementById('u-desc-padrao-val');
    if (hintVal) {
      hintVal.textContent = (cfg.desconto_maximo_vendedor || '10') + '%';
    }
  }).catch(() => {});

  openModal('modal-user');
}

export function setupUsuarios() {
  const btnNew = document.getElementById('btn-new-user');
  if (btnNew) {
    btnNew.addEventListener('click', () => openUserModal(null));
  }

  const form = document.getElementById('form-user');
  if (form) {
    form.addEventListener('submit', async (e) => {
      e.preventDefault();
      const userId = form.user_id.value;
      const isEdit = !!userId;

      const descVal = form.desconto_max_pct ? form.desconto_max_pct.value.trim() : '';

      const payload = {
        nome: form.nome.value.trim(),
        login: form.login.value.trim(),
        perfil: form.perfil.value,
        comissao_pct: parseFloat(form.comissao_pct.value) || 0,
        desconto_max_pct: descVal !== '' ? parseFloat(descVal) : null,
        ativo: form.ativo.checked ? 1 : 0
      };

      if (form.senha.value) {
        payload.senha = form.senha.value;
      }

      try {
        if (isEdit) {
          await api.put(`/api/usuarios/${userId}`, payload);
          showToast('Usuário atualizado com sucesso!', 'success');
        } else {
          if (!payload.senha) {
            showToast('Informe a senha do usuário', 'error');
            return;
          }
          await api.post('/api/usuarios', payload);
          showToast('Usuário criado com sucesso!', 'success');
        }
        closeModal(document.getElementById('modal-user'));
        await loadUsuarios();
      } catch (err) {
        showToast(err.message || 'Erro ao salvar usuário', 'error');
      }
    });
  }
}

export function setupAuthActions() {
  // Logout
  const handleLogout = async () => {
    if (!confirm('Deseja realmente sair do sistema?')) return;
    try {
      await api.post('/api/auth/logout', {});
    } catch (e) {
      // Ignora erro
    }
    window.location.href = '/login';
  };

  const btnLogout = document.getElementById('btn-logout');
  if (btnLogout) btnLogout.addEventListener('click', handleLogout);

  const btnMobileLogout = document.getElementById('btn-mobile-logout');
  if (btnMobileLogout) btnMobileLogout.addEventListener('click', handleLogout);

  // Trocar Senha
  const formSenha = document.getElementById('form-trocar-senha');
  if (formSenha) {
    formSenha.addEventListener('submit', async (e) => {
      e.preventDefault();
      const atual = formSenha.senha_atual.value;
      const nova = formSenha.nova_senha.value;
      const confirma = formSenha.confirma_senha.value;

      if (nova !== confirma) {
        showToast('A nova senha e a confirmação não conferem.', 'error');
        return;
      }
      if (nova.length < 6) {
        showToast('A nova senha deve ter no mínimo 6 caracteres.', 'error');
        return;
      }

      try {
        await api.post('/api/auth/senha', { atual, nova });
        showToast('Senha alterada com sucesso!', 'success');
        formSenha.reset();
        closeModal(document.getElementById('modal-trocar-senha'));
      } catch (err) {
        showToast(err.message || 'Erro ao alterar senha', 'error');
      }
    });
  }
}

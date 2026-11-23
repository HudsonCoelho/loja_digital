import { api } from '../core/api.js';
import { showToast } from '../core/ui.js';

export async function loadConfiguracoes() {
  await Promise.all([
    fetchStoreConfigs(),
    fetchBackupsList(),
    fetchBackupStatus()
  ]);
}

async function fetchStoreConfigs() {
  const form = document.getElementById('form-configuracoes');
  if (!form) return;

  try {
    const cfg = await api.get('/api/configuracoes');
    if (form.loja_nome) form.loja_nome.value = cfg.loja_nome || 'Estilo Único';
    if (form.loja_documento) form.loja_documento.value = cfg.loja_documento || '';
    if (form.loja_endereco) form.loja_endereco.value = cfg.loja_endereco || '';
    if (form.loja_telefone) form.loja_telefone.value = cfg.loja_telefone || '';
    if (form.cupom_rodape) form.cupom_rodape.value = cfg.cupom_rodape || 'Obrigado pela preferência!';
    if (form.dias_produto_parado) form.dias_produto_parado.value = cfg.dias_produto_parado || '60';
    if (form.desconto_maximo_vendedor) form.desconto_maximo_vendedor.value = cfg.desconto_maximo_vendedor || '10';
    if (form.backup_destino_extra) form.backup_destino_extra.value = cfg.backup_destino_extra || '';
  } catch (err) {
    showToast(err.message || 'Erro ao carregar configurações', 'error');
  }
}

async function fetchBackupStatus() {
  const statusEl = document.getElementById('backup-status-banner');
  if (!statusEl) return;

  try {
    const status = await api.get('/api/backup/status');
    const form = document.getElementById('form-configuracoes');

    if (status.destino_efetivo && status.destino_acessivel) {
      const isDrive = status.origem_destino === 'google_drive_auto';
      statusEl.className = 'status-box status-box--ok';
      statusEl.style.cssText = 'margin-bottom:1rem; padding:0.85rem 1rem; border-radius:8px; background:rgba(16, 185, 129, 0.1); border:1px solid rgba(16, 185, 129, 0.3); font-size:0.85rem; line-height:1.4; color:var(--text);';
      statusEl.innerHTML = `
        <strong style="color:var(--emerald-400); display:block; margin-bottom:0.25rem;">
          ${isDrive ? '☁️ Google Drive Detectado e Ativo' : '💾 Destino Extra Ativo'}
        </strong>
        As cópias de segurança estão sendo salvas no disco local e duplicadas para: <br>
        <code style="word-break:break-all;">${status.destino_efetivo}</code>
      `;
    } else if (status.google_drive_detectado) {
      statusEl.className = 'status-box status-box--info';
      statusEl.style.cssText = 'margin-bottom:1rem; padding:0.85rem 1rem; border-radius:8px; background:rgba(59, 130, 246, 0.1); border:1px solid rgba(59, 130, 246, 0.3); font-size:0.85rem; line-height:1.4; color:var(--text);';
      statusEl.innerHTML = `
        <strong style="color:#60a5fa; display:block; margin-bottom:0.25rem;">
          ☁️ Google Drive encontrado no sistema
        </strong>
        Pasta detectada: <code>${status.google_drive_detectado}</code><br>
        <button type="button" class="btn btn--secondary btn--sm" id="btn-usar-gdrive" style="margin-top:0.5rem">
          Definir como destino de backup
        </button>
      `;
      const btnUsar = document.getElementById('btn-usar-gdrive');
      if (btnUsar && form && form.backup_destino_extra) {
        btnUsar.addEventListener('click', () => {
          form.backup_destino_extra.value = status.google_drive_detectado;
          showToast('Google Drive preenchido! Clique em "Salvar Configurações"', 'info');
        });
      }
    } else {
      statusEl.className = 'status-box status-box--warn';
      statusEl.style.cssText = 'margin-bottom:1rem; padding:0.85rem 1rem; border-radius:8px; background:rgba(245, 181, 68, 0.1); border:1px solid rgba(245, 181, 68, 0.3); font-size:0.85rem; line-height:1.4; color:var(--text);';
      statusEl.innerHTML = `
        <strong style="color:var(--warning); display:block; margin-bottom:0.25rem;">
          ⚠️ Destino Extra Não Configurado
        </strong>
        Os backups estão sendo salvos apenas no mesmo disco local (<code>backups/diario/</code>).<br>
        Para proteger o sistema contra falha mecânica/defeito do HD, instale o <strong>Google Drive para Computador</strong> ou conecte um <strong>Pendrive</strong> e informe o caminho no campo acima.
      `;
    }
  } catch (err) {
    console.warn('Erro ao checar status do backup:', err);
  }
}

async function fetchBackupsList() {
  const tbody = document.getElementById('backup-table-body');
  const empty = document.getElementById('backup-empty');
  if (!tbody) return;

  try {
    tbody.innerHTML = '<tr><td colspan="4" class="text-center py-4 muted">Carregando backups...</td></tr>';
    const backups = await api.get('/api/backup/historico');

    if (!backups || backups.length === 0) {
      tbody.innerHTML = '';
      if (empty) empty.hidden = false;
      return;
    }
    if (empty) empty.hidden = true;

    tbody.innerHTML = backups.map(b => `
      <tr>
        <td><code>${b.nome}</code></td>
        <td>${b.criado_em}</td>
        <td class="num">${b.tamanho_fmt}</td>
        <td style="text-align: right">
          <a href="/api/backup/download/${encodeURIComponent(b.nome)}" class="btn btn--ghost btn--sm" download>
            Baixar Cópia (.db)
          </a>
        </td>
      </tr>
    `).join('');
  } catch (err) {
    tbody.innerHTML = `<tr><td colspan="4" class="text-center py-4 text-danger">${err.message || 'Erro ao listar backups'}</td></tr>`;
  }
}

export function setupConfiguracoes() {
  const form = document.getElementById('form-configuracoes');
  if (form) {
    form.addEventListener('submit', async (e) => {
      e.preventDefault();
      const payload = {
        loja_nome: form.loja_nome.value.trim(),
        loja_documento: form.loja_documento.value.trim(),
        loja_endereco: form.loja_endereco.value.trim(),
        loja_telefone: form.loja_telefone.value.trim(),
        cupom_rodape: form.cupom_rodape.value.trim(),
        dias_produto_parado: form.dias_produto_parado.value.trim(),
        desconto_maximo_vendedor: form.desconto_maximo_vendedor ? form.desconto_maximo_vendedor.value.trim() : '10',
        backup_destino_extra: form.backup_destino_extra.value.trim()
      };

      try {
        await api.post('/api/configuracoes', payload);
        showToast('Configurações salvas com sucesso!', 'success');
        await fetchBackupStatus();
      } catch (err) {
        showToast(err.message || 'Erro ao salvar configurações', 'error');
      }
    });
  }

  const btnBackup = document.getElementById('btn-fazer-backup');
  if (btnBackup) {
    btnBackup.addEventListener('click', async () => {
      btnBackup.disabled = true;
      btnBackup.textContent = 'Gerando backup...';
      try {
        const res = await api.post('/api/backup/executar', {});
        let msg = `Backup gerado com sucesso: ${res.arquivo}`;
        if (res.copiado_extra) {
          msg += ' (cópia duplicada na pasta de nuvem/pendrive!)';
        } else if (res.erro_extra) {
          msg += ` (Aviso: cópia extra falhou: ${res.erro_extra})`;
        }
        showToast(msg, res.copiado_extra ? 'success' : 'warning');
        await fetchBackupsList();
        await fetchBackupStatus();
      } catch (err) {
        showToast(err.message || 'Erro ao gerar backup', 'error');
      } finally {
        btnBackup.disabled = false;
        btnBackup.innerHTML = '<svg class="icon"><use href="#i-box"/></svg> Fazer Backup Agora';
      }
    });
  }
}

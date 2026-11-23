import { api } from '../core/api.js';
import { showToast, openModal, closeModal } from '../core/ui.js';
import { fmtMoney, fmtDateStr, escapeHtml } from '../core/format.js';

const els = {
  chipStatus: document.getElementById('chip-register-status'),
  btnManage: document.getElementById('btn-manage-register'),
  posOverlay: document.getElementById('pos-overlay'),
  posMain: document.getElementById('pos-main'),
  
  formOpen: document.getElementById('form-open-register'),
  formMov: document.getElementById('form-register-mov'),
  formClose: document.getElementById('form-close-register'),
  
  movsTable: document.querySelector('#reg-movs-table tbody'),
  closeDiff: document.getElementById('reg-close-diff'),
  btnSubmitClose: document.getElementById('btn-submit-close-register'),
  
  tabs: document.querySelectorAll('#modal-register .tab'),
  tabPanels: document.querySelectorAll('#modal-register .tab-panel'),
  footFechar: document.getElementById('reg-foot-fechar')
};

let currentState = 'fechado';
let currentPreview = null;

export async function initRegister() {
  await checkStatus();
  setupListeners();
}

async function checkStatus() {
  try {
    const res = await api.get('/api/caixa/status');
    currentState = res.status;
    updateUI();
  } catch (e) {
    console.error('Erro ao verificar status do caixa', e);
  }
}

function updateUI() {
  if (currentState === 'aberto') {
    els.chipStatus.innerHTML = '<span class="pulse" aria-hidden="true"></span> Caixa aberto';
    els.chipStatus.style.color = 'var(--emerald-400)';
    els.chipStatus.style.borderColor = 'var(--emerald-500)';
    els.btnManage.dataset.openModal = 'modal-register';
    
    if (els.posOverlay) els.posOverlay.hidden = true;
    if (els.posMain) {
      els.posMain.style.opacity = '1';
      els.posMain.style.pointerEvents = 'auto';
    }
  } else {
    els.chipStatus.innerHTML = '<span class="pulse" aria-hidden="true" style="background:var(--red-500)"></span> Caixa fechado';
    els.chipStatus.style.color = 'var(--gray-300)';
    els.chipStatus.style.borderColor = 'var(--gray-700)';
    els.btnManage.dataset.openModal = 'modal-open-register';
    
    if (els.posOverlay) els.posOverlay.hidden = false;
    if (els.posMain) {
      els.posMain.style.opacity = '0.5';
      els.posMain.style.pointerEvents = 'none';
    }
  }
}

function setupListeners() {
  if (els.formOpen) {
    els.formOpen.addEventListener('submit', async (e) => {
      e.preventDefault();
      const val = parseFloat(els.formOpen.valor_abertura.value);
      try {
        await api.post('/api/caixa/abrir', { valor_abertura: val });
        showToast('Caixa aberto com sucesso!', 'success');
        closeModal(document.getElementById('modal-open-register'));
        els.formOpen.reset();
        await checkStatus();
      } catch (err) {
        showToast(err.message || 'Erro ao abrir caixa', 'error');
      }
    });
  }

  if (els.formMov) {
    els.formMov.addEventListener('submit', async (e) => {
      e.preventDefault();
      const payload = {
        tipo: els.formMov.tipo.value,
        valor: parseFloat(els.formMov.valor.value),
        motivo: els.formMov.motivo.value
      };
      try {
        await api.post('/api/caixa/movimento', payload);
        showToast('Movimento registrado com sucesso!', 'success');
        els.formMov.reset();
        loadMovimentos();
      } catch (err) {
        showToast(err.message || 'Erro ao registrar movimento', 'error');
      }
    });
  }

  // Tabs logic inside modal
  els.tabs.forEach(tab => {
    tab.addEventListener('click', () => {
      els.tabs.forEach(t => t.classList.remove('is-active'));
      els.tabPanels.forEach(p => p.hidden = true);
      
      tab.classList.add('is-active');
      const target = document.getElementById(tab.dataset.target);
      if (target) target.hidden = false;
      
      if (tab.dataset.target === 'tab-fechar') {
        els.footFechar.hidden = false;
        loadPreview();
      } else {
        els.footFechar.hidden = true;
      }
    });
  });

  els.btnManage.addEventListener('click', () => {
    if (currentState === 'aberto') {
      loadMovimentos();
      els.tabs[0].click(); // Reset to first tab
    }
  });

  if (els.formClose) {
    els.formClose.addEventListener('input', calculateDiff);
  }

  if (els.btnSubmitClose) {
    els.btnSubmitClose.addEventListener('click', async () => {
      if (!confirm('Deseja realmente encerrar o turno e fechar o caixa?')) return;
      
      const contagem = {
        Dinheiro: parseFloat(els.formClose.Dinheiro.value) || 0,
        Pix: parseFloat(els.formClose.Pix.value) || 0,
        "Débito": parseFloat(els.formClose['Débito'].value) || 0,
        "Crédito": parseFloat(els.formClose['Crédito'].value) || 0
      };

      try {
        const res = await api.post('/api/caixa/fechar', { contagem });
        showToast('Caixa fechado com sucesso!', 'success');
        closeModal(document.getElementById('modal-register'));
        els.formClose.reset();
        els.closeDiff.textContent = 'R$ 0,00';
        els.closeDiff.style.color = '';
        await checkStatus();
      } catch (err) {
        showToast(err.message || 'Erro ao fechar caixa', 'error');
      }
    });
  }
}

async function loadMovimentos() {
  if (!els.movsTable) return;
  try {
    const movs = await api.get('/api/caixa/movimentos');
    els.movsTable.innerHTML = movs.map(m => `
      <tr>
        <td>${m.data.split(' ')[1].substring(0,5)}</td>
        <td><span class="chip">${escapeHtml(m.tipo)}</span></td>
        <td>${escapeHtml(m.motivo)}</td>
        <td>${escapeHtml(m.usuario || '-')}</td>
        <td class="num ${m.tipo === 'sangria' ? 'color-red' : 'color-emerald'}">
          ${m.tipo === 'sangria' ? '−' : '+'}${fmtMoney(m.valor)}
        </td>
      </tr>
    `).join('') || '<tr><td colspan="5" class="muted text-center py-4">Nenhum movimento registrado neste turno.</td></tr>';
  } catch (err) {
    console.error('Erro ao carregar movimentos', err);
  }
}

async function loadPreview() {
  try {
    currentPreview = await api.get('/api/caixa/fechamento-preview');
    if (currentPreview && currentPreview.esperado) {
      const esp = currentPreview.esperado;
      const setVal = (id, val) => {
        const el = document.getElementById(id);
        if (el) el.textContent = fmtMoney(val || 0);
      };
      setVal('reg-esp-dinheiro', esp.Dinheiro);
      setVal('reg-esp-pix', esp.Pix);
      setVal('reg-esp-debito', esp['Débito']);
      setVal('reg-esp-credito', esp['Crédito']);
      setVal('reg-esp-vale', esp['Vale-Troca'] || esp['Vale-troca']);
    }

    // Renderiza resumo por vendedor (somente para admin - decisão de 14/10/2026)
    const wrapVend = document.getElementById('reg-close-vendedores-wrap');
    const ehAdmin = Boolean(window.currentUser && window.currentUser.perfil === 'admin');
    const vendedores = currentPreview && currentPreview.por_vendedor;

    if (wrapVend) {
      if (!ehAdmin || !vendedores) {
        wrapVend.hidden = true;
        wrapVend.style.display = 'none';
      } else {
        wrapVend.hidden = false;
        wrapVend.style.display = '';
        const tbodyVend = document.getElementById('reg-vendedores-tbody');
        if (tbodyVend) {
          if (vendedores.length === 0) {
            tbodyVend.innerHTML = '<tr><td colspan="7" class="text-center py-2 muted small">Nenhuma venda registrada neste turno.</td></tr>';
          } else {
            tbodyVend.innerHTML = vendedores.map(v => `
              <tr>
                <td><strong>${escapeHtml(v.vendedor_nome)}</strong></td>
                <td class="num">${fmtMoney(v.dinheiro)}</td>
                <td class="num">${fmtMoney(v.pix)}</td>
                <td class="num">${fmtMoney(v.debito)}</td>
                <td class="num">${fmtMoney(v.credito)}</td>
                <td class="num">${fmtMoney(v.vale_troca)}</td>
                <td class="num font-bold text-emerald-400">${fmtMoney(v.total)}</td>
              </tr>
            `).join('');
          }
        }
      }
    }

    calculateDiff();
  } catch (err) {
    showToast(err.message || 'Erro ao carregar resumo de fechamento', 'error');
  }
}

function calculateDiff() {
  if (!currentPreview) return;
  const esp = currentPreview.esperado;
  let totEsp = (esp.Dinheiro||0) + (esp.Pix||0) + (esp['Débito']||0) + (esp['Crédito']||0);
  
  let totCont = 
    (parseFloat(els.formClose.Dinheiro.value) || 0) +
    (parseFloat(els.formClose.Pix.value) || 0) +
    (parseFloat(els.formClose['Débito'].value) || 0) +
    (parseFloat(els.formClose['Crédito'].value) || 0);

  const diff = totCont - totEsp;
  
  els.closeDiff.textContent = fmtMoney(Math.abs(diff));
  if (diff < -0.01) {
    els.closeDiff.textContent = '− ' + fmtMoney(Math.abs(diff));
    els.closeDiff.style.color = 'var(--red-400)';
  } else if (diff > 0.01) {
    els.closeDiff.textContent = '+ ' + fmtMoney(diff);
    els.closeDiff.style.color = 'var(--emerald-400)';
  } else {
    els.closeDiff.textContent = 'R$ 0,00';
    els.closeDiff.style.color = 'var(--gray-300)';
  }
}

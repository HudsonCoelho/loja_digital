import { api } from '../core/api.js';
import { fmtMoney, fmtDateStr } from '../core/format.js';
import { showToast, openModal, closeModal } from '../core/ui.js';

let fornecedoresCache = [];
let produtosListaCache = [];
let produtosVariacoesCache = [];
let entradaLinhasItens = [];
let produtosNovosNaNota = new Set();
let proximoIdLinha = 1;

export function normalizarNome(str) {
  return (str || '')
    .normalize('NFD')
    .replace(/[\u0300-\u036f]/g, '')
    .toLowerCase()
    .replace(/\s+/g, ' ')
    .trim();
}

function escapeHtml(str) {
  return (str || '')
    .replace(/&/g, '&amp;')
    .replace(/</g, '&lt;')
    .replace(/>/g, '&gt;')
    .replace(/"/g, '&quot;')
    .replace(/'/g, '&#039;');
}

export async function loadEntradasView() {
  await Promise.all([
    fetchEntradas(),
    fetchFornecedores(),
    carregarOpcoesProdutos()
  ]);
}

export async function carregarOpcoesProdutos() {
  try {
    const prods = await api.get('/api/produtos?_=' + Date.now());
    produtosListaCache = prods;
    window.produtosListaCache = prods;

    const flat = [];
    prods.forEach(p => {
      (p.variacoes || []).forEach(v => {
        flat.push({
          variacao_id: v.id,
          produto_id: p.id,
          nome: p.nome,
          tamanho: v.tamanho,
          cor: v.cor,
          estoque: v.estoque,
          sku: v.sku || '',
          codigo_barras: v.codigo_barras || '',
          img: p.img || '',
          label: `${p.nome} — ${v.tamanho} / ${v.cor} (Atual: ${v.estoque} un)`,
          custo_padrao: p.custo || p.preco_custo || 0
        });
      });
    });
    produtosVariacoesCache = flat;
    return flat;
  } catch (err) {
    console.warn('Erro ao carregar lista de variações para entrada:', err);
    return [];
  }
}

async function fetchEntradas() {
  const tbody = document.getElementById('entradas-table-body');
  const empty = document.getElementById('entradas-empty');
  if (!tbody) return;

  try {
    tbody.innerHTML = '<tr><td colspan="7" class="text-center py-4 muted">Carregando entradas...</td></tr>';
    const entradas = await api.get('/api/entradas');

    if (!entradas || entradas.length === 0) {
      tbody.innerHTML = '';
      if (empty) empty.hidden = false;
      return;
    }
    if (empty) empty.hidden = true;

    tbody.innerHTML = entradas.map(e => `
      <tr>
        <td class="id-cell">#${e.id}</td>
        <td><strong>${e.numero_nota || 'S/N'}</strong></td>
        <td>${fmtDateStr(e.data)}</td>
        <td>${e.fornecedor_nome || 'Não informado'}</td>
        <td class="num font-bold">${e.total_pecas || 0} pçs (${e.total_itens || 0} itens)</td>
        <td class="num font-bold text-emerald-400">${fmtMoney(e.total || 0)}</td>
        <td style="text-align: right">
          <button type="button" class="btn btn--ghost btn--sm" onclick="window.verDetalhesEntrada(${e.id})">
            Ver Itens
          </button>
        </td>
      </tr>
    `).join('');
  } catch (err) {
    tbody.innerHTML = `<tr><td colspan="7" class="text-center py-4 text-danger">${err.message || 'Erro ao listar entradas'}</td></tr>`;
  }
}

async function fetchFornecedores() {
  const tbody = document.getElementById('fornecedores-table-body');
  const empty = document.getElementById('fornecedores-empty');
  const selectForn = document.getElementById('entrada-fornecedor');
  if (!tbody) return;

  try {
    tbody.innerHTML = '<tr><td colspan="7" class="text-center py-4 muted">Carregando fornecedores...</td></tr>';
    const forns = await api.get('/api/fornecedores');
    fornecedoresCache = forns;

    if (selectForn) {
      selectForn.innerHTML = '<option value="">Sem fornecedor / Compra direta</option>' +
        forns.map(f => `<option value="${f.id}">${f.nome} ${f.cnpj ? `(${f.cnpj})` : ''}</option>`).join('');
    }

    if (!forns || forns.length === 0) {
      tbody.innerHTML = '';
      if (empty) empty.hidden = false;
      return;
    }
    if (empty) empty.hidden = true;

    tbody.innerHTML = forns.map(f => `
      <tr>
        <td class="id-cell">#${f.id}</td>
        <td><strong>${f.nome}</strong></td>
        <td><code>${f.cnpj || '—'}</code></td>
        <td>${f.telefone || '—'}</td>
        <td>${f.contato || f.email || '—'}</td>
        <td class="num">${f.total_entradas || 0}</td>
        <td style="text-align: right">
          <button type="button" class="btn btn--secondary btn--sm" onclick="window.editarFornecedor(${f.id})">
            Editar
          </button>
        </td>
      </tr>
    `).join('');
  } catch (err) {
    tbody.innerHTML = `<tr><td colspan="7" class="text-center py-4 text-danger">${err.message || 'Erro ao listar fornecedores'}</td></tr>`;
  }
}

export function setupEntradas() {
  // Tabs da view de Entradas / Fornecedores
  const tabs = document.querySelectorAll('#view-entradas .tab');
  tabs.forEach(tab => {
    tab.addEventListener('click', () => {
      tabs.forEach(t => t.classList.remove('is-active'));
      tab.classList.add('is-active');
      const targetId = tab.dataset.target;
      document.querySelectorAll('#view-entradas .tab-panel').forEach(p => {
        p.hidden = p.id !== targetId;
        p.classList.toggle('is-active', p.id === targetId);
      });
    });
  });

  // Botão Nova Entrada
  const btnNovaEntrada = document.getElementById('btn-nova-entrada');
  if (btnNovaEntrada) {
    btnNovaEntrada.addEventListener('click', async () => {
      const form = document.getElementById('form-entrada');
      if (form) form.reset();
      produtosNovosNaNota = new Set();
      if (!produtosVariacoesCache || produtosVariacoesCache.length === 0) {
        await carregarOpcoesProdutos();
      }
      entradaLinhasItens = [];
      adicionarLinhaEntradaItem();
      renderLinhasEntrada();

      const searchInput = document.getElementById('entrada-search-input');
      const searchResults = document.getElementById('entrada-search-results');
      const similarAlert = document.getElementById('entrada-similar-alert');
      if (searchInput) searchInput.value = '';
      if (searchResults) { searchResults.hidden = true; searchResults.innerHTML = ''; }
      if (similarAlert) { similarAlert.hidden = true; similarAlert.innerHTML = ''; }

      openModal('modal-entrada');
      setTimeout(() => searchInput?.focus(), 150);
    });
  }

  // Campo de Busca de Produtos Recebidos
  setupBuscaRecebidos();

  // Adicionar item manual na entrada
  const btnAddItem = document.getElementById('btn-add-entrada-item');
  if (btnAddItem) {
    btnAddItem.addEventListener('click', () => {
      adicionarLinhaEntradaItem();
      renderLinhasEntrada();
    });
  }

  // Entrada em Grade (Fase 2)
  setupEntradaGrade();

  // Form submit da Entrada
  const formEntrada = document.getElementById('form-entrada');
  if (formEntrada) {
    formEntrada.addEventListener('submit', async (e) => {
      e.preventDefault();
      if (entradaLinhasItens.length === 0) {
        showToast('Adicione ao menos um produto para dar entrada', 'warning');
        return;
      }

      const itens = [];
      for (const linha of entradaLinhasItens) {
        const sel = document.getElementById(`entrada-var-${linha.id}`);
        const qtdEl = document.getElementById(`entrada-qtd-${linha.id}`);
        const custoEl = document.getElementById(`entrada-custo-${linha.id}`);
        const vid = parseInt(sel?.value);
        const qtd = parseInt(qtdEl?.value);
        const custo = parseFloat(custoEl?.value) || 0;

        if (!vid) {
          showToast('Selecione o produto de todas as linhas adicionadas', 'warning');
          return;
        }
        if (!qtd || qtd <= 0) {
          showToast('A quantidade de peças deve ser maior que zero', 'warning');
          return;
        }
        itens.push({ variacao_id: vid, quantidade: qtd, custo_unit: custo });
      }

      const fornecedorId = formEntrada.fornecedor_id.value;
      const payload = {
        fornecedor_id: fornecedorId ? parseInt(fornecedorId) : null,
        numero_nota: formEntrada.numero_nota.value.trim(),
        obs: formEntrada.obs.value.trim(),
        itens
      };

      const btnSave = document.getElementById('btn-save-entrada');
      if (btnSave) { btnSave.disabled = true; btnSave.textContent = 'Processando nota...'; }

      try {
        const res = await api.post('/api/entradas', payload);
        showToast(`Entrada #${res.entrada_id} registrada! ${res.itens_processados} itens adicionados ao estoque.`, 'success');
        closeModal(document.getElementById('modal-entrada'));
        await fetchEntradas();
        await carregarOpcoesProdutos();
      } catch (err) {
        showToast(err.message || 'Erro ao registrar entrada', 'error');
      } finally {
        if (btnSave) { btnSave.disabled = false; btnSave.textContent = 'Confirmar e Alimentar Estoque'; }
      }
    });
  }

  // Fornecedores
  setupFornecedoresHandlers();
}

function setupBuscaRecebidos() {
  const searchInput = document.getElementById('entrada-search-input');
  const searchResults = document.getElementById('entrada-search-results');
  const similarAlert = document.getElementById('entrada-similar-alert');

  if (!searchInput || !searchResults) return;

  searchInput.addEventListener('input', () => {
    const q = searchInput.value.trim();
    if (!q) {
      searchResults.hidden = true;
      searchResults.innerHTML = '';
      if (similarAlert) similarAlert.hidden = true;
      return;
    }

    const qLower = q.toLowerCase();
    const qNorm = normalizarNome(q);

    // 1. Aviso de nome parecido (compara sem acento, minúsculas, espaços colapsados)
    if (similarAlert) {
      if (qNorm.length >= 3) {
        const prodParecido = (produtosListaCache || []).find(p => {
          const pNorm = normalizarNome(p.nome);
          return pNorm === qNorm && p.nome.toLowerCase() !== qLower;
        });

        if (prodParecido) {
          similarAlert.innerHTML = `
            <div style="display:flex; justify-content:space-between; align-items:center; padding:0.6rem 0.85rem; background:rgba(245,181,68,0.12); border:1px solid var(--warning); border-radius:var(--radius-sm); font-size:0.83rem;">
              <span>⚠️ Já existe o produto cadastrado <strong>${escapeHtml(prodParecido.nome)}</strong>. Deseja usá-lo?</span>
              <button type="button" class="btn btn--secondary btn--xs" id="btn-usar-prod-similar">
                Usar "${escapeHtml(prodParecido.nome)}"
              </button>
            </div>
          `;
          similarAlert.hidden = false;
          const btnUsar = document.getElementById('btn-usar-prod-similar');
          if (btnUsar) {
            btnUsar.addEventListener('click', () => {
              searchInput.value = prodParecido.nome;
              similarAlert.hidden = true;
              searchInput.dispatchEvent(new Event('input'));
            });
          }
        } else {
          similarAlert.hidden = true;
        }
      } else {
        similarAlert.hidden = true;
      }
    }

    // 2. Filtra variações por nome, código de barras, SKU, tamanho, cor
    const matches = (produtosVariacoesCache || []).filter(p => {
      const nomeNorm = normalizarNome(p.nome);
      return (
        (p.codigo_barras && p.codigo_barras.toLowerCase() === qLower) ||
        (p.codigo_barras && p.codigo_barras.toLowerCase().includes(qLower)) ||
        (p.sku && p.sku.toLowerCase() === qLower) ||
        (p.sku && p.sku.toLowerCase().includes(qLower)) ||
        (nomeNorm && nomeNorm.includes(qNorm)) ||
        (p.tamanho && p.tamanho.toLowerCase() === qLower) ||
        (p.cor && p.cor.toLowerCase().includes(qLower)) ||
        String(p.produto_id) === q ||
        String(p.variacao_id) === q
      );
    }).slice(0, 12);

    if (matches.length === 0) {
      searchResults.innerHTML = `
        <li style="padding:1rem; text-align:center; color:var(--text-muted); cursor:default">
          <p style="margin-bottom:0.6rem; font-size:0.875rem">Nenhum produto encontrado para "<strong>${escapeHtml(q)}</strong>".</p>
          <button type="button" class="btn btn--primary btn--sm" id="btn-cadastrar-rapido-vazio">
            + Cadastrar «${escapeHtml(q)}»
          </button>
        </li>
      `;
      searchResults.hidden = false;
      const btnCadVazio = document.getElementById('btn-cadastrar-rapido-vazio');
      if (btnCadVazio) {
        btnCadVazio.addEventListener('click', () => abrirCadastroRapido(q));
      }
      return;
    }

    searchResults.innerHTML = matches.map(m => {
      const estoqueBadge = m.estoque === 0
        ? `<span class="badge badge--out" style="font-size:0.65rem; font-weight:700;">Estoque 0</span>`
        : `<span class="muted small">Estoque: <strong>${m.estoque} un</strong></span>`;

      return `
        <li class="result entrada-search-hit" data-vid="${m.variacao_id}" style="padding:0.6rem 0.8rem; cursor:pointer; display:grid; grid-template-columns: 40px 1fr auto; align-items:center; gap:0.75rem; border-bottom:1px solid var(--border)">
          <img src="${m.img || '/static/erp/img/placeholder.svg'}" onerror="this.onerror=null;this.src='/static/erp/img/placeholder.svg'" alt="" style="width:40px; height:40px; border-radius:var(--radius-sm); object-fit:cover;">
          <div>
            <div style="font-weight:600; font-size:0.875rem; display:flex; align-items:center; gap:6px; flex-wrap:wrap;">
              ${escapeHtml(m.nome)}
              <span class="badge" style="font-size:0.7rem">${m.tamanho} / ${m.cor}</span>
              <span class="badge badge--ok" style="font-size:0.65rem">Cadastrado</span>
            </div>
            <div class="small" style="margin-top:2px; display:flex; gap:8px; align-items:center; flex-wrap:wrap;">
              ${estoqueBadge}
              <span class="muted">| Custo: <strong>${fmtMoney(m.custo_padrao || 0)}</strong></span>
              ${m.codigo_barras ? `<span class="muted">| EAN: <code>${m.codigo_barras}</code></span>` : ''}
              ${m.sku ? `<span class="muted">| SKU: <code>${m.sku}</code></span>` : ''}
            </div>
          </div>
          <button type="button" class="btn btn--secondary btn--sm" style="pointer-events:none">
            + Inserir
          </button>
        </li>
      `;
    }).join('');

    searchResults.hidden = false;
  });

  searchResults.addEventListener('click', (e) => {
    const hit = e.target.closest('.entrada-search-hit');
    if (hit) {
      const vid = parseInt(hit.dataset.vid);
      adicionarProdutoPorBusca(vid);
      searchInput.value = '';
      searchResults.hidden = true;
      if (similarAlert) similarAlert.hidden = true;
    }
  });

  searchInput.addEventListener('keydown', (e) => {
    if (e.key === 'Enter') {
      e.preventDefault();
      const q = searchInput.value.trim();
      if (!q) return;

      const qLower = q.toLowerCase();

      // 1. Procura match exato por código de barras ou SKU (leitor com Enter)
      const matchCodigo = (produtosVariacoesCache || []).find(v => 
        (v.codigo_barras && v.codigo_barras.trim().toLowerCase() === qLower) ||
        (v.sku && v.sku.trim().toLowerCase() === qLower)
      );

      if (matchCodigo) {
        adicionarProdutoPorBusca(matchCodigo.variacao_id);
        searchInput.value = '';
        searchResults.hidden = true;
        if (similarAlert) similarAlert.hidden = true;
        showToast(`Adicionado à nota: ${matchCodigo.nome} (${matchCodigo.tamanho}/${matchCodigo.cor})`, 'success');
        return;
      }

      // 2. Se houver primeiro resultado na lista de busca
      const firstHit = searchResults.querySelector('.entrada-search-hit');
      if (firstHit && !searchResults.hidden) {
        const vid = parseInt(firstHit.dataset.vid);
        adicionarProdutoPorBusca(vid);
        searchInput.value = '';
        searchResults.hidden = true;
        if (similarAlert) similarAlert.hidden = true;
        return;
      }

      // 3. Código ou nome inexistente: abre cadastro rápido
      abrirCadastroRapido(q);
    } else if (e.key === 'Escape') {
      searchResults.hidden = true;
      if (similarAlert) similarAlert.hidden = true;
    }
  });

  document.addEventListener('click', (e) => {
    if (!e.target.closest('#entrada-search-input') && !e.target.closest('#entrada-search-results')) {
      searchResults.hidden = true;
    }
  });
}

export function abrirCadastroRapido(termo) {
  const formProd = document.getElementById('form-product');
  if (formProd) {
    formProd.reset();
    const pName = document.getElementById('p-name');
    const pBarcode = document.getElementById('p-barcode');
    
    // Se for numérico (com cara de EAN-13 / código de barras)
    if (/^\d{6,14}$/.test(termo.trim())) {
      if (pBarcode) pBarcode.value = termo.trim();
    } else {
      if (pName) pName.value = termo.trim();
    }

    // Registra callback para quando o produto for salvo
    window.onProdutoCadastradoNaEntrada = async (novoProd) => {
      await carregarOpcoesProdutos();
      if (novoProd && novoProd.variacoes) {
        novoProd.variacoes.forEach(v => {
          produtosNovosNaNota.add(v.id);
          adicionarLinhaEntradaItem(v.id, novoProd.preco_custo || 0, 1);
        });
      }
      renderLinhasEntrada();
      openModal('modal-entrada');
      showToast(`Produto "${novoProd.nome}" cadastrado e variações inseridas na nota!`, 'success');
    };

    closeModal(document.getElementById('modal-entrada'));
    openModal('modal-product');
    setTimeout(() => {
      if (!pName?.value) pName?.focus();
      else document.getElementById('p-price')?.focus();
    }, 150);
  }
}

function adicionarLinhaEntradaItem(variacaoId = null, custoUnit = null, qtd = 1) {
  sincronizarValoresLinhas();
  const id = proximoIdLinha++;
  entradaLinhasItens.push({ 
    id, 
    variacao_id: variacaoId, 
    custo_unit: custoUnit, 
    quantidade: qtd 
  });
  return id;
}

function sincronizarValoresLinhas() {
  for (const linha of entradaLinhasItens) {
    const sel = document.getElementById(`entrada-var-${linha.id}`);
    const qtdEl = document.getElementById(`entrada-qtd-${linha.id}`);
    const custoEl = document.getElementById(`entrada-custo-${linha.id}`);
    if (sel && sel.value) linha.variacao_id = parseInt(sel.value);
    if (qtdEl && qtdEl.value) linha.quantidade = parseInt(qtdEl.value) || 1;
    if (custoEl && custoEl.value !== '') linha.custo_unit = parseFloat(custoEl.value) || 0;
  }
}

function adicionarProdutoPorBusca(variacaoId) {
  sincronizarValoresLinhas();
  const vInfo = produtosVariacoesCache.find(p => p.variacao_id === variacaoId);
  if (!vInfo) return;

  // Se já existe uma linha com essa variação na nota, incrementa +1 peça
  const linhaExistente = entradaLinhasItens.find(l => l.variacao_id === variacaoId);
  if (linhaExistente) {
    linhaExistente.quantidade = (parseInt(linhaExistente.quantidade) || 1) + 1;
    renderLinhasEntrada();
    destacarLinha(linhaExistente.id);
    showToast(`+1 un para ${vInfo.nome} (${vInfo.tamanho})`, 'info');
    return;
  }

  // Se a primeira linha estiver vazia, preenche ela
  const primeiraVazia = entradaLinhasItens.find(l => !l.variacao_id);
  if (primeiraVazia) {
    primeiraVazia.variacao_id = variacaoId;
    primeiraVazia.quantidade = 1;
    primeiraVazia.custo_unit = vInfo.custo_padrao || 0;
    renderLinhasEntrada();
    destacarLinha(primeiraVazia.id);
    return;
  }

  // Senão cria nova linha
  const novoId = proximoIdLinha++;
  entradaLinhasItens.push({
    id: novoId,
    variacao_id: variacaoId,
    quantidade: 1,
    custo_unit: vInfo.custo_padrao || 0
  });
  renderLinhasEntrada();
  destacarLinha(novoId);
}

function destacarLinha(linhaId) {
  setTimeout(() => {
    const el = document.getElementById(`entrada-qtd-${linhaId}`);
    if (el) {
      el.focus();
      el.select();
      const card = el.closest('.card');
      if (card) {
        card.style.borderColor = 'var(--brand-500)';
        card.scrollIntoView({ behavior: 'smooth', block: 'nearest' });
        setTimeout(() => { card.style.borderColor = 'var(--border)'; }, 1000);
      }
    }
  }, 60);
}

function renderLinhasEntrada() {
  const container = document.getElementById('entrada-itens-container');
  if (!container) return;

  container.innerHTML = entradaLinhasItens.map(linha => {
    const optionsHtml = produtosVariacoesCache.map(p => 
      `<option value="${p.variacao_id}" data-custo="${p.custo_padrao}" ${linha.variacao_id === p.variacao_id ? 'selected' : ''}>${escapeHtml(p.label)}</option>`
    ).join('');

    const custoVal = (linha.custo_unit !== undefined && linha.custo_unit !== null)
      ? Number(linha.custo_unit).toFixed(2)
      : '0.00';

    const isNovo = linha.variacao_id && produtosNovosNaNota.has(linha.variacao_id);
    const tagNovo = isNovo ? `<span class="badge" style="font-size:0.65rem; background:rgba(99,102,241,0.2); color:var(--brand-300);">Produto Novo</span>` : '';

    return `
      <div class="card entrada-item-card" style="margin-bottom:0.6rem; padding:0.65rem 0.85rem; display:grid; grid-template-columns: 2fr 90px 110px 42px; gap:0.6rem; align-items:center;">
        <div class="field entrada-col-prod" style="margin:0">
          <label class="field__label" style="font-size:0.75rem; display:flex; justify-content:space-between;">
            <span>Produto & Grade</span>
            ${tagNovo}
          </label>
          <select class="input select" id="entrada-var-${linha.id}" required onchange="window.onEntradaVarChange(${linha.id})">
            <option value="">Selecione o produto...</option>
            ${optionsHtml}
          </select>
        </div>
        <div class="field" style="margin:0">
          <label class="field__label" style="font-size:0.75rem">Qtd Peças</label>
          <input class="input input--qty" type="number" id="entrada-qtd-${linha.id}" min="1" value="${linha.quantidade || 1}" required oninput="window.calcTotalEntrada()">
        </div>
        <div class="field" style="margin:0">
          <label class="field__label" style="font-size:0.75rem">Custo Unit.</label>
          <div class="input-money">
            <span class="input-money__prefix">R$</span>
            <input class="input input--money" type="number" id="entrada-custo-${linha.id}" min="0" step="0.01" value="${custoVal}" oninput="window.calcTotalEntrada()">
          </div>
        </div>
        <div>
          <button type="button" class="btn btn--icon btn--ghost" style="color:var(--danger); height:40px; width:40px; margin-top:14px;" onclick="window.removerLinhaEntrada(${linha.id})" title="Remover item">
            <svg class="icon"><use href="#i-trash"/></svg>
          </button>
        </div>
      </div>
    `;
  }).join('');

  window.calcTotalEntrada();
}

window.removerLinhaEntrada = (linhaId) => {
  if (entradaLinhasItens.length <= 1) {
    showToast('A entrada precisa de pelo menos um produto', 'warning');
    return;
  }
  entradaLinhasItens = entradaLinhasItens.filter(l => l.id !== linhaId);
  renderLinhasEntrada();
};

window.onEntradaVarChange = (linhaId) => {
  const sel = document.getElementById(`entrada-var-${linhaId}`);
  const custoInput = document.getElementById(`entrada-custo-${linhaId}`);
  if (sel && custoInput) {
    const opt = sel.options[sel.selectedIndex];
    const custo = opt.getAttribute('data-custo');
    if (custo && parseFloat(custo) > 0) {
      custoInput.value = parseFloat(custo).toFixed(2);
    }
  }
  window.calcTotalEntrada();
};

window.calcTotalEntrada = () => {
  let soma = 0;
  let totalPecas = 0;
  let qtdNovos = 0;
  let qtdReposicao = 0;

  for (const linha of entradaLinhasItens) {
    const sel = document.getElementById(`entrada-var-${linha.id}`);
    const qtdEl = document.getElementById(`entrada-qtd-${linha.id}`);
    const custoEl = document.getElementById(`entrada-custo-${linha.id}`);
    const vid = parseInt(sel?.value);
    const qtd = parseInt(qtdEl?.value) || 0;
    const custo = parseFloat(custoEl?.value) || 0;
    
    totalPecas += qtd;
    soma += qtd * custo;

    if (vid && produtosNovosNaNota.has(vid)) {
      qtdNovos += qtd;
    } else {
      qtdReposicao += qtd;
    }
  }

  const totalEl = document.getElementById('entrada-calc-total');
  const pecasEl = document.getElementById('entrada-calc-pecas');
  if (totalEl) totalEl.textContent = fmtMoney(soma);
  if (pecasEl) pecasEl.textContent = `${totalPecas} peças`;

  // Resumo antes de confirmar: separa novos e reposição
  const elNovos = document.getElementById('resumo-qtd-novos');
  const elRep = document.getElementById('resumo-qtd-reposicao');
  if (elNovos) elNovos.textContent = `${qtdNovos} peças`;
  if (elRep) elRep.textContent = `${qtdReposicao} peças`;
};

// ================= ENTRADA EM GRADE (FASE 2) =================
function setupEntradaGrade() {
  const btnGrade = document.getElementById('btn-grade-entrada');
  const selectProd = document.getElementById('grade-select-produto');
  const wrap = document.getElementById('grade-tabela-wrap');
  const theadTr = document.getElementById('grade-thead-tr');
  const tbody = document.getElementById('grade-tbody');
  const custoInput = document.getElementById('grade-custo-unit');
  const btnConfirmar = document.getElementById('btn-confirmar-grade');

  if (btnGrade) {
    btnGrade.addEventListener('click', () => {
      if (selectProd) {
        selectProd.innerHTML = '<option value="">Selecione um produto...</option>' +
          (produtosListaCache || []).map(p => `<option value="${p.id}">${escapeHtml(p.nome)}</option>`).join('');
      }
      if (wrap) wrap.hidden = true;
      if (tbody) tbody.innerHTML = '';
      if (custoInput) custoInput.value = '';
      openModal('modal-entrada-grade');
    });
  }

  if (selectProd) {
    selectProd.addEventListener('change', () => {
      const pid = parseInt(selectProd.value);
      if (!pid) {
        if (wrap) wrap.hidden = true;
        return;
      }

      const prod = (produtosListaCache || []).find(p => p.id === pid);
      if (!prod || !prod.variacoes || prod.variacoes.length === 0) {
        if (wrap) wrap.hidden = true;
        showToast('Este produto não possui grade de variações cadastrada', 'warning');
        return;
      }

      if (custoInput) {
        custoInput.value = (prod.preco_custo || 0).toFixed(2);
      }

      // Identifica tamanhos e cores únicos
      const tamanhos = [...new Set(prod.variacoes.map(v => v.tamanho))];
      const cores = [...new Set(prod.variacoes.map(v => v.cor))];

      // Monta cabeçalho
      theadTr.innerHTML = '<th>Cor</th>' + tamanhos.map(t => `<th class="num" style="min-width:70px">${t}</th>`).join('') + '<th class="num font-bold">Total</th>';

      // Monta linhas por cor
      tbody.innerHTML = cores.map(cor => {
        const cells = tamanhos.map(tam => {
          const v = prod.variacoes.find(item => item.cor === cor && item.tamanho === tam);
          if (v) {
            return `
              <td class="num">
                <input type="number" class="input input--qty grade-qty-input" min="0" value="0"
                       data-vid="${v.id}" data-cor="${escapeHtml(cor)}" data-tam="${escapeHtml(tam)}"
                       style="width:65px; text-align:center; padding:4px;">
              </td>
            `;
          }
          return `<td class="text-center muted">—</td>`;
        }).join('');

        return `
          <tr class="grade-row" data-cor="${escapeHtml(cor)}">
            <td><strong>${escapeHtml(cor)}</strong></td>
            ${cells}
            <td class="num font-bold grade-row-total">0</td>
          </tr>
        `;
      }).join('');

      wrap.hidden = false;

      // Listeners nos inputs para totalizar linha
      tbody.querySelectorAll('.grade-qty-input').forEach(inp => {
        inp.addEventListener('input', () => {
          const row = inp.closest('.grade-row');
          if (row) {
            let rowTotal = 0;
            row.querySelectorAll('.grade-qty-input').forEach(i => {
              rowTotal += parseInt(i.value) || 0;
            });
            const totEl = row.querySelector('.grade-row-total');
            if (totEl) totEl.textContent = rowTotal;
          }
        });
      });
    });
  }

  if (btnConfirmar) {
    btnConfirmar.addEventListener('click', () => {
      const inputs = tbody.querySelectorAll('.grade-qty-input');
      const custo = parseFloat(custoInput.value) || 0;
      let adicionados = 0;

      sincronizarValoresLinhas();

      inputs.forEach(inp => {
        const qtd = parseInt(inp.value) || 0;
        const vid = parseInt(inp.dataset.vid);
        if (qtd > 0 && vid) {
          // Se já existe linha com esse vid, soma
          const linhaExistente = entradaLinhasItens.find(l => l.variacao_id === vid);
          if (linhaExistente) {
            linhaExistente.quantidade = (parseInt(linhaExistente.quantidade) || 0) + qtd;
            linhaExistente.custo_unit = custo;
          } else {
            adicionarLinhaEntradaItem(vid, custo, qtd);
          }
          adicionados++;
        }
      });

      if (adicionados === 0) {
        showToast('Informe a quantidade de pelo menos uma variação da grade', 'warning');
        return;
      }

      closeModal(document.getElementById('modal-entrada-grade'));
      renderLinhasEntrada();
      showToast(`${adicionados} item(ns) da grade adicionados à nota!`, 'success');
    });
  }
}

function setupFornecedoresHandlers() {
  const btnNovoFornecedor = document.getElementById('btn-novo-fornecedor');
  if (btnNovoFornecedor) {
    btnNovoFornecedor.addEventListener('click', () => {
      const form = document.getElementById('form-fornecedor');
      if (form) {
        form.reset();
        document.getElementById('forn-id').value = '';
        document.getElementById('modal-fornecedor-title').textContent = 'Cadastrar Novo Fornecedor';
      }
      openModal('modal-fornecedor');
    });
  }

  const formFornecedor = document.getElementById('form-fornecedor');
  if (formFornecedor) {
    formFornecedor.addEventListener('submit', async (e) => {
      e.preventDefault();
      const fid = document.getElementById('forn-id').value;
      const payload = {
        nome: formFornecedor.nome.value.trim(),
        cnpj: formFornecedor.cnpj.value.trim(),
        telefone: formFornecedor.telefone.value.trim(),
        email: formFornecedor.email.value.trim(),
        contato: formFornecedor.contato.value.trim(),
        obs: formFornecedor.obs.value.trim()
      };

      try {
        if (fid) {
          await api.put(`/api/fornecedores/${fid}`, payload);
          showToast('Fornecedor atualizado com sucesso!', 'success');
        } else {
          await api.post('/api/fornecedores', payload);
          showToast('Fornecedor cadastrado com sucesso!', 'success');
        }
        closeModal(document.getElementById('modal-fornecedor'));
        await fetchFornecedores();
      } catch (err) {
        showToast(err.message || 'Erro ao salvar fornecedor', 'error');
      }
    });
  }

  window.editarFornecedor = (id) => {
    const f = fornecedoresCache.find(item => item.id === id);
    if (!f) return;
    const form = document.getElementById('form-fornecedor');
    if (!form) return;
    document.getElementById('forn-id').value = f.id;
    form.nome.value = f.nome || '';
    form.cnpj.value = f.cnpj || '';
    form.telefone.value = f.telefone || '';
    form.email.value = f.email || '';
    form.contato.value = f.contato || '';
    form.obs.value = f.obs || '';
    document.getElementById('modal-fornecedor-title').textContent = `Editar Fornecedor #${f.id}`;
    openModal('modal-fornecedor');
  };

  window.verDetalhesEntrada = async (id) => {
    const modalBody = document.getElementById('entrada-detalhes-body');
    const modalTitle = document.getElementById('modal-entrada-detalhes-title');
    if (!modalBody) return;

    modalBody.innerHTML = '<div class="text-center py-4 muted">Carregando dados da entrada...</div>';
    openModal('modal-entrada-detalhes');

    try {
      const e = await api.get(`/api/entradas/${id}`);
      if (modalTitle) modalTitle.textContent = `Entrada #${e.id} — Nota: ${e.numero_nota || 'S/N'}`;

      const itensHtml = (e.itens || []).map(it => `
        <tr>
          <td><strong>${it.produto_nome}</strong></td>
          <td><span class="size-chip">${it.tamanho} / ${it.cor}</span></td>
          <td class="num font-bold">${it.quantidade} un</td>
          <td class="num">${fmtMoney(it.custo_unit || 0)}</td>
          <td class="num font-bold text-emerald-400">${fmtMoney((it.quantidade || 0) * (it.custo_unit || 0))}</td>
        </tr>
      `).join('');

      modalBody.innerHTML = `
        <div style="display:grid; grid-template-columns: repeat(auto-fit, minmax(180px, 1fr)); gap:1rem; margin-bottom:1.5rem; background:rgba(255,255,255,0.03); padding:1rem; border-radius:8px; border:1px solid var(--border)">
          <div><small class="muted uppercase">Fornecedor</small><div class="font-bold">${e.fornecedor_nome || 'Direto / Não especificado'}</div></div>
          <div><small class="muted uppercase">Data da Entrada</small><div class="font-bold">${fmtDateStr(e.data)}</div></div>
          <div><small class="muted uppercase">Registrado por</small><div>${e.usuario_nome || '—'}</div></div>
          <div><small class="muted uppercase">Total da Nota</small><div class="font-bold text-emerald-400" style="font-size:1.25rem">${fmtMoney(e.total || 0)}</div></div>
          ${e.obs ? `<div style="grid-column:1/-1"><small class="muted uppercase">Observações</small><div class="small">${e.obs}</div></div>` : ''}
        </div>

        <h3 style="font-size:0.875rem; text-transform:uppercase; color:var(--text-muted); margin-bottom:0.5rem">Produtos Recebidos</h3>
        <div class="table-wrap">
          <table class="table table--compact">
            <thead>
              <tr>
                <th>Produto</th>
                <th>Variação</th>
                <th class="num">Qtd Recebida</th>
                <th class="num">Custo Unitário</th>
                <th class="num">Subtotal</th>
              </tr>
            </thead>
            <tbody>${itensHtml}</tbody>
          </table>
        </div>
      `;
    } catch (err) {
      modalBody.innerHTML = `<div class="text-center py-4 text-danger">${err.message || 'Erro ao carregar detalhes da entrada'}</div>`;
    }
  };
}

import { api } from '../core/api.js';
import { fmtMoney } from '../core/format.js';
import { showToast, openModal, closeModal } from '../core/ui.js';

export let cart = [];

const els = {
  posSearch: document.getElementById('pos-search'),
  posResults: document.getElementById('pos-results'),
  quickGrid: document.getElementById('quick-grid'),
  cartList: document.getElementById('cart-list'),
  cartCountPills: [document.getElementById('nav-cart-count'), document.getElementById('cart-count')],
  cartEmpty: document.getElementById('cart-empty'),
  sumSubtotal: document.getElementById('sum-subtotal'),
  sumDiscount: document.getElementById('sum-discount'),
  sumTotal: document.getElementById('sum-total'),
  sumItems: document.getElementById('sum-items'),
  discountVal: document.getElementById('discount-value'),
  discountTypes: document.getElementsByName('discount-type'),
  btnCheckout: document.getElementById('btn-checkout'),
};

export function initPOS(getProductsCallback, fetchProductsCallback) {
  if (!els.discountVal) return;

  els.discountVal.addEventListener('input', updateCheckout);
  els.discountTypes.forEach(r => r.addEventListener('change', updateCheckout));

  document.getElementById('btn-clear-cart').addEventListener('click', clearCart);
  els.btnCheckout.addEventListener('click', () => openCheckoutModal());
  
  setupCheckoutModal(fetchProductsCallback);
  loadSellerMeta();

  els.posSearch.addEventListener('keydown', (e) => {
    if (e.key === 'Enter') {
      e.preventDefault();
      const q = e.target.value.trim();
      if (!q) return;
      
      const products = getProductsCallback();
      let matchVar = null;
      let matchProd = null;
      
      // Look for exact barcode or sku match
      for (const p of products) {
        for (const v of p.variacoes) {
          if (v.codigo_barras === q || v.sku === q) {
            matchVar = v;
            matchProd = p;
            break;
          }
        }
        if (matchVar) break;
      }
      
      if (matchVar) {
        if (matchVar.estoque > 0) {
          addToCart(matchVar.id, products);
          e.target.value = '';
          els.posResults.hidden = true;
          // beep
          const audio = new Audio("data:audio/wav;base64,UklGRl9vT19XQVZFZm10IBAAAAABAAEAQB8AAEAfAAABAAgAZGF0YU");
          audio.play().catch(()=>{});
        } else {
          showToast('Produto fora de estoque!', 'warning');
        }
      }
    }
  });

  els.posSearch.addEventListener('input', (e) => {
    const q = e.target.value.toLowerCase().trim();
    if (q.length < 2) {
      els.posResults.hidden = true;
      return;
    }
    
    const products = getProductsCallback();
    const hits = products.filter(p => 
      p.nome.toLowerCase().includes(q) || String(p.id).includes(q)
    );

    els.posResults.innerHTML = hits.map(p => {
      const sizesHtml = p.variacoes.map(v => `
        <button type="button" class="size-chip ${v.estoque === 0 ? 'is-zero' : ''}" 
          data-vid="${v.id}" ${v.estoque === 0 ? 'disabled' : ''}>
          ${v.tamanho}
        </button>
      `).join('');

      return `
      <li class="result" role="option" tabindex="0">
        <img src="${p.img || '/static/erp/img/placeholder.svg'}" onerror="this.onerror=null;this.src='/static/erp/img/placeholder.svg'" alt="" loading="lazy">
        <div class="result__info">
          <div class="result__name">${p.nome} <span class="muted font-normal text-xs ml-1">#${p.id}</span></div>
          <div class="result__meta">${fmtMoney(p.preco)}</div>
        </div>
        <div class="result__sizes">${sizesHtml}</div>
      </li>
    `}).join('');
    els.posResults.hidden = hits.length === 0;
  });

  els.posResults.addEventListener('click', (e) => {
    const btn = e.target.closest('.size-chip');
    if (btn && !btn.disabled) {
      addToCart(parseInt(btn.dataset.vid), getProductsCallback());
      els.posSearch.value = '';
      els.posResults.hidden = true;
    }
  });

  document.addEventListener('click', (e) => {
    if (!e.target.closest('.search-card')) els.posResults.hidden = true;
  });
}

export function renderQuickAccess(products) {
  if (!els.quickGrid) return;
  els.quickGrid.innerHTML = products.map(p => `
    <article class="quick-item">
      <img src="${p.img || '/static/erp/img/placeholder.svg'}" onerror="this.onerror=null;this.src='/static/erp/img/placeholder.svg'" alt="" loading="lazy">
      <h3 class="quick-item__name" title="${p.nome}">${p.nome}</h3>
      <p class="quick-item__price">${fmtMoney(p.preco)}</p>
      <div class="quick-item__sizes">
        ${p.variacoes.map(v => `
          <button type="button" class="size-chip ${v.estoque === 0 ? 'is-zero' : ''}" 
            data-vid="${v.id}" onclick="window.addToCartGlobal(${v.id})" ${v.estoque === 0 ? 'disabled' : ''}>
            ${v.tamanho}
          </button>
        `).join('')}
      </div>
    </article>
  `).join('');
}

export function addToCart(variacaoId, products) {
  // Find product and variacao
  let product, variacao;
  for (const p of products) {
    variacao = p.variacoes.find(v => v.id === variacaoId);
    if (variacao) {
      product = p;
      break;
    }
  }

  if (!product || !variacao || variacao.estoque <= 0) return showToast('Produto sem estoque.', 'error');

  const exist = cart.find(i => i.variacao_id === variacaoId);
  if (exist) {
    if (exist.quantidade >= variacao.estoque) return showToast('Estoque máximo atingido.', 'warning');
    exist.quantidade++;
  } else {
    cart.unshift({ 
      variacao_id: variacao.id, 
      nome: product.nome, 
      preco: product.preco, 
      imagem: product.img, 
      tamanho: variacao.tamanho, 
      quantidade: 1,
      max: variacao.estoque
    });
  }
  
  renderCart();
  showToast(`Adicionado: ${product.nome} (${variacao.tamanho})`, 'success');
}

window.updateCartQtyGlobal = (idx, delta) => {
  const item = cart[idx];
  const newQty = item.quantidade + delta;
  
  if (newQty <= 0) cart.splice(idx, 1);
  else if (newQty > item.max) return showToast('Estoque insuficiente.', 'warning');
  else item.quantidade = newQty;
  renderCart();
};

window.removeCartItemGlobal = (idx) => {
  cart.splice(idx, 1); 
  renderCart();
};

function clearCart() {
  if (!cart.length) return;
  if (confirm('Limpar o carrinho?')) {
    cart = [];
    els.discountVal.value = '';
    renderCart();
  }
}

export function renderCart() {
  const hasItems = cart.length > 0;
  els.cartList.innerHTML = '';
  
  if (hasItems) {
    cart.forEach((item, i) => {
      const li = document.createElement('li');
      li.className = 'cart-item';
      li.innerHTML = `
        <img src="${item.imagem || '/static/erp/img/placeholder.svg'}" onerror="this.onerror=null;this.src='/static/erp/img/placeholder.svg'" alt="" class="cart-item__img">
        <div class="cart-item__info">
          <div class="cart-item__name" title="${item.nome}">${item.nome}</div>
          <div class="cart-item__meta"><span class="size-chip">${item.tamanho}</span><span>Ref: ${item.variacao_id}</span></div>
        </div>
        <div class="cart-item__size"><span class="size-chip">${item.tamanho}</span></div>
        <div class="cart-item__unit">${fmtMoney(item.preco)}</div>
        <div class="cart-item__qty">
          <div class="stepper">
            <button type="button" aria-label="Diminuir" onclick="updateCartQtyGlobal(${i}, -1)"><svg class="icon"><use href="#i-minus"/></svg></button>
            <output>${item.quantidade}</output>
            <button type="button" aria-label="Aumentar" onclick="updateCartQtyGlobal(${i}, 1)"><svg class="icon"><use href="#i-plus"/></svg></button>
          </div>
        </div>
        <div class="cart-item__subtotal">${fmtMoney(item.preco * item.quantidade)}</div>
        <button type="button" class="btn btn--icon btn--ghost cart-item__remove" onclick="removeCartItemGlobal(${i})"><svg class="icon"><use href="#i-trash"/></svg></button>
      `;
      els.cartList.appendChild(li);
    });
  }

  els.cartEmpty.hidden = hasItems;
  document.querySelector('.cart__head').style.display = hasItems ? 'grid' : 'none';
  
  const count = cart.reduce((a, i) => a + i.quantidade, 0);
  els.cartCountPills.forEach(p => { p.textContent = count; p.hidden = count === 0; });

  updateCheckout();
}

function updateCheckout() {
  const items = cart.reduce((a, i) => a + i.quantidade, 0);
  const subtotal = cart.reduce((a, i) => a + (i.preco * i.quantidade), 0);
  
  let discount = 0;
  const rawDisc = parseFloat(els.discountVal.value) || 0;
  if (rawDisc > 0) {
    const type = document.querySelector('input[name="discount-type"]:checked').value;
    discount = type === 'pct' ? subtotal * (Math.min(rawDisc, 100) / 100) : Math.min(rawDisc, subtotal);
  }
  const total = subtotal - discount;

  els.sumItems.textContent = items;
  els.sumSubtotal.textContent = fmtMoney(subtotal);
  els.sumDiscount.textContent = discount > 0 ? `− ${fmtMoney(discount)}` : 'R$ 0,00';
  els.sumTotal.textContent = fmtMoney(total);
  
  els.sumTotal.classList.remove('bump');
  void els.sumTotal.offsetWidth;
  els.sumTotal.classList.add('bump');

  els.btnCheckout.disabled = items === 0;
}

export function getCartTotals() {
  const count = cart.reduce((a, i) => a + i.quantidade, 0);
  const subtotal = cart.reduce((a, i) => a + (i.preco * i.quantidade), 0);
  let discount = 0;
  const rawDisc = parseFloat(els.discountVal.value) || 0;
  if (rawDisc > 0) {
    const type = document.querySelector('input[name="discount-type"]:checked').value;
    discount = type === 'pct' ? subtotal * (Math.min(rawDisc, 100) / 100) : Math.min(rawDisc, subtotal);
  }
  const total = subtotal - discount;
  return { subtotal, discount, total, count };
}

// ================= CHECKOUT MODAL =================
let checkoutPayments = [];
let checkoutTotal = 0;

export function openCheckoutModal() {
  if (cart.length === 0) {
    showToast('O carrinho está vazio', 'warning');
    return;
  }
  const { total } = getCartTotals();
  if (total <= 0) {
    showToast('Valor total inválido', 'error');
    return;
  }
  
  checkoutTotal = total;
  checkoutPayments = [];
  
  document.getElementById('checkout-total').textContent = fmtMoney(checkoutTotal);
  document.getElementById('checkout-amount').value = checkoutTotal.toFixed(2);
  const methodSelect = document.getElementById('checkout-method');
  if (methodSelect) methodSelect.value = 'Pix';
  const fieldVale = document.getElementById('field-vale-codigo');
  if (fieldVale) fieldVale.hidden = true;
  const inputVale = document.getElementById('checkout-vale-codigo');
  if (inputVale) inputVale.value = '';

  const selCliente = document.getElementById('checkout-cliente');
  if (selCliente) {
    selCliente.innerHTML = '<option value="">Consumidor Final (Sem cadastro)</option>';
    api.get('/api/clientes').then(clientes => {
      selCliente.innerHTML = '<option value="">Consumidor Final (Sem cadastro)</option>' +
        (clientes || []).map(c => `<option value="${c.id}">${c.nome} ${c.cpf ? `(${c.cpf})` : ''}</option>`).join('');
    }).catch(() => {});
  }
  
  updateCheckoutState();
  openModal('modal-checkout');
}

export function setupCheckoutModal(fetchProductsCallback) {
  const formAdd = document.getElementById('form-add-payment');
  const btnConfirm = document.getElementById('btn-confirm-sale');
  const methodSelect = document.getElementById('checkout-method');
  const fieldVale = document.getElementById('field-vale-codigo');
  const inputVale = document.getElementById('checkout-vale-codigo');
  const btnConsultarVale = document.getElementById('btn-consultar-vale');
  const amountInput = document.getElementById('checkout-amount');

  if (methodSelect) {
    methodSelect.addEventListener('change', () => {
      const isVale = methodSelect.value === 'Vale-Troca';
      if (fieldVale) fieldVale.hidden = !isVale;
      if (isVale && inputVale) inputVale.focus();
    });
  }

  if (btnConsultarVale) {
    btnConsultarVale.addEventListener('click', async () => {
      const code = (inputVale.value || '').trim().toUpperCase();
      if (!code) {
        showToast('Informe o código do vale (ex: VT-XXXXXX)', 'warning');
        return;
      }
      try {
        const vale = await api.get(`/api/vales/${encodeURIComponent(code)}`);
        if (vale.expirado) {
          showToast(`Vale ${code} expirou em ${vale.validade}`, 'error');
          return;
        }
        if (vale.status !== 'ativo' || vale.saldo <= 0) {
          showToast(`Vale ${code} não está ativo ou sem saldo (Status: ${vale.status})`, 'error');
          return;
        }
        showToast(`Vale válido! Saldo disponível: ${fmtMoney(vale.saldo)}`, 'success');
        
        // Calcula quanto falta receber e sugere o valor
        const totalPaid = checkoutPayments.reduce((acc, p) => acc + p.valor, 0);
        const remaining = Math.max(0, checkoutTotal - totalPaid);
        const jaUsadoMesmoVale = checkoutPayments
          .filter(p => p.forma === 'Vale-Troca' && p.vale_codigo === code)
          .reduce((acc, p) => acc + p.valor, 0);
        const saldoRestante = Math.max(0, vale.saldo - jaUsadoMesmoVale);
        const valorAplicar = Math.min(saldoRestante, remaining);
        if (valorAplicar > 0) {
          amountInput.value = valorAplicar.toFixed(2);
        }
      } catch (err) {
        showToast(err.message || 'Vale não encontrado', 'error');
      }
    });
  }
  
  formAdd.addEventListener('submit', async (e) => {
    e.preventDefault();
    const method = methodSelect.value;
    const amount = parseFloat(amountInput.value);
    
    if (!amount || amount <= 0) return;

    let valeCodigo = null;
    if (method === 'Vale-Troca') {
      valeCodigo = (inputVale.value || '').trim().toUpperCase();
      if (!valeCodigo) {
        showToast('Informe o código do vale', 'error');
        if (inputVale) inputVale.focus();
        return;
      }
      try {
        const vale = await api.get(`/api/vales/${encodeURIComponent(valeCodigo)}`);
        if (vale.expirado) {
          showToast(`Vale ${valeCodigo} expirou em ${vale.validade}`, 'error');
          return;
        }
        if (vale.status !== 'ativo' || vale.saldo <= 0) {
          showToast(`Vale ${valeCodigo} não está ativo ou sem saldo`, 'error');
          return;
        }
        const jaUsado = checkoutPayments
          .filter(p => p.forma === 'Vale-Troca' && p.vale_codigo === valeCodigo)
          .reduce((acc, p) => acc + p.valor, 0);
        if (jaUsado + amount > vale.saldo) {
          showToast(`Saldo insuficiente no vale ${valeCodigo}. Disponível: ${fmtMoney(vale.saldo - jaUsado)}`, 'error');
          return;
        }
      } catch (err) {
        showToast(err.message || 'Vale inválido', 'error');
        return;
      }
    }
    
    checkoutPayments.push({ 
      forma: method, 
      valor: amount, 
      vale_codigo: valeCodigo 
    });

    if (inputVale) inputVale.value = '';
    if (fieldVale) fieldVale.hidden = true;
    if (methodSelect) methodSelect.value = 'Pix';
    
    // Auto-adjust next input amount if there is remaining
    const totalPaid = checkoutPayments.reduce((acc, p) => acc + p.valor, 0);
    const remaining = checkoutTotal - totalPaid;
    if (remaining > 0) {
      amountInput.value = remaining.toFixed(2);
    } else {
      amountInput.value = '';
    }
    
    updateCheckoutState();
  });
  
  btnConfirm.addEventListener('click', () => finishSale(fetchProductsCallback));
  
  // Make global for inline removal
  window.removeCheckoutPayment = (index) => {
    checkoutPayments.splice(index, 1);
    const totalPaid = checkoutPayments.reduce((acc, p) => acc + p.valor, 0);
    const remaining = checkoutTotal - totalPaid;
    if (remaining > 0) {
      document.getElementById('checkout-amount').value = remaining.toFixed(2);
    }
    updateCheckoutState();
  };
}

function updateCheckoutState() {
  const tbody = document.querySelector('#checkout-payments-table tbody');
  const remainingEl = document.getElementById('checkout-remaining');
  const changeWrap = document.getElementById('checkout-change-wrap');
  const changeEl = document.getElementById('checkout-change');
  const btnConfirm = document.getElementById('btn-confirm-sale');
  
  tbody.innerHTML = checkoutPayments.map((p, i) => `
    <tr>
      <td><strong>${p.forma}</strong> ${p.vale_codigo ? `<span class="chip" style="margin-left:0.5rem; font-size:11px">${p.vale_codigo}</span>` : ''}</td>
      <td class="num">${fmtMoney(p.valor)}</td>
      <td style="text-align:right">
        <button type="button" class="btn btn--icon btn--ghost" style="color:var(--danger)" onclick="removeCheckoutPayment(${i})">
          <svg class="icon"><use href="#i-trash"/></svg>
        </button>
      </td>
    </tr>
  `).join('') || '<tr><td colspan="3" class="muted text-center py-2">Nenhum pagamento inserido</td></tr>';
  
  const totalPaid = checkoutPayments.reduce((acc, p) => acc + p.valor, 0);
  const diff = checkoutTotal - totalPaid;
  
  if (diff > 0) {
    remainingEl.textContent = fmtMoney(diff);
    remainingEl.style.color = 'var(--warning)';
    changeWrap.hidden = true;
    btnConfirm.disabled = true;
  } else {
    remainingEl.textContent = 'R$ 0,00';
    remainingEl.style.color = 'var(--emerald-400)';
    btnConfirm.disabled = false;
    
    if (diff < 0) {
      changeWrap.hidden = false;
      changeEl.textContent = fmtMoney(Math.abs(diff));
    } else {
      changeWrap.hidden = true;
    }
  }
}

async function finishSale(fetchProductsCallback) {
  const { discount } = getCartTotals();
  const selCliente = document.getElementById('checkout-cliente');
  const clienteId = selCliente?.value ? parseInt(selCliente.value) : null;
  
  const payload = {
    cliente_id: clienteId,
    itens: cart.map(item => ({
      variacao_id: item.variacao_id,
      quantidade: item.quantidade,
      preco_unit: item.preco
    })),
    desconto: { tipo: 'valor', valor: discount },
    pagamentos: checkoutPayments
  };

  els.btnCheckout.disabled = true;
  document.getElementById('btn-confirm-sale').disabled = true;
  document.getElementById('btn-confirm-sale').textContent = 'Processando...';

  try {
    const res = await api.post('/api/vendas', payload);
    showToast('Venda finalizada!', 'success');
    
    closeModal(document.getElementById('modal-checkout'));
    
    // Clear cart & UI
    cart = [];
    els.discountVal.value = '';
    renderCart();
    
    // Refresh products (stock)
    if (typeof fetchProductsCallback === 'function') {
      fetchProductsCallback();
    }

    // Refresh seller goal progress bar in real time without page reload
    loadSellerMeta();
    
    // Open Receipt if returned
    if (res && res.id) {
      window.open(`/static/erp/cupom.html?id=${res.id}`, '_blank', 'width=380,height=600');
    }
    
  } catch (err) {
    showToast(err.message || 'Erro ao finalizar venda', 'error');
  } finally {
    els.btnCheckout.disabled = false;
    const btnConfirm = document.getElementById('btn-confirm-sale');
    if (btnConfirm) {
        btnConfirm.disabled = false;
        btnConfirm.textContent = 'Confirmar Venda';
    }
  }
}

export async function loadSellerMeta() {
  const bar = document.getElementById('pos-meta-bar');
  const txt = document.getElementById('pos-meta-texto');
  const faltaEl = document.getElementById('pos-meta-falta');
  const fill = document.getElementById('pos-meta-fill');
  if (!bar) return;

  try {
    const user = window.currentUser || {};
    if (user.perfil === 'admin') {
      bar.hidden = true;
      return;
    }

    const res = await api.get('/api/metas');
    let meta = null;
    if (Array.isArray(res) && res.length > 0) {
      if (user.id) {
        meta = res.find(m => m.vendedor_id === user.id) || res[0];
      } else {
        meta = res[0];
      }
    }

    if (!meta || !meta.valor_meta || meta.valor_meta <= 0) {
      bar.hidden = true;
      return;
    }

    bar.hidden = false;
    const meses = ['Janeiro', 'Fevereiro', 'Março', 'Abril', 'Maio', 'Junho', 'Julho', 'Agosto', 'Setembro', 'Outubro', 'Novembro', 'Dezembro'];
    const [ano, mesNum] = (meta.periodo || '').split('-');
    const nomeMes = mesNum ? meses[parseInt(mesNum, 10) - 1] : 'mês';

    if (txt) {
      txt.textContent = `Sua meta de ${nomeMes}: ${fmtMoney(meta.vendido)} de ${fmtMoney(meta.valor_meta)} (${meta.percentual}%)`;
    }
    if (faltaEl) {
      faltaEl.textContent = meta.falta > 0 ? `Falta: ${fmtMoney(meta.falta)}` : 'Meta atingida!';
    }
    if (fill) {
      fill.style.width = `${Math.min(meta.percentual, 100)}%`;
      if (meta.percentual >= 100) {
        fill.style.background = 'var(--emerald-400)';
      } else {
        fill.style.background = 'linear-gradient(90deg, var(--brand-500), var(--emerald-400))';
      }
    }
  } catch (err) {
    bar.hidden = true;
  }
}

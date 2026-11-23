export function showToast(msg, type = 'info') {
  const toasts = document.getElementById('toasts');
  if (!toasts) return;
  const toast = document.createElement('div');
  toast.className = `toast toast--${type}`;
  const icon = type === 'success' ? '#i-check' : type === 'warning' ? '#i-minus' : '#i-tag';
  toast.innerHTML = `<svg class="icon"><use href="${icon}"/></svg><span>${msg}</span>`;
  toasts.appendChild(toast);
  setTimeout(() => {
    toast.classList.add('is-leaving');
    toast.addEventListener('animationend', () => toast.remove());
  }, 4000);
}

export function openModal(id) {
  const modal = typeof id === 'string' ? document.getElementById(id) : id;
  if (modal) {
    modal.classList.remove('is-closing');
    modal.hidden = false;
    modal.removeAttribute('hidden');
    modal.setAttribute('aria-hidden', 'false');
    document.body.style.overflow = 'hidden';
  }
}

export function closeModal(el) {
  if (!el) return;
  const modal = el.closest ? el.closest('.modal') : (el.classList && el.classList.contains('modal') ? el : null);
  if (modal) {
    modal.classList.add('is-closing');
    let done = false;
    const finish = () => {
      if (done) return;
      done = true;
      modal.classList.remove('is-closing');
      modal.hidden = true;
      modal.setAttribute('hidden', '');
      modal.setAttribute('aria-hidden', 'true');
      document.body.style.overflow = '';
      modal.removeEventListener('animationend', finish);
    };
    modal.addEventListener('animationend', function handler(e) {
      if (e.animationName === 'fade' || e.animationName === 'pop') finish();
    });
    // Fallback if CSS animations are cached/missing
    setTimeout(finish, 350);
  }
}

export function setupUIBindings() {
  document.querySelectorAll('[data-open-modal]').forEach(btn => {
    btn.addEventListener('click', () => openModal(btn.dataset.openModal));
  });
  document.querySelectorAll('[data-close-modal]').forEach(btn => {
    btn.addEventListener('click', (e) => closeModal(e.target));
  });

  document.addEventListener('keydown', (e) => {
    if (e.key === 'Escape') {
      const openM = document.querySelector('.modal:not([hidden])');
      if (openM) closeModal(openM.querySelector('[data-close-modal]'));
    }
  });

  // Melhorias globais para inputs de números e moedas
  document.addEventListener('focusin', (e) => {
    if (e.target && e.target.matches && e.target.matches('input[type="number"], .input--money, .input--qty')) {
      setTimeout(() => {
        try { e.target.select(); } catch (_) {}
      }, 20);
    }
  });

  // Evita alteração indesejada de valor ao usar a roda do mouse sobre o campo
  document.addEventListener('wheel', () => {
    const el = document.activeElement;
    if (el && el.matches && el.matches('input[type="number"], .input--money, .input--qty')) {
      el.blur();
    }
  }, { passive: true });
}

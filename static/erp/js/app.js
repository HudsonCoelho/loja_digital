import { setupUIBindings } from './core/ui.js?v=4';
import { fetchProducts, renderStock, products, setupEstoqueViews } from './views/estoque.js?v=5';
import { initPOS, renderQuickAccess, addToCart } from './views/caixa.js?v=6';
import { loadReports, setupRelatorios } from './views/relatorios.js?v=2';
import { setupProductForm } from './views/produto-form.js';
import { initRegister } from './views/caixa-turno.js?v=2';
import { api } from './core/api.js';
import { loadVendas, setupVendas } from './views/vendas.js?v=6';
import { loadUsuarios, setupUsuarios, setupAuthActions } from './views/usuarios.js';
import { loadConfiguracoes, setupConfiguracoes } from './views/configuracoes.js';
import { loadClientes, setupClientes } from './views/clientes.js?v=2';
import { loadEntradasView, setupEntradas } from './views/entradas.js?v=3';

const App = (() => {
  let navLinks = document.querySelectorAll('.nav__link');
  let views = document.querySelectorAll('.view');

  // --- NAVEGAÇÃO SPA ---
  function initRouter() {
    const ADMIN_ONLY_ROUTES = ['relatorios', 'usuarios', 'configuracoes', 'entradas'];
    const drawerLinks = document.querySelectorAll('.drawer__link');
    const btnOpenDrawer = document.getElementById('btn-open-drawer');

    const navigate = (route) => {
      if (window.currentUser && window.currentUser.perfil !== 'admin' && ADMIN_ONLY_ROUTES.includes(route)) {
        route = 'caixa';
        history.replaceState(null, '', '#caixa');
      }

      navLinks.forEach(link => {
        link.classList.toggle('is-active', link.dataset.route === route);
        link.setAttribute('aria-current', link.dataset.route === route ? 'page' : 'false');
      });

      drawerLinks.forEach(link => {
        link.classList.toggle('is-active', link.dataset.route === route);
      });

      if (btnOpenDrawer) {
        btnOpenDrawer.classList.toggle('is-active', ADMIN_ONLY_ROUTES.includes(route));
      }

      views.forEach(view => {
        const isCurrent = view.dataset.view === route;
        view.hidden = !isCurrent;
        if (isCurrent) {
          const navTitle = document.getElementById(`nav-${route}`);
          if (navTitle) {
            const labelEl = navTitle.querySelector('.nav__label');
            document.getElementById('page-title').textContent = labelEl ? labelEl.textContent.trim() : navTitle.textContent.trim();
          }
          const eyebrow = document.getElementById('page-eyebrow');
          if (eyebrow) {
            eyebrow.textContent = route === 'caixa' ? 'Frente de Caixa' : 'Gestão da Loja';
          }
        }
      });

      if (route === 'estoque') renderStock();
      if (route === 'relatorios') loadReports();
      if (route === 'vendas') loadVendas();
      if (route === 'usuarios') loadUsuarios();
      if (route === 'configuracoes') loadConfiguracoes();
      if (route === 'clientes') loadClientes();
      if (route === 'entradas') loadEntradasView();
    };

    navLinks.forEach(link => {
      link.addEventListener('click', (e) => {
        e.preventDefault();
        const route = link.dataset.route;
        if (route) {
          if (location.hash !== `#${route}`) {
            history.pushState(null, '', `#${route}`);
          }
          navigate(route);
        }
      });
    });

    drawerLinks.forEach(link => {
      link.addEventListener('click', (e) => {
        e.preventDefault();
        const route = link.dataset.route;
        if (route) {
          if (location.hash !== `#${route}`) {
            history.pushState(null, '', `#${route}`);
          }
          navigate(route);
        }
      });
    });

    window.addEventListener('hashchange', () => {
      const currentRoute = location.hash.replace('#', '') || 'caixa';
      navigate(currentRoute);
    });

    const initialRoute = location.hash.replace('#', '') || 'caixa';
    navigate(initialRoute);
  }

  // --- MOBILE DRAWER (MENU SLIDEOVER) ---
  function initMobileDrawer() {
    const drawer = document.getElementById('mobile-drawer');
    const btnOpen = document.getElementById('btn-open-drawer');
    const btnTopbar = document.getElementById('btn-topbar-menu');
    const btnClose = document.getElementById('btn-close-drawer');
    const backdrop = document.getElementById('mobile-drawer-backdrop');

    if (!drawer) return;

    const open = () => {
      drawer.classList.add('is-open');
      drawer.removeAttribute('aria-hidden');
      document.body.style.overflow = 'hidden';
    };

    const close = () => {
      drawer.classList.remove('is-open');
      drawer.setAttribute('aria-hidden', 'true');
      document.body.style.overflow = '';
    };

    if (btnOpen) btnOpen.addEventListener('click', open);
    if (btnTopbar) btnTopbar.addEventListener('click', open);
    if (btnClose) btnClose.addEventListener('click', close);
    if (backdrop) backdrop.addEventListener('click', close);

    const drawerLinks = drawer.querySelectorAll('.drawer__link');
    drawerLinks.forEach(link => {
      link.addEventListener('click', close);
    });

    const btnDrawerSenha = document.getElementById('btn-drawer-senha');
    if (btnDrawerSenha) {
      btnDrawerSenha.addEventListener('click', close);
    }

    const btnDrawerLogout = document.getElementById('btn-drawer-logout');
    if (btnDrawerLogout) {
      btnDrawerLogout.addEventListener('click', async () => {
        if (!confirm('Deseja realmente sair do sistema?')) return;
        try {
          await api.post('/api/auth/logout', {});
        } catch (e) {}
        window.location.href = '/login';
      });
    }
  }

  function initClock() {
    const clock = document.getElementById('clock');
    if (!clock) return;
    const tick = () => {
      const now = new Date();
      clock.textContent = now.toLocaleTimeString('pt-BR', { hour: '2-digit', minute: '2-digit' });
      clock.dateTime = now.toISOString();
    };
    tick();
    setInterval(tick, 60000);
  }

  // Bind addToCart globally so inline HTML onclick can reach it
  window.addToCartGlobal = (variacaoId) => addToCart(variacaoId, products);

  async function checkAuth() {
    try {
      const { usuario, csrf } = await api.get('/api/auth/estado');
      if (csrf) window.CSRF_TOKEN = csrf;
      if (!usuario) {
        window.location.href = '/login';
        return;
      }
      if (usuario) {
        window.currentUser = usuario;
        const ehAdmin = usuario.perfil === 'admin';
        const initials = (usuario.nome || '').split(' ').filter(Boolean).map(n => n[0]).slice(0, 2).join('').toUpperCase() || 'US';

        const nameEl = document.getElementById('user-display-name') || document.querySelector('.user-chip__info strong');
        const roleEl = document.getElementById('user-display-role') || document.querySelector('.user-chip__info small');
        const avatarEl = document.getElementById('user-avatar') || document.querySelector('.avatar');
        
        if (nameEl) nameEl.textContent = usuario.nome;
        if (roleEl) roleEl.textContent = ehAdmin ? 'Administrador' : 'Vendedor';
        if (avatarEl) avatarEl.textContent = initials;

        // Drawer mobile: preenche informações do usuário
        const drawerName = document.getElementById('drawer-user-name');
        const drawerRole = document.getElementById('drawer-user-role');
        const drawerAvatar = document.getElementById('drawer-avatar');
        const drawerAdmin = document.getElementById('drawer-admin-section');

        if (drawerName) drawerName.textContent = usuario.nome;
        if (drawerRole) drawerRole.textContent = ehAdmin ? 'Administrador' : 'Vendedor';
        if (drawerAvatar) drawerAvatar.textContent = initials;
        if (drawerAdmin) drawerAdmin.hidden = !ehAdmin;

        // Se não for admin, oculta as rotas restritas no menu
        const navRelatorios = document.getElementById('nav-item-relatorios');
        if (navRelatorios) navRelatorios.hidden = !ehAdmin;

        const navUsuarios = document.getElementById('nav-item-usuarios');
        if (navUsuarios) navUsuarios.hidden = !ehAdmin;

        const navConfiguracoes = document.getElementById('nav-item-configuracoes');
        if (navConfiguracoes) navConfiguracoes.hidden = !ehAdmin;

        const navEntradas = document.getElementById('nav-item-entradas');
        if (navEntradas) navEntradas.hidden = !ehAdmin;
      }
    } catch (e) {
      console.error('Erro ao verificar autenticação:', e);
    }
  }

  async function init() {
    await checkAuth();
    await initRegister();
    setupUIBindings();
    initRouter();
    initMobileDrawer();
    initClock();
    setupProductForm(fetchAndRenderProducts);
    setupVendas();
    setupUsuarios();
    setupConfiguracoes();
    setupClientes();
    setupEntradas();
    setupRelatorios();
    setupEstoqueViews();
    setupAuthActions();
    
    // Pass callbacks so caixa can fetch products or refresh them
    initPOS(() => products, fetchAndRenderProducts);
    fetchAndRenderProducts();
  }

  async function fetchAndRenderProducts() {
    const prods = await fetchProducts();
    renderQuickAccess(prods);
  }

  return { init };
})();

// Initialize immediately since modules are deferred and DOM is already parsed
App.init();

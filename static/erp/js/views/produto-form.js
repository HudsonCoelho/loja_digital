import { api } from '../core/api.js';
import { showToast } from '../core/ui.js';
import { escapeHtml } from '../core/format.js';

export function setupProductForm(fetchProductsCallback) {
  const formProd = document.getElementById('form-product');
  const pImage = document.getElementById('p-image');
  const gradeSelect = document.getElementById('p-grade');
  const sizesContainer = document.getElementById('p-sizes-container');

  function renderGradeSizes(gradeId) {
    if (!sizesContainer) return;
    const grades = window.grades || [];
    const grade = grades.find(g => String(g.id) === String(gradeId)) || grades[0];

    // Tamanhos da grade escolhida
    let tamanhos = [];
    if (grade && Array.isArray(grade.tamanhos)) {
      tamanhos = grade.tamanhos;
    } else {
      // Fallback padrão se ainda não carregou
      tamanhos = ['PP', 'P', 'M', 'G', 'GG'];
    }

    // Se for grade Letras padrão com muitos tamanhos, limitamos aos mais comuns na loja (PP, P, M, G, GG, XG)
    // a menos que o usuário queira todos
    let displayTamanhos = tamanhos;
    if (grade && grade.nome && grade.nome.toLowerCase().includes('letra') && tamanhos.includes('PP')) {
      displayTamanhos = tamanhos.filter(t => ['PP', 'P', 'M', 'G', 'GG', 'XG'].includes(t));
      if (displayTamanhos.length === 0) displayTamanhos = tamanhos;
    }

    const sizesHtml = displayTamanhos.map(tam => `
      <label>
        <span>${escapeHtml(tam)}</span>
        <input class="input input--qty" type="number" min="0" value="0" name="tam_${escapeHtml(tam)}" data-tam="${escapeHtml(tam)}" aria-label="Quantidade tamanho ${escapeHtml(tam)}">
      </label>
    `).join('');

    const minHtml = `
      <label>
        <span style="color:var(--brand-300);">Mín.</span>
        <input class="input input--qty" type="number" min="0" value="5" name="min" aria-label="Quantidade mínima">
      </label>
    `;

    sizesContainer.innerHTML = sizesHtml + minHtml;
  }

  // Load categories and grades for the form
  async function loadFormOptions() {
    try {
      const [cats, grades] = await Promise.all([
        api.get('/api/categorias'),
        api.get('/api/grades')
      ]);

      window.grades = grades;
      
      const catSelect = document.getElementById('p-category');
      if (catSelect) {
        catSelect.innerHTML = '<option value="">Selecione…</option>' + 
          cats.map(c => `<option value="${c.id}">${escapeHtml(c.nome)}</option>`).join('');
      }

      if (gradeSelect && grades && grades.length > 0) {
        gradeSelect.innerHTML = grades.map(g => {
          const sample = (g.tamanhos || []).slice(0, 4).join(', ') + ((g.tamanhos || []).length > 4 ? '...' : '');
          return `<option value="${g.id}">${escapeHtml(g.nome)} (${escapeHtml(sample)})</option>`;
        }).join('');

        // Seleciona Letras ou a primeira grade por padrão
        const gradeLetras = grades.find(g => g.nome.toLowerCase().includes('letra')) || grades[0];
        gradeSelect.value = gradeLetras.id;
        renderGradeSizes(gradeLetras.id);
      }
    } catch(e) {
      console.warn('Erro ao carregar opções de produto', e);
    }
  }

  loadFormOptions();

  if (gradeSelect) {
    gradeSelect.addEventListener('change', () => {
      renderGradeSizes(gradeSelect.value);
    });
  }

  if (formProd) {
    formProd.addEventListener('submit', async (e) => {
      e.preventDefault();
      
      const fd = new FormData(formProd);
      
      const nome = fd.get('nome');
      const categoria_id = parseInt(fd.get('categoria')) || 1;
      const grade_id = parseInt(fd.get('grade_id')) || 1;
      const cor = fd.get('cor') || 'Única';
      const preco_venda = parseFloat(fd.get('preco')) || 0;
      const qtd_minima = parseInt(fd.get('min')) || 5;
      const codigo = fd.get('codigo') || '';
      
      // Coleta todas as variações geradas pelos campos dinâmicos da grade
      const variacoes = [];
      const sizeInputs = formProd.querySelectorAll('#p-sizes-container [data-tam]');
      sizeInputs.forEach(inp => {
        const tam = inp.dataset.tam;
        const est = parseInt(inp.value) || 0;
        variacoes.push({
          tamanho: tam,
          cor: cor,
          estoque: est,
          codigo_barras: codigo ? codigo : ''
        });
      });

      if (variacoes.length === 0) {
        showToast('Nenhum tamanho disponível para a grade selecionada.', 'error');
        return;
      }

      const dados = {
        nome,
        categoria_id,
        grade_id,
        preco_venda,
        preco_custo: 0,
        qtd_minima,
        variacoes
      };

      const finalData = new FormData();
      finalData.append('dados', JSON.stringify(dados));
      if (pImage && pImage.files[0]) {
        finalData.append('imagem', pImage.files[0]);
      }

      try {
        const res = await api.request('/api/produtos', {
          method: 'POST',
          body: finalData
        });
        
        showToast('Produto cadastrado com sucesso!', 'success');
        
        const closeBtn = formProd.closest('.modal').querySelector('[data-close-modal]');
        if (closeBtn) closeBtn.click();
        
        formProd.reset();
        if (gradeSelect) {
          renderGradeSizes(gradeSelect.value);
        }
        const preview = document.getElementById('p-preview');
        const hint = document.getElementById('upload-hint');
        if(preview) preview.hidden = true;
        if(hint) hint.hidden = false;
        
        if (typeof fetchProductsCallback === 'function') {
          fetchProductsCallback();
        }

        if (typeof window.onProdutoCadastradoNaEntrada === 'function') {
          const cb = window.onProdutoCadastradoNaEntrada;
          window.onProdutoCadastradoNaEntrada = null;
          cb(res.produto);
        }
      } catch (err) {
        showToast(err.message || 'Erro ao cadastrar produto', 'error');
      }
    });

    // Aviso de nome parecido no formulário de produtos
    const pName = document.getElementById('p-name');
    if (pName && pName.parentNode) {
      const pNameWarn = document.createElement('div');
      pNameWarn.id = 'p-name-similar-warn';
      pNameWarn.style.cssText = 'color:var(--warning); font-size:0.75rem; margin-top:0.25rem; display:none;';
      pName.parentNode.appendChild(pNameWarn);
      pName.addEventListener('input', () => {
        const val = pName.value.trim();
        const normVal = (val || '').normalize('NFD').replace(/[\u0300-\u036f]/g, '').toLowerCase().replace(/\s+/g, ' ').trim();
        if (normVal.length >= 3 && window.produtosListaCache) {
          const similar = window.produtosListaCache.find(p => {
            const normP = (p.nome || '').normalize('NFD').replace(/[\u0300-\u036f]/g, '').toLowerCase().replace(/\s+/g, ' ').trim();
            return normP === normVal;
          });
          if (similar) {
            pNameWarn.innerHTML = `⚠️ Aviso: Já existe um produto cadastrado com este nome: "<strong>${escapeHtml(similar.nome)}</strong>".`;
            pNameWarn.style.display = 'block';
            return;
          }
        }
        pNameWarn.style.display = 'none';
      });
    }
  }

  if (pImage) {
    pImage.addEventListener('change', (e) => {
      const file = e.target.files[0];
      if (file) {
        const reader = new FileReader();
        reader.onload = (e) => {
          const preview = document.getElementById('p-preview');
          const hint = document.getElementById('upload-hint');
          if (preview) {
            preview.src = e.target.result;
            preview.hidden = false;
          }
          if (hint) hint.hidden = true;
        };
        reader.readAsDataURL(file);
      }
    });
  }
}

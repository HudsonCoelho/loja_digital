# Estilo Único · Sistema de Gestão ERP & PDV

![Python](https://img.shields.io/badge/Python-3.11%2B-3776AB?style=flat-square&logo=python&logoColor=white)
![Flask](https://img.shields.io/badge/Flask-2.3-000000?style=flat-square&logo=flask&logoColor=white)
![Waitress](https://img.shields.io/badge/Waitress-WSGI-2E8B57?style=flat-square)
![SQLite](https://img.shields.io/badge/SQLite-WAL%20%2B%20Online%20Backup-003B57?style=flat-square&logo=sqlite&logoColor=white)
![JavaScript](https://img.shields.io/badge/JavaScript-ES6%20Modules-F7DF1E?style=flat-square&logo=javascript&logoColor=black)
![Offline First](https://img.shields.io/badge/100%25-Offline%20First-7C5CE6?style=flat-square)
![License: MIT](https://img.shields.io/badge/License-MIT-blue?style=flat-square)

Sistema completo de **Gestão Comercial (ERP)** e **Frente de Caixa (PDV)** desenvolvido sob medida para o varejo de moda (*Estilo Único*), projetado para operar **100% offline em rede local (Wi-Fi)** sem dependência de internet ou frameworks pesados no frontend.

Construído com arquitetura em camadas no backend (**Python + Flask + Waitress + SQLite**), API REST modular (55 endpoints) e **Single Page Application (SPA)** responsiva em **JavaScript ES6 modular**, pronta para uso em desktop, tablet e celular.

---

## Principais Funcionalidades

### Frente de Caixa (PDV) e Turnos
- Registro ágil de vendas com busca instantânea por nome, SKU ou **leitor de código de barras (EAN-13)**
- Suporte a **múltiplas formas de pagamento** na mesma venda (Pix, Dinheiro com cálculo de troco, Débito, Crédito e Vale-Troca)
- Limite configurável de desconto por vendedor e cálculo automático de comissões
- **Gestão de Turno de Caixa**: abertura, suprimentos, sangrias, conferência de fechamento e resumo individual por vendedor (visível apenas para administradores)
- **Impressão de Cupom** (`cupom.html`) com dados dinâmicos da loja configurados no banco

### Estoque, Grade de Roupas e Entradas
- Cadastro de produtos com **grade de variações** (tamanho + cor), geração automática de SKU e EAN-13 interno, e upload validado de fotos
- **Ajustes avulsos de estoque** (avaria, furto, contagem, etc.) com justificativa obrigatória para perdas e auditoria completa de movimentações
- **Inventário em lote atômico**: se qualquer item for inválido, nenhuma alteração é aplicada
- Gestão de **Fornecedores** e **Entradas de Mercadorias** com atualização automática de estoque e histórico

### Vendas, Trocas e Clientes
- Histórico de vendas com filtros, cancelamento com estorno automático de estoque e devolução parcial/total com emissão de **Vale-Troca**
- Cadastro completo de clientes (CPF, telefone/WhatsApp, histórico de compras)
- **Privacidade por perfil**: vendedores visualizam apenas suas próprias vendas e não têm acesso a preços de custo, margens ou relatórios gerenciais

### Relatórios Gerenciais e Metas
- Dashboard analítico com gráficos locais (**Chart.js**): faturamento por período, métodos de pagamento e produtos parados
- Análise de **Curva ABC** por faturamento/participação
- **Metas mensais por vendedor** com acompanhamento em tempo real (descontando cancelamentos e devoluções) e cópia automática das metas do mês anterior

### Operação Offline e Backups Automáticos
- **100% Offline**: fontes tipográficas (*Inter*, *Montserrat*, *Courier Prime* em `.woff2`) e *Chart.js* hospedados localmente — zero requisições a CDNs externos
- **SQLite Online Backup API**: backups consistentes a quente sem travar o caixa, disparados automaticamente no fechamento de turno e por agendador diário em background
- Retenção automática de 30 dias + suporte a **cópia secundária** em pendrive ou pasta sincronizada (Google Drive / OneDrive) + download direto pelo painel administrativo

---

## Destaques de Engenharia e Segurança

| Camada | Implementação |
| :--- | :--- |
| **Arquitetura Backend** | Application Factory (`create_app`), 9 Blueprints REST, camada dedicada de `services/` para regras transacionais e migrações versionadas via `PRAGMA user_version` |
| **Autenticação & Sessão** | Senhas com hash via Werkzeug, prevenção de *session fixation* (`session.clear()`), invalidação automática de sessões ativas ao trocar senha e cookies `HttpOnly` + `SameSite=Lax` |
| **Proteção CSRF** | Validação em `before_request` para toda mutação `/api/*` via header `X-CSRF-Token` comparado com `secrets.compare_digest` |
| **Rate Limiting** | Bloqueio *thread-safe* por usuário + IP após 5 tentativas falhas de login (bloqueio de 5 minutos) |
| **Autorização (RBAC)** | Controle granular entre `admin` e `vendedor` (isolamento de vendas, ocultação de custo/margem, bloqueio de ajustes de estoque, metas e relatórios) |
| **Upload Seguro** | Validação de extensão permitida, limite de 5 MB, `secure_filename` e verificação de *magic bytes* (PNG, JPEG, GIF, WEBP) |
| **Headers de Segurança** | `X-Content-Type-Options: nosniff`, `X-Frame-Options: SAMEORIGIN`, `Referrer-Policy` e `Cache-Control: no-store` em respostas da API |

---

## Como Executar Rapidamente

### Pré-requisitos
- Python **3.11+** instalado

### 1. Clonar e instalar dependências
```bash
git clone https://github.com/HudsonCoelho/loja_digital.git
cd loja_digital

python -m venv .venv
# Windows (PowerShell):
.venv\Scripts\Activate.ps1
# Linux / macOS:
# source .venv/bin/activate

pip install -r requirements.txt
```

### 2. Popular dados de demonstração *(recomendado para testar)*
Para experimentar o sistema imediatamente com produtos (com fotos), estoque, clientes, caixa aberto, metas e vendas fictícias:
```bash
python popular_dados_demonstracao.py
```
Credenciais de demonstração geradas:
- **Administrador:** `admin` / `admin123`
- **Vendedora:** `carla` / `123456`

> **Ou iniciar com banco limpo:** basta pular este passo e executar `python app.py`. No primeiro acesso em `/login`, o sistema detecta automaticamente que não há usuários cadastrados e exibe o assistente para criar o primeiro **Administrador**.

### 3. Iniciar o servidor
```bash
# Modo produção (Waitress em 0.0.0.0:8000 — acessível na rede local)
python app.py

# Modo desenvolvimento (Flask com reload automático)
python app.py --dev
```
Acesse no navegador: **http://localhost:8000**

---

## Testes Automatizados

O projeto possui uma suíte automatizada de integração cobrindo regras críticas de negócio em banco temporário isolado (sem afetar dados locais):
- Controle de permissões (RBAC) em ajustes de estoque, inventário, metas, vendas, produtos, entradas e relatórios
- Atomicidade do inventário em lote e validações de baixa de estoque
- Cálculo de metas descontando vendas canceladas e devoluções
- Privacidade de vendas e fechamento de caixa por vendedor

Execute com:
```bash
python tests_backend_entrega.py
```

---

## Estrutura do Projeto

```text
loja_web/
├── app.py                           # Ponto de entrada (migração + Waitress/Flask)
├── requirements.txt                 # Dependências Python fixadas
├── popular_dados_demonstracao.py    # Seed completo com dados e imagens fictícias
├── tests_backend_entrega.py         # Suíte de testes automatizados do backend
├── iniciar_sistema.bat              # Inicialização rápida em produção (Windows)
├── configurar_inicializacao.bat     # Configura firewall (porta 8000), energia e startup
├── backup_diario.bat                # Execução manual de backup via CLI
├── loja/                            # Pacote principal da aplicação
│   ├── __init__.py                  # Factory Flask, headers de segurança e rotas SPA
│   ├── config.py                    # Configuração de caminhos e SECRET_KEY persistente
│   ├── db.py                        # Conexão SQLite e gerenciador de transações
│   ├── migrations.py                # Schema completo e migrações versionadas
│   ├── security.py                  # Auth, RBAC, CSRF e rate limiting de login
│   ├── utils.py                     # Helpers monetários, SKU, EAN-13 e ErroNegocio
│   ├── routes/                      # 9 Blueprints REST (auth, caixa, vendas, estoque...)
│   └── services/                    # Lógica transacional (vendas, caixa, devoluções, backup...)
└── static/
    ├── erp/                         # Frontend SPA 100% offline
    │   ├── index.html               # Aplicação principal
    │   ├── login.html               # Tela de login e setup inicial
    │   ├── cupom.html               # Layout de impressão de cupom
    │   ├── css/                     # Design system e @font-face locais
    │   ├── fonts/                   # Fontes .woff2 (Inter, Montserrat, Courier Prime)
    │   ├── img/                     # Favicons, placeholders e fotos de demonstração
    │   └── js/                      # ES6 modules (core/, views/ e Chart.js local)
    └── images/                      # Pasta de uploads de produtos em runtime (ignorada no Git)
```

---

## Uso em Rede Local (Windows / Loja Física)

<details>
<summary>Clique para expandir o guia operacional para uso em rede Wi-Fi da loja</summary>

1. **Execução em produção**: rode `python app.py` (ou dê dois cliques em `iniciar_sistema.bat`). O servidor **Waitress** escuta em `0.0.0.0:8000`, permitindo acesso de celulares, tablets e outros PCs na mesma rede Wi-Fi.
2. **IP local**: execute `ipconfig` no computador principal para descobrir o IPv4 (ex.: `192.168.1.150`) e acesse `http://192.168.1.150:8000` nos demais aparelhos. Recomenda-se reservar IP fixo no roteador.
3. **Firewall e inicialização automática**: execute `configurar_inicializacao.bat` como Administrador para liberar a porta `8000` apenas na rede privada, evitar suspensão do computador e iniciar o sistema junto com o Windows.
4. **Personalização da loja e backups**: no menu **Configurações** (somente admin), defina nome da loja, CNPJ/CPF, endereço, rodapé do cupom e uma pasta secundária de backup (pendrive ou nuvem).

</details>

---

## Autor

Desenvolvido por **Hudson Coelho**.

Distribuído sob a licença [MIT](LICENSE).

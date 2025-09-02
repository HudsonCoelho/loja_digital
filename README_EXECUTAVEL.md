# 🚀 Sistema de Vendas - Executável

## 📋 Informações do Executável

- **Arquivo:** `SistemaVendas.exe`
- **Tamanho:** ~26MB
- **Localização:** `dist/SistemaVendas.exe`
- **Sistema:** Windows 64-bit

## 🎯 Como Usar

### 1. **Executar o Programa**
- Dê duplo clique no arquivo `SistemaVendas.exe`
- Ou execute via linha de comando: `.\SistemaVendas.exe`

### 2. **Acessar a Aplicação**
- O servidor será iniciado automaticamente
- Abra seu navegador
- Acesse: `http://127.0.0.1:5000`

### 3. **Funcionalidades Disponíveis**
- ✅ **Dashboard** - Visão geral do sistema
- ✅ **Cadastrar Produtos** - Adicionar produtos com imagens
- ✅ **Estoque** - Gerenciar produtos (editar/excluir)
- ✅ **Registrar Vendas** - Processar vendas
- ✅ **Relatórios** - Visualizar histórico de vendas
- ✅ **Gráficos** - Análises estatísticas
- ✅ **Configurações** - Personalizar fundo do site

## 🔧 Características Técnicas

### **Banco de Dados**
- SQLite3 integrado
- Arquivo: `estoque.db` (criado automaticamente)
- Não requer instalação de banco de dados

### **Arquivos Incluídos**
- ✅ Templates HTML
- ✅ Arquivos CSS/JS
- ✅ Pasta de imagens
- ✅ Todas as dependências Python

### **Requisitos do Sistema**
- Windows 10/11 (64-bit)
- Não requer Python instalado
- Não requer dependências adicionais

## 📁 Estrutura de Arquivos

```
SistemaVendas.exe
├── Banco de dados (criado automaticamente)
├── Pasta de imagens (criada automaticamente)
└── Logs do sistema
```

## 🚨 Importante

### **Primeira Execução**
- O banco de dados será criado automaticamente
- A pasta `static/images` será criada para uploads
- Todas as tabelas serão inicializadas

### **Segurança**
- Mantenha o executável em local seguro
- Faça backup do arquivo `estoque.db` regularmente
- Não compartilhe o executável com pessoas não autorizadas

## 🔄 Atualizações

Para atualizar o sistema:
1. Pare o executável atual (Ctrl+C)
2. Substitua o arquivo `SistemaVendas.exe`
3. Execute novamente

## 📞 Suporte

Em caso de problemas:
1. Verifique se o Windows Defender não bloqueou o arquivo
2. Execute como administrador se necessário
3. Verifique se a porta 5000 não está em uso

## 🎉 Pronto para Usar!

O executável está pronto para distribuição e uso em qualquer computador Windows sem necessidade de instalação de Python ou dependências adicionais.

"""Popula o banco SQLite com dados fictícios completos para demonstração do ERP/PDV.

Uso:
    python popular_dados_demonstracao.py
    python popular_dados_demonstracao.py caminho/opcional/banco.db
"""
import sqlite3
import sys
from datetime import datetime
from werkzeug.security import generate_password_hash

from loja.config import build_config
from loja.migrations import migrate


def popular_demo(db_path: str | None = None, backup_dir: str | None = None) -> None:
    cfg = build_config()
    db_path = db_path or cfg["DATABASE"]
    backup_dir = backup_dir or cfg["BACKUP_DIR"]

    # Garante que o banco existe e está migrado para a última versão
    migrate(db_path, backup_dir)

    conn = sqlite3.connect(db_path)
    cursor = conn.cursor()

    senha_admin = generate_password_hash("admin123")
    senha_vendedor = generate_password_hash("123456")

    # 1. Usuários de demonstração (Admin + Vendedora)
    cursor.execute("UPDATE usuarios SET nome = ?, senha_hash = ?, perfil = 'admin', ativo = 1 WHERE LOWER(login) = 'admin'",
                   ("Administrador Demo", senha_admin))
    if cursor.rowcount == 0:
        cursor.execute("""
            INSERT INTO usuarios (nome, login, senha_hash, perfil, ativo)
            VALUES ('Administrador Demo', 'admin', ?, 'admin', 1)
        """, (senha_admin,))

    cursor.execute("SELECT id FROM usuarios WHERE LOWER(login) = 'admin'")
    admin_id = cursor.fetchone()[0]

    cursor.execute("SELECT id FROM usuarios WHERE LOWER(login) = 'carla'")
    row = cursor.fetchone()
    if not row:
        cursor.execute("""
            INSERT INTO usuarios (nome, login, senha_hash, perfil, comissao_pct, desconto_max_pct, ativo)
            VALUES ('Carla Mendes', 'carla', ?, 'vendedor', 3.5, 10.0, 1)
        """, (senha_vendedor,))
        carla_id = cursor.lastrowid
    else:
        cursor.execute("UPDATE usuarios SET senha_hash = ?, ativo = 1 WHERE id = ?", (senha_vendedor, row[0]))
        carla_id = row[0]

    # Mapear categorias e grades pelo nome
    categorias = {nome: cid for cid, nome in cursor.execute("SELECT id, nome FROM categorias").fetchall()}
    grades = {nome: gid for gid, nome in cursor.execute("SELECT id, nome FROM grades").fetchall()}
    cat = lambda nome: categorias.get(nome, 1)
    grd = lambda nome: grades.get(nome, 1)

    # 2. Configurações de demonstração da loja
    configs_demo = {
        "loja_nome": "Estilo Único",
        "loja_documento": "00.000.000/0001-00",
        "loja_telefone": "(11) 99999-0000",
        "loja_endereco": "Av. Paulista, 1000 - Loja 12, São Paulo - SP",
        "cupom_rodape": "Obrigado pela preferência! Trocas em até 30 dias com etiqueta.",
    }
    for chave, valor in configs_demo.items():
        cursor.execute("""
            INSERT INTO configuracoes (chave, valor) VALUES (?, ?)
            ON CONFLICT(chave) DO UPDATE SET valor = excluded.valor
        """, (chave, valor))

    # 3. Limpar dados transacionais antigos para recriar demonstração limpa
    for tabela in ("venda_pagamentos", "venda_itens", "vendas", "caixa_movimentos",
                   "caixas", "metas_vendedor", "movimentacoes_estoque",
                   "variacoes", "produtos", "clientes", "fornecedores"):
        cursor.execute(f"DELETE FROM {tabela}")

    # 4. Clientes fictícios
    cursor.execute("""
        INSERT INTO clientes (nome, cpf, telefone, email)
        VALUES ('Mariana Costa', '123.456.789-00', '(11) 98765-4321', 'mariana.demo@example.com')
    """)
    cli_mariana = cursor.lastrowid

    cursor.execute("""
        INSERT INTO clientes (nome, cpf, telefone, email)
        VALUES ('Lucas Fernandes', '987.654.321-99', '(21) 97654-3210', 'lucas.demo@example.com')
    """)
    cli_lucas = cursor.lastrowid

    # 5. Fornecedor fictício
    cursor.execute("""
        INSERT INTO fornecedores (nome, cnpj, telefone, email, contato, ativo)
        VALUES ('Moda Brasil Confecções', '12.345.678/0001-90', '(11) 3322-1100', 'contato@modabrasil.example.com', 'Roberto Alves', 1)
    """)

    # 6. Produtos e variações (com imagens locais incluídas no repositório)
    cursor.execute("""
        INSERT INTO produtos (nome, categoria_id, grade_id, preco_venda, preco_custo, qtd_minima, descricao, imagem, ativo)
        VALUES ('Vestido Midi Seda Floral', ?, ?, 189.90, 85.00, 3,
                'Vestido elegante em tecido de seda com estampa floral exclusiva.',
                'erp/img/vestido_floral.jpg', 1)
    """, (cat("Vestidos"), grd("Letras")))
    p1 = cursor.lastrowid
    cursor.execute("INSERT INTO variacoes (produto_id, sku, codigo_barras, tamanho, cor, estoque, ativo) VALUES (?, 'VES-FLOR-P-AZ', '7891000000011', 'P', 'Azul', 8, 1)", (p1,))
    v1_p = cursor.lastrowid
    cursor.execute("INSERT INTO variacoes (produto_id, sku, codigo_barras, tamanho, cor, estoque, ativo) VALUES (?, 'VES-FLOR-M-AZ', '7891000000028', 'M', 'Azul', 12, 1)", (p1,))
    cursor.execute("INSERT INTO variacoes (produto_id, sku, codigo_barras, tamanho, cor, estoque, ativo) VALUES (?, 'VES-FLOR-G-AZ', '7891000000035', 'G', 'Azul', 4, 1)", (p1,))

    cursor.execute("""
        INSERT INTO produtos (nome, categoria_id, grade_id, preco_venda, preco_custo, qtd_minima, descricao, imagem, ativo)
        VALUES ('Camisa Linho Manga Longa', ?, ?, 149.90, 65.00, 5,
                'Camisa social esporte fino em 100% linho puro.',
                'erp/img/camisa_linho.jpg', 1)
    """, (cat("Camisas"), grd("Letras")))
    p2 = cursor.lastrowid
    cursor.execute("INSERT INTO variacoes (produto_id, sku, codigo_barras, tamanho, cor, estoque, ativo) VALUES (?, 'CAM-LIN-M-BR', '7891000000042', 'M', 'Branco', 15, 1)", (p2,))
    v2_m = cursor.lastrowid
    cursor.execute("INSERT INTO variacoes (produto_id, sku, codigo_barras, tamanho, cor, estoque, ativo) VALUES (?, 'CAM-LIN-G-BR', '7891000000059', 'G', 'Branco', 10, 1)", (p2,))
    cursor.execute("INSERT INTO variacoes (produto_id, sku, codigo_barras, tamanho, cor, estoque, ativo) VALUES (?, 'CAM-LIN-GG-AZ', '7891000000066', 'GG', 'Azul Claro', 2, 1)", (p2,))

    cursor.execute("""
        INSERT INTO produtos (nome, categoria_id, grade_id, preco_venda, preco_custo, qtd_minima, descricao, imagem, ativo)
        VALUES ('Calça Jeans Slim Denim', ?, ?, 199.90, 89.00, 4,
                'Calça jeans com elastano e modelagem slim fit.',
                'erp/img/calca_jeans.jpg', 1)
    """, (cat("Calças"), grd("Numérica")))
    p3 = cursor.lastrowid
    cursor.execute("INSERT INTO variacoes (produto_id, sku, codigo_barras, tamanho, cor, estoque, ativo) VALUES (?, 'JEA-SLI-38-ES', '7891000000073', '38', 'Azul Escuro', 6, 1)", (p3,))
    cursor.execute("INSERT INTO variacoes (produto_id, sku, codigo_barras, tamanho, cor, estoque, ativo) VALUES (?, 'JEA-SLI-40-ES', '7891000000080', '40', 'Azul Escuro', 9, 1)", (p3,))
    cursor.execute("INSERT INTO variacoes (produto_id, sku, codigo_barras, tamanho, cor, estoque, ativo) VALUES (?, 'JEA-SLI-42-ES', '7891000000097', '42', 'Azul Escuro', 7, 1)", (p3,))

    cursor.execute("""
        INSERT INTO produtos (nome, categoria_id, grade_id, preco_venda, preco_custo, qtd_minima, descricao, imagem, ativo)
        VALUES ('Camiseta Algodão Egípcio', ?, ?, 89.90, 32.00, 10,
                'Camiseta básica premium com toque macio e caimento reto.',
                'erp/img/camiseta_preta.jpg', 1)
    """, (cat("Camisetas"), grd("Letras")))
    p4 = cursor.lastrowid
    cursor.execute("INSERT INTO variacoes (produto_id, sku, codigo_barras, tamanho, cor, estoque, ativo) VALUES (?, 'TSH-EGI-P-PR', '7891000000103', 'P', 'Preto', 20, 1)", (p4,))
    cursor.execute("INSERT INTO variacoes (produto_id, sku, codigo_barras, tamanho, cor, estoque, ativo) VALUES (?, 'TSH-EGI-M-PR', '7891000000110', 'M', 'Preto', 25, 1)", (p4,))
    v4_m = cursor.lastrowid
    cursor.execute("INSERT INTO variacoes (produto_id, sku, codigo_barras, tamanho, cor, estoque, ativo) VALUES (?, 'TSH-EGI-G-BR', '7891000000127', 'G', 'Branco', 18, 1)", (p4,))

    cursor.execute("""
        INSERT INTO produtos (nome, categoria_id, grade_id, preco_venda, preco_custo, qtd_minima, descricao, imagem, ativo)
        VALUES ('Calça Alfaiataria Reta', ?, ?, 229.90, 105.00, 3,
                'Calça de alfaiataria com cintura alta e corte estruturado.',
                'erp/img/calca_alfaiataria.jpg', 1)
    """, (cat("Calças"), grd("Numérica")))
    p5 = cursor.lastrowid
    cursor.execute("INSERT INTO variacoes (produto_id, sku, codigo_barras, tamanho, cor, estoque, ativo) VALUES (?, 'ALF-RET-38-BG', '7891000000134', '38', 'Bege', 5, 1)", (p5,))
    cursor.execute("INSERT INTO variacoes (produto_id, sku, codigo_barras, tamanho, cor, estoque, ativo) VALUES (?, 'ALF-RET-40-BG', '7891000000141', '40', 'Bege', 7, 1)", (p5,))

    cursor.execute("""
        INSERT INTO produtos (nome, categoria_id, grade_id, preco_venda, preco_custo, qtd_minima, descricao, imagem, ativo)
        VALUES ('Vestido Longo Crepe Lavanda', ?, ?, 259.90, 118.00, 3,
                'Vestido longo fluido em crepe leve para ocasiões especiais.',
                'erp/img/vestido_roxo.jpg', 1)
    """, (cat("Vestidos"), grd("Letras")))
    p6 = cursor.lastrowid
    cursor.execute("INSERT INTO variacoes (produto_id, sku, codigo_barras, tamanho, cor, estoque, ativo) VALUES (?, 'VES-CRP-P-RX', '7891000000158', 'P', 'Roxo', 4, 1)", (p6,))
    cursor.execute("INSERT INTO variacoes (produto_id, sku, codigo_barras, tamanho, cor, estoque, ativo) VALUES (?, 'VES-CRP-M-RX', '7891000000165', 'M', 'Roxo', 6, 1)", (p6,))

    # 7. Caixa aberto
    hoje = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    ano = datetime.now().strftime("%Y")
    cursor.execute("INSERT INTO caixas (aberto_por, valor_abertura, aberto_em, status) VALUES (?, 150.00, ?, 'aberto')",
                   (admin_id, hoje))
    caixa_id = cursor.lastrowid

    # 8. Vendas de demonstração
    cursor.execute("""
        INSERT INTO vendas (codigo, data, cliente_id, vendedor_id, caixa_id, subtotal, desconto, total, custo_total, troco, status)
        VALUES (?, ?, ?, ?, ?, 279.80, 0.0, 279.80, 117.00, 0.0, 'concluida')
    """, (f"VEN-{ano}-0001", hoje, cli_mariana, carla_id, caixa_id))
    venda1_id = cursor.lastrowid

    cursor.execute("""
        INSERT INTO venda_itens (venda_id, variacao_id, produto_id, nome, tamanho, cor, quantidade, preco_unit, custo_unit, desconto, total, qtd_devolvida)
        VALUES (?, ?, ?, 'Vestido Midi Seda Floral', 'P', 'Azul', 1, 189.90, 85.00, 0.0, 189.90, 0)
    """, (venda1_id, v1_p, p1))
    cursor.execute("""
        INSERT INTO venda_itens (venda_id, variacao_id, produto_id, nome, tamanho, cor, quantidade, preco_unit, custo_unit, desconto, total, qtd_devolvida)
        VALUES (?, ?, ?, 'Camiseta Algodão Egípcio', 'M', 'Preto', 1, 89.90, 32.00, 0.0, 89.90, 0)
    """, (venda1_id, v4_m, p4))
    cursor.execute("INSERT INTO venda_pagamentos (venda_id, forma, valor) VALUES (?, 'Pix', 279.80)", (venda1_id,))

    cursor.execute("""
        INSERT INTO vendas (codigo, data, cliente_id, vendedor_id, caixa_id, subtotal, desconto, total, custo_total, troco, status)
        VALUES (?, ?, ?, ?, ?, 149.90, 0.0, 149.90, 65.00, 0.10, 'concluida')
    """, (f"VEN-{ano}-0002", hoje, cli_lucas, admin_id, caixa_id))
    venda2_id = cursor.lastrowid
    cursor.execute("""
        INSERT INTO venda_itens (venda_id, variacao_id, produto_id, nome, tamanho, cor, quantidade, preco_unit, custo_unit, desconto, total, qtd_devolvida)
        VALUES (?, ?, ?, 'Camisa Linho Manga Longa', 'M', 'Branco', 1, 149.90, 65.00, 0.0, 149.90, 0)
    """, (venda2_id, v2_m, p2))
    cursor.execute("INSERT INTO venda_pagamentos (venda_id, forma, valor) VALUES (?, 'Dinheiro', 150.00)", (venda2_id,))

    # 9. Metas do mês
    periodo_atual = datetime.now().strftime("%Y-%m")
    cursor.execute("""
        INSERT INTO metas_vendedor (vendedor_id, periodo, valor_meta)
        VALUES (?, ?, 12000.00)
    """, (carla_id, periodo_atual))

    conn.commit()
    conn.close()
    print("Dados de demonstração populados com sucesso!")
    print("  Admin    -> login: admin  | senha: admin123")
    print("  Vendedor -> login: carla  | senha: 123456")


if __name__ == "__main__":
    destino = sys.argv[1] if len(sys.argv) > 1 else None
    popular_demo(destino)

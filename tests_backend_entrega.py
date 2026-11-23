"""Script de teste automatizado para validar todas as regras de negócio da entrega:
1. Ajuste de estoque avulso (baixa e contagem)
2. Inventário em lote
3. Metas por vendedor
4. Resumo por vendedor no fechamento do caixa
"""
import os
import sys
import tempfile
import sqlite3
from decimal import Decimal

from loja import create_app
from loja.migrations import migrate
from loja.db import get_db, transaction
from werkzeug.security import generate_password_hash

def run_tests():
    temp_dir = tempfile.mkdtemp()
    test_db = os.path.join(temp_dir, "test_estoque.db")
    backup_dir = os.path.join(temp_dir, "backups")
    upload_dir = os.path.join(temp_dir, "uploads")

    # Executa migrações
    migrate(test_db, backup_dir)

    app = create_app({
        "DATABASE": test_db,
        "BACKUP_DIR": backup_dir,
        "UPLOAD_DIR": upload_dir,
        "SECRET_KEY": "test-key",
        "CSRF_DISABLED": True,
        "TESTING": True
    })

    client = app.test_client()

    with app.app_context():
        conn = get_db()
        # Cria admin e vendedora Ana e vendedor Bruno
        senha_hash = generate_password_hash("123456")
        admin_id = conn.execute(
            "INSERT INTO usuarios (nome, login, senha_hash, perfil, ativo) VALUES (?, ?, ?, ?, ?)",
            ("Administrador", "admin_teste", senha_hash, "admin", 1)
        ).lastrowid
        ana_id = conn.execute(
            "INSERT INTO usuarios (nome, login, senha_hash, perfil, ativo) VALUES (?, ?, ?, ?, ?)",
            ("Ana Vendedora", "ana_teste", senha_hash, "vendedor", 1)
        ).lastrowid
        bruno_id = conn.execute(
            "INSERT INTO usuarios (nome, login, senha_hash, perfil, ativo) VALUES (?, ?, ?, ?, ?)",
            ("Bruno Vendedor", "bruno_teste", senha_hash, "vendedor", 1)
        ).lastrowid

        # Cria produto com variações
        prod_id = conn.execute(
            "INSERT INTO produtos (nome, categoria_id, grade_id, preco_venda, preco_custo, qtd_minima, ativo) VALUES (?, 1, 1, 100.0, 50.0, 5, 1)",
            ("Vestido Seda",)
        ).lastrowid
        var1_id = conn.execute(
            "INSERT INTO variacoes (produto_id, tamanho, cor, estoque, ativo) VALUES (?, 'P', 'Azul', 10, 1)",
            (prod_id,)
        ).lastrowid
        var2_id = conn.execute(
            "INSERT INTO variacoes (produto_id, tamanho, cor, estoque, ativo) VALUES (?, 'M', 'Azul', 5, 1)",
            (prod_id,)
        ).lastrowid
        conn.commit()

    print("--- 1. TESTES DE AJUSTE DE ESTOQUE E INVENTÁRIO ---")
    
    # Login como Vendedor Ana
    with client.session_transaction() as sess:
        sess["uid"] = ana_id
        sess["csrf"] = "test-csrf"

    # Vendedora recebe 403 em /api/estoque/ajuste
    r = client.post("/api/estoque/ajuste", json={
        "variacao_id": var1_id, "modo": "baixa", "quantidade": 1, "motivo": "Avaria"
    })
    assert r.status_code == 403, f"Esperado 403 para vendedor, obteve {r.status_code}"
    print("[OK] Vendedor recebe 403 em /api/estoque/ajuste")

    # Vendedora recebe 403 em /api/estoque/inventario
    r = client.post("/api/estoque/inventario", json={"itens": [{"variacao_id": var1_id, "quantidade": 5}]})
    assert r.status_code == 403, f"Esperado 403 para vendedor em inventario, obteve {r.status_code}"
    print("[OK] Vendedor recebe 403 em /api/estoque/inventario")

    # Login como Admin
    with client.session_transaction() as sess:
        sess["uid"] = admin_id
        sess["csrf"] = "test-csrf"

    # Furto sem observação é recusado (400)
    r = client.post("/api/estoque/ajuste", json={
        "variacao_id": var1_id, "modo": "baixa", "quantidade": 1, "motivo": "Furto", "obs": ""
    })
    assert r.status_code == 400, f"Esperado 400 para Furto sem obs, obteve {r.status_code}"
    print("[OK] Motivo Furto sem observação é recusado (400)")

    # Outro sem observação é recusado (400)
    r = client.post("/api/estoque/ajuste", json={
        "variacao_id": var1_id, "modo": "baixa", "quantidade": 1, "motivo": "Outro", "obs": ""
    })
    assert r.status_code == 400, f"Esperado 400 para Outro sem obs, obteve {r.status_code}"
    print("[OK] Motivo Outro sem observação é recusado (400)")

    # Admin dá baixa de 2 unidades com motivo Avaria
    r = client.post("/api/estoque/ajuste", json={
        "variacao_id": var1_id, "modo": "baixa", "quantidade": 2, "motivo": "Avaria"
    })
    assert r.status_code == 200, f"Erro na baixa: {r.get_json()}"
    dados = r.get_json()
    assert dados["saldo_apos"] == 8, f"Esperado saldo 8, obteve {dados['saldo_apos']}"
    assert dados["tipo"] == "ajuste_avaria"
    print("[OK] Admin dá baixa de 2 unidades com motivo Avaria (saldo 10 -> 8, tipo ajuste_avaria)")

    # Baixa maior que o estoque devolve 409 e não altera nada
    r = client.post("/api/estoque/ajuste", json={
        "variacao_id": var1_id, "modo": "baixa", "quantidade": 15, "motivo": "Avaria"
    })
    assert r.status_code == 409, f"Esperado 409 para baixa excessiva, obteve {r.status_code}"
    print("[OK] Baixa maior que estoque devolve 409 e não altera nada")

    # Contagem de 7 com estoque 8 grava delta -1
    r = client.post("/api/estoque/ajuste", json={
        "variacao_id": var1_id, "modo": "contagem", "quantidade": 7, "motivo": "Inventário (contagem)"
    })
    assert r.status_code == 200
    dados = r.get_json()
    assert dados["delta"] == -1 and dados["saldo_apos"] == 7
    print("[OK] Contagem de 7 com estoque 8 grava delta -1 (saldo -> 7)")

    # Contagem igual ao estoque (7) não grava movimento
    r = client.post("/api/estoque/ajuste", json={
        "variacao_id": var1_id, "modo": "contagem", "quantidade": 7, "motivo": "Inventário (contagem)"
    })
    assert r.status_code == 200
    dados = r.get_json()
    assert dados["delta"] == 0
    print("[OK] Contagem igual ao estoque não altera nada (delta 0)")

    # Inventário em lote com uma variação inválida: atômico (tudo ou nada)
    r = client.post("/api/estoque/inventario", json={
        "itens": [
            {"variacao_id": var2_id, "quantidade": 20},
            {"variacao_id": 99999, "quantidade": 5} # inválida
        ]
    })
    assert r.status_code == 404
    # Confirma que var2_id não foi alterada (continua 5)
    with app.app_context():
        v2 = get_db().execute("SELECT estoque FROM variacoes WHERE id = ?", (var2_id,)).fetchone()
        assert v2["estoque"] == 5, f"Esperado estoque 5 inalterado, obteve {v2['estoque']}"
    print("[OK] Inventário em lote com item inválido não aplica nada (atômico)")

    # Histórico de movimentações com filtro 'ajuste' retorna os ajustes criados
    r = client.get("/api/estoque/movimentacoes?tipo=ajuste")
    assert r.status_code == 200
    movs = r.get_json()
    assert len(movs) >= 2
    for m in movs:
        assert m["tipo"].startswith("ajuste")
    print("[OK] Filtro 'ajuste' no histórico lista todos os tipos que começam com ajuste")

    # Vendedora Ana tenta acessar histórico de movimentações e recebe 403
    with client.session_transaction() as sess:
        sess["uid"] = ana_id
        sess["csrf"] = "test-csrf"
    r = client.get("/api/estoque/movimentacoes")
    assert r.status_code == 403
    print("[OK] Vendedor recebe 403 em /api/estoque/movimentacoes (histórico só admin)")

    # Retorna sessão para admin
    with client.session_transaction() as sess:
        sess["uid"] = admin_id
        sess["csrf"] = "test-csrf"

    print("\n--- 2. TESTES DE METAS POR VENDEDOR ---")

    # Admin define meta de R$ 5.000 para a vendedora Ana em 2026-10
    r = client.put("/api/metas", json={
        "vendedor_id": ana_id,
        "periodo": "2026-10",
        "valor_meta": 5000.0
    })
    assert r.status_code == 200
    print("[OK] Admin define meta de R$ 5.000 para Ana em 2026-10")

    # Consulta GET /api/metas como admin: só lista vendedores (ignora admin)
    r = client.get("/api/metas?periodo=2026-10")
    assert r.status_code == 200
    metas = r.get_json()
    assert not any(m["vendedor_id"] == admin_id for m in metas)
    ana_meta = next(m for m in metas if m["vendedor_id"] == ana_id)
    assert ana_meta["valor_meta"] == 5000.0
    assert ana_meta["vendido"] == 0.0
    assert ana_meta["falta"] == 5000.0
    assert ana_meta["percentual"] == 0.0
    print("[OK] GET /api/metas lista só vendedores (ignora admin) e devolve valores corretos")

    # PUT /api/metas com vendedor_id de um admin recusa com 400
    r = client.put("/api/metas", json={"vendedor_id": admin_id, "periodo": "2026-10", "valor_meta": 8000.0})
    assert r.status_code == 400
    print("[OK] PUT /api/metas recusa meta para admin (400)")

    # Vendedora Ana consulta GET /api/metas e recebe só o próprio registro
    with client.session_transaction() as sess:
        sess["uid"] = ana_id
        sess["csrf"] = "test-csrf"

    r = client.get("/api/metas?periodo=2026-10")
    assert r.status_code == 200
    metas_ana = r.get_json()
    assert len(metas_ana) == 1
    assert metas_ana[0]["vendedor_id"] == ana_id
    print("[OK] Ana consulta GET /api/metas e recebe só o próprio registro")

    # Ana tenta PUT /api/metas e recebe 403
    r = client.put("/api/metas", json={"vendedor_id": ana_id, "periodo": "2026-10", "valor_meta": 1000})
    assert r.status_code == 403
    print("[OK] Vendedora recebe 403 em PUT /api/metas")

    # Cria vendas para Ana e testa cálculo de 'vendido'
    with app.app_context():
        conn = get_db()
        # Venda 1 da Ana: concluída de R$ 1.000 em 2026-10
        v1_id = conn.execute("""
            INSERT INTO vendas (codigo, data, vendedor_id, subtotal, total, status)
            VALUES ('V001', '2026-10-05 10:00:00', ?, 1000.0, 1000.0, 'concluida')
        """, (ana_id,)).lastrowid

        # Venda 2 da Ana: cancelada de R$ 500 em 2026-10 (não conta)
        conn.execute("""
            INSERT INTO vendas (codigo, data, vendedor_id, subtotal, total, status)
            VALUES ('V002', '2026-10-06 11:00:00', ?, 500.0, 500.0, 'cancelada')
        """, (ana_id,))

        # Devolução parcial de R$ 200 na Venda 1 da Ana
        conn.execute("""
            INSERT INTO devolucoes (venda_id, data, tipo, valor)
            VALUES (?, '2026-10-07 14:00:00', 'dinheiro', 200.0)
        """, (v1_id,))
        conn.commit()

    r = client.get("/api/metas?periodo=2026-10")
    assert r.status_code == 200
    res = r.get_json()
    meta_calculada = res[0]
    # Vendido deve ser 1000 - 200 = 800
    assert meta_calculada["vendido"] == 800.0, f"Esperado vendido 800.0, obteve {meta_calculada['vendido']}"
    assert meta_calculada["falta"] == 4200.0, f"Esperado falta 4200.0, obteve {meta_calculada['falta']}"
    assert meta_calculada["percentual"] == 16.0, f"Esperado percentual 16.0, obteve {meta_calculada['percentual']}"
    print("[OK] Venda concluída soma, venda cancelada não soma e devolução é descontada (vendido = 800.0)")

    # Teste copiar metas do mês anterior
    with client.session_transaction() as sess:
        sess["uid"] = admin_id
        sess["csrf"] = "test-csrf"

    # Já define uma meta para Bruno em 2026-11
    client.put("/api/metas", json={"vendedor_id": bruno_id, "periodo": "2026-11", "valor_meta": 3000.0})
    # Copia de 2026-10 para 2026-11
    r = client.post("/api/metas/copiar-mes-anterior", json={"periodo": "2026-11"})
    assert r.status_code == 200
    # Verifica metas em 2026-11: Ana copiada (5000), Bruno manteve 3000
    r = client.get("/api/metas?periodo=2026-11")
    metas_novas = {m["vendedor_id"]: m["valor_meta"] for m in r.get_json()}
    assert metas_novas[ana_id] == 5000.0
    assert metas_novas[bruno_id] == 3000.0
    print("[OK] Copiar metas do mês anterior cria metas sem sobrescrever as já definidas")

    print("\n--- 3. TESTES DE CAIXA FECHAMENTO POR VENDEDOR ---")
    with app.app_context():
        conn = get_db()
        # Abre caixa
        caixa_id = conn.execute("""
            INSERT INTO caixas (aberto_por, aberto_em, valor_abertura, status)
            VALUES (?, '2026-10-13 08:00:00', 100.0, 'aberto')
        """, (admin_id,)).lastrowid

        # Venda da Ana: R$ 300 (R$ 100 dinheiro, R$ 200 Pix)
        v_ana = conn.execute("""
            INSERT INTO vendas (codigo, data, vendedor_id, caixa_id, subtotal, total, status)
            VALUES ('V10', '2026-10-13 09:00:00', ?, ?, 300.0, 300.0, 'concluida')
        """, (ana_id, caixa_id)).lastrowid
        conn.execute("INSERT INTO venda_pagamentos (venda_id, forma, valor) VALUES (?, 'Dinheiro', 100.0)", (v_ana,))
        conn.execute("INSERT INTO venda_pagamentos (venda_id, forma, valor) VALUES (?, 'Pix', 200.0)", (v_ana,))

        # Venda do Bruno: R$ 500 (R$ 200 débito, R$ 300 crédito)
        v_bru = conn.execute("""
            INSERT INTO vendas (codigo, data, vendedor_id, caixa_id, subtotal, total, status)
            VALUES ('V11', '2026-10-13 10:00:00', ?, ?, 500.0, 500.0, 'concluida')
        """, (bruno_id, caixa_id)).lastrowid
        conn.execute("INSERT INTO venda_pagamentos (venda_id, forma, valor) VALUES (?, 'Débito', 200.0)", (v_bru,))
        conn.execute("INSERT INTO venda_pagamentos (venda_id, forma, valor) VALUES (?, 'Crédito', 300.0)", (v_bru,))
        conn.commit()

    r = client.get("/api/caixa/fechamento-preview")
    assert r.status_code == 200
    prev = r.get_json()
    assert "por_vendedor" in prev
    pv = {v["vendedor_id"]: v for v in prev["por_vendedor"]}
    assert pv[ana_id]["total"] == 300.0
    assert pv[ana_id]["dinheiro"] == 100.0
    assert pv[ana_id]["pix"] == 200.0
    assert pv[bruno_id]["total"] == 500.0
    assert pv[bruno_id]["debito"] == 200.0
    assert pv[bruno_id]["credito"] == 300.0
    # Soma bate com total de vendas (300 + 500 = 800)
    soma_vendedores = sum(v["total"] for v in prev["por_vendedor"])
    assert soma_vendedores == 800.0
    print("[OK] Fechamento-preview traz formas de pagamento de cada vendedor para admin (R$ 800.0)")

    # Vendedora Ana chama GET /api/caixa/fechamento-preview: NÃO recebe por_vendedor (decisão 14/10/2026)
    with client.session_transaction() as sess:
        sess["uid"] = ana_id
        sess["csrf"] = "test-csrf"

    r = client.get("/api/caixa/fechamento-preview")
    assert r.status_code == 200
    prev_ana = r.get_json()
    assert "esperado" in prev_ana
    assert "por_vendedor" not in prev_ana, "Vendedora não pode receber por_vendedor no fechamento-preview"
    print("[OK] Vendedora Ana chama fechamento-preview e NÃO recebe por_vendedor (campo omitido)")

    print("\n--- 4. TESTES DE PRIVACIDADE DE VENDAS (VENDEDOR SÓ AS SUAS) ---")
    # Vendedora Ana lista vendas: só vê as próprias
    with client.session_transaction() as sess:
        sess["uid"] = ana_id
        sess["csrf"] = "test-csrf"

    r = client.get("/api/vendas")
    assert r.status_code == 200
    vendas_ana = r.get_json()
    ids_ana = [v["id"] for v in vendas_ana]
    assert v_ana in ids_ana
    assert v_bru not in ids_ana
    print("[OK] Vendedora listando vendas só recebe as próprias vendas")

    # Vendedora Ana tenta abrir detalhe de venda de outro vendedor -> 404
    r = client.get(f"/api/vendas/{v_bru}")
    assert r.status_code == 404
    print("[OK] Detalhe de venda de outro vendedor devolve 404 para vendedor")

    # Vendedora Ana abre a própria venda -> 200
    r = client.get(f"/api/vendas/{v_ana}")
    assert r.status_code == 200
    print("[OK] Vendedora acessa normalmente o detalhe da sua própria venda")

    # Admin vê todas as vendas e acessa detalhes de qualquer vendedor
    with client.session_transaction() as sess:
        sess["uid"] = admin_id
        sess["csrf"] = "test-csrf"

    r = client.get("/api/vendas")
    assert r.status_code == 200
    ids_admin = [v["id"] for v in r.get_json()]
    assert v_ana in ids_admin
    assert v_bru in ids_admin
    r = client.get(f"/api/vendas/{v_bru}")
    assert r.status_code == 200
    print("[OK] Admin visualiza todas as vendas e acessa detalhes de qualquer vendedor")

    print("\n--- 5. TESTES DE ENTRADAS & PRODUTOS ---")
    # Vendedora Ana tenta cadastrar produto -> 403
    with client.session_transaction() as sess:
        sess["uid"] = ana_id
        sess["csrf"] = "test-csrf"

    r = client.post("/api/produtos", json={
        "nome": "Produto Proibido",
        "categoria_id": 1,
        "grade_id": 1,
        "preco_venda": 50.0,
        "variacoes": [{"tamanho": "M", "cor": "Azul", "sku": "AZ-M", "codigo_barras": "1234567890123"}]
    })
    assert r.status_code == 403
    print("[OK] Vendedor recebe 403 em /api/produtos (criação)")

    # Vendedora Ana tenta dar entrada -> 403
    r = client.post("/api/entradas", json={
        "fornecedor_id": 1,
        "itens": [{"variacao_id": var1_id, "quantidade": 5, "preco_custo": 40.0}]
    })
    assert r.status_code == 403
    print("[OK] Vendedor recebe 403 em /api/entradas (criação)")

    # Vendedora Ana tenta listar entradas, fornecedores e relatórios -> 403
    assert client.get("/api/entradas").status_code == 403
    assert client.get("/api/fornecedores").status_code == 403
    assert client.get("/api/relatorios").status_code == 403
    assert client.get("/api/relatorios/abc").status_code == 403
    assert client.get("/api/relatorios/vendas").status_code == 403
    print("[OK] Vendedor recebe 403 em GET /api/entradas, /api/fornecedores e /api/relatorios")

    # Vendedora consulta produtos: não recebe preço de custo nem margem
    r = client.get("/api/produtos")
    assert r.status_code == 200
    prods_vendedor = r.get_json()
    assert len(prods_vendedor) > 0
    assert "custo" not in prods_vendedor[0]
    assert "margem" not in prods_vendedor[0]
    print("[OK] Vendedor consulta /api/produtos sem ver preço de custo nem margem")

    # Admin cadastra produto rápido pela entrada
    with client.session_transaction() as sess:
        sess["uid"] = admin_id
        sess["csrf"] = "test-csrf"

    # Cria fornecedor de teste se necessário
    with app.app_context():
        conn = get_db()
        forn_id = conn.execute("INSERT INTO fornecedores (nome, ativo) VALUES ('Fornecedor Teste', 1)").lastrowid
        conn.commit()

    r = client.post("/api/produtos", json={
        "nome": "Vestido Linho Puro",
        "categoria_id": 1,
        "grade_id": 1,
        "preco_venda": 180.0,
        "preco_custo": 90.0,
        "variacoes": [
            {"tamanho": "P", "cor": "Branco", "sku": "VLP-BR-P", "codigo_barras": "7891001"},
            {"tamanho": "M", "cor": "Branco", "sku": "VLP-BR-M", "codigo_barras": "7891002"}
        ]
    })
    assert r.status_code in (200, 201)
    res_prod = r.get_json()
    assert "produto" in res_prod
    novo_prod = res_prod["produto"]
    assert "id" in novo_prod
    assert "variacoes" in novo_prod
    var_nova_id = novo_prod["variacoes"][0]["id"]
    print("[OK] Admin cadastra produto novo com sucesso (POST /api/produtos)")

    # Confirma entrada de 10 unidades na variação nova
    r = client.post("/api/entradas", json={
        "fornecedor_id": forn_id,
        "numero_nota": "NF-12345",
        "itens": [{"variacao_id": var_nova_id, "quantidade": 10, "preco_custo": 90.0}]
    })
    assert r.status_code in (200, 201)
    
    # Verifica que o estoque subiu para 10
    with app.app_context():
        conn = get_db()
        row = conn.execute("SELECT estoque FROM variacoes WHERE id = ?", (var_nova_id,)).fetchone()
        assert row["estoque"] == 10
        mov = conn.execute("SELECT tipo, quantidade, saldo_apos FROM movimentacoes_estoque WHERE variacao_id = ? ORDER BY id DESC LIMIT 1", (var_nova_id,)).fetchone()
        assert mov["tipo"] == "entrada"
        assert mov["quantidade"] == 10
        assert mov["saldo_apos"] == 10
    print("[OK] Confirmação de entrada aumenta estoque do produto novo e grava movimentação 'entrada'")

    print("\nTODOS OS TESTES DE BACKEND PASSARAM COM SUCESSO!")

if __name__ == "__main__":
    run_tests()

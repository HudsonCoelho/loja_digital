def cancelar_venda(conn, venda_id: int, usuario: dict, motivo: str):
    if not motivo or len(motivo.strip()) < 5:
        raise ErroNegocio("Motivo do cancelamento deve ter pelo menos 5 caracteres")
        
    with transaction(conn):
        venda = conn.execute("SELECT * FROM vendas WHERE id = ?", (venda_id,)).fetchone()
        if not venda:
            raise ErroNegocio("Venda não encontrada", 404)
        if venda["status"] == "cancelada":
            raise ErroNegocio("Venda já está cancelada")
            
        # Verifica se já houve alguma devolução
        tem_devolucao = conn.execute("SELECT 1 FROM devolucoes WHERE venda_id = ?", (venda_id,)).fetchone()
        if tem_devolucao:
            raise ErroNegocio("Não é possível cancelar uma venda que já possui itens devolvidos/trocados.")

        # 1. Atualizar status da venda
        conn.execute(
            """UPDATE vendas SET status = 'cancelada', cancelada_em = ?, 
               cancelada_por = ?, motivo_cancelamento = ? WHERE id = ?""",
            (agora(), usuario["id"], motivo.strip(), venda_id)
        )
        
        # 2. Devolver itens para o estoque e registrar movimentação
        itens = conn.execute("SELECT variacao_id, quantidade FROM venda_itens WHERE venda_id = ?", (venda_id,)).fetchall()
        for it in itens:
            if it["variacao_id"]:
                movimentar(conn, it["variacao_id"], it["quantidade"], "cancelamento", 
                          usuario["id"], "venda", venda_id)

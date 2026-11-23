"""Único ponto do sistema que altera o estoque — sempre deixando rastro em movimentacoes_estoque."""
from ..utils import ErroNegocio, agora


def movimentar(conn, variacao_id: int, delta: int, tipo: str, usuario_id: int | None = None,
               ref_tipo: str | None = None, ref_id: int | None = None, obs: str | None = None) -> int:
    """Soma `delta` ao estoque da variação (negativo = saída). Nunca deixa ficar negativo.
    Deve ser chamado dentro de uma transação."""
    if delta == 0:
        row = conn.execute("SELECT estoque FROM variacoes WHERE id = ?", (variacao_id,)).fetchone()
        if not row:
            raise ErroNegocio("Variação não encontrada", 404)
        return row[0]
    cur = conn.execute(
        "UPDATE variacoes SET estoque = estoque + ? WHERE id = ? AND estoque + ? >= 0",
        (delta, variacao_id, delta),
    )
    if cur.rowcount == 0:
        info = conn.execute(
            """SELECT p.nome, v.tamanho, v.cor, v.estoque FROM variacoes v
               JOIN produtos p ON p.id = v.produto_id WHERE v.id = ?""", (variacao_id,)).fetchone()
        if not info:
            raise ErroNegocio("Variação não encontrada", 404)
        raise ErroNegocio(
            f"Estoque insuficiente: {info['nome']} ({info['tamanho']} / {info['cor']}) — disponível: {info['estoque']}",
            409, variacao_id=variacao_id, disponivel=info["estoque"])
    saldo = conn.execute("SELECT estoque FROM variacoes WHERE id = ?", (variacao_id,)).fetchone()[0]
    conn.execute(
        """INSERT INTO movimentacoes_estoque (variacao_id, tipo, quantidade, saldo_apos, ref_tipo, ref_id,
               usuario_id, obs, data) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)""",
        (variacao_id, tipo, delta, saldo, ref_tipo, ref_id, usuario_id, obs, agora()),
    )
    return saldo

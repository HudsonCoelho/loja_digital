from flask import Blueprint, jsonify, request
from ..db import get_db, rows, one, transaction
from ..security import login_required, is_admin
from ..utils import ErroNegocio, limpar

bp = Blueprint("clientes", __name__)

def _mascarar_cpf(cpf: str | None) -> str:
    if not cpf:
        return ""
    digitos = "".join(ch for ch in cpf if ch.isdigit())
    if len(digitos) == 11:
        return f"***.{digitos[3:6]}.{digitos[6:9]}-**"
    elif len(cpf) > 4:
        return cpf[:2] + "*" * (len(cpf) - 4) + cpf[-2:]
    return "***"

def _mascarar_email(email: str | None) -> str:
    if not email or "@" not in email:
        return email or ""
    partes = email.split("@", 1)
    user, dom = partes[0], partes[1]
    if len(user) <= 2:
        masked_user = user[0] + "*"
    else:
        masked_user = user[:2] + "*" * (len(user) - 2)
    return f"{masked_user}@{dom}"

def _mascarar_cliente(c: dict) -> dict:
    c_copia = dict(c)
    if c_copia.get("cpf"):
        c_copia["cpf"] = _mascarar_cpf(c_copia["cpf"])
    if c_copia.get("email"):
        c_copia["email"] = _mascarar_email(c_copia["email"])
    return c_copia

@bp.get("/api/clientes")
@login_required
def listar_clientes():
    """Lista clientes com busca opcional por nome, CPF ou telefone."""
    conn = get_db()
    busca = request.args.get("q", "").strip()
    campos = """
        SELECT id, nome, cpf, telefone, email, nascimento, obs, criado_em,
               (SELECT COUNT(*) FROM vendas WHERE cliente_id = clientes.id AND status = 'concluida') as total_compras,
               (SELECT COALESCE(SUM(total), 0) FROM vendas WHERE cliente_id = clientes.id AND status = 'concluida') as total_gasto,
               (SELECT MAX(data) FROM vendas WHERE cliente_id = clientes.id AND status = 'concluida') as ultima_compra
        FROM clientes
    """
    if busca:
        param = f"%{busca}%"
        digitos = "".join(ch for ch in busca if ch.isdigit())
        param_dig = f"%{digitos}%" if digitos else param
        clientes = rows(conn.execute(campos + """
            WHERE nome LIKE ? OR cpf LIKE ? OR telefone LIKE ?
               OR REPLACE(REPLACE(REPLACE(cpf, '.', ''), '-', ''), ' ', '') LIKE ?
               OR REPLACE(REPLACE(REPLACE(REPLACE(REPLACE(telefone, '(', ''), ')', ''), '-', ''), ' ', ''), '.', '') LIKE ?
            ORDER BY nome
            LIMIT 50
        """, (param, param, param, param_dig, param_dig)))
    else:
        clientes = rows(conn.execute(campos + " ORDER BY nome LIMIT 200"))
    if not is_admin():
        clientes = [_mascarar_cliente(c) for c in clientes]
    return jsonify(clientes)

@bp.post("/api/clientes")
@login_required
def criar_cliente():
    """Cadastra um novo cliente."""
    conn = get_db()
    dados = request.json or {}
    nome = limpar(dados.get("nome"), 100)
    if not nome:
        raise ErroNegocio("Nome do cliente é obrigatório")
    
    cpf = limpar(dados.get("cpf"), 20) or None
    telefone = limpar(dados.get("telefone"), 20)
    email = limpar(dados.get("email"), 80)
    nascimento = limpar(dados.get("nascimento"), 10)
    obs = limpar(dados.get("obs"), 250)
    
    with transaction(conn):
        if cpf:
            existente = one(conn.execute("SELECT id FROM clientes WHERE cpf = ?", (cpf,)))
            if existente:
                raise ErroNegocio("Já existe um cliente cadastrado com este CPF", 409)
                
        cid = conn.execute("""
            INSERT INTO clientes (nome, cpf, telefone, email, nascimento, obs)
            VALUES (?, ?, ?, ?, ?, ?)
        """, (nome, cpf, telefone, email, nascimento, obs)).lastrowid
        
    cliente = one(conn.execute("SELECT * FROM clientes WHERE id = ?", (cid,)))
    return jsonify(cliente), 201

@bp.put("/api/clientes/<int:cid>")
@login_required
def editar_cliente(cid):
    """Atualiza o cadastro de um cliente."""
    conn = get_db()
    if not one(conn.execute("SELECT id FROM clientes WHERE id = ?", (cid,))):
        raise ErroNegocio("Cliente não encontrado", 404)
    dados = request.json or {}
    nome = limpar(dados.get("nome"), 100)
    if not nome:
        raise ErroNegocio("Nome do cliente é obrigatório")
    cpf = limpar(dados.get("cpf"), 20) or None
    email = limpar(dados.get("email"), 80)
    with transaction(conn):
        antigo = one(conn.execute("SELECT cpf, email FROM clientes WHERE id = ?", (cid,)))
        if cpf and "*" in cpf and antigo:
            cpf = antigo["cpf"]
        if email and "*" in email and antigo:
            email = antigo["email"]

        if cpf and one(conn.execute("SELECT id FROM clientes WHERE cpf = ? AND id <> ?", (cpf, cid))):
            raise ErroNegocio("Já existe outro cliente com este CPF", 409)
        conn.execute("""
            UPDATE clientes SET nome = ?, cpf = ?, telefone = ?, email = ?, nascimento = ?, obs = ?
            WHERE id = ?
        """, (nome, cpf, limpar(dados.get("telefone"), 20), email,
              limpar(dados.get("nascimento"), 10), limpar(dados.get("obs"), 250), cid))
    cliente = one(conn.execute("SELECT * FROM clientes WHERE id = ?", (cid,)))
    if not is_admin():
        cliente = _mascarar_cliente(cliente)
    return jsonify(cliente)

@bp.get("/api/clientes/<int:cid>")
@login_required
def detalhe_cliente(cid):
    """Retorna detalhes do cliente, suas últimas compras e vales-troca ativos."""
    conn = get_db()
    cliente = one(conn.execute("SELECT * FROM clientes WHERE id = ?", (cid,)))
    if not cliente:
        raise ErroNegocio("Cliente não encontrado", 404)
        
    vendas = rows(conn.execute("""
        SELECT id, codigo, data, total, status
        FROM vendas
        WHERE cliente_id = ?
        ORDER BY data DESC LIMIT 20
    """, (cid,)))
    
    vales = rows(conn.execute("""
        SELECT id, codigo, valor_original, saldo, status, criado_em, validade
        FROM vales_troca
        WHERE cliente_id = ?
        ORDER BY id DESC
    """, (cid,)))
    
    cliente["vendas"] = vendas
    cliente["vales"] = vales
    if not is_admin():
        cliente = _mascarar_cliente(cliente)
    return jsonify(cliente)

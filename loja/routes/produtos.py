import json
import uuid
from pathlib import Path

from flask import Blueprint, current_app, jsonify, request
from werkzeug.utils import secure_filename

from ..db import get_db, one, rows, transaction
from ..security import admin_required, is_admin, login_required, usuario_atual
from ..services.estoque import movimentar
from ..utils import (ErroNegocio, agora, gerar_ean13_interno, gerar_sku, limpar, money, parse_int,
                     to_float, validar_codigo_barras)

bp = Blueprint("produtos", __name__)

PLACEHOLDER = "/static/erp/img/placeholder.svg"


# ---------------- Imagens ----------------
def resolver_imagem(imagem: str | None) -> str:
    """Converte o caminho salvo no banco em URL. Uploads ficam em /media (pasta de dados)."""
    if not imagem:
        return PLACEHOLDER
    caminho = imagem.replace("\\", "/")
    while caminho.startswith(("../", "./", "/")):
        caminho = caminho.split("/", 1)[1] if caminho.startswith(("../", "./")) else caminho[1:]
    if caminho.startswith("static/"):
        caminho = caminho[len("static/"):]
    if caminho.startswith("images/"):
        return "/media/" + caminho[len("images/"):]
    return "/static/" + caminho


def _validar_assinatura_imagem(stream) -> bool:
    try:
        pos = stream.tell() if hasattr(stream, "tell") else 0
        header = stream.read(16)
        if hasattr(stream, "seek"):
            stream.seek(pos)
        if not header or len(header) < 4:
            return False
        if header.startswith(b"\x89PNG\r\n\x1a\n"):
            return True
        if header.startswith(b"\xff\xd8\xff"):
            return True
        if header.startswith(b"GIF87a") or header.startswith(b"GIF89a"):
            return True
        if header.startswith(b"RIFF") and len(header) >= 12 and header[8:12] == b"WEBP":
            return True
        return False
    except Exception:
        return False


def _salvar_upload(arquivo) -> str | None:
    if not arquivo or not arquivo.filename:
        return None
    nome = secure_filename(arquivo.filename)
    ext = nome.rsplit(".", 1)[-1].lower() if "." in nome else ""
    if ext not in current_app.config["ALLOWED_EXTENSIONS"]:
        raise ErroNegocio("Formato de imagem não permitido (use PNG, JPG, WEBP ou GIF)")
    if not _validar_assinatura_imagem(arquivo.stream):
        raise ErroNegocio("Conteúdo do arquivo não corresponde a uma imagem válida (PNG, JPG, WEBP ou GIF)")
    pasta = Path(current_app.config["UPLOAD_DIR"])
    pasta.mkdir(parents=True, exist_ok=True)
    final = f"{uuid.uuid4().hex}_{nome}"
    if hasattr(arquivo.stream, "seek"):
        arquivo.stream.seek(0)
    arquivo.save(pasta / final)
    return f"images/{final}"


def _apagar_upload(imagem: str | None):
    if not imagem:
        return
    url = resolver_imagem(imagem)
    if not url.startswith("/media/"):
        return
    pasta = Path(current_app.config["UPLOAD_DIR"]).resolve()
    alvo = (pasta / url[len("/media/"):]).resolve()
    if alvo.parent == pasta and alvo.exists():
        try:
            alvo.unlink()
        except OSError:
            current_app.logger.warning("Não foi possível apagar a imagem %s", alvo)


# ---------------- Serialização ----------------
def _serializar(db, produtos: list[dict], incluir_inativas: bool = False) -> list[dict]:
    if not produtos:
        return []
    admin = is_admin()
    ids = [p["id"] for p in produtos]
    marcadores = ",".join("?" * len(ids))
    filtro = "" if incluir_inativas else "AND ativo = 1"
    variacoes = rows(db.execute(
        f"SELECT * FROM variacoes WHERE produto_id IN ({marcadores}) {filtro} ORDER BY id", ids))
    por_produto: dict[int, list[dict]] = {}
    for v in variacoes:
        por_produto.setdefault(v["produto_id"], []).append(v)

    saida = []
    for p in produtos:
        tamanhos_grade = json.loads(p["grade_tamanhos"]) if p.get("grade_tamanhos") else []
        ordem = {t: i for i, t in enumerate(tamanhos_grade)}
        vs = sorted(por_produto.get(p["id"], []), key=lambda v: (ordem.get(v["tamanho"], 999), v["cor"].lower()))
        cores: list[str] = []
        for v in vs:
            if v["cor"] not in cores:
                cores.append(v["cor"])
        tamanhos = [t for t in tamanhos_grade if any(v["tamanho"] == t for v in vs)] + sorted(
            {v["tamanho"] for v in vs if v["tamanho"] not in ordem})
        item = {
            "id": p["id"],
            "nome": p["nome"],
            "categoria_id": p["categoria_id"],
            "categoria": p.get("categoria_nome") or "Geral",
            "grade_id": p["grade_id"],
            "grade": p.get("grade_nome"),
            "grade_tamanhos": tamanhos_grade,
            "descricao": p.get("descricao") or "",
            "img": resolver_imagem(p.get("imagem")),
            "preco": p["preco_venda"],
            "min": p["qtd_minima"],
            "ativo": bool(p["ativo"]),
            "cores": cores,
            "tamanhos": tamanhos,
            "estoque_total": sum(v["estoque"] for v in vs if v["ativo"]),
            "variacoes": [{
                "id": v["id"], "tamanho": v["tamanho"], "cor": v["cor"], "sku": v["sku"],
                "codigo_barras": v["codigo_barras"], "estoque": v["estoque"], "ativo": bool(v["ativo"]),
            } for v in vs],
        }
        if admin:
            item["custo"] = p["preco_custo"]
            item["margem"] = round((p["preco_venda"] - p["preco_custo"]) / p["preco_venda"] * 100, 1) \
                if p["preco_venda"] else None
        saida.append(item)
    return saida


_SELECT_PRODUTO = """
    SELECT p.*, c.nome AS categoria_nome, g.nome AS grade_nome, g.tamanhos AS grade_tamanhos
    FROM produtos p
    LEFT JOIN categorias c ON c.id = p.categoria_id
    LEFT JOIN grades g ON g.id = p.grade_id
"""


def _produto(db, pid: int, incluir_inativas: bool = True) -> dict:
    p = one(db.execute(_SELECT_PRODUTO + " WHERE p.id = ?", (pid,)))
    if not p:
        raise ErroNegocio("Produto não encontrado", 404)
    return _serializar(db, [p], incluir_inativas)[0]


# ---------------- Validação ----------------
def _ler_payload() -> dict:
    bruto = request.form.get("dados")
    if bruto is None:
        return request.get_json(silent=True) or {}
    try:
        return json.loads(bruto)
    except json.JSONDecodeError:
        raise ErroNegocio("Dados do produto inválidos")


def _validar_campos(db, d: dict) -> dict:
    nome = limpar(d.get("nome"), 120)
    if not nome:
        raise ErroNegocio("Informe o nome do produto")
    cat = one(db.execute("SELECT id, nome FROM categorias WHERE id = ?", (d.get("categoria_id"),)))
    if not cat:
        raise ErroNegocio("Selecione uma categoria válida")
    grade = one(db.execute("SELECT id, tamanhos FROM grades WHERE id = ?", (d.get("grade_id"),)))
    if not grade:
        raise ErroNegocio("Selecione uma grade de tamanhos válida")
    preco = money(d.get("preco_venda"))
    if preco <= 0:
        raise ErroNegocio("Preço de venda deve ser maior que zero")
    custo = money(d.get("preco_custo") or 0)
    if custo < 0:
        raise ErroNegocio("Preço de custo inválido")
    return {
        "nome": nome,
        "categoria_id": cat["id"],
        "categoria_nome": cat["nome"],
        "grade_id": grade["id"],
        "grade_tamanhos": json.loads(grade["tamanhos"]),
        "descricao": limpar(d.get("descricao"), 500),
        "preco_venda": to_float(preco),
        "preco_custo": to_float(custo),
        "qtd_minima": parse_int(d.get("qtd_minima", 5), "Quantidade mínima", 0),
    }


def _codigo_livre(db, codigo: str, variacao_id: int | None):
    dono = one(db.execute(
        """SELECT v.id, p.nome, v.tamanho, v.cor FROM variacoes v JOIN produtos p ON p.id = v.produto_id
           WHERE v.codigo_barras = ? AND v.id IS NOT ?""", (codigo, variacao_id)))
    if dono:
        raise ErroNegocio(
            f"O código {codigo} já pertence a {dono['nome']} ({dono['tamanho']} / {dono['cor']})", 409)


def _salvar_variacoes(db, pid: int, campos: dict, variacoes: list, criando: bool, motivo: str, uid: int):
    if not isinstance(variacoes, list) or not variacoes:
        raise ErroNegocio("Adicione pelo menos uma cor à grade do produto")
    existentes = {(v["tamanho"], v["cor"].lower()): v
                  for v in rows(db.execute("SELECT * FROM variacoes WHERE produto_id = ?", (pid,)))}
    vistos = set()
    for item in variacoes:
        tam = limpar(item.get("tamanho"), 10)
        cor = limpar(item.get("cor"), 40)
        if not tam or not cor:
            raise ErroNegocio("Tamanho e cor são obrigatórios em cada variação")
        if tam not in campos["grade_tamanhos"]:
            raise ErroNegocio(f"Tamanho {tam} não pertence à grade escolhida")
        chave = (tam, cor.lower())
        if chave in vistos:
            raise ErroNegocio(f"Variação repetida: {tam} / {cor}")
        vistos.add(chave)
        estoque = parse_int(item.get("estoque", 0), f"Estoque {tam}/{cor}", 0)
        raw_codigo = (item.get("codigo_barras") or "").strip()
        ex = existentes.get(chave)
        if ex:
            if raw_codigo and raw_codigo != ex["codigo_barras"]:
                codigo = validar_codigo_barras(raw_codigo)
                _codigo_livre(db, codigo, ex["id"])
                db.execute("UPDATE variacoes SET codigo_barras = ? WHERE id = ?", (codigo, ex["id"]))
            if not ex["ativo"]:
                db.execute("UPDATE variacoes SET ativo = 1 WHERE id = ?", (ex["id"],))
            delta = estoque - ex["estoque"]
            if delta:
                if not motivo:
                    raise ErroNegocio("Informe o motivo do ajuste de estoque")
                movimentar(db, ex["id"], delta, "ajuste", uid, "produto", pid, motivo)
        else:
            codigo = validar_codigo_barras(raw_codigo) if raw_codigo else ""
            vid = db.execute(
                "INSERT INTO variacoes (produto_id, tamanho, cor, sku, estoque) VALUES (?, ?, ?, ?, 0)",
                (pid, tam, cor, None)).lastrowid
            sku = gerar_sku(pid, campos["categoria_nome"], cor, tam)
            if db.execute("SELECT 1 FROM variacoes WHERE sku = ?", (sku,)).fetchone():
                sku = f"{sku}-{vid}"
            if codigo:
                _codigo_livre(db, codigo, vid)
            db.execute("UPDATE variacoes SET sku = ?, codigo_barras = ? WHERE id = ?",
                       (sku, codigo or gerar_ean13_interno(vid), vid))
            if estoque:
                movimentar(db, vid, estoque, "ajuste", uid, "produto", pid,
                           "Estoque inicial" if criando else (motivo or "Nova variação"))
    for chave, ex in existentes.items():
        if chave not in vistos and ex["ativo"]:
            db.execute("UPDATE variacoes SET ativo = 0 WHERE id = ?", (ex["id"],))


# ---------------- Rotas: produtos ----------------
@bp.get("/api/produtos")
@login_required
def listar():
    db = get_db()
    incluir_inativos = request.args.get("inativos") == "1" and is_admin()
    where = "" if incluir_inativos else "WHERE p.ativo = 1"
    produtos = rows(db.execute(_SELECT_PRODUTO + f" {where} ORDER BY p.nome COLLATE NOCASE"))
    return jsonify(_serializar(db, produtos))


@bp.get("/api/produtos/<int:pid>")
@login_required
def detalhe(pid: int):
    return jsonify(_produto(get_db(), pid, incluir_inativas=False))


@bp.post("/api/produtos")
@admin_required
def criar():
    db = get_db()
    d = _ler_payload()
    campos = _validar_campos(db, d)
    imagem = _salvar_upload(request.files.get("imagem"))
    try:
        with transaction(db):
            pid = db.execute(
                """INSERT INTO produtos (nome, categoria_id, grade_id, descricao, imagem, preco_venda, preco_custo,
                       qtd_minima, atualizado_em) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)""",
                (campos["nome"], campos["categoria_id"], campos["grade_id"], campos["descricao"], imagem,
                 campos["preco_venda"], campos["preco_custo"], campos["qtd_minima"], agora())).lastrowid
            _salvar_variacoes(db, pid, campos, d.get("variacoes"), True, "", usuario_atual()["id"])
    except Exception:
        _apagar_upload(imagem)
        raise
    return jsonify({"success": True, "produto": _produto(db, pid, incluir_inativas=False)})


@bp.put("/api/produtos/<int:pid>")
@admin_required
def editar(pid: int):
    db = get_db()
    d = _ler_payload()
    atual = one(db.execute("SELECT * FROM produtos WHERE id = ?", (pid,)))
    if not atual:
        raise ErroNegocio("Produto não encontrado", 404)
    campos = _validar_campos(db, d)
    nova_imagem = _salvar_upload(request.files.get("imagem"))
    remover = d.get("remover_imagem") is True
    imagem = nova_imagem or (None if remover else atual["imagem"])
    try:
        with transaction(db):
            db.execute(
                """UPDATE produtos SET nome = ?, categoria_id = ?, grade_id = ?, descricao = ?, imagem = ?,
                       preco_venda = ?, preco_custo = ?, qtd_minima = ?, ativo = 1, atualizado_em = ? WHERE id = ?""",
                (campos["nome"], campos["categoria_id"], campos["grade_id"], campos["descricao"], imagem,
                 campos["preco_venda"], campos["preco_custo"], campos["qtd_minima"], agora(), pid))
            _salvar_variacoes(db, pid, campos, d.get("variacoes"), False,
                              limpar(d.get("motivo_ajuste"), 200), usuario_atual()["id"])
    except Exception:
        _apagar_upload(nova_imagem)
        raise
    if imagem != atual["imagem"]:
        _apagar_upload(atual["imagem"])
    return jsonify({"success": True, "produto": _produto(db, pid, incluir_inativas=False)})


@bp.delete("/api/produtos/<int:pid>")
@admin_required
def excluir(pid: int):
    db = get_db()
    atual = one(db.execute("SELECT * FROM produtos WHERE id = ?", (pid,)))
    if not atual:
        raise ErroNegocio("Produto não encontrado", 404)
    with transaction(db):
        tem_historico = db.execute(
            """SELECT 1 FROM venda_itens WHERE produto_id = ?
               UNION SELECT 1 FROM venda_itens vi JOIN variacoes v ON v.id = vi.variacao_id WHERE v.produto_id = ?
               UNION SELECT 1 FROM entrada_itens ei JOIN variacoes v ON v.id = ei.variacao_id WHERE v.produto_id = ?
               LIMIT 1""", (pid, pid, pid)).fetchone()
        if tem_historico:
            db.execute("UPDATE produtos SET ativo = 0, atualizado_em = ? WHERE id = ?", (agora(), pid))
            modo = "desativado"
        else:
            db.execute("DELETE FROM produtos WHERE id = ?", (pid,))
            modo = "excluido"
    if modo == "excluido":
        _apagar_upload(atual["imagem"])
    return jsonify({"success": True, "modo": modo})


@bp.get("/api/produtos/<int:pid>/movimentacoes")
@admin_required
def movimentacoes(pid: int):
    return jsonify(rows(get_db().execute(
        """SELECT m.id, m.data, m.tipo, m.quantidade, m.saldo_apos, m.obs, m.ref_tipo, m.ref_id,
                  v.tamanho, v.cor, u.nome AS usuario
           FROM movimentacoes_estoque m
           JOIN variacoes v ON v.id = m.variacao_id
           LEFT JOIN usuarios u ON u.id = m.usuario_id
           WHERE v.produto_id = ? ORDER BY m.id DESC LIMIT 300""", (pid,))))


# ---------------- Rotas: categorias ----------------
@bp.get("/api/categorias")
@login_required
def listar_categorias():
    return jsonify(rows(get_db().execute(
        "SELECT id, nome FROM categorias WHERE ativo = 1 ORDER BY nome COLLATE NOCASE")))


@bp.post("/api/categorias")
@admin_required
def criar_categoria():
    nome = limpar((request.get_json(silent=True) or {}).get("nome"), 60)
    if not nome:
        raise ErroNegocio("Informe o nome da categoria")
    db = get_db()
    with transaction(db):
        existe = one(db.execute("SELECT id, ativo FROM categorias WHERE nome = ?", (nome,)))
        if existe:
            db.execute("UPDATE categorias SET ativo = 1 WHERE id = ?", (existe["id"],))
            cid = existe["id"]
        else:
            cid = db.execute("INSERT INTO categorias (nome) VALUES (?)", (nome,)).lastrowid
    return jsonify({"success": True, "categoria": {"id": cid, "nome": nome}})


# ---------------- Rotas: grades ----------------
def _grade_json(g: dict) -> dict:
    return {"id": g["id"], "nome": g["nome"], "tamanhos": json.loads(g["tamanhos"]), "padrao": bool(g["padrao"])}


@bp.get("/api/grades")
@login_required
def listar_grades():
    return jsonify([_grade_json(g) for g in rows(get_db().execute("SELECT * FROM grades ORDER BY padrao DESC, id"))])


@bp.post("/api/grades")
@admin_required
def criar_grade():
    d = request.get_json(silent=True) or {}
    nome = limpar(d.get("nome"), 40)
    tamanhos = d.get("tamanhos") or []
    if isinstance(tamanhos, str):
        tamanhos = tamanhos.split(",")
    tamanhos = [limpar(t, 10).upper() for t in tamanhos if limpar(t, 10)]
    if not nome:
        raise ErroNegocio("Informe o nome da grade")
    if not tamanhos or len(tamanhos) > 30:
        raise ErroNegocio("Informe de 1 a 30 tamanhos")
    if len(set(tamanhos)) != len(tamanhos):
        raise ErroNegocio("Há tamanhos repetidos na grade")
    db = get_db()
    with transaction(db):
        if db.execute("SELECT 1 FROM grades WHERE nome = ?", (nome,)).fetchone():
            raise ErroNegocio("Já existe uma grade com esse nome", 409)
        gid = db.execute("INSERT INTO grades (nome, tamanhos) VALUES (?, ?)",
                         (nome, json.dumps(tamanhos, ensure_ascii=False))).lastrowid
    return jsonify({"success": True, "grade": _grade_json(one(db.execute("SELECT * FROM grades WHERE id = ?", (gid,))))})


@bp.delete("/api/grades/<int:gid>")
@admin_required
def excluir_grade(gid: int):
    db = get_db()
    with transaction(db):
        g = one(db.execute("SELECT * FROM grades WHERE id = ?", (gid,)))
        if not g:
            raise ErroNegocio("Grade não encontrada", 404)
        if g["padrao"]:
            raise ErroNegocio("As grades padrão não podem ser excluídas")
        if db.execute("SELECT 1 FROM produtos WHERE grade_id = ?", (gid,)).fetchone():
            raise ErroNegocio("Essa grade está em uso por produtos")
        db.execute("DELETE FROM grades WHERE id = ?", (gid,))
    return jsonify({"success": True})

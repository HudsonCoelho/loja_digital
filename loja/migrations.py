"""Migrações versionadas via PRAGMA user_version.

v1: schema completo do ERP + conversão do banco legado (produtos com tamanho_p/m/g e
    vendas com 1 linha por item). Antes de converter, um backup é gravado em backups/.
"""
import json
import sqlite3
from datetime import datetime
from pathlib import Path

from .utils import gerar_ean13_interno, gerar_sku, limpar

GRADES_PADRAO = [
    ("Letras", ["PP", "P", "M", "G", "GG", "XG", "XGG"]),
    ("Numérica", ["34", "36", "38", "40", "42", "44", "46", "48"]),
    ("Calçados", [str(n) for n in range(33, 45)]),
    ("Único", ["U"]),
]
CATEGORIAS_PADRAO = ["Camisas", "Camisetas", "Calças", "Bermudas", "Vestidos", "Saias", "Calçados", "Acessórios"]

SCHEMA_V1 = """
CREATE TABLE IF NOT EXISTS configuracoes (
    chave TEXT PRIMARY KEY,
    valor TEXT
);
CREATE TABLE usuarios (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    nome TEXT NOT NULL,
    login TEXT NOT NULL UNIQUE COLLATE NOCASE,
    senha_hash TEXT NOT NULL,
    perfil TEXT NOT NULL CHECK (perfil IN ('admin', 'vendedor')),
    comissao_pct REAL NOT NULL DEFAULT 0,
    desconto_max_pct REAL DEFAULT NULL,
    ativo INTEGER NOT NULL DEFAULT 1,
    criado_em TEXT NOT NULL DEFAULT (datetime('now', 'localtime'))
);
CREATE TABLE categorias (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    nome TEXT NOT NULL UNIQUE COLLATE NOCASE,
    ativo INTEGER NOT NULL DEFAULT 1
);
CREATE TABLE grades (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    nome TEXT NOT NULL UNIQUE COLLATE NOCASE,
    tamanhos TEXT NOT NULL,
    padrao INTEGER NOT NULL DEFAULT 0
);
CREATE TABLE produtos (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    nome TEXT NOT NULL,
    categoria_id INTEGER REFERENCES categorias(id),
    grade_id INTEGER REFERENCES grades(id),
    descricao TEXT,
    imagem TEXT,
    preco_venda REAL NOT NULL CHECK (preco_venda >= 0),
    preco_custo REAL NOT NULL DEFAULT 0 CHECK (preco_custo >= 0),
    qtd_minima INTEGER NOT NULL DEFAULT 5,
    ativo INTEGER NOT NULL DEFAULT 1,
    criado_em TEXT NOT NULL DEFAULT (datetime('now', 'localtime')),
    atualizado_em TEXT
);
CREATE TABLE variacoes (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    produto_id INTEGER NOT NULL REFERENCES produtos(id) ON DELETE CASCADE,
    tamanho TEXT NOT NULL,
    cor TEXT NOT NULL,
    sku TEXT UNIQUE,
    codigo_barras TEXT UNIQUE,
    estoque INTEGER NOT NULL DEFAULT 0 CHECK (estoque >= 0),
    ativo INTEGER NOT NULL DEFAULT 1,
    UNIQUE (produto_id, tamanho, cor)
);
CREATE INDEX ix_variacoes_produto ON variacoes(produto_id);
CREATE TABLE movimentacoes_estoque (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    variacao_id INTEGER NOT NULL REFERENCES variacoes(id) ON DELETE CASCADE,
    tipo TEXT NOT NULL,
    quantidade INTEGER NOT NULL,
    saldo_apos INTEGER NOT NULL,
    ref_tipo TEXT,
    ref_id INTEGER,
    usuario_id INTEGER REFERENCES usuarios(id),
    obs TEXT,
    data TEXT NOT NULL DEFAULT (datetime('now', 'localtime'))
);
CREATE INDEX ix_mov_variacao ON movimentacoes_estoque(variacao_id, data);
CREATE TABLE clientes (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    nome TEXT NOT NULL,
    cpf TEXT UNIQUE,
    telefone TEXT,
    email TEXT,
    nascimento TEXT,
    obs TEXT,
    criado_em TEXT NOT NULL DEFAULT (datetime('now', 'localtime'))
);
CREATE TABLE caixas (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    aberto_por INTEGER REFERENCES usuarios(id),
    aberto_em TEXT NOT NULL,
    valor_abertura REAL NOT NULL DEFAULT 0,
    fechado_por INTEGER REFERENCES usuarios(id),
    fechado_em TEXT,
    contagem TEXT,
    esperado TEXT,
    diferenca REAL,
    status TEXT NOT NULL DEFAULT 'aberto' CHECK (status IN ('aberto', 'fechado')),
    obs TEXT
);
CREATE UNIQUE INDEX ux_caixa_unico_aberto ON caixas(status) WHERE status = 'aberto';
CREATE TABLE caixa_movimentos (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    caixa_id INTEGER NOT NULL REFERENCES caixas(id),
    tipo TEXT NOT NULL CHECK (tipo IN ('sangria', 'suprimento')),
    valor REAL NOT NULL CHECK (valor > 0),
    motivo TEXT,
    usuario_id INTEGER REFERENCES usuarios(id),
    data TEXT NOT NULL DEFAULT (datetime('now', 'localtime'))
);
CREATE TABLE vales_troca (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    codigo TEXT NOT NULL UNIQUE,
    cliente_id INTEGER REFERENCES clientes(id),
    valor_original REAL NOT NULL,
    saldo REAL NOT NULL CHECK (saldo >= 0),
    status TEXT NOT NULL DEFAULT 'ativo' CHECK (status IN ('ativo', 'usado', 'cancelado')),
    validade TEXT,
    criado_em TEXT NOT NULL DEFAULT (datetime('now', 'localtime'))
);
CREATE TABLE vendas (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    codigo TEXT NOT NULL UNIQUE,
    data TEXT NOT NULL,
    cliente_id INTEGER REFERENCES clientes(id),
    vendedor_id INTEGER REFERENCES usuarios(id),
    caixa_id INTEGER REFERENCES caixas(id),
    subtotal REAL NOT NULL,
    desconto REAL NOT NULL DEFAULT 0,
    total REAL NOT NULL,
    custo_total REAL,
    troco REAL NOT NULL DEFAULT 0,
    status TEXT NOT NULL DEFAULT 'concluida' CHECK (status IN ('concluida', 'cancelada')),
    cancelada_em TEXT,
    cancelada_por INTEGER REFERENCES usuarios(id),
    motivo_cancelamento TEXT,
    legado INTEGER NOT NULL DEFAULT 0
);
CREATE INDEX ix_vendas_data ON vendas(data);
CREATE TABLE venda_itens (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    venda_id INTEGER NOT NULL REFERENCES vendas(id) ON DELETE CASCADE,
    variacao_id INTEGER REFERENCES variacoes(id) ON DELETE SET NULL,
    produto_id INTEGER REFERENCES produtos(id) ON DELETE SET NULL,
    nome TEXT NOT NULL,
    tamanho TEXT,
    cor TEXT,
    quantidade INTEGER NOT NULL CHECK (quantidade > 0),
    preco_unit REAL NOT NULL,
    custo_unit REAL,
    desconto REAL NOT NULL DEFAULT 0,
    total REAL NOT NULL,
    qtd_devolvida INTEGER NOT NULL DEFAULT 0
);
CREATE INDEX ix_venda_itens_venda ON venda_itens(venda_id);
CREATE INDEX ix_venda_itens_variacao ON venda_itens(variacao_id);
CREATE TABLE venda_pagamentos (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    venda_id INTEGER NOT NULL REFERENCES vendas(id) ON DELETE CASCADE,
    forma TEXT NOT NULL,
    valor REAL NOT NULL,
    parcelas INTEGER NOT NULL DEFAULT 1,
    vale_id INTEGER REFERENCES vales_troca(id)
);
CREATE INDEX ix_venda_pag_venda ON venda_pagamentos(venda_id);
CREATE TABLE devolucoes (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    venda_id INTEGER NOT NULL REFERENCES vendas(id),
    data TEXT NOT NULL,
    usuario_id INTEGER REFERENCES usuarios(id),
    caixa_id INTEGER REFERENCES caixas(id),
    tipo TEXT NOT NULL CHECK (tipo IN ('vale', 'dinheiro')),
    valor REAL NOT NULL,
    vale_id INTEGER REFERENCES vales_troca(id),
    obs TEXT
);
CREATE TABLE devolucao_itens (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    devolucao_id INTEGER NOT NULL REFERENCES devolucoes(id) ON DELETE CASCADE,
    venda_item_id INTEGER NOT NULL REFERENCES venda_itens(id),
    quantidade INTEGER NOT NULL CHECK (quantidade > 0),
    valor REAL NOT NULL
);
CREATE TABLE fornecedores (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    nome TEXT NOT NULL,
    cnpj TEXT,
    telefone TEXT,
    email TEXT,
    contato TEXT,
    obs TEXT,
    ativo INTEGER NOT NULL DEFAULT 1
);
CREATE TABLE entradas (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    fornecedor_id INTEGER REFERENCES fornecedores(id),
    numero_nota TEXT,
    data TEXT NOT NULL,
    total REAL NOT NULL DEFAULT 0,
    usuario_id INTEGER REFERENCES usuarios(id),
    obs TEXT
);
CREATE TABLE entrada_itens (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    entrada_id INTEGER NOT NULL REFERENCES entradas(id) ON DELETE CASCADE,
    variacao_id INTEGER NOT NULL REFERENCES variacoes(id),
    quantidade INTEGER NOT NULL CHECK (quantidade > 0),
    custo_unit REAL NOT NULL DEFAULT 0
)
"""


def _statements(script: str):
    return [s.strip() for s in script.split(";") if s.strip()]


def _tables(conn) -> set[str]:
    return {r[0] for r in conn.execute("SELECT name FROM sqlite_master WHERE type='table'")}


def _columns(conn, table: str) -> set[str]:
    return {r[1] for r in conn.execute(f"PRAGMA table_info({table})")}


def backup_database(db_path: str, backup_dir: str, sufixo: str = "") -> str | None:
    if not Path(db_path).exists():
        return None
    Path(backup_dir).mkdir(parents=True, exist_ok=True)
    destino = Path(backup_dir) / f"estoque_{datetime.now():%Y%m%d_%H%M%S}{sufixo}.db"
    src = sqlite3.connect(db_path)
    dst = sqlite3.connect(destino)
    try:
        src.backup(dst)
    finally:
        dst.close()
        src.close()
    return str(destino)


def _normalizar_imagem(imagem: str | None) -> str | None:
    if not imagem:
        return None
    caminho = imagem.replace("\\", "/")
    while caminho.startswith(("../", "./", "/")):
        caminho = caminho.split("/", 1)[1] if caminho.startswith(("../", "./")) else caminho[1:]
    if caminho.startswith("static/"):
        caminho = caminho[len("static/"):]
    return caminho


def _migrar_legado(conn, tem_produtos: bool, tem_vendas: bool):
    grade_letras = conn.execute("SELECT id FROM grades WHERE nome = 'Letras'").fetchone()[0]

    def categoria_id(nome: str) -> int:
        nome = limpar(nome, 60) or "Geral"
        row = conn.execute("SELECT id FROM categorias WHERE nome = ?", (nome,)).fetchone()
        if row:
            return row[0]
        return conn.execute("INSERT INTO categorias (nome) VALUES (?)", (nome,)).lastrowid

    mapa_var: dict[tuple[int, str], int] = {}
    if tem_produtos:
        cols = _columns(conn, "legado_produtos")
        for p in conn.execute("SELECT * FROM legado_produtos").fetchall():
            p = dict(p)
            cat_nome = limpar(p.get("categoria") or "Geral", 60) or "Geral"
            cat_id = categoria_id(cat_nome)
            cor = limpar(p.get("cor") or "", 40)
            if not cor or cor.upper() == "N/A":
                cor = "Única"
            conn.execute(
                """INSERT INTO produtos (id, nome, categoria_id, grade_id, imagem, preco_venda,
                       preco_custo, qtd_minima, ativo)
                   VALUES (?, ?, ?, ?, ?, ?, 0, ?, 1)""",
                (p["id"], limpar(p.get("nome") or f"Produto {p['id']}", 120), cat_id, grade_letras,
                 _normalizar_imagem(p.get("imagem")), max(float(p.get("preco") or 0), 0),
                 int(p.get("qtd_minima") or 5) if "qtd_minima" in cols else 5),
            )
            tp = int(p.get("tamanho_p") or 0) if "tamanho_p" in cols else 0
            tm = int(p.get("tamanho_m") or 0) if "tamanho_m" in cols else 0
            tg = int(p.get("tamanho_g") or 0) if "tamanho_g" in cols else 0
            if tp + tm + tg == 0 and int(p.get("quantidade") or 0) > 0:
                tm = int(p["quantidade"])
            for tam, qtd in (("P", tp), ("M", tm), ("G", tg)):
                qtd = max(qtd, 0)
                vid = conn.execute(
                    "INSERT INTO variacoes (produto_id, tamanho, cor, sku, estoque) VALUES (?, ?, ?, ?, ?)",
                    (p["id"], tam, cor, gerar_sku(p["id"], cat_nome, cor, tam), qtd),
                ).lastrowid
                conn.execute("UPDATE variacoes SET codigo_barras = ? WHERE id = ?", (gerar_ean13_interno(vid), vid))
                if qtd:
                    conn.execute(
                        """INSERT INTO movimentacoes_estoque (variacao_id, tipo, quantidade, saldo_apos, obs)
                           VALUES (?, 'ajuste', ?, ?, 'Saldo migrado do sistema anterior')""",
                        (vid, qtd, qtd),
                    )
                mapa_var[(p["id"], tam)] = vid

    if tem_vendas:
        cols = _columns(conn, "legado_vendas")
        linhas = [dict(r) for r in conn.execute("SELECT * FROM legado_vendas ORDER BY id").fetchall()]
        grupos: dict[str, list[dict]] = {}
        for v in linhas:
            chave = (v.get("id_venda_agrupada") if "id_venda_agrupada" in cols else None) or f"L{v['id']:07d}"
            grupos.setdefault(chave, []).append(v)
        for codigo, itens in grupos.items():
            total = round(sum(float(i.get("total") or 0) for i in itens), 2)
            data = itens[0].get("data") or "2000-01-01 00:00:00"
            forma = (itens[0].get("forma_pagamento") if "forma_pagamento" in cols else None) or "Pix"
            if forma == "Cartão":
                forma = "Crédito"
            venda_id = conn.execute(
                """INSERT INTO vendas (codigo, data, subtotal, desconto, total, custo_total, status, legado)
                   VALUES (?, ?, ?, 0, ?, NULL, 'concluida', 1)""",
                (codigo, data, total, total),
            ).lastrowid
            for i in itens:
                qtd = max(int(i.get("quantidade") or 1), 1)
                tam = (i.get("tamanho") if "tamanho" in cols else None) or "-"
                pid = i.get("id_produto")
                existe = pid and conn.execute("SELECT 1 FROM produtos WHERE id = ?", (pid,)).fetchone()
                tot = round(float(i.get("total") or 0), 2)
                conn.execute(
                    """INSERT INTO venda_itens (venda_id, variacao_id, produto_id, nome, tamanho, cor,
                           quantidade, preco_unit, custo_unit, desconto, total)
                       VALUES (?, ?, ?, ?, ?, NULL, ?, ?, NULL, 0, ?)""",
                    (venda_id, mapa_var.get((pid, tam)), pid if existe else None,
                     i.get("nome") or "Produto", tam, qtd, round(tot / qtd, 2), tot),
                )
            conn.execute(
                "INSERT INTO venda_pagamentos (venda_id, forma, valor) VALUES (?, ?, ?)",
                (venda_id, forma, total),
            )


def _v1(conn, db_path: str, backup_dir: str):
    tabelas = _tables(conn)
    tem_produtos = "produtos" in tabelas and "preco" in _columns(conn, "produtos")
    tem_vendas = "vendas" in tabelas and "id_produto" in _columns(conn, "vendas")

    if tem_produtos or tem_vendas:
        destino = backup_database(db_path, backup_dir, "_antes_v1")
        print(f"Backup do banco legado salvo em: {destino}")

    conn.execute("BEGIN IMMEDIATE")
    try:
        if tem_produtos:
            conn.execute("ALTER TABLE produtos RENAME TO legado_produtos")
        if tem_vendas:
            conn.execute("ALTER TABLE vendas RENAME TO legado_vendas")
        for stmt in _statements(SCHEMA_V1):
            conn.execute(stmt)
        for nome, tamanhos in GRADES_PADRAO:
            conn.execute("INSERT INTO grades (nome, tamanhos, padrao) VALUES (?, ?, 1)",
                         (nome, json.dumps(tamanhos, ensure_ascii=False)))
        for nome in CATEGORIAS_PADRAO:
            conn.execute("INSERT OR IGNORE INTO categorias (nome) VALUES (?)", (nome,))
        for chave, valor in (("loja_nome", "Estilo Único"), ("loja_documento", ""), ("loja_endereco", ""),
                             ("loja_telefone", ""), ("cupom_rodape", "Obrigado pela preferência!"),
                             ("dias_produto_parado", "60"), ("desconto_maximo_vendedor", "10")):
            conn.execute("INSERT OR IGNORE INTO configuracoes (chave, valor) VALUES (?, ?)", (chave, valor))
        if tem_produtos or tem_vendas:
            _migrar_legado(conn, tem_produtos, tem_vendas)
        if tem_vendas:
            conn.execute("DROP TABLE legado_vendas")
        if tem_produtos:
            conn.execute("DROP TABLE legado_produtos")
        conn.execute("PRAGMA user_version = 1")
        conn.execute("COMMIT")
    except BaseException:
        conn.execute("ROLLBACK")
        raise


def _v2(conn, db_path: str, backup_dir: str):
    conn.execute("BEGIN IMMEDIATE")
    try:
        conn.execute("""
            CREATE TABLE IF NOT EXISTS metas_vendedor (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                vendedor_id INTEGER NOT NULL REFERENCES usuarios(id) ON DELETE CASCADE,
                periodo TEXT NOT NULL,
                valor_meta REAL NOT NULL DEFAULT 0,
                criado_por INTEGER REFERENCES usuarios(id),
                atualizado_em TEXT NOT NULL DEFAULT (datetime('now', 'localtime')),
                UNIQUE (vendedor_id, periodo)
            )
        """)
        conn.execute("CREATE INDEX IF NOT EXISTS ix_metas_periodo ON metas_vendedor(periodo)")
        conn.execute("PRAGMA user_version = 2")
        conn.execute("COMMIT")
    except BaseException:
        conn.execute("ROLLBACK")
        raise


def _v3(conn, db_path: str, backup_dir: str):
    conn.execute("BEGIN IMMEDIATE")
    try:
        cols = _columns(conn, "usuarios")
        if "desconto_max_pct" not in cols:
            conn.execute("ALTER TABLE usuarios ADD COLUMN desconto_max_pct REAL DEFAULT NULL")

        # Atualiza grade Numérica para garantir inclusão de tamanhos adicionais (ex.: 50, 52)
        row = conn.execute("SELECT id, tamanhos FROM grades WHERE nome LIKE 'Num%rica' OR id = 2").fetchone()
        if row:
            try:
                tams = json.loads(row["tamanhos"])
                alterou = False
                for t in ["50", "52"]:
                    if t not in tams:
                        tams.append(t)
                        alterou = True
                if alterou:
                    conn.execute("UPDATE grades SET tamanhos = ? WHERE id = ?", (json.dumps(tams, ensure_ascii=False), row["id"]))
            except Exception:
                pass

        conn.execute("PRAGMA user_version = 3")
        conn.execute("COMMIT")
    except BaseException:
        conn.execute("ROLLBACK")
        raise


MIGRACOES = [_v1, _v2, _v3]


def migrate(db_path: str, backup_dir: str) -> int:
    Path(db_path).parent.mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(db_path, isolation_level=None)
    conn.row_factory = sqlite3.Row
    try:
        conn.execute("PRAGMA journal_mode = WAL")
        conn.execute("PRAGMA foreign_keys = OFF")  # durante rename/cópia
        versao = conn.execute("PRAGMA user_version").fetchone()[0]
        for numero, migracao in enumerate(MIGRACOES, start=1):
            if versao < numero:
                migracao(conn, db_path, backup_dir)
                versao = numero
        problemas = conn.execute("PRAGMA foreign_key_check").fetchall()
        if problemas:
            print(f"Aviso: {len(problemas)} referências inconsistentes no banco.")
        return versao
    finally:
        conn.close()

"""Acesso ao SQLite com transações explícitas e configuração para uso concorrente."""
import sqlite3
from contextlib import contextmanager

from flask import current_app, g


def connect(path: str) -> sqlite3.Connection:
    # isolation_level=None => autocommit; transações são abertas explicitamente
    conn = sqlite3.connect(path, timeout=10, isolation_level=None, check_same_thread=False)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA foreign_keys = ON")
    conn.execute("PRAGMA busy_timeout = 5000")
    return conn


def get_db() -> sqlite3.Connection:
    if "db" not in g:
        g.db = connect(current_app.config["DATABASE"])
    return g.db


def close_db(_exc=None):
    db = g.pop("db", None)
    if db is not None:
        db.close()


@contextmanager
def transaction(conn: sqlite3.Connection, immediate: bool = True):
    """BEGIN IMMEDIATE reserva a escrita já no início, evitando que duas vendas
    simultâneas leiam o mesmo estoque antes de gravar."""
    conn.execute("BEGIN IMMEDIATE" if immediate else "BEGIN")
    try:
        yield conn
        conn.execute("COMMIT")
    except BaseException:
        conn.execute("ROLLBACK")
        raise


def rows(cursor) -> list[dict]:
    return [dict(r) for r in cursor.fetchall()]


def one(cursor) -> dict | None:
    r = cursor.fetchone()
    return dict(r) if r else None

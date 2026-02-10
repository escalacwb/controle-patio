import os
from psycopg2 import pool
from dotenv import load_dotenv

load_dotenv()

_db_pool = None


def get_db_url() -> str:
    db_url = os.getenv("DB_URL")
    if not db_url:
        raise RuntimeError("DB_URL nao configurada")
    return db_url


def get_pool() -> pool.SimpleConnectionPool:
    global _db_pool
    if _db_pool is None:
        _db_pool = pool.SimpleConnectionPool(1, 10, dsn=get_db_url())
    return _db_pool


def get_connection():
    return get_pool().getconn()


def release_connection(conn) -> None:
    if conn:
        get_pool().putconn(conn)

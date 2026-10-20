"""Pool de conexões com o PostgreSQL (um pool por worker do Gunicorn)."""
import threading

from psycopg.rows import dict_row
from psycopg_pool import ConnectionPool

from . import config

_pool: ConnectionPool | None = None
_lock = threading.Lock()


def obter_pool() -> ConnectionPool:
    """Cria o pool de forma preguiçosa, já dentro do worker (após o fork)."""
    global _pool
    if _pool is None:
        with _lock:
            if _pool is None:
                _pool = ConnectionPool(
                    conninfo=config.conninfo(admin=False),
                    min_size=1,
                    max_size=config.DB_POOL_MAX,
                    timeout=config.DB_POOL_TIMEOUT,
                    kwargs={"row_factory": dict_row, "autocommit": False},
                    # testa a conexão antes de entregar (banco pode ter reiniciado)
                    check=ConnectionPool.check_connection,
                    open=True,
                )
    return _pool

"""Aguarda o PostgreSQL aceitar conexões (o healthcheck do compose já ajuda,
mas o usuário api_leitura é criado logo depois do banco subir)."""
import sys
import time

import psycopg

from app import config

for tentativa in range(1, 61):
    try:
        with psycopg.connect(config.conninfo(admin=True)) as conn:
            conn.execute("SELECT 1")
        print(f"[esperar_banco] banco pronto (tentativa {tentativa}).")
        sys.exit(0)
    except psycopg.OperationalError as exc:
        print(f"[esperar_banco] tentativa {tentativa}/60: {str(exc).strip()[:120]}")
        time.sleep(2)

print("[esperar_banco] banco não respondeu em 120 s.")
sys.exit(1)

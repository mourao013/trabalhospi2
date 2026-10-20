#!/bin/sh
# 1) espera o PostgreSQL  2) importa os dados (ETL)  3) sobe o Gunicorn
set -e

echo "[backend] aguardando banco de dados..."
python -m etl.esperar_banco

if [ "${PULAR_ETL:-0}" != "1" ]; then
    echo "[backend] executando ETL (importacao dos CSV)..."
    python -m etl.importar
fi

echo "[backend] iniciando Gunicorn..."
exec gunicorn -c gunicorn.conf.py "app:create_app()"

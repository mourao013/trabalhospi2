#!/bin/sh
# Cria um usuário SOMENTE LEITURA para a API.
# Mesmo que uma SQL injection passasse pelas validações, este usuário
# não consegue alterar/apagar dados (defesa em profundidade).
set -e

psql -v ON_ERROR_STOP=1 --username "$POSTGRES_USER" --dbname "$POSTGRES_DB" <<-EOSQL
    CREATE ROLE api_leitura LOGIN PASSWORD '${API_DB_PASSWORD:-leitura123}';
    GRANT CONNECT ON DATABASE "${POSTGRES_DB}" TO api_leitura;
    GRANT USAGE ON SCHEMA public TO api_leitura;
    GRANT SELECT ON ALL TABLES IN SCHEMA public TO api_leitura;
    ALTER DEFAULT PRIVILEGES IN SCHEMA public GRANT SELECT ON TABLES TO api_leitura;
    -- Nenhuma consulta da API pode passar de 5 s no banco
    ALTER ROLE api_leitura SET statement_timeout = '5s';
EOSQL

echo "[db-init] usuario api_leitura criado (somente leitura)."

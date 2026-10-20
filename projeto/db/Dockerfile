# Contêiner db-server: PostgreSQL com extensões de busca por similaridade.
FROM postgres:16-alpine

# Scripts executados automaticamente na PRIMEIRA inicialização do volume.
COPY init/ /docker-entrypoint-initdb.d/

# Garante finais de linha Unix nos scripts .sh (evita erro "\r: not found"
# quando o repositório é clonado no Windows). Ver REGISTRO_DE_ERROS.md (ERR-004).
RUN sed -i 's/\r$//' /docker-entrypoint-initdb.d/*.sh /docker-entrypoint-initdb.d/*.sql

EXPOSE 5432

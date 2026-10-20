"""Configurações lidas de variáveis de ambiente (definidas no docker-compose.yml)."""
import os


def _int(nome: str, padrao: int) -> int:
    try:
        return int(os.getenv(nome, padrao))
    except ValueError:
        return padrao


DB_HOST = os.getenv("DB_HOST", "db")
DB_PORT = _int("DB_PORT", 5432)
DB_NAME = os.getenv("DB_NAME", "servidores")

# Usuário SOMENTE LEITURA usado pela API
API_DB_USER = os.getenv("API_DB_USER", "api_leitura")
API_DB_PASSWORD = os.getenv("API_DB_PASSWORD", "leitura123")

# Usuário administrador (usado apenas pelo ETL)
ADMIN_DB_USER = os.getenv("POSTGRES_USER", "postgres")
ADMIN_DB_PASSWORD = os.getenv("POSTGRES_PASSWORD", "postgres")

# Tamanho do pool de conexões POR WORKER (deve ser >= threads do Gunicorn)
DB_POOL_MAX = _int("DB_POOL_MAX", 8)
# Tempo máximo esperando uma conexão livre no pool (s)
DB_POOL_TIMEOUT = _int("DB_POOL_TIMEOUT", 5)

# Tempo máximo de uma busca no banco (ms) -> acima disso retorna 504
BUSCA_TIMEOUT_MS = _int("BUSCA_TIMEOUT_MS", 5000)

# Paginação
POR_PAGINA_PADRAO = _int("POR_PAGINA_PADRAO", 20)
POR_PAGINA_MAX = _int("POR_PAGINA_MAX", 100)
# Teto de registros contados/paginados numa busca ampla (evita COUNT(*) caro)
MAX_RESULTADOS = _int("MAX_RESULTADOS", 10000)
# Limite máximo da busca por similaridade
SIMILAR_LIMIT_MAX = _int("SIMILAR_LIMIT_MAX", 100)

# Proteção contra sobrecarga
RATE_LIMIT_REQUISICOES = _int("RATE_LIMIT_REQUISICOES", 120)   # por IP...
RATE_LIMIT_JANELA_S = _int("RATE_LIMIT_JANELA_S", 60)          # ...nesta janela
MAX_BUSCAS_SIMULTANEAS = _int("MAX_BUSCAS_SIMULTANEAS", 8)     # por worker
ESPERA_VAGA_S = float(os.getenv("ESPERA_VAGA_S", "2"))          # espera por vaga


def conninfo(admin: bool = False) -> str:
    usuario = ADMIN_DB_USER if admin else API_DB_USER
    senha = ADMIN_DB_PASSWORD if admin else API_DB_PASSWORD
    return (
        f"host={DB_HOST} port={DB_PORT} dbname={DB_NAME} "
        f"user={usuario} password={senha} connect_timeout=5 "
        f"application_name={'etl' if admin else 'api'}"
    )

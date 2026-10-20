"""Validação e normalização dos parâmetros de busca.

Toda entrada do usuário passa por aqui ANTES de chegar ao banco.
As consultas SQL também são 100% parametrizadas (dupla proteção contra SQL injection).
"""
import re
import unicodedata

from . import config

UFS = {
    "AC", "AL", "AP", "AM", "BA", "CE", "DF", "ES", "GO", "MA", "MT", "MS", "MG", "PA",
    "PB", "PR", "PE", "PI", "RJ", "RN", "RS", "RO", "RR", "SC", "SP", "SE", "TO",
}

PARAMETROS_PERMITIDOS = {
    "nome", "similar", "cargo", "uf", "orgao", "situacao", "pagina", "por_pagina", "limit",
}
FILTROS_PRINCIPAIS = ("nome", "similar", "cargo", "uf", "orgao")

TAM_MIN = 2
TAM_MAX = 100

# Letras (inclusive acentuadas), espaço, apóstrofo, hífen e ponto.
_LETRAS = "A-Za-zÀ-ÖØ-öø-ÿ"
RE_NOME = re.compile(rf"^[{_LETRAS} .'\-]+$")
# Similaridade: igual ao nome + curinga '%'. ('_' NÃO é aceito: é curinga do LIKE)
RE_SIMILAR = re.compile(rf"^[{_LETRAS} .'\-%]+$")
# Cargo / órgão: aceitam também dígitos, barra, parênteses, vírgula, &, º, ª
RE_TEXTO = re.compile(rf"^[{_LETRAS}0-9 .'\-/(),&ºª]+$")

# Padrões típicos de SQL injection
RE_SQL_INJECTION = re.compile(
    r"(--|;|/\*|\*/|\\|"
    r"\b(union|select|insert|update|delete|drop|alter|truncate|create|grant|exec|execute|"
    r"sleep|pg_sleep|information_schema|pg_catalog)\b|"
    r"'\s*(or|and)\s|"
    r"\b(or|and)\s+\d+\s*=\s*\d+|"
    r"'\s*=\s*')",
    re.IGNORECASE,
)

SITUACOES = {
    "ATIVO": "ATIVO", "ATIVOS": "ATIVO",
    "APOSENTADO": "APOSENTADO", "APOSENTADOS": "APOSENTADO", "INATIVO": "APOSENTADO",
}


class ErroValidacao(Exception):
    """Erro de entrada do usuário -> vira resposta JSON 4xx."""

    def __init__(self, codigo: str, mensagem: str, status: int = 400, campo: str | None = None):
        super().__init__(mensagem)
        self.codigo = codigo
        self.mensagem = mensagem
        self.status = status
        self.campo = campo


def normalizar(texto: str) -> str:
    """'  José   da Silva ' -> 'JOSE DA SILVA' (mesma regra usada no ETL)."""
    texto = unicodedata.normalize("NFKD", texto)
    texto = "".join(c for c in texto if not unicodedata.combining(c))
    return re.sub(r"\s+", " ", texto).strip().upper()


def _limpar(valor: str) -> str:
    """Remove espaços e aspas/sinais envolventes: "<%no%me%>" -> %no%me%."""
    valor = valor.strip()
    while len(valor) >= 2 and (valor[0], valor[-1]) in {('"', '"'), ("'", "'"), ("<", ">"),
                                                          ("“", "”"), ("”", "”")}:
        valor = valor[1:-1].strip()
    return valor


def _texto(campo: str, valor: str, regex: re.Pattern, codigo_invalido: str) -> str:
    if RE_SQL_INJECTION.search(valor):
        raise ErroValidacao(
            "SQL_INJECTION_DETECTADA",
            f"O parâmetro '{campo}' contém comandos ou caracteres SQL não permitidos.",
            campo=campo,
        )
    if len(valor) < TAM_MIN or len(valor) > TAM_MAX:
        raise ErroValidacao(
            "TAMANHO_INVALIDO",
            f"O parâmetro '{campo}' deve ter entre {TAM_MIN} e {TAM_MAX} caracteres.",
            campo=campo,
        )
    if not regex.match(valor):
        raise ErroValidacao(
            codigo_invalido,
            f"O parâmetro '{campo}' contém caracteres inválidos.",
            campo=campo,
        )
    return valor


def _inteiro(campo: str, valor: str, minimo: int, maximo: int) -> int:
    try:
        numero = int(valor)
    except ValueError:
        raise ErroValidacao("PARAMETRO_INVALIDO", f"'{campo}' deve ser um número inteiro.",
                            campo=campo) from None
    if numero < minimo or numero > maximo:
        raise ErroValidacao("PARAMETRO_INVALIDO",
                            f"'{campo}' deve estar entre {minimo} e {maximo}.", campo=campo)
    return numero


def validar_busca(args) -> dict:
    """Recebe request.args (MultiDict) e devolve filtros validados e normalizados."""
    desconhecidos = sorted(set(args.keys()) - PARAMETROS_PERMITIDOS)
    if desconhecidos:
        raise ErroValidacao(
            "PARAMETRO_INVALIDO",
            f"Parâmetro(s) não reconhecido(s): {', '.join(desconhecidos)}. "
            f"Permitidos: {', '.join(sorted(PARAMETROS_PERMITIDOS))}.",
        )
    for chave in args.keys():
        if len(args.getlist(chave)) > 1:
            raise ErroValidacao("PARAMETRO_INVALIDO", f"O parâmetro '{chave}' foi informado mais de uma vez.",
                                campo=chave)

    brutos = {k: _limpar(args.get(k, "")) for k in args.keys()}
    for chave, valor in brutos.items():
        if valor == "":
            raise ErroValidacao("PARAMETRO_VAZIO", f"O parâmetro '{chave}' está vazio.", campo=chave)

    if not any(k in brutos for k in FILTROS_PRINCIPAIS):
        raise ErroValidacao(
            "FILTRO_OBRIGATORIO",
            "Informe ao menos um filtro: nome, similar, cargo, uf ou orgao.",
        )
    if "nome" in brutos and "similar" in brutos:
        raise ErroValidacao("PARAMETRO_INVALIDO", "Use 'nome' (exato) OU 'similar', não os dois.")

    filtros: dict = {}

    if "nome" in brutos:
        valor = _texto("nome", brutos["nome"], RE_NOME, "NOME_INVALIDO")
        filtros["nome"] = normalizar(valor)

    if "similar" in brutos:
        valor = _texto("similar", brutos["similar"], RE_SIMILAR, "NOME_INVALIDO")
        letras = re.sub(r"[^A-Za-zÀ-ÖØ-öø-ÿ]", "", valor)
        if len(letras) < 3:
            raise ErroValidacao("NOME_INVALIDO",
                                "A busca por similaridade precisa de ao menos 3 letras.", campo="similar")
        padrao = re.sub(r"%+", "%", normalizar(valor))
        padrao = re.sub(r"\s*%\s*", "%", padrao)  # "NOME % SOBRENOME" -> "NOME%SOBRENOME"
        if "%" not in padrao:
            padrao = f"%{padrao}%"
        filtros["similar"] = padrao
        # texto sem curingas, usado para ordenar por similaridade (pg_trgm)
        filtros["similar_texto"] = re.sub(r"\s+", " ", padrao.replace("%", " ")).strip()

    if "cargo" in brutos:
        filtros["cargo"] = normalizar(_texto("cargo", brutos["cargo"], RE_TEXTO, "CARGO_INVALIDO"))

    if "orgao" in brutos:
        filtros["orgao"] = normalizar(_texto("orgao", brutos["orgao"], RE_TEXTO, "ORGAO_INVALIDO"))

    if "uf" in brutos:
        uf = brutos["uf"].upper()
        if RE_SQL_INJECTION.search(uf):
            raise ErroValidacao("SQL_INJECTION_DETECTADA",
                                "O parâmetro 'uf' contém comandos SQL não permitidos.", campo="uf")
        if uf not in UFS:
            raise ErroValidacao("UF_INVALIDA",
                                f"UF '{brutos['uf'][:10]}' inválida. Use uma sigla como SP, RJ, DF...",
                                campo="uf")
        filtros["uf"] = uf

    if "situacao" in brutos:
        situacao = SITUACOES.get(normalizar(brutos["situacao"]))
        if not situacao:
            raise ErroValidacao("PARAMETRO_INVALIDO", "'situacao' deve ser ATIVO ou APOSENTADO.",
                                campo="situacao")
        filtros["situacao"] = situacao

    filtros["pagina"] = _inteiro("pagina", brutos.get("pagina", "1"), 1, 100000)

    por_pagina_padrao = config.POR_PAGINA_PADRAO
    if "limit" in brutos:
        limite = _inteiro("limit", brutos["limit"], 1, config.SIMILAR_LIMIT_MAX)
        if "similar" in filtros:
            filtros["limit"] = limite          # nº máximo de nomes similares
        else:
            por_pagina_padrao = limite         # sem 'similar', limit = itens por página
    elif "similar" in filtros:
        filtros["limit"] = config.SIMILAR_LIMIT_MAX

    filtros["por_pagina"] = _inteiro("por_pagina", brutos.get("por_pagina", str(por_pagina_padrao)),
                                     1, config.POR_PAGINA_MAX)
    return filtros


def validar_termo_autocompletar(valor: str | None) -> str:
    """Valida o termo 'q' dos endpoints /api/cargos e /api/orgaos."""
    valor = _limpar(valor or "")
    if not valor:
        return ""
    return normalizar(_texto("q", valor, RE_TEXTO, "PARAMETRO_INVALIDO"))

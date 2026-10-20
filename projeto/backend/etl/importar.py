"""ETL - importa os CSV de servidores (dados.gov.br) para o PostgreSQL.

Uso (feito automaticamente pelo entrypoint do contêiner):
    python -m etl.importar [pasta]      # padrão: /dados

Etapas por arquivo:
  1. Detecta codificação (UTF-8 / Windows-1252) e separador (; , | tab)
  2. Normaliza cabeçalhos e mapeia colunas por sinônimos (dicionário de dados)
  3. Trata valores: espaços, "Sem informação", datas, UF, situação
  4. COPY para tabela temporária (rápido) -> popula cargo, orgao e servidor
  5. Registra o arquivo em controle_importacao (não importa duas vezes)
"""
import csv
import io
import os
import random
import re
import sys
import time
import unicodedata
import zipfile
from datetime import date, datetime
from pathlib import Path

PASTA_PADRAO = os.getenv("PASTA_DADOS", "/dados")
FONTE_AMOSTRA = "AMOSTRA_FICTICIA"
UFS = {
    "AC", "AL", "AP", "AM", "BA", "CE", "DF", "ES", "GO", "MA", "MT", "MS", "MG", "PA",
    "PB", "PR", "PE", "PI", "RJ", "RN", "RS", "RO", "RR", "SC", "SP", "SE", "TO",
}
VAZIOS = {"", "-", "--", "NULL", "NAN", "NONE", "SEM INFORMACAO", "NAO INFORMADO", "N/A", "NA",
          "INVALIDO", "SEM INFORMAÇÃO", "NÃO INFORMADO"}

# Cabeçalho normalizado -> campo interno (o primeiro que existir no arquivo vence)
SINONIMOS = {
    "nome": ["nome", "nome_servidor", "nome_aposentado", "no_servidor", "nome_do_servidor",
             "nome_pensionista", "nome_beneficiario"],
    "cpf": ["cpf", "cpf_servidor", "nr_cpf", "cpf_mascarado"],
    "matricula": ["matricula", "matricula_siape", "mat_servidor", "matricula_servidor"],
    "cargo": ["descricao_cargo", "cargo", "nome_cargo", "no_cargo", "ds_cargo", "cargo_emprego",
              "descricao_cargo_emprego", "denominacao_cargo", "nome_cargo_emprego", "carreira",
              "descricao_carreira"],
    "orgao": ["orgao_lotacao", "nome_orgao", "orgao", "org_lotacao", "orgao_exercicio", "no_orgao",
              "nome_orgao_lotacao", "orgao_origem", "orgsup_lotacao", "orgao_superior", "uorg_lotacao"],
    "uf": ["uf_exercicio", "uf", "sg_uf", "uf_lotacao", "uf_upag", "uf_residencia", "sigla_uf",
           "uf_orgao", "uf_da_upag", "sg_uf_upag"],
    "situacao": ["situacao_vinculo", "situacao", "tipo_vinculo", "situacao_servidor", "situacao_funcional"],
    "tipo_aposentadoria": ["tipo_aposentadoria", "descricao_tipo_aposentadoria", "no_tipo_aposentadoria",
                           "tipo_de_aposentadoria", "fundamentacao_inatividade"],
    "data_ingresso": ["data_ingresso_servicopublico", "data_ingresso_servico_publico", "data_ingresso",
                      "data_ingresso_cargofuncao", "dt_ingresso", "data_de_ingresso"],
    "data_aposentadoria": ["data_aposentadoria", "dt_aposentadoria", "data_inicio_aposentadoria",
                           "data_de_aposentadoria", "data_inatividade"],
}


# ----------------------------------------------------------------------------
# Funções puras de tratamento (testadas em tests/test_etl.py)
# ----------------------------------------------------------------------------
def sem_acento(texto: str) -> str:
    texto = unicodedata.normalize("NFKD", texto)
    return "".join(c for c in texto if not unicodedata.combining(c))


def normalizar(texto: str) -> str:
    """Mesma regra do app/validacao.py: MAIÚSCULO, sem acento, espaços simples."""
    return re.sub(r"\s+", " ", sem_acento(texto)).strip().upper()


def normalizar_cabecalho(coluna: str) -> str:
    coluna = sem_acento(coluna.replace("\ufeff", "")).strip().lower()
    return re.sub(r"[^a-z0-9]+", "_", coluna).strip("_")


def mapear_colunas(cabecalho: list[str]) -> dict[str, int]:
    normalizados = [normalizar_cabecalho(c) for c in cabecalho]
    mapa = {}
    for campo, opcoes in SINONIMOS.items():
        for opcao in opcoes:
            if opcao in normalizados:
                mapa[campo] = normalizados.index(opcao)
                break
    return mapa


def limpar(valor: str | None) -> str | None:
    if valor is None:
        return None
    valor = re.sub(r"\s+", " ", valor).strip().strip('"').strip()
    if normalizar(valor) in VAZIOS or set(valor) <= {"*", ".", "-", " "}:
        return None
    return valor


def tratar_data(valor: str | None) -> date | None:
    valor = limpar(valor)
    if not valor:
        return None
    valor = valor[:10]
    for formato in ("%d/%m/%Y", "%Y-%m-%d", "%d-%m-%Y", "%Y%m%d", "%d%m%Y"):
        try:
            data = datetime.strptime(valor, formato).date()
            return data if 1900 <= data.year <= 2100 else None
        except ValueError:
            continue
    return None


def tratar_uf(valor: str | None) -> str | None:
    valor = limpar(valor)
    if not valor:
        return None
    valor = normalizar(valor)
    return valor if valor in UFS else None


def tratar_situacao(valor: str | None, nome_arquivo: str) -> str:
    v = normalizar(valor or "")
    if any(p in v for p in ("APOSENT", "INATIV", "RESERVA", "REFORMA")):
        return "APOSENTADO"
    if "ATIV" in v:
        return "ATIVO"
    return "APOSENTADO" if "APOSENT" in normalizar(nome_arquivo) else "ATIVO"


def detectar_codificacao(amostra: bytes, truncada: bool = False) -> str:
    """truncada=True quando a amostra é só o começo do arquivo (pode cortar um
    caractere UTF-8 multibyte no final - ver ERR-011)."""
    if amostra.startswith(b"\xef\xbb\xbf"):
        return "utf-8-sig"
    try:
        amostra.decode("utf-8")
        return "utf-8"
    except UnicodeDecodeError as exc:
        if truncada and exc.start >= len(amostra) - 3:
            return "utf-8"
        return "cp1252"


def detectar_separador(primeira_linha: str) -> str:
    contagem = {s: primeira_linha.count(s) for s in (";", ",", "|", "\t")}
    return max(contagem, key=contagem.get)


def transformar_linha(linha: list[str], mapa: dict[str, int], nome_arquivo: str) -> tuple | None:
    def campo(nome):
        i = mapa.get(nome)
        return linha[i] if i is not None and i < len(linha) else None

    nome = limpar(campo("nome"))
    if not nome or len(nome) < 2:
        return None
    cargo = limpar(campo("cargo"))
    orgao = limpar(campo("orgao"))
    return (
        nome[:200], normalizar(nome)[:200],
        limpar(campo("cpf")), limpar(campo("matricula")),
        tratar_situacao(campo("situacao"), nome_arquivo),
        cargo[:300] if cargo else None, normalizar(cargo)[:300] if cargo else None,
        orgao[:300] if orgao else None, normalizar(orgao)[:300] if orgao else None,
        tratar_uf(campo("uf")),
        limpar(campo("tipo_aposentadoria")),
        tratar_data(campo("data_ingresso")), tratar_data(campo("data_aposentadoria")),
    )


# ----------------------------------------------------------------------------
# Leitura de arquivos (.csv soltos ou dentro de .zip)
# ----------------------------------------------------------------------------
def listar_fontes(pasta: Path):
    """Gera (nome_logico, função_que_abre_bytes)."""
    for caminho in sorted(pasta.rglob("*")):
        sufixo = caminho.suffix.lower()
        if sufixo == ".csv":
            yield caminho.name, (lambda c=caminho: open(c, "rb"))
        elif sufixo == ".zip":
            with zipfile.ZipFile(caminho) as z:
                membros = [m for m in z.namelist() if m.lower().endswith(".csv")]
            for membro in membros:
                yield (f"{caminho.name}:{membro}",
                       (lambda c=caminho, m=membro: _abrir_membro_zip(c, m)))


class _MembroZip(io.RawIOBase):
    """Abre um CSV dentro do .zip e, ao fechar, fecha TAMBÉM o ZipFile
    (senão o arquivo .zip fica preso/aberto - ver ERR-010)."""

    def __init__(self, caminho: Path, membro: str):
        super().__init__()
        self._zip = zipfile.ZipFile(caminho)
        self._membro = self._zip.open(membro)

    def readable(self):
        return True

    def readinto(self, buffer):
        dados = self._membro.read(len(buffer))
        buffer[:len(dados)] = dados
        return len(dados)

    def close(self):
        if not self.closed:
            self._membro.close()
            self._zip.close()
        super().close()


def _abrir_membro_zip(caminho: Path, membro: str):
    return io.BufferedReader(_MembroZip(caminho, membro), buffer_size=1 << 20)


def ler_csv(abrir):
    """Gera (cabecalho, iterador_de_linhas) detectando codificação e separador."""
    tamanho = 65536
    with abrir() as bruto:
        amostra = bruto.read(tamanho)
    codificacao = detectar_codificacao(amostra, truncada=len(amostra) == tamanho)
    texto_amostra = amostra.decode(codificacao, errors="replace")
    separador = detectar_separador(texto_amostra.splitlines()[0] if texto_amostra else "")

    arquivo = abrir()
    texto = io.TextIOWrapper(arquivo, encoding=codificacao, errors="replace", newline="")
    leitor = csv.reader(texto, delimiter=separador, quotechar='"')
    cabecalho = next(leitor, [])
    return cabecalho, leitor, texto


# ----------------------------------------------------------------------------
# Banco de dados
# ----------------------------------------------------------------------------
SQL_STAGING = """
CREATE TEMP TABLE IF NOT EXISTS stg (
    nome TEXT, nome_busca TEXT, cpf TEXT, matricula TEXT, situacao TEXT,
    cargo TEXT, cargo_busca TEXT, orgao TEXT, orgao_busca TEXT, uf TEXT,
    tipo_aposentadoria TEXT, data_ingresso DATE, data_aposentadoria DATE
) ON COMMIT DELETE ROWS
"""

SQL_CARREGAR = """
INSERT INTO cargo (nome, nome_busca)
SELECT DISTINCT ON (cargo) cargo, cargo_busca FROM stg WHERE cargo IS NOT NULL
ON CONFLICT (nome) DO NOTHING;

INSERT INTO orgao (nome, nome_busca)
SELECT DISTINCT ON (orgao) orgao, orgao_busca FROM stg WHERE orgao IS NOT NULL
ON CONFLICT (nome) DO NOTHING;

INSERT INTO servidor (nome, nome_busca, cpf_mascarado, matricula, situacao, cargo_id, orgao_id,
                      uf, tipo_aposentadoria, data_ingresso, data_aposentadoria, fonte)
SELECT t.nome, t.nome_busca, t.cpf, t.matricula, t.situacao, c.id, o.id,
       t.uf, t.tipo_aposentadoria, t.data_ingresso, t.data_aposentadoria, %s
  FROM stg t
  LEFT JOIN cargo c ON c.nome = t.cargo
  LEFT JOIN orgao o ON o.nome = t.orgao;
"""

LOTE = 50000


def importar_arquivo(conn, nome_logico: str, abrir) -> int:
    cabecalho, leitor, texto = ler_csv(abrir)
    mapa = mapear_colunas(cabecalho)
    try:
        if "nome" not in mapa:
            if "cargo" in mapa:
                return importar_somente_cargos(conn, leitor, mapa, nome_logico)
            print(f"  ! {nome_logico}: sem colunas reconhecidas, ignorado. Cabeçalho: {cabecalho[:8]}")
            return 0

        print(f"  > {nome_logico}: colunas mapeadas {sorted(mapa)}")
        total, descartadas = 0, 0
        with conn.cursor() as cur:
            cur.execute(SQL_STAGING)
            lote = []
            for linha in leitor:
                registro = transformar_linha(linha, mapa, nome_logico)
                if registro is None:
                    descartadas += 1
                    continue
                lote.append(registro)
                if len(lote) >= LOTE:
                    total += _gravar_lote(cur, lote, nome_logico)
                    lote.clear()
                    print(f"    ... {total} linhas")
            if lote:
                total += _gravar_lote(cur, lote, nome_logico)
            cur.execute(
                "INSERT INTO controle_importacao (arquivo, linhas) VALUES (%s, %s)",
                (nome_logico, total),
            )
        conn.commit()
        print(f"  OK {nome_logico}: {total} importadas, {descartadas} descartadas (sem nome)")
        return total
    finally:
        texto.close()


def _gravar_lote(cur, lote: list[tuple], fonte: str) -> int:
    with cur.copy(
        "COPY stg (nome, nome_busca, cpf, matricula, situacao, cargo, cargo_busca, orgao, orgao_busca,"
        " uf, tipo_aposentadoria, data_ingresso, data_aposentadoria) FROM STDIN"
    ) as copia:
        for registro in lote:
            copia.write_row(registro)
    for comando in [c for c in SQL_CARREGAR.split(";") if c.strip()]:
        cur.execute(comando, (fonte,) if "%s" in comando else None)
    cur.execute("TRUNCATE stg")
    return len(lote)


def importar_somente_cargos(conn, leitor, mapa, nome_logico: str) -> int:
    nomes = set()
    for linha in leitor:
        i = mapa["cargo"]
        cargo = limpar(linha[i]) if i < len(linha) else None
        if cargo:
            nomes.add(cargo[:300])
    with conn.cursor() as cur:
        cur.executemany(
            "INSERT INTO cargo (nome, nome_busca) VALUES (%s, %s) ON CONFLICT (nome) DO NOTHING",
            [(n, normalizar(n)) for n in nomes],
        )
        cur.execute("INSERT INTO controle_importacao (arquivo, linhas) VALUES (%s, %s)",
                    (nome_logico, len(nomes)))
    conn.commit()
    print(f"  OK {nome_logico}: {len(nomes)} cargos (tabela de carreiras/cargos)")
    return len(nomes)


# ----------------------------------------------------------------------------
# Amostra fictícia (somente quando não há CSV real na pasta)
# ----------------------------------------------------------------------------
PRENOMES = ["ANA", "MARIA", "JOSE", "JOAO", "ANTONIO", "FRANCISCO", "CARLOS", "PAULO", "PEDRO",
            "LUCAS", "LUIZ", "MARCOS", "LUIS", "GABRIEL", "RAFAEL", "DANIEL", "MARCELO", "BRUNO",
            "FERNANDA", "JULIANA", "PATRICIA", "ALINE", "SANDRA", "CAMILA", "AMANDA", "BRUNA",
            "JESSICA", "LETICIA", "JULIA", "LUCIANA", "VANESSA", "MARIANA", "GABRIELA", "VERA",
            "RAIMUNDO", "SEBASTIAO", "TEREZA", "RITA", "CLAUDIA", "ROBERTO"]
SOBRENOMES = ["SILVA", "SANTOS", "OLIVEIRA", "SOUZA", "RODRIGUES", "FERREIRA", "ALVES", "PEREIRA",
              "LIMA", "GOMES", "COSTA", "RIBEIRO", "MARTINS", "CARVALHO", "ALMEIDA", "LOPES",
              "SOARES", "FERNANDES", "VIEIRA", "BARBOSA", "ROCHA", "DIAS", "NASCIMENTO", "ANDRADE",
              "MOREIRA", "NUNES", "MARQUES", "MACHADO", "MENDES", "FREITAS", "CARDOSO", "RAMOS"]
CARGOS = ["PROFESSOR DO MAGISTERIO SUPERIOR", "TECNICO EM ASSUNTOS EDUCACIONAIS", "ANALISTA TRIBUTARIO",
          "AUDITOR FISCAL DA RECEITA FEDERAL", "AGENTE ADMINISTRATIVO", "MEDICO", "ENFERMEIRO",
          "ASSISTENTE EM ADMINISTRACAO", "ENGENHEIRO", "AGENTE DE POLICIA FEDERAL",
          "PESQUISADOR", "ANALISTA DE INFRAESTRUTURA", "TECNICO DO SEGURO SOCIAL",
          "ANALISTA DO SEGURO SOCIAL", "AUXILIAR DE ENFERMAGEM", "PROFESSOR ENS BASICO TECN TECNOLOGICO",
          "ADMINISTRADOR", "CONTADOR", "BIBLIOTECARIO-DOCUMENTALISTA", "ECONOMISTA"]
ORGAOS = ["MINISTERIO DA SAUDE", "MINISTERIO DA EDUCACAO", "INSTITUTO NACIONAL DO SEGURO SOCIAL",
          "UNIVERSIDADE FEDERAL DE MINAS GERAIS", "UNIVERSIDADE DE BRASILIA", "MINISTERIO DA FAZENDA",
          "DEPARTAMENTO DE POLICIA FEDERAL", "UNIVERSIDADE FEDERAL DO RIO DE JANEIRO",
          "INSTITUTO FEDERAL DE SAO PAULO", "FUNDACAO OSWALDO CRUZ", "MINISTERIO DA ECONOMIA",
          "UNIVERSIDADE FEDERAL DO PARANA", "INSTITUTO BRASILEIRO DE GEOGRAFIA E ESTATISTICA",
          "UNIVERSIDADE FEDERAL DA BAHIA", "MINISTERIO DA AGRICULTURA E PECUARIA"]
TIPOS_APOSENTADORIA = ["VOLUNTARIA", "COMPULSORIA", "INVALIDEZ PERMANENTE", "ESPECIAL"]


def gerar_amostra(quantidade: int = 20000):
    rnd = random.Random(42)  # semente fixa: a amostra é sempre a mesma
    ufs = sorted(UFS)
    for i in range(quantidade):
        nome = f"{rnd.choice(PRENOMES)} {rnd.choice(SOBRENOMES)} {rnd.choice(SOBRENOMES)}"
        aposentado = rnd.random() < 0.45
        ingresso = date(rnd.randint(1975, 2018), rnd.randint(1, 12), rnd.randint(1, 28))
        apos = date(min(ingresso.year + rnd.randint(25, 38), 2025), rnd.randint(1, 12), rnd.randint(1, 28)) \
            if aposentado else None
        cargo, orgao = rnd.choice(CARGOS), rnd.choice(ORGAOS)
        yield (
            nome, nome, f"***.{rnd.randint(100, 999)}.{rnd.randint(100, 999)}-**", f"{1000000 + i}",
            "APOSENTADO" if aposentado else "ATIVO",
            cargo, cargo, orgao, orgao, rnd.choice(ufs),
            rnd.choice(TIPOS_APOSENTADORIA) if aposentado else None, ingresso, apos,
        )


def importar_amostra(conn) -> None:
    print(f"  > Nenhum CSV encontrado: gerando amostra FICTÍCIA ({FONTE_AMOSTRA}).")
    with conn.cursor() as cur:
        cur.execute(SQL_STAGING)
        total = _gravar_lote(cur, list(gerar_amostra()), FONTE_AMOSTRA)
        cur.execute("INSERT INTO controle_importacao (arquivo, linhas) VALUES (%s, %s)",
                    (FONTE_AMOSTRA, total))
    conn.commit()
    print(f"  OK amostra fictícia: {total} registros")


# ----------------------------------------------------------------------------
def main(pasta: str = PASTA_PADRAO) -> None:
    import psycopg  # import tardio: as funções puras podem ser testadas sem psycopg

    from app import config

    inicio = time.time()
    pasta_dados = Path(pasta)
    fontes = list(listar_fontes(pasta_dados)) if pasta_dados.exists() else []
    print(f"[ETL] pasta {pasta_dados}: {len(fontes)} arquivo(s) CSV encontrado(s).")

    with psycopg.connect(config.conninfo(admin=True)) as conn:
        ja_importados = {r[0] for r in conn.execute("SELECT arquivo FROM controle_importacao")}
        conn.commit()

        if fontes and FONTE_AMOSTRA in ja_importados:
            print("  > CSV reais encontrados: removendo amostra fictícia.")
            conn.execute("DELETE FROM servidor WHERE fonte = %s", (FONTE_AMOSTRA,))
            conn.execute("DELETE FROM controle_importacao WHERE arquivo = %s", (FONTE_AMOSTRA,))
            conn.commit()

        novos = 0
        for nome_logico, abrir in fontes:
            if nome_logico in ja_importados:
                print(f"  = {nome_logico}: já importado, pulando.")
                continue
            try:
                novos += importar_arquivo(conn, nome_logico, abrir)
            except Exception as exc:  # um arquivo ruim não derruba a importação inteira
                conn.rollback()
                print(f"  ! ERRO em {nome_logico}: {type(exc).__name__}: {exc}")

        if not fontes and FONTE_AMOSTRA not in ja_importados:
            importar_amostra(conn)
            novos += 1

        if novos:
            print("  > ANALYZE (atualiza estatísticas do planejador)...")
            conn.autocommit = True
            conn.execute("ANALYZE")

    print(f"[ETL] concluído em {time.time() - inicio:.1f}s.")


if __name__ == "__main__":
    main(sys.argv[1] if len(sys.argv) > 1 else PASTA_PADRAO)

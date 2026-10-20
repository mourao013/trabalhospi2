-- =====================================================================
-- Esquema do banco "servidores" - Servidores do Poder Executivo Federal
-- Fontes: dados.gov.br
--   * Gestão de Pessoas do Executivo Federal - Aposentados
--   * Gestão de Pessoas do Executivo Federal - Carreiras/Cargos
-- =====================================================================

-- Extensão de trigramas: permite índices GIN para LIKE '%x%' e similarity().
CREATE EXTENSION IF NOT EXISTS pg_trgm;

-- ---------------------------------------------------------------------
-- Tabelas de domínio (normalização: evita repetir textos longos)
-- ---------------------------------------------------------------------
CREATE TABLE IF NOT EXISTS uf (
    sigla CHAR(2) PRIMARY KEY,
    nome  TEXT    NOT NULL
);

INSERT INTO uf (sigla, nome) VALUES
 ('AC','Acre'),('AL','Alagoas'),('AP','Amapá'),('AM','Amazonas'),('BA','Bahia'),
 ('CE','Ceará'),('DF','Distrito Federal'),('ES','Espírito Santo'),('GO','Goiás'),
 ('MA','Maranhão'),('MT','Mato Grosso'),('MS','Mato Grosso do Sul'),('MG','Minas Gerais'),
 ('PA','Pará'),('PB','Paraíba'),('PR','Paraná'),('PE','Pernambuco'),('PI','Piauí'),
 ('RJ','Rio de Janeiro'),('RN','Rio Grande do Norte'),('RS','Rio Grande do Sul'),
 ('RO','Rondônia'),('RR','Roraima'),('SC','Santa Catarina'),('SP','São Paulo'),
 ('SE','Sergipe'),('TO','Tocantins')
ON CONFLICT (sigla) DO NOTHING;

CREATE TABLE IF NOT EXISTS cargo (
    id         SERIAL PRIMARY KEY,
    nome       TEXT NOT NULL UNIQUE,      -- texto original
    nome_busca TEXT NOT NULL              -- MAIÚSCULO, sem acento (normalizado no ETL)
);

CREATE TABLE IF NOT EXISTS orgao (
    id         SERIAL PRIMARY KEY,
    nome       TEXT NOT NULL UNIQUE,
    nome_busca TEXT NOT NULL
);

-- ---------------------------------------------------------------------
-- Tabela principal
-- ---------------------------------------------------------------------
CREATE TABLE IF NOT EXISTS servidor (
    id                 BIGSERIAL PRIMARY KEY,
    nome               TEXT NOT NULL,
    nome_busca         TEXT NOT NULL,
    cpf_mascarado      TEXT,
    matricula          TEXT,
    situacao           TEXT NOT NULL CHECK (situacao IN ('ATIVO', 'APOSENTADO')),
    cargo_id           INTEGER REFERENCES cargo(id),
    orgao_id           INTEGER REFERENCES orgao(id),
    uf                 CHAR(2) REFERENCES uf(sigla),
    tipo_aposentadoria TEXT,
    data_ingresso      DATE,
    data_aposentadoria DATE,
    fonte              TEXT NOT NULL      -- arquivo de origem (rastreabilidade)
);

-- Controle de arquivos já importados (ETL idempotente)
CREATE TABLE IF NOT EXISTS controle_importacao (
    arquivo      TEXT PRIMARY KEY,
    linhas       INTEGER NOT NULL,
    importado_em TIMESTAMPTZ NOT NULL DEFAULT now()
);

-- ---------------------------------------------------------------------
-- Índices para buscas indexadas e por similaridade
-- ---------------------------------------------------------------------
-- Busca exata por nome  (WHERE nome_busca = 'FULANO DE TAL')
CREATE INDEX IF NOT EXISTS idx_servidor_nome_exato  ON servidor (nome_busca text_pattern_ops);
-- Busca por similaridade / curingas (LIKE '%FULANO%TAL%' e similarity())
CREATE INDEX IF NOT EXISTS idx_servidor_nome_trgm   ON servidor USING gin (nome_busca gin_trgm_ops);
-- Filtros
CREATE INDEX IF NOT EXISTS idx_servidor_uf          ON servidor (uf);
CREATE INDEX IF NOT EXISTS idx_servidor_cargo       ON servidor (cargo_id);
CREATE INDEX IF NOT EXISTS idx_servidor_orgao       ON servidor (orgao_id);
CREATE INDEX IF NOT EXISTS idx_servidor_situacao    ON servidor (situacao);
-- Combinações frequentes (cargo+UF, órgão+UF)
CREATE INDEX IF NOT EXISTS idx_servidor_cargo_uf    ON servidor (cargo_id, uf);
CREATE INDEX IF NOT EXISTS idx_servidor_orgao_uf    ON servidor (orgao_id, uf);
-- Busca parcial em cargos e órgãos
CREATE INDEX IF NOT EXISTS idx_cargo_trgm ON cargo USING gin (nome_busca gin_trgm_ops);
CREATE INDEX IF NOT EXISTS idx_orgao_trgm ON orgao USING gin (nome_busca gin_trgm_ops);

-- View de consulta usada pela API
CREATE OR REPLACE VIEW vw_servidor AS
SELECT s.id, s.nome, s.nome_busca, s.cpf_mascarado, s.matricula, s.situacao,
       c.nome AS cargo, o.nome AS orgao, s.uf, u.nome AS uf_nome,
       s.tipo_aposentadoria, s.data_ingresso, s.data_aposentadoria,
       s.cargo_id, s.orgao_id
  FROM servidor s
  LEFT JOIN cargo c ON c.id = s.cargo_id
  LEFT JOIN orgao o ON o.id = s.orgao_id
  LEFT JOIN uf    u ON u.sigla = s.uf;

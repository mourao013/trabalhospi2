# Sistema de Consulta de Servidores do Poder Executivo Federal

Aplicação Full Stack modularizada em **Docker** para consulta otimizada de servidores **Ativos** e **Aposentados** do Poder Executivo Federal (`dados.gov.br`), desenvolvida como trabalho do 3º Bimestre.

---

## Equipe de Desenvolvimento

| Nome do Integrante | Matrícula | Papel no Projeto |
| :--- | :---: | :--- |
| **Pedro Henrique Cardoso** | `169618` | Engenharia de Dados, Modelagem PostgreSQL (`pg_trgm`) e Pipeline ETL |
| **Carlos Mourão** | `171075` | Líder Técnico, Arquitetura Docker, Backend Flask + WSGI Gunicorn e Segurança |
| **João Vitor** | `171077` | Front-end Web (HTML/CSS/JS + Nginx), App Desktop (Tkinter) e Testes de Sobrecarga |

*(Veja também o arquivo [`INTEGRANTES.txt`](INTEGRANTES.txt)).*

---

## Estrutura do Projeto

```text
projeto/
├── docker-compose.yml          # Orquestração dos 3 contêineres (db-server, backend, frontend)
├── db/                         # Contêiner db-server (PostgreSQL 16 + pg_trgm)
│   ├── Dockerfile
│   ├── init/
│   │   ├── 01_schema.sql       # Tabelas normalizadas + Índices B-Tree e GIN (trigramas)
│   │   └── 02_usuario_api.sh   # Role somente-leitura (api_leitura) com statement_timeout=5s
│   └── dados/                  # Pasta para os CSVs do dados.gov.br (Aposentados / Carreiras)
├── backend/                    # Contêiner backend (Python 3.12 + Flask + WSGI Gunicorn gthread)
│   ├── Dockerfile
│   ├── entrypoint.sh
│   ├── gunicorn.conf.py
│   ├── requirements.txt
│   ├── app/                    # API REST (/api/servidores, validação anti-SQLi, proteção)
│   ├── etl/                    # Importador automático CSV/ZIP -> PostgreSQL (COPY)
│   ├── scripts/
│   │   └── teste_sobrecarga.py # Teste de estresse paralelo na API
│   └── tests/                  # 33 testes unitários (validação, ETL e endpoints)
├── frontend/                   # Contêiner frontend (Nginx + HTML5/CSS3/JS)
│   ├── Dockerfile
│   ├── nginx.conf              # Servidor estático + Proxy Reverso /api + Rate Limit
│   └── site/
│       ├── index.html
│       ├── css/estilo.css
│       └── js/app.js
└── desktop/                    # Adicional: Aplicação Desktop nativa sem Docker (Python/Tkinter)
    ├── app_desktop.py
    └── LEIA-ME.md
```

---

## Como Executar (Docker Compose)

A partir da pasta `projeto/`, execute:

```bash
cd projeto
docker compose up --build
```

Após a inicialização automática dos 3 contêineres:
- **Aplicação Web (Front-end)**: [http://localhost:8080](http://localhost:8080)
- **API Flask + Gunicorn (Back-end)**: [http://localhost:5000/api/saude](http://localhost:5000/api/saude)
- **PostgreSQL (`db-server`)**: `localhost:5432` (banco `servidores`)

> **Nota sobre a Base de Dados**: Coloque os arquivos `.csv` ou `.zip` baixados do Portal Brasileiro de Dados Abertos (`dados.gov.br`) em `projeto/db/dados/`. Caso a pasta esteja vazia na primeira execução, o ETL gera automaticamente uma amostra de 20.000 servidores para testes imediatos, substituindo-a assim que arquivos CSV reais forem adicionados.

---

## Exemplos de Endpoints da API

- **Busca por nome exato**: `GET /api/servidores?nome=MARIA DA SILVA`
- **Busca por similaridade (com limite)**: `GET /api/servidores?similar=%MARIA%SILVA%&limit=100`
- **Busca por cargo/profissão**: `GET /api/servidores?cargo=PROFESSOR`
- **Busca por estado (UF)**: `GET /api/servidores?uf=DF`
- **Busca por instituição/órgão**: `GET /api/servidores?orgao=MINISTERIO DA SAUDE`
- **Busca combinada avançada**: `GET /api/servidores?nome=ANA&cargo=MEDICO&uf=SP&situacao=ATIVO&pagina=1&por_pagina=20`

---

## Como Executar os Testes e o App Desktop

```bash
# Testes unitários do Backend (33 testes)
cd projeto/backend
python -m unittest discover -s tests -v

# Teste de sobrecarga paralela (Requisito 7)
python scripts/teste_sobrecarga.py http://localhost:5000 32 160

# Aplicação Desktop (Adicional - sem Docker)
python ../desktop/app_desktop.py
```

---

## Documentação Adicional

- [`INTEGRANTES.txt`](INTEGRANTES.txt): Identificação completa dos integrantes da equipe e respectivas matrículas.
- [`RELATORIO_FINAL.md`](RELATORIO_FINAL.md): Relatório ágil completo (divisão de tarefas da equipe, Sprints, gráfico de Burndown, arquitetura, pontos fortes/fracos e limitações).
- [`REGISTRO_DE_ERROS.md`](REGISTRO_DE_ERROS.md): Catálogo detalhado de todos os erros encontrados e resolvidos durante o desenvolvimento (incluindo `ERR-013` sobre interpolação de crases no PowerShell).

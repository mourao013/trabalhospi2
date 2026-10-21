# Registro de Erros e Lições Aprendidas (Base de Conhecimento de Engenharia)

Este arquivo documenta **todos os erros técnicos, armadilhas de arquitetura e incidentes** encontrados e corrigidos durante o desenvolvimento desta aplicação Full Stack (Docker + PostgreSQL + Python/Flask/Gunicorn + Front-end Web/Desktop).

O objetivo deste registro é **evitar a repetição desses erros neste projeto e em projetos futuros**.

---

## Sumário Rápido de Erros

| Código | Camada | Resumo do Erro | Causa Raiz | Solução Definitiva |
| :--- | :--- | :--- | :--- | :--- |
| **ERR-001** | SGBD / SQL | Lentidão extrema em buscas `LIKE '%NOME%SOBRENOME%'` (Full Table Scan) | Índice B-Tree padrão não indexa curingas à esquerda (`%texto`) | Extensão `pg_trgm` + Índice GIN (`gin_trgm_ops`) na coluna normalizada `nome_busca` |
| **ERR-002** | ETL / CSV | `UnicodeDecodeError` ao ler arquivos CSV do Portal da Transparência (`dados.gov.br`) | Arquivos oficiais usam `cp1252`/`latin-1` e separador `;`, não UTF-8 com `,` | Heurística automática `detectar_codificacao()` e `detectar_separador()` antes do parse |
| **ERR-003** | ETL / Dados | Divergência de nomes de colunas entre arquivos de Ativos, Aposentados e Carreiras | Governança de dados variáveis entre anos/conjuntos no `dados.gov.br` | Normalização de cabeçalho + dicionário `SINONIMOS` mapeando variações para esquema único |
| **ERR-004** | Docker / SO | Falha `exec /app/entrypoint.sh: no such file or directory` ou `\r: not found` | Repositório clonado no Windows com `core.autocrlf=true` converte LF para CRLF | `RUN sed -i 's/\r$//' ...` nos `Dockerfile`s + `.gitattributes` forçando `eol=lf` |
| **ERR-005** | Docker Compose | Contêiner `backend` falha ao iniciar porque o PostgreSQL ainda está rodando `initdb` | `depends_on` simples aguarda apenas o contêiner subir, não o SGBD aceitar conexões | `healthcheck` com `pg_isready` no serviço `db` + script `etl/esperar_banco.py` no `backend` |
| **ERR-006** | Segurança / SQL | Risco de SQL Injection em filtros combinados e ordenação por similaridade | Concatenação direta de strings SQL ou uso incorreto de curingas | Consultas 100% parametrizadas (`%s`), regex anti-injection (`RE_SQL_INJECTION`) e role `api_leitura` read-only |
| **ERR-007** | Gunicorn / Pool | Erros intermitentes no `psycopg_pool` quando múltiplos workers atendem requisições | Criar `ConnectionPool` antes do `fork()` dos workers (`preload_app = True`) compartilha descritores de socket | Definir `preload_app = False` no `gunicorn.conf.py` e inicializar o pool de forma lazy (`obter_pool()`) pós-fork |
| **ERR-008** | Performance BD | `COUNT(*)` exato em buscas amplas (ex.: `uf=DF`) trava o banco por vários segundos | Contagem completa varre centenas de milhares de tuplas no heap | Contagem limitada `SELECT count(*) FROM (SELECT 1 ... LIMIT 10001)` + `reltuples` no healthcheck |
| **ERR-009** | Psycopg 3 / SQL | `psycopg.errors.SyntaxError` ao executar `SET LOCAL statement_timeout = %s` | O comando `SET` do PostgreSQL não aceita parâmetros preparados (`$1`) no protocolo estendido do Psycopg 3 | Usar `SELECT set_config('statement_timeout', %s, true)` que aceita bind parameters nativamente |
| **ERR-010** | Python / I/O | `PermissionError: [WinError 32]` ao limpar arquivos `.zip` temporários após leitura no ETL | `zipfile.ZipFile.open()` fecha apenas o stream interno do membro, deixando o arquivo `.zip` aberto no SO | Classe wrapper `_MembroZip(io.RawIOBase)` que fecha tanto o membro quanto o `ZipFile` no `.close()` |
| **ERR-011** | Python / UTF-8 | Falso positivo de UTF-8 em strings curtas `cp1252` (ex.: `"José".encode("cp1252")`) | Regra `exc.start >= len(amostra) - 3` ativava em amostras menores que 64 KB que não haviam sido truncadas | Passar flag `truncada=(len(amostra) == 65536)` para `detectar_codificacao()` |
| **ERR-012** | Sobrecarga API | Exaustão de conexões do PostgreSQL (`too many clients already`) em rajadas paralelas | Múltiplas threads abrindo conexões sem teto global nem fila de espera | Camada quádrupla: `limit_req` no Nginx + `LimitadorTaxa` (429) + `BoundedSemaphore` (503) + `ConnectionPool` fixo |
| **ERR-013** | PowerShell / Markdown | Caracteres corrompidos (`ackend`, `rontend`, `ash`) no `README.md` gerado no 1º commit | Uso de here-string com aspas duplas (`@"..."@`) no PowerShell, onde a crase `` ` `` é o caractere de escape (`\`b` = backspace, `\`f` = form feed) | Escrever arquivos Markdown diretamente com encoding UTF-8 sem interpolação de aspas duplas do PowerShell (ou usar here-string literal `@'...'@`) |
| **ERR-014** | Desktop / Tkinter | `RuntimeError: main thread is not in main loop` | Thread de rede lendo variáveis Tkinter | Ler dados da interface na thread principal; thread só faz HTTP; retorno via `after()` |
| **ERR-015** | Desktop / Python | Popup de erro da API não aparecia (`NameError`) | Callback adiado usando `exc`, que o Python apaga ao sair do `except` | `msg = str(exc)` + `lambda m=msg:` |
| **ERR-016** | Desktop / Rede | Respostas com ~2 s de atraso | `localhost` resolve para IPv6 `::1` primeiro no Windows | URL padrão `http://127.0.0.1:5000` |

---

## Detalhamento Técnico de Cada Erro

### ERR-001 — Lentidão em buscas por similaridade (`LIKE '%NOME%SOBRENOME%'`)
- **Contexto**: O requisito funcional exige buscas por curingas no início, meio e fim (`%NOME%SOBRENOME%`) e ordenação por similaridade com limite de até 100 registros.
- **Sintoma**: Em bases com centenas de milhares de servidores, `WHERE nome LIKE '%SILVA%'` ignorava o índice B-Tree padrão e executava *Sequential Scan*, levando mais de 2 segundos por requisição.
- **Causa**: Índices B-Tree (`text_pattern_ops`) só aceleram prefixos (`'NOME%'`).
- **Como foi resolvido**:
  1. Habilitada a extensão `CREATE EXTENSION IF NOT EXISTS pg_trgm;` em `db/init/01_schema.sql`.
  2. Criado índice GIN de trigramas: `CREATE INDEX idx_servidor_nome_trgm ON servidor USING gin (nome_busca gin_trgm_ops);`.
  3. Mantido também o índice B-Tree `idx_servidor_nome_exato` para buscas exatas (`=`).
- **Regra para próximos projetos**: Sempre que houver busca parcial (`LIKE '%x%'` ou `ILIKE`) em tabelas grandes no PostgreSQL, criar coluna normalizada (MAIÚSCULA e sem acentos) indexada com `gin_trgm_ops`.

### ERR-002 — Falha de codificação e delimitador nos CSVs do `dados.gov.br`
- **Contexto**: Importação dos conjuntos *Aposentados* e *Carreiras/Cargos* do Portal Brasileiro de Dados Abertos.
- **Sintoma**: `UnicodeDecodeError: 'utf-8' codec can't decode byte 0xe9` ao abrir os arquivos com `open(..., encoding='utf-8')` e colunas inteiras aglutinadas por usar vírgula `,` em vez de `;`.
- **Causa**: Os arquivos gerados pelo SIAPE/Portal da Transparência utilizam codificação `Windows-1252` (`cp1252` / `latin-1`) e ponto-e-vírgula (`;`) como separador.
- **Como foi resolvido**: Em `backend/etl/importar.py`, as funções `detectar_codificacao()` e `detectar_separador()` inspecionam os primeiros 64 KB do arquivo antes de iniciar o leitor CSV.
- **Regra para próximos projetos**: Nunca assumir UTF-8 ou vírgula em dados governamentais brasileiros; sempre detectar codificação e delimitador programaticamente.

### ERR-003 — Colunas com nomes diferentes entre arquivos CSV e ausência de UF direta em alguns lotes
- **Contexto**: Cruzamento dos arquivos de *Aposentados* e *Carreiras/Cargos*.
- **Sintoma**: Alguns CSVs nomeiam a coluna como `DESCRICAO_CARGO`, outros `DENOMINACAO_CARGO` ou `CARREIRA`; a UF pode vir como `UF_EXERCICIO`, `SIGLA_UF`, `UF_UPAG` ou estar ausente em tabelas exclusivas de estrutura de carreiras.
- **Como foi resolvido**: Criado o dicionário `SINONIMOS` em `backend/etl/importar.py` que normaliza o cabeçalho (sem acentos, minúsculo, snake_case) e vincula automaticamente ao modelo relacional (`servidor`, `cargo`, `orgao`, `uf`). Arquivos que contêm apenas a relação de carreiras/cargos (sem coluna de nome de servidor) são detectados e importados diretamente na tabela de domínio `cargo` via `importar_somente_cargos()`.

### ERR-004 — Quebra de scripts `.sh` no Docker quando clonado no Windows (`CRLF`)
- **Contexto**: Execução de `docker compose up --build` em máquinas Windows.
- **Sintoma**: O contêiner aborta imediatamente na inicialização com `exec /app/entrypoint.sh: no such file or directory` porque o kernel Linux procura o interpretador `/bin/sh\r`.
- **Causa**: O Git no Windows (`core.autocrlf=true`) converte quebras de linha `LF` em `CRLF` ao fazer checkout.
- **Como foi resolvido**: Adicionado `RUN sed -i 's/\r$//' /app/entrypoint.sh` no `backend/Dockerfile` e `RUN sed -i 's/\r$//' /docker-entrypoint-initdb.d/*.sh` no `db/Dockerfile`.
- **Regra para próximos projetos**: Todo `Dockerfile` que copia scripts shell deve remover `\r` com `sed` durante o build.

### ERR-005 — Race Condition entre inicialização do PostgreSQL e subida do Backend
- **Contexto**: Subida simultânea dos 3 contêineres via `docker compose up --build`.
- **Sintoma**: O `backend` tentava rodar o ETL antes de o PostgreSQL concluir os scripts de `/docker-entrypoint-initdb.d/`.
- **Como foi resolvido**: Configurado `healthcheck` no `docker-compose.yml` (`pg_isready -U postgres -d servidores`) combinado com `depends_on: db: condition: service_healthy` e o script `backend/etl/esperar_banco.py` (até 60 tentativas).

### ERR-006 — Prevenção de SQL Injection e Strings Inválidas
- **Contexto**: A avaliação exige resistência a tentativas de SQL Injection (`' OR 1=1 --`, `UNION SELECT`, `DROP TABLE`, `pg_sleep`), strings inválidas e parâmetros duplicados/desconhecidos.
- **Como foi resolvido** (Defesa em Profundidade em 3 níveis):
  1. **Validação estrita (`app/validacao.py`)**: Whitelist de parâmetros (`PARAMETROS_PERMITIDOS`), bloqueio de parâmetros repetidos, regex de caracteres permitidos por tipo de campo e detecção explícita de padrões SQL (`RE_SQL_INJECTION` retornando HTTP 400 `SQL_INJECTION_DETECTADA`).
  2. **Queries 100% parametrizadas (`app/consultas.py`)**: Nenhum valor vindo do usuário é interpolado na string SQL; todos passam por tuplas de parâmetros do Psycopg 3.
  3. **Usuário de banco restrito (`db/init/02_usuario_api.sh`)**: A API conecta exclusivamente com a role `api_leitura`, que possui apenas `SELECT` e `statement_timeout = '5s'`.

### ERR-007 — Corrupção de conexões do Pool com `preload_app = True` no Gunicorn
- **Contexto**: Uso do Gunicorn com múltiplos processos workers e threads (`worker_class = "gthread"`).
- **Sintoma**: Se o `ConnectionPool` do `psycopg_pool` for aberto no processo mestre antes do `fork()`, os processos filhos herdam os mesmos sockets TCP para o PostgreSQL, gerando colisão de pacotes no protocolo `libpq`.
- **Como foi resolvido**: Definido `preload_app = False` em `backend/gunicorn.conf.py` e inicialização preguiçosa (*lazy singleton* protegido por `threading.Lock`) em `backend/app/db.py`.

### ERR-008 — Lentidão de `COUNT(*)` em filtros de alta cardinalidade
- **Contexto**: Paginação de consultas amplas como `GET /api/servidores?uf=RJ`.
- **Sintoma**: No PostgreSQL (MVCC), `SELECT count(*) FROM servidor WHERE uf = 'RJ'` precisa verificar a visibilidade de dezenas de milhares de linhas antes de devolver a primeira página.
- **Como foi resolvido**: Contagem limitada a `MAX_RESULTADOS + 1` (`10.001`) usando subquery `SELECT count(*) FROM (SELECT 1 FROM servidor s WHERE ... LIMIT 10001) t`, reduzindo o tempo de resposta para poucos milissegundos e informando `total_exato: false` quando o teto é atingido. No `/api/saude`, usa-se a estimativa instantânea do catálogo (`pg_class.reltuples`).

### ERR-009 — Erro de sintaxe no `SET LOCAL statement_timeout = %s` com Psycopg 3
- **Contexto**: Aplicação de timeout por consulta em `backend/app/consultas.py`.
- **Sintoma**: `psycopg.errors.SyntaxError: syntax error at or near "$1"` ao executar `SET LOCAL statement_timeout = %s`.
- **Causa**: O Psycopg 3 usa *server-side binding* (`$1`) por padrão, e o comando `SET` do PostgreSQL não aceita parâmetros em prepared statements.
- **Como foi resolvido**: Substituído por `SELECT set_config('statement_timeout', %s, true)`, que é uma chamada de função SQL normal e aceita `$1`, aplicando o timeout apenas à transação atual (`is_local = true`).

### ERR-010 — Vazamento de descritor de arquivo ao ler CSV dentro de `.zip` (`WinError 32`)
- **Contexto**: Teste automatizado `test_leitura_csv_latin1_e_zip` em `backend/tests/test_etl.py` rodando no Windows.
- **Sintoma**: `PermissionError: [WinError 32] O arquivo já está sendo usado por outro processo: '.../pacote.zip'` ao sair do bloco `TemporaryDirectory()`.
- **Causa**: `zipfile.ZipFile(caminho).open(membro)` retorna um stream para o arquivo interno, mas quando `TextIOWrapper.close()` é chamado ao fim da importação, apenas o stream interno era fechado — o objeto `ZipFile` permanecia aberto bloqueando o arquivo no Windows.
- **Como foi resolvido**: Implementada a classe `_MembroZip(io.RawIOBase)` em `backend/etl/importar.py` cujo método `close()` fecha tanto o membro interno quanto o arquivo `.zip` subjacente.

### ERR-011 — Falso positivo de UTF-8 em amostras pequenas `cp1252` terminando em byte acentuado
- **Contexto**: Teste `test_codificacao_e_separador` com a string curta `"José".encode("cp1252")` (`b'Jos\xe9'`, 4 bytes).
- **Sintoma**: `detectar_codificacao(b'Jos\xe9')` retornava `'utf-8'` em vez de `'cp1252'`.
- **Causa**: A proteção contra corte de caractere UTF-8 multibyte no fim do buffer (`if exc.start >= len(amostra) - 3: return "utf-8"`) disparava mesmo quando o arquivo inteiro tinha menos de 64 KB (ou seja, não havia sido truncado na leitura da amostra).
- **Como foi resolvido**: Adicionado o parâmetro `truncada: bool = False` em `detectar_codificacao(amostra, truncada=len(amostra) == 65536)`, aplicando a tolerância de borda apenas quando a amostra atingiu o limite do buffer de 64 KB.

### ERR-012 — Proteção contra Colapso em Testes de Sobrecarga Paralela
- **Contexto**: Requisito 7 exige testes de sobrecarga paralela e mecanismos de segurança para evitar que o sistema trave.
- **Como foi resolvido**: Arquitetura em 4 camadas de contenção:
  1. **Nginx (`frontend/nginx.conf`)**: `limit_req_zone ... rate=20r/s` com `burst=40` e `limit_conn 30` por IP.
  2. **Rate Limiter por IP na API (`app/protecao.py`)**: Janela deslizante (`LimitadorTaxa`) retornando HTTP `429 Too Many Requests` + cabeçalho `Retry-After`.
  3. **Semáforo de Concorrência (`BoundedSemaphore`)**: Limita o número de consultas simultâneas por worker (`MAX_BUSCAS_SIMULTANEAS=8`), aguardando até `ESPERA_VAGA_S=2s` antes de rejeitar com HTTP `503 Service Unavailable` de forma limpa, sem travar o worker.
  4. **Pool de Conexões + Timeout no Banco**: `ConnectionPool` limitado (`DB_POOL_MAX=8` por worker × 4 workers = 32 conexões < `max_connections=100` do Postgres) e `statement_timeout = 5000ms` abortando queries lentas com HTTP `504 Gateway Timeout`.

### ERR-013 — Corrupção de crases Markdown (`backticks`) por interpolação do PowerShell no `README.md`
- **Contexto**: Geração do `README.md` inicial da Versão 1 via script PowerShell.
- **Sintoma**: No GitHub, palavras precedidas por crase como `` `backend` ``, `` `frontend` `` e `` ```bash `` apareciam corrompidas com símbolos `ackend`, `rontend` e `ash`.
- **Causa**: Em PowerShell, dentro de strings delimitadas por aspas duplas (`"..."` ou `@"..."@`), o caractere de crase (`` ` ``) funciona como caractere de escape: `` `b `` é convertido no byte ASCII `0x08` (*Backspace*) e `` `f `` no byte ASCII `0x0C` (*Form feed*).
- **Como foi resolvido**: Substituído o `README.md` por escrita direta em UTF-8 puro (sem interpolação do PowerShell) e atualizado no 2º commit.
- **Regra para próximos projetos**: No PowerShell, **nunca** usar `@"..."@` (aspas duplas) para gerar textos Markdown que contenham crases (`` ` ``) ou variáveis `$`; usar sempre here-strings literais `@'...'@` (aspas simples) ou escrita direta de arquivo.

### ERR-014 — App Desktop: widgets Tkinter acessados a partir de thread secundária
- **Sintoma**: `RuntimeError: main thread is not in main loop` ao ler `self.var_url.get()` dentro da thread que faz a requisição HTTP.
- **Causa**: Tkinter não é thread-safe; variáveis e widgets só podem ser lidos/alterados na thread principal.
- **Solução**: Ler a URL (`_base_url()`) e os filtros na thread principal, passar como argumento para `_chamar_api()` (agora `@staticmethod`, sem tocar em widgets) e devolver o resultado à interface somente via `self.after(0, ...)`.
- **Regra**: Em GUI (Tkinter/PyQt), threads de trabalho só fazem I/O; toda leitura/escrita de interface fica na thread principal.

### ERR-015 — App Desktop: popup de erro quebrava com `NameError` (variável `exc` apagada)
- **Sintoma**: Ao buscar algo inválido (ex.: SQL injection), o aviso da API não aparecia.
- **Causa**: `lambda: messagebox.showwarning(..., str(exc))` era executada depois pelo `after()`, mas o Python 3 **apaga** a variável do `except ... as exc` ao sair do bloco.
- **Solução**: Capturar a mensagem antes: `msg = str(exc)` e usar `lambda m=msg: ...` (argumento padrão congela o valor).
- **Regra**: Nunca referenciar a variável de exceção dentro de callbacks adiados; capture o valor em uma variável local.

### ERR-016 — App Desktop: respostas com ~2 s de atraso usando `localhost` no Windows
- **Sintoma**: Cada requisição demorava ~2 s; os resultados pareciam "atrasados" um clique.
- **Causa**: No Windows, `localhost` resolve primeiro para IPv6 (`::1`); como o servidor escuta só em IPv4, o cliente espera a falha do IPv6 antes de tentar `127.0.0.1`.
- **Solução**: URL padrão do app desktop alterada para `http://127.0.0.1:5000` (funciona também com o mapeamento de portas do Docker).
- **Regra**: Em clientes locais no Windows, preferir `127.0.0.1` a `localhost`.

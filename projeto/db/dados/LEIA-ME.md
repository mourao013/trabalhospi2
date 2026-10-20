# Pasta de dados (CSV do dados.gov.br)

Coloque aqui os arquivos baixados de:

- Gestão de Pessoas do Executivo Federal — **Aposentados**
  https://dados.gov.br/dados/conjuntos-dados/gestao-de-pessoas-executivo-federal--aposentados
- Gestão de Pessoas do Executivo Federal — **Carreiras/Cargos**
  https://dados.gov.br/dados/conjuntos-dados/gestao-de-pessoas-executivo-federal---carreiras--cargos

Aceita `.csv` ou `.zip` (com CSVs dentro), em qualquer subpasta.

## Como o ETL trata os arquivos

- **Codificação**: detecta UTF-8 ou Windows-1252/Latin-1 automaticamente.
- **Separador**: detecta `;`, `,`, `|` ou tab.
- **Cabeçalhos**: normaliza (minúsculo, sem acento) e mapeia por sinônimos
  (`NOME`, `DESCRICAO_CARGO`, `ORGAO_LOTACAO`, `UF_EXERCICIO`, ... ver
  `backend/etl/importar.py`, dicionário `SINONIMOS`).
- **Situação**: coluna de situação/vínculo, se existir; senão, arquivos com
  "aposent" no nome viram `APOSENTADO` e os demais `ATIVO`.
- Arquivos **sem coluna de nome** (ex.: só tabela de carreiras/cargos)
  alimentam só a tabela `cargo`.
- Cada arquivo é importado **uma vez só** (tabela `controle_importacao`).

## Sem arquivos?

Se a pasta estiver vazia, o ETL gera uma **amostra FICTÍCIA** (20.000
registros, `fonte = 'AMOSTRA_FICTICIA'`) para a aplicação poder ser testada.
Quando os CSVs reais forem adicionados, a amostra é apagada automaticamente.

> Os CSVs reais não vão para o GitHub (estão no `.gitignore`) por serem grandes.

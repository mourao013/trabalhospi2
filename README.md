# Sistema de Consulta de Servidores do Poder Executivo Federal (Em Desenvolvimento)

Estrutura base do projeto Full Stack modularizado com Docker (db-server, ackend Flask + Gunicorn, rontend Nginx/Web) e pipeline ETL para as bases do dados.gov.br (Aposentados e Carreiras/Cargos).

## Como subir os contêineres

`ash
cd projeto
docker compose up --build
`

## Próximas entregas (Sprint 2)
- Suíte de testes unitários e script de sobrecarga paralela (ackend/tests/ e ackend/scripts/)
- Aplicativo Desktop multi-plataforma em Python/Tkinter (projeto/desktop/)
- Relatório Final com gráfico de Burndown e Registro de Erros

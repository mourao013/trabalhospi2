FROM python:3.12-slim

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PIP_NO_CACHE_DIR=1

WORKDIR /app

COPY requirements.txt .
RUN pip install -r requirements.txt

COPY . .

# Evita erro "exec /app/entrypoint.sh: no such file or directory" causado por
# finais de linha CRLF quando o repositório é clonado no Windows (ERR-004).
RUN sed -i 's/\r$//' /app/entrypoint.sh && chmod +x /app/entrypoint.sh \
    && useradd --create-home --uid 1000 appuser && chown -R appuser /app
USER appuser

EXPOSE 5000

ENTRYPOINT ["/app/entrypoint.sh"]

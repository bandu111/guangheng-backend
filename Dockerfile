FROM python:3.11-slim-bookworm

ENV PYTHONUNBUFFERED=1 \
    PYTHONDONTWRITEBYTECODE=1 \
    PIP_DISABLE_PIP_VERSION_CHECK=1

WORKDIR /app

COPY requirements.txt ./
RUN pip install --no-cache-dir --timeout 120 --retries 5 -r requirements.txt

RUN groupadd --gid 10001 guangheng \
    && useradd --uid 10001 --gid guangheng --create-home --home-dir /home/guangheng guangheng \
    && mkdir -p /app/storage \
    && chown -R guangheng:guangheng /app /home/guangheng

COPY --chown=guangheng:guangheng app/ ./app/
COPY --chown=guangheng:guangheng config/ ./config/

USER guangheng

EXPOSE 8000

HEALTHCHECK --interval=30s --timeout=5s --start-period=10s --retries=3 \
    CMD ["python", "-c", "import urllib.request; urllib.request.urlopen('http://127.0.0.1:8000/health', timeout=3).read()"]

CMD ["uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8000", "--workers", "1"]

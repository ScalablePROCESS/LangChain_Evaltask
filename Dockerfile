FROM python:3.12-slim AS base

WORKDIR /app

# Dépendances système
RUN apt-get update && apt-get install -y --no-install-recommends \
    build-essential \
    curl \
    && rm -rf /var/lib/apt/lists/*

# Dépendances Python
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# Code applicatif
COPY . .

# Créer un utilisateur non privilégié et les répertoires de données
RUN useradd --system --uid 10001 --create-home appuser \
    && mkdir -p /app/data/chromadb /app/data/knowledge \
    && chown -R appuser:appuser /app

USER appuser

# Port
EXPOSE 8000

# Healthcheck (liveness)
HEALTHCHECK --interval=30s --timeout=5s --start-period=10s --retries=3 \
    CMD curl -sf http://localhost:8000/api/v1/health || exit 1

# Démarrage
CMD ["gunicorn", "app.main:app", \
     "-w", "4", \
     "-k", "uvicorn.workers.UvicornWorker", \
     "--bind", "0.0.0.0:8000", \
     "--timeout", "120", \
     "--access-logfile", "-"]

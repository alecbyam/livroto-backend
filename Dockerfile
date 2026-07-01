FROM python:3.12-slim

WORKDIR /app

# Dépendances système (PostgreSQL client + build tools)
RUN apt-get update && apt-get install -y \
    gcc \
    libpq-dev \
    curl \
    && rm -rf /var/lib/apt/lists/*

# Copier requirements en premier (cache Docker optimisé)
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# Copier le code
COPY . .

# Créer un utilisateur non-root (sécurité)
RUN adduser --disabled-password --gecos "" appuser && chown -R appuser /app
USER appuser

EXPOSE 8000

# Railway injecte $PORT automatiquement
CMD ["sh", "-c", "alembic upgrade head && uvicorn app.main:app --host 0.0.0.0 --port ${PORT:-8000} --workers 2 --log-level info"]

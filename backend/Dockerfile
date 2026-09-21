FROM python:3.14-slim

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1

WORKDIR /app

# Install dependencies first so this layer stays cached when only the code changes
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

COPY . .

# Run as a non-root user
RUN useradd --create-home appuser
USER appuser

EXPOSE 8000

# API keys and POSTGRES_DB come from the environment at run time, e.g. `docker run --env-file .env`
# Shell form, because hosts like Render assign the port through $PORT and exec form won't expand it
CMD uvicorn app:app --host 0.0.0.0 --port ${PORT:-8000}

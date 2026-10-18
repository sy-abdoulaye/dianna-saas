# Image unique : serveur web (Gunicorn) et, plus tard, travailleur de tâches (même image).

# --- Étape 1 : feuille de style Tailwind (binaire autonome, sans Node) ---
FROM debian:bookworm-slim AS css
RUN apt-get update && apt-get install -y --no-install-recommends curl ca-certificates make \
    && rm -rf /var/lib/apt/lists/*
WORKDIR /src
COPY Makefile ./
COPY static ./static
COPY templates ./templates
COPY apps ./apps
RUN make css-build

# --- Étape 2 : application ---
FROM python:3.13-slim AS app
ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    UV_COMPILE_BYTECODE=1 \
    UV_LINK_MODE=copy \
    UV_PROJECT_ENVIRONMENT=/opt/venv \
    PATH="/opt/venv/bin:$PATH" \
    DJANGO_SETTINGS_MODULE=config.settings.prod
COPY --from=ghcr.io/astral-sh/uv:0.13.1 /uv /usr/local/bin/uv
WORKDIR /app
COPY pyproject.toml uv.lock .python-version ./
RUN uv sync --frozen --no-dev --no-install-project
COPY . .
COPY --from=css /src/static/build ./static/build
RUN SECRET_KEY=build-only python manage.py collectstatic --noinput \
    && useradd --system --uid 1000 dianna && chown -R dianna /app
USER dianna
EXPOSE 8000
CMD ["gunicorn", "config.wsgi:application", "--bind", "0.0.0.0:8000", "--workers", "3", "--access-logfile", "-"]

# Dianna : commandes de développement. `make help` liste les cibles.
SHELL := /bin/bash
.DEFAULT_GOAL := help

UV ?= uv
RUN := $(UV) run
MANAGE := $(RUN) python manage.py

# Tailwind CSS : binaire autonome, version et sommes SHA-256 fixées (T-04).
TAILWIND_VERSION := v4.3.3
TAILWIND_SHA256_linux-x64 := dc61b3ac6b8c9ca874c0cc4c57b2409791a64c5540404ca5f5367360babc313a
TAILWIND_SHA256_linux-arm64 := 55fd0b241214eff3de1e8ee4f22796662f2d2e7a49bcfca7477cfd0bac398195
TAILWIND_SHA256_macos-x64 := 7922e0953f2110c05976e3bf58f14e643d90427575e766b7d433f5f80cbee7e1
TAILWIND_SHA256_macos-arm64 := cdf646702987a743464dff4d9c60fd4480d1c1e73dd819a9a67f1078815dce9d

UNAME_S := $(shell uname -s)
UNAME_M := $(shell uname -m)
TW_OS := $(if $(filter Darwin,$(UNAME_S)),macos,linux)
TW_ARCH := $(if $(filter arm64 aarch64,$(UNAME_M)),arm64,x64)
TW_PLATFORM := $(TW_OS)-$(TW_ARCH)
TAILWIND := bin/tailwindcss-$(TAILWIND_VERSION)-$(TW_PLATFORM)
CSS_IN := static/css/app.css
CSS_OUT := static/build/app.css

.PHONY: help install up down db css css-build migrate test cov e2e lint format seed shell check worker purge-tasks

help: ## Affiche cette aide
	@grep -E '^[a-z-]+:.*## ' $(MAKEFILE_LIST) | awk -F':.*## ' '{printf "  \033[1m%-10s\033[0m %s\n", $$1, $$2}'

install: $(TAILWIND) ## Installe les dépendances, le navigateur de test et le .env local
	$(UV) sync
	$(RUN) playwright install chromium
	@test -f .env || (cp .env.example .env && echo "Fichier .env créé depuis .env.example")
	$(RUN) pre-commit install

$(TAILWIND):
	@mkdir -p bin
	@echo "Téléchargement de Tailwind CSS $(TAILWIND_VERSION) ($(TW_PLATFORM))"
	@curl -fsSL -o $@.tmp https://github.com/tailwindlabs/tailwindcss/releases/download/$(TAILWIND_VERSION)/tailwindcss-$(TW_PLATFORM)
	@echo "$(TAILWIND_SHA256_$(TW_PLATFORM))  $@.tmp" | sha256sum -c --quiet - || (rm -f $@.tmp; echo "Somme de contrôle invalide"; exit 1)
	@chmod +x $@.tmp && mv $@.tmp $@

db: ## Démarre PostgreSQL 18 (Docker) et attend qu'il soit prêt
	docker compose up -d --wait db

up: db css-build migrate ## Démarre PostgreSQL et le serveur de développement (http://localhost:8000)
	$(MANAGE) runserver 0.0.0.0:8000

worker: ## Travailleur des tâches en arrière-plan (e-mails), dans un second terminal
	$(MANAGE) db_worker

purge-tasks: ## Purge des résultats de tâches (échecs de plus de 7 jours), chaque jour en production
	$(MANAGE) purge_task_results

down: ## Arrête PostgreSQL
	docker compose down

css: $(TAILWIND) ## Compile Tailwind en mode watch
	$(TAILWIND) -i $(CSS_IN) -o $(CSS_OUT) --watch

css-build: $(TAILWIND) ## Compile Tailwind une fois (minifié)
	$(TAILWIND) -i $(CSS_IN) -o $(CSS_OUT) --minify

migrate: ## Applique les migrations
	$(MANAGE) migrate

test: css-build ## Tests unitaires et d'intégration (pytest, sans les parcours e2e)
	$(RUN) pytest -m "not e2e" --cov --cov-report=term-missing:skip-covered

e2e: css-build ## Parcours de bout en bout Playwright
	$(RUN) pytest -m e2e tests/e2e

lint: ## ruff check, ruff format --check, djlint
	$(RUN) ruff check .
	$(RUN) ruff format --check .
	$(RUN) djlint templates --lint

format: ## Formate le code Python et les templates
	$(RUN) ruff check --fix .
	$(RUN) ruff format .

check: ## Vérifications Django (dont la configuration de production)
	$(MANAGE) check
	DJANGO_SETTINGS_MODULE=config.settings.prod SECRET_KEY=$$(python3 -c "import secrets; print(secrets.token_urlsafe(50))") MFA_ENCRYPTION_KEY=$$(python3 -c "import base64,os; print(base64.urlsafe_b64encode(os.urandom(32)).decode())") TASKS_ENCRYPTION_KEY=$$(python3 -c "import base64,os; print(base64.urlsafe_b64encode(os.urandom(32)).decode())") ALLOWED_HOSTS=example.com $(MANAGE) check --deploy --fail-level WARNING

seed: ## Charge l'entreprise de démonstration « Exemple SAS » (disponible au lot 1)
	@if $(MANAGE) help seed_demo >/dev/null 2>&1; then $(MANAGE) seed_demo; \
	else echo "La commande seed_demo arrive au lot 1 (docs/06-plan-de-livraison.md)."; exit 1; fi

shell: ## Shell Django
	$(MANAGE) shell

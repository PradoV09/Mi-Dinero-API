SHELL := /bin/bash
VENV := .venv
PY := $(VENV)/bin/python
PIP := $(VENV)/bin/pip
ALEMBIC := $(VENV)/bin/alembic

.DEFAULT_GOAL := help

.PHONY: help bootstrap up down reset-db migrate downgrade test psql logs backup restore

help:
	@echo "Mi Dinero - comandos disponibles:"
	@echo "  make bootstrap   Crea el venv, instala dependencias y copia .env si falta"
	@echo "  make up          Levanta Postgres y Mailpit"
	@echo "  make down        Detiene los contenedores"
	@echo "  make reset-db    Borra el volumen y recrea la base de datos (CONFIRM=yes)"
	@echo "  make migrate     Aplica migraciones de Alembic"
	@echo "  make downgrade   Revierte una migracion"
	@echo "  make test        Levanta la infra y corre pytest contra la BD de pruebas"
	@echo "  make psql        Abre una consola psql en el contenedor"
	@echo "  make logs        Muestra logs de los contenedores"
	@echo "  make backup      Exporta un dump de la BD a backups/"
	@echo "  make restore FILE=backups/archivo.dump  Restaura un dump"

bootstrap:
	test -d $(VENV) || python3 -m venv $(VENV)
	$(PIP) install --upgrade pip
	$(PIP) install -r requirements.txt
	test -f .env || cp .env.example .env
	@echo "Listo. Revisa .env con tus valores."

up:
	docker compose up -d --wait

down:
	docker compose down

reset-db:
	@test "$(CONFIRM)" = "yes" || (echo "Esto borra la base de datos. Usa: make reset-db CONFIRM=yes"; exit 1)
	docker compose down -v
	docker compose up -d --wait

migrate:
	$(ALEMBIC) upgrade head

downgrade:
	$(ALEMBIC) downgrade -1

test: up
	$(VENV)/bin/pytest

psql:
	docker compose exec postgres sh -c 'psql -U "$$POSTGRES_USER" -d "$$POSTGRES_DB"'

logs:
	docker compose logs -f

backup:
	@mkdir -p backups
	docker compose exec -T postgres sh -c 'pg_dump -U "$$POSTGRES_USER" -d "$$POSTGRES_DB" -Fc' \
		> backups/mi_dinero_$$(date +%Y%m%d_%H%M%S).dump
	@echo "Dump creado en backups/"

restore:
	@test -n "$(FILE)" || (echo "Usa: make restore FILE=backups/archivo.dump"; exit 1)
	docker compose exec -T postgres sh -c 'pg_restore -U "$$POSTGRES_USER" -d "$$POSTGRES_DB" --clean --if-exists --no-owner' < $(FILE)
	@echo "Restauracion completada"

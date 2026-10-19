# Mi Dinero - API

Backend de la app personal de finanzas (FastAPI / SQLAlchemy async / PostgreSQL).
Estado: **M1 - base de datos (PostgreSQL, SQLAlchemy async y Alembic)**.

Este repositorio contiene solo la API. El frontend (React + Vite) vive en un repositorio aparte.

## Requisitos
- Docker y Docker Compose
- Python 3.12+ (tambien puedes ejecutar la API en el contenedor)

## Puesta en marcha
    make bootstrap   # crea .venv, instala dependencias y copia .env.example a .env
    make up          # levanta Postgres (127.0.0.1:5433) y Mailpit (1025/8025)
    make migrate     # aplica migraciones de Alembic

Revisa `.env` antes de levantar la infraestructura (contiene credenciales ficticias de desarrollo).

## Ejecutar la API
    source .venv/bin/activate
    uvicorn app.main:app --reload --port 8000   # http://localhost:8000/health

## Produccion
- Web: `https://midinero.pradov.xyz`
- API: `https://api-midinero.pradov.xyz`

En el servidor define `FRONTEND_URL=https://midinero.pradov.xyz` y
`BACKEND_URL=https://api-midinero.pradov.xyz`. CORS solo permite el dominio web, y el correo
de produccion usa `EMAIL_PROVIDER=resend`.

## Pruebas
Los tests corren contra el PostgreSQL real del compose, usando la base de datos de pruebas
`mi_dinero_test` (definida en `TEST_DATABASE_URL`). No usan SQLite.

    make test

## Migraciones
    make migrate              # aplica todas las migraciones
    make downgrade            # revierte una migracion
    .venv/bin/alembic revision --autogenerate -m "descripcion"

## Infraestructura
- `postgres`: PostgreSQL 16, volumen nombrado, healthcheck, puerto `127.0.0.1:${POSTGRES_PORT}` (5433 por defecto).
- `mailpit`: SMTP en `127.0.0.1:1025`, interfaz web en http://127.0.0.1:8025. Se usara en M7.

### Backup y restauracion
    make backup                                   # crea backups/mi_dinero_<fecha>.dump
    make restore FILE=backups/mi_dinero_....dump  # restaura con --clean --if-exists

Los dumps usan formato custom (`pg_dump -Fc`) y `pg_restore` dentro del contenedor.
`backups/` esta en `.gitignore`.

### Reset de la base de datos
    make reset-db CONFIRM=yes   # elimina el volumen y recrea la base de datos y la de pruebas

## Docker de la API
`Dockerfile` es multi-stage, corre como usuario no root y esta pensado para desplegar en Railway.
El contexto de build es la raiz del repositorio:

    docker build -t mi-dinero-api .

## Estructura
    app/{api,core,db,models,schemas,services,repositories}
    alembic/                   migraciones
    tests/                     pruebas contra Postgres real
    docker/postgres/init/      creacion de la base de datos de pruebas
    docs/                      api-contract.md, security.md

## Variables de entorno
Ver `.env.example`. Principales: `DATABASE_URL`, `TEST_DATABASE_URL`, `POSTGRES_*`,
`SECRET_KEY`, `FIELD_ENCRYPTION_KEY`, `FRONTEND_URL`, `BACKEND_URL`, `EMAIL_PROVIDER`
(`smtp` en desarrollo, `resend` en produccion), `SMTP_HOST`, `SMTP_PORT`,
`EMAIL_PROVIDER_API_KEY`, `EMAIL_FROM`, `EMAIL_VERIFICATION_TTL_HOURS`.

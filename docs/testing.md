# Pruebas - Mi Dinero

## Como ejecutar
```bash
make test                                  # suite completa
.venv/bin/pytest tests/unit -q             # sin base de datos
.venv/bin/pytest tests/integration -q      # PostgreSQL real (mi_dinero_test)
.venv/bin/pytest --cov=app --cov-branch --cov-report=term-missing
```

`tests/integration` aplica `alembic upgrade head` sobre `TEST_DATABASE_URL` y trunca las
tablas entre pruebas. Nunca usa `DATABASE_URL`; `tests/integration/conftest.py` falla si la
URL de pruebas no contiene `test` o coincide con la principal.

## Taxonomia
- **`tests/unit`**: logica pura, sin base de datos (configuracion, dinero, cifrado, esquemas,
  modelo de moneda).
- **`tests/integration`**: endpoints, persistencia, aislamiento por usuario, migraciones,
  outbox y rate limiting contra PostgreSQL real. El proveedor de correo se sustituye por
  `MemoryEmailProvider`.

## Cobertura actual
- 103 pruebas, 93% de lineas/ramas (`--cov-branch`).
- `app/core/money.py`, `security.py`, `config.py` y todos los modelos: 100%.
- `app/api/v1/auth.py` y `accounts.py`: >90%.
- Sin cubrir: integraciones reales con SMTP/Resend (`app/services/email.py`), handlers de
  error no alcanzables por API y `app/db/session.py`.

## Pruebas de mutacion manuales (auditoria)
Se comprobo que las pruebas detectan regresiones reales:
- Quitar el validador de URL async en `config.py` -> falla `test_config.py`.
- Relajar el `CheckConstraint` de `minor_units` -> falla `test_currency_model.py`.
- Quitar el filtro `user_id` en `accounts` -> falla el test de aislamiento.
- Devolver el nombre sin cifrar en `accounts.name` -> falla el test de cifrado.

## Riesgos aceptados y pendientes
- **CORS permisivo**: `allow_origin_regex=r".*"` con `allow_credentials=True` (commit
  `dba0672`, decision del proyecto). Debe restringirse a `FRONTEND_URL` antes de produccion
  con cookies entre dominios.
- **Rate limiting por proceso**: no se comparte entre replicas.
- **Cookies `Secure`/`SameSite=None`**: configuracion validada, no probada en navegador real.
- **Integraciones de correo**: SMTP/Mailpit y Resend solo se probaron con el proveedor en
  memoria; falta una prueba de humo contra Mailpit.
- **Anti-enumeracion temporal**: se iguala el camino de login con un hash ficticio, pero no
  hay medicion estadistica de latencias.

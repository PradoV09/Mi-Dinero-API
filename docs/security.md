# Seguridad - Mi Dinero

Documento vivo. Describe que se protege, con que mecanismo y que no se cifra.

## Estado actual: M1 (base de datos e infraestructura)

### Implementado
- **Credenciales de base de datos**: solo por variables de entorno. `.env` esta en `.gitignore`;
  el repositorio solo contiene `.env.example` con valores ficticios.
- **Postgres**: el puerto se publica unicamente en `127.0.0.1` y usa un volumen nombrado.
- **Base de datos de pruebas separada** (`mi_dinero_test`) y validacion en `tests/conftest.py`
  de que los tests nunca apunten a la base de datos principal.
- **Logs de Alembic**: no imprimen la URL de conexion con credenciales (`sqlalchemy.url` se
  sustituye en `env.py` y no se registra).
- **Contenedor del backend** (opcional): usuario no root (`uid 10001`), imagen multi-stage.

### Exposicion de OpenAPI
- Por decision del proyecto, `/docs`, `/redoc` y `/openapi.json` estan habilitados en todos los
  entornos, incluida produccion. Esto expone el esquema de la API (rutas y modelos), no datos
  de usuarios. Si mas adelante se quiere restringir, se puede exigir autenticacion o desactivarlo
  con una variable de entorno.

### No implementado todavia (se abordara en M2+)
- Hash de contrasenas (argon2id).
- Tokens de confirmacion/reset/sesion (SHA-256, un solo uso, expiracion).
- Cifrado a nivel de aplicacion de `transactions.description` y `accounts.name`.
- Cookies de sesion `HttpOnly`, `Secure`, `SameSite` y proteccion CSRF.
- Rate limiting.
- HTTPS obligatorio en produccion.
- Filtrado de datos sensibles en logs.

## Que NO se cifra y por que

- **Importes, fechas, tipos de movimiento y correo**: no se cifran a nivel de aplicacion porque
  el sistema los agrega, filtra y busca en SQL (saldos, reportes, unicidad de correo). Cifrarlos
  romperia indices y agregaciones. El campo `email` es dato personal, pero se protege con
  controles de acceso, HTTPS en transito y minimizacion, no con cifrado de campo.
- **Claves**: `FIELD_ENCRYPTION_KEY` incluira un identificador de version para permitir rotacion.

## Manejo de claves
- `SECRET_KEY` y `FIELD_ENCRYPTION_KEY` viven en variables de entorno, nunca en el repositorio.
- `.env.example` contiene unicamente valores ficticios de desarrollo.

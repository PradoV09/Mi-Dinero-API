# Seguridad - Mi Dinero

Documento vivo. Describe que se protege, con que mecanismo y que no se cifra.

## Estado actual: M2 (autenticacion y sesiones)

### Implementado
- **Credenciales de base de datos**: solo por variables de entorno. `.env` esta en `.gitignore`;
  el repositorio solo contiene `.env.example` con valores ficticios.
- **Postgres**: el puerto se publica unicamente en `127.0.0.1` y usa un volumen nombrado.
- **Base de datos de pruebas separada** (`mi_dinero_test`) y validacion en `tests/conftest.py`
  de que los tests nunca apunten a la base de datos principal.
- **Logs de Alembic**: no imprimen la URL de conexion con credenciales (`sqlalchemy.url` se
  sustituye en `env.py` y no se registra).
- **Contenedor del backend** (opcional): usuario no root (`uid 10001`), imagen multi-stage.
- **Contrasenas**: `argon2id` con `time_cost=3`, `memory_cost=65536 KiB` (64 MiB),
  `parallelism=4`, `hash_len=32`, `salt_len=16` (`app/core/security.py`). Nunca se guardan en claro.
- **Tokens** (confirmacion, reset, sesion): generados con `secrets.token_urlsafe(32)`; en la
  base de datos solo se guarda `SHA-256` del token. Confirmacion y reset son de un solo uso y
  tienen expiracion. La sesion se revoca en servidor.
- **Registro sin cuenta prematura**: `pending_registrations` guarda el hash de la contrasena y
  el token; el usuario solo se crea al confirmar el correo.
- **Sesiones en servidor**: cookie opaca `mi_dinero_session` (`HttpOnly`); el token en claro
  solo vive en la cookie. Logout y reset de contrasena revocan sesiones de verdad.
- **CSRF**: double-submit. Cookie `mi_dinero_csrf` legible por JS + header `X-CSRF-Token`
  obligatorio en peticiones mutantes autenticadas (p. ej. logout).
- **Cookies**: `HttpOnly` para la sesion, `Secure` configurable (`COOKIE_SECURE`, poner `true`
  en produccion) y `SameSite` configurable (`COOKIE_SAMESITE`; `none` + `Secure` si web y API
  estan en dominios distintos).
- **Rate limiting** en registro, reenvio, login y recuperacion (memoria del proceso; ver riesgos).
- **Anti-enumeracion**: respuestas genericas identicas en registro y recuperacion; login usa
  el mismo mensaje y verifica un hash ficticio cuando el usuario no existe (igualar tiempos).
- **Outbox de correo**: el fallo del proveedor no rompe el registro; los envios quedan en
  `outbox_emails` con `attempts` y `last_error` para reintentar.
- **Correos**: SMTP/Mailpit en desarrollo; Resend en produccion (`EMAIL_PROVIDER=resend`).

### Exposicion de OpenAPI
- Por decision del proyecto, `/docs`, `/redoc` y `/openapi.json` estan habilitados en todos los
  entornos, incluida produccion. Esto expone el esquema de la API (rutas y modelos), no datos
  de usuarios. Si mas adelante se quiere restringir, se puede exigir autenticacion o desactivarlo
  con una variable de entorno.

### No implementado todavia
- Cifrado a nivel de aplicacion de `transactions.description` y `accounts.name` (Fase 2/3).
- HTTPS obligatorio en produccion (se configura en el proxy/hosting).
- Filtrado de datos sensibles en logs (revision pendiente; hoy no se registran cuerpos de auth).
- Rate limiting distribuido: el actual es por proceso; con varias replicas cada una tiene su
  propio contador.

## Que NO se cifra y por que

- **Importes, fechas, tipos de movimiento y correo**: no se cifran a nivel de aplicacion porque
  el sistema los agrega, filtra y busca en SQL (saldos, reportes, unicidad de correo). Cifrarlos
  romperia indices y agregaciones. El campo `email` es dato personal, pero se protege con
  controles de acceso, HTTPS en transito y minimizacion, no con cifrado de campo.
- **Claves**: `FIELD_ENCRYPTION_KEY` incluira un identificador de version para permitir rotacion.

## Manejo de claves
- `SECRET_KEY` y `FIELD_ENCRYPTION_KEY` viven en variables de entorno, nunca en el repositorio.
- `.env.example` contiene unicamente valores ficticios de desarrollo.

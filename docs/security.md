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
- **Cifrado de campos** (`app/core/crypto.py`): AES-256-GCM con nonce aleatorio de 12 bytes.
  El texto cifrado se guarda como `vN:<base64url(nonce||ciphertext)>`.
- **Rotacion de clave**: `FIELD_ENCRYPTION_KEY` acepta varias versiones separadas por coma;
  la primera es la actual (`v2:<clave>,v1:<clave>`). Se descifra con la version indicada en
  el prefijo, asi que rotar la clave no rompe datos existentes.
- **Unicidad de nombres cifrados**: como el nonce hace distinto cada cifrado, se guarda
  `name_fingerprint = HMAC-SHA256(SECRET_KEY, nombre_normalizado)` y un indice unico parcial
  en `(user_id, name_fingerprint) WHERE is_archived = false`. No se puede buscar por nombre en SQL.
  **`SECRET_KEY` debe permanecer estable**: rotarla cambia los fingerprints y rompe la deteccion
  de duplicados sobre cuentas existentes (el cifrado de campos no depende de ella).
- **Descripciones de movimientos**: `transactions.description` se cifra con el mismo AES-GCM.
  No se puede filtrar por texto de descripcion en SQL.
- **Idempotencia cifrada**: las respuestas guardadas en `idempotency_keys.response_body` se
  cifran (contenian descripciones descifradas e importes), se guardan 24 h y se eliminan con
  `purge_expired_idempotency_keys()`.
- **Aislamiento**: toda consulta de cuentas, categorias y movimientos filtra por `user_id` de
  la sesion; recursos ajenos responden 404. Las categorias del sistema (`user_id NULL`) son
  visibles para todos, las personalizadas solo para su dueno.

### Exposicion de OpenAPI
- Por decision del proyecto, `/docs`, `/redoc` y `/openapi.json` estan habilitados en todos los
  entornos, incluida produccion. Esto expone el esquema de la API (rutas y modelos), no datos
  de usuarios. Si mas adelante se quiere restringir, se puede exigir autenticacion o desactivarlo
  con una variable de entorno.

### No implementado todavia
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

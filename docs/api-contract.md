# Contrato de API - Mi Dinero

Base URL de negocio: `/api/v1`. Los endpoints de infraestructura (`/health`) no estan versionados.
OpenAPI esta disponible en `/docs`, `/redoc` y `/openapi.json` en todos los entornos.

## Convenciones

### Dinero
- Los importes se almacenan como `NUMERIC` en PostgreSQL y `Decimal` en Python. Nunca `float`.
- En JSON viajan como **string decimal**, por ejemplo `"12500.50"`.
- Cada moneda define `minor_units` en la tabla `currencies`. La aplicacion rechaza importes con
  mas decimales de los permitidos por la moneda; no redondea en silencio.

### Fechas
- `created_at` y `updated_at` son `TIMESTAMPTZ` en UTC (los genera la base de datos).
- `transaction_date` es un `DATE` interpretado en la zona `America/Bogota`.

### Formato de error
Todos los errores usan el mismo sobre:

```json
{
  "error": {
    "code": "account_not_found",
    "message": "La cuenta no existe",
    "details": []
  }
}
```

- `code`: identificador estable para el frontend.
- `message`: texto en espanol apto para el usuario.
- `details`: lista opcional (por ejemplo errores de validacion por campo).

Codigos HTTP usados: 401 (no autenticado), 404 (no encontrado o recurso ajeno),
409 (conflicto, por ejemplo cambio de moneda con movimientos), 422 (validacion),
429 (limite de intentos).

### Paginacion
Los listados aceptan `page` (1-based) y `page_size` (con maximo) y responden:

```json
{
  "items": [],
  "page": 1,
  "page_size": 20,
  "total": 0
}
```

### Autenticacion
- `user_id` proviene siempre de la sesion del servidor, nunca del cuerpo del request.
- Acceder a un recurso de otro usuario responde 404.

---

## Health

### GET /health
Verifica que el proceso responde. No consulta la base de datos.

**Request:** sin cuerpo ni parametros.

**Response 200**
```json
{ "status": "ok" }
```

**Errores:** ninguno esperado.

---

## Autenticacion (/api/v1/auth)

La sesion se transporta en una cookie **HttpOnly** llamada `mi_dinero_session`.
Las peticiones mutantes autenticadas requieren el header `X-CSRF-Token` con el
mismo valor de la cookie `mi_dinero_csrf` (double-submit). El cliente nunca lee
tokens de `localStorage`.

### POST /auth/register
Crea un registro **pendiente**; el usuario no existe hasta confirmar el correo.
La respuesta es identica exista o no el correo (anti-enumeracion).

**Request**
```json
{ "email": "ana@example.com", "name": "Ana", "password": "secreto123" }
```

**Response 202**
```json
{ "message": "Si el correo es valido, recibiras un mensaje para continuar." }
```

Errores: 422 (datos invalidos), 429 (limite de intentos).

### POST /auth/verify-email
Consume el token (un solo uso, expira segun `EMAIL_VERIFICATION_TTL_HOURS`) y
crea el usuario. No inicia sesion automaticamente.

**Request** `{ "token": "..." }` · **Response 201**
```json
{ "message": "Correo confirmado. Ya puedes iniciar sesion." }
```
Errores: 400 `invalid_token` / `expired_token`.

### POST /auth/resend-verification
**Request** `{ "email": "ana@example.com" }` · **Response 202** (mensaje generico).
Aplica cooldown (`RESEND_COOLDOWN_SECONDS`) y rate limit por correo/IP.

### POST /auth/login
**Request** `{ "email": "ana@example.com", "password": "secreto123" }`

**Response 200** (ademas fija `mi_dinero_session` y `mi_dinero_csrf`)
```json
{
  "id": "3f0f...",
  "email": "ana@example.com",
  "name": "Ana",
  "created_at": "2026-10-19T20:00:00Z"
}
```
Errores: 401 `invalid_credentials` (mismo mensaje si no existe, no esta confirmado
o la contrasena es incorrecta), 429.

### POST /auth/logout
Requiere sesion y `X-CSRF-Token`. Revoca la sesion en servidor y borra cookies.
**Response 200** `{ "message": "Sesion cerrada." }` · Errores: 401, 403 `csrf_failed`.

### GET /auth/me
Requiere sesion. **Response 200** igual a `UserResponse`. Errores: 401.

### POST /auth/forgot-password
**Request** `{ "email": "ana@example.com" }` · **Response 202** generico siempre.
Si la cuenta existe, encola un correo con token de un solo uso que expira segun
`PASSWORD_RESET_TTL_HOURS`.

### POST /auth/reset-password
**Request** `{ "token": "...", "new_password": "nuevaclave1" }`
Cambia la contrasena e invalida **todas** las sesiones activas del usuario.
**Response 200** `{ "message": "Contrasena actualizada. Inicia sesion de nuevo." }`
Errores: 400 `invalid_token` / `expired_token`, 422.

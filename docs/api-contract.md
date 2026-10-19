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

---

## Cuentas (/api/v1/accounts)

Todas las rutas requieren sesion. Las mutaciones (`POST`, `PATCH`) requieren ademas
`X-CSRF-Token`. Un `user_id` enviado en el cuerpo se rechaza con 422 (mass assignment).

### Modelo
- `name`: texto cifrado en reposo. La unicidad es **por usuario, solo entre cuentas
  activas** e **insensible a mayusculas/espacios** (`"Mi Cuenta"` == `"  mi   cuenta "`).
  Al archivar una cuenta su nombre puede reutilizarse.
- `account_type`: `bank`, `savings`, `debit_card`, `credit_card`, `digital_wallet`,
  `cash`, `other` (tabla `account_types`).
- `currency_code`: moneda activa (`COP`, `USD`, `EUR`).
- `opening_balance`: decimal como **string** con la escala de la moneda (COP/USD/EUR: 2).
  Solo `credit_card` admite valores negativos.
- `is_archived` / `archived_at`: el archivo es logico; conserva el historial.

### GET /accounts
Query: `include_archived` (bool, por defecto `false`), `page` (>=1), `page_size` (1..100,
por defecto 20). Orden: `created_at DESC, id DESC`.

**Response 200**
```json
{
  "items": [
    {
      "id": "3f0f...",
      "name": "Efectivo",
      "account_type": "cash",
      "currency_code": "COP",
      "opening_balance": "1000.00",
      "balance": "1500.00",
      "is_archived": false,
      "archived_at": null,
      "created_at": "2026-10-19T20:00:00Z",
      "updated_at": "2026-10-19T20:00:00Z"
    }
  ],
  "page": 1,
  "page_size": 20,
  "total": 1,
  "balances": [{ "currency_code": "COP", "balance": "1000.00" }]
}
```
`balance` es el saldo **calculado**: `opening_balance + ingresos - gastos` de los
movimientos de la cuenta (no se almacena, por lo que no puede desincronizarse).
`balances` agrupa por moneda y **siempre excluye cuentas archivadas**, aunque
`include_archived=true`.

### POST /accounts
**Request**
```json
{
  "name": "Efectivo",
  "account_type": "cash",
  "currency_code": "COP",
  "opening_balance": "1000.00"
}
```
**Response 201** igual al item de arriba. Errores: 409 `account_name_taken`,
422 `invalid_account_type` / `invalid_currency` / `invalid_amount_scale` /
`negative_opening_balance_not_allowed`, 403 `csrf_failed`.

### GET /accounts/{id}
**Response 200** item. Cuenta de otro usuario o inexistente: **404** `account_not_found`.

### PATCH /accounts/{id}
Campos permitidos: `name`, `account_type`, `currency_code` (todos opcionales; al menos uno).
**Response 200** item. Errores: 404, 409 `account_name_taken`,
409 `currency_change_not_allowed` si la cuenta ya tiene movimientos, 422.

### POST /accounts/{id}/archive
Idempotente: si ya estaba archivada responde 200 sin error. **Response 200** item con
`is_archived: true` y `archived_at`. Errores: 404, 403 `csrf_failed`.

---

## Categorias (/api/v1/categories)

Requieren sesion. `POST` requiere `X-CSRF-Token`.

### GET /categories
Query: `type` (`income`|`expense`, opcional), `page`, `page_size` (1..100, 20 por defecto).
Devuelve categorias del sistema (`is_system: true`) y las propias del usuario, ordenadas
por tipo y nombre. Un usuario nunca ve categorias personalizadas de otro.

**Response 200**
```json
{
  "items": [{ "id": "3f0f...", "name": "Salario", "type": "income", "is_system": true }],
  "page": 1,
  "page_size": 20,
  "total": 4
}
```

### POST /categories
**Request** `{ "type": "expense", "name": "Mascotas" }` · **Response 201** item con
`is_system: false`. Duplicado por tipo y nombre (sin distinguir mayusculas): 409
`category_name_taken`. Errores: 422, 403 `csrf_failed`.

---

## Movimientos (/api/v1/transactions)

Requieren sesion. `POST`, `PATCH` y `DELETE` requieren `X-CSRF-Token`.
`POST` y `PATCH` requieren ademas el header **`Idempotency-Key`** (1..128 caracteres).

### Modelo
- `type`: `income` (suma) o `expense` (resta). El importe siempre es positivo; el signo
  lo determina el tipo.
- `amount`: decimal como string, mayor que cero y con la escala de la moneda de la cuenta.
- `account_id`: cuenta propia y **no archivada** para crear o mover el movimiento.
- `category_id`: categoria del sistema o propia; su `type` debe coincidir con el movimiento.
- `currency_code`: se hereda de la cuenta (no se envia).
- `transaction_date`: `DATE` (`YYYY-MM-DD`), sin hora ni zona.
- `description`: opcional, maximo 500 caracteres, **cifrada en reposo**.

### GET /transactions
Filtros: `from` y `to` (inclusive), `account_id`, `category_id`, `type`, `page`,
`page_size` (1..100, 20 por defecto). Orden: `transaction_date DESC, created_at DESC, id DESC`.

**Response 200**
```json
{
  "items": [
    {
      "id": "3f0f...",
      "type": "expense",
      "account_id": "9a1e...",
      "category_id": "7b2c...",
      "category_name": "Alimentacion",
      "amount": "30.50",
      "currency_code": "COP",
      "transaction_date": "2026-10-15",
      "description": "Mercado",
      "created_at": "2026-10-19T20:00:00Z",
      "updated_at": "2026-10-19T20:00:00Z"
    }
  ],
  "page": 1,
  "page_size": 20,
  "total": 1
}
```
`from` mayor que `to`: 422 `invalid_date_range`.

### POST /transactions
**Request**
```json
{
  "type": "expense",
  "account_id": "9a1e...",
  "category_id": "7b2c...",
  "amount": "30.50",
  "transaction_date": "2026-10-15",
  "description": "Mercado"
}
```
**Response 201** item. Errores: 400 `idempotency_key_required` /
`invalid_idempotency_key`, 404 `account_not_found` / `category_not_found`,
409 `account_archived`, 422 `category_type_mismatch` / `invalid_amount_scale`.

### PATCH /transactions/{id}
Actualizacion parcial de `type`, `account_id`, `category_id`, `amount`,
`transaction_date` y `description` (admite `null` para borrarla). **Response 200** item.
Errores: 404 `transaction_not_found` / `account_not_found` / `category_not_found`,
409 `account_archived`, 422, 400 si falta `Idempotency-Key`.

### DELETE /transactions/{id}
Elimina el movimiento y el saldo se recalcula al consultar. **Response 204** sin cuerpo.
Errores: 404 `transaction_not_found`, 403 `csrf_failed`.

### Idempotencia
- Alcance por usuario; la clave se guarda 24 horas.
- Repetir la misma peticion (misma clave, mismo metodo, ruta y cuerpo) devuelve la
  respuesta original sin crear ni modificar nada.
- Misma clave con otro cuerpo/ruta: 409 `idempotency_key_reused`.
- Peticion simultanea con la misma clave: 409 `idempotency_key_in_progress`.
- Si la operacion falla, la clave no se consume y puede reintentarse.

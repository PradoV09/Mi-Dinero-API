# Contrato de API - Mi Dinero

Base URL de negocio: `/api/v1`. Los endpoints de infraestructura (`/health`) no estan versionados.
OpenAPI (`/docs`, `/openapi.json`, `/redoc`) solo esta disponible en desarrollo (`ENVIRONMENT=development`).

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

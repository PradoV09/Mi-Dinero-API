#!/bin/sh
set -eu

if [ -z "${POSTGRES_TEST_DB:-}" ]; then
    echo "POSTGRES_TEST_DB no esta definido; no se crea la base de datos de pruebas"
    exit 0
fi

echo "Creando base de datos de pruebas: ${POSTGRES_TEST_DB}"

psql -v ON_ERROR_STOP=1 --username "$POSTGRES_USER" --dbname "$POSTGRES_DB" --set=test_db="$POSTGRES_TEST_DB" <<'EOSQL'
SELECT 'CREATE DATABASE ' || quote_ident(:'test_db')
WHERE NOT EXISTS (SELECT FROM pg_database WHERE datname = :'test_db')\gexec
EOSQL

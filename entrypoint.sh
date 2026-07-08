#!/bin/sh
set -eu

ENV_FILE="/app/.env"

if [ ! -f "$ENV_FILE" ]; then
    SECRET_KEY="$(python3 -c 'import secrets; print(secrets.token_hex(32))')"
    cat > "$ENV_FILE" <<EOF
MYSQL_PASSWORD=
SECRET_KEY=$SECRET_KEY
ADMIN_PASSWORD=
EOF
fi

exec "$@"

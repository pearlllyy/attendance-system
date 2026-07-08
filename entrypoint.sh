#!/bin/sh
set -eu

ENV_FILE="/app/.env"

if [ ! -f "$ENV_FILE" ]; then
    SECRET_KEY="$(python3 -c 'import secrets; print(secrets.token_hex(32))')"
    cat > "$ENV_FILE" <<EOF
MYSQL_HOST=db
MYSQL_PASSWORD=
SECRET_KEY=$SECRET_KEY
ADMIN_PASSWORD=
EOF
fi

if ! grep -q '^MYSQL_HOST=' "$ENV_FILE"; then
    printf '\nMYSQL_HOST=db\n' >> "$ENV_FILE"
fi

DB_HOST="${MYSQL_HOST:-db}"
DB_PORT="${MYSQL_PORT:-3306}"

for _ in $(seq 1 60); do
    if python3 -c 'import socket, sys; socket.getaddrinfo(sys.argv[1], sys.argv[2])' "$DB_HOST" "$DB_PORT" >/dev/null 2>&1; then
        break
    fi
    sleep 2
done

exec "$@"

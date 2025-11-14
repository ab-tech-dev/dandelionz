#!/usr/bin/env bash
set -e

# helper to wait for a host:port
wait_for() {
  local host="$1"
  local port="$2"
  local retries=30
  local wait=2

  until nc -z "$host" "$port"; do
    retries=$((retries-1))
    if [ $retries -le 0 ]; then
      echo "Timeout waiting for $host:$port"
      return 1
    fi
    echo "Waiting for $host:$port..."
    sleep $wait
  done
  return 0
}

echo "Starting entrypoint..."

# load .env if present (only for local/dev; in container env_file is loaded by compose)
if [ -f .env ]; then
  export $(grep -v '^#' .env | xargs)
fi

# # Parse DB host and port from DATABASE_URL if available
# if [ -n "$DATABASE_URL" ]; then
#   # example DATABASE_URL: postgres://user:pass@db:5432/dbname
#   DB_HOST=$(echo "$DATABASE_URL" | sed -n 's/.*@\(.*\):.*/\1/p')
#   DB_PORT=$(echo "$DATABASE_URL" | sed -n 's/.*:\([0-9]*\)\/.*/\1/p')
# fi

# fallback defaults
DB_HOST=${DB_HOST:-db}
DB_PORT=${DB_PORT:-5432}
REDIS_HOST=${REDIS_HOST:-redis}
REDIS_PORT=${REDIS_PORT:-6379}

# Wait for DB and Redis
echo "Waiting for database at $DB_HOST:$DB_PORT"
wait_for "$DB_HOST" "$DB_PORT" || exit 1

echo "Waiting for redis at $REDIS_HOST:$REDIS_PORT"
wait_for "$REDIS_HOST" "$REDIS_PORT" || exit 1

# Run migrations & collectstatic (non-interactive)
echo "Running migrations..."
python manage.py makemigrations --noinput || true
python manage.py migrate --noinput

echo "Collecting static files..."
python manage.py collectstatic --noinput

# Optionally create a default superuser if envs set (no plain password in repo)
if [ -n "$DJANGO_SUPERUSER_USERNAME" ] && [ -n "$DJANGO_SUPERUSER_EMAIL" ] && [ -n "$DJANGO_SUPERUSER_PASSWORD" ] ; then
  echo "Creating superuser if not exists..."
  python manage.py shell -c "from django.contrib.auth import get_user_model; User=get_user_model(); \
  USERNAME='${DJANGO_SUPERUSER_USERNAME}'; EMAIL='${DJANGO_SUPERUSER_EMAIL}'; PASS='${DJANGO_SUPERUSER_PASSWORD}'; \
  u=User.objects.filter(username=USERNAME).first(); \
  (u or User.objects.create_superuser(USERNAME, EMAIL, PASS))"
fi

# Start the requested CMD (gunicorn typically)
echo "Starting process: $@"
exec "$@"

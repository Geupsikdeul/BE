#!/usr/bin/env sh
# Runs before the API starts (Dockerfile CMD): apply migrations, then seed initial data.
set -e

alembic upgrade head
python -m app.db.init_db

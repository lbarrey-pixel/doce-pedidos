#!/bin/sh
# Migrations (dono do schema), senha do papel da API, seed de demonstração e servidor.
set -e
alembic upgrade head
python -m scripts.preparar_banco
if [ "${DOCE_SEED:-1}" = "1" ]; then python -m scripts.seed; fi
exec uvicorn app.main:app_de_producao --factory --host 0.0.0.0 --port "${PORT:-8000}"

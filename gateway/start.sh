#!/usr/bin/env bash
# ─────────────────────────────────────────────────────
#  gateway/start.sh — Arranca el API Gateway
#  Puerto: 80  (EC2 pública, única expuesta a internet)
#
#  Este script va en la EC2 del gateway.
#  Las IPs de los otros servicios se ponen en .env.
# ─────────────────────────────────────────────────────
set -e

ENV_FILE="$(dirname "$0")/../.env"
if [ -f "$ENV_FILE" ]; then
  export $(grep -v '^#' "$ENV_FILE" | xargs)
  echo "✔  Variables cargadas desde .env"
else
  echo "⚠  No se encontró .env — usando valores por defecto"
fi

cd "$(dirname "$0")"

echo "──────────────────────────────────────────────────"
echo "  API GATEWAY — Puerto 80"
echo "  Ruteo:"
echo "    /catalogo/*   →  ${CATALOGO_URL:-http://localhost:4001}"
echo "    /carrito/*    →  ${CARRITO_URL:-http://localhost:4002}"
echo "    /ordenes/*    →  ${ORDENES_URL:-http://localhost:4003}"
echo "    /inventario/* →  ${ORDENES_URL:-http://localhost:4003}"
echo "──────────────────────────────────────────────────"

pip install -q -r requirements.txt

echo "▶  Iniciando gateway..."
exec uvicorn main:app \
  --host 0.0.0.0 \
  --port 80 \
  --log-level info

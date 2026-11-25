#!/usr/bin/env bash
# ─────────────────────────────────────────────────────
#  start.sh — Arranca los 3 servicios en la EC2
#  Uso: bash start.sh [catalogo|carrito|ordenes|all]
# ─────────────────────────────────────────────────────
set -e

# Cargar variables de entorno desde .env
if [ -f .env ]; then
  export $(grep -v '^#' .env | xargs)
fi

SERVICIO=${1:-all}

arrancar() {
  local nombre="Órdenes"
  local puerto=4003
  echo "Arrancando $nombre en puerto $puerto..."
  pip install -q -r requirements.txt
  uvicorn main:app --host 0.0.0.0 --port "$puerto" --reload &
  echo "   OK — http://0.0.0.0:$puerto/docs"
}

BASE="$(dirname "$0")"
cd "$BASE"

case $SERVICIO in
  catalogo)  arrancar "Catálogo"   8001 catalogo ;;
  carrito)   arrancar "Carrito"    8002 carrito  ;;
  ordenes)   arrancar "Órdenes"    8003 ordenes  ;;
  all)
    arrancar "Catálogo" 8001 catalogo
    arrancar "Carrito"  8002 carrito
    arrancar "Órdenes"  8003 ordenes
    echo ""
    echo "✅  Los 3 servicios están corriendo."
    echo "    Catálogo: http://localhost:8001/docs"
    echo "    Carrito:  http://localhost:8002/docs"
    echo "    Órdenes:  http://localhost:8003/docs"
    wait
    ;;
  *)
    echo "Uso: bash start.sh [catalogo|carrito|ordenes|all]"
    exit 1
    ;;
esac
